from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication, QPushButton
from shiboken6 import delete as delete_qt_object

from frontend.styles._btn_styles import _SECONDARY_BTN
from frontend.widgets.button_auto_fit import fit_button_to_text, required_button_width


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_button_auto_fit_expands_fixed_width_button():
    _app()
    button = QPushButton("Purge Operational Data")
    button.setFixedWidth(80)

    fit_button_to_text(button)

    required = required_button_width(button)
    assert button.minimumWidth() >= required
    assert button.maximumWidth() >= required


def test_secondary_button_has_filled_surface():
    assert "background-color: transparent" not in _SECONDARY_BTN


def test_button_auto_fit_ignores_deleted_button():
    _app()
    button = QPushButton("Delete Operational Data")
    delete_qt_object(button)

    fit_button_to_text(button)

    assert required_button_width(button) == 0
