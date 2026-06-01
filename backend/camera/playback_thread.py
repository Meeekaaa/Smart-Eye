import collections
import contextlib
import json
import ast
import logging
import os
import time
from concurrent.futures import Future, ThreadPoolExecutor

import cv2
import numpy as np
from PySide6.QtCore import QMutex, QThread, Signal

from backend.pipeline.detector_manager import get_manager
from backend.pipeline.inference_utils import build_state
from backend.repository import db

_AUTO_CLIP_SECONDS = 5
_AUTO_CLIP_LATENCY_SLACK_SECONDS = 5


class PlaybackThread(QThread):
    frame_ready = Signal(int, np.ndarray, dict)
    playback_finished = Signal(int)
    clip_saved = Signal(str)
    clip_failed = Signal(str)

    def __init__(self, video_path, virtual_camera_id=-1, fps_limit=30, parent=None):
        super().__init__(parent)
        self._video_path = video_path
        self._camera_id = virtual_camera_id
        self._fps_limit = fps_limit
        self._fps_lock = QMutex()
        self._running = False
        self._paused = False
        self._seek_frame = -1
        self._cap = None
        self._total_frames = 0
        self._plugins_enabled = False
        self._face_detection_enabled = True
        self._disabled_object_classes: set[str] = set()
        self._record_enabled = False
        self._frame_buffer: collections.deque = collections.deque()
        self._frame_buffer_bytes = 0
        self._clip_max_buffer_bytes = 128 * 1024 * 1024
        self._clip_buffer_max_dim = 640
        self._video_fps_actual: float = 30.0
        try:
            self._infer_target_fps = float(db.get_float("playback_infer_target_fps", 12.0) or 12.0)
        except Exception:
            self._infer_target_fps = 12.0
        self._infer_target_fps = max(1.0, min(30.0, self._infer_target_fps))

        try:
            self._face_detection_enabled = bool(db.get_bool("playback_face_detection_enabled", True))
        except Exception:
            self._face_detection_enabled = True
        try:
            raw = db.get_setting("playback_disabled_object_classes", "[]")
            if isinstance(raw, str):
                try:
                    parsed = json.loads(raw or "[]")
                except (TypeError, ValueError, json.JSONDecodeError):
                    parsed = ast.literal_eval(raw) if raw else []
            else:
                parsed = raw or []
            self._disabled_object_classes = {str(v).strip().lower() for v in parsed if str(v).strip()}
        except Exception:
            self._disabled_object_classes = set()
        try:
            self._clip_max_buffer_bytes = max(8, int(db.get_int("live_clip_max_buffer_mb", 128) or 128)) * 1024 * 1024
            self._clip_buffer_max_dim = max(160, int(db.get_int("live_clip_buffer_max_dim", 640) or 640))
        except Exception:
            self._clip_max_buffer_bytes = 128 * 1024 * 1024
            self._clip_buffer_max_dim = 640

    @property
    def camera_id(self):
        return self._camera_id

    def run(self):
        self._running = True
        with contextlib.suppress(Exception):
            get_manager().clear_camera_state(self._camera_id)
        self._cap = cv2.VideoCapture(self._video_path)
        if not self._cap.isOpened():
            logging.getLogger(__name__).warning("Playback: failed to open video %s", self._video_path)
            self.playback_finished.emit(self._camera_id)
            return
        self._total_frames = int(self._cap.get(cv2.CAP_PROP_FRAME_COUNT))
        video_fps = self._cap.get(cv2.CAP_PROP_FPS) or 30
        self._video_fps_actual = video_fps
        infer_stride = max(1, int(round(video_fps / max(1.0, self._infer_target_fps))))
        logging.getLogger(__name__).info(
            "Playback: start path=%s frames=%s fps=%.2f cam_id=%s infer_target_fps=%.1f stride=%s",
            self._video_path,
            self._total_frames,
            video_fps,
            self._camera_id,
            self._infer_target_fps,
            infer_stride,
        )
        buf_max = max(1, int(video_fps * (_AUTO_CLIP_SECONDS + _AUTO_CLIP_LATENCY_SLACK_SECONDS)))
        infer_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"play-infer-cam{self._camera_id}")
        clip_executor = ThreadPoolExecutor(max_workers=1, thread_name_prefix=f"play-clip-cam{self._camera_id}")
        clip_futures: set[Future] = set()
        detector = get_manager()
        pending_future: Future | None = None
        last_detect_state: dict = {"triggered_rules": [], "frame_index": 0}
        last_detect_frame_idx = -1
        frame_idx = 0
        _clip_cooldown = 0

        def _evaluate_frame(frame, w, h, infer_idx):
            detection_results = detector.process_frame(
                frame,
                self._camera_id,
                run_plugins=self._plugins_enabled,
                run_faces=self._face_detection_enabled,
                identify_faces=self._face_detection_enabled,
                lightweight=not self._face_detection_enabled,
            )
            if not self._plugins_enabled:
                detection_results["objects"] = []
            if not self._face_detection_enabled:
                detection_results["faces"] = []
            if self._disabled_object_classes:
                detection_results["objects"] = [
                    o
                    for o in detection_results.get("objects", [])
                    if str(o.get("class_name") or o.get("class") or "").strip().lower() not in self._disabled_object_classes
                ]
            primary, triggered = build_state(
                detection_results,
                self._camera_id,
                evaluate_rule_triggers=self._record_enabled,
            )
            return infer_idx, frame, w, h, primary, triggered

        def _handle_triggers(primary_state, triggered, frame_idx, video_fps):
            nonlocal _clip_cooldown
            if not triggered:
                primary_state["triggered_rules"] = []
                primary_state["active_violations"] = []
                return

            rule_names = [str(r.get("name") or "Rule") for r in triggered]
            primary_state["triggered_rules"] = rule_names
            primary_state["active_violations"] = [
                {"rule": name, "rule_name": name, "camera_id": self._camera_id}
                for name in rule_names
            ]
            logging.getLogger(__name__).info(
                "Playback: rule trigger cam_id=%s frame=%s rules=%s record=%s buffer=%s cooldown=%s",
                self._camera_id,
                frame_idx,
                rule_names,
                self._record_enabled,
                len(self._frame_buffer),
                _clip_cooldown,
            )
            if self._record_enabled and self._frame_buffer and _clip_cooldown <= 0:
                if self._save_clip_async(
                    clip_executor,
                    clip_futures,
                    video_fps,
                    primary_state,
                    rule_names,
                    event_frame_idx=frame_idx,
                ):
                    _clip_cooldown = int(video_fps * _AUTO_CLIP_SECONDS)

        while self._running and not self.isInterruptionRequested():
            force_read = False
            if self._seek_frame >= 0:
                self._cap.set(cv2.CAP_PROP_POS_FRAMES, self._seek_frame)
                frame_idx = self._seek_frame
                self._seek_frame = -1
                force_read = True
                if pending_future is not None and not pending_future.done():
                    pending_future.cancel()
                pending_future = None
                last_detect_state = {"triggered_rules": [], "frame_index": frame_idx}
                last_detect_frame_idx = -1
            if self._paused and not force_read:
                time.sleep(0.05)
                continue
            t_start = time.time()
            ret, frame = self._cap.read()
            if not ret:
                logging.getLogger(__name__).info("Playback: reached end of video")
                self.playback_finished.emit(self._camera_id)
                break

            if self._record_enabled and not self._paused:
                self._append_clip_frame(frame_idx, frame)
                while len(self._frame_buffer) > buf_max:
                    _idx, old_frame = self._frame_buffer.popleft()
                    self._frame_buffer_bytes -= int(getattr(old_frame, "nbytes", 0) or 0)

            h, w = frame.shape[:2]

            if pending_future is not None and pending_future.done():
                try:
                    det_idx, det_frame, det_w, det_h, det_state, det_triggered = pending_future.result(timeout=0)
                    if det_idx >= last_detect_frame_idx:
                        if self._record_enabled:
                            _handle_triggers(det_state, det_triggered, det_idx, video_fps)
                        else:
                            det_state["triggered_rules"] = []
                            det_state["active_violations"] = []
                        det_state["frame_index"] = det_idx
                        last_detect_state = det_state
                        last_detect_frame_idx = det_idx
                except RuntimeError as exc:
                    msg = str(exc).lower()
                    if "interpreter shutdown" in msg or "cannot schedule new futures after shutdown" in msg:
                        logging.getLogger(__name__).info("Playback: stopping detection loop due shutdown")
                        break
                    logging.getLogger(__name__).warning(
                        "Playback: runtime detection failure at frame=%s cam_id=%s",
                        frame_idx,
                        self._camera_id,
                        exc_info=True,
                    )
                except Exception:
                    logging.getLogger(__name__).warning(
                        "Playback: detection failure at frame=%s cam_id=%s",
                        frame_idx,
                        self._camera_id,
                        exc_info=True,
                    )
                pending_future = None

            should_schedule = (
                (self._plugins_enabled or self._face_detection_enabled)
                and pending_future is None
                and self._running
                and not self.isInterruptionRequested()
                and (
                    frame_idx
                    % (
                        max(1, int(round(video_fps / max(1.0, min(self._infer_target_fps, 8.0)))))
                        if self._face_detection_enabled and not self._plugins_enabled
                        else infer_stride
                    )
                    == 0
                    or last_detect_frame_idx < 0
                )
            )
            if should_schedule:
                try:
                    pending_future = infer_executor.submit(_evaluate_frame, frame, w, h, frame_idx)
                except RuntimeError as exc:
                    msg = str(exc).lower()
                    if "interpreter shutdown" in msg or "cannot schedule new futures after shutdown" in msg:
                        logging.getLogger(__name__).info("Playback: infer submit skipped due shutdown")
                        break
                    logging.getLogger(__name__).warning("Playback: infer submit failed", exc_info=True)

            if (not self._plugins_enabled and not self._face_detection_enabled) and pending_future is not None:
                if not pending_future.done():
                    pending_future.cancel()
                pending_future = None

            primary_state = dict(last_detect_state) if (self._plugins_enabled or self._face_detection_enabled) else {"triggered_rules": []}
            primary_state["frame_index"] = frame_idx

            if _clip_cooldown > 0:
                _clip_cooldown -= 1

            self.frame_ready.emit(self._camera_id, frame, primary_state)
            if not self._paused:
                frame_idx += 1
            elapsed = time.time() - t_start
            self._fps_lock.lock()
            try:
                fps_limit = self._fps_limit
            finally:
                self._fps_lock.unlock()
            frame_delay = 1.0 / max(0.25, fps_limit)
            sleep_time = frame_delay - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
        if pending_future is not None and not pending_future.done():
            pending_future.cancel()
        infer_executor.shutdown(wait=False)
        clip_executor.shutdown(wait=True)
        with contextlib.suppress(Exception):
            detector.clear_camera_state(self._camera_id)
        if self._cap:
            self._cap.release()

    def _prepare_clip_frame(self, frame: np.ndarray) -> np.ndarray:
        max_dim = int(self._clip_buffer_max_dim or 0)
        if max_dim <= 0:
            return frame.copy()
        h, w = frame.shape[:2]
        longest = max(h, w)
        if longest <= max_dim:
            return frame.copy()
        scale = max_dim / float(longest)
        return cv2.resize(frame, (max(1, int(w * scale)), max(1, int(h * scale))), interpolation=cv2.INTER_AREA)

    def _append_clip_frame(self, frame_idx: int, frame: np.ndarray) -> None:
        clip_frame = self._prepare_clip_frame(frame)
        frame_bytes = int(getattr(clip_frame, "nbytes", 0) or 0)
        self._frame_buffer.append((int(frame_idx), clip_frame))
        self._frame_buffer_bytes += frame_bytes
        while self._frame_buffer and self._frame_buffer_bytes > self._clip_max_buffer_bytes:
            _idx, old_frame = self._frame_buffer.popleft()
            self._frame_buffer_bytes -= int(getattr(old_frame, "nbytes", 0) or 0)

    def _buffered_clip_frames(self, fps: float, event_frame_idx: int | None = None) -> list[np.ndarray]:
        entries = list(self._frame_buffer)
        if not entries:
            return []
        max_frames = max(1, int(float(fps or 30.0) * _AUTO_CLIP_SECONDS))
        if event_frame_idx is None:
            selected = entries[-max_frames:]
        else:
            start_idx = int(event_frame_idx) - max_frames + 1
            selected = [
                entry
                for entry in entries
                if isinstance(entry, tuple) and start_idx <= int(entry[0]) <= int(event_frame_idx)
            ]
        if not selected:
            selected = entries[-max_frames:]
        out = []
        for entry in selected:
            if isinstance(entry, tuple):
                out.append(entry[1])
            else:
                out.append(entry)
        return out

    def _save_clip(
        self,
        fps: float,
        state: dict | None = None,
        rules: list[str] | None = None,
        event_frame_idx: int | None = None,
    ) -> str | None:
        frames = self._buffered_clip_frames(fps, event_frame_idx=event_frame_idx)
        return self._write_clip(frames, fps, state=state, rules=rules)

    def _save_clip_async(
        self,
        executor: ThreadPoolExecutor,
        futures: set[Future],
        fps: float,
        state: dict | None = None,
        rules: list[str] | None = None,
        event_frame_idx: int | None = None,
    ) -> bool:
        frames = self._buffered_clip_frames(fps, event_frame_idx=event_frame_idx)
        if not frames:
            logging.getLogger(__name__).warning("Playback: no buffered frames; skipping clip save")
            return False
        future = executor.submit(self._write_clip, frames, fps, state, rules)
        futures.add(future)

        def _done(done_future: Future) -> None:
            futures.discard(done_future)
            with contextlib.suppress(Exception):
                done_future.result()

        future.add_done_callback(_done)
        return True

    def _write_clip(
        self,
        frames: list[np.ndarray],
        fps: float,
        state: dict | None = None,
        rules: list[str] | None = None,
    ) -> str | None:
        try:
            if not db.can_persist_events():
                logging.getLogger(__name__).warning("Playback clip skipped: database size limit is reached")
                return None
            os.makedirs("data/clips", exist_ok=True)
            fname = os.path.join("data", "clips", f"clip_{time.time_ns()}.mp4")
            if not frames:
                logging.getLogger(__name__).warning("Playback: no buffered frames; skipping clip save")
                return None
            h, w = frames[0].shape[:2]
            fourcc = cv2.VideoWriter.fourcc(*"mp4v")
            writer = cv2.VideoWriter(fname, fourcc, fps, (w, h))
            if not writer.isOpened():
                raise RuntimeError("VideoWriter failed to open (mp4v)")
            try:
                for f in frames:
                    writer.write(f)
            finally:
                writer.release()
            try:
                det = (state or {}).get("detections", {}) or {}
                obj_types = [
                    k
                    for k, v in det.items()
                    if k not in ("identity", "gender") and v not in (False, 0, "unknown", None, "none")
                ]
                db.add_clip(
                    fname,
                    "playback",
                    self._camera_id,
                    int(time.time()),
                    (state or {}).get("identity"),
                    rules or [],
                    obj_types,
                )
            except Exception:
                logging.getLogger(__name__).exception("Playback: failed to record clip metadata")
            self.clip_saved.emit(fname)
            logging.getLogger(__name__).info("Playback: clip saved %s", fname)
            return fname
        except Exception as e:
            msg = f"Clip save failed: {e}"
            logging.getLogger(__name__).exception("Playback: failed to save clip")
            self.clip_failed.emit(msg)
            return None

    def stop(self):
        self._running = False
        self._paused = False
        self.requestInterruption()

    def pause(self):
        self._paused = True

    def resume(self):
        self._paused = False

    def seek(self, frame_number):
        self._seek_frame = frame_number

    def set_plugins_enabled(self, enabled: bool):
        self._plugins_enabled = bool(enabled)

    def set_detection_enabled(self, enabled: bool):
        # Backward-compatible alias for older call sites.
        self.set_plugins_enabled(enabled)

    def set_face_detection_enabled(self, enabled: bool):
        self._face_detection_enabled = bool(enabled)

    def set_disabled_object_classes(self, class_names: set[str] | list[str]):
        self._disabled_object_classes = {str(v).strip().lower() for v in (class_names or set()) if str(v).strip()}

    def set_record_enabled(self, enabled: bool):
        self._record_enabled = bool(enabled)

    def set_fps_limit(self, fps_limit: float) -> None:
        self._fps_lock.lock()
        try:
            self._fps_limit = max(0.25, float(fps_limit))
        finally:
            self._fps_lock.unlock()

    @property
    def total_frames(self):
        return self._total_frames

    @property
    def is_paused(self):
        return self._paused
