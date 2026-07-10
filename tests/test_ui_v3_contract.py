import json
import re
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

            const calls = [];
            globalThis.location = {{ origin: "https://cinescope.test" }};
            globalThis.fetch = async (path, options) => {{
              calls.push({{ path, options }});
              return {{ ok: true, json: async () => ({{ ok: true }}) }};
            }};

            for (const unsafePath of [
              "https://attacker.test/api/v2/recommend",
              "//attacker.test/api/v2/recommend",
              "data:application/json,{{}}",
              "blob:https://cinescope.test/asset",
              "/api/v1/recommend",
              "/health",
            ]) {{
              let rejected = false;
              try {{ await postV2(unsafePath, {{ schema_version: 99 }}); }} catch (error) {{ rejected = error instanceof TypeError; }}
              if (!rejected) throw new Error(`unsafe path was accepted: ${{unsafePath}}`);
              if (calls.length !== 0) throw new Error(`fetch ran for unsafe path: ${{unsafePath}}`);
            }}

            await postV2("/api/v2/recommend", {{ schema_version: 99, intent: "mystery" }});
            await postV2("https://cinescope.test/api/v2/recommend?source=absolute", {{ schema_version: 77 }});
            if (calls.length !== 2) throw new Error("valid V2 requests were not sent");
            const [relativeCall, absoluteCall] = calls;
            const body = JSON.parse(relativeCall.options.body);
            const absoluteBody = JSON.parse(absoluteCall.options.body);
            if (body.schema_version !== 2 || absoluteBody.schema_version !== 2) throw new Error("caller replaced schema version");
            if (relativeCall.options.method !== "POST") throw new Error("request was not POST");
            if (absoluteCall.path !== "/api/v2/recommend?source=absolute") throw new Error("same-origin absolute URL was not normalised");
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

    def test_shell_transitions_only_animate_transform_or_opacity(self):
        css = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")
        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", css)

        self.assertTrue(declarations)
        for declaration in declarations:
            for transition in declaration.split(","):
                property_name = transition.strip().split(maxsplit=1)[0]
                with self.subTest(transition=transition):
                    self.assertIn(property_name, {"transform", "opacity"})

    def test_media_component_refuses_external_src(self):
        source = (UI_ROOT / "js" / "core" / "media.js").read_text(encoding="utf-8")
        source += (UI_ROOT / "js" / "components" / "media-frame.js").read_text(encoding="utf-8")

        self.assertIn("isLocalMediaUrl", source)
        self.assertIn("media-fallback", source)
        self.assertNotIn("onerror=", source)

    def test_card_css_enforces_stable_aspect_and_line_clamp(self):
        css = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")

        self.assertIn("aspect-ratio: 2 / 3", css)
        self.assertIn("-webkit-line-clamp: 2", css)

    def test_media_preload_refuses_unsafe_urls_and_only_inserts_a_decoded_image(self):
        output = run_node_module(
            f'''
            import {{ preloadLocalMedia }} from "{module_url('js/core/media.js')}";
            import {{ renderMediaFrame }} from "{module_url('js/components/media-frame.js')}";

            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase();
                this.children = [];
                this.dataset = {{}};
                this.attributes = new Map();
                this.className = "";
                this.textContent = "";
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}

            let domImageCreates = 0;
            globalThis.document = {{
              createElement(tagName) {{
                if (tagName.toLowerCase() === "img") domImageCreates += 1;
                return new FakeElement(tagName);
              }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            let imageMode = "success";
            const createdImages = [];
            globalThis.Image = class FakeImage {{
              constructor() {{
                this.tagName = "IMG";
                this.naturalWidth = 640;
                createdImages.push(this);
              }}
              set src(value) {{
                this._src = value;
                queueMicrotask(() => {{
                  if (imageMode === "load-failure") this.onerror?.(new Error("load failed"));
                  else this.onload?.();
                }});
              }}
              get src() {{ return this._src; }}
              decode() {{
                return imageMode === "decode-failure"
                  ? Promise.reject(new Error("decode failed"))
                  : Promise.resolve();
              }}
            }};

            const settle = async () => {{
              await Promise.resolve();
              await Promise.resolve();
              await Promise.resolve();
              await Promise.resolve();
            }};

            for (const unsafeUrl of [
              "https://remote.test/media/poster.webp",
              "//remote.test/media/poster.webp",
              "data:image/png;base64,AA==",
              "blob:https://cinescope.test/media/poster.webp",
              "/media.evil/poster.webp",
            ]) {{
              if (await preloadLocalMedia(unsafeUrl) !== null) throw new Error("unsafe media was accepted");
              const frame = renderMediaFrame({{
                localUrl: unsafeUrl,
                kind: "poster",
                title: "External",
                status: "ready",
              }});
              await settle();
              if (!frame.firstElementChild?.className.includes("media-fallback")) {{
                throw new Error("external media replaced the fallback");
              }}
            }}
            if (createdImages.length !== 0 || domImageCreates !== 0) {{
              throw new Error("unsafe URL created an image element");
            }}

            imageMode = "decode-failure";
            const failedFrame = renderMediaFrame({{
              localUrl: "/media/failing-poster.webp",
              kind: "poster",
              title: "Decode Failure",
              status: "ready",
            }});
            await settle();
            if (!failedFrame.firstElementChild?.className.includes("media-fallback")) {{
              throw new Error("decode failure removed the fallback");
            }}

            imageMode = "success";
            const imageIndex = createdImages.length;
            const readyFrame = renderMediaFrame({{
              localUrl: "/media/ready-poster.webp",
              kind: "poster",
              title: "Ready Poster",
              status: "ready",
            }});
            await settle();
            const decodedImage = createdImages[imageIndex];
            if (readyFrame.firstElementChild !== decodedImage) {{
              throw new Error("rendered image was not the decoded preload element");
            }}
            if (decodedImage.alt !== "Ready Poster 海报") {{
              throw new Error("decoded image alt text was not assigned");
            }}
            console.log(JSON.stringify({{ images: createdImages.length, domImageCreates }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["images"])
        self.assertEqual(0, result["domImageCreates"])

    def test_media_adapters_normalize_recommendation_catalog_and_person_payloads(self):
        output = run_node_module(
            f'''
            import {{
              adaptCatalogMedia,
              adaptPersonMedia,
              adaptRecommendationMedia,
            }} from "{module_url('js/core/media.js')}";

            globalThis.location = {{ origin: "https://cinescope.test" }};

            const recommendation = adaptRecommendationMedia({{
              title: "Cipher Line",
              source: "recommendation-cache",
              poster: {{ localUrl: "/media/recommendation.webp", status: "ready" }},
            }});
            const catalogPoster = adaptCatalogMedia({{
              title: "Archive 81",
              source: "catalog-cache",
              media: {{
                poster: {{ localUrl: "/media/catalog-poster.webp", status: "ready" }},
                backdrop: {{ localUrl: "/media/catalog-backdrop.webp", status: "ready" }},
              }},
            }}, "poster");
            const catalogBackdrop = adaptCatalogMedia({{
              title: "Archive 81",
              source: "catalog-cache",
              media: {{
                poster: {{ localUrl: "/media/catalog-poster.webp", status: "ready" }},
                backdrop: {{ localUrl: "/media/catalog-backdrop.webp", status: "ready" }},
              }},
            }}, "backdrop");
            const person = adaptPersonMedia({{
              name: "Jane Doe",
              source: "people-cache",
              portrait: {{ localUrl: "/media/person.webp", status: "ready" }},
            }});
            const blocked = adaptRecommendationMedia({{
              title: "Untrusted",
              poster: {{ localUrl: "https://remote.test/media/poster.webp", status: "ready" }},
            }});

            for (const [asset, expectedKind, expectedTitle, expectedUrl, expectedSource] of [
              [recommendation, "poster", "Cipher Line", "/media/recommendation.webp", "recommendation-cache"],
              [catalogPoster, "poster", "Archive 81", "/media/catalog-poster.webp", "catalog-cache"],
              [catalogBackdrop, "backdrop", "Archive 81", "/media/catalog-backdrop.webp", "catalog-cache"],
              [person, "portrait", "Jane Doe", "/media/person.webp", "people-cache"],
            ]) {{
              if (asset.kind !== expectedKind || asset.title !== expectedTitle || asset.localUrl !== expectedUrl) {{
                throw new Error("media adapter did not preserve its normalized shape");
              }}
              if (asset.status !== "ready" || asset.source !== expectedSource) {{
                throw new Error("media adapter lost status or source");
              }}
            }}
            if (blocked.localUrl !== null || blocked.status !== "unavailable") {{
              throw new Error("adapter passed through an external image URL");
            }}
            console.log(JSON.stringify({{ recommendation, catalogPoster, catalogBackdrop, person }}));
            '''
        )
        normalized = json.loads(output)
        self.assertEqual("portrait", normalized["person"]["kind"])
        self.assertEqual("/media/catalog-backdrop.webp", normalized["catalogBackdrop"]["localUrl"])

    def test_title_cards_and_shelves_use_text_content_for_untrusted_copy(self):
        sources = (
            (UI_ROOT / "js" / "components" / "title-card.js").read_text(encoding="utf-8")
            + (UI_ROOT / "js" / "components" / "shelf.js").read_text(encoding="utf-8")
        )
        self.assertNotIn("innerHTML", sources)

        output = run_node_module(
            f'''
            import {{ renderTitleCard }} from "{module_url('js/components/title-card.js')}";
            import {{ renderShelf }} from "{module_url('js/components/shelf.js')}";

            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase();
                this.children = [];
                this.dataset = {{}};
                this.className = "";
                this.textContent = "";
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute() {{}}
              addEventListener() {{}}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            Object.defineProperty(FakeElement.prototype, "innerHTML", {{
              set() {{ throw new Error("innerHTML must not be used"); }},
            }});
            let imageCreates = 0;
            globalThis.document = {{
              createElement(tagName) {{
                if (tagName.toLowerCase() === "img") imageCreates += 1;
                return new FakeElement(tagName);
              }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            const unsafe = "<img src=x onerror=alert(1)>";
            const card = renderTitleCard({{
              title: unsafe,
              reason: unsafe,
              metadata: [unsafe],
              poster: {{ localUrl: "https://remote.test/poster.webp", status: "ready" }},
            }});
            const shelf = renderShelf({{
              title: unsafe,
              items: [{{ title: unsafe, reason: unsafe }}],
              batchState: {{ label: unsafe }},
            }});
            const collectText = (element) => [
              element.textContent,
              ...element.children.flatMap((child) => collectText(child)),
            ];
            if (!collectText(card).includes(unsafe) || !collectText(shelf).includes(unsafe)) {{
              throw new Error("untrusted copy was not retained as text");
            }}
            if (imageCreates !== 0) throw new Error("text rendering created an image element");
            console.log(JSON.stringify({{
              cardHasUnsafeText: collectText(card).includes(unsafe),
              shelfHasUnsafeText: collectText(shelf).includes(unsafe),
            }}));
            '''
        )
        rendered = json.loads(output)
        self.assertTrue(rendered["cardHasUnsafeText"])
        self.assertTrue(rendered["shelfHasUnsafeText"])

    def test_component_styles_and_motion_load_after_shell_with_reduced_motion_budget(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        components_css = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")
        motion_css = (UI_ROOT / "styles" / "motion.css").read_text(encoding="utf-8")

        shell_index = html.index("/assets/v3/styles/shell.css")
        components_index = html.index("/assets/v3/styles/components.css")
        motion_index = html.index("/assets/v3/styles/motion.css")
        self.assertLess(shell_index, components_index)
        self.assertLess(components_index, motion_index)
        self.assertIn("--motion-fast: 180ms", motion_css)
        self.assertIn("--motion-standard: 280ms", motion_css)
        self.assertIn("--motion-immersive: 440ms", motion_css)
        self.assertIn("prefers-reduced-motion", motion_css)
        self.assertIn("--motion-fast: 1ms", motion_css)
        self.assertIn("transform: none", motion_css)

        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", components_css + motion_css)
        for declaration in declarations:
            for transition in declaration.split(","):
                property_name = transition.strip().split(maxsplit=1)[0]
                with self.subTest(transition=transition):
                    self.assertIn(property_name, {"transform", "opacity"})

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
