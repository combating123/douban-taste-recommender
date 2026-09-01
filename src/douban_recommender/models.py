from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass, field
from typing import Any


_SAFE_EXTERNAL_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9._~-]+$")
_SAFE_ROUTE_SEGMENT_RE = re.compile(r"^[A-Za-z0-9:._~-]+$")


def is_safe_route_segment(value: object) -> bool:
    text = str(value or "")
    if not text or text != text.strip() or text in {".", ".."} or ".." in text:
        return False
    return bool(_SAFE_ROUTE_SEGMENT_RE.fullmatch(text))


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


def canonical_media_type(value: object) -> str:
    text = str(value or "").strip()
    normalized = text.casefold().replace(" ", "").replace("_", "").replace("-", "")
    aliases = {
        "movie": "电影",
        "film": "电影",
        "电影": "电影",
        "tv": "电视剧",
        "series": "电视剧",
        "tvseries": "电视剧",
        "show": "电视剧",
        "电视剧": "电视剧",
        "剧集": "电视剧",
        "anime": "动漫",
        "animation": "动漫",
        "animatedseries": "动漫",
        "动画": "动漫",
        "动漫": "动漫",
        "动画剧集": "动漫",
    }
    return aliases.get(normalized, text)


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
        self.media_type = canonical_media_type(self.media_type)
        self.genres = _clean_list(self.genres)
        self.countries = _clean_list(self.countries)
        self.languages = _clean_list(self.languages)
        self.directors = _clean_list(self.directors)
        self.casts = _clean_list(self.casts)
        self.tags = _clean_list(self.tags)
        if not self.media_type:
            self.media_type = canonical_media_type(guess_media_type(self))
        if not isinstance(self.raw, dict):
            self.raw = {}

    @property
    def identity(self) -> str:
        return recommendation_item_key(self)

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
            "item": [recommendation_item_key(self)],
            "media_type": [self.media_type] if self.media_type else [],
            "genre": self.genres,
            "country": self.countries,
            "language": self.languages,
            "director": self.directors,
            "cast": self.casts[:8],
            "tag": self.tags,
            "year_bucket": year_bucket,
        }


def recommendation_item_key(item: MediaItem | dict[str, Any]) -> str:
    if isinstance(item, dict):
        getter = item.get
    else:
        getter = lambda key, default="": getattr(item, key, default)
    identifier = str(getter("douban_id") or "").strip()
    if identifier:
        if identifier.isdigit():
            return f"douban:{identifier}"
        if _SAFE_EXTERNAL_IDENTIFIER_RE.fullmatch(identifier) and is_safe_route_segment(identifier):
            return f"external:{identifier}"
        opaque_identifier = hashlib.sha256(identifier.encode("utf-8")).hexdigest()[:24]
        return f"external:{opaque_identifier}"
    basis = "|".join(
        [
            str(getter("title") or "").strip().casefold(),
            str(getter("year") or ""),
            canonical_media_type(getter("media_type") or "").casefold(),
        ]
    )
    return "item:" + hashlib.sha256(basis.encode("utf-8")).hexdigest()[:24]


def recommendation_identity_tokens(item: MediaItem | dict[str, Any]) -> tuple[str, ...]:
    """Return stable aliases used to suppress duplicate versions of the same work.

    Provider IDs remain the strongest identity.  A normalized title/year/type alias
    bridges records where one source has a Douban ID and another source does not.
    """

    if isinstance(item, dict):
        getter = item.get
        raw = item.get("raw") if isinstance(item.get("raw"), dict) else {}
    else:
        getter = lambda key, default="": getattr(item, key, default)
        raw = item.raw if isinstance(item.raw, dict) else {}
    titles = [str(getter("title") or "").strip()]
    original_title = str(raw.get("original_title") or "").strip()
    if original_title:
        titles.append(original_title)
    for field_name in ("original_titles", "aliases"):
        values = raw.get(field_name)
        if isinstance(values, str):
            values = [values]
        if isinstance(values, (list, tuple, set)):
            titles.extend(str(value or "").strip() for value in values)
    year = str(getter("year") or "").strip()
    media_type = canonical_media_type(getter("media_type") or "").strip()
    tokens = [recommendation_item_key(item)]
    provider_ids = raw.get("provider_ids")
    if isinstance(provider_ids, dict):
        for provider, identifier in sorted(provider_ids.items(), key=lambda entry: str(entry[0])):
            normalized_provider = re.sub(r"[^a-z0-9._~-]+", "", str(provider or "").casefold())
            normalized_identifier = str(identifier or "").strip().casefold()
            if normalized_provider and normalized_identifier:
                tokens.append(f"provider:{normalized_provider}:{normalized_identifier}")
    for title in titles:
        normalized = normalize_title(title)
        if not normalized:
            continue
        if year:
            tokens.append(f"title-year-type:{normalized}|{year}|{media_type}")
        else:
            tokens.append(f"title-type:{normalized}|{media_type}")
    return tuple(dict.fromkeys(token for token in tokens if token))


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
