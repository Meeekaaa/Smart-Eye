from __future__ import annotations

import logging
import contextlib

from PySide6.QtCore import Qt, Signal, QThread
from PySide6.QtGui import QFont
from PySide6.QtWidgets import (
    QComboBox,
    QFrame,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QVBoxLayout,
    QWidget,
)

from backend.repository import db
from frontend.app_theme import safe_set_point_size
from frontend.widgets.action_feedback import make_manager_footer_layout
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.ui_tokens import (
    FONT_SIZE_CAPTION,
    FONT_SIZE_SUBHEAD,
    SIZE_BTN_W_80,
    SIZE_CONTROL_MD,
    SIZE_SECTION_H,
    SPACE_10,
    SPACE_14,
    SPACE_20,
    SPACE_6,
    SPACE_MD,
    SPACE_SM,
    SPACE_XL,
    SPACE_XXXS,
    SPACE_XS,
)

from ._constants import (
    _BG_RAISED,
    _BG_SURFACE,
    _BORDER_DIM,
    _TEXT_BTN_BLUE,
    _TEXT_BTN_GHOST,
    _TEXT_MUTED,
    _TEXT_PRI,
    _combo_ss,
    _input_ss,
    _make_sdiv,
    _spin_ss,
    _srow,
)

logger = logging.getLogger(__name__)


