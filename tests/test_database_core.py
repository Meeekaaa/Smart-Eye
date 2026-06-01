from __future__ import annotations

import json

from backend.database import migrations
from backend.analytics import stats_engine


def test_schema_migrations_and_defaults(temp_db):
    conn = temp_db.get_conn()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.CURRENT_VERSION
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cameras", "detection_logs", "app_settings", "rules"}.issubset(tables)

    defaults = temp_db.get_setting_defaults(["theme", "liveness_check_global"])
    assert defaults["theme"]["value"] == "dark"
    assert defaults["liveness_check_global"]["value"] == "0"
    assert "liveness_enabled" not in temp_db.get_setting_defaults()


def test_detection_log_normalizes_gender_and_identity(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    log_id = temp_db.add_detection_log(
        cam_id,
        identity={"name": "Alice"},
        face_confidence=0.87,
        detections={"gender": "female", "identity": "Alice"},
        rules_triggered=["Rule A"],
        alarm_level=2,
    )
    row = temp_db.get_conn().execute("SELECT * FROM detection_logs WHERE id=?", (log_id,)).fetchone()
    assert row["gender_norm"] == "female"
    assert row["has_identity"] == 1
    assert json.loads(row["detections"])["gender"] == "female"


def test_seed_detection_logs_preserves_derived_columns(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    inserted = temp_db.seed_detection_logs(
        [
            {
                "timestamp": "2026-01-01 00:00:00",
                "camera_id": cam_id,
                "identity": "Unknown",
                "detections": {"gender": "male", "identity": "Unknown"},
            },
            {
                "timestamp": "2026-01-01 00:00:01",
                "camera_id": cam_id,
                "identity": "Bob",
                "detections": {"gender": "male", "identity": "Bob"},
            },
        ],
        ignore_size_limit=True,
    )
    assert inserted == 2
    rows = temp_db.get_conn().execute("SELECT identity, gender_norm, has_identity FROM detection_logs ORDER BY timestamp").fetchall()
    assert [(row["identity"], row["gender_norm"], row["has_identity"]) for row in rows] == [
        ("Unknown", "male", 0),
        ("Bob", "male", 1),
    ]


def test_assign_camera_plugin_class_uses_writer_path(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    plugin_id = temp_db.add_plugin("Plugin 1", "object", "missing.onnx")
    class_id = temp_db.add_plugin_class(plugin_id, 0, "person", "Person")

    temp_db.assign_camera_plugin_class(cam_id, class_id, enabled=1, confidence=0.7)
    temp_db.assign_camera_plugin_class(cam_id, class_id, enabled=0, confidence=0.4)

    rows = temp_db.get_camera_plugin_classes(cam_id, plugin_id)
    assert len(rows) == 1
    assert rows[0]["enabled"] == 0
    assert rows[0]["confidence"] == 0.4


def test_debug_service_seed_support_uses_db_writer(temp_db):
    from frontend.services.debug_service import DebugService

    rows = DebugService().prepare_seed_support(camera_count=1, face_count=1)

    assert len(rows) == 1
    assert temp_db.get_rules(enabled_only=True, camera_id=rows[0]["id"])
    assert temp_db.get_known_faces()
    assert temp_db.get_notification_profiles(enabled_only=True)


def test_analytics_summary_honors_rule_filter(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    temp_db.add_detection_log(cam_id, identity="Alice", detections={}, rules_triggered=["Rule A"], alarm_level=1)
    temp_db.add_detection_log(cam_id, identity="Bob", detections={}, rules_triggered=["Rule B"], alarm_level=1)

    summary = stats_engine.get_summary(camera_id=cam_id, rule_name="Rule A")

    assert summary["total_detections"] == 1
    assert summary["violations"] == 1


def test_settings_import_rejects_unknown_keys(temp_db):
    try:
        temp_db.import_settings_json({"unknown_setting": {"value": "1", "type": "bool"}})
    except ValueError as exc:
        assert "Unknown setting key" in str(exc)
    else:
        raise AssertionError("Unknown settings import key should be rejected")


def test_database_preserves_at_least_one_admin(temp_db):
    conn = temp_db.get_conn()
    conn.execute("DELETE FROM accounts")
    conn.commit()
    questions = ["Question 1", "Question 2", "Question 3"]
    answers = ["Answer 1", "Answer 2", "Answer 3"]
    admin_id = temp_db.create_account(
        "admin@gmail.com",
        "password",
        [],
        is_admin=True,
        security=(questions, answers),
    )

    for operation in (
        lambda: temp_db.update_account(admin_id, is_admin=False, allowed_tabs=["dashboard"]),
        lambda: temp_db.delete_account(admin_id),
    ):
        try:
            operation()
        except ValueError as exc:
            assert "administrator" in str(exc).lower()
        else:
            raise AssertionError("Last administrator operation should be blocked")
