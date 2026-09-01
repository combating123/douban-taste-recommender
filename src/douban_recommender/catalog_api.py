from __future__ import annotations

import time
from pathlib import Path

from .catalog_registry import CatalogRegistry
from .curated_catalog import apply_curated_people_photos
from .database import AppDatabase
from .douban_sources import enrich_media_items, enrich_public_metadata, fetch_douban_detail_html, is_localized_summary, summary_translation_needs_refresh
from .exploration_service import ExplorationError, ExplorationService
from .intent_parser import RecommendationIntent, parse_recommendation_intent
from .models import is_safe_route_segment
from .runtime_paths import resolve_database_path, resolve_media_dir


class CatalogApiError(ValueError):
    status_code = 400


class CatalogApiNotFound(CatalogApiError):
    status_code = 404


def _map_error(exc: ExplorationError) -> CatalogApiError:
    if getattr(exc, "status_code", 400) == 404:
        return CatalogApiNotFound(str(exc))
    return CatalogApiError(str(exc))


def _needs_public_metadata_fallback(item) -> bool:
    raw = item.raw if isinstance(item.raw, dict) else {}
    ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    has_rating = item.douban_rating is not None
    if not has_rating:
        for value in ratings.values():
            try:
                if float(value) > 0:
                    has_rating = True
                    break
            except (TypeError, ValueError):
                continue
    stills = raw.get("stills") if isinstance(raw.get("stills"), list) else []
    if summary_translation_needs_refresh(item):
        return True
    return not all((
        is_localized_summary(item.summary),
        bool(item.genres),
        has_rating,
        bool(item.directors),
        bool(item.casts),
        bool(stills),
    ))


