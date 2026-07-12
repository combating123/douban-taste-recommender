from __future__ import annotations

from typing import Any

from .models import MediaItem


MEDIA_ITEM_FIELDS = [
    "title",
    "my_rating",
    "douban_rating",
    "vote_count",
    "year",
    "media_type",
    "genres",
    "countries",
    "languages",
    "directors",
    "casts",
    "tags",
    "url",
    "douban_id",
    "cover",
    "summary",
    "source",
    "raw",
]


def media_item_to_dict(item: MediaItem) -> dict[str, object]:
    return {field: getattr(item, field) for field in MEDIA_ITEM_FIELDS}


def media_item_from_dict(data: dict[str, Any]) -> MediaItem:
    clean = {field: data.get(field) for field in MEDIA_ITEM_FIELDS}
    for text_field in ("title", "media_type", "url", "douban_id", "cover", "summary", "source"):
        clean[text_field] = str(clean.get(text_field) or "").strip()
    for list_field in ("genres", "countries", "languages", "directors", "casts", "tags"):
        value = clean.get(list_field)
        if isinstance(value, list):
            clean[list_field] = [str(part).strip() for part in value if str(part).strip()]
        elif isinstance(value, str) and value.strip():
            clean[list_field] = [value.strip()]
        else:
            clean[list_field] = []
    raw = clean.get("raw")
    clean["raw"] = dict(raw) if isinstance(raw, dict) else {}
    return MediaItem(**clean)


def redact_cookie(value: str) -> str:
    parts = []
    for part in str(value or "").split(";"):
        text = part.strip()
        if not text:
            continue
        if "=" in text:
            name = text.split("=", 1)[0].strip()
            parts.append(f"{name}=<redacted>")
        else:
            parts.append("<redacted>")
    return "; ".join(parts)


def redact_cookie_from_text(value: str, cookie: str) -> str:
    text = str(value or "")
    raw_cookie = str(cookie or "").strip()
    if not raw_cookie:
        return text

    text = text.replace(raw_cookie, redact_cookie(raw_cookie))
    text = text.replace(raw_cookie.replace(" ", ""), redact_cookie(raw_cookie))
    for part in raw_cookie.split(";"):
        piece = part.strip()
        if not piece:
            continue
        if "=" in piece:
            name, secret = piece.split("=", 1)
            name = name.strip()
            secret = secret.strip().strip('"')
            if secret:
                text = text.replace(secret, "<redacted>")
            if name:
                text = text.replace(f"{name}={secret}", f"{name}=<redacted>")
        else:
            text = text.replace(piece, "<redacted>")
    return text
