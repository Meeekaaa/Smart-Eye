from __future__ import annotations

from array import array
from datetime import datetime
import uuid

from backend.repository import db


_DUMMY_SOURCE_PREFIX = "debug://dummy/"
_DUMMY_CAMERA_LOCATIONS = [
    "Front Entrance",
    "Back Door",
    "Warehouse Aisle",
    "Packing Bay",
    "Loading Dock",
    "Safety Corridor",
]
_DUMMY_FACE_IDENTITIES = [
    ("Alice Chen", "Safety"),
    ("Bob Martinez", "Operations"),
    ("Carol King", "Warehouse"),
    ("David Lee", "Logistics"),
    ("Ethan Park", "Security"),
    ("Mia Rivera", "Quality"),
]
_DUMMY_FACE_IMAGE = "frontend/assets/icons/person.png"
_DEBUG_NOTIFICATION_PROFILES = [
    {
        "name": "[DEBUG] Safety Email",
        "type": "email",
        "endpoint": "debug-alerts@smarteye.local",
        "auth_token": "",
    },
    {
        "name": "[DEBUG] Safety Webhook",
        "type": "webhook",
        "endpoint": "http://localhost:9000/smarteye/debug-webhook",
        "auth_token": "debug-token",
    },
]
_DEBUG_RULES = [
    {
        "slug": "ppe-hardhat",
        "name": "PPE Hardhat Violation",
        "description": "Debug auto rule: trigger when NO-Hardhat is detected.",
        "logic": "AND",
        "action": "alarm",
        "priority": 95,
        "conditions": [
            {"attribute": "object", "operator": "eq", "value": "NO-Hardhat"},
        ],
        "alarms": [
            {"escalation_level": 2, "trigger_after_sec": 0, "action_type": "sound", "action_value": "", "cooldown_sec": 8},
        ],
    },
    {
        "slug": "ppe-vest",
        "name": "PPE Vest Violation",
        "description": "Debug auto rule: trigger when NO-Safety Vest is detected.",
        "logic": "AND",
        "action": "alarm",
        "priority": 94,
        "conditions": [
            {"attribute": "object", "operator": "eq", "value": "NO-Safety Vest"},
        ],
        "alarms": [
            {"escalation_level": 2, "trigger_after_sec": 0, "action_type": "sound", "action_value": "", "cooldown_sec": 8},
        ],
    },
    {
        "slug": "unknown-restricted",
        "name": "Unknown Person Alert",
        "description": "Debug auto rule: trigger when identity is unknown and a person is present.",
        "logic": "AND",
        "action": "alarm",
        "priority": 84,
        "conditions": [
            {"attribute": "identity", "operator": "eq", "value": "unknown"},
            {"attribute": "object", "operator": "eq", "value": "person"},
        ],
        "alarms": [
            {"escalation_level": 1, "trigger_after_sec": 0, "action_type": "sound", "action_value": "", "cooldown_sec": 12},
        ],
    },
    {
        "slug": "crowd-threshold",
        "name": "Crowd Threshold Exceeded",
        "description": "Debug auto rule: trigger when person count is at or above 4.",
        "logic": "AND",
        "action": "alarm",
        "priority": 72,
        "conditions": [
            {"attribute": "person_count", "operator": "gte", "value": "4"},
        ],
        "alarms": [
            {"escalation_level": 2, "trigger_after_sec": 5, "action_type": "sound", "action_value": "", "cooldown_sec": 10},
        ],
    },
]


