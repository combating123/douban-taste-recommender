# CineScope Studio Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the local Douban recommender into CineScope Studio: reliable Douban sync diagnostics, local cache, movie/series/anime candidate expansion, quality-first recommendations, and a cinematic poster-wall UI.

**Architecture:** Keep the dependency-free Python standard-library HTTP server. Split the system into focused modules: `crawler.py` for sync and diagnostics, `storage.py` for non-sensitive cache, `candidate_planner.py` for query plans, `douban_sources.py` for public candidate fetching, `recommender.py` for sectioned scoring, `web.py` for APIs, and `web_ui.py` for the local app.

**Tech Stack:** Python standard library only; `http.server`, `urllib`, `json`, `dataclasses`, `re`, `html`, `unittest`; frontend is one local HTML/CSS/vanilla JS document.

## Global Constraints

- UI copy is Simplified Chinese.
- Cookie is optional and used only for current local Douban requests.
- Cookie is never written to disk, logs, API responses, diagnostics, README examples, generated reports, or cache files.
- No automatic Douban login, CAPTCHA solving, commercial account system, cloud sync, payment, or ads.
- Default Douban sync page count is `40`; allowed range is `1..200`.
- Default recommendation scope includes movie, series, and anime.
- Default taste text is `评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以`.
- Default avoid text is `电视剧古装，注水剧，低分狗血，粗制滥造`.
- Default recommendation result limit is `120`; first curated section contains `24` items.
- Implementation uses TDD: write failing tests, verify failure, implement, verify passing tests, commit.

---

## File Structure

- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\serialization.py` — JSON round-trip and Cookie redaction.
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py` — diagnostics, page classification, scale, fallback parsing.
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\storage.py` — non-sensitive JSON cache under `output/cache`.
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\candidate_planner.py` — movie/series/anime query planner.
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\douban_sources.py` — fetch planned candidates with partial diagnostics.
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\recommender.py` — sectioned quality-first ranking.
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py` — sync/cache/recommend APIs.
- Replace: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py` — CineScope Studio UI.
- Modify: `C:\path\to\douban-taste-recommender\README.md` — clean Chinese guide and Cookie tutorial.
- Add/modify tests in `C:\path\to\douban-taste-recommender\tests\`.

---

### Task 1: Serialization Safety and README Encoding Guard

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\serialization.py`
- Modify: `C:\path\to\douban-taste-recommender\tests\test_serialization.py`
- Create/Modify: `C:\path\to\douban-taste-recommender\tests\test_readme.py`

**Interfaces:**
- Consumes: `MediaItem` from `douban_recommender.models`.
- Produces: `redact_cookie_from_text(value: str, cookie: str) -> str`.

- [ ] **Step 1: Write failing tests**

```python
# tests/test_serialization.py
class CookieRedactionTextTests(unittest.TestCase):
    def test_redact_cookie_from_text_removes_raw_cookie_and_values(self):
        from douban_recommender.serialization import redact_cookie_from_text
        cookie = 'bid=abc123; ck=secret-token; dbcl2="999:user"'
        message = 'failed with bid=abc123 and ck=secret-token in Cookie header'
        redacted = redact_cookie_from_text(message, cookie)
        self.assertNotIn('abc123', redacted)
        self.assertNotIn('secret-token', redacted)
        self.assertNotIn('999:user', redacted)
        self.assertIn('<redacted>', redacted)
```

```python
# tests/test_readme.py
from pathlib import Path
import unittest
ROOT = Path(__file__).resolve().parents[1]
class ReadmeEncodingTests(unittest.TestCase):
    def test_readme_contains_readable_chinese_title(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('豆瓣', text)
        self.assertIn('CineScope Studio', text)
        self.assertNotIn('璞嗙摚', text)
        self.assertNotIn('鎶撳彇', text)
```

- [ ] **Step 2: Verify failure**

```powershell
cd C:\path\to\douban-taste-recommender
$env:PYTHONPATH="$PWD\src"
$env:PYTHONDONTWRITEBYTECODE="1"
python -m unittest tests.test_serialization tests.test_readme -v
```

Expected: failure because the helper is missing and README is not yet rewritten.

- [ ] **Step 3: Implement helper**

```python
def redact_cookie_from_text(value: str, cookie: str) -> str:
    text = str(value or '')
    raw_cookie = str(cookie or '').strip()
    if not raw_cookie:
        return text
    text = text.replace(raw_cookie, redact_cookie(raw_cookie))
    text = text.replace(raw_cookie.replace(' ', ''), redact_cookie(raw_cookie))
    for part in raw_cookie.split(';'):
        piece = part.strip()
        if not piece:
            continue
        if '=' in piece:
            name, secret = piece.split('=', 1)
            name = name.strip()
            secret = secret.strip().strip('"')
            if secret:
                text = text.replace(secret, '<redacted>')
            if name:
                text = text.replace(f'{name}={secret}', f'{name}=<redacted>')
        else:
            text = text.replace(piece, '<redacted>')
    return text
```

- [ ] **Step 4: Replace README title and intro**

```markdown
# CineScope Studio：豆瓣私人影视策展器

CineScope Studio 是一个本地运行的豆瓣影视资料同步、口味分析和推荐工作台。你可以输入豆瓣用户 ID 或主页链接，可选粘贴 Cookie，同步“看过 / 想看”数据，再获得电影、电视剧、动漫三类推荐。

项目坚持本地优先：Cookie 只用于本机请求豆瓣页面，不保存到磁盘，不写入报告，不上传到外部服务。
```

- [ ] **Step 5: Verify pass and commit**

