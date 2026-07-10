from __future__ import annotations

from dataclasses import dataclass, field
from math import log10

from .models import MediaItem, normalize_title
from .profiler import TasteProfile


@dataclass
class Recommendation:
    item: MediaItem
    score: float
    reasons: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    matched_positive: list[str] = field(default_factory=list)
    matched_negative: list[str] = field(default_factory=list)
    section: str = ""
    badges: list[str] = field(default_factory=list)
    quality_label: str = ""
    short_reason: str = ""
    risk_label: str = ""
    is_wishlist: bool = False
    score_breakdown: dict[str, object] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        item = self.item
        return {
            "title": item.title,
            "year": item.year,
            "media_type": item.media_type,
            "douban_rating": item.douban_rating,
            "vote_count": item.vote_count,
            "score": round(self.score, 2),
            "genres": item.genres,
            "countries": item.countries,
            "directors": item.directors,
            "casts": item.casts,
            "tags": item.tags,
            "url": item.url,
            "douban_id": item.douban_id,
            "cover": item.cover,
            "summary": item.summary,
            "source": item.source,
            "people_photos": item.raw.get("people_photos", {}) if isinstance(item.raw, dict) else {},
            "reasons": self.reasons,
            "warnings": self.warnings,
            "matched_positive": self.matched_positive,
            "matched_negative": self.matched_negative,
            "section": self.section,
            "badges": self.badges,
            "quality_label": self.quality_label,
            "short_reason": self.short_reason,
            "risk_label": self.risk_label,
            "is_wishlist": self.is_wishlist,
            "score_breakdown": self.score_breakdown,
        }


def recommend(
    rated_items: list[MediaItem],
    candidates: list[MediaItem],
    profile: TasteProfile,
    limit: int = 30,
    include_movies: bool = True,
    include_series: bool = True,
    include_anime: bool = True,
) -> list[Recommendation]:
    watched_items = [
        item for item in rated_items
        if "看过" in set(item.tags or []) or item.source.endswith(":collect") or item.my_rating is not None
    ]
    wish_items = [
        item for item in rated_items
        if "想看" in set(item.tags or []) or item.source.endswith(":wish")
    ]
    seen_titles = {normalize_title(item.title) for item in watched_items if item.title}
    seen_ids = {item.douban_id for item in watched_items if item.douban_id}
    wish_ids = {item.douban_id for item in wish_items if item.douban_id}
    wish_titles = {normalize_title(item.title) for item in wish_items if item.title}

    deduped: dict[str, MediaItem] = {}
    for item in candidates:
        if not item.title:
            continue
        if item.douban_id and item.douban_id in seen_ids:
            continue
        if normalize_title(item.title) in seen_titles:
            continue
        if item.media_type == "电影" and not include_movies:
            continue
        if item.media_type == "电视剧" and not include_series:
            continue
        if item.media_type == "动漫" and not include_anime:
            continue
        key = item.douban_id or normalize_title(item.title)
        existing = deduped.get(key)
        if existing is None or item_quality(item) > item_quality(existing):
            deduped[key] = item

    recs = []
    for item in deduped.values():
        rec = score_item(item, profile)
        if (item.douban_id and item.douban_id in wish_ids) or normalize_title(item.title) in wish_titles:
            rec.is_wishlist = True
            rec.badges.append("想看")
            rec.score += 2.5
            if rec.section not in {"必看 Top Picks", "想看优先"}:
                rec.section = "想看优先"
        rec.badges = unique_keep_order(rec.badges)
        recs.append(rec)
    recs.sort(key=lambda r: r.score, reverse=True)
    return diversify_recommendations(recs, limit)


