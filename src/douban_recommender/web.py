from __future__ import annotations

import hashlib
import json
import inspect
import os
import threading
import time
import uuid
import webbrowser
from concurrent.futures import Future
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlencode, urlparse
import urllib.error
import urllib.request

from .candidate_planner import build_candidate_plan
from .catalog_api import CatalogApi, CatalogApiError, build_default_catalog_api
from .catalog_hydration import CatalogHydrationCoordinator
from .crawler import crawl_user_collections, normalize_douban_user_id, redact_cookie_from_message
from .curated_catalog import apply_curated_people_photos, apply_curated_posters, backfill_missing_media_types
from .database import AppDatabase
from .diagnostics import build_diagnostics, unknown_diagnostics
from .douban_sources import enrich_media_items, enrich_missing_posters_from_subject_suggest, enrich_missing_posters_from_web_sources, fetch_candidates_from_plan, fetch_douban_candidates, fetch_url_candidates
from .douban_sources import needs_external_poster_rescue, poster_source_config_from_dict
from .douban_sources import build_retry_url_opener, build_url_opener
from .io import load_media_csv, load_media_csv_from_text, read_text_file
from .media_api import MediaApi, build_default_media_api
from .media.url_candidates import image_request_headers, image_url_candidates as shared_image_url_candidates
from .models import MediaItem, is_safe_route_segment
from .profiler import build_taste_profile
from .recommendation_api import RecommendationApi, RecommendationApiError, build_default_recommendation_api
from .recommender import recommend
from .runtime_paths import resolve_data_dir, resolve_database_path
from .serialization import media_item_from_dict, media_item_to_dict
from .storage import CacheStore, default_cache_dir
from .sync_api import SyncApi, build_default_sync_api
from .web_ui import INDEX_HTML
from .web_ui_v3 import asset_response, is_v3_frontend_route, load_index_html, selected_ui_version

ROOT = Path(__file__).resolve().parents[2]
SAMPLE_RATINGS = ROOT / "sample_data" / "ratings_sample.csv"
SAMPLE_CANDIDATES = ROOT / "sample_data" / "candidates_sample.csv"
CACHE = CacheStore(default_cache_dir(ROOT))
POSTER_JOBS: dict[str, dict[str, object]] = {}
POSTER_JOBS_LOCK = threading.Lock()
MAX_POSTER_JOB_EVENTS = 80
IMAGE_PROXY_CACHE: dict[str, tuple[bytes, str]] = {}
IMAGE_PROXY_NEGATIVE_CACHE: dict[str, tuple[float, str]] = {}
IMAGE_PROXY_INFLIGHT: dict[str, Future[tuple[bytes, str]]] = {}
MAX_IMAGE_PROXY_CACHE_ITEMS = 512
IMAGE_PROXY_NEGATIVE_TTL_SECONDS = 300.0
IMAGE_PROXY_REQUEST_TIMEOUT_SECONDS = 3.0
IMAGE_PROXY_TOTAL_BUDGET_SECONDS = 6.0
MAX_IMAGE_PROXY_NETWORK_ATTEMPTS = 4
IMAGE_PROXY_CACHE_LOCK = threading.RLock()
IMAGE_PROXY_DISK_CACHE_DIR = resolve_data_dir() / "image-proxy-cache"
IMAGE_PROXY_CONTENT_TYPE_EXTENSIONS = {
    "image/avif": ".avif",
    "image/gif": ".gif",
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
}
CINESCOPE_SYNC_ENRICH_LIMIT = 40
PUBLIC_PEOPLE_PHOTO_CACHE: dict[str, str] = {}
PUBLIC_PEOPLE_PHOTO_NEGATIVE_CACHE: dict[str, float] = {}
PUBLIC_PEOPLE_NEGATIVE_TTL_SECONDS = 120.0
MEDIA_API: MediaApi | None = None
MEDIA_API_LOCK = threading.Lock()
SYNC_API: SyncApi | None = None
SYNC_API_LOCK = threading.Lock()
RECOMMENDATION_API: RecommendationApi | None = None
RECOMMENDATION_API_LOCK = threading.Lock()
CATALOG_API: CatalogApi | None = None
CATALOG_API_LOCK = threading.Lock()
CATALOG_HYDRATOR: CatalogHydrationCoordinator | None = None
CATALOG_HYDRATOR_LOCK = threading.Lock()
CATALOG_SCHEMA_VERSION = 2
PUBLIC_PEOPLE_QUERY_ALIASES: dict[str, str] = {
    "黑泽明": "Akira Kurosawa",
    "三船敏郎": "Toshiro Mifune",
    "志村乔": "Takashi Shimura",
    "李安": "Ang Lee",
    "郎雄": "Sihung Lung",
    "杨贵媚": "Yang Kuei-mei",
    "金元锡": "Kim Won-seok",
    "李帝勋": "Lee Je-hoon",
    "金惠秀": "Kim Hye-soo",
    "申元浩": "Shin Won-ho (director)",
    "曹政奚": "Cho Jung-seok",
    "柳演锡": "Yoo Yeon-seok",
    "米歇尔·金": "Michelle King",
    "罗伯特·金": "Robert King (writer)",
    "朱丽安娜·玛格丽丝": "Julianna Margulies",
    "诺亚·霍利": "Noah Hawley",
    "马丁·弗瑞曼": "Martin Freeman",
    "比利·鲍伯·松顿": "Billy Bob Thornton",
    "尼克·皮佐拉托": "Nic Pizzolatto",
    "马修·麦康纳": "Matthew McConaughey",
    "伍迪·哈里森": "Woody Harrelson",
    "蒂姆·米勒": "Tim Miller (director)",
    "大卫·芬奇": "David Fincher",
    "迈克尔·丹特·迪马蒂诺": "Michael Dante DiMartino",
    "渡边信一郎": "Shinichirou Watanabe",
    "山寺宏一": "Kouichi Yamadera",
    "石冢运升": "Unshou Ishizuka",
    "林原惠美": "Megumi Hayashibara",
    "中井和哉": "Kazuya Nakai",
    "川澄绫子": "Ayako Kawasumi",
    "佐藤银平": "Ginpei Sato",
    "长滨博史": "Hiroshi Nagahama",
    "中野裕斗": "Yuuto Nakano",
    "土井美加": "Mika Doi",
}


def get_media_api() -> MediaApi:
    global MEDIA_API
    if MEDIA_API is not None:
        return MEDIA_API
    with MEDIA_API_LOCK:
        if MEDIA_API is None:
            MEDIA_API = build_default_media_api()
    return MEDIA_API


def get_sync_api() -> SyncApi:
    global SYNC_API
    if SYNC_API is not None:
        return SYNC_API
    with SYNC_API_LOCK:
        if SYNC_API is None:
            SYNC_API = build_default_sync_api()
    return SYNC_API


def get_recommendation_api() -> RecommendationApi:
    global RECOMMENDATION_API
    if RECOMMENDATION_API is not None:
        return RECOMMENDATION_API
    with RECOMMENDATION_API_LOCK:
        if RECOMMENDATION_API is None:
            RECOMMENDATION_API = build_default_recommendation_api()
    return RECOMMENDATION_API


