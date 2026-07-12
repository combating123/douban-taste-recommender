from __future__ import annotations

from dataclasses import dataclass

from .models import MediaItem
from .profiler import TasteProfile


@dataclass(frozen=True)
class CandidateQuery:
    channel: str
    tags: str
    sort: str = "U"
    start: int = 0
    limit: int = 20
    media_type: str = "电影"


def _manual_terms(profile: TasteProfile) -> list[str]:
    terms: list[str] = []
    for term in list(profile.manual_likes) + ["剧情", "高分", "口碑佳"]:
        text = str(term or "").strip()
        if text and text not in terms:
            terms.append(text)
    return terms[:6]


def _add_offsets(
    out: list[CandidateQuery],
    channel: str,
    tags_list: list[str],
    media_type: str,
    starts: list[int],
) -> None:
    for tags in tags_list:
        for sort in ("U", "R"):
            for start in starts:
                out.append(CandidateQuery(
                    channel=channel,
                    tags=tags,
                    sort=sort,
                    start=start,
                    media_type=media_type,
                ))


def build_candidate_plan(
    profile: TasteProfile,
    include_movies: bool = True,
    include_series: bool = True,
    include_anime: bool = True,
    depth: str = "deep",
    wishlist: list[MediaItem] | None = None,
) -> list[CandidateQuery]:
    starts = [0, 20, 40] if depth == "deep" else [0]
    terms = _manual_terms(profile)
    out: list[CandidateQuery] = []

    if include_movies:
        movie_tags = ["电影", "电影,热门", "电影,剧情", "电影,高分", "电影,悬疑", "电影,犯罪"]
        movie_tags.extend(f"电影,{term}" for term in terms[:3])
        _add_offsets(out, "movie_quality", movie_tags, "电影", starts)

    if include_series:
        series_tags = ["电视剧", "电视剧,热门", "电视剧,剧情", "电视剧,悬疑", "电视剧,犯罪", "电视剧,高分"]
        _add_offsets(out, "series_quality", series_tags, "电视剧", starts)

    if include_anime:
        anime_tags = ["动画", "动漫", "动画,热门", "日本动画", "电视剧,动画", "电视剧,动画,热门"]
        _add_offsets(out, "anime_quality", anime_tags, "动漫", starts)

    for item in wishlist or []:
        for tag in (item.genres + item.tags + [item.media_type])[:4]:
            if tag and tag not in {"想看", "看过"}:
                out.append(CandidateQuery(
                    channel="wishlist_boost",
                    tags=f"{item.media_type or '电影'},{tag}",
                    media_type=item.media_type or "电影",
                ))

    seen: set[tuple[str, str, str, int]] = set()
    deduped: list[CandidateQuery] = []
    for query in out:
        key = (query.channel, query.tags, query.sort, query.start)
        if key not in seen:
            deduped.append(query)
            seen.add(key)
    return deduped
