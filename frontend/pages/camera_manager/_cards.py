from __future__ import annotations

import logging
import sqlite3

from PySide6.QtCore import Qt, QTimer, Signal
from PySide6.QtGui import (
    QFont,
    QImage,
    QPainter,
    QPainterPath as _QPPath,
    QPixmap,
)
from PySide6.QtWidgets import (
    QFrame,
    QLabel,
    QSizePolicy,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.services.camera_service import CameraService
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.styles._colors import (
    _ACCENT_BG_12,
    _ACCENT_HI,
    _SUCCESS,
    _SUCCESS_BG_14,
    _MUTED_BG_10,
    _TEXT_MUTED,
    _TEXT_PRI,
    _TEXT_SEC,
)

from ._constants import _pill
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    RADIUS_7,
    SIZE_CONTROL_22,
    SIZE_CONTROL_MID,
    SIZE_PANEL_SM,
    SIZE_PANEL_W_MD,
    SPACE_MD,
    SPACE_XS,
)
from frontend.widgets.base.roster_card_base import (
    apply_roster_card_style,
    build_roster_card_layout,
)
from frontend.styles.page_styles import text_style

logger = logging.getLogger(__name__)


class CardPreviewWidget(QWidget):
    def __init__(self, cam_id: int, enabled: bool, parent=None):
        super().__init__(parent)
        self._cam_id = cam_id
        self._enabled = enabled
        self._pixmap: QPixmap | None = None
        self.setFixedWidth(SIZE_PANEL_SM)
        self.setSizePolicy(QSizePolicy.Policy.Fixed, QSizePolicy.Policy.Expanding)
        self.setAttribute(Qt.WidgetAttribute.WA_TranslucentBackground)
        if enabled:
            self._connect_thread()

    def _connect_thread(self):
        try:
            import cv2 as _cv2
            import numpy as _np
            from backend.camera.camera_manager import get_camera_manager

            _cm = get_camera_manager()
            _thread = _cm.get_thread(self._cam_id)
            if not (_thread and _thread.isRunning()):
                return
            _last: list = [None]

            def _on_frame(cid: int, frame: _np.ndarray, _r):
                if cid == self._cam_id:
                    _last[0] = frame

            _thread.frame_ready.connect(_on_frame)
            _timer = QTimer(self)
            _timer.setInterval(600)

            def _tick():
                f = _last[0]
                if f is None:
                    return
                try:
                    rgb = _cv2.cvtColor(f, _cv2.COLOR_BGR2RGB)
                    h, w = rgb.shape[:2]
                    qi = QImage(rgb.data, w, h, w * 3, QImage.Format.Format_RGB888).copy()
                    self._pixmap = QPixmap.fromImage(qi)
                    self.update()
                except (RuntimeError, ValueError, TypeError):
                    logger.debug("Skipping preview frame conversion cam_id=%s", self._cam_id, exc_info=True)

            _timer.timeout.connect(_tick)
            _timer.start()

            def _cleanup(_t=_thread, _fn=_on_frame, _tm=_timer):
                _tm.stop()
                try:
                    if hasattr(_t, "frame_ready"):
                        _t.frame_ready.disconnect(_fn)
                except (RuntimeError, TypeError):
                    logger.debug("Preview disconnect already released cam_id=%s", self._cam_id, exc_info=True)

            self.destroyed.connect(_cleanup)
        except (ImportError, RuntimeError, OSError):
            logger.warning("Unable to connect camera preview thread cam_id=%s", self._cam_id, exc_info=True)

    def paintEvent(self, _event):
        p = QPainter(self)
        p.setRenderHint(QPainter.RenderHint.Antialiasing)
        p.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        w, h = self.width(), self.height()
        r = float(RADIUS_7)

        clip = _QPPath()
        clip.addRoundedRect(0, 0, w + r, h, r, r)
        p.setClipPath(clip)

        if self._pixmap is not None:
            scaled = self._pixmap.scaled(
                w,
                h,
                Qt.AspectRatioMode.KeepAspectRatioByExpanding,
                Qt.TransformationMode.SmoothTransformation,
            )

            sx = (scaled.width() - w) // 2
            sy = (scaled.height() - h) // 2
            p.drawPixmap(0, 0, scaled, sx, sy, w, h)
        else:
            icon_path = "frontend/assets/icons/camera_offline.png" if not self._enabled else "frontend/assets/icons/camera.png"
            _icon_pix = QPixmap(icon_path)
            if not _icon_pix.isNull():
                max_dim = min(w - SPACE_MD, h - SPACE_MD)
                scaled_icon = _icon_pix.scaled(
                    max_dim,
                    max_dim,
                    Qt.AspectRatioMode.KeepAspectRatio,
                    Qt.TransformationMode.SmoothTransformation,
                )
                ox = (w - scaled_icon.width()) // 2
                oy = (h - scaled_icon.height()) // 2
                p.setOpacity(0.28 if self._enabled else 0.40)
                p.drawPixmap(ox, oy, scaled_icon)
                p.setOpacity(1.0)
        p.end()