def get_catalog_api() -> CatalogApi:
    global CATALOG_API
    if CATALOG_API is not None:
        return CATALOG_API
    with CATALOG_API_LOCK:
        if CATALOG_API is None:
            CATALOG_API = build_default_catalog_api()
    return CATALOG_API


def get_catalog_hydrator() -> CatalogHydrationCoordinator:
    global CATALOG_HYDRATOR
    if CATALOG_HYDRATOR is not None:
        return CATALOG_HYDRATOR
    with CATALOG_HYDRATOR_LOCK:
        if CATALOG_HYDRATOR is None:
            CATALOG_HYDRATOR = CatalogHydrationCoordinator(get_catalog_api())
    return CATALOG_HYDRATOR


def get_runtime_diagnostics() -> dict[str, object]:
    try:
        return build_diagnostics(
            db=AppDatabase(resolve_database_path()),
            cache_dir=CACHE.cache_dir,
        )
    except Exception:
        return unknown_diagnostics()


def catalog_error_payload(message: str) -> dict[str, object]:
    return {"schema_version": CATALOG_SCHEMA_VERSION, "error": str(message or "error")}


def anime_subsection_name(countries: list[str]) -> str:
    country_set = set(countries or [])
    if country_set & {"中国大陆", "中国", "中国香港", "中国台湾"}:
        return "动漫 · 国创动画"
    if country_set & {"美国", "英国", "法国", "加拿大", "爱尔兰", "西班牙"}:
        return "动漫 · 欧美动画"
    if "日本" in country_set:
        return "动漫 · 日漫精品"
    return ""


def build_recommendation_sections(recs) -> list[dict[str, object]]:
    order = [
        "必看 Top Picks",
        "高分剧情",
        "电影",
        "电视剧",
        "动漫",
        "动漫 · 国创动画",
        "动漫 · 欧美动画",
        "动漫 · 日漫精品",
        "想看优先",
        "冷门惊喜",
    ]
    grouped: dict[str, list[dict[str, object]]] = {}
    for rec in recs:
        name = rec.section or rec.item.media_type or "全部"
        row = rec.to_dict()
        grouped.setdefault(name, []).append(row)
        if rec.item.media_type == "动漫":
            subchannel = anime_subsection_name(rec.item.countries)
            if subchannel:
                grouped.setdefault(subchannel, []).append(row)

    sections: list[dict[str, object]] = []
    for name in order:
        rows = grouped.pop(name, [])
        if rows:
            sections.append({"name": name, "count": len(rows), "items": rows})
    for name, rows in grouped.items():
        sections.append({"name": name, "count": len(rows), "items": rows})
    return sections


