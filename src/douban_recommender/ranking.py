from __future__ import annotations

from dataclasses import asdict, dataclass
from math import log10

from .eligibility import ScoreSignal, evaluate_eligibility
from .intent_parser import RecommendationIntent
from .models import MediaItem, normalize_title, recommendation_item_key
from .profiler import TasteProfile
from .recommender import Recommendation, item_quality, score_item


@dataclass(frozen=True)
class ScoreBreakdown:
    quality: float
    taste: float
    context: float
    exploration: float
    total: float
    confidence: float
    signals: tuple[ScoreSignal, ...] = ()
    conflicts: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, object]:
        payload = asdict(self)
        payload["signals"] = [asdict(signal) for signal in self.signals]
        payload["conflicts"] = list(self.conflicts)
        return payload


def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> float:
    return max(minimum, min(maximum, float(value)))


def calibrated_quality(item: MediaItem) -> tuple[float, list[ScoreSignal]]:
    prior_rating = 7.6
    prior_votes = 5000.0
    rating = float(item.douban_rating) if item.douban_rating is not None else 7.0
    votes = max(0.0, float(item.vote_count or 0))
    bayesian_rating = (votes / (votes + prior_votes)) * rating + (prior_votes / (votes + prior_votes)) * prior_rating
    score = bayesian_rating * 10.0
    signals = [
        ScoreSignal(
            "bayesian-rating",
            "贝叶斯质量评分",
            round(score, 3),
            (f"rating={rating:g}", f"votes={int(votes)}"),
        )
    ]
    completeness = 0.0
    if item.summary:
        completeness += 2.0
    if item.genres:
        completeness += 1.0
    if item.year:
        completeness += 0.8
    if item.directors:
        completeness += 1.0
    if item.casts:
        completeness += 0.8
    if item.cover and not str(item.cover).startswith("data:image/svg+xml"):
        completeness += 0.8
    people_photos = item.raw.get("people_photos") if isinstance(item.raw, dict) else None
    if isinstance(people_photos, dict) and people_photos:
        completeness += min(1.6, len(people_photos) * 0.35)
    if completeness:
        score += completeness
        signals.append(ScoreSignal("metadata-completeness", "资料完整度", completeness))
    if item.douban_rating is None:
        score -= 8.0
        signals.append(ScoreSignal("quality-rating-missing", "缺少稳定评分", -8.0))
    return _clamp(score), signals


def _raw_number(item: MediaItem, *keys: str) -> float | None:
    raw = item.raw if isinstance(item.raw, dict) else {}
    for key in keys:
        try:
            value = raw.get(key)
            if value not in (None, ""):
                return float(value)
        except (TypeError, ValueError):
            continue
    return None


def context_score(item: MediaItem, intent: RecommendationIntent) -> tuple[float, list[ScoreSignal]]:
    score = 72.0
    signals: list[ScoreSignal] = []
    blob = item.search_blob()
    genre_hits = set(intent.genres) & set(item.genres)
    if genre_hits:
        value = min(14.0, 7.0 + len(genre_hits) * 2.0)
        score += value
        signals.append(ScoreSignal("context-genre", "当前题材匹配", value, tuple(sorted(genre_hits))))
    mood_hits = [mood for mood in intent.moods if mood.casefold() in blob]
    if mood_hits:
        value = min(12.0, len(mood_hits) * 4.0)
        score += value
        signals.append(ScoreSignal("context-mood", "当前情绪匹配", value, tuple(mood_hits)))
    country_hits = set(intent.countries) & set(item.countries)
    if country_hits:
        score += 6.0
        signals.append(ScoreSignal("context-country", "当前地区匹配", 6.0, tuple(sorted(country_hits))))

    if intent.episode_runtime_max:
        runtime = _raw_number(item, "episode_runtime", "episodeRuntime", "episode_minutes", "duration_per_episode")
        if runtime is not None:
            if runtime <= intent.episode_runtime_max:
                score += 9.0
                signals.append(ScoreSignal("context-episode-runtime", "单集时长适合", 9.0, (f"{runtime:g}",)))
            else:
                score -= 14.0
                signals.append(ScoreSignal("context-episode-runtime-over", "单集时长偏长", -14.0, (f"{runtime:g}",)))
    if intent.runtime_max:
        runtime = _raw_number(item, "runtime", "runtime_minutes", "duration", "minutes")
        if runtime is not None:
            if runtime <= intent.runtime_max:
                score += 7.0
                signals.append(ScoreSignal("context-runtime", "片长适合", 7.0, (f"{runtime:g}",)))
            else:
                score -= 12.0
                signals.append(ScoreSignal("context-runtime-over", "片长偏长", -12.0, (f"{runtime:g}",)))

    raw = item.raw if isinstance(item.raw, dict) else {}
    pace = str(raw.get("pace") or "").casefold()
    if intent.pace == "fast" and pace:
        value = 7.0 if pace in {"fast", "quick", "紧凑", "快"} else -7.0
        score += value
        signals.append(ScoreSignal("context-pace", "节奏匹配" if value > 0 else "节奏冲突", value, (pace,)))
    return _clamp(score), signals


