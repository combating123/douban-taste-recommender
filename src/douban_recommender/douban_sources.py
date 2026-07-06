from __future__ import annotations

import html
import json
import os
import re
import time
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from typing import Iterable

from .candidate_planner import CandidateQuery
from .io import extract_douban_id, parse_list
from .models import MediaItem
from .profiler import KNOWN_GENRES, TasteProfile

DOUBAN_EXPLORE_ENDPOINT = "https://movie.douban.com/j/new_search_subjects"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Referer": "https://movie.douban.com/explore",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


@dataclass
class CandidateFetchReport:
    items: list[MediaItem] = field(default_factory=list)
    successful_queries: int = 0
    failed_queries: int = 0
    errors: list[str] = field(default_factory=list)


def fetch_candidates_from_plan(
    plan: list[CandidateQuery],
    fetcher=None,
    sleep_seconds: float = 0.15,
    max_consecutive_failures: int = 10,
) -> CandidateFetchReport:
    fetch = fetcher or fetch_explore
    report = CandidateFetchReport()
    seen: set[str] = set()
    consecutive_failures = 0
    for query in plan:
        try:
            rows = fetch(tags=query.tags, sort=query.sort, start=query.start, limit=query.limit)
            report.successful_queries += 1
            consecutive_failures = 0
        except Exception as exc:
            report.failed_queries += 1
            report.errors.append(f"{query.channel} {query.tags} start={query.start}: {exc}")
            rows = []
            consecutive_failures += 1
        for row in rows:
            if not row.media_type or row.media_type == "电影":
                row.media_type = query.media_type
            row.source = row.source or f"douban_plan:{query.channel}:{query.tags}"
            key = row.douban_id or row.title
            if key and key not in seen:
                report.items.append(row)
                seen.add(key)
        if sleep_seconds:
            time.sleep(sleep_seconds)
        if max_consecutive_failures and consecutive_failures >= max_consecutive_failures and not report.items:
            report.errors.append(f"已提前停止：连续 {consecutive_failures} 个豆瓣候选查询失败，改用本地精选候选池。")
            break
    return report


def fetch_douban_candidates(
    profile: TasteProfile,
    include_movies: bool = True,
    include_series: bool = True,
    per_query: int = 20,
    max_queries: int = 14,
    sorts: Iterable[str] = ("U", "R"),
    sleep_seconds: float = 0.15,
) -> list[MediaItem]:
    queries = build_queries(profile, include_movies=include_movies, include_series=include_series, max_queries=max_queries)
    candidates: list[MediaItem] = []
    seen: set[str] = set()
    for tags in queries:
        for sort in sorts:
            try:
                rows = fetch_explore(tags=tags, sort=sort, start=0, limit=per_query)
            except Exception:
                rows = []
            for row in rows:
                key = row.douban_id or row.title
                if key and key not in seen:
                    candidates.append(row)
                    seen.add(key)
            if sleep_seconds:
                time.sleep(sleep_seconds)
    if include_movies:
        try:
            for row in fetch_top250(max_pages=2):
                key = row.douban_id or row.title
                if key and key not in seen:
                    candidates.append(row)
                    seen.add(key)
        except Exception:
            pass
    return candidates


def build_queries(profile: TasteProfile, include_movies: bool = True, include_series: bool = True, max_queries: int = 14) -> list[str]:
    bases: list[str] = []
    if include_movies:
        bases.append("电影")
    if include_series:
        bases.append("电视剧")

    terms: list[str] = []
    for value, _ in profile.top_positive("genre", 10):
        if value and value not in terms:
            terms.append(value)
    for value, _ in profile.top_positive("tag", 10):
        if value in KNOWN_GENRES and value not in terms:
            terms.append(value)
    for term in profile.manual_likes:
        if term and term not in terms:
            terms.append(term)

    fallback = ["剧情", "悬疑", "犯罪", "喜剧", "科幻", "纪录片", "动画"]
    for term in fallback:
        if term not in terms:
            terms.append(term)

    queries: list[str] = []
    for base in bases:
        queries.append(base)
        for term in terms[:6]:
            queries.append(f"{base},{term}")
        if len(terms) >= 2:
            queries.append(f"{base},{terms[0]},{terms[1]}")
        if len(terms) >= 3:
            queries.append(f"{base},{terms[0]},{terms[2]}")
    out: list[str] = []
    seen: set[str] = set()
    for q in queries:
        if q not in seen:
            out.append(q)
            seen.add(q)
        if len(out) >= max_queries:
            break
    return out