```powershell
python -m unittest tests.test_serialization tests.test_readme -v
git add src/douban_recommender/serialization.py tests/test_serialization.py tests/test_readme.py README.md
git commit -m "chore: harden serialization and readable docs"
```

---

### Task 2: Crawl Diagnostics and Page Classification

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`
- Modify: `C:\path\to\douban-taste-recommender\tests\test_crawler.py`

**Interfaces:**
- Produces: `PageDiagnostic`, enhanced `CrawlResult`, `classify_collection_page(page_html: str, parsed_count: int) -> tuple[str, str]`.

- [ ] **Step 1: Write failing classifier tests**

```python
class CrawlerDiagnosticTests(unittest.TestCase):
    def test_classify_login_required_page(self):
        from douban_recommender.crawler import classify_collection_page
        classification, message = classify_collection_page('<html>登录后查看更多 请登录</html>', 0)
        self.assertEqual(classification, 'login_required')
        self.assertIn('需要 Cookie', message)

    def test_classify_security_check_page(self):
        from douban_recommender.crawler import classify_collection_page
        classification, message = classify_collection_page('<html>检测到有异常请求 captcha verify</html>', 0)
        self.assertEqual(classification, 'security_check')
        self.assertIn('安全验证', message)

    def test_classify_nonempty_parse_failure(self):
        from douban_recommender.crawler import classify_collection_page
        html = '<a href="https://movie.douban.com/subject/1234567/">片名</a>'
        classification, message = classify_collection_page(html, 0)
        self.assertEqual(classification, 'parse_failed_nonempty')
        self.assertIn('页面有内容', message)
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_crawler.CrawlerDiagnosticTests -v
```

Expected: failure because classifier is missing.

- [ ] **Step 3: Add structures and classifier**

```python
@dataclass
class PageDiagnostic:
    status: str
    start: int
    url: str
    http_status: int | None = None
    item_count: int = 0
    classification: str = ''
    message: str = ''


def classify_collection_page(page_html: str, parsed_count: int) -> tuple[str, str]:
    text = clean_html(page_html or '')
    lower = text.lower()
    if parsed_count > 0:
        return 'ok_with_items', f'解析到 {parsed_count} 条'
    if any(marker in text for marker in ['登录后', '请登录', '登陆后', '加入豆瓣']):
        return 'login_required', '页面提示需要登录或需要 Cookie 才能查看完整数据'
    if any(marker in lower for marker in ['captcha', 'verify']) or any(marker in text for marker in ['异常请求', '安全验证', '机器人']):
        return 'security_check', '豆瓣返回安全验证页，建议稍后重试或减少页数'
    if '仅自己可见' in text or '没有权限' in text:
        return 'privacy_or_permission', '页面可能受隐私或权限限制'
    if 'movie.douban.com/subject/' in (page_html or ''):
        return 'parse_failed_nonempty', '页面有内容但当前解析器未识别到标准条目'
    if len(text.strip()) < 80:
        return 'true_empty_page', '已到达真实空白分页'
    return 'parse_failed_nonempty', '页面有内容但解析结果为空'
```

Extend `CrawlResult`:

```python
    diagnostics: list[PageDiagnostic] = field(default_factory=list)
    expected_collect: int | None = None
    expected_wish: int | None = None
    completeness: dict[str, object] = field(default_factory=dict)
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_crawler.CrawlerDiagnosticTests -v
git add src/douban_recommender/crawler.py tests/test_crawler.py
git commit -m "feat: classify douban crawl pages"
```

---

### Task 3: Scale Sync to 242 / 34 and Add Completeness

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`
- Modify: `C:\path\to\douban-taste-recommender\tests\test_crawler.py`

**Interfaces:**
- Produces: `calculate_completeness(collect_count: int, wish_count: int, expected_collect: int | None, expected_wish: int | None) -> dict[str, object]`; `crawl_user_collections` default `max_pages=40`, clamp `1..200`, `include_do=False`, expected counts.

- [ ] **Step 1: Write failing large sync tests**

```python
class CrawlerScaleTests(unittest.TestCase):
    def make_page(self, status, start, count):
        rows = []
        for index in range(count):
            subject_id = 8000000 + start + index
            title = f'{status}-{start + index}'
            rows.append(f'<div class="item"><a href="https://movie.douban.com/subject/{subject_id}/"><em>{title}</em></a><img alt="{title}" src="https://img.example/{subject_id}.jpg"><li class="intro">2024 / 中国大陆 / 剧情 / 导演 / 演员</li><span class="rating5-t"></span></div>')
        return '<html><body>' + ''.join(rows) + '</body></html>'

    def test_crawl_default_pages_cover_242_collect_and_34_wish(self):
        from douban_recommender.crawler import crawl_user_collections
        def fake_fetcher(user_id, status, start, cookie='', timeout=12):
            if status == 'collect' and start < 240:
                return self.make_page(status, start, 15)
            if status == 'collect' and start == 240:
                return self.make_page(status, start, 2)
            if status == 'wish' and start < 30:
                return self.make_page(status, start, 15)
            if status == 'wish' and start == 30:
                return self.make_page(status, start, 4)
            return '<html><body></body></html>'
        result = crawl_user_collections('moviefan123', max_pages=40, include_wish=True, expected_collect=242, expected_wish=34, fetcher=fake_fetcher, sleep_seconds=0)
        self.assertEqual(len([x for x in result.items if x.source.endswith(':collect')]), 242)
        self.assertEqual(len([x for x in result.items if x.source.endswith(':wish')]), 34)
        self.assertEqual(result.completeness['collect_percent'], 100)
        self.assertEqual(result.completeness['wish_percent'], 100)
        self.assertGreater(len(result.diagnostics), 0)

    def test_crawl_clamps_max_pages_to_200(self):
        from douban_recommender.crawler import crawl_user_collections
        calls = []
        def fake_fetcher(user_id, status, start, cookie='', timeout=12):
            calls.append(start)
            return self.make_page(status, start, 15)
        crawl_user_collections('moviefan123', max_pages=999, include_wish=False, fetcher=fake_fetcher, sleep_seconds=0)
        self.assertEqual(len(calls), 200)
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_crawler.CrawlerScaleTests -v
```

