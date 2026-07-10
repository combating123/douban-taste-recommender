from __future__ import annotations

import re
from dataclasses import asdict, dataclass


@dataclass(frozen=True)
class RecommendationIntent:
    media_types: tuple[str, ...] = ()
    genres: tuple[str, ...] = ()
    moods: tuple[str, ...] = ()
    pace: str = ""
    complexity: str = ""
    intensity_max: str = ""
    runtime_max: int | None = None
    episode_runtime_max: int | None = None
    countries: tuple[str, ...] = ()
    languages: tuple[str, ...] = ()
    year_min: int | None = None
    year_max: int | None = None
    quality_floor: float | None = None
    avoid: tuple[str, ...] = ()
    exploration_level: float = 0.35
    surprise_level: float = 0.20
    session_only_adjustments: tuple[str, ...] = ()
    permanent_avoid: tuple[str, ...] = ()
    free_text: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)

    @classmethod
    def from_dict(cls, payload: dict | None) -> "RecommendationIntent":
        data = dict(payload or {})
        tuple_fields = {
            "media_types",
            "genres",
            "moods",
            "countries",
            "languages",
            "avoid",
            "session_only_adjustments",
            "permanent_avoid",
        }
        for field_name in tuple_fields:
            value = data.get(field_name, ())
            if isinstance(value, str):
                value = [value]
            data[field_name] = tuple(str(item) for item in (value or ()) if str(item).strip())
        allowed = {field.name for field in cls.__dataclass_fields__.values()}
        return cls(**{key: value for key, value in data.items() if key in allowed})


@dataclass(frozen=True)
class IntentChip:
    key: str
    label: str
    value: object
    removable: bool = True


MEDIA_PHRASES = (
    ("动漫", ("动画剧集", "动漫剧集", "番剧", "动漫", "动画番剧")),
    ("电视剧", ("电视剧", "剧集", "美剧", "英剧", "日剧", "韩剧", "国产剧")),
    ("电影", ("电影", "影片")),
)
GENRES = (
    "悬疑",
    "犯罪",
    "科幻",
    "剧情",
    "喜剧",
    "爱情",
    "惊悚",
    "动作",
    "冒险",
    "纪录片",
    "奇幻",
    "音乐",
    "战争",
)
MOOD_ALIASES = {
    "群像": ("群像",),
    "聪明叙事": ("聪明", "机巧", "智性"),
    "轻松": ("轻松", "轻盈", "不费脑"),
    "温暖": ("温暖", "暖心"),
    "治愈": ("治愈",),
    "烧脑": ("烧脑", "复杂精密"),
    "成长": ("成长",),
    "现实": ("现实", "写实"),
    "浪漫": ("浪漫",),
}
COUNTRIES = ("中国大陆", "中国", "美国", "英国", "日本", "韩国", "法国", "德国", "加拿大", "印度")
AVOID_ALIASES = {
    "过度压抑": ("太压抑", "过度压抑", "特别压抑", "很压抑", "压抑"),
    "古装": ("古装",),
    "注水": ("注水剧", "注水"),
    "慢热": ("慢热",),
    "狗血": ("狗血",),
    "恐怖": ("恐怖", "吓人"),
    "血腥": ("血腥",),
    "低幼": ("低幼",),
}
NEGATION_MARKERS = ("不要", "不想看", "避开", "拒绝", "别来", "不喜欢", "不看", "不要太")
SESSION_MARKERS = ("今晚", "今天", "现在", "这次", "此刻", "这会儿")
PERMANENT_MARKERS = ("以后", "永久", "永远", "长期", "再也")


def _ordered_unique(values) -> tuple[str, ...]:
    out: list[str] = []
    for value in values:
        text = str(value or "").strip()
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _contains_any(text: str, aliases) -> bool:
    return any(alias in text for alias in aliases)


def _is_negated(text: str, alias: str) -> bool:
    start = text.find(alias)
    while start >= 0:
        prefix = text[max(0, start - 24) : start]
        if any(marker in prefix for marker in NEGATION_MARKERS):
            return True
        start = text.find(alias, start + len(alias))
    return False


def _extract_runtime(text: str, episode: bool) -> int | None:
    prefix = r"(?:一集|单集|每集)[^，。；]{0,12}?" if episode else r""
    minute_match = re.search(prefix + r"(\d{1,3})\s*分钟(?:以内|以下|之内|不超过)?", text)
    if minute_match:
        return int(minute_match.group(1))
    if episode:
        return None
    hour_match = re.search(r"(\d+(?:\.\d+)?)\s*个?小时(?:以内|以下|之内|不超过)?", text)
    if hour_match:
        return int(round(float(hour_match.group(1)) * 60))
    chinese_hour = re.search(r"([一二两三四五六])\s*个?小时(?:以内|以下|之内|不超过)?", text)
    if chinese_hour:
        values = {"一": 1, "二": 2, "两": 2, "三": 3, "四": 4, "五": 5, "六": 6}
        return values[chinese_hour.group(1)] * 60
    return None


