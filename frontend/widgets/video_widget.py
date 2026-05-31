import time

from PySide6.QtCore import QRect, Qt
from PySide6.QtGui import QBrush, QColor, QFont, QImage, QPainter, QPen, QPixmap
from PySide6.QtWidgets import QLabel, QSizePolicy

from frontend.styles._colors import (
    _ACCENT_HI,
    _BG_HEATMAP_90,
    _BG_SURFACE,
    _BLACK,
    _CLASS_COLOR_1,
    _CLASS_COLOR_2,
    _CLASS_COLOR_3,
    _CLASS_COLOR_4,
    _CLASS_COLOR_5,
    _CLASS_COLOR_6,
    _CLASS_COLOR_7,
    _CLASS_COLOR_8,
    _DANGER_DIM,
    _SUCCESS,
    _TEXT_FAINT,
    _TEXT_ON_ACCENT,
    _WARNING_ORANGE,
    _WHITE_04,
)
from frontend.ui_tokens import FONT_SIZE_LARGE, FONT_WEIGHT_BOLD, RADIUS_LG, SPACE_XXXS

_CLASS_COLORS = [
    _CLASS_COLOR_1,
    _CLASS_COLOR_2,
    _CLASS_COLOR_3,
    _CLASS_COLOR_4,
    _CLASS_COLOR_5,
    _CLASS_COLOR_6,
    _CLASS_COLOR_7,
    _CLASS_COLOR_8,
]


def _class_color(text: str) -> str:
    return _CLASS_COLORS[hash(text) % len(_CLASS_COLORS)]


