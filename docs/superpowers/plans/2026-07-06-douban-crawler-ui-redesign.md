# Douban Crawler and Humanized UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a local-first Douban crawler and a calmer three-step recommendation UI so the user can fetch personal Douban ratings with an optional Cookie and get understandable movie/series recommendations without external export tools.

**Architecture:** Keep the current dependency-free Python HTTP server, but split responsibilities into focused modules: `crawler.py` fetches/parses Douban pages, `serialization.py` converts `MediaItem` to/from JSON, `web_ui.py` owns the browser UI, and `web.py` only routes API requests. Recommendation logic remains in `profiler.py`, `douban_sources.py`, and `recommender.py`.

**Tech Stack:** Python 3.14 standard library only; `http.server` for local web; `urllib` for Douban requests; `re`/`html` for resilient HTML parsing; `unittest` for tests; no frontend framework.

## Global Constraints

- Do not automate Douban login, bypass verification, or solve CAPTCHA.
- Do not persist Cookie to disk.
- Do not include Cookie in server logs, API responses, generated reports, README examples, or error messages.
- Continue using the current no-dependency local web server.
- Prefer public pages when Cookie is empty; use Cookie only as an optional request header.
- Keep UI copy in Simplified Chinese and focused on user actions.
- Keep crawler limits conservative: default `max_pages` is `8`; allowed range is `1..60`.
- Preserve old CSV workflow and sample data workflow.
- Use TDD: each feature task writes a failing test, verifies the failure, implements the minimal code, then verifies passing tests.

---

## Feasibility and Human-Centered Product Analysis

### Feasibility Findings

1. **Public Douban user collection pages are feasible to parse.** The pages contain repeated item blocks with title links, rating CSS classes such as `rating5-t`, dates, intro text, and comments. The parser should be tolerant: if directors/casts/genres are incomplete, still return a useful `MediaItem`.
2. **Cookie mode is feasible and should be optional.** Cookie copying is realistic for desktop users, but it is intimidating. The UI should present it as “如果公开数据不够，再粘贴 Cookie,” not as a required first step.
3. **A full browser automation crawler is not worth the complexity.** It would add dependencies, login fragility, and UI confusion. The best product is a simple local HTTP crawler with clear limits and clear failure messages.
4. **The current UI overload is the biggest usability issue.** The most human-friendly version is a wizard: connect Douban → confirm taste → read recommendations. Advanced inputs belong behind collapsible panels.
5. **The recommendation engine already works well enough.** The useful upgrade is not a new algorithm; it is better data ingestion, automatic “already watched” exclusion, and better explanations.

### Product Decision

Build a **three-step local assistant**:

1. **连接豆瓣**: user enters profile URL/ID, optionally expands Cookie tutorial.
2. **确认口味**: user edits short “喜欢/不喜欢” chips and chooses movie/series scope.
3. **查看推荐**: user sees compact cards first, opens details only when needed.

This is the most usable version because it gives the user one decision at a time, avoids demanding Cookie upfront, keeps privacy promises visible, and keeps recommendation explanations short by default.

---

## File Structure

- Create: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\serialization.py`
  - Converts `MediaItem` to/from safe JSON dictionaries.
  - Redacts Cookie-like text for error/log safety.
- Create: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py`
  - Normalizes Douban user input.
  - Builds collection URLs.
  - Fetches collection pages with optional Cookie.
  - Parses collection HTML into `MediaItem` objects.
  - Crawls `collect` and optional `wish` pagination.
- Create: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web_ui.py`
  - Owns the new three-step HTML/CSS/JS UI.
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web.py`
  - Imports `INDEX_HTML` from `web_ui.py`.
  - Adds `POST /api/crawl-douban`.
  - Lets `POST /api/recommend` accept `rated_items` JSON.
- Modify: `C:\Users\11616\douban-taste-recommender\README.md`
  - Adds direct crawler usage and Cookie tutorial.
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_serialization.py`
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_crawler.py`
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_web_api.py`
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_ui_html.py`
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_readme.py`

---

### Task 1: Safe MediaItem JSON Serialization

**Files:**
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_serialization.py`
- Create: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\serialization.py`

**Interfaces:**
- Consumes: `douban_recommender.models.MediaItem`
- Produces:
  - `media_item_to_dict(item: MediaItem) -> dict[str, object]`
  - `media_item_from_dict(data: dict[str, object]) -> MediaItem`
  - `redact_cookie(value: str) -> str`

- [ ] **Step 1: Write the failing serialization tests**

Create `C:\Users\11616\douban-taste-recommender\tests\test_serialization.py`:

```python
import unittest

from douban_recommender.models import MediaItem
from douban_recommender.serialization import media_item_from_dict, media_item_to_dict, redact_cookie


class SerializationTests(unittest.TestCase):
    def test_media_item_round_trips_through_json_dict(self):
        item = MediaItem(
            title="隐秘的角落",
            my_rating=5,
            douban_rating=8.8,
            year=2020,
            media_type="电视剧",
            genres=["剧情", "悬疑", "犯罪"],
            countries=["中国大陆"],
            directors=["辛爽"],
            casts=["秦昊", "王景春"],
            tags=["看过", "现实主义"],
            url="https://movie.douban.com/subject/33404425/",
            douban_id="33404425",
            cover="https://img.example/poster.jpg",
            summary="孩子、家庭与犯罪的阴影",
            source="douban_user:collect",
        )

        payload = media_item_to_dict(item)
        restored = media_item_from_dict(payload)

        self.assertEqual(restored.title, "隐秘的角落")
        self.assertEqual(restored.my_rating, 5)
        self.assertEqual(restored.douban_rating, 8.8)
        self.assertEqual(restored.genres, ["剧情", "悬疑", "犯罪"])
        self.assertEqual(restored.tags, ["看过", "现实主义"])
        self.assertEqual(restored.douban_id, "33404425")

    def test_redact_cookie_removes_sensitive_values(self):
        raw = "bid=abc123; dbcl2=\"999:user\"; ck=secret; push_noty_num=0"

        redacted = redact_cookie(raw)

        self.assertNotIn("abc123", redacted)
        self.assertNotIn("secret", redacted)
        self.assertIn("bid=<redacted>", redacted)
        self.assertIn("ck=<redacted>", redacted)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_serialization -v
