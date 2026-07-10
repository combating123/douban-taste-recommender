# CineScope Five-Space Experience UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved five-space, 70%A/30%C interface as maintainable native modules, including Command Lens, cinematic recommendations, detail/person routes, universe exploration, library, taste, health, and sync.

**Architecture:** A new `ui/` package contains static HTML, focused CSS layers, core ES modules, and feature modules. `web_ui_v3.py` loads the shell and `web.py` serves immutable assets. The new UI consumes `/api/v2` services but the legacy UI remains reachable through a feature flag until final browser acceptance.

**Tech Stack:** Semantic HTML, CSS custom properties, native ES Modules, Canvas 2D, Python static asset server, Node `--check`, Python `unittest` contract tests.

## Global Constraints

- Do not add a Node runtime dependency or CDN dependency.
- No visible external image URL; use `/media/*` or a designed DOM fallback.
- Left navigation defaults to 72px and can be completely hidden.
- Movie, series, and animated-series channels keep independent batches.
- Refresh and deep links must restore state instead of returning to sync step one.
- Motion uses transform/opacity and honors `prefers-reduced-motion`.
- Text must not overflow at 1440×900, 1280×800, 1024×768, or 390×844.

---

### Task 1: Static Asset Loader and Feature-Flagged App Shell

**Files:**
- Create: `src/douban_recommender/web_ui_v3.py`
- Create: `src/douban_recommender/ui/index.html`
- Create: `src/douban_recommender/ui/styles/tokens.css`
- Create: `src/douban_recommender/ui/js/app.js`
- Create: `tests/test_ui_v3_assets.py`
- Modify: `src/douban_recommender/web.py`
- Modify: `pyproject.toml`

**Interfaces:**
- Produces: `load_index_html() -> str`
- Produces: `asset_response(relative_path: str) -> tuple[bytes, str]`
- Produces: `CINESCOPE_UI_VERSION=v3|legacy` environment switch
- Produces: `/assets/v3/*`

- [ ] **Step 1: Write failing asset and shell tests**

```python
def test_v3_shell_uses_native_modules_and_five_spaces():
    html = load_index_html()
    self.assertIn('type="module"', html)
    for route in ("/tonight", "/universe", "/library", "/taste", "/health"):
        self.assertIn(route, html)

def test_asset_loader_rejects_parent_traversal():
    with self.assertRaises(FileNotFoundError):
        asset_response("../web.py")
```

- [ ] **Step 2: Run and verify missing module**

Run: `python -m unittest tests.test_ui_v3_assets -v`

Expected: import failure.

- [ ] **Step 3: Implement shell and safe asset loading**

```python
UI_ROOT = Path(__file__).with_name("ui")

def asset_response(relative_path):
    candidate = (UI_ROOT / relative_path).resolve()
    if UI_ROOT.resolve() not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError(relative_path)
    return candidate.read_bytes(), mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
```

`index.html` must contain skip navigation, a 72px rail, top bar, `#command-lens-root`, `#app-view`, `#overlay-root`, and a `<noscript>` explanation.

- [ ] **Step 4: Add package data and feature flag**

```toml
[tool.setuptools.package-data]
douban_recommender = ["ui/**/*.html", "ui/**/*.css", "ui/**/*.js", "ui/**/*.svg"]
```

When `CINESCOPE_UI_VERSION=legacy`, continue returning the current `INDEX_HTML`. Default remains legacy until the rollout plan.

- [ ] **Step 5: Run tests and JavaScript syntax check**

Run: `python -m unittest tests.test_ui_v3_assets tests.test_web_api -v; node --check src/douban_recommender/ui/js/app.js`

Expected: PASS and no Node output.

- [ ] **Step 6: Commit**

```powershell
git add pyproject.toml src/douban_recommender/web.py src/douban_recommender/web_ui_v3.py src/douban_recommender/ui tests/test_ui_v3_assets.py
git commit -m "feat: add modular cinescope v3 shell"
```

### Task 2: Router, Versioned Client Store, and Collapsible Navigation

**Files:**
- Create: `src/douban_recommender/ui/js/core/router.js`
- Create: `src/douban_recommender/ui/js/core/store.js`
- Create: `src/douban_recommender/ui/js/core/api.js`
- Create: `src/douban_recommender/ui/js/core/dom.js`
- Create: `src/douban_recommender/ui/styles/shell.css`
- Create: `tests/test_ui_v3_contract.py`
- Modify: `src/douban_recommender/ui/js/app.js`

**Interfaces:**
- Produces: `createRouter(routes, { onRoute })`
- Produces: `navigate(path, state={})`
- Produces: `createStore(initialState, reducer)`
- Produces: `persistUiState(state)` and `restoreUiState()` with `schemaVersion: 3`

