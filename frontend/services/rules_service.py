from __future__ import annotations

from backend.repository import db
from backend.pipeline.rule_engine import invalidate_rule_cache, simulate_rule


_ALLOWED_ATTRIBUTES = {"identity", "gender", "object", "objects"}
_ALLOWED_RULE_ACTIONS = {"alarm", "suppress", "log_only"}
_ALLOWED_LOGICS = {"AND", "OR"}
_ALLOWED_OPERATORS_BY_ATTRIBUTE = {
    "identity": {"eq", "neq", "contains"},
    "gender": {"eq", "neq"},
    "object": {"eq", "neq", "contains"},
    "objects": {"eq", "neq", "gt", "lt", "gte", "lte"},
}
_ALLOWED_ALARM_ACTIONS = {"sound", "popup", "email", "webhook"}


class RulesService:
    def get_rules(self) -> list[dict]:
        return db.get_rules()

    def get_rule(self, rule_id: int) -> dict | None:
        return db.get_rule(rule_id)

    def get_rule_conditions(self, rule_id: int) -> list[dict]:
        return db.get_rule_conditions(rule_id)

    def get_alarm_actions(self, rule_id: int) -> list[dict]:
        return db.get_alarm_actions(rule_id)

    def save_rule(
        self,
        rule_id: int | None,
        data: dict,
        conditions: list[dict],
        alarms: list[dict],
    ) -> int:
        action = str(data.get("action", "log_only") or "log_only").strip()
        logic = str(data.get("logic", "AND") or "AND").strip().upper()
        if action not in _ALLOWED_RULE_ACTIONS:
            raise ValueError("Rule action is unsupported.")
        if logic not in _ALLOWED_LOGICS:
            raise ValueError("Rule logic must be AND or OR.")
        self.validate_conditions(conditions)
        self.validate_alarms(alarms, rule_action=action)
        alarm_rows = alarms if action == "alarm" else []

        def _op(conn):
            if rule_id is None:
                cur = conn.execute(
                    "INSERT INTO rules (name, description, logic, action, enabled, priority, camera_id) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    (
                        data["name"],
                        data.get("description", ""),
                        logic,
                        action,
                        1 if data.get("enabled", True) else 0,
                        int(data.get("priority", 0)),
                        data.get("camera_id"),
                    ),
                )
                rid = cur.lastrowid
            else:
                rid = int(rule_id)
                conn.execute(
                    "UPDATE rules SET name=?, description=?, logic=?, action=?, priority=?, camera_id=?, enabled=? "
                    "WHERE id=?",
                    (
                        data["name"],
                        data.get("description", ""),
                        logic,
                        action,
                        int(data.get("priority", 0)),
                        data.get("camera_id"),
                        1 if data.get("enabled", True) else 0,
                        rid,
                    ),
                )
                conn.execute("DELETE FROM rule_conditions WHERE rule_id=?", (rid,))
                conn.execute("DELETE FROM alarm_actions WHERE rule_id=?", (rid,))

            for cond in conditions:
                conn.execute(
                    "INSERT INTO rule_conditions (rule_id, attribute, operator, value) VALUES (?, ?, ?, ?)",
                    (
                        rid,
                        str(cond["attribute"]).strip(),
                        str(cond["operator"]).strip(),
                        str(cond["value"]).strip(),
                    ),
                )
            for alarm in alarm_rows:
                conn.execute(
                    "INSERT INTO alarm_actions "
                    "(rule_id, escalation_level, trigger_after_sec, action_type, action_value, cooldown_sec) "
                    "VALUES (?, ?, ?, ?, ?, ?)",
                    (
                        rid,
                        int(alarm["escalation_level"]),
                        int(alarm["trigger_after_sec"]),
                        str(alarm["action_type"]).strip(),
                        str(alarm.get("action_value") or "").strip(),
                        int(alarm["cooldown_sec"]),
                    ),
                )
            return rid

        rid = db.write_transaction(_op)
        invalidate_rule_cache()
        return int(rid)

    def validate_conditions(self, conditions: list[dict]) -> None:
        if not conditions:
            raise ValueError("Rule needs at least one condition.")
        for idx, cond in enumerate(conditions, 1):
            attr = str(cond.get("attribute") or "").strip()
            op = str(cond.get("operator") or "").strip()
            value = str(cond.get("value") or "").strip()
            if attr not in _ALLOWED_ATTRIBUTES:
                raise ValueError(f"Condition {idx} has an unsupported field.")
            allowed_ops = _ALLOWED_OPERATORS_BY_ATTRIBUTE.get(attr, set())
            if op not in allowed_ops:
                raise ValueError(f"Condition {idx} uses an operator that does not apply to {attr}.")
            if not value:
                raise ValueError(f"Condition {idx} needs a value.")
            if attr == "objects":
                try:
                    float(value)
                except (TypeError, ValueError):
                    raise ValueError(f"Condition {idx} needs a numeric object count.") from None

    def validate_alarms(self, alarms: list[dict], rule_action: str = "alarm") -> None:
        action = str(rule_action or "alarm").strip()
        if action != "alarm":
            return
        if not alarms:
            raise ValueError("Alarm rules need at least one escalation action.")
        for idx, alarm in enumerate(alarms, 1):
            action_type = str(alarm.get("action_type") or "").strip()
            if action_type not in _ALLOWED_ALARM_ACTIONS:
                raise ValueError(f"Alarm action {idx} has an unsupported action.")
            if action_type in {"email", "webhook"} and not str(alarm.get("action_value") or "").strip():
                raise ValueError(f"Alarm action {idx} needs a notification profile.")
            for key, label in (
                ("escalation_level", "level"),
                ("trigger_after_sec", "delay"),
                ("cooldown_sec", "cooldown"),
            ):
                try:
                    value = int(alarm.get(key, 0))
                except (TypeError, ValueError):
                    raise ValueError(f"Alarm action {idx} has an invalid {label}.") from None
                if key == "escalation_level" and not 1 <= value <= 5:
                    raise ValueError(f"Alarm action {idx} level must be between 1 and 5.")
                if key != "escalation_level" and value < 0:
                    raise ValueError(f"Alarm action {idx} {label} cannot be negative.")

    def set_rule_enabled(self, rule_id: int, enabled: bool) -> None:
        db.update_rule(rule_id, enabled=1 if enabled else 0)

    def delete_rule(self, rule_id: int) -> None:
        db.delete_rule(rule_id)

    def simulate_rule(self, rule_id: int, payload: dict) -> tuple[bool, list | str]:
        return simulate_rule(rule_id, payload)
