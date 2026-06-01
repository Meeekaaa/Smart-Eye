from __future__ import annotations

import contextlib
import os
from urllib.parse import urlparse

from backend.repository import db


_VIDEO_EXTENSIONS = {".avi", ".mkv", ".mov", ".mp4", ".mpeg", ".mpg", ".wmv"}


class CameraService:
    @staticmethod
    def validate_source(source: str) -> tuple[bool, str]:
        text = str(source or "").strip()
        if not text:
            return False, "Camera source is required."
        if text.isdecimal():
            return True, ""

        parsed = urlparse(text)
        if parsed.scheme.lower() in {"rtsp", "rtmp", "http", "https"}:
            if parsed.netloc:
                return True, ""
            return False, "Network camera sources must include a host."

        if parsed.scheme and parsed.scheme.lower() not in {"file"}:
            return False, f"Unsupported camera source scheme: {parsed.scheme}."

        path = parsed.path if parsed.scheme.lower() == "file" else text
        if os.path.isfile(path):
            return True, ""
        ext = os.path.splitext(path)[1].lower()
        if ext in _VIDEO_EXTENSIONS:
            return False, "Video file source does not exist."
        return False, "Use a webcam index, RTSP/HTTP URL, or existing video file."

    def add_camera(self, opts: dict) -> int:
        ok, message = self.validate_source(opts.get("source", ""))
        if not ok:
            raise ValueError(message)

        cam_id = db.add_camera(
            name=opts["name"],
            source=opts["source"],
            location=opts.get("location", ""),
            resolution=opts.get("resolution", "1280x720"),
            fps_limit=int(opts.get("fps_limit", 30)),
            face_recognition=int(opts.get("face_recognition", 0)),
            enabled=int(opts.get("enabled", 1)),
        )
        with contextlib.suppress(Exception):
            db.update_camera(cam_id, face_similarity_threshold=float(opts.get("threshold", 0.45)))
        with contextlib.suppress(Exception):
            db.set_setting(f"camera_{cam_id}_max_faces", int(opts.get("max_faces", 16)))
        with contextlib.suppress(Exception):
            db.set_setting(f"camera_{cam_id}_min_face_size", int(opts.get("min_face_size", 24)))
        if opts.get("assign_active_plugins"):
            with contextlib.suppress(Exception):
                for plug in db.get_plugins(enabled_only=True) or []:
                    pid = plug.get("id")
                    if pid is not None:
                        db.assign_plugin_to_camera(cam_id, pid)
        with contextlib.suppress(Exception):
            db.set_setting(f"camera_{cam_id}_plugins_explicit", True)
        return int(cam_id)

    def set_enabled(self, cam_id: int, enabled: bool) -> None:
        db.update_camera(cam_id, enabled=1 if enabled else 0)
        from backend.camera.camera_manager import get_camera_manager

        cm = get_camera_manager()
        if enabled:
            cm.start_camera(cam_id)
        else:
            cm.stop_camera(cam_id)

    def delete_camera(self, cam_id: int) -> None:
        with contextlib.suppress(Exception):
            from backend.camera.camera_manager import get_camera_manager

            get_camera_manager().stop_camera(cam_id)
        db.delete_camera(cam_id)

    def assign_class_override(self, camera_id: int, plugin_class_id: int, enabled: bool, confidence: float) -> None:
        db.assign_camera_plugin_class(camera_id, plugin_class_id, 1 if enabled else 0, confidence)

    def remove_class_override(self, camera_id: int, plugin_class_id: int) -> None:
        db.remove_camera_plugin_class(camera_id, plugin_class_id)