def diversify_recommendations(recs: list[Recommendation], limit: int) -> list[Recommendation]:
    """Quality-preserving diversity rerank.

    `score_item()` still owns the taste/quality score. This pass only changes
    presentation order so a long list does not become one-country / one-format
    monotony, especially in anime where high-score Japanese entries can crowd
    out global animated series.
    """
    if limit <= 0 or not recs:
        return []
    remaining = list(recs)
    selected: list[Recommendation] = []

    def first(values: list[str]) -> str:
        return values[0] if values else ""

    while remaining and len(selected) < limit:
        country_counts: dict[str, int] = {}
        media_counts: dict[str, int] = {}
        director_counts: dict[str, int] = {}
        genre_counts: dict[str, int] = {}
        anime_countries: dict[str, int] = {}
        for rec in selected:
            media_type = rec.item.media_type or ""
            country = first(rec.item.countries)
            media_counts[media_type] = media_counts.get(media_type, 0) + 1
            if country:
                country_counts[country] = country_counts.get(country, 0) + 1
                if media_type == "动漫":
                    anime_countries[country] = anime_countries.get(country, 0) + 1
            for director in (rec.item.directors or [])[:2]:
                director_counts[director] = director_counts.get(director, 0) + 1
            for genre in (rec.item.genres or [])[:3]:
                genre_counts[genre] = genre_counts.get(genre, 0) + 1

        def effective(rec: Recommendation) -> float:
            item = rec.item
            media_type = item.media_type or ""
            country = first(item.countries)
            value = rec.score
            value -= media_counts.get(media_type, 0) * 0.22
            if country:
                value -= country_counts.get(country, 0) * 1.25
            for director in (item.directors or [])[:2]:
                value -= director_counts.get(director, 0) * 1.1
            for genre in (item.genres or [])[:3]:
                value -= genre_counts.get(genre, 0) * 0.16
            if media_type == "动漫":
                japanese_count = anime_countries.get("日本", 0)
                if country == "日本" and japanese_count >= 2:
                    value -= 4.8 + (japanese_count - 2) * 1.4
                if country in {"中国大陆", "中国", "美国", "英国", "法国", "加拿大"} and country not in anime_countries:
                    value += 4.4 if japanese_count >= 2 else 1.6
                if country in {"中国大陆", "中国"}:
                    value += 0.45
                elif country == "美国":
                    value += 0.35
            return value

        best = max(remaining, key=lambda rec: (effective(rec), rec.score))
        selected.append(best)
        remaining.remove(best)

    return selected

PLACEHOLDER_PERSON_HINTS = (
    "专家",
    "担当",
    "核心",
    "剧集统筹",
    "动画监督",
    "声优A",
    "声优B",
)


def _item_people_photos(item: MediaItem) -> dict[str, str]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    photos = raw.get("people_photos")
    return photos if isinstance(photos, dict) else {}


def _has_placeholder_people(item: MediaItem) -> bool:
    people = [*(item.directors or []), *(item.casts or [])]
    return any(any(hint in str(name) for hint in PLACEHOLDER_PERSON_HINTS) for name in people)


def _is_designed_cover(item: MediaItem) -> bool:
    return str(item.cover or "").startswith("data:image/svg+xml")


def _has_external_cover(item: MediaItem) -> bool:
    return str(item.cover or "").startswith("https://")


def metadata_quality_adjustment(item: MediaItem) -> tuple[float, list[str], list[str]]:
    score_delta = 0.0
    reasons: list[str] = []
    warnings: list[str] = []
    photo_count = len(_item_people_photos(item))
    if photo_count >= 2:
        score_delta += 2.4
        reasons.append("资料完整")
    elif photo_count == 1:
        score_delta += 0.8
    if _has_external_cover(item):
        score_delta += 0.8
    if _has_placeholder_people(item):
        score_delta -= 4.0
        warnings.append("演职员资料待绑定，已降低展示优先级")
    if _is_designed_cover(item):
        score_delta -= 1.0
        warnings.append("海报仍为设计封面，等待真实图源")
    return score_delta, reasons, warnings


