from __future__ import annotations

import html
import json
import re
import time
import urllib.parse
import urllib.request
from typing import Iterable

from .io import extract_douban_id, parse_list
from .models import MediaItem
from .profiler import KNOWN_GENRES, TasteProfile

DOUBAN_EXPLORE_ENDPOINT = "https://movie.douban.com/j/new_search_subjects"
DEFAULT_HEADERS = {
    "User-Agent": "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 Chrome/126 Safari/537.36",
    "Referer": "https://movie.douban.com/explore",
    "Accept": "application/json,text/html;q=0.9,*/*;q=0.8",
}


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


def fetch_explore(tags: str, sort: str = "U", start: int = 0, limit: int = 20) -> list[MediaItem]:
    params = {
        "sort": sort,
        "range": "0,10",
        "tags": tags,
        "start": start,
    }
    url = DOUBAN_EXPLORE_ENDPOINT + "?" + urllib.parse.urlencode(params)
    payload = http_get(url)
    data = json.loads(payload.decode("utf-8"))
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


def http_get(url: str, accept_json: bool = True, timeout: int = 12) -> bytes:
    headers = dict(DEFAULT_HEADERS)
    if not accept_json:
        headers["Accept"] = "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8"
    request = urllib.request.Request(url, headers=headers)
    with urllib.request.urlopen(request, timeout=timeout) as response:
        return response.read()


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