Expected: failure because completeness/default/clamp logic is not in place.

- [ ] **Step 3: Add completeness helper and update crawl signature**

```python
def calculate_completeness(collect_count: int, wish_count: int, expected_collect: int | None, expected_wish: int | None) -> dict[str, object]:
    def percent(actual: int, expected: int | None) -> int | None:
        if not expected:
            return None
        return min(100, int(round(actual * 100 / max(expected, 1))))
    collect_percent = percent(collect_count, expected_collect)
    wish_percent = percent(wish_count, expected_wish)
    return {'collect_count': collect_count, 'wish_count': wish_count, 'expected_collect': expected_collect, 'expected_wish': expected_wish, 'collect_percent': collect_percent, 'wish_percent': wish_percent, 'is_complete': (collect_percent in (None, 100)) and (wish_percent in (None, 100))}
```

Change `crawl_user_collections` to accept:

```python
max_pages: int = 40,
include_do: bool = False,
expected_collect: int | None = None,
expected_wish: int | None = None,
```

Set:

```python
limited_pages = max(1, min(200, int(max_pages)))
statuses = ['collect']
if include_wish:
    statuses.append('wish')
if include_do:
    statuses.append('do')
result = CrawlResult(expected_collect=expected_collect, expected_wish=expected_wish)
```

For each fetched page, append a diagnostic:

```python
url = build_user_collection_url(user_id, status, start)
classification, message = classify_collection_page(page_html, len(page_items))
result.diagnostics.append(PageDiagnostic(status=status, start=start, url=url, item_count=len(page_items), classification=classification, message=message))
```

Before return:

```python
collect_count = sum(1 for item in result.items if item.source.endswith(':collect'))
wish_count = sum(1 for item in result.items if item.source.endswith(':wish'))
result.completeness = calculate_completeness(collect_count, wish_count, expected_collect, expected_wish)
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_crawler.CrawlerScaleTests tests.test_crawler.CrawlerParserTests -v
git add src/douban_recommender/crawler.py tests/test_crawler.py
git commit -m "feat: scale douban sync with completeness"
```

---

### Task 4: Add Fallback Parser and Anime Inference

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\crawler.py`
- Modify: `C:\path\to\douban-taste-recommender\tests\test_crawler.py`

**Interfaces:**
- Produces: `parse_fallback_subject_links(page_html: str, status: str) -> list[MediaItem]`; `infer_media_type` returns `动漫` for animation/anime signals.

- [ ] **Step 1: Write failing parser variant tests**

```python
class CrawlerParserVariantTests(unittest.TestCase):
    def test_parse_subject_links_when_item_class_missing(self):
        from douban_recommender.crawler import parse_user_collection_html
        html = '<html><body><div class="grid-view"><a href="https://movie.douban.com/subject/1292052/"><img alt="肖申克的救赎" src="https://img.example/s.jpg"></a><span class="rating5-t"></span></div></body></html>'
        items = parse_user_collection_html(html, status='collect')
        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, '肖申克的救赎')
        self.assertEqual(items[0].douban_id, '1292052')
        self.assertEqual(items[0].cover, 'https://img.example/s.jpg')

    def test_parse_anime_media_type_from_intro(self):
        from douban_recommender.crawler import parse_user_collection_html
        html = '<div class="item"><a href="https://movie.douban.com/subject/20495023/"><em>排球少年</em></a><img alt="排球少年" src="https://img.example/h.jpg"><li class="intro">2014 / 日本 / 动画 运动 / 满仲劝 / 村濑步</li></div>'
        items = parse_user_collection_html(html, status='collect')
        self.assertEqual(items[0].media_type, '动漫')
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_crawler.CrawlerParserVariantTests -v
```

Expected: failure because fallback parser and anime inference are missing.

- [ ] **Step 3: Add anime inference and fallback parser**

```python
# inside infer_media_type, before series detection
if any(marker in blob for marker in ['动画', '动漫', '番剧', '日本动画', '剧场版', 'anime']):
    return '动漫'
```

```python
def parse_fallback_subject_links(page_html: str, status: str) -> list[MediaItem]:
    items: list[MediaItem] = []
    seen: set[str] = set()
    pattern = r'<a[^>]+href=["\'](https://movie\.douban\.com/subject/(\d+)/?[^"\']*)["\'][^>]*>(.*?)</a>'
    for match in re.finditer(pattern, page_html or '', flags=re.S | re.I):
        url = html.unescape(match.group(1))
        subject_id = match.group(2)
        inner = match.group(3)
        local = page_html[max(0, match.start() - 300): match.end() + 300]
        title = clean_html(first_match(r'<img[^>]+alt=["\']([^"\']+)["\']', inner + local)) or clean_html(inner)
        cover = html.unescape(first_match(r'<img[^>]+src=["\']([^"\']+)["\']', inner + local))
        if not title or subject_id in seen:
            continue
        seen.add(subject_id)
        tag = '想看' if status == 'wish' else '看过'
        items.append(MediaItem(title=title, url=url, douban_id=subject_id, cover=cover, tags=[tag], source=f'douban_user:{status}'))
    return items
