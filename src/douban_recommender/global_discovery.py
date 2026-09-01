from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Callable, Mapping

from .intent_parser import RecommendationIntent
from .models import MediaItem, canonical_media_type, normalize_title
from .profiler import TasteProfile
from .douban_sources import build_url_opener, configured_proxy_url
from .localization import localize_anime_title, localize_genre, to_simplified_chinese


TMDB_API_ROOT = "https://api.themoviedb.org/3"
TMDB_IMAGE_W500 = "https://image.tmdb.org/t/p/w500"
TMDB_IMAGE_W1280 = "https://image.tmdb.org/t/p/w1280"
OMDB_ENDPOINT = "https://www.omdbapi.com/"
TVMAZE_SEARCH_ENDPOINT = "https://api.tvmaze.com/search/shows"
TVMAZE_SCHEDULE_ENDPOINT = "https://api.tvmaze.com/schedule/web"
ANILIST_GRAPHQL_ENDPOINT = "https://graphql.anilist.co"
JIKAN_TOP_ENDPOINT = "https://api.jikan.moe/v4/top/anime"
JIKAN_SEASON_ENDPOINT = "https://api.jikan.moe/v4/seasons/now"
APPLE_TOP_MOVIES_ENDPOINT = "https://itunes.apple.com/{storefront}/rss/topmovies/limit={limit}/json"


TMDB_GENRES = {
    12: "冒险",
    14: "奇幻",
    16: "动画",
    18: "剧情",
    27: "恐怖",
    28: "动作",
    35: "喜剧",
    36: "历史",
    37: "西部",
    53: "惊悚",
    80: "犯罪",
    99: "纪录片",
    878: "科幻",
    9648: "悬疑",
    10402: "音乐",
    10749: "爱情",
    10751: "家庭",
    10752: "战争",
    10759: "动作",
    10762: "儿童",
    10763: "新闻",
    10764: "真人秀",
    10765: "科幻",
    10766: "肥皂剧",
    10767: "脱口秀",
    10768: "战争",
}

GENRE_SEARCH_TERMS = {
    "剧情": "drama",
    "犯罪": "crime",
    "科幻": "science fiction",
    "悬疑": "mystery",
    "惊悚": "thriller",
    "喜剧": "comedy",
    "爱情": "romance",
    "动作": "action",
    "奇幻": "fantasy",
    "冒险": "adventure",
    "纪录片": "documentary",
    "动画": "animation",
}

COUNTRY_CODES = {
    "CN": "中国大陆",
    "HK": "中国香港",
    "TW": "中国台湾",
    "US": "美国",
    "GB": "英国",
    "JP": "日本",
    "KR": "韩国",
    "FR": "法国",
    "DE": "德国",
    "CA": "加拿大",
    "IN": "印度",
    "ES": "西班牙",
    "IT": "意大利",
    "AU": "澳大利亚",
}

LANGUAGE_CODES = {
    "zh": "中文",
    "en": "英语",
    "ja": "日语",
    "ko": "韩语",
    "fr": "法语",
    "de": "德语",
    "es": "西班牙语",
    "it": "意大利语",
}

_TAG_RE = re.compile(r"<[^>]+>")
_SPACE_RE = re.compile(r"\s+")
_SAFE_ERROR_RE = re.compile(
    r"(?i)(?:api[_-]?key|apikey|authorization|token|secret|password)\s*[:=]\s*[^\s,;&]+"
)


def _bool(value: object, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, (int, float)):
        return bool(value)
    text = str(value).strip().casefold()
    if text in {"1", "true", "yes", "on", "enabled"}:
        return True
    if text in {"0", "false", "no", "off", "disabled"}:
        return False
    return default


