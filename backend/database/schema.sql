CREATE TABLE IF NOT EXISTS cameras (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    source      TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    face_recognition INTEGER DEFAULT 1,
    location    TEXT,
    resolution  TEXT DEFAULT '1280x720',
    fps_limit   INTEGER DEFAULT 30,
    face_similarity_threshold REAL,
    added_at    DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS zones (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id   INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    name        TEXT NOT NULL,
    color       TEXT DEFAULT '#FF0000',
    x1 REAL, y1 REAL, x2 REAL, y2 REAL,
    enabled     INTEGER DEFAULT 1
);

CREATE TABLE IF NOT EXISTS model_plugins (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    name            TEXT NOT NULL UNIQUE,
    model_type      TEXT NOT NULL,
    weight_path     TEXT NOT NULL,
    enabled         INTEGER DEFAULT 1,
    confidence      REAL DEFAULT 0.60,
    preferred_provider TEXT DEFAULT 'auto',
    last_provider   TEXT,
    last_error      TEXT,
    last_error_at   DATETIME,
    description     TEXT,
    version         TEXT,
    added_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS plugin_classes (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    plugin_id       INTEGER REFERENCES model_plugins(id) ON DELETE CASCADE,
    class_index     INTEGER NOT NULL,
    class_name      TEXT NOT NULL,
    display_name    TEXT NOT NULL,
    value_type      TEXT DEFAULT 'boolean',
    enabled         INTEGER DEFAULT 1,
    confidence      REAL DEFAULT 0.5
);

CREATE TABLE IF NOT EXISTS camera_plugins (
    camera_id   INTEGER REFERENCES cameras(id) ON DELETE CASCADE,
    plugin_id   INTEGER REFERENCES model_plugins(id) ON DELETE CASCADE,
    PRIMARY KEY (camera_id, plugin_id)
);

CREATE TABLE IF NOT EXISTS camera_plugin_classes (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    camera_id           INTEGER NOT NULL REFERENCES cameras(id) ON DELETE CASCADE,
    plugin_class_id     INTEGER NOT NULL REFERENCES plugin_classes(id) ON DELETE CASCADE,
    enabled             INTEGER DEFAULT 1,
    confidence          REAL,
    UNIQUE(camera_id, plugin_class_id)
);

CREATE TABLE IF NOT EXISTS rules (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    description TEXT,
    logic       TEXT NOT NULL DEFAULT 'AND',
    action      TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    priority    INTEGER DEFAULT 0,
    camera_id   INTEGER REFERENCES cameras(id),
    zone_id     INTEGER REFERENCES zones(id)
);

CREATE TABLE IF NOT EXISTS rule_conditions (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id     INTEGER REFERENCES rules(id) ON DELETE CASCADE,
    attribute   TEXT NOT NULL,
    operator    TEXT NOT NULL,
    value       TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS alarm_actions (
    id                  INTEGER PRIMARY KEY AUTOINCREMENT,
    rule_id             INTEGER REFERENCES rules(id) ON DELETE CASCADE,
    escalation_level    INTEGER DEFAULT 1,
    trigger_after_sec   INTEGER DEFAULT 0,
    action_type         TEXT NOT NULL,
    action_value        TEXT,
    cooldown_sec        INTEGER DEFAULT 10
);

CREATE TABLE IF NOT EXISTS known_faces (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    uuid            TEXT NOT NULL UNIQUE,
    name            TEXT NOT NULL,
    role            TEXT,
    department      TEXT,
    national_id     TEXT,
    address         TEXT,
    country         TEXT,
    birth_date      TEXT,
    phone           TEXT,
    email           TEXT,
    embedding       BLOB NOT NULL,
    image_path      TEXT,
    embedding_model TEXT DEFAULT '',
    authorized_cameras  TEXT DEFAULT '[]',
    liveness_required   INTEGER DEFAULT 0,
    gender_norm         TEXT DEFAULT 'unknown',
    enabled             INTEGER DEFAULT 1,
    added_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS face_inbox (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    temp_name       TEXT,
    camera_id       INTEGER,
    image_path      TEXT NOT NULL,
    embedding       BLOB,
    embedding_model TEXT DEFAULT '',
    added_at        DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS access_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    face_id     INTEGER REFERENCES known_faces(id),
    camera_id   INTEGER REFERENCES cameras(id),
    timestamp   DATETIME DEFAULT CURRENT_TIMESTAMP,
    decision    TEXT NOT NULL,
    reason      TEXT
);

CREATE TABLE IF NOT EXISTS detection_logs (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    timestamp       DATETIME DEFAULT CURRENT_TIMESTAMP,
    camera_id       INTEGER REFERENCES cameras(id),
    zone_id         INTEGER REFERENCES zones(id),
    identity        TEXT,
    face_confidence REAL,
    detections      TEXT,
    gender_norm     TEXT DEFAULT 'unknown',
    rules_triggered TEXT,
    alarm_level     INTEGER DEFAULT 0,
    snapshot_path   TEXT,
    reviewed        INTEGER DEFAULT 0,
    has_identity    INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS notification_profiles (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    name        TEXT NOT NULL,
    type        TEXT NOT NULL,
    endpoint    TEXT NOT NULL,
    enabled     INTEGER DEFAULT 1,
    auth_token  TEXT
);

CREATE TABLE IF NOT EXISTS app_settings (
    key     TEXT PRIMARY KEY,
    value   TEXT,
    type    TEXT DEFAULT 'string',
    label   TEXT,
    section TEXT
);

CREATE TABLE IF NOT EXISTS clips (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    path            TEXT NOT NULL UNIQUE,
    source          TEXT DEFAULT 'live',
    camera_id       INTEGER REFERENCES cameras(id),
    ts              INTEGER,
    face_label      TEXT,
    rules_triggered TEXT,
    object_types    TEXT,
    created_at      DATETIME DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS accounts (
    id            INTEGER PRIMARY KEY AUTOINCREMENT,
    email         TEXT NOT NULL UNIQUE,
    username      TEXT,
    password_hash TEXT NOT NULL,
    salt          TEXT NOT NULL,
    allowed_tabs  TEXT NOT NULL DEFAULT '[]',
    is_admin      INTEGER DEFAULT 0,
    sec_q1        TEXT,
    sec_q2        TEXT,
    sec_q3        TEXT,
    sec_a1_hash   TEXT,
    sec_a2_hash   TEXT,
    sec_a3_hash   TEXT,
    sec_salt      TEXT,
    avatar_path   TEXT,
    created_at    DATETIME DEFAULT CURRENT_TIMESTAMP,
    last_login    DATETIME
);

INSERT OR IGNORE INTO app_settings VALUES ('theme', 'dark', 'string', 'UI Theme', 'appearance');
INSERT OR IGNORE INTO app_settings VALUES ('gpu_enabled', '1', 'bool', 'Use GPU', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('max_cameras', '4', 'int', 'Max Simultaneous Cameras', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('snapshot_on_alarm', '1', 'bool', 'Save Snapshot on Alarm', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('face_similarity_threshold', '0.45', 'float', 'Face Match Threshold', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('face_recognition_enabled_global', '1', 'bool', 'Enable Face Recognition', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_check_global', '0', 'bool', 'Require Liveness Globally', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_challenge_seconds', '8.0', 'float', 'Liveness Challenge Seconds', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_yaw_threshold', '0.16', 'float', 'Liveness Head Turn Threshold', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_pose_frames', '2', 'int', 'Liveness Consecutive Pose Frames', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_pass_ttl_sec', '30.0', 'float', 'Liveness Pass Time-To-Live', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_failure_hold_sec', '2.0', 'float', 'Liveness Failure Hold', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('liveness_allow_bbox_fallback', '0', 'bool', 'Allow BBox Liveness Fallback', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('log_retention_days', '90', 'int', 'Log Retention (days)', 'data');
INSERT OR IGNORE INTO app_settings VALUES ('db_size_limit_bytes', '0', 'int', 'DB Size Limit (bytes)', 'data');
INSERT OR IGNORE INTO app_settings VALUES ('report_logo_path', '', 'string', 'Report Logo Path', 'reports');
INSERT OR IGNORE INTO app_settings VALUES ('smtp_host', '', 'string', 'SMTP Host', 'notifications');
INSERT OR IGNORE INTO app_settings VALUES ('smtp_port', '587', 'int', 'SMTP Port', 'notifications');
INSERT OR IGNORE INTO app_settings VALUES ('smtp_user', '', 'string', 'SMTP Username', 'notifications');
INSERT OR IGNORE INTO app_settings VALUES ('smtp_pass', '', 'string', 'SMTP Password', 'notifications');
INSERT OR IGNORE INTO app_settings VALUES ('smtp_tls', '1', 'bool', 'Use TLS', 'notifications');
INSERT OR IGNORE INTO app_settings VALUES ('auto_start_cameras', '0', 'bool', 'Auto-start cameras on launch', 'general');
INSERT OR IGNORE INTO app_settings VALUES ('auth_onboarded', '0', 'bool', 'Require sign-in on launch', 'general');
INSERT OR IGNORE INTO app_settings VALUES ('insightface_model_name', 'buffalo_l', 'string', 'Face Model', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('insightface_model_dir', '', 'string', 'Face Model Directory', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('insightface_root_cache', '', 'string', 'InsightFace Root Cache', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('insightface_allowed_modules', '["detection","recognition"]', 'json', 'Allowed InsightFace Modules', 'detection');
INSERT OR IGNORE INTO app_settings VALUES ('limit_resources', '0', 'bool', 'Limit Resource Usage', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('max_cpu_cores', '2', 'int', 'Max CPU Cores', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('max_ram_mb', '4096', 'int', 'Max RAM (MB)', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('ui_tab_transitions_enabled', '1', 'bool', 'Tab transition animations', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('ui_pause_inactive_tabs', '1', 'bool', 'Pause inactive tabs', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('ui_unload_on_leave', '1', 'bool', 'Unload heavy tabs on leave', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('ui_unload_idle_min', '5', 'int', 'Unload idle tabs after (min)', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('auto_pause_live_when_idle', '0', 'bool', 'Auto-stop live cameras when idle', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('live_clip_enabled', '0', 'bool', 'Save Live Alarm Clips', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('live_clip_seconds', '5', 'int', 'Live Clip Seconds', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('live_clip_max_buffer_mb', '128', 'int', 'Live Clip Buffer Limit (MB)', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('live_clip_buffer_max_dim', '640', 'int', 'Live Clip Buffer Max Dimension', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('ui_live_render_fps', '15', 'float', 'Live View Render FPS', 'performance');
INSERT OR IGNORE INTO app_settings VALUES ('inference_future_timeout_sec', '2.0', 'float', 'Inference Timeout (seconds)', 'performance');
CREATE INDEX IF NOT EXISTS idx_detection_logs_timestamp ON detection_logs (timestamp);
CREATE INDEX IF NOT EXISTS idx_detection_logs_camera_id ON detection_logs (camera_id);
CREATE INDEX IF NOT EXISTS idx_known_faces_name ON known_faces (name);
CREATE INDEX IF NOT EXISTS idx_rule_conditions_rule_id ON rule_conditions (rule_id);
CREATE INDEX IF NOT EXISTS idx_alarm_actions_rule_id ON alarm_actions (rule_id);
CREATE INDEX IF NOT EXISTS idx_clips_ts ON clips (ts);
CREATE INDEX IF NOT EXISTS idx_clips_camera_id ON clips (camera_id);