```

Expected: FAIL or ERROR because `douban_recommender.serialization` does not exist.

- [ ] **Step 3: Create the minimal serialization implementation**

Create `C:\Users\11616\douban-taste-recommender\src\douban_recommender\serialization.py`:

```python
from __future__ import annotations

from typing import Any

from .models import MediaItem


MEDIA_ITEM_FIELDS = [
    "title",
    "my_rating",
    "douban_rating",
    "vote_count",
    "year",
    "media_type",
    "genres",
    "countries",
    "languages",
    "directors",
    "casts",
    "tags",
    "url",
    "douban_id",
    "cover",
    "summary",
    "source",
]


def media_item_to_dict(item: MediaItem) -> dict[str, object]:
    return {field: getattr(item, field) for field in MEDIA_ITEM_FIELDS}


def media_item_from_dict(data: dict[str, Any]) -> MediaItem:
    clean = {field: data.get(field) for field in MEDIA_ITEM_FIELDS}
    for list_field in ("genres", "countries", "languages", "directors", "casts", "tags"):
        value = clean.get(list_field)
        if isinstance(value, list):
            clean[list_field] = [str(part).strip() for part in value if str(part).strip()]
        elif isinstance(value, str) and value.strip():
            clean[list_field] = [value.strip()]
        else:
            clean[list_field] = []
    return MediaItem(**clean)


def redact_cookie(value: str) -> str:
    parts = []
    for part in str(value or "").split(";"):
        text = part.strip()
        if not text:
            continue
        if "=" in text:
            name = text.split("=", 1)[0].strip()
            parts.append(f"{name}=<redacted>")
        else:
            parts.append("<redacted>")
    return "; ".join(parts)
```

- [ ] **Step 4: Run tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_serialization -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_serialization.py src/douban_recommender/serialization.py
git commit -m "feat: add safe media item serialization"
```

---

### Task 2: Douban User Collection URL and HTML Parser

**Files:**
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_crawler.py`
- Create: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py`

**Interfaces:**
- Consumes:
  - `douban_recommender.models.MediaItem`
  - `douban_recommender.io.extract_douban_id`
- Produces:
  - `normalize_douban_user_id(value: str) -> str`
  - `build_user_collection_url(user_id: str, status: str, start: int) -> str`
  - `parse_user_collection_html(page_html: str, status: str) -> list[MediaItem]`

- [ ] **Step 1: Write the failing crawler parser tests**

Create `C:\Users\11616\douban-taste-recommender\tests\test_crawler.py` with the initial parser tests:

```python
import unittest

from douban_recommender.crawler import (
    build_user_collection_url,
    normalize_douban_user_id,
    parse_user_collection_html,
)


COLLECT_HTML = """
<html><body>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/33404425/">
        <img alt="隐秘的角落" src="https://img.example/cover.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/33404425/"><em>隐秘的角落</em></a>
        </li>
        <li class="intro">2020 / 中国大陆 / 剧情 悬疑 犯罪 / 辛爽 / 秦昊 王景春</li>
        <li>
          <span class="rating5-t"></span>
          <span class="date">2024-01-01</span>
        </li>
        <li><span class="comment">孩子、家庭与犯罪的阴影</span></li>
      </ul>
    </div>
  </div>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/30468961/">
        <img alt="想见你" src="https://img.example/want.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/30468961/"><em>想见你</em></a>
        </li>
        <li class="intro">2019 / 中国台湾 / 爱情 悬疑 奇幻 / 黄天仁 / 柯佳嬿 许光汉</li>
        <li><span class="date">2024-02-02</span></li>
      </ul>
    </div>
  </div>
</body></html>
"""


class CrawlerParserTests(unittest.TestCase):
    def test_normalize_douban_user_id_accepts_plain_id(self):
        self.assertEqual(normalize_douban_user_id("moviefan123"), "moviefan123")

    def test_normalize_douban_user_id_extracts_people_url(self):
        url = "https://www.douban.com/people/moviefan123/collect"
        self.assertEqual(normalize_douban_user_id(url), "moviefan123")

    def test_build_user_collection_url_for_collect(self):
        url = build_user_collection_url("moviefan123", "collect", 30)
        self.assertEqual(url, "https://movie.douban.com/people/moviefan123/collect?start=30&sort=time&rating=all&filter=all&mode=grid")

    def test_parse_user_collection_html_extracts_title_rating_and_url(self):
        items = parse_user_collection_html(COLLECT_HTML, status="collect")

        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.title, "隐秘的角落")
        self.assertEqual(first.my_rating, 5)
        self.assertEqual(first.year, 2020)
        self.assertEqual(first.media_type, "电影")
        self.assertIn("剧情", first.genres)
        self.assertIn("悬疑", first.genres)
        self.assertIn("犯罪", first.genres)
        self.assertIn("中国大陆", first.countries)
        self.assertIn("看过", first.tags)
        self.assertEqual(first.douban_id, "33404425")
        self.assertEqual(first.cover, "https://img.example/cover.jpg")
        self.assertEqual(first.summary, "孩子、家庭与犯罪的阴影")

    def test_parse_user_collection_html_handles_no_rating(self):
        items = parse_user_collection_html(COLLECT_HTML, status="wish")

        second = items[1]
        self.assertEqual(second.title, "想见你")
        self.assertIsNone(second.my_rating)
        self.assertIn("想看", second.tags)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_crawler -v
```