def _int(value: object, default: int, minimum: int, maximum: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


def _float(value: object, default: float, minimum: float, maximum: float) -> float:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        parsed = default
    return max(minimum, min(maximum, parsed))


@dataclass(frozen=True)
class GlobalDiscoveryConfig:
    enabled: bool = True
    tmdb_api_key: str = ""
    omdb_api_key: str = ""
    enable_tmdb: bool = True
    enable_omdb: bool = True
    enable_tvmaze: bool = True
    enable_anilist: bool = True
    enable_jikan: bool = True
    enable_apple_movies: bool = True
    apple_storefront: str = "tw"
    include_current: bool = True
    max_per_source: int = 24
    max_total: int = 180
    timeout_seconds: float = 8.0
    language: str = "zh-CN"
    region: str = "CN"

    @classmethod
    def from_payload(
        cls,
        payload: Mapping[str, object] | None,
        env: Mapping[str, str] | None = None,
    ) -> "GlobalDiscoveryConfig":
        values = dict(payload or {})
        environment = os.environ if env is None else env
        return cls(
            enabled=_bool(values.get("enabled"), True),
            tmdb_api_key=str(
                values.get("tmdb_api_key")
                or values.get("tmdbApiKey")
                or environment.get("CINESCOPE_TMDB_API_KEY")
                or ""
            ).strip(),
            omdb_api_key=str(
                values.get("omdb_api_key")
                or values.get("omdbApiKey")
                or environment.get("CINESCOPE_OMDB_API_KEY")
                or ""
            ).strip(),
            enable_tmdb=_bool(values.get("enable_tmdb", values.get("enableTmdb")), True),
            enable_omdb=_bool(values.get("enable_omdb", values.get("enableOmdb")), True),
            enable_tvmaze=_bool(values.get("enable_tvmaze", values.get("enableTvmaze")), True),
            enable_anilist=_bool(values.get("enable_anilist", values.get("enableAnilist")), True),
            enable_jikan=_bool(values.get("enable_jikan", values.get("enableJikan")), True),
            enable_apple_movies=_bool(values.get("enable_apple_movies", values.get("enableAppleMovies")), True),
            apple_storefront=(
                re.sub(
                    r"[^a-z]",
                    "",
                    str(
                        values.get("apple_storefront")
                        or values.get("appleStorefront")
                        or environment.get("CINESCOPE_APPLE_STOREFRONT")
                        or "tw"
                    ).strip().casefold(),
                )[:2]
                or "tw"
            ),
            include_current=_bool(values.get("include_current", values.get("includeCurrent")), True),
            max_per_source=_int(values.get("max_per_source", values.get("maxPerSource")), 24, 4, 80),
            max_total=_int(values.get("max_total", values.get("maxTotal")), 180, 12, 500),
            timeout_seconds=_float(values.get("timeout_seconds", values.get("timeoutSeconds")), 8.0, 2.0, 25.0),
            language=str(values.get("language") or "zh-CN").strip()[:16] or "zh-CN",
            region=str(values.get("region") or "CN").strip().upper()[:4] or "CN",
        )

    def public_summary(self) -> dict[str, object]:
        return {
            "enabled": self.enabled,
            "tmdb_configured": bool(self.tmdb_api_key),
            "omdb_configured": bool(self.omdb_api_key),
            "enable_tmdb": self.enable_tmdb,
            "enable_omdb": self.enable_omdb,
            "enable_tvmaze": self.enable_tvmaze,
            "enable_anilist": self.enable_anilist,
            "enable_jikan": self.enable_jikan,
            "enable_apple_movies": self.enable_apple_movies,
            "apple_storefront": self.apple_storefront,
            "include_current": self.include_current,
            "max_per_source": self.max_per_source,
            "max_total": self.max_total,
            "timeout_seconds": self.timeout_seconds,
            "language": self.language,
            "region": self.region,
        }


@dataclass
class GlobalDiscoveryReport:
    items: list[MediaItem] = field(default_factory=list)
    source_counts: dict[str, int] = field(default_factory=dict)
    source_status: dict[str, dict[str, object]] = field(default_factory=dict)
    query_keywords: tuple[str, ...] = ()
    config: dict[str, object] = field(default_factory=dict)
    status: str = "complete"
    generated_at: float = field(default_factory=time.time)

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "candidate_count": len(self.items),
            "source_counts": dict(self.source_counts),
            "source_status": {
                source: dict(value)
                for source, value in self.source_status.items()
            },
            "query_keywords": list(self.query_keywords),
            "config": dict(self.config),
            "generated_at": self.generated_at,
        }


Transport = Callable[[urllib.request.Request, float], bytes]


def _configured_proxy() -> str:
    return configured_proxy_url()


def _default_transport(request: urllib.request.Request, timeout: float = 8.0) -> bytes:
    opener = build_url_opener()
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def _request_json(
    url: str,
    transport: Transport,
    timeout: float,
    *,
    data: bytes | None = None,
    headers: Mapping[str, str] | None = None,
) -> object:
    request_headers = {
        "Accept": "application/json",
        "User-Agent": "CineScopeLocal/2.0",
    }
    request_headers.update(dict(headers or {}))
    request = urllib.request.Request(
        url,
        data=data,
        headers=request_headers,
        method="POST" if data is not None else "GET",
    )
    payload = transport(request, timeout)
    if isinstance(payload, bytes):
        text = payload.decode("utf-8", errors="replace")
    else:
        text = str(payload or "")
    return json.loads(text)


def _clean_html(value: object) -> str:
    text = html.unescape(_TAG_RE.sub(" ", str(value or "")))
    return to_simplified_chinese(_SPACE_RE.sub(" ", text).strip())


def _number(value: object) -> float | None:
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _year(value: object) -> int | None:
    match = re.search(r"\b(19\d{2}|20\d{2})\b", str(value or ""))
    return int(match.group(1)) if match else None


def _dedupe_strings(values) -> list[str]:
    out: list[str] = []
    seen: set[str] = set()
    for value in values or ():
        text = str(value or "").strip()
        if not text or text in seen:
            continue
        out.append(text)
        seen.add(text)
    return out


def _genre(value: object) -> str:
    return localize_genre(value)


def _country(value: object) -> str:
    text = str(value or "").strip()
    return to_simplified_chinese(COUNTRY_CODES.get(text.upper(), text))


def _language(value: object) -> str:
    text = str(value or "").strip()
    return to_simplified_chinese(LANGUAGE_CODES.get(text.casefold(), text))


def _image(base: str, path: object) -> str:
    text = str(path or "").strip()
    if not text or text == "None":
        return ""
    if text.startswith(("http://", "https://")):
        return text
    return base + (text if text.startswith("/") else "/" + text)


def _ratings(provider: str, value: object) -> dict[str, float]:
    rating = _number(value)
    return {provider: round(rating, 2)} if rating is not None and rating > 0 else {}


def _provider_raw(
    row: Mapping[str, object],
    *,
    provider: str,
    provider_id: str,
    rating: object = None,
    backdrop: str = "",
    aliases: list[str] | None = None,
    now: float,
    extra: Mapping[str, object] | None = None,
) -> dict[str, object]:
    raw = dict(row)
    raw.update({
        "provider_ids": {provider: provider_id} if provider_id else {},
        "ratings": _ratings(provider, rating),
        "discovery_sources": [provider],
        "discovered_at": now,
        "aliases": _dedupe_strings(aliases or []),
    })
    if backdrop:
        raw["backdrop"] = backdrop
    raw.update(dict(extra or {}))
    return raw


