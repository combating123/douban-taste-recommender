from __future__ import annotations

import base64
import hashlib
import json
import math
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, dataclass, replace
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Sequence
from urllib.parse import quote, urlsplit

from .database import AppDatabase
from .eligibility import catalog_quality_reasons
from .curated_catalog import curated_display_title_for_provider, curated_metadata_for_title, curated_summary_for_provider
from .feedback_service import FeedbackService
from .global_discovery import GlobalDiscoveryConfig, discover_global_candidates
from .media.store import MediaStore
from .intent_parser import RecommendationIntent, intent_to_chips, parse_recommendation_intent
from .models import MediaItem, canonical_media_type, recommendation_identity_tokens, recommendation_item_key
from .ratings import fused_rating
from .localization import (
    contains_non_chinese_east_asian_script,
    is_reliable_chinese_title,
    localize_genre,
    localize_people_names,
    localize_summary,
    to_simplified_chinese,
)
from .semantic import feature_vector
from .profiler import build_taste_profile
from .runtime_paths import resolve_database_path, resolve_media_dir
from .serialization import media_item_from_dict, media_item_to_dict

SCHEMA_VERSION = 2
SAFE_STATE_RE = re.compile(r"^[A-Za-z0-9_-]+$")
ALLOWED_LIBRARY_STATES = {"candidate", "watched", "wish", "wanted", "rated", "collect", "ready", "hidden", "archived", "all"}
SESSION_ONLY_EVENT_TYPES = {"not-tonight", "tonight-candidate"}
APPROVED_ASSET_DECISIONS = {"selected", "approved", "accepted", "chosen"}
SENSITIVE_KEY_MARKERS = {
    "auth",
    "authtoken",
    "bearer",
    "cookie",
    "token",
    "accesstoken",
    "refreshtoken",
    "sessiontoken",
    "apikey",
    "jwt",
    "privatekey",
    "subscription",
    "password",
    "authorization",
    "secret",
}
URL_RE = re.compile(r"https?://[^\s<>'\")\]]+", re.I)
JWT_RE = re.compile(r"\b[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\.[A-Za-z0-9_-]{8,}\b")
SECRET_VALUE_RE = re.compile(
    r"(?i)\b(?:bearer|auth(?:orization)?|access[_-]?token|refresh[_-]?token|session[_-]?token|cookie|token|api[_-]?key|jwt|private[_-]?key|subscription|password|secret)\b\s*[:=]?\s*\S*"
)
TOKEN_LIKE_RE = re.compile(r"\b(?:sk|pk|rk)_(?:live|test|prod)_[A-Za-z0-9_-]{10,}\b", re.I)
RELATION_FIELDS = ("director", "cast", "genre", "country", "media_type", "year_bucket")
RELATION_WEIGHTS = {"director": 4.0, "cast": 2.5, "genre": 1.8, "country": 1.0, "media_type": 0.6, "year_bucket": 0.8}
PROXIED_IMAGE_HOSTS = {
    "static.tvmaze.com",
    "cdn.myanimelist.net",
    "s4.anilist.co",
    "image.tmdb.org",
    "media.themoviedb.org",
    "upload.wikimedia.org",
    "m.media-amazon.com",
    "ia.media-imdb.com",
    "img1.doubanio.com",
    "img2.doubanio.com",
    "img3.doubanio.com",
    "img9.doubanio.com",
}
LATEST_DISCOVERY_TTL_SECONDS = 300.0
LATEST_DISCOVERY_STALE_MAX_AGE_SECONDS = 7 * 24 * 60 * 60.0
LATEST_DISCOVERY_CACHE_SCHEMA = 6
MULTI_FOCUS_CACHE_TTL_SECONDS = 5 * 60.0
MULTI_FOCUS_CACHE_MAX_ENTRIES = 64
MULTI_FOCUS_RANK_CACHE_MAX_ENTRIES = 32
GENERIC_DISCOVERY_GENRES = {
    "剧情",
    "动作",
    "喜剧",
    "爱情",
    "家庭",
    "冒险",
    "作品",
    "其他",
    "电影",
    "电视剧",
    "动漫",
}
GENERIC_DISCOVERY_TAGS = {
    "热门",
    "经典",
    "高分",
    "电影",
    "电视剧",
    "动漫",
    "剧情",
    "动作",
    "作品",
}
PLACEHOLDER_PORTRAIT_MARKERS = (
    "personage-default",
    "celebrity-default",
    "default-avatar",
    "default_portrait",
)


def _is_placeholder_portrait_url(value: object) -> bool:
    url = str(value or "").strip().casefold()
    return bool(url) and any(marker in url for marker in PLACEHOLDER_PORTRAIT_MARKERS)


class ExplorationError(ValueError):
    status_code = 400


class ExplorationNotFound(ExplorationError):
    status_code = 404


@dataclass(frozen=True)
class LibraryRecord:
    item_key: str
    item: MediaItem
    payload: dict[str, Any]
    state: str
    source: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class IdentityRecord:
    id: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class MultiFocusCandidate:
    record: LibraryRecord
    connections: tuple[tuple[float, tuple[str, ...], bool], ...]
    matched_count: int
    score: float
    quality: float
    is_intersection: bool
    components: tuple[dict[str, float], ...] = ()
    # Virtual metadata-complete item used by ranking/MMR.  Keeping it beside
    # the source record avoids re-running curated lookups for every diversity
    # comparison while preserving the original persisted payload.
    item: MediaItem | None = None


def _record_preference_key(record: LibraryRecord) -> tuple[object, ...]:
    item = record.item
    state = str(record.state or "").strip()
    state_priority = {
        "watched": 6,
        "rated": 6,
        "collect": 6,
        "wish": 5,
        "wanted": 5,
        "ready": 4,
        "candidate": 1,
        "hidden": 0,
        "archived": 0,
    }.get(state, 3)
    has_localized_title = bool(re.search(r"[\u3400-\u9fff]", str(item.title or "")))
    has_numeric_douban_id = str(item.douban_id or "").strip().isdigit()
    metadata_score = sum(
        bool(value)
        for value in (
            item.summary,
            item.genres,
            item.countries,
            item.directors,
            item.casts,
            item.tags,
            item.douban_rating,
            item.vote_count,
        )
    )
    payload = record.payload if isinstance(record.payload, dict) else {}
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    media_score = sum(
        _usable_media_reference(value)
        for value in (
            item.cover,
            payload.get("cover"),
            payload.get("backdrop"),
            raw.get("backdrop"),
        )
    )
    media_score += min(
        2,
        sum(_usable_media_reference(value) for value in raw.get("stills", []) if isinstance(raw.get("stills"), list)),
    )
    return (
        state not in {"candidate", "hidden", "archived"},
        state_priority,
        has_localized_title,
        has_numeric_douban_id,
        media_score,
        metadata_score,
        float(item.douban_rating or 0),
        int(item.vote_count or 0),
        float(record.updated_at or 0),
        record.item_key,
    )


def _collapse_duplicate_records(
    records: Sequence[LibraryRecord],
) -> tuple[list[LibraryRecord], list[LibraryRecord]]:
    """Collapse records whose stable identity aliases intersect."""

    items = list(records)
    if len(items) < 2:
        return items, []

    parents = list(range(len(items)))

    def find(index: int) -> int:
        while parents[index] != index:
            parents[index] = parents[parents[index]]
            index = parents[index]
        return index

    def union(left: int, right: int) -> None:
        left_root = find(left)
        right_root = find(right)
        if left_root != right_root:
            parents[right_root] = left_root

    token_owner: dict[str, int] = {}
    for index, record in enumerate(items):
        for token in recommendation_identity_tokens(record.item):
            owner = token_owner.get(token)
            if owner is None:
                token_owner[token] = index
            else:
                union(index, owner)

    groups: dict[int, list[int]] = {}
    for index in range(len(items)):
        groups.setdefault(find(index), []).append(index)

    selected_rows: list[tuple[int, int]] = []
    selected_indices: set[int] = set()
    for indices in groups.values():
        selected_index = max(indices, key=lambda index: _record_preference_key(items[index]))
        selected_indices.add(selected_index)
        selected_rows.append((min(indices), selected_index))
    selected_rows.sort(key=lambda row: row[0])
    selected = [items[selected_index] for _, selected_index in selected_rows]
    dropped = [record for index, record in enumerate(items) if index not in selected_indices]
    return selected, dropped


class ExplorationRepository:
    def __init__(self, database: AppDatabase):
        self.database = database
        self.database.initialize()

    def library_records(self, state: str | None = None) -> list[LibraryRecord]:
        where = ""
        params: list[Any] = []
        if state and state != "all":
            where = " WHERE state = ?"
            params.append(state)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT item_key, payload_json, state, source, created_at, updated_at
                FROM library_items{where}
                ORDER BY updated_at DESC, item_key DESC
                """,
                params,
            ).fetchall()
        return [self._record_from_row(row) for row in rows]

    def library_record(self, item_key: str) -> LibraryRecord | None:
        lookup = str(item_key or "").strip()
        if not lookup:
            return None
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT item_key, payload_json, state, source, created_at, updated_at
                FROM library_items
                WHERE item_key = ?
                LIMIT 1
                """,
                (lookup,),
            ).fetchone()
        return self._record_from_row(row) if row else None

    def visibility_revision(self) -> tuple[int, float, int, float, int, float]:
        """Return a cheap revision for inputs that decide library visibility."""

        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT
                    (SELECT COUNT(*) FROM library_items) AS library_count,
                    (SELECT COALESCE(MAX(updated_at), 0) FROM library_items) AS library_updated_at,
                    (
                        SELECT COUNT(*) FROM user_asset_overrides
                        WHERE entity_kind = 'media' AND kind = 'poster'
                    ) AS poster_override_count,
                    (
                        SELECT COALESCE(MAX(updated_at), 0) FROM user_asset_overrides
                        WHERE entity_kind = 'media' AND kind = 'poster'
                    ) AS poster_override_updated_at,
                    (
                        SELECT COUNT(*)
                        FROM user_asset_overrides o
                        JOIN asset_files a ON a.asset_id = o.asset_id
                        WHERE o.entity_kind = 'media' AND o.kind = 'poster'
                    ) AS poster_asset_count,
                    (
                        SELECT COALESCE(MAX(a.last_verified_at), 0)
                        FROM user_asset_overrides o
                        JOIN asset_files a ON a.asset_id = o.asset_id
                        WHERE o.entity_kind = 'media' AND o.kind = 'poster'
                    ) AS poster_asset_verified_at
                """
            ).fetchone()
        return (
            int(row["library_count"] or 0),
            float(row["library_updated_at"] or 0),
            int(row["poster_override_count"] or 0),
            float(row["poster_override_updated_at"] or 0),
            int(row["poster_asset_count"] or 0),
            float(row["poster_asset_verified_at"] or 0),
        )

    def paged_library(self, state: str, limit: int, cursor: tuple[float, str] | None) -> tuple[list[LibraryRecord], bool]:
        clauses: list[str] = []
        params: list[Any] = []
        if state != "all":
            clauses.append("state = ?")
            params.append(state)
        if cursor is not None:
            clauses.append("(updated_at < ? OR (updated_at = ? AND item_key < ?))")
            params.extend([cursor[0], cursor[0], cursor[1]])
        where = (" WHERE " + " AND ".join(clauses)) if clauses else ""
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT item_key, payload_json, state, source, created_at, updated_at
                FROM library_items{where}
                ORDER BY updated_at DESC, item_key DESC
                LIMIT ?
                """,
                [*params, limit + 1],
            ).fetchall()
        records = [self._record_from_row(row) for row in rows]
        return records[:limit], len(records) > limit

    def _record_from_row(self, row) -> LibraryRecord:
        payload = _json_object(row["payload_json"])
        item = _media_item(payload)
        return LibraryRecord(
            item_key=str(row["item_key"]),
            item=item,
            payload=payload,
            state=str(row["state"] or ""),
            source=str(row["source"] or ""),
            created_at=float(row["created_at"] or 0),
            updated_at=float(row["updated_at"] or 0),
        )

    def media_identity(self, media_id: str) -> IdentityRecord | None:
        with self.database.connection() as connection:
            row = connection.execute("SELECT id, metadata_json FROM media_identities WHERE id = ?", (media_id,)).fetchone()
        return IdentityRecord(str(row["id"]), _json_object(row["metadata_json"])) if row else None

    def person_identity(self, person_id: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT id, name, aliases_json, metadata_json FROM person_identities WHERE id = ?",
                (person_id,),
            ).fetchone()
        if not row:
            return None
        return {"id": str(row["id"]), "name": str(row["name"] or ""), "aliases": _json_list(row["aliases_json"]), "metadata": _json_object(row["metadata_json"])}

    def provider_ids(self, entity_kind: str, entity_id: str) -> dict[str, str]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT provider, provider_id FROM provider_identities
                WHERE entity_kind = ? AND entity_id = ?
                ORDER BY provider, provider_id
                """,
                (entity_kind, entity_id),
            ).fetchall()
        return {str(row["provider"]): str(row["provider_id"]) for row in rows}

    def media_identity_for_item(self, record: LibraryRecord) -> IdentityRecord | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, metadata_json FROM media_identities
                WHERE json_extract(metadata_json, '$.item_key') = ?
                ORDER BY updated_at DESC, id LIMIT 1
                """,
                (record.item_key,),
            ).fetchone()
            if row:
                return IdentityRecord(str(row["id"]), _json_object(row["metadata_json"]))
            if record.item.douban_id:
                row = connection.execute(
                    """
                    SELECT m.id, m.metadata_json
                    FROM provider_identities p
                    JOIN media_identities m ON m.id = p.entity_id
                    WHERE p.entity_kind = 'media' AND p.provider = 'douban' AND p.provider_id = ?
                    ORDER BY p.confidence DESC, m.updated_at DESC, m.id LIMIT 1
                    """,
                    (str(record.item.douban_id),),
                ).fetchone()
                if row:
                    return IdentityRecord(str(row["id"]), _json_object(row["metadata_json"]))
        return None

    def media_entity_ids_for_records(self, records: list[LibraryRecord]) -> dict[str, str]:
        item_keys = sorted({record.item_key for record in records if str(record.item_key or "").strip()})
        douban_ids = sorted({str(record.item.douban_id) for record in records if str(record.item.douban_id or "").strip()})
        by_item_key: dict[str, str] = {}
        by_douban_id: dict[str, str] = {}
        if not item_keys and not douban_ids:
            return {record.item_key: "" for record in records}

        def chunks(values: list[str], size: int = 400):
            for offset in range(0, len(values), size):
                yield values[offset:offset + size]

        with self.database.connection() as connection:
            # Restrict both lookups to the requested records.  The previous
            # implementation scanned every identity row for every graph and
            # library page; that became the dominant cost once the catalog
            # grew beyond a few hundred titles.
            for values in chunks(item_keys):
                placeholders = ",".join("?" for _ in values)
                identity_rows = connection.execute(
                    f"""
                    SELECT id, json_extract(metadata_json, '$.item_key') AS item_key
                    FROM media_identities
                    WHERE json_extract(metadata_json, '$.item_key') IN ({placeholders})
                    ORDER BY updated_at DESC, id
                    """,
                    values,
                ).fetchall()
                for row in identity_rows:
                    item_key = str(row["item_key"] or "").strip()
                    if item_key:
                        by_item_key.setdefault(item_key, str(row["id"]))
            for values in chunks(douban_ids):
                placeholders = ",".join("?" for _ in values)
                provider_rows = connection.execute(
                    f"""
                    SELECT p.entity_id, p.provider_id
                    FROM provider_identities p
                    LEFT JOIN media_identities m ON m.id = p.entity_id
                    WHERE p.entity_kind = 'media'
                      AND p.provider = 'douban'
                      AND p.provider_id IN ({placeholders})
                    ORDER BY p.confidence DESC, m.updated_at DESC, p.entity_id
                    """,
                    values,
                ).fetchall()
                for row in provider_rows:
                    provider_id = str(row["provider_id"] or "").strip()
                    if provider_id:
                        by_douban_id.setdefault(provider_id, str(row["entity_id"]))
        return {
            record.item_key: by_item_key.get(record.item_key)
            or by_douban_id.get(str(record.item.douban_id or ""), "")
            for record in records
        }

    def asset_override(self, entity_kind: str, entity_id: str, kind: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT o.asset_id, o.decision, a.relative_path, a.mime_type, a.extension, a.kind, a.status
                FROM user_asset_overrides o
                LEFT JOIN asset_files a ON a.asset_id = o.asset_id
                WHERE o.entity_kind = ? AND o.entity_id = ? AND o.kind = ?
                """,
                (entity_kind, entity_id, kind),
            ).fetchone()
        return dict(row) if row else None

    def asset_overrides_for_kind(
        self,
        entity_kind: str,
        kind: str,
        entity_ids: Sequence[str] | None = None,
    ) -> dict[str, dict[str, Any]]:
        clean_ids = sorted({str(value or "").strip() for value in (entity_ids or ()) if str(value or "").strip()})
        clauses = ["o.entity_kind = ?", "o.kind = ?"]
        params: list[Any] = [entity_kind, kind]
        if clean_ids:
            clauses.append(f"o.entity_id IN ({','.join('?' for _ in clean_ids)})")
            params.extend(clean_ids)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT o.entity_id, o.asset_id, o.decision, a.relative_path, a.mime_type,
                       a.extension, a.kind, a.status, a.byte_size
                FROM user_asset_overrides o
                LEFT JOIN asset_files a ON a.asset_id = o.asset_id
                WHERE {' AND '.join(clauses)}
                """,
                params,
            ).fetchall()
        return {str(row["entity_id"]): dict(row) for row in rows}

    def asset_for_route(self, asset_id: str, extension: str) -> dict[str, Any] | None:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT asset_id, relative_path, mime_type, extension, kind, status
                FROM asset_files
                WHERE asset_id = ? AND lower(extension) = lower(?)
                """,
                (asset_id, extension),
            ).fetchone()
        return dict(row) if row else None

    def person_id_by_name(self, name: str) -> str | None:
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT id FROM person_identities WHERE name = ? ORDER BY updated_at DESC, id LIMIT 1",
                (name,),
            ).fetchone()
        return str(row["id"]) if row else None

    def feedback_rows(self, profile_key: str) -> list[dict[str, Any]]:
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, session_id, item_key, payload_json, undone_by, created_at
                FROM feedback_events WHERE profile_key = ?
                ORDER BY created_at DESC, id DESC
                """,
                (profile_key,),
            ).fetchall()
        return [dict(row) for row in rows]


