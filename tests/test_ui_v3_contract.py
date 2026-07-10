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
        encoding="utf-8",
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

    def test_media_adapters_normalize_v2_backend_payloads_and_legacy_poster_objects(self):
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
              cover: "/media/recommendation.webp",
              media_status: {{ poster: "ready" }},
            }});
            const catalogPoster = adaptCatalogMedia({{
              title: "Archive 81",
              source: "catalog-cache",
              poster: {{ url: "/media/catalog-poster.webp", media_status: "ready" }},
              backdrop: {{ url: "/media/catalog-backdrop.webp", media_status: "ready" }},
            }}, "poster");
            const catalogBackdrop = adaptCatalogMedia({{
              title: "Archive 81",
              source: "catalog-cache",
              poster: {{ url: "/media/catalog-poster.webp", media_status: "ready" }},
              backdrop: {{ url: "/media/catalog-backdrop.webp", media_status: "ready" }},
            }}, "backdrop");
            const person = adaptPersonMedia({{
              name: "Jane Doe",
              source: "people-cache",
              portrait: {{ url: "/media/person.webp", media_status: "ready" }},
            }});
            const topLevelStatus = adaptCatalogMedia({{
              title: "Mapped Status",
              poster: {{ url: "/media/mapped-poster.webp" }},
              media_status: {{ poster: "ready" }},
            }}, "poster");
            const legacyPoster = adaptRecommendationMedia({{
              title: "Legacy",
              poster: {{ localUrl: "/media/legacy-poster.webp", status: "ready" }},
            }});

            for (const [asset, expectedKind, expectedTitle, expectedUrl, expectedSource] of [
              [recommendation, "poster", "Cipher Line", "/media/recommendation.webp", "recommendation-cache"],
              [catalogPoster, "poster", "Archive 81", "/media/catalog-poster.webp", "catalog-cache"],
              [catalogBackdrop, "backdrop", "Archive 81", "/media/catalog-backdrop.webp", "catalog-cache"],
              [person, "portrait", "Jane Doe", "/media/person.webp", "people-cache"],
              [topLevelStatus, "poster", "Mapped Status", "/media/mapped-poster.webp", "local"],
              [legacyPoster, "poster", "Legacy", "/media/legacy-poster.webp", "local"],
            ]) {{
              if (asset.kind !== expectedKind || asset.title !== expectedTitle || asset.localUrl !== expectedUrl) {{
                throw new Error("media adapter did not preserve its normalized shape");
              }}
              if (asset.status !== "ready" || asset.source !== expectedSource) {{
                throw new Error("media adapter lost status or source");
              }}
            }}
            console.log(JSON.stringify({{ recommendation, catalogPoster, catalogBackdrop, person, topLevelStatus, legacyPoster }}));
            '''
        )
        normalized = json.loads(output)
        self.assertEqual("portrait", normalized["person"]["kind"])
        self.assertEqual("/media/catalog-backdrop.webp", normalized["catalogBackdrop"]["localUrl"])

    def test_media_frame_fails_closed_for_v2_nonready_and_external_assets(self):
        output = run_node_module(
            f'''
            import {{ normalizeMediaAsset }} from "{module_url('js/core/media.js')}";
            import {{ renderMediaFrame }} from "{module_url('js/components/media-frame.js')}";

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
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}

            globalThis.document = {{ createElement: (tagName) => new FakeElement(tagName) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const createdImages = [];
            globalThis.Image = class FakeImage {{
              constructor() {{ this.naturalWidth = 640; createdImages.push(this); }}
              set src(value) {{ this._src = value; queueMicrotask(() => this.onload?.()); }}
              decode() {{ return Promise.resolve(); }}
            }};
            const settle = async () => {{
              await Promise.resolve();
              await Promise.resolve();
              await Promise.resolve();
            }};

            const expectedStates = new Map([
              ["designed-fallback", "missing"],
              ["missing", "missing"],
              ["degraded", "unverified"],
              ["ambiguous", "unverified"],
              ["queued", "pending"],
              ["resolving", "pending"],
              ["downloading", "pending"],
              ["validating", "pending"],
              ["failed", "unavailable"],
              ["unknown-state", "unverified"],
              [undefined, "unverified"],
            ]);
            for (const [inputStatus, expectedStatus] of expectedStates) {{
              const asset = normalizeMediaAsset({{
                localUrl: "/media/" + (inputStatus || "absent") + ".webp",
                kind: "poster",
                title: "Fallback",
                status: inputStatus,
              }});
              if (asset.status !== expectedStatus) {{
                throw new Error("normalized status mismatch: " + inputStatus + ":" + asset.status);
              }}
              const frame = renderMediaFrame(asset);
              await settle();
              if (!frame.firstElementChild?.className.includes("media-fallback")) {{
                throw new Error("non-ready asset replaced its fallback: " + inputStatus);
              }}
              if (!frame.firstElementChild.children[2]?.textContent) {{
                throw new Error("fallback has no static status label: " + inputStatus);
              }}
            }}
            if (createdImages.length !== 0) throw new Error("non-ready local assets created Image instances");

            const external = renderMediaFrame({{
              localUrl: "https://remote.test/media/external.webp",
              kind: "poster",
              title: "External",
              status: "ready",
            }});
            await settle();
            if (!external.firstElementChild?.className.includes("media-fallback") || createdImages.length !== 0) {{
              throw new Error("external asset created an image");
            }}
            console.log(JSON.stringify({{ imageCreates: createdImages.length }}));
            '''
        )
        self.assertEqual(0, json.loads(output)["imageCreates"])

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

    def test_tonight_renders_distinct_counts_three_shelves_and_batch_requests(self):
        output = run_node_module(
            f'''
            import {{
              configureTonight,
              renderTonight,
              requestNextBatch,
              restorePreviousBatch,
            }} from "{module_url('js/features/tonight.js')}";

            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase();
                this.children = [];
                this.dataset = {{}};
                this.attributes = new Map();
                this.className = "";
                this.textContent = "";
                this.disabled = false;
                this.value = "";
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              remove() {{ this.parentNode?.children.splice(this.parentNode.children.indexOf(this), 1); }}
              focus() {{}}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            Object.defineProperty(FakeElement.prototype, "innerHTML", {{
              set() {{ throw new Error("innerHTML must not be used"); }},
            }});

            globalThis.document = {{ createElement: (tagName) => new FakeElement(tagName) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            const root = new FakeElement("main");
            const calls = [];
            const actions = [];
            const state = {{
              recommendation: {{
                sessionId: "session-42",
                activeChannel: "movie",
                channels: {{
                  movie: {{
                    pool_size: 30,
                    matched_size: 17,
                    visible_size: 12,
                    active_batch: 2,
                    batch: {{ index: 2, visible_size: 12, items: Array.from({{ length: 12 }}, (_, index) => ({{ title: `电影${{index}}` }})) }},
                  }},
                  series: {{
                    pool_size: 24,
                    matched_size: 11,
                    visible_size: 8,
                    active_batch: 3,
                    batch: {{ index: 3, visible_size: 8, items: Array.from({{ length: 8 }}, (_, index) => ({{ title: `剧集${{index}}` }})) }},
                  }},
                  "anime-series": {{
                    pool_size: 19,
                    matched_size: 10,
                    visible_size: 7,
                    active_batch: 4,
                    batch: {{ index: 4, visible_size: 7, items: Array.from({{ length: 7 }}, (_, index) => ({{ title: `动画${{index}}` }})) }},
                  }},
                }},
              }},
            }};
            const store = {{
              getState: () => state,
              dispatch(action) {{ actions.push(action); }},
            }};
            const api = {{
              async postV2(path, payload) {{
                calls.push({{ path, payload }});
                return {{ session_id: "session-42", channel: payload.channel, batch: {{ id: `batch-${{calls.length}}`, index: calls.length + 4, items: [], pool_size: 30, matched_size: 17, visible_size: 0 }} }};
              }},
            }};
            configureTonight({{ store, api, root }});
            const page = renderTonight(state);

            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const all = collect(page);
            const text = all.map((node) => node.textContent).filter(Boolean);
            const shelfRails = all.filter((node) => node.className === "title-shelf__rail");
            if (!text.includes("候选池 30") || !text.includes("匹配 17") || !text.includes("本批可见 12")) {{
              throw new Error(`three count semantics were not rendered: ${{text}}`);
            }}
            if (shelfRails.length !== 3) throw new Error(`expected three shelves, got ${{shelfRails.length}}`);
            if (shelfRails.some((rail) => rail.children.length > 9)) throw new Error("initial shelf exceeded the nine-card cap");

            await requestNextBatch("series", "太相似");
            await restorePreviousBatch("anime-series");
            if (calls[0].path !== "/api/v2/recommend/sessions/session-42/batch") throw new Error("next batch path mismatch");
            if (calls[0].payload.channel !== "电视剧" || calls[0].payload.reason !== "太相似") throw new Error("reasoned series shuffle was not grounded");
            if (calls[1].path !== "/api/v2/recommend/sessions/session-42/previous" || calls[1].payload.channel !== "动漫") throw new Error("anime previous batch path mismatch");
            if (actions.map((action) => action.channel).join(",") !== "series,anime-series") throw new Error("channel-specific batch actions were not dispatched");
            console.log(JSON.stringify({{ text, shelfSizes: shelfRails.map((rail) => rail.children.length), calls, actions }}));
            '''
        )
        rendered = json.loads(output)
        self.assertEqual([9, 8, 7], rendered["shelfSizes"])
        self.assertEqual("太相似", rendered["calls"][0]["payload"]["reason"])

    def test_command_lens_uses_only_server_chips_and_ctrl_k(self):
        output = run_node_module(
            f'''
            import {{
              configureCommandLens,
              openCommandLens,
              submitIntent,
            }} from "{module_url('js/features/command-lens.js')}";

            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase();
                this.children = [];
                this.dataset = {{}};
                this.attributes = new Map();
                this.className = "";
                this.textContent = "";
                this.value = "";
                this.hidden = false;
                this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              remove() {{ this.parentNode?.children.splice(this.parentNode.children.indexOf(this), 1); }}
              focus() {{ this.focused = true; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            Object.defineProperty(FakeElement.prototype, "innerHTML", {{
              set() {{ throw new Error("innerHTML must not be used"); }},
            }});

            const listeners = new Map();
            const root = new FakeElement("div");
            globalThis.document = {{
              createElement: (tagName) => new FakeElement(tagName),
              addEventListener(type, listener) {{ listeners.set(type, listener); }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            const calls = [];
            const actions = [];
            const serverResponse = {{
              id: "session-grounded",
              intent: {{ genres: ["悬疑"], free_text: "<img src=x onerror=alert(1)>" }},
              chips: [{{ key: "genre", label: "服务端悬疑", value: "悬疑", removable: true }}],
              channels: {{}},
            }};
            const replacementResponse = {{
              id: "session-replacement",
              intent: {{ genres: [], free_text: "" }},
              chips: [],
              channels: {{}},
            }};
            configureCommandLens({{
              root,
              store: {{
                getState: () => ({{ commandLens: {{ draft: "", chips: [] }} }}),
                dispatch(action) {{ actions.push(action); }},
              }},
              api: {{ async postV2(path, payload) {{ calls.push({{ path, payload }}); return calls.length === 1 ? serverResponse : replacementResponse; }} }},
            }});

            let prevented = false;
            listeners.get("keydown")({{ key: "K", ctrlKey: true, metaKey: false, preventDefault() {{ prevented = true; }} }});
            if (!prevented || root.children.length !== 1) throw new Error("Ctrl+K did not open the command lens");
            openCommandLens("今晚想看悬疑片");
            await submitIntent("今晚想看悬疑片");

            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const all = collect(root);
            const text = all.map((node) => node.textContent).filter(Boolean);
            if (!text.includes("服务端悬疑")) throw new Error("server chip was not rendered");
            if (text.includes(serverResponse.intent.free_text)) throw new Error("free-form model text was parsed into visible chips");
            if (!all.some((node) => node.className.includes("intent-chip"))) throw new Error("editable intent chip was not rendered");
            if (calls[0].path !== "/api/v2/recommend/sessions" || calls[0].payload.intent_text !== "今晚想看悬疑片") throw new Error("intent submission path mismatch");
            if (!actions.some((action) => action.type === "recommendation/sessionReceived" && action.session.id === "session-grounded")) throw new Error("grounded session was not dispatched");
            const remove = all.find((node) => node.className === "intent-chip__remove");
            await remove.onclick();
            if (calls[1].payload.intent_text !== undefined || calls[1].payload.intent.genres.length !== 0) {{
              throw new Error("chip removal did not rebuild from the server structured intent");
            }}
            console.log(JSON.stringify({{ text, calls, actions, prevented }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["prevented"])
        self.assertEqual("今晚想看悬疑片", result["calls"][0]["payload"]["intent_text"])
        self.assertEqual([], result["calls"][1]["payload"]["intent"]["genres"])

    def test_tonight_stylesheet_is_static_and_motion_safe(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "tonight.css").read_text(encoding="utf-8")

        self.assertIn('<link rel="stylesheet" href="/assets/v3/styles/tonight.css" />', html)
        self.assertIn("prefers-reduced-motion", css)
        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", css)
        for declaration in declarations:
            for transition in declaration.split(","):
                property_name = transition.strip().split(maxsplit=1)[0]
                with self.subTest(transition=transition):
                    self.assertIn(property_name, {"transform", "opacity"})

        app_source = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("createElement(\"link\")", app_source)
        self.assertNotIn("createElement('link')", app_source)


if __name__ == "__main__":
    unittest.main()
