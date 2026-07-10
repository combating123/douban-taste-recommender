from __future__ import annotations

from dataclasses import dataclass, field
import html
import re
import time
import urllib.error
import urllib.parse
import urllib.request
from typing import Callable

from .io import extract_douban_id, parse_year
from .models import MediaItem
from .profiler import KNOWN_GENRES
from .serialization import redact_cookie

DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.7",
}

MAX_CRAWL_PAGES = 250

COUNTRY_WORDS = [
    "中国大陆",
    "中国香港",
    "中国台湾",
    "美国",
    "英国",
    "日本",
    "韩国",
    "法国",
    "德国",
    "意大利",
    "西班牙",
    "印度",
    "加拿大",
    "澳大利亚",
    "泰国",
]


@dataclass
class PageDiagnostic:
    status: str
    start: int
    url: str
    http_status: int | None = None
    item_count: int = 0
    classification: str = ""
    message: str = ""


@dataclass
class CrawlResult:
    items: list[MediaItem] = field(default_factory=list)
    pages_ok: int = 0
    pages_failed: int = 0
    errors: list[str] = field(default_factory=list)
    stopped_reason: str = ""
    diagnostics: list[PageDiagnostic] = field(default_factory=list)
    expected_collect: int | None = None
    expected_wish: int | None = None
    completeness: dict[str, object] = field(default_factory=dict)


def classify_collection_page(page_html: str, parsed_count: int) -> tuple[str, str]:
    text = clean_html(page_html or "")
    lower = text.lower()
    if parsed_count > 0:
        return "ok_with_items", f"解析到 {parsed_count} 条"
    if any(marker in text for marker in ["登录后", "请登录", "登陆后", "加入豆瓣", "登录跳转"]):
        return "login_required", "页面提示需要登录或需要 Cookie 才能查看完整数据"
    if any(marker in lower for marker in ["captcha", "verify"]) or any(marker in text for marker in ["异常请求", "安全验证", "机器人"]):
        return "security_check", "豆瓣返回安全验证页，建议稍后重试或减少页数"
    if "仅自己可见" in text or "没有权限" in text:
        return "privacy_or_permission", "页面可能受隐私或权限限制"
    if "movie.douban.com/subject/" in (page_html or ""):
        return "parse_failed_nonempty", "页面有内容但当前解析器未识别到标准条目"
    if len(text.strip()) < 80:
        return "true_empty_page", "已到达真实空白分页"
    return "parse_failed_nonempty", "页面有内容但解析结果为空"


def normalize_douban_user_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("请输入豆瓣用户 ID 或主页链接")
    match = re.search(r"douban\.com/people/([^/?#]+)/?", text)
    if match:
        return urllib.parse.unquote(match.group(1)).strip()
    text = text.strip("/")
    if "/" in text or "?" in text or "#" in text:
        raise ValueError("豆瓣用户 ID 或主页链接格式不正确")
    return text


def build_user_collection_url(user_id: str, status: str, start: int) -> str:
    if status not in {"collect", "wish"}:
        raise ValueError("status 只能是 collect 或 wish")
    safe_user_id = urllib.parse.quote(normalize_douban_user_id(user_id), safe="")
    return f"https://movie.douban.com/people/{safe_user_id}/{status}?start={int(start)}&sort=time&rating=all&filter=all&mode=grid"


