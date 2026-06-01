from __future__ import annotations

from PySide6.QtCore import QEvent, QObject, QTimer
from PySide6.QtWidgets import QApplication, QPushButton
from shiboken6 import isValid as _qt_object_is_valid

from frontend.ui_tokens import SIZE_BTN_W_80, SPACE_20, SPACE_MD

_QWIDGETSIZE_MAX = 16777215
_filter_instance = None


def _button_is_alive(button: QPushButton | None) -> bool:
    try:
        return bool(button is not None and _qt_object_is_valid(button))
    except RuntimeError:
        return False


def _visible_button_text(button: QPushButton) -> str:
    # Strip Qt mnemonic markers so width checks match what the user sees.
    if not _button_is_alive(button):
        return ""
    try:
        return str(button.text() or "").replace("&&", "&").replace("&", "").strip()
    except RuntimeError:
        return ""


def required_button_width(button: QPushButton) -> int:
    text = _visible_button_text(button)
    if not text:
        return 0

    try:
        line_width = max(button.fontMetrics().horizontalAdvance(line) for line in text.splitlines() or [text])
        icon_extra = 0
        if not button.icon().isNull():
            icon_extra = button.iconSize().width() + SPACE_MD
        return max(SIZE_BTN_W_80, line_width + icon_extra + (SPACE_20 * 2))
    except RuntimeError:
        return 0


def fit_button_to_text(button: QPushButton) -> None:
    try:
        if not _button_is_alive(button) or button.property("skip_auto_fit"):
            return
        text = _visible_button_text(button)
        if not text:
            return

        # Keep square close/icon buttons square even if they use a one-character fallback.
        if len(text) <= 2 and button.maximumWidth() <= max(48, button.maximumHeight() + 8):
            return

        required = required_button_width(button)
        if required <= 0:
            return

        if button.minimumWidth() < required:
            button.setMinimumWidth(required)
        if button.maximumWidth() != _QWIDGETSIZE_MAX and button.maximumWidth() < required:
            button.setMaximumWidth(required)
    except RuntimeError:
        return


class _ButtonAutoFitFilter(QObject):
    def eventFilter(self, obj, event):
        if isinstance(obj, QPushButton) and event.type() in {
            QEvent.Type.Polish,
            QEvent.Type.Show,
            QEvent.Type.Resize,
            QEvent.Type.FontChange,
        }:
            QTimer.singleShot(0, lambda button=obj: fit_button_to_text(button))
        return super().eventFilter(obj, event)


def install_button_auto_fit(app: QApplication) -> None:
    global _filter_instance
    if _filter_instance is not None:
        return
    _filter_instance = _ButtonAutoFitFilter(app)
    app.installEventFilter(_filter_instance)
