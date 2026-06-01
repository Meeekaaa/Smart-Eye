from __future__ import annotations

import os

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

from PySide6.QtWidgets import QApplication

from backend.pipeline.alarm_handler import _parse_sound_action_value
from frontend.pages.rules_manager._widgets import ConditionRow, _IdentityPicker


def _app() -> QApplication:
    return QApplication.instance() or QApplication([])


def test_identity_placeholder_returns_empty_value():
    _app()
    picker = _IdentityPicker("")

    assert picker.get_value() == ""


def test_object_count_condition_uses_numeric_control():
    _app()
    row = ConditionRow("objects", "gte", "2")

    data = row.get_data()

    assert data["attribute"] == "objects"
    assert data["operator"] == "gte"
    assert data["value"] == "2"


def test_sound_action_value_parses_volume_and_path():
    path, volume = _parse_sound_action_value("frontend/assets/sounds/alarm_level_4.wav|0.25")

    assert path == "frontend/assets/sounds/alarm_level_4.wav"
    assert volume == 0.25
