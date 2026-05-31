from __future__ import annotations

from backend.repository import db
from backend.pipeline.rule_engine import simulate_rule


_ALLOWED_ATTRIBUTES = {"identity", "gender", "object", "objects"}
_ALLOWED_OPERATORS = {"eq", "neq", "contains", "gt", "lt", "gte", "lte"}
_ALLOWED_ALARM_ACTIONS = {"sound", "email", "webhook"}


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
        self.validate_conditions(conditions)
        self.validate_alarms(alarms)
        if rule_id is None:
            rid = db.add_rule(
                data["name"],
                data.get("description", ""),
                data.get("logic", "AND"),
                data.get("action", "log_only"),
                int(data.get("priority", 0)),
                data.get("camera_id"),
            )
            db.update_rule(rid, enabled=1 if data.get("enabled", True) else 0)
        else:
            rid = rule_id
            db.update_rule(
                rid,
                name=data["name"],
                description=data.get("description", ""),
                logic=data.get("logic", "AND"),
                action=data.get("action", "log_only"),
                priority=int(data.get("priority", 0)),
                camera_id=data.get("camera_id"),
                enabled=1 if data.get("enabled", True) else 0,
            )
            db.delete_rule_conditions(rid)
            db.delete_alarm_actions(rid)

        for cond in conditions:
            db.add_rule_condition(rid, cond["attribute"], cond["operator"], cond["value"])
        for alarm in alarms:
            db.add_alarm_action(
                rid,
                alarm["escalation_level"],
                alarm["trigger_after_sec"],
                alarm["action_type"],
                alarm["action_value"],
                alarm["cooldown_sec"],
            )
        return rid

    def validate_conditions(self, conditions: list[dict]) -> None:
        for idx, cond in enumerate(conditions, 1):
            attr = str(cond.get("attribute") or "").strip()
            op = str(cond.get("operator") or "").strip()
            value = str(cond.get("value") or "").strip()
            if attr not in _ALLOWED_ATTRIBUTES:
                raise ValueError(f"Condition {idx} has an unsupported field.")
            if op not in _ALLOWED_OPERATORS:
                raise ValueError(f"Condition {idx} has an unsupported operator.")
            if not value:
                raise ValueError(f"Condition {idx} needs a value.")

    def validate_alarms(self, alarms: list[dict]) -> None:
        for idx, alarm in enumerate(alarms, 1):
            action_type = str(alarm.get("action_type") or "").strip()
            if action_type not in _ALLOWED_ALARM_ACTIONS:
                raise ValueError(f"Alarm action {idx} has an unsupported action.")
            if action_type in {"email", "webhook"} and not str(alarm.get("action_value") or "").strip():
                raise ValueError(f"Alarm action {idx} needs a notification profile.")

    def set_rule_enabled(self, rule_id: int, enabled: bool) -> None:
        db.update_rule(rule_id, enabled=1 if enabled else 0)

    def delete_rule(self, rule_id: int) -> None:
        db.delete_rule(rule_id)

    def simulate_rule(self, rule_id: int, payload: dict) -> tuple[bool, list | str]:
        return simulate_rule(rule_id, payload)
