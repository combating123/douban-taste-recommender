import json
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "douban_recommender" / "ui"


def module_url(relative_path):
    return (UI_ROOT / relative_path).resolve().as_uri()


def run_node_module(script):
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            "Node module test failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return json.loads(result.stdout)


def fake_recovery_dom():
    return r'''
      class FakeElement {
        constructor(tagName, id = "") {
          this.tagName = String(tagName).toUpperCase(); this.id = id; this.children = [];
          this.parentNode = null; this.dataset = {}; this.attributes = new Map();
          this.listeners = new Map(); this.textContent = ""; this.className = ""; this.type = "";
        }
        append(...nodes) { nodes.forEach((node) => { this.children.push(node); node.parentNode = this; }); }
        replaceChildren(...nodes) {
          this.children.forEach((node) => { node.parentNode = null; });
          this.children = []; this.append(...nodes);
        }
        setAttribute(name, value) { this.attributes.set(name, String(value)); }
        addEventListener(type, listener) { this.listeners.set(type, listener); }
        querySelector(selector) {
          const wanted = selector.toUpperCase();
          const visit = (node) => {
            for (const child of node.children || []) {
              if (child.tagName === wanted) return child;
              const nested = visit(child); if (nested) return nested;
            }
            return null;
          };
          return visit(this);
        }
        focus(options) { this.focusOptions = options; }
      }
      const appView = new FakeElement("main", "app-view");
      globalThis.document = {
        readyState: "loading",
        createElement(tagName) { return new FakeElement(tagName); },
        getElementById(id) { return id === "app-view" ? appView : null; },
        addEventListener() {}, querySelectorAll() { return []; },
      };
      globalThis.window = { matchMedia() { return { matches: true }; } };
    '''


def timed_recovery_dom():
    return r'''
      const observedMutations = [];
      class FakeMutationObserver {
        constructor(callback) { this.callback = callback; this.root = null; this.active = false; observedMutations.push(this); }
        observe(root, options) { this.root = root; this.options = options; this.active = true; root.observers.add(this); }
        disconnect() { this.active = false; this.root?.observers.delete(this); this.root = null; }
      }
      class FakeElement {
        constructor(tagName, id = "") {
          this.tagName = String(tagName).toUpperCase(); this.id = id; this.children = [];
          this.parentNode = null; this.dataset = {}; this.attributes = new Map();
          this.listeners = new Map(); this.textContent = ""; this.className = ""; this.type = "";
          this.observers = new Set(); this.focusCalls = [];
        }
        append(...nodes) { nodes.forEach((node) => { this.children.push(node); node.parentNode = this; }); }
        replaceChildren(...nodes) {
          this.children.forEach((node) => { node.parentNode = null; });
          this.children = []; this.append(...nodes);
          for (const observer of [...this.observers]) {
            queueMicrotask(() => { if (observer.active) observer.callback([{ type: "childList", target: this }], observer); });
          }
        }
        setAttribute(name, value) { this.attributes.set(name, String(value)); }
        getAttribute(name) { return this.attributes.get(name) ?? null; }
        addEventListener(type, listener) { this.listeners.set(type, listener); }
        querySelector(selector) {
          const wanted = selector.toUpperCase();
          const visit = (node) => {
            for (const child of node.children || []) {
              if (child.tagName === wanted) return child;
              const nested = visit(child); if (nested) return nested;
            }
            return null;
          };
          return visit(this);
        }
        focus(options) { this.focusCalls.push(options); }
      }
      const appView = new FakeElement("main", "app-view");
      globalThis.MutationObserver = FakeMutationObserver;
      const bodyClasses = new Set();
      globalThis.document = {
        readyState: "loading", body: { classList: { toggle(name, enabled) { if (enabled) bodyClasses.add(name); else bodyClasses.delete(name); } } },
        createElement(tagName) { return new FakeElement(tagName); },
        getElementById(id) { return id === "app-view" ? appView : null; },
        addEventListener() {}, querySelectorAll() { return []; },
      };
      globalThis.window = { matchMedia() { return { matches: true }; } };
      const deferred = () => { let resolve; let reject; const promise = new Promise((yes, no) => { resolve = yes; reject = no; }); return { promise, resolve, reject }; };
      const flushMicrotasks = async () => { for (let index = 0; index < 8; index += 1) await Promise.resolve(); };
    '''


