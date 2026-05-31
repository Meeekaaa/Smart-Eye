from __future__ import annotations

from backend.pipeline import rule_engine


def test_identity_unknown_can_match_explicit_unknown_rule(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    rule_id = temp_db.add_rule("Unknown", "", "AND", "alarm", priority=10, camera_id=cam_id)
    temp_db.add_rule_condition(rule_id, "identity", "eq", "unknown")

    triggered = rule_engine.evaluate_rules({"detections": {"identity": "unknown"}, "object_bboxes": []}, camera_id=cam_id)

    assert [rule["name"] for rule in triggered] == ["Unknown"]


def test_and_rule_fails_closed_when_condition_is_unknown(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    rule_id = temp_db.add_rule("Known male", "", "AND", "alarm", priority=10, camera_id=cam_id)
    temp_db.add_rule_condition(rule_id, "identity", "eq", "Alice")
    temp_db.add_rule_condition(rule_id, "gender", "eq", "male")

    triggered = rule_engine.evaluate_rules({"detections": {"identity": "Alice"}, "object_bboxes": []}, camera_id=cam_id)

    assert triggered == []


def test_object_class_and_count_conditions(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    class_rule_id = temp_db.add_rule("Person class", "", "AND", "alarm", priority=10, camera_id=cam_id)
    temp_db.add_rule_condition(class_rule_id, "object", "eq", "person")
    count_rule_id = temp_db.add_rule("Object count", "", "AND", "alarm", priority=9, camera_id=cam_id)
    temp_db.add_rule_condition(count_rule_id, "objects", "gte", "2")

    state = {
        "detections": {},
        "object_bboxes": [{"class_name": "person"}, {"class_name": "forklift"}],
    }
    triggered = rule_engine.evaluate_rules(state, camera_id=cam_id)

    assert [rule["name"] for rule in triggered] == ["Person class", "Object count"]