def diversify_recommendation_mix(recs, target_limit: int, requested_types: list[str]) -> list:
    if target_limit < 120 or len(requested_types) < 2:
        return recs[:target_limit]
    floor = min(50, max(1, target_limit // len(requested_types)))
    by_type = {media_type: [rec for rec in recs if rec.item.media_type == media_type] for media_type in requested_types}
    selected = []
    seen: set[str] = set()

    def add(rec) -> None:
        key = rec.item.identity
        if key not in seen:
            selected.append(rec)
            seen.add(key)

    for media_type in requested_types:
        for rec in by_type.get(media_type, [])[:floor]:
            add(rec)
    for rec in recs:
        if len(selected) >= target_limit:
            break
        add(rec)
    selected.sort(key=lambda rec: rec.score, reverse=True)
    return selected[:target_limit]


def call_crawl_user_collections(**kwargs):
    signature = inspect.signature(crawl_user_collections)
    accepts_kwargs = any(param.kind == inspect.Parameter.VAR_KEYWORD for param in signature.parameters.values())
    if accepts_kwargs:
        return crawl_user_collections(**kwargs)
    filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return crawl_user_collections(**filtered)


def diagnostic_to_dict(diag) -> dict:
    if isinstance(diag, dict):
        return dict(diag)
    if hasattr(diag, "__dict__"):
        return dict(diag.__dict__)
    return {"message": str(diag)}


def analyze_sync_input(user_id_or_url: str, cookie: str = "") -> dict[str, object]:
    text = str(user_id_or_url or "").strip()
    lower = text.lower()
    is_profile_url = "douban.com/people/" in lower
    analysis: dict[str, object] = {
        "user_id": "",
        "profile_url": is_profile_url,
        "cookie_provided": bool(str(cookie or "").strip()),
        "profile_url_is_not_cookie": is_profile_url and not bool(str(cookie or "").strip()),
        "can_parse": False,
    }
    try:
        analysis["user_id"] = normalize_douban_user_id(text)
        analysis["can_parse"] = True
    except Exception as exc:
        analysis["error"] = str(exc)
    return analysis


def poster_config_from_payload(payload: dict):
    return poster_source_config_from_dict(payload.get("poster_sources") or payload.get("posterSources") or {})


def poster_config_public_summary(config) -> dict[str, object]:
    return {
        "tmdb_api_enabled": bool(config.enable_tmdb_api and config.tmdb_api_key),
        "omdb_enabled": bool(config.enable_omdb and config.omdb_api_key),
        "tvmaze_enabled": bool(config.enable_tvmaze),
        "anilist_enabled": bool(config.enable_anilist),
        "jikan_enabled": bool(config.enable_jikan),
        "tmdb_html_enabled": bool(config.enable_tmdb_html),
        "douban_enabled": bool(config.enable_douban),
        "wikipedia_enabled": bool(config.enable_wikipedia),
        "prefer_external_over_douban": bool(config.prefer_external_over_douban),
    }


def is_low_confidence_public_candidate(item: MediaItem) -> bool:
    source = str(getattr(item, "source", "") or "")
    if not (source.startswith("douban_plan:") or source.startswith("douban_explore:")):
        return False
    if getattr(item, "douban_rating", None) is not None:
        return False
    tags = set(getattr(item, "tags", []) or [])
    if "想看" in tags or "看过" in tags:
        return False
    return True


def filter_low_confidence_public_candidates(items: list[MediaItem]) -> tuple[list[MediaItem], int]:
    filtered = [item for item in items if not is_low_confidence_public_candidate(item)]
    return filtered, max(0, len(items) - len(filtered))


def call_poster_enricher(items, **kwargs) -> int:
    """Call the poster enrichment function while staying compatible with monkeypatched tests."""

    signature = inspect.signature(enrich_missing_posters_from_web_sources)
    filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return enrich_missing_posters_from_web_sources(items, **filtered)


def call_detail_enricher(items, **kwargs) -> list[MediaItem]:
    """Call detail enrichment while staying compatible with monkeypatched tests."""

    signature = inspect.signature(enrich_media_items)
    filtered = {key: value for key, value in kwargs.items() if key in signature.parameters}
    return enrich_media_items(items, **filtered)


def serialize_poster_job(job: dict[str, object]) -> dict[str, object]:
    out = dict(job)
    out["events"] = list(job.get("events", []))
    out["items"] = list(job.get("items", []))
    return out


def update_poster_job(job_id: str, **updates) -> None:
    with POSTER_JOBS_LOCK:
        job = POSTER_JOBS.get(job_id)
        if not job:
            return
        job.update(updates)


def append_poster_job_event(job_id: str, event: dict[str, object], items: list[MediaItem]) -> None:
    with POSTER_JOBS_LOCK:
        job = POSTER_JOBS.get(job_id)
        if not job:
            return
        events = list(job.get("events", []))
        clean_event = {
            "title": str(event.get("title") or ""),
            "source": str(event.get("source") or ""),
            "status": str(event.get("status") or ""),
            "cover": str(event.get("cover") or ""),
            "time": time.time(),
        }
        events.append(clean_event)
        if len(events) > MAX_POSTER_JOB_EVENTS:
            events = events[-MAX_POSTER_JOB_EVENTS:]
        done = min(int(job.get("total") or 0), int(job.get("done") or 0) + 1)
        found = int(job.get("found") or 0) + (1 if clean_event["status"] == "found" else 0)
        missed = int(job.get("missed") or 0) + (1 if clean_event["status"] != "found" else 0)
        job.update({
            "done": done,
            "found": found,
            "missed": missed,
            "current_title": clean_event["title"],
            "current_source": clean_event["source"],
            "events": events,
            "items": [media_item_to_dict(item) for item in items],
            "updated_at": time.time(),
        })


def run_poster_job(job_id: str, items: list[MediaItem], limit: int, source_config) -> None:
    update_poster_job(job_id, state="running", started_at=time.time())

    def progress(event: dict[str, object]) -> None:
        append_poster_job_event(job_id, event, items)

    try:
        enriched = call_poster_enricher(
            items,
            limit=limit,
            sleep_seconds=0.01,
            max_seconds=90.0,
            source_config=source_config,
            progress_callback=progress,
        )
        with POSTER_JOBS_LOCK:
            job = POSTER_JOBS.get(job_id)
            if job:
                job["state"] = "done"
                job["done"] = int(job.get("total") or len(items))
                job["found"] = max(int(job.get("found") or 0), int(enriched or 0))
                job["items"] = [media_item_to_dict(item) for item in items]
                job["finished_at"] = time.time()
                job["updated_at"] = time.time()
    except Exception as exc:
        with POSTER_JOBS_LOCK:
            job = POSTER_JOBS.get(job_id)
            if job:
                job["state"] = "error"
                job["error"] = str(exc)
                job["items"] = [media_item_to_dict(item) for item in items]
                job["updated_at"] = time.time()


def build_sync_recovery(result, collect_count: int, wish_count: int) -> dict[str, object]:
    diagnostics = [diagnostic_to_dict(diag) for diag in getattr(result, "diagnostics", [])]
    classifications = {str(diag.get("classification") or "") for diag in diagnostics}
    http_statuses = {diag.get("http_status") for diag in diagnostics}
    has_items = (collect_count + wish_count) > 0
    stopped_reason = str(getattr(result, "stopped_reason", "") or "")
    pages_failed = int(getattr(result, "pages_failed", 0) or 0)
    blank_page_stop = "空白" in stopped_reason or "blank" in stopped_reason.lower()
    if has_items:
        if pages_failed == 0:
            return {
                "status": "complete",
                "headline": "同步完成：已拿到可用数据",
                "can_continue_without_sync": False,
                "actions": [
                    f"空白分页是豆瓣列表的正常结束信号：已抓到 {collect_count} 部看过 / {wish_count} 部想看",
                    "继续确认口味",
                    "生成推荐",
                ] if blank_page_stop else ["继续确认口味", "生成推荐"],
            }
        return {
            "status": "ok",
            "headline": "同步已拿到可用数据，部分分页可稍后重试",
            "can_continue_without_sync": False,
            "actions": ["继续确认口味", "生成推荐", "稍后重试失败页"],
        }
    if "login_required" in classifications or 401 in http_statuses or 403 in http_statuses:
        return {
            "status": "needs_cookie",
            "headline": "豆瓣要求登录态或 Cookie，匿名抓取被拦截",
            "can_continue_without_sync": True,
            "actions": [
                "Cookie 解锁：复制当前浏览器里 movie.douban.com 请求的 Cookie 后重试",
                "继续用高质量片库生成推荐：先跳过同步，也能生成电影 / 电视剧 / 动漫推荐",
                "CSV 兜底：从豆瓣导出或手动整理评分后粘贴",
            ],
        }
    if "security_check" in classifications:
        return {
            "status": "security_check",
            "headline": "豆瓣触发安全验证，建议稍后重试或降低抓取频率",
            "can_continue_without_sync": True,
            "actions": ["稍后重试", "减少页数后同步", "继续用高质量片库生成推荐"],
        }
    if pages_failed:
        return {
            "status": "partial_failure",
            "headline": "部分分页抓取失败，可以继续使用已有数据",
            "can_continue_without_sync": True,
            "actions": ["重试失败页", "继续确认口味", "继续用高质量片库生成推荐"],
        }
    return {
        "status": "idle",
        "headline": "还没有同步数据",
        "can_continue_without_sync": True,
        "actions": ["同步豆瓣", "继续用高质量片库生成推荐"],
    }


def build_image_request(url: str) -> urllib.request.Request:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"}:
        raise ValueError("invalid image url")
    return urllib.request.Request(url, headers=image_request_headers(url))


def image_url_candidates(url: str) -> list[str]:
    return list(shared_image_url_candidates(url))


def _validate_proxy_image_payload(data: bytes, content_type: str) -> tuple[bytes, str]:
    clean_type = (content_type or "image/jpeg").split(";")[0].strip().lower()
    head = (data or b"")[:80].lstrip().lower()
    if not clean_type.startswith("image/") or head.startswith((b"<script", b"<!doctype", b"<html")):
        raise ValueError("remote image returned non-image content")
    if clean_type == "image/png" and len(data or b"") < 64:
        raise ValueError("remote image returned an empty transparent placeholder")
    return data, clean_type


def _image_proxy_disk_key(url: str) -> str:
    return hashlib.sha256(str(url or "").strip().encode("utf-8")).hexdigest()


def _read_image_proxy_disk_cache(url: str) -> tuple[bytes, str] | None:
    stem = _image_proxy_disk_key(url)
    root = Path(IMAGE_PROXY_DISK_CACHE_DIR)
    for content_type, extension in IMAGE_PROXY_CONTENT_TYPE_EXTENSIONS.items():
        path = root / f"{stem}{extension}"
        try:
            if not path.is_file():
                continue
            return _validate_proxy_image_payload(path.read_bytes(), content_type)
        except (OSError, ValueError):
            try:
                path.unlink(missing_ok=True)
            except OSError:
                pass
    return None


def _write_image_proxy_disk_cache(url: str, data: bytes, content_type: str) -> None:
    extension = IMAGE_PROXY_CONTENT_TYPE_EXTENSIONS.get(content_type)
    if not extension:
        return
    root = Path(IMAGE_PROXY_DISK_CACHE_DIR)
    try:
        root.mkdir(parents=True, exist_ok=True)
        destination = root / f"{_image_proxy_disk_key(url)}{extension}"
        temporary = root / f".{destination.name}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp"
        temporary.write_bytes(data)
        temporary.replace(destination)
    except OSError:
        try:
            temporary.unlink(missing_ok=True)
        except (OSError, UnboundLocalError):
            pass


def fetch_proxy_image(url: str) -> tuple[bytes, str]:

    def read_with_opener(opener, image_url: str) -> tuple[bytes, str]:
        nonlocal network_attempts
        if network_attempts >= MAX_IMAGE_PROXY_NETWORK_ATTEMPTS:
            raise TimeoutError("image proxy attempt budget exhausted")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            raise TimeoutError("image proxy time budget exhausted")
        network_attempts += 1
        request = build_image_request(image_url)
        timeout = min(IMAGE_PROXY_REQUEST_TIMEOUT_SECONDS, max(0.1, remaining))
        with opener.open(request, timeout=timeout) as response:
            content_type = response.headers.get("Content-Type") or "image/jpeg"
            return _validate_proxy_image_payload(response.read(), content_type)

    def closed_http_error_details(error: urllib.error.HTTPError) -> tuple[int, str]:
        try:
            return error.code, str(error.reason)
        finally:
            error.close()

    cache_key = str(url or "").strip()
    with IMAGE_PROXY_CACHE_LOCK:
        cached = IMAGE_PROXY_CACHE.get(cache_key)
    if cached:
        return cached
    disk_cached = _read_image_proxy_disk_cache(cache_key)
    if disk_cached:
        with IMAGE_PROXY_CACHE_LOCK:
            IMAGE_PROXY_CACHE[cache_key] = disk_cached
            IMAGE_PROXY_NEGATIVE_CACHE.pop(cache_key, None)
        return disk_cached

    with IMAGE_PROXY_CACHE_LOCK:
        cached = IMAGE_PROXY_CACHE.get(cache_key)
        if cached:
            return cached
        now = time.monotonic()
        negative_cached = IMAGE_PROXY_NEGATIVE_CACHE.get(cache_key)
        if negative_cached and negative_cached[0] <= now:
            IMAGE_PROXY_NEGATIVE_CACHE.pop(cache_key, None)
            negative_cached = None
        if negative_cached:
            raise urllib.error.URLError(negative_cached[1])
        inflight = IMAGE_PROXY_INFLIGHT.get(cache_key)
        is_owner = inflight is None
        if inflight is None:
            inflight = Future()
            IMAGE_PROXY_INFLIGHT[cache_key] = inflight

    if not is_owner:
        return inflight.result()

    try:
        last_error: Exception | tuple[int, str] | None = None
        result: tuple[bytes, str] | None = None
        deadline = time.monotonic() + IMAGE_PROXY_TOTAL_BUDGET_SECONDS
        network_attempts = 0
        for candidate_url in image_url_candidates(cache_key):
            if network_attempts >= MAX_IMAGE_PROXY_NETWORK_ATTEMPTS or time.monotonic() >= deadline:
                break
            try:
                result = read_with_opener(build_url_opener(), candidate_url)
                break
            except urllib.error.HTTPError as exc:
                last_error = closed_http_error_details(exc)
                try:
                    result = read_with_opener(build_retry_url_opener(), candidate_url)
                    break
                except urllib.error.HTTPError as direct_exc:
                    last_error = closed_http_error_details(direct_exc)
                    continue
                except (urllib.error.URLError, ValueError, TimeoutError) as direct_exc:
                    last_error = direct_exc
                    continue
            except urllib.error.URLError as exc:
                last_error = exc
                try:
                    result = read_with_opener(build_retry_url_opener(), candidate_url)
                    break
                except urllib.error.HTTPError as direct_exc:
                    last_error = closed_http_error_details(direct_exc)
                    continue
                except (urllib.error.URLError, ValueError, TimeoutError) as direct_exc:
                    last_error = direct_exc
                    continue
            except (ValueError, TimeoutError) as exc:
                last_error = exc
                continue
        if result is None:
            if isinstance(last_error, tuple):
                failure_message = f"HTTP {last_error[0]}: {last_error[1]}"
            else:
                failure_message = str(last_error or "image unavailable")
            with IMAGE_PROXY_CACHE_LOCK:
                if len(IMAGE_PROXY_NEGATIVE_CACHE) >= MAX_IMAGE_PROXY_CACHE_ITEMS:
                    IMAGE_PROXY_NEGATIVE_CACHE.pop(next(iter(IMAGE_PROXY_NEGATIVE_CACHE)), None)
                IMAGE_PROXY_NEGATIVE_CACHE[cache_key] = (
                    time.monotonic() + IMAGE_PROXY_NEGATIVE_TTL_SECONDS,
                    failure_message,
                )
            if isinstance(last_error, tuple):
                status_code, reason = last_error
                error = urllib.error.HTTPError(cache_key, status_code, reason, hdrs=None, fp=None)
                error.close()
                raise error
            if last_error:
                raise last_error
            raise ValueError("invalid image url")
        with IMAGE_PROXY_CACHE_LOCK:
            if len(IMAGE_PROXY_CACHE) >= MAX_IMAGE_PROXY_CACHE_ITEMS:
                IMAGE_PROXY_CACHE.pop(next(iter(IMAGE_PROXY_CACHE)), None)
            IMAGE_PROXY_CACHE[cache_key] = result
            IMAGE_PROXY_NEGATIVE_CACHE.pop(cache_key, None)
        _write_image_proxy_disk_cache(cache_key, result[0], result[1])
    except BaseException as exc:
        inflight.set_exception(exc)
        raise
    else:
        inflight.set_result(result)
        return result
    finally:
        with IMAGE_PROXY_CACHE_LOCK:
            if IMAGE_PROXY_INFLIGHT.get(cache_key) is inflight:
                IMAGE_PROXY_INFLIGHT.pop(cache_key, None)

def visible_people_names_for_item(item: MediaItem) -> set[str]:
    return {
        str(name).strip()
        for name in [*(item.directors or []), *(item.casts or [])]
        if str(name).strip()
    }


def filtered_people_photos_for_item(item: MediaItem) -> dict[str, str]:
    photos = item.raw.get("people_photos") if isinstance(item.raw, dict) else {}
    if not isinstance(photos, dict) or not photos:
        return {}
    visible_names = visible_people_names_for_item(item)
    if not visible_names:
        return {}
    filtered: dict[str, str] = {}
    for name in visible_names:
        for key in (name, f"导演:{name}", f"主演:{name}"):
            url = photos.get(key)
            if url:
                filtered[name] = str(url)
                break
    return filtered


def build_douban_detail_request(url: str, cookie: str = "") -> urllib.request.Request:
    headers = {
        "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://movie.douban.com/",
    }
    clean_cookie = str(cookie or "").strip()
    if clean_cookie:
        headers["Cookie"] = clean_cookie
    return urllib.request.Request(url, headers=headers)


def fetch_douban_detail_html(url: str, cookie: str = "") -> bytes:
    request = build_douban_detail_request(url, cookie)
    opener = build_url_opener()
    with opener.open(request, timeout=12) as response:
        return response.read()


def _public_people_query_candidates(name: str) -> list[str]:
    clean = str(name or "").strip()
    if not clean:
        return []
    candidates = [PUBLIC_PEOPLE_QUERY_ALIASES.get(clean, ""), clean]
    out: list[str] = []
    for candidate in candidates:
        candidate = str(candidate or "").strip()
        if candidate and candidate not in out:
            out.append(candidate)
    return out


def _resolve_jikan_people_photo(query: str, opener) -> str:
    safe_query = str(query or "").strip()
    if not safe_query:
        return ""
    api_url = "https://api.jikan.moe/v4/people?" + urlencode({"q": safe_query, "limit": "1"})
    request = urllib.request.Request(
        api_url,
        headers={
            "User-Agent": "CineScopeLocalPersonalRecommender/1.0",
            "Accept": "application/json",
        },
    )
    try:
        with opener.open(request, timeout=4) as response:
            data = json.loads(response.read().decode("utf-8", "ignore"))
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
        return ""
    rows = data.get("data") if isinstance(data, dict) else None
    if not isinstance(rows, list):
        return ""
    for row in rows:
        if not isinstance(row, dict):
            continue
        images = row.get("images")
        jpg = images.get("jpg") if isinstance(images, dict) else None
        image = str(jpg.get("image_url") or "").strip() if isinstance(jpg, dict) else ""
        if image.startswith("https://") and "cdn.myanimelist.net" in image:
            return image
    return ""


def resolve_public_people_photos(names: list[str] | tuple[str, ...] | set[str]) -> dict[str, str]:
    """Resolve visible cast/director portraits from public encyclopedia thumbnails.

    This is a no-key fallback for the detail drawer's "立即补图" button when
    Douban detail pages do not expose public person thumbnails. It first tries
    public encyclopedia thumbnails, then uses Jikan/MyAnimeList for anime staff
    and voice actors. Names are capped, requests are short-timeout, and failures
    are cached as negative hits for the current server process.
    """
    resolved: dict[str, str] = {}
    unique_names: list[str] = []
    for raw_name in names or []:
        name = str(raw_name or "").strip()
        if name and name not in unique_names:
            unique_names.append(name)
    if not unique_names:
        return resolved

    opener = build_url_opener()
    for name in unique_names[:8]:
        if name in PUBLIC_PEOPLE_PHOTO_CACHE:
            resolved[name] = PUBLIC_PEOPLE_PHOTO_CACHE[name]
            continue
        now = time.monotonic()
        negative_at = PUBLIC_PEOPLE_PHOTO_NEGATIVE_CACHE.get(name)
        if negative_at is not None and now - negative_at < PUBLIC_PEOPLE_NEGATIVE_TTL_SECONDS:
            continue
        PUBLIC_PEOPLE_PHOTO_NEGATIVE_CACHE.pop(name, None)
        found = ""
        for query in _public_people_query_candidates(name):
            languages = ["en", "zh", "ja", "ko"] if all(ord(ch) < 128 for ch in query) else ["zh", "en", "ja", "ko"]
            for language in languages:
                api_url = f"https://{language}.wikipedia.org/api/rest_v1/page/summary/{quote(query)}"
                request = urllib.request.Request(
                    api_url,
                    headers={
                        "User-Agent": "CineScopeLocalPersonalRecommender/1.0",
                        "Accept": "application/json",
                    },
                )
                try:
                    with opener.open(request, timeout=3) as response:
                        data = json.loads(response.read().decode("utf-8", "ignore"))
                except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError, ValueError, json.JSONDecodeError):
                    continue
                image = ""
                thumbnail = data.get("thumbnail") if isinstance(data, dict) else None
                original = data.get("originalimage") if isinstance(data, dict) else None
                if isinstance(thumbnail, dict):
                    image = str(thumbnail.get("source") or "")
                if not image and isinstance(original, dict):
                    image = str(original.get("source") or "")
                if image.startswith("https://"):
                    found = image
                    break
            if found:
                break
        if not found:
            for query in _public_people_query_candidates(name):
                found = _resolve_jikan_people_photo(query, opener)
                if found:
                    break
        if found:
            PUBLIC_PEOPLE_PHOTO_CACHE[name] = found
            resolved[name] = found
        else:
            PUBLIC_PEOPLE_PHOTO_NEGATIVE_CACHE[name] = now
    return resolved


class Handler(BaseHTTPRequestHandler):
    server_version = "DoubanTasteRecommender/0.1"

    def log_message(self, fmt: str, *args) -> None:
        print("[web] " + fmt % args)

    def do_GET(self) -> None:
        parsed = urlparse(self.path)
        path = parsed.path
        try:
            if path in {"/", "/index.html"}:
                html = load_index_html() if selected_ui_version(os.environ) == "v3" else INDEX_HTML
                self.send_text(
                    html,
                    content_type="text/html; charset=utf-8",
                    cache_control="no-cache, no-store, must-revalidate",
                )
            elif path.startswith("/assets/v3/"):
                relative_path = path.removeprefix("/assets/v3/")
                try:
                    data, content_type = asset_response(relative_path)
                except FileNotFoundError:
                    self.send_json({"error": "asset not found"}, status=404)
                    return
                self.send_bytes(data, content_type=content_type, cache_control="no-cache, no-store, must-revalidate")
            elif path == "/sample/ratings":
                self.send_text(read_text_file(SAMPLE_RATINGS), content_type="text/plain; charset=utf-8")
            elif path == "/sample/candidates":
                self.send_text(read_text_file(SAMPLE_CANDIDATES), content_type="text/plain; charset=utf-8")
            elif path == "/api/cache":
                self.send_json(self.handle_cache_get())
            elif path == "/api/image-proxy":
                query = parse_qs(parsed.query)
                image_url = query.get("url", [""])[0]
                try:
                    data, content_type = fetch_proxy_image(image_url)
                except (urllib.error.URLError, ValueError, TimeoutError):
                    self.send_json(
                        {"error": "image unavailable"},
                        status=404,
                        cache_control="public, max-age=300",
                    )
                    return
                self.send_bytes(
                    data,
                    content_type=content_type,
                    cache_control="public, max-age=2592000, immutable",
                )
            elif path.startswith("/media/"):
                route_filename = path.removeprefix("/media/")
                asset = get_media_api().asset(route_filename)
                if not asset:
                    self.send_json({"error": "media not found"}, status=404)
                    return
                self.send_bytes(
                    asset.path.read_bytes(),
                    content_type=asset.mime_type,
                    cache_control="public, max-age=31536000, immutable",
                )
            elif path == "/api/v2/media/health":
                self.send_json(get_media_api().health())
            elif path == "/api/v2/catalog/hydration":
                self.send_json({"schema_version": 2, **get_catalog_hydrator().status()})
            elif path == "/api/v2/diagnostics":
                self.send_json(get_runtime_diagnostics())
            elif path.startswith("/api/v2/media/jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                data = get_media_api().get_job(job_id)
                self.send_json(data, status=404 if data.get("error") == "media job not found" else 200)
            elif path == "/api/v2/titles/search":
                self.send_json(get_catalog_api().search_titles(parse_qs(parsed.query)))
            elif path == "/api/v2/discovery/similar":
                self.send_json(get_catalog_api().similar_titles(parse_qs(parsed.query)))
            elif path == "/api/v2/discovery/multi":
                self.send_json(get_catalog_api().multi_focus_titles(parse_qs(parsed.query)))
            elif path.startswith("/api/v2/titles/"):
                title_id = unquote(path.removeprefix("/api/v2/titles/").strip("/"))
                if not is_safe_route_segment(title_id):
                    self.send_json(catalog_error_payload("not found"), status=404)
                    return
                self.send_json(get_catalog_api().get_title(title_id))
            elif path.startswith("/api/v2/people/"):
                person_id = unquote(path.removeprefix("/api/v2/people/").strip("/"))
                if not is_safe_route_segment(person_id):
                    self.send_json(catalog_error_payload("not found"), status=404)
                    return
                self.send_json(get_catalog_api().get_person(person_id))
            elif path == "/api/v2/library":
                self.send_json(get_catalog_api().list_library(parse_qs(parsed.query)))
            elif path == "/api/v2/recent":
                self.send_json(get_catalog_api().recent(parse_qs(parsed.query)))
            elif path == "/api/v2/discovery/latest":
                self.send_json(get_catalog_api().latest(parse_qs(parsed.query)))
            elif path == "/api/v2/observatory":
                self.send_json(get_catalog_api().observatory(parse_qs(parsed.query)))
            elif path == "/api/v2/taste":
                self.send_json(get_catalog_api().taste(parse_qs(parsed.query)))
            elif path == "/api/v2/universe":
                self.send_json(get_catalog_api().universe(parse_qs(parsed.query)))
            elif path == "/api/v2/sync/settings":
                self.send_json(get_sync_api().get_settings())
            elif path == "/api/v2/sync/browser-auth":
                self.send_json(get_sync_api().get_browser_authorization())
            elif path.startswith("/api/v2/sync/jobs/"):
                job_id = path.removeprefix("/api/v2/sync/jobs/").strip("/")
                if not job_id or "/" in job_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                data = get_sync_api().get_job(job_id)
                self.send_json(data, status=404 if data.get("error") else 200)
            elif path == "/api/v2/recommend/sessions/latest":
                self.send_json(get_recommendation_api().latest_session())
            elif path.startswith("/api/v2/recommend/sessions/"):
                session_id = path.removeprefix("/api/v2/recommend/sessions/").strip("/")
                if not session_id or "/" in session_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                self.send_json(get_recommendation_api().get_session(session_id))
            elif path.startswith("/api/poster-jobs/"):
                job_id = path.rsplit("/", 1)[-1]
                self.send_json(self.handle_poster_job_get(job_id))
            elif is_v3_frontend_route(path):
                html = load_index_html() if selected_ui_version(os.environ) == "v3" else INDEX_HTML
                self.send_text(
                    html,
                    content_type="text/html; charset=utf-8",
                    cache_control="no-cache, no-store, must-revalidate",
                )
            else:
                self.send_json({"error": "not found"}, status=404)
        except CatalogApiError as exc:
            self.send_json(catalog_error_payload(str(exc)), status=exc.status_code)
        except RecommendationApiError as exc:
            self.send_json({"error": str(exc)}, status=exc.status_code)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_POST(self) -> None:
        path = urlparse(self.path).path
        payload = {}
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path.startswith("/api/v2/") and not isinstance(payload, dict):
                self.send_json({"error": "JSON body must be an object"}, status=400)
                return
            if path == "/api/recommend":
                data = self.handle_recommend(payload)
            elif path == "/api/enrich-posters":
                data = self.handle_enrich_posters(payload)
            elif path == "/api/enrich-people":
                data = self.handle_enrich_people(payload)
            elif path == "/api/poster-jobs":
                data = self.handle_poster_job_create(payload)
            elif path == "/api/v2/discovery/query":
                data = get_catalog_api().discovery_query(payload)
            elif path == "/api/v2/discovery/blend":
                data = get_catalog_api().blend_titles(payload)
            elif path.startswith("/api/v2/titles/") and path.endswith("/enrich"):
                title_id = unquote(path.removeprefix("/api/v2/titles/")[: -len("/enrich")].strip("/"))
                if not title_id or "/" in title_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                data = get_catalog_api().enrich_title(title_id, cookie=str(payload.get("cookie") or ""))
            elif path == "/api/v2/media/jobs":
                data = get_media_api().create_job(payload)
            elif path == "/api/v2/sync/browser-auth":
                try:
                    data = get_sync_api().start_browser_authorization(payload)
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=400)
                    return
                except RuntimeError as exc:
                    self.send_json({"error": str(exc)}, status=503)
                    return
            elif path == "/api/v2/sync/run-now":
                try:
                    data = get_sync_api().run_now()
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=400)
                    return
            elif path == "/api/v2/sync/jobs":
                try:
                    data = get_sync_api().create_job(payload)
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=400)
                    return
            elif path.startswith("/api/v2/sync/jobs/") and path.endswith("/resume"):
                job_id = path.removeprefix("/api/v2/sync/jobs/")[: -len("/resume")].strip("/")
                if not job_id or "/" in job_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                try:
                    data = get_sync_api().resume_job(job_id, payload)
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=400)
                    return
            elif path == "/api/v2/recommend/sessions":
                data = get_recommendation_api().create_session(payload)
            elif path.startswith("/api/v2/recommend/sessions/") and path.endswith("/batch"):
                session_id = path.removeprefix("/api/v2/recommend/sessions/")[: -len("/batch")].strip("/")
                if not session_id or "/" in session_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                data = get_recommendation_api().next_batch(session_id, payload)
            elif path.startswith("/api/v2/recommend/sessions/") and path.endswith("/previous"):
                session_id = path.removeprefix("/api/v2/recommend/sessions/")[: -len("/previous")].strip("/")
                if not session_id or "/" in session_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                data = get_recommendation_api().previous_batch(session_id, payload)
            elif path == "/api/v2/feedback":
                data = get_recommendation_api().record_feedback(payload)
            elif path.startswith("/api/v2/feedback/") and path.endswith("/undo"):
                event_id = path.removeprefix("/api/v2/feedback/")[: -len("/undo")].strip("/")
                if not event_id or "/" in event_id:
                    self.send_json({"error": "not found"}, status=404)
                    return
                data = get_recommendation_api().undo_feedback(event_id, payload)
            elif path in {"/api/crawl-douban", "/api/sync-douban"}:
                data = self.handle_sync_douban(payload)
            else:
                self.send_json({"error": "not found"}, status=404)
                return
            self.send_json(data)
        except RecommendationApiError as exc:
            self.send_json({"error": str(exc)}, status=exc.status_code)
        except Exception as exc:
            cookie = payload.get("cookie") if isinstance(payload, dict) else ""
            self.send_json({"error": redact_cookie_from_message(str(exc), cookie or "")}, status=500)

    def do_PUT(self) -> None:
        path = urlparse(self.path).path
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8")) if length else {}
            if not isinstance(payload, dict):
                self.send_json({"error": "JSON body must be an object"}, status=400)
                return
            if path == "/api/v2/sync/settings":
                try:
                    self.send_json(get_sync_api().update_settings(payload))
                except ValueError as exc:
                    self.send_json({"error": str(exc)}, status=400)
            else:
                self.send_json({"error": "not found"}, status=404)
        except (json.JSONDecodeError, UnicodeDecodeError):
            self.send_json({"error": "invalid JSON body"}, status=400)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def do_DELETE(self) -> None:
        path = urlparse(self.path).path
        try:
            if path == "/api/cache":
                self.send_json(self.handle_cache_delete())
            elif path == "/api/v2/sync/jobs":
                self.send_json(get_sync_api().clear_history())
            else:
                self.send_json({"error": "not found"}, status=404)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)

    def handle_cache_get(self) -> dict:
        items, report = CACHE.load_library()
        summary = CACHE.summary()
        return {
            "cache_dir": summary.cache_dir,
            "files": summary.files,
            "library_count": len(items),
            "sync_report": report,
        }

    def handle_cache_delete(self) -> dict:
        return {"removed": CACHE.clear()}

    def handle_sync_douban(self, payload: dict) -> dict:
        user_id_or_url = payload.get("user_id_or_url") or ""
        cookie = payload.get("cookie") or ""
        input_analysis = analyze_sync_input(user_id_or_url, cookie)
        result = call_crawl_user_collections(
            user_id_or_url=user_id_or_url,
            cookie=cookie,
            max_pages=max(1, min(200, int(payload.get("max_pages") or 40))),
            include_wish=bool(payload.get("include_wish", True)),
            include_do=bool(payload.get("include_do", False)),
            expected_collect=int(payload["expected_collect"]) if str(payload.get("expected_collect") or "").strip() else None,
            expected_wish=int(payload["expected_wish"]) if str(payload.get("expected_wish") or "").strip() else None,
        )
        collect_count, wish_count = count_crawl_sources(result.items)
        diagnostics = [diagnostic_to_dict(diag) for diag in getattr(result, "diagnostics", [])]
        CACHE.save_library(result.items, {
            "counts": getattr(result, "completeness", {}),
            "diagnostics": diagnostics,
            "stopped_reason": result.stopped_reason,
        })
        return {
            "items": [media_item_to_dict(item) for item in result.items],
            "counts": {
                "items": len(result.items),
                "collect_count": collect_count,
                "wish_count": wish_count,
                "pages_ok": result.pages_ok,
                "pages_failed": result.pages_failed,
                "stopped_reason": result.stopped_reason,
            },
            "diagnostics": diagnostics,
            "completeness": getattr(result, "completeness", {}),
            "errors": result.errors,
            "stopped_reason": result.stopped_reason,
            "input_analysis": input_analysis,
            "recovery": build_sync_recovery(result, collect_count, wish_count),
        }

    handle_crawl_douban = handle_sync_douban

    def handle_recommend(self, payload: dict) -> dict:
        target_limit = max(1, min(300, int(payload.get("limit") or 120)))
        poster_source_config = poster_config_from_payload(payload)
        target_candidate_total = max(90, target_limit + 30) if target_limit >= 120 else None
        rated_items_payload = payload.get("rated_items") or []
        if rated_items_payload:
            string_defaults = {
                "title": "",
                "media_type": "",
                "url": "",
                "douban_id": "",
                "cover": "",
                "summary": "",
                "source": "",
            }
            rated = [media_item_from_dict({**string_defaults, **item}) for item in rated_items_payload if isinstance(item, dict)]
        else:
            ratings_csv = payload.get("ratings_csv") or ""
            rated = load_media_csv_from_text(ratings_csv, kind="ratings") if ratings_csv.strip() else load_media_csv(SAMPLE_RATINGS, kind="ratings")
        profile = build_taste_profile(
            rated,
            like_terms=payload.get("like_terms") or "",
            dislike_terms=payload.get("dislike_terms") or "",
        )

        candidates = []
        candidates_csv = payload.get("candidates_csv") or ""
        has_custom_candidates = bool(candidates_csv.strip())
        if has_custom_candidates:
            candidates.extend(load_media_csv_from_text(candidates_csv, kind="candidates"))
        elif payload.get("use_sample_candidates"):
            candidates.extend(load_media_csv(SAMPLE_CANDIDATES, kind="candidates"))
        apply_curated_people_photos(apply_curated_posters(candidates))
        urls_text = payload.get("candidate_urls") or ""
        urls = [x.strip() for x in urls_text.replace("\n", ",").split(",") if x.strip()]
        if urls:
            candidates.extend(fetch_url_candidates(urls))
        include_anime = bool(payload.get("include_anime", True))
        filtered_low_confidence = 0
        defer_live_douban_fetch = bool(payload.get("fetch_douban")) and target_limit > CINESCOPE_SYNC_ENRICH_LIMIT
        if payload.get("fetch_douban") and not defer_live_douban_fetch:
            wishlist = [item for item in rated if "想看" in set(item.tags or [])]
            plan = build_candidate_plan(
                profile,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=include_anime,
                wishlist=wishlist,
            )
            report = fetch_candidates_from_plan(plan, sleep_seconds=0.02, max_consecutive_failures=8)
            candidates.extend(report.items)
            if not candidates:
                candidates.extend(fetch_douban_candidates(
                    profile,
                    include_movies=bool(payload.get("include_movies", True)),
                    include_series=bool(payload.get("include_series", True)),
                    per_query=max(5, min(50, int(payload.get("per_query") or 20))),
                ))
        if not has_custom_candidates:
            candidates, filtered_low_confidence = filter_low_confidence_public_candidates(candidates)
        curated_before = len(candidates)
        if not has_custom_candidates:
            candidates = backfill_missing_media_types(
                candidates,
                include_movies=bool(payload.get("include_movies", True)),
                include_series=bool(payload.get("include_series", True)),
                include_anime=include_anime,
                target_total=target_candidate_total,
            )
        apply_curated_people_photos(apply_curated_posters(candidates))
        curated_added = max(0, len(candidates) - curated_before)
        requested_types: list[str] = []
        if bool(payload.get("include_movies", True)):
            requested_types.append("电影")
        if bool(payload.get("include_series", True)):
            requested_types.append("电视剧")
        if include_anime:
            requested_types.append("动漫")
        scored_limit = len(candidates) if target_candidate_total is not None else target_limit
        recs = recommend(
            rated,
            candidates,
            profile,
            limit=scored_limit,
            include_movies=bool(payload.get("include_movies", True)),
            include_series=bool(payload.get("include_series", True)),
            include_anime=include_anime,
        )
        recs = diversify_recommendation_mix(recs, target_limit, requested_types)
        wants_enrichment = bool(payload.get("enrich_details", True)) and bool(recs)
        defer_slow_enrichment = wants_enrichment and target_limit > CINESCOPE_SYNC_ENRICH_LIMIT
        if wants_enrichment and not defer_slow_enrichment:
            enrich_limit = max(1, min(24, len(recs), target_limit))
            call_detail_enricher([rec.item for rec in recs[:enrich_limit]], limit=enrich_limit)
        poster_rescue_pending = sum(1 for rec in recs if needs_external_poster_rescue(rec.item))
        deferred_enrichment = defer_slow_enrichment or poster_rescue_pending > 0
        return {
            "profile": profile.summary(),
            "counts": {
                "rated": len(rated),
                "candidates": len(candidates),
                "curated_candidates": curated_added,
                "filtered_low_confidence": filtered_low_confidence,
                "target_limit": target_limit,
                "returned": len(recs),
                "candidate_target": target_candidate_total or len(candidates),
                "deferred_douban_fetch": defer_live_douban_fetch,
                "deferred_enrichment": deferred_enrichment,
                "poster_rescue_pending": poster_rescue_pending,
            },
            "poster_sources": poster_config_public_summary(poster_source_config),
            "sections": build_recommendation_sections(recs),
            "results": [rec.to_dict() for rec in recs],
        }

    def handle_enrich_posters(self, payload: dict) -> dict:
        items_payload = payload.get("items") or payload.get("recommendations") or []
        if not isinstance(items_payload, list):
            items_payload = []
        string_defaults = {
            "title": "",
            "media_type": "",
            "url": "",
            "douban_id": "",
            "cover": "",
            "summary": "",
            "source": "",
        }
        items = [
            media_item_from_dict({**string_defaults, **item})
            for item in items_payload
            if isinstance(item, dict)
        ]
        poster_source_config = poster_config_from_payload(payload)
        limit = max(1, min(300, int(payload.get("limit") or len(items) or 120)))
        before_designed = sum(1 for item in items if needs_external_poster_rescue(item))
        enriched = call_poster_enricher(
            items,
            limit=limit,
            sleep_seconds=0.01,
            max_seconds=90.0,
            source_config=poster_source_config,
        )
        after_designed = sum(1 for item in items if needs_external_poster_rescue(item))
        return {
            "items": [media_item_to_dict(item) for item in items],
            "counts": {
                "input": len(items),
                "target": limit,
                "rescue_before": before_designed,
                "rescue_remaining": after_designed,
                "designed_before": before_designed,
                "designed_remaining": after_designed,
                "enriched": enriched,
            },
            "poster_sources": poster_config_public_summary(poster_source_config),
        }

    def handle_enrich_people(self, payload: dict) -> dict:
        item_payload = payload.get("item") or {}
        if not isinstance(item_payload, dict):
            item_payload = {}
        string_defaults = {
            "title": "",
            "media_type": "",
            "url": "",
            "douban_id": "",
            "cover": "",
            "summary": "",
            "source": "",
        }
        item = media_item_from_dict({**string_defaults, **item_payload})
        if not isinstance(item.raw, dict):
            item.raw = {}
        incoming_photos = item_payload.get("people_photos") or item_payload.get("peoplePhotos") or {}
        if isinstance(incoming_photos, dict) and incoming_photos:
            item.raw["people_photos"] = {str(name): str(url) for name, url in incoming_photos.items() if name and url}
        apply_curated_people_photos([item])
        before = filtered_people_photos_for_item(item)
        before_count = len(before)
        cookie = str(payload.get("cookie") or "").strip()
        fetcher = (lambda url: fetch_douban_detail_html(url, cookie)) if cookie else None
        call_detail_enricher([item], fetcher=fetcher, limit=1, sleep_seconds=0.01, force_people_photos=True)
        apply_curated_people_photos([item])
        photos = filtered_people_photos_for_item(item)
        visible_names = sorted(visible_people_names_for_item(item), key=lambda n: ([*(item.directors or []), *(item.casts or [])].index(n) if n in [*(item.directors or []), *(item.casts or [])] else 999))
        missing_public_names = [name for name in visible_names if name not in photos]
        allow_public_partial_fill = (item.media_type == "动漫")
        if missing_public_names and (not photos or allow_public_partial_fill) and len(photos) < min(len(visible_names), 4):
            public_photos = resolve_public_people_photos(missing_public_names)
            if public_photos:
                existing_photos = item.raw.get("people_photos") if isinstance(item.raw, dict) else {}
                merged_public = dict(existing_photos) if isinstance(existing_photos, dict) else {}
                merged_public.update(public_photos)
                item.raw["people_photos"] = merged_public
                photos = filtered_people_photos_for_item(item)
        if isinstance(item.raw, dict):
            item.raw["people_photos"] = photos
        serialized = media_item_to_dict(item)
        serialized["people_photos"] = photos
        return {
            "item": serialized,
            "counts": {
                "input": 1,
                "before": before_count,
                "people_photos": len(photos),
                "added": max(0, len(photos) - before_count),
            },
        }

    def handle_poster_job_create(self, payload: dict) -> dict:
        items_payload = payload.get("items") or payload.get("recommendations") or []
        if not isinstance(items_payload, list):
            items_payload = []
        string_defaults = {
            "title": "",
            "media_type": "",
            "url": "",
            "douban_id": "",
            "cover": "",
            "summary": "",
            "source": "",
        }
        items = [
            media_item_from_dict({**string_defaults, **item})
            for item in items_payload
            if isinstance(item, dict)
        ]
        limit = max(1, min(300, int(payload.get("limit") or len(items) or 120)))
        source_config = poster_config_from_payload(payload)
        job_id = uuid.uuid4().hex[:12]
        job = {
            "job_id": job_id,
            "state": "queued",
            "done": 0,
            "total": min(limit, len([item for item in items if needs_external_poster_rescue(item)]) or len(items)),
            "found": 0,
            "missed": 0,
            "current_title": "",
            "current_source": "",
            "events": [],
            "items": [media_item_to_dict(item) for item in items],
            "poster_sources": poster_config_public_summary(source_config),
            "created_at": time.time(),
            "updated_at": time.time(),
        }
        with POSTER_JOBS_LOCK:
            POSTER_JOBS[job_id] = job
        thread = threading.Thread(target=run_poster_job, args=(job_id, items, limit, source_config), daemon=True)
        thread.start()
        return serialize_poster_job(job)

    def handle_poster_job_get(self, job_id: str) -> dict:
        with POSTER_JOBS_LOCK:
            job = POSTER_JOBS.get(job_id)
            if not job:
                return {"error": "poster job not found", "job_id": job_id}
            return serialize_poster_job(job)

    def send_text(
        self,
        text: str,
        content_type: str = "text/plain; charset=utf-8",
        status: int = 200,
        cache_control: str | None = None,
    ) -> None:
        data = text.encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self.wfile.write(data)

    def _write_response_body(self, data: bytes) -> bool:
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionAbortedError, ConnectionResetError):
            return False
        return True

    def send_bytes(
        self,
        data: bytes,
        content_type: str = "application/octet-stream",
        status: int = 200,
        cache_control: str = "public, max-age=86400",
    ) -> None:
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(data)))
        self.send_header("Cache-Control", cache_control)
        self.send_header("X-Content-Type-Options", "nosniff")
        self.end_headers()
        self._write_response_body(data)

    def send_json(
        self,
        payload: dict,
        status: int = 200,
        cache_control: str | None = None,
    ) -> None:
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        if cache_control:
            self.send_header("Cache-Control", cache_control)
        self.end_headers()
        self._write_response_body(data)


def count_crawl_sources(items) -> tuple[int, int]:
    collect_count = 0
    wish_count = 0
    for item in items:
        source = str(getattr(item, "source", "") or "")
        tags = set(getattr(item, "tags", []) or [])
        if source.endswith(":wish") or "想看" in tags:
            wish_count += 1
        else:
            collect_count += 1
    return collect_count, wish_count


def main(argv: list[str] | None = None) -> int:
    import argparse
    parser = argparse.ArgumentParser(description="启动豆瓣口味影视推荐器网页")
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=7861)
    parser.add_argument("--no-browser", action="store_true")
    args = parser.parse_args(argv)

    sync_api = get_sync_api()
    catalog_hydrator = get_catalog_hydrator()
    server = ThreadingHTTPServer((args.host, args.port), Handler)
    url = f"http://{args.host}:{args.port}"
    print(f"豆瓣口味影视推荐器已启动：{url}")
    print("按 Ctrl+C 停止。")
    if not args.no_browser:
        threading.Timer(0.6, lambda: webbrowser.open(url)).start()
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n已停止。")
    finally:
        try:
            catalog_hydrator.close()
        finally:
            try:
                sync_api.close()
            finally:
                server.server_close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