def fetch_explore(tags: str, sort: str = "U", start: int = 0, limit: int = 20, fetcher=None) -> list[MediaItem]:
    params = {
        "sort": sort,
        "range": "0,10",
        "tags": tags,
        "start": start,
    }
    url = DOUBAN_EXPLORE_ENDPOINT + "?" + urllib.parse.urlencode(params)
    fetch = fetcher or http_get
    payload = fetch(url)
    data = json.loads(payload.decode("utf-8"))
    if data.get("msg") and not data.get("data"):
        raise RuntimeError(f"豆瓣探索接口返回风控或错误：{data.get('msg')}")
    tag_list = parse_list(tags)
    media_type = "电视剧" if any(t in {"电视剧", "美剧", "英剧", "日剧", "韩剧", "国产剧", "港剧", "台剧"} for t in tag_list) else "电影"
    query_tags = [t for t in tag_list if t not in {"电影", "电视剧"}]
    out: list[MediaItem] = []
    for row in data.get("data", [])[:limit]:
        rate = parse_float(row.get("rate"))
        out.append(MediaItem(
            title=row.get("title") or "",
            douban_rating=rate,
            media_type=media_type,
            genres=[t for t in query_tags if t in KNOWN_GENRES],
            tags=query_tags,
            directors=[str(x) for x in row.get("directors") or []],
            casts=[str(x) for x in row.get("casts") or []],
            url=(row.get("url") or "").replace("\\/", "/"),
            douban_id=str(row.get("id") or extract_douban_id(row.get("url") or "")),
            cover=(row.get("cover") or "").replace("\\/", "/"),
            source=f"douban_explore:{tags}:sort={sort}",
            raw=row,
        ))
    return out


def fetch_top250(max_pages: int = 10) -> list[MediaItem]:
    out: list[MediaItem] = []
    seen: set[str] = set()
    for page in range(max_pages):
        start = page * 25
        url = f"https://movie.douban.com/top250?start={start}"
        try:
            text = http_get(url, accept_json=False).decode("utf-8", errors="ignore")
        except Exception:
            continue
        for block in re.findall(r'<div class="item">(.*?)</div>\s*</li>', text, flags=re.S):
            link = first_match(r'<a\s+href="([^"]+)"', block)
            title = first_match(r'<span class="title">(.*?)</span>', block)
            rating = first_match(r'<span class="rating_num"[^>]*>(.*?)</span>', block)
            quote = first_match(r'<span class="inq">(.*?)</span>', block)
            pic = first_match(r'<img[^>]+src="([^"]+)"', block)
            if not title:
                continue
            title = clean_html(title)
            key = extract_douban_id(link) or title
            if key in seen:
                continue
            seen.add(key)
            out.append(MediaItem(
                title=title,
                douban_rating=parse_float(clean_html(rating)),
                media_type="电影",
                url=link,
                douban_id=extract_douban_id(link),
                cover=pic,
                summary=clean_html(quote),
                source="douban_top250",
            ))
    return out


def fetch_url_candidates(urls: Iterable[str]) -> list[MediaItem]:
    out: list[MediaItem] = []
    for url in urls:
        url = str(url or "").strip()
        if not url:
            continue
        if "new_search_subjects" in url:
            parsed = urllib.parse.urlparse(url)
            qs = urllib.parse.parse_qs(parsed.query)
            tags = qs.get("tags", ["电影"])[0]
            sort = qs.get("sort", ["U"])[0]
            start = int(qs.get("start", [0])[0])
            out.extend(fetch_explore(tags=tags, sort=sort, start=start, limit=50))
        elif "top250" in url:
            out.extend(fetch_top250(max_pages=4))
        else:
            out.extend(fetch_generic_movie_links(url))
    return out