class ExplorationService:
    def __init__(self, database: AppDatabase, media_root: Path | str | None = None):
        self.database = database
        self.database.initialize()
        self.media_root = Path(media_root or resolve_media_dir()).resolve()
        self.repository = ExplorationRepository(database)
        self.feedback_service = FeedbackService(database)
        self.media_store = MediaStore(self.media_root, database)
        self._visibility_cache_revision: tuple[int, float, int, float, int, float] | None = None
        self._visibility_cache_records: list[LibraryRecord] = []
        self._visibility_cache_hidden_candidates = 0
        self._library_records_cache_revision: tuple[int, float, int, float, int, float] | None = None
        self._library_records_cache: list[LibraryRecord] = []
        self._library_records_cache_lock = threading.RLock()
        self._latest_discovery_cache: dict[tuple[str, str, int], dict[str, object]] = {}
        self._latest_discovery_lock = threading.RLock()
        self._multi_focus_cache: dict[tuple[object, ...], tuple[float, dict[str, object]]] = {}
        self._multi_focus_lock = threading.RLock()
        # Ranking a multi-focus graph is the expensive part; presentation
        # batches (limit/round/poster requirement) can safely reuse it until
        # the library or online discovery revision changes.
        self._multi_focus_rank_cache: dict[tuple[object, ...], dict[str, object]] = {}
        self._multi_focus_rank_lock = threading.RLock()
        self._discovery_feature_cache: dict[str, tuple[object, str, tuple[float, ...], dict[str, float], frozenset[str], float]] = {}
        self._discovery_feature_lock = threading.RLock()

    def _library_records_snapshot(self) -> list[LibraryRecord]:
        """Return a short-lived immutable-ish catalog snapshot.

        Several observatory paths used to decode the complete SQLite payload
        repeatedly in one request (and once per ``换一批`` click).  The
        visibility revision already captures the fields that affect candidate
        visibility, so it is a safe and cheap cache key for the in-process
        snapshot.
        """

        revision = self.repository.visibility_revision()
        with self._library_records_cache_lock:
            if revision == self._library_records_cache_revision:
                return list(self._library_records_cache)
        records = self.repository.library_records()
        with self._library_records_cache_lock:
            self._library_records_cache_revision = revision
            self._library_records_cache = list(records)
        return list(records)

    def _prepared_discovery_features(
        self,
        record: LibraryRecord,
    ) -> tuple[str, tuple[float, ...], dict[str, float], frozenset[str], float]:
        """Prepare reusable graph features once per catalog revision.

        Vectorisation and trait inference are pure functions but relatively
        expensive for a thousand-record catalog.  Keeping them by stable item
        key/update time makes the first graph responsive and subsequent
        batches effectively presentation-only work.
        """

        # The caller may provide a raw repository record (for example from a
        # similarity endpoint rather than the multi-focus snapshot).  Apply
        # the same virtual metadata repair here so every discovery surface
        # benefits from sparse-record recovery.
        record = _enrich_discovery_record(record)
        text = _discovery_text(record.item)
        fingerprint = (float(record.updated_at or 0), text)
        with self._discovery_feature_lock:
            cached = self._discovery_feature_cache.get(record.item_key)
            if cached is not None and cached[0] == fingerprint:
                return cached[1], cached[2], dict(cached[3]), cached[4], cached[5]
        vector = feature_vector(text)
        traits = _trait_values(record.item)
        identity_tokens = frozenset(recommendation_identity_tokens(record.item))
        quality = _quality_affinity(record.item)
        value = (fingerprint, text, vector, dict(traits), identity_tokens, quality)
        with self._discovery_feature_lock:
            self._discovery_feature_cache[record.item_key] = value
            # Keep the cache bounded if a long-running process receives many
            # sync revisions.  Eviction is insertion-order deterministic.
            while len(self._discovery_feature_cache) > 4096:
                self._discovery_feature_cache.pop(next(iter(self._discovery_feature_cache)))
        return text, vector, dict(traits), identity_tokens, quality

    def title(self, lookup_id: str) -> dict[str, object]:
        record = self.find_title(lookup_id)
        if record is not None:
            return self.serialize_title(record)
        discovery_item = self._find_latest_discovery_item(lookup_id)
        if discovery_item is not None:
            return self._serialize_latest_discovery_title(discovery_item)
        raise ExplorationNotFound("title not found")

    def _find_latest_discovery_item(self, lookup_id: str) -> dict[str, object] | None:
        """Resolve a live card without inserting it into the local library."""

        lookup = str(lookup_id or "").strip()
        if not lookup:
            return None

        def find_in_snapshot(snapshot: object) -> dict[str, object] | None:
            if not isinstance(snapshot, dict):
                return None
            for item in snapshot.get("items", []):
                if not isinstance(item, dict) or not item.get("is_live"):
                    continue
                item_key = str(item.get("item_key") or item.get("id") or "").strip()
                if item_key == lookup:
                    return dict(item)
            return None

        with self._latest_discovery_lock:
            memory_snapshots = [dict(snapshot) for snapshot in self._latest_discovery_cache.values()]
        for snapshot in reversed(memory_snapshots):
            if item := find_in_snapshot(snapshot):
                return item

        cutoff = time.time() - LATEST_DISCOVERY_STALE_MAX_AGE_SECONDS
        try:
            with self.database.connection() as connection:
                rows = connection.execute(
                    """
                    SELECT payload_json
                    FROM ui_snapshots
                    WHERE key LIKE 'latest-discovery:%' AND updated_at >= ?
                    ORDER BY updated_at DESC
                    LIMIT 64
                    """,
                    (cutoff,),
                ).fetchall()
        except (OSError, ValueError):
            return None
        for row in rows:
            try:
                snapshot = json.loads(str(row["payload_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if item := find_in_snapshot(snapshot):
                return item
        return None

    def _serialize_latest_discovery_title(self, payload: dict[str, object]) -> dict[str, object]:
        item = _localized_latest_discovery_item(payload)
        item_key = str(item.get("item_key") or item.get("id") or "").strip()
        if not item_key:
            raise ExplorationNotFound("title not found")
        poster = dict(item.get("poster") or {}) if isinstance(item.get("poster"), dict) else {"url": "", "media_status": "missing"}
        backdrop = dict(item.get("backdrop") or {}) if isinstance(item.get("backdrop"), dict) else {"url": "", "media_status": "missing"}
        source_ratings = _rating_map(item.get("source_ratings"))
        rating_votes = _vote_map(item.get("rating_votes"))
        provider_ids = _discovery_provider_ids(item)
        display_title = str(item.get("display_title") or item.get("title") or "").strip()
        original_title = str(item.get("original_title") or item.get("title") or display_title).strip()
        aliases = _dedupe([
            original_title,
            *(
                [str(value or "").strip() for value in item.get("aliases", [])]
                if isinstance(item.get("aliases"), list)
                else []
            ),
        ])
        discovery_sources = [
            str(value or "").strip()
            for value in item.get("discovery_sources", [])
            if str(value or "").strip()
        ] if isinstance(item.get("discovery_sources"), list) else []
        source_labels = [
            str(value or "").strip()
            for value in item.get("source_labels", [])
            if str(value or "").strip()
        ] if isinstance(item.get("source_labels"), list) else []
        release_date = str(item.get("release_date") or "").strip()
        raw: dict[str, object] = {
            "ratings": source_ratings,
            "rating_votes": rating_votes,
            "provider_ids": provider_ids,
            "aliases": aliases,
            "original_title": original_title,
            "comment_count": _positive_int(item.get("comment_count")),
            "review_count": _positive_int(item.get("review_count")),
            "release_date": release_date,
            "discovery_sources": discovery_sources,
            "source_labels": source_labels,
            "discovered_at": _finite_number(item.get("discovered_at")),
        }
        if isinstance(item.get("original_directors"), list):
            raw["original_directors"] = [
                str(value).strip()
                for value in item["original_directors"]
                if str(value).strip()
            ]
        media_type = canonical_media_type(item.get("media_type"))
        item_payload: dict[str, object] = {
            "title": display_title,
            "display_title": display_title,
            "original_title": original_title,
            "year": _positive_int(item.get("year")),
            "media_type": media_type,
            "genres": [localize_genre(value) for value in item.get("genres", [])] if isinstance(item.get("genres"), list) else [],
            "countries": [to_simplified_chinese(value) for value in item.get("countries", [])] if isinstance(item.get("countries"), list) else [],
            "languages": [to_simplified_chinese(value) for value in item.get("languages", [])] if isinstance(item.get("languages"), list) else [],
            "directors": [to_simplified_chinese(value) for value in item.get("directors", [])] if isinstance(item.get("directors"), list) else [],
            "casts": [to_simplified_chinese(value) for value in item.get("casts", [])] if isinstance(item.get("casts"), list) else [],
            "tags": [to_simplified_chinese(value) for value in item.get("tags", [])] if isinstance(item.get("tags"), list) else [],
            "summary": localize_summary(item.get("summary")),
            "douban_rating": _finite_number(item.get("douban_rating")),
            "vote_count": _positive_int(item.get("vote_count")),
            "release_date": release_date,
            "source": "global-discovery",
            "raw": raw,
        }
        stills = [
            dict(value)
            for value in item.get("stills", [])
            if isinstance(value, dict) and str(value.get("url") or "").strip()
        ] if isinstance(item.get("stills"), list) else []
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "id": item_key,
            "item_key": item_key,
            "state": "online",
            "is_live": True,
            "discovery_status": "online",
            "title": display_title,
            "display_title": display_title,
            "original_title": original_title,
            "title_localization_source": str(item.get("title_localization_source") or "online"),
            "media_type": media_type,
            "media_badge": item.get("media_badge") or _media_badge(media_type, item_payload["genres"]),
            "year": item_payload["year"],
            "item": item_payload,
            "poster": poster,
            "backdrop": backdrop,
            "stills": stills,
            "people": [],
            "source_labels": source_labels,
            "discovery_sources": discovery_sources,
            "updated_at": _finite_number(item.get("discovered_at")) or time.time(),
        })

    def _latest_discovery_record(self, payload: dict[str, object]) -> LibraryRecord:
        title = self._serialize_latest_discovery_title(payload)
        item_payload = dict(title.get("item") or {})
        poster = title.get("poster") if isinstance(title.get("poster"), dict) else {}
        backdrop = title.get("backdrop") if isinstance(title.get("backdrop"), dict) else {}
        item_payload["cover"] = str(poster.get("url") or "")
        record_item = media_item_from_dict(item_payload)
        updated_at = _finite_number(title.get("updated_at")) or time.time()
        return LibraryRecord(
            item_key=str(title.get("item_key") or ""),
            item=record_item,
            payload={
                **item_payload,
                "cover": str(poster.get("url") or ""),
                "backdrop": str(backdrop.get("url") or ""),
                "raw": dict(item_payload.get("raw") or {}),
            },
            state="online",
            source="global-discovery",
            created_at=updated_at,
            updated_at=updated_at,
        )

    def _cached_live_discovery_records(self) -> list[LibraryRecord]:
        """Reuse already-fetched online titles without putting network I/O on graph rebuilds."""

        with self._latest_discovery_lock:
            snapshots = [dict(snapshot) for snapshot in self._latest_discovery_cache.values()]
        records: list[LibraryRecord] = []
        for snapshot in reversed(snapshots):
            items = snapshot.get("items") if isinstance(snapshot.get("items"), list) else []
            for payload in items:
                if not isinstance(payload, dict) or not payload.get("is_live"):
                    continue
                localized = _localized_latest_discovery_item(payload)
                if not _has_publishable_discovery_title(localized):
                    continue
                try:
                    records.append(self._latest_discovery_record(localized))
                except (ExplorationError, TypeError, ValueError):
                    continue
        collapsed, _ = _collapse_duplicate_records(records)
        return collapsed

    def _discovery_serialization_context(
        self,
        records: Sequence[LibraryRecord],
    ) -> dict[str, dict[str, object]]:
        """Batch identity and asset lookups so one graph response does not issue N+1 queries."""

        local_records = [
            record
            for record in records
            if record.state != "online" and record.source != "global-discovery"
        ]
        if not local_records:
            return {}
        unique_records = list({record.item_key: record for record in local_records}.values())
        identity_ids = self.repository.media_entity_ids_for_records(unique_records)
        asset_entity_ids = [
            value
            for value in {
                *identity_ids.values(),
                *(record.item_key for record in unique_records),
            }
            if str(value or "").strip()
        ]
        poster_overrides = self.repository.asset_overrides_for_kind(
            "media",
            "poster",
            entity_ids=asset_entity_ids,
        )
        backdrop_overrides = self.repository.asset_overrides_for_kind(
            "media",
            "backdrop",
            entity_ids=asset_entity_ids,
        )
        context: dict[str, dict[str, object]] = {}
        for record in unique_records:
            identity_id = identity_ids.get(record.item_key, "")
            asset_entity_id = identity_id or record.item_key
            context[record.item_key] = {
                "identity_id": identity_id,
                "assets": {
                    "poster": poster_overrides.get(asset_entity_id),
                    "backdrop": backdrop_overrides.get(asset_entity_id),
                },
            }
        return context

    def person(self, lookup_id: str) -> dict[str, object]:
        identity = self.repository.person_identity(str(lookup_id or "").strip())
        derived = self._derive_person(str(lookup_id or "").strip(), identity)
        if derived is None:
            raise ExplorationNotFound("person not found")
        person_id, name, aliases, metadata, evidence = derived
        portrait = self._person_asset(person_id, name)
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "id": person_id,
            "name": name,
            "aliases": aliases,
            "bio": str(metadata.get("bio") or "") if isinstance(metadata, dict) else "",
            "portrait": portrait,
            "media_status": portrait["media_status"],
            "known_for": [self._node_payload(record) for record in evidence[:8]],
            "evidence_title_ids": [record.item_key for record in evidence],
            "evidence": [{"title_id": record.item_key, "title": record.item.title, "roles": self._roles_for_person(record, name)} for record in evidence],
        })

    def library(self, state: str = "all", cursor: str = "", limit: int = 24) -> dict[str, object]:
        clean_state = self._validate_state(state)
        clean_limit = self._validate_limit(limit, 1, 100, field="limit")
        parsed_cursor = self._decode_cursor(cursor) if cursor else None
        visible_records, hidden_candidates = self.visible_library_records(include_hidden_count=True)
        records = visible_records if clean_state == "all" else [record for record in visible_records if record.state == clean_state]
        if parsed_cursor is not None:
            records = [
                record
                for record in records
                if record.updated_at < parsed_cursor[0]
                or (record.updated_at == parsed_cursor[0] and record.item_key < parsed_cursor[1])
            ]
        has_more = len(records) > clean_limit
        records = records[:clean_limit]
        counts = self._library_counts(visible_records)
        media_entity_ids = self.repository.media_entity_ids_for_records(records) if records else {}
        poster_overrides = self.repository.asset_overrides_for_kind("media", "poster") if records else {}
        backdrop_overrides = self.repository.asset_overrides_for_kind("media", "backdrop") if records else {}
        items: list[dict[str, object]] = []
        for record in records:
            identity_id = media_entity_ids.get(record.item_key, "")
            asset_entity_id = identity_id or record.item_key
            items.append(
                self.serialize_title(
                    record,
                    include_schema=False,
                    include_people=False,
                    identity_id=identity_id,
                    prefetched_assets={
                        "poster": poster_overrides.get(asset_entity_id),
                        "backdrop": backdrop_overrides.get(asset_entity_id),
                    },
                )
            )
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "state": clean_state,
            "limit": clean_limit,
            "counts": counts,
            "hidden_candidates": hidden_candidates,
            "items": items,
            "next_cursor": self._encode_cursor(records[-1]) if has_more and records else "",
        })

    def recent_history(self, profile_key: str = "default", limit: int = 24) -> dict[str, object]:
        """Return a date-aware recent-watch timeline.

        A Douban collection date is preferred when present.  Explicit
        ``watched`` feedback events are used next, and the local library
        update time is only a transparent fallback.  This prevents a sync
        timestamp from being presented as if it were the date the user
        actually watched a title.
        """

        clean_limit = self._validate_limit(limit, 1, 100, field="limit")
        profile = str(profile_key or "default").strip() or "default"
        records = self._library_records_snapshot()
        records_by_key = {record.item_key: record for record in records}
        watched_records = {
            record.item_key: record
            for record in records
            if str(record.state or "").strip() in {"watched", "collect", "rated"}
            or _record_is_seen(record)
        }

        token_owner: dict[str, LibraryRecord] = {}
        for record in watched_records.values():
            token_owner.setdefault(record.item_key, record)
            for token in recommendation_identity_tokens(record.item):
                token_owner.setdefault(token, record)

        undone_ids = {
            str(_json_object(row.get("payload_json")).get("target_event_id") or "")
            for row in self.repository.feedback_rows(profile)
            if str(row.get("event_type") or "") == "undo"
        }
        event_timestamps: dict[str, list[float]] = {}
        event_only: dict[str, LibraryRecord] = {}
        for row in self.repository.feedback_rows(profile):
            event_id = str(row.get("id") or "")
            if event_id in undone_ids or str(row.get("event_type") or "") != "watched":
                continue
            try:
                timestamp = float(row.get("created_at") or 0)
            except (TypeError, ValueError):
                timestamp = 0.0
            if timestamp <= 0:
                continue
            payload = _json_object(row.get("payload_json"))
            item_key = str(row.get("item_key") or "").strip()
            record = records_by_key.get(item_key) or token_owner.get(item_key)
            if record is None:
                aliases = payload.get("identity_aliases", payload.get("identity_tokens", ()))
                if isinstance(aliases, (list, tuple, set)):
                    for alias in aliases:
                        record = token_owner.get(str(alias or "").strip())
                        if record is not None:
                            break
            if record is None:
                item_payload = payload.get("item")
                if isinstance(item_payload, dict):
                    item = _media_item(item_payload)
                    item_key = item_key or recommendation_item_key(item)
                    if item_key:
                        record = event_only.get(item_key)
                        if record is None:
                            record = LibraryRecord(
                                item_key=item_key,
                                item=item,
                                payload=dict(item_payload),
                                state="watched",
                                source="feedback:watched",
                                created_at=timestamp,
                                updated_at=timestamp,
                            )
                            event_only[item_key] = record
            if record is None:
                continue
            event_timestamps.setdefault(record.item_key, []).append(timestamp)

        all_records = {**watched_records, **event_only}
        timeline_rows: list[tuple[float, str, LibraryRecord, dict[str, object], str, list[float]]] = []
        for record in all_records.values():
            raw = record.payload.get("raw") if isinstance(record.payload.get("raw"), dict) else {}
            source_date = _first_activity_date(raw)
            source_timestamp = _activity_timestamp(source_date)
            feedback_dates = event_timestamps.get(record.item_key, [])
            feedback_timestamp = max(feedback_dates, default=0.0)
            if feedback_timestamp > 0:
                watched_at = max(feedback_timestamp, source_timestamp)
                watch_source = "feedback" if feedback_timestamp >= source_timestamp else "douban"
            elif source_timestamp > 0:
                watched_at = source_timestamp
                watch_source = "douban"
            else:
                watched_at = float(record.updated_at or record.created_at or 0)
                watch_source = "sync"
            if watched_at <= 0:
                continue
            timeline_rows.append((watched_at, record.item_key, record, raw, watch_source, feedback_dates))

        timeline_rows.sort(key=lambda row: (-row[0], row[1]))
        selected_rows = timeline_rows[:clean_limit]
        selected_records = [row[2] for row in selected_rows]
        media_entity_ids = self.repository.media_entity_ids_for_records(selected_records) if selected_records else {}
        poster_overrides = self.repository.asset_overrides_for_kind("media", "poster") if selected_records else {}
        backdrop_overrides = self.repository.asset_overrides_for_kind("media", "backdrop") if selected_records else {}

        timeline: list[dict[str, object]] = []
        for watched_at, _, record, raw, watch_source, feedback_dates in selected_rows:
            identity_id = media_entity_ids.get(record.item_key, "")
            asset_entity_id = identity_id or record.item_key
            serialized = self.serialize_title(
                record,
                include_schema=False,
                include_people=False,
                identity_id=identity_id,
                prefetched_assets={
                    "poster": poster_overrides.get(asset_entity_id),
                    "backdrop": backdrop_overrides.get(asset_entity_id),
                },
            )
            progress = _watch_progress(raw)
            serialized.update({
                "watched_at": watched_at,
                "watched_at_iso": _iso_timestamp(watched_at),
                "watched_date": _date_from_timestamp(watched_at),
                "watched_relative": _relative_date_label(watched_at),
                "watch_source": watch_source,
                "watch_source_label": {
                    "feedback": "应用观影记录",
                    "douban": "豆瓣看过日期",
                    "sync": "同步时间（未提供观看日期）",
                }.get(watch_source, "观影记录"),
                "watch_count": max(1, len(feedback_dates)),
                "watch_progress": progress,
            })
            timeline.append(serialized)

        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "profile_key": profile,
            "count": len(timeline_rows),
            "items": timeline,
            "has_more": len(timeline_rows) > clean_limit,
            "generated_at": time.time(),
        })

    def latest_discovery(
        self,
        profile_key: str = "default",
        limit: int = 24,
        *,
        refresh: bool = False,
        media_type: str = "",
    ) -> dict[str, object]:
        """Fetch and cache a bounded online-now feed with honest source status."""

        clean_limit = self._validate_limit(limit, 1, 60, field="limit")
        profile = str(profile_key or "default").strip() or "default"
        canonical_type = canonical_media_type(media_type)
        cache_key = (profile, canonical_type or "all", clean_limit)
        snapshot_key = (
            f"latest-discovery:v{LATEST_DISCOVERY_CACHE_SCHEMA}:"
            f"{profile}:{canonical_type or 'all'}:{clean_limit}"
        )
        now = time.time()
        with self._latest_discovery_lock:
            cached = self._latest_discovery_cache.get(cache_key)
            if cached and not refresh and float(cached.get("expires_at") or 0) > now:
                return _sanitize_catalog_payload(dict(cached))
        if not refresh:
            try:
                persisted = self.database.get_ui_snapshot(snapshot_key)
            except (OSError, ValueError, json.JSONDecodeError):
                persisted = None
            if isinstance(persisted, dict) and isinstance(persisted.get("items"), list) and persisted.get("items"):
                fetched_at = _finite_number(persisted.get("fetched_at")) or 0.0
                age = max(0.0, now - fetched_at) if fetched_at > 0 else math.inf
                if age <= LATEST_DISCOVERY_STALE_MAX_AGE_SECONDS:
                    restored = dict(persisted)
                    if float(restored.get("expires_at") or 0) <= now:
                        restored["is_stale"] = True
                        restored["status"] = "stale"
                        restored["restored_at"] = now
                        restored["expires_at"] = now + 30.0
                    with self._latest_discovery_lock:
                        self._latest_discovery_cache[cache_key] = dict(restored)
                    return _sanitize_catalog_payload(restored)

        records = self.repository.library_records()
        rated_items = [record.item for record in records if _record_is_seen(record)]
        feedback_signals = self.feedback_service.feedback_signals(profile, now)
        taste_profile = build_taste_profile(rated_items, feedback_signals=feedback_signals)
        intent = RecommendationIntent(
            media_types=(canonical_type,) if canonical_type in {"电影", "电视剧", "动漫"} else (),
        )
        config = GlobalDiscoveryConfig.from_payload({
            "max_per_source": max(8, min(24, clean_limit * 2)),
            "max_total": max(24, min(120, clean_limit * 4)),
            "timeout_seconds": 4.0,
            "include_current": True,
            "enable_jikan": False,
        })
        report = None
        error_text = ""
        try:
            report = discover_global_candidates(
                intent,
                taste_profile,
                include_movies=not canonical_type or canonical_type == "电影",
                include_series=not canonical_type or canonical_type == "电视剧",
                include_anime=not canonical_type or canonical_type == "动漫",
                config=config,
                now=lambda: now,
            )
        except Exception as error:  # Network providers are optional by design.
            error_text = type(error).__name__

        live_items: list[dict[str, object]] = []
        if report is not None:
            for rank, item in enumerate(report.items, start=1):
                payload = _live_discovery_payload(item, rank=rank, generated_at=now)
                if payload is not None:
                    live_items.append(payload)
        live_items = _sort_latest_payloads(live_items)

        # Keep a useful offline rail when a provider is unavailable. Local
        # candidates are explicitly marked as fallback rather than pretending
        # they are current online results.
        local_items: list[dict[str, object]] = []
        local_records = [
            record for record in self.visible_library_records()
            if record.state == "candidate"
            and (not canonical_type or record.item.media_type == canonical_type)
        ]
        local_records.sort(key=_latest_record_sort_key, reverse=True)
        live_token_index = {
            token: item
            for item in live_items
            for token in item.get("identity_tokens", [])
            if str(token or "").strip()
        }
        live_signature_index = {
            signature: item
            for item in live_items
            for signature in _discovery_payload_signatures(item)
        }
        for record in local_records:
            tokens = list(recommendation_identity_tokens(record.item))
            payload = self.serialize_title(record, include_schema=False, include_people=False)
            raw = record.item.raw if isinstance(record.item.raw, dict) else {}
            source_ratings = _rating_map(raw.get("ratings"))
            if record.item.douban_rating is not None:
                rating = _finite_number(record.item.douban_rating)
                if rating is not None and rating > 0:
                    source_ratings.setdefault("douban", round(rating, 2))
            payload.update({
                "is_live": False,
                "discovery_status": "local-fallback",
                "identity_tokens": tokens,
                "genres": [localize_genre(value) for value in record.item.genres],
                "countries": [to_simplified_chinese(value) for value in record.item.countries],
                "summary": localize_summary(str(record.item.summary or "").strip()),
                "source_ratings": source_ratings,
                "rating_votes": _vote_map(raw.get("rating_votes")),
                "douban_rating": record.item.douban_rating,
                "vote_count": _positive_int(record.item.vote_count),
                "comment_count": _positive_int(raw.get("comment_count")),
                "review_count": _positive_int(raw.get("review_count")),
                "release_date": _first_activity_date(
                    raw,
                    include_release=True,
                ),
            })
            duplicate_live = next(
                (live_token_index[token] for token in tokens if token in live_token_index),
                None,
            )
            if duplicate_live is None:
                duplicate_live = next(
                    (
                        live_signature_index[signature]
                        for signature in _discovery_payload_signatures(payload)
                        if signature in live_signature_index
                    ),
                    None,
                )
            if duplicate_live is not None:
                _merge_local_duplicate_into_live(duplicate_live, payload)
                continue
            local_items.append(payload)
            if len(local_items) >= clean_limit:
                break

        combined = live_items[:clean_limit]
        if len(combined) < clean_limit:
            combined.extend(local_items[: clean_limit - len(combined)])
        report_status = str(getattr(report, "status", "failed") if report is not None else "failed")
        status = "live" if live_items else "fallback" if local_items else report_status
        result: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "profile_key": profile,
            "media_type": canonical_type or "all",
            "status": status,
            "is_stale": False,
            "fetched_at": now,
            "fetched_at_iso": _iso_timestamp(now),
            "live_count": len(live_items),
            "fallback_count": len(local_items),
            "source_counts": dict(getattr(report, "source_counts", {}) if report is not None else {}),
            "source_status": dict(getattr(report, "source_status", {}) if report is not None else {}),
            "config": config.public_summary(),
            "items": combined,
        }
        if error_text:
            result["error"] = error_text
        if not live_items and cached:
            # Preserve the last successful online payload if a manual refresh
            # happens during a temporary provider outage.
            stale = dict(cached)
            stale["is_stale"] = True
            stale["status"] = "stale"
            stale["refreshed_at"] = now
            with self._latest_discovery_lock:
                self._latest_discovery_cache[cache_key] = stale
            return _sanitize_catalog_payload(stale)

        result["expires_at"] = now + LATEST_DISCOVERY_TTL_SECONDS
        with self._latest_discovery_lock:
            self._latest_discovery_cache[cache_key] = dict(result)
        if live_items:
            try:
                self.database.upsert_ui_snapshot(snapshot_key, _sanitize_catalog_payload(dict(result)))
            except (OSError, ValueError, TypeError):
                pass
        return _sanitize_catalog_payload(result)

    def observatory(
        self,
        profile_key: str = "default",
        limit: int = 18,
        *,
        refresh: bool = False,
    ) -> dict[str, object]:
        """Aggregate recent history, live discovery, and a graph seed."""

        clean_limit = self._validate_limit(limit, 1, 60, field="limit")
        request_limit = min(clean_limit, 36)
        with ThreadPoolExecutor(max_workers=2, thread_name_prefix="cinescope-observatory") as executor:
            recent_future = executor.submit(self.recent_history, profile_key, request_limit)
            latest_future = executor.submit(
                self.latest_discovery,
                profile_key,
                request_limit,
                refresh=refresh,
            )

            # The graph only depends on recent history. Build it while online
            # providers are still in flight rather than serializing all three
            # independent parts of the observatory response.
            recent = recent_future.result()
            recent_items = recent.get("items") if isinstance(recent, dict) else []
            focus_id = str(recent_items[0].get("item_key") or "") if recent_items and isinstance(recent_items[0], dict) else ""
            if not focus_id:
                local = self.repository.library_records(state="candidate")
                focus_id = local[0].item_key if local else ""
            graph = {
                "schema_version": SCHEMA_VERSION,
                "focus_id": focus_id,
                "nodes": [],
                "edges": [],
            }
            if focus_id:
                try:
                    graph = self.build_universe_graph(focus_id, limit=min(18, max(3, clean_limit)))
                except ExplorationError:
                    pass
            latest = latest_future.result()
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "generated_at": time.time(),
            "recent": recent,
            "latest": latest,
            "graph": graph,
            "summary": {
                "recent_count": int(recent.get("count") or 0) if isinstance(recent, dict) else 0,
                "live_count": int(latest.get("live_count") or 0) if isinstance(latest, dict) else 0,
                "latest_status": str(latest.get("status") or "unknown") if isinstance(latest, dict) else "unknown",
            },
        })

    def visible_library_records(self, include_hidden_count: bool = False):
        revision = self.repository.visibility_revision()
        if revision == self._visibility_cache_revision:
            visible_records = list(self._visibility_cache_records)
            hidden_candidates = self._visibility_cache_hidden_candidates
            return (visible_records, hidden_candidates) if include_hidden_count else visible_records

        all_records = self._library_records_snapshot()
        media_entity_ids = self.repository.media_entity_ids_for_records(all_records)
        visible_records, hidden_candidates = self._visible_library_records(
            all_records,
            media_entity_ids=media_entity_ids,
            poster_overrides=self.repository.asset_overrides_for_kind(
                "media",
                "poster",
                entity_ids=[*media_entity_ids.values(), *(record.item_key for record in all_records)],
            ),
        )
        self._visibility_cache_revision = revision
        self._visibility_cache_records = list(visible_records)
        self._visibility_cache_hidden_candidates = hidden_candidates
        return (visible_records, hidden_candidates) if include_hidden_count else visible_records

    def taste(self, profile_key: str = "default") -> dict[str, object]:
        profile_key = str(profile_key or "default").strip() or "default"
        records = self._library_records_snapshot()
        rated_items = [record.item for record in records if record.item.my_rating is not None]
        profile = build_taste_profile(rated_items, feedback_signals=self.feedback_service.feedback_signals(profile_key, time.time()))
        groups = self._taste_groups(records, self.repository.feedback_rows(profile_key))
        self._attach_taste_evidence(groups, records)
        return _sanitize_catalog_payload({"schema_version": SCHEMA_VERSION, "profile_key": profile_key, "summary": profile.summary(), "groups": groups})

    def _library_counts(self, records: list[LibraryRecord]) -> dict[str, int]:
        counts = {"all": len(records), "watched": 0, "wish": 0, "candidate": 0, "rated": 0}
        for record in records:
            state = str(record.state or "").strip()
            if state in {"watched", "wish", "candidate"}:
                counts[state] += 1
            if state == "wanted":
                counts["wish"] += 1
        counts["rated"] = sum(record.item.my_rating is not None for record in records)
        return counts

    def _visible_library_records(
        self,
        records: list[LibraryRecord],
        *,
        media_entity_ids: dict[str, str],
        poster_overrides: dict[str, dict[str, Any]],
    ) -> tuple[list[LibraryRecord], int]:
        visible_records: list[LibraryRecord] = []
        hidden_candidates = 0
        personal_douban_ids = {
            str(record.item.douban_id or "").strip()
            for record in records
            if record.state != "candidate" and str(record.item.douban_id or "").strip().isdigit()
        }
        for record in records:
            if record.state != "candidate":
                visible_records.append(record)
                continue
            candidate_douban_id = str(record.item.douban_id or "").strip()
            if candidate_douban_id.isdigit() and candidate_douban_id in personal_douban_ids:
                hidden_candidates += 1
                continue
            if catalog_quality_reasons(record.item):
                hidden_candidates += 1
                continue
            if not self._still_assets(record):
                hidden_candidates += 1
                continue
            entity_id = media_entity_ids.get(record.item_key) or record.item_key
            poster_override = poster_overrides.get(entity_id)
            poster = (
                self._manifest_media_asset(poster_override, "poster")
                if poster_override
                else self._media_asset_from_override(None, "poster", record.payload.get("cover"))
            )
            if (
                not isinstance(poster, dict)
                or poster.get("media_status") != "ready"
                or not _safe_media_route(str(poster.get("url") or ""))
            ):
                hidden_candidates += 1
                continue
            visible_records.append(record)
        visible_records, duplicates = _collapse_duplicate_records(visible_records)
        hidden_candidates += sum(record.state == "candidate" for record in duplicates)
        return visible_records, hidden_candidates

    def _attach_taste_evidence(
        self,
        groups: dict[str, list[dict[str, object]]],
        records: list[LibraryRecord],
    ) -> None:
        title_by_id = {record.item_key: record.item.title for record in records}
        for signals in groups.values():
            for signal in signals:
                evidence_ids = _dedupe(list(signal.get("evidence_item_ids") or []))
                signal["evidence_count"] = len(evidence_ids)
                signal["evidence_titles"] = [
                    {"id": evidence_id, "title": title_by_id.get(evidence_id) or "已记录作品"}
                    for evidence_id in evidence_ids[:4]
                ]

    def search_titles(
        self,
        query: str,
        limit: int = 4,
        media_hint: str = "",
    ) -> dict[str, object]:
        clean_query = str(query or "").strip()
        if not clean_query:
            raise ExplorationError("query is required")
        if len(clean_query) > 120:
            raise ExplorationError("query is too long")
        clean_limit = self._validate_limit(limit, 1, 8, field="limit")
        canonical_hint = canonical_media_type(media_hint)
        scored: list[tuple[tuple[float, ...], LibraryRecord, str]] = []
        records, _ = _collapse_duplicate_records(self._library_records_snapshot())
        for record in records:
            match_kind, match_score = _title_match(record.item, clean_query)
            if not match_kind:
                continue
            media_match = 1.0 if canonical_hint and record.item.media_type == canonical_hint else 0.0
            history_match = 1.0 if _record_is_seen(record) else 0.0
            rating = max(0.0, min(10.0, float(record.item.douban_rating or 0)))
            popularity = math.log10(max(0, int(record.item.vote_count or 0)) + 1)
            year = float(record.item.year or 0)
            scored.append((
                (match_score, media_match, history_match, popularity, rating, year),
                record,
                match_kind,
            ))
        scored.sort(key=lambda row: tuple(-value for value in row[0]) + (row[1].item_key,))
        items = []
        for score, record, match_kind in scored[:clean_limit]:
            payload = self._discovery_item_payload(record)
            payload.update({
                "match_kind": match_kind,
                "media_hint_match": bool(canonical_hint and record.item.media_type == canonical_hint),
            })
            items.append(payload)
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "query": clean_query,
            "media_hint": canonical_hint,
            "items": items,
        })

    def similar_titles(
        self,
        focus_id: str,
        *,
        mode: str = "balanced",
        intent: RecommendationIntent | dict[str, object] | None = None,
        limit: int = 12,
        require_poster: bool = False,
    ) -> dict[str, object]:
        focus = self.find_title(focus_id)
        live_focus: dict[str, object] | None = None
        if focus is None:
            live_focus = self._find_latest_discovery_item(focus_id)
            if live_focus is None:
                raise ExplorationNotFound("focus not found")
            focus = self._latest_discovery_record(live_focus)
        focus = _enrich_discovery_record(focus)
        clean_limit = self._validate_limit(limit, 1, 30, field="limit")
        parsed_intent = intent if isinstance(intent, RecommendationIntent) else RecommendationIntent.from_dict(intent)
        clean_mode = _discovery_mode(mode or parsed_intent.similarity_mode)
        ranked = self._rank_discovery_records(
            focus=focus,
            intent=parsed_intent,
            mode=clean_mode,
            exclude_ids={focus.item_key},
        )
        items: list[dict[str, object]] = []
        seen_title_types: set[str] = set()
        for score, record, evidence in ranked:
            payload = self._discovery_item_payload(record)
            if not _has_publishable_discovery_title(payload):
                continue
            if require_poster and not _has_renderable_poster(payload):
                continue
            visible_title_key = _discovery_title_key(payload.get("display_title") or payload.get("title"))
            visible_media_type = canonical_media_type(payload.get("media_type"))
            title_type_key = f"{visible_title_key}|{visible_media_type}" if visible_title_key and visible_media_type else ""
            if title_type_key and title_type_key in seen_title_types:
                continue
            if title_type_key:
                seen_title_types.add(title_type_key)
            reason_evidence = _similar_reason_evidence(record.item, evidence, score)
            explanation = _similar_explanation(
                focus.item,
                record.item,
                evidence,
                parsed_intent,
                score=score,
                reason_evidence=reason_evidence,
            )
            payload.update({
                "rank_score": round(score, 5),
                "evidence": evidence,
                "primary_reason": explanation,
                "reason_evidence": reason_evidence,
                "reason_chips": [
                    f"{row['label']} · {row['value']}"
                    for row in reason_evidence[:3]
                ],
                "explanation": explanation,
            })
            items.append(payload)
            if len(items) >= clean_limit:
                break
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "mode": clean_mode,
            "focus": _localized_latest_discovery_item(live_focus) if live_focus is not None else self._discovery_item_payload(focus),
            "items": items,
        })

    def _build_multi_focus_rank_snapshot(self, clean_ids: Sequence[str]) -> dict[str, object]:
        """Build the expensive, identity-collapsed multi-focus ranking once.

        The UI can request several presentation batches from the same focus
        set.  Keeping the vectors, candidate connections and batched media
        context together avoids rescanning the complete catalog for every
        click on “换一批”.
        """

        # Ranking should not be held hostage by sparse provider payloads.  We
        # enrich records in-memory from the trusted curated catalog (and a
        # few explicit discovery fields) while keeping SQLite untouched.  The
        # resulting virtual records are used for both feature extraction and
        # the final serializer, so the explanation and the visible metadata
        # stay in lock-step.
        local_records = [
            _enrich_discovery_record(record)
            for record in self._library_records_snapshot()
        ]
        local_by_key = {record.item_key: record for record in local_records}
        focuses: list[LibraryRecord] = []
        for focus_id in clean_ids:
            record = local_by_key.get(focus_id)
            if record is None:
                record = self.find_title(focus_id)
                if record is not None:
                    record = _enrich_discovery_record(record)
            if record is None:
                live = self._find_latest_discovery_item(focus_id)
                if live is None:
                    raise ExplorationNotFound("focus not found")
                record = _enrich_discovery_record(self._latest_discovery_record(live))
            record_tokens = set(recommendation_identity_tokens(record.item))
            if any(record_tokens.intersection(recommendation_identity_tokens(existing.item)) for existing in focuses):
                continue
            focuses.append(record)
        if not focuses:
            raise ExplorationNotFound("focus not found")

        focus_keys = {record.item_key for record in focuses}
        focus_prepared: dict[str, tuple[str, tuple[float, ...], dict[str, float], frozenset[str], float]] = {
            focus.item_key: self._prepared_discovery_features(focus)
            for focus in focuses
        }
        focus_tokens = set().union(*(set(focus_prepared[focus.item_key][3]) for focus in focuses))
        live_records = [
            _enrich_discovery_record(record)
            for record in self._cached_live_discovery_records()
        ]
        records, _ = _collapse_duplicate_records([*local_records, *live_records])
        serialization_context = self._discovery_serialization_context([*records, *focuses])
        ranked: list[MultiFocusCandidate] = []
        candidate_pool_size = 0
        for record in records:
            if record.item_key in focus_keys or _record_is_seen(record):
                continue
            if record.state in {"hidden", "archived"}:
                continue
            _candidate_text, candidate_vector, candidate_traits, candidate_tokens, quality = self._prepared_discovery_features(record)
            if focus_tokens.intersection(candidate_tokens):
                continue
            candidate_pool_size += 1
            connections: list[tuple[float, tuple[str, ...], bool]] = []
            connection_components: list[dict[str, float]] = []
            for focus in focuses:
                _focus_text, focus_vector, focus_traits, _focus_tokens, _focus_quality = focus_prepared[focus.item_key]
                similarity, evidence, details = _item_similarity_details(
                    focus.item,
                    record.item,
                    left_vector=focus_vector,
                    right_vector=candidate_vector,
                    left_traits=focus_traits,
                    right_traits=candidate_traits,
                )
                matched = _is_meaningful_focus_match(
                    focus.item,
                    record.item,
                    similarity,
                    evidence,
                    details=details,
                )
                evidence_copy = list(evidence)
                if matched and details.get("structural", 0.0) < 0.16:
                    evidence_copy.append("语义桥接：叙事与气质相近")
                connections.append((similarity, tuple(_dedupe(evidence_copy)), matched))
                connection_components.append(details)
            matched_count = sum(connection[2] for connection in connections)
            if matched_count <= 0:
                continue
            similarities = [connection[0] for connection in connections]
            average_similarity = sum(similarities) / len(similarities)
            bridge_similarity = min(similarities)
            match_ratio = matched_count / len(focuses)
            score = average_similarity * 0.52 + bridge_similarity * 0.22 + match_ratio * 0.16 + quality * 0.10
            is_intersection = matched_count == len(focuses)
            ranked.append(MultiFocusCandidate(
                record=record,
                connections=tuple(connections),
                matched_count=matched_count,
                score=score,
                quality=quality,
                is_intersection=is_intersection,
                components=tuple(connection_components),
                item=record.item,
            ))

        ranked.sort(key=lambda row: (-int(row.is_intersection), -row.matched_count, -row.score, -row.quality, row.record.item_key))
        return {
            "focuses": focuses,
            "ranked": ranked,
            "serialization_context": serialization_context,
            "candidate_pool_size": candidate_pool_size,
            "strict_pool_size": sum(candidate.is_intersection for candidate in ranked),
        }

    def _candidate_has_renderable_poster(
        self,
        record: LibraryRecord,
        serialization_context: dict[str, dict[str, object]],
    ) -> bool:
        """Check poster readiness without serializing the entire candidate.

        ``complete_media=1`` is a presentation contract: cards without a
        verified poster must not consume a slot.  Filtering only after a
        batch was selected caused the first graph page to contain two cards
        even though dozens of later candidates had usable posters.  This
        bounded check lets the selector choose from the renderable pool and
        keeps the ranking cache independent from media hydration.
        """

        context = serialization_context.get(record.item_key) or {}
        assets = context.get("assets") if isinstance(context.get("assets"), dict) else {}
        override = assets.get("poster") if isinstance(assets, dict) else None
        if isinstance(override, dict) and self._manifest_media_asset(override, "poster").get("media_status") == "ready":
            return True

        direct = record.payload.get("cover") or record.item.cover
        if isinstance(direct, dict):
            direct = direct.get("url") or direct.get("localUrl") or direct.get("src")
        direct_text = str(direct or "").strip()
        if _safe_media_route(direct_text) or direct_text.startswith("/api/image-proxy?url="):
            return True
        return bool(_proxied_image_url(direct_text))

    def multi_focus_titles(
        self,
        focus_ids: Sequence[str],
        *,
        limit: int = 18,
        require_poster: bool = False,
        round_index: int = 0,
    ) -> dict[str, object]:
        started_at = time.perf_counter()
        clean_ids = _dedupe([str(value or "").strip() for value in focus_ids])[:3]
        if not clean_ids:
            raise ExplorationError("at least one focus is required")
        clean_limit = self._validate_limit(limit, 1, 30, field="limit")
        clean_round = self._clamp_int(round_index, 0, 0, 99)

        visibility_revision = self.repository.visibility_revision()
        with self._latest_discovery_lock:
            latest_revision = tuple(sorted(
                (
                    str(key),
                    round(float(snapshot.get("fetched_at") or snapshot.get("restored_at") or 0), 3),
                    len(snapshot.get("items") or []) if isinstance(snapshot.get("items"), list) else 0,
                )
                for key, snapshot in self._latest_discovery_cache.items()
                if isinstance(snapshot, dict)
            ))
        cache_key: tuple[object, ...] = (
            tuple(clean_ids),
            clean_limit,
            bool(require_poster),
            clean_round,
            visibility_revision,
            latest_revision,
        )
        now = time.time()
        with self._multi_focus_lock:
            expired = [key for key, (expires_at, _payload) in self._multi_focus_cache.items() if expires_at <= now]
            for key in expired:
                self._multi_focus_cache.pop(key, None)
            cached = self._multi_focus_cache.get(cache_key)
        if cached is not None:
            cached_payload = dict(cached[1])
            cached_payload["cache_hit"] = True
            cached_payload["calculation_ms"] = round((time.perf_counter() - started_at) * 1000.0, 2)
            return _sanitize_catalog_payload(cached_payload)

        rank_cache_key: tuple[object, ...] = (
            tuple(clean_ids),
            visibility_revision,
            latest_revision,
        )
        # Serialize a cold build per focus set.  Without holding the rank
        # cache lock across the miss path, two quick clicks (or two browser
        # tabs) could both scan and vectorise the 900-item catalogue before
        # either result was published.  Cache hits remain lock-only and the
        # lock is re-entrant for the bounded cache maintenance below.
        with self._multi_focus_rank_lock:
            rank_snapshot = self._multi_focus_rank_cache.get(rank_cache_key)
            rank_cache_hit = rank_snapshot is not None
            if rank_snapshot is None:
                rank_snapshot = self._build_multi_focus_rank_snapshot(clean_ids)
                self._multi_focus_rank_cache[rank_cache_key] = rank_snapshot
                while len(self._multi_focus_rank_cache) > MULTI_FOCUS_RANK_CACHE_MAX_ENTRIES:
                    self._multi_focus_rank_cache.pop(next(iter(self._multi_focus_rank_cache)))

        focuses = list(rank_snapshot.get("focuses") or [])
        ranked = list(rank_snapshot.get("ranked") or [])
        serialization_context = rank_snapshot.get("serialization_context") or {}
        candidate_pool_size = int(rank_snapshot.get("candidate_pool_size") or 0)
        strict_pool_size = int(rank_snapshot.get("strict_pool_size") or 0)
        batch_seed = "|".join(record.item_key for record in focuses)
        # Keep presentation filtering ahead of MMR selection.  Previously a
        # batch could spend slots on provider-only English titles and those
        # cards were discarded after the diversity pass, leaving a request for
        # 18 cards with only 16 visible results even though the ranked pool
        # still contained enough usable candidates.  The localized title
        # resolver is the same one used by ``_discovery_item_payload`` so the
        # selector and the renderer now agree on eligibility.
        publishable_ranked = [
            candidate
            for candidate in ranked
            if _record_has_publishable_discovery_title(candidate.record)
        ]
        selection_pool = publishable_ranked
        if require_poster:
            selection_pool = [
                candidate
                for candidate in publishable_ranked
                if self._candidate_has_renderable_poster(candidate.record, serialization_context)
            ]
        diversified = _select_multi_focus_batch(
            selection_pool,
            batch_size=clean_limit,
            round_index=clean_round,
            seed_key=batch_seed,
        )
        items: list[dict[str, object]] = []
        edges: list[dict[str, object]] = []
        selected_candidates: list[MultiFocusCandidate] = []
        for candidate in diversified:
            record = candidate.record
            connections = candidate.connections
            payload = self._discovery_item_payload(record, prefetched=serialization_context.get(record.item_key))
            if not _has_publishable_discovery_title(payload):
                continue
            if require_poster and not _has_renderable_poster(payload):
                continue
            matched_seed_ids = [
                focus.item_key
                for focus, connection in zip(focuses, connections)
                if connection[2]
            ]
            evidence_by_seed = {
                focus.item_key: connection[1]
                for focus, connection in zip(focuses, connections)
                if connection[1]
            }
            match_kind = (
                "similar"
                if len(focuses) == 1
                else "intersection" if candidate.is_intersection else "blend"
            )
            fusion_dimensions = _multi_focus_dimensions(focuses, record, connections)
            score_breakdown = _multi_focus_score_breakdown(candidate, focuses)
            explanation = _multi_focus_explanation(focuses, record, connections, candidate.is_intersection)
            payload.update({
                "rank_score": round(candidate.score, 5),
                "matched_seed_count": candidate.matched_count,
                "total_seed_count": len(focuses),
                "matched_seed_ids": matched_seed_ids,
                "match_kind": match_kind,
                "evidence_by_seed": evidence_by_seed,
                "fusion_dimensions": fusion_dimensions,
                "fusion_summary": _multi_focus_summary(fusion_dimensions, candidate.matched_count, len(focuses)),
                "score_breakdown": score_breakdown,
                "primary_reason": explanation,
                "reason_evidence": fusion_dimensions,
                "reason_chips": [
                    f"{row['label']} · {row['value']}"
                    for row in fusion_dimensions[:3]
                    if row.get("label") and row.get("value")
                ],
                "explanation": explanation,
            })
            items.append(payload)
            selected_candidates.append(candidate)
            for focus, (similarity, evidence, matched) in zip(focuses, connections):
                if not matched and similarity < 0.18:
                    continue
                reason = evidence[0] if evidence else f"语义接近《{focus.item.title}》"
                edges.append({
                    "source": focus.item_key,
                    "target": record.item_key,
                    "score": round(similarity, 5),
                    "reason": reason,
                    "reasons": evidence,
                    "matched": matched,
                })
            if len(items) >= clean_limit:
                break

        strict_count = sum(1 for item in items if item.get("match_kind") == "intersection")
        rating_count = sum(bool(item.get("source_ratings")) for item in items)
        source_mix = {
            "online": sum(bool(item.get("is_live")) for item in items),
            "local": sum(not bool(item.get("is_live")) for item in items),
        }
        seeds: list[dict[str, object]] = []
        for index, focus in enumerate(focuses):
            seed = self._discovery_item_payload(focus, prefetched=serialization_context.get(focus.item_key))
            seed.update({"id": focus.item_key, "item_key": focus.item_key, "is_seed": True, "seed_index": index})
            seeds.append(seed)
        graph_nodes = [*seeds, *[{**item, "id": item["item_key"]} for item in items]]
        selection_mode = "single" if len(focuses) == 1 else "intersection" if items and all(item["match_kind"] == "intersection" for item in items) else "hybrid"
        has_more = len(selection_pool) > (clean_round + 1) * clean_limit
        batch_count = math.ceil(len(selection_pool) / clean_limit) if selection_pool else 0
        result = {
            "schema_version": SCHEMA_VERSION,
            "selection_mode": selection_mode,
            "round": clean_round,
            "strict_count": strict_count,
            "strict_pool_size": strict_pool_size,
            "candidate_pool_size": candidate_pool_size,
            "matched_pool_size": len(ranked),
            "publishable_pool_size": len(publishable_ranked),
            "selection_pool_size": len(selection_pool),
            "rating_coverage": {
                "rated": rating_count,
                "total": len(items),
                "percent": round(rating_count / len(items) * 100.0, 1) if items else 0.0,
            },
            "source_mix": source_mix,
            "fusion_profile": _multi_focus_profile(focuses, candidate_pool_size, strict_pool_size),
            "seeds": seeds,
            "items": items,
            "graph": {
                "focus_id": focuses[0].item_key,
                "focus_ids": [focus.item_key for focus in focuses],
                "nodes": graph_nodes,
                "edges": edges,
            },
            # Batches are intentionally disjoint.  Report availability based
            # on the next complete batch instead of merely checking whether
            # the current rank list is longer than the rendered cards.
            "has_more": has_more,
            "next_round": clean_round + 1 if has_more else None,
            "batch_count": batch_count,
            "batch_size": clean_limit,
            "rank_cache_hit": rank_cache_hit,
            "cache_hit": False,
            "calculation_ms": round((time.perf_counter() - started_at) * 1000.0, 2),
        }
        sanitized = _sanitize_catalog_payload(result)
        with self._multi_focus_lock:
            self._multi_focus_cache[cache_key] = (now + MULTI_FOCUS_CACHE_TTL_SECONDS, dict(sanitized))
            while len(self._multi_focus_cache) > MULTI_FOCUS_CACHE_MAX_ENTRIES:
                self._multi_focus_cache.pop(next(iter(self._multi_focus_cache)))
        return sanitized

    def blend_titles(
        self,
        left_id: str,
        right_id: str,
        *,
        left_weight: float = 0.5,
        intent: RecommendationIntent | dict[str, object] | None = None,
        limit: int = 12,
    ) -> dict[str, object]:
        left = self.find_title(left_id)
        right = self.find_title(right_id)
        if left is None or right is None:
            raise ExplorationNotFound("blend source not found")
        if left.item_key == right.item_key:
            raise ExplorationError("blend sources must be different")
        clean_limit = self._validate_limit(limit, 1, 30, field="limit")
        try:
            weight = float(left_weight)
        except (TypeError, ValueError):
            weight = 0.5
        weight = max(0.05, min(0.95, weight))
        parsed_intent = intent if isinstance(intent, RecommendationIntent) else RecommendationIntent.from_dict(intent)
        ranked: list[tuple[float, LibraryRecord, list[str], list[str]]] = []
        for record in self._library_records_snapshot():
            if record.item_key in {left.item_key, right.item_key} or _record_is_seen(record):
                continue
            if record.state in {"hidden", "archived"} or _matches_avoid(record.item, parsed_intent):
                continue
            left_similarity, left_evidence = _item_similarity(left.item, record.item)
            right_similarity, right_evidence = _item_similarity(right.item, record.item)
            mood = _mood_axis_affinity(record.item, parsed_intent)
            quality = _quality_affinity(record.item)
            weighted_similarity = weight * left_similarity + (1.0 - weight) * right_similarity
            bridge = min(left_similarity, right_similarity)
            score = weighted_similarity * 0.74 + bridge * 0.12 + quality * 0.09 + mood * 0.05
            ranked.append((score, record, left_evidence, right_evidence))
        ranked.sort(key=lambda row: (-row[0], -_quality_affinity(row[1].item), row[1].item_key))
        items: list[dict[str, object]] = []
        for score, record, left_evidence, right_evidence in ranked[:clean_limit]:
            payload = self._discovery_item_payload(record)
            payload.update({
                "rank_score": round(score, 5),
                "evidence": _dedupe([*left_evidence, *right_evidence]),
                "explanation": _blend_explanation(
                    left.item,
                    right.item,
                    record.item,
                    left_evidence,
                    right_evidence,
                ),
            })
            items.append(payload)
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "left_weight": round(weight, 3),
            "right_weight": round(1.0 - weight, 3),
            "sources": [self._discovery_item_payload(left), self._discovery_item_payload(right)],
            "items": items,
        })

    def discover_from_query(
        self,
        text: str,
        *,
        selection_id: str = "",
        base_intent: RecommendationIntent | dict[str, object] | None = None,
        limit: int = 12,
    ) -> dict[str, object]:
        clean_text = str(text or "").strip()
        if not clean_text:
            raise ExplorationError("text is required")
        base = base_intent if isinstance(base_intent, RecommendationIntent) else RecommendationIntent.from_dict(base_intent)
        intent = parse_recommendation_intent(clean_text, base=base)
        clean_limit = self._validate_limit(limit, 1, 30, field="limit")
        chips = [asdict(chip) for chip in intent_to_chips(intent)]
        matched_reference: dict[str, object] | None = None
        alternatives: list[dict[str, object]] = []
        items: list[dict[str, object]] = []
        mode = _discovery_mode(intent.similarity_mode)
        if intent.reference_titles:
            media_hint = intent.media_types[0] if intent.media_types else ""
            matches = self.search_titles(intent.reference_titles[0], limit=4, media_hint=media_hint)["items"]
            selected_record = self.find_title(selection_id) if selection_id else None
            if selected_record is None and matches:
                selected_record = self.find_title(str(matches[0].get("item_key") or matches[0].get("id") or ""))
            if selected_record is not None:
                result = self.similar_titles(
                    selected_record.item_key,
                    mode=mode,
                    intent=intent,
                    limit=clean_limit,
                )
                matched_reference = result["focus"]
                items = list(result["items"])
                alternatives = [
                    match for match in matches
                    if str(match.get("item_key") or match.get("id") or "") != selected_record.item_key
                ]
        if matched_reference is None:
            ranked = self._rank_discovery_records(
                focus=None,
                intent=intent,
                mode=mode,
                exclude_ids=set(),
            )
            for score, record, evidence in ranked[:clean_limit]:
                payload = self._discovery_item_payload(record)
                payload.update({
                    "rank_score": round(score, 5),
                    "evidence": evidence,
                    "explanation": _query_explanation(record.item, evidence, intent),
                })
                items.append(payload)
        notice = ""
        if matched_reference:
            notice = (
                f"已匹配：{matched_reference.get('media_badge', {}).get('label') or matched_reference.get('media_type') or '作品'}"
                f" · {matched_reference.get('year') or '年份待补'}《{matched_reference.get('title') or ''}》"
            )
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "query": clean_text,
            "mode": mode,
            "intent": intent.to_dict(),
            "chips": chips,
            "matched_reference": matched_reference,
            "alternatives": alternatives,
            "match_notice": notice,
            "items": items,
        })

    def _rank_discovery_records(
        self,
        *,
        focus: LibraryRecord | None,
        intent: RecommendationIntent,
        mode: str,
        exclude_ids: set[str],
    ) -> list[tuple[float, LibraryRecord, list[str]]]:
        weights = {
            "faithful": (0.78, 0.12, 0.10),
            "balanced": (0.62, 0.22, 0.16),
            "surprise": (0.42, 0.34, 0.24),
        }[mode]
        ranked: list[tuple[float, LibraryRecord, list[str]]] = []
        records, _ = _collapse_duplicate_records([
            _enrich_discovery_record(record)
            for record in self._library_records_snapshot()
        ])
        focus_tokens = set(recommendation_identity_tokens(focus.item)) if focus is not None else set()
        for record in records:
            if record.item_key in exclude_ids or _record_is_seen(record):
                continue
            if focus_tokens and focus_tokens.intersection(recommendation_identity_tokens(record.item)):
                continue
            if record.state in {"hidden", "archived"} or _matches_avoid(record.item, intent):
                continue
            if focus is not None:
                similarity, evidence = _item_similarity(focus.item, record.item)
            else:
                similarity, evidence = _intent_affinity(record.item, intent)
            quality = _quality_affinity(record.item)
            mood = _mood_axis_affinity(record.item, intent)
            novelty = (1.0 - similarity) * max(0.0, min(1.0, intent.exploration_level))
            score = similarity * weights[0] + quality * weights[1] + mood * weights[2]
            if mode == "surprise":
                score += novelty * 0.12
            ranked.append((score, record, evidence))
        ranked.sort(key=lambda row: (-row[0], -_quality_affinity(row[1].item), row[1].item_key))
        return ranked

    def _discovery_item_payload(
        self,
        record: LibraryRecord,
        *,
        prefetched: dict[str, object] | None = None,
    ) -> dict[str, object]:
        is_live = record.state == "online" or record.source == "global-discovery"
        if is_live:
            localization = _title_localization(record.item)
            poster_url = str(record.payload.get("cover") or record.item.cover or "").strip()
            backdrop_url = str(record.payload.get("backdrop") or _raw_value(record.payload, "backdrop") or "").strip()
            serialized: dict[str, object] = {
                "id": record.item_key,
                "display_title": localization.get("display_title") or record.item.title,
                "original_title": localization.get("original_title") or record.item.title,
                "title_localization_source": localization.get("title_localization_source") or "online",
                "poster": {
                    "url": poster_url,
                    "media_status": "ready" if _usable_media_reference(poster_url) else "missing",
                },
                "backdrop": {
                    "url": backdrop_url,
                    "media_status": "ready" if _usable_media_reference(backdrop_url) else "missing",
                },
                "item": self._safe_item_payload(record),
            }
        else:
            identity_id = None
            assets = None
            if prefetched is not None:
                identity_id = str(prefetched.get("identity_id") or "")
                assets = prefetched.get("assets") if isinstance(prefetched.get("assets"), dict) else {}
            serialized = self.serialize_title(
                record,
                include_schema=False,
                include_people=False,
                identity_id=identity_id,
                prefetched_assets=assets,
            )
        item = serialized.get("item") if isinstance(serialized.get("item"), dict) else {}
        raw = record.item.raw if isinstance(record.item.raw, dict) else {}
        source_ratings = _rating_map(raw.get("ratings"))
        douban_rating = _finite_number(record.item.douban_rating)
        if douban_rating is not None and douban_rating > 0:
            source_ratings.setdefault("douban", round(douban_rating, 2))
        rating_votes = _vote_map(raw.get("rating_votes"))
        fused = fused_rating(record.item)
        discovery_sources = [
            str(value or "").strip()
            for value in raw.get("discovery_sources", [])
            if str(value or "").strip()
        ] if isinstance(raw.get("discovery_sources"), (list, tuple, set)) else []
        source_labels = [
            str(value or "").strip()
            for value in raw.get("source_labels", [])
            if str(value or "").strip()
        ] if isinstance(raw.get("source_labels"), (list, tuple, set)) else []
        return {
            "id": record.item_key,
            "catalog_id": serialized.get("id") or record.item_key,
            "item_key": record.item_key,
            "title": record.item.title,
            "display_title": str(serialized.get("display_title") or record.item.title),
            "original_title": str(serialized.get("original_title") or record.item.title),
            "title_localization_source": str(serialized.get("title_localization_source") or ""),
            "year": record.item.year,
            "media_type": record.item.media_type,
            "media_badge": _media_badge(record.item.media_type, record.item.genres),
            "countries": list(record.item.countries),
            "genres": list(record.item.genres),
            "douban_rating": record.item.douban_rating,
            "vote_count": _positive_int(record.item.vote_count) or sum(rating_votes.values()),
            "source_ratings": source_ratings,
            "rating_votes": rating_votes,
            "fused_rating": fused.rating,
            "rating_confidence": fused.confidence,
            "summary": str(item.get("summary") or record.item.summary or ""),
            "poster": serialized.get("poster") or {"url": "", "media_status": "missing"},
            "backdrop": serialized.get("backdrop") or {"url": "", "media_status": "missing"},
            "is_live": is_live,
            "online": is_live,
            "discovery_sources": discovery_sources,
            "source_labels": source_labels,
        }

    def build_universe_graph(self, focus_id: str, limit: int = 9) -> dict[str, object]:
        clean_limit = self._clamp_int(limit, 9, 3, 25)
        focus = self.find_title(focus_id)
        live_focus: dict[str, object] | None = None
        if focus is None:
            live_focus = self._find_latest_discovery_item(focus_id)
            if live_focus is None:
                raise ExplorationNotFound("focus not found")
            focus = self._latest_discovery_record(live_focus)
        scored: list[tuple[float, str, LibraryRecord, list[str]]] = []
        focus_features = _relation_features(focus.item)
        focus_tokens = set(recommendation_identity_tokens(focus.item))
        records, _ = _collapse_duplicate_records(self._library_records_snapshot())
        for record in records:
            if record.item_key == focus.item_key:
                continue
            if focus_tokens.intersection(recommendation_identity_tokens(record.item)):
                continue
            shared = _shared_reasons(focus_features, _relation_features(record.item))
            if shared and all(field == "media_type" for field, _ in shared):
                shared = []
            if not shared:
                continue
            score = round(sum(RELATION_WEIGHTS.get(field, 0.5) for field, _ in shared), 4)
            scored.append((score, record.item_key, record, [f"{_reason_label(field)}: {value}" for field, value in shared]))
        scored.sort(key=lambda row: (-row[0], row[1]))
        selected = scored[: max(0, clean_limit - 1)]
        if live_focus is not None:
            live_node = _localized_latest_discovery_item(live_focus)
            focus_node = {
                "id": focus.item_key,
                "title": str(live_node.get("display_title") or live_node.get("title") or ""),
                "media_type": focus.item.media_type,
                "media_badge": live_node.get("media_badge") or _media_badge(focus.item.media_type, focus.item.genres),
                "year": focus.item.year,
                "poster": live_node.get("poster") or {"url": "", "media_status": "missing"},
                "online": True,
            }
        else:
            focus_node = self._node_payload(focus)
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "focus_id": focus.item_key,
            "limit": clean_limit,
            "nodes": [focus_node] + [self._node_payload(row[2]) for row in selected],
            "edges": [{"source": focus.item_key, "target": row[2].item_key, "score": row[0], "reason": row[3][0], "reasons": row[3]} for row in selected],
        })

    def find_title(self, lookup_id: str) -> LibraryRecord | None:
        lookup = str(lookup_id or "").strip()
        if not lookup:
            return None
        direct = self.repository.library_record(lookup)
        if direct is not None:
            return direct
        records = self._library_records_snapshot()
        by_key = {record.item_key: record for record in records}
        if lookup in by_key:
            return by_key[lookup]
        douban_id = lookup.removeprefix("douban:") if lookup.startswith("douban:") else lookup if lookup.isdigit() else ""
        if douban_id:
            for record in records:
                if str(record.item.douban_id or "") == douban_id or record.item_key == f"douban:{douban_id}":
                    return record
        identity = self.repository.media_identity(lookup)
        if identity:
            item_key = str(identity.metadata.get("item_key") or "")
            if item_key in by_key:
                return by_key[item_key]
            provider_douban = self.repository.provider_ids("media", identity.id).get("douban", "")
            if provider_douban:
                for record in records:
                    if str(record.item.douban_id or "") == provider_douban:
                        return record
        for record in records:
            if str(record.payload.get("identity_id") or record.payload.get("media_identity_id") or "") == lookup:
                return record
        return None

    def serialize_title(
        self,
        record: LibraryRecord,
        *,
        include_schema: bool = True,
        include_people: bool = True,
        identity_id: str | None = None,
        prefetched_assets: dict[str, dict[str, Any] | None] | None = None,
    ) -> dict[str, object]:
        if identity_id is None:
            identity = self.repository.media_identity_for_item(record)
            resolved_identity_id = identity.id if identity else ""
        else:
            resolved_identity_id = str(identity_id or "")
        asset_entity_id = resolved_identity_id or record.item_key
        poster_legacy = self._legacy_media_value(record, "poster", include_equivalents=include_people)
        backdrop_legacy = self._legacy_media_value(record, "backdrop", include_equivalents=include_people)
        if prefetched_assets is None:
            poster = self._media_asset("media", asset_entity_id, "poster", poster_legacy)
            backdrop = self._media_asset("media", asset_entity_id, "backdrop", backdrop_legacy)
        else:
            poster = self._prefetched_media_asset(prefetched_assets.get("poster"), "poster", poster_legacy)
            backdrop = self._prefetched_media_asset(prefetched_assets.get("backdrop"), "backdrop", backdrop_legacy)
        title_localization = _title_localization(record.item)
        result: dict[str, object] = {
            "id": resolved_identity_id or record.item_key,
            "item_key": record.item_key,
            "state": record.state,
            "title": record.item.title,
            **title_localization,
            "media_type": record.item.media_type,
            "media_badge": _media_badge(record.item.media_type, record.item.genres),
            "year": record.item.year,
            "item": self._safe_item_payload(record),
            "poster": poster,
            "backdrop": backdrop,
            "stills": self._still_assets(record),
            "people": self._people_for_title(record) if include_people else [],
            "updated_at": record.updated_at,
        }
        return _sanitize_catalog_payload({"schema_version": SCHEMA_VERSION, **result} if include_schema else result)

    def _legacy_media_value(
        self,
        record: LibraryRecord,
        kind: str,
        *,
        include_equivalents: bool,
    ) -> object:
        direct = (
            record.payload.get("cover")
            if kind == "poster"
            else record.payload.get("backdrop") or _raw_value(record.payload, "backdrop")
        )
        if _usable_media_reference(direct) or not include_equivalents:
            return direct
        identity_tokens = set(recommendation_identity_tokens(record.item))
        if not identity_tokens:
            return direct
        candidates: list[tuple[tuple[object, ...], object]] = []
        for sibling in self._library_records_snapshot():
            if sibling.item_key == record.item_key:
                continue
            if not identity_tokens.intersection(recommendation_identity_tokens(sibling.item)):
                continue
            value = (
                sibling.payload.get("cover")
                if kind == "poster"
                else sibling.payload.get("backdrop") or _raw_value(sibling.payload, "backdrop")
            )
            if _usable_media_reference(value):
                candidates.append((_record_preference_key(sibling), value))
        return max(candidates, key=lambda row: row[0])[1] if candidates else direct

    def _prefetched_media_asset(
        self,
        override: dict[str, Any] | None,
        kind: str,
        legacy_value: object = "",
    ) -> dict[str, str]:
        if override:
            return self._manifest_media_asset(override, kind)
        return self._media_asset_from_override(None, kind, legacy_value)

    def _safe_item_payload(self, record: LibraryRecord) -> dict[str, object]:
        payload = media_item_to_dict(record.item)
        metadata = curated_metadata_for_title(payload.get("title", ""), payload.get("douban_id", ""))
        if not payload.get("genres"):
            genres = metadata.get("genres") if isinstance(metadata.get("genres"), list) else []
            payload["genres"] = [str(value).strip() for value in genres if str(value).strip()]
        if not payload.get("genres"):
            payload["genres"] = [str(payload.get("media_type") or "作品").strip() or "作品"]
        curated_summary = str(metadata.get("summary") or "").strip()
        current_summary = str(payload.get("summary") or "").strip()
        if curated_summary and (not current_summary or _is_largely_latin_summary(current_summary)):
            payload["summary"] = curated_summary
        elif not current_summary:
            payload["summary"] = (
                f"正在补齐这部{payload.get('media_type') or '作品'}的剧情简介；"
                f"目前已确认类型为{' / '.join(payload.get('genres') or ['作品'])}。"
            )
        raw = record.item.raw if isinstance(record.item.raw, dict) else {}
        duration = raw.get("duration")
        if isinstance(duration, int) and 0 < duration < 1000:
            payload["duration"] = duration
        release_date = str(raw.get("release_date") or "").strip()
        if re.fullmatch(r"\d{4}-\d{2}-\d{2}", release_date):
            payload["release_date"] = release_date
        payload["url"] = ""
        payload["cover"] = ""
        source = str(record.item.source or "").strip()
        payload["source"] = "" if "://" in source else source
        payload["raw"] = self._safe_raw(record.payload)
        return _sanitize_catalog_payload(payload)

    def _still_assets(self, record: LibraryRecord) -> list[dict[str, str]]:
        raw = record.payload.get("raw") if isinstance(record.payload.get("raw"), dict) else {}
        values = raw.get("stills") if isinstance(raw.get("stills"), list) else []
        assets: list[dict[str, str]] = []
        for index, value in enumerate(values[:8]):
            url = str(value or "").strip()
            if url.startswith("/media/") and _safe_media_route(url):
                assets.append({"id": f"still-{index}", "url": url, "media_status": "ready"})
                continue
            proxy_url = _proxied_image_url(url)
            if not proxy_url:
                continue
            assets.append({
                "id": f"still-{index}",
                "url": proxy_url,
                "media_status": "ready",
            })
        return assets

    def _people_for_title(self, record: LibraryRecord) -> list[dict[str, object]]:
        people: list[dict[str, object]] = []
        raw = record.item.raw if isinstance(record.item.raw, dict) else {}
        photo_map = raw.get("people_photos") if isinstance(raw.get("people_photos"), dict) else {}
        for role, names in (("director", record.item.directors), ("cast", record.item.casts)):
            for name in names:
                person_id = self._person_id_for_name(name)
                portrait = self._person_asset(person_id, name)
                if portrait["media_status"] != "ready":
                    raw_photo = photo_map.get(name)
                    proxy_url = "" if _is_placeholder_portrait_url(raw_photo) else _proxied_image_url(raw_photo)
                    if proxy_url:
                        portrait = {"url": proxy_url, "media_status": "ready"}
                people.append({"id": person_id, "role": role, "name": name, "portrait": portrait, "media_status": portrait["media_status"], "evidence_title_ids": [record.item_key]})
        return people

    def _derive_person(self, lookup_id: str, identity: dict[str, Any] | None):
        person_id, name, aliases, metadata = lookup_id, "", [], {}
        if identity:
            person_id, name = str(identity["id"]), str(identity["name"])
            aliases, metadata = list(identity.get("aliases") or []), dict(identity.get("metadata") or {})
        else:
            name = _name_from_derived_id(lookup_id)
        evidence = [record for record in self._library_records_snapshot() if name and self._roles_for_person(record, name)]
        if not identity and not evidence:
            return None
        return person_id, name, aliases, metadata, evidence

    def _roles_for_person(self, record: LibraryRecord, name: str) -> list[str]:
        roles = []
        if name in record.item.directors:
            roles.append("director")
        if name in record.item.casts:
            roles.append("cast")
        return roles

    def _person_id_for_name(self, name: str) -> str:
        existing_id = self.repository.person_id_by_name(name)
        if existing_id:
            return existing_id
        slug = base64.urlsafe_b64encode(str(name).encode("utf-8")).decode("ascii").rstrip("=")
        return f"derived:{slug}"

    def _person_asset(self, person_id: str, name: str) -> dict[str, str]:
        return self._media_asset("person", person_id, "portrait", "")

    def _media_asset(self, entity_kind: str, entity_id: str, kind: str, legacy_value: object = "") -> dict[str, str]:
        override = self.repository.asset_override(entity_kind, entity_id, kind) if entity_id else None
        return self._media_asset_from_override(override, kind, legacy_value)

    def _media_asset_from_override(
        self,
        override: dict[str, Any] | None,
        kind: str,
        legacy_value: object = "",
    ) -> dict[str, str]:
        if override:
            local = self._local_asset_url(override, kind)
            return {"url": local, "media_status": "ready" if local else "missing"}
        legacy = str(legacy_value or "").strip()
        legacy_asset = _parse_media_route(legacy)
        if legacy_asset:
            asset_id, extension = legacy_asset
            row = self.repository.asset_for_route(asset_id, extension)
            local = self._local_asset_url(row or {}, kind)
            return {"url": local, "media_status": "ready" if local else ("designed-fallback" if kind == "poster" else "missing")}
        if legacy.startswith("data:image/"):
            return {"url": "", "media_status": "designed-fallback"}
        if legacy:
            proxy_url = _proxied_image_url(legacy)
            if proxy_url:
                return {"url": proxy_url, "media_status": "ready"}
            return {"url": "", "media_status": "designed-fallback" if kind == "poster" else "missing"}
        return {"url": "", "media_status": "missing"}

    def _manifest_media_asset(self, row: dict[str, Any], kind: str) -> dict[str, str]:
        """Resolve an already-validated local asset without decoding it again.

        Candidate visibility touches hundreds of posters. Full pixel validation
        still happens when a visible poster is serialized or served, while this
        bounded manifest check keeps pagination responsive.
        """

        asset_id = str(row.get("asset_id") or "").strip().lower()
        extension = str(row.get("extension") or "").strip().lower()
        relative_path = str(row.get("relative_path") or "").strip()
        decision = str(row.get("decision") or "").strip().lower()
        asset_kind = str(row.get("kind") or "").strip().lower()
        status = str(row.get("status") or "").strip().lower()
        try:
            byte_size = int(row.get("byte_size") or 0)
        except (TypeError, ValueError):
            byte_size = 0
        expected_relative = f"{asset_id[:2]}/{asset_id}{extension}" if asset_id and extension else ""
        if (
            not re.fullmatch(r"[0-9a-f]{64}", asset_id)
            or decision not in APPROVED_ASSET_DECISIONS
            or asset_kind not in {kind, "shared"}
            or status != "ready"
            or not re.fullmatch(r"\.(?:avif|gif|jpe?g|png|webp)", extension)
            or relative_path != expected_relative
            or "\\" in relative_path
            or byte_size <= 0
        ):
            return {"url": "", "media_status": "missing"}
        path = (self.media_root / Path(*relative_path.split("/"))).resolve()
        try:
            if self.media_root != path and self.media_root not in path.parents:
                return {"url": "", "media_status": "missing"}
            if not path.is_file() or path.stat().st_size != byte_size:
                return {"url": "", "media_status": "missing"}
        except OSError:
            return {"url": "", "media_status": "missing"}
        return {"url": f"/media/{asset_id}{extension}", "media_status": "ready"}

    def _local_asset_url(self, row: dict[str, Any], kind: str) -> str:
        asset_id = str(row.get("asset_id") or "").strip().lower()
        relative_path = str(row.get("relative_path") or "").strip()
        extension = str(row.get("extension") or "") or Path(relative_path).suffix
        decision = str(row.get("decision") or "selected").strip().lower()
        if (
            not re.fullmatch(r"[0-9a-f]{64}", asset_id)
            or decision not in APPROVED_ASSET_DECISIONS
        ):
            return ""
        stored = self.media_store.lookup(f"{asset_id}{extension}")
        if stored is None or stored.kind not in {kind, "shared"} or stored.status != "ready":
            return ""
        return stored.local_url

    def _safe_raw(self, payload: dict[str, Any]) -> dict[str, object]:
        allowed: dict[str, object] = {}
        for key in ("people_photos", "backdrop"):
            if key in payload:
                allowed[key] = _strip_external(payload[key])
        raw = payload.get("raw")
        if isinstance(raw, dict):
            for key in (
                "people", "credits", "comment", "short_comment", "review",
                "ratings", "rating_votes", "provider_ids", "aliases", "original_title",
                "comment_count", "review_count", "summary_original", "summary_source", "summary_generated",
                "summary_translation_version", "activity_date", "watched_date", "wish_date",
                "in_progress_date", "watched_at", "watch_progress", "episodes_watched", "total_episodes",
            ):
                if key in raw:
                    allowed[key] = _strip_external(raw[key])
        return allowed

    def _node_payload(self, record: LibraryRecord) -> dict[str, object]:
        identity = self.repository.media_identity_for_item(record)
        return {
            "id": record.item_key,
            "title": record.item.title,
            "media_type": record.item.media_type,
            "media_badge": _media_badge(record.item.media_type, record.item.genres),
            "year": record.item.year,
            "poster": self._media_asset(
                "media",
                identity.id if identity else record.item_key,
                "poster",
                record.payload.get("cover"),
            ),
        }

    def _taste_groups(self, records: list[LibraryRecord], feedback_rows: list[dict[str, Any]]) -> dict[str, list[dict[str, object]]]:
        positive: dict[str, dict[str, Any]] = {}
        negative: dict[str, dict[str, Any]] = {}
        recent: dict[str, dict[str, Any]] = {}
        unexplored: dict[str, dict[str, Any]] = {}

        def add(bucket: dict[str, dict[str, Any]], feature: str, weight: float, item_key: str, source: str) -> None:
            row = bucket.setdefault(feature, {"feature": feature, "score": 0.0, "evidence_item_ids": [], "sources": []})
            row["score"] = round(float(row["score"]) + weight, 4)
            if item_key and item_key not in row["evidence_item_ids"]:
                row["evidence_item_ids"].append(item_key)
            if source and source not in row["sources"]:
                row["sources"].append(source)

        for record in records:
            rating = record.item.my_rating
            features = _preference_features(record.item)
            if rating is not None and float(rating) >= 4.0:
                for feature in features:
                    add(positive, feature, float(rating), record.item_key, "library-rating")
                    add(recent, feature, float(rating), record.item_key, "library-rating")
            elif rating is not None and float(rating) <= 2.5:
                for feature in features:
                    add(negative, feature, 3.0 - float(rating), record.item_key, "library-rating")
                    add(recent, feature, 3.0 - float(rating), record.item_key, "library-rating")
            elif {tag.lower() for tag in record.item.tags} & {"wish", "wanted", "想看", "鎯崇湅"} or record.state in {"wish", "wanted"}:
                for feature in features[:4]:
                    add(unexplored, feature, 1.0, record.item_key, "wishlist")

        undone = {str(_json_object(row.get("payload_json")).get("target_event_id") or "") for row in feedback_rows if row.get("event_type") == "undo"}
        for row in feedback_rows:
            event_id = str(row.get("id") or "")
            event_type = str(row.get("event_type") or "")
            if event_type == "undo" or event_id in undone:
                continue
            item_key = str(row.get("item_key") or "")
            features = _payload_features(_json_object(row.get("payload_json"))) or ([f"item:{item_key}"] if item_key else [])
            for feature in features:
                if event_type in {"more-like-this", "want"}:
                    add(positive, feature, 2.0, item_key, "feedback")
                    add(recent, feature, 2.0, item_key, "feedback")
                elif event_type in {"less-like-this", "permanent-avoid"}:
                    add(negative, feature, 2.0, item_key, "feedback")
                    add(recent, feature, 2.0, item_key, "feedback")
                elif event_type in SESSION_ONLY_EVENT_TYPES:
                    continue

        conflicts: dict[str, dict[str, Any]] = {}
        for feature in sorted(set(positive) & set(negative)):
            pos, neg = positive[feature], negative[feature]
            conflicts[feature] = {"feature": feature, "score": round(float(pos["score"]) + float(neg["score"]), 4), "evidence_item_ids": _dedupe([*pos["evidence_item_ids"], *neg["evidence_item_ids"]]), "sources": _dedupe([*pos["sources"], *neg["sources"]])}
            positive.pop(feature, None)
        if not unexplored:
            for record in records:
                if record.item.my_rating is None:
                    for feature in _preference_features(record.item)[:2]:
                        add(unexplored, feature, 1.0, record.item_key, "unrated")
        return {"stable": _top_signals(positive, 12), "conflicting": _top_signals(conflicts, 8), "recent": _top_signals(recent, 12), "negative": _top_signals(negative, 12), "unexplored": _top_signals(unexplored, 12)}

    def _validate_state(self, value: str) -> str:
        state = str(value or "all").strip() or "all"
        if not SAFE_STATE_RE.fullmatch(state) or state not in ALLOWED_LIBRARY_STATES:
            raise ExplorationError("invalid state")
        return state

    def _validate_limit(self, value: int, minimum: int, maximum: int, *, field: str) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError) as exc:
            raise ExplorationError(f"invalid {field}") from exc
        if parsed < minimum or parsed > maximum:
            raise ExplorationError(f"invalid {field}")
        return parsed

    def _clamp_int(self, value: int, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    def _encode_cursor(self, record: LibraryRecord) -> str:
        raw = json.dumps({"updated_at": record.updated_at, "item_key": record.item_key}, separators=(",", ":")).encode("utf-8")
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def _decode_cursor(self, value: str) -> tuple[float, str]:
        try:
            padded = str(value) + "=" * (-len(str(value)) % 4)
            decoded = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
            if not isinstance(decoded, dict) or set(decoded) != {"updated_at", "item_key"}:
                raise ValueError("invalid cursor shape")
            updated_at = float(decoded["updated_at"])
            item_key = str(decoded["item_key"] or "").strip()
            if not math.isfinite(updated_at) or not item_key:
                raise ValueError("invalid cursor value")
            return updated_at, item_key
        except Exception as exc:
            raise ExplorationError("invalid cursor") from exc


def _normalize_title_text(value: object) -> str:
    text = str(value or "").casefold().strip()
    return re.sub(r"[\s·:：\-—_（）()《》\[\]【】'\"“”]+", "", text)


def _contains_han(value: object) -> bool:
    return bool(re.search(r"[\u3400-\u9fff]", str(value or "")))


def _is_unlocalized_latin_title(value: object) -> bool:
    """Reject Latin-script provider titles that have no verified localization."""

    text = str(value or "").strip()
    if not text or _contains_han(text):
        return False
    letters = [char for char in text if char.isalpha()]
    if len(letters) < 2:
        return False
    ascii_latin = sum(char.isascii() and char.isalpha() for char in letters)
    return ascii_latin / len(letters) >= 0.75


def _title_source(item: MediaItem) -> str:
    raw = item.raw if isinstance(item.raw, dict) else {}
    provider_ids = raw.get("provider_ids") if isinstance(raw.get("provider_ids"), dict) else {}
    if str(provider_ids.get("douban") or "").strip() or str(item.douban_id or "").strip().isdigit():
        return "douban"
    discovery_sources = raw.get("discovery_sources")
    if isinstance(discovery_sources, str):
        discovery_sources = [discovery_sources]
    if isinstance(discovery_sources, (list, tuple, set)):
        for value in discovery_sources:
            provider = re.sub(r"[^a-z0-9._-]+", "", str(value or "").strip().casefold())
            if provider:
                return provider
    for provider in ("tmdb", "tvmaze", "anilist", "jikan", "imdb"):
        if str(provider_ids.get(provider) or "").strip():
            return provider
    return ""


def _title_localization(item: MediaItem) -> dict[str, str]:
    title = str(item.title or "").strip()
    raw = item.raw if isinstance(item.raw, dict) else {}
    raw_original = str(raw.get("original_title") or "").strip()
    aliases = _title_aliases(item)
    original_title = raw_original
    if not original_title:
        if title and not _contains_han(title):
            original_title = title
        else:
            original_title = next((value for value in aliases if not _contains_han(value)), title)

    provider_ids = raw.get("provider_ids") if isinstance(raw.get("provider_ids"), dict) else {}
    provider_title = next(
        (
            localized
            for provider, provider_id in provider_ids.items()
            if (localized := curated_display_title_for_provider(provider, provider_id))
        ),
        "",
    )
    if provider_title:
        return {
            "display_title": to_simplified_chinese(provider_title),
            "original_title": original_title or title or provider_title,
            "title_localization_source": "curated_catalog",
        }

    if is_reliable_chinese_title(title):
        return {
            "display_title": to_simplified_chinese(title),
            "original_title": original_title or title,
            "title_localization_source": _title_source(item) or "catalog",
        }

    curated_title = next(
        (
            localized
            for provider, provider_id in provider_ids.items()
            if (localized := curated_display_title_for_provider(provider, provider_id))
        ),
        "",
    )
    if not curated_title:
        external_id = str(item.douban_id or "").strip()
        provider_match = re.fullmatch(r"([a-z0-9]+)-(.+)", external_id, flags=re.I)
        if provider_match:
            curated_title = curated_display_title_for_provider(provider_match.group(1), provider_match.group(2))
    if curated_title:
        return {
            "display_title": to_simplified_chinese(curated_title),
            "original_title": original_title or title,
            "title_localization_source": "curated_catalog",
        }

    source = _title_source(item)
    localized_alias = next((value for value in aliases if is_reliable_chinese_title(value)), "") if source else ""
    return {
        "display_title": to_simplified_chinese(localized_alias or title),
        "original_title": original_title or title,
        "title_localization_source": source if localized_alias else "",
    }


def _usable_media_reference(value: object) -> bool:
    text = str(value or "").strip()
    if not text or text.startswith("data:image/"):
        return False
    return bool(
        text.startswith("/media/")
        or text.startswith("/api/image-proxy?url=")
        or re.match(r"^https?://", text, flags=re.I)
    )


def _discovery_provider_ids(payload: dict[str, object]) -> dict[str, str]:
    raw = payload.get("raw") if isinstance(payload.get("raw"), dict) else {}
    raw_provider_ids = raw.get("provider_ids") if isinstance(raw.get("provider_ids"), dict) else {}
    provider_ids = {
        re.sub(r"[^a-z0-9._~-]+", "", str(provider or "").casefold()): str(provider_id or "").strip()
        for provider, provider_id in raw_provider_ids.items()
        if str(provider or "").strip() and str(provider_id or "").strip()
    }
    direct_ids = payload.get("provider_ids") if isinstance(payload.get("provider_ids"), dict) else {}
    for provider, provider_id in direct_ids.items():
        clean_provider = re.sub(r"[^a-z0-9._~-]+", "", str(provider or "").casefold())
        clean_id = str(provider_id or "").strip()
        if clean_provider and clean_id:
            provider_ids.setdefault(clean_provider, clean_id)

    item_key = str(payload.get("item_key") or payload.get("id") or "").strip()
    patterns = (
        ("apple_movies", r"^external:apple-movie-(.+)$"),
        ("anilist", r"^external:anilist-(.+)$"),
        ("jikan", r"^external:(?:jikan|mal)-(.+)$"),
        ("tvmaze", r"^external:tvmaze-(.+)$"),
        ("tmdb", r"^external:tmdb-(.+)$"),
    )
    for provider, pattern in patterns:
        match = re.match(pattern, item_key, flags=re.I)
        if match:
            provider_ids.setdefault(provider, match.group(1))
            break
    return provider_ids


def _localized_latest_discovery_item(payload: dict[str, object]) -> dict[str, object]:
    item = dict(payload)
    original_title = str(item.get("original_title") or item.get("title") or item.get("display_title") or "").strip()
    provider_ids = _discovery_provider_ids(item)
    provider_title = next(
        (
            localized
            for provider, provider_id in provider_ids.items()
            if (localized := curated_display_title_for_provider(provider, provider_id))
        ),
        "",
    )
    display_title = to_simplified_chinese(
        provider_title or item.get("display_title") or item.get("title") or ""
    ).strip()
    item.update({
        "title": display_title,
        "display_title": display_title,
        "original_title": original_title or display_title,
        "title_localization_source": (
            "curated_catalog" if provider_title else str(item.get("title_localization_source") or "online")
        ),
        "provider_ids": provider_ids,
        "summary": localize_summary(item.get("summary")),
    })
    if isinstance(item.get("genres"), list):
        item["genres"] = [localize_genre(value) for value in item["genres"]]
    if isinstance(item.get("directors"), list):
        original_directors = [str(value).strip() for value in item["directors"] if str(value).strip()]
        item["directors"] = localize_people_names(original_directors, verified_only=True)
        if original_directors and original_directors != item["directors"]:
            item["original_directors"] = original_directors
    for field in ("countries", "languages", "casts", "tags", "aliases"):
        if isinstance(item.get(field), list):
            item[field] = [to_simplified_chinese(value) for value in item[field]]
    return item


def _title_aliases(item: MediaItem) -> list[str]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    aliases: list[str] = []
    original_title = str(raw.get("original_title") or "").strip()
    if original_title:
        aliases.append(original_title)
    for key in ("aliases", "original_titles", "aka"):
        values = raw.get(key)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple, set)):
            aliases.extend(str(value).strip() for value in values if str(value).strip())
    return _dedupe(aliases)


