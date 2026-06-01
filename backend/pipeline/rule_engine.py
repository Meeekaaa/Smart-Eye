import threading
import time

from backend.repository import db
from backend.models.face_model import normalize_gender


def _normalize_attr_value(attr, value):
    if attr == "gender":
        return normalize_gender(value)
    return value


def _normalize_operator(op: str) -> str:
    val = str(op or "").strip().lower()
    aliases = {
        "equals": "eq",
        "not equals": "neq",
        "greater than": "gt",
        "less than": "lt",
        "greater than or equal": "gte",
        "less than or equal": "lte",
    }
    return aliases.get(val, val)


def _should_evaluate_unknown(attr: str, operator: str, expected) -> bool:
    """Allow explicit unknown matching (e.g. identity == unknown)."""
    if str(attr or "").strip().lower() != "identity":
        return False
    op = _normalize_operator(operator)
    if op not in ("eq", "neq"):
        return False
    return str(expected or "").strip().lower() == "unknown"


def _active_objects(state: dict) -> list[dict]:
    objects = state.get("object_bboxes", []) or []
    active = []
    for obj in objects:
        if not isinstance(obj, dict):
            continue
        if obj.get("_coasted") or obj.get("_weak_track_recovery"):
            continue
        if obj.get("_track_confirmed", True) is False:
            continue
        active.append(obj)
    return active


def _object_classes(objects: list[dict]) -> set[str]:
    return {str(o.get("class_name") or o.get("class") or "").lower() for o in objects}


def _rule_action(rule: dict) -> str:
    return str(rule.get("action") or "").strip().lower()


def _rule_logic(rule: dict) -> str:
    logic = str(rule.get("logic") or "AND").strip().upper()
    return logic if logic in ("AND", "OR") else "AND"


def _rule_priority(rule: dict) -> int:
    try:
        return int(rule.get("priority", 0) or 0)
    except (TypeError, ValueError):
        return 0


def _compile_condition(cond):
    attr = cond["attribute"]
    op = _normalize_operator(cond["operator"])
    expected = _normalize_attr_value(attr, cond["value"])
    is_obj_count = attr == "objects"
    is_obj_class = attr == "object" or attr.startswith("object.") or attr.startswith("object:")

    if is_obj_count:
        try:
            exp_num = float(expected)
        except (ValueError, TypeError):
            return (attr, True, None, False)
        if op == "eq":

            def check_fn(objs, _e=exp_num):
                return len(objs) == _e
        elif op == "neq":

            def check_fn(objs, _e=exp_num):
                return len(objs) != _e
        elif op == "gt":

            def check_fn(objs, _e=exp_num):
                return len(objs) > _e
        elif op == "lt":

            def check_fn(objs, _e=exp_num):
                return len(objs) < _e
        elif op == "gte":

            def check_fn(objs, _e=exp_num):
                return len(objs) >= _e
        elif op == "lte":

            def check_fn(objs, _e=exp_num):
                return len(objs) <= _e
        else:
            check_fn = None
        return (attr, True, check_fn, False)

    if is_obj_class:
        _es = str(expected).strip().lower()
        if op == "eq":

            def check_fn(objs, _e=_es):
                return _e in _object_classes(objs)
        elif op == "neq":

            def check_fn(objs, _e=_es):
                return _e not in _object_classes(objs)
        elif op == "contains":

            def check_fn(objs, _e=_es):
                return any(_e in cls for cls in _object_classes(objs))
        else:
            check_fn = None
        return (attr, True, check_fn, False)

    try:
        exp_num = float(expected)
        exp_has_num = True
    except (ValueError, TypeError):
        exp_num = None
        exp_has_num = False
    exp_str = str(expected).lower()
    exp_bool = exp_str in ("true", "1", "yes")

    def check_val(actual, _op=op, _en=exp_num, _eh=exp_has_num, _es=exp_str, _eb=exp_bool):
        if isinstance(actual, bool):
            if _op == "eq":
                return actual == _eb
            if _op == "neq":
                return actual != _eb
            return False
        if isinstance(actual, (int, float)):
            if not _eh:
                return False
            if _op == "eq":
                return actual == _en
            if _op == "neq":
                return actual != _en
            if _op == "gt":
                return actual > _en
            if _op == "lt":
                return actual < _en
            if _op == "gte":
                return actual >= _en
            if _op == "lte":
                return actual <= _en
            return False
        a = str(actual).lower()
        if _op == "eq":
            return a == _es
        if _op == "neq":
            return a != _es
        if _op == "contains":
            return _es in a
        return False

    allow_unknown_eval = _should_evaluate_unknown(attr, op, expected)
    return (attr, False, check_val, allow_unknown_eval)