class UiV3MigrationTests(unittest.TestCase):
    def test_migration_projects_only_safe_fields_and_filters_legacy_artifacts(self):
        result = run_node_module(
            f'''
            import {{ migrateLegacyClientState, MIGRATION_FINGERPRINT_KEY }} from "{module_url('js/core/migrate.js')}";
            import {{ UI_STATE_KEY }} from "{module_url('js/core/store.js')}";
            const values = new Map([
              ["CINESCOPE_LAST_RECOMMENDATION_V4", JSON.stringify({{
                railHidden: true,
                recommendations: [
                  {{ id: "premium-42", title: "电影策展12", poster: "data:image/svg+xml;base64,SECRET" }},
                  {{ id: "douban:1", title: "Safe title", cover: "https://images.example/secret.jpg" }},
                ],
                profile: {{ raw: "must-not-copy" }},
                url: "https://snapshot.example/raw",
              }})],
              ["CINESCOPE_PREFS_V2", JSON.stringify({{
                userInput: "https://www.douban.com/people/safe_user/?from=home",
                maxPages: 80, includeWish: false, includeDo: true,
                expectedCollect: 242, expectedWish: 34,
                rememberCookieSession: true,
                arbitrarySecret: "sk-super-secret-value",
              }})],
              ["CINESCOPE_POSTER_SOURCE_PREFS_V1", JSON.stringify({{ tmdb_api_key: "must-not-read" }})],
            ]);
            const gets = []; const sets = [];
            const storage = {{
              getItem(key) {{ gets.push(key); return values.has(key) ? values.get(key) : null; }},
              setItem(key, value) {{ sets.push([key, String(value)]); values.set(key, String(value)); }},
            }};
            const migration = migrateLegacyClientState(storage);
            const stateRaw = values.get(UI_STATE_KEY); const fingerprint = values.get(MIGRATION_FINGERPRINT_KEY);
            console.log(JSON.stringify({{ migration, gets, sets: sets.map(([key]) => key), state: JSON.parse(stateRaw), stateRaw, fingerprint }}));
            '''
        )

        self.assertEqual(3, result["state"]["schemaVersion"])
        self.assertEqual("hidden", result["state"]["rail"]["mode"])
        self.assertEqual("safe_user", result["state"]["sync"]["profile"])
        self.assertEqual(80, result["state"]["sync"]["options"]["maxPages"])
        self.assertFalse(result["state"]["sync"]["options"]["includeWish"])
        self.assertTrue(result["state"]["sync"]["options"]["includeDo"])
        self.assertEqual(1, result["migration"]["stats"]["placeholderTitles"])
        self.assertEqual(1, result["migration"]["stats"]["premiumIds"])
        self.assertEqual(1, result["migration"]["stats"]["dataImages"])
        self.assertGreaterEqual(result["migration"]["stats"]["externalUrls"], 1)
        self.assertEqual(
            {
                "cinescope.ui.state",
                "cinescope.ui.migration.v3",
                "CINESCOPE_LAST_RECOMMENDATION_V4",
                "CINESCOPE_PREFS_V2",
            },
            set(result["gets"]),
        )
        combined = result["stateRaw"] + result["fingerprint"] + json.dumps(result["migration"])
        for forbidden in ("premium-42", "电影策展12", "data:image", "http://", "https://", "secret", "api_key", "Cookie"):
            self.assertNotIn(forbidden.lower(), combined.lower())

    def test_valid_v3_is_never_overwritten(self):
        result = run_node_module(
            f'''
            import {{ migrateLegacyClientState }} from "{module_url('js/core/migrate.js')}";
            import {{ createEmptyUiState, UI_STATE_KEY }} from "{module_url('js/core/store.js')}";
            const original = JSON.stringify({{ ...createEmptyUiState(), rail: {{ mode: "collapsed" }} }});
            const values = new Map([[UI_STATE_KEY, original], ["CINESCOPE_LAST_RECOMMENDATION_V4", JSON.stringify({{ railHidden: true }})]]);
            const sets = [];
            const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ sets.push(key); values.set(key, String(value)); }} }};
            const migration = migrateLegacyClientState(storage);
            console.log(JSON.stringify({{ migration, original, after: values.get(UI_STATE_KEY), sets }}));
            '''
        )
        self.assertEqual(result["original"], result["after"])
        self.assertEqual([], result["sets"])
        self.assertEqual("existing-v3", result["migration"]["status"])

    def test_fingerprint_failure_retries_without_rewriting_state(self):
        result = run_node_module(
            f'''
            import {{ migrateLegacyClientState, MIGRATION_FINGERPRINT_KEY }} from "{module_url('js/core/migrate.js')}";
            import {{ UI_STATE_KEY }} from "{module_url('js/core/store.js')}";
            const values = new Map([["CINESCOPE_PREFS_V2", JSON.stringify({{ userInput: "safe_user", maxPages: 12 }})]]);
            const writes = []; let failFingerprint = true;
            const storage = {{
              getItem(key) {{ return values.get(key) ?? null; }},
              setItem(key, value) {{
                writes.push(key);
                if (key === MIGRATION_FINGERPRINT_KEY && failFingerprint) {{ failFingerprint = false; throw new Error("fingerprint quota"); }}
                values.set(key, String(value));
              }},
            }};
            const first = migrateLegacyClientState(storage);
            const rawAfterFirst = values.get(UI_STATE_KEY);
            const second = migrateLegacyClientState(storage);
            const rawAfterSecond = values.get(UI_STATE_KEY);
            const third = migrateLegacyClientState(storage);
            console.log(JSON.stringify({{ first, second, third, writes, rawAfterFirst, rawAfterSecond, fingerprint: values.get(MIGRATION_FINGERPRINT_KEY) }}));
            '''
        )
        self.assertEqual("fingerprint-write-failed", result["first"]["status"])
        self.assertEqual("fingerprinted-existing-migration", result["second"]["status"])
        self.assertEqual("already-migrated", result["third"]["status"])
        self.assertEqual(result["rawAfterFirst"], result["rawAfterSecond"])
        self.assertEqual(1, result["writes"].count("cinescope.ui.state"))
        self.assertEqual(2, result["writes"].count("cinescope.ui.migration.v3"))

    def test_state_quota_failure_never_writes_fingerprint_and_keeps_rollback_bytes(self):
        result = run_node_module(
            f'''
            import {{ migrateLegacyClientState, MIGRATION_FINGERPRINT_KEY }} from "{module_url('js/core/migrate.js')}";
            import {{ UI_STATE_KEY }} from "{module_url('js/core/store.js')}";
            const snapshot = '{{"railHidden":true,"recommendations":[{{"title":"Keep me byte-for-byte"}}]}}';
            const prefs = '{{"userInput":"safe_user","maxPages":40}}';
            const rollback = {{
              CINESCOPE_LAST_RECOMMENDATION_V1: 'v1:raw bytes',
              CINESCOPE_LAST_RECOMMENDATION_V2: 'v2:raw bytes',
              CINESCOPE_LAST_RECOMMENDATION_V3: 'v3:raw bytes',
              CINESCOPE_LAST_RECOMMENDATION_V4: snapshot,
              CINESCOPE_PREFS_V2: prefs,
            }};
            const values = new Map(Object.entries(rollback));
            const writes = [];
            const storage = {{
              getItem(key) {{ return values.get(key) ?? null; }},
              setItem(key, value) {{ writes.push(key); if (key === UI_STATE_KEY) throw new Error("quota"); values.set(key, String(value)); }},
            }};
            const migration = migrateLegacyClientState(storage);
            console.log(JSON.stringify({{ migration, writes, rollback, after: Object.fromEntries([...Object.keys(rollback)].map((key) => [key, values.get(key)])), fingerprint: values.get(MIGRATION_FINGERPRINT_KEY) ?? null }}));
            '''
        )
        self.assertEqual("state-write-failed", result["migration"]["status"])
        self.assertEqual(["cinescope.ui.state"], result["writes"])
        self.assertIsNone(result["fingerprint"])
        self.assertEqual(result["rollback"], result["after"])

    def test_malformed_json_schema_mismatch_and_storage_errors_do_not_throw_or_write_partial_state(self):
        result = run_node_module(
            f'''
            import {{ migrateLegacyClientState }} from "{module_url('js/core/migrate.js')}";
            import {{ UI_STATE_KEY }} from "{module_url('js/core/store.js')}";
            const malformedValues = new Map([[UI_STATE_KEY, '{{bad-json'], ["CINESCOPE_LAST_RECOMMENDATION_V4", '{{also-bad']]);
            const malformedWrites = [];
            const malformed = migrateLegacyClientState({{ getItem(key) {{ return malformedValues.get(key) ?? null; }}, setItem(key, value) {{ malformedWrites.push([key, value]); }} }});
            const mismatchValues = new Map([[UI_STATE_KEY, JSON.stringify({{ schemaVersion: 2, partial: true }})]]);
            const mismatchWrites = [];
            const mismatch = migrateLegacyClientState({{ getItem(key) {{ return mismatchValues.get(key) ?? null; }}, setItem(key, value) {{ mismatchWrites.push([key, value]); }} }});
            const storageError = migrateLegacyClientState({{ getItem() {{ throw new Error("denied"); }}, setItem() {{ throw new Error("must not write"); }} }});
            console.log(JSON.stringify({{ malformed, malformedWrites, mismatch, mismatchWrites, storageError }}));
            '''
        )
        self.assertEqual([], result["malformedWrites"])
        self.assertEqual([], result["mismatchWrites"])
        self.assertEqual("no-safe-legacy-state", result["malformed"]["status"])
        self.assertEqual("no-safe-legacy-state", result["mismatch"]["status"])
        self.assertEqual("storage-unavailable", result["storageError"]["status"])

    def test_sync_throw_async_reject_and_clear_then_throw_never_leave_blank_root(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            const diagnostics = []; console.error = (...args) => diagnostics.push(args);
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely }} = await import("{module_url('js/core/recovery.js')}");
            const stableNode = document.createElement("section"); stableNode.textContent = "stable"; appView.replaceChildren(stableNode);
            let currentPath = "/library";
            configureRecoveryBoundary({{ root: appView, getCurrentPath: () => currentPath }});
            rememberLastStableState({{
              activePath: "/library", activeParams: {{}}, scrollByRoute: {{ "/library": 123 }}, rail: {{ mode: "hidden" }},
              recommendation: {{ activeChannel: "series", channels: {{ series: {{ sessionId: "session-1", batchIndex: 2, batchIds: ["batch-1"] }} }} }},
              candidateTray: {{ context: {{ universeFocusId: "douban:42", expandedIds: ["douban:43"], externalUrl: "https://bad.example" }} }},
              library: {{ state: "wish" }}, sync: {{ profile: "safe_user", options: {{ maxPages: 20 }}, knownJobIds: ["job-1"] }},
              commandLens: {{ draft: "must-not-stabilize", chips: [{{ key: "x" }}] }}, apiKey: "must-not-stabilize",
            }});
            const syncResult = await renderSafely({{ path: currentPath }}, () => {{ throw new Error("Cookie: bid=secret https://bad.example"); }});
            const syncText = appView.children[0]?.children?.map((node) => node.textContent).join(" ") || "";
            const asyncResult = await renderSafely({{ path: currentPath }}, async () => {{ throw new Error("async secret"); }});
            const clearResult = await renderSafely({{ path: currentPath }}, () => {{ appView.replaceChildren(); throw new Error("cleared"); }});
            console.log(JSON.stringify({{ syncResult, asyncResult, clearResult, childCount: appView.children.length, syncText, diagnostics }}));
            '''
        )
        self.assertGreater(result["childCount"], 0)
        self.assertTrue(result["syncResult"]["recovered"])
        self.assertTrue(result["asyncResult"]["recovered"])
        self.assertTrue(result["clearResult"]["recovered"])
        self.assertIn("恢复上次稳定状态", result["syncText"])
        self.assertNotIn("secret", result["syncText"].lower())
        self.assertNotIn("http", result["syncText"].lower())
        self.assertEqual(3, len(result["diagnostics"]))
        diagnostic_text = json.dumps(result["diagnostics"], ensure_ascii=False)
        for forbidden in ("secret", "Cookie", "http://", "https://", "rawError"):
            self.assertNotIn(forbidden, diagnostic_text)

    def test_pending_clear_then_reject_restores_previous_dom_before_fallback_and_nonempty_commit_wins(self):
        result = run_node_module(
            f'''
            {timed_recovery_dom()}
            console.error = () => {{}};
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely }} = await import("{module_url('js/core/recovery.js')}");
            let currentPath = "/library";
            configureRecoveryBoundary({{ root: appView, getCurrentPath: () => currentPath }});
            rememberLastStableState({{ activePath: currentPath, activeParams: {{}}, scrollByRoute: {{}}, rail: {{ mode: "expanded" }}, recommendation: {{ channels: {{}} }}, candidateTray: {{ context: {{}} }}, library: {{ state: "all" }}, sync: {{}} }});
            const stable = document.createElement("section"); stable.textContent = "previous stable"; appView.replaceChildren(stable);

            const rejection = deferred();
            const pendingFailure = renderSafely({{ path: currentPath }}, async () => {{
              appView.replaceChildren();
              await rejection.promise;
              throw new Error("late failure");
            }});
            await flushMicrotasks();
            const duringFailure = appView.children.map((node) => node.textContent);
            rejection.resolve();
            const failed = await pendingFailure;
            const afterFailure = appView.children[0]?.querySelector?.("button")?.textContent || appView.querySelector("button")?.textContent || "";

            appView.replaceChildren(stable);
            const success = deferred();
            const nextView = document.createElement("section"); nextView.textContent = "complete view";
            const pendingSuccess = renderSafely({{ path: currentPath }}, async () => {{
              appView.replaceChildren();
              await success.promise;
              appView.replaceChildren(nextView);
              return "done";
            }});
            await flushMicrotasks();
            const duringSuccess = appView.children.map((node) => node.textContent);
            success.resolve();
            const succeeded = await pendingSuccess;
            await flushMicrotasks();
            console.log(JSON.stringify({{
              duringFailure, failed, afterFailure, duringSuccess, succeeded,
              finalText: appView.children[0]?.textContent,
              observersDisconnected: observedMutations.every((observer) => !observer.active),
            }}));
            '''
        )
        self.assertEqual(["previous stable"], result["duringFailure"])
        self.assertTrue(result["failed"]["recovered"])
        self.assertEqual("恢复上次稳定状态", result["afterFailure"])
        self.assertEqual(["previous stable"], result["duringSuccess"])
        self.assertTrue(result["succeeded"]["ok"])
        self.assertEqual("complete view", result["finalText"])
        self.assertTrue(result["observersDisconnected"])

    def test_microtask_fallback_guards_pending_blank_and_dispose_or_stale_observer_never_writes(self):
        result = run_node_module(
            f'''
            {timed_recovery_dom()}
            console.error = () => {{}};
            const {{ configureRecoveryBoundary, renderSafely }} = await import("{module_url('js/core/recovery.js')}");
            const {{ createAppRouteHandler }} = await import("{module_url('js/app.js')}");
            let currentPath = "/title/old";
            configureRecoveryBoundary({{ root: appView, getCurrentPath: () => currentPath }});
            const stable = document.createElement("section"); stable.textContent = "old stable"; appView.replaceChildren(stable);

            delete globalThis.MutationObserver;
            const fallbackDeferred = deferred();
            const fallbackRender = renderSafely({{ path: currentPath }}, async () => {{ appView.replaceChildren(); await fallbackDeferred.promise; }});
            await flushMicrotasks();
            const microtaskRestored = appView.children[0]?.textContent;
            fallbackDeferred.resolve(); await fallbackRender;

            globalThis.MutationObserver = FakeMutationObserver;
            const staleDeferred = deferred();
            const state = {{ activePath: "/library", activeParams: {{}}, recommendation: {{ channels: {{}} }}, scrollByRoute: {{}}, rail: {{ mode: "expanded" }}, candidateTray: {{ context: {{}} }}, library: {{ state: "all" }}, sync: {{}} }};
            const store = {{ getState() {{ return state; }}, dispatch(action) {{ if (action.type === "route/changed") state.activePath = action.route.path; }} }};
            const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
            const handler = createAppRouteHandler({{
              appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate,
              prepare() {{}}, setNavigation() {{}}, setStatus() {{}}, announceRoute() {{}},
              async renderTasteView() {{ appView.replaceChildren(); await staleDeferred.promise; throw new Error("stale"); }},
            }});
            const staleRender = handler({{ name: "taste", path: "/taste", params: {{}} }});
            await flushMicrotasks();
            handler.dispose();
            state.activePath = "/library";
            const fresh = document.createElement("section"); fresh.textContent = "fresh route"; appView.replaceChildren(fresh);
            await flushMicrotasks();
            staleDeferred.resolve();
            const staleResult = await staleRender;
            await flushMicrotasks();
            console.log(JSON.stringify({{
              microtaskRestored, staleResult, finalText: appView.children[0]?.textContent,
              observersDisconnected: observedMutations.every((observer) => !observer.active),
            }}));
            '''
        )
        self.assertEqual("old stable", result["microtaskRestored"])
        self.assertFalse(result["staleResult"])
        self.assertEqual("fresh route", result["finalText"])
        self.assertTrue(result["observersDisconnected"])

    def test_stale_recovery_does_not_overwrite_new_route(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            const {{ configureRecoveryBoundary, renderSafely }} = await import("{module_url('js/core/recovery.js')}");
            let currentPath = "/title/old";
            configureRecoveryBoundary({{ root: appView, getCurrentPath: () => currentPath }});
            let rejectOld;
            const old = renderSafely({{ path: "/title/old" }}, () => new Promise((_resolve, reject) => {{ rejectOld = reject; }}));
            currentPath = "/library";
            const fresh = document.createElement("section"); fresh.textContent = "new route";
            await renderSafely({{ path: "/library" }}, () => {{ appView.replaceChildren(fresh); }});
            rejectOld(new Error("late failure"));
            const oldResult = await old;
            console.log(JSON.stringify({{ oldResult, text: appView.children[0]?.textContent, count: appView.children.length }}));
            '''
        )
        self.assertTrue(result["oldResult"]["stale"])
        self.assertEqual("new route", result["text"])
        self.assertEqual(1, result["count"])

    def test_retry_restores_allowlisted_last_stable_state_once(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely, restoreLastStableState }} = await import("{module_url('js/core/recovery.js')}");
            let currentPath = "/health"; const retries = [];
            configureRecoveryBoundary({{ root: appView, getCurrentPath: () => currentPath, onRetry: (stable) => retries.push(stable) }});
            rememberLastStableState({{
              activePath: "/library", activeParams: {{ filter: "wish", url: "https://bad.example" }},
              scrollByRoute: {{ "/library": 456 }}, rail: {{ mode: "collapsed" }},
              recommendation: {{ activeChannel: "movie", channels: {{ movie: {{ sessionId: "session-1", batchIndex: 3, batchIds: ["batch-1", "https://bad.example"] }} }} }},
              candidateTray: {{ context: {{ universeFocusId: "douban:42", expandedIds: ["douban:43"], draft: "drop" }} }},
              library: {{ state: "wish" }}, sync: {{ profile: "https://www.douban.com/people/safe_user/", options: {{ maxPages: 30, includeWish: true }}, knownJobIds: ["job-1"] }},
              commandLens: {{ draft: "drop", chips: [{{ key: "drop" }}] }}, rawError: "drop", headers: {{ Authorization: "drop" }},
            }});
            await renderSafely({{ path: currentPath }}, () => {{ throw new Error("failed"); }});
            const button = appView.querySelector("button"); button.listeners.get("click")({{ preventDefault() {{}} }});
            const stable = restoreLastStableState();
            console.log(JSON.stringify({{ retries, stable }}));
            '''
        )
        self.assertEqual(1, len(result["retries"]))
        self.assertEqual("/library", result["retries"][0]["activePath"])
        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in ("commandLens", "draft", "chips", "apiKey", "headers", "rawError", "http://", "https://"):
            self.assertNotIn(forbidden, serialized)
        self.assertEqual("safe_user", result["stable"]["sync"]["profile"])

    def test_recovery_merges_fresh_scroll_preserves_candidate_counts_and_discards_failed_render_state(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            console.error = () => {{}};
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely, restoreLastStableState }} = await import("{module_url('js/core/recovery.js')}");
            const stableState = {{
              activePath: "/library", activeParams: {{ filter: "wish" }}, scrollByRoute: {{ "/library": 100 }},
              rail: {{ mode: "collapsed" }},
              recommendation: {{
                activeChannel: "movie",
                channels: {{
                  movie: {{ sessionId: "session-stable", batchIndex: 2, batchIds: ["batch-stable"], candidate_counts: {{ target_size: null, returned_size: 37 }} }},
                  series: {{ sessionId: "session-series", candidate_counts: {{ target_size: -1, returned_size: 1.5 }} }},
                }},
              }},
              candidateTray: {{ context: {{ universeFocusId: "douban:42" }} }},
              library: {{ state: "wish" }}, sync: {{}},
            }};
            const liveState = JSON.parse(JSON.stringify(stableState));
            liveState.scrollByRoute["/library"] = 900;
            liveState.candidateTray.itemIds = ["douban:pre-render-drop"];
            let reads = 0; const retries = [];
            rememberLastStableState(stableState);
            configureRecoveryBoundary({{
              root: appView,
              getCurrentPath: () => "/taste",
              getStableState: () => {{ reads += 1; return liveState; }},
              onRetry: (state) => retries.push(state),
            }});
            const result = await renderSafely({{ path: "/taste" }}, () => {{
              liveState.scrollByRoute["/library"] = 1200;
              liveState.recommendation.channels.movie.candidate_counts.returned_size = 999;
              liveState.candidateTray.itemIds.push("douban:failed-render");
              liveState.commandLens = {{ draft: "failed renderer draft" }};
              throw new Error("failed");
            }});
            const button = appView.querySelector("button"); button.listeners.get("click")({{ preventDefault() {{}} }});
            console.log(JSON.stringify({{ result, retries, restored: restoreLastStableState(), reads }}));
            '''
        )
        self.assertEqual(1, result["reads"])
        self.assertEqual("/library", result["result"]["previousStable"]["activePath"])
        self.assertEqual(900, result["result"]["previousStable"]["scrollByRoute"]["/library"])
        self.assertIsNone(result["result"]["previousStable"]["recommendation"]["channels"]["movie"]["candidate_counts"]["target_size"])
        self.assertEqual(37, result["result"]["previousStable"]["recommendation"]["channels"]["movie"]["candidate_counts"]["returned_size"])
        self.assertIsNone(result["result"]["previousStable"]["recommendation"]["channels"]["series"]["candidate_counts"]["target_size"])
        self.assertIsNone(result["result"]["previousStable"]["recommendation"]["channels"]["series"]["candidate_counts"]["returned_size"])
        self.assertEqual(result["result"]["previousStable"], result["retries"][0])
        self.assertEqual(result["result"]["previousStable"], result["restored"])
        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in ("pre-render-drop", "failed-render", "failed renderer draft", "999", "1200"):
            self.assertNotIn(forbidden, serialized)

    def test_failed_route_recovers_newer_live_body_captured_before_renderer(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            console.error = () => {{}};
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely, restoreLastStableState }} = await import("{module_url('js/core/recovery.js')}");
            const remembered = {{
              activePath: "/tonight/anime-series", activeParams: {{ channel: "anime-series" }},
              scrollByRoute: {{ "/tonight/anime-series": 100, "/remembered-only": 240 }},
              rail: {{ mode: "collapsed" }},
              recommendation: {{
                activeChannel: "anime-series",
                channels: {{
                  "anime-series": {{ sessionId: "session-old", batchIndex: 1, batchIds: ["batch-old"], candidate_counts: {{ target_size: 24, returned_size: 9 }} }},
                }},
              }},
              candidateTray: {{ context: {{ universeFocusId: "douban:old", expandedIds: ["douban:old-child"] }} }},
              library: {{ state: "all" }},
              sync: {{ profile: "old_user", options: {{ maxPages: 30, includeWish: true, includeDo: false }}, knownJobIds: ["job-old"] }},
            }};
            const live = structuredClone(remembered);
            live.scrollByRoute["/tonight/anime-series"] = 900;
            live.scrollByRoute["/live-only"] = 810;
            live.rail.mode = "hidden";
            live.recommendation.channels["anime-series"] = {{
              sessionId: "session-live", batchIndex: 2, batchIds: ["batch-old", "batch-live"],
              candidate_counts: {{ target_size: null, returned_size: 18 }},
            }};
            live.candidateTray.context = {{ universeFocusId: "douban:live", expandedIds: ["douban:live-child"] }};
            live.library.state = "wish";
            live.sync = {{
              profile: "live_user",
              options: {{ maxPages: 77, includeWish: false, includeDo: true, expectedCollect: 242, expectedWish: 34 }},
              knownJobIds: ["job-old", "job-live"],
            }};
            let reads = 0; const retries = [];
            rememberLastStableState(remembered);
            configureRecoveryBoundary({{
              root: appView,
              getCurrentPath: () => "/taste",
              getStableState: () => {{ reads += 1; return live; }},
              onRetry: (state) => retries.push(state),
            }});
            const rendered = await renderSafely({{ path: "/taste" }}, () => {{
              live.rail.mode = "expanded";
              live.recommendation.channels["anime-series"].batchIndex = 99;
              live.recommendation.channels["anime-series"].batchIds.push("batch-failed");
              live.candidateTray.context.universeFocusId = "douban:failed";
              live.library.state = "archived";
              live.sync.profile = "failed_user";
              live.scrollByRoute["/tonight/anime-series"] = 1200;
              throw new Error("failed next route");
            }});
            const button = appView.querySelector("button"); button.listeners.get("click")({{ preventDefault() {{}} }});
            const restored = restoreLastStableState();
            console.log(JSON.stringify({{ rendered, retries, restored, reads }}));
            '''
        )
        stable = result["rendered"]["previousStable"]
        anime = stable["recommendation"]["channels"]["anime-series"]
        self.assertEqual(1, result["reads"])
        self.assertEqual("hidden", stable["rail"]["mode"])
        self.assertEqual("session-live", anime["sessionId"])
        self.assertEqual(2, anime["batchIndex"])
        self.assertEqual(["batch-old", "batch-live"], anime["batchIds"])
        self.assertIsNone(anime["candidate_counts"]["target_size"])
        self.assertEqual(18, anime["candidate_counts"]["returned_size"])
        self.assertEqual("wish", stable["library"]["state"])
        self.assertEqual("douban:live", stable["candidateTray"]["context"]["universeFocusId"])
        self.assertEqual(["douban:live-child"], stable["candidateTray"]["context"]["expandedIds"])
        self.assertEqual("live_user", stable["sync"]["profile"])
        self.assertEqual(77, stable["sync"]["options"]["maxPages"])
        self.assertFalse(stable["sync"]["options"]["includeWish"])
        self.assertTrue(stable["sync"]["options"]["includeDo"])
        self.assertEqual(["job-old", "job-live"], stable["sync"]["knownJobIds"])
        self.assertEqual(900, stable["scrollByRoute"]["/tonight/anime-series"])
        self.assertEqual(240, stable["scrollByRoute"]["/remembered-only"])
        self.assertEqual(810, stable["scrollByRoute"]["/live-only"])
        self.assertEqual(stable, result["retries"][0])
        self.assertEqual(stable, result["restored"])
        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in ("batch-failed", "douban:failed", "failed_user", "99", "1200"):
            self.assertNotIn(forbidden, serialized)

    def test_recovery_canonicalizes_high_cardinality_scroll_with_live_routes_first(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            console.error = () => {{}};
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely, restoreLastStableState }} = await import("{module_url('js/core/recovery.js')}");
            const rememberedScroll = Object.fromEntries(Array.from({{ length: 100 }}, (_, index) => [`/remembered-${{String(index).padStart(3, "0")}}`, index]));
            const liveScroll = Object.fromEntries(Array.from({{ length: 100 }}, (_, index) => [`/live-${{String(index).padStart(3, "0")}}`, 1000 + index]));
            const stableState = {{
              activePath: "/library", activeParams: {{ filter: "wish" }}, scrollByRoute: rememberedScroll,
              rail: {{ mode: "collapsed" }}, recommendation: {{ activeChannel: "anime-series", channels: {{}} }},
              candidateTray: {{ context: {{ universeFocusId: "douban:42" }} }}, library: {{ state: "wish" }}, sync: {{}},
            }};
            const liveState = {{ ...structuredClone(stableState), scrollByRoute: liveScroll }};
            let reads = 0; let rendererStartedAfterCapture = false; const retries = [];
            rememberLastStableState(stableState);
            configureRecoveryBoundary({{
              root: appView,
              getCurrentPath: () => "/taste",
              getStableState: () => {{ reads += 1; rendererStartedAfterCapture = true; return liveState; }},
              onRetry: (state) => retries.push(state),
            }});
            const rendered = await renderSafely({{ path: "/taste" }}, () => {{
              if (!rendererStartedAfterCapture) throw new Error("renderer ran before live state capture");
              liveState.scrollByRoute["/live-099"] = 9999;
              throw new Error("failed");
            }});
            const button = appView.querySelector("button"); button.listeners.get("click")({{ preventDefault() {{}} }});
            const restored = restoreLastStableState();
            const canonical = rendered.previousStable;
            console.log(JSON.stringify({{
              canonical, retries, restored, reads,
              distinctClones: canonical !== retries[0]
                && canonical !== restored
                && retries[0] !== restored
                && canonical.scrollByRoute !== retries[0].scrollByRoute
                && canonical.scrollByRoute !== restored.scrollByRoute,
            }}));
            '''
        )
        canonical = result["canonical"]
        scroll = canonical["scrollByRoute"]
        self.assertEqual(1, result["reads"])
        self.assertEqual(100, len(scroll))
        self.assertEqual(1099, scroll["/live-099"])
        self.assertEqual({f"/live-{index:03d}" for index in range(100)}, set(scroll))
        self.assertEqual(canonical, result["retries"][0])
        self.assertEqual(canonical, result["restored"])
        self.assertTrue(result["distinctClones"])

    def test_failed_route_restores_runtime_persistence_router_and_retry_to_previous_stable(self):
        result = run_node_module(
            f'''
            {timed_recovery_dom()}
            console.error = () => {{}};
            const values = new Map();
            globalThis.localStorage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            const browserListeners = new Map(); const scrolls = [];
            Object.assign(window, {{
              location: {{ pathname: "/library" }}, scrollY: 345,
              history: {{
                state: null, scrollRestoration: "auto",
                pushState(state, _title, path) {{ this.state = state; window.location.pathname = path; }},
                replaceState(state, _title, path) {{ this.state = state; window.location.pathname = path; }},
              }},
              addEventListener(type, listener) {{ browserListeners.set(type, listener); }},
              removeEventListener(type, listener) {{ if (browserListeners.get(type) === listener) browserListeners.delete(type); }},
              dispatchEvent(event) {{ browserListeners.get(event.type)?.(event); }},
              requestAnimationFrame(callback) {{ callback(); }},
              scrollTo(options) {{ scrolls.push(options.top); this.scrollY = options.top; }},
            }});
            const {{ configureRecoveryBoundary }} = await import("{module_url('js/core/recovery.js')}");
            const {{ createEmptyUiState, createStore, persistUiState, restoreUiState, UI_STATE_KEY }} = await import("{module_url('js/core/store.js')}");
            const {{ createRouter }} = await import("{module_url('js/core/router.js')}");
            const {{ createAppRouteHandler, reduceUiState }} = await import("{module_url('js/app.js')}");
            const initial = createEmptyUiState(); initial.activePath = "/library"; initial.library.state = "wish"; initial.scrollByRoute["/library"] = 345;
            persistUiState(initial);
            const store = createStore(restoreUiState(), reduceUiState);
            const unsubscribe = store.subscribe((state) => persistUiState(state));
            const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
            const announcements = []; const retryPaths = []; let router; let retryPromise = Promise.resolve(null);
            configureRecoveryBoundary({{ root: appView, getCurrentPath: () => store.getState().activePath, onRetry(stable) {{ retryPaths.push(stable.activePath); retryPromise = router.navigate(stable.activePath); }} }});
            const handler = createAppRouteHandler({{
              appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate, prepare() {{}}, setNavigation() {{}}, setStatus() {{}},
              renderLibraryView(root) {{ const view = document.createElement("section"); const heading = document.createElement("h1"); heading.textContent = "Library"; view.append(heading); root.replaceChildren(view); return {{ dispose() {{}} }}; }},
              async renderTasteView(root) {{
                root.replaceChildren();
                store.dispatch({{ type: "candidateTray/nodeAdded", itemId: "douban:failed" }});
                store.dispatch({{ type: "commandLens/grounded", draft: "failed draft", chips: [{{ key: "failed", label: "failed", value: "failed" }}] }});
                store.dispatch({{ type: "recommendation/sessionReceived", session: {{ id: "failed-session", channels: {{}}, chips: [] }}, source: "create" }});
                await Promise.resolve();
                throw new Error("async fail");
              }},
              announceRoute(message) {{ announcements.push(message); }},
            }});
            router = createRouter([{{ pattern: "/library", name: "library" }}, {{ pattern: "/taste", name: "taste" }}], {{ onRoute: handler }});
            await router.start(); announcements.length = 0; appView.focusCalls.length = 0;
            const failedResult = await router.navigate("/taste", {{ raw: "https://evil.example", token: "must-drop" }});
            await flushMicrotasks();
            const currentRouteAfterFailure = router.currentRoute?.path;
            const browserPathAfterFailure = window.location.pathname;
            const browserStateAfterFailure = window.history.state;
            const recoveryAnnouncements = [...announcements];
            const focusAfterFailure = appView.focusCalls.length;
            const scrollYAfterFailure = window.scrollY;
            const scrollsAfterFailure = [...scrolls];
            const persistedAfterFailure = JSON.parse(values.get(UI_STATE_KEY));
            const refreshed = restoreUiState();
            const button = appView.querySelector("button"); button.listeners.get("click")({{ preventDefault() {{}} }});
            const afterRetry = await retryPromise;
            unsubscribe();
            console.log(JSON.stringify({{
              failedResult, currentRouteAfterFailure, browserPathAfterFailure, browserStateAfterFailure,
              runtimePath: store.getState().activePath, persistedPath: persistedAfterFailure.activePath, refreshedPath: refreshed.activePath,
              persistedLibrary: persistedAfterFailure.library.state, retryPaths, afterRetry: afterRetry?.path,
              runtimeCandidateIds: store.getState().candidateTray.itemIds,
              persistedCandidateIds: persistedAfterFailure.candidateTray.itemIds,
              runtimeDraft: store.getState().commandLens.draft,
              persistedDraft: persistedAfterFailure.commandLens.draft,
              runtimeSessionId: store.getState().recommendation.sessionId,
              persistedSessionId: persistedAfterFailure.recommendation.sessionId,
              recoveryAnnouncements, focusAfterFailure, scrollYAfterFailure, scrollsAfterFailure, announcements, scrolls, childCount: appView.children.length,
            }}));
            '''
        )
        self.assertIsNone(result["failedResult"])
        self.assertEqual("/library", result["currentRouteAfterFailure"])
        self.assertEqual("/library", result["browserPathAfterFailure"])
        self.assertEqual({}, result["browserStateAfterFailure"])
        self.assertEqual("/library", result["runtimePath"])
        self.assertEqual("/library", result["persistedPath"])
        self.assertEqual("/library", result["refreshedPath"])
        self.assertEqual("wish", result["persistedLibrary"])
        self.assertEqual([], result["runtimeCandidateIds"])
        self.assertEqual([], result["persistedCandidateIds"])
        self.assertEqual("", result["runtimeDraft"])
        self.assertEqual("", result["persistedDraft"])
        self.assertIsNone(result["runtimeSessionId"])
        self.assertIsNone(result["persistedSessionId"])
        self.assertEqual(["/library"], result["retryPaths"])
        self.assertEqual("/library", result["afterRetry"])
        self.assertGreater(result["childCount"], 0)
        self.assertEqual(1, len(result["recoveryAnnouncements"]))
        self.assertIn("恢复", result["recoveryAnnouncements"][0])
        self.assertEqual(0, result["focusAfterFailure"])
        self.assertEqual(345, result["scrollYAfterFailure"])
        self.assertEqual([345], result["scrollsAfterFailure"])

    def test_route_setup_failures_commit_recovery_before_main_can_blank(self):
        result = run_node_module(
            f'''
            {timed_recovery_dom()}
            console.error = () => {{}};
            const values = new Map();
            globalThis.localStorage = {{
              getItem(key) {{ return values.get(key) ?? null; }},
              setItem(key, value) {{ values.set(key, String(value)); }},
            }};
            Object.assign(window, {{
              location: {{ pathname: "/library" }},
              history: {{
                state: null,
                replaceState(state, _title, path) {{ this.state = state; window.location.pathname = path; historyPaths.push(path); }},
              }},
            }});
            const historyPaths = [];
            const {{ createEmptyUiState, createStore, persistUiState, restoreUiState, UI_STATE_KEY }} = await import("{module_url('js/core/store.js')}");
            const {{ createAppRouteHandler, reduceUiState }} = await import("{module_url('js/app.js')}");

            async function exercise(kind) {{
              values.clear(); historyPaths.length = 0; window.location.pathname = "/library";
              const initial = createEmptyUiState(); initial.activePath = "/library"; initial.scrollByRoute["/library"] = 345;
              persistUiState(initial);
              const store = createStore(restoreUiState(), reduceUiState);
              const actions = []; const originalDispatch = store.dispatch;
              store.dispatch = (action) => {{ actions.push(action.type); return originalDispatch(action); }};
              const unsubscribe = store.subscribe((state) => persistUiState(state));
              const stable = document.createElement("section"); const stableHeading = document.createElement("h1"); stableHeading.textContent = "Stable library"; stable.append(stableHeading); appView.replaceChildren(stable);
              const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
              let poisonDisposals = 0; let tasteRenders = 0;
              const handler = createAppRouteHandler({{
                appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate,
                prepare() {{
                  if (kind === "prepare") throw new Error("prepare failed");
                  if (kind === "clear-prepare") {{ appView.replaceChildren(); throw new Error("prepare cleared then failed"); }}
                }},
                setNavigation() {{}}, setStatus() {{}}, announceRoute() {{}},
                renderLibraryView(root) {{
                  const view = document.createElement("section"); const heading = document.createElement("h1"); heading.textContent = "Stable library"; view.append(heading); root.replaceChildren(view);
                  return {{ dispose() {{ poisonDisposals += 1; throw new Error("poison disposer"); }} }};
                }},
                renderTasteView(root) {{ const view = document.createElement("section"); const heading = document.createElement("h1"); heading.textContent = "Taste"; view.append(heading); root.replaceChildren(view); tasteRenders += 1; return {{ dispose() {{}} }}; }},
              }});
              if (kind === "dispose") await handler({{ name: "library", path: "/library", params: {{}} }});
              actions.length = 0; historyPaths.length = 0;
              const failed = await handler({{ name: "taste", path: "/taste", params: {{}} }});
              await flushMicrotasks();
              const afterFailure = {{
                failed, activePath: store.getState().activePath, persistedPath: JSON.parse(values.get(UI_STATE_KEY)).activePath,
                browserPath: window.location.pathname, childCount: appView.children.length,
                recovered: actions.includes("recovery/restored"), historyPaths: [...historyPaths], poisonDisposals,
              }};
              let retry = null;
              if (kind === "dispose") retry = await handler({{ name: "taste", path: "/taste", params: {{}} }});
              let cleanupError = null;
              unsubscribe();
              try {{ handler.dispose(); }} catch (error) {{ cleanupError = error.message; }}
              return {{ ...afterFailure, retry, tasteRenders, cleanupError }};
            }}

            const dispose = await exercise("dispose");
            const prepare = await exercise("prepare");
            const clearPrepare = await exercise("clear-prepare");
            console.log(JSON.stringify({{ dispose, prepare, clearPrepare }}));
            '''
        )
        for name in ("dispose", "prepare", "clearPrepare"):
            with self.subTest(name=name):
                row = result[name]
                self.assertFalse(row["failed"])
                self.assertTrue(row["recovered"])
                self.assertEqual("/library", row["activePath"])
                self.assertEqual("/library", row["persistedPath"])
                self.assertEqual("/library", row["browserPath"])
                self.assertIn("/library", row["historyPaths"])
                self.assertGreater(row["childCount"], 0)
                self.assertIsNone(row["cleanupError"])
        self.assertTrue(result["dispose"]["retry"])
        self.assertEqual(1, result["dispose"]["poisonDisposals"])
        self.assertEqual(1, result["dispose"]["tasteRenders"])

    def test_safe_routes_reject_embedded_external_url_text_in_store_recovery_scroll_and_diagnostics(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            const diagnostics = []; console.error = (...args) => diagnostics.push(args);
            const {{ normalizeUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ configureRecoveryBoundary, rememberLastStableState, renderSafely, restoreLastStableState }} = await import("{module_url('js/core/recovery.js')}");
            const evil = "/title/https://evil.example/x"; const protocolRelative = "/title//evil.example/x"; const safe = "/title/douban:123";
            const normalized = normalizeUiState({{ activePath: evil, scrollByRoute: {{ [evil]: 100, [protocolRelative]: 150, [safe]: 200 }} }});
            const safeNormalized = normalizeUiState({{ activePath: safe }});
            let currentPath = evil; configureRecoveryBoundary({{ root: appView, getCurrentPath: () => currentPath }});
            rememberLastStableState({{ activePath: evil, activeParams: {{ id: "douban:123" }}, scrollByRoute: {{ [evil]: 100, [safe]: 200 }}, rail: {{ mode: "expanded" }}, recommendation: {{ channels: {{}} }}, candidateTray: {{ context: {{}} }}, library: {{ state: "all" }}, sync: {{}} }});
            const invalidStable = restoreLastStableState();
            rememberLastStableState({{ activePath: safe, activeParams: {{ id: "douban:123" }}, scrollByRoute: {{ [safe]: 200 }}, rail: {{ mode: "expanded" }}, recommendation: {{ channels: {{}} }}, candidateTray: {{ context: {{}} }}, library: {{ state: "all" }}, sync: {{}} }});
            const safeStable = restoreLastStableState();
            await renderSafely({{ path: evil }}, () => {{ throw new Error("failed"); }});
            console.log(JSON.stringify({{ normalized, safeNormalized, invalidStable, safeStable, diagnostics }}));
            '''
        )
        self.assertIsNone(result["normalized"]["activePath"])
        self.assertNotIn("/title/https://evil.example/x", result["normalized"]["scrollByRoute"])
        self.assertNotIn("/title//evil.example/x", result["normalized"]["scrollByRoute"])
        self.assertEqual(200, result["normalized"]["scrollByRoute"]["/title/douban:123"])
        self.assertEqual("/title/douban:123", result["safeNormalized"]["activePath"])
        self.assertIsNone(result["invalidStable"])
        self.assertEqual("/title/douban:123", result["safeStable"]["activePath"])
        diagnostic_text = json.dumps(result["diagnostics"], ensure_ascii=False)
        self.assertNotIn("evil.example", diagnostic_text)
        self.assertNotIn("https://", diagnostic_text)
        self.assertIsNone(result["diagnostics"][0][1]["route"])

    def test_bootstrap_runs_migration_before_restore_store_and_router(self):
        source = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        bootstrap = source[source.index("export function bootstrapCineScopeShell") :]
        migration = bootstrap.index("migrateLegacyClientState(")
        restore = bootstrap.index("restoreUiState(")
        store = bootstrap.index("createStore(")
        router = bootstrap.index("createRouter(")
        self.assertLess(migration, restore)
        self.assertLess(migration, store)
        self.assertLess(migration, router)


if __name__ == "__main__":
    unittest.main()