def _tmdb_genre_ids(intent: RecommendationIntent) -> list[int]:
    inverse = {value: key for key, value in TMDB_GENRES.items()}
    return _dedupe_numbers(inverse.get(genre) for genre in intent.genres)


def _dedupe_numbers(values) -> list[int]:
    out: list[int] = []
    for value in values:
        if isinstance(value, int) and value not in out:
            out.append(value)
    return out


def _tmdb_items(
    payload: object,
    *,
    kind: str,
    source: str,
    include_series: bool,
    include_anime: bool,
    now: float,
) -> list[MediaItem]:
    rows = payload.get("results") if isinstance(payload, dict) else []
    out: list[MediaItem] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict):
            continue
        title = to_simplified_chinese(str(row.get("title") or row.get("name") or "").strip())
        if not title:
            continue
        genre_ids = [value for value in row.get("genre_ids", []) if isinstance(value, int)]
        genres = _dedupe_strings(TMDB_GENRES.get(value, "") for value in genre_ids)
        is_animation = kind == "tv" and 16 in genre_ids
        media_type = "电影" if kind == "movie" else "动漫" if is_animation else "电视剧"
        if media_type == "电视剧" and not include_series:
            continue
        if media_type == "动漫" and not include_anime:
            continue
        provider_id = str(row.get("id") or "").strip()
        cover = _image(TMDB_IMAGE_W500, row.get("poster_path"))
        if not cover:
            continue
        backdrop = _image(TMDB_IMAGE_W1280, row.get("backdrop_path"))
        original = str(row.get("original_title") or row.get("original_name") or "").strip()
        countries = [_country(value) for value in row.get("origin_country", [])]
        raw = _provider_raw(
            row,
            provider="tmdb",
            provider_id=provider_id,
            rating=row.get("vote_average"),
            backdrop=backdrop,
            aliases=[original],
            now=now,
            extra={
                "discovery_channel": source,
                "popularity": row.get("popularity"),
                "rating_votes": {"tmdb": int(row.get("vote_count") or 0)},
            },
        )
        out.append(MediaItem(
            title=title,
            media_type=media_type,
            year=_year(row.get("release_date") or row.get("first_air_date")),
            genres=genres,
            countries=_dedupe_strings(countries),
            languages=_dedupe_strings([_language(row.get("original_language"))]),
            url=f"https://www.themoviedb.org/{kind}/{provider_id}" if provider_id else "",
            douban_id=f"tmdb-{kind}-{provider_id}" if provider_id else "",
            cover=cover,
            summary=str(row.get("overview") or "").strip(),
            source=f"global:{source}",
            vote_count=int(row.get("vote_count") or 0) or None,
            raw=raw,
        ))
    return out


def _discover_tmdb(
    intent: RecommendationIntent,
    config: GlobalDiscoveryConfig,
    transport: Transport,
    *,
    include_movies: bool,
    include_series: bool,
    include_anime: bool,
    now: float,
) -> list[MediaItem]:
    if not config.tmdb_api_key:
        return []
    kinds: list[str] = []
    if include_movies:
        kinds.append("movie")
    if include_series or include_anime:
        kinds.append("tv")
    genre_ids = _tmdb_genre_ids(intent)
    out: list[MediaItem] = []
    for kind in kinds:
        base_params = {
            "api_key": config.tmdb_api_key,
            "language": config.language,
            "region": config.region,
            "include_adult": "false",
            "page": "1",
        }
        trending_url = f"{TMDB_API_ROOT}/trending/{kind}/week?" + urllib.parse.urlencode(base_params)
        trending = _request_json(trending_url, transport, config.timeout_seconds)
        out.extend(_tmdb_items(
            trending,
            kind=kind,
            source=f"tmdb_trending_{kind}",
            include_series=include_series,
            include_anime=include_anime,
            now=now,
        ))
        discover_params = dict(base_params)
        discover_params.update({
            "sort_by": "vote_average.desc",
            "vote_count.gte": "300",
            "with_genres": ",".join(str(value) for value in genre_ids),
        })
        discover_url = f"{TMDB_API_ROOT}/discover/{kind}?" + urllib.parse.urlencode(discover_params)
        discovered = _request_json(discover_url, transport, config.timeout_seconds)
        out.extend(_tmdb_items(
            discovered,
            kind=kind,
            source=f"tmdb_quality_{kind}",
            include_series=include_series,
            include_anime=include_anime,
            now=now,
        ))
    return out[: config.max_per_source]


def _split_csv(value: object) -> list[str]:
    return _dedupe_strings(part.strip() for part in str(value or "").split(",") if part.strip() and part.strip() != "N/A")


def _digits(value: object) -> int | None:
    match = re.search(r"\d+", str(value or "").replace(",", ""))
    return int(match.group(0)) if match else None