```

Merge fallback results into `parse_user_collection_html` only for unseen IDs.

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_crawler.CrawlerParserVariantTests -v
git add src/douban_recommender/crawler.py tests/test_crawler.py
git commit -m "feat: parse douban collection variants"
```

---

### Task 5: Non-Sensitive Local Cache

**Files:**
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\storage.py`
- Create: `C:\path\to\douban-taste-recommender\tests\test_storage.py`

**Interfaces:**
- Produces: `CacheStore`, `CacheSummary`, `default_cache_dir(root: Path) -> Path`.

- [ ] **Step 1: Write failing storage tests**

```python
from pathlib import Path
import tempfile
import unittest
from douban_recommender.models import MediaItem
from douban_recommender.storage import CacheStore

class CacheStoreTests(unittest.TestCase):
    def test_library_round_trips_without_cookie(self):
        with tempfile.TemporaryDirectory() as tmp:
            store = CacheStore(Path(tmp))
            store.save_library([MediaItem(title='隐秘的角落', douban_id='33404425', tags=['看过'])], sync_report={'status': 'ok', 'cookie': 'bid=secret'})
            loaded_items, report = store.load_library()
            raw = (Path(tmp) / 'library.json').read_text(encoding='utf-8') + (Path(tmp) / 'sync_report.json').read_text(encoding='utf-8')
            self.assertEqual(loaded_items[0].title, '隐秘的角落')
            self.assertEqual(report['status'], 'ok')
            self.assertNotIn('secret', raw)
            self.assertNotIn('bid=', raw)

    def test_broken_cache_returns_empty_values(self):
        with tempfile.TemporaryDirectory() as tmp:
            (Path(tmp) / 'library.json').write_text('{bad json', encoding='utf-8')
            items, report = CacheStore(Path(tmp)).load_library()
            self.assertEqual(items, [])
            self.assertEqual(report, {})
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_storage -v
```

Expected: failure because storage module is missing.

- [ ] **Step 3: Implement cache store**

```python
from __future__ import annotations
from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any
from .models import MediaItem
from .serialization import media_item_from_dict, media_item_to_dict

SENSITIVE_KEYS = {'cookie', 'Cookie', 'set-cookie', 'Set-Cookie'}

def default_cache_dir(root: Path) -> Path:
    return root / 'output' / 'cache'

def scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {k: scrub_sensitive(v) for k, v in value.items() if k not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [scrub_sensitive(v) for v in value]
    if isinstance(value, str) and ('bid=' in value or 'ck=' in value or 'dbcl2=' in value):
        return '<redacted>'
    return value

@dataclass
class CacheSummary:
    cache_dir: str
    files: list[str]

class CacheStore:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)
    def path(self, name: str) -> Path:
        return self.cache_dir / name
    def save_json(self, name: str, payload: dict[str, Any]) -> None:
        self.path(name).write_text(json.dumps(scrub_sensitive(payload), ensure_ascii=False, indent=2), encoding='utf-8')
    def load_json(self, name: str) -> dict[str, Any]:
        try:
            path = self.path(name)
            return json.loads(path.read_text(encoding='utf-8')) if path.exists() else {}
        except Exception:
            return {}
    def save_library(self, items: list[MediaItem], sync_report: dict[str, Any]) -> None:
        self.save_json('library.json', {'items': [media_item_to_dict(item) for item in items]})
        self.save_json('sync_report.json', sync_report)
    def load_library(self) -> tuple[list[MediaItem], dict[str, Any]]:
        data = self.load_json('library.json')
        report = self.load_json('sync_report.json')
        return [media_item_from_dict(row) for row in data.get('items', []) if isinstance(row, dict)], report
    def summary(self) -> CacheSummary:
        return CacheSummary(str(self.cache_dir), sorted(p.name for p in self.cache_dir.glob('*.json')))
    def clear(self) -> int:
        removed = 0
        for path in self.cache_dir.glob('*.json'):
            path.unlink(); removed += 1
        return removed
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_storage -v
git add src/douban_recommender/storage.py tests/test_storage.py
git commit -m "feat: add local non-sensitive cache"
```

---

### Task 6: Candidate Planner for Movie, Series, and Anime

**Files:**
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\candidate_planner.py`
- Create: `C:\path\to\douban-taste-recommender\tests\test_candidate_planner.py`

**Interfaces:**
- Produces: `CandidateQuery`, `build_candidate_plan(profile, include_movies=True, include_series=True, include_anime=True, depth='deep', wishlist=None) -> list[CandidateQuery]`.

- [ ] **Step 1: Write failing candidate planner tests**

```python
import unittest
from douban_recommender.candidate_planner import build_candidate_plan
from douban_recommender.models import MediaItem
from douban_recommender.profiler import build_taste_profile

class CandidatePlannerTests(unittest.TestCase):
    def test_plan_contains_movie_series_and_anime_channels(self):
        profile = build_taste_profile([], like_terms='评分高，剧情好', dislike_terms='电视剧古装')
        plan = build_candidate_plan(profile, include_movies=True, include_series=True, include_anime=True, depth='deep')
        channels = {query.channel for query in plan}
        tags = ' '.join(query.tags for query in plan)
        self.assertIn('movie_quality', channels)
        self.assertIn('series_quality', channels)
        self.assertIn('anime_quality', channels)
        self.assertIn('电影', tags)
        self.assertIn('电视剧', tags)
        self.assertIn('动画', tags)
        self.assertTrue(any(query.start > 0 for query in plan))

    def test_plan_uses_wishlist_boost(self):
        profile = build_taste_profile([], like_terms='剧情', dislike_terms='')
        wishlist = [MediaItem(title='排球少年', media_type='动漫', tags=['想看', '运动'])]
        plan = build_candidate_plan(profile, wishlist=wishlist)
        self.assertTrue(any(query.channel == 'wishlist_boost' for query in plan))
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_candidate_planner -v
```

