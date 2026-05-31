import contextlib
import json
import logging
import os
import hashlib
import secrets
import sqlite3
import threading
import uuid
import queue
import time
from datetime import datetime

from utils.auth_validation import get_email_validation_error


_write_lock = threading.RLock()

_DB_PATH = None
_conn_local = threading.local()
_CONN_TIMEOUT = 15
_writer_thread = None
_writer_thread_id = None
_writer_conn = None
_write_queue = queue.Queue(maxsize=10000)
_writer_stop = threading.Event()


def _apply_pragmas(conn: sqlite3.Connection) -> None:
    with contextlib.suppress(Exception):
        conn.execute("PRAGMA journal_mode=WAL")
    with contextlib.suppress(Exception):
        conn.execute("PRAGMA synchronous=NORMAL")
    with contextlib.suppress(Exception):
        conn.execute("PRAGMA temp_store=MEMORY")
    with contextlib.suppress(Exception):
        conn.execute("PRAGMA cache_size=2000")
    with contextlib.suppress(Exception):
        conn.execute("PRAGMA foreign_keys=ON")


def _create_conn() -> sqlite3.Connection:
    if not _DB_PATH:
        raise RuntimeError("Database not initialized")
    conn = sqlite3.connect(_DB_PATH, check_same_thread=False, timeout=_CONN_TIMEOUT)
    conn.row_factory = sqlite3.Row
    _apply_pragmas(conn)
    return conn


def _writer_loop():
    global _writer_conn, _writer_thread_id
    _writer_thread_id = threading.get_ident()
    _writer_conn = _create_conn()
    while True:
        try:
            item = _write_queue.get(timeout=0.2)
        except queue.Empty:
            continue
        if item is None:
            _write_queue.task_done()
            break
        kind = item[0]
        result_q = item[-1]
        try:
            if kind == "SQL":
                _, sql, params, commit, result_q = item
                cur = _writer_conn.execute(sql, params)
                if commit:
                    _writer_conn.commit()
                result_q.put((cur, None))
            elif kind == "CALL":
                _, fn, result_q = item
                res = fn(_writer_conn)
                result_q.put((res, None))
        except Exception as e:
            try:
                _writer_conn.rollback()
            except Exception:
                pass
            result_q.put((None, e))
        finally:
            _write_queue.task_done()
    try:
        if _writer_conn:
            _writer_conn.close()
    except Exception:
        pass


def _ensure_writer():
    global _writer_thread
    if _writer_thread and _writer_thread.is_alive():
        return
    _writer_stop.clear()
    _writer_thread = threading.Thread(target=_writer_loop, name="db-writer", daemon=True)
    _writer_thread.start()


def _queue_write_item(item):
    if _writer_stop.is_set():
        raise RuntimeError("Database writer is closed")
    try:
        _write_queue.put(item, timeout=2.0)
        return
    except queue.Full:
        logging.getLogger(__name__).warning("DB write queue full; waiting for worker")
    _write_queue.put(item)


class _ConnProxy:
    def _get(self) -> sqlite3.Connection:
        conn = getattr(_conn_local, "conn", None)
        if conn is None:
            conn = _create_conn()
            _conn_local.conn = conn
        return conn

    def __getattr__(self, name):
        return getattr(self._get(), name)

    def __setattr__(self, name, value):
        setattr(self._get(), name, value)