Expected: FAIL or ERROR because `douban_recommender.crawler` does not exist.

- [ ] **Step 3: Create parser implementation**

Create `C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py` with URL and parser functions:

```python
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
    blocks = re.findall(r'<div\s+class="item">(.*?)</div>\s*</div>\s*</div>|<div\s+class="item">(.*?)</div>\s*</li>', page_html, flags=re.S)
    flattened = [first or second for first, second in blocks]
    if not flattened:
        flattened = re.findall(r'<div\s+class="item">(.*?)(?=<div\s+class="item">|</body>|</html>)', page_html, flags=re.S)
    items: list[MediaItem] = []
    for block in flattened:
        url = first_match(r'href="(https://movie\.douban\.com/subject/\d+/[^"]*)"', block)
        title = clean_html(first_match(r"<em>(.*?)</em>", block)) or clean_html(first_match(r'alt="([^"]+)"', block))
        if not title or not url:
            continue
        intro = clean_html(first_match(r'<li\s+class="intro">(.*?)</li>', block))
        comment = clean_html(first_match(r'<span\s+class="comment">(.*?)</span>', block))
        rating_match = re.search(r"rating(\d)-t", block)
        my_rating = float(rating_match.group(1)) if rating_match else None
        cover = html.unescape(first_match(r'<img[^>]+src="([^"]+)"', block))
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
            url=html.unescape(url),
            douban_id=extract_douban_id(url),
            cover=cover,
            summary=comment,
            source=f"douban_user:{status}",
            raw={"intro": intro},
        ))
    return items


def split_people_from_intro(parts: list[str]) -> tuple[list[str], list[str]]:
    if len(parts) < 4:
        return [], []
    directors = [name.strip() for name in re.split(r"\s+", parts[-2]) if name.strip()]
    casts = [name.strip() for name in re.split(r"\s+", parts[-1]) if name.strip()]
    return directors[:4], casts[:8]


def first_match(pattern: str, text: str) -> str:
    match = re.search(pattern, text, flags=re.S)
    return match.group(1).strip() if match else ""


def clean_html(value: str) -> str:
    text = re.sub(r"<.*?>", "", value or "", flags=re.S)
    return html.unescape(text).strip()
```

- [ ] **Step 4: Run parser tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_crawler -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_crawler.py src/douban_recommender/crawler.py
git commit -m "feat: parse Douban user collection pages"
```

---

### Task 3: Douban Crawl Orchestration with Optional Cookie

**Files:**
- Modify: `C:\Users\11616\douban-taste-recommender\tests\test_crawler.py`
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py`

**Interfaces:**
- Consumes:
  - `normalize_douban_user_id(value: str) -> str`
  - `build_user_collection_url(user_id: str, status: str, start: int) -> str`
  - `parse_user_collection_html(page_html: str, status: str) -> list[MediaItem]`
- Produces:
  - `fetch_user_collection_page(user_id: str, status: str, start: int, cookie: str = "", timeout: int = 12) -> str`
  - `crawl_user_collections(user_id_or_url: str, cookie: str = "", max_pages: int = 8, include_wish: bool = True, page_size: int = 15, fetcher: Callable[..., str] | None = None, sleep_seconds: float = 0.15) -> CrawlResult`

- [ ] **Step 1: Add failing crawl orchestration tests**

Append to `CrawlerParserTests` in `C:\Users\11616\douban-taste-recommender\tests\test_crawler.py`:

```python
    def test_crawl_user_collections_uses_collect_and_wish_until_empty_page(self):
        from douban_recommender.crawler import crawl_user_collections

        calls = []

        def fake_fetcher(user_id, status, start, cookie="", timeout=12):
            calls.append((user_id, status, start, cookie))
            if start == 0:
                return COLLECT_HTML
            return "<html><body></body></html>"

        result = crawl_user_collections(
            "https://www.douban.com/people/moviefan123/",
            cookie="bid=secret",
            max_pages=2,
            include_wish=True,
            fetcher=fake_fetcher,
            sleep_seconds=0,
        )

        self.assertEqual(result.pages_ok, 4)
        self.assertEqual(result.pages_failed, 0)
        self.assertGreaterEqual(len(result.items), 4)
        self.assertEqual(calls[0], ("moviefan123", "collect", 0, "bid=secret"))
        self.assertEqual(calls[2], ("moviefan123", "wish", 0, "bid=secret"))
        self.assertEqual(result.stopped_reason, "已到达空白分页")

    def test_crawl_user_collections_redacts_cookie_from_errors(self):
        from douban_recommender.crawler import crawl_user_collections

        def failing_fetcher(user_id, status, start, cookie="", timeout=12):
            raise RuntimeError(f"request failed with {cookie}")

        result = crawl_user_collections(
            "moviefan123",
            cookie="bid=secret-cookie-value; ck=hidden",
            max_pages=1,
            include_wish=False,
            fetcher=failing_fetcher,
            sleep_seconds=0,
        )

        joined = "\n".join(result.errors)
        self.assertEqual(result.pages_failed, 1)
        self.assertNotIn("secret-cookie-value", joined)
        self.assertNotIn("hidden", joined)
        self.assertIn("<redacted>", joined)
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_crawler -v
```

Expected: FAIL or ERROR because `crawl_user_collections` is not defined.

- [ ] **Step 3: Add fetch and crawl functions**

Append these functions to `C:\Users\11616\douban-taste-recommender\src\douban_recommender\crawler.py`:

```python

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
                    key = item.douban_id or item.title
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
        result.stopped_reason = "已到达空白分页"
    elif result.pages_failed:
        result.stopped_reason = "部分分页抓取失败"
    else:
        result.stopped_reason = "已达到页数上限"
    return result
```

- [ ] **Step 4: Run crawler tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_crawler -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_crawler.py src/douban_recommender/crawler.py
git commit -m "feat: crawl Douban collections with optional cookie"
```

---

### Task 4: Web API for Crawling and JSON-Based Recommendations

**Files:**
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_web_api.py`
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web.py`

**Interfaces:**
- Consumes:
  - `crawl_user_collections(...) -> CrawlResult`
  - `media_item_to_dict(item: MediaItem) -> dict[str, object]`
  - `media_item_from_dict(data: dict[str, object]) -> MediaItem`
- Produces:
  - `POST /api/crawl-douban`
  - `POST /api/recommend` accepts `rated_items: list[dict]`

- [ ] **Step 1: Write failing web API tests**

Create `C:\Users\11616\douban-taste-recommender\tests\test_web_api.py`:

```python
import json
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer

from douban_recommender.crawler import CrawlResult
from douban_recommender.models import MediaItem
from douban_recommender.web import Handler
import douban_recommender.web as web_module


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post_json(self, path, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

    def test_crawl_api_returns_items_and_never_echoes_cookie(self):
        original = web_module.crawl_user_collections

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            return CrawlResult(
                items=[
                    MediaItem(
                        title="隐秘的角落",
                        my_rating=5,
                        media_type="电视剧",
                        genres=["剧情", "悬疑", "犯罪"],
                        url="https://movie.douban.com/subject/33404425/",
                        douban_id="33404425",
                        source="douban_user:collect",
                    )
                ],
                pages_ok=1,
                pages_failed=0,
                stopped_reason="已到达空白分页",
            )

        web_module.crawl_user_collections = fake_crawl
        try:
            response = self.post_json("/api/crawl-douban", {
                "user_id_or_url": "moviefan123",
                "cookie": "bid=secret-cookie-value; ck=hidden",
                "max_pages": 1,
                "include_wish": True,
            })
        finally:
            web_module.crawl_user_collections = original

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertEqual(response["counts"]["items"], 1)
        self.assertEqual(response["items"][0]["title"], "隐秘的角落")
        self.assertNotIn("secret-cookie-value", serialized)
        self.assertNotIn("hidden", serialized)

    def test_recommend_api_accepts_json_rated_items(self):
        response = self.post_json("/api/recommend", {
            "rated_items": [
                {
                    "title": "隐秘的角落",
                    "my_rating": 5,
                    "media_type": "电视剧",
                    "genres": ["剧情", "悬疑", "犯罪"],
                    "tags": ["看过"],
                    "douban_id": "33404425",
                }
            ],
            "candidates_csv": "title,media_type,douban_rating,genres,tags\\n新片,电影,8.1,剧情 / 犯罪,现实主义\\n",
            "fetch_douban": False,
            "use_sample_candidates": False,
            "include_movies": True,
            "include_series": True,
            "like_terms": "犯罪,现实主义",
            "dislike_terms": "甜宠",
            "limit": 5,
        })

        self.assertEqual(response["counts"]["rated"], 1)
        self.assertEqual(response["results"][0]["title"], "新片")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_web_api -v
```

Expected: FAIL because `/api/crawl-douban` is not routed and `rated_items` JSON is not accepted.

- [ ] **Step 3: Modify imports in web.py**

In `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web.py`, add:

```python
from .crawler import crawl_user_collections
from .serialization import media_item_from_dict, media_item_to_dict
```

- [ ] **Step 4: Add route for crawl API**

In `Handler.do_POST`, replace the single-path guard with this logic:

```python
        try:
            length = int(self.headers.get("Content-Length", "0"))
            payload = json.loads(self.rfile.read(length).decode("utf-8"))
            if path == "/api/recommend":
                data = self.handle_recommend(payload)
            elif path == "/api/crawl-douban":
                data = self.handle_crawl_douban(payload)
            else:
                self.send_json({"error": "not found"}, status=404)
                return
            self.send_json(data)
        except Exception as exc:
            self.send_json({"error": str(exc)}, status=500)
```

- [ ] **Step 5: Add handler method for crawl API**

Add this method inside `Handler`:

```python
    def handle_crawl_douban(self, payload: dict) -> dict:
        result = crawl_user_collections(
            user_id_or_url=payload.get("user_id_or_url") or "",
            cookie=payload.get("cookie") or "",
            max_pages=max(1, min(60, int(payload.get("max_pages") or 8))),
            include_wish=bool(payload.get("include_wish", True)),
        )
        return {
            "items": [media_item_to_dict(item) for item in result.items],
            "counts": {
                "items": len(result.items),
                "pages_ok": result.pages_ok,
                "pages_failed": result.pages_failed,
            },
            "errors": result.errors,
            "stopped_reason": result.stopped_reason,
        }
```

- [ ] **Step 6: Allow JSON rated items in recommendation API**

In `Handler.handle_recommend`, replace the current `rated = ...` assignment with:

```python
        rated_items_payload = payload.get("rated_items") or []
        if rated_items_payload:
            rated = [media_item_from_dict(item) for item in rated_items_payload if isinstance(item, dict)]
        else:
            ratings_csv = payload.get("ratings_csv") or ""
            rated = load_media_csv_from_text(ratings_csv, kind="ratings") if ratings_csv.strip() else load_media_csv(SAMPLE_RATINGS, kind="ratings")
```

- [ ] **Step 7: Run web API tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_web_api -v
```

Expected: `OK`.

- [ ] **Step 8: Run existing smoke test**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m douban_recommender.cli --ratings sample_data\ratings_sample.csv --candidates sample_data\candidates_sample.csv --limit 3 --output output\api_regression.html
```

Expected: exit code `0` and output includes `已生成`.

- [ ] **Step 9: Commit**

Run:

```powershell
git add tests/test_web_api.py src/douban_recommender/web.py
git commit -m "feat: add Douban crawl and JSON recommendation APIs"
```

---

### Task 5: Three-Step Humanized UI

**Files:**
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_ui_html.py`
- Create: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web_ui.py`
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web.py`

**Interfaces:**
- Consumes:
  - `POST /api/crawl-douban`
  - `POST /api/recommend`
- Produces:
  - `INDEX_HTML: str`
  - Browser functions: `renderStepNav`, `renderCrawlerPanel`, `renderTastePanel`, `renderRecommendations`, `renderCookieGuide`

- [ ] **Step 1: Write failing UI structure tests**

Create `C:\Users\11616\douban-taste-recommender\tests\test_ui_html.py`:

```python
import unittest

from douban_recommender.web_ui import INDEX_HTML


class UiHtmlTests(unittest.TestCase):
    def test_ui_uses_three_clear_steps(self):
        self.assertIn("第一步：连接豆瓣", INDEX_HTML)
        self.assertIn("第二步：确认口味", INDEX_HTML)
        self.assertIn("第三步：查看推荐", INDEX_HTML)

    def test_ui_contains_cookie_tutorial_and_privacy_copy(self):
        self.assertIn("Cookie 教程", INDEX_HTML)
        self.assertIn("Cookie 只用于本机请求豆瓣页面", INDEX_HTML)
        self.assertIn("不会保存到磁盘", INDEX_HTML)

    def test_ui_contains_required_render_functions(self):
        for name in [
            "renderStepNav",
            "renderCrawlerPanel",
            "renderTastePanel",
            "renderRecommendations",
            "renderCookieGuide",
        ]:
            self.assertIn(f"function {name}", INDEX_HTML)

    def test_recommendation_cards_are_expandable(self):
        self.assertIn("<details", INDEX_HTML)
        self.assertIn("展开详情", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_ui_html -v
```

Expected: FAIL or ERROR because `douban_recommender.web_ui` does not exist.

- [ ] **Step 3: Create the UI module**

Create `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web_ui.py` with this complete minimal UI. It intentionally favors clarity over dense controls:

```python
from __future__ import annotations

INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>豆瓣口味影视推荐器</title>
  <style>
    :root { --bg:#f6f7fb; --panel:#ffffff; --text:#172033; --muted:#667085; --line:#e5e7eb; --green:#16a34a; --green-bg:#ecfdf3; --blue:#2563eb; --orange:#ea580c; }
    * { box-sizing:border-box; }
    body { margin:0; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Microsoft YaHei",sans-serif; background:var(--bg); color:var(--text); }
    .shell { max-width:1100px; margin:0 auto; padding:28px 18px 80px; }
    .hero { display:flex; justify-content:space-between; gap:18px; align-items:flex-start; margin-bottom:18px; }
    h1 { margin:0 0 8px; font-size:34px; letter-spacing:-.4px; }
    .lead { margin:0; color:var(--muted); line-height:1.7; max-width:760px; }
    .privacy { padding:10px 12px; border-radius:999px; background:var(--green-bg); color:#166534; font-weight:700; white-space:nowrap; }
    .steps { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin:18px 0; }
    .step { border:1px solid var(--line); background:var(--panel); border-radius:18px; padding:14px; color:var(--muted); }
    .step.active { border-color:#86efac; box-shadow:0 0 0 4px var(--green-bg); color:var(--text); }
    .step b { display:block; margin-bottom:4px; color:var(--text); }
    .grid { display:grid; grid-template-columns:minmax(300px,390px) 1fr; gap:16px; align-items:start; }
    .panel { background:var(--panel); border:1px solid var(--line); border-radius:22px; padding:18px; box-shadow:0 14px 35px rgba(15,23,42,.06); }
    .panel h2 { margin:0 0 6px; }
    .hint { color:var(--muted); line-height:1.65; font-size:14px; }
    label { display:block; font-weight:800; margin:14px 0 7px; }
    input[type=text], input[type=number], textarea { width:100%; border:1px solid var(--line); border-radius:14px; padding:12px; font:inherit; background:#fff; color:var(--text); }
    textarea { min-height:82px; resize:vertical; }
    .row { display:grid; grid-template-columns:1fr 1fr; gap:10px; }
    .actions { display:flex; flex-wrap:wrap; gap:10px; margin-top:14px; }
    button { border:0; border-radius:14px; padding:11px 14px; font-weight:900; cursor:pointer; background:var(--green); color:white; }
    button.secondary { background:#eef2ff; color:#3730a3; }
    button.ghost { background:#fff; color:var(--text); border:1px solid var(--line); }
    button:disabled { opacity:.55; cursor:not-allowed; }
    details { border:1px solid var(--line); border-radius:16px; padding:12px; background:#fff; margin-top:12px; }
    summary { cursor:pointer; font-weight:800; }
    .mini-list { margin:10px 0 0 20px; color:var(--muted); line-height:1.8; }
    .status { margin-top:12px; color:var(--muted); white-space:pre-wrap; line-height:1.6; }
    .statbar { display:grid; grid-template-columns:repeat(auto-fit,minmax(120px,1fr)); gap:10px; margin-top:12px; }
    .stat { background:#f8fafc; border:1px solid var(--line); border-radius:16px; padding:12px; }
    .stat b { display:block; font-size:20px; color:var(--text); }
    .empty { border:1px dashed var(--line); border-radius:18px; padding:28px; text-align:center; color:var(--muted); }
    .card { background:#fff; border:1px solid var(--line); border-radius:20px; padding:16px; margin:12px 0; }
    .card-top { display:flex; gap:12px; justify-content:space-between; align-items:flex-start; }
    .score { background:var(--green-bg); color:#166534; padding:6px 10px; border-radius:999px; font-weight:900; white-space:nowrap; }
    .meta { display:flex; flex-wrap:wrap; gap:7px; color:var(--muted); font-size:13px; margin:8px 0; }
    .meta span { background:#f8fafc; border:1px solid var(--line); padding:4px 8px; border-radius:999px; }
    .reasons { margin:8px 0 0 18px; line-height:1.65; }
    .warn { color:var(--orange); }
    .link { color:var(--blue); text-decoration:none; font-weight:800; }
    .hidden { display:none; }
    @media(max-width:880px) { .hero { display:block; } .privacy { display:inline-block; margin-top:12px; } .grid { grid-template-columns:1fr; } .steps { grid-template-columns:1fr; } .row { grid-template-columns:1fr; } }
  </style>
</head>
<body>
  <main class="shell">
    <section class="hero">
      <div>
        <h1>豆瓣口味影视推荐器</h1>
        <p class="lead">先连接豆瓣，再确认口味，最后看推荐。Cookie 是可选项：公开数据够用就不用填。</p>
      </div>
      <div class="privacy">本地运行，不保存 Cookie</div>
    </section>
    <nav id="stepNav" class="steps"></nav>
    <section class="grid">
      <div id="leftPanel" class="panel"></div>
      <div id="rightPanel" class="panel"></div>
    </section>
  </main>
<script>
const state = { step: 1, ratedItems: [], recommendations: [], profile: null, counts: null };
const $ = (id) => document.getElementById(id);
function esc(value) { return String(value ?? "").replace(/[&<>"']/g, ch => ({ "&":"&amp;", "<":"&lt;", ">":"&gt;", "\"":"&quot;", "'":"&#39;" }[ch])); }
function setStatus(text) { const el = document.getElementById("status"); if (el) el.textContent = text || ""; }
function renderStepNav() {
  const steps = [
    ["第一步：连接豆瓣", "输入 ID，公开抓取；需要时再填 Cookie"],
    ["第二步：确认口味", "用短句告诉我喜欢和不喜欢什么"],
    ["第三步：查看推荐", "先看摘要，想深挖再展开详情"]
  ];
  $("stepNav").innerHTML = steps.map((s, i) => `<div class="step ${state.step === i + 1 ? "active" : ""}"><b>${s[0]}</b>${s[1]}</div>`).join("");
}
function renderCookieGuide() {
  return `<details><summary>Cookie 教程</summary>
    <ol class="mini-list">
      <li>打开浏览器并登录豆瓣。</li>
      <li>进入 https://movie.douban.com/。</li>
      <li>按 F12 打开开发者工具，进入 Network / 网络。</li>
      <li>刷新页面，点击任意 movie.douban.com 或 www.douban.com 请求。</li>
      <li>在 Headers / 标头里找到 Request Headers。</li>
      <li>复制 Cookie: 后面的整段内容，粘贴到这里。</li>
    </ol>
    <p class="hint">Cookie 只用于本机请求豆瓣页面，不会保存到磁盘，也不会出现在推荐报告里。</p>
  </details>`;
}
function renderCrawlerPanel() {
  $("leftPanel").innerHTML = `<h2>第一步：连接豆瓣</h2>
    <p class="hint">填豆瓣用户 ID 或主页链接。Cookie 可不填；如果抓不到完整评分，再按教程复制 Cookie。</p>
    <label>豆瓣用户 ID 或主页链接</label>
    <input id="doubanUser" type="text" placeholder="例如：https://www.douban.com/people/你的ID/" />
    <label>Cookie（可选）</label>
    <textarea id="doubanCookie" placeholder="公开数据够用就不用填"></textarea>
    <div class="row"><div><label>最多抓取页数</label><input id="maxPages" type="number" min="1" max="60" value="8" /></div><div><label>想看列表</label><label><input id="includeWish" type="checkbox" checked /> 同时抓取想看</label></div></div>
    ${renderCookieGuide()}
    <div class="actions"><button onclick="crawlDouban()">开始抓取</button><button class="secondary" onclick="loadSample()">使用示例数据</button></div>
    <div id="status" class="status"></div>`;
  renderCrawlSummary();
}
function renderCrawlSummary() {
  $("rightPanel").innerHTML = `<h2>抓取结果</h2>` + (state.ratedItems.length ? `<div class="statbar"><div class="stat"><b>${state.ratedItems.length}</b>条数据</div><div class="stat"><b>${state.counts?.pages_ok ?? "-"}</b>成功页</div><div class="stat"><b>${state.counts?.pages_failed ?? "-"}</b>失败页</div></div><h3>最近抓到</h3><ul class="mini-list">${state.ratedItems.slice(0,5).map(x => `<li>${esc(x.title)} ${x.my_rating ? "· 我的评分 " + x.my_rating : ""}</li>`).join("")}</ul><div class="actions"><button onclick="goStep(2)">下一步：确认口味</button></div>` : `<div class="empty">还没有数据。你可以抓取豆瓣，也可以使用示例数据先试跑。</div>`);
}
function renderTastePanel() {
  $("leftPanel").innerHTML = `<h2>第二步：确认口味</h2>
    <p class="hint">评分会自动分析；这里补充你最近想看的方向和明确避雷点。</p>
    <label>喜欢的口味</label><textarea id="likeTerms">悬疑, 犯罪, 现实主义, 黑色幽默, 群像</textarea>
    <label>不喜欢的口味</label><textarea id="dislikeTerms">甜宠, 狗血, 低幼, 恐怖血腥</textarea>
    <label>推荐范围</label>
    <label><input id="includeMovies" type="checkbox" checked /> 电影</label>
    <label><input id="includeSeries" type="checkbox" checked /> 电视剧</label>
    <details><summary>高级候选来源</summary>
      <label><input id="fetchDouban" type="checkbox" checked /> 从豆瓣探索候选池补充</label>
      <label><input id="useSampleCandidates" type="checkbox" checked /> 加入本地示例候选</label>
      <label>推荐数量</label><input id="limit" type="number" min="5" max="100" value="30" />
    </details>
    <div class="actions"><button onclick="recommend()">生成推荐</button><button class="ghost" onclick="goStep(1)">返回上一步</button></div>
    <div id="status" class="status"></div>`;
  $("rightPanel").innerHTML = `<h2>你的数据</h2><div class="statbar"><div class="stat"><b>${state.ratedItems.length}</b>条评分/想看</div></div><p class="hint">系统会用高分条目学习偏好，用低分条目学习避雷，并自动排除已经看过的条目。</p>`;
}
function renderRecommendations() {
  const cards = state.recommendations.map((r, i) => `<article class="card">
    <div class="card-top"><div><h2>${i + 1}. ${r.url ? `<a class="link" href="${esc(r.url)}" target="_blank">${esc(r.title)}</a>` : esc(r.title)}</h2><div class="meta"><span>${esc(r.media_type)}</span><span>豆瓣 ${r.douban_rating || "-"}</span><span>${esc((r.genres || []).slice(0,3).join(" / "))}</span></div></div><div class="score">${Number(r.score).toFixed(1)}</div></div>
    <ul class="reasons">${(r.reasons || []).slice(0,3).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <details><summary>展开详情</summary><ul class="mini-list">${(r.reasons || []).slice(3).map(x => `<li>${esc(x)}</li>`).join("")}${(r.warnings || []).map(x => `<li class="warn">${esc(x)}</li>`).join("")}</ul><p class="hint">导演：${esc((r.directors || []).join(" / ") || "-")}<br>主演：${esc((r.casts || []).slice(0,6).join(" / ") || "-")}<br>来源：${esc(r.source || "-")}</p></details>
  </article>`).join("");
  $("leftPanel").innerHTML = `<h2>第三步：查看推荐</h2><p class="hint">默认只展示最有用的理由；想看匹配细节再展开。</p><div class="actions"><button class="ghost" onclick="goStep(2)">调整口味</button><button class="secondary" onclick="goStep(1)">重新抓取</button></div>`;
  $("rightPanel").innerHTML = cards || `<div class="empty">还没有推荐结果。</div>`;
}
function goStep(step) {
  state.step = step;
  renderStepNav();
  if (step === 1) renderCrawlerPanel();
  if (step === 2) renderTastePanel();
  if (step === 3) renderRecommendations();
}
async function crawlDouban() {
  setStatus("正在抓取豆瓣页面，通常需要几十秒以内。");
  const payload = { user_id_or_url: $("doubanUser").value, cookie: $("doubanCookie").value, max_pages: Number($("maxPages").value || 8), include_wish: $("includeWish").checked };
  const res = await fetch("/api/crawl-douban", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) { setStatus("抓取失败：" + (data.error || "请求失败")); return; }
  state.ratedItems = data.items || [];
  state.counts = data.counts || {};
  renderCrawlerPanel();
}
async function loadSample() {
  const text = await fetch("/sample/ratings").then(r => r.text());
  const res = await fetch("/api/recommend", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify({ ratings_csv:text, fetch_douban:false, use_sample_candidates:true, include_movies:true, include_series:true, limit:1 }) });
  const data = await res.json();
  state.ratedItems = [];
  state.counts = { pages_ok: "-", pages_failed: "-" };
  setStatus("示例数据已加载。请进入第二步生成完整推荐。");
  goStep(2);
}
async function recommend() {
  setStatus("正在生成推荐。");
  const payload = { rated_items:state.ratedItems, like_terms:$("likeTerms").value, dislike_terms:$("dislikeTerms").value, include_movies:$("includeMovies").checked, include_series:$("includeSeries").checked, fetch_douban:$("fetchDouban").checked, use_sample_candidates:$("useSampleCandidates").checked, limit:Number($("limit").value || 30) };
  const res = await fetch("/api/recommend", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) { setStatus("推荐失败：" + (data.error || "请求失败")); return; }
  state.recommendations = data.results || [];
  state.profile = data.profile || null;
  goStep(3);
}
goStep(1);
</script>
</body>
</html>'''
```

- [ ] **Step 4: Modify web.py to import INDEX_HTML from web_ui**

In `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web.py`:

1. Add this import:

```python
from .web_ui import INDEX_HTML
```

2. Remove the old `INDEX_HTML = r'''...'''` block from `web.py`.

- [ ] **Step 5: Run UI tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_ui_html -v
```

Expected: `OK`.

- [ ] **Step 6: Run web API tests to verify import split did not break routes**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest tests.test_web_api -v
```

Expected: `OK`.

- [ ] **Step 7: Commit**

Run:

```powershell
git add tests/test_ui_html.py src/douban_recommender/web_ui.py src/douban_recommender/web.py
git commit -m "feat: redesign UI as three-step assistant"
```

---

### Task 6: README Cookie Tutorial and User Instructions

**Files:**
- Create: `C:\Users\11616\douban-taste-recommender\tests\test_readme.py`
- Modify: `C:\Users\11616\douban-taste-recommender\README.md`

**Interfaces:**
- Consumes: current `README.md`
- Produces: README sections with direct crawler workflow and Cookie tutorial

- [ ] **Step 1: Write failing README tests**

Create `C:\Users\11616\douban-taste-recommender\tests\test_readme.py`:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
    def test_readme_explains_direct_douban_crawler(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("直接抓取豆瓣数据", text)
        self.assertIn("豆瓣用户 ID 或主页链接", text)
        self.assertIn("Cookie 是可选项", text)

    def test_readme_contains_cookie_tutorial_and_privacy_copy(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Cookie 获取教程", text)
        self.assertIn("F12", text)
        self.assertIn("Network / 网络", text)
        self.assertIn("Cookie 只用于本机请求豆瓣页面", text)
        self.assertIn("不会保存到磁盘", text)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run test and verify the expected failure**

Run:

```powershell
python -m unittest tests.test_readme -v
```

Expected: FAIL because README lacks the new crawler and Cookie tutorial copy.

- [ ] **Step 3: Add README sections**

Append this section to `C:\Users\11616\douban-taste-recommender\README.md`:

```markdown

## 直接抓取豆瓣数据

现在可以不借助外部导出工具，直接在本地网页里抓取豆瓣数据：

1. 启动应用：`.\run_app.ps1`
2. 打开 <http://127.0.0.1:7861>
3. 在“第一步：连接豆瓣”里输入豆瓣用户 ID 或主页链接。
4. 如果公开数据够用，Cookie 可以留空。
5. 如果抓不到完整评分，再粘贴 Cookie 后重试。

Cookie 是可选项。它只用于本机请求豆瓣页面，不会保存到磁盘，不会写入报告，也不会上传到外部服务。

## Cookie 获取教程

1. 打开浏览器并登录豆瓣。
2. 进入任意豆瓣页面，例如 `https://movie.douban.com/`。
3. 按 `F12` 打开开发者工具。
4. 选择 `Network / 网络`。
5. 刷新页面。
6. 点击任意 `movie.douban.com` 或 `www.douban.com` 请求。
7. 在右侧 `Headers / 标头` 中找到 `Request Headers`。
8. 复制其中 `Cookie: ` 后面的整段内容。
9. 粘贴到本应用的 Cookie 输入框。

如果抓取失败，先确认豆瓣网页本身能正常打开，再把最多抓取页数调小后重试。
```

- [ ] **Step 4: Run README tests and verify pass**

Run:

```powershell
python -m unittest tests.test_readme -v
```

Expected: `OK`.

- [ ] **Step 5: Commit**

Run:

```powershell
git add tests/test_readme.py README.md
git commit -m "docs: add Douban crawler and cookie guide"
```

---

### Task 7: Final Regression and Manual Smoke Verification

**Files:**
- Modify only if verification reveals a defect:
  - `C:\Users\11616\douban-taste-recommender\src\douban_recommender\*.py`
  - `C:\Users\11616\douban-taste-recommender\tests\*.py`

**Interfaces:**
- Consumes: all features from Tasks 1-6
- Produces: verified local app and clean git working tree

- [ ] **Step 1: Run all unit tests**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m unittest discover -s tests -v
```

Expected: all tests report `ok` and final output contains `OK`.

- [ ] **Step 2: Run CLI smoke test**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
python -m douban_recommender.cli --ratings sample_data\ratings_sample.csv --candidates sample_data\candidates_sample.csv --like "悬疑,犯罪,现实主义" --dislike "甜宠,狗血" --limit 5 --output output\final_smoke.html
```

Expected: exit code `0`, output includes `已生成`, and top results do not include the user's rated titles from `sample_data\ratings_sample.csv`.

- [ ] **Step 3: Run web API smoke test**

Run:

```powershell
$env:PYTHONPATH = "C:\Users\11616\douban-taste-recommender\src"
@'
import json
import threading
import urllib.request
from http.server import ThreadingHTTPServer

from douban_recommender.web import Handler

server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
port = server.server_address[1]
thread = threading.Thread(target=server.serve_forever, daemon=True)
thread.start()
try:
    home = urllib.request.urlopen(f"http://127.0.0.1:{port}/", timeout=5).read().decode("utf-8")
    assert "第一步：连接豆瓣" in home
    payload = json.dumps({
        "ratings_csv": "",
        "fetch_douban": False,
        "use_sample_candidates": True,
        "include_movies": True,
        "include_series": True,
        "limit": 3
    }, ensure_ascii=False).encode("utf-8")
    request = urllib.request.Request(
        f"http://127.0.0.1:{port}/api/recommend",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    response = json.loads(urllib.request.urlopen(request, timeout=10).read().decode("utf-8"))
    assert len(response["results"]) == 3
    print("WEB_SMOKE_OK", [item["title"] for item in response["results"]])
finally:
    server.shutdown()
    server.server_close()
'@ | python -
```

Expected: exit code `0`, output starts with `WEB_SMOKE_OK`.

- [ ] **Step 4: Remove generated Python caches**

Run:

```powershell
$root = Resolve-Path "C:\Users\11616\douban-taste-recommender"
Get-ChildItem -Path $root -Recurse -Directory -Filter "__pycache__" | ForEach-Object {
  if ($_.FullName.StartsWith($root.Path)) {
    Remove-Item -LiteralPath $_.FullName -Recurse -Force
  }
}
```

Expected: no output.

- [ ] **Step 5: Inspect git status**

Run:

```powershell
git status --short
```

Expected: no untracked `__pycache__` files. If only `output/final_smoke.html` appears, leave it untracked because `output/` is ignored.

- [ ] **Step 6: Commit verification fixes if files changed**

If Step 5 shows tracked source, tests, or docs changed after verification, run:

```powershell
git add src tests README.md docs
git commit -m "test: verify Douban crawler UI workflow"
```

Expected: commit created only when tracked files changed.
