# CineScope Verification and Default Rollout Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Migrate existing local state, prove the new experience in real browsers and live local data, fix every discovered defect, then make CineScope V3 the default without removing the rollback path.

**Architecture:** Add explicit migration and diagnostic endpoints, deterministic browser audit helpers, and screenshot/performance evidence. Keep `CINESCOPE_UI_VERSION=legacy` as an emergency rollback while the default changes to V3 only after all acceptance gates pass.

**Tech Stack:** Python `unittest`, native browser APIs, Codex computer-use/browser inspection, PowerShell, existing local HTTP service.

## Global Constraints

- Evidence before completion claims.
- Test at 1440×900, 1280×800, 1024×768, and 390×844.
- Visible image failures must be exactly zero.
- Canary identity mismatches must be exactly zero.
- Refresh must restore channel, batch, route, and scroll.
- Do not retrieve Cookie from browser profiles or disk.
- Preserve a documented legacy rollback environment switch.

---

### Task 1: V3 Client-State Migration and Recovery Boundary

**Files:**
- Create: `src/douban_recommender/ui/js/core/migrate.js`
- Create: `src/douban_recommender/ui/js/core/recovery.js`
- Create: `tests/test_ui_v3_migration.py`
- Modify: `src/douban_recommender/ui/js/app.js`

**Interfaces:**
- Produces: `migrateLegacyClientState(storage) -> MigrationResult`
- Produces: `renderRecoveryBoundary(error, stableState)`
- Produces: `restoreLastStableState()`

- [ ] **Step 1: Write migration contract tests**

```python
def test_migration_names_known_legacy_keys_and_excludes_cookie():
    js = ui_text("js/core/migrate.js")
    self.assertIn("recommendationSnapshot", js)
    self.assertIn("schemaVersion", js)
    self.assertNotIn("doubanCookie", js)

def test_recovery_boundary_never_renders_blank_root():
    js = ui_text("js/core/recovery.js")
    self.assertIn("恢复上次稳定状态", js)
    self.assertIn("app-view", js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_migration -v`

Expected: missing modules.

- [ ] **Step 3: Implement idempotent schema migration**

Read only known non-sensitive legacy keys, filter numbered placeholder titles and stale premium covers, write schema version 3, then set a migration fingerprint. Keep the old values for rollback.

- [ ] **Step 4: Implement route-level recovery**

Wrap each feature render in `renderSafely(route, renderer)`. On exception, log a redacted diagnostic object and render recovery controls without clearing the previous stable DOM until the fallback is ready.

- [ ] **Step 5: Run tests and commit**

Run: `python -m unittest tests.test_ui_v3_migration tests.test_ui_v3_contract -v; node --check src/douban_recommender/ui/js/core/migrate.js; node --check src/douban_recommender/ui/js/core/recovery.js`

```powershell
git add src/douban_recommender/ui/js/core/migrate.js src/douban_recommender/ui/js/core/recovery.js src/douban_recommender/ui/js/app.js tests/test_ui_v3_migration.py
git commit -m "feat: migrate and recover cinescope client state"
```

### Task 2: Runtime Diagnostics and Media Audit Endpoint

**Files:**
- Create: `src/douban_recommender/diagnostics.py`
- Create: `tests/test_diagnostics.py`
- Modify: `src/douban_recommender/web.py`

**Interfaces:**
- Produces: `GET /api/v2/diagnostics`
- Produces: `audit_recommendation_media(rows, db) -> MediaAudit`
- Produces: `MediaAudit(total, ready, degraded, ambiguous, missing, wrong_identity_candidates)`

- [ ] **Step 1: Write redaction and count tests**

```python
def test_diagnostics_redacts_sensitive_values():
    payload = build_diagnostics({"cookie": "secret", "tmdb_api_key": "key"})
    text = json.dumps(payload, ensure_ascii=False)
    self.assertNotIn("secret", text)
    self.assertNotIn("\"key\"", text)

def test_media_audit_counts_local_ready_assets_only():
    audit = audit_recommendation_media(seed_rows(), self.db)
    self.assertEqual(audit.ready, 2)
    self.assertEqual(audit.missing, 1)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_diagnostics -v`