- [ ] **Step 1: Write contract tests for routes and persistence**

```python
UI_ROOT = Path("src/douban_recommender/ui")

def ui_text(relative):
    return (UI_ROOT / relative).read_text(encoding="utf-8")

def test_router_defines_deep_link_routes():
    js = ui_text("js/app.js") + ui_text("js/core/router.js")
    for route in ("/title/:id", "/person/:id", "/tonight/anime-series"):
        self.assertIn(route, js)

def test_store_never_persists_cookie():
    js = ui_text("js/core/store.js")
    self.assertIn("schemaVersion: 3", js)
    self.assertNotIn("doubanCookie", js)
    self.assertNotIn("COOKIE_SESSION_KEY", js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing files.

- [ ] **Step 3: Implement route matching and scroll restoration**

```javascript
export function navigate(path, state = {}) {
  history.pushState(state, "", path);
  window.dispatchEvent(new PopStateEvent("popstate", { state }));
}

export function saveScroll(routeKey, y = window.scrollY) {
  const state = restoreUiState();
  state.scrollByRoute[routeKey] = y;
  persistUiState(state);
}
```

The router must save outgoing scroll, render incoming route, then restore scroll after the next animation frame.

- [ ] **Step 4: Implement rail behavior**

Use classes `rail-collapsed` and `rail-hidden`; expose buttons with `aria-expanded`. On screens below 720px, replace the rail with a five-item bottom navigation.

- [ ] **Step 5: Run syntax and contract tests**

Run: `python -m unittest tests.test_ui_v3_contract -v; Get-ChildItem src/douban_recommender/ui/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/js/core src/douban_recommender/ui/js/app.js src/douban_recommender/ui/styles/shell.css tests/test_ui_v3_contract.py
git commit -m "feat: add restorable cinescope navigation"
```

### Task 3: Design System, Safe Media, Cards, Shelves, and Motion

**Files:**
- Create: `src/douban_recommender/ui/styles/components.css`
- Create: `src/douban_recommender/ui/styles/motion.css`
- Create: `src/douban_recommender/ui/js/core/media.js`
- Create: `src/douban_recommender/ui/js/components/media-frame.js`
- Create: `src/douban_recommender/ui/js/components/title-card.js`
- Create: `src/douban_recommender/ui/js/components/shelf.js`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `renderMediaFrame({localUrl, kind, title, status, source})`
- Produces: `renderTitleCard(item, actions)`
- Produces: `renderShelf({title, items, batchState})`
- Produces: `preloadLocalMedia(url) -> Promise<boolean>`

- [ ] **Step 1: Add failing zero-broken-media and density tests**

```python
def test_media_component_refuses_external_src():
    js = ui_text("js/core/media.js") + ui_text("js/components/media-frame.js")
    self.assertIn("isLocalMediaUrl", js)
    self.assertIn("media-fallback", js)
    self.assertNotIn("onerror=", js)

def test_card_css_enforces_stable_aspect_and_line_clamp():
    css = ui_text("styles/components.css")
    self.assertIn("aspect-ratio: 2 / 3", css)
    self.assertIn("-webkit-line-clamp: 2", css)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing component assets.

- [ ] **Step 3: Implement safe media rendering**

```javascript
export function isLocalMediaUrl(value = "") {
  return value.startsWith("/media/") || value.startsWith("data:image/svg+xml");
}

export function renderMediaFrame(asset) {
  if (!isLocalMediaUrl(asset.localUrl) || asset.status !== "ready") {
    return designedFallback(asset.kind, asset.title, asset.status);
  }
  return `<div class="media-frame ${escapeAttr(asset.kind)}"><img src="${escapeAttr(asset.localUrl)}" alt="" decoding="async"><span class="media-source">${escapeHtml(asset.source)}</span></div>`;
}
```

Insert the `<img>` only after `preloadLocalMedia(url)` resolves with `image.decode()` and a positive natural width.

- [ ] **Step 4: Implement design tokens and motion budget**

Use `--motion-fast: 180ms`, `--motion-standard: 280ms`, and `--motion-immersive: 440ms`. Add a `prefers-reduced-motion` block that sets all durations to `1ms` and disables parallax.

- [ ] **Step 5: Run tests and syntax checks**

Run: `python -m unittest tests.test_ui_v3_contract -v; Get-ChildItem src/douban_recommender/ui/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/styles src/douban_recommender/ui/js/core/media.js src/douban_recommender/ui/js/components tests/test_ui_v3_contract.py
git commit -m "feat: add cinescope visual component system"
```

### Task 4: Tonight Curation and Global Command Lens