class RuleEngine:
    def __init__(self):
        self._rules_cache = {}
        self._conditions_cache = {}
        self._compiled_cache = {}
        self._rules_ttl = 1.0
        self._conditions_ttl = 1.0
        self._lock = threading.Lock()

    def invalidate(self):
        with self._lock:
            self._rules_cache.clear()
            self._conditions_cache.clear()
            self._compiled_cache.clear()

    def _get_rules_cached(self, enabled_only=True, camera_id=None):
        key = (enabled_only, camera_id)
        now = time.time()
        with self._lock:
            entry = self._rules_cache.get(key)
            if entry and (now - entry[0] < self._rules_ttl):
                return entry[1]
        try:
            data = db.get_rules(enabled_only=enabled_only, camera_id=camera_id)
        except Exception:
            data = []
        with self._lock:
            self._rules_cache[key] = (now, data)
        return data

    def _get_rule_conditions_cached(self, rule_id):
        now = time.time()
        with self._lock:
            entry = self._conditions_cache.get(rule_id)
            if entry and (now - entry[0] < self._conditions_ttl):
                return entry[1]
        try:
            data = db.get_rule_conditions(rule_id)
        except Exception:
            data = []
        with self._lock:
            self._conditions_cache[rule_id] = (now, data)
        return data

    def _get_compiled_conditions_cached(self, rule_id):
        now = time.time()
        with self._lock:
            entry = self._compiled_cache.get(rule_id)
            if entry and (now - entry[0] < self._conditions_ttl):
                return entry[1]
        raw = self._get_rule_conditions_cached(rule_id)
        compiled = [_compile_condition(c) for c in raw]
        with self._lock:
            self._compiled_cache[rule_id] = (now, compiled)
        return compiled

    def _conditions_pass(self, compiled, state):
        objs = _active_objects(state)
        detections = state.get("detections", {})
        results = []
        for item in compiled:
            if len(item) == 4:
                attr, is_obj, check_fn, allow_unknown_eval = item
            else:
                attr, is_obj, check_fn = item
                allow_unknown_eval = False
            if check_fn is None:
                results.append(None)
                continue
            if is_obj:
                try:
                    results.append(check_fn(objs))
                except Exception:
                    results.append(None)
            else:
                actual = _normalize_attr_value(attr, detections.get(attr))
                if (actual is None or actual == "unknown") and not allow_unknown_eval:
                    results.append(None)
                    continue
                if actual is None:
                    actual = "unknown"
                try:
                    results.append(check_fn(actual))
                except Exception:
                    results.append(None)
        valid_results = [r for r in results if r is not None]
        if not valid_results:
            return False
        has_unknown = any(r is None for r in results)
        return results, valid_results, has_unknown

    def evaluate_rules(self, state, camera_id=None):
        rules = self._get_rules_cached(enabled_only=True, camera_id=camera_id)
        triggered = []
        suppress_priority = None
        sorted_rules = sorted(
            rules,
            key=lambda r: (_rule_priority(r), 1 if _rule_action(r) == "suppress" else 0, -int(r.get("id", 0) or 0)),
            reverse=True,
        )
        for rule in sorted_rules:
            compiled = self._get_compiled_conditions_cached(rule["id"])
            if not compiled:
                continue
            match_result = self._conditions_pass(compiled, state)
            if not match_result:
                continue
            results, valid_results, has_unknown = match_result
            logic = _rule_logic(rule)
            if logic == "AND":
                # Fail closed for AND rules when any condition is unknown.
                passed = (not has_unknown) and all(valid_results)
            else:
                passed = any(valid_results)
            if not passed:
                continue
            priority = _rule_priority(rule)
            if _rule_action(rule) == "suppress":
                suppress_priority = priority if suppress_priority is None else max(suppress_priority, priority)
                continue
            if suppress_priority is not None and priority <= suppress_priority:
                continue
            triggered.append(rule)
        return triggered