def _omdb_item(
    row: Mapping[str, object],
    *,
    include_movies: bool,
    include_series: bool,
    include_anime: bool,
    now: float,
) -> MediaItem | None:
    if str(row.get("Response") or "True").casefold() == "false":
        return None
    title = to_simplified_chinese(str(row.get("Title") or "").strip())
    provider_id = str(row.get("imdbID") or "").strip()
    kind = str(row.get("Type") or "").strip().casefold()
    genres = _dedupe_strings(_genre(value) for value in _split_csv(row.get("Genre")))
    is_animation = "动画" in genres
    if kind == "movie":
        if not include_movies:
            return None
        media_type = "电影"
    elif is_animation:
        if not include_anime:
            return None
        media_type = "动漫"
    else:
        if not include_series:
            return None
        media_type = "电视剧"
    cover = str(row.get("Poster") or "").strip()
    if not title or not provider_id or not cover.startswith(("http://", "https://")):
        return None
    rating = _number(row.get("imdbRating"))
    votes = _digits(row.get("imdbVotes"))
    runtime = _digits(row.get("Runtime"))
    raw = _provider_raw(
        row,
        provider="imdb",
        provider_id=provider_id,
        rating=rating,
        aliases=[],
        now=now,
        extra={
            "format": "MOVIE" if kind == "movie" else "SERIES",
            "rating_votes": {"imdb": votes or 0},
            **({"runtime": runtime} if runtime and kind == "movie" else {}),
            **({"episode_runtime": runtime} if runtime and kind != "movie" else {}),
            **({"seasons": _digits(row.get("totalSeasons"))} if _digits(row.get("totalSeasons")) else {}),
        },
    )
    return MediaItem(
        title=title,
        media_type=media_type,
        year=_year(row.get("Year")),
        genres=genres,
        countries=_split_csv(row.get("Country")),
        languages=_split_csv(row.get("Language")),
        directors=_split_csv(row.get("Director")),
        casts=_split_csv(row.get("Actors")),
        url=f"https://www.imdb.com/title/{provider_id}/",
        douban_id=f"imdb-{provider_id}",
        cover=cover,
        summary=str(row.get("Plot") or "").strip() if str(row.get("Plot") or "").strip() != "N/A" else "",
        source="global:omdb",
        vote_count=votes,
        raw=raw,
    )


def _discover_omdb(
    keywords: tuple[str, ...],
    config: GlobalDiscoveryConfig,
    transport: Transport,
    *,
    include_movies: bool,
    include_series: bool,
    include_anime: bool,
    now: float,
) -> list[MediaItem]:
    if not config.omdb_api_key:
        return []
    search_types = []
    if include_movies:
        search_types.append("movie")
    if include_series or include_anime:
        search_types.append("series")
    identifiers: list[str] = []
    for keyword in keywords[:3]:
        for kind in search_types:
            url = OMDB_ENDPOINT + "?" + urllib.parse.urlencode({
                "apikey": config.omdb_api_key,
                "s": keyword,
                "type": kind,
                "page": "1",
            })
            payload = _request_json(url, transport, config.timeout_seconds)
            rows = payload.get("Search") if isinstance(payload, dict) else []
            for row in rows if isinstance(rows, list) else []:
                if not isinstance(row, dict):
                    continue
                identifier = str(row.get("imdbID") or "").strip()
                if identifier and identifier not in identifiers:
                    identifiers.append(identifier)
                if len(identifiers) >= config.max_per_source:
                    break
            if len(identifiers) >= config.max_per_source:
                break
        if len(identifiers) >= config.max_per_source:
            break

    out: list[MediaItem] = []
    for identifier in identifiers:
        url = OMDB_ENDPOINT + "?" + urllib.parse.urlencode({
            "apikey": config.omdb_api_key,
            "i": identifier,
            "plot": "full",
        })
        payload = _request_json(url, transport, config.timeout_seconds)
        if not isinstance(payload, dict):
            continue
        item = _omdb_item(
            payload,
            include_movies=include_movies,
            include_series=include_series,
            include_anime=include_anime,
            now=now,
        )
        if item:
            out.append(item)
    return out[: config.max_per_source]


def _query_keywords(intent: RecommendationIntent, profile: TasteProfile, include_anime: bool) -> tuple[str, ...]:
    values: list[str] = []
    values.extend(GENRE_SEARCH_TERMS.get(value, value) for value in intent.genres)
    values.extend(GENRE_SEARCH_TERMS.get(value, value) for value in intent.moods)
    values.extend(GENRE_SEARCH_TERMS.get(value, value) for value, _ in profile.top_positive("genre", 4))
    if include_anime:
        values.append("animation")
    if not values:
        values.extend(["drama", "mystery", "science fiction"])
    return tuple(_dedupe_strings(values)[:4])


def _tvmaze_item(
    row: Mapping[str, object],
    *,
    include_series: bool,
    include_anime: bool,
    now: float,
) -> MediaItem | None:
    show = row.get("show") if isinstance(row.get("show"), dict) else row
    if not isinstance(show, dict):
        return None
    title = to_simplified_chinese(str(show.get("name") or "").strip())
    image = show.get("image") if isinstance(show.get("image"), dict) else {}
    cover = str(image.get("original") or image.get("medium") or "").strip()
    if not title or not cover.startswith(("http://", "https://")):
        return None
    genres = _dedupe_strings(_genre(value) for value in show.get("genres", []))
    provider_format = str(show.get("type") or "").strip()
    if provider_format.casefold() == "documentary":
        genres = _dedupe_strings([*genres, "纪录片"])
    is_animation = "动画" in genres
    media_type = "动漫" if is_animation else "电视剧"
    if media_type == "动漫" and not include_anime:
        return None
    if media_type == "电视剧" and not include_series:
        return None
    provider_id = str(show.get("id") or "").strip()
    rating_data = show.get("rating") if isinstance(show.get("rating"), dict) else {}
    network = show.get("network") if isinstance(show.get("network"), dict) else {}
    web_channel = show.get("webChannel") if isinstance(show.get("webChannel"), dict) else {}
    country_data = network.get("country") if isinstance(network.get("country"), dict) else {}
    if not country_data and isinstance(web_channel.get("country"), dict):
        country_data = web_channel.get("country")
    country_code = str(country_data.get("code") or "").strip()
    rating = rating_data.get("average")
    raw = _provider_raw(
        show,
        provider="tvmaze",
        provider_id=provider_id,
        rating=rating,
        aliases=[],
        now=now,
        extra={
            "discovery_score": row.get("score"),
            "provider_format": provider_format,
            "rating_votes": {"tvmaze_weight": int(show.get("weight") or 0)},
        },
    )
    return MediaItem(
        title=title,
        media_type=media_type,
        year=_year(show.get("premiered")),
        genres=genres,
        countries=_dedupe_strings([_country(country_code or country_data.get("name"))]),
        languages=_dedupe_strings([_language(show.get("language"))]),
        url=str(show.get("officialSite") or show.get("url") or "").strip(),
        douban_id=f"tvmaze-{provider_id}" if provider_id else "",
        cover=cover,
        summary=_clean_html(show.get("summary")),
        source="global:tvmaze",
        vote_count=int(show.get("weight") or 0) or None,
        raw=raw,
    )


