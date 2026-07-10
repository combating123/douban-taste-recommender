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


def _json_value(value, fallback):
    try:
        return json.loads(str(value))
    except (TypeError, ValueError, json.JSONDecodeError):
        return fallback


def _collect_legacy_key_mappings(value, mappings: dict[str, str]) -> None:
    if isinstance(value, dict):
        for nested in value.values():
            _collect_legacy_key_mappings(nested, mappings)
        return
    if isinstance(value, (list, tuple)):
        for nested in value:
            _collect_legacy_key_mappings(nested, mappings)
        return
    if isinstance(value, str) and value.startswith("external:"):
        canonical = recommendation_item_key({"douban_id": value.removeprefix("external:")})
        if canonical != value:
            mappings[value] = canonical


def _rewrite_legacy_keys(value, mappings: dict[str, str]):
    if isinstance(value, dict):
        return {str(key): _rewrite_legacy_keys(nested, mappings) for key, nested in value.items()}
    if isinstance(value, list):
        return [_rewrite_legacy_keys(nested, mappings) for nested in value]
    if isinstance(value, tuple):
        return [_rewrite_legacy_keys(nested, mappings) for nested in value]
    if isinstance(value, str):
        return mappings.get(value, value)
    return value


def _encoded_json(value) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":"))


def migrate_recommendation_item_keys(connection) -> int:
    """Canonicalize unsafe legacy external keys in one caller-owned transaction."""
    mappings: dict[str, str] = {}
    for table, column in (
        ("library_items", "item_key"),
        ("feedback_events", "item_key"),
        ("sync_items", "item_key"),
        ("media_identities", "id"),
    ):
        for row in connection.execute(f"SELECT {column} FROM {table}").fetchall():
            _collect_legacy_key_mappings(str(row[column]), mappings)
    json_columns = (
        ("ui_snapshots", "payload_json"),
        ("recommendation_sessions", "channels_json"),
        ("recommendation_batches", "item_keys_json"),
        ("recommendation_batches", "payload_json"),
        ("feedback_events", "payload_json"),
        ("library_items", "payload_json"),
        ("sync_items", "payload_json"),
        ("media_identities", "metadata_json"),
        ("person_identities", "metadata_json"),
        ("provider_identities", "metadata_json"),
        ("asset_candidates", "metadata_json"),
        ("resolution_jobs", "attempts_json"),
        ("sync_jobs", "request_json"),
        ("sync_jobs", "result_json"),
    )
    for table, column in json_columns:
        for row in connection.execute(f"SELECT {column} FROM {table}").fetchall():
            _collect_legacy_key_mappings(_json_value(row[column], {}), mappings)
    if not mappings:
        return 0

    library_rows = connection.execute(
        """
        SELECT item_key, payload_json, state, source, created_at, updated_at
        FROM library_items ORDER BY item_key
        """
    ).fetchall()
    grouped_library: dict[str, list] = {}
    for row in library_rows:
        grouped_library.setdefault(mappings.get(str(row["item_key"]), str(row["item_key"])), []).append(row)
    for canonical_key, rows in grouped_library.items():
        if len(rows) == 1 and str(rows[0]["item_key"]) == canonical_key:
            continue
        payload_winner = max(
            rows,
            key=lambda candidate: (
                float(candidate["updated_at"] or 0),
                str(candidate["item_key"]) == canonical_key,
                str(candidate["item_key"]),
            ),
        )
        state = max(
            (str(candidate["state"] or "candidate") for candidate in rows),
            key=lambda value: ({"watched": 3, "wanted": 2, "candidate": 1}.get(value, 0), value),
        )
        payload = _rewrite_legacy_keys(_json_value(payload_winner["payload_json"], {}), mappings)
        connection.executemany(
            "DELETE FROM library_items WHERE item_key = ?",
            [(str(candidate["item_key"]),) for candidate in rows],
        )
        connection.execute(
            """
            INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_key,
                _encoded_json(payload),
                state,
                str(payload_winner["source"] or ""),
                min(float(candidate["created_at"] or 0) for candidate in rows),
                max(float(candidate["updated_at"] or 0) for candidate in rows),
            ),
        )

    media_rows = connection.execute(
        """
        SELECT id, title, original_titles_json, year, media_type, countries_json,
               metadata_json, created_at, updated_at
        FROM media_identities ORDER BY id
        """
    ).fetchall()
    grouped_media: dict[str, list] = {}
    for row in media_rows:
        grouped_media.setdefault(mappings.get(str(row["id"]), str(row["id"])), []).append(row)
    for canonical_id, rows in grouped_media.items():
        if len(rows) == 1 and str(rows[0]["id"]) == canonical_id:
            continue
        winner = max(
            rows,
            key=lambda candidate: (
                float(candidate["updated_at"] or 0),
                str(candidate["id"]) == canonical_id,
                str(candidate["id"]),
            ),
        )
        metadata = _rewrite_legacy_keys(_json_value(winner["metadata_json"], {}), mappings)
        connection.executemany(
            "DELETE FROM media_identities WHERE id = ?",
            [(str(candidate["id"]),) for candidate in rows],
        )
        connection.execute(
            """
            INSERT INTO media_identities(
                id, title, original_titles_json, year, media_type, countries_json,
                metadata_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                canonical_id,
                str(winner["title"]),
                str(winner["original_titles_json"]),
                winner["year"],
                str(winner["media_type"]),
                str(winner["countries_json"]),
                _encoded_json(metadata),
                min(float(candidate["created_at"] or 0) for candidate in rows),
                max(float(candidate["updated_at"] or 0) for candidate in rows),
            ),
        )

    for old_key, canonical_key in sorted(mappings.items()):
        for table in ("provider_identities", "asset_candidates", "resolution_jobs"):
            connection.execute(
                f"UPDATE {table} SET entity_id = ? WHERE entity_kind = 'media' AND entity_id = ?",
                (canonical_key, old_key),
            )

    override_rows = connection.execute(
        """
        SELECT id, entity_id, kind, updated_at
        FROM user_asset_overrides WHERE entity_kind = 'media'
        ORDER BY entity_id, kind, updated_at, id
        """
    ).fetchall()
    grouped_overrides: dict[tuple[str, str], list] = {}
    for row in override_rows:
        canonical_id = mappings.get(str(row["entity_id"]), str(row["entity_id"]))
        grouped_overrides.setdefault((canonical_id, str(row["kind"])), []).append(row)
    for (canonical_id, _), rows in grouped_overrides.items():
        if len(rows) == 1 and str(rows[0]["entity_id"]) == canonical_id:
            continue
        winner = max(
            rows,
            key=lambda candidate: (
                float(candidate["updated_at"] or 0),
                str(candidate["entity_id"]) == canonical_id,
                str(candidate["id"]),
            ),
        )
        connection.executemany(
            "DELETE FROM user_asset_overrides WHERE id = ?",
            [(str(candidate["id"]),) for candidate in rows if str(candidate["id"]) != str(winner["id"])],
        )
        connection.execute(
            "UPDATE user_asset_overrides SET entity_id = ? WHERE id = ?",
            (canonical_id, str(winner["id"])),
        )

    for old_key, canonical_key in sorted(mappings.items()):
        connection.execute(
            "UPDATE feedback_events SET item_key = ? WHERE item_key = ?",
            (canonical_key, old_key),
        )

    sync_rows = connection.execute(
        "SELECT job_id, item_key, payload_json, source, status FROM sync_items ORDER BY job_id, item_key"
    ).fetchall()
    grouped_sync: dict[tuple[str, str], list] = {}
    for row in sync_rows:
        canonical_key = mappings.get(str(row["item_key"]), str(row["item_key"]))
        grouped_sync.setdefault((str(row["job_id"]), canonical_key), []).append(row)
    for (job_id, canonical_key), rows in grouped_sync.items():
        if len(rows) == 1 and str(rows[0]["item_key"]) == canonical_key:
            continue
        winner = max(rows, key=lambda candidate: (str(candidate["item_key"]) == canonical_key, str(candidate["item_key"])))
        payload = _rewrite_legacy_keys(_json_value(winner["payload_json"], {}), mappings)
        connection.executemany(
            "DELETE FROM sync_items WHERE job_id = ? AND item_key = ?",
            [(job_id, str(candidate["item_key"])) for candidate in rows],
        )
        connection.execute(
            "INSERT INTO sync_items(job_id, item_key, payload_json, source, status) VALUES(?, ?, ?, ?, ?)",
            (job_id, canonical_key, _encoded_json(payload), str(winner["source"]), str(winner["status"])),
        )

    for table, column in json_columns:
        rows = connection.execute(
            f"SELECT rowid AS migration_rowid, {column} FROM {table}"
        ).fetchall()
        for row in rows:
            decoded = _json_value(row[column], None)
            if decoded is None:
                continue
            rewritten = _rewrite_legacy_keys(decoded, mappings)
            if rewritten != decoded:
                connection.execute(
                    f"UPDATE {table} SET {column} = ? WHERE rowid = ?",
                    (_encoded_json(rewritten), int(row["migration_rowid"])),
                )
    return len(mappings)


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
