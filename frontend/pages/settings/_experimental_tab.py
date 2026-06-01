from __future__ import annotations

import logging

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
from utils import config as app_config
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

from ._constants import _PRIMARY_BTN, _make_sdiv, _srow

logger = logging.getLogger(__name__)


class ExperimentalTab(QWidget):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._inbox_toggle = None
        self._preload_toggles: dict[str, ToggleSwitch] = {}
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

        bl.addWidget(_make_sdiv("Inbox Capture"))

        self._inbox_toggle = ToggleSwitch()
        bl.addWidget(
            _srow(
                "Save unknown faces to Inbox",
                self._inbox_toggle,
                hint="save unlabeled faces for later review. Turn off to stop captures.",
            )
        )

        bl.addWidget(_make_sdiv("Page Preload"))
        for key, label in [
            ("dashboard", "Dashboard"),
            ("detectors", "Camera Manager"),
            ("rules", "Rules Manager"),
            ("analytics", "Analytics"),
            ("models", "Models / Plugins"),
            ("faces", "Face Manager"),
            ("logs", "Logs Viewer"),
            ("notifications", "Notifications"),
            ("settings", "Settings"),
        ]:
            sw = ToggleSwitch()
            self._preload_toggles[key] = sw
            bl.addWidget(
                _srow(
                    f"Preload {label}",
                    sw,
                    hint=f"Create the {label} page during startup instead of on first open.",
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
        db.set_setting("inbox_capture_enabled", 1 if self._inbox_toggle.isChecked() else 0)
        for key, sw in self._preload_toggles.items():
            db.set_setting(f"preload_{key}_page", 1 if sw.isChecked() else 0)
        app_config.invalidate_cache()
        if db.get_bool("ui_show_save_popups", False):
            from PySide6.QtWidgets import QMessageBox

            QMessageBox.information(self, "Saved", "Experimental settings saved.")
        else:
            self._flash_status("Saved")
            logger.info("Experimental settings saved.")

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
        self._inbox_toggle.setChecked(db.get_bool("inbox_capture_enabled", False))
        for key, sw in self._preload_toggles.items():
            sw.setChecked(db.get_setting(f"preload_{key}_page", "0") in ("1", 1, True, "true", "True"))
