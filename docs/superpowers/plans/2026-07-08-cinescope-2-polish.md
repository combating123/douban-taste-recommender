# CineScope 2.0 Polish Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Upgrade CineScope Studio with resilient director/cast portraits, a cinematic full-width carousel, global anime diversity, and quality-preserving recommendation reranking.

**Architecture:** Keep the current Python standard-library backend and vanilla HTML/CSS/JS frontend. Extend existing focused modules instead of introducing a framework: `curated_catalog.py` owns curated data, `recommender.py` owns scoring/reranking, `web.py` exposes sections, and `web_ui.py` renders the cinematic experience.

**Tech Stack:** Python standard library, `unittest`, vanilla JS/CSS, local HTTP server, existing `/api/image-proxy`.

## Global Constraints

- UI copy remains Simplified Chinese.
- Cookie is never written to disk, logs, cache, README examples, or API responses.
- Proxy subscription URLs are never saved or documented; only local proxy ports such as `http://127.0.0.1:7890` are allowed.
- Anime means animated series / serialized animation, not animated movies.
- External images must fail gracefully through local fallback; no browser broken image icons.
- TDD is mandatory: write failing tests, verify red, implement, verify green.

---

## File Structure

- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\curated_catalog.py` — expand people photos and global anime seed candidates.
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\recommender.py` — add diversity reranking and richer badges/reasons.
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web.py` — expose richer anime sections if needed through existing `build_recommendation_sections`.
- Modify: `C:\Users\11616\douban-taste-recommender\src\douban_recommender\web_ui.py` — rebuild carousel and person UI.
- Modify tests: `tests/test_curated_catalog.py`, `tests/test_recommender.py`, `tests/test_ui_html.py`, `tests/test_web_api.py`.

---

### Task 1: Resilient People Portrait UI

**Files:**
- Modify: `src/douban_recommender/web_ui.py`
- Modify: `tests/test_ui_html.py`

**Interfaces:**
- Produces JS helpers: `personPortraitStatus(person)`, enhanced `personPortrait(person)`, enhanced `peopleCarousel(r)`.

- [ ] **Step 1: Write failing UI test**

Add to `tests/test_ui_html.py`:

```python
def test_people_portraits_have_status_badges_and_no_broken_image_experience(self):
    for token in [
        "personPortraitStatus",
        "人物图源",
        "真实资料图",
        "设计肖像",
        "portrait-fallback",
        "onerror=\"this.onerror=null;this.src=",
        "people-spotlight-rail",
    ]:
        self.assertIn(token, INDEX_HTML)
