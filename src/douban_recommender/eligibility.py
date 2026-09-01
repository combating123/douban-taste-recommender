from __future__ import annotations

import re
from dataclasses import dataclass

from .intent_parser import RecommendationIntent
from .models import MediaItem, canonical_media_type, recommendation_identity_tokens
from .ratings import fused_rating


@dataclass(frozen=True)
class ScoreSignal:
    code: str
    label: str
    value: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class EligibilityDecision:
    eligible: bool
    reasons: tuple[str, ...] = ()
    penalties: tuple[ScoreSignal, ...] = ()


PLACEHOLDER_TITLE_RE = re.compile(r"^(?:电影|电视剧|动漫|动画|影视|作品)?候选\s*#?\s*\d+$", re.I)
MOVIE_FORMATS = {"MOVIE", "FILM", "FEATURE", "THEATRICAL", "ANIME_MOVIE", "ANIMATION_MOVIE", "动画电影"}
SERIES_FORMATS = {"TV", "TV_SERIES", "SERIES", "ONA", "WEB", "MINISERIES"}
PLACEHOLDER_COVER_MARKERS = ("_default_", "/default_")


def _raw_int(raw: dict, *keys: str) -> int | None:
    for key in keys:
        value = raw.get(key)
        try:
            if value not in (None, ""):
                return int(value)
        except (TypeError, ValueError):
            continue
    return None


def is_animated_series(item: MediaItem) -> bool:
    raw = item.raw if isinstance(item.raw, dict) else {}
    if canonical_media_type(item.media_type) != "动漫":
        return False
    raw_format = str(
        raw.get("format")
        or raw.get("type")
        or raw.get("media_format")
        or raw.get("mediaType")
        or ""
    ).strip().upper().replace(" ", "_")
    if raw.get("is_movie") is True or raw_format in MOVIE_FORMATS or "动画电影" in item.search_blob():
        return False
    episodes = _raw_int(raw, "episodes", "episode_count", "num_episodes", "episodeCount")
    if raw_format in {"OVA", "OAD", "SPECIAL"}:
        return bool(episodes and episodes > 1)
    if raw_format in SERIES_FORMATS:
        return True
    if episodes is not None:
        return episodes > 0
    return False


def _search_blob(item: MediaItem) -> str:
    raw = item.raw if isinstance(item.raw, dict) else {}
    parts = [
        item.title,
        item.media_type,
        item.summary,
        " ".join(item.genres),
        " ".join(item.tags),
        str(raw.get("format") or ""),
        str(raw.get("pace") or ""),
        str(raw.get("mood") or ""),
    ]
    return " ".join(parts).casefold()


def _term_matches(item: MediaItem, term: str) -> bool:
    text = str(term or "").strip().casefold()
    if not text:
        return False
    blob = _search_blob(item)
    aliases = {
        "过度压抑": ("压抑", "沉重", "致郁"),
        "注水": ("注水", "拖沓"),
        "慢热": ("慢热", "节奏缓慢"),
        "古装": ("古装", "宫廷", "武侠"),
    }
    return any(alias.casefold() in blob for alias in aliases.get(text, (text,)))


def _runtime(item: MediaItem, episode: bool) -> int | None:
    raw = item.raw if isinstance(item.raw, dict) else {}
    keys = (
        ("episode_runtime", "episodeRuntime", "episode_minutes", "duration_per_episode")
        if episode
        else ("runtime", "runtime_minutes", "duration", "minutes")
    )
    return _raw_int(raw, *keys)


def catalog_quality_reasons(item: MediaItem) -> tuple[str, ...]:
    title = str(item.title or "").strip()
    if not title or PLACEHOLDER_TITLE_RE.fullmatch(re.sub(r"\s+", "", title)):
        return ("placeholder-title",)
    cover = str(item.cover or "").strip().casefold()
    if cover and any(marker in cover for marker in PLACEHOLDER_COVER_MARKERS):
        return ("placeholder-cover",)
    source = str(item.source or "").strip().casefold()
    user_tags = {str(tag or "").strip() for tag in item.tags or []}
    if (
        source.startswith(("douban_plan:", "douban_explore:"))
        and item.douban_rating is None
        and not ({"想看", "看过"} & user_tags)
    ):
        return ("unrated-public-discovery",)
    return ()


