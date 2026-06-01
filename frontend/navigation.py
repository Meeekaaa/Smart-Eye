NAV_ITEMS = [
    ("MONITOR", None, None),
    ("Dashboard", "dashboard", "frontend/assets/icons/dashboard.png"),
    ("Playback", "playback", "frontend/assets/icons/playback.png"),
    ("Logs", "logs", "frontend/assets/icons/logs.png"),
    ("CONFIGURE", None, None),
    ("Cameras", "detectors", "frontend/assets/icons/cameras.png"),
    ("Rules", "rules", "frontend/assets/icons/rules.png"),
    ("Faces", "faces", "frontend/assets/icons/faces.png"),
    ("Notifications", "notifications", "frontend/assets/icons/notifications.png"),
    ("Models", "models", "frontend/assets/icons/object.png"),
    ("INSIGHTS", None, None),
    ("Analytics", "analytics", "frontend/assets/icons/analytics.png"),
    ("Settings", "settings", "frontend/assets/icons/settings.png"),
]


def nav_keys():
    return [key for _, key, _ in NAV_ITEMS if key]


def nav_label_map():
    return {key: label for label, key, _ in NAV_ITEMS if key}
