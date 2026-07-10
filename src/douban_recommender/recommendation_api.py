from __future__ import annotations

import time
from dataclasses import replace
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from .candidate_planner import build_candidate_plan
from .curated_catalog import apply_curated_people_photos, apply_curated_posters, backfill_missing_media_types
from .database import AppDatabase
from .douban_sources import fetch_candidates_from_plan, fetch_douban_candidates, fetch_url_candidates
from .feedback_service import FeedbackEvent, FeedbackService
from .intent_parser import RecommendationIntent, parse_recommendation_intent
from .io import load_media_csv, load_media_csv_from_text
from .models import MediaItem, recommendation_item_key
from .profiler import build_taste_profile
from .ranking import rank_candidates
from .recommendation_service import RecommendationBatch, RecommendationSession, RecommendationSessionService
from .runtime_paths import resolve_database_path
from .serialization import media_item_from_dict


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


class RecommendationApiError(ValueError):
    status_code = 400


class RecommendationApiNotFound(RecommendationApiError):
    status_code = 404


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


def _media_status(item: dict[str, object]) -> dict[str, str]:
    cover = str(item.get("cover") or "").strip()
    if cover.startswith("/media/"):
        poster = "ready"
    elif cover.startswith("data:image/svg+xml"):
        poster = "designed"
    elif cover:
        poster = "external"
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


def _normalize_batch_item(item: dict[str, object]) -> dict[str, object]:
    payload = dict(item)
    payload["url"] = _safe_url(payload.get("url"))
    payload["cover"] = _safe_url(payload.get("cover"), allow_data=True)
    payload["source"] = _safe_source(payload.get("source"))
    payload["people_photos"] = _safe_people_photos(payload.get("people_photos"))
    payload["item_key"] = recommendation_item_key(payload)
    payload["conflicts"] = _conflicts(payload)
    payload["media_status"] = _media_status(payload)
    return payload


def _safe_url(value: object, *, allow_data: bool = False) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    if allow_data and text.startswith("data:image/"):
        return text
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


