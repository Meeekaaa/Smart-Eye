from frontend.services.camera_service import CameraService
from frontend.services.log_service import LogService
from frontend.services.notification_validation import validate_notification_target
from frontend.services.rules_service import RulesService


def test_camera_source_validation_accepts_webcam_index_and_rejects_missing_host():
    assert CameraService.validate_source("0") == (True, "")

    ok, message = CameraService.validate_source("rtsp://")
    assert not ok
    assert "host" in message.lower()


def test_rule_validation_rejects_empty_condition_value():
    service = RulesService()

    try:
        service.validate_conditions([{"attribute": "identity", "operator": "eq", "value": ""}])
    except ValueError as exc:
        assert "needs a value" in str(exc)
    else:
        raise AssertionError("Expected empty rule condition value to be rejected")


def test_notification_target_validation():
    assert validate_notification_target("email", "operator@gmail.com") == ""
    assert "valid HTTP" in validate_notification_target("webhook", "ftp://example.com/hook")


def test_log_service_uses_page_offset(monkeypatch):
    captured = {}

    def fake_get_detection_logs(**kwargs):
        captured.update(kwargs)
        return []

    monkeypatch.setattr("frontend.services.log_service.db.get_detection_logs", fake_get_detection_logs)

    LogService().get_logs(limit=25, page=3)

    assert captured["limit"] == 25
    assert captured["offset"] == 50
