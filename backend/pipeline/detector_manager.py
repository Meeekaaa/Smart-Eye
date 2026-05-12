import contextlib
import logging
import os
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor

import cv2

from backend.repository import db
from backend.models import model_loader
from utils import config
from backend.pipeline.liveness_manager import LivenessManager

logger = logging.getLogger(__name__)

_MAX_INFER_DIM = 512


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


def _smooth_bbox(prev, curr, alpha=0.6, max_scale_change=0.12):
    try:
        if not prev or not curr:
            return curr

        px1, py1, px2, py2 = [float(x) for x in prev]

        cx1, cy1, cx2, cy2 = [float(x) for x in curr]

        pcx = (px1 + px2) / 2.0
        pcy = (py1 + py2) / 2.0
        pw = max(1.0, px2 - px1)
        ph = max(1.0, py2 - py1)

        ccx = (cx1 + cx2) / 2.0
        ccy = (cy1 + cy2) / 2.0
        cw = max(1.0, cx2 - cx1)
        ch = max(1.0, cy2 - cy1)

        alpha_pos = float(alpha)
        alpha_size = min(0.82, max(0.55, alpha_pos * 0.78))

        ncx = alpha_pos * ccx + (1.0 - alpha_pos) * pcx
        ncy = alpha_pos * ccy + (1.0 - alpha_pos) * pcy

        nw = alpha_size * cw + (1.0 - alpha_size) * pw
        nh = alpha_size * ch + (1.0 - alpha_size) * ph

        min_w = pw * (1.0 - max_scale_change)
        max_w = pw * (1.0 + max_scale_change)
        min_h = ph * (1.0 - max_scale_change)
        max_h = ph * (1.0 + max_scale_change)
        nw = max(min_w, min(max_w, nw))
        nh = max(min_h, min(max_h, nh))

        nx1 = int(ncx - nw / 2.0)
        ny1 = int(ncy - nh / 2.0)
        nx2 = int(ncx + nw / 2.0)
        ny2 = int(ncy + nh / 2.0)

        return [nx1, ny1, nx2, ny2]
    except Exception:
        return curr


def _as_float(value, default=0.0):
    try:
        return float(value)
    except Exception:
        return float(default)


def _bbox_center(box):
    return ((box[0] + box[2]) / 2.0, (box[1] + box[3]) / 2.0)


def _bbox_size(box):
    return max(1.0, float(box[2] - box[0]), float(box[3] - box[1]))


def _shift_bbox(box, dx, dy):
    return [float(box[0]) + dx, float(box[1]) + dy, float(box[2]) + dx, float(box[3]) + dy]


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


def _adaptive_smoothing_alpha(rel_move, match_iou):
    rel = _as_float(rel_move)
    iou = _as_float(match_iou)

    if rel >= 1.10:
        return 0.96
    if rel >= 0.75:
        return 0.93
    if rel >= 0.45:
        return 0.88
    if rel >= 0.25:
        return 0.82

    if iou < 0.25:
        return 0.90
    if iou < 0.45:
        return 0.84
    return 0.76


def _adaptive_object_smoothing_alpha(rel_move, match_iou):
    rel = _as_float(rel_move)
    iou = _as_float(match_iou)

    if rel >= 1.10:
        return 0.80
    if rel >= 0.75:
        return 0.72
    if rel >= 0.45:
        return 0.64
    if rel >= 0.25:
        return 0.56

    if iou < 0.25:
        return 0.62
    if iou < 0.45:
        return 0.52
    return 0.44


