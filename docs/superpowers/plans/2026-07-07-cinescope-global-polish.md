# CineScope Global Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Make CineScope Studio resilient and visually polished across sync, taste, recommendation, and detail pages.

**Architecture:** Keep the dependency-free Python HTTP server and one-file vanilla frontend. Add a local curated catalog for fallback candidates, strengthen Douban parsing/proxy behavior, and upgrade the existing UI helpers rather than adding a framework.

**Tech Stack:** Python standard library, `unittest`, vanilla HTML/CSS/JS, local SVG fallbacks, local HTTP proxy environment variables.

## Global Constraints

- UI copy is Simplified Chinese.
- Cookie is never saved, logged, cached, or echoed.
- Do not store proxy subscription URLs; only support local proxy endpoints through environment variables.
- No commercial API keys.
- Movie, series, and anime must all remain first-class sections.
- Poster failures must degrade to local generated title art.
- TDD: every behavior change gets a failing test first.

---

### Task 1: Curated fallback catalog

**Files:**
- Create: `C:\path\to\douban-taste-recommender\src\douban_recommender\curated_catalog.py`
- Test: `C:\path\to\douban-taste-recommender\tests\test_curated_catalog.py`

**Interfaces:**
- Produces: `curated_seed_candidates() -> list[MediaItem]`
- Produces: `backfill_missing_media_types(candidates, include_movies, include_series, include_anime, minimum_per_type=10) -> list[MediaItem]`

- [x] Write failing tests requiring movie / series / anime seeds and minimum per type.
- [x] Implement local seed catalog with no cookies and no paid API.
- [x] Verify tests pass.

### Task 2: Douban source resilience

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\douban_sources.py`
- Test: `C:\path\to\douban-taste-recommender\tests\test_douban_sources.py`

**Interfaces:**
- Produces: `fetch_explore(..., fetcher=None)` raising on Douban security JSON.
- Produces: `subject_detail_urls(item)` with mobile URL first.
- Produces: proxy-aware `http_get()`.

- [x] Write failing tests for security JSON, early stop, and mobile-first detail URLs.
- [x] Implement explicit security errors and consecutive-failure early stop.
- [x] Implement mobile detail URL priority and proxy-aware opener.
- [x] Verify tests pass.

### Task 3: Recommendation API fallback and proxy image behavior

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web.py`
- Test: `C:\path\to\douban-taste-recommender\tests\test_web_api.py`

**Interfaces:**
- Consumes: `backfill_missing_media_types()`
- Produces: API `counts.curated_candidates`
- Produces: image proxy using same proxy opener.

- [x] Write failing API test showing default pool gets anime.
- [x] Backfill missing / thin categories when user did not provide custom CSV.
- [x] Keep custom CSV behavior unchanged.
- [x] Verify tests pass.

### Task 4: Global UI polish

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`
- Test: `C:\path\to\douban-taste-recommender\tests\test_ui_html.py`

**Interfaces:**
- Produces: `imageResilienceGuide()`
- Produces: `tasteDNA()`
- Produces: `renderHeroCarousel()`, `categorySpotlight()`, `spotlightPool()`
- Produces: `peopleCarousel()`, `filterByPerson()`

- [x] Write failing UI contract tests for global polish markers.
- [x] Add global visual system and proxy tutorial.
- [x] Make Hero category-specific.
- [x] Add people carousel and person filtering.
- [x] Verify UI tests pass.

### Task 5: Documentation and verification

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\README.md`
- Test: `C:\path\to\douban-taste-recommender\tests\test_readme.py`

- [x] Document `DOUBAN_RECOMMENDER_HTTP_PROXY`, Clash and V2Ray local-port setup.
- [x] State 鈥滀笉瑕佺矘璐磋闃呭湴鍧€鈥?
- [x] Run full `python -m unittest discover -s tests -v`.
- [x] Run CLI smoke to `output\cinescope-smoke.html`.
- [x] Run browser visual smoke against `http://127.0.0.1:7861`.