def parse_user_collection_html(page_html: str, status: str) -> list[MediaItem]:
    blocks = split_item_blocks(page_html or "")
    items: list[MediaItem] = []
    for block in blocks:
        url = html.unescape(first_match(r'''href=["'](https://movie\.douban\.com/subject/\d+/?[^"']*)["']''', block))
        title = clean_html(first_match(r"<em[^>]*>(.*?)</em>", block)) or clean_html(first_match(r'''<img[^>]+alt=["']([^"']+)["']''', block))
        if not title or not url:
            continue

        intro = clean_html(first_match(r'''<li\s+class=["']intro["'][^>]*>(.*?)</li>''', block))
        comment = clean_html(first_match(r'''<span\s+class=["']comment["'][^>]*>(.*?)</span>''', block))
        rating_match = re.search(r"rating(\d)-t", block)
        my_rating = float(rating_match.group(1)) if rating_match else None
        cover = html.unescape(first_match(r'''<img[^>]+src=["']([^"']+)["']''', block))
        genres = [genre for genre in KNOWN_GENRES if genre in intro]
        countries = [country for country in COUNTRY_WORDS if country in intro]
        people_parts = [part.strip() for part in re.split(r"\s*/\s*", intro) if part.strip()]
        directors, casts = split_people_from_intro(people_parts)
        tag = "想看" if status == "wish" else "看过"
        media_type = infer_media_type(title, intro)
        items.append(MediaItem(
            title=title,
            my_rating=my_rating,
            year=parse_year(intro),
            media_type=media_type,
            genres=genres,
            countries=countries,
            directors=directors,
            casts=casts,
            tags=[tag],
            url=url,
            douban_id=extract_douban_id(url),
            cover=cover,
            summary=comment,
            source=f"douban_user:{status}",
            raw={"intro": intro},
        ))
    fallback_items = parse_fallback_subject_links(page_html or "", status=status)
    seen_ids = {item.douban_id for item in items if item.douban_id}
    seen_titles = {item.title for item in items if item.title}
    for item in fallback_items:
        if (item.douban_id and item.douban_id in seen_ids) or item.title in seen_titles:
            continue
        items.append(item)
    return items


def infer_media_type(title: str, intro: str) -> str:
    blob = f"{title or ''} {intro or ''}".lower()
    anime_markers = [
        "动画",
        "动漫",
        "番剧",
        "日本动画",
        "剧场版",
        "anime",
    ]
    if any(marker in blob for marker in anime_markers):
        return "动漫"
    series_markers = [
        "电视剧",
        "剧集",
        "连续剧",
        "网剧",
        "迷你剧",
        "美剧",
        "英剧",
        "日剧",
        "韩剧",
        "国产剧",
        "港剧",
        "台剧",
        "season",
        "series",
        "episode",
    ]
    if any(marker in blob for marker in series_markers):
        return "电视剧"
    if re.search(r"第[一二三四五六七八九十0-9\d]+季", title or ""):
        return "电视剧"
    return "电影"


def parse_fallback_subject_links(page_html: str, status: str) -> list[MediaItem]:
    items: list[MediaItem] = []
    seen: set[str] = set()
    pattern = r'''<a[^>]+href=["'](https://movie\.douban\.com/subject/(\d+)/?[^"']*)["'][^>]*>(.*?)</a>'''
    for match in re.finditer(pattern, page_html or "", flags=re.S | re.I):
        url = html.unescape(match.group(1))
        subject_id = match.group(2)
        inner = match.group(3)
        local = page_html[max(0, match.start() - 300): match.end() + 300]
        title = clean_html(first_match(r'''<img[^>]+alt=["']([^"']+)["']''', inner + local)) or clean_html(inner)
        cover = html.unescape(first_match(r'''<img[^>]+src=["']([^"']+)["']''', inner + local))
        if not title or subject_id in seen:
            continue
        seen.add(subject_id)
        tag = "想看" if status == "wish" else "看过"
        items.append(MediaItem(
            title=title,
            url=url,
            douban_id=subject_id,
            cover=cover,
            tags=[tag],
            source=f"douban_user:{status}",
        ))
    return items


def split_item_blocks(page_html: str) -> list[str]:
    starts = [match.start() for match in re.finditer(r'''<div\s+class=["']item["'][^>]*>''', page_html, flags=re.I)]
    blocks: list[str] = []
    for index, start in enumerate(starts):
        end = starts[index + 1] if index + 1 < len(starts) else len(page_html)
        block = page_html[start:end]
        body_end = re.search(r"</body>|</html>", block, flags=re.I)
        if body_end:
            block = block[: body_end.start()]
        blocks.append(block)
    return blocks


