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
2. **Cookie mode is feasible and should be optional.** Cookie copying is realistic for desktop users, but it is intimidating. The UI should present it as 鈥滃鏋滃叕寮€鏁版嵁涓嶅锛屽啀绮樿创 Cookie,鈥?not as a required first step.
3. **A full browser automation crawler is not worth the complexity.** It would add dependencies, login fragility, and UI confusion. The best product is a simple local HTTP crawler with clear limits and clear failure messages.
4. **The current UI overload is the biggest usability issue.** The most human-friendly version is a wizard: connect Douban 鈫?confirm taste 鈫?read recommendations. Advanced inputs belong behind collapsible panels.
5. **The recommendation engine already works well enough.** The useful upgrade is not a new algorithm; it is better data ingestion, automatic 鈥渁lready watched鈥?exclusion, and better explanations.

### Product Decision

Build a **three-step local assistant**:

1. **杩炴帴璞嗙摚**: user enters profile URL/ID, optionally expands Cookie tutorial.
2. **纭鍙ｅ懗**: user edits short 鈥滃枩娆?涓嶅枩娆⑩€?chips and chooses movie/series scope.
3. **鏌ョ湅鎺ㄨ崘**: user sees compact cards first, opens details only when needed.

This is the most usable version because it gives the user one decision at a time, avoids demanding Cookie upfront, keeps privacy promises visible, and keeps recommendation explanations short by default.

---

## File Structure

- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\serialization.py`
  - Converts `MediaItem` to/from safe JSON dictionaries.
  - Redacts Cookie-like text for error/log safety.
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`
  - Normalizes Douban user input.
  - Builds collection URLs.
  - Fetches collection pages with optional Cookie.
  - Parses collection HTML into `MediaItem` objects.
  - Crawls `collect` and optional `wish` pagination.
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`
  - Owns the new three-step HTML/CSS/JS UI.
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`
  - Imports `INDEX_HTML` from `web_ui.py`.
  - Adds `POST /api/crawl-douban`.
  - Lets `POST /api/recommend` accept `rated_items` JSON.
- Modify: `C:\path\to\douban-taste-recommender\README.md`
  - Adds direct crawler usage and Cookie tutorial.
- Create: `C:\path\to\douban-taste-recommender\tests\test_serialization.py`
- Create: `C:\path\to\douban-taste-recommender\tests\test_crawler.py`
- Create: `C:\path\to\douban-taste-recommender\tests\test_web_api.py`
- Create: `C:\path\to\douban-taste-recommender\tests\test_ui_html.py`
- Create: `C:\path\to\douban-taste-recommender\tests\test_readme.py`

---

### Task 1: Safe MediaItem JSON Serialization

**Files:**
- Create: `C:\path\to\douban-taste-recommender\tests\test_serialization.py`
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\serialization.py`

**Interfaces:**
- Consumes: `douban_recommender.models.MediaItem`
- Produces:
  - `media_item_to_dict(item: MediaItem) -> dict[str, object]`
  - `media_item_from_dict(data: dict[str, object]) -> MediaItem`
  - `redact_cookie(value: str) -> str`

- [ ] **Step 1: Write the failing serialization tests**

Create `C:\path\to\douban-taste-recommender\tests\test_serialization.py`:

```python
import unittest

from douban_recommender.models import MediaItem
from douban_recommender.serialization import media_item_from_dict, media_item_to_dict, redact_cookie