def _discover_tvmaze(
    keywords: tuple[str, ...],
    config: GlobalDiscoveryConfig,
    transport: Transport,
    *,
    include_series: bool,
    include_anime: bool,
    now: float,
) -> list[MediaItem]:
    requests: list[str] = [
        TVMAZE_SEARCH_ENDPOINT + "?" + urllib.parse.urlencode({"q": keyword})
        for keyword in keywords[:3]
    ]
    if config.include_current:
        date = datetime.fromtimestamp(now, tz=timezone.utc).date().isoformat()
        requests.append(
            TVMAZE_SCHEDULE_ENDPOINT + "?" + urllib.parse.urlencode({"date": date, "country": "US"})
        )

    if not requests:
        return []

    # TVMaze discovery previously paid the full latency of three keyword
    # searches plus the current schedule in sequence. These requests are
    # independent, so issue the small bounded batch together while retaining
    # deterministic input order when the payloads are merged.
    with ThreadPoolExecutor(
        max_workers=min(4, len(requests)),
        thread_name_prefix="cinescope-tvmaze",
    ) as executor:
        payloads = list(executor.map(
            lambda url: _request_json(url, transport, config.timeout_seconds),
            requests,
        ))

    out: list[MediaItem] = []
    for payload in payloads:
        for row in payload if isinstance(payload, list) else []:
            if isinstance(row, dict):
                item = _tvmaze_item(row, include_series=include_series, include_anime=include_anime, now=now)
                if item:
                    out.append(item)
    return out[: config.max_per_source]


def _anime_title(row: Mapping[str, object]) -> tuple[str, list[str]]:
    return localize_anime_title(row)


def _anime_series_format(value: object) -> bool:
    return str(value or "").strip().upper() not in {"MOVIE", "MUSIC"}


def _discover_anilist(
    config: GlobalDiscoveryConfig,
    transport: Transport,
    *,
    now: float,
) -> list[MediaItem]:
    query = """
    query ($perPage: Int) {
      Page(page: 1, perPage: $perPage) {
        media(type: ANIME, sort: [TRENDING_DESC, SCORE_DESC, POPULARITY_DESC], isAdult: false) {
          id
          title { romaji english native }
          synonyms
          format
          seasonYear
          genres
          description
          coverImage { large extraLarge color }
          bannerImage
          siteUrl
          averageScore
          popularity
          episodes
          duration
          countryOfOrigin
        }
      }
    }
    """
    body = json.dumps({"query": query, "variables": {"perPage": config.max_per_source}}, ensure_ascii=False).encode("utf-8")
    payload = _request_json(
        ANILIST_GRAPHQL_ENDPOINT,
        transport,
        config.timeout_seconds,
        data=body,
        headers={"Content-Type": "application/json"},
    )
    page = ((payload.get("data") or {}).get("Page") or {}) if isinstance(payload, dict) else {}
    rows = page.get("media") if isinstance(page, dict) else []
    out: list[MediaItem] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _anime_series_format(row.get("format")):
            continue
        title, aliases = _anime_title(row)
        cover_data = row.get("coverImage") if isinstance(row.get("coverImage"), dict) else {}
        cover = str(cover_data.get("extraLarge") or cover_data.get("large") or "").strip()
        if not title or not cover.startswith(("http://", "https://")):
            continue
        provider_id = str(row.get("id") or "").strip()
        backdrop = str(row.get("bannerImage") or "").strip()
        raw = _provider_raw(
            row,
            provider="anilist",
            provider_id=provider_id,
            rating=(_number(row.get("averageScore")) or 0) / 10.0,
            backdrop=backdrop,
            aliases=aliases,
            now=now,
            extra={
                "episodes": row.get("episodes"),
                "episode_runtime": row.get("duration"),
                "rating_votes": {"anilist_popularity": int(row.get("popularity") or 0)},
            },
        )
        out.append(MediaItem(
            title=title,
            media_type="动漫",
            year=_year(row.get("seasonYear")),
            genres=_dedupe_strings(_genre(value) for value in row.get("genres", [])),
            countries=_dedupe_strings([_country(row.get("countryOfOrigin"))]),
            url=str(row.get("siteUrl") or (f"https://anilist.co/anime/{provider_id}" if provider_id else "")),
            douban_id=f"anilist-{provider_id}" if provider_id else "",
            cover=cover,
            summary=_clean_html(row.get("description")),
            source="global:anilist",
            vote_count=int(row.get("popularity") or 0) or None,
            raw=raw,
        ))
    return out[: config.max_per_source]


