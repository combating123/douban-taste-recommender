from __future__ import annotations

import copy
import json
import time
from dataclasses import asdict, replace
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlsplit, urlunsplit

from .candidate_origin import candidate_origin
from .candidate_planner import build_candidate_plan
from .catalog_enrichment import enrich_media_items_parallel
from .curated_catalog import (
    TITLE_PEOPLE_METADATA,
    apply_curated_people_photos,
    apply_curated_posters,
    backfill_missing_media_types,
    curated_metadata_for_title,
)
from .database import AppDatabase
from .douban_sources import fetch_candidates_from_plan, fetch_douban_candidates, fetch_douban_detail_html, fetch_url_candidates
from .feedback_service import FeedbackEvent, FeedbackService
from .global_discovery import GlobalDiscoveryConfig, GlobalDiscoveryReport, discover_global_candidates
from .intent_parser import RecommendationIntent, intent_to_chips, parse_recommendation_intent
from .io import load_media_csv, load_media_csv_from_text
from .language_adapter import LanguageService, LocalRuleLanguageAdapter, OpenAICompatibleLanguageAdapter
from .media.store import MediaStore
from .models import MediaItem, recommendation_identity_tokens, recommendation_item_key
from .profiler import build_taste_profile
from .privacy import scrub_sensitive
from .ranking import rank_candidates
from .recommendation_service import RecommendationBatch, RecommendationSession, RecommendationSessionService
from .runtime_paths import resolve_database_path, resolve_media_dir
from .serialization import media_item_from_dict, media_item_to_dict


SCHEMA_VERSION = 2
ROOT = Path(__file__).resolve().parents[2]
DEFAULT_SAMPLE_RATINGS = ROOT / "sample_data" / "ratings_sample.csv"
DEFAULT_SAMPLE_CANDIDATES = ROOT / "sample_data" / "candidates_sample.csv"
CHANNEL_ORDER = ("电影", "电视剧", "动漫")
CHANNEL_FLAGS = {
    "电影": "include_movies",
    "电视剧": "include_series",
    "动漫": "include_anime",
}
EVENT_SCOPE_RULES = {
    "want": {"permanent"},
    "watched": {"permanent"},
    "tonight-candidate": {"session"},
    "not-tonight": {"session"},
    "less-like-this": {"permanent"},
    "more-like-this": {"permanent"},
    "permanent-avoid": {"permanent"},
    "data-error": {"permanent"},
}
SESSION_ONLY_EVENT_TYPES = {"not-tonight", "tonight-candidate"}
SESSION_STATE_EVENT_TYPES = {"not-tonight", "watched", "want", "permanent-avoid"}
ITEM_TEXT_FIELDS = {
    "title",
    "media_type",
    "url",
    "douban_id",
    "cover",
    "summary",
    "source",
}
ITEM_NUMBER_FIELDS = {"my_rating", "douban_rating", "vote_count", "year"}
ITEM_STRING_LIST_FIELDS = {"genres", "countries", "languages", "directors", "casts", "tags"}
INTENT_STRING_LIST_FIELDS = {
    "media_types",
    "genres",
    "moods",
    "countries",
    "languages",
    "avoid",
    "session_only_adjustments",
    "permanent_avoid",
}
INTENT_TEXT_FIELDS = {"pace", "complexity", "intensity_max", "free_text"}
INTENT_NUMBER_FIELDS = {
    "runtime_max",
    "episode_runtime_max",
    "year_min",
    "year_max",
    "quality_floor",
    "exploration_level",
    "surprise_level",
}
CREATE_SESSION_STRING_FIELDS = {"ratings_csv", "candidates_csv", "profile_key", "intent_text", "text"}
CREATE_SESSION_STRING_LIST_FIELDS = {"candidate_urls", "like_terms", "dislike_terms"}
CREATE_SESSION_INTEGER_FIELDS = {"batch_size", "visible_size", "limit", "per_query"}
CREATE_SESSION_BOOL_FIELDS = {
    "include_movies",
    "include_series",
    "include_anime",
    "fetch_douban",
    "fetch_global",
    "use_local_index",
    "use_sample_ratings",
    "use_sample_candidates",
}
FEEDBACK_STRING_FIELDS = {"event_type", "scope", "item_key", "session_id", "profile_key"}
LANGUAGE_STRING_FIELDS = {"endpoint", "model", "api_key"}


class RecommendationApiError(ValueError):
    status_code = 400


class RecommendationApiNotFound(RecommendationApiError):
    status_code = 404


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _raise_schema_error(path: str, message: str) -> None:
    raise RecommendationApiError(f"{path} {message}")


def _validate_optional_string_field(payload: dict[str, Any], field: str) -> None:
    if field in payload and not isinstance(payload[field], str):
        _raise_schema_error(field, "must be string")


def _validate_optional_bool_field(payload: dict[str, Any], field: str) -> None:
    if field in payload and type(payload[field]) is not bool:
        _raise_schema_error(field, "must be bool")


def _validate_optional_integer_field(payload: dict[str, Any], field: str) -> None:
    if field in payload and type(payload[field]) is not int:
        _raise_schema_error(field, "must be integer")


def _validate_string_or_string_array(value: object, path: str) -> None:
    if isinstance(value, str):
        return
    if isinstance(value, list):
        for index, item in enumerate(value):
            if not isinstance(item, str):
                _raise_schema_error(f"{path}[{index}]", "must be string")
        return
    _raise_schema_error(path, "must be string or string array")


def _validate_item_schema(item: dict[str, Any], path: str) -> None:
    for field in ITEM_TEXT_FIELDS:
        if field in item and not isinstance(item[field], str):
            _raise_schema_error(f"{path}.{field}", "must be string")
    for field in ITEM_NUMBER_FIELDS:
        if field in item and not _is_number(item[field]):
            _raise_schema_error(f"{path}.{field}", "must be number")
    for field in ITEM_STRING_LIST_FIELDS:
        if field in item:
            _validate_string_or_string_array(item[field], f"{path}.{field}")


