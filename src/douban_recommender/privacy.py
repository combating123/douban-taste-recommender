from __future__ import annotations

import re
from typing import Any
from urllib.parse import SplitResult, urlsplit, urlunsplit


SENSITIVE_KEY_MARKERS = (
    "auth",
    "authorization",
    "bearer",
    "cookie",
    "token",
    "jwt",
    "apikey",
    "privatekey",
    "password",
    "secret",
    "credential",
    "subscription",
    "session",
    "access",
    "refresh",
)
URL_RE = re.compile(r"https?://[^\s<>'\")\]]+", re.I)
COOKIE_VALUE_RE = re.compile(
    r"(?i)\b(?:bid|ck|dbcl2|cookie|session(?:id)?|sid|token|api[_-]?key|apikey|jwt|password|secret|credential|subscription|access[_-]?token|refresh[_-]?token)\s*=\s*([^\s;,&]+)"
)
BEARER_RE = re.compile(r"(?i)\bbearer\s+[^\s,;]+")
ASSIGNMENT_RE = re.compile(
    r"(?i)\b(?P<name>auth(?:orization)?|token|api[_-]?key|apikey|jwt|private[_-]?key|password|secret|credential|subscription|access[_-]?token|refresh[_-]?token)\b(?P<sep>\s*[:=]\s*)(?P<value>[^\s,;]+)"
)


def is_sensitive_key(key: object) -> bool:
    raw = str(key or "").casefold()
    normalized = re.sub(r"[^a-z0-9]+", "", raw)
    if not normalized:
        return False
    return any(marker in normalized for marker in SENSITIVE_KEY_MARKERS)


def sanitize_source_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").strip()
    if scheme not in {"http", "https"} or not host:
        return ""
    netloc = host.lower()
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port is not None:
        netloc = f"{netloc}:{port}"
    sanitized = SplitResult(
        scheme=scheme,
        netloc=netloc,
        path=parsed.path or "",
        query="",
        fragment="",
    )
    return urlunsplit(sanitized)


def _sanitize_string(value: str) -> str:
    sanitized = str(value or "")
    sanitized = URL_RE.sub(lambda match: sanitize_source_url(match.group(0)), sanitized)
    sanitized = BEARER_RE.sub("Bearer <redacted>", sanitized)
    sanitized = COOKIE_VALUE_RE.sub(lambda match: match.group(0).split("=", 1)[0] + "=<redacted>", sanitized)
    sanitized = ASSIGNMENT_RE.sub(
        lambda match: f"{match.group('name')}{match.group('sep')}<redacted>",
        sanitized,
    )
    return re.sub(r"\s{2,}", " ", sanitized).strip()


def scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {
            str(key): scrub_sensitive(nested)
            for key, nested in value.items()
            if not is_sensitive_key(key)
        }
    if isinstance(value, (list, tuple, set)):
        return [scrub_sensitive(nested) for nested in value]
    if isinstance(value, str):
        return _sanitize_string(value)
    return value
