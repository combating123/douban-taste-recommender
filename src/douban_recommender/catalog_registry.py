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
_PLACEHOLDER_PORTRAIT_MARKERS = (
    "personage-default",
    "celebrity-default",
    "default-avatar",
    "default_portrait",
)


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
            if (
                url.startswith(("https://", "http://"))
                and not any(marker in url.casefold() for marker in _PLACEHOLDER_PORTRAIT_MARKERS)
                and url not in sources
            ):
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
    def reconcile_sync_snapshot(
        connection,
        user_id: str,
        items: Iterable[MediaItem | dict[str, object]],
        now: float,
    ) -> dict[str, int]:
        """Make a fully successful Douban crawl an authoritative user-library snapshot."""

        clean_user_id = str(user_id or "").strip()
        registrations = _coalesce_items(items)
        snapshot_keys: set[str] = set()
        updated = 0
        for item_key, registration in registrations.items():
            if registration.state not in {"watched", "wish"}:
                continue
            snapshot_keys.add(item_key)
            existing = connection.execute(
                "SELECT payload_json FROM library_items WHERE item_key=?",
                (item_key,),
            ).fetchone()
            existing_payload = _json_object(existing["payload_json"]) if existing else {}
            payload = _merge_payload(registration.payload, existing_payload)
            status_tags = {"collect", "watched", "看过", "wish", "wanted", "想看"}
            tags = [tag for tag in _dedupe(payload.get("tags") or []) if tag.casefold() not in status_tags]
            status = "collect" if registration.state == "watched" else "wish"
            tags.append("看过" if registration.state == "watched" else "想看")
            payload["tags"] = tags
            payload["source"] = f"douban_user:{status}"
            source = f"douban-sync:{clean_user_id}:{registration.state}"
            connection.execute(
                """
                UPDATE library_items
                SET payload_json=?, state=?, source=?, updated_at=?
                WHERE item_key=?
                """,
                (_json_dumps(payload), registration.state, source, float(now), item_key),
            )
            updated += 1

        where = "source LIKE ? OR source LIKE 'douban_user:%'"
        params: list[object] = [f"douban-sync:{clean_user_id}:%"]
        if snapshot_keys:
            placeholders = ",".join("?" for _ in snapshot_keys)
            where = f"({where}) AND item_key NOT IN ({placeholders})"
            params.extend(sorted(snapshot_keys))
        deleted = connection.execute(
            f"DELETE FROM library_items WHERE {where}",
            params,
        ).rowcount
        return {"updated": updated, "deleted": max(0, int(deleted or 0)), "snapshot_items": len(snapshot_keys)}

    @staticmethod
    def register_enriched_item(
        connection,
        item_key: str,
        item: MediaItem | dict[str, object],
        now: float,
    ) -> MediaItem:
        """Patch verified metadata into an existing library row without changing its route key."""

        cleaned = _clean_item(item)
        if cleaned is None:
            raise ValueError("enriched item requires a title")
        enriched_item, enriched_payload = cleaned
        existing = connection.execute(
            "SELECT payload_json FROM library_items WHERE item_key=?",
            (str(item_key),),
        ).fetchone()
        if existing is None:
            raise KeyError("library item not found")

        enriched_raw = enriched_payload.get("raw") if isinstance(enriched_payload.get("raw"), dict) else {}
        repaired_identity = bool(str(enriched_raw.get("identity_repaired_from") or "").strip())
        merged_payload = (
            enriched_payload
            if repaired_identity
            else _merge_payload(enriched_payload, _json_object(existing["payload_json"]))
        )
        people_credit_source = str(enriched_raw.get("people_credit_source") or "").strip()
        expected_credit_source = f"douban:{str(enriched_item.douban_id or '').strip()}"
        if people_credit_source == expected_credit_source and expected_credit_source.removeprefix("douban:").isdigit():
            for field in ("directors", "casts"):
                authoritative_names = enriched_payload.get(field)
                if isinstance(authoritative_names, list) and authoritative_names:
                    merged_payload[field] = list(authoritative_names)
        if isinstance(enriched_raw.get("people_photos"), dict):
            merged_raw = merged_payload.get("raw") if isinstance(merged_payload.get("raw"), dict) else {}
            merged_raw["people_photos"] = dict(enriched_raw["people_photos"])
            merged_payload["raw"] = merged_raw
        effective = media_item_from_dict(merged_payload)
        if repaired_identity:
            current_douban_id = str(effective.douban_id or "").strip()
            connection.execute(
                """
                DELETE FROM provider_identities
                WHERE entity_kind='media' AND entity_id=? AND provider='douban' AND provider_id<>?
                """,
                (str(item_key), current_douban_id),
            )
            for table in ("asset_candidates", "resolution_jobs", "user_asset_overrides"):
                connection.execute(
                    f"DELETE FROM {table} WHERE entity_kind='media' AND entity_id=?",
                    (str(item_key),),
                )
        connection.execute(
            "UPDATE library_items SET payload_json=?, updated_at=? WHERE item_key=?",
            (_json_dumps(merged_payload), float(now), str(item_key)),
        )
        CatalogRegistry._upsert_media_identity(
            connection,
            str(item_key),
            effective,
            float(now),
            replace_existing=repaired_identity,
        )
        if effective.douban_id:
            CatalogRegistry._upsert_douban_identity(connection, str(item_key), effective, float(now))

        for role, names in (("director", effective.directors), ("cast", effective.casts)):
            for name in names:
                clean_name = unicodedata.normalize("NFKC", str(name or "").strip())
                if not clean_name:
                    continue
                CatalogRegistry._upsert_person_identity(
                    connection,
                    clean_name,
                    {
                        "roles": {role},
                        "evidence_title_ids": {str(item_key)},
                        "known_works": {effective.title},
                        "portrait_source_urls": set(_person_photo_sources(effective, clean_name)),
                    },
                    float(now),
                )
        return effective

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
    def _upsert_media_identity(
        connection,
        item_key: str,
        item: MediaItem,
        now: float,
        *,
        replace_existing: bool = False,
    ) -> None:
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
        if existing is not None and not replace_existing:
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
        metadata["portrait_source_urls"] = [
            url
            for url in metadata["portrait_source_urls"]
            if not any(marker in url.casefold() for marker in _PLACEHOLDER_PORTRAIT_MARKERS)
        ]
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
