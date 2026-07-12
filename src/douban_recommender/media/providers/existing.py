from __future__ import annotations

from collections.abc import Callable, Iterable
from typing import Any

from ...douban_sources import (
    fetch_anilist_suggestions,
    fetch_jikan_suggestions,
    fetch_subject_suggestions,
    fetch_themoviedb_suggestions,
    fetch_tvmaze_suggestions,
    fetch_wikipedia_image_suggestions,
)
from ...identity_service import PersonIdentity, WorkIdentity
from ...models import MediaItem
from ..public_people import resolve_public_people_photos
from .base import AssetCandidate, AssetQuery
from .inline import InlineProvider


SearchFunction = Callable[..., list[MediaItem]]
PeopleResolver = Callable[[list[str]], dict[str, str]]


def _int_or_none(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _original_titles(item: MediaItem) -> tuple[str, ...]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    values: list[str] = []
    for key in (
        "original_title",
        "original_name",
        "title_english",
        "title_japanese",
        "english_title",
        "romaji_title",
    ):
        value = raw.get(key)
        if value:
            values.append(str(value).strip())
    nested_title = raw.get("title")
    if isinstance(nested_title, dict):
        values.extend(str(value).strip() for value in nested_title.values() if value)
    titles = raw.get("titles")
    if isinstance(titles, list):
        for value in titles:
            if isinstance(value, dict):
                text = value.get("title") or value.get("name")
                if text:
                    values.append(str(text).strip())
            elif value:
                values.append(str(value).strip())
    seen: set[str] = set()
    out: list[str] = []
    for value in values:
        if value and value != item.title and value not in seen:
            seen.add(value)
            out.append(value)
    return tuple(out)


def _provider_ids(item: MediaItem) -> dict[str, str]:
    identifier = str(item.douban_id or "").strip()
    if not identifier:
        return {}
    prefixes = {
        "anilist-": "anilist",
        "mal-": "mal",
        "tvmaze-": "tvmaze",
        "imdb-": "imdb",
        "tmdb-movie-": "tmdb",
        "tmdb-tv-": "tmdb",
    }
    for prefix, provider in prefixes.items():
        if identifier.startswith(prefix):
            return {provider: identifier[len(prefix) :]}
    if identifier.isdigit():
        return {"douban": identifier}
    return {}


def _work_identity(item: MediaItem) -> WorkIdentity:
    raw = item.raw if isinstance(item.raw, dict) else {}
    return WorkIdentity(
        title=item.title,
        original_titles=_original_titles(item),
        year=item.year,
        media_type=item.media_type or str(raw.get("format") or ""),
        countries=tuple(item.countries or ()),
        directors=tuple(item.directors or ()),
        casts=tuple(item.casts or ()),
        episode_count=(
            _int_or_none(raw.get("episodes"))
            or _int_or_none(raw.get("episode_count"))
            or _int_or_none(raw.get("num_episodes"))
        ),
        provider_ids=_provider_ids(item),
    )


def _declared_type(url: str) -> str:
    lower = str(url or "").lower().split("?", 1)[0]
    if lower.endswith((".jpg", ".jpeg")):
        return "image/jpeg"
    if lower.endswith(".png"):
        return "image/png"
    if lower.endswith(".webp"):
        return "image/webp"
    return ""


class ExistingPosterProvider:
    name = "existing"

    def __init__(self, searcher: SearchFunction):
        self.searcher = searcher

    def _search_items(self, query: AssetQuery) -> list[MediaItem]:
        return list(self.searcher(query.title, media_type=query.media_type) or [])

    def search(self, query: AssetQuery) -> list[AssetCandidate]:
        if query.kind not in {"poster", "backdrop"} or not query.title:
            return []
        candidates: list[AssetCandidate] = []
        for item in self._search_items(query):
            url = str(item.cover or "").strip()
            if not url.startswith(("http://", "https://")):
                continue
            candidates.append(
                AssetCandidate(
                    url=url,
                    source=self.name,
                    kind=query.kind,
                    work_identity=_work_identity(item),
                    declared_type=_declared_type(url),
                    metadata={"provider_source": item.source, "provider_url": item.url},
                )
            )
        return candidates


class TmdbProvider(ExistingPosterProvider):
    name = "tmdb"

    def __init__(self, searcher: SearchFunction | None = None):
        super().__init__(searcher or fetch_themoviedb_suggestions)


class TvMazeProvider(ExistingPosterProvider):
    name = "tvmaze"

    def __init__(self, searcher: SearchFunction | None = None):
        super().__init__(searcher or fetch_tvmaze_suggestions)


class AniListProvider(ExistingPosterProvider):
    name = "anilist"

    def __init__(self, searcher: SearchFunction | None = None):
        super().__init__(searcher or fetch_anilist_suggestions)


class JikanProvider(ExistingPosterProvider):
    name = "jikan"

    def __init__(self, searcher: SearchFunction | None = None):
        super().__init__(searcher or fetch_jikan_suggestions)


class DoubanProvider(ExistingPosterProvider):
    name = "douban"

    def __init__(self, searcher: SearchFunction | None = None):
        super().__init__(searcher or fetch_subject_suggestions)

    def _search_items(self, query: AssetQuery) -> list[MediaItem]:
        return list(self.searcher(query.title) or [])


class WikidataProvider(ExistingPosterProvider):
    name = "wikidata"

    def __init__(
        self,
        searcher: SearchFunction | None = None,
        people_resolver: PeopleResolver | None = None,
    ):
        super().__init__(searcher or fetch_wikipedia_image_suggestions)
        self.people_resolver = (
            people_resolver if people_resolver is not None else resolve_public_people_photos
        )

    def search(self, query: AssetQuery) -> list[AssetCandidate]:
        if query.kind != "portrait":
            return super().search(query)
        name = str(query.person_name or "").strip()
        if not name or self.people_resolver is None:
            return []
        resolved = self.people_resolver([name]) or {}
        url = str(resolved.get(name) or "").strip()
        if not url.startswith(("http://", "https://")):
            return []
        return [
            AssetCandidate(
                url=url,
                source=self.name,
                kind="portrait",
                person_identity=PersonIdentity(
                    name=name,
                    aliases=tuple(query.aliases),
                    occupations=tuple(query.occupations),
                    known_works=tuple(query.work_context),
                    provider_ids=dict(query.provider_ids),
                ),
                declared_type=_declared_type(url),
            )
        ]


def providers_for(kind: str, media_type: str) -> list[Any]:
    normalized_kind = str(kind or "poster").strip().lower()
    normalized_type = str(media_type or "").strip()
    if normalized_kind == "portrait":
        if normalized_type == "电视剧":
            return [InlineProvider(), TvMazeProvider(), WikidataProvider(), DoubanProvider()]
        if normalized_type in {"动漫", "动画"}:
            return [InlineProvider(), JikanProvider(), WikidataProvider(), DoubanProvider()]
        return [InlineProvider(), TmdbProvider(), WikidataProvider(), DoubanProvider()]
    if normalized_type in {"动漫", "动画"}:
        return [InlineProvider(), AniListProvider(), JikanProvider(), TmdbProvider(), WikidataProvider(), DoubanProvider()]
    if normalized_type == "电视剧":
        return [InlineProvider(), TvMazeProvider(), TmdbProvider(), WikidataProvider(), DoubanProvider()]
    return [InlineProvider(), TmdbProvider(), WikidataProvider(), DoubanProvider()]
