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
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            "Node module test failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


class UiV3ContractTests(unittest.TestCase):
    def test_router_declares_deep_link_patterns(self):
        source = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        source += (UI_ROOT / "js" / "core" / "router.js").read_text(encoding="utf-8")

        for route in ("/title/:id", "/person/:id", "/tonight/anime-series"):
            with self.subTest(route=route):
                self.assertIn(route, source)

    def test_store_declares_schema_without_cookie_names(self):
        source = (UI_ROOT / "js" / "core" / "store.js").read_text(encoding="utf-8")

        self.assertIn("schemaVersion: 3", source)
        self.assertNotIn("doubanCookie", source)
        self.assertNotIn("COOKIE_SESSION_KEY", source)

    def test_store_allowlists_ui_state_and_filters_sensitive_values(self):
        output = run_node_module(
            f'''
            import {{ persistUiState, restoreUiState, UI_STATE_KEY }} from "{module_url('js/core/store.js')}";

            const values = new Map();
            globalThis.localStorage = {{
              getItem(key) {{ return values.has(key) ? values.get(key) : null; }},
              setItem(key, value) {{ values.set(key, String(value)); }},
            }};

            const persisted = persistUiState({{
              activePath: "/title/douban%3A1295644",
              activeParams: {{ id: "douban:1295644" }},
              recommendation: {{
                sessionId: "session-42",
                activeChannel: "series",
                channels: {{
                  movie: {{ batchIndex: 1, batchIds: ["movie-1"] }},
                  series: {{ batchIndex: 2, batchIds: ["series-1", "https://images.example/poster.jpg"] }},
                  "anime-series": {{ batchIndex: 3, batchIds: ["anime-1"] }},
                }},
              }},
              scrollByRoute: {{ "/title/douban%3A1295644": 480 }},
              candidateTray: {{
                itemIds: ["title-1"],
                context: {{ reason: "watch later", externalImage: "https://images.example/poster.jpg" }},
              }},
              commandLens: {{
                draft: "90 minute mystery",
                chips: [{{ key: "duration", label: "90 minutes", value: "90", removable: true }}],
              }},
              rail: {{ mode: "hidden" }},
              doubanCookie: "must-not-persist",
              apiKey: "must-not-persist",
              headers: {{ Authorization: "must-not-persist" }},
              arbitraryRootValue: "must-not-persist",
            }});

            const raw = values.get(UI_STATE_KEY);
            const restored = restoreUiState();
            if (persisted.schemaVersion !== 3 || restored.schemaVersion !== 3) throw new Error("schema version was not persisted");
            if (restored.activePath !== "/title/douban%3A1295644") throw new Error("active route was not restored");
            if (restored.recommendation.channels.series.batchIndex !== 2) throw new Error("channel batch state was not restored");
            if (restored.scrollByRoute["/title/douban%3A1295644"] !== 480) throw new Error("scroll state was not restored");
            if (restored.commandLens.chips.length !== 1 || restored.rail.mode !== "hidden") throw new Error("allowed UI state was not restored");
            for (const forbidden of ["must-not-persist", "https://images.example/poster.jpg", "arbitraryRootValue"]) {{
              if (raw.includes(forbidden)) throw new Error(`sensitive value persisted: ${{forbidden}}`);
            }}

            const unsafePathState = persistUiState({{
              activePath: "//images.example/poster.jpg",
              scrollByRoute: {{ "//images.example/poster.jpg": 90 }},
            }});
            const unsafePathRaw = values.get(UI_STATE_KEY);
            if (unsafePathState.activePath !== null || unsafePathRaw.includes("//images.example/poster.jpg")) {{
              throw new Error("protocol-relative external URL persisted");
            }}

            values.set(UI_STATE_KEY, JSON.stringify({{ schemaVersion: 2, activePath: "/sync" }}));
            if (restoreUiState().activePath !== null) throw new Error("incompatible schema was restored");
            console.log(JSON.stringify(restored));
            '''
        )
        restored = json.loads(output)
        self.assertEqual("session-42", restored["recommendation"]["sessionId"])
        self.assertEqual(["title-1"], restored["candidateTray"]["itemIds"])

    def test_post_v2_forces_schema_and_maps_channels(self):
        output = run_node_module(
            f'''
            import {{ backendChannel, postV2 }} from "{module_url('js/core/api.js')}";

            let captured;
            globalThis.fetch = async (path, options) => {{
              captured = {{ path, options }};
              return {{ ok: true, json: async () => ({{ ok: true }}) }};
            }};

            await postV2("/api/v2/recommend", {{ schema_version: 99, intent: "mystery" }});
            const body = JSON.parse(captured.options.body);
            if (body.schema_version !== 2) throw new Error("caller replaced schema version");
            if (captured.options.method !== "POST") throw new Error("request was not POST");
            if (backendChannel("movie") !== "电影") throw new Error("movie channel mismatch");
            if (backendChannel("series") !== "电视剧") throw new Error("series channel mismatch");
            if (backendChannel("anime-series") !== "动漫") throw new Error("anime channel mismatch");
            let unsupported = false;
            try {{ backendChannel("unknown"); }} catch (error) {{ unsupported = error instanceof TypeError; }}
            if (!unsupported) throw new Error("unsupported channel was accepted");
            console.log(JSON.stringify(body));
            '''
        )
        self.assertEqual(2, json.loads(output)["schema_version"])

    def test_router_matches_params_and_restores_scroll_after_render(self):
        output = run_node_module(
            f'''
            import {{ createRouter }} from "{module_url('js/core/router.js')}";
            import {{ restoreUiState }} from "{module_url('js/core/store.js')}";

            const values = new Map();
            const listeners = new Map();
            const events = [];
            const browser = {{
              location: {{ pathname: "/title/douban%3A1295644" }},
              scrollY: 120,
              history: {{
                state: null,
                scrollRestoration: "auto",
                pushState(state, _title, path) {{
                  this.state = state;
                  browser.location.pathname = path;
                }},
              }},
              localStorage: {{
                getItem(key) {{ return values.has(key) ? values.get(key) : null; }},
                setItem(key, value) {{ values.set(key, String(value)); }},
              }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }},
              removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }},
              requestAnimationFrame(callback) {{ events.push("frame"); callback(); return 1; }},
              scrollTo(options) {{ events.push(`scroll:${{options.top}}`); }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser;
            globalThis.history = browser.history;
            globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser);
            globalThis.PopStateEvent = browser.PopStateEvent;

            const router = createRouter([
              {{ pattern: "/tonight" , name: "tonight" }},
              {{ pattern: "/tonight/:channel", name: "tonight-channel" }},
              {{ pattern: "/title/:id", name: "title" }},
              {{ pattern: "/person/:id", name: "person" }},
            ], {{
              onRoute: async (route) => {{ events.push(`render:${{route.name}}:${{route.params.id ?? route.params.channel ?? ""}}`); }},
            }});

            const matched = router.match("/tonight/anime-series");
            if (!matched || matched.name !== "tonight-channel" || matched.params.channel !== "anime-series") throw new Error("channel route did not match");
            await router.start();
            browser.scrollY = 480;
            const eventStart = events.length;
            await router.navigate("/person/person-7", {{ source: "test" }});
            const navigationEvents = events.slice(eventStart);
            const renderIndex = navigationEvents.indexOf("render:person:person-7");
            const frameIndex = navigationEvents.indexOf("frame");
            const scrollIndex = navigationEvents.indexOf("scroll:0");
            if (renderIndex < 0 || frameIndex !== renderIndex + 1 || scrollIndex !== frameIndex + 1) throw new Error(`scroll was not restored after render: ${{navigationEvents}}`);
            if (restoreUiState().scrollByRoute["/title/douban%3A1295644"] !== 480) throw new Error("outgoing scroll was not saved");
            if (router.currentRoute.name !== "person" || router.currentRoute.params.id !== "person-7") throw new Error("person route was not active");
            if (browser.history.scrollRestoration !== "manual") throw new Error("browser scroll restoration remained automatic");
            console.log(JSON.stringify({{ events, active: router.currentRoute }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("person", result["active"]["name"])
        self.assertIn("render:person:person-7", result["events"])


if __name__ == "__main__":
    unittest.main()