Expected: failure because candidate planner is missing.

- [ ] **Step 3: Implement planner**

```python
from __future__ import annotations
from dataclasses import dataclass
from .models import MediaItem
from .profiler import TasteProfile

@dataclass(frozen=True)
class CandidateQuery:
    channel: str
    tags: str
    sort: str = 'U'
    start: int = 0
    limit: int = 20
    media_type: str = '电影'

def _manual_terms(profile: TasteProfile) -> list[str]:
    terms: list[str] = []
    for term in list(profile.manual_likes) + ['剧情', '高分', '口碑佳']:
        text = str(term or '').strip()
        if text and text not in terms:
            terms.append(text)
    return terms[:6]

def _add_offsets(out: list[CandidateQuery], channel: str, tags_list: list[str], media_type: str, starts: list[int]) -> None:
    for tags in tags_list:
        for sort in ('U', 'R'):
            for start in starts:
                out.append(CandidateQuery(channel=channel, tags=tags, sort=sort, start=start, media_type=media_type))

def build_candidate_plan(profile: TasteProfile, include_movies: bool = True, include_series: bool = True, include_anime: bool = True, depth: str = 'deep', wishlist: list[MediaItem] | None = None) -> list[CandidateQuery]:
    starts = [0, 20, 40] if depth == 'deep' else [0]
    terms = _manual_terms(profile)
    out: list[CandidateQuery] = []
    if include_movies:
        _add_offsets(out, 'movie_quality', ['电影', '电影,剧情', '电影,高分', '电影,悬疑', '电影,犯罪'] + [f'电影,{term}' for term in terms[:3]], '电影', starts)
    if include_series:
        _add_offsets(out, 'series_quality', ['电视剧', '电视剧,剧情', '电视剧,悬疑', '电视剧,犯罪', '电视剧,高分'], '电视剧', starts)
    if include_anime:
        _add_offsets(out, 'anime_quality', ['动画', '动漫', '日本动画', '电影,动画', '电视剧,动画'], '动漫', starts)
    for item in wishlist or []:
        for tag in (item.genres + item.tags + [item.media_type])[:4]:
            if tag and tag not in {'想看', '看过'}:
                out.append(CandidateQuery(channel='wishlist_boost', tags=f'{item.media_type or "电影"},{tag}', media_type=item.media_type or '电影'))
    seen: set[tuple[str, str, str, int]] = set()
    deduped: list[CandidateQuery] = []
    for query in out:
        key = (query.channel, query.tags, query.sort, query.start)
        if key not in seen:
            deduped.append(query); seen.add(key)
    return deduped
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_candidate_planner -v
git add src/douban_recommender/candidate_planner.py tests/test_candidate_planner.py
git commit -m "feat: plan movie series anime candidates"
```

---

### Task 7: Fetch Planned Candidates with Partial Success

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\douban_sources.py`
- Create/Modify: `C:\path\to\douban-taste-recommender\tests\test_douban_sources.py`

**Interfaces:**
- Produces: `CandidateFetchReport`, `fetch_candidates_from_plan(plan: list[CandidateQuery], fetcher=None, sleep_seconds=0.15) -> CandidateFetchReport`.

- [ ] **Step 1: Write failing fetch plan test**

```python
import unittest
from douban_recommender.candidate_planner import CandidateQuery
from douban_recommender.douban_sources import fetch_candidates_from_plan
from douban_recommender.models import MediaItem

class CandidateFetchPlanTests(unittest.TestCase):
    def test_fetch_candidates_from_plan_dedupes_and_keeps_partial_success(self):
        plan = [CandidateQuery('movie_quality', '电影,剧情', media_type='电影'), CandidateQuery('anime_quality', '动画', media_type='动漫'), CandidateQuery('bad', 'bad')]
        def fake_fetcher(tags, sort='U', start=0, limit=20):
            if tags == 'bad':
                raise RuntimeError('network failed')
            return [MediaItem(title='共同条目', douban_id='1', media_type='电影'), MediaItem(title=tags, douban_id=tags, media_type='动漫' if tags == '动画' else '电影')]
        report = fetch_candidates_from_plan(plan, fetcher=fake_fetcher, sleep_seconds=0)
        self.assertEqual(len([item for item in report.items if item.douban_id == '1']), 1)
        self.assertTrue(any(item.media_type == '动漫' for item in report.items))
        self.assertEqual(report.failed_queries, 1)
        self.assertGreaterEqual(report.successful_queries, 2)
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_douban_sources.CandidateFetchPlanTests -v
```

Expected: failure because `fetch_candidates_from_plan` is missing.

- [ ] **Step 3: Implement fetch report**

```python
from dataclasses import dataclass, field
from .candidate_planner import CandidateQuery

@dataclass
class CandidateFetchReport:
    items: list[MediaItem] = field(default_factory=list)
    successful_queries: int = 0
    failed_queries: int = 0
    errors: list[str] = field(default_factory=list)