def _title_match(item: MediaItem, query: str) -> tuple[str, float]:
    needle = _normalize_title_text(query)
    if not needle:
        return "", 0.0
    title = _normalize_title_text(item.title)
    aliases = [_normalize_title_text(value) for value in _title_aliases(item)]
    if needle == title:
        return "exact", 4.0
    if needle in aliases:
        return "alias", 3.8
    names = [title, *aliases]
    if any(value.startswith(needle) or needle.startswith(value) for value in names if value):
        return "prefix", 3.0
    if any(needle in value for value in names if value):
        return "partial", 2.5
    blob = _normalize_title_text(item.search_blob())
    if needle and needle in blob:
        return "metadata", 1.5
    return "", 0.0


def _media_badge(media_type: object, genres: Sequence[object] = ()) -> dict[str, str]:
    canonical = canonical_media_type(media_type)
    normalized_genres = {str(genre or "").strip().casefold() for genre in genres}
    if canonical == "电视剧" and any("纪录片" in genre or "documentary" in genre for genre in normalized_genres):
        return {"label": "纪录片剧集", "icon": "tv", "tone": "cyan"}
    return {
        "电影": {"label": "电影", "icon": "film", "tone": "amber"},
        "电视剧": {"label": "剧集", "icon": "tv", "tone": "violet"},
        "动漫": {"label": "动画", "icon": "sparkles", "tone": "cyan"},
    }.get(canonical, {"label": canonical or "作品", "icon": "play", "tone": "slate"})