def _pick_best_prev(candidates, curr_box, allow_entry=None, min_iou=0.10, max_rel_dist=3.0):
    best = None
    best_score = -1e9
    best_iou = 0.0
    best_rel = 999.0

    for _idx, entry in candidates:
        if allow_entry and not allow_entry(entry):
            continue
        pb = entry.get("bbox")
        if not pb:
            continue

        score, iou, rel = _match_score(pb, curr_box, entry.get("vx", 0.0), entry.get("vy", 0.0))
        if score > best_score:
            best = entry
            best_score = score
            best_iou = iou
            best_rel = rel

    if best is None:
        return None, 0.0, 999.0

    if best_iou < min_iou and best_rel > max_rel_dist:
        return None, best_iou, best_rel

    return best, best_iou, best_rel


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
        return _scale_frame(frame, max_dim=_MAX_INFER_DIM)

    def _run_face_detection(self, camera_id, small, scale):
        t0 = time.time()
        faces = self._face_model.detect_faces(small)
        try:
            min_face_size = int(db.get_setting(f"camera_{camera_id}_min_face_size", None) or 0)
            if min_face_size <= 0:
                min_face_size = int(config.get("min_face_size", 40) or 40)
        except Exception:
            min_face_size = 40
        results = []
        for face in faces:
            face["bbox"] = _scale_bbox_up(face["bbox"], scale)
            try:
                x1, y1, x2, y2 = face["bbox"]
                if (x2 - x1) < min_face_size or (y2 - y1) < min_face_size:
                    continue
            except Exception:
                continue
            results.append(
                {
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
            )
        return results, (time.time() - t0) * 1000

    def _run_plugin(self, pid, small, scale, camera_id):
        with self._plugin_models_lock:
            entry = self._plugin_models.get(pid)
        if entry is None:
            return [], 0.0
        model = entry["model"]
        t0 = time.time()
        detections = model.detect(small) or []

        logger.debug("Plugin %s raw detections: %d", pid, len(detections))

        global_classes = {int(c.get("class_index")): c for c in entry.get("classes", [])}

        cam_over = []
        try:
            cam_over = self._get_camera_plugin_classes_cached(camera_id, pid) or []
        except Exception:
            cam_over = []
        overrides = {int(r.get("class_index")): r for r in cam_over}

        plugin_conf = entry.get("info", {}).get("confidence", 0.5)
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

            effective = dict(global_classes.get(cls, {}))

            if cls in overrides:
                over = overrides[cls]
                try:
                    effective["enabled"] = int(over.get("enabled", effective.get("enabled", 1)))
                except Exception:
                    effective["enabled"] = effective.get("enabled", 1)
                if over.get("confidence") is not None:
                    effective["confidence"] = over.get("confidence")

            if effective.get("enabled", 1) in (0, "0", False):
                continue

            class_conf = effective.get("confidence")
            if class_conf is None:
                try:
                    class_conf = float(entry.get("info", {}).get("confidence", plugin_conf))
                except Exception:
                    class_conf = plugin_conf

            if det.get("confidence", 0.0) < float(class_conf):
                continue

            det["plugin_id"] = pid
            det["plugin_name"] = entry.get("info", {}).get("name")
            det["class"] = cls
            det["class_name"] = det.get("class_name") or global_classes.get(cls, {}).get("class_name") or str(cls)
            det["det_score"] = det.get("confidence", 0.0)
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
        timeout_s = 30.0
        for key, fut in futures.items():
            try:
                data, ms = fut.result(timeout=timeout_s)
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

    @staticmethod
    def _build_grid(entries):
        grid = {}
        sizes = []
        for e in entries:
            pb = e.get("bbox")
            if not pb:
                continue
            w = max(1.0, pb[2] - pb[0])
            h = max(1.0, pb[3] - pb[1])
            sizes.append(max(w, h))
        avg_sz = max(16, int(sum(sizes) / len(sizes))) if sizes else 80
        bucket = max(48, int(avg_sz * 1.5))
        for idx, e in enumerate(entries):
            pb = e.get("bbox")
            if not pb:
                continue
            cx = int((pb[0] + pb[2]) / 2.0)
            cy = int((pb[1] + pb[3]) / 2.0)
            grid.setdefault((cx // bucket, cy // bucket), []).append((idx, e))
        return grid, bucket

    @staticmethod
    def _nearby_candidates(grid, bucket, box):
        cx = int((box[0] + box[2]) / 2.0)
        cy = int((box[1] + box[3]) / 2.0)
        gx, gy = cx // bucket, cy // bucket
        cand = []
        for dx in (-1, 0, 1):
            for dy in (-1, 0, 1):
                cell = (gx + dx, gy + dy)
                if cell in grid:
                    cand.extend(grid[cell])
        return cand

    def _apply_smoothing(self, camera_id, faces, objects):
        state = self._get_camera_state(camera_id)
        stable_raw = config.get("experimental_object_bbox_stabilization", True)
        if isinstance(stable_raw, str):
            use_stable_object_bboxes = stable_raw.strip().lower() in ("1", "true", "yes", "on")
        else:
            use_stable_object_bboxes = bool(stable_raw)
        with state.smoothing_lock:
            prev = state.smoothing_state
            now = time.time()

            new_face_state = []
            face_grid, face_bucket = self._build_grid(prev.get("faces", []))

            for f in faces:
                curr_box = f.get("bbox")
                if not curr_box:
                    new_face_state.append(
                        {
                            "id": None,
                            "bbox": None,
                            "vx": 0.0,
                            "vy": 0.0,
                            "last_seen": now,
                            "_ident_info": None,
                            "_confidence": None,
                            "_liveness": 1.0,
                            "_det_score": 0.0,
                            "_gender": "unknown",
                            "_gender_conf": 0.0,
                        }
                    )
                    continue
                ident = None
                if isinstance(f.get("identity"), dict):
                    ident = f["identity"].get("id")

                matched = None
                best_iou = 0.0
                if ident:
                    for p in prev["faces"]:
                        if p.get("id") == ident and p.get("bbox"):
                            matched = p
                            _score, best_iou, _ = _match_score(
                                p.get("bbox"),
                                curr_box,
                                p.get("vx", 0.0),
                                p.get("vy", 0.0),
                            )
                            break

                if not matched:
                    candidates = self._nearby_candidates(face_grid, face_bucket, curr_box)
                    matched, best_iou, _ = _pick_best_prev(
                        candidates,
                        curr_box,
                        min_iou=0.08,
                        max_rel_dist=3.2,
                    )

                vx = vy = 0.0
                if matched and matched.get("bbox"):
                    pb = matched["bbox"]
                    cx_prev, cy_prev = _bbox_center(pb)
                    cx_curr, cy_curr = _bbox_center(curr_box)
                    move_dist = ((cx_prev - cx_curr) ** 2 + (cy_prev - cy_curr) ** 2) ** 0.5
                    rel_move = move_dist / _bbox_size(curr_box)
                    alpha = _adaptive_smoothing_alpha(rel_move, best_iou)
                    f["bbox"] = _smooth_bbox(pb, curr_box, alpha=alpha)
                    sbx, sby = _bbox_center(f["bbox"])
                    inst_vx = sbx - cx_prev
                    inst_vy = sby - cy_prev
                    prev_vx = _as_float(matched.get("vx", 0.0))
                    prev_vy = _as_float(matched.get("vy", 0.0))
                    vx = (0.55 * prev_vx) + (0.45 * inst_vx)
                    vy = (0.55 * prev_vy) + (0.45 * inst_vy)

                f["track_vx"] = vx
                f["track_vy"] = vy

                new_face_state.append(
                    {
                        "id": ident,
                        "bbox": f.get("bbox"),
                        "vx": vx,
                        "vy": vy,
                        "last_seen": now,
                        "_ident_info": f.get("identity"),
                        "_confidence": f.get("confidence"),
                        "_liveness": f.get("liveness", 1.0),
                        "_det_score": f.get("det_score", 0.0),
                        "_gender": f.get("gender", "unknown"),
                        "_gender_conf": f.get("gender_confidence", 0.0),
                    }
                )

            new_obj_state = []
            obj_grid, obj_bucket = self._build_grid(prev.get("objects", []))

            for o in objects:
                curr_box = o.get("bbox")
                if not curr_box:
                    new_obj_state.append(
                        {
                            "plugin": o.get("plugin_id"),
                            "class": None,
                            "bbox": None,
                            "vx": 0.0,
                            "vy": 0.0,
                            "last_seen": now,
                            "_class_name": None,
                            "_plugin_name": None,
                            "_det_score": 0.0,
                        }
                    )
                    continue
                plugin = o.get("plugin_id")
                cls = o.get("class") or o.get("label") or o.get("class_name")
                candidates = self._nearby_candidates(obj_grid, obj_bucket, curr_box)
                matched, best_iou, _ = _pick_best_prev(
                    candidates,
                    curr_box,
                    allow_entry=lambda p: p.get("plugin") == plugin
                    and not (p.get("class") is not None and cls is not None and p.get("class") != cls),
                    min_iou=0.16,
                    max_rel_dist=2.2,
                )

                vx = vy = 0.0
                if matched and matched.get("bbox"):
                    sb_prev = matched["bbox"]
                    cx_prev, cy_prev = _bbox_center(sb_prev)
                    cx_curr, cy_curr = _bbox_center(curr_box)
                    move_dist = ((cx_prev - cx_curr) ** 2 + (cy_prev - cy_curr) ** 2) ** 0.5
                    rel_move = move_dist / _bbox_size(curr_box)
                    if use_stable_object_bboxes:
                        if best_iou >= 0.72 and rel_move <= 0.045:
                            o["bbox"] = [int(v) for v in sb_prev]
                            prev_vx = _as_float(matched.get("vx", 0.0))
                            prev_vy = _as_float(matched.get("vy", 0.0))
                            vx = prev_vx * 0.45
                            vy = prev_vy * 0.45
                        else:
                            alpha = _adaptive_object_smoothing_alpha(rel_move, best_iou)
                            if rel_move < 0.04:
                                alpha = min(alpha, 0.38)
                            o["bbox"] = _smooth_bbox(sb_prev, curr_box, alpha=alpha, max_scale_change=0.06)
                            sbx, sby = _bbox_center(o["bbox"])
                            inst_vx = sbx - cx_prev
                            inst_vy = sby - cy_prev
                            prev_vx = _as_float(matched.get("vx", 0.0))
                            prev_vy = _as_float(matched.get("vy", 0.0))
                            vx = (0.75 * prev_vx) + (0.25 * inst_vx)
                            vy = (0.75 * prev_vy) + (0.25 * inst_vy)
                            if abs(vx) < 0.14:
                                vx = 0.0
                            if abs(vy) < 0.14:
                                vy = 0.0
                    else:
                        alpha = _adaptive_smoothing_alpha(rel_move, best_iou)
                        alpha = min(0.92, max(0.72, alpha + 0.08))
                        o["bbox"] = _smooth_bbox(sb_prev, curr_box, alpha=alpha, max_scale_change=0.12)
                        sbx, sby = _bbox_center(o["bbox"])
                        inst_vx = sbx - cx_prev
                        inst_vy = sby - cy_prev
                        prev_vx = _as_float(matched.get("vx", 0.0))
                        prev_vy = _as_float(matched.get("vy", 0.0))
                        vx = (0.55 * prev_vx) + (0.45 * inst_vx)
                        vy = (0.55 * prev_vy) + (0.45 * inst_vy)
                        if abs(vx) < 0.10:
                            vx = 0.0
                        if abs(vy) < 0.10:
                            vy = 0.0

                o["track_vx"] = vx
                o["track_vy"] = vy

                new_obj_state.append(
                    {
                        "plugin": plugin,
                        "class": cls,
                        "bbox": o.get("bbox"),
                        "vx": vx,
                        "vy": vy,
                        "last_seen": now,
                        "_class_name": o.get("class_name"),
                        "_plugin_name": o.get("plugin_name"),
                        "_det_score": o.get("det_score", 0.0),
                    }
                )

            prev["faces"] = new_face_state
            prev["objects"] = new_obj_state
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
        if faces and identify_faces and not lightweight:
            self._identify_faces_for_frame(camera_id, faces, aggressive_mode, max_identify, small, frame_idx)

        if not lightweight:
            if faces or objects:
                self._rebuild_trackers(camera_id, faces, objects, max_trackers)
            self._apply_smoothing(camera_id, faces, objects)

            # Evaluate liveness after smoothing so bbox jitter/resets don't
            # break per-face liveness tracks that rely on stable coordinates.
            if faces and self._liveness is not None:
                try:
                    self._evaluate_liveness_for_frame(camera_id, faces, frame, frame_idx)
                except Exception:
                    logger.debug("Liveness evaluation failed for camera %s", camera_id, exc_info=True)

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

    def _evaluate_liveness_for_frame(self, camera_id, faces, frame_for_liveness, frame_idx):
        try:
            for f in faces:
                try:
                    liveness_required = config.liveness_global()
                    if f.get("identity") and not liveness_required:
                        row = db.get_known_face(f["identity"].get("id"))
                        if row and row.get("liveness_required"):
                            liveness_required = True
                except Exception:
                    liveness_required = False

                if liveness_required and self._liveness is not None:
                    try:
                        lval, spoof, pending, seconds_left = self._liveness.evaluate(camera_id, frame_for_liveness, f, frame_idx)
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
                            f.pop("_liveness_pending", None)
                            f.pop("_liveness_seconds_left", None)
                    except Exception:
                        f["liveness"] = 1.0
                else:
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


def notify_plugins_changed():
    try:
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
