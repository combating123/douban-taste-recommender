# CineScope Real Data and Trusted Media Recovery Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development or superpowers:executing-plans to implement this plan task-by-task. Every behavioral change follows RED -> GREEN -> REFACTOR.

**Goal:** Make CineScope visibly and verifiably use the owner's real Douban watched/wish history, deliver correct local posters and cast/director portraits, and remove the route-level flicker and dead navigation that make the current V3 feel unfinished.

**Architecture:** A new catalog registry is the single write boundary from sync/candidate data into library and identity tables. Media resolution receives embedded source URLs, verifies identity, downloads through source-specific URL failover, and atomically binds the ready asset to its media/person entity. Recommendation sessions derive personalization from the registered library, while Tonight becomes a stable shell whose channel content updates in place.

**Tech Stack:** Python 3.10+, SQLite, urllib, Pillow, vanilla ES modules, CSS, unittest, Node syntax/contract tests, real in-app browser acceptance.

## Global Constraints

- Cookies may only come from the visible sync input/current browser tab and must never be persisted or echoed.
- Do not read browser profiles, disk cookies, clipboard history, hidden storage, or the previously supplied proxy subscription credential.
- Movie, television series, and animated series are separate channels; animation movies must not enter the animated-series channel.
- Television costume drama is down-ranked unless explicitly requested.
- A CSS/data-URI fallback is a graceful missing state, never evidence that a real image loaded.
- Only locally validated `/media/<sha256>.<ext>` assets may be returned as ready media.
- Synced watched/wish states outrank recommendation candidate state and repeated syncs are idempotent.
- Recommendation metadata must state whether it is based on Douban sync and expose watched/wish/rated counts.
- Fake creators, template biographies, fabricated years/countries, and mismatched posters are not permitted as factual metadata.
- Completion requires full tests plus a fresh browser session against the real profile `272042071`.

---

### Task 1: Parse Real Douban Collection Markup

**Files:**
- Create: `tests/fixtures/douban_collection_comment_item.html`
- Modify: `tests/test_crawler.py`
- Modify: `src/douban_recommender/crawler.py`

**Interfaces:**
- Produces: `parse_user_collection_html(html, status) -> list[MediaItem]` with canonical title, aliases, rating, year, countries, genres, cast, directors, duration-informed media type, and source URL.

- [ ] Add a fixture using `<div class="item comment-item">`, a real slash-delimited intro, aliases, and `rating5-t`.
- [ ] Add tests asserting the standard parser—not fallback—returns `仙剑奇侠传三`, rating `5`, year `2009`, China, cast `胡歌`, director `李国立`, genre `古装`, and media type `电视剧`.
- [ ] Add a test proving an animated feature over 60 minutes remains `电影` while a short episodic animation becomes `动漫`.
- [ ] Run `python -m unittest tests.test_crawler -v` and confirm the new tests fail.
- [ ] Generalize item-class matching, canonicalize the first title segment, parse the intro around country/runtime boundaries, retain aliases in `raw`, and make animation-series inference duration/series-aware.
- [ ] Re-run the focused tests and commit.

### Task 2: Register Sync Results as Real Library and Identity Data

**Files:**
- Create: `src/douban_recommender/catalog_registry.py`
- Create: `tests/test_catalog_registry.py`
- Modify: `src/douban_recommender/sync_service.py`
- Modify: `tests/test_sync_service.py`

**Interfaces:**
- Produces: `CatalogRegistry.register_sync_items(connection, user_id, items, now) -> dict[str, int]`.
- Produces stable media/person identities, Douban provider identities, library states, and active profile metadata in one transaction.

- [ ] Add tests for collect -> watched, wish -> wish, watched precedence, deterministic person/media IDs, Douban provider mapping, and idempotent re-sync.
- [ ] Add a sync-service integration test proving a completed job writes both `sync_items` and `library_items` without storing the Cookie.
- [ ] Run the focused tests and confirm failure.
- [ ] Implement the registry and call it inside the existing sync transaction before `_finish`.
- [ ] Re-run focused tests, inspect SQLite counts, and commit.

### Task 3: Make Recommendation Sessions Explicitly Personal

**Files:**
- Modify: `src/douban_recommender/recommendation_api.py`
- Modify: `src/douban_recommender/profiler.py`
- Modify: `src/douban_recommender/curated_catalog.py`
- Modify: `tests/test_recommendation_api_v2.py`
- Modify: `tests/test_profiler.py`
- Modify: `tests/test_curated_catalog.py`

**Interfaces:**
- Produces: session field `personalization = {source, user_id, watched_count, wish_count, rated_count}`.
- Consumes watched and wish library rows when callers do not send explicit ratings.

- [ ] Add tests proving synced watched titles are excluded, wish rows weakly shape taste without being treated as watched, and counts/source appear in the session response.
- [ ] Add tests that production fallback candidates contain no placeholder creators or data-URI assets and that animated movies are excluded from `动漫`.
- [ ] Run focused tests and confirm failure.
- [ ] Load watched and wish rows, derive personalization on every serialized session, and apply a bounded wishlist preference weight.
- [ ] Remove fabricated premium metadata from the default production path; prefer real cached/live candidates and verified curated seeds only.
- [ ] Re-run focused tests and commit.

### Task 4: Download, Validate, Fail Over, and Bind Every Ready Image

