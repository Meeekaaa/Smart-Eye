import contextlib
import logging
import os
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait

import cv2

from backend.repository import db
from backend.models import model_loader
from utils import config
from backend.pipeline.liveness_manager import LivenessManager

logger = logging.getLogger(__name__)

_MAX_INFER_DIM = 768
_DEMO_VIDEO_EXTENSIONS = (".mp4", ".avi", ".mkv", ".mov", ".wmv", ".webm", ".m4v")


def _scale_frame(frame, max_dim=_MAX_INFER_DIM):
    h, w = frame.shape[:2]
    largest = max(h, w)
    if largest <= max_dim:
        return frame, 1.0
    scale = max_dim / largest
    return cv2.resize(frame, (int(w * scale), int(h * scale))), scale


def _scale_bbox_up(bbox, scale):
    if scale == 1.0:
        return bbox
    s = 1.0 / scale
    return [int(bbox[0] * s), int(bbox[1] * s), int(bbox[2] * s), int(bbox[3] * s)]


def _scale_points_up(points, scale):
    if not points:
        return None
    try:
        s = 1.0 / float(scale or 1.0)
        return [[float(p[0]) * s, float(p[1]) * s] for p in points if len(p) >= 2]
    except Exception:
        return None


def _iou(a, b):
    try:
        if not a or not b:
            return 0.0
        xA, yA = max(a[0], b[0]), max(a[1], b[1])
        xB, yB = min(a[2], b[2]), min(a[3], b[3])
        inter = max(0, xB - xA) * max(0, yB - yA)
        areaA = max(0, a[2] - a[0]) * max(0, a[3] - a[1])
        areaB = max(0, b[2] - b[0]) * max(0, b[3] - b[1])
        denom = float(areaA + areaB - inter)
        return inter / denom if denom > 0 else 0.0
    except Exception:
        return 0.0


def _as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _bbox_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _bbox_width_height(box):
    return max(1.0, float(box[2] - box[0])), max(1.0, float(box[3] - box[1]))


def _bbox_size(box):
    return max(1.0, float(box[2] - box[0]), float(box[3] - box[1]))


def _box_area(box):
    try:
        return max(0.0, float(box[2] - box[0])) * max(0.0, float(box[3] - box[1]))
    except Exception:
        return 0.0


def _box_intersection_area(a, b):
    try:
        x1 = max(float(a[0]), float(b[0]))
        y1 = max(float(a[1]), float(b[1]))
        x2 = min(float(a[2]), float(b[2]))
        y2 = min(float(a[3]), float(b[3]))
        return max(0.0, x2 - x1) * max(0.0, y2 - y1)
    except Exception:
        return 0.0


def _class_name_key(value):
    return str(value or "").strip().lower().replace("_", " ").replace("-", " ")


def _is_demo_stream_source(source, *, http_as_live: bool = False) -> bool:
    text = str(source or "").strip().lower()
    if not text:
        return False
    if "twitch.tv/" in text or "www.twitch.tv/" in text:
        return True
    if http_as_live and text.startswith(("http://", "https://")):
        return True
    return text.endswith(_DEMO_VIDEO_EXTENSIONS)


def _face_linked_to_person_box(person_box, face_box):
    if not person_box or not face_box:
        return False
    pcx1, pcy1, pcx2, pcy2 = [float(v) for v in person_box]
    fcx, fcy = _bbox_center(face_box)
    face_area = max(1.0, _box_area(face_box))
    face_inside = pcx1 <= fcx <= pcx2 and pcy1 <= fcy <= pcy2
    face_overlap = _box_intersection_area(person_box, face_box) / face_area
    return face_inside or face_overlap >= 0.35


def _box_from_center(cx, cy, w, h):
    return [float(cx) - (float(w) / 2.0), float(cy) - (float(h) / 2.0), float(cx) + (float(w) / 2.0), float(cy) + (float(h) / 2.0)]


def _shift_bbox(box, dx, dy):
    return [float(box[0]) + dx, float(box[1]) + dy, float(box[2]) + dx, float(box[3]) + dy]


def _clip_bbox_to_shape(box, frame_shape):
    try:
        if frame_shape is None:
            return [int(round(v)) for v in box]
        h, w = frame_shape[:2]
        x1 = max(0.0, min(float(w - 1), float(box[0])))
        y1 = max(0.0, min(float(h - 1), float(box[1])))
        x2 = max(0.0, min(float(w - 1), float(box[2])))
        y2 = max(0.0, min(float(h - 1), float(box[3])))
        if x2 - x1 < 2.0 or y2 - y1 < 2.0:
            return None
        return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]
    except Exception:
        return None


def _match_score(prev_box, curr_box, vx=0.0, vy=0.0):
    if not prev_box or not curr_box:
        return -1.0, 0.0, 999.0

    predicted = _shift_bbox(prev_box, _as_float(vx), _as_float(vy))
    iou_raw = _iou(prev_box, curr_box)
    iou_pred = _iou(predicted, curr_box)
    iou_best = max(iou_raw, iou_pred)

    pcx, pcy = _bbox_center(predicted)
    ccx, ccy = _bbox_center(curr_box)
    rel_dist = ((pcx - ccx) ** 2 + (pcy - ccy) ** 2) ** 0.5 / _bbox_size(curr_box)

    score = (iou_best * 1.15) - (rel_dist * 0.12)
    return score, iou_best, rel_dist