def fetch_generic_movie_links(url: str) -> list[MediaItem]:
    text = http_get(url, accept_json=False).decode("utf-8", errors="ignore")
    out: list[MediaItem] = []
    seen: set[str] = set()
    for match in re.finditer(r'href="(https://movie\.douban\.com/subject/(\d+)/[^"]*)"[^>]*>(.*?)</a>', text, flags=re.S):
        link, subject_id, inner = match.group(1), match.group(2), match.group(3)
        title = clean_html(inner)
        if not title or len(title) > 80 or subject_id in seen:
            continue
        seen.add(subject_id)
        out.append(MediaItem(title=title, url=link, douban_id=subject_id, source=f"douban_page:{url}"))
    return out


def parse_subject_detail_html(page_html: str, url: str = "") -> MediaItem:
    text = page_html or ""
    title = clean_html(
        first_match(r'<span[^>]+property=["\']v:itemreviewed["\'][^>]*>(.*?)</span>', text)
        or first_match(r'<meta[^>]+property=["\']og:title["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<title>(.*?)</title>', text).replace("(豆瓣)", "")
    )
    title = re.sub(r"\s*-\s*(电影|电视剧|动画|动漫)\s*$", "", title).strip()
    cover = html.unescape(
        first_match(r'<meta[^>]+property=["\']og:image["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<meta[^>]+itemprop=["\']image["\'][^>]+content=["\']([^"\']+)["\']', text)
        or first_match(r'<img[^>]+rel=["\']v:image["\'][^>]+src=["\']([^"\']+)["\']', text)
    )
    summary = clean_html(
        first_match(r'<span[^>]+property=["\']v:summary["\'][^>]*>(.*?)</span>', text)
        or first_match(r'<div[^>]+class=["\']related-info["\'][^>]*>.*?<span[^>]*>(.*?)</span>', text)
        or first_match(r'<section[^>]+class=["\']subject-intro["\'][^>]*>.*?<p[^>]*>(.*?)</p>', text)
        or _summary_from_og_description(first_match(r'<meta[^>]+property=["\']og:description["\'][^>]+content=["\']([^"\']+)["\']', text))
    )
    directors = [
        clean_html(value)
        for value in re.findall(r'<a[^>]+rel=["\']v:directedBy["\'][^>]*>(.*?)</a>', text, flags=re.S)
        if clean_html(value)
    ]
    casts = [
        clean_html(value)
        for value in re.findall(r'<a[^>]+rel=["\']v:starring["\'][^>]*>(.*?)</a>', text, flags=re.S)
        if clean_html(value)
    ]
    genres = [
        clean_html(value)
        for value in re.findall(r'<span[^>]+property=["\']v:genre["\'][^>]*>(.*?)</span>', text, flags=re.S)
        if clean_html(value)
    ]
    countries = parse_list(clean_html(first_match(r'制片国家/地区:</span>\s*([^<]+)<', text)))
    languages = parse_list(clean_html(first_match(r'语言:</span>\s*([^<]+)<', text)))
    year = None
    year_text = (
        first_match(r'property=["\']v:initialReleaseDate["\'][^>]+content=["\'](\d{4})', text)
        or first_match(r'property=["\']v:initialReleaseDate["\'][^>]*>\s*(\d{4})', text)
        or first_match(r'\((\d{4})\)', title)
    )
    if year_text:
        try:
            year = int(year_text)
        except ValueError:
            year = None
    return MediaItem(
        title=title,
        year=year,
        genres=genres,
        countries=countries,
        languages=languages,
        directors=directors,
        casts=casts,
        url=url,
        douban_id=extract_douban_id(url),
        cover=cover,
        summary=summary,
        source="douban_subject_detail",
    )