Expected: missing diagnostics module.

- [ ] **Step 3: Implement redacted diagnostics**

Return schema version, app version, database path hash rather than full path, sync counts, session counts, provider health, queue status, cache bytes, and media audit totals. Never return request headers or raw environment values.

- [ ] **Step 4: Run diagnostics and API tests**

Run: `python -m unittest tests.test_diagnostics tests.test_media_api tests.test_web_api -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/diagnostics.py src/douban_recommender/web.py tests/test_diagnostics.py
git commit -m "feat: add redacted runtime diagnostics"
```

### Task 3: Deterministic Browser Audit Helper

**Files:**
- Create: `src/douban_recommender/ui/js/core/audit.js`
- Create: `tests/test_ui_v3_audit.py`
- Modify: `src/douban_recommender/ui/js/app.js`

**Interfaces:**
- Produces: `window.__CINESCOPE_AUDIT__()` in development/local mode.
- Returns: `{route, viewport, brokenImages, externalImages, overflowNodes, emptyMain, focusFailures, reducedMotion}`

- [ ] **Step 1: Write audit contract test**

```python
def test_browser_audit_checks_images_overflow_and_empty_main():
    js = ui_text("js/core/audit.js")
    for token in ("naturalWidth", "scrollWidth", "clientWidth", "externalImages", "emptyMain"):
        self.assertIn(token, js)
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_audit -v`

Expected: missing module.

- [ ] **Step 3: Implement audit helper**

```javascript
export function runAudit() {
  const images = [...document.images];
  const brokenImages = images.filter(img => img.complete && img.naturalWidth === 0);
  const externalImages = images.filter(img => !new URL(img.src, location.href).pathname.startsWith("/media/"));
  const overflowNodes = [...document.querySelectorAll("body *")].filter(
    node => node.scrollWidth > node.clientWidth + 2 && getComputedStyle(node).overflowX === "visible"
  );
  return { route: location.pathname, viewport: [innerWidth, innerHeight], brokenImages: describe(brokenImages), externalImages: describe(externalImages), overflowNodes: describe(overflowNodes), emptyMain: !document.querySelector("#app-view")?.textContent.trim() };
}
```

- [ ] **Step 4: Run syntax and contract tests**

Run: `python -m unittest tests.test_ui_v3_audit -v; node --check src/douban_recommender/ui/js/core/audit.js`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/ui/js/core/audit.js src/douban_recommender/ui/js/app.js tests/test_ui_v3_audit.py
git commit -m "test: add in-browser cinescope audit hook"
```

### Task 4: Four-Viewport Visual Acceptance Loop

**Files:**
- Create: `docs/acceptance/2026-07-10-cinescope-v3.md`
- Create: `output/acceptance/.gitkeep`
- Modify only UI files implicated by observed defects.

**Interfaces:**
- Consumes: `window.__CINESCOPE_AUDIT__()`
- Produces: screenshots and an evidence table for every required route/viewport.

- [ ] **Step 1: Start V3 on a dedicated port**

Run:

```powershell
$env:CINESCOPE_UI_VERSION='v3'
$env:CINESCOPE_DATA_DIR="$PWD\output\acceptance-data"
python -m douban_recommender.web --host 127.0.0.1 --port 7862 --no-browser
```

Expected: service prints `http://127.0.0.1:7862` and remains running.

- [ ] **Step 2: Inspect all principal routes at 1440×900**

Use Codex computer-use/browser tools to visit `/tonight`, each content channel, one title detail, one person detail, `/universe`, `/library`, `/taste`, and `/health`. For each route run `window.__CINESCOPE_AUDIT__()` and save a screenshot under `output/acceptance/1440x900/`.

Expected for every route: `brokenImages=[]`, `externalImages=[]`, `overflowNodes=[]`, `emptyMain=false`.

- [ ] **Step 3: Repeat at 1280×800, 1024×768, and 390×844**

Save screenshots under matching viewport directories. At 390px verify the bottom navigation replaces the desktop rail and no horizontal page scroll exists.