_conn = _ConnProxy()
_DEFAULT_ALLOWED_TABS = [
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
_DEFAULT_ADMIN_EMAIL = "admin@smarteye.local"
_SEC_QUESTIONS_DEFAULT = (
    "What is your favorite color?",
    "What city were you born in?",
    "What is your pet name?",
)
_SETTING_DEFAULTS = {
    "theme": {"value": "dark", "type": "string", "label": "UI Theme", "section": "appearance"},
    "theme_json_path": {"value": "", "type": "string", "label": "Theme JSON Path", "section": "general"},
    "log_retention_days": {"value": "90", "type": "int", "label": "Log Retention (days)", "section": "data"},
    "auto_start_cameras": {"value": "0", "type": "bool", "label": "Auto-start cameras on launch", "section": "general"},
    "minimize_to_tray": {"value": "0", "type": "bool", "label": "Minimize to tray", "section": "general"},
    "popup_notifications_enabled": {"value": "1", "type": "bool", "label": "Popup notifications", "section": "notifications"},
    "debug_mode_enabled": {"value": "0", "type": "bool", "label": "Debugging mode", "section": "general"},
    "experimental_mode_enabled": {"value": "0", "type": "bool", "label": "Experimental settings", "section": "general"},
    "liveness_check_global": {"value": "0", "type": "bool", "label": "Require Liveness Globally", "section": "detection"},
}


def init(db_path):
    global _DB_PATH
    _DB_PATH = db_path
    conn = _create_conn()
    _conn_local.conn = conn
    _ensure_writer()

    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")
    try:
        with open(schema_path) as f:
            schema_sql = f.read()
        conn.executescript(schema_sql)
        conn.commit()
    except Exception as e:
        logging.getLogger(__name__).exception("Failed to apply initial schema: %s", e)

    try:
        from backend.database import migrations

        try:
            migrations.apply(conn)
        except Exception:
            logging.getLogger(__name__).exception("Failed to apply migrations")
    except Exception:
        pass

    try:
        tables = [r[0] for r in conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
        if "cameras" not in tables:
            logging.getLogger(__name__).warning("Essential table 'cameras' missing - attempting to reapply schema.sql")
            try:
                with open(schema_path) as f:
                    conn.executescript(f.read())
                conn.commit()
            except Exception:
                logging.getLogger(__name__).exception("Reapplying schema failed")
    except Exception:
        logging.getLogger(__name__).exception("Failed to verify database tables")


def get_conn():
    return _conn._get()


def close():
    global _writer_thread, _writer_thread_id, _writer_conn
    _writer_stop.set()
    wait_for_writer_idle(timeout_sec=5.0)
    conn = getattr(_conn_local, "conn", None)
    if conn:
        conn.close()
        _conn_local.conn = None
    writer = _writer_thread
    if writer and writer.is_alive():
        try:
            _write_queue.put(None, timeout=2.0)
        except Exception:
            pass
    try:
        if writer and writer.is_alive():
            writer.join(timeout=2.0)
    except Exception:
        pass
    if writer is _writer_thread and (writer is None or not writer.is_alive()):
        _writer_thread = None
        _writer_thread_id = None
        _writer_conn = None


def _normalize_email(email: str) -> str:
    return (email or "").strip().lower()


def is_bootstrap_admin_email(email: str) -> bool:
    return _normalize_email(email) == _DEFAULT_ADMIN_EMAIL


def get_bootstrap_admin_account():
    row = _conn.execute("SELECT * FROM accounts WHERE email=?", (_DEFAULT_ADMIN_EMAIL,)).fetchone()
    return _row_to_account(row) if row else None


def reconcile_bootstrap_state() -> bool:
    active = get_bool("bootstrap_password_active", False)
    if not active:
        return False
    bootstrap_account = get_bootstrap_admin_account()
    if bootstrap_account:
        return True
    _clear_bootstrap_token()
    return False


def bootstrap_password_change_required(account=None) -> bool:
    if not reconcile_bootstrap_state():
        return False
    if account is None:
        return True
    email = account.get("email", "") if isinstance(account, dict) else str(account or "")
    return is_bootstrap_admin_email(email)


def _infer_setting_type(value) -> str:
    if isinstance(value, bool):
        return "bool"
    if isinstance(value, int) and not isinstance(value, bool):
        return "int"
    if isinstance(value, float):
        return "float"
    if isinstance(value, (list, tuple, dict)):
        return "json"
    return "string"


def _serialize_setting_value(value, vtype: str) -> str:
    if vtype == "bool":
        return "1" if _as_bool(value, False) else "0"
    if vtype == "json":
        return json.dumps(value)
    return "" if value is None else str(value)


def _normalize_tabs(tabs):
    if not tabs:
        return []
    uniq = []
    for t in tabs:
        if t and t not in uniq:
            uniq.append(t)
    return uniq


def _build_update(allowed: set[str], kwargs: dict) -> tuple[str | None, list | None]:
    if not kwargs:
        return None, None
    safe = {k: v for k, v in kwargs.items() if k in allowed}
    unknown = [k for k in kwargs.keys() if k not in allowed]
    if unknown:
        logging.getLogger(__name__).warning("Ignoring unknown update fields: %s", unknown)
    if not safe:
        return None, None
    sets = ", ".join(f"{k}=?" for k in safe.keys())
    vals = list(safe.values())
    return sets, vals


def _write_execute(sql: str, params=(), commit: bool = True):
    _ensure_writer()
    if threading.get_ident() == _writer_thread_id and _writer_conn is not None:
        cur = _writer_conn.execute(sql, params)
        if commit:
            _writer_conn.commit()
        return cur
    result_q = queue.Queue(maxsize=1)
    _queue_write_item(("SQL", sql, params, commit, result_q))
    cur, err = result_q.get()
    if err:
        raise err
    return cur


def _write_call(fn):
    _ensure_writer()
    if threading.get_ident() == _writer_thread_id and _writer_conn is not None:
        return fn(_writer_conn)
    result_q = queue.Queue(maxsize=1)
    _queue_write_item(("CALL", fn, result_q))
    res, err = result_q.get()
    if err:
        raise err
    return res


def write_transaction(fn):
    def _op(conn):
        result = fn(conn)
        conn.commit()
        return result

    return _write_call(_op)


def get_setting_defaults(keys=None):
    if keys is None:
        selected = _SETTING_DEFAULTS
    else:
        selected = {key: _SETTING_DEFAULTS[key] for key in keys if key in _SETTING_DEFAULTS}
    return {key: dict(value) for key, value in selected.items()}


def _hash_password(password: str, salt: str | None = None):
    salt_val = salt or secrets.token_hex(16)
    digest = hashlib.pbkdf2_hmac("sha256", password.encode("utf-8"), bytes.fromhex(salt_val), 120000)
    return salt_val, digest.hex()


def _hash_answer(answer: str, salt: str):
    digest = hashlib.pbkdf2_hmac("sha256", answer.strip().lower().encode("utf-8"), bytes.fromhex(salt), 80000)
    return digest.hex()


def _generate_bootstrap_password() -> str:
    return secrets.token_urlsafe(12)


def _store_bootstrap_token(token: str) -> None:
    try:
        set_setting("bootstrap_password_active", "1")
        set_setting("bootstrap_token", token)
    except Exception:
        pass


def _clear_bootstrap_token() -> None:
    try:
        set_setting("bootstrap_password_active", "0")
        set_setting("bootstrap_token", "")
    except Exception:
        pass


def _row_to_account(row):
    allowed = []
    try:
        allowed = json.loads(row["allowed_tabs"]) if row["allowed_tabs"] else []
    except Exception:
        allowed = []
    return {
        "id": row["id"],
        "email": row["email"],
        "username": row["username"] if "username" in row.keys() else "",
        "allowed_tabs": allowed,
        "is_admin": bool(row["is_admin"]),
        "created_at": row["created_at"],
        "last_login": row["last_login"],
        "sec_q1": row["sec_q1"] if "sec_q1" in row.keys() else None,
        "sec_q2": row["sec_q2"] if "sec_q2" in row.keys() else None,
        "sec_q3": row["sec_q3"] if "sec_q3" in row.keys() else None,
        "avatar_path": row["avatar_path"] if "avatar_path" in row.keys() else "",
    }


def ensure_default_account():
    tables = [r[0] for r in _conn.execute("SELECT name FROM sqlite_master WHERE type='table'").fetchall()]
    if "accounts" not in tables:
        return
    row = _conn.execute("SELECT COUNT(*) FROM accounts").fetchone()
    if not row or row[0] > 0:
        return
    try:
        bootstrap_password = _generate_bootstrap_password()
        _store_bootstrap_token(bootstrap_password)
        logging.getLogger(__name__).warning(
            "Bootstrap admin password generated. Change it after first login: %s",
            bootstrap_password,
        )
        create_account(
            _DEFAULT_ADMIN_EMAIL,
            bootstrap_password,
            allowed_tabs=_DEFAULT_ALLOWED_TABS,
            is_admin=True,
            security=(list(_SEC_QUESTIONS_DEFAULT), ["", "", ""]),
        )
    except Exception:
        pass


def create_account(
    email: str,
    password: str,
    allowed_tabs=None,
    is_admin: bool = False,
    security=None,
    avatar_path: str = "",
    username: str = "",
):
    err = get_email_validation_error(email, allow_internal=True)
    if err:
        raise ValueError(err)
    sec_questions, sec_answers = security or ([], [])
    salt, pw_hash = _hash_password(password)
    sec_salt = secrets.token_hex(16)
    hashes = []
    for ans in sec_answers or []:
        hashes.append(_hash_answer(ans or "", sec_salt))
    while len(hashes) < 3:
        hashes.append("")
    qs = list(sec_questions or [])
    while len(qs) < 3:
        qs.append("")
    tabs = json.dumps(_normalize_tabs(allowed_tabs or []))
    cur = _write_execute(
        """INSERT INTO accounts
        (email, username, password_hash, salt, allowed_tabs, is_admin,
         sec_q1, sec_q2, sec_q3, sec_a1_hash, sec_a2_hash, sec_a3_hash, sec_salt, avatar_path)
         VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            _normalize_email(email),
            (username or "").strip(),
            pw_hash,
            salt,
            tabs,
            1 if is_admin else 0,
            qs[0],
            qs[1],
            qs[2],
            hashes[0],
            hashes[1],
            hashes[2],
            sec_salt,
            avatar_path or "",
        ),
    )
    return cur.lastrowid


def update_account(account_id: int, *, email=None, password=None, allowed_tabs=None, is_admin=None, security=None, avatar_path=None, username=None):
    current = get_account(account_id)
    sets = []
    vals = []
    password_updated = False
    if email is not None:
        err = get_email_validation_error(email, allow_internal=True)
        if err:
            raise ValueError(err)
        sets.append("email=?")
        vals.append(_normalize_email(email))
    if username is not None:
        sets.append("username=?")
        vals.append((username or "").strip())
    if password is not None:
        salt, pw_hash = _hash_password(password)
        sets.append("password_hash=?")
        sets.append("salt=?")
        vals.append(pw_hash)
        vals.append(salt)
        password_updated = True
    if security is not None:
        sec_questions, sec_answers = security
        sec_salt = secrets.token_hex(16)
        qs = list(sec_questions or [])
        while len(qs) < 3:
            qs.append("")
        hashes = []
        for ans in sec_answers or []:
            hashes.append(_hash_answer(ans or "", sec_salt))
        while len(hashes) < 3:
            hashes.append("")
        sets.extend(["sec_q1=?", "sec_q2=?", "sec_q3=?", "sec_a1_hash=?", "sec_a2_hash=?", "sec_a3_hash=?", "sec_salt=?"])
        vals.extend([qs[0], qs[1], qs[2], hashes[0], hashes[1], hashes[2], sec_salt])
    if allowed_tabs is not None:
        sets.append("allowed_tabs=?")
        vals.append(json.dumps(_normalize_tabs(allowed_tabs)))
    if is_admin is not None:
        sets.append("is_admin=?")
        vals.append(1 if is_admin else 0)
    if avatar_path is not None:
        sets.append("avatar_path=?")
        vals.append(avatar_path)
    if not sets:
        return
    vals.append(account_id)
    _write_execute(f"UPDATE accounts SET {', '.join(sets)} WHERE id=?", vals)
    current_email = current.get("email", "") if current else ""
    updated_email = email if email is not None else current_email
    if (
        reconcile_bootstrap_state()
        and (password_updated or updated_email != current_email)
        and (is_bootstrap_admin_email(current_email) or is_bootstrap_admin_email(updated_email))
    ):
        _clear_bootstrap_token()


def delete_account(account_id: int):
    account = get_account(account_id)
    _write_execute("DELETE FROM accounts WHERE id=?", (account_id,))
    if account and is_bootstrap_admin_email(account.get("email", "")):
        _clear_bootstrap_token()


def get_accounts():
    rows = _conn.execute("SELECT * FROM accounts ORDER BY email").fetchall()
    return [_row_to_account(r) for r in rows]


def get_account(account_id: int):
    row = _conn.execute("SELECT * FROM accounts WHERE id=?", (account_id,)).fetchone()
    return _row_to_account(row) if row else None


def get_account_by_email(email: str):
    row = _conn.execute("SELECT * FROM accounts WHERE email=?", (_normalize_email(email),)).fetchone()
    return row


def get_first_admin_account():
    row = _conn.execute("SELECT * FROM accounts WHERE is_admin=1 ORDER BY id LIMIT 1").fetchone()
    return _row_to_account(row) if row else None


def verify_credentials(email: str, password: str):
    row = _conn.execute("SELECT * FROM accounts WHERE email=?", (_normalize_email(email),)).fetchone()
    if not row:
        return None
    salt = row["salt"]
    _, pw_hash = _hash_password(password, salt)
    if pw_hash != row["password_hash"]:
        return None
    return _row_to_account(row)


def verify_security_answers(email: str, answers: list[str]):
    row = get_account_by_email(email)
    if not row:
        return None
    salt = row["sec_salt"]
    if not salt:
        return None
    if not answers or len(answers) < 3:
        return None
    if any(not (a or "").strip() for a in answers[:3]):
        return None
    hashes = []
    for ans in answers[:3]:
        hashes.append(_hash_answer(ans or "", salt))
    stored = [row["sec_a1_hash"], row["sec_a2_hash"], row["sec_a3_hash"]]
    if all(h1 == h2 for h1, h2 in zip(hashes, stored)):
        return _row_to_account(row)
    return None


def set_password(account_id: int, new_password: str):
    salt, pw_hash = _hash_password(new_password)
    _write_execute("UPDATE accounts SET password_hash=?, salt=? WHERE id=?", (pw_hash, salt, account_id))
    account = get_account(account_id)
    if account and reconcile_bootstrap_state() and is_bootstrap_admin_email(account.get("email", "")):
        _clear_bootstrap_token()


def touch_last_login(account_id: int):
    try:
        now = datetime.utcnow().isoformat()
    except Exception:
        now = None
    _write_execute("UPDATE accounts SET last_login=? WHERE id=?", (now, account_id))


def add_camera(name, source, location="", resolution="1280x720", fps_limit=30, face_recognition=1, enabled=1):
    cur = _write_execute(
        "INSERT INTO cameras (name, source, enabled, location, resolution, fps_limit, face_recognition) VALUES (?, ?, ?, ?, ?, ?, ?)",
        (
            name,
            source,
            1 if enabled in (1, True, "1", "true") else 0,
            location,
            resolution,
            fps_limit,
            1 if face_recognition in (1, True, "1", "true") else 0,
        ),
    )
    return cur.lastrowid


def update_camera(cam_id, **kwargs):
    allowed = {
        "name",
        "source",
        "enabled",
        "location",
        "resolution",
        "fps_limit",
        "face_recognition",
        "face_similarity_threshold",
    }
    sets, vals = _build_update(allowed, kwargs)
    if not sets:
        return
    vals.append(cam_id)
    _write_execute(f"UPDATE cameras SET {sets} WHERE id=?", vals)


def delete_camera(cam_id):
    def _op(conn):
        cur = conn.cursor()
        try:
            zone_ids = [r[0] for r in cur.execute("SELECT id FROM zones WHERE camera_id=?", (cam_id,)).fetchall()]
            if zone_ids:
                placeholders = ",".join("?" for _ in zone_ids)
                cur.execute(f"UPDATE rules SET zone_id=NULL WHERE zone_id IN ({placeholders})", zone_ids)

            cur.execute("DELETE FROM clips WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM face_inbox WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM detection_logs WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM access_log WHERE camera_id=?", (cam_id,))
            cur.execute("UPDATE rules SET camera_id=NULL WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM camera_plugin_classes WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM camera_plugins WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM zones WHERE camera_id=?", (cam_id,))
            cur.execute("DELETE FROM cameras WHERE id=?", (cam_id,))
            conn.commit()
        except Exception:
            conn.rollback()
            raise

    _write_call(_op)


def get_cameras(enabled_only=False):
    q = "SELECT * FROM cameras"
    if enabled_only:
        q += " WHERE enabled=1"
    return [dict(r) for r in _conn.execute(q).fetchall()]


def get_camera(cam_id):
    row = _conn.execute("SELECT * FROM cameras WHERE id=?", (cam_id,)).fetchone()
    return dict(row) if row else None


def get_camera_face_threshold(camera_id):
    cam = get_camera(camera_id)
    if not cam:
        return None
    val = cam.get("face_similarity_threshold")
    if val is None:
        return None
    try:
        return float(val)
    except Exception:
        return None


def add_plugin(name, model_type, weight_path, confidence=0.6, description="", version="1.0"):
    cur = _write_execute(
        "INSERT INTO model_plugins (name, model_type, weight_path, confidence, description, version) VALUES (?, ?, ?, ?, ?, ?)",
        (name, model_type, weight_path, confidence, description, version),
    )
    return cur.lastrowid


def update_plugin(plugin_id, **kwargs):
    allowed = {
        "name",
        "model_type",
        "weight_path",
        "enabled",
        "confidence",
        "description",
        "version",
        "preferred_provider",
        "last_error",
        "last_error_at",
        "last_provider",
    }
    sets, vals = _build_update(allowed, kwargs)
    if not sets:
        return
    vals.append(plugin_id)
    _write_execute(f"UPDATE model_plugins SET {sets} WHERE id=?", vals)


def set_plugin_error(plugin_id, message):
    try:
        now = datetime.utcnow().isoformat()
    except Exception:
        now = None
    update_plugin(plugin_id, last_error=message, last_error_at=now)


def clear_plugin_error(plugin_id, *, preferred_provider=None, last_provider=None):
    payload = {"last_error": None, "last_error_at": None}
    if preferred_provider is not None:
        payload["preferred_provider"] = preferred_provider
    if last_provider is not None:
        payload["last_provider"] = last_provider
    update_plugin(plugin_id, **payload)


def delete_plugin(plugin_id):
    _write_execute("DELETE FROM model_plugins WHERE id=?", (plugin_id,))


def get_plugins(enabled_only=False):
    q = "SELECT * FROM model_plugins"
    if enabled_only:
        q += " WHERE enabled=1"
    return [dict(r) for r in _conn.execute(q).fetchall()]


def get_plugin(plugin_id):
    row = _conn.execute("SELECT * FROM model_plugins WHERE id=?", (plugin_id,)).fetchone()
    return dict(row) if row else None


def add_plugin_class(plugin_id, class_index, class_name, display_name, value_type="boolean", confidence=0.5):
    cur = _write_execute(
        "INSERT INTO plugin_classes (plugin_id, class_index, class_name, display_name, value_type, confidence) VALUES (?, ?, ?, ?, ?, ?)",
        (plugin_id, class_index, class_name, display_name, value_type, confidence),
    )
    try:
        from backend.pipeline import analyzer

        analyzer.invalidate_cache()
    except Exception:
        pass
    return cur.lastrowid


def set_class_color(class_id: int, color: str) -> None:
    _write_execute("UPDATE plugin_classes SET color=? WHERE id=?", (color, class_id))
    try:
        from backend.pipeline import analyzer

        analyzer.invalidate_cache()
    except Exception:
        pass


def update_plugin_class(cls_id, **kwargs):
    allowed = {
        "plugin_id",
        "class_index",
        "class_name",
        "display_name",
        "value_type",
        "enabled",
        "confidence",
        "color",
    }
    sets, vals = _build_update(allowed, kwargs)
    if not sets:
        return
    vals.append(cls_id)
    _write_execute(f"UPDATE plugin_classes SET {sets} WHERE id=?", vals)
    try:
        from backend.pipeline import analyzer

        analyzer.invalidate_cache()
    except Exception:
        pass


def get_plugin_classes(plugin_id=None, enabled_only=False):
    q = "SELECT * FROM plugin_classes WHERE 1=1"
    params = []
    if plugin_id is not None:
        q += " AND plugin_id=?"
        params.append(plugin_id)
    if enabled_only:
        q += " AND enabled=1"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def assign_plugin_to_camera(camera_id, plugin_id):
    _write_execute(
        "INSERT OR IGNORE INTO camera_plugins (camera_id, plugin_id) VALUES (?, ?)",
        (camera_id, plugin_id),
    )


def unassign_plugin_from_camera(camera_id, plugin_id):
    _write_execute(
        "DELETE FROM camera_plugins WHERE camera_id=? AND plugin_id=?",
        (camera_id, plugin_id),
    )


def get_camera_plugins(camera_id):
    rows = _conn.execute(
        "SELECT mp.* FROM model_plugins mp JOIN camera_plugins cp ON mp.id=cp.plugin_id WHERE cp.camera_id=? AND mp.enabled=1",
        (camera_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def get_plugin_cameras(plugin_id):
    rows = _conn.execute(
        "SELECT c.* FROM cameras c JOIN camera_plugins cp ON c.id=cp.camera_id WHERE cp.plugin_id=?",
        (plugin_id,),
    ).fetchall()
    return [dict(r) for r in rows]


def assign_camera_plugin_class(camera_id, plugin_class_id, enabled=1, confidence=None):
    enabled_value = 1 if enabled in (1, True, "1", "true") else 0

    def _op(conn):
        try:
            conn.execute(
                "INSERT INTO camera_plugin_classes (camera_id, plugin_class_id, enabled, confidence) VALUES (?, ?, ?, ?) "
                "ON CONFLICT(camera_id, plugin_class_id) DO UPDATE SET enabled=excluded.enabled, confidence=excluded.confidence",
                (camera_id, plugin_class_id, enabled_value, confidence),
            )
        except Exception:
            cur = conn.execute(
                "UPDATE camera_plugin_classes SET enabled=?, confidence=? WHERE camera_id=? AND plugin_class_id=?",
                (enabled_value, confidence, camera_id, plugin_class_id),
            )
            if cur.rowcount == 0:
                conn.execute(
                    "INSERT OR IGNORE INTO camera_plugin_classes (camera_id, plugin_class_id, enabled, confidence) VALUES (?, ?, ?, ?)",
                    (camera_id, plugin_class_id, enabled_value, confidence),
                )
        conn.commit()

    _write_call(_op)


def get_camera_plugin_classes(camera_id, plugin_id):

    q = """
        SELECT cpc.*, pc.class_index, pc.class_name, pc.id as plugin_class_id
        FROM camera_plugin_classes cpc
        JOIN plugin_classes pc ON cpc.plugin_class_id = pc.id
        WHERE cpc.camera_id = ? AND pc.plugin_id = ?
    """
    rows = _conn.execute(q, (camera_id, plugin_id)).fetchall()
    return [dict(r) for r in rows]


def remove_camera_plugin_class(camera_id, plugin_class_id):
    _write_execute(
        "DELETE FROM camera_plugin_classes WHERE camera_id=? AND plugin_class_id=?",
        (camera_id, plugin_class_id),
    )


def add_rule(name, description, logic, action, priority=0, camera_id=None):
    cur = _write_execute(
        "INSERT INTO rules (name, description, logic, action, priority, camera_id) VALUES (?, ?, ?, ?, ?, ?)",
        (name, description, logic, action, priority, camera_id),
    )
    try:
        from backend.pipeline import rule_engine

        rule_engine.invalidate_rule_cache()
    except Exception:
        pass
    return cur.lastrowid


def update_rule(rule_id, **kwargs):
    allowed = {
        "name",
        "description",
        "logic",
        "action",
        "enabled",
        "priority",
        "camera_id",
    }
    sets, vals = _build_update(allowed, kwargs)
    if not sets:
        return
    vals.append(rule_id)
    _write_execute(f"UPDATE rules SET {sets} WHERE id=?", vals)
    try:
        from backend.pipeline import rule_engine

        rule_engine.invalidate_rule_cache()
    except Exception:
        pass


def delete_rule(rule_id):
    _write_execute("DELETE FROM rules WHERE id=?", (rule_id,))
    try:
        from backend.pipeline import rule_engine

        rule_engine.invalidate_rule_cache()
    except Exception:
        pass


def get_rules(enabled_only=False, camera_id=None):
    q = "SELECT * FROM rules WHERE 1=1"
    params = []
    if enabled_only:
        q += " AND enabled=1"
    if camera_id is not None:
        q += " AND (camera_id IS NULL OR camera_id=?)"
        params.append(camera_id)
    q += " ORDER BY priority DESC"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def get_rule(rule_id):
    row = _conn.execute("SELECT * FROM rules WHERE id=?", (rule_id,)).fetchone()
    return dict(row) if row else None


def add_rule_condition(rule_id, attribute, operator, value):
    cur = _write_execute(
        "INSERT INTO rule_conditions (rule_id, attribute, operator, value) VALUES (?, ?, ?, ?)",
        (rule_id, attribute, operator, value),
    )
    try:
        from backend.pipeline import rule_engine

        rule_engine.invalidate_rule_cache()
    except Exception:
        pass
    return cur.lastrowid


def delete_rule_conditions(rule_id):
    _write_execute("DELETE FROM rule_conditions WHERE rule_id=?", (rule_id,))
    try:
        from backend.pipeline import rule_engine

        rule_engine.invalidate_rule_cache()
    except Exception:
        pass


def get_rule_conditions(rule_id):
    return [dict(r) for r in _conn.execute("SELECT * FROM rule_conditions WHERE rule_id=?", (rule_id,)).fetchall()]


def add_alarm_action(rule_id, escalation_level, trigger_after_sec, action_type, action_value="", cooldown_sec=10):
    cur = _write_execute(
        "INSERT INTO alarm_actions (rule_id, escalation_level, trigger_after_sec, action_type, action_value, cooldown_sec) VALUES (?, ?, ?, ?, ?, ?)",
        (rule_id, escalation_level, trigger_after_sec, action_type, action_value, cooldown_sec),
    )
    return cur.lastrowid


def delete_alarm_actions(rule_id):
    _write_execute("DELETE FROM alarm_actions WHERE rule_id=?", (rule_id,))


def get_alarm_actions(rule_id=None, escalation_level=None):
    q = "SELECT * FROM alarm_actions WHERE 1=1"
    params = []
    if rule_id is not None:
        q += " AND rule_id=?"
        params.append(rule_id)
    if escalation_level is not None:
        q += " AND escalation_level<=?"
        params.append(escalation_level)
    q += " ORDER BY escalation_level"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def add_known_face(
    name,
    role,
    department,
    embedding_bytes,
    image_path="",
    authorized_cameras="[]",
    liveness_required=0,
    external_uuid=None,
    address="",
    country="",
    birth_date="",
    phone="",
    email="",
    embedding_model="",
    gender=None,
    national_id="",
):

    try:
        emb_param = embedding_bytes
        if emb_param is None:
            raise ValueError("embedding_bytes is None")

        try:
            import numpy as _np

            if isinstance(emb_param, _np.ndarray):
                emb_param = emb_param.astype(_np.float32).tobytes()
        except Exception:
            pass
        if isinstance(emb_param, memoryview):
            emb_param = bytes(emb_param)
        if isinstance(emb_param, bytearray):
            emb_param = bytes(emb_param)

        emb_param = sqlite3.Binary(emb_param)
    except Exception as e:
        raise ValueError(f"Invalid embedding_bytes for known face: {e}") from e

    row_uuid = external_uuid or str(uuid.uuid4())
    gender_norm = _normalize_gender_value(gender)
    cur = _write_execute(
        """INSERT INTO known_faces
           (uuid, name, role, department, national_id, address, country, birth_date, phone, email, embedding, image_path, authorized_cameras, liveness_required, embedding_model, gender_norm)
           VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
        (
            row_uuid,
            name,
            role,
            department,
            national_id,
            address,
            country,
            birth_date,
            phone,
            email,
            emb_param,
            image_path,
            authorized_cameras,
            liveness_required,
            embedding_model or "",
            gender_norm,
        ),
    )
    return cur.lastrowid


def add_face_inbox(temp_name, camera_id, embedding_bytes, image_path="", embedding_model=""):
    emb_param = None
    try:
        emb_param = embedding_bytes
        if emb_param is not None:
            import numpy as _np

            if isinstance(emb_param, _np.ndarray):
                emb_param = emb_param.astype(_np.float32).tobytes()
        if isinstance(emb_param, memoryview):
            emb_param = bytes(emb_param)
        if isinstance(emb_param, bytearray):
            emb_param = bytes(emb_param)
        if emb_param is not None:
            emb_param = sqlite3.Binary(emb_param)
    except Exception:
        emb_param = None
    cur = _write_execute(
        """INSERT INTO face_inbox (temp_name, camera_id, image_path, embedding, embedding_model)
           VALUES (?, ?, ?, ?, ?)""",
        (temp_name, camera_id, image_path, emb_param, embedding_model or ""),
    )
    return cur.lastrowid


def get_face_inbox():
    rows = _conn.execute("SELECT * FROM face_inbox ORDER BY added_at DESC").fetchall()
    return [dict(r) for r in rows]


def delete_face_inbox(entry_id: int):
    _write_execute("DELETE FROM face_inbox WHERE id=?", (entry_id,))


def update_known_face(face_id, **kwargs):
    if not kwargs:
        return
    if "gender" in kwargs and "gender_norm" not in kwargs:
        kwargs["gender_norm"] = _normalize_gender_value(kwargs.pop("gender"))
    elif "gender_norm" in kwargs:
        kwargs["gender_norm"] = _normalize_gender_value(kwargs.get("gender_norm"))
    allowed = {
        "uuid",
        "name",
        "role",
        "department",
        "address",
        "country",
        "national_id",
        "birth_date",
        "phone",
        "email",
        "embedding",
        "image_path",
        "authorized_cameras",
        "liveness_required",
        "embedding_model",
        "gender_norm",
        "enabled",
    }
    sets, vals = _build_update(allowed, kwargs)
    if not sets:
        return
    vals.append(face_id)
    _write_execute(f"UPDATE known_faces SET {sets} WHERE id=?", vals)


def delete_known_face(face_id):
    def _op(conn):
        conn.execute("DELETE FROM access_log WHERE face_id=?", (face_id,))
        conn.execute("DELETE FROM known_faces WHERE id=?", (face_id,))
        conn.commit()

    _write_call(_op)


def get_known_faces(enabled_only=False):
    q = "SELECT * FROM known_faces"
    if enabled_only:
        q += " WHERE enabled=1"
    rows = [dict(r) for r in _conn.execute(q).fetchall()]
    for row in rows:
        row["gender"] = _normalize_gender_value(row.get("gender") or row.get("gender_norm"))
    return rows


def get_known_face(face_id):
    row = _conn.execute("SELECT * FROM known_faces WHERE id=?", (face_id,)).fetchone()
    if not row:
        return None
    data = dict(row)
    data["gender"] = _normalize_gender_value(data.get("gender") or data.get("gender_norm"))
    return data


def add_access_log(face_id, camera_id, decision, reason=""):
    cur = _write_execute(
        "INSERT INTO access_log (face_id, camera_id, decision, reason) VALUES (?, ?, ?, ?)",
        (face_id, camera_id, decision, reason),
    )
    return cur.lastrowid


def _normalize_gender_value(value) -> str:
    if value is None:
        return "unknown"
    text = str(value).strip().lower()
    if text in ("male", "m", "man", "boy", "1"):
        return "male"
    if text in ("female", "f", "woman", "girl", "0"):
        return "female"
    return "unknown"


def _identity_to_text(identity) -> str:
    if identity is None:
        return ""
    if isinstance(identity, dict):
        for key in ("name", "identity", "email", "id"):
            value = identity.get(key)
            if value is not None and str(value).strip():
                return str(value).strip()
        return ""
    return str(identity).strip()


def _json_safe_value(value):
    if value is None or isinstance(value, (str, int, float, bool)):
        return value
    if isinstance(value, dict):
        return {str(k): _json_safe_value(v) for k, v in value.items() if k != "embedding"}
    if isinstance(value, (list, tuple)):
        return [_json_safe_value(v) for v in value]
    if isinstance(value, bytes):
        return "<bytes>"
    tolist = getattr(value, "tolist", None)
    if callable(tolist):
        try:
            return _json_safe_value(tolist())
        except Exception:
            return str(value)
    return str(value)


def _normalize_detections_payload(payload):
    data = payload
    if isinstance(payload, str):
        try:
            data = json.loads(payload)
        except Exception:
            data = {}
    if not isinstance(data, dict):
        data = {}
    data = _json_safe_value(dict(data))
    data["gender"] = _normalize_gender_value(data.get("gender"))
    return data


def _serialize_rules_triggered(rules_triggered):
    if rules_triggered is None:
        return None
    if isinstance(rules_triggered, str):
        return rules_triggered
    return json.dumps(_json_safe_value(rules_triggered))


def _has_identity_value(identity: str) -> int:
    ident_text = (identity or "").strip().lower()
    return 1 if ident_text and ident_text != "unknown" else 0


def _prepare_detection_log_values(record: dict, *, include_timestamp: bool = False):
    det_norm = _normalize_detections_payload(record.get("detections"))
    identity = _identity_to_text(record.get("identity"))
    if not identity:
        identity = _identity_to_text(det_norm.get("identity"))
    gender_norm = _normalize_gender_value(record.get("gender") or det_norm.get("gender"))
    values = [
        record.get("camera_id"),
        record.get("zone_id"),
        identity,
        float(record.get("face_confidence") or 0.0),
        json.dumps(det_norm),
        gender_norm,
        _serialize_rules_triggered(record.get("rules_triggered")),
        int(record.get("alarm_level") or 0),
        record.get("snapshot_path") or "",
        int(record.get("reviewed") or 0),
        _has_identity_value(identity),
    ]
    if include_timestamp:
        values.insert(0, record.get("timestamp") or datetime.utcnow().strftime("%Y-%m-%d %H:%M:%S"))
    return tuple(values)


def _db_size_bytes() -> int:
    if not _DB_PATH:
        return 0
    total = 0
    for suffix in ("", "-wal", "-shm", "-journal"):
        path = f"{_DB_PATH}{suffix}"
        with contextlib.suppress(OSError):
            total += os.path.getsize(path)
    return total


def is_db_size_over_limit() -> bool:
    try:
        limit = int(get_setting("db_size_limit_bytes", 0) or 0)
    except Exception:
        limit = 0
    return limit > 0 and _db_size_bytes() >= limit


def can_persist_events() -> bool:
    return not is_db_size_over_limit()


def add_detection_log(camera_id, identity=None, face_confidence=0.0, detections=None, rules_triggered=None, alarm_level=0, snapshot_path=""):
    if is_db_size_over_limit():
        logging.getLogger(__name__).warning("Skipping detection log: database size limit reached")
        return None
    values = _prepare_detection_log_values(
        {
            "camera_id": camera_id,
            "identity": identity,
            "face_confidence": face_confidence,
            "detections": detections,
            "rules_triggered": rules_triggered,
            "alarm_level": alarm_level,
            "snapshot_path": snapshot_path,
        }
    )
    cur = _write_execute(
        "INSERT INTO detection_logs "
        "(camera_id, zone_id, identity, face_confidence, detections, gender_norm, rules_triggered, alarm_level, snapshot_path, reviewed, has_identity) "
        "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
        values,
    )
    return cur.lastrowid


def seed_detection_logs(rows, *, ignore_size_limit: bool = False) -> int:
    if not rows:
        return 0
    if not ignore_size_limit and is_db_size_over_limit():
        logging.getLogger(__name__).warning("Skipping detection log seed: database size limit reached")
        return 0
    prepared = [_prepare_detection_log_values(dict(row), include_timestamp=True) for row in rows]

    def _op(conn):
        conn.executemany(
            "INSERT INTO detection_logs "
            "(timestamp, camera_id, zone_id, identity, face_confidence, detections, gender_norm, rules_triggered, alarm_level, snapshot_path, reviewed, has_identity) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            prepared,
        )
        conn.commit()
        return len(prepared)

    return _write_call(_op)


def get_detection_logs(
    camera_id=None,
    date_from=None,
    date_to=None,
    identity=None,
    rule_name=None,
    alarm_level=None,
    reviewed=None,
    limit=500,
    offset=0,
):
    q = """SELECT dl.*, c.name as camera_name
           FROM detection_logs dl
           LEFT JOIN cameras c ON dl.camera_id=c.id
           WHERE 1=1"""
    params = []
    if camera_id is not None:
        q += " AND dl.camera_id=?"
        params.append(camera_id)
    if date_from:
        q += " AND dl.timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND dl.timestamp<=?"
        params.append(date_to)
    if identity:
        q += " AND (dl.identity LIKE ? OR dl.detections LIKE ?)"
        like = f"%{identity}%"
        params.append(like)
        params.append(like)
    if rule_name:
        q += " AND dl.rules_triggered LIKE ?"
        params.append(f"%{rule_name}%")
    if alarm_level is not None:
        q += " AND dl.alarm_level>=?"
        params.append(alarm_level)
    if reviewed is not None:
        q += " AND dl.reviewed=?"
        params.append(reviewed)
    q += " ORDER BY dl.timestamp DESC LIMIT ? OFFSET ?"
    params.append(max(1, int(limit or 1)))
    params.append(max(0, int(offset or 0)))
    rows = [dict(r) for r in _conn.execute(q, params).fetchall()]
    for row in rows:
        row["detections"] = json.dumps(_normalize_detections_payload(row.get("detections")))
    return rows


def add_notification_profile(name, ntype, endpoint, auth_token=""):
    cur = _write_execute(
        "INSERT INTO notification_profiles (name, type, endpoint, auth_token) VALUES (?, ?, ?, ?)",
        (name, ntype, endpoint, auth_token),
    )
    return cur.lastrowid


def update_notification_profile(profile_id, **kwargs):
    allowed = {
        "name",
        "type",
        "endpoint",
        "enabled",
        "auth_token",
    }
    sets, vals = _build_update(allowed, kwargs)
    if not sets:
        return
    vals.append(profile_id)
    _write_execute(f"UPDATE notification_profiles SET {sets} WHERE id=?", vals)


def delete_notification_profile(profile_id):
    _write_execute("DELETE FROM notification_profiles WHERE id=?", (profile_id,))


def get_notification_profiles(enabled_only=False, ntype=None):
    q = "SELECT * FROM notification_profiles WHERE 1=1"
    params = []
    if enabled_only:
        q += " AND enabled=1"
    if ntype:
        q += " AND type=?"
        params.append(ntype)
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def get_setting(key, default=None):
    row = _conn.execute("SELECT value, type FROM app_settings WHERE key=?", (key,)).fetchone()
    if not row:
        return default
    val, vtype = row["value"], row["type"]
    if vtype == "int":
        return int(val) if val else default
    if vtype == "float":
        return float(val) if val else default
    if vtype == "bool":
        return val == "1"
    if vtype == "json":
        return json.loads(val) if val else default
    return val


_TRUE_SET = {"1", "true", "yes", "on"}
_FALSE_SET = {"0", "false", "no", "off", ""}


def _as_bool(val, default=False):
    if val is None:
        return default
    if isinstance(val, bool):
        return val
    if isinstance(val, (int, float)):
        return val != 0
    try:
        s = str(val).strip().lower()
    except Exception:
        return default
    if s in _TRUE_SET:
        return True
    if s in _FALSE_SET:
        return False
    return default


def get_bool(key: str, default: bool = False) -> bool:
    try:
        return _as_bool(get_setting(key, None), default)
    except Exception:
        return default


def get_int(key: str, default: int | None = None) -> int | None:
    try:
        val = get_setting(key, None)
        return int(val)
    except Exception:
        return default


def get_float(key: str, default: float | None = None) -> float | None:
    try:
        val = get_setting(key, None)
        return float(val)
    except Exception:
        return default


def set_setting(key, value):
    def _op(conn):
        row = conn.execute("SELECT type FROM app_settings WHERE key=?", (key,)).fetchone()
        if row:
            vtype = (row["type"] or "").strip().lower() or _infer_setting_type(value)
            v = _serialize_setting_value(value, vtype)
            conn.execute(
                "UPDATE app_settings SET value=?, type=CASE WHEN type IS NULL OR type='' THEN ? ELSE type END WHERE key=?",
                (v, vtype, key),
            )
        else:
            vtype = _infer_setting_type(value)
            v = _serialize_setting_value(value, vtype)
            conn.execute(
                "INSERT INTO app_settings (key, value, type) VALUES (?, ?, ?)",
                (key, v, vtype),
            )
        conn.commit()

    _write_call(_op)


def get_all_settings(section=None):
    q = "SELECT * FROM app_settings"
    params = []
    if section:
        q += " WHERE section=?"
        params.append(section)
    q += " ORDER BY section, key"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def add_clip(path: str, source: str, camera_id: int | None, ts: int | None, face_label: str | None, rules, object_types):
    if is_db_size_over_limit():
        logging.getLogger(__name__).warning("Skipping clip metadata: database size limit reached")
        return
    try:
        rules_json = json.dumps(rules or [])
        obj_json = json.dumps(object_types or [])
    except Exception:
        rules_json = "[]"
        obj_json = "[]"

    def _op(conn):
        safe_camera_id = camera_id
        if safe_camera_id is not None:
            try:
                row = conn.execute("SELECT 1 FROM cameras WHERE id=?", (safe_camera_id,)).fetchone()
                if row is None:
                    safe_camera_id = None
            except Exception:
                safe_camera_id = None

        conn.execute(
            """
            INSERT OR REPLACE INTO clips (path, source, camera_id, ts, face_label, rules_triggered, object_types)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            """,
            (path, source, safe_camera_id, ts, face_label, rules_json, obj_json),
        )
        conn.commit()

    _write_call(_op)


def delete_clip(path: str):
    _write_execute("DELETE FROM clips WHERE path=?", (path,))


def get_clips(
    camera_id: int | None = None,
    ts_from: int | None = None,
    ts_to: int | None = None,
    face_label: str | None = None,
    object_type: str | None = None,
    rule_triggered: str | None = None,
    limit: int | None = 500,
):
    q = "SELECT * FROM clips WHERE 1=1"
    params = []
    if camera_id is not None and camera_id != -1:
        q += " AND camera_id=?"
        params.append(camera_id)
    if ts_from is not None:
        q += " AND ts>=?"
        params.append(int(ts_from))
    if ts_to is not None:
        q += " AND ts<=?"
        params.append(int(ts_to))
    if face_label:
        q += " AND face_label LIKE ?"
        params.append(f"%{face_label}%")
    if rule_triggered:
        q += " AND rules_triggered LIKE ?"
        params.append(f"%{rule_triggered}%")
    if object_type:
        q += " AND object_types LIKE ?"
        params.append(f"%{object_type}%")
    q += " ORDER BY ts DESC"
    if limit is not None:
        q += " LIMIT ?"
        params.append(max(1, int(limit or 500)))
    rows = _conn.execute(q, params).fetchall()
    return [dict(r) for r in rows]


def get_clip_paths(limit: int | None = 1000):
    q = "SELECT path FROM clips ORDER BY ts DESC"
    params = []
    if limit is not None:
        q += " LIMIT ?"
        params.append(max(1, int(limit or 1000)))
    return [r["path"] for r in _conn.execute(q, params).fetchall()]


def get_settings_sections():
    rows = _conn.execute("SELECT DISTINCT section FROM app_settings WHERE section IS NOT NULL ORDER BY section").fetchall()
    return [r["section"] for r in rows]


def export_settings_json():
    settings = get_all_settings()
    return {s["key"]: {"value": s["value"], "type": s["type"], "label": s["label"], "section": s["section"]} for s in settings}


def import_settings_json(data):
    def _op(conn):
        for key, info in data.items():
            conn.execute(
                "INSERT OR REPLACE INTO app_settings (key, value, type, label, section) VALUES (?, ?, ?, ?, ?)",
                (key, info.get("value", ""), info.get("type", "string"), info.get("label", ""), info.get("section", "")),
            )
        conn.commit()

    _write_call(_op)


def vacuum():
    def _op(conn):
        conn.execute("VACUUM")

    _write_call(_op)


def backup(dest_path):
    def _op(conn):
        backup_conn = sqlite3.connect(dest_path)
        try:
            conn.backup(backup_conn)
        finally:
            backup_conn.close()

    _write_call(_op)


def get_detection_stats(date_from=None, date_to=None, camera_id=None, min_alarm_level=None, gender=None):
    q = "SELECT COUNT(*) as total, SUM(CASE WHEN alarm_level>0 THEN 1 ELSE 0 END) as violations FROM detection_logs WHERE 1=1"
    params = []
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if camera_id:
        q += " AND camera_id=?"
        params.append(camera_id)
    if min_alarm_level is not None:
        q += " AND alarm_level>=?"
        params.append(int(min_alarm_level))
    if gender:
        q += " AND gender_norm=?"
        params.append(_normalize_gender_value(gender))
    row = _conn.execute(q, params).fetchone()
    return dict(row)


def get_hourly_violations(
    date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, time_basis=None, gender=None
):
    if time_basis == "Local":
        q = "SELECT strftime('%H', timestamp, 'localtime') as hour, COUNT(*) as count FROM detection_logs WHERE 1=1"
    else:
        q = "SELECT strftime('%H', timestamp) as hour, COUNT(*) as count FROM detection_logs WHERE 1=1"
    params = []
    if min_alarm_level is not None:
        q += " AND alarm_level>=?"
        params.append(int(min_alarm_level))
    else:
        q += " AND alarm_level>0"
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if camera_id:
        q += " AND camera_id=?"
        params.append(camera_id)
    if rule_name:
        q += " AND rules_triggered LIKE ?"
        params.append(f"%{rule_name}%")
    if gender:
        q += " AND gender_norm=?"
        params.append(_normalize_gender_value(gender))
    q += " GROUP BY hour ORDER BY hour"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def get_violations_by_person(
    date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, limit=20, gender=None
):
    q = """SELECT identity,
           COALESCE(MAX(CASE WHEN gender_norm != 'unknown' THEN gender_norm END), 'unknown') as gender,
           COUNT(*) as count
           FROM detection_logs
           WHERE identity IS NOT NULL AND identity != ''"""
    params = []
    if min_alarm_level is not None:
        q += " AND alarm_level>=?"
        params.append(int(min_alarm_level))
    else:
        q += " AND alarm_level>0"
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if camera_id:
        q += " AND camera_id=?"
        params.append(camera_id)
    if rule_name:
        q += " AND rules_triggered LIKE ?"
        params.append(f"%{rule_name}%")
    if gender:
        q += " AND gender_norm=?"
        params.append(_normalize_gender_value(gender))
    q += " GROUP BY identity ORDER BY count DESC LIMIT ?"
    params.append(max(1, int(limit or 20)))
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def get_violations_by_gender(date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, gender=None):
    q = "SELECT gender_norm, COUNT(*) as count FROM detection_logs WHERE 1=1"
    params = []
    if min_alarm_level is not None:
        q += " AND alarm_level>=?"
        params.append(int(min_alarm_level))
    else:
        q += " AND alarm_level>0"
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if camera_id:
        q += " AND camera_id=?"
        params.append(camera_id)
    if rule_name:
        q += " AND rules_triggered LIKE ?"
        params.append(f"%{rule_name}%")
    if gender:
        q += " AND gender_norm=?"
        params.append(_normalize_gender_value(gender))

    q += " GROUP BY gender_norm"
    counts = {"male": 0, "female": 0, "unknown": 0}
    for row in _conn.execute(q, params).fetchall():
        g = _normalize_gender_value(row["gender_norm"])
        counts[g] = counts.get(g, 0) + int(row["count"] or 0)
    return [
        {"gender": "male", "count": counts["male"]},
        {"gender": "female", "count": counts["female"]},
        {"gender": "unknown", "count": counts["unknown"]},
    ]


def get_camera_activity(date_from=None, date_to=None, camera_id=None):
    q = """SELECT c.id as camera_id, c.name as camera_name, COUNT(dl.id) as count
           FROM cameras c
           LEFT JOIN detection_logs dl ON c.id=dl.camera_id"""
    params = []
    conditions = []
    if date_from:
        conditions.append("dl.timestamp>=?")
        params.append(date_from)
    if date_to:
        conditions.append("dl.timestamp<=?")
        params.append(date_to)
    if camera_id:
        conditions.append("c.id=?")
        params.append(camera_id)
    if conditions:
        q += " WHERE " + " AND ".join(conditions)
    q += " GROUP BY c.id ORDER BY count DESC"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def get_compliance_over_time(rule_name=None, date_from=None, date_to=None, camera_id=None, time_basis=None, gender=None):
    if time_basis == "Local":
        date_expr = "DATE(timestamp, 'localtime')"
    else:
        date_expr = "DATE(timestamp)"
    q = f"""SELECT {date_expr} as day,
           COUNT(*) as total,
           SUM(CASE WHEN alarm_level=0 THEN 1 ELSE 0 END) as compliant
           FROM detection_logs WHERE 1=1"""
    params = []
    if rule_name:
        q += " AND rules_triggered LIKE ?"
        params.append(f"%{rule_name}%")
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if camera_id:
        q += " AND camera_id=?"
        params.append(camera_id)
    if gender:
        q += " AND gender_norm=?"
        params.append(_normalize_gender_value(gender))
    q += " GROUP BY day ORDER BY day"
    return [dict(r) for r in _conn.execute(q, params).fetchall()]


def get_identified_count(date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, gender=None):
    q = """SELECT COUNT(DISTINCT identity) as count
           FROM detection_logs
           WHERE has_identity=1"""
    params = []
    if min_alarm_level is not None:
        q += " AND alarm_level>=?"
        params.append(int(min_alarm_level))
    if rule_name:
        q += " AND rules_triggered LIKE ?"
        params.append(f"%{rule_name}%")
    if date_from:
        q += " AND timestamp>=?"
        params.append(date_from)
    if date_to:
        q += " AND timestamp<=?"
        params.append(date_to)
    if camera_id:
        q += " AND camera_id=?"
        params.append(camera_id)
    if gender:
        q += " AND gender_norm=?"
        params.append(_normalize_gender_value(gender))
    row = _conn.execute(q, params).fetchone()
    return dict(row) if row else {"count": 0}


def get_faces():
    return get_known_faces()


def get_face(face_id):
    return get_known_face(face_id)


def add_face(
    name,
    department,
    embedding_bytes,
    photo_path="",
    authorized=1,
    authorized_cameras="[]",
    external_uuid=None,
    address="",
    country="",
    birth_date="",
    phone="",
    email="",
    national_id="",
    embedding_model="",
    gender=None,
):
    return add_known_face(
        name,
        "member",
        department,
        embedding_bytes,
        photo_path,
        authorized_cameras,
        0,
        external_uuid=external_uuid,
        address=address,
        country=country,
        birth_date=birth_date,
        phone=phone,
        email=email,
        national_id=national_id,
        embedding_model=embedding_model,
        gender=gender,
    )


def update_face(face_id, **kwargs):
    return update_known_face(face_id, **kwargs)


def delete_face(face_id):
    return delete_known_face(face_id)


def delete_detection_log(log_id):
    _write_execute("DELETE FROM detection_logs WHERE id=?", (log_id,))


def cleanup_old_logs(cutoff_date):
    cur = _write_execute("DELETE FROM detection_logs WHERE timestamp<?", (cutoff_date,))
    return cur.rowcount


def export_settings():
    return export_settings_json()


def import_settings(data):
    return import_settings_json(data)


def get_db_path():
    return _DB_PATH


def wait_for_writer_idle(timeout_sec: float = 5.0) -> bool:
    deadline = time.time() + max(0.0, float(timeout_sec))
    while time.time() < deadline:
        pending = getattr(_write_queue, "unfinished_tasks", 0)
        if pending <= 0:
            return True
        time.sleep(0.05)
    return getattr(_write_queue, "unfinished_tasks", 0) <= 0


def reset_database():
    schema_path = os.path.join(os.path.dirname(__file__), "schema.sql")

    _PRESERVE = {"app_settings", "accounts"}

    def _op(conn):
        with contextlib.suppress(Exception):
            conn.execute("PRAGMA busy_timeout = 5000")
        conn.execute("PRAGMA foreign_keys = OFF")
        conn.commit()
        tables = conn.execute("SELECT name FROM sqlite_master WHERE type='table' AND name NOT LIKE 'sqlite_%'").fetchall()
        for t in tables:
            if t["name"] in _PRESERVE:
                continue
            last_exc = None
            for _ in range(3):
                try:
                    conn.execute(f"DELETE FROM [{t['name']}]")
                    last_exc = None
                    break
                except Exception as exc:
                    last_exc = exc
                    time.sleep(0.05)
            if last_exc is not None:
                raise last_exc
        conn.commit()
        conn.execute("PRAGMA foreign_keys = ON")
        conn.commit()

        try:
            with open(schema_path) as f:
                conn.executescript(f.read())
        except Exception:
            pass

        try:
            conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
            conn.commit()
        except Exception:
            pass

        try:
            saved_isolation = conn.isolation_level
            conn.isolation_level = None
            conn.execute("VACUUM")
            conn.isolation_level = saved_isolation
        except Exception:
            pass

    _write_call(_op)



    ensure_default_account()
