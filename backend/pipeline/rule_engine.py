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


def _compile_condition(cond):
    attr = cond["attribute"]
    op = _normalize_operator(cond["operator"])
    expected = _normalize_attr_value(attr, cond["value"])
    is_obj = attr in ("object", "objects") or attr.startswith("object.") or attr.startswith("object:")

    if is_obj:
        try:
            exp_num = float(expected)
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
        except (ValueError, TypeError):
            _es = str(expected).lower()
            if op in ("eq", "contains"):

                def check_fn(objs, _e=_es):
                    return _e in {str(o.get("class_name") or o.get("class") or "").lower() for o in objs}
            elif op == "neq":

                def check_fn(objs, _e=_es):
                    return _e not in {str(o.get("class_name") or o.get("class") or "").lower() for o in objs}
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

    def evaluate_rules(self, state, camera_id=None):
        rules = self._get_rules_cached(enabled_only=True, camera_id=camera_id)
        triggered = []
        suppressed = set()
        sorted_rules = sorted(rules, key=lambda r: r.get("priority", 0), reverse=True)
        objs = state.get("object_bboxes", []) or []
        detections = state.get("detections", {})
        for rule in sorted_rules:
            compiled = self._get_compiled_conditions_cached(rule["id"])
            if not compiled:
                continue
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
                continue
            logic = rule.get("logic", "AND")
            has_unknown = any(r is None for r in results)
            if logic == "AND":
                # Fail closed for AND rules when any condition is unknown.
                passed = (not has_unknown) and all(valid_results)
            else:
                passed = any(valid_results)
            if passed:
                if rule["action"] == "suppress":
                    suppressed.add(int(rule["id"]))
                else:
                    triggered.append(rule)
        final = [r for r in triggered if int(r["id"]) not in suppressed]
        return final


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
    try:
        exp_num = float(expected)
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
    except Exception:
        exp_str = str(expected).lower()
        classes = {str(o.get("class_name") or o.get("class") or "").lower() for o in objects}
        if operator in ("eq", "contains"):
            return exp_str in classes
        if operator == "neq":
            return exp_str not in classes
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
        if attr in ("object", "objects") or attr.startswith("object.") or attr.startswith("object:"):
            objs = state.get("object_bboxes", []) or []
            match = _evaluate_object_condition(objs, cond["operator"], cond["value"])
            results.append(match)
            details.append(f"{attr} {cond['operator']} {cond['value']} => {match} (objects: {len(objs)})")
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
    logic = rule.get("logic", "AND")
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
