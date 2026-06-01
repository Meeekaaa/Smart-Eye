from datetime import date, datetime, timedelta

from backend.repository import db


_DUMMY_ANALYTICS_SETTING = "debug_dummy_analytics_enabled"
_GENDER_TOTALS = {
    None: (1842, 312),
    "male": (970, 155),
    "female": (726, 113),
    "unknown": (146, 44),
}
_HOURLY_PROFILE = [1, 0, 0, 0, 0, 1, 2, 4, 7, 10, 12, 14, 13, 11, 10, 9, 8, 12, 15, 14, 9, 6, 4, 2]
_TOP_VIOLATORS = [
    {"identity": "Ava Carter", "gender": "female", "count": 37},
    {"identity": "Liam Brooks", "gender": "male", "count": 34},
    {"identity": "Noah Patel", "gender": "male", "count": 31},
    {"identity": "Mia Rivera", "gender": "female", "count": 28},
    {"identity": "Sofia Reed", "gender": "female", "count": 22},
    {"identity": "Ethan Park", "gender": "male", "count": 21},
    {"identity": "Chris Dunn", "gender": "unknown", "count": 18},
    {"identity": "Olivia Hart", "gender": "female", "count": 17},
    {"identity": "Lucas Gray", "gender": "male", "count": 16},
    {"identity": "Jordan Quinn", "gender": "unknown", "count": 12},
]


def _normalize_gender(gender):
    if gender is None:
        return None
    normalized = str(gender).strip().lower()
    if normalized in {"male", "female", "unknown"}:
        return normalized
    return None


def _parse_date(value):
    if not value:
        return None
    text = str(value).strip()
    candidates = [text, text[:19], text[:10]]
    for candidate in candidates:
        if not candidate:
            continue
        try:
            return datetime.fromisoformat(candidate).date()
        except Exception:
            pass
        try:
            return datetime.strptime(candidate, "%Y-%m-%d %H:%M:%S").date()
        except Exception:
            pass
        try:
            return datetime.strptime(candidate, "%Y-%m-%d").date()
        except Exception:
            pass
    return None


def _build_dummy_days(date_from=None, date_to=None, max_days=14):
    end_day = _parse_date(date_to) or date.today()
    start_day = _parse_date(date_from) or (end_day - timedelta(days=max_days - 1))
    if start_day > end_day:
        start_day, end_day = end_day, start_day
    span = (end_day - start_day).days + 1
    if span <= 0:
        start_day = end_day - timedelta(days=max_days - 1)
    elif span > max_days:
        start_day = end_day - timedelta(days=max_days - 1)
    days = []
    cursor = start_day
    while cursor <= end_day:
        days.append(cursor.strftime("%Y-%m-%d"))
        cursor += timedelta(days=1)
    return days


def _alarm_factor(min_alarm_level):
    if min_alarm_level is None:
        return 1.0
    try:
        level = int(min_alarm_level)
    except Exception:
        level = 1
    if level >= 3:
        return 0.22
    if level == 2:
        return 0.44
    return 1.0


def is_dummy_analytics_enabled():
    try:
        return db.get_bool("debug_mode_enabled", False) and db.get_bool(_DUMMY_ANALYTICS_SETTING, False)
    except Exception:
        return False


def _dummy_summary(min_alarm_level=None, gender=None):
    gender_key = _normalize_gender(gender)
    total, violations = _GENDER_TOTALS.get(gender_key, _GENDER_TOTALS[None])
    if min_alarm_level is not None:
        try:
            level = int(min_alarm_level)
        except Exception:
            level = 1
        if level <= 1:
            total = violations
        elif level == 2:
            total = max(1, int(round(violations * 0.42)))
        else:
            total = max(1, int(round(violations * 0.14)))
        violations = total
    compliant = max(0, total - violations)
    rate = (compliant / total * 100) if total > 0 else 100.0
    return {
        "total_detections": total,
        "violations": violations,
        "compliant": compliant,
        "compliance_rate": round(rate, 1),
    }