**Files:**
- Create: `src/douban_recommender/ui/js/features/tonight.js`
- Create: `src/douban_recommender/ui/js/features/command-lens.js`
- Create: `src/douban_recommender/ui/styles/tonight.css`
- Modify: `src/douban_recommender/ui/js/app.js`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `renderTonight(state)`
- Produces: `openCommandLens(initialText="")`
- Produces: `submitIntent(text)`
- Produces: `requestNextBatch(channel, reason="")`
- Produces: `restorePreviousBatch(channel)`

- [ ] **Step 1: Write channel and count contract tests**

```python
def test_tonight_renders_pool_match_visible_counts_and_batch_controls():
    js = ui_text("js/features/tonight.js")
    for token in ("pool_size", "matched_size", "visible_size", "requestNextBatch", "restorePreviousBatch"):
        self.assertIn(token, js)

def test_command_lens_has_editable_intent_chips_and_ctrl_k():
    js = ui_text("js/features/command-lens.js")
    self.assertIn('event.key.toLowerCase() === "k"', js)
    self.assertIn("intent-chip", js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing feature modules.

- [ ] **Step 3: Implement tonight data flow**

`renderTonight()` must render one horizontal cinematic Hero, then compact shelves for movie, series, and anime. A channel switch preserves every channel's session ID and batch index. The batch toolbar displays all three counts and offers undo plus reasoned shuffle.

```javascript
export const MAX_INITIAL_CARDS = 9;

export async function requestNextBatch(channel, reason = "") {
  const sessionId = store.getState().recommendation.sessionId;
  const batch = await api.post(`/api/v2/recommend/sessions/${sessionId}/batch`, { channel, reason });
  store.dispatch({ type: "recommendation/batchReceived", channel, batch });
}
```

- [ ] **Step 4: Implement Command Lens grounding**

Submit text to session creation or intent update, render only server-returned chips, and show a local fallback message if the optional language adapter is unavailable. Do not place model output directly into `innerHTML`.

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_ui_v3_contract tests.test_recommendation_api_v2 -v; node --check src/douban_recommender/ui/js/features/tonight.js; node --check src/douban_recommender/ui/js/features/command-lens.js`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/js/features/tonight.js src/douban_recommender/ui/js/features/command-lens.js src/douban_recommender/ui/styles/tonight.css src/douban_recommender/ui/js/app.js tests/test_ui_v3_contract.py
git commit -m "feat: build ai tonight curation experience"
```

### Task 5: Cinematic Title Detail and Person Spotlight

**Files:**
- Create: `src/douban_recommender/ui/js/features/detail.js`
- Create: `src/douban_recommender/ui/js/features/people.js`
- Create: `src/douban_recommender/ui/styles/detail.css`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `renderTitleDetail(titleId)`
- Produces: `openPersonSheet(personId, originRect)`
- Produces: `renderPersonPage(personId)`
- Produces: `prefetchVisiblePeople(title)`

- [ ] **Step 1: Write detail and portrait contract tests**

```python
def test_detail_uses_separate_backdrop_and_contained_poster():
    css = ui_text("styles/detail.css")
    self.assertIn(".detail-backdrop", css)
    self.assertIn("object-fit: contain", css)