def _safe_people_photos(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, str] = {}
    for name, url in value.items():
        clean_name = str(name or "").strip()
        clean_url = _safe_url(url)
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
    ):
        self.database = database
        self.database.initialize()
        self.session_service = session_service or RecommendationSessionService(database)
        self.feedback_service = feedback_service or FeedbackService(database)
        self.sample_ratings_path = sample_ratings_path or DEFAULT_SAMPLE_RATINGS
        self.sample_candidates_path = sample_candidates_path or DEFAULT_SAMPLE_CANDIDATES

    def create_session(self, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        profile_key = _base_text(payload.get("profile_key")) or "default"
        intent = self._intent(payload)
        rated_items = self._rated_items(payload)
        profile = self._profile(profile_key, rated_items, payload)
        candidates = self._candidates(payload, profile, rated_items)
        ranked_by_channel = self._ranked_channels(payload, intent, rated_items, candidates, profile)
        session = self.session_service.create_session(
            profile_key,
            intent,
            ranked_by_channel,
            self._batch_sizes(payload),
        )
        for channel in CHANNEL_ORDER:
            self.session_service.next_batch(session.id, channel)
        return self.get_session(session.id)

    def get_session(self, session_id: str) -> dict[str, object]:
        session = self._restore_session(session_id)
        return self._serialize_session(session)

    def next_batch(self, session_id: str, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        session = self._restore_session(session_id)
        channel = self._channel(payload)
        batch = self._service_call(self.session_service.next_batch, session.id, channel, _base_text(payload.get("reason")))
        return self._serialize_batch_response(session, channel, batch)

    def previous_batch(self, session_id: str, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
        session = self._restore_session(session_id)
        channel = self._channel(payload)
        batch = self._service_call(self.session_service.previous_batch, session.id, channel)
        return self._serialize_batch_response(session, channel, batch)

    def record_feedback(self, payload: dict[str, Any]) -> dict[str, object]:
        self._require_schema(payload)
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
        if scope == "session":
            if not session_id:
                raise RecommendationApiError("session_id is required for session scope")
            session = self._restore_session(session_id)
            profile_key = session.profile_key

        item_key = _base_text(payload.get("item_key"))
        if not item_key and isinstance(payload.get("item"), dict):
            item_key = recommendation_item_key(payload["item"])
        if not item_key:
            raise RecommendationApiError("item_key is required")

        if scope == "session" and event_type not in SESSION_ONLY_EVENT_TYPES:
            raise RecommendationApiError("session-only feedback must remain session-only")

        event_id = self.feedback_service.record_feedback(
            FeedbackEvent(
                event_type=event_type,
                item_key=item_key,
                profile_key=profile_key,
                session_id=session_id,
                payload=dict(payload.get("payload") or {}),
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

    def _intent(self, payload: dict[str, Any]) -> RecommendationIntent:
        base = RecommendationIntent.from_dict(payload.get("intent")) if isinstance(payload.get("intent"), dict) else None
        text = _base_text(payload.get("intent_text") or payload.get("text"))
        return parse_recommendation_intent(text, base=base) if text else (base or RecommendationIntent())

    def _rated_items(self, payload: dict[str, Any]) -> list[MediaItem]:
        rated_items = _item_dicts(payload.get("rated_items"))
        if rated_items:
            return rated_items
        ratings_csv = _base_text(payload.get("ratings_csv"))
        if ratings_csv:
            return load_media_csv_from_text(ratings_csv, kind="ratings")
        if bool(payload.get("use_sample_ratings")):
            return load_media_csv(self.sample_ratings_path, kind="ratings")
        return []

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
        candidates = _item_dicts(payload.get("candidate_items"))
        candidates_csv = _base_text(payload.get("candidates_csv"))
        has_custom_candidates = bool(candidates or candidates_csv)
        if candidates_csv:
            candidates.extend(load_media_csv_from_text(candidates_csv, kind="candidates"))
        elif bool(payload.get("use_sample_candidates")):
            candidates.extend(load_media_csv(self.sample_candidates_path, kind="candidates"))

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

        if not has_custom_candidates:
            candidates = backfill_missing_media_types(
                candidates,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=bool(payload.get("include_anime", True)),
                target_total=max(30, _to_int(payload.get("limit"), 120, 1, 300)),
            )
        apply_curated_people_photos(apply_curated_posters(candidates))
        deduped: dict[str, MediaItem] = {}
        for item in candidates:
            key = recommendation_item_key(item)
            if key not in deduped:
                deduped[key] = item
        return list(deduped.values())

    def _ranked_channels(
        self,
        payload: dict[str, Any],
        intent: RecommendationIntent,
        rated_items: list[MediaItem],
        candidates: list[MediaItem],
        profile,
    ) -> dict[str, dict[str, object]]:
        ranked_by_channel: dict[str, dict[str, object]] = {}
        for channel in CHANNEL_ORDER:
            enabled = bool(payload.get(CHANNEL_FLAGS[channel], True))
            channel_candidates = [item for item in candidates if item.media_type == channel]
            pool_size = len(channel_candidates) if enabled else 0
            ranked_items: list[dict[str, object]] = []
            if enabled and (not intent.media_types or channel in intent.media_types):
                channel_intent = replace(intent, media_types=(channel,))
                ranked = rank_candidates(rated_items, channel_candidates, profile, channel_intent)
                ranked_items = [row.to_dict() for row in ranked]
            ranked_by_channel[channel] = {
                "items": ranked_items,
                "pool_size": pool_size,
                "matched_size": len(ranked_items),
            }
        return ranked_by_channel

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
        return {
            "schema_version": SCHEMA_VERSION,
            "id": restored.id,
            "profile_key": restored.profile_key,
            "status": restored.status,
            "intent": restored.intent.to_dict(),
            "channels": channels,
            "restore": self._restore_metadata(restored.channels),
            "created_at": restored.created_at,
            "updated_at": restored.updated_at,
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

    def _serialize_batch(self, batch: RecommendationBatch) -> dict[str, object]:
        return {
            "id": batch.id,
            "session_id": batch.session_id,
            "channel": batch.channel,
            "index": batch.index,
            "items": [_normalize_batch_item(dict(item)) for item in batch.items],
            "item_keys": list(batch.item_keys),
            "pool_size": batch.pool_size,
            "matched_size": batch.matched_size,
            "visible_size": batch.visible_size,
            "reason": batch.reason,
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
    return RecommendationApi(database)