def _validate_item_array(payload: dict[str, Any], field: str) -> None:
    if field not in payload:
        return
    value = payload[field]
    if not isinstance(value, list):
        _raise_schema_error(field, "must be array<object>")
    for index, item in enumerate(value):
        if not isinstance(item, dict):
            _raise_schema_error(f"{field}[{index}]", "must be object")
        _validate_item_schema(item, f"{field}[{index}]")


def _sanitize_unverified_expansion(item: MediaItem) -> MediaItem:
    if str(item.source or "") != "premium_expansion":
        return item
    raw = dict(item.raw or {})
    aliases = [str(value).strip() for value in raw.get("aliases", []) if str(value).strip()]
    format_value = str(raw.get("format") or "").strip()
    item.my_rating = None
    item.douban_rating = None
    item.vote_count = None
    item.year = None
    item.genres = []
    item.countries = []
    item.languages = []
    item.directors = []
    item.casts = []
    item.tags = []
    item.douban_id = ""
    item.cover = ""
    item.summary = ""
    item.source = "title_seed"
    item.raw = {"aliases": aliases, **({"format": format_value} if format_value else {})}
    return item


def _validate_intent_schema(payload: dict[str, Any]) -> None:
    if "intent" not in payload:
        return
    intent = payload["intent"]
    if not isinstance(intent, dict):
        _raise_schema_error("intent", "must be object")
    for field in INTENT_STRING_LIST_FIELDS:
        if field in intent:
            _validate_string_or_string_array(intent[field], f"intent.{field}")
    for field in INTENT_TEXT_FIELDS:
        if field in intent and not isinstance(intent[field], str):
            _raise_schema_error(f"intent.{field}", "must be string")
    for field in INTENT_NUMBER_FIELDS:
        if field in intent and not _is_number(intent[field]):
            _raise_schema_error(f"intent.{field}", "must be number")


def _validate_batch_size_by_channel(payload: dict[str, Any]) -> None:
    if "batch_size_by_channel" not in payload:
        return
    value = payload["batch_size_by_channel"]
    if not isinstance(value, dict):
        _raise_schema_error("batch_size_by_channel", "must be object")
    for channel, size in value.items():
        if channel not in CHANNEL_ORDER:
            _raise_schema_error(f"batch_size_by_channel.{channel}", f"must use one of {', '.join(CHANNEL_ORDER)}")
        if type(size) is not int:
            _raise_schema_error(f"batch_size_by_channel.{channel}", "must be integer")


def _to_int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _base_text(text: object) -> str:
    return str(text or "").strip()