def _jikan_items(payload: object, *, now: float) -> list[MediaItem]:
    rows = payload.get("data") if isinstance(payload, dict) else []
    out: list[MediaItem] = []
    for row in rows if isinstance(rows, list) else []:
        if not isinstance(row, dict) or not _anime_series_format(row.get("type")):
            continue
        title, aliases = _anime_title(row)
        images = row.get("images") if isinstance(row.get("images"), dict) else {}
        jpg = images.get("jpg") if isinstance(images.get("jpg"), dict) else {}
        webp = images.get("webp") if isinstance(images.get("webp"), dict) else {}
        cover = str(
            jpg.get("large_image_url")
            or webp.get("large_image_url")
            or jpg.get("image_url")
            or webp.get("image_url")
            or ""
        ).strip()
        if not title or not cover.startswith(("http://", "https://")):
            continue
        provider_id = str(row.get("mal_id") or "").strip()
        trailer = row.get("trailer") if isinstance(row.get("trailer"), dict) else {}
        trailer_images = trailer.get("images") if isinstance(trailer.get("images"), dict) else {}
        backdrop = str(
            trailer_images.get("maximum_image_url")
            or trailer_images.get("large_image_url")
            or ""
        ).strip()
        raw = _provider_raw(
            row,
            provider="jikan",
            provider_id=provider_id,
            rating=row.get("score"),
            backdrop=backdrop,
            aliases=aliases,
            now=now,
            extra={
                "episodes": row.get("episodes"),
                "rating_votes": {"jikan": int(row.get("scored_by") or 0)},
                "popularity": row.get("members") or row.get("popularity"),
            },
        )
        out.append(MediaItem(
            title=title,
            media_type="动漫",
            year=_year(row.get("year") or ((row.get("aired") or {}).get("from") if isinstance(row.get("aired"), dict) else "")),
            genres=_dedupe_strings(_genre(value.get("name")) for value in row.get("genres", []) if isinstance(value, dict)),
            countries=["日本"],
            url=str(row.get("url") or (f"https://myanimelist.net/anime/{provider_id}" if provider_id else "")),
            douban_id=f"mal-{provider_id}" if provider_id else "",
            cover=cover,
            summary=_clean_html(row.get("synopsis")),
            source="global:jikan",
            vote_count=int(row.get("scored_by") or row.get("members") or 0) or None,
            raw=raw,
        ))
    return out


def _discover_jikan(config: GlobalDiscoveryConfig, transport: Transport, *, now: float) -> list[MediaItem]:
    urls = [
        JIKAN_TOP_ENDPOINT + "?" + urllib.parse.urlencode({
            "type": "tv",
            "filter": "bypopularity",
            "sfw": "true",
            "limit": str(config.max_per_source),
        }),
    ]
    if config.include_current:
        urls.append(JIKAN_SEASON_ENDPOINT + "?" + urllib.parse.urlencode({
            "filter": "tv",
            "sfw": "true",
            "limit": str(config.max_per_source),
        }))
    out: list[MediaItem] = []
    for url in urls:
        out.extend(_jikan_items(_request_json(url, transport, config.timeout_seconds), now=now))
    return out[: config.max_per_source]


def _apple_label(value: object) -> str:
    if isinstance(value, dict):
        return str(value.get("label") or "").strip()
    return str(value or "").strip()


def _localized_apple_title(value: object) -> str:
    """Keep a Chinese storefront title and remove duplicated Latin suffixes."""

    title = _SPACE_RE.sub(" ", _apple_label(value)).strip()
    if not title or not re.search(r"[\u3400-\u9fff]", title):
        return ""
    first_han = re.search(r"[\u3400-\u9fff]", title)
    if first_han and first_han.start() > 0:
        title = title[first_han.start():]
    title = re.sub(r"\s*[-–—]\s*[A-Za-z][A-Za-z0-9 .:'’!?&/+\-]*$", "", title).strip()
    title = re.sub(r"\s+[A-Za-z][A-Za-z0-9 .:'’!?&/+\-]*$", "", title).strip(" -–—·:：")
    title = to_simplified_chinese(title)
    return title if len(re.findall(r"[\u3400-\u9fff]", title)) >= 2 else ""


def _apple_artwork(value: object) -> str:
    rows = value if isinstance(value, list) else []
    candidates: list[tuple[int, str]] = []
    for row in rows:
        if not isinstance(row, dict):
            continue
        url = _apple_label(row)
        attributes = row.get("attributes") if isinstance(row.get("attributes"), dict) else {}
        try:
            height = int(attributes.get("height") or 0)
        except (TypeError, ValueError):
            height = 0
        if url.startswith(("http://", "https://")):
            candidates.append((height, url))
    if not candidates:
        return ""
    url = max(candidates, key=lambda entry: entry[0])[1]
    return re.sub(r"/\d+x\d+bb\.(?:jpg|jpeg|png)$", "/600x900bb.jpg", url, flags=re.I)