- [ ] **Step 4: Fix every observed issue with a failing contract test first**

For each issue, add a focused assertion to `tests/test_ui_v3_contract.py` or a relevant Python test, verify it fails, implement the minimum CSS/JS change, and repeat the exact screenshot/audit.

- [ ] **Step 5: Record evidence**

`docs/acceptance/2026-07-10-cinescope-v3.md` must list route, viewport, screenshot path, audit result, observed issue, and final status. Do not write “looks good” without an audit object.

- [ ] **Step 6: Commit acceptance fixes and evidence**

```powershell
git add src/douban_recommender/ui tests/test_ui_v3_contract.py docs/acceptance/2026-07-10-cinescope-v3.md output/acceptance/.gitkeep
git commit -m "fix: pass cinescope visual acceptance"
```

### Task 5: Live Sync, Recommendation, Batch, and Refresh Acceptance

**Files:**
- Create: `tests/test_live_acceptance_contract.py`
- Modify only code implicated by failures.
- Update: `docs/acceptance/2026-07-10-cinescope-v3.md`

**Interfaces:**
- Validates the known profile `272042071` without persisting a Cookie.

- [ ] **Step 1: Add fixture-level acceptance assertions**

```python
def test_profile_url_normalizes_known_user():
    value = "https://www.douban.com/people/272042071/?_dtcc=1&_i=fixture"
    self.assertEqual(normalize_user(value), "272042071")

def test_auto_pagination_safety_cap_is_not_user_visible_limit():
    self.assertGreaterEqual(DEFAULT_SYNC_SAFETY_CAP, 250)
```

- [ ] **Step 2: Run fixture acceptance tests**

Run: `python -m unittest tests.test_live_acceptance_contract -v`

Expected: PASS after any needed normalization fix.

- [ ] **Step 3: Run a public or session-authorized sync**

Use the UI with `https://www.douban.com/people/272042071/`. If Douban requires login, paste the Cookie only into the visible session input; do not retrieve it from disk. Confirm the UI reports collect/wish pages, successes, failures, and stop reason. Expected known baseline is approximately 242 watched and 34 wanted, allowing accurate explanation if Douban data changed.

- [ ] **Step 4: Validate recommendation semantics**

Create a 160-target session. Confirm all three numbers are visible, anime contains no animated films, series avoids costume dominance, and three consecutive batch changes do not repeat titles before exhaustion.

- [ ] **Step 5: Validate refresh restoration**

On anime batch 3, scroll midway, open a title detail, refresh, go back, and confirm route, anime batch 3, scroll, and candidate tray restore. Run the browser audit after refresh.

- [ ] **Step 6: Fix failures through TDD and update evidence**

Add a regression test for every failure before changing implementation. Record final counts and restoration evidence in the acceptance document.

- [ ] **Step 7: Commit**

```powershell
git add tests/test_live_acceptance_contract.py src docs/acceptance/2026-07-10-cinescope-v3.md
git commit -m "fix: pass live sync and recommendation acceptance"
```

### Task 6: Performance and Media Coverage Gate

**Files:**
- Create: `tests/test_performance_contract.py`
- Modify only files implicated by measurements.
- Update: `docs/acceptance/2026-07-10-cinescope-v3.md`

**Interfaces:**
- Validates warm-cache LCP target, bounded initial card count, prefetch priority, and media coverage.

- [ ] **Step 1: Add static performance contract tests**

```python
def test_initial_channel_render_is_bounded():
    js = ui_text("js/features/tonight.js")
    self.assertIn("MAX_INITIAL_CARDS", js)
    self.assertRegex(js, r"MAX_INITIAL_CARDS\s*=\s*(?:9|10|11|12)")

def test_people_prefetch_is_limited_to_director_and_eight_cast():
    js = ui_text("js/features/detail.js")
    self.assertIn("casts.slice(0, 8)", js)
```

- [ ] **Step 2: Measure warm-cache navigation timing in browser**

Use `PerformanceObserver` and `performance.getEntriesByType('navigation')`. Record LCP, DOM content loaded, total transferred local media bytes, and long tasks for `/tonight` and one detail route.

