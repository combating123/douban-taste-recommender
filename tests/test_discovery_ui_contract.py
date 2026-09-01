from __future__ import annotations

import json
import re
import subprocess
import textwrap
import unittest
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "douban_recommender" / "ui"


def run_node(script: str) -> dict:
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=False,
    )
    if result.returncode:
        raise AssertionError(f"Node failed\nstdout:\n{result.stdout}\nstderr:\n{result.stderr}")
    return json.loads(result.stdout)


class DiscoveryUiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.api = (UI_ROOT / "js" / "core" / "api.js").read_text(encoding="utf-8")
        self.detail = (UI_ROOT / "js" / "features" / "detail.js").read_text(encoding="utf-8")
        self.library = (UI_ROOT / "js" / "features" / "library.js").read_text(encoding="utf-8")
        self.tonight = (UI_ROOT / "js" / "features" / "tonight.js").read_text(encoding="utf-8")
        self.universe = (UI_ROOT / "js" / "features" / "universe.js").read_text(encoding="utf-8")
        self.observatory = (UI_ROOT / "js" / "features" / "observatory.js").read_text(encoding="utf-8")
        self.components = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")
        self.health = (UI_ROOT / "js" / "features" / "health.js").read_text(encoding="utf-8")
        self.app = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        self.spaces = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.universe_css = (UI_ROOT / "styles" / "universe.css").read_text(encoding="utf-8")

    def test_get_v2_coalesces_hot_requests_and_force_refreshes(self):
        output = run_node(
            r'''
            globalThis.location = { origin: "https://cinescope.test" };
            const session = new Map();
            globalThis.sessionStorage = {
              getItem(key) { return session.has(key) ? session.get(key) : null; },
              setItem(key, value) { session.set(key, String(value)); },
              removeItem(key) { session.delete(key); },
              key(index) { return [...session.keys()][index] ?? null; },
              get length() { return session.size; },
            };
            let fetchCalls = 0;
            let release;
            const gate = new Promise((resolve) => { release = resolve; });
            globalThis.fetch = async () => {
              fetchCalls += 1;
              if (fetchCalls === 1) await gate;
              return { ok: true, status: 200, async json() { return { fetchCalls }; } };
            };
            const { getV2, clearV2GetCache } = await import("./src/douban_recommender/ui/js/core/api.js");
            clearV2GetCache();
            const first = getV2("/api/v2/titles/search?q=%E4%B8%89%E4%BD%93&limit=4");
            const second = getV2("/api/v2/titles/search?q=%E4%B8%89%E4%BD%93&limit=4");
            await Promise.resolve();
            const duringFlight = fetchCalls;
            release();
            const [a, b] = await Promise.all([first, second]);
            const hot = await getV2("/api/v2/titles/search?q=%E4%B8%89%E4%BD%93&limit=4");
            const afterHot = fetchCalls;
            const forced = await getV2("/api/v2/titles/search?q=%E4%B8%89%E4%BD%93&limit=4", { force: true });
            console.log(JSON.stringify({ duringFlight, afterHot, finalCalls: fetchCalls, a, b, hot, forced }));
            ''',
        )
        self.assertEqual(1, output["duringFlight"])
        self.assertEqual(1, output["afterHot"])
        self.assertEqual(2, output["finalCalls"])
        self.assertEqual(output["a"], output["b"])
        self.assertEqual(output["a"], output["hot"])

    def test_get_v2_abort_is_isolated_per_consumer(self):
        output = run_node(
            r'''
            globalThis.location = { origin: "https://cinescope.test" };
            globalThis.sessionStorage = { getItem() { return null; }, setItem() {}, removeItem() {}, key() { return null; }, length: 0 };
            let fetchCalls = 0;
            let release;
            const gate = new Promise((resolve) => { release = resolve; });
            globalThis.fetch = async () => {
              fetchCalls += 1;
              await gate;
              return { ok: true, status: 200, async json() { return { title: "Arrival" }; } };
            };
            const { getV2, clearV2GetCache } = await import("./src/douban_recommender/ui/js/core/api.js");
            clearV2GetCache();
            const controller = new AbortController();
            const cancelled = getV2("/api/v2/titles/douban:1", { signal: controller.signal })
              .then(() => "resolved", (error) => error?.name || "rejected");
            const survivor = getV2("/api/v2/titles/douban:1");
            controller.abort();
            release();
            console.log(JSON.stringify({ fetchCalls, cancelled: await cancelled, survivor: await survivor }));
            ''',
        )
        self.assertEqual(1, output["fetchCalls"])
        self.assertEqual("AbortError", output["cancelled"])
        self.assertEqual("Arrival", output["survivor"]["title"])

    def test_get_cache_has_bounded_memory_and_stable_session_tier(self):
        for token in ("MAX_GET_CACHE_ENTRIES", "sessionStorage", "STABLE_SESSION_ROUTES", "invalidateV2GetCache"):
            with self.subTest(token=token):
                self.assertIn(token, self.api)
        self.assertRegex(self.api, r"MAX_GET_CACHE_ENTRIES\s*=\s*(?:9[6-9]|1[0-5][0-9]|160)")

    def test_detail_commits_title_before_background_discovery(self):
        body = re.search(r"export async function renderTitleDetail\([^)]*\)\s*\{([\s\S]+?)\n\}", self.detail)
        self.assertIsNotNone(body)
        source = body.group(1)
        commit_at = source.find("commitView")
        hydrate_at = source.find("hydrateDetailDiscovery")
        self.assertGreaterEqual(commit_at, 0)
        self.assertGreater(hydrate_at, commit_at)
        self.assertNotIn("await universePromise", source[:commit_at])
        for token in ("renderRelationsSkeleton", "/api/v2/discovery/similar", "detail-similar", "activeDetail?.titleId"):
            with self.subTest(token=token):
                self.assertIn(token, self.detail)

    def test_library_uses_lightbox_gentle_motion_and_coordinated_nearby_loading(self):
        lightbox_path = UI_ROOT / "js" / "components" / "media-lightbox.js"
        self.assertTrue(lightbox_path.exists())
        lightbox = lightbox_path.read_text(encoding="utf-8")
        for token in (
            "openMediaLightbox",
            "ArrowLeft",
            "ArrowRight",
            "Escape",
            "查看完整详情",
            "media-lightbox__backdrop",
            "preloadLocalMedia",
            "MEDIA_LOAD_PRIORITY.background",
            "cancelNeighbourPreloads",
        ):
            with self.subTest(token=token):
                self.assertIn(token, lightbox)
        for token in (
            "openMediaLightbox",
            "attachResilientImage",
            "MEDIA_LOAD_PRIORITY",
            "0.45",
            "0.65",
            "suppressNextClick",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.library)
        self.assertNotIn("preloadLocalMedia", self.library)
        library_window = re.search(r"\.library-window\s*\{([^}]*)\}", self.spaces, re.DOTALL)
        self.assertIsNotNone(library_window)
        self.assertRegex(library_window.group(1), r"height:\s*auto")
        self.assertRegex(library_window.group(1), r"overflow(?:-y)?:\s*visible")
        self.assertNotRegex(self.spaces, r"\.library-window\s*\{[^}]*height:\s*66vh")

    def test_tonight_has_composition_safe_natural_language_discovery(self):
        for token in (
            "DISCOVERY_DEBOUNCE_MS = 420",
            "compositionstart",
            "compositionend",
            "AbortController",
            "discoveryRequestSequence",
            "/api/v2/titles/search",
            "/api/v2/discovery/query",
            "media_badge",
            "explanation",
            "已为你匹配热度最高的",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.tonight)

    def test_observatory_live_cards_expose_full_copy_without_forcing_navigation(self):
        for token in (
            "observatory-live-card__expand",
            "aria-expanded",
            "展开说明",
            "收起说明",
            "observatory-live-card--expanded",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.observatory)

    def test_decision_cards_keep_long_titles_legible_and_expandable(self):
        self.assertNotIn("font-size: clamp(0.64rem", self.components)
        self.assertRegex(
            self.components,
            r'\.title-card__title\[data-length="extreme"\]\s*\{[^}]*font-size:\s*clamp\(0\.82rem',
        )

    def test_universe_is_an_exploration_lab_with_blend_and_mood_axes(self):
        for token in (
            "探索实验室",
            "/api/v2/discovery/blend",
            "left_weight",
            "节奏",
            "氛围",
            "脑力消耗",
            "情绪强度",
            "恢复默认",
            "来自 A",
            "来自 B",
            "融合结果",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.universe)
        for selector in (".exploration-lab", ".blend-stage", ".mood-equalizer", ".blend-results"):
            with self.subTest(selector=selector):
                self.assertIn(selector, self.universe_css)
        self.assertIn("universe-canvas", self.universe)

    def test_universe_blend_payload_clamps_weight_and_preserves_axes(self):
        output = run_node(
            r'''
            const { buildBlendPayload } = await import("./src/douban_recommender/ui/js/features/universe.js");
            const payload = buildBlendPayload({
              leftId: "douban:A",
              rightId: "douban:B",
              leftWeight: 1.4,
              axes: {
                pace_axis: -0.75,
                atmosphere_axis: 0.5,
                cognitive_load_axis: 0.25,
                emotional_intensity_axis: -2,
              },
            });
            let duplicateError = "";
            try {
              buildBlendPayload({ leftId: "douban:A", rightId: "douban:A" });
            } catch (error) {
              duplicateError = error?.name || "error";
            }
            console.log(JSON.stringify({ payload, duplicateError }));
            ''',
        )
        self.assertEqual("douban:A", output["payload"]["left"])
        self.assertEqual("douban:B", output["payload"]["right"])
        self.assertEqual(0.95, output["payload"]["left_weight"])
        self.assertEqual(12, output["payload"]["limit"])
        self.assertEqual(-0.75, output["payload"]["intent"]["pace_axis"])
        self.assertEqual(0.5, output["payload"]["intent"]["atmosphere_axis"])
        self.assertEqual(0.25, output["payload"]["intent"]["cognitive_load_axis"])
        self.assertEqual(-1, output["payload"]["intent"]["emotional_intensity_axis"])
        self.assertEqual("RangeError", output["duplicateError"])

    def test_exploration_lab_prefers_verified_display_titles_everywhere_visible(self):
        output = run_node(
            r'''
            class FakeElement {
              constructor(tagName) {
                this.tagName = String(tagName).toUpperCase(); this.children = []; this.attributes = new Map();
                this.dataset = {}; this.className = ""; this.textContent = ""; this.style = { setProperty() {} };
                this.hidden = false; this.disabled = false; this.id = ""; this.value = "";
              }
              append(...nodes) { for (const node of nodes) this.appendChild(node); }
              appendChild(node) { this.children.push(node); node.parentNode = this; return node; }
              replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
              setAttribute(name, value) { this.attributes.set(name, String(value)); }
              getAttribute(name) { return this.attributes.get(name) ?? null; }
              addEventListener(type, listener) { this[`on${type}`] = listener; }
              get firstElementChild() { return this.children[0] ?? null; }
              focus() {}
            }
            globalThis.document = { createElement: (tag) => new FakeElement(tag) };
            globalThis.location = { origin: "https://cinescope.test" };
            const root = new FakeElement("main");
            const timers = new Map(); let timerId = 0;
            const flushTimers = async () => {
              const callbacks = [...timers.values()]; timers.clear();
              for (const callback of callbacks) callback();
              for (let index = 0; index < 8; index += 1) await Promise.resolve();
            };
            const localized = {
              "Mystery Map": "\u795e\u79d8\u5730\u56fe",
              "Arrival": "\u964d\u4e34",
            };
            const result = {
              id: "external:localized-result", item_key: "external:localized-result",
              title: "Science: The Real History", display_title: "\u79d1\u5e7b\u771f\u53f2",
              original_title: "Science: The Real History", title_localization_source: "douban",
              media_type: "documentary series", poster: { url: "", media_status: "missing" }, explanation: {},
            };
            const { configureUniverse, renderUniverse } = await import("./src/douban_recommender/ui/js/features/universe.js");
            configureUniverse({
              api: {
                async getV2(path) {
                  const query = new URL(path, "https://cinescope.test").searchParams.get("q");
                  return { items: [{
                    id: query === "Mystery Map" ? "external:left" : "external:right",
                    item_key: query === "Mystery Map" ? "external:left" : "external:right",
                    title: query, display_title: localized[query], original_title: query,
                    title_localization_source: "douban", media_type: "movie",
                    poster: { url: "", media_status: "missing" },
                  }] };
                },
                async postV2() { return { left_weight: 0.5, right_weight: 0.5, items: [result] }; },
              },
              preloadMedia: async () => true,
              setTimer(callback) { const id = ++timerId; timers.set(id, callback); return id; },
              clearTimer(id) { timers.delete(id); },
            });
            renderUniverse(root, null);
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const byClass = (name) => collect(root).filter((node) => node.className === name);
            const inputs = byClass("blend-source__input");
            inputs[0].value = "Mystery Map"; inputs[0].oninput(); await flushTimers();
            const candidate = byClass("blend-candidate")[0];
            const candidateTitle = byClass("blend-candidate__title")[0]?.textContent || "";
            const candidateAria = candidate?.getAttribute("aria-label") || "";
            if (candidateTitle !== "\u795e\u79d8\u5730\u56fe" || !candidateAria.includes("\u795e\u79d8\u5730\u56fe") || candidateAria.includes("Mystery Map")) {
              throw new Error(`localized blend candidate missing: ${candidateTitle} / ${candidateAria}`);
            }
            candidate.onclick();
            const sourceTitle = byClass("blend-source-card__title")[0]?.textContent || "";
            const sourceClearAria = byClass("blend-source-card__clear")[0]?.getAttribute("aria-label") || "";
            if (sourceTitle !== "\u795e\u79d8\u5730\u56fe" || inputs[0].value !== "\u795e\u79d8\u5730\u56fe" || !sourceClearAria.includes("\u795e\u79d8\u5730\u56fe")) {
              throw new Error(`localized selected source missing: ${sourceTitle} / ${inputs[0].value} / ${sourceClearAria}`);
            }
            inputs[1].value = "Arrival"; inputs[1].oninput(); await flushTimers();
            byClass("blend-candidate")[0]?.onclick();
            for (let index = 0; index < 12; index += 1) await Promise.resolve();
            const resultTitle = byClass("blend-result-card__title")[0]?.textContent || "";
            const resultAria = byClass("blend-result-card__poster")[0]?.getAttribute("aria-label") || "";
            const resultsHeading = byClass("blend-results__title")[0]?.textContent || "";
            const reasonCopies = byClass("blend-result-card__reason-copy").map((node) => node.textContent);
            const visible = [resultTitle, resultAria, resultsHeading, ...reasonCopies].join(" | ");
            for (const expected of ["\u795e\u79d8\u5730\u56fe", "\u964d\u4e34", "\u79d1\u5e7b\u771f\u53f2"]) {
              if (!visible.includes(expected)) throw new Error(`visible blend copy omitted ${expected}: ${visible}`);
            }
            for (const raw of ["Mystery Map", "Arrival", "Science: The Real History"]) {
              if (visible.includes(raw)) throw new Error(`visible blend copy leaked original title ${raw}: ${visible}`);
            }
            console.log(JSON.stringify({ candidateTitle, candidateAria, sourceTitle, sourceInput: inputs[0].value, sourceClearAria, resultTitle, resultAria, resultsHeading, reasonCopies }));
            ''',
        )
        self.assertEqual("\u795e\u79d8\u5730\u56fe", output["candidateTitle"])
        self.assertEqual("\u79d1\u5e7b\u771f\u53f2", output["resultTitle"])

    def test_editing_a_blend_source_aborts_and_invalidates_the_inflight_result(self):
        output = run_node(
            r'''
            class FakeElement {
              constructor(tagName) {
                this.tagName = String(tagName).toUpperCase(); this.children = []; this.attributes = new Map();
                this.dataset = {}; this.className = ""; this.textContent = ""; this.style = { setProperty() {} };
                this.hidden = false; this.disabled = false; this.id = ""; this.value = "";
              }
              append(...nodes) { for (const node of nodes) this.appendChild(node); }
              appendChild(node) { this.children.push(node); node.parentNode = this; return node; }
              replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
              setAttribute(name, value) { this.attributes.set(name, String(value)); }
              getAttribute(name) { return this.attributes.get(name) ?? null; }
              addEventListener(type, listener) { this[`on${type}`] = listener; }
              get firstElementChild() { return this.children[0] ?? null; }
              focus() {}
            }
            globalThis.document = { createElement: (tag) => new FakeElement(tag) };
            globalThis.location = { origin: "https://cinescope.test" };
            const root = new FakeElement("main");
            const timers = new Map(); let timerId = 0;
            const flushTimers = async () => {
              const callbacks = [...timers.values()]; timers.clear();
              for (const callback of callbacks) callback();
              await Promise.resolve(); await Promise.resolve();
            };
            let resolveBlend;
            const blendCalls = [];
            const { configureUniverse, renderUniverse } = await import("./src/douban_recommender/ui/js/features/universe.js");
            configureUniverse({
              api: {
                async getV2(path) {
                  const query = new URL(path, "https://cinescope.test").searchParams.get("q");
                  return { items: [{ id: `douban:${query}`, item_key: `douban:${query}`, title: query, media_type: "movie", poster: { url: "", media_status: "missing" } }] };
                },
                postV2(path, payload, options) {
                  blendCalls.push({ path, payload, options });
                  return new Promise((resolve) => { resolveBlend = resolve; });
                },
              },
              preloadMedia: async () => true,
              setTimer(callback) { const id = ++timerId; timers.set(id, callback); return id; },
              clearTimer(id) { timers.delete(id); },
            });
            renderUniverse(root, null);
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const inputs = collect(root).filter((node) => node.className === "blend-source__input");
            if (inputs.length !== 2) throw new Error("blank exploration lab did not expose symmetric A/B inputs");
            inputs[0].value = "A"; inputs[0].oninput(); await flushTimers();
            collect(root).find((node) => node.className === "blend-candidate")?.onclick();
            inputs[1].value = "B"; inputs[1].oninput(); await flushTimers();
            collect(root).find((node) => node.className === "blend-candidate")?.onclick();
            if (blendCalls.length !== 1) throw new Error(`expected one blend request, got ${blendCalls.length}`);
            inputs[0].value = "A2"; inputs[0].oninput();
            const abortedAfterEdit = blendCalls[0].options.signal.aborted;
            resolveBlend({ items: [{ id: "douban:stale", title: "stale", explanation: "stale" }] });
            await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
            const results = collect(root).find((node) => node.className === "blend-results");
            const staleCards = collect(root).filter((node) => node.className === "blend-result-card").length;
            console.log(JSON.stringify({ abortedAfterEdit, resultsHidden: results?.hidden, staleCards, blendCalls: blendCalls.length }));
            ''',
        )
        self.assertTrue(output["abortedAfterEdit"])
        self.assertTrue(output["resultsHidden"])
        self.assertEqual(0, output["staleCards"])
        self.assertEqual(1, output["blendCalls"])

    def test_detail_discovery_keeps_cached_get_api_after_partial_reconfigure(self):
        output = run_node(
            r'''
            class FakeElement {
              constructor(tagName) {
                this.tagName = String(tagName).toUpperCase(); this.children = []; this.attributes = new Map();
                this.dataset = {}; this.className = ""; this.textContent = ""; this.style = { setProperty() {} };
                this.hidden = false; this.disabled = false; this.id = "";
              }
              append(...nodes) { for (const node of nodes) this.appendChild(node); }
              appendChild(node) { this.children.push(node); node.parentNode = this; return node; }
              replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
              replaceWith(node) {
                const parent = this.parentNode; const index = parent?.children.indexOf(this) ?? -1;
                if (index >= 0) { parent.children.splice(index, 1, node); node.parentNode = parent; }
              }
              setAttribute(name, value) { this.attributes.set(name, String(value)); }
              getAttribute(name) { return this.attributes.get(name) ?? null; }
              addEventListener(type, listener) { this[`on${type}`] = listener; }
              get firstElementChild() { return this.children[0] ?? null; }
              focus() {}
            }
            const root = new FakeElement("main");
            globalThis.document = {
              createElement: (tag) => new FakeElement(tag),
              createDocumentFragment: () => new FakeElement("fragment"),
              getElementById: () => null,
            };
            globalThis.location = { origin: "https://cinescope.test" };
            const title = {
              item_key: "douban:42", title: "缓存详情", media_type: "movie", year: 2024,
              poster: { url: "/media/poster.jpg", media_status: "ready" },
              backdrop: { url: "/media/backdrop.jpg", media_status: "ready" },
              item: { title: "缓存详情", summary: "完整且经过验证的剧情简介。", genres: ["剧情"], directors: ["导演甲"], casts: [] },
              people: [], stills: [],
            };
            const apiPaths = []; const fetchPaths = []; let postCalls = 0;
            const { configureDetail, renderTitleDetail } = await import("./src/douban_recommender/ui/js/features/detail.js");
            configureDetail({
              root,
              async fetchJson(path) {
                fetchPaths.push(path);
                if (path === "/api/v2/titles/douban:42") return title;
                throw new Error(`uncached discovery path: ${path}`);
              },
              api: {
                async getV2(path) {
                  apiPaths.push(path);
                  return path.includes("/discovery/similar") ? { items: [] } : { focus_id: "douban:42", nodes: [], edges: [] };
                },
              },
            });
            configureDetail({ api: { async postV2() { postCalls += 1; return null; } } });
            await renderTitleDetail("douban:42");
            await Promise.resolve(); await Promise.resolve(); await Promise.resolve();
            console.log(JSON.stringify({ apiPaths, fetchPaths, postCalls }));
            ''',
        )
        self.assertEqual(["/api/v2/titles/douban:42"], output["fetchPaths"])
        self.assertEqual(2, len(output["apiPaths"]))
        self.assertTrue(any(path.startswith("/api/v2/universe?") for path in output["apiPaths"]))
        self.assertTrue(any(path.startswith("/api/v2/discovery/similar?") for path in output["apiPaths"]))
        self.assertEqual(0, output["postCalls"])

    def test_app_injects_cached_get_and_post_clients_into_detail_and_lab(self):
        self.assertRegex(self.app, r"configureUniverse\(\{\s*api:\s*\{\s*getV2,\s*postV2\s*\}")
        self.assertRegex(self.app, r"configureDetail\(\{\s*root:\s*appView,\s*api:\s*\{\s*getV2,\s*postV2\s*\}")

    def test_exploration_lab_route_copy_is_consistent(self):
        for token in (
            'universe: ["探索实验室"',
            "CineScope 探索实验室已就绪，可直接选择两部作品开始碰撞",
            "CineScope 正在浏览：探索实验室",
            "探索实验室暂时无法展开；已保留恢复入口",
        ):
            with self.subTest(token=token):
                self.assertIn(token, self.app)
        self.assertIn('if (path === "/universe") return "返回探索实验室"', self.detail)

    def test_health_prioritises_actionable_assets_and_collapses_legacy_audit(self):
        self.assertNotIn('metric("历史媒体审计（不代表当前页面）"', self.health)
        for token in ("素材可用度", "海报可用", "剧照可用", "本地缓存", "等待修复", "确认失效", "高级诊断", "检查并修复素材", "浏览器授权并自动续传"):
            with self.subTest(token=token):
                self.assertIn(token, self.health)
        self.assertRegex(self.health, r'element\("details",\s*"health-advanced"')


if __name__ == "__main__":
    unittest.main()
