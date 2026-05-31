import hashlib
import logging
import json
import secrets
import uuid


CURRENT_VERSION = 43


def apply(conn):
    row = conn.execute("PRAGMA user_version").fetchone()
    version = row[0] if row else 0
    if version < 1:
        _migrate_v1(conn)
    if version < 2:
        _migrate_v2(conn)
    if version < 3:
        _migrate_v3(conn)
    if version < 4:
        _migrate_v4(conn)
    if version < 5:
        _migrate_v5(conn)
    if version < 6:
        _migrate_v6(conn)
    if version < 7:
        _migrate_v7(conn)
    if version < 8:
        _migrate_v8(conn)
    if version < 9:
        _migrate_v9(conn)
    if version < 10:
        _migrate_v10(conn)
    if version < 11:
        _migrate_v11(conn)
    if version < 12:
        _migrate_v12(conn)
    if version < 13:
        _migrate_v13(conn)
    if version < 14:
        _migrate_v14(conn)
    if version < 15:
        _migrate_v15(conn)
    if version < 16:
        _migrate_v16(conn)
    if version < 17:
        _migrate_v17(conn)
    if version < 18:
        _migrate_v18(conn)
    if version < 19:
        _migrate_v19(conn)
    if version < 20:
        _migrate_v20(conn)
    if version < 21:
        _migrate_v21(conn)
    if version < 22:
        _migrate_v22(conn)
    if version < 23:
        _migrate_v23(conn)
    if version < 24:
        _migrate_v24(conn)
    if version < 25:
        _migrate_v25(conn)
    if version < 26:
        _migrate_v26(conn)
    if version < 27:
        _migrate_v27(conn)
    if version < 28:
        _migrate_v28(conn)
    if version < 29:
        _migrate_v29(conn)
    if version < 30:
        _migrate_v30(conn)
    if version < 31:
        _migrate_v31(conn)
    if version < 32:
        _migrate_v32(conn)
    if version < 33:
        _migrate_v33(conn)
    if version < 34:
        _migrate_v34(conn)
    if version < 35:
        _migrate_v35(conn)
    if version < 36:
        _migrate_v36(conn)
    if version < 37:
        _migrate_v37(conn)
    if version < 38:
        _migrate_v38(conn)
    if version < 39:
        _migrate_v39(conn)
    if version < 40:
        _migrate_v40(conn)
    if version < 41:
        _migrate_v41(conn)
    if version < 42:
        _migrate_v42(conn)
    if version < 43:
        _migrate_v43(conn)
    conn.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
    conn.commit()


def _migrate_v43(conn):
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("display_bbox_hold_sec", "0.45", "float", "Display BBox Hold", "performance"),
    )
    conn.execute(
        "UPDATE app_settings SET value='0.45', type='float', label='Display BBox Hold', section='performance' "
        "WHERE key='display_bbox_hold_sec'"
    )
    conn.commit()