def fetch_candidates_from_plan(plan: list[CandidateQuery], fetcher=None, sleep_seconds: float = 0.15) -> CandidateFetchReport:
    fetch = fetcher or fetch_explore
    report = CandidateFetchReport()
    seen: set[str] = set()
    for query in plan:
        try:
            rows = fetch(tags=query.tags, sort=query.sort, start=query.start, limit=query.limit)
            report.successful_queries += 1
        except Exception as exc:
            report.failed_queries += 1
            report.errors.append(f'{query.channel} {query.tags} start={query.start}: {exc}')
            rows = []
        for row in rows:
            if not row.media_type or row.media_type == '电影':
                row.media_type = query.media_type
            row.source = row.source or f'douban_plan:{query.channel}:{query.tags}'
            key = row.douban_id or row.title
            if key and key not in seen:
                report.items.append(row); seen.add(key)
        if sleep_seconds:
            time.sleep(sleep_seconds)
    return report
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_douban_sources.CandidateFetchPlanTests -v
git add src/douban_recommender/douban_sources.py tests/test_douban_sources.py
git commit -m "feat: fetch planned douban candidates"
```

---

### Task 8: Quality-First Recommendation Sections

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\recommender.py`
- Create/Modify: `C:\path\to\douban-taste-recommender\tests\test_recommender.py`

**Interfaces:**
- Produces: enhanced `Recommendation` fields `section`, `badges`, `quality_label`, `short_reason`, `risk_label`, `is_wishlist`; `recommend(..., include_anime=True)`.

- [ ] **Step 1: Write failing recommendation tests**

```python
import unittest
from douban_recommender.models import MediaItem
from douban_recommender.profiler import build_taste_profile
from douban_recommender.recommender import recommend

class CineScopeRecommendationTests(unittest.TestCase):
    def test_quality_first_includes_anime_and_downranks_costume_series(self):
        rated = [MediaItem(title='已看电影', douban_id='seen1', media_type='电影', tags=['看过'], my_rating=5)]
        candidates = [MediaItem(title='高分剧情片', douban_id='m1', media_type='电影', douban_rating=9.0, genres=['剧情'], summary='人物塑造扎实'), MediaItem(title='高分动画', douban_id='a1', media_type='动漫', douban_rating=9.1, genres=['动画', '剧情'], summary='叙事强'), MediaItem(title='古装大剧', douban_id='s1', media_type='电视剧', douban_rating=9.2, genres=['古装', '剧情'], summary='宫廷 权谋')]
        profile = build_taste_profile(rated, like_terms='评分高，剧情好，叙事强', dislike_terms='电视剧古装，注水剧')
        recs = recommend(rated, candidates, profile, limit=10, include_movies=True, include_series=True, include_anime=True)
        titles = [rec.item.title for rec in recs]
        self.assertIn('高分动画', titles)
        self.assertGreater(recs[titles.index('高分剧情片')].score, recs[titles.index('古装大剧')].score)
        self.assertTrue(any('古装' in warning for warning in recs[titles.index('古装大剧')].warnings))
        self.assertTrue(recs[0].section)
        self.assertTrue(recs[0].short_reason)

    def test_wishlist_item_is_tagged_not_excluded(self):
        rated = [MediaItem(title='想看的动画', douban_id='wish1', media_type='动漫', tags=['想看'])]
        candidates = [MediaItem(title='想看的动画', douban_id='wish1', media_type='动漫', douban_rating=8.8, genres=['动画'])]
        profile = build_taste_profile(rated, like_terms='动画', dislike_terms='')
        recs = recommend(rated, candidates, profile, limit=5, include_anime=True)
        self.assertEqual(len(recs), 1)
        self.assertTrue(recs[0].is_wishlist)
        self.assertIn('想看', recs[0].badges)
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_recommender.CineScopeRecommendationTests -v
```

Expected: failure because new fields and anime parameter are missing.

- [ ] **Step 3: Implement recommendation metadata and scoring rules**

Add fields to `Recommendation`, include them in `to_dict()`, add `include_anime` to `recommend`, separate watched from wish items, keep wish items as recommendable, and add this scoring block in `score_item`:

```python
quality_terms = ['剧情', '叙事', '人物', '口碑', '高分']
if item.douban_rating and item.douban_rating >= 8.5:
    score += 6.0
if any(term in blob for term in quality_terms):
    score += 4.0
costume_terms = ['古装', '武侠', '仙侠', '宫廷', '历史', '朝代', '权谋']
if item.media_type == '电视剧' and any(term in blob for term in costume_terms):
    score -= 18.0
    warnings.append('电视剧古装 / 宫廷 / 历史向内容，与你的避雷设置冲突')
section = '高分剧情'
if item.media_type == '动漫':
    section = '动漫'
elif item.media_type == '电视剧':
    section = '电视剧'
elif item.douban_rating and item.douban_rating >= 8.7:
    section = '必看 Top Picks'
quality_label = '高分佳作' if item.douban_rating and item.douban_rating >= 8.5 else '潜力推荐'
short_reason = reasons[0] if reasons else '质量优先策略推荐'
risk_label = warnings[0] if warnings else ''
badges = [item.media_type] if item.media_type else []
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_recommender.CineScopeRecommendationTests -v
git add src/douban_recommender/recommender.py tests/test_recommender.py
git commit -m "feat: rank cinescope recommendations"
```

---

### Task 9: Sync, Cache, and Enhanced Recommendation APIs

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`
- Create/Modify: `C:\path\to\douban-taste-recommender\tests\test_web_api.py`

**Interfaces:**
- Produces: `POST /api/sync-douban`, legacy alias `/api/crawl-douban`, `GET /api/cache`, `DELETE /api/cache`, `build_recommendation_sections(recs) -> list[dict[str, object]]`.

- [ ] **Step 1: Write failing API shape tests**

```python
import unittest
from douban_recommender.web import Handler, build_recommendation_sections
from douban_recommender.recommender import Recommendation
from douban_recommender.models import MediaItem