class VideoWidget(QLabel):
    def __init__(self, camera_name: str = "", parent=None):
        super().__init__(parent)
        self._camera_name = camera_name
        self.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.setMinimumSize(320, 240)
        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Expanding)
        self.setStyleSheet("background-color: {}; border-radius: {}px;".format(_BLACK, RADIUS_LG))
        self._state = {}
        self._show_overlays = True
        self._last_frame = None
        self._frame_w = 1
        self._frame_h = 1
        self._fps = 0.0
        self._render_fps = 0.0
        self._infer_fps = 0.0
        self._has_infer_fps = False
        self._render_count = 0
        self._last_render_fps_time = time.monotonic()

    def update_frame(self, frame, state=None):
        if state is not None:
            self._state = state or {}
            self._fps = float(state.get("_capture_fps", self._fps) or 0.0)
            if "_infer_fps" in state:
                self._infer_fps = float(state.get("_infer_fps") or 0.0)
                self._has_infer_fps = True
        if frame is None:
            return
        self._last_frame = frame
        if len(frame.shape) != 3 or frame.shape[2] != 3:
            return
        self._update_render_fps()
        h, w, ch = frame.shape
        self._frame_w, self._frame_h = w, h
        qimg = QImage(frame.data, w, h, ch * w, QImage.Format.Format_BGR888)
        pixmap = QPixmap.fromImage(qimg)

        viewport_px = max(1, self.width() * self.height())
        frame_px = max(1, w * h)
        use_fast = frame_px > viewport_px * 1.2 or frame_px >= 960 * 540
        scaled = pixmap.scaled(
            self.size(),
            Qt.AspectRatioMode.KeepAspectRatio,
            Qt.TransformationMode.FastTransformation if use_fast else Qt.TransformationMode.SmoothTransformation,
        )
        if self._show_overlays:
            scaled = self._draw_overlays(scaled, w, h)
        self.setPixmap(scaled)

    def _update_render_fps(self):
        self._render_count += 1
        now = time.monotonic()
        elapsed = now - self._last_render_fps_time
        if elapsed >= 1.0:
            self._render_fps = self._render_count / elapsed
            self._render_count = 0
            self._last_render_fps_time = now

    def _scale_bbox(self, bbox, frame_w, frame_h, px_w, px_h):
        sx = px_w / frame_w
        sy = px_h / frame_h
        x1, y1, x2, y2 = bbox
        return (int(x1 * sx), int(y1 * sy), int(x2 * sx), int(y2 * sy))

    def _draw_overlays(self, pixmap: QPixmap, frame_w: int, frame_h: int) -> QPixmap:
        px_w, px_h = pixmap.width(), pixmap.height()
        painter = QPainter(pixmap)
        hi_quality = (px_w * px_h) <= (960 * 540)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing, hi_quality)

        label_font = QFont("Segoe UI", 9, QFont.Weight.Bold)
        painter.setFont(label_font)

        def draw_box(bbox, color_hex, label_text):
            x1, y1, x2, y2 = self._scale_bbox(bbox, frame_w, frame_h, px_w, px_h)
            color = QColor(color_hex)
            painter.setPen(QPen(color, 2))
            painter.setBrush(Qt.BrushStyle.NoBrush)
            painter.drawRoundedRect(x1, y1, x2 - x1, y2 - y1, 4, 4)
            if not label_text:
                return
            fm = painter.fontMetrics()
            text_w = fm.horizontalAdvance(label_text) + 10
            text_h = fm.height() + 4
            bg_rect = QRect(x1, max(0, y1 - text_h), text_w, text_h)
            bg_color = QColor(color_hex)
            bg_color.setAlpha(200)
            painter.setBrush(QBrush(bg_color))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(bg_rect, 3, 3)
            painter.setPen(QColor(_TEXT_ON_ACCENT))
            painter.drawText(bg_rect, Qt.AlignmentFlag.AlignCenter, label_text)

        for face in self._state.get("all_faces", []):
            identity = face.get("identity")
            gender = (face.get("gender") or "unknown").title()
            conf = face.get("confidence") or 0.0
            liveness = face.get("liveness") or 0.0
            pending = bool(face.get("liveness_pending", False))
            secs = int(face.get("liveness_seconds_left", 0.0) or 0)
            spoof = face.get("spoof_type")

            if spoof:
                color = _DANGER_DIM
                if spoof == "landmarks_missing":
                    label = "Face landmarks unavailable"
                elif spoof in ("liveness_model_missing", "passive_unavailable"):
                    label = "Liveness model unavailable"
                elif spoof == "passive_spoof":
                    label = "Spoof suspected"
                elif spoof == "screen_presentation":
                    label = "Screen presentation blocked"
                else:
                    label = "Verification failed"
            elif pending:
                color = _WARNING_ORANGE
                if secs > 0:
                    label = f"Verifying face ({secs}s)"
                else:
                    label = "Verifying face"
            else:
                if identity:
                    if liveness >= 0.5:
                        color = _SUCCESS
                        label = f"{identity} ({gender}) {conf:.1%}"
                    else:
                        color = _WARNING_ORANGE
                        label = "Unverified face"
                else:
                    color = _DANGER_DIM
                    label = f"Unknown ({gender}) {conf:.1%}" if conf > 0.1 else f"Face ({gender})"

            draw_box(face["bbox"], color, label)

        if not self._state.get("all_faces") and self._state.get("face_bbox"):
            identity = self._state.get("identity", "Unknown")
            gender = (self._state.get("gender") or "unknown").title()
            conf = self._state.get("face_confidence", 0.0)
            color = _SUCCESS if identity and identity != "Unknown" else _DANGER_DIM
            draw_box(self._state["face_bbox"], color, f"{identity or 'Unknown'} ({gender}) {conf:.1%}")

        for obj in self._state.get("object_bboxes", []):
            cls = obj.get("class_name", obj.get("plugin_name", "?"))
            conf = obj.get("confidence", 0.0)
            color = obj.get("bbox_color") or _class_color(cls)
            draw_box(obj["bbox"], color, f"{cls} {conf:.1%}")

        if self._camera_name:
            painter.setFont(QFont("Segoe UI", 8))
            painter.setPen(QColor(255, 255, 255, 160))
            painter.drawText(QRect(px_w - 160, 6, 154, 18), Qt.AlignmentFlag.AlignRight, self._camera_name)

        n_faces = len(self._state.get("all_faces", []))
        n_obj = len(self._state.get("object_bboxes", []))
        if n_faces or n_obj:
            parts = []
            if n_faces:
                parts.append(f"{n_faces} face{'s' if n_faces > 1 else ''}")
            if n_obj:
                parts.append(f"{n_obj} obj")
            badge_text = "  ".join(parts)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            bw = fm.horizontalAdvance(badge_text) + 12
            bh = fm.height() + 6
            bg = QColor(_BG_SURFACE)
            bg.setAlpha(200)
            painter.setBrush(QBrush(bg))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRect(6, 6, bw, bh), 4, 4)
            painter.setPen(QColor(_ACCENT_HI))
            painter.drawText(QRect(6, 6, bw, bh), Qt.AlignmentFlag.AlignCenter, badge_text)

        if self._fps > 0 or self._render_fps > 0 or self._has_infer_fps:
            metrics = []
            if self._fps > 0:
                metrics.append(("Cam", self._fps))
            if self._render_fps > 0:
                metrics.append(("UI", self._render_fps))
            if self._has_infer_fps:
                metrics.append(("AI", self._infer_fps))
            fps_text = "  ".join(f"{name} {value:.1f}" for name, value in metrics)
            painter.setFont(QFont("Segoe UI", 8, QFont.Weight.Bold))
            fm = painter.fontMetrics()
            bw = fm.horizontalAdvance(fps_text) + 10
            if bw > px_w - 12:
                fps_text = "  ".join(f"{name[0]} {value:.0f}" for name, value in metrics)
                bw = fm.horizontalAdvance(fps_text) + 10
            bh = fm.height() + 4
            bg2 = QColor(_BG_SURFACE)
            bg2.setAlpha(180)
            painter.setBrush(QBrush(bg2))
            painter.setPen(Qt.PenStyle.NoPen)
            painter.drawRoundedRect(QRect(6, px_h - bh - 6, bw, bh), 3, 3)
            displayed_fps = self._render_fps or self._fps
            fps_color = _SUCCESS if displayed_fps >= 20 else (_WARNING_ORANGE if displayed_fps >= 10 else _DANGER_DIM)
            painter.setPen(QColor(fps_color))
            painter.drawText(QRect(6, px_h - bh - 6, bw, bh), Qt.AlignmentFlag.AlignCenter, fps_text)

        painter.end()
        return pixmap

    def set_fps(self, fps: float):
        self._fps = fps

    def set_show_overlays(self, show):
        self._show_overlays = show

    def set_camera_name(self, name: str):
        self._camera_name = name

    def show_placeholder(self, text="No Signal"):
        self.clear()
        self.setText(text)
        self.setStyleSheet(
            "background-color: {bg}; color: {text}; font-size: {size}px; "
            "font-weight: {weight}; border-radius: {radius}px; border: {border_w}px solid {border};".format(
                bg=_BG_HEATMAP_90,
                text=_TEXT_FAINT,
                size=FONT_SIZE_LARGE,
                weight=FONT_WEIGHT_BOLD,
                radius=RADIUS_LG,
                border_w=SPACE_XXXS,
                border=_WHITE_04,
            )
        )
