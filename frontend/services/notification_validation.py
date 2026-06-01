from __future__ import annotations

from urllib.parse import urlparse

from utils.auth_validation import get_email_validation_error


def validate_notification_target(profile_type: str, target: str) -> str:
    ptype = str(profile_type or "").strip().lower()
    value = str(target or "").strip()
    if not value:
        return "Target is required."
    if ptype == "email":
        return get_email_validation_error(value, allow_internal=False) or ""
    if ptype == "webhook":
        parsed = urlparse(value)
        if parsed.scheme not in {"http", "https"} or not parsed.netloc:
            return "Webhook target must be a valid HTTP or HTTPS URL."
        return ""
    return "Profile type must be email or webhook."
