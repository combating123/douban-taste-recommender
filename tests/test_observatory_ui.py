import json
import re
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "douban_recommender" / "ui"


def module_url(relative_path: str) -> str:
    return (UI_ROOT / relative_path).resolve().as_uri()


def run_node_module(script: str) -> str:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
        timeout=30,
    )
    if result.returncode:
        raise AssertionError(
            "Node module test failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


def fake_dom_module_prelude() -> str:
    return textwrap.dedent(
        r'''
        class FakeClassList {
          constructor(owner) { this.owner = owner; this.values = new Set(); }
          add(...names) { names.filter(Boolean).forEach((name) => this.values.add(name)); this.sync(); }
          remove(...names) { names.forEach((name) => this.values.delete(name)); this.sync(); }
          toggle(name, force) {
            const enabled = force === undefined ? !this.values.has(name) : Boolean(force);
            if (enabled) this.values.add(name); else this.values.delete(name);
            this.sync(); return enabled;
          }
          contains(name) { return this.values.has(name); }
          sync() { this.owner._className = [...this.values].join(" "); }
          replace(value) { this.values = new Set(String(value || "").split(/\s+/).filter(Boolean)); this.sync(); }
        }
        class FakeElement {
          constructor(tagName) {
            this.tagName = String(tagName).toUpperCase(); this.children = []; this.parentNode = null;
            this.attributes = new Map(); this.dataset = {}; this.style = { height: "", setProperty(name, value) { this[name] = String(value); } };
            this.listeners = new Map(); this._className = ""; this.classList = new FakeClassList(this); this._textContent = "";
            this.value = ""; this.checked = false; this.disabled = false; this.hidden = false; this.type = "";
            this.clientWidth = 1000; this.clientHeight = 520; this.scrollTop = 0; this.scrollLeft = 0;
          }
          set className(value) { this.classList.replace(value); } get className() { return this._className; }
          set textContent(value) { this._textContent = String(value ?? ""); this.children = []; }
          get textContent() { return this._textContent + this.children.map((child) => child.textContent || "").join(""); }
          append(...nodes) { nodes.forEach((node) => this.appendChild(node)); }
          appendChild(node) { if (node == null) return node; this.children.push(node); node.parentNode = this; return node; }
          replaceChildren(...nodes) { this.children.forEach((node) => { node.parentNode = null; }); this.children = []; this._textContent = ""; this.append(...nodes); }
          setAttribute(name, value) {
            const text = String(value); this.attributes.set(name, text);
            if (name === "class") this.className = text;
            if (name.startsWith("data-")) this.dataset[name.slice(5).replace(/-([a-z])/g, (_m, c) => c.toUpperCase())] = text;
          }
          getAttribute(name) { return this.attributes.get(name) ?? null; }
          addEventListener(type, listener) { if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }
          removeEventListener(type, listener) { this.listeners.get(type)?.delete(listener); }
          dispatchEvent(event) { event.target ||= this; for (const listener of this.listeners.get(event.type) || []) listener(event); return true; }
          focus() { globalThis.document.activeElement = this; }
          matches(selector) {
            if (selector.startsWith(".")) return this.classList.contains(selector.slice(1));
            const data = selector.match(/^\[data-([a-z-]+)="([^"]+)"\]$/);
            if (data) return this.dataset[data[1].replace(/-([a-z])/g, (_m, c) => c.toUpperCase())] === data[2];
            return this.tagName === selector.toUpperCase();
          }
          querySelectorAll(selector) { return this.children.flatMap((child) => [child, ...(typeof child.querySelectorAll === "function" ? child.querySelectorAll(selector) : [])]).filter((node) => typeof node.matches === "function" && node.matches(selector)); }
          querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
          get firstElementChild() { return this.children[0] || null; }
        }
        globalThis.document = {
          readyState: "loading", activeElement: null, visibilityState: "visible",
          createElement(tagName) { return new FakeElement(tagName); },
          addEventListener() {}, removeEventListener() {}, querySelectorAll() { return []; }, getElementById() { return null; },
        };
        globalThis.location = { origin: "https://cinescope.test", pathname: "/observatory" };
        globalThis.window = { addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: false }), devicePixelRatio: 1 };
        globalThis.Image = class FakeImage {
          constructor() { this.tagName = "IMG"; this.naturalWidth = 640; this.children = []; this.hidden = true; }
          set src(value) { this._src = value; queueMicrotask(() => this.onload?.()); } get src() { return this._src; }
          decode() { return Promise.resolve(); }
        };
        const collectNodes = (node) => [node, ...node.children.flatMap((child) => collectNodes(child))];
        const flush = async () => { for (let index = 0; index < 12; index += 1) await Promise.resolve(); };
        '''
    )


class ObservatoryUiTests(unittest.TestCase):
    def test_observatory_is_packaged_as_a_deep_linked_library_space(self):
        app = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        index = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        library = (UI_ROOT / "js" / "features" / "library.js").read_text(encoding="utf-8")
        detail = (UI_ROOT / "js" / "features" / "detail.js").read_text(encoding="utf-8")
        store = (UI_ROOT / "js" / "core" / "store.js").read_text(encoding="utf-8")
        styles = (UI_ROOT / "styles" / "observatory.css").read_text(encoding="utf-8")

        self.assertIn('import { renderObservatory } from "./features/observatory.js"', app)
        self.assertIn('{ pattern: "/observatory", name: "observatory" }', app)
        self.assertIn('route.name === "observatory"', app)
        self.assertIn('href="/assets/v3/styles/observatory.css"', index)
        self.assertIn('observatoryEntry.href = "/observatory"', library)
        self.assertIn("library-observatory-entry", library)
        self.assertIn("observatory", detail.split("SAFE_DETAIL_RETURN_PATH", 1)[1].split(";", 1)[0])
        self.assertIn("observatory", store.split("SAFE_DETAIL_RETURN_PATH", 1)[1].split(";", 1)[0])
        for selector in (
            ".observatory-neural__canvas-shell",
            ".observatory-neural__view-controls",
            ".observatory-neural__inspector",
            ".observatory-focus-composer",
            ".observatory-focus-candidate",
            ".observatory-neural__compose",
            ".observatory-recent__rail",
            ".observatory-live-card",
            ".library-observatory-entry",
            "@media (prefers-reduced-motion: reduce)",
        ):
            with self.subTest(selector=selector):
                self.assertIn(selector, styles)

    def test_recent_timeline_live_decision_cards_and_filters_render_only_complete_media(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const poster = {{ url: "/api/image-proxy?url=https%3A%2F%2Fimage.tmdb.org%2Ft%2Fp500%2Fposter.jpg", media_status: "ready" }};
            const payload = {{
              generated_at: 1788048000,
              recent: {{ count: 1, items: [{{
                item_key: "douban:recent-1", title: "漫长的季节", display_title: "漫长的季节", media_type: "电视剧", year: 2023,
                poster, douban_rating: 9.4, watched_date: "2026-08-28", watched_at_iso: "2026-08-28T12:00:00Z",
                watched_relative: "2天前", watch_source_label: "豆瓣看过日期", watch_progress: {{ label: "追到第6集 / 共12集", percent: 50 }},
              }}] }},
              latest: {{
                fetched_at: 1788048000, live_count: 2, fallback_count: 0, source_counts: {{ tmdb: 2 }}, source_status: {{ tmdb: {{ state: "ready" }} }},
                items: [
                  {{ item_key: "external:tmdb-1", title: "新片甲", display_title: "新片甲", media_type: "电影", year: 2026, genres: ["科幻", "剧情"], poster,
                     is_live: true, release_date: "2026-08-29", source_ratings: {{ tmdb: 8.3, imdb: 7.9 }}, rating_votes: {{ tmdb: 135000, imdb: 42000 }},
                     vote_count: 177000, comment_count: 23800, review_count: 640, source_labels: ["TMDb 热门电影"], summary: "一部身份和素材均已核对的新片。" }},
                  {{ item_key: "external:tmdb-missing", title: "缺图作品", display_title: "缺图作品", media_type: "电影", year: 2026,
                     poster: {{ url: "", media_status: "missing" }}, is_live: true }},
                ],
              }},
              graph: {{ focus_id: "douban:recent-1", nodes: [{{ id: "douban:recent-1", title: "漫长的季节", media_type: "电视剧" }}], edges: [] }},
            }};
            const requests = [];
            const explored = [];
            const navigated = [];
            const cleared = [];
            const root = document.createElement("main");
            const {{ createObservatoryController }} = await import("{module_url('js/features/observatory.js')}");
            const controller = createObservatoryController({{
              root,
              fetchJson: async (path) => {{ requests.push(path); return path.includes("/discovery/latest") ? payload.latest : payload; }},
              onExplore: (item) => explored.push(item.display_title || item.title),
              onNavigate: (path) => navigated.push(path),
              setIntervalFn: () => 77,
              clearIntervalFn: (id) => cleared.push(id),
            }});
            await controller.mount();
            await flush();
            const all = () => collectNodes(root);
            const copy = root.textContent;
            if (!copy.includes("漫长的季节") || !copy.includes("2026年8月28日") || !copy.includes("追到第6集 / 共12集")) throw new Error(`recent timeline incomplete: ${{copy}}`);
            if (!copy.includes("新片甲") || !copy.includes("总评价") || !copy.includes("短评") || !copy.includes("影评")) throw new Error(`decision evidence missing: ${{copy}}`);
            if (!copy.includes("当前展示 1 条在线候选") || copy.includes("在线更新 2 条")) throw new Error(`visible feed count is misleading: ${{copy}}`);
            if (copy.includes("缺图作品")) throw new Error(`incomplete poster candidate rendered: ${{copy}}`);
            const detailAction = all().find((node) => node.className === "observatory-live-card__action" && node.textContent.includes("查看详情"));
            if (detailAction?.href !== "/title/external:tmdb-1" || detailAction?.dataset?.route !== "") throw new Error("online detail route missing");
            const visualLink = all().find((node) => node.className === "observatory-live-card__visual" && node.tagName === "A");
            visualLink?.dispatchEvent({{ type: "pointerenter" }});
            await flush();
            const action = all().find((node) => node.className.includes("observatory-live-card__action--secondary") && node.textContent.includes("围绕它找片"));
            action?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            const graphChip = all().find((node) => node.className.includes("observatory-node-chip") && node.textContent.includes("新片甲"));
            graphChip?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            const openableBody = all().find((node) => node.className.includes("observatory-live-card__body") && node.className.includes("is-openable"));
            openableBody?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            const series = all().find((node) => node.dataset?.observatoryFilter === "series");
            series?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush();
            if (!requests.some((path) => decodeURIComponent(path).includes("media_type=电视剧"))) throw new Error(`series filter request missing: ${{JSON.stringify(requests)}}`);
            if (!requests.includes("/api/v2/titles/external:tmdb-1")) throw new Error(`online detail was not prewarmed: ${{JSON.stringify(requests)}}`);
            const snapshot = controller.snapshot();
            controller.dispose();
            console.log(JSON.stringify({{ copy, requests, explored, navigated, cleared, snapshot }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["新片甲"], result["explored"])
        self.assertEqual(1, result["navigated"].count("/title/external:tmdb-1"))
        self.assertTrue(any("/api/v2/discovery/multi?" in path for path in result["requests"]))
        self.assertEqual([77], result["cleared"])
        self.assertEqual(1, result["snapshot"]["recentCount"])
        self.assertEqual(1, result["snapshot"]["latestCount"])
        self.assertEqual("series", result["snapshot"]["activeFilter"])
        self.assertEqual(300000, result["snapshot"]["autoRefreshMs"])

    def test_focus_composer_replaces_the_automatic_start_then_adds_a_second_manual_seed(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            const node = (id, title, extra = {{}}) => ({{
              id, item_key: id, title, display_title: title, media_type: "电影", year: 2020,
              douban_rating: 8.4, ...extra,
            }});
            const automatic = node("auto:start", "系统起点", {{ is_seed: true }});
            const manualA = node("manual:a", "手选甲", {{ year: 2018, douban_rating: 8.8 }});
            const manualB = node("manual:b", "手选乙", {{ year: 2022, douban_rating: 9.0 }});
            const initial = {{
              generated_at: 1,
              recent: {{ count: 0, items: [] }},
              latest: {{ fetched_at: 1, live_count: 0, items: [], source_counts: {{}}, source_status: {{}} }},
              graph: {{
                focus_id: automatic.id, focus_ids: [automatic.id], nodes: [automatic, node("auto:candidate", "默认候选")],
                edges: [{{ source: automatic.id, target: "auto:candidate", score: 0.8, reason: "共同类型：剧情" }}],
              }},
            }};
            const requests = [];
            const fetchJson = async (path) => {{
              requests.push(path);
              if (path.includes("/titles/search")) {{
                const query = new URL(path, "https://cinescope.test").searchParams.get("q");
                return {{ items: query === "手选乙" ? [manualB] : [manualA] }};
              }}
              if (path.includes("/discovery/multi?")) {{
                const focuses = new URL(path, "https://cinescope.test").searchParams.getAll("focus");
                const seeds = focuses.map((id, index) => node(id, id === manualA.id ? manualA.title : manualB.title, {{ is_seed: true, seed_index: index }}));
                const candidate = node(`result:${{focuses.length}}`, focuses.length > 1 ? "融合结果" : "相似结果", {{
                  matched_seed_count: focuses.length, total_seed_count: focuses.length, fused_rating: 8.7,
                  match_kind: focuses.length > 1 ? "intersection" : "similar",
                }});
                return {{
                  selection_mode: focuses.length > 1 ? "intersection" : "single", round: 0,
                  strict_count: focuses.length > 1 ? 1 : 0, candidate_pool_size: 80, rating_coverage: {{ percent: 100 }}, has_more: true,
                  seeds, items: [candidate],
                  fusion_profile: {{ headline: `${{focuses.length}} 部作品的多维交集`, strategy: "按共同类型与气质排序。", dimensions: [] }},
                  graph: {{
                    focus_id: focuses[0], focus_ids: focuses, nodes: [...seeds, candidate],
                    edges: seeds.map((seed) => ({{ source: seed.id, target: candidate.id, score: 0.9, reason: "共同类型：剧情" }})),
                  }},
                }};
              }}
              return initial;
            }};
            const root = document.createElement("main");
            const {{ createObservatoryController }} = await import("{module_url('js/features/observatory.js')}");
            const controller = createObservatoryController({{
              root, fetchJson,
              setIntervalFn: () => 1, clearIntervalFn() {{}},
            }});
            await controller.mount();
            await flush();
            const all = () => collectNodes(root);
            const input = all().find((item) => item.className === "observatory-focus-composer__input");
            const search = all().find((item) => item.className === "observatory-focus-composer__search-button");
            const initialCopy = all().find((item) => item.className === "observatory-focus-composer__copy")?.textContent || "";
            input.value = "手选甲";
            search.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush();
            let candidate = all().find((item) => item.className.includes("observatory-focus-candidate") && item.dataset?.itemId === manualA.id);
            const firstAction = candidate?.textContent || "";
            candidate?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush(); await flush();
            const afterFirst = controller.snapshot();

            input.value = "手选乙";
            search.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush();
            candidate = all().find((item) => item.className.includes("observatory-focus-candidate") && item.dataset?.itemId === manualB.id);
            const secondAction = candidate?.textContent || "";
            candidate?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush(); await flush();
            const afterSecond = controller.snapshot();
            const finalCopy = all().find((item) => item.className === "observatory-focus-composer__copy")?.textContent || "";
            const composeCopy = all().find((item) => item.className === "observatory-neural__compose")?.textContent || "";
            controller.dispose();
            console.log(JSON.stringify({{ initialCopy, firstAction, secondAction, afterFirst, afterSecond, finalCopy, composeCopy, requests }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("首次手动选择会直接替换", result["initialCopy"])
        self.assertIn("设为首焦点", result["firstAction"])
        self.assertEqual(["manual:a"], result["afterFirst"]["selectedSeedIds"])
        self.assertTrue(result["afterFirst"]["manualFocusSelectionStarted"])
        self.assertIn("加入融合", result["secondAction"])
        self.assertEqual(["manual:a", "manual:b"], result["afterSecond"]["selectedSeedIds"])
        self.assertEqual("intersection", result["afterSecond"]["selectionMode"])
        self.assertIn("已手动选择 2/3", result["finalCopy"])
        self.assertEqual("生成融合推荐", result["composeCopy"])
        multi_paths = [path for path in result["requests"] if "/api/v2/discovery/multi?" in path]
        self.assertEqual(2, len(multi_paths))
        self.assertNotIn("focus=auto%3Astart", multi_paths[0])
        self.assertIn("focus=manual%3Aa", multi_paths[0])
        self.assertIn("focus=manual%3Aa", multi_paths[1])
        self.assertIn("focus=manual%3Ab", multi_paths[1])

    def test_neural_canvas_cancels_animation_and_listeners_and_honors_reduced_motion(self):
        output = run_node_module(
            f'''
            const paintedText = [];
            const gradient = () => ({{ addColorStop() {{}} }});
            const context = {{
              setTransform() {{}}, clearRect() {{}}, createRadialGradient: gradient, fillRect() {{}}, save() {{}}, translate() {{}}, restore() {{}},
              beginPath() {{}}, arc() {{}}, fill() {{}}, stroke() {{}}, moveTo() {{}}, lineTo() {{}}, fillText(value) {{ paintedText.push(String(value)); }},
            }};
            const makeTarget = (extra = {{}}) => {{
              const listeners = new Map();
              return {{
                listeners,
                addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
                removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
                ...extra,
              }};
            }};
            const makeCanvas = (canvasWidth = 960, canvasHeight = 560) => makeTarget({{
              style: {{}}, clientWidth: canvasWidth, clientHeight: canvasHeight, width: 0, height: 0,
              getContext: () => context,
              getBoundingClientRect: () => ({{ left: 0, top: 0, width: canvasWidth, height: canvasHeight }}),
              setAttribute() {{}}, setPointerCapture() {{}}, releasePointerCapture() {{}},
            }});
            globalThis.ResizeObserver = undefined;
            const graph = {{ focus_id: "a", nodes: [{{ id: "a", title: "核心", media_type: "电影" }}, {{ id: "b", title: "邻居", media_type: "电视剧" }}], edges: [{{ source: "a", target: "b", score: 2, reason: "共同类型：剧情" }}] }};
            const frames = [];
            const cancelled = [];
            const canvas = makeCanvas();
            const windowTarget = makeTarget({{ matchMedia: () => ({{ matches: false }}), devicePixelRatio: 1 }});
            const documentTarget = makeTarget({{ visibilityState: "visible" }});
            const {{ createNeuralCanvas }} = await import("{module_url('js/features/observatory.js')}");
            const controller = createNeuralCanvas({{
              canvas, graph, windowTarget, documentTarget,
              requestFrame: (callback) => {{ frames.push(callback); return frames.length; }},
              cancelFrame: (id) => cancelled.push(id),
            }});
            const before = controller.snapshot();
            controller.dispose();
            const after = controller.snapshot();
            const remainingCanvasListeners = [...canvas.listeners.values()].reduce((sum, values) => sum + values.size, 0);
            const remainingWindowListeners = [...windowTarget.listeners.values()].reduce((sum, values) => sum + values.size, 0);
            const remainingDocumentListeners = [...documentTarget.listeners.values()].reduce((sum, values) => sum + values.size, 0);

            let reducedFrames = 0;
            const reduced = createNeuralCanvas({{
              canvas: makeCanvas(), graph,
              windowTarget: makeTarget({{ matchMedia: () => ({{ matches: true }}), devicePixelRatio: 1 }}),
              documentTarget: makeTarget({{ visibilityState: "visible" }}),
              requestFrame: () => {{ reducedFrames += 1; return reducedFrames; }},
              cancelFrame() {{}},
            }});
            const reducedSnapshot = reduced.snapshot();
            reduced.dispose();

            const mobileCanvas = makeCanvas(390, 496);
            const mobile = createNeuralCanvas({{
              canvas: mobileCanvas, graph,
              windowTarget: makeTarget({{ matchMedia: () => ({{ matches: true }}), devicePixelRatio: 1 }}),
              documentTarget: makeTarget({{ visibilityState: "visible" }}),
              requestFrame: () => 1,
              cancelFrame() {{}},
            }});
            const mobileInitial = mobile.snapshot();
            let pageWheelPrevented = 0;
            mobileCanvas.listeners.get("wheel")?.values().next().value?.({{
              clientX: 12, clientY: 24, deltaY: -180, preventDefault() {{ pageWheelPrevented += 1; }},
            }});
            const mobileAfterPageWheel = mobile.snapshot();
            let zoomWheelPrevented = 0;
            mobileCanvas.listeners.get("wheel")?.values().next().value?.({{
              clientX: 12, clientY: 24, deltaY: -180, ctrlKey: true, preventDefault() {{ zoomWheelPrevented += 1; }},
            }});
            const mobileAdjusted = mobile.snapshot();
            mobileCanvas.listeners.get("keydown")?.values().next().value?.({{
              key: "0", preventDefault() {{}},
            }});
            const mobileReset = mobile.snapshot();
            mobile.dispose();
            console.log(JSON.stringify({{ before, after, frameCount: frames.length, cancelled, remainingCanvasListeners, remainingWindowListeners, remainingDocumentListeners, reducedFrames, reducedSnapshot, mobileInitial, mobileAfterPageWheel, mobileAdjusted, mobileReset, pageWheelPrevented, zoomWheelPrevented, paintedText }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["before"]["running"])
        self.assertFalse(result["after"]["running"])
        self.assertEqual(1, result["frameCount"])
        self.assertEqual([1], result["cancelled"])
        self.assertEqual(0, result["remainingCanvasListeners"])
        self.assertEqual(0, result["remainingWindowListeners"])
        self.assertEqual(0, result["remainingDocumentListeners"])
        self.assertEqual(0, result["reducedFrames"])
        self.assertFalse(result["reducedSnapshot"]["running"])
        self.assertGreaterEqual(result["mobileInitial"]["zoom"], 0.38)
        self.assertLess(result["mobileInitial"]["zoom"], 0.62)
        self.assertAlmostEqual(result["mobileInitial"]["fitZoom"], result["mobileInitial"]["zoom"])
        self.assertFalse(result["mobileInitial"]["userAdjustedView"])
        self.assertTrue(result["mobileInitial"]["compactView"])
        self.assertEqual(0, result["pageWheelPrevented"])
        self.assertAlmostEqual(result["mobileInitial"]["zoom"], result["mobileAfterPageWheel"]["zoom"])
        self.assertEqual(1, result["zoomWheelPrevented"])
        self.assertTrue(result["mobileAdjusted"]["userAdjustedView"])
        self.assertGreater(result["mobileAdjusted"]["zoom"], result["mobileInitial"]["zoom"])
        self.assertEqual({"x": 0, "y": 0}, result["mobileAdjusted"]["pan"])
        self.assertFalse(result["mobileReset"]["userAdjustedView"])
        self.assertAlmostEqual(result["mobileReset"]["fitZoom"], result["mobileReset"]["zoom"])
        self.assertEqual({"x": 0, "y": 0}, result["mobileReset"]["pan"])
        self.assertEqual(2, result["before"]["labelCount"])
        self.assertEqual(1, result["before"]["edgeLabelCount"])
        self.assertGreater(result["before"]["minimumNodeGap"], 100)
        self.assertIn("核心", result["paintedText"])
        self.assertIn("邻居", result["paintedText"])
        self.assertTrue(any("类型 · 剧情" in value for value in result["paintedText"]))

    def test_neural_canvas_uses_wide_orbits_and_paints_every_title_without_hiding_relationship_copy(self):
        output = run_node_module(
            f'''
            const paintedText = [];
            const gradient = () => ({{ addColorStop() {{}} }});
            const context = {{
              setTransform() {{}}, clearRect() {{}}, createRadialGradient: gradient, fillRect() {{}}, save() {{}}, translate() {{}}, restore() {{}},
              beginPath() {{}}, arc() {{}}, fill() {{}}, stroke() {{}}, moveTo() {{}}, lineTo() {{}}, fillText(value) {{ paintedText.push(String(value)); }},
            }};
            const makeTarget = (extra = {{}}) => {{
              const listeners = new Map();
              return {{
                listeners,
                addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
                removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
                ...extra,
              }};
            }};
            const canvas = makeTarget({{
              style: {{}}, clientWidth: 1440, clientHeight: 820, width: 0, height: 0,
              getContext: () => context,
              getBoundingClientRect: () => ({{ left: 0, top: 0, width: 1440, height: 820 }}),
              setAttribute() {{}}, setPointerCapture() {{}}, releasePointerCapture() {{}},
            }});
            globalThis.ResizeObserver = undefined;
            const seeds = [
              {{ id: "seed-a", title: "焦点甲", media_type: "电影", matched_seed_count: 3 }},
              {{ id: "seed-b", title: "焦点乙", media_type: "电视剧", matched_seed_count: 3 }},
              {{ id: "seed-c", title: "焦点丙", media_type: "动画", matched_seed_count: 3 }},
            ];
            const candidates = Array.from({{ length: 21 }}, (_, index) => ({{
              id: `candidate-${{index + 1}}`, title: `候选作品${{String(index + 1).padStart(2, "0")}}`,
              media_type: index % 3 === 0 ? "电影" : index % 3 === 1 ? "电视剧" : "动画",
              matched_seed_count: 3, fused_rating: 7.2 + (index % 8) * 0.2,
            }}));
            const edges = candidates.flatMap((candidate, candidateIndex) => seeds.map((seed, seedIndex) => ({{
              source: seed.id, target: candidate.id, score: 1 - candidateIndex * 0.01 - seedIndex * 0.001,
              reason: seedIndex === 0 ? "共同类型：剧情 / 悬疑" : seedIndex === 1 ? "共同气质：克制" : "共同导演：主创甲",
            }})));
            const graph = {{ focus_id: "seed-a", focus_ids: seeds.map((seed) => seed.id), nodes: [...seeds, ...candidates], edges }};
            const titles = graph.nodes.map((node) => node.title);
            const {{ createNeuralCanvas }} = await import("{module_url('js/features/observatory.js')}");
            const controller = createNeuralCanvas({{
              canvas, graph,
              windowTarget: makeTarget({{ matchMedia: () => ({{ matches: true }}), devicePixelRatio: 1 }}),
              documentTarget: makeTarget({{ visibilityState: "visible" }}),
              requestFrame: () => 1, cancelFrame() {{}},
            }});
            const snapshot = controller.snapshot();
            const titleHits = titles.filter((title) => paintedText.includes(title));
            const relationshipCopy = paintedText.filter((value) => /类型 ·|气质 ·|导演 ·/.test(value));
            controller.dispose();
            console.log(JSON.stringify({{ snapshot, titleHits, relationshipCopy }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(24, result["snapshot"]["nodeCount"])
        self.assertEqual(24, result["snapshot"]["labelCount"])
        self.assertEqual(3, result["snapshot"]["edgeLabelCount"])
        self.assertGreater(result["snapshot"]["minimumNodeGap"], 70)
        self.assertGreater(result["snapshot"]["layoutExtentX"], 650)
        self.assertGreater(result["snapshot"]["layoutExtentY"], 450)
        self.assertEqual(24, len(result["titleHits"]))
        self.assertGreaterEqual(len(result["relationshipCopy"]), 3)

    def test_multi_focus_seed_selection_toggles_up_to_three_titles_and_builds_one_request(self):
        output = run_node_module(
            f'''
            const {{ nextGraphSeeds, multiFocusDiscoveryPath }} = await import("{module_url('js/features/observatory.js')}");
            const a = {{ id: "a", item_key: "a", title: "甲" }};
            const b = {{ id: "b", item_key: "b", title: "乙" }};
            const c = {{ id: "c", item_key: "c", title: "丙" }};
            const d = {{ id: "d", item_key: "d", title: "丁" }};
            let seeds = nextGraphSeeds([], a);
            seeds = nextGraphSeeds(seeds, b);
            seeds = nextGraphSeeds(seeds, c);
            seeds = nextGraphSeeds(seeds, d);
            const capped = seeds.map((item) => item.item_key);
            seeds = nextGraphSeeds(seeds, c);
            const toggled = seeds.map((item) => item.item_key);
            const path = multiFocusDiscoveryPath(seeds, 18);
            console.log(JSON.stringify({{ capped, toggled, path }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["b", "c", "d"], result["capped"])
        self.assertEqual(["b", "d"], result["toggled"])
        self.assertIn("/api/v2/discovery/multi?", result["path"])
        self.assertEqual(2, result["path"].count("focus="))
        self.assertIn("limit=18", result["path"])

    def test_graph_batch_prewarm_uses_a_valid_idle_request_options_object(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            const seed = (id, title, index = 0) => ({{
              id, item_key: id, title, display_title: title, media_type: "电影",
              is_seed: true, seed_index: index,
            }});
            const initial = {{
              generated_at: 1,
              recent: {{ count: 0, items: [] }},
              latest: {{ fetched_at: 1, live_count: 0, items: [], source_counts: {{}}, source_status: {{}} }},
              graph: {{
                focus_id: "a", focus_ids: ["a"],
                nodes: [seed("a", "甲"), {{ id: "b", item_key: "b", title: "乙", display_title: "乙", media_type: "电影" }}],
                edges: [{{ source: "a", target: "b", score: 0.8, reason: "共同类型：剧情" }}],
              }},
            }};
            const rebuilt = {{
              selection_mode: "intersection", round: 0, strict_count: 1, candidate_pool_size: 25,
              rating_coverage: {{ percent: 100 }}, has_more: true,
              fusion_profile: {{
                headline: "2 部作品的多维交集", strategy: "按多维证据排序。",
                dimensions: [{{ key: "genre", label: "类型配方", value: "剧情 × 悬疑" }}],
                weights: {{ "语义相似": 0.74, "焦点覆盖": 0.16 }},
              }},
              seeds: [seed("a", "甲", 0), seed("b", "乙", 1)],
              items: [{{
                id: "c", item_key: "c", title: "丙", display_title: "丙", media_type: "电影",
                match_kind: "intersection", matched_seed_count: 2, total_seed_count: 2,
                fusion_summary: "严格交集 · 类型：剧情", reason_chips: ["类型 · 剧情"],
              }}],
              graph: {{
                focus_id: "a", focus_ids: ["a", "b"],
                nodes: [seed("a", "甲", 0), seed("b", "乙", 1), {{
                  id: "c", item_key: "c", title: "丙", display_title: "丙", media_type: "电影",
                  match_kind: "intersection", matched_seed_count: 2, total_seed_count: 2,
                  fusion_summary: "严格交集 · 类型：剧情",
                }}],
                edges: [{{ source: "a", target: "c", score: 0.8, reason: "共同类型：剧情" }}],
              }},
            }};
            const idleCalls = [];
            const windowTarget = {{
              addEventListener() {{}}, removeEventListener() {{}}, matchMedia: () => ({{ matches: true }}), devicePixelRatio: 1,
              requestIdleCallback(callback, options) {{
                if (!options || typeof options !== "object" || Array.isArray(options)) {{
                  throw new TypeError("IdleRequestOptions must be an object");
                }}
                idleCalls.push(options);
                return idleCalls.length;
              }},
            }};
            const root = document.createElement("main");
            const {{ createObservatoryController }} = await import("{module_url('js/features/observatory.js')}");
            const controller = createObservatoryController({{
              root, windowTarget,
              fetchJson: async (path) => path.includes("/discovery/multi?") ? rebuilt : initial,
              setIntervalFn: () => 1, clearIntervalFn() {{}},
            }});
            await controller.mount();
            const target = collectNodes(root).find((node) => node.dataset?.nodeId === "b");
            target?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush(); await flush();
            const mode = collectNodes(root).find((node) => node.className === "observatory-neural__seed-mode")?.textContent || "";
            if (!idleCalls.length || idleCalls[0].timeout !== 900) throw new Error(`invalid idle options: ${{JSON.stringify(idleCalls)}}`);
            if (mode.includes("重建未完成")) throw new Error(`successful graph was mislabeled as failed: ${{mode}}`);
            controller.dispose();
            console.log(JSON.stringify({{ idleCalls, mode }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(900, result["idleCalls"][0]["timeout"])
        self.assertNotIn("重建未完成", result["mode"])

    def test_rapid_focus_clicks_keep_the_newest_graph_when_the_old_request_is_aborted(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            const node = (id, title, extra = {{}}) => ({{ id, item_key: id, title, display_title: title, media_type: "电影", ...extra }});
            const initial = {{
              generated_at: 1,
              recent: {{ count: 0, items: [] }},
              latest: {{ fetched_at: 1, live_count: 0, items: [], source_counts: {{}}, source_status: {{}} }},
              graph: {{
                focus_id: "a", focus_ids: ["a"],
                nodes: [node("a", "甲", {{ is_seed: true }}), node("b", "乙"), node("c", "丙")],
                edges: [
                  {{ source: "a", target: "b", score: 0.8, reason: "共同类型：剧情" }},
                  {{ source: "a", target: "c", score: 0.7, reason: "共同气质：克制" }},
                ],
              }},
            }};
            const pending = [];
            const fetchJson = (path, options = {{}}) => {{
              if (!path.includes("/discovery/multi?")) return Promise.resolve(initial);
              return new Promise((resolve, reject) => {{
                const request = {{ path, signal: options.signal, resolve, reject }};
                pending.push(request);
                options.signal?.addEventListener?.("abort", () => {{
                  const error = new Error("aborted"); error.name = "AbortError"; reject(error);
                }}, {{ once: true }});
              }});
            }};
            const root = document.createElement("main");
            const {{ createObservatoryController }} = await import("{module_url('js/features/observatory.js')}");
            const controller = createObservatoryController({{
              root, fetchJson,
              setIntervalFn: () => 1, clearIntervalFn() {{}},
            }});
            await controller.mount();
            let all = collectNodes(root);
            all.find((item) => item.dataset?.nodeId === "b")?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            all.find((item) => item.dataset?.nodeId === "c")?.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            if (pending.length !== 2) throw new Error(`expected two graph requests: ${{pending.length}}`);
            const latest = {{
              selection_mode: "intersection", round: 0, strict_count: 1, candidate_pool_size: 42,
              rating_coverage: {{ percent: 100 }}, has_more: false,
              fusion_profile: {{
                headline: "3 部作品的多维交集", strategy: "按类型、气质、主创与口碑共同排序。",
                dimensions: [{{ key: "genre", label: "类型配方", value: "剧情 × 悬疑 × 犯罪" }}],
                weights: {{ "语义相似": 0.74, "焦点覆盖": 0.16 }},
              }},
              seeds: [node("a", "甲", {{ is_seed: true, seed_index: 0 }}), node("b", "乙", {{ is_seed: true, seed_index: 1 }}), node("c", "丙", {{ is_seed: true, seed_index: 2 }})],
              items: [node("d", "丁", {{ match_kind: "intersection", matched_seed_count: 3, total_seed_count: 3, fusion_summary: "严格交集 · 类型：剧情" }})],
              graph: {{
                focus_id: "a", focus_ids: ["a", "b", "c"],
                nodes: [node("a", "甲", {{ is_seed: true, seed_index: 0 }}), node("b", "乙", {{ is_seed: true, seed_index: 1 }}), node("c", "丙", {{ is_seed: true, seed_index: 2 }}), node("d", "丁", {{ match_kind: "intersection", matched_seed_count: 3, total_seed_count: 3, fusion_summary: "严格交集 · 类型：剧情" }})],
                edges: [{{ source: "a", target: "d", score: 0.9, reason: "共同类型：剧情" }}],
              }},
            }};
            pending[1].resolve(latest);
            await flush(); await flush();
            const mode = collectNodes(root).find((item) => item.className === "observatory-neural__seed-mode")?.textContent || "";
            const snapshot = controller.snapshot();
            if (!pending[0].signal.aborted) throw new Error("superseded graph request was not aborted");
            if (mode.includes("重建未完成")) throw new Error(`aborted request overwrote the newest state: ${{mode}}`);
            if (!mode.includes("3 个严格交集") && !mode.includes("1 个严格交集")) throw new Error(`newest graph state missing: ${{mode}}`);
            controller.dispose();
            console.log(JSON.stringify({{ mode, snapshot, firstAborted: pending[0].signal.aborted }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["firstAborted"])
        self.assertNotIn("重建未完成", result["mode"])
        self.assertEqual(["a", "b", "c"], result["snapshot"]["selectedSeedIds"])

    def test_title_card_shows_candidate_specific_reason_before_expansion_and_uses_overlay_copy(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderTitleCard }} = await import("{module_url('js/components/title-card.js')}");
            const reason = "《降临》与《星际穿越》的首要连接是气质“思考密度高”，并在类型“科幻 / 剧情”上继续重合。";
            const card = renderTitleCard({{
              item_key: "douban:arrival", title: "降临", media_type: "电影", year: 2016,
              genres: ["科幻", "剧情"], summary: "语言学家试图理解外星访客，并在时间与记忆之间重新认识自己的选择。",
              primary_reason: reason,
              reason_evidence: [
                {{ key: "tone", label: "气质", value: "思考密度高", strength: 0.82 }},
                {{ key: "genre", label: "类型", value: "科幻 / 剧情", strength: 0.78 }},
                {{ key: "quality", label: "口碑证据", value: "7.8 · 2 源", strength: 0.71 }},
              ],
              reason_chips: ["气质 · 思考密度高", "类型 · 科幻 / 剧情", "口碑证据 · 7.8 · 2 源"],
            }});
            const reasonNode = card.querySelector(".title-card__why");
            const chips = card.querySelectorAll(".title-card__reason-chip");
            const expand = card.querySelector(".title-card__expand");
            const panel = card.querySelector(".title-card__expanded-panel");
            if (reasonNode?.textContent !== reason) throw new Error(`default reason missing: ${{card.textContent}}`);
            if (chips.length !== 3) throw new Error(`evidence chips missing: ${{chips.length}}`);
            if (!expand || !panel || panel.hidden !== true) throw new Error("overlay controls were not created in their closed state");
            expand.dispatchEvent({{ type: "click", preventDefault() {{}}, stopPropagation() {{}} }});
            if (panel.hidden || card.dataset.expanded !== "true") throw new Error("full copy did not open as an overlay");
            console.log(JSON.stringify({{ reason: reasonNode.textContent, chips: chips.map((chip) => chip.textContent), expanded: card.dataset.expanded, panelParent: panel.parentNode === card }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("true", result["expanded"])
        self.assertTrue(result["panelParent"])
        self.assertEqual(3, len(result["chips"]))

        styles = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")
        detail_styles = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")
        self.assertRegex(styles, r"\.title-card__expanded-panel\s*\{[^}]*position:\s*absolute", re.DOTALL)
        self.assertRegex(detail_styles, r"\.detail-similar__grid\s*\{[^}]*grid-auto-rows:\s*1fr", re.DOTALL)

    def test_detail_hides_incomplete_similar_posters_and_switches_sparse_overview_to_flow_layout(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ visibleSimilarItems, detailOverviewLayout }} = await import("{module_url('js/features/detail.js')}");
            const payload = {{ items: [
              {{ item_key: "ready", title: "完整海报", poster: {{ url: "/media/{'a' * 64}.jpg", media_status: "ready" }} }},
              {{ item_key: "missing", title: "缺失海报", poster: {{ url: "", media_status: "missing" }} }},
              {{ item_key: "fallback", title: "设计占位", poster: {{ url: "", media_status: "designed-fallback" }} }},
            ] }};
            const sparse = detailOverviewLayout({{
              is_live: true, year: 2026, media_type: "电影",
              item: {{ genres: ["家庭"], directors: ["导演甲"], raw: {{}} }},
            }});
            const balanced = detailOverviewLayout({{
              year: 2016, media_type: "电影",
              item: {{ douban_rating: 8.8, my_rating: 5, vote_count: 10000, genres: ["剧情", "科幻"], directors: ["导演甲"], countries: ["中国"], languages: ["中文"], release_date: "2016-01-01", duration: 120, raw: {{ original_title: "Example" }} }},
            }});
            const oneScore = detailOverviewLayout({{
              year: 2016, media_type: "film",
              item: {{ douban_rating: 8.8, vote_count: 10000, genres: ["Drama"], directors: ["Director A"], countries: ["CN"], languages: ["zh"], release_date: "2016-01-01", duration: 120, raw: {{ original_title: "Example" }} }},
            }});
            console.log(JSON.stringify({{
              visible: visibleSimilarItems(payload).map((item) => item.item_key),
              sparse,
              balanced,
              oneScore,
            }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["ready"], result["visible"])
        self.assertEqual("flow", result["sparse"]["mode"])
        self.assertEqual("balanced", result["balanced"]["mode"])
        self.assertEqual("flow", result["oneScore"]["mode"])

        styles = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")
        observatory_styles = (UI_ROOT / "styles" / "observatory.css").read_text(encoding="utf-8")
        self.assertIn(".detail-overview-grid--flow", styles)
        self.assertIn(".observatory-neural__seed-tray", observatory_styles)
        self.assertIn(".observatory-neural__detail-action", observatory_styles)
        self.assertIn(".observatory-neural__canvas-shell.is-rebuilding", observatory_styles)

    def test_online_title_handoff_opens_a_structured_natural_language_search(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ observatoryIntentForItem }} = await import("{module_url('js/app.js')}");
            const value = observatoryIntentForItem({{ display_title: "降临", genres: ["科幻", "剧情"] }});
            console.log(JSON.stringify({{ value }}));
            '''
        )
        value = json.loads(output)["value"]
        self.assertIn("《降临》", value)
        self.assertIn("科幻、剧情", value)
        self.assertIn("新的叙事或视角", value)

    def test_online_detail_is_compact_and_does_not_render_empty_media_sections(self):
        detail = (UI_ROOT / "js" / "features" / "detail.js").read_text(encoding="utf-8")
        styles = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")
        observatory = (UI_ROOT / "js" / "features" / "observatory.js").read_text(encoding="utf-8")

        self.assertIn('copy.append(renderExpandableSummary(summary))', detail)
        self.assertIn('if (!title?.is_live || visualAssets(title).length)', detail)
        self.assertIn('if (!title?.is_live || (Array.isArray(title?.people) && title.people.length))', detail)
        self.assertIn('if (title?.is_live) return false;', detail)
        self.assertIn('renderDetailReturn(title)', detail)
        self.assertIn('detail-overview-grid', detail)
        self.assertIn('if (!grid.children.length && !title?.is_live)', detail)
        self.assertIn('.detail-backdrop--ambient', styles)
        self.assertIn('-webkit-line-clamp: 4', styles)
        self.assertIn('.detail-overview-grid .detail-score-grid', styles)
        self.assertIn('.detail-overview-grid .detail-facts__grid', styles)
        self.assertNotIn('min-height: 9.5rem', styles)
        self.assertNotIn('min-height: 11rem', styles)
        self.assertRegex(styles, r"\.detail-section\s*\{[^}]*padding:\s*clamp\(1\.55rem,\s*3vw,\s*2\.75rem\)", re.DOTALL)
        self.assertRegex(styles, r"\.detail-facts__grid\s*\{[^}]*grid-template-columns:\s*repeat\(4", re.DOTALL)
        for untranslated in (
            "OBSERVATORY / LIVING TASTE GRAPH",
            "NEURAL ROAM / EXPLAINABLE",
            "VIEWING DIARY / RECENT",
            "LIVE DISCOVERY / MULTI-SOURCE",
            "LIVE / ONLINE",
            "LOCAL / FALLBACK",
            "双击",
        ):
            with self.subTest(untranslated=untranslated):
                self.assertNotIn(untranslated, observatory)
        for localized in ("实时口味图谱", "可解释神经漫游", "观影日记", "多来源在线发现", "实时在线", "本地精选"):
            with self.subTest(localized=localized):
                self.assertIn(localized, observatory)

    def test_detail_hides_unlocalized_original_title_but_keeps_chinese_alias(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ displayableOriginalTitle, factRows }} = await import("{module_url('js/features/detail.js')}");
            const rows = factRows({{
              year: 1957,
              media_type: "电影",
              item: {{
                countries: ["美国"], genres: ["剧情"], directors: ["比利·怀尔德"],
                raw: {{ original_title: "Witness for the Prosecution", aliases: ["Witness for the Prosecution", "控方证人"] }},
              }},
            }});
            console.log(JSON.stringify({{
              english: displayableOriginalTitle("Witness for the Prosecution"),
              chinese: displayableOriginalTitle("控方证人"),
              rows,
              visibleText: rows.flat().join(" | "),
            }}));
            '''
        )
        rendered = json.loads(output)
        self.assertEqual("", rendered["english"])
        self.assertEqual("控方证人", rendered["chinese"])
        self.assertNotIn("Witness for the Prosecution", rendered["visibleText"])
        self.assertIn("控方证人", rendered["visibleText"])


if __name__ == "__main__":
    unittest.main()