def score_item(item: MediaItem, profile: TasteProfile) -> Recommendation:
    score = 50.0
    reasons: list[str] = []
    warnings: list[str] = []
    pos_hits: list[tuple[str, float, str]] = []
    neg_hits: list[tuple[str, float, str]] = []

    for field, values in item.feature_values().items():
        for value in values:
            key = f"{field}:{value.lower()}"
            pos = float(profile.positive.get(key, 0.0))
            neg = float(profile.negative.get(key, 0.0))
            if pos:
                delta = pos * 1.15
                score += delta
                pos_hits.append((pretty_feature(field, value), delta, key))
            if neg:
                # 国家/媒介形式这类宽泛特征很容易因为一两部低分片被误伤：
                # 例如既喜欢国产现实主义剧，又讨厌国产甜宠剧。这里降低宽泛负向特征权重，
                # 并且当正向证据更强时，只做很轻的扣分，不生成强避雷。
                factor = 1.45
                if field in {"media_type", "country", "language", "year_bucket"}:
                    factor = 0.45
                if pos >= neg:
                    factor *= 0.35
                delta = neg * factor
                score -= delta
                if neg > pos * 1.15 or field not in {"media_type", "country", "language", "year_bucket"}:
                    neg_hits.append((pretty_feature(field, value), delta, key))

    blob = item.search_blob()
    for term in profile.manual_likes:
        if term and term.lower() in blob:
            delta = 4.0 if len(term) >= 2 else 1.5
            score += delta
            pos_hits.append((f"关键词：{term}", delta, f"keyword:{term}"))
    for term in profile.manual_dislikes:
        if term and term.lower() in blob:
            delta = 6.0 if len(term) >= 2 else 2.0
            score -= delta
            neg_hits.append((f"避雷关键词：{term}", delta, f"keyword:{term}"))

    quality_terms = ["剧情", "叙事", "人物", "口碑", "高分"]
    if item.douban_rating and item.douban_rating >= 8.5:
        score += 6.0
    if any(term in blob for term in quality_terms):
        score += 4.0
    costume_terms = ["古装", "武侠", "仙侠", "宫廷", "历史", "朝代", "权谋"]
    if item.media_type == "电视剧" and any(term in blob for term in costume_terms):
        score -= 18.0
        warnings.append("电视剧古装 / 宫廷 / 历史向内容，与你的避雷设置冲突")

    if item.douban_rating is not None:
        quality = (float(item.douban_rating) - 7.0) * 3.2
        score += quality
        if item.douban_rating >= 8.5:
            reasons.append(f"豆瓣评分 {item.douban_rating:g}，口碑很稳")
        elif item.douban_rating >= 8.0:
            reasons.append(f"豆瓣评分 {item.douban_rating:g}，整体评价较高")
        elif item.douban_rating < 6.5:
            warnings.append(f"豆瓣评分 {item.douban_rating:g} 偏低，建议谨慎")
    if item.vote_count:
        score += min(4.0, log10(max(item.vote_count, 1)) * 0.8)
    if "douban_explore" in item.source:
        score += 1.2
        reasons.append("来自豆瓣探索候选池，已利用豆瓣平台的候选排序")
    if "douban_top250" in item.source:
        score += 2.0
        reasons.append("来自豆瓣 Top250 候选池")

    metadata_delta, metadata_reasons, metadata_warnings = metadata_quality_adjustment(item)
    score += metadata_delta
    reasons.extend(metadata_reasons)
    warnings.extend(metadata_warnings)

    pos_hits.sort(key=lambda x: x[1], reverse=True)
    neg_hits.sort(key=lambda x: x[1], reverse=True)

    for label, _, key in pos_hits[:5]:
        examples = profile.positive_examples.get(key, [])
        if examples:
            reasons.append(f"匹配你的高分偏好：{label}（来自 {', '.join(examples[:2])}）")
        else:
            reasons.append(f"匹配你的偏好：{label}")
    for label, _, key in neg_hits[:4]:
        examples = profile.negative_examples.get(key, [])
        if examples:
            warnings.append(f"可能踩雷：{label}（你低分/避雷里出现过 {', '.join(examples[:2])}）")
        else:
            warnings.append(f"可能踩雷：{label}")

    if not reasons:
        reasons.append("与你的已评分条目没有强冲突，可作为探索项")
    if len(neg_hits) >= 3:
        score -= 4.0
        warnings.append("负向匹配较多，放在低优先级尝试")

    section = "高分剧情"
    if item.media_type == "动漫":
        section = "动漫"
    elif item.media_type == "电视剧":
        section = "电视剧"
    elif item.douban_rating and item.douban_rating >= 8.7:
        section = "必看 Top Picks"
    quality_label = "高分佳作" if item.douban_rating and item.douban_rating >= 8.5 else "潜力推荐"
    short_reason = reasons[0] if reasons else "质量优先策略推荐"
    risk_label = warnings[0] if warnings else ""
    badges = [item.media_type] if item.media_type else []

    return Recommendation(
        item=item,
        score=score,
        reasons=unique_keep_order(reasons),
        warnings=unique_keep_order(warnings),
        matched_positive=[x[0] for x in pos_hits[:8]],
        matched_negative=[x[0] for x in neg_hits[:8]],
        section=section,
        badges=badges,
        quality_label=quality_label,
        short_reason=short_reason,
        risk_label=risk_label,
    )


def item_quality(item: MediaItem) -> float:
    value = 0.0
    if item.douban_rating:
        value += float(item.douban_rating)
    if item.vote_count:
        value += min(2.0, log10(max(item.vote_count, 1)) / 3)
    if item.source:
        value += 0.2
    return value


def pretty_feature(field: str, value: str) -> str:
    names = {
        "genre": "类型",
        "tag": "标签",
        "director": "导演",
        "cast": "演员",
        "country": "地区",
        "language": "语言",
        "media_type": "形式",
        "year_bucket": "年代",
    }
    return f"{names.get(field, field)}：{value}"


def unique_keep_order(values: list[str]) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        if value not in seen:
            out.append(value)
            seen.add(value)
    return out