**Files:**
- Create: `src/douban_recommender/media/url_candidates.py`
- Create: `src/douban_recommender/media/providers/inline.py`
- Modify: `src/douban_recommender/media/providers/base.py`
- Modify: `src/douban_recommender/media/providers/existing.py`
- Modify: `src/douban_recommender/media/orchestrator.py`
- Modify: `src/douban_recommender/media/store.py`
- Modify: `src/douban_recommender/media_api.py`
- Modify: `tests/test_media_providers.py`
- Modify: `tests/test_media_orchestrator.py`
- Modify: `tests/test_media_store.py`
- Modify: `tests/test_media_api.py`

**Interfaces:**
- Extends: `AssetQuery.source_urls: tuple[str, ...]`.
- Produces: `image_url_candidates(url) -> tuple[str, ...]` including Douban `img1/img2/img3/img9` and Wikimedia thumbnail variants.
- Produces: `MediaStore.bind_asset(entity_kind, entity_id, kind, stored, source, confidence, metadata)`.

- [ ] Add tests for embedded poster/portrait candidates, Douban host failover, exact title+year acceptance, ready-asset binding, and immediate catalog visibility.
- [ ] Run focused tests and confirm failure.
- [ ] Implement URL candidates and browser-like source-specific request headers.
- [ ] Put the inline provider first; give portrait providers a real public resolver instead of `None`.
- [ ] Bind every ready asset to `asset_candidates` and `user_asset_overrides` in the same success path.
- [ ] Re-run focused tests, download representative TMDb/Wikimedia/Douban images, and commit.

### Task 5: Persist Enriched Metadata and Prefetch Visible Media

**Files:**
- Create: `src/douban_recommender/media_prefetch.py`
- Modify: `src/douban_recommender/catalog_registry.py`
- Modify: `src/douban_recommender/exploration_service.py`
- Modify: `src/douban_recommender/recommendation_api.py`
- Modify: `src/douban_recommender/web.py`
- Create: `tests/test_media_prefetch.py`
- Modify: `tests/test_catalog_api_v2.py`

**Interfaces:**
- Produces bounded priority prefetch for hero, visible cards, and visible people.
- Persists subject-detail summaries, genres, credits, and `people_photos` before scheduling local assets.

- [ ] Add tests proving enrichment updates the canonical library payload and identities, then prefetch creates local poster/portrait overrides.
- [ ] Run focused tests and confirm failure.
- [ ] Implement bounded concurrent prefetch with deterministic priority and no unbounded background queue.
- [ ] Make detail APIs return synopsis, genres, rating, credits, and only real local assets as ready.
- [ ] Re-run focused tests and commit.

### Task 6: Stable Tonight Shell and Product Navigation

**Files:**
- Modify: `src/douban_recommender/ui/index.html`
- Modify: `src/douban_recommender/ui/js/app.js`
- Modify: `src/douban_recommender/ui/js/features/tonight.js`
- Modify: `src/douban_recommender/ui/js/features/detail.js`
- Modify: `src/douban_recommender/ui/js/features/people.js`
- Modify: `src/douban_recommender/ui/js/features/health.js`
- Modify: `src/douban_recommender/ui/styles/shell.css`
- Modify: `src/douban_recommender/ui/styles/tonight.css`
- Modify: `src/douban_recommender/ui/styles/detail.css`
- Modify: `src/douban_recommender/ui/styles/responsive.css`
- Modify: `tests/test_ui_v3_contract.py`
- Modify: `tests/test_ui_v3_assets.py`

**Interfaces:**
- Tonight owns channel state and synchronizes the URL with History API without route disposal.
- Top-level navigation is Tonight, Library, Taste; Universe is contextual and Sync/Health live under Settings.

- [ ] Add a DOM contract test proving channel switching does not dispose Tonight or clear the root.
- [ ] Add tests for personalization copy, skeleton-to-image transitions, useful missing-image actions, settings navigation, and no empty top-level spaces.
- [ ] Run focused tests and confirm failure.
- [ ] Keep a full-width cinematic hero and card grid mounted while atomically replacing only channel content.
- [ ] Replace cryptic one-character navigation with icon+label controls, a true collapse state, and a settings sheet.
- [ ] Upgrade detail/person interactions with progressive disclosure, motion-safe transitions, and metadata/credit carousels.
- [ ] Re-run UI tests and commit.

### Task 7: Real Profile Rollout and Acceptance

**Files:**
- Modify: `README.md`
- Add evidence under: `output/real-profile-acceptance/`

- [ ] Run all Python tests: `python -m unittest discover -s tests -v`.
- [ ] Run syntax checks for every UI JavaScript module.
- [ ] Restart port `7861` using the default runtime database.
- [ ] Sync `272042071` anonymously first, adding a visible Cookie only if Douban explicitly requires it.
- [ ] Verify library counts, identity counts, provider attempts, asset files, and personalization metadata in SQLite/API.
- [ ] Generate all three channels and prefetch the first visible batches.
- [ ] In a fresh browser session verify: no route flicker, no blank recovery page, correct titles, synopsis/genres/ratings, working batch changes, and useful navigation.
- [ ] Audit image pixels/HTTP responses rather than DOM placeholders: hero 100%, visible posters >=95%, visible credited people >=80%, wrong-identity count 0.
- [ ] Capture desktop/tablet/mobile screenshots and commit final evidence only after the acceptance thresholds pass.

