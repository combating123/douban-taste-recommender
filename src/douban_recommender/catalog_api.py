from __future__ import annotations

from pathlib import Path

from .database import AppDatabase
from .exploration_service import ExplorationError, ExplorationService
from .runtime_paths import resolve_database_path, resolve_media_dir


class CatalogApiError(ValueError):
    status_code = 400


class CatalogApiNotFound(CatalogApiError):
    status_code = 404


def _map_error(exc: ExplorationError) -> CatalogApiError:
    if getattr(exc, "status_code", 400) == 404:
        return CatalogApiNotFound(str(exc))
    return CatalogApiError(str(exc))


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

    def taste(self, query: dict[str, list[str]]) -> dict[str, object]:
        try:
            return self.service.taste(profile_key=_query_value(query, "profile_key", "default"))
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
    text = str(value or "").strip("/")
    if not text or "/" in text or "\\" in text or ".." in text:
        raise CatalogApiNotFound("not found")
    return text


def _query_value(query: dict[str, list[str]], key: str, default: str) -> str:
    values = query.get(key)
    if not values:
        return default
    return str(values[0] or "")


def _int_query(query: dict[str, list[str]], key: str, default: int) -> int:
    raw = _query_value(query, key, str(default))
    try:
        return int(raw)
    except (TypeError, ValueError) as exc:
        raise CatalogApiError(f"invalid {key}") from exc
