import hashlib
import logging
import json
import secrets
import uuid


CURRENT_VERSION = 28


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
    conn.execute(f"PRAGMA user_version = {CURRENT_VERSION}")
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
        ("remember_login", "0", "bool", "Keep Me Logged In", "security"),
        ("remember_email", "", "string", "Remembered Email", "security"),
        ("remember_account_id", "", "string", "Remembered Account Id", "security"),
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