def _migrate_v42(conn):
    settings = [
        ("bbox_hold_max_frames", "6", "int", "BBox Hold Frames", "performance"),
        ("bbox_hold_max_stale_sec", "0.75", "float", "BBox Hold Staleness", "performance"),
        ("display_bbox_hold_sec", "0.45", "float", "Display BBox Hold", "performance"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute("UPDATE app_settings SET value='6' WHERE key='bbox_hold_max_frames' AND CAST(value AS INTEGER) < 6")
    conn.execute("UPDATE app_settings SET value='0.75' WHERE key='bbox_hold_max_stale_sec' AND CAST(value AS REAL) < 0.75")
    conn.commit()


def _migrate_v41(conn):
    settings = [
        ("detection_interval", "1", "int", "Detection Interval", "performance"),
        ("insightface_det_size", "640", "int", "InsightFace Detector Size", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute("UPDATE app_settings SET value='640' WHERE key='insightface_det_size' AND CAST(value AS INTEGER) < 320")
    conn.commit()


def _migrate_v40(conn):
    settings = [
        ("live_infer_dim", "640", "int", "Live Inference Size", "performance"),
        ("live_infer_dim_min", "384", "int", "Live Inference Size Min", "performance"),
        ("live_infer_dim_max", "768", "int", "Live Inference Size Max", "performance"),
        ("adaptive_live_infer_dim", "1", "bool", "Adaptive Live Inference Size", "performance"),
        ("detector_max_infer_dim", "768", "int", "Detector Max Inference Size", "performance"),
        ("bbox_hold_max_frames", "6", "int", "BBox Hold Frames", "performance"),
        ("bbox_hold_max_stale_sec", "0.75", "float", "BBox Hold Staleness", "performance"),
        ("min_face_size", "24", "int", "Minimum Face Size", "detection"),
        ("object_min_area_ratio", "0.00025", "float", "Object Minimum Area Ratio", "detection"),
        ("person_weak_detection_confidence", "0.55", "float", "Weak Person Confidence", "detection"),
        ("person_tiny_area_ratio", "0.006", "float", "Tiny Person Area Ratio", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute("UPDATE app_settings SET value='640' WHERE key='live_infer_dim' AND CAST(value AS INTEGER) < 640")
    conn.execute("UPDATE app_settings SET value='384' WHERE key='live_infer_dim_min' AND CAST(value AS INTEGER) < 384")
    conn.execute("UPDATE app_settings SET value='768' WHERE key='live_infer_dim_max' AND CAST(value AS INTEGER) < 768")
    conn.execute("UPDATE app_settings SET value='24' WHERE key='min_face_size' AND CAST(value AS INTEGER) >= 40")
    conn.execute("UPDATE app_settings SET value='24' WHERE key LIKE 'camera_%_min_face_size' AND CAST(value AS INTEGER) >= 40")
    conn.commit()


def _migrate_v39(conn):
    row = conn.execute("SELECT value FROM app_settings WHERE key='insightface_allowed_modules'").fetchone()
    gender_row = conn.execute("SELECT value FROM app_settings WHERE key='gender_inference_enabled'").fetchone()
    gender_enabled = str(gender_row[0]).strip().lower() in ("1", "true", "yes", "on") if gender_row else False
    existing = []
    if row and row[0]:
        try:
            parsed = json.loads(row[0])
            if isinstance(parsed, list):
                existing = [str(v) for v in parsed]
        except Exception:
            existing = []
    modules = ["detection", "recognition"]
    if gender_enabled and ("genderage" in existing or not row):
        modules.append("genderage")
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("insightface_allowed_modules", json.dumps(modules), "json", "Allowed InsightFace Modules", "detection"),
    )
    conn.commit()


def _migrate_v38(conn):
    for key in ("bbox_predict_max_frames", "bbox_predict_max_stale_sec"):
        conn.execute("DELETE FROM app_settings WHERE key=?", (key,))
    conn.commit()


def _migrate_v37(conn):
    settings = [
        ("live_infer_interval_max", "2", "int", "Live Inference Interval Max", "performance"),
        ("bbox_predict_max_frames", "2", "int", "BBox Prediction Max Frames", "performance"),
        ("bbox_predict_max_stale_sec", "0.20", "float", "BBox Prediction Max Staleness", "performance"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute("UPDATE app_settings SET value='2' WHERE key='live_infer_interval_max' AND value='3'")
    conn.commit()


def _migrate_v36(conn):
    settings = [
        ("adaptive_live_infer_interval", "1", "bool", "Adaptive Live Inference Interval", "performance"),
        ("live_infer_interval_min", "1", "int", "Live Inference Interval Min", "performance"),
        ("live_infer_interval_max", "2", "int", "Live Inference Interval Max", "performance"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.commit()


def _migrate_v35(conn):
    settings = [
        ("liveness_pass_recheck_every_n_frames", "1", "int", "Liveness Pass Recheck Stride", "detection"),
        ("liveness_pass_revoke_threshold", "0.20", "float", "Liveness Pass Revoke Threshold", "detection"),
        ("liveness_identity_track_min_iou", "0.20", "float", "Liveness Identity Track Minimum IOU", "detection"),
        ("liveness_failure_log_cooldown_sec", "20.0", "float", "Liveness Failure Log Cooldown", "detection"),
        ("liveness_block_screen_presentations", "1", "bool", "Block Screen Presentations", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.commit()


def _migrate_v34(conn):
    settings = [
        ("liveness_passive_real_class_index", "1", "int", "Passive Liveness Real Class Index", "detection"),
        ("liveness_passive_normalization", "raw", "string", "Passive Liveness Normalization", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute(
        "UPDATE app_settings SET value=? WHERE key=? AND value=?",
        ("1", "liveness_passive_real_class_index", "0"),
    )
    conn.execute(
        "UPDATE app_settings SET value=? WHERE key=? AND value=?",
        ("raw", "liveness_passive_normalization", "zero_one"),
    )
    conn.commit()


def _migrate_v33(conn):
    settings = [
        ("liveness_passive_real_class_index", "1", "int", "Passive Liveness Real Class Index", "detection"),
        ("liveness_passive_color_order", "bgr", "string", "Passive Liveness Color Order", "detection"),
        ("liveness_passive_crop_scale", "2.7", "float", "Passive Liveness Crop Scale", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute(
        "UPDATE app_settings SET value=? WHERE key=? AND value=?",
        ("1", "liveness_passive_real_class_index", "0"),
    )
    conn.commit()


def _migrate_v32(conn):
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("liveness_passive_temporal_fallback", "0", "bool", "Passive Temporal Fallback", "detection"),
    )
    conn.execute(
        "UPDATE app_settings SET value=?, type=?, label=?, section=? WHERE key=?",
        ("0", "bool", "Passive Temporal Fallback", "detection", "liveness_passive_temporal_fallback"),
    )
    conn.commit()


def _migrate_v31(conn):
    settings = [
        ("liveness_mode", "passive", "string", "Liveness Mode", "detection"),
        ("liveness_passive_model_path", "data/models/liveness.onnx", "string", "Passive Liveness Model Path", "detection"),
        ("liveness_passive_threshold", "0.70", "float", "Passive Liveness Threshold", "detection"),
        ("liveness_passive_min_frames", "3", "int", "Passive Liveness Minimum Frames", "detection"),
        ("liveness_passive_window_sec", "1.2", "float", "Passive Liveness Window", "detection"),
        ("liveness_passive_every_n_frames", "3", "int", "Passive Liveness Inference Stride", "detection"),
        ("liveness_passive_real_class_index", "1", "int", "Passive Liveness Real Class Index", "detection"),
        ("liveness_passive_normalization", "raw", "string", "Passive Liveness Normalization", "detection"),
        ("liveness_passive_color_order", "bgr", "string", "Passive Liveness Color Order", "detection"),
        ("liveness_passive_crop_scale", "2.7", "float", "Passive Liveness Crop Scale", "detection"),
        ("liveness_passive_temporal_fallback", "0", "bool", "Passive Temporal Fallback", "detection"),
        ("liveness_onnx_provider_preference", "auto", "string", "Liveness ONNX Provider", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.commit()


def _migrate_v30(conn):
    settings = [
        ("liveness_challenge_seconds", "8.0", "float", "Liveness Challenge Seconds", "detection"),
        ("liveness_yaw_threshold", "0.16", "float", "Liveness Head Turn Threshold", "detection"),
        ("liveness_pose_frames", "2", "int", "Liveness Consecutive Pose Frames", "detection"),
        ("liveness_pass_ttl_sec", "30.0", "float", "Liveness Pass Time-To-Live", "detection"),
        ("liveness_failure_hold_sec", "2.0", "float", "Liveness Failure Hold", "detection"),
        ("liveness_allow_bbox_fallback", "0", "bool", "Allow BBox Liveness Fallback", "detection"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.commit()


def _migrate_v29(conn):
    settings = [
        ("remember_login", "0", "bool", "Remember Email", "security"),
        ("remember_email", "", "string", "Remembered Email", "security"),
        ("live_clip_enabled", "0", "bool", "Save Live Alarm Clips", "performance"),
        ("live_clip_seconds", "5", "int", "Live Clip Seconds", "performance"),
        ("live_clip_max_buffer_mb", "128", "int", "Live Clip Buffer Limit (MB)", "performance"),
        ("live_clip_buffer_max_dim", "640", "int", "Live Clip Buffer Max Dimension", "performance"),
        ("ui_live_render_fps", "15", "float", "Live View Render FPS", "performance"),
        ("inference_future_timeout_sec", "2.0", "float", "Inference Timeout (seconds)", "performance"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute("DELETE FROM app_settings WHERE key='remember_account_id'")
    conn.commit()


def _migrate_v28(conn):
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("ui_tab_transitions_enabled", "1", "bool", "Tab transition animations", "performance"),
    )
    conn.execute(
        "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
        ("bool", "Tab transition animations", "performance", "ui_tab_transitions_enabled"),
    )
    conn.commit()


def _migrate_v27(conn):
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("face_recognition_enabled_global", "1", "bool", "Enable Face Recognition", "detection"),
    )
    conn.execute(
        "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
        ("bool", "Enable Face Recognition", "detection", "face_recognition_enabled_global"),
    )
    conn.commit()


def _migrate_v26(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "known_faces" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(known_faces)").fetchall()]
        if "national_id" not in cols:
            conn.execute("ALTER TABLE known_faces ADD COLUMN national_id TEXT")
    conn.commit()


def _migrate_v25(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "accounts" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
        if "username" not in cols:
            conn.execute("ALTER TABLE accounts ADD COLUMN username TEXT")
    settings = [
        ("max_cpu_cores", "2", "int", "Max CPU Cores", "performance"),
        ("max_ram_mb", "4096", "int", "Max RAM (MB)", "performance"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.commit()


def _migrate_v24(conn):
    row = conn.execute("SELECT value FROM app_settings WHERE key='bootstrap_password_active'").fetchone()
    active = bool(row and str(row[0]).strip().lower() in ("1", "true", "yes", "on"))
    if not active:
        conn.commit()
        return
    bootstrap_admin = conn.execute(
        "SELECT id FROM accounts WHERE LOWER(TRIM(email))='admin@smarteye.local' LIMIT 1"
    ).fetchone()
    if bootstrap_admin:
        conn.commit()
        return
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("bootstrap_password_active", "0", "bool", "Bootstrap Password Active", "security"),
    )
    conn.execute(
        "INSERT OR REPLACE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("bootstrap_token", "", "string", "Bootstrap Token", "security"),
    )
    conn.commit()


def _migrate_v23(conn):
    settings = [
        ("remember_login", "0", "bool", "Remember Email", "security"),
        ("remember_email", "", "string", "Remembered Email", "security"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
    conn.execute(
        "UPDATE app_settings SET value = CASE "
        "WHEN LOWER(TRIM(COALESCE(value, ''))) IN ('1', 'true', 'yes', 'on') THEN '1' "
        "ELSE '0' END "
        "WHERE key='remember_login'"
    )
    conn.commit()


def _migrate_v22(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "known_faces" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(known_faces)").fetchall()]
        if "gender_norm" not in cols:
            conn.execute("ALTER TABLE known_faces ADD COLUMN gender_norm TEXT DEFAULT 'unknown'")
            conn.execute("CREATE INDEX IF NOT EXISTS idx_known_faces_gender_norm ON known_faces (gender_norm)")
    conn.commit()


def _migrate_v8(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "known_faces" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(known_faces)").fetchall()]
        if "embedding_model" not in cols:
            conn.execute("ALTER TABLE known_faces ADD COLUMN embedding_model TEXT DEFAULT ''")
    conn.commit()


def _migrate_v9(conn):
    missing_settings = [
        ("smtp_tls", "1", "bool", "Use TLS", "notifications"),
        ("auto_start_cameras", "0", "bool", "Auto-start cameras on launch", "general"),
        ("insightface_model_name", "buffalo_l", "string", "Face Model", "detection"),
        ("insightface_model_dir", "", "string", "Face Model Directory", "detection"),
        ("insightface_root_cache", "", "string", "InsightFace Root Cache", "detection"),
        ("limit_resources", "0", "bool", "Limit Resource Usage", "performance"),
    ]
    for key, value, vtype, label, section in missing_settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_detection_logs_timestamp ON detection_logs (timestamp)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_detection_logs_camera_id ON detection_logs (camera_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_known_faces_name ON known_faces (name)")
    conn.commit()


def _migrate_v11(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "plugin_classes" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(plugin_classes)").fetchall()]
        if "color" not in cols:
            conn.execute("ALTER TABLE plugin_classes ADD COLUMN color TEXT DEFAULT ''")
    conn.commit()


def _migrate_v10(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "cameras" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cameras)").fetchall()]
        if "face_similarity_threshold" not in cols:
            conn.execute("ALTER TABLE cameras ADD COLUMN face_similarity_threshold REAL")
    conn.commit()


def _migrate_v1(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "detection_logs" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(detection_logs)").fetchall()]
        if "reviewed" not in cols:
            conn.execute("ALTER TABLE detection_logs ADD COLUMN reviewed INTEGER DEFAULT 0")
    conn.commit()


def _migrate_v2(conn):

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "cameras" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cameras)").fetchall()]
        if "face_recognition" not in cols:
            conn.execute("ALTER TABLE cameras ADD COLUMN face_recognition INTEGER DEFAULT 1")
    conn.commit()


def _migrate_v3(conn):

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "plugin_classes" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(plugin_classes)").fetchall()]
        if "confidence" not in cols:
            conn.execute("ALTER TABLE plugin_classes ADD COLUMN confidence REAL DEFAULT 0.5")
    conn.commit()


def _migrate_v4(conn):

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "camera_plugin_classes" not in tables:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS camera_plugin_classes (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                camera_id INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
                plugin_class_id INTEGER NOT NULL REFERENCES plugin_classes(id) ON DELETE CASCADE,
                enabled INTEGER DEFAULT 1,
                confidence REAL,
                UNIQUE(camera_id, plugin_class_id)
            )
        """)
    conn.commit()


def _migrate_v5(conn):

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "cameras" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(cameras)").fetchall()]
        if "face_similarity_threshold" not in cols:
            conn.execute("ALTER TABLE cameras ADD COLUMN face_similarity_threshold REAL")
    conn.commit()


def _migrate_v6(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "model_plugins" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(model_plugins)").fetchall()]
        if "preferred_provider" not in cols:
            conn.execute("ALTER TABLE model_plugins ADD COLUMN preferred_provider TEXT DEFAULT 'auto'")
        if "last_error" not in cols:
            conn.execute("ALTER TABLE model_plugins ADD COLUMN last_error TEXT")
        if "last_error_at" not in cols:
            conn.execute("ALTER TABLE model_plugins ADD COLUMN last_error_at DATETIME")
        if "last_provider" not in cols:
            conn.execute("ALTER TABLE model_plugins ADD COLUMN last_provider TEXT")
    conn.commit()


def _migrate_v7(conn):

    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "known_faces" not in tables:
        conn.commit()
        return

    cols = [r[1] for r in conn.execute("PRAGMA table_info(known_faces)").fetchall()]
    if "uuid" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN uuid TEXT")
    if "address" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN address TEXT")
    if "country" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN country TEXT")
    if "birth_date" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN birth_date TEXT")
    if "phone" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN phone TEXT")
    if "email" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN email TEXT")
    conn.commit()

    rows = conn.execute("SELECT id, uuid FROM known_faces").fetchall()
    for row in rows:
        existing = row[1]
        if existing:
            continue
        conn.execute("UPDATE known_faces SET uuid=? WHERE id=?", (str(uuid.uuid4()), row[0]))

    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_known_faces_uuid ON known_faces(uuid)")
    conn.commit()


def _migrate_v12(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(known_faces)").fetchall()]
    if "enabled" not in cols:
        conn.execute("ALTER TABLE known_faces ADD COLUMN enabled INTEGER DEFAULT 1")
    conn.commit()


def _migrate_v13(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "accounts" not in tables:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS accounts (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                email TEXT NOT NULL UNIQUE,
                password_hash TEXT NOT NULL,
                salt TEXT NOT NULL,
                allowed_tabs TEXT NOT NULL DEFAULT '[]',
                is_admin INTEGER DEFAULT 0,
                created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
                last_login DATETIME
            )
            """
        )
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
    if "allowed_tabs" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN allowed_tabs TEXT NOT NULL DEFAULT '[]'")
    if "is_admin" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN is_admin INTEGER DEFAULT 0")
    if "created_at" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN created_at DATETIME DEFAULT CURRENT_TIMESTAMP")
    if "last_login" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN last_login DATETIME")
    conn.execute("CREATE UNIQUE INDEX IF NOT EXISTS idx_accounts_email ON accounts(email)")
    row = conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
    if row and row[0] == 0:
        bootstrap_password = secrets.token_urlsafe(12)
        salt = secrets.token_hex(16)
        pw_hash = hashlib.pbkdf2_hmac(
            "sha256",
            bootstrap_password.encode("utf-8"),
            bytes.fromhex(salt),
            120000,
        ).hex()
        tabs = [
            "analytics",
            "dashboard",
            "detectors",
            "faces",
            "logs",
            "models",
            "notifications",
            "playback",
            "rules",
            "settings",
        ]
        conn.execute(
            "INSERT INTO accounts (email, password_hash, salt, allowed_tabs, is_admin) VALUES (?, ?, ?, ?, 1)",
            ("admin@smarteye.local", pw_hash, salt, json.dumps(tabs)),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            ("bootstrap_password_active", "1", "bool", "Bootstrap Password Active", "security"),
        )
        conn.execute(
            "INSERT OR REPLACE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            ("bootstrap_token", bootstrap_password, "string", "Bootstrap Token", "security"),
        )
        logging.getLogger(__name__).warning(
            "Bootstrap admin password generated during migration. Change it after first login: %s",
            bootstrap_password,
        )
    conn.commit()


def _migrate_v14(conn):
    conn.execute(
        "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
        ("auth_onboarded", "0", "bool", "Require sign-in on launch", "general"),
    )
    conn.commit()


def _migrate_v15(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
    new_cols = [
        ("sec_q1", "TEXT"),
        ("sec_q2", "TEXT"),
        ("sec_q3", "TEXT"),
        ("sec_a1_hash", "TEXT"),
        ("sec_a2_hash", "TEXT"),
        ("sec_a3_hash", "TEXT"),
        ("sec_salt", "TEXT"),
    ]
    for name, ctype in new_cols:
        if name not in cols:
            conn.execute(f"ALTER TABLE accounts ADD COLUMN {name} {ctype}")
    conn.commit()


def _migrate_v16(conn):
    cols = [r[1] for r in conn.execute("PRAGMA table_info(accounts)").fetchall()]
    if "avatar_path" not in cols:
        conn.execute("ALTER TABLE accounts ADD COLUMN avatar_path TEXT")
    conn.commit()


def _migrate_v17(conn):
    conn.execute("CREATE INDEX IF NOT EXISTS idx_rule_conditions_rule_id ON rule_conditions (rule_id)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_alarm_actions_rule_id ON alarm_actions (rule_id)")
    conn.commit()


def _migrate_v18(conn):
    conn.execute(
        """
        CREATE TABLE IF NOT EXISTS clips (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            path TEXT NOT NULL UNIQUE,
            source TEXT DEFAULT 'live',
            camera_id INTEGER REFERENCES cameras(id),
            ts INTEGER,
            face_label TEXT,
            rules_triggered TEXT,
            object_types TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
        """
    )
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_ts ON clips (ts)")
    conn.execute("CREATE INDEX IF NOT EXISTS idx_clips_camera_id ON clips (camera_id)")
    conn.commit()


def _migrate_v19(conn):
    settings = [
        ("ui_pause_inactive_tabs", "1", "bool", "Pause inactive tabs", "performance"),
        ("ui_unload_on_leave", "1", "bool", "Unload heavy tabs on leave", "performance"),
        ("ui_unload_idle_min", "5", "int", "Unload idle tabs after (min)", "performance"),
        ("auto_pause_live_when_idle", "0", "bool", "Auto-stop live cameras when idle", "performance"),
    ]
    for key, value, vtype, label, section in settings:
        conn.execute(
            "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
            (key, value, vtype, label, section),
        )
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=? AND (type IS NULL OR type='')",
            (vtype, label, section, key),
        )
    conn.commit()


def _migrate_v20(conn):
    settings = [
        ("ui_pause_inactive_tabs", "bool", "Pause inactive tabs", "performance"),
        ("ui_unload_on_leave", "bool", "Unload heavy tabs on leave", "performance"),
        ("ui_unload_idle_min", "int", "Unload idle tabs after (min)", "performance"),
        ("auto_pause_live_when_idle", "bool", "Auto-stop live cameras when idle", "performance"),
        ("theme_json_path", "string", "Theme JSON Path", "general"),
    ]
    for key, vtype, label, section in settings:
        conn.execute(
            "UPDATE app_settings SET type=?, label=?, section=? WHERE key=?",
            (vtype, label, section, key),
        )
        if key == "theme_json_path":
            conn.execute(
                "INSERT OR IGNORE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
                ("theme_json_path", "", "string", "Theme JSON Path", "general"),
            )
    conn.commit()


def _migrate_v21(conn):
    tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "detection_logs" in tables:
        cols = [r[1] for r in conn.execute("PRAGMA table_info(detection_logs)").fetchall()]
        if "gender_norm" not in cols:
            conn.execute("ALTER TABLE detection_logs ADD COLUMN gender_norm TEXT DEFAULT 'unknown'")
        if "has_identity" not in cols:
            conn.execute("ALTER TABLE detection_logs ADD COLUMN has_identity INTEGER DEFAULT 0")
        conn.execute(
            "UPDATE detection_logs SET gender_norm = CASE "
            "WHEN detections LIKE '%\"gender\": \"male\"%' THEN 'male' "
            "WHEN detections LIKE '%\"gender\": \"female\"%' THEN 'female' "
            "ELSE 'unknown' END "
        )
        conn.execute(
            "UPDATE detection_logs SET has_identity = CASE "
            "WHEN identity IS NOT NULL AND TRIM(identity) != '' AND LOWER(TRIM(identity)) != 'unknown' THEN 1 "
            "ELSE 0 END "
        )
        conn.execute("CREATE INDEX IF NOT EXISTS idx_detection_logs_gender_norm ON detection_logs (gender_norm)")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_detection_logs_has_identity ON detection_logs (has_identity)")

    obsolete_settings = [
        "experimental_optimization_enabled",
        "experimental_auto_optimize_enabled",
        "experimental_motion_gate_enabled",
        "experimental_motion_threshold",
        "experimental_motion_full_scan_every",
        "experimental_plugin_infer_stride",
        "plugin_failure_cooldown_sec",
        "inference_future_timeout_sec",
    ]
    for key in obsolete_settings:
        conn.execute("DELETE FROM app_settings WHERE key = ?", (key,))
    conn.commit()