def split_people_from_intro(parts: list[str]) -> tuple[list[str], list[str]]:
    if len(parts) < 4:
        return [], []
    directors = [name.strip() for name in re.split(r"\s+", parts[-2]) if name.strip()]
    casts = [name.strip() for name in re.split(r"\s+", parts[-1]) if name.strip()]
    return directors[:4], casts[:8]


def first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.S | re.I)
    return match.group(1).strip() if match else ""


def clean_html(value: str) -> str:
    text = re.sub(r"<.*?>", "", value or "", flags=re.S)
    return html.unescape(text).strip()


def fetch_user_collection_page(user_id: str, status: str, start: int, cookie: str = "", timeout: int = 12) -> str:
    url = build_user_collection_url(user_id, status, start)
    headers = dict(DEFAULT_HEADERS)
    headers["Referer"] = f"https://movie.douban.com/people/{urllib.parse.quote(normalize_douban_user_id(user_id), safe='')}/"
    if cookie.strip():
        headers["Cookie"] = cookie.strip()
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read().decode("utf-8", errors="ignore")


def classify_http_error(exc: urllib.error.HTTPError, cookie: str) -> tuple[str, str, int | None]:
    try:
        body = exc.read().decode("utf-8", errors="ignore")
    except Exception:
        body = ""
    classification, page_message = classify_collection_page(body, 0) if body else ("network_error", "")
    status_code = getattr(exc, "code", None)
    if status_code in {401, 403} and classification in {"login_required", "true_empty_page", "parse_failed_nonempty", "network_error"}:
        return (
            "login_required",
            f"HTTP {status_code}：豆瓣要求登录态或 Cookie；请粘贴 Cookie 后重试，或先用本地高质量片库继续推荐。",
            status_code,
        )
    message = page_message or redact_cookie_from_message(str(exc), cookie)
    if status_code:
        message = f"HTTP {status_code}：{message}"
    return classification, message, status_code


def redact_cookie_from_message(message: str, cookie: str) -> str:
    redacted_message = str(message)
    stripped_cookie = str(cookie or "").strip()
    if not stripped_cookie:
        return redacted_message

    redacted_message = redacted_message.replace(stripped_cookie, redact_cookie(stripped_cookie))
    redacted_message = redacted_message.replace(stripped_cookie.replace(" ", ""), redact_cookie(stripped_cookie))

    for part in stripped_cookie.split(";"):
        text = part.strip()
        if not text:
            continue
        if "=" in text:
            name, value = text.split("=", 1)
            name = name.strip()
            value = value.strip()
            if value:
                redacted_message = redacted_message.replace(value, "<redacted>")
            if name:
                redacted_message = re.sub(
                    rf"(?i)\b{re.escape(name)}\s*=\s*<redacted>",
                    f"{name}=<redacted>",
                    redacted_message,
                )
                redacted_message = re.sub(
                    rf"(?i)\b{re.escape(name)}\s*=\s*{re.escape(value)}",
                    f"{name}=<redacted>",
                    redacted_message,
                )
        else:
            redacted_message = redacted_message.replace(text, "<redacted>")
    return redacted_message


def calculate_completeness(
    collect_count: int,
    wish_count: int,
    expected_collect: int | None,
    expected_wish: int | None,
) -> dict[str, object]:
    def percent(actual: int, expected: int | None) -> int | None:
        if not expected:
            return None
        return min(100, int(round(actual * 100 / max(expected, 1))))

    collect_percent = percent(collect_count, expected_collect)
    wish_percent = percent(wish_count, expected_wish)
    return {
        "collect_count": collect_count,
        "wish_count": wish_count,
        "expected_collect": expected_collect,
        "expected_wish": expected_wish,
        "collect_percent": collect_percent,
        "wish_percent": wish_percent,
        "is_complete": (collect_percent in (None, 100)) and (wish_percent in (None, 100)),
    }