def _strings(value: object) -> list[str]:
    if isinstance(value, str):
        values = value.replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = ()
    out: list[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if text and text not in out:
            out.append(text)
    return out


def _merge_intents(base: RecommendationIntent | None, parsed: RecommendationIntent) -> RecommendationIntent:
    if base is None:
        return parsed
    defaults = RecommendationIntent()
    merged = base.to_dict()
    for field, value in parsed.to_dict().items():
        if value != getattr(defaults, field):
            merged[field] = value
    return RecommendationIntent.from_dict(merged)


def _scrub_intent(intent: RecommendationIntent) -> RecommendationIntent:
    cleaned: dict[str, object] = {}
    for field, value in intent.to_dict().items():
        if isinstance(value, str):
            cleaned[field] = scrub_sensitive(value)
        elif isinstance(value, (list, tuple)):
            cleaned[field] = [scrub_sensitive(item) if isinstance(item, str) else item for item in value]
        else:
            cleaned[field] = value
    return RecommendationIntent.from_dict(cleaned)


def _item_dicts(value: object) -> list[MediaItem]:
    if not isinstance(value, list):
        return []
    string_defaults = {
        "title": "",
        "media_type": "",
        "url": "",
        "douban_id": "",
        "cover": "",
        "summary": "",
        "source": "",
    }
    return [
        media_item_from_dict({**string_defaults, **row})
        for row in value
        if isinstance(row, dict)
    ]


def _candidate_richness(item: MediaItem) -> tuple[int, int, int, int]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    return (
        int(bool(item.cover)) * 8
        + int(bool(item.summary)) * 5
        + int(bool(item.year)) * 2
        + len(item.genres)
        + len(item.directors)
        + min(4, len(item.casts))
        + len(ratings) * 2,
        len(item.summary or ""),
        int(item.vote_count or 0),
        len(raw),
    )


def _merge_candidate_raw(primary: dict[str, object], secondary: dict[str, object]) -> dict[str, object]:
    merged = copy.deepcopy(secondary)
    for key, value in primary.items():
        if value not in (None, "", [], {}):
            merged[key] = copy.deepcopy(value)
    for key in ("ratings", "provider_ids", "rating_votes"):
        left = primary.get(key) if isinstance(primary.get(key), dict) else {}
        right = secondary.get(key) if isinstance(secondary.get(key), dict) else {}
        if left or right:
            merged[key] = {**right, **left}
    for key in ("aliases", "discovery_sources", "stills"):
        left = primary.get(key) if isinstance(primary.get(key), list) else []
        right = secondary.get(key) if isinstance(secondary.get(key), list) else []
        values = []
        markers: set[str] = set()
        for value in [*left, *right]:
            marker = repr(value)
            if marker in markers:
                continue
            markers.add(marker)
            values.append(copy.deepcopy(value))
        if values:
            merged[key] = values
    return merged


def _merge_candidate_items(left: MediaItem, right: MediaItem) -> MediaItem:
    primary, secondary = (left, right) if _candidate_richness(left) >= _candidate_richness(right) else (right, left)
    merged = copy.deepcopy(primary)
    for field_name in ("genres", "countries", "languages", "directors", "casts", "tags"):
        values: list[str] = []
        for value in [*getattr(primary, field_name), *getattr(secondary, field_name)]:
            clean = str(value or "").strip()
            if clean and clean not in values:
                values.append(clean)
        setattr(merged, field_name, values)
    if len(secondary.summary or "") > len(merged.summary or ""):
        merged.summary = secondary.summary
    for field_name in ("year", "douban_rating", "my_rating"):
        if getattr(merged, field_name) is None:
            setattr(merged, field_name, getattr(secondary, field_name))
    for field_name in ("cover", "url", "douban_id"):
        if not getattr(merged, field_name):
            setattr(merged, field_name, getattr(secondary, field_name))
    merged.vote_count = max(int(primary.vote_count or 0), int(secondary.vote_count or 0)) or None
    sources = [source for source in [*str(primary.source or "").split("|"), *str(secondary.source or "").split("|")] if source]
    merged.source = "|".join(dict.fromkeys(sources))
    merged.raw = _merge_candidate_raw(
        primary.raw if isinstance(primary.raw, dict) else {},
        secondary.raw if isinstance(secondary.raw, dict) else {},
    )
    return merged


def _is_generated_summary(value: object) -> bool:
    summary = str(value or "").strip()
    return not summary or any(
        summary.startswith(prefix)
        for prefix in (
            "正在补齐这部",
            "资料有限：本地片库暂未记录作品简介",
            "由 CineScope 精选扩展池补入的",
            "详情：点击卡片查看简介",
        )
    )


def _hydrate_batch_item_from_catalog(item: dict[str, object], catalog: dict[str, object] | None) -> dict[str, object]:
    if not isinstance(catalog, dict):
        return dict(item)
    hydrated = copy.deepcopy(dict(item))
    stored = media_item_from_dict(catalog)
    for field_name in ("title", "media_type", "url", "douban_id", "cover"):
        value = str(getattr(stored, field_name) or "").strip()
        if value and not str(hydrated.get(field_name) or "").strip():
            hydrated[field_name] = value
    stored_summary = str(stored.summary or "").strip()
    current_summary = str(hydrated.get("summary") or "").strip()
    if stored_summary and (_is_generated_summary(current_summary) or len(stored_summary) > len(current_summary)):
        hydrated["summary"] = stored_summary
    for field_name in ("genres", "countries", "languages", "directors", "casts"):
        values = list(getattr(stored, field_name) or [])
        if values:
            hydrated[field_name] = values
    if stored.tags:
        hydrated["tags"] = list(dict.fromkeys([*(hydrated.get("tags") or []), *stored.tags]))
    for field_name in ("year", "douban_rating", "my_rating"):
        value = getattr(stored, field_name)
        if value is not None and hydrated.get(field_name) is None:
            hydrated[field_name] = value
    if stored.vote_count is not None:
        hydrated["vote_count"] = max(int(hydrated.get("vote_count") or 0), int(stored.vote_count or 0)) or None
    current_raw = hydrated.get("raw") if isinstance(hydrated.get("raw"), dict) else {}
    stored_raw = stored.raw if isinstance(stored.raw, dict) else {}
    merged_raw = _merge_candidate_raw(stored_raw, current_raw)
    hydrated["raw"] = merged_raw
    if isinstance(merged_raw.get("ratings"), dict):
        current_ratings = hydrated.get("source_ratings") if isinstance(hydrated.get("source_ratings"), dict) else {}
        hydrated["source_ratings"] = {**current_ratings, **merged_raw["ratings"]}
    for field_name in ("provider_ids", "stills", "episodes"):
        value = merged_raw.get(field_name)
        if value not in (None, "", [], {}):
            hydrated[field_name] = copy.deepcopy(value)
    return hydrated


def _dedupe_candidate_items(items: list[MediaItem]) -> list[MediaItem]:
    merged: dict[str, MediaItem] = {}
    token_to_key: dict[str, str] = {}
    for item in items:
        tokens = recommendation_identity_tokens(item)
        canonical = next((token_to_key[token] for token in tokens if token in token_to_key), "")
        if not canonical:
            canonical = recommendation_item_key(item)
            merged[canonical] = item
        else:
            merged[canonical] = _merge_candidate_items(merged[canonical], item)
        for token in recommendation_identity_tokens(merged[canonical]):
            token_to_key[token] = canonical
        for token in tokens:
            token_to_key[token] = canonical
    return list(merged.values())


def _media_status(item: dict[str, object], *, had_cover: bool = False) -> dict[str, str]:
    cover = str(item.get("cover") or "").strip()
    if cover.startswith("/media/"):
        poster = "ready"
    elif had_cover:
        poster = "designed-fallback"
    else:
        poster = "missing"
    return {"poster": poster}


def _conflicts(item: dict[str, object]) -> list[str]:
    breakdown = item.get("score_breakdown")
    if isinstance(breakdown, dict):
        raw = breakdown.get("conflicts")
        if isinstance(raw, list):
            return [str(value) for value in raw]
    warnings = item.get("warnings")
    if isinstance(warnings, list):
        return [str(value) for value in warnings]
    return []


def _normalize_batch_item(item: dict[str, object], media_store: MediaStore) -> dict[str, object]:
    scrubbed = scrub_sensitive(dict(item))
    payload = scrubbed if isinstance(scrubbed, dict) else {}
    title = str(payload.get("title") or "").strip()
    douban_id = str(payload.get("douban_id") or "").strip()
    title_metadata = TITLE_PEOPLE_METADATA.get(title)
    metadata = curated_metadata_for_title(title, douban_id)
    if isinstance(title_metadata, dict):
        metadata = {**metadata, **title_metadata}
    if not payload.get("genres") and isinstance(metadata.get("genres"), list):
        payload["genres"] = [str(value).strip() for value in metadata["genres"] if str(value).strip()]
    if not payload.get("genres"):
        media_type = str(payload.get("media_type") or payload.get("format") or "作品").strip()
        payload["genres"] = [media_type] if media_type else ["作品"]
    had_cover = bool(str(payload.get("cover") or "").strip())
    payload["url"] = _safe_url(payload.get("url"))
    payload["item_key"] = recommendation_item_key(payload)
    payload["cover"] = _safe_media_url(payload.get("cover"), media_store) or _bound_media_url(
        payload["item_key"], "poster", media_store
    )
    payload["source"] = _safe_source(payload.get("source"))
    payload["candidate_origin"] = candidate_origin(payload)
    payload["people_photos"] = _safe_people_photos(payload.get("people_photos"), media_store)
    payload["conflicts"] = _conflicts(payload)
    payload["media_status"] = _media_status(payload, had_cover=had_cover)
    return payload


def _bound_media_url(item_key: str, kind: str, media_store: MediaStore) -> str:
    entity_ids = [str(item_key or "").strip()]
    if not entity_ids[0]:
        return ""
    with media_store.database.connection() as connection:
        identity_rows = connection.execute(
            "SELECT id FROM media_identities WHERE json_extract(metadata_json, '$.item_key')=?",
            (entity_ids[0],),
        ).fetchall()
        for row in identity_rows:
            identity_id = str(row["id"] or "").strip()
            if identity_id and identity_id not in entity_ids:
                entity_ids.append(identity_id)
        placeholders = ",".join("?" for _ in entity_ids)
        rows = connection.execute(
            f"""
            SELECT o.entity_id, o.asset_id, o.decision, a.extension, a.kind, a.status
            FROM user_asset_overrides o
            JOIN asset_files a ON a.asset_id=o.asset_id
            WHERE o.entity_kind='media' AND o.kind=? AND o.entity_id IN ({placeholders})
            ORDER BY CASE WHEN o.entity_id=? THEN 0 ELSE 1 END, o.updated_at DESC
            """,
            (kind, *entity_ids, entity_ids[0]),
        ).fetchall()
    for row in rows:
        if str(row["decision"] or "").lower() not in {"selected", "approved", "accepted", "chosen"}:
            continue
        if str(row["status"] or "") != "ready" or str(row["kind"] or "") not in {kind, "shared"}:
            continue
        stored = media_store.lookup(f"{row['asset_id']}{row['extension']}")
        if stored is not None and stored.status == "ready" and stored.kind in {kind, "shared"}:
            return stored.local_url
    return ""


def _safe_url(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    try:
        parsed = urlsplit(text)
    except ValueError:
        return ""
    if parsed.scheme not in {"http", "https"}:
        return ""
    hostname = parsed.hostname or ""
    if not hostname:
        return ""
    netloc = f"[{hostname}]" if ":" in hostname and not hostname.startswith("[") else hostname
    try:
        port = parsed.port
    except ValueError:
        return ""
    if port:
        netloc = f"{netloc}:{port}"
    return urlunsplit((parsed.scheme, netloc, parsed.path or "", "", ""))


def _safe_media_url(value: object, media_store: MediaStore) -> str:
    text = str(value or "").strip()
    if not text.startswith("/media/") or "?" in text or "#" in text:
        return ""
    stored = media_store.lookup(text.removeprefix("/media/"))
    return stored.local_url if stored is not None and stored.status == "ready" else ""


def _safe_source(value: object) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if text.startswith(("http://", "https://")):
        return "external_url"
    prefix, separator, suffix = text.partition(":")
    if separator and (
        suffix.startswith("//")
        or "://" in suffix
        or "@" in suffix
        or "?" in suffix
        or "#" in suffix
    ):
        return prefix or "external_url"
    return text


def _safe_people_photos(value: object, media_store: MediaStore) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for name, url in value.items():
        clean_name = str(name or "").strip()
        clean_url = _safe_media_url(url, media_store)
        if clean_name and clean_url:
            out[clean_name] = clean_url
    return out


class RecommendationApi:
    def __init__(
        self,
        database: AppDatabase,
        session_service: RecommendationSessionService | None = None,
        feedback_service: FeedbackService | None = None,
        sample_ratings_path: Path | None = None,
        sample_candidates_path: Path | None = None,
        language_adapter_factory: Callable[..., object] | None = None,
        media_store: MediaStore | None = None,
        media_root: Path | str | None = None,
        detail_enricher: Callable[..., list[MediaItem]] | None = None,
        detail_fetcher: Callable[[str], object] | None = None,
        global_discoverer: Callable[..., GlobalDiscoveryReport] | None = None,
        enrich_limit: int = 12,
    ):
        self.database = database
        self.database.initialize()
        self.session_service = session_service or RecommendationSessionService(database)
        self.feedback_service = feedback_service or FeedbackService(database)
        self.sample_ratings_path = sample_ratings_path or DEFAULT_SAMPLE_RATINGS
        self.sample_candidates_path = sample_candidates_path or DEFAULT_SAMPLE_CANDIDATES
        self.language_adapter_factory = language_adapter_factory or OpenAICompatibleLanguageAdapter
        self.media_store = media_store or MediaStore(media_root or resolve_media_dir(), database)
        self.detail_enricher = detail_enricher
        self.detail_fetcher = detail_fetcher
        self.global_discoverer = global_discoverer or discover_global_candidates
        self.enrich_limit = max(0, min(36, int(enrich_limit)))

    def create_session(self, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        self._validate_create_session_payload(payload)
        profile_key = _base_text(payload.get("profile_key")) or "default"
        intent = self._intent(payload)
        rated_items = self._rated_items(payload)
        profile = self._profile(profile_key, rated_items, payload)
        candidates, discovery = self._candidate_pool(payload, intent, profile, rated_items)
        ranked_by_channel = self._ranked_channels(
            payload,
            intent,
            rated_items,
            candidates,
            profile,
            discovery=discovery,
        )
        if self._enrich_visible_candidates(candidates, ranked_by_channel, self._batch_sizes(payload)):
            ranked_by_channel = self._ranked_channels(
                payload,
                intent,
                rated_items,
                candidates,
                profile,
                discovery=discovery,
            )
        session = self.session_service.create_session(
            profile_key,
            intent,
            ranked_by_channel,
            self._batch_sizes(payload),
        )
        for channel in CHANNEL_ORDER:
            self.session_service.next_batch(session.id, channel)
        return self.get_session(session.id)

    def _enrich_visible_candidates(
        self,
        candidates: list[MediaItem],
        ranked_by_channel: dict[str, dict[str, object]],
        batch_sizes: dict[str, int],
    ) -> bool:
        if not self.detail_enricher or self.enrich_limit <= 0:
            return False
        by_key = {recommendation_item_key(item): item for item in candidates}
        selected: list[MediaItem] = []
        seen: set[str] = set()
        visible_rows = {
            channel: list((ranked_by_channel.get(channel) or {}).get("items") or [])[
                : max(1, int(batch_sizes.get(channel) or 1))
            ]
            for channel in CHANNEL_ORDER
        }
        depth = 0
        while len(selected) < self.enrich_limit and any(depth < len(rows) for rows in visible_rows.values()):
            for channel in CHANNEL_ORDER:
                rows = visible_rows[channel]
                if depth >= len(rows):
                    continue
                row = rows[depth]
                key = recommendation_item_key(row)
                item = by_key.get(key)
                if item is None or key in seen:
                    continue
                seen.add(key)
                selected.append(item)
                if len(selected) >= self.enrich_limit:
                    break
            depth += 1
        if not selected:
            return False
        before = [copy.deepcopy(media_item_to_dict(item)) for item in selected]
        try:
            self.detail_enricher(
                selected,
                fetcher=self.detail_fetcher,
                limit=len(selected),
                sleep_seconds=0.0,
                force_people_photos=True,
            )
        except Exception:
            return False
        return any(media_item_to_dict(item) != previous for previous, item in zip(before, selected))

    def get_session(self, session_id: str) -> dict[str, object]:
        session = self._restore_session(session_id)
        return self._serialize_session(session)

    def latest_session(self) -> dict[str, object]:
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id
                FROM recommendation_sessions
                WHERE status='active'
                ORDER BY updated_at DESC, id DESC
                LIMIT 1
                """
            ).fetchone()
        if not row:
            raise RecommendationApiNotFound("recommendation session not found")
        return self.get_session(str(row["id"]))

    def next_batch(self, session_id: str, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        self._validate_batch_payload(payload)
        session = self._restore_session(session_id)
        channel = self._channel(payload)
        batch = self._service_call(self.session_service.next_batch, session.id, channel, _base_text(payload.get("reason")))
        return self._serialize_batch_response(session, channel, batch)

    def previous_batch(self, session_id: str, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        self._validate_batch_payload(payload)
        session = self._restore_session(session_id)
        channel = self._channel(payload)
        batch = self._service_call(self.session_service.previous_batch, session.id, channel)
        return self._serialize_batch_response(session, channel, batch)

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        self._validate_feedback_payload(payload)
        event_type = _base_text(payload.get("event_type"))
        if event_type not in EVENT_SCOPE_RULES:
            raise RecommendationApiError("unsupported event_type")
        allowed_scopes = EVENT_SCOPE_RULES[event_type]
        scope = _base_text(payload.get("scope")) or next(iter(allowed_scopes))
        if scope not in {"session", "permanent"}:
            raise RecommendationApiError("unsupported scope")
        if scope not in allowed_scopes:
            raise RecommendationApiError(f"scope '{scope}' is not allowed for event_type '{event_type}'")

        session_id = _base_text(payload.get("session_id"))
        profile_key = _base_text(payload.get("profile_key")) or "default"
        session = None
        if scope == "session":
            if not session_id:
                raise RecommendationApiError("session_id is required for session scope")
            session = self._restore_session(session_id)
            profile_key = session.profile_key
        elif session_id:
            session = self._restore_session(session_id)
            profile_key = session.profile_key

        item_key = _base_text(payload.get("item_key"))
        if not item_key and isinstance(payload.get("item"), dict):
            item_key = recommendation_item_key(payload["item"])
        if not item_key:
            raise RecommendationApiError("item_key is required")

        if scope == "session" and event_type not in SESSION_ONLY_EVENT_TYPES:
            raise RecommendationApiError("session-only feedback must remain session-only")

        feedback_payload = payload.get("payload")
        if feedback_payload is None:
            feedback_payload = {}
        elif not isinstance(feedback_payload, dict):
            raise RecommendationApiError("payload must be object")

        if session is not None and event_type in SESSION_STATE_EVENT_TYPES:
            applied = self._service_call(
                self.session_service.apply_feedback,
                session.id,
                event_type,
                item_key,
                dict(feedback_payload),
            )
            event_id = str(applied["event_id"])
        else:
            event_id = self.feedback_service.record_feedback(
                FeedbackEvent(
                    event_type=event_type,
                    item_key=item_key,
                    profile_key=profile_key,
                    session_id=session_id,
                    payload=dict(feedback_payload),
                    created_at=time.time(),
                )
            )
        return {
            "schema_version": SCHEMA_VERSION,
            "id": event_id,
            "event_type": event_type,
            "scope": scope,
            "profile_key": profile_key,
            "session_id": session_id,
            "item_key": item_key,
            "restore": {
                "undo_supported": True,
                "undo_path": f"/api/v2/feedback/{event_id}/undo",
            },
        }

    def undo_feedback(self, event_id: str, payload: dict[str, Any] | None = None) -> dict[str, object]:
        self._require_schema(payload or {})
        try:
            undo_id = self.session_service.undo_feedback(event_id)
            if undo_id is None:
                undo_id = self.feedback_service.undo_feedback(event_id)
        except ValueError as exc:
            raise RecommendationApiNotFound("feedback event not found") from exc
        return {
            "schema_version": SCHEMA_VERSION,
            "id": undo_id,
            "undone_event_id": str(event_id),
            "restore": {
                "target_event_id": str(event_id),
                "undo_supported": False,
            },
        }

    def _require_schema(self, payload: dict[str, Any]) -> None:
        if "schema_version" not in payload:
            raise RecommendationApiError("schema_version must be 2")
        version = payload.get("schema_version")
        if type(version) is not int or version != SCHEMA_VERSION:
            raise RecommendationApiError("schema_version must be 2")

    def _validate_create_session_payload(self, payload: dict[str, Any]) -> None:
        _validate_intent_schema(payload)
        _validate_item_array(payload, "rated_items")
        _validate_item_array(payload, "candidate_items")
        _validate_batch_size_by_channel(payload)
        for field in CREATE_SESSION_STRING_FIELDS:
            _validate_optional_string_field(payload, field)
        for field in CREATE_SESSION_STRING_LIST_FIELDS:
            if field in payload:
                _validate_string_or_string_array(payload[field], field)
        for field in CREATE_SESSION_INTEGER_FIELDS:
            _validate_optional_integer_field(payload, field)
        for field in CREATE_SESSION_BOOL_FIELDS:
            _validate_optional_bool_field(payload, field)
        if "global_discovery" in payload and not isinstance(payload["global_discovery"], dict):
            _raise_schema_error("global_discovery", "must be object")
        self._validate_language_config(payload)

    def _validate_language_config(self, payload: dict[str, Any]) -> None:
        if "language" not in payload:
            return
        language = payload["language"]
        if not isinstance(language, dict):
            _raise_schema_error("language", "must be object")
        for field in LANGUAGE_STRING_FIELDS:
            if field in language and not isinstance(language[field], str):
                _raise_schema_error(f"language.{field}", "must be string")
        endpoint = _base_text(language.get("endpoint"))
        model = _base_text(language.get("model"))
        if endpoint and not model:
            _raise_schema_error("language.model", "is required with language.endpoint")
        if model and not endpoint:
            _raise_schema_error("language.endpoint", "is required with language.model")

    def _validate_batch_payload(self, payload: dict[str, Any]) -> None:
        _validate_optional_string_field(payload, "channel")
        _validate_optional_string_field(payload, "reason")

    def _validate_feedback_payload(self, payload: dict[str, Any]) -> None:
        for field in FEEDBACK_STRING_FIELDS:
            _validate_optional_string_field(payload, field)
        if "item" in payload:
            item = payload["item"]
            if not isinstance(item, dict):
                _raise_schema_error("item", "must be object")
            _validate_item_schema(item, "item")
        if "payload" in payload and not isinstance(payload["payload"], dict):
            _raise_schema_error("payload", "must be object")

    def _intent(self, payload: dict[str, Any]) -> RecommendationIntent:
        base = RecommendationIntent.from_dict(payload.get("intent")) if isinstance(payload.get("intent"), dict) else None
        text = _base_text(payload.get("intent_text") or payload.get("text"))
        if not text:
            return _scrub_intent(base or RecommendationIntent())
        text = _base_text(scrub_sensitive(text))
        language = payload.get("language") if isinstance(payload.get("language"), dict) else {}
        endpoint = _base_text(language.get("endpoint"))
        model = _base_text(language.get("model"))
        if not endpoint and not model:
            parsed = LocalRuleLanguageAdapter().parse(text, {})
            merged = parse_recommendation_intent(text, base=base) if base is not None else parsed
            return _scrub_intent(merged)
        primary = self.language_adapter_factory(
            endpoint=endpoint,
            model=model,
            api_key=_base_text(language.get("api_key")),
        )
        parsed = LanguageService(primary=primary, fallback=LocalRuleLanguageAdapter()).parse(text, {})
        return _scrub_intent(_merge_intents(base, parsed))

    def _rated_items(self, payload: dict[str, Any]) -> list[MediaItem]:
        rated_items = _item_dicts(payload.get("rated_items"))
        if not rated_items:
            ratings_csv = _base_text(payload.get("ratings_csv"))
            if ratings_csv:
                rated_items = load_media_csv_from_text(ratings_csv, kind="ratings")
            elif bool(payload.get("use_sample_ratings")):
                rated_items = load_media_csv(self.sample_ratings_path, kind="ratings")

        library_items: list[MediaItem] = []
        for record in self.session_service.library_items(states=["watched", "wish", "wanted"]):
            if not isinstance(record.get("payload"), dict):
                continue
            item = media_item_from_dict(record["payload"])
            state = str(record.get("state") or "").strip().lower()
            required_tag = "看过" if state == "watched" else "想看"
            if required_tag not in item.tags:
                item.tags.append(required_tag)
            library_items.append(item)
        deduped: dict[str, MediaItem] = {}
        for item in rated_items:
            key = recommendation_item_key(item)
            if key not in deduped:
                deduped[key] = item
        for item in library_items:
            key = recommendation_item_key(item)
            existing = deduped.get(key)
            if existing is None:
                deduped[key] = item
                continue
            for tag in item.tags:
                if tag not in existing.tags:
                    existing.tags.append(tag)
        return list(deduped.values())

    def _profile(self, profile_key: str, rated_items: list[MediaItem], payload: dict[str, Any]):
        feedback_signals = self.feedback_service.feedback_signals(profile_key, time.time())
        return build_taste_profile(
            rated_items,
            like_terms=payload.get("like_terms") or "",
            dislike_terms=payload.get("dislike_terms") or "",
            feedback_signals=feedback_signals,
        )

    def _candidates(
        self,
        payload: dict[str, Any],
        profile,
        rated_items: list[MediaItem],
    ) -> list[MediaItem]:
        """Compatibility wrapper for callers that inspect the resolved local pool."""
        candidates, _ = self._candidate_pool(payload, self._intent(payload), profile, rated_items)
        return candidates

    def _candidate_pool(
        self,
        payload: dict[str, Any],
        intent: RecommendationIntent,
        profile,
        rated_items: list[MediaItem],
    ) -> tuple[list[MediaItem], dict[str, object]]:
        candidates = _item_dicts(payload.get("candidate_items"))
        candidates_csv = _base_text(payload.get("candidates_csv"))
        has_custom_candidates = bool(candidates or candidates_csv)
        discovery: dict[str, object] = {
            "status": "disabled",
            "local_index_size": 0,
            "live_size": 0,
            "source_counts": {},
            "source_status": {},
            "query_keywords": [],
            "config": {},
            "generated_at": None,
        }
        if candidates_csv:
            candidates.extend(load_media_csv_from_text(candidates_csv, kind="candidates"))
        elif bool(payload.get("use_sample_candidates")):
            candidates.extend(load_media_csv(self.sample_candidates_path, kind="candidates"))

        if bool(payload.get("use_local_index")):
            local_items: list[MediaItem] = []
            for record in self.session_service.library_items(states=["candidate"]):
                stored = record.get("payload")
                if not isinstance(stored, dict):
                    continue
                item = media_item_from_dict(stored)
                if item.title:
                    local_items.append(item)
            candidates.extend(local_items)
            discovery["local_index_size"] = len(local_items)
            if local_items:
                discovery["status"] = "local-index"

        urls = _strings(payload.get("candidate_urls"))
        if urls:
            candidates.extend(fetch_url_candidates(urls))

        if bool(payload.get("fetch_douban")):
            wishlist = [item for item in rated_items if "想看" in set(item.tags or [])]
            plan = build_candidate_plan(
                profile,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=bool(payload.get("include_anime", True)),
                wishlist=wishlist,
            )
            report = fetch_candidates_from_plan(plan, sleep_seconds=0.02, max_consecutive_failures=8)
            candidates.extend(report.items)
            if not report.items:
                candidates.extend(fetch_douban_candidates(
                    profile,
                    include_movies=bool(payload.get("include_movies", True)),
                    include_series=bool(payload.get("include_series", True)),
                    per_query=_to_int(payload.get("per_query"), 20, 5, 50),
                ))

        if bool(payload.get("fetch_global")):
            config_payload = payload.get("global_discovery")
            config = GlobalDiscoveryConfig.from_payload(config_payload if isinstance(config_payload, dict) else {})
            try:
                report = self.global_discoverer(
                    intent,
                    profile,
                    include_movies=bool(payload.get("include_movies", True)),
                    include_series=bool(payload.get("include_series", True)),
                    include_anime=bool(payload.get("include_anime", True)),
                    config=config,
                )
            except Exception as error:
                discovery.update({
                    "status": "failed",
                    "source_counts": {},
                    "source_status": {
                        "global": {
                            "state": "failed",
                            "count": 0,
                            "error": type(error).__name__,
                        }
                    },
                    "config": config.public_summary(),
                    "generated_at": time.time(),
                })
            else:
                live_items = list(report.items or [])
                candidates.extend(live_items)
                public_report = report.to_dict()
                discovery.update(public_report)
                discovery["live_size"] = len(live_items)
            discovery["local_index_size"] = int(discovery.get("local_index_size") or 0)

        if not has_custom_candidates:
            candidates = backfill_missing_media_types(
                candidates,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=bool(payload.get("include_anime", True)),
                target_total=self._candidate_target(payload),
            )
        candidates = [_sanitize_unverified_expansion(item) for item in candidates]
        apply_curated_people_photos(apply_curated_posters(candidates))
        safe_discovery = scrub_sensitive(discovery)
        return _dedupe_candidate_items(candidates), safe_discovery if isinstance(safe_discovery, dict) else {}

    def _ranked_channels(
        self,
        payload: dict[str, Any],
        intent: RecommendationIntent,
        rated_items: list[MediaItem],
        candidates: list[MediaItem],
        profile,
        *,
        discovery: dict[str, object] | None = None,
    ) -> dict[str, dict[str, object]]:
        feedback_signals = self.feedback_service.feedback_signals("default", time.time())
        profile_key = _base_text(payload.get("profile_key")) or "default"
        if profile_key != "default":
            feedback_signals = self.feedback_service.feedback_signals(profile_key, time.time())
        hard_excluded_tokens = set(feedback_signals.permanent_excluded_item_keys)
        ranked_by_channel: dict[str, dict[str, object]] = {}
        for channel in CHANNEL_ORDER:
            enabled = bool(payload.get(CHANNEL_FLAGS[channel], True))
            channel_candidates = [item for item in candidates if item.media_type == channel]
            pool_size = len(channel_candidates) if enabled else 0
            ranked_items: list[dict[str, object]] = []
            if enabled and (not intent.media_types or channel in intent.media_types):
                channel_intent = replace(intent, media_types=(channel,))
                ranked = rank_candidates(
                    rated_items,
                    channel_candidates,
                    profile,
                    channel_intent,
                    hard_excluded_tokens=hard_excluded_tokens,
                )
                ranked_items = [row.to_dict() for row in ranked]
            ranked_by_channel[channel] = {
                "items": ranked_items,
                "pool_size": pool_size,
                "matched_size": len(ranked_items),
            }
        recommendation_origin_counts = {
            channel: {
                "online": sum(
                    1
                    for item in state["items"]
                    if candidate_origin(item)["kind"] == "online"
                ),
                "catalog": sum(
                    1
                    for item in state["items"]
                    if candidate_origin(item)["kind"] != "online"
                ),
                "total": len(state["items"]),
            }
            for channel, state in ranked_by_channel.items()
        }
        public_discovery = dict(discovery or {})
        public_discovery["recommendation_origin_counts"] = recommendation_origin_counts
        for state in ranked_by_channel.values():
            state["discovery"] = dict(public_discovery)
        candidate_counts = {
            "target_size": self._candidate_target(payload),
            "returned_size": sum(int(state.get("pool_size") or 0) for state in ranked_by_channel.values()),
        }
        for state in ranked_by_channel.values():
            state["candidate_counts"] = candidate_counts
        return ranked_by_channel

    def _candidate_target(self, payload: dict[str, Any]) -> int:
        return max(30, _to_int(payload.get("limit"), 120, 1, 300))

    def _batch_sizes(self, payload: dict[str, Any]) -> dict[str, int]:
        default_size = _to_int(payload.get("batch_size") or payload.get("visible_size"), 9, 1, 24)
        raw = payload.get("batch_size_by_channel") or {}
        if not isinstance(raw, dict):
            raw = {}
        return {
            channel: _to_int(raw.get(channel), default_size, 1, 24)
            for channel in CHANNEL_ORDER
        }

    def _restore_session(self, session_id: str) -> RecommendationSession:
        try:
            return self.session_service.restore_session(str(session_id))
        except ValueError as exc:
            raise RecommendationApiNotFound("recommendation session not found") from exc

    def _channel(self, payload: dict[str, Any]) -> str:
        channel = _base_text(payload.get("channel"))
        if channel not in CHANNEL_ORDER:
            raise RecommendationApiError("unsupported channel")
        return channel

    def _service_call(self, fn, *args):
        try:
            return fn(*args)
        except ValueError as exc:
            message = str(exc)
            if "not found" in message:
                raise RecommendationApiNotFound(message) from exc
            raise RecommendationApiError(message) from exc

    def _serialize_session(self, session: RecommendationSession) -> dict[str, object]:
        restored = self.session_service.restore_session(session.id)
        channels: dict[str, dict[str, object]] = {}
        for channel in CHANNEL_ORDER:
            state = dict(restored.channels.get(channel) or {})
            batch = self._service_call(self.session_service.current_batch, session.id, channel)
            channels[channel] = self._serialize_channel(channel, state, batch)
        candidate_counts = next(
            (
                dict(state.get("candidate_counts"))
                for state in restored.channels.values()
                if isinstance(state, dict) and isinstance(state.get("candidate_counts"), dict)
            ),
            {},
        )
        candidate_counts.setdefault("target_size", None)
        candidate_counts["returned_size"] = sum(channel["pool_size"] for channel in channels.values())
        discovery = next(
            (
                dict(state.get("discovery"))
                for state in restored.channels.values()
                if isinstance(state, dict) and isinstance(state.get("discovery"), dict)
            ),
            {},
        )
        return {
            "schema_version": SCHEMA_VERSION,
            "id": restored.id,
            "profile_key": restored.profile_key,
            "status": restored.status,
            "intent": restored.intent.to_dict(),
            "chips": [asdict(chip) for chip in intent_to_chips(restored.intent)],
            "candidate_counts": candidate_counts,
            "discovery": discovery,
            "personalization": self._personalization(),
            "channels": channels,
            "restore": self._restore_metadata(restored.channels),
            "created_at": restored.created_at,
            "updated_at": restored.updated_at,
        }

    def _personalization(self) -> dict[str, object]:
        rows = self.session_service.library_items(states=["watched", "wish", "wanted"])
        watched_count = 0
        wish_count = 0
        rated_count = 0
        has_douban_source = False
        for row in rows:
            state = str(row.get("state") or "").strip().lower()
            if state == "watched":
                watched_count += 1
            elif state in {"wish", "wanted"}:
                wish_count += 1
            payload = row.get("payload") if isinstance(row.get("payload"), dict) else {}
            if payload.get("my_rating") is not None:
                rated_count += 1
            source = str(row.get("source") or payload.get("source") or "")
            if "douban" in source.casefold():
                has_douban_source = True
        user_id = str(self.database.get_meta("active_douban_user_id") or "").strip()
        source = "douban-sync" if user_id and has_douban_source else ("local-library" if rows else "unpersonalized")
        return {
            "source": source,
            "user_id": user_id if source == "douban-sync" else "",
            "watched_count": watched_count,
            "wish_count": wish_count,
            "rated_count": rated_count,
        }

    def _serialize_channel(
        self,
        channel: str,
        state: dict[str, object],
        batch: RecommendationBatch,
    ) -> dict[str, object]:
        return {
            "key": channel,
            "label": channel,
            "pool_size": int(state.get("pool_size") or batch.pool_size),
            "matched_size": int(state.get("matched_size") or batch.matched_size),
            "visible_size": batch.visible_size,
            "batch": self._serialize_batch(batch),
            "active_batch": int(state.get("active_batch") or batch.index),
            "last_batch": int(state.get("last_batch") or batch.index),
        }

    def _serialize_batch_response(
        self,
        session: RecommendationSession,
        channel: str,
        batch: RecommendationBatch,
    ) -> dict[str, object]:
        restored = self.session_service.restore_session(session.id)
        return {
            "schema_version": SCHEMA_VERSION,
            "session_id": session.id,
            "channel": channel,
            "batch": self._serialize_batch(batch),
            "restore": self._restore_metadata(restored.channels),
        }

    def _catalog_payloads_for_batch(self, items: list[dict[str, object]]) -> dict[str, dict[str, object]]:
        keys = [
            _base_text(item.get("item_key")) or recommendation_item_key(item)
            for item in items
            if isinstance(item, dict)
        ]
        keys = list(dict.fromkeys(key for key in keys if key))
        if not keys:
            return {}
        placeholders = ",".join("?" for _ in keys)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"SELECT item_key, payload_json FROM library_items WHERE item_key IN ({placeholders})",
                tuple(keys),
            ).fetchall()
        payloads: dict[str, dict[str, object]] = {}
        for row in rows:
            try:
                payload = json.loads(str(row["payload_json"] or "{}"))
            except (TypeError, ValueError, json.JSONDecodeError):
                continue
            if isinstance(payload, dict):
                payloads[str(row["item_key"])] = payload
        return payloads

    def _serialize_batch(self, batch: RecommendationBatch) -> dict[str, object]:
        raw_items = [dict(item) for item in batch.items]
        catalog_payloads = self._catalog_payloads_for_batch(raw_items)
        hydrated_items = [
            _hydrate_batch_item_from_catalog(
                item,
                catalog_payloads.get(_base_text(item.get("item_key")) or recommendation_item_key(item)),
            )
            for item in raw_items
        ]
        return {
            "id": batch.id,
            "session_id": batch.session_id,
            "channel": batch.channel,
            "index": batch.index,
            "items": [_normalize_batch_item(item, self.media_store) for item in hydrated_items],
            "item_keys": list(batch.item_keys),
            "pool_size": batch.pool_size,
            "matched_size": batch.matched_size,
            "visible_size": batch.visible_size,
            "reason": batch.reason,
            "reason_adjustment": dict(batch.reason_adjustment),
            "exhausted": batch.exhausted,
            "created_at": batch.created_at,
        }

    def _restore_metadata(self, channels: dict[str, dict[str, object]]) -> dict[str, object]:
        return {
            "channels": {
                channel: {
                    "active_batch": int((channels.get(channel) or {}).get("active_batch") or 0),
                    "last_batch": int((channels.get(channel) or {}).get("last_batch") or 0),
                    "cursor": int((channels.get(channel) or {}).get("cursor") or 0),
                    "can_restore_previous": int((channels.get(channel) or {}).get("active_batch") or 0) > 1,
                }
                for channel in CHANNEL_ORDER
            }
        }


def build_default_recommendation_api() -> RecommendationApi:
    database = AppDatabase(resolve_database_path())
    database.initialize()
    return RecommendationApi(
        database,
        detail_enricher=enrich_media_items_parallel,
        detail_fetcher=lambda url: fetch_douban_detail_html(url, timeout=5),
        enrich_limit=6,
    )
