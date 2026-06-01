import time
import contextlib
import logging
import collections
from concurrent.futures import Future, ThreadPoolExecutor

import cv2
import numpy as np
from PySide6.QtCore import QThread, Signal
import os

from backend.repository import db
from backend.pipeline.detector_manager import get_manager
from backend.pipeline.inference_utils import build_state
from backend.services.pipeline_service import PipelineService
from backend.services.service_manager import get_service_manager
from utils.runtime_metrics import record_runtime_metric

_DEFAULT_INFER_INTERVAL = 1
_LIVE_CLIP_SECONDS = 5
_LIVE_CLIP_LATENCY_SLACK_SEC = 5.0


class CameraThread(QThread):
    frame_ready = Signal(int, np.ndarray, dict)
    error_occurred = Signal(int, str)
    reconnecting = Signal(int)
    fps_updated = Signal(int, float)

    def __init__(self, camera_id, source, fps_limit=30, parent=None):
        super().__init__(parent)
        self._camera_id = camera_id
        self._source = source
        self._fps_limit = fps_limit
        self._running = False
        self._cap = None
        self._frame_count = 0
        self._fps = 0.0
        self._last_fps_time = 0
        self._infer_interval = _DEFAULT_INFER_INTERVAL
        self._base_infer_interval = _DEFAULT_INFER_INTERVAL
        self._adaptive_infer_interval = True
        self._infer_interval_min = _DEFAULT_INFER_INTERVAL
        self._infer_interval_max = 3
        self._raw_source = source
        self._is_twitch = "twitch.tv/" in str(source)
        self._last_inbox_save_ts = 0.0
        self._recent_inbox_embs: list[tuple[float, np.ndarray]] = []
        self._inbox_enabled = False
        self._suppress_errors = False
        self._clip_enabled = False
        self._clip_seconds = 5
        self._clip_buffer: collections.deque[tuple[float, np.ndarray]] = collections.deque()
        self._clip_buffer_bytes = 0
        self._clip_max_buffer_bytes = 128 * 1024 * 1024
        self._clip_buffer_max_dim = 640
        self._last_clip_ts = 0.0
        self._clip_recent: dict[tuple[str, tuple[str, ...]], float] = {}
        self._clip_min_interval = 10.0
        self._clip_repeat_window = 60.0
        self._ui_frame_interval_sec = 1.0 / 15.0
        self._last_frame_emit_ts = 0.0
        self._infer_dim = 640
        self._infer_dim_min = 384
        self._infer_dim_max = 768
        self._adaptive_infer_dim = True
        self._infer_tune_counter = 0
        self._last_inference_ts = 0.0
        self._inference_count = 0
        self._infer_fps = 0.0
        self._last_infer_fps_time = 0.0

    @property
    def camera_id(self):
        return self._camera_id

    @property
    def fps(self):
        return self._fps

    def set_inference_interval(self, n: int):
        self._base_infer_interval = max(1, int(n or 1))
        self._infer_interval = self._base_infer_interval

    @staticmethod
    def _parse_resolution_text(value):
        if not value:
            return None
        try:
            txt = str(value).strip().lower()
            if txt in ("original", "native", "auto"):
                return None
            if "x" not in txt:
                return None
            w_txt, h_txt = txt.split("x", 1)
            w = int(w_txt.strip())
            h = int(h_txt.strip())
            if w <= 0 or h <= 0:
                return None
            return w, h
        except Exception:
            return None

    def _preferred_capture_resolution(self):
        try:
            max_res = db.get_setting("max_resolution", "Original")
        except Exception:
            max_res = "Original"
        pref = self._parse_resolution_text(max_res)
        if pref:
            return pref

        try:
            cam = db.get_camera(self._camera_id)
            if cam:
                return self._parse_resolution_text(cam.get("resolution"))
        except Exception:
            pass
        return None

    def _configure_capture(self):
        if not self._cap:
            return
        try:
            self._cap.set(cv2.CAP_PROP_BUFFERSIZE, 1)
        except Exception:
            pass

        pref = self._preferred_capture_resolution()
        if pref:
            pw, ph = pref
            try:
                self._cap.set(cv2.CAP_PROP_FRAME_WIDTH, int(pw))
                self._cap.set(cv2.CAP_PROP_FRAME_HEIGHT, int(ph))
            except Exception:
                pass

    def _tune_infer_dim(self, result: dict):
        self._infer_tune_counter += 1
        if self._infer_tune_counter % 5 != 0:
            return

        try:
            face_ms = float(result.get("face_time_ms", 0.0) or 0.0)
            obj_ms = float(result.get("object_time_ms", 0.0) or 0.0)
        except Exception:
            return

        infer_ms = max(face_ms, obj_ms)
        if infer_ms <= 0.0:
            return

        if self._adaptive_infer_dim:
            target_budget_ms = (1000.0 / max(8.0, float(self._fps_limit or 30))) * max(1, int(self._infer_interval or 1))
            upper = target_budget_ms * 1.35
            lower = target_budget_ms * 0.70

            current_dim = int(self._infer_dim)
            if infer_ms > upper and current_dim > self._infer_dim_min:
                self._infer_dim = max(self._infer_dim_min, int(current_dim * 0.92))
            elif infer_ms < lower and current_dim < self._infer_dim_max:
                self._infer_dim = min(self._infer_dim_max, int(current_dim * 1.05))

        if not self._adaptive_infer_interval:
            return

        current_interval = max(1, int(self._infer_interval or 1))
        frame_budget_ms = 1000.0 / max(8.0, float(self._fps_limit or 30))
        interval_budget_ms = frame_budget_ms * current_interval
        if infer_ms > interval_budget_ms * 1.25 and current_interval < self._infer_interval_max:
            self._infer_interval = min(self._infer_interval_max, current_interval + 1)
        elif infer_ms < interval_budget_ms * 0.42 and current_interval > self._infer_interval_min:
            self._infer_interval = max(self._infer_interval_min, current_interval - 1)

    @staticmethod
    def _clone_display_entry(entry: dict) -> dict:
        cloned = dict(entry)
        bbox = cloned.get("bbox")
        if bbox and len(bbox) == 4:
            cloned["bbox"] = [int(round(float(v))) for v in bbox]
        return cloned

    @staticmethod
    def _predict_bbox_for_display(bbox, entry, lead_sec, frame_w, frame_h):
        if not bbox or len(bbox) != 4 or lead_sec <= 0.0:
            return bbox
        try:
            vx = float(entry.get("track_vx_sec", 0.0) or 0.0)
            vy = float(entry.get("track_vy_sec", 0.0) or 0.0)
        except Exception:
            return bbox
        if vx == 0.0 and vy == 0.0:
            return bbox

        try:
            x1 = float(bbox[0]) + (vx * lead_sec)
            y1 = float(bbox[1]) + (vy * lead_sec)
            x2 = float(bbox[2]) + (vx * lead_sec)
            y2 = float(bbox[3]) + (vy * lead_sec)
            x1 = max(0.0, min(float(frame_w - 1), x1))
            y1 = max(0.0, min(float(frame_h - 1), y1))
            x2 = max(0.0, min(float(frame_w - 1), x2))
            y2 = max(0.0, min(float(frame_h - 1), y2))
            if x2 - x1 < 2.0 or y2 - y1 < 2.0:
                return bbox
            return [int(round(x1)), int(round(y1)), int(round(x2)), int(round(y2))]
        except Exception:
            return bbox

    def _predict_display_state(self, state: dict, now_ts: float, frame_w: int, frame_h: int) -> dict:
        if not state:
            return {}

        display_state = dict(state)
        try:
            source_ts = float(display_state.get("_state_ts", 0.0) or 0.0)
        except Exception:
            source_ts = 0.0
        if source_ts <= 0.0:
            return display_state

        base_lead = max(0.0, now_ts - source_ts)
        max_lead = 0.30

        def _predict_entry(entry):
            cloned = self._clone_display_entry(entry)
            try:
                entry_ts = float(entry.get("track_ts", 0.0) or source_ts)
            except Exception:
                entry_ts = source_ts
            lead = max(base_lead, now_ts - entry_ts)
            if cloned.get("_coasted"):
                lead = min(lead, 0.14)
            else:
                lead = min(lead, max_lead)
            cloned["bbox"] = self._predict_bbox_for_display(cloned.get("bbox"), cloned, lead, frame_w, frame_h)
            return cloned

        faces = [_predict_entry(f) for f in display_state.get("all_faces", [])]
        if faces:
            display_state["all_faces"] = faces

        objects = [_predict_entry(o) for o in display_state.get("object_bboxes", [])]
        if objects:
            display_state["object_bboxes"] = objects

        if display_state.get("face_bbox") and display_state.get("all_faces"):
            old_box = state.get("face_bbox")
            for original, predicted in zip(state.get("all_faces", []), display_state.get("all_faces", []), strict=False):
                if original.get("bbox") == old_box:
                    display_state["face_bbox"] = predicted.get("bbox")
                    break
        return display_state

    def run(self):
        self._running = True
        run_started_at = time.perf_counter()
        startup_recorded = False
        try:
            os.environ.setdefault("OPENCV_VIDEOIO_PRIORITY_MSMF", "1")
            os.environ.setdefault("OPENCV_VIDEOIO_DISABLE_DIRECTSHOW", "1")
            configured_prefixes = db.get_setting("live_stream_prefixes", None)
            http_as_live = db.get_bool("http_stream_as_live", False)
            configured_backends = db.get_setting("capture_backends", None)
            twitch_enabled = db.get_bool("twitch_enabled", False)
            self._inbox_enabled = db.get_bool("inbox_capture_enabled", False)
            self._clip_enabled = db.get_bool("live_clip_enabled", True)
            self._clip_seconds = _LIVE_CLIP_SECONDS
            self._clip_max_buffer_bytes = max(8, int(db.get_int("live_clip_max_buffer_mb", 128) or 128)) * 1024 * 1024
            self._clip_buffer_max_dim = max(160, int(db.get_int("live_clip_buffer_max_dim", 640) or 640))
            self._clip_min_interval = float(db.get_float("live_clip_min_interval_sec", 10.0) or 10.0)
            self._clip_repeat_window = float(db.get_float("live_clip_repeat_window_sec", 60.0) or 60.0)
            ui_fps = max(1.0, min(60.0, float(db.get_float("ui_live_render_fps", 15.0) or 15.0)))
            self._ui_frame_interval_sec = 1.0 / ui_fps
            self._adaptive_infer_interval = db.get_bool("adaptive_live_infer_interval", True)
            self._infer_interval_min = max(
                1,
                int(db.get_int("live_infer_interval_min", self._base_infer_interval) or self._base_infer_interval),
                int(self._base_infer_interval or 1),
            )
            self._infer_interval_max = max(
                self._infer_interval_min,
                int(db.get_int("live_infer_interval_max", 2) or 2),
            )
            self._infer_interval = max(self._infer_interval_min, min(int(self._infer_interval or 1), self._infer_interval_max))
        except Exception:
            configured_prefixes = None
            http_as_live = False
            configured_backends = None
            twitch_enabled = False
            self._inbox_enabled = False
            self._clip_enabled = True
            self._clip_seconds = _LIVE_CLIP_SECONDS
            self._clip_max_buffer_bytes = 128 * 1024 * 1024
            self._clip_buffer_max_dim = 640
            self._clip_min_interval = 10.0
            self._clip_repeat_window = 60.0
            self._ui_frame_interval_sec = 1.0 / 15.0
            self._adaptive_infer_interval = True
            self._infer_interval_min = max(1, int(self._base_infer_interval or 1))
            self._infer_interval_max = max(self._infer_interval_min, 3)
            self._infer_interval = self._infer_interval_min

        try:
            self._infer_dim = int(db.get_int("live_infer_dim", 640) or 640)
            self._infer_dim_min = int(db.get_int("live_infer_dim_min", 384) or 384)
            self._infer_dim_max = int(db.get_int("live_infer_dim_max", 768) or 768)
            self._adaptive_infer_dim = bool(db.get_bool("adaptive_live_infer_dim", True))
        except Exception:
            self._infer_dim = 640
            self._infer_dim_min = 384
            self._infer_dim_max = 768
            self._adaptive_infer_dim = True

        self._infer_dim_min = max(256, int(self._infer_dim_min))
        self._infer_dim_max = max(self._infer_dim_min, int(self._infer_dim_max))
        self._infer_dim = max(self._infer_dim_min, min(self._infer_dim_max, int(self._infer_dim)))

        live_prefixes = list(configured_prefixes or ["rtsp"])
        if http_as_live:
            live_prefixes.extend(["http://", "https://"])

        def _resolve_backends():

            default_names = ["CAP_MSMF"]
            names = configured_backends or default_names
            resolved = []
            for name in names:
                val = getattr(cv2, name, None)
                if val is not None:
                    resolved.append(val)
            return resolved or [cv2.CAP_ANY]

        def _resolve_source():
            if self._is_twitch and twitch_enabled in (True, 1, "1", "true", "True"):
                try:
                    import streamlink

                    session = streamlink.Streamlink()
                    streams = session.streams(str(self._raw_source))
                    if streams:
                        stream = streams.get("best") or next(iter(streams.values()))
                        url = stream.to_url() if hasattr(stream, "to_url") else getattr(stream, "url", None)
                        if url:
                            return url
                except Exception:
                    pass
            try:
                return int(self._raw_source) if str(self._raw_source).isdigit() else self._raw_source
            except (ValueError, AttributeError):
                return self._raw_source

        try:
            src = _resolve_source()
        except (ValueError, AttributeError):
            src = self._raw_source

        self._cap = None
        backends = _resolve_backends()
        for backend in backends:
            try:
                cap = cv2.VideoCapture(src, backend)
            except Exception:
                cap = None
            if cap and cap.isOpened():
                self._cap = cap
                break
            with contextlib.suppress(Exception):
                if cap:
                    cap.release()

        if self._cap is None or not self._cap.isOpened():
            try:
                self._cap = cv2.VideoCapture(src)
            except Exception:
                self._cap = None
            if not self._cap or not self._cap.isOpened():
                self.error_occurred.emit(self._camera_id, f"Cannot open camera: {self._source}")
                return

        self._configure_capture()

        _src_is_live = str(self._source).isdigit() or any(str(self._source).startswith(p) for p in live_prefixes)
        if _src_is_live:
            self._cap.set(cv2.CAP_PROP_FPS, self._fps_limit)

        with contextlib.suppress(Exception):
            actual_w = int(self._cap.get(cv2.CAP_PROP_FRAME_WIDTH) or 0)
            actual_h = int(self._cap.get(cv2.CAP_PROP_FRAME_HEIGHT) or 0)
            actual_fps = float(self._cap.get(cv2.CAP_PROP_FPS) or 0.0)
            actual_exp = float(self._cap.get(cv2.CAP_PROP_EXPOSURE) or 0.0)
            auto_exp = float(self._cap.get(cv2.CAP_PROP_AUTO_EXPOSURE) or 0.0)
            logging.getLogger(__name__).info(
                "Camera %s capture configured: requested_fps=%s actual=%sx%s@%.2f exp=%.2f auto=%.2f",
                self._camera_id,
                self._fps_limit,
                actual_w,
                actual_h,
                actual_fps,
                actual_exp,
                auto_exp,
            )

        detector = get_manager()
        pipeline = PipelineService(self._camera_id)

        executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"infer-cam{self._camera_id}")
        pending_future: Future | None = None
        self._last_state: dict = {}

        display_delay = 1.0 / max(self._fps_limit, 1)
        self._last_fps_time = time.time()
        self._frame_count = 0
        self._last_infer_fps_time = self._last_fps_time
        self._inference_count = 0
        self._infer_fps = 0.0

        is_file = not str(self._source).isdigit() and not any(str(self._source).startswith(p) for p in live_prefixes)
        consecutive_failures = 0
        _MAX_FAILURES = 5 if not is_file else 1
        frame_num = 0
        sec_last_infer_ms = 0.0
        sec_last_face_ms = 0.0
        sec_last_obj_ms = 0.0

        def _do_inference(infer_frame, cid, fw, fh, infer_scale=1.0, source_ts=None):
            try:
                t0 = time.perf_counter()
                det = detector.process_frame(infer_frame, cid)
                infer_ms = (time.perf_counter() - t0) * 1000.0
                record_runtime_metric(
                    "average_inference_time_per_frame",
                    infer_ms,
                    context={"source": "live_camera", "camera_id": cid},
                    min_interval_sec=1.0,
                )
                if infer_scale < 0.999:
                    _inv = 1.0 / infer_scale
                    for _fi in det.get("faces", []):
                        _b = _fi.get("bbox")
                        if _b:
                            _fi["bbox"] = [int(_b[0] * _inv), int(_b[1] * _inv), int(_b[2] * _inv), int(_b[3] * _inv)]
                    for _oi in det.get("objects", []):
                        _b = _oi.get("bbox")
                        if _b:
                            _oi["bbox"] = [int(_b[0] * _inv), int(_b[1] * _inv), int(_b[2] * _inv), int(_b[3] * _inv)]
                primary, all_triggered = build_state(det, cid)
                primary["_triggered"] = all_triggered
                primary["_rule_trigger_perf"] = time.perf_counter() if all_triggered else 0.0
                primary["_fw"] = fw
                primary["_fh"] = fh
                primary["_infer_ms"] = infer_ms
                primary["_face_ms"] = float(det.get("face_time_ms", 0.0) or 0.0)
                primary["_object_ms"] = float(det.get("object_time_ms", 0.0) or 0.0)
                primary["_source_ts"] = float(source_ts or time.time())
                return primary
            except Exception:
                logging.getLogger(__name__).warning("_do_inference failed for camera %s", cid, exc_info=True)
                return {
                    "_triggered": [],
                    "_fw": fw,
                    "_fh": fh,
                    "_source_ts": float(source_ts or time.time()),
                }

        def _handle_inference_result(result, frame, fallback_fw, fallback_fh):
            triggered = result.pop("_triggered", [])
            infer_fw = result.pop("_fw", fallback_fw)
            infer_fh = result.pop("_fh", fallback_fh)
            infer_ms = float(result.pop("_infer_ms", 0.0) or 0.0)
            face_ms = float(result.pop("_face_ms", 0.0) or 0.0)
            object_ms = float(result.pop("_object_ms", 0.0) or 0.0)
            source_ts = float(result.pop("_source_ts", time.time()) or time.time())
            result["_triggered"] = triggered
            result = pipeline.handle_result(
                result,
                frame,
                infer_fw=infer_fw,
                infer_fh=infer_fh,
                enable_inbox=self._inbox_enabled,
                enable_heatmap=get_service_manager().is_active("heatmap_generation"),
                inbox_context=self,
            )
            result["_state_ts"] = source_ts
            self._last_state = result
            self._last_inference_ts = time.time()
            self._inference_count += 1
            infer_fps_elapsed = self._last_inference_ts - self._last_infer_fps_time
            if infer_fps_elapsed >= 1.0:
                self._infer_fps = self._inference_count / infer_fps_elapsed
                self._inference_count = 0
                self._last_infer_fps_time = self._last_inference_ts
            nonlocal sec_last_infer_ms, sec_last_face_ms, sec_last_obj_ms
            sec_last_infer_ms = infer_ms
            sec_last_face_ms = face_ms
            sec_last_obj_ms = object_ms
            self._tune_infer_dim(result)
            if triggered and self._clip_enabled and self._clip_buffer:
                if self._should_save_clip(result):
                    clip_path = self._save_clip_from_buffer(event_ts=source_ts)
                    if clip_path:
                        try:
                            det = result.get("detections", {}) or {}
                            obj_types = [
                                k
                                for k, v in det.items()
                                if k not in ("identity", "gender") and v not in (False, 0, "unknown", None, "none")
                            ]
                            db.add_clip(
                                clip_path,
                                "live",
                                self._camera_id,
                                int(time.time()),
                                result.get("identity"),
                                result.get("triggered_rules") or [],
                                obj_types,
                            )
                        except Exception:
                            logging.getLogger(__name__).exception("Failed to record clip metadata for %s", clip_path)
                        self._last_clip_ts = time.time()

        def _submit_inference(frame, fw, fh):
            source_ts = time.time()
            _INFER_DIM = int(self._infer_dim)
            _max_side = max(fw, fh)
            if _max_side > _INFER_DIM:
                _pre = _INFER_DIM / _max_side
                _infer_frame = cv2.resize(frame, (max(1, int(fw * _pre)), max(1, int(fh * _pre)))).copy()
            else:
                _infer_frame = frame.copy()
                _pre = 1.0
            return executor.submit(
                _do_inference,
                _infer_frame,
                self._camera_id,
                fw,
                fh,
                _pre,
                source_ts,
            )

        while self._running:
            t_start = time.time()
            ret, frame = self._cap.read()

            if not ret:
                consecutive_failures += 1
                if is_file:
                    self._cap.set(cv2.CAP_PROP_POS_FRAMES, 0)
                    consecutive_failures = 0
                    time.sleep(0.05)
                    continue
                if consecutive_failures >= _MAX_FAILURES:
                    self._suppress_errors = True
                    try:
                        self.reconnecting.emit(self._camera_id)
                    except Exception:
                        pass
                    self._cap.release()
                    time.sleep(1.5)
                    try:
                        src = _resolve_source()
                    except Exception:
                        src = self._raw_source
                    self._cap = cv2.VideoCapture(src)
                    if not self._cap.isOpened():
                        self._suppress_errors = False
                        self.error_occurred.emit(self._camera_id, f"Cannot reconnect: {self._source}")
                        break
                    self._suppress_errors = False
                    consecutive_failures = 0
                else:
                    time.sleep(0.05)
                continue

            consecutive_failures = 0
            self._suppress_errors = False
            frame_num += 1
            if not startup_recorded:
                record_runtime_metric(
                    "camera_startup_time",
                    (time.perf_counter() - run_started_at) * 1000.0,
                    context={"camera_id": self._camera_id, "source": str(self._source)},
                )
                startup_recorded = True
            fh, fw = frame.shape[:2]
            self._append_clip_frame(frame, time.time())

            if pending_future is not None and pending_future.done():
                try:
                    result = pending_future.result(timeout=0)
                    _handle_inference_result(result, frame, fw, fh)
                except Exception:
                    logging.getLogger(__name__).exception("Inference result handling failed for camera %s", self._camera_id)
                pending_future = None

            should_try_schedule = pending_future is None and (frame_num % self._infer_interval == 0)
            if should_try_schedule:
                pending_future = _submit_inference(frame, fw, fh)

            self._frame_count += 1
            now = time.time()
            if now - self._last_fps_time >= 1.0:
                self._fps = self._frame_count / (now - self._last_fps_time)
                self._frame_count = 0
                self._last_fps_time = now
                record_runtime_metric(
                    "average_displayed_fps",
                    self._fps,
                    context={"source": "live_camera", "camera_id": self._camera_id},
                    min_interval_sec=1.0,
                )
                self.fps_updated.emit(self._camera_id, self._fps)
            if self._last_inference_ts > 0.0 and now - self._last_inference_ts >= 2.0:
                self._infer_fps = 0.0
                self._inference_count = 0
                self._last_infer_fps_time = now

            if now - self._last_frame_emit_ts >= self._ui_frame_interval_sec:
                self._last_frame_emit_ts = now
                display_state = self._predict_display_state(self._last_state, now, fw, fh)
                display_state["_capture_fps"] = self._fps
                display_state["_infer_fps"] = self._infer_fps
                display_state["_infer_interval"] = int(self._infer_interval or 1)
                self.frame_ready.emit(self._camera_id, frame, display_state)

            elapsed = time.time() - t_start
            sleep_time = display_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)

        executor.shutdown(wait=False)
        if self._cap:
            self._cap.release()

    def stop(self):
        self._running = False
        self.wait(3000)

    def clear_last_state(self):
        self._last_state = {}

    def _prepare_clip_frame(self, frame):
        max_dim = int(self._clip_buffer_max_dim or 0)
        if max_dim <= 0:
            return frame.copy()
        h, w = frame.shape[:2]
        largest = max(h, w)
        if largest <= max_dim:
            return frame.copy()
        scale = max_dim / float(largest)
        return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))))

    def _append_clip_frame(self, frame, now_ts: float):
        clip_frame = self._prepare_clip_frame(frame)
        frame_bytes = int(getattr(clip_frame, "nbytes", 0) or 0)
        self._clip_buffer.append((now_ts, clip_frame))
        self._clip_buffer_bytes += frame_bytes
        max_age = max(1.0, float(self._clip_seconds or _LIVE_CLIP_SECONDS)) + _LIVE_CLIP_LATENCY_SLACK_SEC
        while self._clip_buffer and (
            now_ts - self._clip_buffer[0][0] > max_age
            or self._clip_buffer_bytes > self._clip_max_buffer_bytes
        ):
            _, old = self._clip_buffer.popleft()
            self._clip_buffer_bytes -= int(getattr(old, "nbytes", 0) or 0)

    def _clip_window_frames(self, event_ts: float | None = None) -> list[tuple[float, np.ndarray]]:
        frames = list(self._clip_buffer)
        if not frames:
            return []
        try:
            end_ts = float(event_ts) if event_ts is not None else float(frames[-1][0])
        except (TypeError, ValueError):
            end_ts = float(frames[-1][0])
        seconds = max(1.0, float(self._clip_seconds or _LIVE_CLIP_SECONDS))
        start_ts = end_ts - seconds
        selected = [(ts, frame) for ts, frame in frames if start_ts <= ts <= end_ts]
        return selected or frames

    def _save_clip_from_buffer(self, event_ts: float | None = None) -> str | None:
        try:
            if not db.can_persist_events():
                logging.getLogger(__name__).warning("Live clip skipped: database size limit is reached")
                return None
            os.makedirs("data/clips_live", exist_ok=True)
            frames = self._clip_window_frames(event_ts)
            if not frames:
                return None
            ts0, _ = frames[0]
            ts1, _ = frames[-1]
            duration = max(0.001, ts1 - ts0)
            fps = max(1.0, min(60.0, len(frames) / duration))
            sample = frames[0][1]
            h, w = sample.shape[:2]
            fname = os.path.join("data", "clips_live", f"clip_cam{self._camera_id}_{int(time.time())}.mp4")
            fourcc = cv2.VideoWriter.fourcc(*"mp4v")
            writer = cv2.VideoWriter(fname, fourcc, fps, (w, h))
            if not writer.isOpened():
                raise RuntimeError("VideoWriter failed to open (mp4v)")
            for _, f in frames:
                writer.write(f)
            writer.release()
            logging.getLogger(__name__).info("Live clip saved: %s", fname)
            return fname
        except Exception:
            logging.getLogger(__name__).exception("Live clip save failed for camera %s", self._camera_id)
            return None

    def _should_save_clip(self, result: dict) -> bool:
        now_ts = time.time()
        if now_ts - self._last_clip_ts < max(2.0, self._clip_min_interval):
            return False

        rules = result.get("triggered_rules") or []
        rules_key = tuple(sorted([str(r) for r in rules]))
        identity = result.get("identity") or "unknown"
        if identity == "unknown":
            identity_key = f"cam:{self._camera_id}"
        else:
            identity_key = f"id:{identity}"

        key = (identity_key, rules_key)
        last_ts = self._clip_recent.get(key)
        if last_ts and (now_ts - last_ts < self._clip_repeat_window):
            return False


        if len(self._clip_recent) > 200:
            cutoff = now_ts - max(self._clip_repeat_window, 120.0)
            self._clip_recent = {k: v for k, v in self._clip_recent.items() if v >= cutoff}

        self._clip_recent[key] = now_ts
        return True
