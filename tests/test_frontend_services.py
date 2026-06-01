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


def test_rule_validation_rejects_empty_condition_list():
    service = RulesService()

    try:
        service.validate_conditions([])
    except ValueError as exc:
        assert "at least one condition" in str(exc)
    else:
        raise AssertionError("Expected condition-less rules to be rejected")


def test_rule_validation_accepts_popup_alarm_action():
    RulesService().validate_alarms(
        [{"action_type": "popup", "escalation_level": 1, "trigger_after_sec": 0, "cooldown_sec": 10}]
    )


def test_log_only_rule_does_not_persist_alarm_actions(temp_db):
    service = RulesService()
    rule_id = service.save_rule(
        None,
        data={"name": "Log known person", "logic": "AND", "action": "log_only", "enabled": True},
        conditions=[{"attribute": "identity", "operator": "eq", "value": "Alice"}],
        alarms=[
            {
                "action_type": "sound",
                "action_value": "frontend/assets/sounds/alarm_level_1.wav|0.80",
                "escalation_level": 1,
                "trigger_after_sec": 0,
                "cooldown_sec": 10,
            }
        ],
    )

    assert temp_db.get_rule(rule_id)["action"] == "log_only"
    assert temp_db.get_alarm_actions(rule_id) == []


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


def test_log_service_filters_type_before_pagination(monkeypatch):
    calls = []

    def fake_get_detection_logs(**kwargs):
        calls.append(kwargs)
        offset = kwargs.get("offset", 0)
        if offset == 0:
            return [{"id": idx, "identity": "", "detections": "{}"} for idx in range(1, 251)]
        if offset == 250:
            return [
                {"id": 3, "identity": "Alice", "detections": "{}"},
                {"id": 4, "identity": "", "detections": '{"object_bboxes":[{"class_name":"person"}]}'},
            ]
        return []

    monkeypatch.setattr("frontend.services.log_service.db.get_detection_logs", fake_get_detection_logs)

    rows = LogService().get_logs(log_type="face", limit=1, page=1)

    assert [row["id"] for row in rows] == [3]
    assert [call["offset"] for call in calls[:2]] == [0, 250]
