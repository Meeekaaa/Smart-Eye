from __future__ import annotations

import json

from backend.database import migrations
from backend.analytics import stats_engine


def test_schema_migrations_and_defaults(temp_db):
    conn = temp_db.get_conn()
    assert conn.execute("PRAGMA user_version").fetchone()[0] == migrations.CURRENT_VERSION
    tables = {row[0] for row in conn.execute("SELECT name FROM sqlite_master WHERE type='table'")}
    assert {"cameras", "detection_logs", "app_settings", "rules"}.issubset(tables)

    defaults = temp_db.get_setting_defaults(["theme", "liveness_check_global", "logs_auto_refresh_enabled"])
    assert defaults["theme"]["value"] == "dark"
    assert defaults["liveness_check_global"]["value"] == "0"
    assert defaults["logs_auto_refresh_enabled"]["value"] == "0"
    assert "liveness_enabled" not in temp_db.get_setting_defaults()
    assert temp_db.get_bool("live_clip_enabled", False) is True
    assert temp_db.get_int("live_clip_seconds", 0) == 5
    assert temp_db.get_bool("playback_record_enabled", False) is True
    assert temp_db.get_bool("liveness_skip_presentation_for_stream_sources", False) is True
    assert temp_db.get_bool("runtime_metrics_enabled", False) is True


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