def _record_is_seen(record: LibraryRecord) -> bool:
    return record.item.my_rating is not None or str(record.state or "").strip() in {"watched", "rated", "collect"}


def _matches_avoid(item: MediaItem, intent: RecommendationIntent) -> bool:
    values = _dedupe([*intent.avoid, *intent.permanent_avoid])
    if not values:
        return False
    raw = item.raw if isinstance(item.raw, dict) else {}
    blob = " ".join([item.search_blob(), json.dumps(raw, ensure_ascii=False)]).casefold()
    for value in values:
        clean = str(value or "").strip().casefold()
        variants = {clean, clean.removeprefix("过度"), clean.removeprefix("太")}
        if any(variant and variant in blob for variant in variants):
            return True
    return False


def _discovery_text(item: MediaItem) -> str:
    raw = item.raw if isinstance(item.raw, dict) else {}
    aliases = _title_aliases(item)
    return " ".join([
        item.title,
        *aliases,
        item.summary,
        item.media_type,
        *item.genres,
        *item.countries,
        *item.languages,
        *item.directors,
        *item.casts[:8],
        *item.tags,
        json.dumps(raw.get("themes") or [], ensure_ascii=False),
        json.dumps(raw.get("style") or [], ensure_ascii=False),
    ])


def _vector_similarity(left: Sequence[float], right: Sequence[float]) -> float:
    if not left or not right:
        return 0.0
    return max(0.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def _trait_values(item: MediaItem) -> dict[str, float]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    stored = raw.get("discovery") if isinstance(raw.get("discovery"), dict) else {}
    values: dict[str, float] = {}
    for key in ("pace", "atmosphere", "cognitive_load", "emotional_intensity"):
        try:
            values[key] = max(-1.0, min(1.0, float(stored.get(key, 0))))
        except (TypeError, ValueError):
            values[key] = 0.0
    blob = _discovery_text(item)
    inference = {
        "pace": (
            (("快节奏", "紧凑", "高能", "动作", "惊悚", "追逐"), 0.7),
            (("舒缓", "缓慢", "慢热", "静谧"), -0.7),
        ),
        "atmosphere": (
            (("阴郁", "压抑", "暗黑", "黑暗", "恐怖", "犯罪"), 0.7),
            (("明快", "温暖", "阳光", "治愈", "轻松", "乐观", "喜剧"), -0.65),
        ),
        "cognitive_load": (
            (("烧脑", "悬疑", "推理", "复杂", "科幻", "非线性"), 0.7),
            (("轻松", "放松", "不费脑", "喜剧"), -0.6),
        ),
        "emotional_intensity": (
            (("强烈", "高能", "惊悚", "动作", "恐怖", "战争", "悲剧"), 0.7),
            (("克制", "平静", "静谧", "治愈"), -0.55),
        ),
    }
    for key, (positive, negative) in inference.items():
        if abs(values[key]) > 0.01:
            continue
        if any(marker in blob for marker in positive[0]):
            values[key] = positive[1]
        elif any(marker in blob for marker in negative[0]):
            values[key] = negative[1]
    return values


def _mood_axis_affinity(item: MediaItem, intent: RecommendationIntent) -> float:
    targets = {
        "pace": float(intent.pace_axis),
        "atmosphere": float(intent.atmosphere_axis),
        "cognitive_load": float(intent.cognitive_load_axis),
        "emotional_intensity": float(intent.emotional_intensity_axis),
    }
    active = [(key, max(-1.0, min(1.0, value))) for key, value in targets.items() if abs(value) >= 0.05]
    if not active:
        return 0.5
    traits = _trait_values(item)
    return sum(1.0 - abs(target - traits[key]) / 2.0 for key, target in active) / len(active)


def _quality_affinity(item: MediaItem) -> float:
    fused = fused_rating(item)
    rating = max(0.0, min(10.0, float(fused.rating or 0))) / 10.0
    popularity = min(1.0, math.log10(max(0, int(fused.vote_count or item.vote_count or 0)) + 1) / 6.5)
    completeness = sum(bool(value) for value in (item.summary, item.genres, item.year)) / 3.0
    return rating * 0.62 + popularity * 0.25 + completeness * 0.13


def _shared_discovery_evidence(left: MediaItem, right: MediaItem) -> list[str]:
    rows: list[str] = []
    fields = (
        ("共同类型", set(left.genres), set(right.genres)),
        ("共同导演", set(left.directors), set(right.directors)),
        ("共同演员", set(left.casts[:8]), set(right.casts[:8])),
        ("共同地区", set(left.countries), set(right.countries)),
        ("共同气质", set(left.tags), set(right.tags)),
    )
    for label, left_values, right_values in fields:
        shared = sorted(left_values & right_values)
        if shared:
            rows.append(f"{label}：{' / '.join(shared[:3])}")
    if not rows and left.media_type and left.media_type == right.media_type:
        rows.append(f"同为{_media_badge(left.media_type)['label']}")
    return rows[:4]


def _item_similarity_details(
    left: MediaItem,
    right: MediaItem,
    *,
    left_vector: Sequence[float] | None = None,
    right_vector: Sequence[float] | None = None,
    left_traits: dict[str, float] | None = None,
    right_traits: dict[str, float] | None = None,
) -> tuple[float, list[str], dict[str, float]]:
    features = (
        (set(left.genres), set(right.genres), 0.30),
        (set(left.directors), set(right.directors), 0.18),
        (set(left.casts[:8]), set(right.casts[:8]), 0.12),
        (set(left.tags), set(right.tags), 0.16),
        (set(left.countries), set(right.countries), 0.09),
        ({left.media_type} if left.media_type else set(), {right.media_type} if right.media_type else set(), 0.08),
    )
    structural = 0.0
    available_weight = 0.0
    for left_values, right_values, weight in features:
        if not left_values or not right_values:
            continue
        available_weight += weight
        overlap = len(left_values & right_values) / max(1, min(len(left_values), len(right_values)))
        structural += overlap * weight
    structural = structural / available_weight if available_weight else 0.0
    semantic = _vector_similarity(
        left_vector if left_vector is not None else feature_vector(_discovery_text(left)),
        right_vector if right_vector is not None else feature_vector(_discovery_text(right)),
    )
    prepared_left_traits = left_traits if left_traits is not None else _trait_values(left)
    prepared_right_traits = right_traits if right_traits is not None else _trait_values(right)
    trait_similarity = sum(
        1.0 - abs(prepared_left_traits[key] - prepared_right_traits[key]) / 2.0
        for key in prepared_left_traits
    ) / 4.0
    score = structural * 0.58 + semantic * 0.27 + trait_similarity * 0.15
    return max(0.0, min(1.0, score)), _shared_discovery_evidence(left, right), {
        "structural": round(max(0.0, min(1.0, structural)), 5),
        "semantic": round(max(0.0, min(1.0, semantic)), 5),
        "trait": round(max(0.0, min(1.0, trait_similarity)), 5),
    }


def _item_similarity(
    left: MediaItem,
    right: MediaItem,
    *,
    left_vector: Sequence[float] | None = None,
    right_vector: Sequence[float] | None = None,
    left_traits: dict[str, float] | None = None,
    right_traits: dict[str, float] | None = None,
) -> tuple[float, list[str]]:
    score, evidence, _details = _item_similarity_details(
        left,
        right,
        left_vector=left_vector,
        right_vector=right_vector,
        left_traits=left_traits,
        right_traits=right_traits,
    )
    return score, evidence


def _has_renderable_poster(payload: dict[str, object]) -> bool:
    poster = payload.get("poster") if isinstance(payload.get("poster"), dict) else {}
    url = str(poster.get("url") or "").strip()
    return str(poster.get("media_status") or "").strip().lower() == "ready" and bool(
        url.startswith("/media/") or url.startswith("/api/image-proxy?url=")
    )


def _has_publishable_discovery_title(payload: dict[str, object]) -> bool:
    display_title = str(payload.get("display_title") or payload.get("title") or "").strip()
    return bool(display_title) and not _is_unlocalized_latin_title(display_title) and not contains_non_chinese_east_asian_script(display_title)


def _record_has_publishable_discovery_title(record: LibraryRecord) -> bool:
    """Return the same title eligibility decision before a card is selected.

    Multi-focus ranking is cached independently from presentation batches.  A
    title therefore needs a cheap, deterministic eligibility check that does
    not serialize media or hit SQLite for every ``换一批`` click.  Reusing the
    canonical localization resolver keeps this in lock-step with the payload
    serializer and prevents English/provider-only titles from consuming MMR
    slots.
    """

    item = record.item
    localized = _title_localization(item)
    display_title = str(localized.get("display_title") or item.title or "").strip()
    return bool(display_title) and not _is_unlocalized_latin_title(display_title) and not contains_non_chinese_east_asian_script(display_title)


def _is_meaningful_focus_match(
    focus: MediaItem,
    candidate: MediaItem,
    similarity: float,
    evidence: Sequence[str],
    *,
    details: dict[str, float] | None = None,
) -> bool:
    shared_directors = set(focus.directors).intersection(candidate.directors)
    shared_casts = set(focus.casts[:8]).intersection(candidate.casts[:8])
    shared_tags = set(focus.tags).intersection(candidate.tags).difference(GENERIC_DISCOVERY_TAGS)
    if shared_directors or shared_casts or shared_tags:
        return True
    shared_genres = set(focus.genres).intersection(candidate.genres)
    distinctive_genres = shared_genres.difference(GENERIC_DISCOVERY_GENRES)
    if distinctive_genres:
        return True
    # A pair of broad-but-complementary genres (for example “动作 + 犯罪”)
    # is still a meaningful structural fingerprint.  Require enough metadata
    # on both sides so a lone provider fallback genre such as “剧情” does not
    # turn into a false positive.
    if len(shared_genres) >= 2 and min(
        _discovery_metadata_coverage(focus),
        _discovery_metadata_coverage(candidate),
    ) >= 0.5:
        return True
    # Sparse records can lack reliable tags or credits.  A sufficiently rich
    # semantic representation is allowed to bridge that gap, but a bare
    # provider title still needs a much stronger score.  This keeps generic
    # “剧情/同为电影” rows out of the strict intersection while allowing
    # curated or provider-supplied summaries to expand the discovery pool.
    focus_coverage = _discovery_metadata_coverage(focus)
    candidate_coverage = _discovery_metadata_coverage(candidate)
    structural = float((details or {}).get("structural") or 0.0)
    if similarity >= 0.70 and min(focus_coverage, candidate_coverage) >= 0.42:
        return True
    if similarity >= 0.74 and structural >= 0.12 and min(focus_coverage, candidate_coverage) >= 0.28:
        return True
    return similarity >= 0.84


def _discovery_metadata_coverage(item: MediaItem) -> float:
    """Estimate how much trustworthy structure is available for one item."""

    raw = item.raw if isinstance(item.raw, dict) else {}
    explicit_themes = _raw_discovery_values(item)
    signals = (
        bool(str(item.summary or "").strip()) and not _is_largely_latin_summary(item.summary),
        bool(item.genres),
        bool(item.countries),
        bool(item.directors),
        bool(item.casts),
        bool(item.tags) or bool(explicit_themes),
        bool(item.year),
        bool(raw.get("discovery")),
    )
    return sum(signals) / len(signals)


def _stable_unit(value: object) -> float:
    digest = hashlib.blake2b(str(value or "").encode("utf-8"), digest_size=8, person=b"CineMMR1").digest()
    return int.from_bytes(digest, "big", signed=False) / float(2**64 - 1)


def _jaccard(left: set[str], right: set[str]) -> float:
    if not left or not right:
        return 0.0
    return len(left & right) / max(1, len(left | right))


def _franchise_key(item: MediaItem) -> str:
    title = _normalize_title_text(item.title)
    title = re.sub(r"(?:第?[0-9一二三四五六七八九十]+(?:季|部|章|集)|[0-9一二三四五六七八九十]+)$", "", title)
    return title[:18]


def _candidate_redundancy(left: MediaItem, right: MediaItem) -> float:
    score = 0.0
    score += _jaccard(set(left.genres), set(right.genres)) * 0.42
    score += _jaccard(set(left.directors), set(right.directors)) * 0.18
    score += _jaccard(set(left.casts[:8]), set(right.casts[:8])) * 0.12
    score += _jaccard(set(left.tags), set(right.tags)) * 0.14
    score += _jaccard(set(left.countries), set(right.countries)) * 0.06
    if left.media_type and left.media_type == right.media_type:
        score += 0.04
    if left.year and right.year and left.year // 10 == right.year // 10:
        score += 0.04
    left_franchise = _franchise_key(left)
    right_franchise = _franchise_key(right)
    if left_franchise and right_franchise and left_franchise == right_franchise:
        score = max(score, 0.92)
    return max(0.0, min(1.0, score))


def _select_multi_focus_batch(
    ranked: Sequence[MultiFocusCandidate],
    *,
    batch_size: int,
    round_index: int,
    seed_key: str,
) -> list[MultiFocusCandidate]:
    """Select a deterministic, non-repeating presentation batch.

    The older selector only penalised items shown in an earlier round.  That
    still allowed a high-scoring title to re-enter the next batch.  We now
    consume earlier batches from the same ranked pool and remove their stable
    identities before selecting the requested round.  The expensive semantic
    ranking is cached by the service, so this extra diversity pass is cheap.
    """

    clean_batch = max(1, int(batch_size))
    clean_round = max(0, int(round_index))
    pool = list(ranked)
    if not pool:
        return []
    selected_tokens: set[str] = set()
    current: list[MultiFocusCandidate] = []
    # Avoid an unbounded loop for a malformed query while still allowing the
    # API's documented round range (0..99).
    for batch_index in range(clean_round + 1):
        available = [
            candidate
            for candidate in pool
            if not selected_tokens.intersection(_candidate_identity_tokens(candidate))
        ]
        if not available:
            return []
        current = _select_multi_focus_candidates(
            available,
            limit=clean_batch,
            round_index=0,
            seed_key=f"{seed_key}|batch:{batch_index}",
            batch_size=clean_batch,
        )
        if not current:
            return []
        if batch_index < clean_round:
            for candidate in current:
                selected_tokens.update(_candidate_identity_tokens(candidate))
    return current


def _candidate_identity_tokens(candidate: MultiFocusCandidate) -> set[str]:
    item = candidate.item or candidate.record.item
    return set(recommendation_identity_tokens(item))


def _select_multi_focus_candidates(
    ranked: Sequence[MultiFocusCandidate],
    *,
    limit: int,
    round_index: int,
    seed_key: str,
    batch_size: int | None = None,
) -> list[MultiFocusCandidate]:
    if not ranked or limit <= 0:
        return []
    clean_limit = min(len(ranked), max(1, int(limit)))
    round_batch = max(1, int(batch_size or min(clean_limit, 24)))
    prior_cutoff = min(len(ranked), max(0, int(round_index)) * round_batch)
    prior_tokens: set[str] = set()
    for candidate in ranked[:prior_cutoff]:
        prior_tokens.update(_candidate_identity_tokens(candidate))
    pool_size = min(len(ranked), max(clean_limit * 5, 160, prior_cutoff + clean_limit * 3))
    remaining = list(ranked[:pool_size])
    selected: list[MultiFocusCandidate] = []
    selected_tokens: set[str] = set()
    genre_counts: dict[str, int] = {}
    media_counts: dict[str, int] = {}
    decade_counts: dict[int, int] = {}

    while remaining and len(selected) < clean_limit:
        best_index = 0
        best_key: tuple[float, float, str] | None = None
        for index, candidate in enumerate(remaining):
            candidate_tokens = _candidate_identity_tokens(candidate)
            if candidate_tokens.intersection(selected_tokens):
                continue
            item = candidate.item or candidate.record.item
            matched_ratio = candidate.matched_count / max(1, len(candidate.connections))
            value = (
                candidate.score * 0.68
                + candidate.quality * 0.10
                + matched_ratio * 0.09
                + (0.13 if candidate.is_intersection else 0.0)
            )
            if candidate_tokens.intersection(prior_tokens):
                value -= 0.24
            if selected:
                redundancy = max(
                    _candidate_redundancy(item, chosen.item or chosen.record.item)
                    for chosen in selected
                )
                value -= redundancy * 0.27
            distinctive = [genre for genre in item.genres if genre not in GENERIC_DISCOVERY_GENRES]
            if distinctive:
                value -= min(0.12, min(genre_counts.get(genre, 0) for genre in distinctive) * 0.035)
            if item.media_type:
                value -= min(0.08, media_counts.get(item.media_type, 0) * 0.012)
            if item.year:
                value -= min(0.06, decade_counts.get(item.year // 10, 0) * 0.012)
            value += (_stable_unit(f"{seed_key}|{round_index}|{candidate.record.item_key}") - 0.5) * 0.035
            key = (value, candidate.score, candidate.record.item_key)
            if best_key is None or key > best_key:
                best_key = key
                best_index = index
        if best_key is None:
            break
        chosen = remaining.pop(best_index)
        selected.append(chosen)
        selected_tokens.update(_candidate_identity_tokens(chosen))
        chosen_item = chosen.item or chosen.record.item
        for genre in chosen_item.genres:
            genre_counts[genre] = genre_counts.get(genre, 0) + 1
        if chosen_item.media_type:
            media_counts[chosen_item.media_type] = media_counts.get(chosen_item.media_type, 0) + 1
        if chosen_item.year:
            decade = chosen_item.year // 10
            decade_counts[decade] = decade_counts.get(decade, 0) + 1
    return selected


def _trait_profile_copy(item: MediaItem) -> str:
    traits = _trait_values(item)
    rows: list[str] = []
    if traits["pace"] >= 0.35:
        rows.append("节奏紧凑")
    elif traits["pace"] <= -0.35:
        rows.append("节奏舒缓")
    if traits["cognitive_load"] >= 0.35:
        rows.append("思考密度高")
    if traits["emotional_intensity"] >= 0.45:
        rows.append("情绪张力强")
    if traits["atmosphere"] >= 0.4:
        rows.append("氛围偏暗")
    elif traits["atmosphere"] <= -0.35:
        rows.append("氛围明快")
    return " / ".join(rows[:2]) or "气质均衡"


def _multi_focus_dimensions(
    focuses: Sequence[LibraryRecord],
    candidate: LibraryRecord,
    connections: Sequence[tuple[float, Sequence[str], bool]],
) -> list[dict[str, object]]:
    matched_count = sum(connection[2] for connection in connections)
    dimensions: list[dict[str, object]] = [{
        "key": "coverage",
        "label": "焦点覆盖",
        "value": f"{matched_count}/{len(focuses)}",
        "strength": round(matched_count / max(1, len(focuses)), 3),
    }]
    evidence_values: dict[str, list[str]] = {}
    for _similarity, evidence, matched in connections:
        if not matched:
            continue
        for row in evidence:
            label, separator, value = str(row).partition("：")
            if separator and value:
                evidence_values.setdefault(label, []).extend(part.strip() for part in value.split("/") if part.strip())
    for label, key in (("共同类型", "genre"), ("共同气质", "tone"), ("共同导演", "director"), ("共同演员", "cast"), ("共同地区", "country")):
        values = _dedupe(evidence_values.get(label, []))
        if values:
            dimensions.append({
                "key": key,
                "label": label.removeprefix("共同"),
                "value": " / ".join(values[:3]),
                "strength": round(min(1.0, 0.5 + len(values) * 0.16), 3),
            })
    if len(dimensions) < 3:
        distinctive = [genre for genre in candidate.item.genres if genre not in GENERIC_DISCOVERY_GENRES]
        if distinctive and not any(row["key"] == "genre" for row in dimensions):
            dimensions.append({"key": "genre", "label": "类型桥", "value": " / ".join(distinctive[:3]), "strength": 0.56})
    if len(dimensions) < 3:
        dimensions.append({"key": "trait", "label": "气质坐标", "value": _trait_profile_copy(candidate.item), "strength": 0.52})
    rating = fused_rating(candidate.item)
    if rating.rating is not None:
        dimensions.append({
            "key": "quality",
            "label": "口碑",
            "value": f"{rating.rating:.1f} · {len(rating.providers)} 源",
            "strength": rating.confidence,
        })
    return dimensions[:4]


def _multi_focus_score_breakdown(
    candidate: MultiFocusCandidate,
    focuses: Sequence[LibraryRecord],
) -> dict[str, object]:
    """Expose the ranking recipe instead of hiding it behind one number."""

    components = list(candidate.components)
    average = {
        key: round(
            sum(float(row.get(key) or 0.0) for row in components) / max(1, len(components)),
            4,
        )
        for key in ("structural", "semantic", "trait")
    }
    similarities = [float(row[0]) for row in candidate.connections]
    matched_ratio = candidate.matched_count / max(1, len(focuses))
    return {
        "final": round(candidate.score, 4),
        "similarity": round(sum(similarities) / max(1, len(similarities)), 4),
        "bridge": round(min(similarities) if similarities else 0.0, 4),
        "coverage": round(matched_ratio, 4),
        "quality": round(candidate.quality, 4),
        "components": average,
        "weights": {
            "similarity": 0.74,
            "coverage": 0.16,
            "quality": 0.10,
            "similarity_components": {
                "structural": 0.58,
                "semantic": 0.27,
                "trait": 0.15,
            },
        },
    }


def _multi_focus_summary(dimensions: Sequence[dict[str, object]], matched: int, total: int) -> str:
    signals = [
        f"{row.get('label')}：{row.get('value')}"
        for row in dimensions
        if row.get("key") not in {"coverage", "quality"} and row.get("value")
    ]
    if total <= 1:
        prefix = "相似扩散"
    else:
        prefix = "严格交集" if matched == total else f"覆盖 {matched}/{total} 个焦点"
    return f"{prefix} · {'；'.join(signals[:2])}" if signals else prefix


def _multi_focus_profile(
    focuses: Sequence[LibraryRecord],
    candidate_pool_size: int,
    strict_pool_size: int,
) -> dict[str, object]:
    genre_sets = [set(record.item.genres).difference(GENERIC_DISCOVERY_GENRES) for record in focuses]
    shared_genres = set.intersection(*genre_sets) if genre_sets and all(genre_sets) else set()
    genre_union = _dedupe([
        genre
        for record in focuses
        for genre in record.item.genres
        if genre not in GENERIC_DISCOVERY_GENRES
    ])
    creators = _dedupe([
        *[name for record in focuses for name in record.item.directors[:2]],
        *[name for record in focuses for name in record.item.casts[:2]],
    ])
    dimensions: list[dict[str, str]] = []
    if shared_genres:
        dimensions.append({"key": "intersection", "label": "共同核心", "value": " / ".join(sorted(shared_genres)[:4])})
    if genre_union:
        dimensions.append({"key": "genre", "label": "类型配方", "value": " × ".join(genre_union[:5])})
    dimensions.append({
        "key": "tone",
        "label": "气质坐标",
        "value": " × ".join(_dedupe([_trait_profile_copy(record.item) for record in focuses])[:3]),
    })
    if creators:
        dimensions.append({"key": "creator", "label": "主创线索", "value": " / ".join(creators[:4])})
    dimensions.append({"key": "pool", "label": "检索范围", "value": f"{candidate_pool_size} 部候选 · {strict_pool_size} 部严格交集"})
    return {
        "headline": "单片相似扩散" if len(focuses) == 1 else f"{len(focuses)} 部作品的多维交集",
        "strategy": "先验证辨识度类型、气质与主创连接，再按语义 74% · 焦点覆盖 16% · 口碑 10% 综合排序，并用多样性重排避免同系列和同质结果占满一轮。",
        "dimensions": dimensions[:5],
        "weights": {
            "语义相似": 0.74,
            "焦点覆盖": 0.16,
            "口碑与资料": 0.10,
            "同质惩罚": 0.27,
        },
    }


_DISCOVERY_GENRE_HINTS: tuple[tuple[str, str], ...] = (
    ("科幻", "科幻"),
    ("science fiction", "科幻"),
    ("sci-fi", "科幻"),
    ("悬疑", "悬疑"),
    ("mystery", "悬疑"),
    ("thriller", "惊悚"),
    ("惊悚", "惊悚"),
    ("犯罪", "犯罪"),
    ("crime", "犯罪"),
    ("爱情", "爱情"),
    ("romance", "爱情"),
    ("喜剧", "喜剧"),
    ("comedy", "喜剧"),
    ("动画", "动画"),
    ("animation", "动画"),
    ("纪录片", "纪录片"),
    ("documentary", "纪录片"),
    ("奇幻", "奇幻"),
    ("fantasy", "奇幻"),
    ("动作", "动作"),
    ("action", "动作"),
)


def _raw_discovery_values(item: MediaItem) -> list[str]:
    """Collect explicit provider theme/style hints without inventing facts."""

    raw = item.raw if isinstance(item.raw, dict) else {}
    values: list[str] = []
    for key in (
        "themes",
        "theme",
        "style",
        "styles",
        "keywords",
        "keyword",
        "moods",
        "mood",
        "topics",
        "topic",
    ):
        value = raw.get(key)
        if isinstance(value, str):
            values.append(value.strip())
        elif isinstance(value, (list, tuple, set)):
            values.extend(str(part or "").strip() for part in value)
    return list(dict.fromkeys(value for value in values if value))


def _enrich_discovery_record(record: LibraryRecord) -> LibraryRecord:
    """Create a virtual, metadata-complete record for exploration ranking.

    Provider syncs often leave a title with only a name and an external id.
    Replacing that record in SQLite would make the sync destructive and would
    also make it impossible to tell verified data from inferred data.  Instead
    we merge only trusted curated fields and explicit provider theme hints into
    a copy used by the exploration pipeline.  The original payload and item
    key remain unchanged, preserving identity and persistence semantics.
    """

    item = record.item
    metadata = curated_metadata_for_title(item.title, item.douban_id)
    data = media_item_to_dict(item)
    changed = False

    def merge_list(field: str, values: object, *, replace_if_empty_only: bool = True) -> None:
        nonlocal changed
        if not isinstance(values, (list, tuple, set)):
            return
        incoming = [str(value or "").strip() for value in values if str(value or "").strip()]
        if not incoming:
            return
        current = data.get(field)
        current_values = [str(value or "").strip() for value in current] if isinstance(current, list) else []
        if replace_if_empty_only and current_values:
            return
        merged = list(dict.fromkeys([*current_values, *incoming]))
        if merged != current_values:
            data[field] = merged
            changed = True

    for field in ("genres", "countries", "directors", "casts"):
        merge_list(field, metadata.get(field))

    current_summary = str(data.get("summary") or "").strip()
    curated_summary = str(metadata.get("summary") or "").strip()
    if curated_summary and (not current_summary or _is_largely_latin_summary(current_summary)):
        data["summary"] = curated_summary
        changed = True

    raw_values = _raw_discovery_values(item)
    if raw_values:
        raw = dict(data.get("raw") or {})
        existing_themes = raw.get("themes")
        existing_theme_values = (
            [str(value or "").strip() for value in existing_themes if str(value or "").strip()]
            if isinstance(existing_themes, (list, tuple, set))
            else []
        )
        if not existing_theme_values:
            raw["themes"] = raw_values[:12]
            data["raw"] = raw
            changed = True

        if not data.get("genres"):
            lowered = " ".join(raw_values).casefold()
            inferred = [label for marker, label in _DISCOVERY_GENRE_HINTS if marker.casefold() in lowered]
            if inferred:
                data["genres"] = list(dict.fromkeys(inferred))[:5]
                changed = True
        if not data.get("tags"):
            # Tags are used as semantic anchors, not shown as verified facts
            # unless the provider explicitly supplied them.
            data["tags"] = raw_values[:8]
            changed = True

    if not changed:
        return record
    enriched = media_item_from_dict(data)
    return replace(record, item=enriched)


def _multi_focus_explanation(
    focuses: Sequence[LibraryRecord],
    candidate: LibraryRecord,
    connections: Sequence[tuple[float, list[str], bool]],
    is_intersection: bool,
) -> str:
    if len(focuses) == 1:
        focus_title = f"《{focuses[0].item.title}》"
        signal_copy = "；".join(_dedupe([
            evidence[0]
            for _similarity, evidence, matched_connection in connections
            if matched_connection and evidence
        ])[:2])
        suffix = f"，主要线索是{signal_copy}" if signal_copy else ""
        return f"围绕{focus_title}展开相似扩散{suffix}，并按类型、气质与口碑筛选候选。"
    matched = [
        focus
        for focus, connection in zip(focuses, connections)
        if connection[2]
    ]
    titles = "、".join(f"《{focus.item.title}》" for focus in matched[:3])
    signals = _dedupe([
        evidence[0]
        for _similarity, evidence, matched_connection in connections
        if matched_connection and evidence
    ])
    signal_copy = "；".join(signals[:2])
    if is_intersection:
        suffix = f"，共同线索是{signal_copy}" if signal_copy else ""
        return f"同时匹配{titles}的内容特征{suffix}，属于多焦点交集候选。"
    strongest_index = max(range(len(connections)), key=lambda index: connections[index][0])
    strongest = focuses[strongest_index]
    bridge = f"，并保留{signal_copy}" if signal_copy else ""
    return f"混合推荐：更接近《{strongest.item.title}》{bridge}，用于补足严格交集之外的探索空间。"


def _intent_affinity(item: MediaItem, intent: RecommendationIntent) -> tuple[float, list[str]]:
    evidence: list[str] = []
    scores: list[float] = []
    if intent.media_types:
        match = 1.0 if item.media_type in intent.media_types else 0.0
        scores.append(match)
        if match:
            evidence.append(f"媒介符合：{_media_badge(item.media_type)['label']}")
    if intent.genres:
        shared = sorted(set(intent.genres) & set(item.genres))
        scores.append(len(shared) / max(1, len(intent.genres)))
        if shared:
            evidence.append(f"类型符合：{' / '.join(shared[:3])}")
    if intent.countries:
        shared = sorted(set(intent.countries) & set(item.countries))
        scores.append(len(shared) / max(1, len(intent.countries)))
        if shared:
            evidence.append(f"地区符合：{' / '.join(shared[:2])}")
    blob = _discovery_text(item)
    matched_moods = [mood for mood in intent.moods if mood in blob]
    if intent.moods:
        scores.append(len(matched_moods) / max(1, len(intent.moods)))
        if matched_moods:
            evidence.append(f"气质符合：{' / '.join(matched_moods[:3])}")
    semantic = _vector_similarity(feature_vector(intent.free_text), feature_vector(_discovery_text(item))) if intent.free_text else 0.0
    metadata = sum(scores) / len(scores) if scores else semantic
    score = semantic * 0.55 + metadata * 0.45
    if not evidence and item.genres:
        evidence.append(f"以{' / '.join(item.genres[:2])}为主要类型")
    return max(0.0, min(1.0, score)), evidence[:4]


def _axis_preference_clauses(intent: RecommendationIntent) -> list[str]:
    clauses: list[str] = []
    if intent.pace_axis >= 0.2:
        clauses.append("更紧凑的节奏")
    elif intent.pace_axis <= -0.2:
        clauses.append("更舒缓的节奏")
    if intent.atmosphere_axis <= -0.2:
        clauses.append("更明快的氛围")
    elif intent.atmosphere_axis >= 0.2:
        clauses.append("更阴郁的氛围")
    if intent.cognitive_load_axis <= -0.2:
        clauses.append("更轻松的观看负担")
    elif intent.cognitive_load_axis >= 0.2:
        clauses.append("更高的思考密度")
    if intent.emotional_intensity_axis <= -0.2:
        clauses.append("更克制的情绪")
    elif intent.emotional_intensity_axis >= 0.2:
        clauses.append("更强烈的情绪")
    return clauses


_SIMILAR_EVIDENCE_PRIORITY = {
    "共同导演": 0,
    "共同演员": 1,
    "共同气质": 2,
    "共同类型": 3,
    "共同地区": 4,
    "媒介": 5,
}


def _similar_reason_evidence(
    candidate: MediaItem,
    evidence: Sequence[str],
    score: float,
) -> list[dict[str, object]]:
    """Return compact, candidate-specific evidence for decision cards.

    The former UI only received one sentence derived from the first shared
    genre.  Candidates with the same broad genres therefore appeared to have
    identical reasons even when their creator, region, tone and quality
    signals were different.  This structure keeps those dimensions explicit
    and lets the client display them without expanding the synopsis.
    """

    parsed: list[tuple[int, dict[str, object]]] = []
    seen: set[tuple[str, str]] = set()
    key_by_label = {
        "共同导演": "director",
        "共同演员": "cast",
        "共同气质": "tone",
        "共同类型": "genre",
        "共同地区": "country",
        "媒介": "media",
    }
    for raw in evidence:
        copy = str(raw or "").strip()
        if not copy:
            continue
        label, separator, value = copy.partition("：")
        if not separator and copy.startswith("同为"):
            label, value = "媒介", copy.removeprefix("同为").strip()
        label = label.strip()
        value = value.strip()
        if not label or not value:
            continue
        token = (label, value)
        if token in seen:
            continue
        seen.add(token)
        parsed.append((
            _SIMILAR_EVIDENCE_PRIORITY.get(label, 9),
            {
                "key": key_by_label.get(label, "signal"),
                "label": label.removeprefix("共同"),
                "value": value,
                "strength": round(max(0.35, min(1.0, float(score))), 3),
            },
        ))
    parsed.sort(key=lambda row: row[0])
    rows = [row for _priority, row in parsed[:3]]

    if not any(row.get("key") == "tone" for row in rows):
        rows.append({
            "key": "tone",
            "label": "观看气质",
            "value": _trait_profile_copy(candidate),
            "strength": 0.52,
        })

    rating = fused_rating(candidate)
    if rating.rating is not None:
        rows.append({
            "key": "quality",
            "label": "口碑证据",
            "value": f"{rating.rating:.1f} · {max(1, len(rating.providers))} 源",
            "strength": round(max(0.25, min(1.0, rating.confidence)), 3),
        })

    if len(rows) < 4:
        level = "高一致扩散" if score >= 0.58 else "平衡相似" if score >= 0.42 else "探索补位"
        rows.append({
            "key": "strategy",
            "label": "推荐角色",
            "value": level,
            "strength": round(max(0.2, min(1.0, float(score))), 3),
        })
    return rows[:4]


def _similar_explanation(
    focus: MediaItem,
    candidate: MediaItem,
    evidence: list[str],
    intent: RecommendationIntent,
    *,
    score: float = 0.0,
    reason_evidence: Sequence[dict[str, object]] | None = None,
) -> str:
    rows = list(reason_evidence or _similar_reason_evidence(candidate, evidence, score))
    content_rows = [
        row for row in rows
        if str(row.get("key") or "") not in {"quality", "strategy"}
        and str(row.get("label") or "").strip()
        and str(row.get("value") or "").strip()
    ]
    if content_rows:
        primary = content_rows[0]
        base = (
            f"《{candidate.title}》与《{focus.title}》的首要连接是"
            f"{primary['label']}“{primary['value']}”"
        )
        if len(content_rows) > 1:
            secondary = content_rows[1]
            base += f"，并在{secondary['label']}“{secondary['value']}”上继续重合"
    else:
        base = f"《{candidate.title}》延续了《{focus.title}》的题材与叙事气质"
    clauses = _axis_preference_clauses(intent)
    if clauses:
        return f"{base}，同时更贴近你此刻想要的{'、'.join(clauses[:2])}。"
    quality = next((row for row in rows if row.get("key") == "quality"), None)
    if quality:
        return f"{base}；其{quality['label']}为{quality['value']}，作为质量校验。"
    return f"{base}。"


def _query_explanation(item: MediaItem, evidence: list[str], intent: RecommendationIntent) -> str:
    clauses = _axis_preference_clauses(intent)
    if evidence and clauses:
        return f"{evidence[0]}，同时贴近你想要的{'、'.join(clauses[:2])}。"
    if evidence:
        return f"{evidence[0]}，适合作为这次描述下的优先选择。"
    if clauses:
        return f"它的整体气质贴近你想要的{'、'.join(clauses[:2])}。"
    return f"这部{_media_badge(item.media_type)['label']}在题材、口碑与当前语境之间更均衡。"


def _blend_reason(source: MediaItem, evidence: list[str]) -> str:
    if evidence:
        raw_evidence = str(evidence[0] or "").strip()
        _label, separator, value = raw_evidence.partition("：")
        if separator and value.strip():
            return f"延续《{source.title}》的{value.strip()}"
        if raw_evidence.startswith("同为"):
            return f"保留《{source.title}》的{raw_evidence}尺度"
        return f"保留《{source.title}》的{raw_evidence}特征"
    return f"保留《{source.title}》的{_media_badge(source.media_type)['label']}叙事尺度"


def _blend_explanation(
    left: MediaItem,
    right: MediaItem,
    candidate: MediaItem,
    left_evidence: list[str],
    right_evidence: list[str],
) -> dict[str, str]:
    from_left = _blend_reason(left, left_evidence)
    from_right = _blend_reason(right, right_evidence)
    fusion = f"把{from_left.removeprefix('延续').removeprefix('保留')}与{from_right.removeprefix('延续').removeprefix('保留')}融合到《{candidate.title}》的观看体验里"
    return {"from_left": from_left, "from_right": from_right, "fusion": fusion}


def _discovery_mode(value: object) -> str:
    clean = str(value or "balanced").strip().casefold()
    aliases = {
        "faithful": "faithful",
        "similar": "faithful",
        "balanced": "balanced",
        "balance": "balanced",
        "surprise": "surprise",
    }
    if clean not in aliases:
        raise ExplorationError("invalid discovery mode")
    return aliases[clean]


def build_universe_graph(focus_id: str, limit: int = 9) -> dict[str, object]:
    database = AppDatabase(resolve_database_path())
    database.initialize()
    return ExplorationService(database).build_universe_graph(focus_id, limit=limit)


def _json_object(value: object) -> dict[str, Any]:
    if isinstance(value, dict):
        return dict(value)
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _calendar_date(value: object) -> str:
    """Return a strict ISO calendar date without trusting provider formatting."""

    text = str(value or "").strip()
    match = re.search(r"\b((?:19|20)\d{2}-\d{2}-\d{2})\b", text)
    if not match:
        return ""
    candidate = match.group(1)
    try:
        datetime.strptime(candidate, "%Y-%m-%d")
    except ValueError:
        return ""
    return candidate


def _first_activity_date(raw: object, *, include_release: bool = False) -> str:
    """Find a trustworthy user activity date, optionally falling back to release data."""

    payload = raw if isinstance(raw, dict) else {}
    keys = ["watched_date", "activity_date"]
    if include_release:
        keys.extend(("release_date", "first_air_date", "premiered", "air_date"))
    for key in keys:
        value = _calendar_date(payload.get(key))
        if value:
            return value

    if include_release:
        aired = payload.get("aired")
        if isinstance(aired, dict):
            value = _calendar_date(aired.get("from") or aired.get("to"))
            if value:
                return value
    return ""


def _activity_timestamp(value: object) -> float:
    calendar_date = _calendar_date(value)
    if not calendar_date:
        return 0.0
    try:
        local_tz = datetime.now().astimezone().tzinfo or timezone.utc
        return datetime.strptime(calendar_date, "%Y-%m-%d").replace(tzinfo=local_tz).timestamp()
    except (OverflowError, OSError, ValueError):
        return 0.0


def _iso_timestamp(timestamp: object) -> str:
    try:
        value = float(timestamp or 0)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(value) or value <= 0:
        return ""
    try:
        return datetime.fromtimestamp(value, tz=timezone.utc).astimezone().isoformat(timespec="seconds")
    except (OverflowError, OSError, ValueError):
        return ""


def _date_from_timestamp(timestamp: object) -> str:
    try:
        value = float(timestamp or 0)
    except (TypeError, ValueError):
        return ""
    if not math.isfinite(value) or value <= 0:
        return ""
    try:
        return datetime.fromtimestamp(value).strftime("%Y-%m-%d")
    except (OverflowError, OSError, ValueError):
        return ""


def _relative_date_label(timestamp: object) -> str:
    date_text = _date_from_timestamp(timestamp)
    if not date_text:
        return ""
    try:
        activity = datetime.strptime(date_text, "%Y-%m-%d").date()
    except ValueError:
        return date_text
    today = datetime.now().astimezone().date()
    days = (today - activity).days
    if days == 0:
        return "今天"
    if days == 1:
        return "昨天"
    if 1 < days <= 30:
        return f"{days} 天前"
    if days < 0:
        return date_text
    return f"{activity.year}年{activity.month}月{activity.day}日"


def _positive_int(value: object) -> int:
    try:
        parsed = int(float(value))
    except (TypeError, ValueError, OverflowError):
        return 0
    return parsed if parsed > 0 else 0


def _finite_number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError, OverflowError):
        return None
    return parsed if math.isfinite(parsed) else None


def _watch_progress(raw: object) -> dict[str, object]:
    payload = raw if isinstance(raw, dict) else {}
    progress = payload.get("watch_progress")
    progress_payload = progress if isinstance(progress, dict) else {}

    watched = _positive_int(
        payload.get("episodes_watched")
        or progress_payload.get("watched")
        or progress_payload.get("current")
        or progress_payload.get("episode")
    )
    total = _positive_int(
        payload.get("total_episodes")
        or progress_payload.get("total")
        or progress_payload.get("episodes")
    )
    percent_value = progress_payload.get("percent")
    if percent_value is None and not isinstance(progress, dict):
        percent_value = progress
    percent = _finite_number(percent_value)
    if percent is not None:
        if 0 < percent <= 1:
            percent *= 100
        percent = max(0.0, min(100.0, percent))
    if watched and total:
        percent = max(percent or 0.0, min(100.0, watched / total * 100.0))

    if watched and total:
        label = f"第 {watched} / {total} 集"
    elif watched:
        label = f"已看至第 {watched} 集"
    elif percent is not None and percent > 0:
        label = f"进度 {round(percent):d}%"
    else:
        label = str(progress_payload.get("label") or "").strip()[:80]
    if not label:
        return {}
    result: dict[str, object] = {"label": label}
    if watched:
        result["watched"] = watched
    if total:
        result["total"] = total
    if percent is not None and percent > 0:
        result["percent"] = round(percent, 1)
    return result


def _rating_map(value: object) -> dict[str, float]:
    payload = value if isinstance(value, dict) else {}
    ratings: dict[str, float] = {}
    for provider, score in payload.items():
        clean_provider = re.sub(r"[^a-z0-9._~-]+", "", str(provider or "").casefold())
        clean_score = _finite_number(score)
        if clean_provider and clean_score is not None and 0 < clean_score <= 10:
            ratings[clean_provider] = round(clean_score, 2)
    return ratings


def _vote_map(value: object) -> dict[str, int]:
    payload = value if isinstance(value, dict) else {}
    votes: dict[str, int] = {}
    for provider, count in payload.items():
        clean_provider = re.sub(r"[^a-z0-9._~-]+", "", str(provider or "").casefold())
        clean_provider = re.sub(r"_(?:popularity|weight|votes)$", "", clean_provider)
        clean_count = _positive_int(count)
        if clean_provider and clean_count:
            votes[clean_provider] = max(votes.get(clean_provider, 0), clean_count)
    return votes


def _release_date_for_item(item: MediaItem) -> str:
    raw = item.raw if isinstance(item.raw, dict) else {}
    return _first_activity_date(raw, include_release=True)


def _live_discovery_payload(item: MediaItem, *, rank: int, generated_at: float) -> dict[str, object] | None:
    """Convert an online provider item into a safe, directly-renderable card."""

    poster_url = _proxied_image_url(item.cover)
    if not poster_url:
        return None
    raw = item.raw if isinstance(item.raw, dict) else {}
    provider_ids = {
        re.sub(r"[^a-z0-9._~-]+", "", str(provider or "").casefold()): str(provider_id or "").strip()
        for provider, provider_id in (raw.get("provider_ids") or {}).items()
        if str(provider or "").strip() and str(provider_id or "").strip()
    } if isinstance(raw.get("provider_ids"), dict) else {}
    localization = _title_localization(item)
    display_title = str(localization.get("display_title") or item.title or "").strip()
    if (
        not display_title
        or _is_unlocalized_latin_title(display_title)
        or contains_non_chinese_east_asian_script(display_title)
    ):
        return None

    backdrop_url = _proxied_image_url(raw.get("backdrop"))
    source_ratings = _rating_map(raw.get("ratings"))
    if item.douban_rating is not None:
        douban_rating = _finite_number(item.douban_rating)
        if douban_rating is not None and douban_rating > 0:
            source_ratings.setdefault("douban", round(douban_rating, 2))
    rating_votes = _vote_map(raw.get("rating_votes"))
    sources = [
        re.sub(r"[^a-z0-9._~-]+", "", str(value or "").casefold())
        for value in raw.get("discovery_sources", [])
        if str(value or "").strip()
    ] if isinstance(raw.get("discovery_sources"), (list, tuple, set)) else []
    source_name = str(item.source or "").strip().removeprefix("global:")
    if source_name:
        sources.append(re.sub(r"[^a-z0-9._~-]+", "", source_name.casefold()))
    sources = _dedupe([source for source in sources if source])
    provider_labels = {
        "tmdb": "TMDb",
        "tmdb_trending_movie": "TMDb 热门电影",
        "tmdb_trending_tv": "TMDb 热门剧集",
        "tmdb_quality_movie": "TMDb 高分电影",
        "tmdb_quality_tv": "TMDb 高分剧集",
        "omdb": "IMDb / OMDb",
        "imdb": "IMDb",
        "tvmaze": "TVMaze",
        "anilist": "AniList",
        "jikan": "MyAnimeList",
        "apple_movies": "Apple TV 热门电影",
    }
    release_date = _release_date_for_item(item)
    popularity = _finite_number(raw.get("popularity")) or _finite_number(raw.get("discovery_score")) or 0.0
    vote_count = _positive_int(item.vote_count) or sum(rating_votes.values())
    rank_score = popularity + math.log10(vote_count + 1) * 12.0 + max(source_ratings.values(), default=0.0) * 4.0
    curated_summary = next(
        (
            summary
            for provider, provider_id in provider_ids.items()
            if (summary := curated_summary_for_provider(provider, provider_id))
        ),
        "",
    )
    summary = curated_summary or localize_summary(str(item.summary or "").strip())
    if _is_largely_latin_summary(summary):
        summary = ""
    comment = next((
        str(raw.get(key) or "").strip()
        for key in ("short_comment", "comment", "review")
        if str(raw.get(key) or "").strip()
    ), "")
    if _is_largely_latin_summary(comment):
        comment = ""
    else:
        comment = localize_summary(comment)
    localized_directors = localize_people_names(item.directors, verified_only=True)

    return {
        "id": recommendation_item_key(item),
        "item_key": recommendation_item_key(item),
        "title": to_simplified_chinese(item.title),
        **localization,
        "year": item.year,
        "media_type": item.media_type,
        "media_badge": _media_badge(item.media_type, item.genres),
        "genres": [localize_genre(value) for value in item.genres],
        "countries": [to_simplified_chinese(value) for value in item.countries],
        "languages": [to_simplified_chinese(value) for value in item.languages],
        "directors": localized_directors,
        "original_directors": [str(value).strip() for value in item.directors if str(value).strip()],
        "casts": [to_simplified_chinese(value) for value in item.casts],
        "tags": [to_simplified_chinese(value) for value in item.tags],
        "aliases": [to_simplified_chinese(value) for value in _title_aliases(item)],
        "summary": summary,
        "review_excerpt": comment,
        "poster": {"url": poster_url, "media_status": "ready"},
        "backdrop": {
            "url": backdrop_url,
            "media_status": "ready" if backdrop_url else "missing",
        },
        "source_ratings": source_ratings,
        "rating_votes": rating_votes,
        "douban_rating": item.douban_rating,
        "vote_count": vote_count,
        "comment_count": _positive_int(raw.get("comment_count")),
        "review_count": _positive_int(raw.get("review_count")),
        "release_date": release_date,
        "provider_ids": provider_ids,
        "discovery_sources": sources,
        "source_labels": [provider_labels.get(source, source.upper()) for source in sources],
        "is_live": True,
        "discovery_status": "online",
        "summary_localization_source": "curated_catalog" if curated_summary else "provider",
        "discovered_at": _finite_number(raw.get("discovered_at")) or generated_at,
        "rank": max(1, int(rank)),
        "rank_score": round(rank_score, 4),
        "identity_tokens": list(recommendation_identity_tokens(item)),
    }


_DISCOVERY_REGION_SUFFIX_RE = re.compile(
    r"[（(]\s*(?:港|台|臺|香港|台灣|臺灣|中国大陆|中國大陸|大陆|大陸|美国|美國)\s*[）)]$",
    re.I,
)


def _discovery_title_key(value: object) -> str:
    """Normalize a display/alias title for cross-source duplicate matching.

    Provider records frequently disagree on punctuation, simplified/traditional
    characters, or a parenthesized regional alias.  Keep this deliberately
    conservative: the year and canonical media type are part of the final
    signature, and only formatting/regional suffixes are removed here.
    """

    text = to_simplified_chinese(str(value or "").strip()).casefold()
    while text:
        stripped = _DISCOVERY_REGION_SUFFIX_RE.sub("", text).strip()
        if stripped == text:
            break
        text = stripped
    for marker in " 　\t\r\n:：-—_·.,，。!！?？《》<>[]【】()（）/\\|\"'&＆":
        text = text.replace(marker, "")
    return text


def _discovery_payload_title_values(payload: dict[str, object]) -> list[str]:
    nested = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    values: list[str] = []
    for source in (payload, nested):
        for key in ("display_title", "title", "original_title"):
            value = source.get(key)
            if isinstance(value, str) and value.strip():
                values.append(value)
        aliases = source.get("aliases")
        if isinstance(aliases, str):
            aliases = [aliases]
        if isinstance(aliases, (list, tuple, set)):
            values.extend(str(value or "") for value in aliases if str(value or "").strip())
        raw = source.get("raw") if isinstance(source.get("raw"), dict) else {}
        raw_aliases = raw.get("aliases")
        if isinstance(raw_aliases, str):
            raw_aliases = [raw_aliases]
        if isinstance(raw_aliases, (list, tuple, set)):
            values.extend(str(value or "") for value in raw_aliases if str(value or "").strip())
    return _dedupe(values)


def _discovery_payload_signatures(payload: dict[str, object]) -> set[str]:
    nested = payload.get("item") if isinstance(payload.get("item"), dict) else {}
    year = _positive_int(payload.get("year") or nested.get("year"))
    media_type = canonical_media_type(payload.get("media_type") or nested.get("media_type"))
    if not year or not media_type:
        return set()
    return {
        f"title-year-type:{key}|{year}|{media_type}"
        for key in (_discovery_title_key(value) for value in _discovery_payload_title_values(payload))
        if len(key) >= 2
    }


def _merge_local_duplicate_into_live(live: dict[str, object], local: dict[str, object]) -> None:
    """Enrich an online card with stronger local metadata without changing its identity."""

    for field in ("genres", "countries", "languages", "directors", "original_directors", "casts", "tags", "aliases", "discovery_sources", "source_labels", "identity_tokens"):
        left = live.get(field)
        right = local.get(field)
        left_values = list(left) if isinstance(left, (list, tuple, set)) else []
        right_values = list(right) if isinstance(right, (list, tuple, set)) else []
        if left_values or right_values:
            live[field] = _dedupe([str(value) for value in [*left_values, *right_values] if str(value or "").strip()])

    left_ratings = live.get("source_ratings") if isinstance(live.get("source_ratings"), dict) else {}
    right_ratings = local.get("source_ratings") if isinstance(local.get("source_ratings"), dict) else {}
    live["source_ratings"] = {**right_ratings, **left_ratings}
    left_votes = live.get("rating_votes") if isinstance(live.get("rating_votes"), dict) else {}
    right_votes = local.get("rating_votes") if isinstance(local.get("rating_votes"), dict) else {}
    live["rating_votes"] = {
        key: max(_positive_int(left_votes.get(key)), _positive_int(right_votes.get(key)))
        for key in set(left_votes) | set(right_votes)
        if max(_positive_int(left_votes.get(key)), _positive_int(right_votes.get(key)))
    }

    for field in ("douban_rating", "vote_count", "comment_count", "review_count"):
        current = live.get(field)
        incoming = local.get(field)
        if field == "douban_rating":
            if not (_finite_number(current) or 0) and (_finite_number(incoming) or 0):
                live[field] = incoming
        else:
            live[field] = max(_positive_int(current), _positive_int(incoming)) or None

    for field in ("summary", "review_excerpt"):
        current = str(live.get(field) or "").strip()
        incoming = str(local.get(field) or "").strip()
        if len(incoming) > len(current):
            live[field] = incoming

    for field in ("stills", "people"):
        if not live.get(field) and local.get(field):
            live[field] = local[field]
    for field in ("poster", "backdrop"):
        current = live.get(field) if isinstance(live.get(field), dict) else {}
        incoming = local.get(field) if isinstance(local.get(field), dict) else {}
        if str(current.get("media_status") or "") != "ready" and incoming.get("url"):
            live[field] = incoming

    if (_finite_number(local.get("douban_rating")) or 0) > 0:
        labels = list(live.get("source_labels")) if isinstance(live.get("source_labels"), list) else []
        if "豆瓣资料" not in labels:
            labels.append("豆瓣资料")
        live["source_labels"] = labels


def _latest_payload_sort_key(item: dict[str, object]) -> tuple[object, ...]:
    release_date = _calendar_date(item.get("release_date"))
    release_value = int(release_date.replace("-", "")) if release_date else 0
    year = _positive_int(item.get("year"))
    ratings = item.get("source_ratings") if isinstance(item.get("source_ratings"), dict) else {}
    best_rating = max((_finite_number(value) or 0.0 for value in ratings.values()), default=0.0)
    return (
        release_value,
        year,
        best_rating,
        _positive_int(item.get("vote_count")),
        _finite_number(item.get("rank_score")) or 0.0,
        -_positive_int(item.get("rank")),
        str(item.get("item_key") or ""),
    )


def _sort_latest_payloads(items: Sequence[dict[str, object]]) -> list[dict[str, object]]:
    ranked = sorted((dict(item) for item in items), key=_latest_payload_sort_key, reverse=True)
    if len(ranked) < 2:
        return ranked

    # A single release-date-heavy provider (for example a storefront movie
    # chart) must not crowd every rated series and anime result out of the
    # combined rail. Preserve each source's internal quality order, then
    # interleave sources in the order their best candidate first appeared.
    groups: dict[str, list[dict[str, object]]] = {}
    source_order: list[str] = []
    for item in ranked:
        sources = item.get("discovery_sources") if isinstance(item.get("discovery_sources"), list) else []
        source = str(sources[0] if sources else "unattributed")
        if source not in groups:
            groups[source] = []
            source_order.append(source)
        groups[source].append(item)

    diversified: list[dict[str, object]] = []
    for index in range(max(len(group) for group in groups.values())):
        for source in source_order:
            group = groups[source]
            if index < len(group):
                diversified.append(group[index])
    return diversified


def _latest_record_sort_key(record: LibraryRecord) -> tuple[object, ...]:
    raw = record.item.raw if isinstance(record.item.raw, dict) else {}
    release_date = _first_activity_date(raw, include_release=True)
    release_value = int(release_date.replace("-", "")) if release_date else 0
    return (
        release_value,
        _positive_int(record.item.year),
        _finite_number(record.item.douban_rating) or 0.0,
        _positive_int(record.item.vote_count),
        float(record.updated_at or 0),
        record.item_key,
    )


def _json_list(value: object) -> list[str]:
    try:
        decoded = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


def _is_largely_latin_summary(value: object) -> bool:
    """Detect provider summaries that would make the Chinese UI feel untranslated."""
    text = str(value or "").strip()
    if not text:
        return False
    cjk = sum("\u3400" <= char <= "\u9fff" for char in text)
    latin = sum(("a" <= char.lower() <= "z") for char in text)
    return cjk == 0 and latin >= 24 and latin >= len(text) * 0.45


def _media_item(payload: dict[str, Any]) -> MediaItem:
    defaults = {
        "title": "",
        "media_type": "",
        "url": "",
        "douban_id": "",
        "cover": "",
        "summary": "",
        "source": "",
    }
    data = {**defaults, **payload}
    for field in defaults:
        if data.get(field) is None:
            data[field] = ""
    item = media_item_from_dict(data)
    item.raw = dict(payload.get("raw") or {}) if isinstance(payload.get("raw"), dict) else {}
    return item


def _proxied_image_url(value: object) -> str:
    url = str(value or "").strip()
    try:
        parsed = urlsplit(url)
    except ValueError:
        return ""
    hostname = (parsed.hostname or "").lower()
    if parsed.scheme not in {"http", "https"} or (
        hostname not in PROXIED_IMAGE_HOSTS
        and not hostname.endswith(".mzstatic.com")
        and not hostname.endswith(".doubanio.com")
    ):
        return ""
    return f"/api/image-proxy?url={quote(url, safe='')}"


def _safe_media_route(url: str) -> bool:
    route = str(url or "")
    if not route.startswith("/media/") or ".." in route or "\\" in route:
        return False
    return re.fullmatch(r"[0-9a-f]{64}(?:\.(?:jpg|jpeg|png|webp))?", route.removeprefix("/media/"), re.I) is not None


def _parse_media_route(url: str) -> tuple[str, str] | None:
    route = str(url or "")
    if not _safe_media_route(route):
        return None
    filename = route.removeprefix("/media/")
    if "." not in filename:
        return None
    asset_id, extension = filename.rsplit(".", 1)
    extension = "." + extension.lower()
    if not re.fullmatch(r"[0-9a-f]{64}", asset_id, re.I) or extension not in {".jpg", ".jpeg", ".png", ".webp"}:
        return None
    return asset_id.lower(), extension


def _raw_value(payload: dict[str, Any], key: str) -> object:
    raw = payload.get("raw")
    return raw.get(key) if isinstance(raw, dict) else ""


def _is_sensitive_key(key: object) -> bool:
    raw = str(key or "").lower()
    normalized = re.sub(r"[^a-z0-9]", "", raw)
    terms = {term for term in re.split(r"[^a-z0-9]+", raw) if term}
    if terms & {"auth", "bearer", "cookie", "token", "jwt", "secret", "password", "subscription"}:
        return True
    return any(marker == normalized or marker in normalized for marker in SENSITIVE_KEY_MARKERS if len(marker) > 4)


def _sanitize_string(value: str) -> str:
    text = str(value or "")
    if text.startswith("/media/") and _safe_media_route(text):
        return text
    if text.startswith("data:image/"):
        return ""
    text = URL_RE.sub("", text)
    text = JWT_RE.sub("", text)
    text = TOKEN_LIKE_RE.sub("", text)
    text = SECRET_VALUE_RE.sub("", text)
    text = re.sub(r"\s{2,}", " ", text).strip()
    if _is_sensitive_key(text):
        return ""
    return text


def _sanitize_catalog_payload(value: object) -> object:
    if isinstance(value, dict):
        sanitized: dict[str, object] = {}
        for key, nested in value.items():
            if _is_sensitive_key(key):
                continue
            sanitized[str(key)] = _sanitize_catalog_payload(nested)
        return sanitized
    if isinstance(value, list):
        return [_sanitize_catalog_payload(nested) for nested in value]
    if isinstance(value, tuple):
        return tuple(_sanitize_catalog_payload(nested) for nested in value)
    if isinstance(value, str):
        return _sanitize_string(value)
    return value


def _strip_external(value: object) -> object:
    if isinstance(value, str):
        return _sanitize_string(value)
    if isinstance(value, dict):
        return {str(key): _strip_external(nested) for key, nested in value.items() if not _is_sensitive_key(key)}
    if isinstance(value, list):
        return [_strip_external(nested) for nested in value]
    return value


def _name_from_derived_id(value: str) -> str:
    text = str(value or "")
    if not text.startswith("derived:"):
        return text
    try:
        encoded = text.split(":", 1)[1]
        return base64.urlsafe_b64decode((encoded + "=" * (-len(encoded) % 4)).encode("ascii")).decode("utf-8")
    except Exception:
        return ""


def _relation_features(item: MediaItem) -> dict[str, set[str]]:
    return {
        "director": set(item.directors),
        "cast": set(item.casts[:8]),
        "genre": set(item.genres),
        "country": set(item.countries),
        "media_type": {item.media_type} if item.media_type else set(),
        "year_bucket": {f"{item.year // 10 * 10}s"} if item.year else set(),
    }


def _shared_reasons(a: dict[str, set[str]], b: dict[str, set[str]]) -> list[tuple[str, str]]:
    shared = [(field, value) for field in RELATION_FIELDS for value in sorted(a.get(field, set()) & b.get(field, set())) if value]
    shared.sort(key=lambda pair: (-RELATION_WEIGHTS.get(pair[0], 0), pair[0], pair[1]))
    return shared


def _reason_label(field: str) -> str:
    return {"director": "shared director", "cast": "shared cast", "genre": "shared genre", "country": "shared country", "media_type": "same media type", "year_bucket": "same decade"}.get(field, field)


def _preference_features(item: MediaItem) -> list[str]:
    values: list[str] = []
    for field, features in (("genre", item.genres), ("director", item.directors), ("cast", item.casts[:4]), ("country", item.countries), ("media_type", [item.media_type] if item.media_type else [])):
        values.extend(f"{field}:{value}" for value in features if str(value or "").strip())
    return _dedupe(values)


def _payload_features(payload: dict[str, Any]) -> list[str]:
    out: list[str] = []
    for field in ("genre", "mood", "pace", "term", "country", "director", "cast", "media_type"):
        values = payload.get(field)
        values = values if isinstance(values, (list, tuple, set)) else [values]
        out.extend(f"{field}:{value}" for value in values if str(value or "").strip())
    features = payload.get("features")
    if isinstance(features, dict):
        for field, values in features.items():
            values = values if isinstance(values, (list, tuple, set)) else [values]
            out.extend(f"{field}:{value}" for value in values if str(value or "").strip())
    return _dedupe(out)


def _top_signals(bucket: dict[str, dict[str, Any]], limit: int) -> list[dict[str, object]]:
    rows = sorted(bucket.values(), key=lambda row: (-float(row.get("score") or 0), str(row.get("feature") or "")))
    return [{"feature": str(row["feature"]), "score": round(float(row.get("score") or 0), 4), "evidence_item_ids": list(row.get("evidence_item_ids") or []), "sources": list(row.get("sources") or [])} for row in rows[:limit] if row.get("evidence_item_ids")]


def _dedupe(values: list[str]) -> list[str]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return out
