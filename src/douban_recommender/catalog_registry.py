from __future__ import annotations

import base64
import json
import unicodedata
from dataclasses import dataclass
from typing import Iterable

from .models import MediaItem
from .privacy import scrub_sensitive
from .serialization import media_item_from_dict, media_item_to_dict


_LIST_FIELDS = ("genres", "countries", "languages", "directors", "casts", "tags")
_STATE_RANK = {
    "candidate": 1,
    "wish": 2,
    "wanted": 2,
    "watched": 3,
    "collect": 3,
    "rated": 3,
}


@dataclass(frozen=True)
class _RegistrationItem:
    item_key: str
    item: MediaItem
    payload: dict[str, object]
    state: str


def _json_dumps(value: object) -> str:
    return json.dumps(value, ensure_ascii=False, sort_keys=True, separators=(",", ":"))


def _json_object(value: object) -> dict[str, object]:
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
    if not isinstance(decoded, list):
        return []
    return _dedupe(decoded)


def _dedupe(values: Iterable[object]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        seen.add(text)
        result.append(text)
    return result


def _clean_item(value: MediaItem | dict[str, object]) -> tuple[MediaItem, dict[str, object]] | None:
    if isinstance(value, MediaItem):
        raw_payload = media_item_to_dict(value)
    elif isinstance(value, dict):
        raw_payload = dict(value)
    else:
        return None
    scrubbed = scrub_sensitive(raw_payload)
    payload = scrubbed if isinstance(scrubbed, dict) else {}
    item = media_item_from_dict(payload)
    if not item.title:
        return None
    clean_payload = media_item_to_dict(item)
    clean_payload["raw"] = dict(item.raw)
    return item, clean_payload


def _library_state(item: MediaItem) -> str:
    source = str(item.source or "").strip().casefold()
    status = source.rsplit(":", 1)[-1]
    tags = {str(tag or "").strip().casefold() for tag in item.tags}
    if status == "collect" or tags & {"collect", "watched", "看过"}:
        return "watched"
    if status == "wish" or tags & {"wish", "wanted", "想看"}:
        return "wish"
    return "candidate"


def _state_rank(state: object) -> int:
    return _STATE_RANK.get(str(state or "").strip().casefold(), 0)


def _payload_richness(payload: dict[str, object]) -> int:
    score = 0
    for value in payload.values():
        if value in (None, "", [], {}):
            continue
        score += len(value) if isinstance(value, (list, dict)) else 1
    return score


def _merge_payload(preferred: dict[str, object], secondary: dict[str, object]) -> dict[str, object]:
    merged = dict(secondary)
    for field in _LIST_FIELDS:
        merged[field] = _dedupe([*(preferred.get(field) or []), *(secondary.get(field) or [])])
    secondary_raw = secondary.get("raw") if isinstance(secondary.get("raw"), dict) else {}
    preferred_raw = preferred.get("raw") if isinstance(preferred.get("raw"), dict) else {}
    raw = _merge_metadata(dict(secondary_raw), dict(preferred_raw))
    for key, value in preferred.items():
        if key in _LIST_FIELDS or key == "raw":
            continue
        if value not in (None, "", [], {}):
            merged[key] = value
    merged["raw"] = raw
    return merged


def _coalesce_items(items: Iterable[MediaItem | dict[str, object]]) -> dict[str, _RegistrationItem]:
    registrations: dict[str, _RegistrationItem] = {}
    for value in items:
        cleaned = _clean_item(value)
        if cleaned is None:
            continue
        item, payload = cleaned
        item_key = item.identity
        state = _library_state(item)
        incoming = _RegistrationItem(item_key, item, payload, state)
        current = registrations.get(item_key)
        if current is None:
            registrations[item_key] = incoming
            continue
        incoming_key = (_state_rank(incoming.state), _payload_richness(incoming.payload), _json_dumps(incoming.payload))
        current_key = (_state_rank(current.state), _payload_richness(current.payload), _json_dumps(current.payload))
        preferred, secondary = (incoming, current) if incoming_key >= current_key else (current, incoming)
        merged_payload = _merge_payload(preferred.payload, secondary.payload)
        merged_item = media_item_from_dict(merged_payload)
        registrations[item_key] = _RegistrationItem(item_key, merged_item, merged_payload, preferred.state)
    return registrations


def _merge_metadata(existing: dict[str, object], incoming: dict[str, object]) -> dict[str, object]:
    merged = dict(existing)
    for key, value in incoming.items():
        current = merged.get(key)
        if value in (None, "", [], {}):
            continue
        if isinstance(value, list):
            merged[key] = _dedupe([*value, *(current if isinstance(current, list) else [])])
        elif isinstance(value, dict):
            merged[key] = _merge_metadata(current if isinstance(current, dict) else {}, value)
        else:
            merged[key] = value
    return merged


def _aliases(item: MediaItem) -> list[str]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    values: list[object] = []
    for key in ("aliases", "original_titles", "original_title"):
        value = raw.get(key)
        if isinstance(value, (list, tuple, set)):
            values.extend(value)
        elif value:
            values.append(value)
    return [alias for alias in _dedupe(values) if alias != item.title]


def _person_id(name: str) -> str:
    normalized = unicodedata.normalize("NFKC", str(name or "").strip())
    encoded = base64.urlsafe_b64encode(normalized.encode("utf-8")).decode("ascii").rstrip("=")
    return f"derived:{encoded}"


def _person_photo_sources(item: MediaItem, name: str) -> list[str]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    photos = raw.get("people_photos")
    if not isinstance(photos, dict):
        return []
    target = unicodedata.normalize("NFKC", str(name or "").strip())
    sources: list[str] = []
    for raw_key, raw_value in photos.items():
        key = unicodedata.normalize("NFKC", str(raw_key or "").strip())
        if ":" in key:
            prefix, matched_name = (part.strip() for part in key.split(":", 1))
            if prefix not in {"导演", "主演", "演员", "配音"}:
                continue
        else:
            matched_name = key
        if matched_name != target:
            continue
        values = raw_value if isinstance(raw_value, (list, tuple, set)) else (raw_value,)
        for value in values:
            url = str(value or "").strip()
            if url.startswith(("https://", "http://")) and url not in sources:
                sources.append(url)
    return sources


class CatalogRegistry:
    @staticmethod
    def register_sync_items(
        connection,
        user_id: str,
        items: Iterable[MediaItem | dict[str, object]],
        now: float,
    ) -> dict[str, int]:
        registrations = _coalesce_items(items)
        if not registrations:
            return {
                "library_items": 0,
                "media_identities": 0,
                "person_identities": 0,
                "provider_identities": 0,
            }
        clean_user_id = str(user_id or "").strip()
        active_row = connection.execute(
            "SELECT value FROM schema_meta WHERE key='active_douban_user_id'"
        ).fetchone()
        active_user_id = str(active_row[0] or "").strip() if active_row else ""
        if active_user_id and clean_user_id and active_user_id != clean_user_id:
            connection.execute(
                """
                DELETE FROM library_items
                WHERE source LIKE 'douban-sync:%' OR source LIKE 'douban_user:%'
                """
            )
        people: dict[str, dict[str, object]] = {}
        provider_ids: set[str] = set()

        for item_key in sorted(registrations):
            registration = registrations[item_key]
            effective = CatalogRegistry._upsert_library_item(
                connection,
                registration,
                clean_user_id,
                float(now),
            )
            CatalogRegistry._upsert_media_identity(connection, item_key, effective, float(now))
            if effective.douban_id:
                CatalogRegistry._upsert_douban_identity(connection, item_key, effective, float(now))
                provider_ids.add(str(effective.douban_id))
            for role, names in (("director", effective.directors), ("cast", effective.casts)):
                for name in names:
                    clean_name = unicodedata.normalize("NFKC", str(name or "").strip())
                    if not clean_name:
                        continue
                    person = people.setdefault(
                        clean_name,
                        {
                            "roles": set(),
                            "evidence_title_ids": set(),
                            "known_works": set(),
                            "portrait_source_urls": set(),
                        },
                    )
                    person["roles"].add(role)
                    person["evidence_title_ids"].add(item_key)
                    person["known_works"].add(effective.title)
                    person["portrait_source_urls"].update(_person_photo_sources(effective, clean_name))

        for name in sorted(people):
            CatalogRegistry._upsert_person_identity(connection, name, people[name], float(now))

        connection.execute(
            """
            INSERT INTO schema_meta(key, value) VALUES('active_douban_user_id', ?)
            ON CONFLICT(key) DO UPDATE SET value=excluded.value
            """,
            (clean_user_id,),
        )
        return {
            "library_items": len(registrations),
            "media_identities": len(registrations),
            "person_identities": len(people),
            "provider_identities": len(provider_ids),
        }

    @staticmethod
    def _upsert_library_item(
        connection,
        registration: _RegistrationItem,
        user_id: str,
        now: float,
    ) -> MediaItem:
        existing = connection.execute(
            "SELECT payload_json, state, source FROM library_items WHERE item_key=?",
            (registration.item_key,),
        ).fetchone()
        payload = dict(registration.payload)
        state = registration.state
        source = (
            f"douban-sync:{user_id}:{state}"
            if user_id and state in {"watched", "wish"}
            else str(registration.item.source or "")
        )
        if existing is not None:
            existing_payload = _json_object(existing["payload_json"])
            if _state_rank(existing["state"]) > _state_rank(registration.state):
                payload = _merge_payload(existing_payload, payload)
                state = str(existing["state"] or state)
                source = str(existing["source"] or source)
            else:
                payload = _merge_payload(payload, existing_payload)
        item = media_item_from_dict(payload)
        connection.execute(
            """
            INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_key) DO UPDATE SET
                payload_json=excluded.payload_json,
                state=excluded.state,
                source=excluded.source,
                updated_at=excluded.updated_at
            """,
            (
                registration.item_key,
                _json_dumps(payload),
                state,
                source,
                now,
                now,
            ),
        )
        return item

    @staticmethod
    def _upsert_media_identity(connection, item_key: str, item: MediaItem, now: float) -> None:
        existing = connection.execute(
            """
            SELECT original_titles_json, countries_json, metadata_json
            FROM media_identities WHERE id=?
            """,
            (item_key,),
        ).fetchone()
        aliases = _aliases(item)
        countries = list(item.countries)
        metadata = {
            "item_key": item_key,
            "douban_id": str(item.douban_id or ""),
            "source_url": str(item.url or ""),
            "cover_url": str(item.cover or ""),
            "summary": str(item.summary or ""),
            "genres": list(item.genres),
            "languages": list(item.languages),
            "directors": list(item.directors),
            "casts": list(item.casts),
            "tags": list(item.tags),
            "raw": dict(item.raw),
        }
        if existing is not None:
            aliases = _dedupe([*aliases, *_json_list(existing["original_titles_json"])])
            countries = _dedupe([*countries, *_json_list(existing["countries_json"])])
            metadata = _merge_metadata(_json_object(existing["metadata_json"]), metadata)
        connection.execute(
            """
            INSERT INTO media_identities(
                id, title, original_titles_json, year, media_type, countries_json,
                metadata_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                title=excluded.title,
                original_titles_json=excluded.original_titles_json,
                year=COALESCE(excluded.year, media_identities.year),
                media_type=CASE WHEN excluded.media_type='' THEN media_identities.media_type ELSE excluded.media_type END,
                countries_json=excluded.countries_json,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (
                item_key,
                item.title,
                _json_dumps(aliases),
                item.year,
                str(item.media_type or ""),
                _json_dumps(countries),
                _json_dumps(metadata),
                now,
                now,
            ),
        )

    @staticmethod
    def _upsert_douban_identity(connection, item_key: str, item: MediaItem, now: float) -> None:
        provider_id = str(item.douban_id or "").strip()
        metadata = {"source_url": str(item.url or ""), "item_key": item_key}
        row = connection.execute(
            """
            SELECT metadata_json FROM provider_identities
            WHERE entity_kind='media' AND provider='douban' AND provider_id=?
            """,
            (provider_id,),
        ).fetchone()
        if row is not None:
            metadata = _merge_metadata(_json_object(row["metadata_json"]), metadata)
        connection.execute(
            """
            INSERT INTO provider_identities(
                entity_kind, entity_id, provider, provider_id, confidence,
                metadata_json, created_at, updated_at
            ) VALUES('media', ?, 'douban', ?, 1.0, ?, ?, ?)
            ON CONFLICT(entity_kind, provider, provider_id) DO UPDATE SET
                entity_id=excluded.entity_id,
                confidence=excluded.confidence,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (item_key, provider_id, _json_dumps(metadata), now, now),
        )

    @staticmethod
    def _upsert_person_identity(connection, name: str, evidence: dict[str, object], now: float) -> None:
        person_id = _person_id(name)
        row = connection.execute(
            "SELECT aliases_json, metadata_json FROM person_identities WHERE id=?",
            (person_id,),
        ).fetchone()
        metadata = {
            "roles": sorted(evidence["roles"]),
            "evidence_title_ids": sorted(evidence["evidence_title_ids"]),
            "known_works": sorted(evidence["known_works"]),
            "portrait_source_urls": sorted(evidence.get("portrait_source_urls") or []),
        }
        aliases: list[str] = []
        if row is not None:
            aliases = _json_list(row["aliases_json"])
            metadata = _merge_metadata(_json_object(row["metadata_json"]), metadata)
        for key in ("roles", "evidence_title_ids", "known_works", "portrait_source_urls"):
            metadata[key] = sorted(_dedupe(metadata.get(key) if isinstance(metadata.get(key), list) else []))
        connection.execute(
            """
            INSERT INTO person_identities(
                id, name, aliases_json, metadata_json, created_at, updated_at
            ) VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(id) DO UPDATE SET
                name=excluded.name,
                aliases_json=excluded.aliases_json,
                metadata_json=excluded.metadata_json,
                updated_at=excluded.updated_at
            """,
            (person_id, name, _json_dumps(aliases), _json_dumps(metadata), now, now),
        )