def test_liveness_failure_logs_are_blocked_and_legacy_rows_hidden(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    normal_id = temp_db.add_detection_log(
        cam_id,
        identity="Alice",
        detections={"identity": "Alice", "gender": "female"},
        rules_triggered=["Rule A"],
        alarm_level=1,
    )
    blocked_id = temp_db.add_detection_log(
        cam_id,
        identity="Alice",
        detections={"identity": "Alice", "liveness": 0.0, "spoof_type": "screen_presentation"},
        rules_triggered=["LivenessFailure"],
        alarm_level=0,
        snapshot_path="data/snapshots/liveness_fail_20260601_120000.jpg",
    )
    temp_db.get_conn().execute(
        """
        INSERT INTO detection_logs
            (timestamp, camera_id, identity, face_confidence, detections, gender_norm,
             rules_triggered, alarm_level, snapshot_path, reviewed, has_identity)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            "2026-06-01 12:00:00",
            cam_id,
            "Alice",
            0.9,
            json.dumps({"identity": "Alice", "liveness": 0.0, "spoof_type": "screen_presentation"}),
            "female",
            json.dumps(["LivenessFailure"]),
            0,
            "data/snapshots/liveness_fail_20260601_120000.jpg",
            0,
            1,
        ),
    )
    temp_db.get_conn().commit()

    assert normal_id is not None
    assert blocked_id is None
    assert temp_db.count_detection_logs() == 1
    assert [row["id"] for row in temp_db.get_detection_logs()] == [normal_id]
    assert temp_db.get_detection_stats()["total"] == 1
    assert temp_db.get_snapshot_logs() == []


def test_liveness_failure_evaluation_does_not_create_detection_log(temp_db):
    import numpy as np

    from backend.pipeline.liveness_manager import LivenessManager
    from utils import config

    temp_db.set_setting("liveness_mode", "active")
    temp_db.set_setting("liveness_challenge_seconds", "-1")
    temp_db.set_setting("liveness_allow_bbox_fallback", "0")
    config.invalidate_cache()

    manager = LivenessManager()
    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    result = manager.evaluate(
        999,
        frame,
        {"bbox": [10, 10, 40, 40], "identity": {"id": 1, "name": "Alice"}},
        frame_idx=1,
        objects=[],
    )

    assert result[:3] == (0.0, "landmarks_missing", False)
    assert temp_db.count_detection_logs() == 0


def test_liveness_presentation_block_can_be_skipped_for_stream_sources(temp_db):
    import numpy as np

    from backend.pipeline.detector_manager import _is_demo_stream_source
    from backend.pipeline.liveness_manager import LivenessManager
    from utils import config

    temp_db.set_setting("liveness_mode", "active")
    temp_db.set_setting("liveness_challenge_seconds", "-1")
    config.invalidate_cache()

    frame = np.zeros((80, 80, 3), dtype=np.uint8)
    face = {"bbox": [20, 20, 40, 40], "identity": {"id": 1, "name": "Alice"}}
    objects = [{"class_name": "screen", "bbox": [0, 0, 80, 80]}]

    assert _is_demo_stream_source("https://www.twitch.tv/example")
    assert _is_demo_stream_source("demo.mp4")
    assert not _is_demo_stream_source("0")

    blocked = LivenessManager().evaluate(100, frame, face, frame_idx=1, objects=objects)
    skipped = LivenessManager().evaluate(
        101,
        frame,
        face,
        frame_idx=1,
        objects=objects,
        block_presentation=False,
    )

    assert blocked[:3] == (0.0, "screen_presentation", False)
    assert skipped[1] != "screen_presentation"


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
    temp_db.add_detection_log(cam_id, identity="Eve", detections={}, rules_triggered=["Rule AB"], alarm_level=1)
    temp_db.add_detection_log(cam_id, identity="Bob", detections={}, rules_triggered=["Rule B"], alarm_level=1)

    summary = stats_engine.get_summary(camera_id=cam_id, rule_name="Rule A")

    assert summary["total_detections"] == 1
    assert summary["violations"] == 1


def test_analytics_filters_are_consistent_and_exclude_unknown_violators(temp_db):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    other_cam_id = temp_db.add_camera("Cam 2", "debug://cam/2")
    temp_db.seed_detection_logs(
        [
            {
                "timestamp": "2026-01-01 08:00:00",
                "camera_id": cam_id,
                "identity": "Alice",
                "detections": {"identity": "Alice", "gender": "male"},
                "rules_triggered": ["Rule A"],
                "alarm_level": 2,
            },
            {
                "timestamp": "2026-01-01 08:10:00",
                "camera_id": cam_id,
                "identity": "Unknown",
                "detections": {"identity": "Unknown", "gender": "male"},
                "rules_triggered": ["Rule A"],
                "alarm_level": 2,
            },
            {
                "timestamp": "2026-01-01 08:20:00",
                "camera_id": cam_id,
                "identity": "Dave",
                "detections": {"identity": "Dave", "gender": "male"},
                "rules_triggered": ["Rule A"],
                "alarm_level": 0,
            },
            {
                "timestamp": "2026-01-01 08:30:00",
                "camera_id": cam_id,
                "identity": "Carol",
                "detections": {"identity": "Carol", "gender": "female"},
                "rules_triggered": ["Rule A"],
                "alarm_level": 2,
            },
            {
                "timestamp": "2026-01-01 08:40:00",
                "camera_id": other_cam_id,
                "identity": "Eve",
                "detections": {"identity": "Eve", "gender": "male"},
                "rules_triggered": ["Rule AB"],
                "alarm_level": 2,
            },
        ],
        ignore_size_limit=True,
    )

    summary = stats_engine.get_summary(rule_name="Rule A", min_alarm_level=2, gender="male")
    activity = stats_engine.get_camera_activity_data(rule_name="Rule A", min_alarm_level=2, gender="male")
    top = stats_engine.get_person_violations(rule_name="Rule A", min_alarm_level=2, gender="male")
    trend = stats_engine.get_compliance_trend(rule_name="Rule A", min_alarm_level=2, gender="male")

    assert summary["total_detections"] == 3
    assert summary["violations"] == 2
    assert summary["compliant"] == 1
    assert activity == [{"camera_id": cam_id, "camera_name": "Cam 1", "count": 2}]
    assert top == [{"identity": "Alice", "gender": "male", "count": 1}]
    assert trend == [{"date": "2026-01-01", "total": 3, "compliant": 1, "rate": 33.3}]


def test_report_export_summary_honors_rule_filter(monkeypatch, tmp_path):
    from backend.analytics import report_generator

    captured = {}
    captured_heatmap = {}

    def fake_get_summary(*args, **kwargs):
        captured.update(kwargs)
        return {
            "total_detections": 1,
            "violations": 1,
            "compliant": 0,
            "compliance_rate": 0,
        }

    monkeypatch.setattr(report_generator.stats_engine, "is_dummy_analytics_enabled", lambda: False)
    monkeypatch.setattr(report_generator.stats_engine, "get_summary", fake_get_summary)
    monkeypatch.setattr(report_generator.stats_engine, "get_compliance_trend", lambda **kwargs: [])
    monkeypatch.setattr(report_generator.stats_engine, "get_hourly_violation_chart", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_generator.stats_engine, "get_camera_activity_data", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_generator.stats_engine, "get_person_violations", lambda *args, **kwargs: [])
    monkeypatch.setattr(report_generator.stats_engine, "get_gender_violations", lambda **kwargs: [])
    def fake_build_heatmap_image(**kwargs):
        captured_heatmap.update(kwargs)
        return None

    monkeypatch.setattr(report_generator, "_build_heatmap_image", fake_build_heatmap_image)

    report_generator.generate_report(str(tmp_path / "report.pdf"), rule_name="Rule A", min_alarm_level=2, gender="male")

    assert captured["rule_name"] == "Rule A"
    assert captured_heatmap["rule_name"] == "Rule A"
    assert captured_heatmap["min_alarm_level"] == 2
    assert captured_heatmap["gender"] == "male"


def test_snapshot_delete_clears_detection_log_link(temp_db, tmp_path):
    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    snap = tmp_path / "snap.jpg"
    snap.write_bytes(b"img")
    log_id = temp_db.add_detection_log(cam_id, detections={}, rules_triggered=["Rule A"], alarm_level=1, snapshot_path=str(snap))

    cleared = temp_db.clear_snapshot_path(str(snap))

    row = temp_db.get_conn().execute("SELECT snapshot_path FROM detection_logs WHERE id=?", (log_id,)).fetchone()
    assert cleared == 1
    assert row["snapshot_path"] == ""


def test_detection_log_filters_count_and_reviewed(temp_db):
    cam_id = temp_db.add_camera("Lobby", "debug://cam/1")
    temp_db.seed_detection_logs(
        [
            {
                "timestamp": "2026-01-01 00:00:00",
                "camera_id": cam_id,
                "identity": "Alice",
                "detections": {"identity": "Alice", "gender": "female", "all_faces": [{"name": "Alice"}]},
                "rules_triggered": ["Rule A"],
                "alarm_level": 2,
                "reviewed": 0,
            },
            {
                "timestamp": "2026-01-01 00:00:01",
                "camera_id": cam_id,
                "identity": "",
                "detections": {"gender": "unknown", "object_bboxes": [{"class_name": "forklift"}]},
                "rules_triggered": ["Rule B"],
                "alarm_level": 0,
                "reviewed": 1,
            },
        ],
        ignore_size_limit=True,
    )

    assert temp_db.count_detection_logs(search="Lobby") == 2
    assert temp_db.count_detection_logs(search="forklift") == 1
    assert temp_db.count_detection_logs(log_type="face") == 1
    assert temp_db.count_detection_logs(log_type="object") == 1
    assert temp_db.count_detection_logs(log_type="violation") == 1
    assert temp_db.count_detection_logs(reviewed=1) == 1

    rows = temp_db.get_detection_logs(search="female", log_type="face")
    assert len(rows) == 1
    assert rows[0]["identity"] == "Alice"


def test_detection_log_batch_review_delete_and_cleanup_evidence(temp_db, tmp_path):
    from frontend.services.log_service import LogService

    cam_id = temp_db.add_camera("Cam 1", "debug://cam/1")
    old_snap = tmp_path / "old.jpg"
    new_snap = tmp_path / "new.jpg"
    old_snap.write_bytes(b"old")
    new_snap.write_bytes(b"new")
    temp_db.seed_detection_logs(
        [
            {
                "timestamp": "2000-01-01 00:00:00",
                "camera_id": cam_id,
                "identity": "Alice",
                "snapshot_path": str(old_snap),
            },
            {
                "timestamp": "2000-01-02 00:00:00",
                "camera_id": cam_id,
                "identity": "Bob",
                "snapshot_path": str(new_snap),
            },
        ],
        ignore_size_limit=True,
    )
    rows = temp_db.get_detection_logs(limit=10)
    ids = [row["id"] for row in rows]

    assert temp_db.mark_detection_logs_reviewed(ids, reviewed=1) == 2
    assert temp_db.count_detection_logs(reviewed=1) == 2

    deleted = LogService().cleanup_older_than_days(1, delete_evidence=True)

    assert deleted["logs"] == 2
    assert deleted["evidence"] == 2
    assert not old_snap.exists()
    assert not new_snap.exists()


def test_log_service_exports_filtered_csv(temp_db, tmp_path):
    from frontend.services.log_service import LogService

    cam_id = temp_db.add_camera("Lobby", "debug://cam/1")
    temp_db.add_detection_log(
        cam_id,
        identity="Alice",
        detections={"gender": "female", "object_bboxes": [{"class_name": "person"}]},
        rules_triggered=["Rule A"],
        alarm_level=1,
    )
    path = tmp_path / "logs.csv"

    exported = LogService().export_logs_csv(str(path), search="Alice", log_type="violation")

    text = path.read_text(encoding="utf-8")
    assert exported == 1
    assert "camera_name" in text
    assert "Lobby" in text
    assert "Alice" in text


def test_clip_filters_match_json_array_values_exactly(temp_db, tmp_path):
    clip_a = tmp_path / "a.mp4"
    clip_b = tmp_path / "b.mp4"
    clip_a.write_bytes(b"a")
    clip_b.write_bytes(b"b")
    temp_db.add_clip(str(clip_a), "playback", None, 10, None, ["Rule A"], ["person"])
    temp_db.add_clip(str(clip_b), "playback", None, 20, None, ["Rule AB"], ["person-extra"])

    assert [row["path"] for row in temp_db.get_clips(rule_triggered="Rule A")] == [str(clip_a)]
    assert [row["path"] for row in temp_db.get_clips(object_type="person")] == [str(clip_a)]


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