def test_people_prefetch_prioritizes_directors_and_first_eight_cast():
    js = ui_text("js/features/detail.js")
    self.assertIn("directors", js)
    self.assertIn("casts.slice(0, 8)", js)
    self.assertIn("/api/v2/media/jobs", js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing modules.

- [ ] **Step 3: Implement routed detail sections**

Render a full-page hero, sticky tabs, explainable score grid, verified facts, horizontal people rail, relation preview, and similar works. Use `document.startViewTransition` when available; otherwise apply a CSS fade/translate transition.

- [ ] **Step 4: Implement person sheet and full page**

The sheet must retain title context and expose “查看 TA 参与的全部候选”. Unverified portraits render a named identity card with a status label, never a remote URL.

- [ ] **Step 5: Run tests and syntax checks**

Run: `python -m unittest tests.test_ui_v3_contract -v; node --check src/douban_recommender/ui/js/features/detail.js; node --check src/douban_recommender/ui/js/features/people.js`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/js/features/detail.js src/douban_recommender/ui/js/features/people.js src/douban_recommender/ui/styles/detail.css tests/test_ui_v3_contract.py
git commit -m "feat: add cinematic title and people spaces"
```

### Task 6: Universe Canvas with On-Demand Spatial Exploration

**Files:**
- Create: `src/douban_recommender/ui/js/features/universe.js`
- Create: `src/douban_recommender/ui/styles/universe.css`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `renderUniverse(container, graph)`
- Produces: `focusNode(nodeId)`
- Produces: `expandNode(nodeId)`
- Produces: `destroyUniverse()`

- [ ] **Step 1: Write lifecycle and accessibility contract tests**

```python
def test_universe_is_lazy_and_has_textual_relationship_list():
    js = ui_text("js/features/universe.js")
    self.assertIn("IntersectionObserver", js)
    self.assertIn("relationship-list", js)
    self.assertIn("destroyUniverse", js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing module.

- [ ] **Step 3: Implement bounded Canvas renderer**

Start with at most nine nodes, use requestAnimationFrame only while interaction or animation is active, and expose every rendered relationship in a semantic list beside the canvas. Wheel zoom must require the canvas to be focused.

- [ ] **Step 4: Run tests**

Run: `python -m unittest tests.test_ui_v3_contract -v; node --check src/douban_recommender/ui/js/features/universe.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/ui/js/features/universe.js src/douban_recommender/ui/styles/universe.css tests/test_ui_v3_contract.py
git commit -m "feat: add on-demand taste universe"
```

### Task 7: Library, Taste DNA, Health, and Sync Spaces

**Files:**
- Create: `src/douban_recommender/ui/js/features/library.js`
- Create: `src/douban_recommender/ui/js/features/taste.js`
- Create: `src/douban_recommender/ui/js/features/health.js`
- Create: `src/douban_recommender/ui/js/features/sync.js`
- Create: `src/douban_recommender/ui/styles/spaces.css`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `renderLibrary()`
- Produces: `renderTasteDna()`
- Produces: `renderHealth()`
- Produces: `startDoubanSync(payload)`
- Produces: `resumeDoubanSync(jobId)`

- [ ] **Step 1: Write privacy, auto-pagination, and health tests**

```python
def test_sync_uses_session_cookie_and_auto_pagination_copy():
    js = ui_text("js/features/sync.js")
    self.assertIn("sessionStorage", js)
    self.assertIn("自动抓取到末页", js)
    self.assertNotIn("localStorage.setItem(COOKIE", js)

def test_health_renders_live_media_sources_and_job_progress():
    js = ui_text("js/features/health.js")
    self.assertIn("/api/v2/media/health", js)
    self.assertIn("resolution", js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing modules.

- [ ] **Step 3: Implement the four spaces**

Library uses segmented filters and a virtualized grid. Taste DNA renders stable, conflicting, recent, and unexplored signals with evidence links. Health shows sync jobs, media jobs, provider latency/backoff, cache size, and privacy state. Sync accepts profile URL or ID, defaults to automatic pagination, and keeps Cookie only in session storage.

- [ ] **Step 4: Run tests and syntax checks**

Run: `python -m unittest tests.test_ui_v3_contract tests.test_web_api -v; Get-ChildItem src/douban_recommender/ui/js/features -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/ui/js/features src/douban_recommender/ui/styles/spaces.css tests/test_ui_v3_contract.py
git commit -m "feat: add library taste health and sync spaces"
```

### Task 8: Responsive, Motion, and Accessibility Gate

**Files:**
- Create: `src/douban_recommender/ui/styles/responsive.css`
- Create: `src/douban_recommender/ui/js/core/focus.js`
- Modify: `src/douban_recommender/ui/index.html`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `trapFocus(element) -> release`
- Produces: `announce(message)`
- Produces responsive layouts at the four required viewports.

- [ ] **Step 1: Add failing a11y and overflow contract tests**

```python
def test_shell_has_skip_link_live_region_and_reduced_motion():
    html = ui_text("index.html")
    css = ui_text("styles/motion.css") + ui_text("styles/responsive.css")
    self.assertIn("skip-link", html)
    self.assertIn('aria-live="polite"', html)
    self.assertIn("prefers-reduced-motion", css)
    self.assertIn("overflow-wrap: anywhere", css)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_contract -v`

Expected: missing responsive/focus assets.

- [ ] **Step 3: Implement focus management and breakpoints**

Use breakpoints at 1200px, 960px, and 720px. At 720px hide the desktop rail and enable the bottom nav. Every overlay must trap focus, close on Escape, and restore focus to its trigger.

- [ ] **Step 4: Run UI contract and syntax checks**

Run: `python -m unittest tests.test_ui_v3_assets tests.test_ui_v3_contract -v; Get-ChildItem src/douban_recommender/ui/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: PASS.

- [ ] **Step 5: Run complete suite with V3 still feature-flagged**

Run: `$env:CINESCOPE_UI_VERSION='v3'; python -m unittest discover -s tests -v`

Expected: all tests PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/styles/responsive.css src/douban_recommender/ui/js/core/focus.js src/douban_recommender/ui/index.html tests/test_ui_v3_contract.py
git commit -m "feat: complete responsive accessible cinescope ui"
```