def _apple_movie_item(
    row: Mapping[str, object],
    *,
    rank: int,
    now: float,
    storefront: str = "tw",
) -> MediaItem | None:
    title = _localized_apple_title(row.get("im:name"))
    cover = _apple_artwork(row.get("im:image"))
    if not title or not cover:
        return None
    identity = row.get("id") if isinstance(row.get("id"), dict) else {}
    identity_attributes = identity.get("attributes") if isinstance(identity.get("attributes"), dict) else {}
    provider_id = str(identity_attributes.get("im:id") or "").strip()
    release_date = _apple_label(row.get("im:releaseDate"))[:10]
    category = row.get("category") if isinstance(row.get("category"), dict) else {}
    category_attributes = category.get("attributes") if isinstance(category.get("attributes"), dict) else {}
    genre = _genre(category_attributes.get("term") or category_attributes.get("label"))
    artist = _apple_label(row.get("im:artist"))
    links = row.get("link") if isinstance(row.get("link"), list) else []
    url = next((
        str((link.get("attributes") or {}).get("href") or "").strip()
        for link in links
        if isinstance(link, dict)
        and isinstance(link.get("attributes"), dict)
        and str(link["attributes"].get("rel") or "").strip() == "alternate"
    ), _apple_label(identity))
    raw = _provider_raw(
        row,
        provider="apple_movies",
        provider_id=provider_id,
        aliases=[_apple_label(row.get("title"))],
        now=now,
        extra={
            "release_date": release_date,
            "popularity": max(1.0, 101.0 - max(1, rank)),
            "feed_rank": max(1, rank),
            "storefront": storefront,
        },
    )
    return MediaItem(
        title=title,
        media_type="电影",
        year=_year(release_date),
        genres=_dedupe_strings([genre]),
        directors=_dedupe_strings([artist]),
        url=url,
        douban_id=f"apple-movie-{provider_id}" if provider_id else "",
        cover=cover,
        summary=_clean_html(_apple_label(row.get("summary"))),
        source="global:apple_movies",
        raw=raw,
    )


def _discover_apple_movies(config: GlobalDiscoveryConfig, transport: Transport, *, now: float) -> list[MediaItem]:
    feed_limit = 25 if config.max_per_source <= 25 else 50
    url = APPLE_TOP_MOVIES_ENDPOINT.format(storefront=config.apple_storefront, limit=feed_limit)
    payload = _request_json(url, transport, config.timeout_seconds)
    feed = payload.get("feed") if isinstance(payload, dict) and isinstance(payload.get("feed"), dict) else {}
    rows = feed.get("entry") if isinstance(feed.get("entry"), list) else []
    items = [
        item
        for rank, row in enumerate(rows, start=1)
        if isinstance(row, dict)
        and (item := _apple_movie_item(row, rank=rank, now=now, storefront=config.apple_storefront)) is not None
    ]
    return items[: config.max_per_source]


def _item_completeness(item: MediaItem) -> float:
    raw = item.raw if isinstance(item.raw, dict) else {}
    ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    return (
        (8.0 if item.cover else 0.0)
        + (5.0 if item.summary else 0.0)
        + min(5.0, len(item.genres) * 1.2)
        + (2.0 if item.year else 0.0)
        + (2.0 if item.countries else 0.0)
        + min(4.0, len(ratings) * 1.4)
        + min(3.0, (item.vote_count or 0) / 100000.0)
    )


def _identity_signature(item: MediaItem) -> str:
    aliases = item.raw.get("aliases") if isinstance(item.raw, dict) and isinstance(item.raw.get("aliases"), list) else []
    titles = [item.title, *aliases]
    normalized = next((normalize_title(title) for title in titles if normalize_title(title)), "")
    return f"{normalized}|{item.year or ''}|{canonical_media_type(item.media_type)}"


def _merge_raw(primary: dict, secondary: dict) -> dict:
    merged = dict(secondary)
    merged.update(primary)
    for key in ("ratings", "provider_ids", "rating_votes"):
        left = primary.get(key) if isinstance(primary.get(key), dict) else {}
        right = secondary.get(key) if isinstance(secondary.get(key), dict) else {}
        merged[key] = {**right, **left}
    merged["aliases"] = _dedupe_strings([*(secondary.get("aliases") or []), *(primary.get("aliases") or [])])
    merged["discovery_sources"] = _dedupe_strings([
        *(secondary.get("discovery_sources") or []),
        *(primary.get("discovery_sources") or []),
    ])
    if not merged.get("backdrop"):
        merged["backdrop"] = secondary.get("backdrop") or primary.get("backdrop") or ""
    return merged


def _merge_items(left: MediaItem, right: MediaItem) -> MediaItem:
    primary, secondary = (left, right) if _item_completeness(left) >= _item_completeness(right) else (right, left)
    primary.genres = _dedupe_strings([*primary.genres, *secondary.genres])
    primary.countries = _dedupe_strings([*primary.countries, *secondary.countries])
    primary.languages = _dedupe_strings([*primary.languages, *secondary.languages])
    primary.directors = _dedupe_strings([*primary.directors, *secondary.directors])
    primary.casts = _dedupe_strings([*primary.casts, *secondary.casts])
    primary.tags = _dedupe_strings([*primary.tags, *secondary.tags])
    if len(secondary.summary) > len(primary.summary):
        primary.summary = secondary.summary
    if not primary.cover:
        primary.cover = secondary.cover
    if not primary.url:
        primary.url = secondary.url
    if not primary.year:
        primary.year = secondary.year
    primary.vote_count = max(primary.vote_count or 0, secondary.vote_count or 0) or None
    primary.source = "|".join(_dedupe_strings([*str(primary.source).split("|"), *str(secondary.source).split("|")]))
    primary.raw = _merge_raw(primary.raw if isinstance(primary.raw, dict) else {}, secondary.raw if isinstance(secondary.raw, dict) else {})
    return primary