def merge_subject_detail(item: MediaItem, detail: MediaItem) -> MediaItem:
    if detail.title and not item.title:
        item.title = detail.title
    if detail.year and not item.year:
        item.year = detail.year
    if detail.cover and not item.cover:
        item.cover = detail.cover
    if detail.summary and not item.summary:
        item.summary = detail.summary
    for field in ["genres", "countries", "languages", "directors", "casts"]:
        current = list(getattr(item, field) or [])
        for value in getattr(detail, field) or []:
            if value and value not in current:
                current.append(value)
        setattr(item, field, current)
    if detail.douban_id and not item.douban_id:
        item.douban_id = detail.douban_id
    if detail.url and not item.url:
        item.url = detail.url
    return item


def enrich_media_items(
    items: list[MediaItem],
    fetcher=None,
    limit: int = 12,
    sleep_seconds: float = 0.05,
) -> list[MediaItem]:
    fetch = fetcher or (lambda url: http_get(url, accept_json=False))
    enriched = 0
    for item in items:
        if enriched >= limit:
            break
        urls = subject_detail_urls(item)
        if not urls:
            continue
        if item.summary and item.directors and item.casts and item.genres and item.cover:
            continue
        for url in urls:
            try:
                payload = fetch(url)
                html_text = payload.decode("utf-8", errors="ignore") if isinstance(payload, bytes) else str(payload)
                detail = parse_subject_detail_html(html_text, url=url)
                if not detail.cover and not detail.summary and detail.title in {"", "豆瓣"}:
                    continue
                merge_subject_detail(item, detail)
                enriched += 1
                break
            except Exception:
                continue
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return items


def http_get(url: str, accept_json: bool = True, timeout: int = 12) -> bytes:
    headers = dict(DEFAULT_HEADERS)
    if not accept_json:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
        if "m.douban.com" in url:
            headers["Referer"] = "https://m.douban.com/movie/"
            headers["User-Agent"] = "Mozilla/5.0 (iPhone; CPU iPhone OS 16_0 like Mac OS X) AppleWebKit/605.1.15 Mobile/15E148"
    request = urllib.request.Request(url, headers=headers)
    opener = build_url_opener()
    with opener.open(request, timeout=timeout) as response:
        return response.read()


def configured_proxy_url() -> str:
    for name in ("DOUBAN_RECOMMENDER_HTTP_PROXY", "HTTPS_PROXY", "HTTP_PROXY", "ALL_PROXY"):
        value = os.environ.get(name) or os.environ.get(name.lower())
        if value:
            return value.strip()
    return ""


def build_url_opener():
    proxy = configured_proxy_url()
    if not proxy:
        return urllib.request.build_opener()
    return urllib.request.build_opener(urllib.request.ProxyHandler({
        "http": proxy,
        "https": proxy,
    }))


def subject_detail_urls(item: MediaItem) -> list[str]:
    subject_id = item.douban_id or extract_douban_id(item.url)
    urls: list[str] = []
    if subject_id:
        mobile = f"https://m.douban.com/movie/subject/{subject_id}/"
        desktop = f"https://movie.douban.com/subject/{subject_id}/"
        for url in (mobile, desktop):
            if url not in urls:
                urls.append(url)
    if item.url and "movie.douban.com/subject/" in item.url and item.url not in urls:
        urls.append(item.url)
    return urls


def _summary_from_og_description(value: str) -> str:
    text = html.unescape(value or "")
    m = re.search(r"简介[:：]\s*(.*)", text, flags=re.S)
    return m.group(1).strip() if m else text.strip()


def first_match(pattern: str, text: str) -> str:
    m = re.search(pattern, text, flags=re.S)
    return m.group(1).strip() if m else ""


def clean_html(text: str | None) -> str:
    if not text:
        return ""
    text = re.sub(r"<.*?>", "", text, flags=re.S)
    return html.unescape(text).strip()


def parse_float(value: object) -> float | None:
    if value is None:
        return None
    m = re.search(r"\d+(?:\.\d+)?", str(value))
    return float(m.group(0)) if m else None
