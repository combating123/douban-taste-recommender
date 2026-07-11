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

    def test_app_route_boundary_handles_sync_and_async_renderer_failures_without_double_announcement(self):
        result = run_node_module(
            f'''
            {fake_recovery_dom()}
            const {{ configureRecoveryBoundary, rememberLastStableState }} = await import("{module_url('js/core/recovery.js')}");
            const {{ createAppRouteHandler }} = await import("{module_url('js/app.js')}");
            const stableNode = document.createElement("section"); stableNode.textContent = "stable"; appView.replaceChildren(stableNode);
            const state = {{ activePath: "/library", activeParams: {{}}, recommendation: {{ channels: {{}} }}, scrollByRoute: {{}}, rail: {{ mode: "expanded" }}, library: {{ state: "all" }}, sync: {{}} }};
            const store = {{ getState() {{ return state; }}, dispatch(action) {{ if (action.type === "route/changed") {{ state.activePath = action.route.path; state.activeParams = action.route.params; }} }} }};
            const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
            const announcements = []; configureRecoveryBoundary({{ root: appView, getCurrentPath: () => state.activePath }}); rememberLastStableState(state);
            const syncHandler = createAppRouteHandler({{ appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate, prepare() {{}}, setNavigation() {{}}, renderLibraryView() {{ throw new Error("sync"); }}, announceRoute(message) {{ announcements.push(message); }} }});
            const syncResult = await syncHandler({{ name: "library", path: "/library", params: {{}} }});
            const asyncHandler = createAppRouteHandler({{ appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate, prepare() {{}}, setNavigation() {{}}, renderTasteView() {{ return Promise.reject(new Error("async")); }}, announceRoute(message) {{ announcements.push(message); }} }});
            const asyncResult = await asyncHandler({{ name: "taste", path: "/taste", params: {{}} }});
            console.log(JSON.stringify({{ syncResult, asyncResult, childCount: appView.children.length, announcements }}));
            '''
        )
        self.assertTrue(result["syncResult"])
        self.assertTrue(result["asyncResult"])
        self.assertGreater(result["childCount"], 0)
        self.assertEqual(2, len(result["announcements"]))

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