def evaluate_eligibility(
    item: MediaItem,
    seen_keys: set[str],
    intent: RecommendationIntent,
) -> EligibilityDecision:
    reasons: list[str] = []
    penalties: list[ScoreSignal] = []
    title = str(item.title or "").strip()
    quality_reasons = catalog_quality_reasons(item)
    if quality_reasons:
        return EligibilityDecision(False, quality_reasons)

    normalized_seen = {str(key).strip() for key in seen_keys if str(key).strip()}
    if set(recommendation_identity_tokens(item)) & normalized_seen:
        return EligibilityDecision(False, ("already-seen",))

    item_type = canonical_media_type(item.media_type)
    requested_types = {canonical_media_type(value) for value in intent.media_types if value}
    if requested_types and item_type not in requested_types:
        return EligibilityDecision(False, ("media-type-mismatch",))
    if "动漫" in requested_types and not is_animated_series(item):
        return EligibilityDecision(False, ("not-animated-series",))

    for term in intent.avoid:
        if _term_matches(item, term):
            return EligibilityDecision(False, ("explicit-avoid", str(term)))
    for term in intent.permanent_avoid:
        if _term_matches(item, term):
            return EligibilityDecision(False, ("explicit-avoid", str(term)))

    if intent.quality_floor is not None:
        quality = fused_rating(item)
        if quality.rating is not None and quality.rating < float(intent.quality_floor):
            return EligibilityDecision(False, ("below-quality-floor",))
        if quality.rating is None:
            penalties.append(ScoreSignal("rating-unknown", "评分资料不足", -6.0))

    if intent.year_min and item.year and int(item.year) < int(intent.year_min):
        return EligibilityDecision(False, ("before-year-range",))
    if intent.year_max and item.year and int(item.year) > int(intent.year_max):
        return EligibilityDecision(False, ("after-year-range",))

    costume_opt_in = "古装" in intent.genres or ("古装" in intent.free_text and "古装" not in intent.avoid)
    if item_type == "电视剧" and _term_matches(item, "古装") and not costume_opt_in:
        penalties.append(
            ScoreSignal(
                "costume-series",
                "电视剧古装默认降权",
                -18.0,
                tuple(value for value in item.genres if value in {"古装", "武侠"}),
            )
        )

    for adjustment in intent.session_only_adjustments:
        if _term_matches(item, adjustment):
            penalties.append(
                ScoreSignal(
                    f"session-{adjustment}",
                    f"本次会话避开：{adjustment}",
                    -14.0,
                    (adjustment,),
                )
            )

    if intent.genres and not (set(intent.genres) & set(item.genres)):
        penalties.append(ScoreSignal("genre-distance", "题材距离", -5.0, tuple(intent.genres)))
    if intent.countries and not (set(intent.countries) & set(item.countries)):
        penalties.append(ScoreSignal("country-distance", "地区距离", -4.0, tuple(intent.countries)))

    if intent.runtime_max:
        runtime = _runtime(item, episode=False)
        if runtime and runtime > intent.runtime_max:
            penalties.append(ScoreSignal("runtime-over", "片长超过当前目标", -8.0, (str(runtime),)))
    if intent.episode_runtime_max:
        episode_runtime = _runtime(item, episode=True)
        if episode_runtime and episode_runtime > intent.episode_runtime_max:
            penalties.append(
                ScoreSignal("episode-runtime-over", "单集时长超过当前目标", -8.0, (str(episode_runtime),))
            )

    reasons.append("eligible")
    return EligibilityDecision(True, tuple(reasons), tuple(penalties))