def parse_recommendation_intent(
    text: str,
    base: RecommendationIntent | None = None,
) -> RecommendationIntent:
    raw = str(text or "").strip()
    current = base or RecommendationIntent()

    media_types = list(current.media_types)
    detected_media: list[str] = []
    for media_type, aliases in MEDIA_PHRASES:
        if _contains_any(raw, aliases):
            detected_media.append(media_type)
    if "动漫" in detected_media and "电视剧" in detected_media:
        explicit_series_aliases = ("电视剧", "美剧", "英剧", "日剧", "韩剧", "国产剧")
        if not _contains_any(raw, explicit_series_aliases):
            detected_media.remove("电视剧")
    if detected_media:
        media_types = detected_media

    genres = list(current.genres)
    genres.extend(genre for genre in GENRES if genre in raw)

    moods = list(current.moods)
    for mood, aliases in MOOD_ALIASES.items():
        if _contains_any(raw, aliases) and not any(_is_negated(raw, alias) for alias in aliases if alias in raw):
            moods.append(mood)

    countries = list(current.countries)
    countries.extend(country for country in COUNTRIES if country in raw)

    avoid = list(current.avoid)
    negated_terms: list[str] = []
    for label, aliases in AVOID_ALIASES.items():
        if any(alias in raw and _is_negated(raw, alias) for alias in aliases):
            avoid.append(label)
            negated_terms.append(label)

    session_adjustments = list(current.session_only_adjustments)
    if negated_terms and _contains_any(raw, SESSION_MARKERS):
        session_adjustments.extend(negated_terms)

    permanent_avoid = list(current.permanent_avoid)
    if negated_terms and _contains_any(raw, PERMANENT_MARKERS):
        permanent_avoid.extend(negated_terms)

    pace = current.pace
    if any(marker in raw for marker in ("快节奏", "节奏快", "紧凑")):
        pace = "fast"
    elif "慢热" in raw and "慢热" not in negated_terms:
        pace = "slow"

    complexity = current.complexity
    if any(marker in raw for marker in ("烧脑", "复杂", "结构精密")):
        complexity = "high"
    elif any(marker in raw for marker in ("不费脑", "简单易看")):
        complexity = "low"

    episode_runtime = _extract_runtime(raw, episode=True) or current.episode_runtime_max
    runtime = _extract_runtime(raw, episode=False) or current.runtime_max

    year_min = current.year_min
    year_max = current.year_max
    minimum_year_match = re.search(r"((?:19|20)\d{2})\s*年?(?:以后|之后|起)", raw)
    maximum_year_match = re.search(r"((?:19|20)\d{2})\s*年?(?:以前|之前|止)", raw)
    if minimum_year_match:
        year_min = int(minimum_year_match.group(1))
    if maximum_year_match:
        year_max = int(maximum_year_match.group(1))

    quality_floor = current.quality_floor
    quality_match = re.search(r"评分\s*(?:至少|不低于|要有)?\s*(\d(?:\.\d+)?)", raw)
    if quality_match:
        quality_floor = float(quality_match.group(1))

    exploration_level = current.exploration_level
    surprise_level = current.surprise_level
    if any(marker in raw for marker in ("给我惊喜", "意外一点", "冷门惊喜")):
        exploration_level = max(exploration_level, 0.72)
        surprise_level = max(surprise_level, 0.80)
    elif any(marker in raw for marker in ("稳妥", "别冒险", "最保险")):
        exploration_level = min(exploration_level, 0.15)
        surprise_level = min(surprise_level, 0.10)

    return RecommendationIntent(
        media_types=_ordered_unique(media_types),
        genres=_ordered_unique(genres),
        moods=_ordered_unique(moods),
        pace=pace,
        complexity=complexity,
        intensity_max=current.intensity_max,
        runtime_max=runtime,
        episode_runtime_max=episode_runtime,
        countries=_ordered_unique(countries),
        languages=current.languages,
        year_min=year_min,
        year_max=year_max,
        quality_floor=quality_floor,
        avoid=_ordered_unique(avoid),
        exploration_level=exploration_level,
        surprise_level=surprise_level,
        session_only_adjustments=_ordered_unique(session_adjustments),
        permanent_avoid=_ordered_unique(permanent_avoid),
        free_text=raw or current.free_text,
    )


def intent_to_chips(intent: RecommendationIntent) -> list[IntentChip]:
    chips: list[IntentChip] = []
    media_labels = {"电影": "电影", "电视剧": "电视剧", "动漫": "动画剧集"}
    for media_type in intent.media_types:
        chips.append(IntentChip("media_type", media_labels.get(media_type, media_type), media_type))
    chips.extend(IntentChip("genre", genre, genre) for genre in intent.genres)
    chips.extend(IntentChip("mood", mood, mood) for mood in intent.moods)
    chips.extend(IntentChip("country", country, country) for country in intent.countries)
    if intent.pace:
        chips.append(IntentChip("pace", "快节奏" if intent.pace == "fast" else "慢热", intent.pace))
    if intent.runtime_max:
        chips.append(IntentChip("runtime_max", f"片长 ≤ {intent.runtime_max} 分钟", intent.runtime_max))
    if intent.episode_runtime_max:
        chips.append(
            IntentChip(
                "episode_runtime_max",
                f"单集 ≤ {intent.episode_runtime_max} 分钟",
                intent.episode_runtime_max,
            )
        )
    if intent.year_min:
        chips.append(IntentChip("year_min", f"{intent.year_min} 年以后", intent.year_min))
    if intent.year_max:
        chips.append(IntentChip("year_max", f"{intent.year_max} 年以前", intent.year_max))
    if intent.quality_floor is not None:
        chips.append(IntentChip("quality_floor", f"评分 ≥ {intent.quality_floor:g}", intent.quality_floor))
    for value in intent.avoid:
        chips.append(IntentChip("avoid", f"避开：{value}", value))
    return chips
