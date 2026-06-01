from __future__ import annotations

import re

INTERNAL_EMAIL_DOMAINS = {"smarteye.local"}
ALLOWED_EMAIL_DOMAINS = {
    "gmail.com",
    "yahoo.com",
    "ymail.com",
    "outlook.com",
    "hotmail.com",
    "live.com",
    "msn.com",
    "icloud.com",
    "me.com",
    "mac.com",
    "aol.com",
    "mail.com",
    "proton.me",
    "protonmail.com",
    "zoho.com",
    "yandex.com",
}
_EMAIL_RE = re.compile(r"^[a-zA-Z0-9._%+\-]+@([a-zA-Z0-9\-]+\.)+[a-zA-Z]{2,}$")


def normalize_email_value(email: str) -> str:
    return (email or "").strip().lower()


def get_email_validation_error(email: str, *, allow_internal: bool = True) -> str | None:
    normalized = normalize_email_value(email)
    if not normalized:
        return "Email is required."
    if not _EMAIL_RE.fullmatch(normalized):
        return "Enter a valid email address."

    domain = normalized.partition("@")[2]
    if allow_internal and domain in INTERNAL_EMAIL_DOMAINS:
        return None
    if domain not in ALLOWED_EMAIL_DOMAINS:
        return "Use a supported email provider like gmail.com, yahoo.com, or outlook.com."
    return None