def _dedupe_items(items: list[MediaItem]) -> list[MediaItem]:
    merged: dict[str, MediaItem] = {}
    for item in items:
        signature = _identity_signature(item)
        if not signature.strip("|"):
            continue
        if signature in merged:
            merged[signature] = _merge_items(merged[signature], item)
        else:
            merged[signature] = item
    return list(merged.values())


def _best_rating(item: MediaItem) -> float:
    raw = item.raw if isinstance(item.raw, dict) else {}
    ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    values = [value for value in (_number(value) for value in ratings.values()) if value is not None]
    if item.douban_rating is not None:
        values.append(float(item.douban_rating))
    return max(values) if values else 0.0


def _discovery_sort_key(item: MediaItem) -> tuple[float, float, float, str]:
    current_year = datetime.now(tz=timezone.utc).year
    freshness = max(0.0, 6.0 - max(0, current_year - int(item.year or current_year)))
    rating = _best_rating(item)
    votes = float(item.vote_count or 0)
    return (
        rating * 10.0 + min(8.0, votes / 50000.0) + freshness + _item_completeness(item),
        rating,
        votes,
        item.title,
    )


def _safe_error(error: BaseException, config: GlobalDiscoveryConfig) -> str:
    text = _SAFE_ERROR_RE.sub("<redacted>", str(error or ""))
    for secret in (config.tmdb_api_key, config.omdb_api_key):
        if secret:
            text = text.replace(secret, "<redacted>")
    text = _SPACE_RE.sub(" ", text).strip()
    return f"{type(error).__name__}: {text[:180]}" if text else type(error).__name__


def discover_global_candidates(
    intent: RecommendationIntent,
    profile: TasteProfile,
    *,
    include_movies: bool = True,
    include_series: bool = True,
    include_anime: bool = True,
    config: GlobalDiscoveryConfig | None = None,
    transport: Transport | None = None,
    now: Callable[[], float] = time.time,
) -> GlobalDiscoveryReport:
    discovery_config = config or GlobalDiscoveryConfig.from_payload({})
    generated_at = float(now())
    report = GlobalDiscoveryReport(
        config=discovery_config.public_summary(),
        generated_at=generated_at,
    )
    if not discovery_config.enabled:
        report.status = "disabled"
        return report

    request_transport = transport or _default_transport
    keywords = _query_keywords(intent, profile, include_anime)
    report.query_keywords = keywords
    tasks: dict[str, Callable[[], list[MediaItem]]] = {}
    if discovery_config.enable_tmdb and discovery_config.tmdb_api_key and (include_movies or include_series or include_anime):
        tasks["tmdb"] = lambda: _discover_tmdb(
            intent,
            discovery_config,
            request_transport,
            include_movies=include_movies,
            include_series=include_series,
            include_anime=include_anime,
            now=generated_at,
        )
    if discovery_config.enable_omdb and discovery_config.omdb_api_key and (include_movies or include_series or include_anime):
        tasks["omdb"] = lambda: _discover_omdb(
            keywords,
            discovery_config,
            request_transport,
            include_movies=include_movies,
            include_series=include_series,
            include_anime=include_anime,
            now=generated_at,
        )
    if discovery_config.enable_tvmaze and (include_series or include_anime):
        tasks["tvmaze"] = lambda: _discover_tvmaze(
            keywords,
            discovery_config,
            request_transport,
            include_series=include_series,
            include_anime=include_anime,
            now=generated_at,
        )
    if discovery_config.enable_anilist and include_anime:
        tasks["anilist"] = lambda: _discover_anilist(
            discovery_config,
            request_transport,
            now=generated_at,
        )
    if discovery_config.enable_jikan and include_anime:
        tasks["jikan"] = lambda: _discover_jikan(
            discovery_config,
            request_transport,
            now=generated_at,
        )
    if discovery_config.enable_apple_movies and include_movies:
        tasks["apple_movies"] = lambda: _discover_apple_movies(
            discovery_config,
            request_transport,
            now=generated_at,
        )

    if not tasks:
        report.status = "unavailable"
        return report

    def run_source(callback: Callable[[], list[MediaItem]]) -> tuple[list[MediaItem], float, Exception | None]:
        started = time.perf_counter()
        try:
            items = callback()
            return items, round((time.perf_counter() - started) * 1000.0, 2), None
        except Exception as error:
            return [], round((time.perf_counter() - started) * 1000.0, 2), error

    collected: list[MediaItem] = []
    with ThreadPoolExecutor(max_workers=min(6, len(tasks)), thread_name_prefix="cinescope-discovery") as executor:
        futures = {executor.submit(run_source, callback): source for source, callback in tasks.items()}
        for future in as_completed(futures):
            source = futures[future]
            items, elapsed_ms, error = future.result()
            if error is None:
                report.source_counts[source] = len(items)
                report.source_status[source] = {
                    "state": "ready" if items else "empty",
                    "count": len(items),
                    "elapsed_ms": elapsed_ms,
                }
                collected.extend(items)
            else:
                report.source_counts[source] = 0
                report.source_status[source] = {
                    "state": "failed",
                    "count": 0,
                    "error": _safe_error(error, discovery_config),
                    "elapsed_ms": elapsed_ms,
                }

    report.items = sorted(_dedupe_items(collected), key=_discovery_sort_key, reverse=True)[: discovery_config.max_total]
    failed = sum(1 for value in report.source_status.values() if value.get("state") == "failed")
    ready = sum(1 for value in report.source_status.values() if value.get("state") == "ready")
    if ready and failed:
        report.status = "partial"
    elif ready:
        report.status = "complete"
    elif failed:
        report.status = "failed"
    else:
        report.status = "empty"
    return report
