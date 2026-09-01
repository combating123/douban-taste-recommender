# CineScope Premium Media UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade the recommendation screen into a resilient, poster-safe, category-rich, world-class media browsing UI.

**Architecture:** Keep the current dependency-free Python HTTP server and one-file vanilla frontend. Implement the premium experience in `web_ui.py` using pure CSS/JS helpers, while preserving API shape and privacy constraints.

**Tech Stack:** Python standard library, `unittest`, vanilla HTML/CSS/JS, SVG data URLs for local poster fallback.

## Global Constraints

- UI copy is Simplified Chinese.
- Cookie is never saved or echoed.
- No paid/commercial API keys.
- Movie, series, and anime must all remain first-class sections.
- Poster failures must degrade to local generated title art.
- TDD: every behavior change gets a failing test first.

---

### Task 1: Premium UI Contract Tests

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\tests\test_ui_html.py`

**Interfaces:**
- Consumes: `INDEX_HTML`
- Produces: tests for premium media UI markers.

- [ ] Add tests requiring `heroShowcase`, `railWall`, `media-rail`, `posterFallback`, `safePosterImg`, `person-chip`, `鐢靛奖`, `鐢佃鍓, `鍔ㄦ极`.
- [ ] Run the tests and confirm they fail before implementation.
- [ ] Commit only after implementation passes.

### Task 2: Poster-Safe Cards and Hero Showcase

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`

**Interfaces:**
- Produces JS helpers: `posterFallback(title, mediaType)`, `posterUrl(rec)`, `safePosterImg(rec)`, `renderHeroShowcase()`.

- [ ] Implement SVG title poster fallback.
- [ ] Add image `onerror` fallback to every real poster.
- [ ] Add `heroShowcase` above recommendation rails.
- [ ] Re-run target UI tests.

### Task 3: Media Rails and Category Browsing

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`

**Interfaces:**
- Produces JS helpers: `buildMediaRails()`, `renderMediaRail(name, items)`, `sectionItems(name)`.

- [ ] Replace single poster grid with premium rail wall.
- [ ] Always expose `绮鹃€塦銆乣鐢靛奖`銆乣鐢佃鍓銆乣鍔ㄦ极` category buttons/rails when data exists.
- [ ] Keep legacy tabs working as quick filters.
- [ ] Re-run UI tests.

### Task 4: Detail Drawer Metadata and People Chips

**Files:**
- Modify: `C:\path\to\douban-taste-recommender\src\douban_recommender\web_ui.py`

**Interfaces:**
- Produces JS helpers: `metadataLine(rec)`, `peopleChips(names, role)`, richer `openDetail(index)`.

- [ ] Detail drawer shows poster, summary, genre, year, country, directors, casts.
- [ ] People chips use initials avatar when no real photo exists.
- [ ] Reasons and warnings remain visible.
- [ ] Re-run UI tests.

### Task 5: Verification

**Files:**
- Modify only concrete failures.

- [ ] Run `python -m unittest discover -s tests -v`.
- [ ] Run CLI smoke generating `output\cinescope-smoke.html`.
- [ ] Run web smoke against `http://127.0.0.1:7861`.
- [ ] Commit implementation.