class AddCameraPanel(QWidget):
    saved = Signal()
    close_requested = Signal()

    def __init__(self, parent=None):
        super().__init__(parent)
        self._saving = False
        self._worker = None
        self._build_ui()

    def _build_ui(self):
        lay = QVBoxLayout(self)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(0)

        banner = QFrame()
        banner.setStyleSheet(f"QFrame{{background:{_BG_RAISED};border:none;}}")
        bh = QHBoxLayout(banner)
        bh.setContentsMargins(SPACE_20, SPACE_14, SPACE_20, SPACE_14)
        bh.setSpacing(SPACE_MD)
        nf = QFont()
        safe_set_point_size(nf, FONT_SIZE_SUBHEAD)
        nf.setBold(True)
        t = QLabel("Add Camera")
        t.setFont(nf)
        t.setStyleSheet(f"color:{_TEXT_PRI};")
        bh.addWidget(t)
        bh.addStretch()

        close_x = QPushButton("✕")
        close_x.setFixedSize(SIZE_CONTROL_MD, SIZE_CONTROL_MD)
        close_x.setStyleSheet(_TEXT_BTN_GHOST)
        close_x.clicked.connect(lambda: self.close_requested.emit())
        bh.addWidget(close_x)
        lay.addWidget(banner)

        sep = QFrame()
        sep.setFrameShape(QFrame.Shape.HLine)
        sep.setStyleSheet(f"background:{_BORDER_DIM};border:none;max-height:{SPACE_XXXS}px;")
        lay.addWidget(sep)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        scroll.setVerticalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAsNeeded)
        scroll.setStyleSheet(f"border:none;background:{_BG_SURFACE};")
        body = QWidget()
        body.setStyleSheet(f"background:{_BG_SURFACE};")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, SPACE_XL)
        bl.setSpacing(0)
        scroll.setWidget(body)
        lay.addWidget(scroll, stretch=1)

        req_lbl = QLabel("Fields marked * are required.")
        req_lbl.setStyleSheet(f"font-size:{FONT_SIZE_CAPTION}px;color:{_TEXT_MUTED};padding:{SPACE_10}px {SPACE_XL}px {SPACE_6}px;")
        bl.addWidget(req_lbl)

        bl.addWidget(_make_sdiv("General"))

        self._e_name = QLineEdit()
        self._e_name.setPlaceholderText("e.g. Front Door")
        self._e_name.setFixedHeight(SIZE_SECTION_H)
        self._e_name.setStyleSheet(_input_ss())
        bl.addWidget(_srow("Name *", self._e_name))

        self._e_source = QLineEdit()
        self._e_source.setPlaceholderText("rtsp://… or 0 for webcam")
        self._e_source.setFixedHeight(SIZE_SECTION_H)
        self._e_source.setStyleSheet(_input_ss())
        bl.addWidget(_srow("Source *", self._e_source))

        self._e_location = QLineEdit()
        self._e_location.setPlaceholderText("e.g. Entrance, Room 1")
        self._e_location.setFixedHeight(SIZE_SECTION_H)
        self._e_location.setStyleSheet(_input_ss())
        bl.addWidget(_srow("Location", self._e_location))

        self._res_combo = QComboBox()
        for res in ["640x480", "1280x720", "1920x1080"]:
            self._res_combo.addItem(res)
        self._res_combo.setCurrentIndex(1)
        self._res_combo.setStyleSheet(_combo_ss())
        bl.addWidget(_srow("Resolution", self._res_combo))

        self._fps_spin = QSpinBox()
        self._fps_spin.setRange(1, 60)
        self._fps_spin.setValue(30)
        self._fps_spin.setStyleSheet(_spin_ss())
        bl.addWidget(_srow("FPS Limit", self._fps_spin))

        bl.addSpacing(SPACE_XS)
        bl.addWidget(_make_sdiv("Detection"))

        def _left(toggle: ToggleSwitch) -> QWidget:
            c = QWidget()
            c.setStyleSheet("background:transparent; border:none;")
            h = QHBoxLayout(c)
            h.setContentsMargins(0, 0, 0, 0)
            h.setSpacing(0)
            h.addWidget(toggle)
            h.addStretch()
            return c

        self._face_toggle = ToggleSwitch()
        self._face_toggle.setChecked(False)
        bl.addWidget(_srow("Face Recognition", _left(self._face_toggle)))

        self._active_plugins_toggle = ToggleSwitch()
        self._active_plugins_toggle.setChecked(True)
        bl.addWidget(_srow("Active Plugins", _left(self._active_plugins_toggle)))

        self._enabled_toggle = ToggleSwitch()
        self._enabled_toggle.setChecked(True)
        bl.addWidget(_srow("Enable on Add", _left(self._enabled_toggle)))

        self._thresh_spin = QSpinBox()
        self._thresh_spin.setRange(1, 100)
        self._thresh_spin.setValue(45)
        self._thresh_spin.setSuffix("%")
        self._thresh_spin.setStyleSheet(_spin_ss())
        bl.addWidget(_srow("Match Threshold", self._thresh_spin))

        self._max_faces_spin = QSpinBox()
        self._max_faces_spin.setRange(1, 256)
        self._max_faces_spin.setValue(16)
        self._max_faces_spin.setStyleSheet(_spin_ss())
        bl.addWidget(_srow("Max Faces / Frame", self._max_faces_spin))

        self._min_face_size_spin = QSpinBox()
        self._min_face_size_spin.setRange(10, 500)
        self._min_face_size_spin.setValue(24)
        self._min_face_size_spin.setSuffix(" px")
        self._min_face_size_spin.setStyleSheet(_spin_ss())
        bl.addWidget(_srow("Min Face Size", self._min_face_size_spin))

        bl.addStretch()

        ab_sep = QFrame()
        ab_sep.setFrameShape(QFrame.Shape.HLine)
        ab_sep.setStyleSheet(f"background:{_BORDER_DIM};border:none;max-height:{SPACE_XXXS}px;")
        lay.addWidget(ab_sep)

        cancel_btn = QPushButton("Cancel")
        cancel_btn.setFixedHeight(SIZE_CONTROL_MD)
        cancel_btn.setFixedWidth(SIZE_BTN_W_80)
        cancel_btn.setStyleSheet(_TEXT_BTN_GHOST)
        cancel_btn.clicked.connect(lambda: self.close_requested.emit())

        add_btn = QPushButton("Save")
        add_btn.setFixedHeight(SIZE_CONTROL_MD)
        add_btn.setFixedWidth(SIZE_BTN_W_80)
        add_btn.setStyleSheet(_TEXT_BTN_BLUE)
        add_btn.clicked.connect(self._do_save)
        lay.addLayout(
            make_manager_footer_layout(
                right_widgets=[cancel_btn, add_btn],
                margins=(SPACE_XL, SPACE_10, SPACE_XL, SPACE_MD),
                spacing=SPACE_SM,
            )
        )
        self._add_btn = add_btn

    def reset(self):
        self._e_name.clear()
        self._e_source.clear()
        self._e_location.clear()
        self._res_combo.setCurrentIndex(1)
        self._fps_spin.setValue(30)
        self._face_toggle.setChecked(True)
        self._active_plugins_toggle.setChecked(True)
        self._thresh_spin.setValue(45)
        self._max_faces_spin.setValue(16)
        self._min_face_size_spin.setValue(24)
        self._enabled_toggle.setChecked(True)

    def _set_busy(self, busy: bool):
        self._saving = busy
        if hasattr(self, "_add_btn"):
            self._add_btn.setEnabled(not busy)
        self.setEnabled(not busy)

    def _do_save(self):
        name = self._e_name.text().strip()
        source = self._e_source.text().strip()
        logger.info("camera_manager.add start name=%s source=%s", name, source)
        if not name:
            logger.warning("Camera name is required.")
            self._e_name.setFocus()
            return
        if not source:
            logger.warning("Camera source is required.")
            self._e_source.setFocus()
            return

        if self._saving:
            return
        self._set_busy(True)

        params = dict(
            name=name,
            source=source,
            location=self._e_location.text().strip(),
            resolution=self._res_combo.currentText(),
            fps_limit=self._fps_spin.value(),
            face_recognition=1 if self._face_toggle.isChecked() else 0,
            assign_active_plugins=1 if self._active_plugins_toggle.isChecked() else 0,
            enabled=1 if self._enabled_toggle.isChecked() else 0,
            threshold=self._thresh_spin.value() / 100.0,
            max_faces=int(self._max_faces_spin.value()),
            min_face_size=int(self._min_face_size_spin.value()),
        )

        class _AddWorker(QThread):
            done = Signal(object, object)

            def __init__(self, opts, parent=None):
                super().__init__(parent)
                self.opts = opts

            def run(self):
                try:
                    cam_id = db.add_camera(
                        name=self.opts["name"],
                        source=self.opts["source"],
                        location=self.opts["location"],
                        resolution=self.opts["resolution"],
                        fps_limit=self.opts["fps_limit"],
                        face_recognition=self.opts["face_recognition"],
                        enabled=self.opts["enabled"],
                    )
                    with contextlib.suppress(Exception):
                        db.update_camera(cam_id, face_similarity_threshold=self.opts["threshold"])
                    with contextlib.suppress(Exception):
                        db.set_setting(f"camera_{cam_id}_max_faces", self.opts["max_faces"])
                    with contextlib.suppress(Exception):
                        db.set_setting(f"camera_{cam_id}_min_face_size", self.opts["min_face_size"])
                    if self.opts.get("assign_active_plugins"):
                        with contextlib.suppress(Exception):
                            for plug in db.get_plugins(enabled_only=True) or []:
                                pid = plug.get("id")
                                if pid is not None:
                                    db.assign_plugin_to_camera(cam_id, pid)
                    with contextlib.suppress(Exception):
                        db.set_setting(f"camera_{cam_id}_plugins_explicit", True)
                    self.done.emit(None, cam_id)
                except (RuntimeError, AttributeError, TypeError, ValueError, OSError) as exc:
                    self.done.emit(exc, None)

        self._worker = _AddWorker(params, self)

        def _finish(err, cam_id):
            self._set_busy(False)
            self._worker = None
            if err:
                logger.exception("camera_manager.add failed name=%s source=%s", name, source)
                return
            if params["enabled"] and cam_id is not None:
                with contextlib.suppress(Exception):
                    from backend.camera.camera_manager import get_camera_manager

                    get_camera_manager().start_camera(cam_id)
            logger.info("camera_manager.add success id=%s name=%s enabled=%s", cam_id, name, params["enabled"])
            self.reset()
            self.saved.emit()

        self._worker.done.connect(_finish)
        self._worker.finished.connect(self._worker.deleteLater)
        self._worker.start()

