from __future__ import annotations

from dataclasses import dataclass
from math import log10

from .models import MediaItem, canonical_media_type


PROVIDER_LABELS = {
    "douban": "豆瓣",
    "imdb": "IMDb",
    "tmdb": "TMDb",
    "tvmaze": "TVMaze",
    "anilist": "AniList",
    "jikan": "MyAnimeList",
}

_PROVIDER_ALIASES = {
    "豆瓣": "douban",
    "mal": "jikan",
    "myanimelist": "jikan",
    "my_anime_list": "jikan",
}

_WEIGHTS = {
    "电影": {
        "douban": 0.38,
        "imdb": 0.32,
        "tmdb": 0.20,
        "tvmaze": 0.04,
        "anilist": 0.03,
        "jikan": 0.03,
    },
    "电视剧": {
        "douban": 0.32,
        "imdb": 0.29,
        "tmdb": 0.18,
        "tvmaze": 0.16,
        "anilist": 0.025,
        "jikan": 0.025,
    },
    "动漫": {
        "douban": 0.24,
        "imdb": 0.10,
        "tmdb": 0.08,
        "tvmaze": 0.04,
        "anilist": 0.28,
        "jikan": 0.26,
    },
}


@dataclass(frozen=True)
class FusedRating:
    rating: float | None
    confidence: float
    providers: tuple[str, ...]
    provider_ratings: dict[str, float]
    vote_count: int

    @property
    def labels(self) -> tuple[str, ...]:
        return tuple(PROVIDER_LABELS.get(provider, provider) for provider in self.providers)


def _provider(value: object) -> str:
    text = str(value or "").strip().casefold().replace("-", "_").replace(" ", "")
    return _PROVIDER_ALIASES.get(text, text)


def _score(value: object) -> float | None:
    try:
        score = float(value)
    except (TypeError, ValueError):
        return None
    if score <= 0:
        return None
    if score <= 10:
        return round(score, 3)
    if score <= 100:
        return round(score / 10.0, 3)
    return None


def _positive_int(value: object) -> int:
    try:
        return max(0, int(float(value)))
    except (TypeError, ValueError):
        return 0


def _rating_votes(item: MediaItem, providers: tuple[str, ...]) -> dict[str, int]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    values = raw.get("rating_votes") if isinstance(raw.get("rating_votes"), dict) else {}
    votes: dict[str, int] = {}
    for key, value in values.items():
        normalized = _provider(key)
        if normalized.endswith("_popularity"):
            normalized = normalized.removesuffix("_popularity")
        if normalized.endswith("_weight"):
            normalized = normalized.removesuffix("_weight")
        if normalized.endswith("_votes"):
            normalized = normalized.removesuffix("_votes")
        amount = _positive_int(value)
        if normalized in providers and amount:
            votes[normalized] = max(votes.get(normalized, 0), amount)

    fallback = _positive_int(item.vote_count)
    if fallback and providers:
        if len(providers) == 1:
            votes.setdefault(providers[0], fallback)
        elif not votes:
            votes[providers[0]] = fallback
    return votes


def fused_rating(item: MediaItem) -> FusedRating:
    raw = item.raw if isinstance(item.raw, dict) else {}
    source_ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    ratings: dict[str, float] = {}
    if item.douban_rating is not None:
        score = _score(item.douban_rating)
        if score is not None:
            ratings["douban"] = score
    for key, value in source_ratings.items():
        provider = _provider(key)
        score = _score(value)
        if provider and score is not None:
            ratings[provider] = score

    media_type = canonical_media_type(item.media_type)
    weights = _WEIGHTS.get(media_type, _WEIGHTS["电影"])
    ordered = tuple(sorted(ratings, key=lambda provider: (-weights.get(provider, 0.06), provider)))
    if not ordered:
        return FusedRating(None, 0.0, (), {}, 0)

    numerator = 0.0
    denominator = 0.0
    for provider in ordered:
        weight = weights.get(provider, 0.06)
        numerator += ratings[provider] * weight
        denominator += weight
    weighted = numerator / denominator if denominator else sum(ratings.values()) / len(ratings)

    votes_by_provider = _rating_votes(item, ordered)
    total_votes = sum(votes_by_provider.values()) or _positive_int(item.vote_count)
    sample_strength = min(1.0, log10(total_votes + 10.0) / 5.0) if total_votes else 0.0
    shrink_strength = 0.70 + 0.30 * sample_strength
    rating = weighted * shrink_strength + 7.4 * (1.0 - shrink_strength)

    spread = max(ratings.values()) - min(ratings.values()) if len(ratings) > 1 else 0.0
    agreement = max(0.0, 1.0 - spread / 3.0)
    provider_confidence = min(0.32, len(ordered) * 0.14)
    vote_confidence = min(0.30, log10(total_votes + 10.0) * 0.06) if total_votes else 0.0
    confidence = min(0.99, 0.28 + provider_confidence + vote_confidence + agreement * 0.10)
    return FusedRating(
        round(rating, 3),
        round(confidence, 3),
        ordered,
        {provider: ratings[provider] for provider in ordered},
        total_votes,
    )