def _dummy_compliance_trend(date_from=None, date_to=None, camera_id=None, gender=None):
    gender_key = _normalize_gender(gender)
    gender_offsets = {None: 0.0, "male": -1.2, "female": 1.1, "unknown": -4.5}
    camera_offset = 0.0
    if camera_id is not None:
        try:
            camera_offset = (int(camera_id) % 3 - 1) * 0.8
        except Exception:
            camera_offset = 0.0
    trend = []
    for idx, day in enumerate(_build_dummy_days(date_from, date_to, max_days=14)):
        total = 90 + ((idx * 17) % 55)
        rate = 81.5 + idx * 0.45 + (1.1 if idx % 5 == 0 else -0.7 if idx % 4 == 0 else 0.0)
        rate += gender_offsets.get(gender_key, 0.0) + camera_offset
        rate = max(60.0, min(98.0, rate))
        compliant = int(round(total * rate / 100.0))
        trend.append(
            {
                "date": day,
                "total": total,
                "compliant": compliant,
                "rate": round(rate, 1),
            }
        )
    return trend


def _dummy_hourly_violations(min_alarm_level=None, camera_id=None, gender=None):
    factor = 1.0
    gender_key = _normalize_gender(gender)
    if gender_key == "male":
        factor *= 0.95
    elif gender_key == "female":
        factor *= 0.8
    elif gender_key == "unknown":
        factor *= 0.45
    factor *= _alarm_factor(min_alarm_level)
    shift = 0
    if camera_id is not None:
        try:
            shift = int(camera_id) % 24
        except Exception:
            shift = 0
    profile = _HOURLY_PROFILE[shift:] + _HOURLY_PROFILE[:shift] if shift else _HOURLY_PROFILE
    return [{"hour": str(hour).zfill(2), "count": max(0, int(round(base * factor)))} for hour, base in enumerate(profile)]


def _dummy_person_violations(limit=20, min_alarm_level=None, gender=None, camera_id=None, rule_name=None):
    factor = _alarm_factor(min_alarm_level)
    if rule_name:
        factor *= 0.86
    if camera_id is not None:
        try:
            factor *= 0.9 + (int(camera_id) % 3) * 0.03
        except Exception:
            pass
    gender_key = _normalize_gender(gender)
    rows = []
    for person in _TOP_VIOLATORS:
        if gender_key and person["gender"] != gender_key:
            continue
        count = max(1, int(round(person["count"] * factor)))
        rows.append(
            {
                "identity": person["identity"],
                "gender": person["gender"],
                "count": count,
            }
        )
    rows.sort(key=lambda item: item["count"], reverse=True)
    return rows[: max(1, int(limit or 20))]


def _dummy_camera_activity(camera_id=None):
    cameras = db.get_cameras()
    rows = []
    profile = [316, 287, 242, 198, 167, 143]
    if cameras:
        for idx, cam in enumerate(cameras):
            cam_id = cam.get("id")
            if camera_id is not None and cam_id != camera_id:
                continue
            cam_mod = 0
            try:
                cam_mod = (int(cam_id or 0) % 5) * 8
            except Exception:
                cam_mod = 0
            rows.append(
                {
                    "camera_id": cam_id,
                    "camera_name": cam.get("name") or f"Camera {idx + 1}",
                    "count": profile[idx % len(profile)] + cam_mod,
                }
            )
        if rows:
            return rows
    if camera_id is not None:
        return [{"camera_id": camera_id, "camera_name": f"Camera {camera_id}", "count": 224}]
    return [
        {"camera_id": 1, "camera_name": "Front Entrance", "count": 316},
        {"camera_id": 2, "camera_name": "Back Door", "count": 287},
        {"camera_id": 3, "camera_name": "Loading Dock", "count": 242},
    ]


def _dummy_identified_count(gender=None, min_alarm_level=None):
    base = {
        None: 58,
        "male": 34,
        "female": 28,
        "unknown": 9,
    }
    count = base.get(_normalize_gender(gender), base[None])
    if min_alarm_level is not None:
        try:
            level = int(min_alarm_level)
        except Exception:
            level = 1
        if level >= 3:
            count = max(1, int(round(count * 0.35)))
        elif level == 2:
            count = max(1, int(round(count * 0.55)))
        else:
            count = max(1, int(round(count * 0.8)))
    return count