class DebugService:
    def get_db_path(self) -> str:
        return db.get_db_path()

    def prepare_seed_support(
        self,
        *,
        camera_count: int = 3,
        camera_rows: list[dict] | None = None,
        face_count: int = 6,
    ) -> list[dict]:
        def _op(conn):
            rows = list(camera_rows or [])
            if not rows and camera_count > 0:
                rows = DebugService.create_dummy_cameras(conn, count=camera_count)
            if not rows:
                rows = DebugService.get_camera_info(conn)
            DebugService.ensure_debug_rules(conn, rows)
            DebugService.ensure_debug_faces(conn, count=face_count)
            DebugService.ensure_debug_notification_profiles(conn)
            return rows

        return db.write_transaction(_op)

    @staticmethod
    def create_dummy_cameras(conn, count: int = 3) -> list[dict]:
        created = []
        if count <= 0:
            return created
        tag = datetime.now().strftime("%Y%m%d-%H%M%S")
        for idx in range(count):
            name = f"Debug Dummy Camera {tag}-{idx + 1}"
            source = f"{_DUMMY_SOURCE_PREFIX}{tag}/{idx + 1}"
            location = _DUMMY_CAMERA_LOCATIONS[idx % len(_DUMMY_CAMERA_LOCATIONS)]
            cur = conn.execute(
                "INSERT INTO cameras (name, source, location, enabled) VALUES (?, ?, ?, 1)",
                (name, source, location),
            )
            created.append(
                {
                    "id": int(cur.lastrowid),
                    "name": name,
                    "source": source,
                    "location": location,
                }
            )
        conn.commit()
        return created

    @staticmethod
    def get_camera_info(conn, camera_ids: list[int] | None = None) -> list[dict]:
        if camera_ids:
            placeholders = ",".join("?" for _ in camera_ids)
            rows = conn.execute(
                f"SELECT id, name, source, location FROM cameras WHERE id IN ({placeholders})",
                tuple(camera_ids),
            ).fetchall()
        else:
            rows = conn.execute("SELECT id, name, source, location FROM cameras").fetchall()
        return [
            {
                "id": int(r[0]),
                "name": str(r[1] or ""),
                "source": str(r[2] or ""),
                "location": str(r[3] or ""),
            }
            for r in rows
        ]

    @staticmethod
    def ensure_cameras(conn) -> list[int]:
        rows = conn.execute("SELECT id FROM cameras LIMIT 10").fetchall()
        if not rows:
            created = DebugService.create_dummy_cameras(conn, count=2)
            return [c["id"] for c in created]
        return [int(r[0]) for r in rows]

    @staticmethod
    def ensure_debug_rules(conn, camera_rows: list[dict] | None = None) -> int:
        rows = camera_rows or []
        if not rows:
            src = f"{_DUMMY_SOURCE_PREFIX}%"
            fetched = conn.execute(
                "SELECT id, name FROM cameras WHERE source LIKE ? ORDER BY id DESC LIMIT 24",
                (src,),
            ).fetchall()
            rows = [{"id": int(r[0]), "name": str(r[1] or "")} for r in fetched]

        if not rows:
            return 0

        touched = 0
        for cam in rows:
            cam_id = int(cam.get("id") or 0)
            if cam_id <= 0:
                continue
            cam_name = str(cam.get("name") or f"Camera {cam_id}")
            for spec in _DEBUG_RULES:
                rule_name = f"[DEBUG] {spec['name']} [cam:{cam_id}]"
                rule_desc = f"{spec['description']} Camera: {cam_name}."
                existing = conn.execute(
                    "SELECT id FROM rules WHERE name=? AND camera_id=?",
                    (rule_name, cam_id),
                ).fetchone()
                if existing:
                    rid = int(existing[0])
                    conn.execute(
                        "UPDATE rules SET description=?, logic=?, action=?, enabled=1, priority=? WHERE id=?",
                        (rule_desc, spec["logic"], spec["action"], int(spec["priority"]), rid),
                    )
                else:
                    cur = conn.execute(
                        "INSERT INTO rules (name, description, logic, action, enabled, priority, camera_id) VALUES (?, ?, ?, ?, 1, ?, ?)",
                        (rule_name, rule_desc, spec["logic"], spec["action"], int(spec["priority"]), cam_id),
                    )
                    rid = int(cur.lastrowid)

                conn.execute("DELETE FROM rule_conditions WHERE rule_id=?", (rid,))
                conn.execute("DELETE FROM alarm_actions WHERE rule_id=?", (rid,))

                for cond in spec["conditions"]:
                    conn.execute(
                        "INSERT INTO rule_conditions (rule_id, attribute, operator, value) VALUES (?, ?, ?, ?)",
                        (rid, cond["attribute"], cond["operator"], str(cond["value"])),
                    )

                for alarm in spec["alarms"]:
                    conn.execute(
                        "INSERT INTO alarm_actions (rule_id, escalation_level, trigger_after_sec, action_type, action_value, cooldown_sec) VALUES (?, ?, ?, ?, ?, ?)",
                        (
                            rid,
                            int(alarm["escalation_level"]),
                            int(alarm["trigger_after_sec"]),
                            str(alarm["action_type"]),
                            str(alarm.get("action_value", "")),
                            int(alarm.get("cooldown_sec", 10)),
                        ),
                    )
                touched += 1

        conn.commit()
        try:
            from backend.pipeline import rule_engine

            rule_engine.invalidate_rule_cache()
        except Exception:
            pass
        return touched

    @staticmethod
    def ensure_debug_faces(conn, count: int = 6) -> int:
        target = max(1, int(count or 1))
        existing = conn.execute("SELECT id, name FROM known_faces").fetchall()
        existing_by_name = {str(r[1] or ""): int(r[0]) for r in existing}

        changed = 0
        for idx in range(target):
            base_name, department = _DUMMY_FACE_IDENTITIES[idx % len(_DUMMY_FACE_IDENTITIES)]
            name = base_name
            if name in existing_by_name:
                conn.execute(
                    "UPDATE known_faces SET image_path=?, department=? WHERE id=?",
                    (_DUMMY_FACE_IMAGE, department, existing_by_name[name]),
                )
                changed += 1
                continue

            embedding_vals = [((idx + 1) * 0.01) + ((j % 17) * 0.0001) for j in range(512)]
            embedding = array("f", embedding_vals).tobytes()

            conn.execute(
                """
                INSERT INTO known_faces
                (uuid, name, role, department, embedding, image_path, authorized_cameras, liveness_required, embedding_model)
                VALUES (?, ?, ?, ?, ?, ?, ?, 0, ?)
                """,
                (
                    str(uuid.uuid4()),
                    name,
                    "member",
                    department,
                    embedding,
                    _DUMMY_FACE_IMAGE,
                    "[]",
                    "debug-seed",
                ),
            )
            changed += 1

        if changed:
            conn.commit()
        return changed

    @staticmethod
    def ensure_debug_notification_profiles(conn) -> int:
        touched = 0
        for profile in _DEBUG_NOTIFICATION_PROFILES:
            existing = conn.execute(
                "SELECT id FROM notification_profiles WHERE name=? AND type=?",
                (profile["name"], profile["type"]),
            ).fetchone()
            if existing:
                conn.execute(
                    "UPDATE notification_profiles SET endpoint=?, auth_token=?, enabled=1 WHERE id=?",
                    (profile["endpoint"], profile.get("auth_token", ""), int(existing[0])),
                )
            else:
                conn.execute(
                    "INSERT INTO notification_profiles (name, type, endpoint, auth_token, enabled) VALUES (?, ?, ?, ?, 1)",
                    (profile["name"], profile["type"], profile["endpoint"], profile.get("auth_token", "")),
                )
            touched += 1

        if touched:
            conn.commit()
        return touched
