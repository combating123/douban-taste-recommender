# CineScope Five-Space Experience UI Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build the approved five-space, 70%A/30%C interface as maintainable native modules, including Command Lens, cinematic recommendations, detail/person routes, universe exploration, library, taste, health, and sync.

**Architecture:** A new `ui/` package contains static HTML, focused CSS layers, core ES modules, and feature modules. `web_ui_v3.py` loads the shell and `web.py` serves immutable assets. The new UI consumes `/api/v2` services but the legacy UI remains reachable through a feature flag until final browser acceptance.

**Tech Stack:** Semantic HTML, CSS custom properties, native ES Modules, Canvas 2D, Python static asset server, Node `--check`, Python `unittest` contract tests.

**Execution Convention:** In PowerShell, run `$env:PYTHONPATH = "$PWD\src"` once before every Python test or server command in this plan. Node is used only for development-time syntax checks and is not a product runtime dependency.

## Global Constraints

- Do not add a Node runtime dependency or CDN dependency.
- No visible external image URL; use `/media/*` or a designed DOM fallback.
- Every visible `<img>` must use a same-origin `/media/*` URL and may enter the DOM only after successful decode; designed fallbacks use HTML/CSS, never `data:` or remote `<img>` sources.
- Left navigation defaults to 72px and can be completely hidden.
- Movie, series, and animated-series channels keep independent batches.
- Every `/api/v2` JSON POST must use `schema_version: 2`; route slugs map explicitly as `movie -> 鐢靛奖`, `series -> 鐢佃鍓, and `anime-series -> 鍔ㄦ极`.
- Refresh and deep links must restore state instead of returning to sync step one.
- Motion uses transform/opacity and honors `prefers-reduced-motion`.
- Text must not overflow at 1440脳900, 1280脳800, 1024脳768, or 390脳844.

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
- Produces: `selected_ui_version(env: Mapping[str, str] | None = None) -> str`
- Produces: `is_v3_frontend_route(path: str) -> bool`
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

def test_v3_route_classifier_supports_deep_links_without_shadowing_services():
    for path in ("/tonight", "/tonight/anime-series", "/title/douban:1295644", "/person/person-1"):
        self.assertTrue(is_v3_frontend_route(path))
    for path in ("/api/v2/taste", "/media/hash.png", "/assets/v3/js/app.js"):
        self.assertFalse(is_v3_frontend_route(path))
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

When V3 is selected, `web.py` must return the V3 shell for the five spaces and valid `/title/<id>` or `/person/<id>` deep links before its final 404 branch. `/api/*`, `/media/*`, and `/assets/v3/*` keep their dedicated handlers and must never be swallowed by the frontend fallback. Add an HTTP-level regression in `tests/test_ui_v3_assets.py` that refreshes one deep link and receives status 200 plus `#app-view`.

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
- Modify: `src/douban_recommender/ui/index.html`
- Modify: `src/douban_recommender/ui/js/app.js`

**Interfaces:**
- Produces: `createRouter(routes, { onRoute })`
- Produces: `navigate(path, state={})`
- Produces: `createStore(initialState, reducer)`
- Produces: `persistUiState(state)` and `restoreUiState()` with `schemaVersion: 3`
- Produces: `postV2(path, payload) -> Promise<object>` with forced `schema_version: 2`
- Produces: `backendChannel(routeSlug) -> "鐢靛奖" | "鐢佃鍓? | "鍔ㄦ极"`

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

def test_v2_client_forces_schema_and_maps_route_channels():
    js = ui_text("js/core/api.js")
    self.assertIn("schema_version", js)
    self.assertIn('"anime-series": "鍔ㄦ极"', js)
    self.assertIn('"series": "鐢佃鍓?', js)
    self.assertIn('"movie": "鐢靛奖"', js)
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

`store.js` persists only non-sensitive state: active path and params, recommendation session ID, active channel slug, per-channel batch indexes/IDs, `scrollByRoute`, candidate tray context, Command Lens draft/chips, and rail state. It must not persist Cookie, API keys, request headers, or raw external image URLs.

`core/api.js` is the only JSON POST boundary for V2 routes. Implement it so caller payload cannot override the protocol version:

```javascript
export const V2_SCHEMA_VERSION = 2;
export const CHANNEL_KEYS = Object.freeze({ movie: "鐢靛奖", series: "鐢佃鍓?, "anime-series": "鍔ㄦ极" });

export function postV2(path, payload = {}) {
  return request(path, { method: "POST", body: { ...payload, schema_version: V2_SCHEMA_VERSION } });
}

export function backendChannel(routeSlug) {
  const channel = CHANNEL_KEYS[routeSlug];
  if (!channel) throw new TypeError(`Unsupported channel: ${routeSlug}`);
  return channel;
}
```

- [ ] **Step 4: Implement rail behavior**

Use classes `rail-collapsed` and `rail-hidden`; expose buttons with `aria-expanded`. On screens below 720px, replace the rail with a five-item bottom navigation.

Load `styles/shell.css` from `index.html` after `styles/tokens.css` so shell overrides are deterministic without runtime stylesheet injection.

- [ ] **Step 5: Run syntax and contract tests**

Run: `python -m unittest tests.test_ui_v3_contract -v; Get-ChildItem src/douban_recommender/ui/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/js/core src/douban_recommender/ui/index.html src/douban_recommender/ui/js/app.js src/douban_recommender/ui/styles/shell.css tests/test_ui_v3_contract.py
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
- Modify: `src/douban_recommender/ui/index.html`
- Modify: `tests/test_ui_v3_contract.py`

**Interfaces:**
- Produces: `renderMediaFrame({localUrl, kind, title, status, source}) -> HTMLElement`
- Produces: `renderTitleCard(item, actions)`
- Produces: `renderShelf({title, items, batchState})`
- Produces: `preloadLocalMedia(url) -> Promise<HTMLImageElement | null>`

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
  try {
    const url = new URL(value, location.origin);
    return url.origin === location.origin && url.pathname.startsWith("/media/");
  } catch {
    return false;
  }
}

export function renderMediaFrame(asset) {
  const frame = designedFallback(asset.kind, asset.title, asset.status);
  if (isLocalMediaUrl(asset.localUrl) && asset.status === "ready") {
    preloadLocalMedia(asset.localUrl).then((image) => {
      if (image) {
        image.alt = asset.title ? `${asset.title} 娴锋姤` : "";
        frame.replaceChildren(image);
      }
    });
  }
  return frame;
}
```

`preloadLocalMedia(url)` must reject every non-`/media/*` URL, call `image.decode()`, and return that same decoded `HTMLImageElement` only when `naturalWidth > 0`; otherwise it returns `null`. `designedFallback()` is a named HTML/CSS identity surface with a status label; it is never an `<img>`. Insert the returned real `<img>` only after the preload promise resolves with the decoded element.

- [ ] **Step 4: Implement design tokens and motion budget**

Use `--motion-fast: 180ms`, `--motion-standard: 280ms`, and `--motion-immersive: 440ms`. Add a `prefers-reduced-motion` block that sets all durations to `1ms` and disables parallax.

Load `styles/components.css` and then `styles/motion.css` from `index.html` after `styles/shell.css`; do not inject stylesheets at runtime.

- [ ] **Step 5: Run tests and syntax checks**

Run: `python -m unittest tests.test_ui_v3_contract -v; Get-ChildItem src/douban_recommender/ui/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/index.html src/douban_recommender/ui/styles src/douban_recommender/ui/js/core/media.js src/douban_recommender/ui/js/components tests/test_ui_v3_contract.py
git commit -m "feat: add cinescope visual component system"
```

### Task 4: Tonight Curation and Global Command Lens

**Files:**
- Create: `src/douban_recommender/ui/js/features/tonight.js`
- Create: `src/douban_recommender/ui/js/features/command-lens.js`
- Create: `src/douban_recommender/ui/styles/tonight.css`
- Modify: `src/douban_recommender/ui/js/app.js`
- Modify: `src/douban_recommender/recommendation_api.py`
- Modify: `tests/test_ui_v3_contract.py`
- Modify: `tests/test_recommendation_api_v2.py`

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

def test_session_response_returns_grounded_intent_chips():
    response = self.create_session(intent_text="90鍒嗛挓鍐呯殑鎮枒鐢靛奖")
    self.assertTrue(response["chips"])
    self.assertEqual({"key", "label", "value", "removable"}, set(response["chips"][0]))
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
  const batch = await api.postV2(`/api/v2/recommend/sessions/${sessionId}/batch`, {
    channel: backendChannel(channel),
    reason,
  });
  store.dispatch({ type: "recommendation/batchReceived", channel, batch });
}
```

- [ ] **Step 4: Implement Command Lens grounding**

Submit text by creating a grounded recommendation session with `postV2()`. Add `chips` to the serialized session response by converting `intent_to_chips(restored.intent)` to plain dictionaries. Editing/removing a chip creates a replacement session from the server-returned structured intent; the UI must never derive chips from free-form model prose. Show a local fallback message if the optional language adapter is unavailable. Do not place model output directly into `innerHTML`.

- [ ] **Step 5: Run tests**

Run: `python -m unittest tests.test_ui_v3_contract tests.test_recommendation_api_v2 -v; node --check src/douban_recommender/ui/js/features/tonight.js; node --check src/douban_recommender/ui/js/features/command-lens.js`

Expected: PASS.

- [ ] **Step 6: Commit**

```powershell
git add src/douban_recommender/ui/js/features/tonight.js src/douban_recommender/ui/js/features/command-lens.js src/douban_recommender/ui/styles/tonight.css src/douban_recommender/ui/js/app.js src/douban_recommender/recommendation_api.py tests/test_ui_v3_contract.py tests/test_recommendation_api_v2.py
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

The sheet must retain title context and expose 鈥滄煡鐪?TA 鍙備笌鐨勫叏閮ㄥ€欓€夆€? Unverified portraits render a named identity card with a status label, never a remote URL.

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
    self.assertIn("鑷姩鎶撳彇鍒版湯椤?, js)
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

Library uses segmented filters and a virtualized grid. Taste DNA renders stable, conflicting, recent, and unexplored signals with evidence links. Health is the fifth top-level space and owns the Sync panel; do not add a sixth top-level `/sync` route. It initially consumes `/api/v2/media/health` and sync job APIs, then merges `/api/v2/diagnostics` when rollout Task 2 adds it. Health shows sync jobs, media jobs, provider latency/backoff, cache size, and privacy state. Sync accepts profile URL or ID, defaults to automatic pagination, and keeps Cookie only in session storage.

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