def exploration_score(item: MediaItem, profile: TasteProfile, intent: RecommendationIntent) -> tuple[float, list[ScoreSignal]]:
    score = 38.0 + intent.exploration_level * 30.0 + intent.surprise_level * 18.0
    signals: list[ScoreSignal] = []
    familiar_countries = {country for country, _ in profile.top_positive("country", 12)}
    item_countries = set(item.countries)
    if item_countries and not (item_countries & familiar_countries):
        score += 7.0
        signals.append(ScoreSignal("exploration-country", "地区探索补位", 7.0, tuple(item.countries[:2])))
    familiar_directors = {director for director, _ in profile.top_positive("director", 20)}
    if item.directors and not (set(item.directors) & familiar_directors):
        score += 4.0
        signals.append(ScoreSignal("exploration-creator", "新创作者探索", 4.0, tuple(item.directors[:2])))
    return _clamp(score), signals


def confidence_score(item: MediaItem, profile: TasteProfile) -> float:
    confidence = 0.28
    if item.douban_rating is not None:
        confidence += 0.20
    if item.vote_count:
        confidence += min(0.18, max(0.0, log10(max(item.vote_count, 1)) - 2.0) * 0.05)
    if item.summary and item.genres:
        confidence += 0.12
    if item.year and item.countries:
        confidence += 0.08
    if item.directors or item.casts:
        confidence += 0.07
    if profile.rated_count:
        confidence += min(0.07, profile.rated_count / 1000.0)
    return max(0.0, min(1.0, confidence))


def _seen_keys(rated_items: list[MediaItem]) -> set[str]:
    seen: set[str] = set()
    for item in rated_items:
        tags = set(item.tags or [])
        if item.my_rating is None and "看过" not in tags and not str(item.source or "").endswith(":collect"):
            continue
        seen.add(recommendation_item_key(item))
        if item.title and item.year is None:
            seen.add(normalize_title(item.title))
            seen.add(item.title)
    return seen


def _feature_set(item: MediaItem) -> set[str]:
    values = {f"media:{item.media_type}"}
    values.update(f"country:{value}" for value in item.countries[:2])
    values.update(f"genre:{value}" for value in item.genres[:4])
    values.update(f"director:{value}" for value in item.directors[:2])
    return values


def _similarity(left: MediaItem, right: MediaItem) -> float:
    left_features = _feature_set(left)
    right_features = _feature_set(right)
    if not left_features or not right_features:
        return 0.0
    return len(left_features & right_features) / len(left_features | right_features)


def diversity_rerank(
    recommendations: list[Recommendation],
    limit: int,
    lambda_value: float = 0.72,
) -> list[Recommendation]:
    if limit <= 0:
        return []
    remaining = sorted(recommendations, key=lambda row: row.score, reverse=True)
    selected: list[Recommendation] = []
    while remaining and len(selected) < limit:
        if not selected:
            selected.append(remaining.pop(0))
            continue

        def effective(row: Recommendation) -> tuple[float, float]:
            maximum_similarity = max(_similarity(row.item, chosen.item) for chosen in selected)
            score_gap = selected[0].score - row.score
            quality_guard = -((score_gap - 8.0) * 6.0 + 8.0) if score_gap > 8.0 else 0.0
            mmr = lambda_value * row.score - (1.0 - lambda_value) * maximum_similarity * 100.0 + quality_guard
            return mmr, row.score

        best = max(remaining, key=effective)
        selected.append(best)
        remaining.remove(best)
    return selected


def rank_candidates(
    rated_items: list[MediaItem],
    candidates: list[MediaItem],
    profile: TasteProfile,
    intent: RecommendationIntent,
    limit: int | None = None,
) -> list[Recommendation]:
    seen = _seen_keys(rated_items)
    deduped: dict[str, MediaItem] = {}
    for item in candidates:
        key = recommendation_item_key(item)
        existing = deduped.get(key)
        if existing is None or item_quality(item) > item_quality(existing):
            deduped[key] = item

    recommendations: list[Recommendation] = []
    costume_opt_in = "古装" in intent.genres or ("古装" in intent.free_text and "古装" not in intent.avoid)
    for item in deduped.values():
        eligibility = evaluate_eligibility(item, seen, intent)
        if not eligibility.eligible:
            continue
        baseline = score_item(item, profile, apply_costume_penalty=not costume_opt_in)
        quality, quality_signals = calibrated_quality(item)
        taste = _clamp(baseline.score)
        context, context_signals = context_score(item, intent)
        exploration, exploration_signals = exploration_score(item, profile, intent)
        signals = [*quality_signals, *context_signals, *exploration_signals, *eligibility.penalties]
        penalty_total = sum(signal.value for signal in eligibility.penalties)
        total = 0.30 * quality + 0.35 * taste + 0.20 * context + 0.15 * exploration + penalty_total
        total = _clamp(total)
        conflicts = [signal.label for signal in signals if signal.value <= -7.0]
        conflicts.extend(baseline.warnings[:2])
        breakdown = ScoreBreakdown(
            quality=round(quality, 2),
            taste=round(taste, 2),
            context=round(context, 2),
            exploration=round(exploration, 2),
            total=round(total, 2),
            confidence=round(confidence_score(item, profile), 3),
            signals=tuple(signals),
            conflicts=tuple(dict.fromkeys(conflicts)),
        )
        baseline.score = total
        baseline.score_breakdown = breakdown.to_dict()
        baseline.warnings = list(dict.fromkeys([*baseline.warnings, *breakdown.conflicts]))
        if context_signals:
            baseline.short_reason = context_signals[0].label
        recommendations.append(baseline)

    recommendations.sort(key=lambda row: row.score, reverse=True)
    target = len(recommendations) if limit is None else max(0, int(limit))
    return diversity_rerank(recommendations, target)