def crawl_user_collections(
    user_id_or_url: str,
    cookie: str = "",
    max_pages: int = 40,
    include_wish: bool = True,
    include_do: bool = False,
    expected_collect: int | None = None,
    expected_wish: int | None = None,
    page_size: int = 15,
    fetcher: Callable[..., str] | None = None,
    sleep_seconds: float = 0.15,
    resume_starts: dict[str, int] | None = None,
    seed_items: list[MediaItem] | None = None,
) -> CrawlResult:
    user_id = normalize_douban_user_id(user_id_or_url)
    limited_pages = max(1, min(MAX_CRAWL_PAGES, int(max_pages)))
    fetch = fetcher or fetch_user_collection_page
    statuses = ["collect"]
    if include_wish:
        statuses.append("wish")
    if include_do:
        statuses.append("do")
    if resume_starts is not None:
        statuses = [status for status in statuses if status in resume_starts]
    result = CrawlResult(
        items=list(seed_items or []),
        expected_collect=expected_collect,
        expected_wish=expected_wish,
    )
    seen: set[str] = set()
    for item in result.items:
        source_status = str(item.source or "").rsplit(":", 1)[-1]
        key_value = item.douban_id or item.title
        key = f"{source_status}:{key_value}" if key_value else ""
        if key:
            seen.add(key)
    empty_page_seen = False
    for status in statuses:
        start_page = max(0, int((resume_starts or {}).get(status, 0)) // max(1, page_size))
        for page_index in range(start_page, limited_pages):
            start = page_index * page_size
            url = build_user_collection_url(user_id, status, start)
            try:
                page_html = fetch(user_id, status, start, cookie=cookie, timeout=12)
                page_items = parse_user_collection_html(page_html, status=status)
                classification, message = classify_collection_page(page_html, len(page_items))
                result.diagnostics.append(PageDiagnostic(
                    status=status,
                    start=start,
                    url=url,
                    item_count=len(page_items),
                    classification=classification,
                    message=message,
                ))
                result.pages_ok += 1
                if not page_items:
                    empty_page_seen = True
                    break
                for item in page_items:
                    key_value = item.douban_id or item.title
                    key = f"{status}:{key_value}" if key_value else ""
                    if key and key not in seen:
                        result.items.append(item)
                        seen.add(key)
            except urllib.error.HTTPError as exc:
                result.pages_failed += 1
                classification, message, http_status = classify_http_error(exc, cookie)
                safe_message = redact_cookie_from_message(message, cookie)
                result.errors.append(f"{status} start={start}: {safe_message}")
                result.diagnostics.append(PageDiagnostic(
                    status=status,
                    start=start,
                    url=url,
                    http_status=http_status,
                    item_count=0,
                    classification=classification,
                    message=safe_message,
                ))
                break
            except Exception as exc:
                result.pages_failed += 1
                message = redact_cookie_from_message(str(exc), cookie)
                result.errors.append(f"{status} start={start}: {message}")
                result.diagnostics.append(PageDiagnostic(
                    status=status,
                    start=start,
                    url=url,
                    item_count=0,
                    classification="network_error",
                    message=message,
                ))
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)
    login_blocked = any(
        diag.classification == "login_required" and diag.http_status in {401, 403}
        for diag in result.diagnostics
    )
    if empty_page_seen:
        result.stopped_reason = "已到达空白分页"
    elif login_blocked:
        result.stopped_reason = "豆瓣要求登录态或 Cookie"
    elif result.pages_failed:
        result.stopped_reason = "部分分页抓取失败"
    else:
        result.stopped_reason = "已达到页数上限"
    collect_count = sum(1 for item in result.items if item.source.endswith(":collect"))
    wish_count = sum(1 for item in result.items if item.source.endswith(":wish"))
    result.completeness = calculate_completeness(collect_count, wish_count, expected_collect, expected_wish)
    return result