Expected: warm-cache LCP ≤ 2500ms and no interaction-blocking long task above 200ms.

- [ ] **Step 3: Audit media coverage and identity canaries**

Call `/api/v2/diagnostics`. For the current visible session, require zero missing browser media, zero wrong-identity canaries, and designed fallback labels for unresolved real portraits. Record real poster and portrait coverage separately rather than hiding fallback use.

- [ ] **Step 4: Fix and remeasure**

Prioritize reducing initial DOM count, preloading only Hero/current shelf, deferring universe canvas, and generating responsive thumbnails. Add a regression test for every code change.

- [ ] **Step 5: Commit**

```powershell
git add tests/test_performance_contract.py src docs/acceptance/2026-07-10-cinescope-v3.md
git commit -m "perf: meet cinescope interaction budgets"
```

### Task 7: Default Switch, Documentation, and Rollback

**Files:**
- Modify: `src/douban_recommender/web.py`
- Modify: `README.md`
- Modify: `run_app.ps1`
- Modify: `tests/test_readme.py`
- Modify: `tests/test_ui_v3_assets.py`

**Interfaces:**
- Makes V3 default.
- Keeps `CINESCOPE_UI_VERSION=legacy` rollback.
- Produces: `selected_ui_version(env: Mapping[str, str] | None = None) -> str`

- [ ] **Step 1: Write failing default and rollback tests**

```python
def test_v3_is_default_and_legacy_is_explicit_opt_in():
    self.assertEqual(selected_ui_version({}), "v3")
    self.assertEqual(selected_ui_version({"CINESCOPE_UI_VERSION": "legacy"}), "legacy")
```

- [ ] **Step 2: Run and verify failure**

Run: `python -m unittest tests.test_ui_v3_assets -v`

Expected: default still legacy.

- [ ] **Step 3: Switch default and document exact launch flow**

`run_app.ps1` launches V3 without requiring environment variables. README documents first sync, Cookie paste location, session-only behavior, optional local proxy port, API keys through environment variables, media health, cache clearing, and legacy rollback.

```python
def selected_ui_version(env=None):
    value = str((os.environ if env is None else env).get("CINESCOPE_UI_VERSION", "v3")).lower()
    return "legacy" if value == "legacy" else "v3"
```

- [ ] **Step 4: Run focused tests**

Run: `python -m unittest tests.test_ui_v3_assets tests.test_readme -v`

Expected: PASS.

- [ ] **Step 5: Commit**

```powershell
git add src/douban_recommender/web.py README.md run_app.ps1 tests/test_readme.py tests/test_ui_v3_assets.py
git commit -m "feat: make cinescope v3 the default experience"
```

### Task 8: Final Verification and Completion Evidence

**Files:**
- Update: `docs/acceptance/2026-07-10-cinescope-v3.md`

**Interfaces:**
- Produces final test, browser, media, performance, and rollback evidence.

- [ ] **Step 1: Run all automated tests**

Run: `python -m unittest discover -s tests -v`

Expected: all tests PASS with the final count recorded verbatim.

- [ ] **Step 2: Run JavaScript syntax checks**

Run: `Get-ChildItem src/douban_recommender/ui/js -Recurse -Filter *.js | ForEach-Object { node --check $_.FullName }`

Expected: no output and exit code 0.

- [ ] **Step 3: Run source hygiene checks**

Run: `git diff --check; rg -n "TBD|TODO|FIXME" src tests README.md docs/acceptance`

Expected: no unintended placeholder or whitespace errors.

- [ ] **Step 4: Repeat final browser smoke**

At 1440×900 and 390×844, verify `/tonight`, anime batch change, one detail, one person, `/health`, refresh restoration, and `window.__CINESCOPE_AUDIT__()` all pass.

- [ ] **Step 5: Verify rollback**

Run with `$env:CINESCOPE_UI_VERSION='legacy'` on a different port and confirm the legacy page still loads without changing data.

- [ ] **Step 6: Record exact evidence and commit**

```powershell
git add docs/acceptance/2026-07-10-cinescope-v3.md
git commit -m "docs: record cinescope v3 completion evidence"
```
