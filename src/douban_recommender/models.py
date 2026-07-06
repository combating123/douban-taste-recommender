from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


def _clean_list(values: list[str] | None) -> list[str]:
    if not values:
        return []
    out: list[str] = []
    seen: set[str] = set()
    for value in values:
        text = str(value).strip()
        if not text:
            continue
        if text not in seen:
            out.append(text)
            seen.add(text)
    return out


@dataclass
class MediaItem:
    title: str
    my_rating: float | None = None
    douban_rating: float | None = None
    vote_count: int | None = None
    year: int | None = None
    media_type: str = ""
    genres: list[str] = field(default_factory=list)
    countries: list[str] = field(default_factory=list)
    languages: list[str] = field(default_factory=list)
    directors: list[str] = field(default_factory=list)
    casts: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    url: str = ""
    douban_id: str = ""
    cover: str = ""
    summary: str = ""
    source: str = ""
    raw: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        self.title = str(self.title or "").strip()
        self.media_type = str(self.media_type or "").strip()
        self.genres = _clean_list(self.genres)
        self.countries = _clean_list(self.countries)
        self.languages = _clean_list(self.languages)
        self.directors = _clean_list(self.directors)
        self.casts = _clean_list(self.casts)
        self.tags = _clean_list(self.tags)
        if not self.media_type:
            self.media_type = guess_media_type(self)

    @property
    def identity(self) -> str:
        if self.douban_id:
            return f"douban:{self.douban_id}"
        return normalize_title(self.title)

    def search_blob(self) -> str:
        parts: list[str] = [
            self.title,
            self.media_type,
            self.summary,
            " ".join(self.genres),
            " ".join(self.countries),
            " ".join(self.languages),
            " ".join(self.directors),
            " ".join(self.casts),
            " ".join(self.tags),
            self.url,
        ]
        return " ".join(part for part in parts if part).lower()

    def feature_values(self) -> dict[str, list[str]]:
        year_bucket = []
        if self.year:
            year_bucket = [f"{self.year // 10 * 10}s"]
        return {
            "media_type": [self.media_type] if self.media_type else [],
            "genre": self.genres,
            "country": self.countries,
            "language": self.languages,
            "director": self.directors,
            "cast": self.casts[:8],
            "tag": self.tags,
            "year_bucket": year_bucket,
        }


def normalize_title(title: str) -> str:
    text = str(title or "").lower().strip()
    for ch in " 　\t\r\n:：-—_·.,，。!！?？《》<>[]【】()（）/\\|\"":
        text = text.replace(ch, "")
    suffixes = ["第一季", "第二季", "第三季", "第四季", "第五季", "第六季", "第七季", "第八季", "第九季", "第十季"]
    for suffix in suffixes:
        if text.endswith(suffix):
            return text[: -len(suffix)]
    return text


def guess_media_type(item: MediaItem) -> str:
    blob = " ".join([item.title, " ".join(item.tags), " ".join(item.genres), item.summary])
    if any(marker in blob for marker in ["美剧", "英剧", "日剧", "韩剧", "国产剧", "港剧", "台剧", "电视剧", "剧集"]):
        return "电视剧"
    if "第" in item.title and "季" in item.title:
        return "电视剧"
    if any(marker in blob for marker in ["电影", "影片", "短片", "纪录片"]):
        return "电影"
    if any(marker in blob.lower() for marker in ["episode", "season", "series"]):
        return "电视剧"
    return "电影"
