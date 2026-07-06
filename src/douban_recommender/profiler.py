from __future__ import annotations

from collections import Counter, defaultdict
from dataclasses import dataclass, field
import re

from .io import parse_list
from .models import MediaItem

KNOWN_GENRES = {
    "剧情", "喜剧", "爱情", "科幻", "悬疑", "犯罪", "惊悚", "恐怖", "动作", "奇幻", "冒险", "动画", "纪录片",
    "历史", "战争", "古装", "武侠", "同性", "音乐", "歌舞", "家庭", "传记", "西部", "灾难", "运动", "黑色电影",
    "短片", "儿童", "现实主义", "黑色幽默", "群像", "女性", "女性题材", "政治", "社会", "职场", "青春", "治愈", "公路",
}

FIELD_WEIGHTS = {
    "genre": 2.4,
    "tag": 1.8,
    "director": 1.6,
    "cast": 0.7,
    "country": 0.8,
    "language": 0.3,
    "media_type": 0.6,
    "year_bucket": 0.35,
    "keyword": 2.0,
}


@dataclass
class TasteProfile:
    positive: Counter[str] = field(default_factory=Counter)
    negative: Counter[str] = field(default_factory=Counter)
    positive_examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    negative_examples: dict[str, list[str]] = field(default_factory=lambda: defaultdict(list))
    manual_likes: list[str] = field(default_factory=list)
    manual_dislikes: list[str] = field(default_factory=list)
    rated_count: int = 0
    liked_count: int = 0
    disliked_count: int = 0

    def top_positive(self, prefix: str | None = None, n: int = 10) -> list[tuple[str, float]]:
        return self._top(self.positive, prefix, n)

    def top_negative(self, prefix: str | None = None, n: int = 10) -> list[tuple[str, float]]:
        return self._top(self.negative, prefix, n)

    @staticmethod
    def _top(counter: Counter[str], prefix: str | None, n: int) -> list[tuple[str, float]]:
        rows = []
        for key, value in counter.most_common():
            if prefix is None or key.startswith(prefix + ":"):
                rows.append((key.split(":", 1)[-1], round(float(value), 3)))
            if len(rows) >= n:
                break
        return rows

    def summary(self) -> dict[str, object]:
        return {
            "rated_count": self.rated_count,
            "liked_count": self.liked_count,
            "disliked_count": self.disliked_count,
            "top_genres": self.top_positive("genre", 8),
            "avoid_genres": self.top_negative("genre", 8),
            "top_tags": self.top_positive("tag", 8),
            "avoid_tags": self.top_negative("tag", 8),
            "top_directors": self.top_positive("director", 6),
            "top_countries": self.top_positive("country", 6),
            "manual_likes": self.manual_likes,
            "manual_dislikes": self.manual_dislikes,
        }


def build_taste_profile(
    rated_items: list[MediaItem],
    like_terms: str | list[str] | None = None,
    dislike_terms: str | list[str] | None = None,
    like_threshold: float = 4.0,
    dislike_threshold: float = 2.5,
) -> TasteProfile:
    profile = TasteProfile()
    profile.manual_likes = normalize_terms(like_terms)
    profile.manual_dislikes = normalize_terms(dislike_terms)
    profile.rated_count = len([item for item in rated_items if item.my_rating is not None])

    for term in profile.manual_likes:
        add_feature(profile.positive, profile.positive_examples, "keyword", term, 3.0, "手动偏好")
        if term in KNOWN_GENRES:
            add_feature(profile.positive, profile.positive_examples, "genre", term, 2.0, "手动偏好")
        else:
            add_feature(profile.positive, profile.positive_examples, "tag", term, 1.4, "手动偏好")
    for term in profile.manual_dislikes:
        add_feature(profile.negative, profile.negative_examples, "keyword", term, 3.2, "手动避雷")
        if term in KNOWN_GENRES:
            add_feature(profile.negative, profile.negative_examples, "genre", term, 2.0, "手动避雷")
        else:
            add_feature(profile.negative, profile.negative_examples, "tag", term, 1.5, "手动避雷")

    for item in rated_items:
        if item.my_rating is None:
            continue
        rating = float(item.my_rating)
        if rating >= like_threshold:
            profile.liked_count += 1
            strength = 0.5 + (rating - 3.0) / 2.0
            add_item_features(profile.positive, profile.positive_examples, item, strength, item.title)
            add_keywords_from_item(profile.positive, profile.positive_examples, item, strength * 0.45, item.title)
        elif rating <= dislike_threshold:
            profile.disliked_count += 1
            strength = 0.6 + (3.0 - rating) / 2.0
            add_item_features(profile.negative, profile.negative_examples, item, strength, item.title)
            add_keywords_from_item(profile.negative, profile.negative_examples, item, strength * 0.5, item.title)
        else:
            if rating > 3.0:
                add_item_features(profile.positive, profile.positive_examples, item, 0.15, item.title)
            elif rating < 3.0:
                add_item_features(profile.negative, profile.negative_examples, item, 0.15, item.title)
    return profile


def add_item_features(counter: Counter[str], examples: dict[str, list[str]], item: MediaItem, strength: float, example: str) -> None:
    for field, values in item.feature_values().items():
        weight = FIELD_WEIGHTS.get(field, 1.0)
        for idx, value in enumerate(values):
            rank_decay = 1.0
            if field == "cast":
                rank_decay = max(0.35, 1.0 - idx * 0.08)
            add_feature(counter, examples, field, value, strength * weight * rank_decay, example)


def add_feature(counter: Counter[str], examples: dict[str, list[str]], field: str, value: str, weight: float, example: str) -> None:
    value = normalize_term(value)
    if not value:
        return
    key = f"{field}:{value}"
    counter[key] += weight
    if len(examples[key]) < 5 and example not in examples[key]:
        examples[key].append(example)


def add_keywords_from_item(counter: Counter[str], examples: dict[str, list[str]], item: MediaItem, strength: float, example: str) -> None:
    blob = " ".join([item.title, item.summary, " ".join(item.tags), " ".join(item.genres)])
    for term in KNOWN_GENRES:
        if term in blob:
            add_feature(counter, examples, "keyword", term, strength, example)


def normalize_terms(terms: str | list[str] | None) -> list[str]:
    if not terms:
        return []
    if isinstance(terms, str):
        values = parse_list(terms)
    else:
        values = terms
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        term = normalize_term(value)
        if term and term not in seen:
            out.append(term)
            seen.add(term)
    return out


def normalize_term(value: str) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"\s+", " ", text)
    aliases = {
        "crime": "犯罪",
        "sci-fi": "科幻",
        "scifi": "科幻",
        "science fiction": "科幻",
        "thriller": "惊悚",
        "mystery": "悬疑",
        "romance": "爱情",
        "documentary": "纪录片",
        "tv": "电视剧",
        "series": "电视剧",
        "movie": "电影",
        "film": "电影",
        "甜宠剧": "甜宠",
        "狗血剧情": "狗血",
    }
    return aliases.get(text, text)