class CatalogApi:
    def __init__(self, database: AppDatabase, media_root: Path | str | None = None, service: ExplorationService | None = None):
        self.database = database
        self.database.initialize()
        self.service = service or ExplorationService(database, media_root=media_root)

    def get_title(self, title_id: str) -> dict[str, object]:
        try:
            return self.service.title(_single_segment(title_id))
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def enrich_title(self, title_id: str, cookie: str = "") -> dict[str, object]:
        clean_id = _single_segment(title_id)
        record = self.service.find_title(clean_id)
        if record is None:
            raise CatalogApiNotFound("title not found")
        item = record.item
        # Curated seed identities are applied before public enrichment so a
        # stale numeric id can never pull another title's synopsis or images.
        apply_curated_people_photos([item])
        clean_cookie = str(cookie or "").strip()
        fetcher = (
            (lambda url: fetch_douban_detail_html(url, clean_cookie, timeout=6))
            if clean_cookie
            else None
        )
        enrich_media_items(
            [item],
            fetcher=fetcher,
            limit=1,
            sleep_seconds=0,
            force_people_photos=True,
        )
        if _needs_public_metadata_fallback(item):
            enrich_public_metadata(item)
        apply_curated_people_photos([item])
        now = time.time()
        with self.database.connection() as connection:
            CatalogRegistry.register_enriched_item(connection, record.item_key, item, now)
        return self.service.title(record.item_key)

    def get_person(self, person_id: str) -> dict[str, object]:
        try:
            return self.service.person(_single_segment(person_id))
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def list_library(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.library(
                state=_query_value(query, "state", "all"),
                cursor=_query_value(query, "cursor", ""),
                limit=_int_query(query, "limit", 24),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def recent(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.recent_history(
                profile_key=_query_value(query, "profile_key", "default"),
                limit=_int_query(query, "limit", 24),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def latest(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.latest_discovery(
                profile_key=_query_value(query, "profile_key", "default"),
                limit=_int_query(query, "limit", 24),
                refresh=_query_bool(query, "refresh", False),
                media_type=_query_value(query, "media_type", ""),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def observatory(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.observatory(
                profile_key=_query_value(query, "profile_key", "default"),
                limit=_int_query(query, "limit", 18),
                refresh=_query_bool(query, "refresh", False),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def taste(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.taste(profile_key=_query_value(query, "profile_key", "default"))
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def search_titles(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.search_titles(
                _query_value(query, "q", ""),
                limit=_int_query(query, "limit", 4),
                media_hint=_query_value(query, "media_type", _query_value(query, "media_hint", "")),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def similar_titles(self, query: dict[str, list[str]]) -> dict[str, object]:
        focus = _query_value(query, "focus", "")
        if not focus:
            raise CatalogApiError("focus is required")
        text = _query_value(query, "text", "")
        intent = parse_recommendation_intent(text) if text else RecommendationIntent()
        try:
            return self.service.similar_titles(
                focus,
                mode=_query_value(query, "mode", intent.similarity_mode),
                intent=intent,
                limit=_int_query(query, "limit", 12),
                require_poster=_query_bool(query, "complete_media", False),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def multi_focus_titles(self, query: dict[str, list[str]]) -> dict[str, object]:
        focuses = [
            _single_segment(value)
            for value in query.get("focus", [])[:3]
            if str(value or "").strip()
        ]
        if not focuses:
            raise CatalogApiError("at least one focus is required")
        try:
            return self.service.multi_focus_titles(
                focuses,
                limit=_int_query(query, "limit", 18),
                require_poster=_query_bool(query, "complete_media", False),
                round_index=_int_query(query, "round", 0),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def discovery_query(self, payload: dict[str, object]) -> dict[str, object]:
        try:
            return self.service.discover_from_query(
                str(payload.get("text") or ""),
                selection_id=str(payload.get("selection_id") or ""),
                base_intent=payload.get("intent") if isinstance(payload.get("intent"), dict) else None,
                limit=_payload_int(payload, "limit", 12),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def blend_titles(self, payload: dict[str, object]) -> dict[str, object]:
        left = str(payload.get("left") or "").strip()
        right = str(payload.get("right") or "").strip()
        if not left or not right:
            raise CatalogApiError("left and right are required")
        base = RecommendationIntent.from_dict(payload.get("intent") if isinstance(payload.get("intent"), dict) else None)
        text = str(payload.get("text") or "").strip()
        intent = parse_recommendation_intent(text, base=base) if text else base
        try:
            return self.service.blend_titles(
                left,
                right,
                left_weight=_payload_float(payload, "left_weight", 0.5),
                intent=intent,
                limit=_payload_int(payload, "limit", 12),
            )
        except ExplorationError as exc:
            raise _map_error(exc) from exc

    def universe(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            focus = _query_value(query, "focus", "")
            if not focus:
                raise CatalogApiError("focus is required")
            return self.service.build_universe_graph(focus, limit=_int_query(query, "limit", 9))
        except ExplorationError as exc:
            raise _map_error(exc) from exc


def build_default_catalog_api() -> CatalogApi:
    database = AppDatabase(resolve_database_path())
    database.initialize()
    return CatalogApi(database, media_root=resolve_media_dir())


def _single_segment(value: str) -> str:
    text = str(value or "")
    if not is_safe_route_segment(text):
        raise CatalogApiNotFound("not found")
    return text


def _query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return str(values[0] or "")


def _payload_int(payload: dict[str, object], key: str, default: int) -> int:
    try:
        return int(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _payload_float(payload: dict[str, object], key: str, default: float) -> float:
    try:
        return float(payload.get(key, default))
    except (TypeError, ValueError):
        return default


def _int_query(query: dict[str, list[str]], key: str, default: int) -> int:
    raw = _query_value(query, key, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise CatalogApiError(f"invalid {key}") from exc


def _query_bool(query: dict[str, list[str]], key: str, default: bool) -> bool:
    raw = _query_value(query, key, "1" if default else "0").strip().casefold()
    if raw in {"1", "true", "yes", "on"}:
        return True
    if raw in {"0", "false", "no", "off", ""}:
        return False
    raise CatalogApiError(f"invalid {key}")
