from __future__ import annotations

import base64
import json
import math
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .database import AppDatabase
from .feedback_service import FeedbackService
from .media.store import MediaStore
from .models import MediaItem, recommendation_item_key
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

    def title(self, lookup_id: str) -> dict[str, object]:
        record = self.find_title(lookup_id)
        if record is None:
            raise ExplorationNotFound("title not found")
        return self.serialize_title(record)

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
        records, has_more = self.repository.paged_library(clean_state, clean_limit, parsed_cursor)
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "state": clean_state,
            "limit": clean_limit,
            "items": [self.serialize_title(record, include_schema=False) for record in records],
            "next_cursor": self._encode_cursor(records[-1]) if has_more and records else "",
        })

    def taste(self, profile_key: str = "default") -> dict[str, object]:
        profile_key = str(profile_key or "default").strip() or "default"
        records = self.repository.library_records()
        rated_items = [record.item for record in records if record.item.my_rating is not None]
        profile = build_taste_profile(rated_items, feedback_signals=self.feedback_service.feedback_signals(profile_key, time.time()))
        return _sanitize_catalog_payload({"schema_version": SCHEMA_VERSION, "profile_key": profile_key, "summary": profile.summary(), "groups": self._taste_groups(records, self.repository.feedback_rows(profile_key))})

    def build_universe_graph(self, focus_id: str, limit: int = 9) -> dict[str, object]:
        clean_limit = self._clamp_int(limit, 9, 3, 25)
        focus = self.find_title(focus_id)
        if focus is None:
            raise ExplorationNotFound("focus not found")
        scored: list[tuple[float, str, LibraryRecord, list[str]]] = []
        focus_features = _relation_features(focus.item)
        for record in self.repository.library_records():
            if record.item_key == focus.item_key:
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
        return _sanitize_catalog_payload({
            "schema_version": SCHEMA_VERSION,
            "focus_id": focus.item_key,
            "limit": clean_limit,
            "nodes": [self._node_payload(focus)] + [self._node_payload(row[2]) for row in selected],
            "edges": [{"source": focus.item_key, "target": row[2].item_key, "score": row[0], "reason": row[3][0], "reasons": row[3]} for row in selected],
        })

    def find_title(self, lookup_id: str) -> LibraryRecord | None:
        lookup = str(lookup_id or "").strip()
        if not lookup:
            return None
        records = self.repository.library_records()
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

    def serialize_title(self, record: LibraryRecord, *, include_schema: bool = True) -> dict[str, object]:
        identity = self.repository.media_identity_for_item(record)
        identity_id = identity.id if identity else ""
        asset_entity_id = identity_id or record.item_key
        result: dict[str, object] = {
            "id": identity_id or record.item_key,
            "item_key": record.item_key,
            "state": record.state,
            "title": record.item.title,
            "media_type": record.item.media_type,
            "year": record.item.year,
            "item": self._safe_item_payload(record),
            "poster": self._media_asset("media", asset_entity_id, "poster", record.payload.get("cover")),
            "backdrop": self._media_asset("media", asset_entity_id, "backdrop", record.payload.get("backdrop") or _raw_value(record.payload, "backdrop")),
            "people": self._people_for_title(record),
            "updated_at": record.updated_at,
        }
        return _sanitize_catalog_payload({"schema_version": SCHEMA_VERSION, **result} if include_schema else result)

    def _safe_item_payload(self, record: LibraryRecord) -> dict[str, object]:
        payload = media_item_to_dict(record.item)
        payload["url"] = ""
        payload["cover"] = ""
        source = str(record.item.source or "").strip()
        payload["source"] = "" if "://" in source else source
        payload["raw"] = self._safe_raw(record.payload)
        return _sanitize_catalog_payload(payload)

    def _people_for_title(self, record: LibraryRecord) -> list[dict[str, object]]:
        people: list[dict[str, object]] = []
        for role, names in (("director", record.item.directors), ("cast", record.item.casts)):
            for name in names:
                person_id = self._person_id_for_name(name)
                portrait = self._person_asset(person_id, name)
                people.append({"id": person_id, "role": role, "name": name, "portrait": portrait, "media_status": portrait["media_status"], "evidence_title_ids": [record.item_key]})
        return people

    def _derive_person(self, lookup_id: str, identity: dict[str, Any] | None):
        person_id, name, aliases, metadata = lookup_id, "", [], {}
        if identity:
            person_id, name = str(identity["id"]), str(identity["name"])
            aliases, metadata = list(identity.get("aliases") or []), dict(identity.get("metadata") or {})
        else:
            name = _name_from_derived_id(lookup_id)
        evidence = [record for record in self.repository.library_records() if name and self._roles_for_person(record, name)]
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
        if entity_id:
            override = self.repository.asset_override(entity_kind, entity_id, kind)
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
            return {"url": "", "media_status": "designed-fallback" if kind == "poster" else "missing"}
        return {"url": "", "media_status": "missing"}

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
            for key in ("people", "credits"):
                if key in raw:
                    allowed[key] = _strip_external(raw[key])
        return allowed

    def _node_payload(self, record: LibraryRecord) -> dict[str, object]:
        identity = self.repository.media_identity_for_item(record)
        return {"id": record.item_key, "title": record.item.title, "media_type": record.item.media_type, "year": record.item.year, "poster": self._media_asset("media", identity.id if identity else record.item_key, "poster", record.payload.get("cover"))}

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


def _json_list(value: object) -> list[str]:
    try:
        decoded = json.loads(str(value or "[]"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return []
    return [str(item) for item in decoded] if isinstance(decoded, list) else []


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