```

- [ ] **Step 2: Verify red**

Run:

```powershell
$env:PYTHONPATH="$PWD\src"
python -m unittest tests.test_ui_html.UiHtmlTests.test_people_portraits_have_status_badges_and_no_broken_image_experience -v
```

Expected: FAIL because `personPortraitStatus` and `people-spotlight-rail` are missing.

- [ ] **Step 3: Implement minimal UI**

Update `web_ui.py`:

```javascript
function personPortraitStatus(person) {
  return person.photo ? '真实资料图' : '设计肖像';
}
function personPortrait(person) {
  const fallback = personPhotoSvg(person.name, person.role);
  const src = personPhotoUrl(person) || fallback;
  const safeFallback = fallback.replace(/'/g, '%27');
  const cls = person.photo ? 'person-photo' : 'person-photo portrait-fallback';
  return `<span class="${cls}" title="${esc(person.role)}人物肖像"><img src="${esc(src)}" alt="${esc(person.name)} 人物肖像" referrerpolicy="no-referrer" onerror="this.onerror=null;this.src='${safeFallback}'"><small class="portrait-source">人物图源 · ${personPortraitStatus(person)}</small></span>`;
}
function peopleCarousel(r) {
  const people = peopleForItem(r);
  if (!people.length) return `<p class="hint">人物资料待补全。</p>`;
  return `<div class="people-carousel people-spotlight-rail">${people.map(person => {
    const encoded = encodeURIComponent(person.name || '');
    const encodedRole = encodeURIComponent(person.role || '');
    return `<button class="person-card magnetic-person" onclick="openPersonSpotlight('${encoded}','${encodedRole}')">${personPortrait(person)}<b>${esc(person.name)}</b><small>${esc(person.role)} · 点击查看 TA 参与的相关推荐</small></button>`;
  }).join('')}</div>`;
}
```

- [ ] **Step 4: Verify green**

Run the same test. Expected: PASS.

---

### Task 2: Full-Width Cinematic Carousel

**Files:**
- Modify: `src/douban_recommender/web_ui.py`
- Modify: `tests/test_ui_html.py`

**Interfaces:**
- Produces CSS classes `.cinematic-banner`, `.banner-backdrop`, `.banner-poster-float`, `.banner-filmstrip`, `.banner-controls`.

- [ ] **Step 1: Write failing UI test**

```python
def test_hero_carousel_is_full_width_cinematic_banner_not_left_strip(self):
    for token in [
        "cinematic-banner",
        "banner-backdrop",
        "banner-poster-float",
        "banner-filmstrip",
        "banner-controls",
        "上一部",
        "下一部",
    ]:
        self.assertIn(token, INDEX_HTML)
    self.assertNotIn("grid-template-columns:minmax(180px,280px) 1fr", INDEX_HTML)
```

- [ ] **Step 2: Verify red**

Run:

```powershell
python -m unittest tests.test_ui_html.UiHtmlTests.test_hero_carousel_is_full_width_cinematic_banner_not_left_strip -v
```

Expected: FAIL because current carousel uses `.hero-showcase` two-column layout.

- [ ] **Step 3: Implement CSS and markup**

Replace the old `.hero-showcase` two-column CSS with full-width banner CSS and update `renderHeroCarousel()` to return:

```javascript
return `<section class="hero-showcase cinematic-banner category-spotlight" id="heroShowcase">
  <div class="banner-backdrop">${safePosterImg(r)}</div>
  <div class="banner-content">
    <div class="banner-copy">...</div>
    <div class="banner-poster-float">${safePosterImg(r)}</div>
  </div>
  <div class="banner-filmstrip">${dots}</div>
  <div class="banner-controls"><button class="ghost" onclick="nextHeroForSection('${esc(name)}',-1)">上一部</button><button onclick="openDetailByKey('${key}')">打开详情</button><button class="ghost" onclick="nextHeroForSection('${esc(name)}',1)">下一部</button></div>
</section>`;
```

- [ ] **Step 4: Verify green**

Run the same test. Expected: PASS.

---

### Task 3: Global Anime Seed Diversity

**Files:**
- Modify: `src/douban_recommender/curated_catalog.py`
- Modify: `tests/test_curated_catalog.py`

**Interfaces:**
- Produces curated anime items whose `countries` include at least Japan, China, and United States.

- [ ] **Step 1: Write failing catalog test**

```python
def test_curated_anime_pool_includes_global_animation_series(self):
    anime = [item for item in curated_seed_candidates() if item.media_type == "动漫"]
    countries = {country for item in anime for country in item.countries}
    titles = {item.title for item in anime}
    self.assertIn("日本", countries)
    self.assertIn("中国大陆", countries)
    self.assertIn("美国", countries)
    self.assertIn("中国奇谭", titles)
    self.assertIn("Arcane", titles)
    self.assertIn("Invincible", titles)
```

- [ ] **Step 2: Verify red**

Run:

```powershell
python -m unittest tests.test_curated_catalog.CuratedCatalogTests.test_curated_anime_pool_includes_global_animation_series -v
```

Expected: FAIL because non-Japanese anime titles are not in seed candidates.

- [ ] **Step 3: Add seed candidates**

Add curated `_item(...)` entries for `中国奇谭`, `伍六七`, `雾山五行`, `灵笼`, `时光代理人`, `Arcane`, `Blue Eye Samurai`, `Invincible`, `Primal`, `Scavengers Reign`, `Love, Death & Robots`, `Avatar: The Last Airbender`.

- [ ] **Step 4: Verify green**

Run the same test. Expected: PASS.

---

### Task 4: Diversity Reranking

**Files:**
- Modify: `src/douban_recommender/recommender.py`
- Modify: `tests/test_recommender.py`

**Interfaces:**
- Produces: `diversify_recommendations(recs: list[Recommendation], limit: int) -> list[Recommendation]`.

- [ ] **Step 1: Write failing rerank test**

```python
def test_recommendation_rerank_reduces_country_and_media_type_monotony(self):
    candidates = [
        MediaItem(title=f"日本动画{i}", douban_id=f"jp{i}", media_type="动漫", douban_rating=9.2, countries=["日本"], genres=["动画", "剧情"])
        for i in range(8)
    ] + [
        MediaItem(title="中国奇谭", douban_id="cn1", media_type="动漫", douban_rating=8.9, countries=["中国大陆"], genres=["动画", "剧情"]),
        MediaItem(title="Arcane", douban_id="us1", media_type="动漫", douban_rating=9.0, countries=["美国"], genres=["动画", "剧情"]),
    ]
    profile = build_taste_profile([], like_terms="评分高，剧情好", dislike_terms="")
    recs = recommend([], candidates, profile, limit=6, include_anime=True)
    countries = [rec.item.countries[0] for rec in recs if rec.item.countries]
    self.assertIn("中国大陆", countries)
    self.assertIn("美国", countries)
```

- [ ] **Step 2: Verify red**

Run:

```powershell
python -m unittest tests.test_recommender.CineScopeRecommendationTests.test_recommendation_rerank_reduces_country_and_media_type_monotony -v
```

Expected: FAIL because pure score sorting may keep mostly Japanese entries.

- [ ] **Step 3: Implement reranker**

Add `diversify_recommendations()` and call it before slicing in `recommend()`.

- [ ] **Step 4: Verify green**

Run the same test. Expected: PASS.

---

### Task 5: Anime Subsections and UI Copy

**Files:**
- Modify: `src/douban_recommender/web.py`
- Modify: `src/douban_recommender/web_ui.py`
- Modify: `tests/test_web_api.py`
- Modify: `tests/test_ui_html.py`

**Interfaces:**
- Produces section names: `动漫 · 国创动画`, `动漫 · 欧美动画`, `动漫 · 日漫精品`.

- [ ] **Step 1: Write failing tests**

```python
def test_sections_include_global_anime_subchannels(self):
    recs = [
        Recommendation(item=MediaItem(title="中国奇谭", media_type="动漫", countries=["中国大陆"]), score=90, section="动漫"),
        Recommendation(item=MediaItem(title="Arcane", media_type="动漫", countries=["美国"]), score=89, section="动漫"),
        Recommendation(item=MediaItem(title="虫师", media_type="动漫", countries=["日本"]), score=88, section="动漫"),
    ]
    names = [section["name"] for section in build_recommendation_sections(recs)]
    self.assertIn("动漫 · 国创动画", names)
    self.assertIn("动漫 · 欧美动画", names)
    self.assertIn("动漫 · 日漫精品", names)
```

UI token test:

```python
def test_ui_exposes_global_anime_channels(self):
    for token in ["动漫 · 国创动画", "动漫 · 欧美动画", "动漫 · 日漫精品", "全球动画剧集"]:
        self.assertIn(token, INDEX_HTML)
```

- [ ] **Step 2: Verify red**

Run both tests. Expected: FAIL.

- [ ] **Step 3: Implement sections and UI copy**

Update `build_recommendation_sections()` to add derived anime subsections based on `countries`. Add UI copy “全球动画剧集”。

- [ ] **Step 4: Verify green**

Run both tests. Expected: PASS.

---

### Task 6: Full Verification and Browser Audit

**Files:**
- Modify only files tied to concrete failures.

- [ ] **Step 1: Run full suite**

```powershell
$env:PYTHONPATH="$PWD\src"
$env:PYTHONDONTWRITEBYTECODE="1"
python -m unittest discover -s tests -v
```

Expected: all tests pass.

- [ ] **Step 2: Restart local servers**

```powershell
Get-NetTCPConnection -LocalPort 7860,7861 -State Listen -ErrorAction SilentlyContinue | ForEach-Object { Stop-Process -Id $_.OwningProcess -Force -ErrorAction SilentlyContinue }
$env:PYTHONPATH="$PWD\src"
Start-Process -FilePath python -ArgumentList @('-m','douban_recommender.web','--host','127.0.0.1','--port','7860','--no-browser') -WorkingDirectory "C:\Users\11616\douban-taste-recommender" -WindowStyle Hidden
Start-Process -FilePath python -ArgumentList @('-m','douban_recommender.web','--host','127.0.0.1','--port','7861','--no-browser') -WorkingDirectory "C:\Users\11616\douban-taste-recommender" -WindowStyle Hidden
```

- [ ] **Step 3: Browser audit**

Open `http://127.0.0.1:7860/` and verify:

- `.cinematic-banner` exists.
- Total image broken count is 0.
- Recommendation page restores after reload.
- Anime channels include global animation copy.

---

## Self-Review Notes

- Spec coverage: people portraits, carousel, anime diversity, reranking, sections, verification are mapped to tasks.
- Placeholder scan: no TBD/TODO placeholders; each task has concrete tests and expected outcomes.
- Type consistency: functions and section names match task interfaces.
