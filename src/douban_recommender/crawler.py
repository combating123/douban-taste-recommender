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
class CrawlResult:
    items: list[MediaItem] = field(default_factory=list)
    pages_ok: int = 0
    pages_failed: int = 0
    errors: list[str] = field(default_factory=list)
    stopped_reason: str = ""


def normalize_douban_user_id(value: str) -> str:
    text = str(value or "").strip()
    if not text:
        raise ValueError("璇疯緭鍏ヨ眴鐡ｇ敤鎴?ID 鎴栦富椤甸摼鎺?")
    match = re.search(r"douban\.com/people/([^/?#]+)/?", text)
    if match:
        return urllib.parse.unquote(match.group(1)).strip()
    text = text.strip("/")
    if "/" in text or "?" in text or "#" in text:
        raise ValueError("璞嗙摚鐢ㄦ埛 ID 鎴栦富椤甸摼鎺ユ牸寮忎笉姝ｇ‘")
    return text


def build_user_collection_url(user_id: str, status: str, start: int) -> str:
    if status not in {"collect", "wish"}:
        raise ValueError("status 鍙兘鏄?collect 鎴?wish")
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
        items.append(MediaItem(
            title=title,
            my_rating=my_rating,
            year=parse_year(intro),
            media_type="电影",
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


def crawl_user_collections(
    user_id_or_url: str,
    cookie: str = "",
    max_pages: int = 8,
    include_wish: bool = True,
    page_size: int = 15,
    fetcher: Callable[..., str] | None = None,
    sleep_seconds: float = 0.15,
) -> CrawlResult:
    user_id = normalize_douban_user_id(user_id_or_url)
    limited_pages = max(1, min(60, int(max_pages or 8)))
    fetch = fetcher or fetch_user_collection_page
    statuses = ["collect", "wish"] if include_wish else ["collect"]
    result = CrawlResult()
    seen: set[str] = set()
    empty_page_seen = False
    for status in statuses:
        for page_index in range(limited_pages):
            start = page_index * page_size
            try:
                page_html = fetch(user_id, status, start, cookie=cookie)
                page_items = parse_user_collection_html(page_html, status=status)
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
            except Exception as exc:
                result.pages_failed += 1
                message = str(exc)
                if cookie:
                    message = message.replace(cookie, redact_cookie(cookie))
                result.errors.append(f"{status} start={start}: {message}")
                break
            if sleep_seconds:
                time.sleep(sleep_seconds)
    if empty_page_seen:
        result.stopped_reason = "\u5df2\u5230\u8fbe\u7a7a\u767d\u5206\u9875"
    elif result.pages_failed:
        result.stopped_reason = "\u90e8\u5206\u5206\u9875\u6293\u53d6\u5931\u8d25"
    else:
        result.stopped_reason = "\u5df2\u8fbe\u5230\u9875\u6570\u4e0a\u9650"
    return result

