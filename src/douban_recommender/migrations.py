from __future__ import annotations

import hashlib
import json
import re
import time
from dataclasses import dataclass

from .database import AppDatabase
from .models import recommendation_item_key


SENSITIVE_KEY_PARTS = ("cookie", "api_key", "apikey", "authorization", "subscription", "proxy_url")
PLACEHOLDER_TITLE_RE = re.compile(r"^(?:电影|电视剧|动漫|动画|影视|作品)?候选\s*#?\s*\d+$", re.I)


@dataclass(frozen=True)
class MigrationReport:
    imported: int = 0
    dropped_placeholders: int = 0
    dropped_stale_assets: int = 0
    warnings: tuple[str, ...] = ()
    fingerprint: str = ""
    skipped: bool = False


def _is_sensitive_key(key: object) -> bool:
    normalized = str(key or "").casefold().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def _scrub(value):
    if isinstance(value, dict):
        return {
            str(key): _scrub(item)
            for key, item in value.items()
            if not _is_sensitive_key(key)
        }
    if isinstance(value, list):
        return [_scrub(item) for item in value]
    if isinstance(value, tuple):
        return [_scrub(item) for item in value]
    return value


def _flatten_row(row: dict) -> dict:
    item = row.get("item") if isinstance(row.get("item"), dict) else row
    clean = _scrub(dict(item or {}))
    allowed = {
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
        "people_photos",
        "backdrop",
    }
    return {key: clean.get(key) for key in allowed if key in clean}


def _is_numbered_placeholder(title: str) -> bool:
    compact = re.sub(r"\s+", "", str(title or "").strip())
    return bool(PLACEHOLDER_TITLE_RE.fullmatch(compact))


def _clear_stale_cover(payload: dict) -> bool:
    cover = str(payload.get("cover") or "").strip()
    source = str(payload.get("source") or "").casefold()
    identifier = str(payload.get("douban_id") or "").casefold()
    synthetic = "premium" in source or identifier.startswith("premium-")
    stale_douban = "doubanio.com" in cover or "img.douban.com" in cover
    if synthetic and stale_douban:
        payload["cover"] = ""
        return True
    return False


def _item_key(payload: dict) -> str:
    return recommendation_item_key(payload)


def _library_state(payload: dict) -> str:
    source = str(payload.get("source") or "")
    tags = {str(value) for value in (payload.get("tags") or [])}
    if source.endswith(":wish") or "想看" in tags:
        return "wanted"
    if source.endswith(":collect") or "看过" in tags:
        return "watched"
    return "candidate"


def migrate_legacy_recommendations(rows: list[dict], database: AppDatabase) -> MigrationReport:
    database.initialize()
    normalized_rows = [_flatten_row(row) for row in rows if isinstance(row, dict)]
    fingerprint = hashlib.sha256(
        json.dumps(normalized_rows, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    meta_key = f"legacy_recommendations:{fingerprint}"
    if database.get_meta(meta_key) == "complete":
        return MigrationReport(fingerprint=fingerprint, skipped=True)

    imported = 0
    dropped_placeholders = 0
    dropped_stale_assets = 0
    warnings: list[str] = []
    now = time.time()
    with database.connection() as connection:
        for payload in normalized_rows:
            title = str(payload.get("title") or "").strip()
            if not title:
                warnings.append("dropped legacy row without title")
                continue
            if _is_numbered_placeholder(title):
                dropped_placeholders += 1
                continue
            if _clear_stale_cover(payload):
                dropped_stale_assets += 1
            encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, ?, ?, ?, ?)
                ON CONFLICT(item_key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    state = excluded.state,
                    source = excluded.source,
                    updated_at = excluded.updated_at
                """,
                (
                    _item_key(payload),
                    encoded,
                    _library_state(payload),
                    str(payload.get("source") or "legacy"),
                    now,
                    now,
                ),
            )
            imported += 1
    database.set_meta(meta_key, "complete")
    return MigrationReport(
        imported=imported,
        dropped_placeholders=dropped_placeholders,
        dropped_stale_assets=dropped_stale_assets,
        warnings=tuple(warnings),
        fingerprint=fingerprint,
        skipped=False,
    )