class DetectorManager:
    def __init__(self):
        self._face_model = None
        self._plugin_models = {}
        self._plugin_models_lock = threading.Lock()
        self._camera_plugins = {}
        self._initialized = False
        self._init_lock = threading.Lock()
        self._camera_plugins_lock = threading.Lock()
        self._camera_states = {}
        self._camera_states_lock = threading.Lock()
        self._camera_threshold_cache = {}
        self._camera_threshold_cache_lock = threading.Lock()
        self._camera_settings_cache = {}
        self._camera_settings_cache_lock = threading.Lock()

        self._cam_plugin_classes_cache = {}
        self._cam_plugin_classes_cache_lock = threading.Lock()

        try:
            self._identify_cooldown = int(config.get("identify_cooldown_frames", 6) or 6)
        except Exception:
            self._identify_cooldown = 6

        try:
            max_threads = int(config.get("max_cpu_cores", None) or config.get("max_threads", None) or 0)
        except Exception:
            max_threads = 0

        if max_threads > 0:
            workers = max(1, max_threads)
        else:
            workers = max(1, min(2, (os.cpu_count() or 2) // 2))

        self._executor_workers = workers
        self._executor_lock = threading.Lock()
        self._executor = ThreadPoolExecutor(max_workers=workers, thread_name_prefix="det-worker")
        # Per-camera liveness/motion challenge manager
        try:
            self._liveness = LivenessManager()
        except Exception:
            self._liveness = None

    def _recreate_executor(self):
        with self._executor_lock:
            self._executor = ThreadPoolExecutor(max_workers=self._executor_workers, thread_name_prefix="det-worker")

    @staticmethod
    def _make_failed_future(exc: Exception):
        fut = Future()
        fut.set_exception(exc)
        return fut

    def _submit_executor_task(self, fn, *args):
        if sys.is_finalizing():
            return self._make_failed_future(RuntimeError("interpreter shutdown"))

        with self._executor_lock:
            executor = self._executor
        try:
            return executor.submit(fn, *args)
        except RuntimeError as exc:
            msg = str(exc).lower()
            if sys.is_finalizing() or "interpreter shutdown" in msg:
                logger.info("Skipping detector executor task submit during interpreter shutdown")
                return self._make_failed_future(exc)
            if "cannot schedule new futures after shutdown" not in msg:
                raise
            logger.warning("Detector executor was shut down unexpectedly; recreating it", exc_info=True)
            try:
                self._recreate_executor()
                with self._executor_lock:
                    return self._executor.submit(fn, *args)
            except RuntimeError as exc2:
                msg2 = str(exc2).lower()
                if "cannot schedule new futures after shutdown" in msg2 or "interpreter shutdown" in msg2:
                    logger.info("Skipping detector executor task submit while executor is shutting down")
                    return self._make_failed_future(exc2)
                raise

    class _CameraState:
        def __init__(self):
            self.frame_counter = 0
            self.counter_lock = threading.Lock()
            self.trackers = []
            self.trackers_lock = threading.Lock()
            self.smoothing_state = {"faces": [], "objects": []}
            self.smoothing_lock = threading.Lock()

    def _get_camera_state(self, camera_id):
        with self._camera_states_lock:
            state = self._camera_states.get(camera_id)
            if state is None:
                state = self._CameraState()
                self._camera_states[camera_id] = state
            return state

    def clear_camera_state(self, camera_id=None):
        with self._camera_states_lock:
            if camera_id is None:
                self._camera_states.clear()
            else:
                self._camera_states.pop(camera_id, None)

    def initialize(self):
        with self._init_lock:
            if self._initialized:
                return
            try:
                self._face_model = model_loader.load_face_model_async()
            except Exception:
                logger.warning("Failed to load face model", exc_info=True)
                self._face_model = None
            self._reload_plugins()
            self._initialized = True

    def ensure_initialized(self):
        if not self._initialized:
            self.initialize()

    def reload(self):
        with self._init_lock:
            self._initialized = False
        config.invalidate_cache()
        self.initialize()

    def _reload_plugins(self):
        try:
            enabled_rows = db.get_plugins(enabled_only=True)
        except Exception:
            logger.warning("Failed to fetch enabled plugins", exc_info=True)
            return

        assigned_enabled = set()
        for p in enabled_rows:
            try:
                if db.get_plugin_cameras(p["id"]):
                    assigned_enabled.add(p["id"])
            except Exception:
                logger.debug("Failed to check cameras for plugin %s", p.get("id"), exc_info=True)

        if not assigned_enabled:
            assigned_enabled = {p.get("id") for p in enabled_rows if p.get("id") is not None}

        try:
            loaded = set(model_loader.get_loaded_plugins().keys())
            for pid in loaded - assigned_enabled:
                try:
                    model_loader.unload_plugin(pid)
                except Exception:
                    logger.debug("Failed to unload plugin %s", pid, exc_info=True)
        except Exception:
            logger.debug("Failed to get loaded plugins", exc_info=True)

        with self._plugin_models_lock:
            self._plugin_models.clear()
            for p in enabled_rows:
                pid = p.get("id")
                if pid not in assigned_enabled:
                    continue
                try:
                    model = model_loader.load_plugin(p)
                    if model is not None:
                        self._plugin_models[pid] = {
                            "model": model,
                            "info": p,
                            "classes": db.get_plugin_classes(pid),
                        }
                except Exception:
                    logger.exception("Failed to load plugin %s (%s)", pid, p.get("name"))

    def get_plugins_for_camera(self, camera_id):
        with self._camera_plugins_lock:
            if camera_id not in self._camera_plugins:
                cp = db.get_camera_plugins(camera_id)
                explicit = False
                try:
                    explicit = db.get_bool(f"camera_{camera_id}_plugins_explicit", False)
                except Exception:
                    explicit = False
                if explicit:
                    # Explicit assignment mode: trust camera-specific list (including empty list).
                    self._camera_plugins[camera_id] = [p["id"] for p in cp] if cp else []
                elif cp:
                    self._camera_plugins[camera_id] = [p["id"] for p in cp]
                else:
                    with self._plugin_models_lock:
                        self._camera_plugins[camera_id] = list(self._plugin_models.keys())
            return list(self._camera_plugins[camera_id])

    def invalidate_camera_cache(self, camera_id=None):
        with self._camera_plugins_lock:
            if camera_id:
                self._camera_plugins.pop(camera_id, None)
            else:
                self._camera_plugins.clear()

    def _make_tracker(self):
        _factories = []
        for _names in (
            ("legacy", "TrackerCSRT_create"),
            (None, "TrackerCSRT_create"),
            ("legacy", "TrackerKCF_create"),
            (None, "TrackerKCF_create"),
        ):
            try:
                module, attr = _names
                if module:
                    _factories.append(getattr(getattr(cv2, module), attr))
                else:
                    _factories.append(getattr(cv2, attr))
            except AttributeError:
                pass
        for factory in _factories:
            try:
                return factory()
            except Exception:
                continue
        return None

    def _read_frame_settings(self):
        try:
            detection_interval = int(config.get("detection_interval", 2) or 2)
        except Exception:
            detection_interval = 2

        aggressive_mode = False
        for key in ("aggressive_perf_mode", "smoothing_enabled", "experimental_smoothing"):
            val = config.get(key, None)
            if val is not None:
                if isinstance(val, str):
                    aggressive_mode = val.strip().lower() in ("1", "true", "yes")
                else:
                    aggressive_mode = bool(val)
                break

        if aggressive_mode:
            try:
                detection_interval = int(config.get("aggressive_detection_interval", 5) or 5)
            except Exception:
                detection_interval = max(detection_interval, 5)

        try:
            max_identify = int(config.get("aggressive_max_identify_per_frame", 2) or 2)
        except Exception:
            max_identify = 2

        try:
            max_trackers = int(config.get("max_trackers_per_cam", 32) or 32)
        except Exception:
            max_trackers = 32

        return detection_interval, aggressive_mode, max_identify, max_trackers

    def _scale_for_mode(self, frame, aggressive_mode):
        if aggressive_mode:
            try:
                max_dim = int(config.get("aggressive_max_infer_dim", 480) or 480)
            except Exception:
                max_dim = 480
            return _scale_frame(frame, max_dim=max_dim)
        try:
            max_dim = int(config.get("detector_max_infer_dim", _MAX_INFER_DIM) or _MAX_INFER_DIM)
        except Exception:
            max_dim = _MAX_INFER_DIM
        return _scale_frame(frame, max_dim=max(320, min(1024, max_dim)))

    def _run_face_detection(self, camera_id, small, scale):
        t0 = time.time()
        faces = self._face_model.detect_faces(small)
        try:
            min_face_size = int(db.get_setting(f"camera_{camera_id}_min_face_size", None) or 0)
            if min_face_size <= 0:
                min_face_size = int(config.get("min_face_size", 24) or 24)
        except Exception:
            min_face_size = 24
        results = []
        for face in faces:
            face["bbox"] = _scale_bbox_up(face["bbox"], scale)
            landmarks = _scale_points_up(face.get("landmarks"), scale)
            try:
                x1, y1, x2, y2 = face["bbox"]
                if (x2 - x1) < min_face_size or (y2 - y1) < min_face_size:
                    continue
            except Exception:
                continue
            result = {
                "bbox": face["bbox"],
                "det_score": face.get("det_score", 1.0),
                "identity": None,
                # Keep confidence numeric for downstream ranking/aggregation paths.
                "confidence": float(face.get("det_score", 0.0) or 0.0),
                "embedding": face.get("embedding"),
                "liveness": None,
                "gender": face.get("gender", "unknown"),
                "gender_confidence": face.get("gender_confidence", 0.0),
            }
            if landmarks:
                result["landmarks"] = landmarks
            results.append(result)
        return results, (time.time() - t0) * 1000

    def _run_plugin(self, pid, small, scale, camera_id):
        with self._plugin_models_lock:
            entry = self._plugin_models.get(pid)
        if entry is None:
            return [], 0.0
        model = entry["model"]

        global_classes = {int(c.get("class_index")): c for c in entry.get("classes", [])}

        cam_over = []
        try:
            cam_over = self._get_camera_plugin_classes_cached(camera_id, pid) or []
        except Exception:
            cam_over = []
        overrides = {int(r.get("class_index")): r for r in cam_over}

        plugin_conf = entry.get("info", {}).get("confidence", 0.5)
        try:
            tracker_low_abs = max(0.01, min(1.0, float(config.get("object_tracker_low_confidence", 0.10) or 0.10)))
        except Exception:
            tracker_low_abs = 0.10
        try:
            tracker_low_ratio = max(0.05, min(1.0, float(config.get("object_tracker_low_confidence_ratio", 0.45) or 0.45)))
        except Exception:
            tracker_low_ratio = 0.45
        try:
            new_track_floor = max(0.01, min(1.0, float(config.get("object_tracker_new_track_confidence", 0.35) or 0.35)))
        except Exception:
            new_track_floor = 0.35

        def _effective_class_conf(cls_index):
            effective = dict(global_classes.get(int(cls_index), {}))
            if int(cls_index) in overrides:
                over = overrides[int(cls_index)]
                try:
                    effective["enabled"] = int(over.get("enabled", effective.get("enabled", 1)))
                except Exception:
                    effective["enabled"] = effective.get("enabled", 1)
                if over.get("confidence") is not None:
                    effective["confidence"] = over.get("confidence")

            if effective.get("enabled", 1) in (0, "0", False):
                return None

            class_conf = effective.get("confidence")
            if class_conf is None:
                try:
                    class_conf = float(entry.get("info", {}).get("confidence", plugin_conf))
                except Exception:
                    class_conf = plugin_conf
            try:
                return max(0.0, min(1.0, float(class_conf)))
            except Exception:
                return max(0.0, min(1.0, float(plugin_conf or 0.5)))

        class_low_thresholds = []
        for cls_idx, cls_row in global_classes.items():
            try:
                if cls_row.get("enabled", 1) in (0, "0", False) and cls_idx not in overrides:
                    continue
                class_conf = _effective_class_conf(cls_idx)
            except Exception:
                class_conf = None
            if class_conf is None:
                continue
            class_low_thresholds.append(max(0.01, min(tracker_low_abs, class_conf * tracker_low_ratio)))
        if not class_low_thresholds:
            try:
                class_low_thresholds.append(max(0.01, min(tracker_low_abs, float(plugin_conf) * tracker_low_ratio)))
            except Exception:
                class_low_thresholds.append(tracker_low_abs)
        model_min_conf = min(class_low_thresholds)

        t0 = time.time()
        try:
            detections = model.detect(small, min_conf=model_min_conf) or []
        except TypeError:
            detections = model.detect(small) or []

        logger.debug("Plugin %s raw detections: %d", pid, len(detections))

        filtered = []

        for det in detections:
            try:
                det["bbox"] = _scale_bbox_up(det["bbox"], scale)
            except Exception:
                logger.debug("Skipping detection with bad bbox in plugin %s", pid, exc_info=True)
                continue

            cls = det.get("class") if det.get("class") is not None else det.get("class_id")
            try:
                cls = int(cls)
            except Exception:
                continue

            class_conf = _effective_class_conf(cls)
            if class_conf is None:
                continue

            track_low_conf = max(0.01, min(tracker_low_abs, float(class_conf) * tracker_low_ratio))
            det_conf = float(det.get("confidence", 0.0) or 0.0)
            if det_conf < track_low_conf:
                continue

            det["plugin_id"] = pid
            det["plugin_name"] = entry.get("info", {}).get("name")
            det["class"] = cls
            det["class_name"] = det.get("class_name") or global_classes.get(cls, {}).get("class_name") or str(cls)
            det["det_score"] = det_conf
            det["_track_low_conf"] = det_conf < float(class_conf)
            det["_display_confidence_threshold"] = float(class_conf)
            det["_new_track_confidence_threshold"] = max(float(class_conf), new_track_floor)
            det["_track_low_confidence_threshold"] = float(track_low_conf)
            filtered.append(det)

        logger.debug("Plugin %s filtered detections: %d", pid, len(filtered))
        return filtered, (time.time() - t0) * 1000

    def _get_camera_plugin_classes_cached(self, camera_id, plugin_id, ttl=2.0):
        key = (camera_id, plugin_id)
        now = time.time()
        with self._cam_plugin_classes_cache_lock:
            entry = self._cam_plugin_classes_cache.get(key)
            if entry and (now - entry[0] < ttl):
                return entry[1]
        try:
            data = db.get_camera_plugin_classes(camera_id, plugin_id)
        except Exception:
            data = []
        with self._cam_plugin_classes_cache_lock:
            self._cam_plugin_classes_cache[key] = (now, data)
        return data

    def _submit_inference_futures(self, camera_id, small, scale, plugin_ids, face_enabled):
        futures = {}
        if face_enabled and self._face_model and self._face_model.is_loaded:
            futures["faces"] = self._submit_executor_task(self._run_face_detection, camera_id, small, scale)
        for pid in plugin_ids:
            with self._plugin_models_lock:
                entry = self._plugin_models.get(pid)
            if entry and entry["model"].is_loaded:
                futures[f"obj_{pid}"] = self._submit_executor_task(self._run_plugin, pid, small, scale, camera_id)
        return futures

    def _collect_futures(self, futures):
        faces, objects, face_ms, obj_ms = [], [], 0.0, 0.0
        if not futures:
            return faces, objects, face_ms, obj_ms
        try:
            timeout_s = max(0.2, float(config.get("inference_future_timeout_sec", 2.0) or 2.0))
        except Exception:
            timeout_s = 2.0
        done, not_done = wait(list(futures.values()), timeout=timeout_s)
        for fut in not_done:
            fut.cancel()
        for key, fut in futures.items():
            if fut not in done:
                logger.warning("Inference future timed out for key %s after %.2fs", key, timeout_s)
                continue
            try:
                data, ms = fut.result(timeout=0)
                if key == "faces":
                    faces = data
                    face_ms = ms
                else:
                    objects.extend(data)
                    obj_ms += ms
            except Exception as e:
                logger.warning("Inference future failed for key %s: %s", key, e, exc_info=True)
        return faces, objects, face_ms, obj_ms

    def _identify_faces(self, camera_id, faces, existing_trackers, aggressive_mode, max_identify, small, frame_idx):
        identifies_used = 0
        identify_cooldown = max(1, int(self._identify_cooldown or 1))
        existing_face_trackers = [ent for ent in existing_trackers if ent.get("type") == "face"]
        for f in faces:
            if f.get("identity"):
                continue

            try:
                if f.get("confidence") is None:
                    f["confidence"] = float(f.get("det_score", 0.0) or 0.0)
            except Exception:
                f["confidence"] = 0.0

            best, best_iou, best_rel, best_score = None, 0.0, 999.0, -1e9
            for ent in existing_face_trackers:
                eb = ent.get("bbox")
                fb = f.get("bbox")
                if not eb or not fb:
                    continue
                score, iou, rel = _match_score(eb, fb, ent.get("vx", 0.0), ent.get("vy", 0.0))
                if score > best_score:
                    best, best_iou, best_rel, best_score = ent, iou, rel, score

            if best and best.get("identity") and (best_iou >= 0.28 or best_rel <= 1.10):
                f["identity"] = best.get("identity")
                f["confidence"] = best.get("confidence")
                try:

                    det_conf = float(f.get("det_score", 0.0) or 0.0)
                    if det_conf > 0.0:
                        prev_conf = float(f.get("confidence", 0.0) or 0.0)
                        f["confidence"] = max(0.0, min(1.0, (prev_conf * 0.65) + (det_conf * 0.35)))
                except Exception:
                    pass
                curr_embedding = f.get("embedding")
                if curr_embedding is None:
                    curr_embedding = best.get("embedding")
                f["embedding"] = curr_embedding
                f["liveness"] = best.get("liveness", 1.0)
                f["gender"] = f.get("gender") or best.get("gender", "unknown")
                f["gender_confidence"] = max(float(f.get("gender_confidence", 0.0)), float(best.get("gender_confidence", 0.0)))

                try:
                    last_identify_frame = int(best.get("last_identify_frame", -1) or -1)
                except Exception:
                    last_identify_frame = -1
                f["last_identify_frame"] = last_identify_frame

                should_refresh = (
                    self._face_model
                    and self._face_model.is_loaded
                    and f.get("embedding") is not None
                    and (frame_idx - last_identify_frame) >= identify_cooldown
                )

                if not should_refresh:
                    continue

                if aggressive_mode and identifies_used >= max_identify:
                    continue

            if aggressive_mode and identifies_used >= max_identify:
                continue

            if self._face_model and self._face_model.is_loaded and f.get("embedding") is not None:
                try:
                    cam_thresh = None
                    with contextlib.suppress(Exception):
                        cam_thresh = self._get_camera_threshold_cached(camera_id)
                    idinfo, score = self._face_model.identify(f.get("embedding"), threshold=cam_thresh)
                    f["identity"] = idinfo
                    f["confidence"] = score
                    # Liveness evaluation moved to post-smoothing stage to
                    # avoid resets from jitter/building of trackers.
                    f["last_identify_frame"] = frame_idx
                    identifies_used += 1
                except Exception:
                    logger.debug("Identify failed for face in camera %s", camera_id, exc_info=True)

    def identify_faces_lightweight(self, camera_id, faces):
        """Attach known-face identities without running tracking or liveness paths."""
        if not faces or not self._face_model or not self._face_model.is_loaded:
            return faces
        cam_thresh = None
        with contextlib.suppress(Exception):
            cam_thresh = self._get_camera_threshold_cached(camera_id)
        for face in faces:
            if not isinstance(face, dict) or face.get("identity") or face.get("embedding") is None:
                continue
            try:
                idinfo, score = self._face_model.identify(face.get("embedding"), threshold=cam_thresh)
                face["identity"] = idinfo
                if idinfo:
                    face["confidence"] = score
            except Exception:
                logger.debug("Playback identify failed for camera %s", camera_id, exc_info=True)
        return faces

    def _get_camera_threshold_cached(self, camera_id, ttl=2.0):
        now = time.time()
        with self._camera_threshold_cache_lock:
            entry = self._camera_threshold_cache.get(camera_id)
            if entry and (now - entry[0] < ttl):
                return entry[1]
        try:
            val = db.get_camera_face_threshold(camera_id)
        except Exception:
            val = None
        with self._camera_threshold_cache_lock:
            self._camera_threshold_cache[camera_id] = (now, val)
        return val

    def _get_camera_settings_cached(self, camera_id, ttl=2.0):
        now = time.time()
        with self._camera_settings_cache_lock:
            entry = self._camera_settings_cache.get(camera_id)
            if entry and (now - entry[0] < ttl):
                return entry[1]
        try:
            cam = db.get_camera(camera_id)
        except Exception:
            cam = None
        with self._camera_settings_cache_lock:
            self._camera_settings_cache[camera_id] = (now, cam)
        return cam

    def _filter_object_quality(self, objects, faces, frame_shape):
        if not objects:
            return objects

        try:
            frame_h, frame_w = frame_shape[:2]
        except Exception:
            frame_h = frame_w = 0
        frame_area = max(1.0, float(frame_w) * float(frame_h))
        face_boxes = [f.get("bbox") for f in faces or [] if f.get("bbox")]

        try:
            min_area_ratio = max(0.0, float(config.get("object_min_area_ratio", 0.00025) or 0.00025))
        except Exception:
            min_area_ratio = 0.00025
        try:
            weak_person_conf = max(0.0, min(1.0, float(config.get("person_weak_detection_confidence", 0.55) or 0.55)))
        except Exception:
            weak_person_conf = 0.55
        try:
            tiny_person_area = max(0.0, float(config.get("person_tiny_area_ratio", 0.006) or 0.006))
        except Exception:
            tiny_person_area = 0.006

        filtered = []
        dropped = 0
        for obj in objects:
            box = obj.get("bbox")
            if not box or len(box) != 4:
                dropped += 1
                continue
            x1, y1, x2, y2 = [float(v) for v in box]
            bw = max(0.0, x2 - x1)
            bh = max(0.0, y2 - y1)
            area_ratio = (bw * bh) / frame_area
            if bw < 4.0 or bh < 4.0 or area_ratio < min_area_ratio:
                dropped += 1
                continue

            cls_key = _class_name_key(obj.get("class_name") or obj.get("class"))
            conf = _as_float(obj.get("confidence", obj.get("det_score", 0.0)))
            if obj.get("_track_low_conf"):
                filtered.append(obj)
                continue

            if cls_key == "person":
                linked_to_face = any(_face_linked_to_person_box(box, face_box) for face_box in face_boxes)
                weak_without_face = face_boxes and conf < weak_person_conf and not linked_to_face
                tiny_weak_person = area_ratio < tiny_person_area and conf < max(weak_person_conf, 0.70)
                if weak_without_face or tiny_weak_person:
                    dropped += 1
                    continue

            filtered.append(obj)

        if dropped:
            logger.debug("Filtered %d low-quality object detections", dropped)
        return filtered

    def _rebuild_trackers(self, camera_id, faces, objects, max_trackers):
        state = self._get_camera_state(camera_id)
        now_ts = time.time()
        entries = []
        for f in faces[:max_trackers]:
            bbox = f.get("bbox")
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            entries.append(
                {
                    "type": "face",
                    "bbox": [x1, y1, x2, y2],
                    "identity": f.get("identity"),
                    "confidence": f.get("confidence"),
                    "det_score": f.get("det_score"),
                    "embedding": f.get("embedding"),
                    "landmarks": f.get("landmarks"),
                    "liveness": f.get("liveness", 1.0),
                    "gender": f.get("gender", "unknown"),
                    "gender_confidence": f.get("gender_confidence", 0.0),
                    "last_identify_frame": f.get("last_identify_frame", -1),
                    "vx": _as_float(f.get("track_vx", 0.0)),
                    "vy": _as_float(f.get("track_vy", 0.0)),
                    "last_seen": now_ts,
                }
            )

        for o in objects[:max_trackers]:
            bbox = o.get("bbox")
            if not bbox:
                continue
            x1, y1, x2, y2 = bbox
            entries.append(
                {
                    "type": "object",
                    "bbox": [x1, y1, x2, y2],
                    "plugin_id": o.get("plugin_id"),
                    "plugin_name": o.get("plugin_name"),
                    "class": o.get("class"),
                    "det_score": o.get("det_score"),
                    "vx": _as_float(o.get("track_vx", 0.0)),
                    "vy": _as_float(o.get("track_vy", 0.0)),
                    "last_seen": now_ts,
                }
            )

        with state.trackers_lock:
            state.trackers = entries

    def _apply_smoothing(self, camera_id, faces, objects, frame_shape=None):
        state = self._get_camera_state(camera_id)
        try:
            hold_frames = max(0, min(4, int(config.get("bbox_hold_max_frames", 3) or 3)))
        except Exception:
            hold_frames = 3
        try:
            hold_stale_sec = max(0.0, min(0.45, float(config.get("bbox_hold_max_stale_sec", 0.35) or 0.35)))
        except Exception:
            hold_stale_sec = 0.35
        try:
            object_confirm_hits = max(1, min(5, int(config.get("object_tracker_confirm_hits", 2) or 2)))
        except Exception:
            object_confirm_hits = 2

        def _center_size(box):
            cx, cy = _bbox_center(box)
            w, h = _bbox_width_height(box)
            return cx, cy, w, h

        def _track_identity(kind, item):
            if kind == "faces":
                identity = item.get("identity")
                if isinstance(identity, dict):
                    return identity.get("id")
                return None
            return None

        def _track_class(kind, item):
            if kind == "objects":
                return (item.get("plugin_id"), item.get("class") or item.get("class_id") or item.get("class_name"))
            return None

        def _confirm_hits_required(kind):
            return 1 if kind == "faces" else object_confirm_hits

        def _is_confirmed(track):
            try:
                return int(track.get("hits", 0) or 0) >= int(track.get("confirm_hits_required", 1) or 1)
            except Exception:
                return True

        def _compatible(kind, track, item):
            if kind == "faces":
                prev_id = track.get("id")
                curr_id = _track_identity(kind, item)
                return not (prev_id is not None and curr_id is not None and prev_id != curr_id)
            prev_plugin, prev_cls = track.get("class_key") or (None, None)
            curr_plugin, curr_cls = _track_class(kind, item)
            if prev_plugin is not None and curr_plugin is not None and prev_plugin != curr_plugin:
                return False
            return not (prev_cls is not None and curr_cls is not None and prev_cls != curr_cls)

        def _predict_track_box(track, now_ts):
            box = track.get("bbox")
            if not box:
                return None
            dt = max(0.0, min(0.30, now_ts - float(track.get("last_update", now_ts) or now_ts)))
            return _shift_bbox(box, _as_float(track.get("vx_sec", 0.0)) * dt, _as_float(track.get("vy_sec", 0.0)) * dt)

        def _find_match(kind, tracks, item, used_track_ids, now_ts, recovery=False):
            curr_box = item.get("bbox")
            if not curr_box:
                return None

            best = None
            best_score = -1e9
            best_iou = 0.0
            best_rel = 999.0
            for track in tracks:
                if id(track) in used_track_ids or not track.get("bbox") or not _compatible(kind, track, item):
                    continue
                pred_box = _predict_track_box(track, now_ts) or track.get("bbox")
                raw_iou = _iou(track.get("bbox"), curr_box)
                pred_iou = _iou(pred_box, curr_box)
                iou = max(raw_iou, pred_iou)
                pcx, pcy = _bbox_center(pred_box)
                ccx, ccy = _bbox_center(curr_box)
                rel = (((pcx - ccx) ** 2 + (pcy - ccy) ** 2) ** 0.5) / _bbox_size(curr_box)
                score = (iou * 1.25) - (rel * (0.14 if kind == "faces" else 0.20))
                if score > best_score:
                    best = track
                    best_score = score
                    best_iou = iou
                    best_rel = rel

            if best is None:
                return None

            if kind == "objects" and recovery:
                min_iou = 0.18
                max_rel = 1.10
            else:
                min_iou = 0.04 if kind == "faces" else 0.10
                max_rel = 2.8 if kind == "faces" else 1.8
            if best_iou < min_iou and best_rel > max_rel:
                return None
            return best

        def _gains(kind, residual_px, rel_residual, iou, box_size):
            jitter_gate = max(1.25, min(5.0 if kind == "faces" else 7.0, box_size * 0.018))
            if residual_px <= jitter_gate and iou >= 0.72:
                return 0.18, 0.045, 0.08
            if rel_residual >= 0.55 or iou < 0.18:
                return 0.92, 0.42, 0.72
            if rel_residual >= 0.25:
                return 0.82, 0.30, 0.55
            if rel_residual >= 0.10:
                return 0.62, 0.18, 0.34
            return 0.38, 0.10, 0.18

        def _cap_velocity(vx_sec, vy_sec, box_size):
            max_speed = max(450.0, min(3200.0, box_size * 18.0))
            speed = ((vx_sec * vx_sec) + (vy_sec * vy_sec)) ** 0.5
            if speed > max_speed > 0.0:
                scale = max_speed / speed
                vx_sec *= scale
                vy_sec *= scale
            deadband = max(6.0, min(20.0, box_size * 0.06))
            if abs(vx_sec) < deadband:
                vx_sec = 0.0
            if abs(vy_sec) < deadband:
                vy_sec = 0.0
            return vx_sec, vy_sec

        def _apply_track_output(item, track, raw_box, filtered_box, delta_x, delta_y):
            item["raw_bbox"] = [int(round(float(v))) for v in raw_box]
            item["bbox"] = [int(round(float(v))) for v in filtered_box]
            item["track_vx"] = float(delta_x)
            item["track_vy"] = float(delta_y)
            item["track_vx_sec"] = _as_float(track.get("vx_sec", 0.0))
            item["track_vy_sec"] = _as_float(track.get("vy_sec", 0.0))
            item["track_ts"] = track.get("last_update", time.time())
            item["_track_id"] = track.get("track_id")
            item["_track_confirmed"] = _is_confirmed(track)

        def _updated_track(kind, item, matched, now_ts, next_track_id):
            raw_box = [float(v) for v in item.get("bbox")]
            raw_cx, raw_cy, raw_w, raw_h = _center_size(raw_box)
            confirm_hits_required = _confirm_hits_required(kind)
            low_conf_recovery = bool(item.get("_track_low_conf"))
            if matched is None or not matched.get("bbox"):
                clipped = _clip_bbox_to_shape(raw_box, frame_shape) or [int(round(v)) for v in raw_box]
                track = {
                    "track_id": next_track_id,
                    "kind": kind,
                    "bbox": [float(v) for v in clipped],
                    "raw_bbox": raw_box,
                    "vx": 0.0,
                    "vy": 0.0,
                    "vx_sec": 0.0,
                    "vy_sec": 0.0,
                    "last_seen": now_ts,
                    "last_update": now_ts,
                    "misses": 0,
                    "hits": 1,
                    "confirm_hits_required": confirm_hits_required,
                    "id": _track_identity(kind, item),
                    "class_key": _track_class(kind, item),
                }
                _copy_track_metadata(kind, track, item)
                _apply_track_output(item, track, raw_box, clipped, 0.0, 0.0)
                return track, next_track_id + 1

            prev_box = matched.get("bbox")
            prev_cx, prev_cy, prev_w, prev_h = _center_size(prev_box)
            dt = max(0.015, min(0.30, now_ts - float(matched.get("last_update", now_ts) or now_ts)))
            prev_raw_box = matched.get("raw_bbox") or prev_box
            prev_raw_cx, prev_raw_cy, _, _ = _center_size(prev_raw_box)
            pred_cx = prev_cx + (_as_float(matched.get("vx_sec", 0.0)) * dt)
            pred_cy = prev_cy + (_as_float(matched.get("vy_sec", 0.0)) * dt)
            rx = raw_cx - pred_cx
            ry = raw_cy - pred_cy
            residual_px = ((rx * rx) + (ry * ry)) ** 0.5
            box_size = _bbox_size(raw_box)
            rel_residual = residual_px / box_size
            pred_box = _box_from_center(pred_cx, pred_cy, prev_w, prev_h)
            match_iou = max(_iou(prev_box, raw_box), _iou(pred_box, raw_box))
            pos_gain, vel_gain, size_gain = _gains(kind, residual_px, rel_residual, match_iou, box_size)

            new_cx = pred_cx + (pos_gain * rx)
            new_cy = pred_cy + (pos_gain * ry)
            measured_vx_sec = (raw_cx - prev_raw_cx) / dt
            measured_vy_sec = (raw_cy - prev_raw_cy) / dt
            if residual_px <= max(1.25, box_size * 0.018) and match_iou >= 0.72:
                vel_mix = 0.10
            else:
                vel_mix = max(0.30, min(0.85, vel_gain * 1.9))
            vx_sec = (_as_float(matched.get("vx_sec", 0.0)) * (1.0 - vel_mix)) + (measured_vx_sec * vel_mix)
            vy_sec = (_as_float(matched.get("vy_sec", 0.0)) * (1.0 - vel_mix)) + (measured_vy_sec * vel_mix)
            vx_sec, vy_sec = _cap_velocity(vx_sec, vy_sec, box_size)

            new_w = prev_w + ((raw_w - prev_w) * size_gain)
            new_h = prev_h + ((raw_h - prev_h) * size_gain)
            min_w = max(2.0, raw_w * 0.55)
            min_h = max(2.0, raw_h * 0.55)
            max_w = raw_w * 1.65
            max_h = raw_h * 1.65
            new_w = max(min_w, min(max_w, new_w))
            new_h = max(min_h, min(max_h, new_h))

            filtered_box = _clip_bbox_to_shape(_box_from_center(new_cx, new_cy, new_w, new_h), frame_shape) or raw_box
            filt_cx, filt_cy, _, _ = _center_size(filtered_box)
            delta_x = filt_cx - prev_cx
            delta_y = filt_cy - prev_cy
            hits = int(matched.get("hits", 1) or 1)
            if not low_conf_recovery:
                hits = min(255, hits + 1)

            track = {
                **matched,
                "bbox": [float(v) for v in filtered_box],
                "raw_bbox": raw_box,
                "vx": delta_x,
                "vy": delta_y,
                "vx_sec": vx_sec,
                "vy_sec": vy_sec,
                "last_seen": now_ts,
                "last_update": now_ts,
                "misses": 0,
                "hits": hits,
                "confirm_hits_required": confirm_hits_required,
                "id": _track_identity(kind, item) if _track_identity(kind, item) is not None else matched.get("id"),
                "class_key": _track_class(kind, item) if kind == "objects" else matched.get("class_key"),
            }
            if low_conf_recovery:
                item["_weak_track_recovery"] = True
                prev_conf = _as_float(matched.get("_confidence"), _as_float(matched.get("_det_score")))
                item_conf = _as_float(item.get("confidence", item.get("det_score", 0.0)))
                item["confidence"] = max(item_conf, prev_conf * 0.82)
                item["det_score"] = max(_as_float(item.get("det_score", item_conf)), _as_float(matched.get("_det_score")) * 0.78)
            _copy_track_metadata(kind, track, item)
            _apply_track_output(item, track, raw_box, filtered_box, delta_x, delta_y)
            return track, next_track_id

        def _copy_track_metadata(kind, track, item):
            if kind == "faces":
                track.update(
                    {
                        "_ident_info": item.get("identity"),
                        "_confidence": item.get("confidence"),
                        "_det_score": item.get("det_score", 0.0),
                        "_embedding": item.get("embedding"),
                        "_liveness": item.get("liveness", 1.0),
                        "_gender": item.get("gender", "unknown"),
                        "_gender_conf": item.get("gender_confidence", 0.0),
                        "_last_identify_frame": item.get("last_identify_frame", -1),
                    }
                )
            else:
                track.update(
                    {
                        "_plugin_id": item.get("plugin_id"),
                        "_plugin_name": item.get("plugin_name"),
                        "_class": item.get("class"),
                        "_class_name": item.get("class_name"),
                        "_det_score": item.get("det_score", 0.0),
                        "_confidence": item.get("confidence", item.get("det_score", 0.0)),
                    }
                )

        def _coast_track(kind, track, now_ts):
            misses = int(track.get("misses", 0) or 0) + 1
            age = now_ts - float(track.get("last_seen", now_ts) or now_ts)
            if misses > hold_frames or age > hold_stale_sec or not track.get("bbox"):
                return None, None

            dt = max(0.015, min(0.30, now_ts - float(track.get("last_update", now_ts) or now_ts)))
            vx_sec = _as_float(track.get("vx_sec", 0.0)) * 0.72
            vy_sec = _as_float(track.get("vy_sec", 0.0)) * 0.72
            pred_box = _clip_bbox_to_shape(_shift_bbox(track["bbox"], vx_sec * dt, vy_sec * dt), frame_shape)
            if not pred_box:
                return None, None

            prev_cx, prev_cy = _bbox_center(track["bbox"])
            pred_cx, pred_cy = _bbox_center(pred_box)
            coasted_track = {
                **track,
                "bbox": [float(v) for v in pred_box],
                "vx": pred_cx - prev_cx,
                "vy": pred_cy - prev_cy,
                "vx_sec": vx_sec,
                "vy_sec": vy_sec,
                "last_update": now_ts,
                "misses": misses,
            }
            if not _is_confirmed(coasted_track):
                return coasted_track, None

            if kind == "faces":
                conf = max(0.0, _as_float(track.get("_confidence"), _as_float(track.get("_det_score"))) * (0.78 ** misses))
                item = {
                    "bbox": pred_box,
                    "raw_bbox": track.get("raw_bbox") or pred_box,
                    "identity": track.get("_ident_info"),
                    "confidence": conf,
                    "det_score": max(0.0, _as_float(track.get("_det_score")) * (0.72 ** misses)),
                    "embedding": track.get("_embedding"),
                    "liveness": track.get("_liveness", 1.0),
                    "gender": track.get("_gender", "unknown"),
                    "gender_confidence": track.get("_gender_conf", 0.0),
                    "last_identify_frame": track.get("_last_identify_frame", -1),
                    "track_vx": coasted_track["vx"],
                    "track_vy": coasted_track["vy"],
                    "track_vx_sec": vx_sec,
                    "track_vy_sec": vy_sec,
                    "track_ts": now_ts,
                    "_track_id": track.get("track_id"),
                    "_track_confirmed": True,
                    "_coasted": True,
                }
                return coasted_track, item

            item = {
                "bbox": pred_box,
                "raw_bbox": track.get("raw_bbox") or pred_box,
                "plugin_id": track.get("_plugin_id"),
                "plugin_name": track.get("_plugin_name"),
                "class": track.get("_class"),
                "class_name": track.get("_class_name") or str(track.get("_class")),
                "confidence": max(0.0, _as_float(track.get("_confidence"), _as_float(track.get("_det_score"))) * (0.78 ** misses)),
                "det_score": max(0.0, _as_float(track.get("_det_score")) * (0.72 ** misses)),
                "track_vx": coasted_track["vx"],
                "track_vy": coasted_track["vy"],
                "track_vx_sec": vx_sec,
                "track_vy_sec": vy_sec,
                "track_ts": now_ts,
                "_track_id": track.get("track_id"),
                "_track_confirmed": True,
                "_coasted": True,
            }
            return coasted_track, item

        def _process(kind, detections, previous_tracks, next_track_id, limit):
            used_track_ids = set()
            new_tracks = []
            visible_items = []
            source_items = [item for item in detections if item.get("bbox")]
            high_items = [item for item in source_items if kind == "faces" or not item.get("_track_low_conf")]
            low_items = [item for item in source_items if kind == "objects" and item.get("_track_low_conf")]

            for item in high_items:
                if not item.get("bbox"):
                    continue
                matched = _find_match(kind, previous_tracks, item, used_track_ids, now)
                if matched is not None:
                    used_track_ids.add(id(matched))
                elif kind == "objects":
                    new_thresh = _as_float(item.get("_new_track_confidence_threshold"), _as_float(item.get("_display_confidence_threshold"), 0.0))
                    if _as_float(item.get("confidence", item.get("det_score", 0.0))) < new_thresh:
                        continue
                track, next_track_id = _updated_track(kind, item, matched, now, next_track_id)
                new_tracks.append(track)
                if _is_confirmed(track):
                    visible_items.append(item)

            for item in low_items:
                matched = _find_match(kind, previous_tracks, item, used_track_ids, now, recovery=True)
                if matched is None:
                    continue
                used_track_ids.add(id(matched))
                track, next_track_id = _updated_track(kind, item, matched, now, next_track_id)
                new_tracks.append(track)
                if _is_confirmed(track):
                    visible_items.append(item)

            for track in previous_tracks:
                if id(track) in used_track_ids:
                    continue
                coasted_track, coasted_item = _coast_track(kind, track, now)
                if coasted_track is None:
                    continue
                new_tracks.append(coasted_track)
                if coasted_item is not None:
                    visible_items.append(coasted_item)

            new_tracks.sort(key=lambda t: float(t.get("last_seen", 0.0) or 0.0), reverse=True)
            detections[:] = visible_items
            return new_tracks[:limit], next_track_id

        with state.smoothing_lock:
            prev = state.smoothing_state
            now = time.time()
            try:
                next_track_id = int(prev.get("next_track_id", 1) or 1)
            except Exception:
                next_track_id = 1

            try:
                max_tracks = max(16, int(config.get("max_trackers_per_cam", 32) or 32))
            except Exception:
                max_tracks = 32
            face_tracks, next_track_id = _process("faces", faces, list(prev.get("faces", [])), next_track_id, max_tracks)
            obj_tracks, next_track_id = _process("objects", objects, list(prev.get("objects", [])), next_track_id, max_tracks)

            prev["faces"] = face_tracks
            prev["objects"] = obj_tracks
            prev["next_track_id"] = next_track_id
            state.smoothing_state = prev

        return [], []

    def process_frame(self, frame, camera_id, run_plugins=True, run_faces=True, identify_faces=True, lightweight=False):
        self.ensure_initialized()
        state = self._get_camera_state(camera_id)

        with state.counter_lock:
            state.frame_counter += 1
            frame_idx = state.frame_counter

        _, aggressive_mode, max_identify, max_trackers = self._read_frame_settings()
        small, scale = self._scale_for_mode(frame, aggressive_mode)

        plugin_ids = self.get_plugins_for_camera(camera_id) if run_plugins else []
        face_enabled = bool(run_faces) and self._is_face_enabled(camera_id)

        futures = self._submit_inference_futures(camera_id, small, scale, plugin_ids, face_enabled)
        faces, objects, face_ms, obj_ms = self._collect_futures(futures)

        logger.debug("Frame %d: faces=%d objects=%d", frame_idx, len(faces), len(objects))

        objects = self._filter_allowed_objects(objects)
        objects = self._filter_object_quality(objects, faces, frame.shape)
        if faces and identify_faces and not lightweight:
            self._identify_faces_for_frame(camera_id, faces, aggressive_mode, max_identify, small, frame_idx)

        if not lightweight:
            self._apply_smoothing(camera_id, faces, objects, frame_shape=frame.shape)

            # Evaluate liveness after smoothing so bbox jitter/resets don't
            # break per-face liveness tracks that rely on stable coordinates.
            real_faces = [f for f in faces if not f.get("_coasted")]
            if real_faces and self._liveness is not None:
                try:
                    self._evaluate_liveness_for_frame(camera_id, real_faces, objects, frame, frame_idx)
                except Exception:
                    logger.debug("Liveness evaluation failed for camera %s", camera_id, exc_info=True)

            self._rebuild_trackers(camera_id, faces, objects, max_trackers)

        return {
            "faces": faces,
            "objects": objects,
            "face_time_ms": face_ms,
            "object_time_ms": obj_ms,
        }

    def _filter_allowed_objects(self, objects):
        with self._plugin_models_lock:
            allowed_pids = set(self._plugin_models.keys())
        return [o for o in objects if o.get("plugin_id") in allowed_pids]

    def _identify_faces_for_frame(self, camera_id, faces, aggressive_mode, max_identify, frame_for_liveness, frame_idx):
        try:
            max_faces_identify = int(config.get("max_faces_identify_per_frame", 16) or 16)
        except Exception:
            max_faces_identify = 16
        max_faces_identify = max(1, max_faces_identify)

        faces_for_identify = faces
        if len(faces) > max_faces_identify:
            ranked_idx = sorted(
                range(len(faces)),
                key=lambda i: float(faces[i].get("det_score", 0.0) or 0.0),
                reverse=True,
            )
            faces_for_identify = [faces[i] for i in ranked_idx[:max_faces_identify]]

        state = self._get_camera_state(camera_id)
        with state.trackers_lock:
            existing_trackers = list(state.trackers)
        self._identify_faces(camera_id, faces_for_identify, existing_trackers, aggressive_mode, max_identify, frame_for_liveness, frame_idx)

    def _skip_presentation_block_for_camera(self, camera_id) -> bool:
        try:
            if not db.get_bool("liveness_skip_presentation_for_stream_sources", True):
                return False
            cam = self._get_camera_settings_cached(camera_id)
            if not cam:
                return False
            return _is_demo_stream_source(
                cam.get("source"),
                http_as_live=db.get_bool("http_stream_as_live", False),
            )
        except Exception:
            return False

    def _evaluate_liveness_for_frame(self, camera_id, faces, objects, frame_for_liveness, frame_idx):
        try:
            skip_presentation_block = self._skip_presentation_block_for_camera(camera_id)
            for f in faces:
                try:
                    liveness_required = config.liveness_global()
                    if f.get("identity") and not liveness_required:
                        row = db.get_known_face(f["identity"].get("id"))
                        if row and row.get("liveness_required"):
                            liveness_required = True
                except Exception:
                    liveness_required = False

                if not liveness_required and self._liveness is not None and f.get("identity"):
                    try:
                        block_presentations = config.get("liveness_block_screen_presentations", True)
                        if isinstance(block_presentations, str):
                            block_presentations = block_presentations.strip().lower() in ("1", "true", "yes", "on")
                        if (
                            block_presentations
                            and not skip_presentation_block
                            and self._liveness.detect_presentation_attack(frame_for_liveness, f, objects=objects)
                        ):
                            f["liveness"] = 0.0
                            f["_spoof_type"] = "screen_presentation"
                            f.pop("_liveness_pending", None)
                            f.pop("_liveness_seconds_left", None)
                            continue
                    except Exception:
                        logger.debug("Presentation check failed for camera %s", camera_id, exc_info=True)

                if liveness_required and self._liveness is not None:
                    try:
                        lval, spoof, pending, seconds_left = self._liveness.evaluate(
                            camera_id,
                            frame_for_liveness,
                            f,
                            frame_idx,
                            objects=objects,
                            block_presentation=not skip_presentation_block,
                        )
                        f["liveness"] = lval
                        if spoof:
                            f["_spoof_type"] = spoof
                            f.pop("_liveness_pending", None)
                            f.pop("_liveness_seconds_left", None)
                        elif pending:
                            f["_liveness_pending"] = True
                            try:
                                f["_liveness_seconds_left"] = float(seconds_left)
                            except Exception:
                                f["_liveness_seconds_left"] = 0.0
                        else:
                            f.pop("_spoof_type", None)
                            f.pop("_liveness_pending", None)
                            f.pop("_liveness_seconds_left", None)
                    except Exception:
                        f.pop("_spoof_type", None)
                        f.pop("_liveness_pending", None)
                        f.pop("_liveness_seconds_left", None)
                        f["liveness"] = 1.0
                else:
                    f.pop("_spoof_type", None)
                    f.pop("_liveness_pending", None)
                    f.pop("_liveness_seconds_left", None)
                    f["liveness"] = 1.0
        except Exception:
            logger.debug("_evaluate_liveness_for_frame failed", exc_info=True)

    def _is_face_enabled(self, camera_id):
        try:
            global_enabled = bool(config.get("face_recognition_enabled_global", True))
            if not global_enabled:
                return False
            cam = self._get_camera_settings_cached(camera_id)
            return True if cam is None else bool(cam.get("face_recognition", 1))
        except Exception:
            return True


_instance = None
_instance_lock = threading.Lock()


def get_manager():
    global _instance
    if _instance is None:
        with _instance_lock:
            if _instance is None:
                _instance = DetectorManager()
    return _instance


def notify_plugins_changed(reload_plugin_sessions: bool = False):
    try:
        if reload_plugin_sessions:
            with contextlib.suppress(Exception):
                model_loader.unload_all_plugins()
        m = get_manager()
        m.invalidate_camera_cache()
        m.reload()
        m.clear_camera_state()
        try:
            from backend.camera.camera_manager import get_camera_manager

            get_camera_manager().clear_all_states()
        except Exception:
            logger.debug("Failed to clear camera states", exc_info=True)
    except Exception:
        logger.warning("notify_plugins_changed failed", exc_info=True)