class CameraCard(QFrame):
    clicked = Signal(int)

    def __init__(self, cam: dict, is_active: bool = False, on_toggle_changed=None, parent=None):
        super().__init__(parent)
        self._cam_id = cam["id"]
        self._on_toggle_changed = on_toggle_changed
        self._build(cam, is_active)
        self.setCursor(Qt.CursorShape.PointingHandCursor)

    def _build(self, cam: dict, is_active: bool):
        enabled = bool(cam.get("enabled"))
        running = False
        try:
            from backend.camera.camera_manager import get_camera_manager

            thread = get_camera_manager().get_thread(cam["id"])
            running = bool(thread and thread.isRunning())
        except (ImportError, RuntimeError, AttributeError, TypeError, OSError):
            running = False
        face_on = bool(cam.get("face_recognition"))
        try:
            plugins = db.get_camera_plugins(cam["id"])
        except (sqlite3.Error, OSError, ValueError):
            plugins = []

        self.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Fixed)
        apply_roster_card_style(self, "CameraCard", is_active)

        left_layout, info, pills, right = build_roster_card_layout(self, pills_slot_width=SIZE_PANEL_W_MD)
        left_layout.addWidget(CardPreviewWidget(cam["id"], enabled))
        pills_wrap = pills.parentWidget()
        if pills_wrap is not None:
            pills_wrap.setFixedWidth(0)
            pills_wrap.hide()

        full_name = str(cam.get("name", "") or "")
        name_lbl = QLabel(full_name)
        name_lbl.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        name_lbl.setMinimumWidth(0)
        name_lbl.setToolTip(full_name)
        name_font = QFont()
        safe_set_point_size(name_font, FONT_SIZE_CAPTION)
        name_font.setBold(True)
        name_lbl.setFont(name_font)
        name_lbl.setStyleSheet(text_style(_TEXT_PRI if enabled else _TEXT_SEC, extra="background: transparent;"))
        info.setSpacing(SPACE_XS)
        info.addWidget(name_lbl)

        right_pills: list[QLabel] = []
        if enabled:
            right_pills.append(_pill("ENABLED", _SUCCESS, _SUCCESS_BG_14))
        else:
            right_pills.append(_pill("DISABLED", _TEXT_MUTED, _MUTED_BG_10))
        right_pills.append(_pill("RUNNING" if running else "STOPPED", _SUCCESS if running else _TEXT_MUTED, _SUCCESS_BG_14 if running else _MUTED_BG_10))
        if face_on:
            right_pills.append(_pill("FACE", _ACCENT_HI, _ACCENT_BG_12))
        if plugins:
            right_pills.append(_pill(f"{len(plugins)} plugin{'s' if len(plugins) != 1 else ''}", _ACCENT_HI, _ACCENT_BG_12))

        for pill in right_pills:
            right.addWidget(pill)

        toggle = ToggleSwitch(width=SIZE_CONTROL_MID, height=SIZE_CONTROL_22)
        toggle.setChecked(enabled)
        toggle.toggled.connect(lambda v, cid=cam["id"]: self._on_toggle(cid, v))
        right.addWidget(toggle)

    def _on_toggle(self, cam_id: int, enabled: bool):
        try:
            CameraService().set_enabled(cam_id, enabled)
        except (RuntimeError, AttributeError, TypeError, ValueError, OSError):
            logger.warning("Failed to update camera enabled state cam_id=%s", cam_id, exc_info=True)
        if self._on_toggle_changed:
            self._on_toggle_changed()

    def mousePressEvent(self, event):
        if event.button() == Qt.MouseButton.LeftButton:
            self.clicked.emit(self._cam_id)
        super().mousePressEvent(event)