def _dummy_gender_violations(gender=None, min_alarm_level=None):
    counts = {
        "male": 155,
        "female": 113,
        "unknown": 44,
    }
    factor = _alarm_factor(min_alarm_level)
    gender_key = _normalize_gender(gender)
    rows = []
    for key in ("male", "female", "unknown"):
        value = int(round(counts[key] * factor))
        if gender_key and gender_key != key:
            value = 0
        rows.append({"gender": key, "count": value})
    return rows


def get_summary(date_from=None, date_to=None, camera_id=None, min_alarm_level=None, gender=None, rule_name=None):
    if is_dummy_analytics_enabled():
        return _dummy_summary(min_alarm_level=min_alarm_level, gender=gender)
    stats = db.get_detection_stats(
        date_from,
        date_to,
        camera_id,
        min_alarm_level=min_alarm_level,
        gender=gender,
        rule_name=rule_name,
    )
    total = stats.get("total", 0) or 0
    violations = stats.get("violations", 0) or 0
    compliant = total - violations
    rate = (compliant / total * 100) if total > 0 else 100.0
    return {
        "total_detections": total,
        "violations": violations,
        "compliant": compliant,
        "compliance_rate": round(rate, 1),
    }


def get_compliance_trend(rule_name=None, date_from=None, date_to=None, camera_id=None, time_basis=None, gender=None):
    if is_dummy_analytics_enabled():
        return _dummy_compliance_trend(date_from=date_from, date_to=date_to, camera_id=camera_id, gender=gender)
    rows = db.get_compliance_over_time(rule_name, date_from, date_to, camera_id=camera_id, time_basis=time_basis, gender=gender)
    trend = []
    for row in rows:
        total = row.get("total", 0) or 0
        compliant = row.get("compliant", 0) or 0
        rate = (compliant / total * 100) if total > 0 else 100.0
        trend.append(
            {
                "date": row["day"],
                "total": total,
                "compliant": compliant,
                "rate": round(rate, 1),
            }
        )
    return trend


def get_hourly_violation_chart(
    date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, time_basis=None, gender=None
):
    if is_dummy_analytics_enabled():
        return _dummy_hourly_violations(min_alarm_level=min_alarm_level, camera_id=camera_id, gender=gender)
    rows = db.get_hourly_violations(
        date_from,
        date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        time_basis=time_basis,
        gender=gender,
    )
    hours = {str(i).zfill(2): 0 for i in range(24)}
    for row in rows:
        hours[row["hour"]] = row["count"]
    return [{"hour": h, "count": c} for h, c in sorted(hours.items())]


def get_person_violations(date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, limit=20, gender=None):
    if is_dummy_analytics_enabled():
        return _dummy_person_violations(
            limit=limit,
            min_alarm_level=min_alarm_level,
            gender=gender,
            camera_id=camera_id,
            rule_name=rule_name,
        )
    return db.get_violations_by_person(
        date_from,
        date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        limit=limit,
        gender=gender,
    )


def get_camera_activity_data(date_from=None, date_to=None, camera_id=None):
    if is_dummy_analytics_enabled():
        return _dummy_camera_activity(camera_id=camera_id)
    return db.get_camera_activity(date_from, date_to, camera_id=camera_id)


def get_identified_count(date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, gender=None):
    if is_dummy_analytics_enabled():
        return _dummy_identified_count(gender=gender, min_alarm_level=min_alarm_level)
    res = db.get_identified_count(
        date_from,
        date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
    return res.get("count", 0) if isinstance(res, dict) else 0


def get_gender_violations(date_from=None, date_to=None, camera_id=None, rule_name=None, min_alarm_level=None, gender=None):
    if is_dummy_analytics_enabled():
        return _dummy_gender_violations(gender=gender, min_alarm_level=min_alarm_level)
    return db.get_violations_by_gender(
        date_from=date_from,
        date_to=date_to,
        camera_id=camera_id,
        rule_name=rule_name,
        min_alarm_level=min_alarm_level,
        gender=gender,
    )
