from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from .models import MediaItem


_PROVIDER_LABELS = {
    "tmdb": "TMDb",
    "omdb": "IMDb",
    "imdb": "IMDb",
    "tvmaze": "TVMaze",
    "anilist": "AniList",
    "jikan": "MAL",
    "mal": "MAL",
    "apple_movies": "Apple TV",
}
_PROVIDER_ORDER = tuple(_PROVIDER_LABELS)
_CURATED_PREFIXES = ("title_seed", "curated_seed", "premium_expansion")
_LOCAL_PREFIXES = ("global-cache:", "douban_user:", "douban-sync:", "local", "csv")
_DOUBAN_DISCOVERY_PREFIXES = ("douban_explore:", "douban_plan:", "douban_page:")


def _record_parts(value: MediaItem | Mapping[str, Any] | object) -> tuple[str, list[str]]:
    if isinstance(value, MediaItem):
        source = str(value.source or "").strip()
        raw = value.raw if isinstance(value.raw, dict) else {}
        providers = raw.get("discovery_sources")
    elif isinstance(value, Mapping):
        source = str(value.get("source") or "").strip()
        providers = value.get("discovery_sources")
        if not isinstance(providers, (list, tuple, set)):
            raw = value.get("raw") if isinstance(value.get("raw"), Mapping) else {}
            providers = raw.get("discovery_sources")
    else:
        source = str(getattr(value, "source", "") or "").strip()
        raw = getattr(value, "raw", {})
        providers = raw.get("discovery_sources") if isinstance(raw, Mapping) else []

    clean_providers: list[str] = []
    if isinstance(providers, (list, tuple, set)):
        for provider in providers:
            clean = str(provider or "").strip().casefold()
            if clean and clean not in clean_providers:
                clean_providers.append(clean)
    return source, clean_providers


def _providers_from_source(source: str) -> list[str]:
    providers: list[str] = []
    for segment in (part.strip().casefold() for part in source.split("|")):
        if not segment.startswith("global:"):
            continue
        suffix = segment.removeprefix("global:")
        for provider in _PROVIDER_ORDER:
            if suffix == provider or suffix.startswith(f"{provider}_") or suffix.startswith(f"{provider}:"):
                canonical = "imdb" if provider == "omdb" else ("jikan" if provider == "mal" else provider)
                if canonical not in providers:
                    providers.append(canonical)
                break
    return providers


def _provider_label(provider: str) -> str:
    return _PROVIDER_LABELS.get(provider.casefold(), provider)


def candidate_origin(value: MediaItem | Mapping[str, Any] | object) -> dict[str, object]:
    """Classify whether a recommendation came from this request's online discovery.

    Cached global rows are deliberately treated as catalog rows: they already live in
    the local index and must not inflate the current request's online-discovery count.
    """

    source, providers = _record_parts(value)
    folded = source.casefold()
    source_segments = [segment.strip() for segment in folded.split("|") if segment.strip()]
    cached_global = folded.startswith("global-cache:")
    online = not cached_global and (
        any(segment.startswith("global:") for segment in source_segments)
        or bool(providers)
    )
    if online:
        for provider in _providers_from_source(source):
            if provider not in providers:
                providers.append(provider)
        visible_labels = [_provider_label(provider) for provider in providers]
        label = "\u5728\u7ebf\u53d1\u73b0"
        if visible_labels:
            label += " \u00b7 " + " / ".join(visible_labels)
        return {"kind": "online", "label": label, "providers": providers}

    if folded.startswith(_LOCAL_PREFIXES):
        label = "\u672c\u673a\u7247\u5e93"
    elif folded.startswith(_DOUBAN_DISCOVERY_PREFIXES):
        label = "\u8c46\u74e3\u5019\u9009"
    elif folded.startswith(_CURATED_PREFIXES):
        label = "\u7cbe\u9009\u5019\u9009"
    else:
        label = "\u7cbe\u9009\u5019\u9009"
    return {"kind": "catalog", "label": label, "providers": []}


def is_online_discovery(value: MediaItem | Mapping[str, Any] | object) -> bool:
    return candidate_origin(value)["kind"] == "online"