def _evaluate_condition(actual, operator, expected):
    operator = _normalize_operator(operator)
    if isinstance(actual, bool):
        expected_bool = str(expected).lower() in ("true", "1", "yes")
        if operator == "eq":
            return actual == expected_bool
        if operator == "neq":
            return actual != expected_bool
        return False
    if isinstance(actual, (int, float)):
        try:
            expected_num = float(expected)
        except (ValueError, TypeError):
            return False
        if operator == "eq":
            return actual == expected_num
        if operator == "neq":
            return actual != expected_num
        if operator == "gt":
            return actual > expected_num
        if operator == "lt":
            return actual < expected_num
        if operator == "gte":
            return actual >= expected_num
        if operator == "lte":
            return actual <= expected_num
        return False
    actual_str = str(actual).lower()
    expected_str = str(expected).lower()
    if operator == "eq":
        return actual_str == expected_str
    if operator == "neq":
        return actual_str != expected_str
    if operator == "contains":
        return expected_str in actual_str
    return False


def _evaluate_object_condition(objects, operator, expected):
    operator = _normalize_operator(operator)
    exp_str = str(expected).strip().lower()
    classes = _object_classes(objects)
    if operator == "eq":
        return exp_str in classes
    if operator == "neq":
        return exp_str not in classes
    if operator == "contains":
        return any(exp_str in cls for cls in classes)
    return False


def _evaluate_object_count_condition(objects, operator, expected):
    operator = _normalize_operator(operator)
    try:
        exp_num = float(expected)
    except (TypeError, ValueError):
        return False
    cnt = len(objects)
    if operator == "eq":
        return cnt == exp_num
    if operator == "neq":
        return cnt != exp_num
    if operator == "gt":
        return cnt > exp_num
    if operator == "lt":
        return cnt < exp_num
    if operator == "gte":
        return cnt >= exp_num
    if operator == "lte":
        return cnt <= exp_num
    return False


def simulate_rule(rule_id, state):
    rule = db.get_rule(rule_id)
    if not rule:
        return False, "Rule not found"
    conditions = db.get_rule_conditions(rule_id)
    results = []
    details = []
    for cond in conditions:
        attr = cond["attribute"]
        if attr == "objects":
            objs = _active_objects(state)
            match = _evaluate_object_count_condition(objs, cond["operator"], cond["value"])
            results.append(match)
            details.append(f"{attr} {cond['operator']} {cond['value']} => {match} (objects: {len(objs)})")
            continue
        if attr == "object" or attr.startswith("object.") or attr.startswith("object:"):
            objs = _active_objects(state)
            match = _evaluate_object_condition(objs, cond["operator"], cond["value"])
            results.append(match)
            details.append(f"{attr} {cond['operator']} {cond['value']} => {match} (active objects: {len(objs)})")
            continue
        actual = _normalize_attr_value(attr, state.get("detections", {}).get(attr))
        expected = _normalize_attr_value(attr, cond["value"])
        if (actual is None or actual == "unknown") and not _should_evaluate_unknown(attr, cond["operator"], expected):
            results.append(None)
            details.append(f"{attr}: skipped (unknown)")
            continue
        if actual is None:
            actual = "unknown"
        match = _evaluate_condition(actual, cond["operator"], expected)
        results.append(match)
        details.append(f"{attr} {cond['operator']} {cond['value']} => {match} (actual: {actual})")
    valid = [r for r in results if r is not None]
    if not valid:
        return False, "All conditions skipped"
    logic = _rule_logic(rule)
    has_unknown = any(r is None for r in results)
    if logic == "AND":
        passed = (not has_unknown) and all(valid)
    else:
        passed = any(valid)
    return passed, details


_engine = RuleEngine()


def evaluate_rules(state, camera_id=None):
    return _engine.evaluate_rules(state, camera_id=camera_id)


def invalidate_rule_cache():
    _engine.invalidate()
