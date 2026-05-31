from __future__ import annotations

import logging
import contextlib

from PySide6.QtCore import QPropertyAnimation
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QScrollArea,
    QVBoxLayout,
    QWidget,
    QGraphicsOpacityEffect,
)

from backend.repository import db
from frontend.widgets.toggle_switch import ToggleSwitch
from frontend.styles._colors import _SUCCESS
from frontend.ui_tokens import (
    FONT_SIZE_LABEL,
    FONT_WEIGHT_BOLD,
    SIZE_BTN_W_100,
    SPACE_20,
    SPACE_MD,
    SPACE_XL,
)

from ._constants import (
    _PRIMARY_BTN,
    _make_sdiv,
    _srow,
)

logger = logging.getLogger(__name__)


class DetectionTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._build_ui()

    def _build_ui(self) -> None:
        root = QVBoxLayout(self)
        root.setContentsMargins(0, 0, 0, 0)
        root.setSpacing(0)

        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setFrameShape(QFrame.Shape.NoFrame)
        body = QWidget()
        body.setStyleSheet("background: transparent;")
        bl = QVBoxLayout(body)
        bl.setContentsMargins(0, 0, 0, SPACE_XL)
        bl.setSpacing(0)
        scroll.setWidget(body)
        root.addWidget(scroll, stretch=1)

        bl.addWidget(_make_sdiv("Face Recognition"))

        self._face_global_toggle = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Global Face Recognition",
                self._face_global_toggle,
                hint="Master switch for live face recognition. Per-camera settings still apply.",
            )
        )

        self._gender_toggle = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Gender Analytics",
                self._gender_toggle,
                hint="Load the optional gender/age sub-model so logs and analytics can include gender.",
            )
        )

        self._liveness_toggle = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Liveness / Human Verification",
                self._liveness_toggle,
                hint="Verify faces passively; use an ONNX anti-spoof model when configured.",
            )
        )

        bl.addStretch()
        bl.addWidget(self._make_action_bar())

    def _make_action_bar(self) -> QWidget:
        bar = QWidget()
        bar.setStyleSheet("background: transparent;")
        row = QHBoxLayout(bar)
        row.setContentsMargins(SPACE_20, SPACE_MD, SPACE_20, SPACE_MD)
        row.addStretch()

        self._status_lbl = QLabel("")
        self._status_lbl.setStyleSheet(f"color:{_SUCCESS};font-weight:{FONT_WEIGHT_BOLD};font-size:{FONT_SIZE_LABEL}px;")
        self._status_lbl.setContentsMargins(0, 0, 0, 0)
        self._status_lbl.setVisible(False)
        row.addWidget(self._status_lbl)

        save_btn = QPushButton("Save")
        save_btn.setStyleSheet(_PRIMARY_BTN)
        save_btn.setFixedWidth(SIZE_BTN_W_100)
        save_btn.clicked.connect(self._save)
        row.addWidget(save_btn)
        return bar

    def _save(self) -> None:
        old_gender = db.get_bool("gender_inference_enabled", False)
        db.set_setting("face_recognition_enabled_global", "1" if self._face_global_toggle.isChecked() else "0")
        db.set_setting("gender_inference_enabled", "1" if self._gender_toggle.isChecked() else "0")
        db.set_setting("liveness_check_global", "1" if self._liveness_toggle.isChecked() else "0")
        if old_gender != self._gender_toggle.isChecked():
            with contextlib.suppress(Exception):
                from backend.models import model_loader

                model_loader.reload_face_model()
        if db.get_bool("ui_show_save_popups", False):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "Saved", "Detection settings saved.")
        else:
            self._flash_status("Saved")
            logger.info("Detection settings saved.")

    def _flash_status(self, text: str) -> None:
        self._status_lbl.setText(text)
        self._status_lbl.setVisible(True)
        eff = QGraphicsOpacityEffect(self._status_lbl)
        self._status_lbl.setGraphicsEffect(eff)
        anim = QPropertyAnimation(eff, b"opacity", self._status_lbl)
        anim.setDuration(1000)
        anim.setStartValue(1.0)
        anim.setEndValue(0.0)
        anim.finished.connect(
            lambda: (
                self._status_lbl.setText(""),
                self._status_lbl.setGraphicsEffect(None),
                self._status_lbl.setVisible(False),
            )
        )
        anim.start(QPropertyAnimation.DeletionPolicy.DeleteWhenStopped)

    def load(self) -> None:
        self._face_global_toggle.setChecked(db.get_bool("face_recognition_enabled_global", True))
        self._gender_toggle.setChecked(db.get_bool("gender_inference_enabled", False))
        self._liveness_toggle.setChecked(db.get_bool("liveness_check_global", False))
