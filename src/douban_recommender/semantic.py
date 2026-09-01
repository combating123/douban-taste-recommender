from __future__ import annotations

import hashlib
import math
import re
import unicodedata
from dataclasses import dataclass
from functools import lru_cache
from typing import Iterable, Sequence

from .intent_parser import RecommendationIntent
from .models import MediaItem
from .profiler import TasteProfile


VECTOR_SIZE = 384
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_WORD_RE = re.compile(r"[a-z0-9]+(?:['._-][a-z0-9]+)*", re.I)


def _tokens(text: object) -> list[str]:
    normalized = unicodedata.normalize("NFKC", str(text or "")).casefold()
    tokens = [f"w:{word}" for word in _WORD_RE.findall(normalized)]
    for sequence in _CJK_RE.findall(normalized):
        tokens.extend(f"c:{char}" for char in sequence)
        for size in (2, 3):
            tokens.extend(
                f"c{size}:{sequence[index:index + size]}"
                for index in range(max(0, len(sequence) - size + 1))
            )
    return tokens


@lru_cache(maxsize=65_536)
def _hash(token: str) -> tuple[int, float]:
    digest = hashlib.blake2b(token.encode("utf-8"), digest_size=8, person=b"CineVec1").digest()
    value = int.from_bytes(digest, "big", signed=False)
    return value % VECTOR_SIZE, 1.0 if value & (1 << 63) else -1.0


def _normalize(vector: Sequence[float]) -> tuple[float, ...]:
    norm = math.sqrt(sum(value * value for value in vector))
    if norm <= 0:
        return tuple(0.0 for _ in range(VECTOR_SIZE))
    return tuple(value / norm for value in vector)


@lru_cache(maxsize=8_192)
def _feature_vector_cached(text: str) -> tuple[float, ...]:
    values = [0.0] * VECTOR_SIZE
    frequencies: dict[str, int] = {}
    for token in _tokens(text):
        frequencies[token] = frequencies.get(token, 0) + 1
    for token, frequency in frequencies.items():
        index, sign = _hash(token)
        values[index] += sign * (1.0 + math.log(float(frequency)))
    return _normalize(values)


def feature_vector(text: object) -> tuple[float, ...]:
    """Return a deterministic local embedding while reusing repeated title text.

    Discovery compares the same focus and candidate records many times during a
    graph rebuild. Normalizing the public input to a string keeps the cache safe
    for arbitrary callers and avoids recomputing thousands of token hashes.
    """

    return _feature_vector_cached(str(text or ""))


def _cosine(left: Sequence[float], right: Sequence[float]) -> float:
    if not any(left) or not any(right):
        return 0.0
    return max(-1.0, min(1.0, sum(a * b for a, b in zip(left, right))))


def _average(vectors: Iterable[tuple[Sequence[float], float]]) -> tuple[float, ...]:
    values = [0.0] * VECTOR_SIZE
    total = 0.0
    for vector, weight in vectors:
        clean_weight = max(0.0, float(weight))
        if clean_weight <= 0 or not any(vector):
            continue
        total += clean_weight
        for index, value in enumerate(vector):
            values[index] += value * clean_weight
    if total:
        values = [value / total for value in values]
    return _normalize(values)


def _media_text(item: MediaItem) -> str:
    raw = item.raw if isinstance(item.raw, dict) else {}
    aliases = raw.get("aliases") if isinstance(raw.get("aliases"), list) else []
    fields = [
        item.title,
        item.summary,
        " ".join(f"类型{value}" for value in item.genres),
        " ".join(f"地区{value}" for value in item.countries),
        " ".join(f"语言{value}" for value in item.languages),
        " ".join(f"导演{value}" for value in item.directors),
        " ".join(f"演员{value}" for value in item.casts[:8]),
        " ".join(f"标签{value}" for value in item.tags),
        " ".join(str(value) for value in aliases),
        item.media_type,
    ]
    return "。".join(value for value in fields if value)