class SerializationTests(unittest.TestCase):
    def test_media_item_round_trips_through_json_dict(self):
        item = MediaItem(
            title="闅愮鐨勮钀?,
            my_rating=5,
            douban_rating=8.8,
            year=2020,
            media_type="鐢佃鍓?,
            genres=["鍓ф儏", "鎮枒", "鐘姜"],
            countries=["涓浗澶ч檰"],
            directors=["杈涚埥"],
            casts=["绉︽槉", "鐜嬫櫙鏄?],
            tags=["鐪嬭繃", "鐜板疄涓讳箟"],
            url="https://movie.douban.com/subject/33404425/",
            douban_id="33404425",
            cover="https://img.example/poster.jpg",
            summary="瀛╁瓙銆佸搴笌鐘姜鐨勯槾褰?,
            source="douban_user:collect",
        )

        payload = media_item_to_dict(item)
        restored = media_item_from_dict(payload)

        self.assertEqual(restored.title, "闅愮鐨勮钀?)
        self.assertEqual(restored.my_rating, 5)
        self.assertEqual(restored.douban_rating, 8.8)
        self.assertEqual(restored.genres, ["鍓ф儏", "鎮枒", "鐘姜"])
        self.assertEqual(restored.tags, ["鐪嬭繃", "鐜板疄涓讳箟"])
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
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_serialization -v
```

Expected: FAIL or ERROR because `douban_recommender.serialization` does not exist.

- [ ] **Step 3: Create the minimal serialization implementation**

Create `C:\path\to\douban-taste-recommender\src\douban_recommender\serialization.py`:

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
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
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
- Create: `C:\path\to\douban-taste-recommender\tests\test_crawler.py`
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`

**Interfaces:**
- Consumes:
  - `douban_recommender.models.MediaItem`
  - `douban_recommender.io.extract_douban_id`
- Produces:
  - `normalize_douban_user_id(value: str) -> str`
  - `build_user_collection_url(user_id: str, status: str, start: int) -> str`
  - `parse_user_collection_html(page_html: str, status: str) -> list[MediaItem]`

- [ ] **Step 1: Write the failing crawler parser tests**

Create `C:\path\to\douban-taste-recommender\tests\test_crawler.py` with the initial parser tests:

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
        <img alt="闅愮鐨勮钀? src="https://img.example/cover.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/33404425/"><em>闅愮鐨勮钀?/em></a>
        </li>
        <li class="intro">2020 / 涓浗澶ч檰 / 鍓ф儏 鎮枒 鐘姜 / 杈涚埥 / 绉︽槉 鐜嬫櫙鏄?/li>
        <li>
          <span class="rating5-t"></span>
          <span class="date">2024-01-01</span>
        </li>
        <li><span class="comment">瀛╁瓙銆佸搴笌鐘姜鐨勯槾褰?/span></li>
      </ul>
    </div>
  </div>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/30468961/">
        <img alt="鎯宠浣? src="https://img.example/want.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/30468961/"><em>鎯宠浣?/em></a>
        </li>
        <li class="intro">2019 / 涓浗鍙版咕 / 鐖辨儏 鎮枒 濂囧够 / 榛勫ぉ浠?/ 鏌匠瀣?璁稿厜姹?/li>
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
        self.assertEqual(first.title, "闅愮鐨勮钀?)
        self.assertEqual(first.my_rating, 5)
        self.assertEqual(first.year, 2020)
        self.assertEqual(first.media_type, "鐢靛奖")
        self.assertIn("鍓ф儏", first.genres)
        self.assertIn("鎮枒", first.genres)
        self.assertIn("鐘姜", first.genres)
        self.assertIn("涓浗澶ч檰", first.countries)
        self.assertIn("鐪嬭繃", first.tags)
        self.assertEqual(first.douban_id, "33404425")
        self.assertEqual(first.cover, "https://img.example/cover.jpg")
        self.assertEqual(first.summary, "瀛╁瓙銆佸搴笌鐘姜鐨勯槾褰?)

    def test_parse_user_collection_html_handles_no_rating(self):
        items = parse_user_collection_html(COLLECT_HTML, status="wish")

        second = items[1]
        self.assertEqual(second.title, "鎯宠浣?)
        self.assertIsNone(second.my_rating)
        self.assertIn("鎯崇湅", second.tags)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_crawler -v
```

Expected: FAIL or ERROR because `douban_recommender.crawler` does not exist.

- [ ] **Step 3: Create parser implementation**

Create `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py` with URL and parser functions:

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
    "涓浗澶ч檰",
    "涓浗棣欐腐",
    "涓浗鍙版咕",
    "缇庡浗",
    "鑻卞浗",
    "鏃ユ湰",
    "闊╁浗",
    "娉曞浗",
    "寰峰浗",
    "鎰忓ぇ鍒?,
    "瑗跨彮鐗?,
    "鍗板害",
    "鍔犳嬁澶?,
    "婢冲ぇ鍒╀簹",
    "娉板浗",
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
        raise ValueError("璇疯緭鍏ヨ眴鐡ｇ敤鎴?ID 鎴栦富椤甸摼鎺?)
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
        tag = "鎯崇湅" if status == "wish" else "鐪嬭繃"
        items.append(MediaItem(
            title=title,
            my_rating=my_rating,
            year=parse_year(intro),
            media_type="鐢靛奖",
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
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
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
- Modify: `C:\path\to\douban-taste-recommender\tests\test_crawler.py`
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`

**Interfaces:**
- Consumes:
  - `normalize_douban_user_id(value: str) -> str`
  - `build_user_collection_url(user_id: str, status: str, start: int) -> str`
  - `parse_user_collection_html(page_html: str, status: str) -> list[MediaItem]`
- Produces:
  - `fetch_user_collection_page(user_id: str, status: str, start: int, cookie: str = "", timeout: int = 12) -> str`
  - `crawl_user_collections(user_id_or_url: str, cookie: str = "", max_pages: int = 8, include_wish: bool = True, page_size: int = 15, fetcher: Callable[..., str] | None = None, sleep_seconds: float = 0.15) -> CrawlResult`

- [ ] **Step 1: Add failing crawl orchestration tests**

Append to `CrawlerParserTests` in `C:\path\to\douban-taste-recommender\tests\test_crawler.py`:

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
        self.assertEqual(result.stopped_reason, "宸插埌杈剧┖鐧藉垎椤?)

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
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_crawler -v
```

Expected: FAIL or ERROR because `crawl_user_collections` is not defined.

- [ ] **Step 3: Add fetch and crawl functions**

Append these functions to `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`:

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
        result.stopped_reason = "宸插埌杈剧┖鐧藉垎椤?
    elif result.pages_failed:
        result.stopped_reason = "閮ㄥ垎鍒嗛〉鎶撳彇澶辫触"
    else:
        result.stopped_reason = "宸茶揪鍒伴〉鏁颁笂闄?
    return result
```

- [ ] **Step 4: Run crawler tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
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
- Create: `C:\path\to\douban-taste-recommender\tests\test_web_api.py`
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`

**Interfaces:**
- Consumes:
  - `crawl_user_collections(...) -> CrawlResult`
  - `media_item_to_dict(item: MediaItem) -> dict[str, object]`
  - `media_item_from_dict(data: dict[str, object]) -> MediaItem`
- Produces:
  - `POST /api/crawl-douban`
  - `POST /api/recommend` accepts `rated_items: list[dict]`

- [ ] **Step 1: Write failing web API tests**

Create `C:\path\to\douban-taste-recommender\tests\test_web_api.py`:

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
                        title="闅愮鐨勮钀?,
                        my_rating=5,
                        media_type="鐢佃鍓?,
                        genres=["鍓ф儏", "鎮枒", "鐘姜"],
                        url="https://movie.douban.com/subject/33404425/",
                        douban_id="33404425",
                        source="douban_user:collect",
                    )
                ],
                pages_ok=1,
                pages_failed=0,
                stopped_reason="宸插埌杈剧┖鐧藉垎椤?,
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
        self.assertEqual(response["items"][0]["title"], "闅愮鐨勮钀?)
        self.assertNotIn("secret-cookie-value", serialized)
        self.assertNotIn("hidden", serialized)

    def test_recommend_api_accepts_json_rated_items(self):
        response = self.post_json("/api/recommend", {
            "rated_items": [
                {
                    "title": "闅愮鐨勮钀?,
                    "my_rating": 5,
                    "media_type": "鐢佃鍓?,
                    "genres": ["鍓ф儏", "鎮枒", "鐘姜"],
                    "tags": ["鐪嬭繃"],
                    "douban_id": "33404425",
                }
            ],
            "candidates_csv": "title,media_type,douban_rating,genres,tags\\n鏂扮墖,鐢靛奖,8.1,鍓ф儏 / 鐘姜,鐜板疄涓讳箟\\n",
            "fetch_douban": False,
            "use_sample_candidates": False,
            "include_movies": True,
            "include_series": True,
            "like_terms": "鐘姜,鐜板疄涓讳箟",
            "dislike_terms": "鐢滃疇",
            "limit": 5,
        })

        self.assertEqual(response["counts"]["rated"], 1)
        self.assertEqual(response["results"][0]["title"], "鏂扮墖")


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_web_api -v
```

Expected: FAIL because `/api/crawl-douban` is not routed and `rated_items` JSON is not accepted.

- [ ] **Step 3: Modify imports in web.py**

In `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`, add:

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
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_web_api -v
```

Expected: `OK`.

- [ ] **Step 8: Run existing smoke test**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m douban_recommender.cli --ratings sample_data\ratings_sample.csv --candidates sample_data\candidates_sample.csv --limit 3 --output output\api_regression.html
```

Expected: exit code `0` and output includes `宸茬敓鎴恅.

- [ ] **Step 9: Commit**

Run:

```powershell
git add tests/test_web_api.py src/douban_recommender/web.py
git commit -m "feat: add Douban crawl and JSON recommendation APIs"
```

---

### Task 5: Three-Step Humanized UI

**Files:**
- Create: `C:\path\to\douban-taste-recommender\tests\test_ui_html.py`
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`

**Interfaces:**
- Consumes:
  - `POST /api/crawl-douban`
  - `POST /api/recommend`
- Produces:
  - `INDEX_HTML: str`
  - Browser functions: `renderStepNav`, `renderCrawlerPanel`, `renderTastePanel`, `renderRecommendations`, `renderCookieGuide`

- [ ] **Step 1: Write failing UI structure tests**

Create `C:\path\to\douban-taste-recommender\tests\test_ui_html.py`:

```python
import unittest

from douban_recommender.web_ui import INDEX_HTML


class UiHtmlTests(unittest.TestCase):
    def test_ui_uses_three_clear_steps(self):
        self.assertIn("绗竴姝ワ細杩炴帴璞嗙摚", INDEX_HTML)
        self.assertIn("绗簩姝ワ細纭鍙ｅ懗", INDEX_HTML)
        self.assertIn("绗笁姝ワ細鏌ョ湅鎺ㄨ崘", INDEX_HTML)

    def test_ui_contains_cookie_tutorial_and_privacy_copy(self):
        self.assertIn("Cookie 鏁欑▼", INDEX_HTML)
        self.assertIn("Cookie 鍙敤浜庢湰鏈鸿姹傝眴鐡ｉ〉闈?, INDEX_HTML)
        self.assertIn("涓嶄細淇濆瓨鍒扮鐩?, INDEX_HTML)

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
        self.assertIn("灞曞紑璇︽儏", INDEX_HTML)


if __name__ == "__main__":
    unittest.main()
```

- [ ] **Step 2: Run tests and verify the expected failure**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_ui_html -v
```

Expected: FAIL or ERROR because `douban_recommender.web_ui` does not exist.

- [ ] **Step 3: Create the UI module**

Create `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py` with this complete minimal UI. It intentionally favors clarity over dense controls:

```python
from __future__ import annotations

INDEX_HTML = r'''<!doctype html>
<html lang="zh-CN">
<head>
  <meta charset="utf-8" />
  <meta name="viewport" content="width=device-width, initial-scale=1" />
  <title>璞嗙摚鍙ｅ懗褰辫鎺ㄨ崘鍣?/title>
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
        <h1>璞嗙摚鍙ｅ懗褰辫鎺ㄨ崘鍣?/h1>
        <p class="lead">鍏堣繛鎺ヨ眴鐡ｏ紝鍐嶇‘璁ゅ彛鍛筹紝鏈€鍚庣湅鎺ㄨ崘銆侰ookie 鏄彲閫夐」锛氬叕寮€鏁版嵁澶熺敤灏变笉鐢ㄥ～銆?/p>
      </div>
      <div class="privacy">鏈湴杩愯锛屼笉淇濆瓨 Cookie</div>
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
    ["绗竴姝ワ細杩炴帴璞嗙摚", "杈撳叆 ID锛屽叕寮€鎶撳彇锛涢渶瑕佹椂鍐嶅～ Cookie"],
    ["绗簩姝ワ細纭鍙ｅ懗", "鐢ㄧ煭鍙ュ憡璇夋垜鍠滄鍜屼笉鍠滄浠€涔?],
    ["绗笁姝ワ細鏌ョ湅鎺ㄨ崘", "鍏堢湅鎽樿锛屾兂娣辨寲鍐嶅睍寮€璇︽儏"]
  ];
  $("stepNav").innerHTML = steps.map((s, i) => `<div class="step ${state.step === i + 1 ? "active" : ""}"><b>${s[0]}</b>${s[1]}</div>`).join("");
}
function renderCookieGuide() {
  return `<details><summary>Cookie 鏁欑▼</summary>
    <ol class="mini-list">
      <li>鎵撳紑娴忚鍣ㄥ苟鐧诲綍璞嗙摚銆?/li>
      <li>杩涘叆 https://movie.douban.com/銆?/li>
      <li>鎸?F12 鎵撳紑寮€鍙戣€呭伐鍏凤紝杩涘叆 Network / 缃戠粶銆?/li>
      <li>鍒锋柊椤甸潰锛岀偣鍑讳换鎰?movie.douban.com 鎴?www.douban.com 璇锋眰銆?/li>
      <li>鍦?Headers / 鏍囧ご閲屾壘鍒?Request Headers銆?/li>
      <li>澶嶅埗 Cookie: 鍚庨潰鐨勬暣娈靛唴瀹癸紝绮樿创鍒拌繖閲屻€?/li>
    </ol>
    <p class="hint">Cookie 鍙敤浜庢湰鏈鸿姹傝眴鐡ｉ〉闈紝涓嶄細淇濆瓨鍒扮鐩橈紝涔熶笉浼氬嚭鐜板湪鎺ㄨ崘鎶ュ憡閲屻€?/p>
  </details>`;
}
function renderCrawlerPanel() {
  $("leftPanel").innerHTML = `<h2>绗竴姝ワ細杩炴帴璞嗙摚</h2>
    <p class="hint">濉眴鐡ｇ敤鎴?ID 鎴栦富椤甸摼鎺ャ€侰ookie 鍙笉濉紱濡傛灉鎶撲笉鍒板畬鏁磋瘎鍒嗭紝鍐嶆寜鏁欑▼澶嶅埗 Cookie銆?/p>
    <label>璞嗙摚鐢ㄦ埛 ID 鎴栦富椤甸摼鎺?/label>
    <input id="doubanUser" type="text" placeholder="渚嬪锛歨ttps://www.douban.com/people/浣犵殑ID/" />
    <label>Cookie锛堝彲閫夛級</label>
    <textarea id="doubanCookie" placeholder="鍏紑鏁版嵁澶熺敤灏变笉鐢ㄥ～"></textarea>
    <div class="row"><div><label>鏈€澶氭姄鍙栭〉鏁?/label><input id="maxPages" type="number" min="1" max="60" value="8" /></div><div><label>鎯崇湅鍒楄〃</label><label><input id="includeWish" type="checkbox" checked /> 鍚屾椂鎶撳彇鎯崇湅</label></div></div>
    ${renderCookieGuide()}
    <div class="actions"><button onclick="crawlDouban()">寮€濮嬫姄鍙?/button><button class="secondary" onclick="loadSample()">浣跨敤绀轰緥鏁版嵁</button></div>
    <div id="status" class="status"></div>`;
  renderCrawlSummary();
}
function renderCrawlSummary() {
  $("rightPanel").innerHTML = `<h2>鎶撳彇缁撴灉</h2>` + (state.ratedItems.length ? `<div class="statbar"><div class="stat"><b>${state.ratedItems.length}</b>鏉℃暟鎹?/div><div class="stat"><b>${state.counts?.pages_ok ?? "-"}</b>鎴愬姛椤?/div><div class="stat"><b>${state.counts?.pages_failed ?? "-"}</b>澶辫触椤?/div></div><h3>鏈€杩戞姄鍒?/h3><ul class="mini-list">${state.ratedItems.slice(0,5).map(x => `<li>${esc(x.title)} ${x.my_rating ? "路 鎴戠殑璇勫垎 " + x.my_rating : ""}</li>`).join("")}</ul><div class="actions"><button onclick="goStep(2)">涓嬩竴姝ワ細纭鍙ｅ懗</button></div>` : `<div class="empty">杩樻病鏈夋暟鎹€備綘鍙互鎶撳彇璞嗙摚锛屼篃鍙互浣跨敤绀轰緥鏁版嵁鍏堣瘯璺戙€?/div>`);
}
function renderTastePanel() {
  $("leftPanel").innerHTML = `<h2>绗簩姝ワ細纭鍙ｅ懗</h2>
    <p class="hint">璇勫垎浼氳嚜鍔ㄥ垎鏋愶紱杩欓噷琛ュ厖浣犳渶杩戞兂鐪嬬殑鏂瑰悜鍜屾槑纭伩闆风偣銆?/p>
    <label>鍠滄鐨勫彛鍛?/label><textarea id="likeTerms">鎮枒, 鐘姜, 鐜板疄涓讳箟, 榛戣壊骞介粯, 缇ゅ儚</textarea>
    <label>涓嶅枩娆㈢殑鍙ｅ懗</label><textarea id="dislikeTerms">鐢滃疇, 鐙楄, 浣庡辜, 鎭愭€栬鑵?/textarea>
    <label>鎺ㄨ崘鑼冨洿</label>
    <label><input id="includeMovies" type="checkbox" checked /> 鐢靛奖</label>
    <label><input id="includeSeries" type="checkbox" checked /> 鐢佃鍓?/label>
    <details><summary>楂樼骇鍊欓€夋潵婧?/summary>
      <label><input id="fetchDouban" type="checkbox" checked /> 浠庤眴鐡ｆ帰绱㈠€欓€夋睜琛ュ厖</label>
      <label><input id="useSampleCandidates" type="checkbox" checked /> 鍔犲叆鏈湴绀轰緥鍊欓€?/label>
      <label>鎺ㄨ崘鏁伴噺</label><input id="limit" type="number" min="5" max="100" value="30" />
    </details>
    <div class="actions"><button onclick="recommend()">鐢熸垚鎺ㄨ崘</button><button class="ghost" onclick="goStep(1)">杩斿洖涓婁竴姝?/button></div>
    <div id="status" class="status"></div>`;
  $("rightPanel").innerHTML = `<h2>浣犵殑鏁版嵁</h2><div class="statbar"><div class="stat"><b>${state.ratedItems.length}</b>鏉¤瘎鍒?鎯崇湅</div></div><p class="hint">绯荤粺浼氱敤楂樺垎鏉＄洰瀛︿範鍋忓ソ锛岀敤浣庡垎鏉＄洰瀛︿範閬块浄锛屽苟鑷姩鎺掗櫎宸茬粡鐪嬭繃鐨勬潯鐩€?/p>`;
}
function renderRecommendations() {
  const cards = state.recommendations.map((r, i) => `<article class="card">
    <div class="card-top"><div><h2>${i + 1}. ${r.url ? `<a class="link" href="${esc(r.url)}" target="_blank">${esc(r.title)}</a>` : esc(r.title)}</h2><div class="meta"><span>${esc(r.media_type)}</span><span>璞嗙摚 ${r.douban_rating || "-"}</span><span>${esc((r.genres || []).slice(0,3).join(" / "))}</span></div></div><div class="score">${Number(r.score).toFixed(1)}</div></div>
    <ul class="reasons">${(r.reasons || []).slice(0,3).map(x => `<li>${esc(x)}</li>`).join("")}</ul>
    <details><summary>灞曞紑璇︽儏</summary><ul class="mini-list">${(r.reasons || []).slice(3).map(x => `<li>${esc(x)}</li>`).join("")}${(r.warnings || []).map(x => `<li class="warn">${esc(x)}</li>`).join("")}</ul><p class="hint">瀵兼紨锛?{esc((r.directors || []).join(" / ") || "-")}<br>涓绘紨锛?{esc((r.casts || []).slice(0,6).join(" / ") || "-")}<br>鏉ユ簮锛?{esc(r.source || "-")}</p></details>
  </article>`).join("");
  $("leftPanel").innerHTML = `<h2>绗笁姝ワ細鏌ョ湅鎺ㄨ崘</h2><p class="hint">榛樿鍙睍绀烘渶鏈夌敤鐨勭悊鐢憋紱鎯崇湅鍖归厤缁嗚妭鍐嶅睍寮€銆?/p><div class="actions"><button class="ghost" onclick="goStep(2)">璋冩暣鍙ｅ懗</button><button class="secondary" onclick="goStep(1)">閲嶆柊鎶撳彇</button></div>`;
  $("rightPanel").innerHTML = cards || `<div class="empty">杩樻病鏈夋帹鑽愮粨鏋溿€?/div>`;
}
function goStep(step) {
  state.step = step;
  renderStepNav();
  if (step === 1) renderCrawlerPanel();
  if (step === 2) renderTastePanel();
  if (step === 3) renderRecommendations();
}
async function crawlDouban() {
  setStatus("姝ｅ湪鎶撳彇璞嗙摚椤甸潰锛岄€氬父闇€瑕佸嚑鍗佺浠ュ唴銆?);
  const payload = { user_id_or_url: $("doubanUser").value, cookie: $("doubanCookie").value, max_pages: Number($("maxPages").value || 8), include_wish: $("includeWish").checked };
  const res = await fetch("/api/crawl-douban", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) { setStatus("鎶撳彇澶辫触锛? + (data.error || "璇锋眰澶辫触")); return; }
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
  setStatus("绀轰緥鏁版嵁宸插姞杞姐€傝杩涘叆绗簩姝ョ敓鎴愬畬鏁存帹鑽愩€?);
  goStep(2);
}
async function recommend() {
  setStatus("姝ｅ湪鐢熸垚鎺ㄨ崘銆?);
  const payload = { rated_items:state.ratedItems, like_terms:$("likeTerms").value, dislike_terms:$("dislikeTerms").value, include_movies:$("includeMovies").checked, include_series:$("includeSeries").checked, fetch_douban:$("fetchDouban").checked, use_sample_candidates:$("useSampleCandidates").checked, limit:Number($("limit").value || 30) };
  const res = await fetch("/api/recommend", { method:"POST", headers:{ "Content-Type":"application/json" }, body:JSON.stringify(payload) });
  const data = await res.json();
  if (!res.ok || data.error) { setStatus("鎺ㄨ崘澶辫触锛? + (data.error || "璇锋眰澶辫触")); return; }
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

In `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`:

1. Add this import:

```python
from .web_ui import INDEX_HTML
```

2. Remove the old `INDEX_HTML = r'''...'''` block from `web.py`.

- [ ] **Step 5: Run UI tests and verify pass**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest tests.test_ui_html -v
```

Expected: `OK`.

- [ ] **Step 6: Run web API tests to verify import split did not break routes**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
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
- Create: `C:\path\to\douban-taste-recommender\tests\test_readme.py`
- Modify: `C:\path\to\douban-taste-recommender\README.md`

**Interfaces:**
- Consumes: current `README.md`
- Produces: README sections with direct crawler workflow and Cookie tutorial

- [ ] **Step 1: Write failing README tests**

Create `C:\path\to\douban-taste-recommender\tests\test_readme.py`:

```python
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


class ReadmeTests(unittest.TestCase):
    def test_readme_explains_direct_douban_crawler(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("鐩存帴鎶撳彇璞嗙摚鏁版嵁", text)
        self.assertIn("璞嗙摚鐢ㄦ埛 ID 鎴栦富椤甸摼鎺?, text)
        self.assertIn("Cookie 鏄彲閫夐」", text)

    def test_readme_contains_cookie_tutorial_and_privacy_copy(self):
        text = (ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Cookie 鑾峰彇鏁欑▼", text)
        self.assertIn("F12", text)
        self.assertIn("Network / 缃戠粶", text)
        self.assertIn("Cookie 鍙敤浜庢湰鏈鸿姹傝眴鐡ｉ〉闈?, text)
        self.assertIn("涓嶄細淇濆瓨鍒扮鐩?, text)


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

Append this section to `C:\path\to\douban-taste-recommender\README.md`:

```markdown

## 鐩存帴鎶撳彇璞嗙摚鏁版嵁

鐜板湪鍙互涓嶅€熷姪澶栭儴瀵煎嚭宸ュ叿锛岀洿鎺ュ湪鏈湴缃戦〉閲屾姄鍙栬眴鐡ｆ暟鎹細

1. 鍚姩搴旂敤锛歚.\run_app.ps1`
2. 鎵撳紑 <http://127.0.0.1:7861>
3. 鍦ㄢ€滅涓€姝ワ細杩炴帴璞嗙摚鈥濋噷杈撳叆璞嗙摚鐢ㄦ埛 ID 鎴栦富椤甸摼鎺ャ€?4. 濡傛灉鍏紑鏁版嵁澶熺敤锛孋ookie 鍙互鐣欑┖銆?5. 濡傛灉鎶撲笉鍒板畬鏁磋瘎鍒嗭紝鍐嶇矘璐?Cookie 鍚庨噸璇曘€?
Cookie 鏄彲閫夐」銆傚畠鍙敤浜庢湰鏈鸿姹傝眴鐡ｉ〉闈紝涓嶄細淇濆瓨鍒扮鐩橈紝涓嶄細鍐欏叆鎶ュ憡锛屼篃涓嶄細涓婁紶鍒板閮ㄦ湇鍔°€?
## Cookie 鑾峰彇鏁欑▼

1. 鎵撳紑娴忚鍣ㄥ苟鐧诲綍璞嗙摚銆?2. 杩涘叆浠绘剰璞嗙摚椤甸潰锛屼緥濡?`https://movie.douban.com/`銆?3. 鎸?`F12` 鎵撳紑寮€鍙戣€呭伐鍏枫€?4. 閫夋嫨 `Network / 缃戠粶`銆?5. 鍒锋柊椤甸潰銆?6. 鐐瑰嚮浠绘剰 `movie.douban.com` 鎴?`www.douban.com` 璇锋眰銆?7. 鍦ㄥ彸渚?`Headers / 鏍囧ご` 涓壘鍒?`Request Headers`銆?8. 澶嶅埗鍏朵腑 `Cookie: ` 鍚庨潰鐨勬暣娈靛唴瀹广€?9. 绮樿创鍒版湰搴旂敤鐨?Cookie 杈撳叆妗嗐€?
濡傛灉鎶撳彇澶辫触锛屽厛纭璞嗙摚缃戦〉鏈韩鑳芥甯告墦寮€锛屽啀鎶婃渶澶氭姄鍙栭〉鏁拌皟灏忓悗閲嶈瘯銆?```

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
  - `C:\path\to\douban-taste-recommender\src\douban_recommender\*.py`
  - `C:\path\to\douban-taste-recommender\tests\*.py`

**Interfaces:**
- Consumes: all features from Tasks 1-6
- Produces: verified local app and clean git working tree

- [ ] **Step 1: Run all unit tests**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m unittest discover -s tests -v
```

Expected: all tests report `ok` and final output contains `OK`.

- [ ] **Step 2: Run CLI smoke test**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
python -m douban_recommender.cli --ratings sample_data\ratings_sample.csv --candidates sample_data\candidates_sample.csv --like "鎮枒,鐘姜,鐜板疄涓讳箟" --dislike "鐢滃疇,鐙楄" --limit 5 --output output\final_smoke.html
```

Expected: exit code `0`, output includes `宸茬敓鎴恅, and top results do not include the user's rated titles from `sample_data\ratings_sample.csv`.

- [ ] **Step 3: Run web API smoke test**

Run:

```powershell
$env:PYTHONPATH = "C:\path\to\douban-taste-recommender\src"
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
    assert "绗竴姝ワ細杩炴帴璞嗙摚" in home
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
$root = Resolve-Path "C:\path\to\douban-taste-recommender"
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