class WebApiShapeTests(unittest.TestCase):
    def test_build_recommendation_sections_groups_by_section(self):
        recs = [Recommendation(item=MediaItem(title='电影A'), score=90, section='必看 Top Picks'), Recommendation(item=MediaItem(title='动画B'), score=88, section='动漫')]
        sections = build_recommendation_sections(recs)
        self.assertEqual(sections[0]['name'], '必看 Top Picks')
        self.assertEqual(sections[0]['count'], 1)
        self.assertEqual(sections[1]['name'], '动漫')

    def test_handler_has_cache_methods(self):
        self.assertTrue(hasattr(Handler, 'handle_cache_get'))
        self.assertTrue(hasattr(Handler, 'handle_cache_delete'))
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_web_api.WebApiShapeTests -v
```

Expected: failure because section helper and cache handlers are missing.

- [ ] **Step 3: Implement routes and helpers**

Add imports:

```python
from .candidate_planner import build_candidate_plan
from .douban_sources import fetch_candidates_from_plan
from .storage import CacheStore, default_cache_dir
CACHE = CacheStore(default_cache_dir(ROOT))
```

Add route handling for `/api/cache`, `/api/sync-douban`, and `DELETE /api/cache`. Add:

```python
def build_recommendation_sections(recs) -> list[dict[str, object]]:
    order = ['必看 Top Picks', '高分剧情', '电影', '电视剧', '动漫', '想看优先', '冷门惊喜']
    grouped: dict[str, list[dict[str, object]]] = {}
    for rec in recs:
        name = rec.section or rec.item.media_type or '全部'
        grouped.setdefault(name, []).append(rec.to_dict())
    sections = []
    for name in order:
        rows = grouped.pop(name, [])
        if rows:
            sections.append({'name': name, 'count': len(rows), 'items': rows})
    for name, rows in grouped.items():
        sections.append({'name': name, 'count': len(rows), 'items': rows})
    return sections
```

Add methods in `Handler`:

```python
def handle_cache_get(self) -> dict:
    items, report = CACHE.load_library()
    summary = CACHE.summary()
    return {'cache_dir': summary.cache_dir, 'files': summary.files, 'library_count': len(items), 'sync_report': report}

def handle_cache_delete(self) -> dict:
    return {'removed': CACHE.clear()}
```

- [ ] **Step 4: Implement sync handler and enhanced recommend handler**

```python
def handle_sync_douban(self, payload: dict) -> dict:
    result = crawl_user_collections(user_id_or_url=payload.get('user_id_or_url') or '', cookie=payload.get('cookie') or '', max_pages=max(1, min(200, int(payload.get('max_pages') or 40))), include_wish=bool(payload.get('include_wish', True)), include_do=bool(payload.get('include_do', False)), expected_collect=int(payload['expected_collect']) if str(payload.get('expected_collect') or '').strip() else None, expected_wish=int(payload['expected_wish']) if str(payload.get('expected_wish') or '').strip() else None)
    collect_count, wish_count = count_crawl_sources(result.items)
    diagnostics = [diag.__dict__ for diag in result.diagnostics]
    CACHE.save_library(result.items, {'counts': result.completeness, 'diagnostics': diagnostics, 'stopped_reason': result.stopped_reason})
    return {'items': [media_item_to_dict(item) for item in result.items], 'counts': {'items': len(result.items), 'collect_count': collect_count, 'wish_count': wish_count, 'pages_ok': result.pages_ok, 'pages_failed': result.pages_failed, 'stopped_reason': result.stopped_reason}, 'diagnostics': diagnostics, 'completeness': result.completeness, 'errors': result.errors}
handle_crawl_douban = handle_sync_douban
```

In `handle_recommend`, call `build_candidate_plan`, `fetch_candidates_from_plan`, pass `include_anime`, and return `sections`.

- [ ] **Step 5: Verify pass and commit**

```powershell
python -m unittest tests.test_web_api.WebApiShapeTests -v
git add src/douban_recommender/web.py tests/test_web_api.py
git commit -m "feat: add cinescope web APIs"
```

---

### Task 10: CineScope Studio UI Redesign

**Files:**
- Replace: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`
- Create/Modify: `C:\path\to\douban-taste-recommender\tests\test_ui_html.py`

**Interfaces:**
- Consumes: `/api/sync-douban`, `/api/recommend`, `/api/cache`.
- Produces: `INDEX_HTML` with hero, sync diagnostics, taste studio, poster wall, tabs, detail drawer, default quality-first copy.

- [ ] **Step 1: Write failing UI tests**

```python
import unittest
from douban_recommender.web_ui import INDEX_HTML

class CineScopeUiHtmlTests(unittest.TestCase):
    def test_ui_contains_cinescope_dashboard_landmarks(self):
        html = INDEX_HTML
        self.assertIn('CineScope Studio', html)
        self.assertIn('cinematic-hero', html)
        self.assertIn('syncTimeline', html)
        self.assertIn('poster-grid', html)
        self.assertIn('detailDrawer', html)
        self.assertIn('评分高，剧情好，叙事强', html)
        self.assertIn('电视剧古装', html)
        self.assertIn('includeAnime', html)
        self.assertIn('/api/sync-douban', html)
        self.assertIn('/api/cache', html)

    def test_ui_has_no_legacy_plain_title_only_experience(self):
        html = INDEX_HTML
        self.assertNotIn('豆瓣口味影视推荐器</h1>', html)
        self.assertIn('私人影视策展器', html)
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_ui_html -v
```

Expected: failure because current UI lacks CineScope landmarks.

- [ ] **Step 3: Replace UI shell**

Implement `INDEX_HTML` with these required tokens and components:

```html
<section class="cinematic-hero">
  <div class="hero-kicker">Local-first Douban Curation</div>
  <h1>CineScope Studio</h1>
  <p>豆瓣私人影视策展器：同步你的看过与想看，分析口味，用电影、电视剧、动漫构建推荐海报墙。</p>
</section>
<aside class="glass-panel" id="controlPanel"></aside>
<section class="glass-panel" id="mainPanel"></section>
<aside class="drawer" id="detailDrawer"></aside>
```

Add CSS classes: `cinematic-hero`, `workspace`, `glass-panel`, `metric-grid`, `timeline`, `tabs`, `poster-grid`, `poster-card`, `drawer`, `empty-state`.

- [ ] **Step 4: Add JS render and API functions**

Implement functions: `renderControls`, `syncDouban`, `generateRecommendations`, `clearCache`, `renderDashboard`, `renderRecommendations`, `openDetail`, `renderEmpty`. Ensure defaults include:

```javascript
<textarea id="tasteText">评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以</textarea>
<textarea id="avoidText">电视剧古装，注水剧，低分狗血，粗制滥造</textarea>
<input id="expectedCollect" type="number" value="242">
<input id="expectedWish" type="number" value="34">
<input id="maxPages" type="number" min="1" max="200" value="40">
<input id="includeAnime" type="checkbox" checked>
```

Ensure `syncDouban` posts to `/api/sync-douban`, `generateRecommendations` posts to `/api/recommend` with `include_anime`, and `clearCache` sends `DELETE` to `/api/cache`.

- [ ] **Step 5: Verify pass and commit**

```powershell
python -m unittest tests.test_ui_html -v
git add src/douban_recommender/web_ui.py tests/test_ui_html.py
git commit -m "feat: redesign cinescope studio UI"
```

---

### Task 11: Complete README and Cookie Tutorial

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\README.md`
- Modify: `C:\path\to\douban-taste-recommender\tests\test_readme.py`

**Interfaces:**
- Produces: clean UTF-8 guide with quick start, 242/34 sync advice, movie/series/anime scope, Cookie tutorial, privacy promise, verification commands.

- [ ] **Step 1: Add README content test**

```python
class ReadmeCineScopeContentTests(unittest.TestCase):
    def test_readme_documents_cinescope_workflow(self):
        text = (ROOT / 'README.md').read_text(encoding='utf-8')
        self.assertIn('CineScope Studio', text)
        self.assertIn('242', text)
        self.assertIn('34', text)
        self.assertIn('电影、电视剧、动漫', text)
        self.assertIn('Cookie 获取教程', text)
        self.assertIn('python -m unittest discover -s tests -v', text)
        self.assertIn('不保存 Cookie', text)
```

- [ ] **Step 2: Verify failure**

```powershell
python -m unittest tests.test_readme -v
```

Expected: failure until README is complete.

- [ ] **Step 3: Rewrite README sections**

Include these headings exactly: `快速启动`, `推荐默认策略`, `同步建议`, `Cookie 获取教程`, `隐私与缓存`, `测试`. Include this command:

```powershell
$env:PYTHONPATH="$PWD\src"
$env:PYTHONDONTWRITEBYTECODE="1"
python -m unittest discover -s tests -v
```

- [ ] **Step 4: Verify pass and commit**

```powershell
python -m unittest tests.test_readme -v
git add README.md tests/test_readme.py
git commit -m "docs: rewrite cinescope studio guide"
```

---

### Task 12: Full Verification and Smoke Test

**Files:**
- Modify only files tied to concrete failing verification output.

**Interfaces:**
- Produces: verified local app state.

- [ ] **Step 1: Run complete unit test suite**

```powershell
cd C:\path\to\douban-taste-recommender
$env:PYTHONPATH="$PWD\src"
$env:PYTHONDONTWRITEBYTECODE="1"
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Run CLI smoke with sample data**

```powershell
python -m douban_recommender.cli --ratings sample_data\ratings_sample.csv --candidates sample_data\candidates_sample.csv --like "评分高, 剧情好" --dislike "电视剧古装, 注水剧" --limit 20 --output output\cinescope-smoke.html
```

Expected: command exits with code 0 and creates `output\cinescope-smoke.html`.

- [ ] **Step 3: Run web smoke**

```powershell
$job = Start-Job -ScriptBlock { Set-Location 'C:\path\to\douban-taste-recommender'; $env:PYTHONPATH="$PWD\src"; python -m douban_recommender.web --no-browser }
Start-Sleep -Seconds 2
try { (Invoke-WebRequest -UseBasicParsing http://127.0.0.1:7861).Content | Select-String 'CineScope Studio' } finally { Stop-Job $job; Remove-Job $job }
```

Expected: response contains `CineScope Studio`.

- [ ] **Step 4: Check git status**

```powershell
git status --short
```

Expected: clean working tree.

- [ ] **Step 5: Commit verification fixes when a concrete fix was made**

```powershell
git add src/douban_recommender tests README.md
git commit -m "fix: pass cinescope verification"
```

Skip this command when Step 1 through Step 4 produce no code changes.

---

## Self-Review Notes

- Spec coverage: sync diagnostics, 242 / 34 completeness, page count 40 / 200, local cache, movie / series / anime candidates, quality-first scoring, costume-drama downranking, poster-wall UI, Cookie tutorial, and verification are mapped to tasks.
- Placeholder scan: the plan uses concrete file paths, commands, expected outcomes, and code snippets for each code-changing task.
- Type consistency: `PageDiagnostic`, `CandidateQuery`, `CandidateFetchReport`, `CacheStore`, enhanced `Recommendation`, `/api/sync-douban`, and `build_recommendation_sections` are introduced before dependent tasks use them.