def _rating_polarity(item: MediaItem) -> tuple[str, float]:
    if item.my_rating is None:
        tags = {str(tag or "").strip() for tag in item.tags}
        return ("positive", 0.35) if "想看" in tags else ("neutral", 0.0)
    rating = float(item.my_rating)
    if rating > 5.0:
        if rating >= 8.0:
            return "positive", 0.75 + min(0.5, (rating - 8.0) / 4.0)
        if rating <= 5.5:
            return "negative", 0.75 + min(0.5, (5.5 - rating) / 5.5)
    else:
        if rating >= 4.0:
            return "positive", 0.75 + min(0.5, (rating - 4.0) / 2.0)
        if rating <= 2.5:
            return "negative", 0.75 + min(0.5, (2.5 - rating) / 2.5)
    return "neutral", 0.0


def _profile_text(profile: TasteProfile, positive: bool) -> str:
    rows: list[str] = []
    source = profile.top_positive if positive else profile.top_negative
    for field in ("genre", "tag", "director", "country", "keyword"):
        rows.extend(value for value, _ in source(field, 12))
    rows.extend(profile.manual_likes if positive else profile.manual_dislikes)
    return " ".join(rows)


def _intent_text(intent: RecommendationIntent) -> str:
    return " ".join([
        intent.free_text,
        *intent.media_types,
        *intent.genres,
        *intent.moods,
        *intent.countries,
        *intent.languages,
        intent.pace,
        intent.complexity,
    ])


@dataclass(frozen=True)
class SemanticScore:
    score: float
    positive_similarity: float
    negative_similarity: float
    intent_similarity: float
    evidence: tuple[str, ...] = ()


@dataclass(frozen=True)
class SemanticTasteModel:
    positive: tuple[float, ...]
    negative: tuple[float, ...]
    intent: tuple[float, ...]
    has_history: bool
    has_intent: bool

    def score(self, item: MediaItem) -> SemanticScore:
        candidate = feature_vector(_media_text(item))
        positive = max(0.0, _cosine(candidate, self.positive)) if self.has_history else 0.0
        negative = max(0.0, _cosine(candidate, self.negative)) if any(self.negative) else 0.0
        current = max(0.0, _cosine(candidate, self.intent)) if self.has_intent else 0.0
        score = max(0.0, min(100.0, 48.0 + positive * 58.0 - negative * 48.0 + current * 52.0))
        evidence: list[str] = []
        if positive > 0.08:
            evidence.append(f"长期口味相似 {positive * 100:.0f}%")
        if current > 0.08:
            evidence.append(f"本次描述相似 {current * 100:.0f}%")
        if negative > 0.10:
            evidence.append(f"负向口味重合 {negative * 100:.0f}%")
        return SemanticScore(
            round(score, 3),
            round(positive, 4),
            round(negative, 4),
            round(current, 4),
            tuple(evidence),
        )


def build_semantic_taste_model(
    rated_items: list[MediaItem],
    profile: TasteProfile,
    intent: RecommendationIntent,
) -> SemanticTasteModel:
    positive_vectors: list[tuple[Sequence[float], float]] = []
    negative_vectors: list[tuple[Sequence[float], float]] = []
    for item in rated_items:
        polarity, weight = _rating_polarity(item)
        if polarity == "neutral":
            continue
        row = (feature_vector(_media_text(item)), weight)
        if polarity == "positive":
            positive_vectors.append(row)
        else:
            negative_vectors.append(row)

    positive_profile = feature_vector(_profile_text(profile, True))
    negative_profile = feature_vector(_profile_text(profile, False))
    if any(positive_profile):
        positive_vectors.append((positive_profile, 0.65))
    if any(negative_profile):
        negative_vectors.append((negative_profile, 0.65))

    positive = _average(positive_vectors)
    negative = _average(negative_vectors)
    current = feature_vector(_intent_text(intent))
    return SemanticTasteModel(
        positive=positive,
        negative=negative,
        intent=current,
        has_history=bool(positive_vectors),
        has_intent=bool(any(current)),
    )
