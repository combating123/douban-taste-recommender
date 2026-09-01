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


def fake_dom_module_prelude():
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
            this.clientWidth = 1000; this.clientHeight = 520; this.scrollTop = 0;
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
          readyState: "loading", activeElement: null,
          createElement(tagName) { return new FakeElement(tagName); },
          addEventListener() {}, removeEventListener() {}, querySelectorAll() { return []; },
        };
        globalThis.location = { origin: "https://cinescope.test", pathname: "/health" };
        globalThis.window = { addEventListener() {}, removeEventListener() {}, matchMedia: () => ({ matches: false }) };
        globalThis.Image = class FakeImage {
          constructor() { this.tagName = "IMG"; this.naturalWidth = 640; this.children = []; }
          set src(value) { this._src = value; queueMicrotask(() => this.onload?.()); } get src() { return this._src; }
          decode() { return Promise.resolve(); }
        };
        const collectNodes = (node) => [node, ...node.children.flatMap((child) => collectNodes(child))];
        const flush = async () => { for (let index = 0; index < 8; index += 1) await Promise.resolve(); };
        '''
    )


class UiV3ContractTests(unittest.TestCase):
    def test_global_discovery_is_enabled_for_every_command_lens_session(self):
        source = (UI_ROOT / "js" / "features" / "command-lens.js").read_text(encoding="utf-8")

        self.assertGreaterEqual(source.count("fetch_global: true"), 2)
        self.assertGreaterEqual(source.count("use_local_index: true"), 2)

    def test_recommendations_use_seen_inspired_wide_decision_cards(self):
        component = (UI_ROOT / "js" / "components" / "title-card.js").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")

        for class_name in (
            "title-card__ratings",
            "title-card__genres",
            "title-card__summary",
            "title-card__why",
        ):
            self.assertIn(class_name, component)
        self.assertRegex(css, r"\.title-shelf__rail\s*\{[^}]*display:\s*grid", re.DOTALL)
        self.assertRegex(
            css,
            r"\.title-card__link\s*\{[^}]*grid-template-columns:\s*minmax\([^;]+minmax\(0,\s*1fr\)",
            re.DOTALL,
        )
        self.assertRegex(css, r"\.title-card__summary\s*\{[^}]*-webkit-line-clamp:\s*3", re.DOTALL)

    def test_recommendation_cards_and_shelf_make_online_candidates_explicit_and_filterable(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const state = {{ recommendation: {{
              sessionId: "source-session", activeChannel: "anime-series",
              discovery: {{
                local_index_size: 687, live_size: 36, source_counts: {{ anilist: 36 }},
                recommendation_origin_counts: {{ "\\u52a8\\u6f2b": {{ online: 17, catalog: 0, total: 17 }} }},
              }},
              channels: {{
                "anime-series": {{
                  sessionId: "source-session", pool_size: 17, matched_size: 17, visible_size: 2, active_batch: 1,
                  batch: {{ index: 1, items: [
                    {{ item_key: "external:anilist-1", title: "Online candidate", media_type: "\\u52a8\\u753b\\u5267\\u96c6", year: 2026, genres: ["\\u52a8\\u753b"], source: "global:anilist", discovery_sources: ["anilist"] }},
                    {{ item_key: "douban:1", title: "Curated candidate", media_type: "\\u52a8\\u753b\\u5267\\u96c6", year: 2024, genres: ["\\u52a8\\u753b"], source: "title_seed" }},
                  ] }},
                }},
              }},
            }} }};
            const root = document.createElement("main");
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            configureTonight({{ root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2: async () => ({{}}) }} }});
            renderTonight(state);
            const all = () => collectNodes(root);
            const copy = root.textContent;
            if (!copy.includes("\\u5728\\u7ebf\\u53d1\\u73b0 \\u00b7 AniList")) throw new Error(`online origin badge missing: ${{copy}}`);
            if (!copy.includes("\\u7cbe\\u9009\\u5019\\u9009")) throw new Error(`catalog origin badge missing: ${{copy}}`);
            if (!copy.includes("\\u5728\\u7ebf\\u65b0\\u589e 1") || !copy.includes("\\u7247\\u5e93 / \\u7cbe\\u9009 1")) throw new Error(`source counts missing: ${{copy}}`);
            if (!copy.includes("\\u52a8\\u6f2b 17")) throw new Error(`online destination summary missing: ${{copy}}`);
            const onlineFilter = all().find((node) => node.className.includes("title-shelf__filter") && node.textContent.includes("\\u5728\\u7ebf\\u65b0\\u589e"));
            if (!onlineFilter) throw new Error("online source filter missing");
            onlineFilter.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            const cards = all().filter((node) => node.className === "title-card");
            if (cards.length !== 1 || !cards[0].textContent.includes("Online candidate") || cards[0].textContent.includes("Curated candidate")) {{
              throw new Error(`online filter did not isolate the online candidate: ${{cards.map((card) => card.textContent)}}`);
            }}
            console.log(JSON.stringify({{ copy, filtered: cards.map((card) => card.textContent) }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("\u5728\u7ebf\u53d1\u73b0 \u00b7 AniList", result["copy"])
        self.assertEqual(1, len(result["filtered"]))

    def test_online_filter_reaches_candidates_beyond_the_initial_card_budget(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const catalogItems = Array.from({{ length: 12 }}, (_, index) => ({{
              item_key: `douban:${{index + 1}}`, title: `Catalog ${{index + 1}}`, media_type: "\u7535\u89c6\u5267",
              year: 2024, genres: ["\u5267\u60c5"], source: "title_seed",
            }}));
            const onlineItems = Array.from({{ length: 6 }}, (_, index) => ({{
              item_key: `external:tvmaze-${{index + 1}}`, title: `Online ${{index + 1}}`, media_type: "\u7535\u89c6\u5267",
              year: 2026, genres: ["\u79d1\u5e7b"], source: "global:tvmaze", discovery_sources: ["tvmaze"],
            }}));
            const state = {{ recommendation: {{
              sessionId: "source-session", activeChannel: "series",
              discovery: {{
                local_index_size: 688, live_size: 25, source_counts: {{ tvmaze: 25 }},
                recommendation_origin_channels: [{{ channel: "\u7535\u89c6\u5267", online: 6, catalog: 12, total: 18 }}],
              }},
              channels: {{ series: {{
                sessionId: "source-session", pool_size: 104, matched_size: 104, visible_size: 18, active_batch: 2,
                batch: {{ index: 2, items: [...catalogItems, ...onlineItems] }},
              }} }},
            }} }};
            const root = document.createElement("main");
            const mediaJobs = [];
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            configureTonight({{
              root,
              store: {{ getState: () => state, dispatch() {{}} }},
              api: {{ postV2: async (path, payload) => {{ if (path === "/api/v2/media/jobs") mediaJobs.push(payload.identity_key); return {{}}; }} }},
            }});
            renderTonight(state);
            const all = () => collectNodes(root);
            const defaultCards = all().filter((node) => node.className === "title-card");
            if (defaultCards.length !== 12) throw new Error(`initial card budget changed: ${{defaultCards.length}}`);
            const onlineFilter = all().find((node) => node.className.includes("title-shelf__filter") && node.textContent.includes("\u5728\u7ebf\u65b0\u589e"));
            if (!onlineFilter?.textContent.includes("6")) throw new Error(`online candidates beyond the initial budget remained hidden: ${{root.textContent}}`);
            onlineFilter.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush();
            const filteredCards = all().filter((node) => node.className === "title-card");
            if (filteredCards.length !== 6 || filteredCards.some((card) => !card.textContent.includes("Online"))) {{
              throw new Error(`online filter did not reveal the complete bounded online set: ${{filteredCards.map((card) => card.textContent)}}`);
            }}
            const onlineMediaJobs = mediaJobs.filter((identity) => identity.startsWith("external:tvmaze-"));
            if (onlineMediaJobs.length !== 6) throw new Error(`visible online media was not prewarmed: ${{JSON.stringify(mediaJobs)}}`);
            console.log(JSON.stringify({{ defaultCount: defaultCards.length, onlineCount: filteredCards.length, onlineMediaJobs, filter: onlineFilter.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(12, result["defaultCount"])
        self.assertEqual(6, result["onlineCount"])
        self.assertEqual(6, len(result["onlineMediaJobs"]))

    def test_online_destination_counts_survive_session_reducer_sanitization(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ createEmptyUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const session = {{
              id: "source-session",
              personalization: {{ source: "douban-sync", watched_count: 249, wish_count: 36 }},
              discovery: {{
                local_index_size: 688,
                live_size: 61,
                source_counts: {{ anilist: 36, tvmaze: 25 }},
                recommendation_origin_counts: {{
                  "\\u7535\\u5f71": {{ online: 0, catalog: 152, total: 152 }},
                  "\\u7535\\u89c6\\u5267": {{ online: 19, catalog: 85, total: 104 }},
                  "\\u52a8\\u6f2b": {{ online: 0, catalog: 0, total: 0 }},
                }},
              }},
              channels: {{
                "\\u7535\\u5f71": {{
                  key: "\\u7535\\u5f71", label: "\\u7535\\u5f71", pool_size: 1, matched_size: 1, visible_size: 1,
                  batch: {{ index: 1, items: [{{ item_key: "douban:1", title: "Local title", media_type: "\\u7535\\u5f71", year: 2024, genres: ["\\u5267\\u60c5"], source: "title_seed" }}] }},
                }},
                "\\u7535\\u89c6\\u5267": {{ key: "\\u7535\\u89c6\\u5267", label: "\\u7535\\u89c6\\u5267", pool_size: 19, matched_size: 19, visible_size: 0, batch: {{ index: 1, items: [] }} }},
                "\\u52a8\\u6f2b": {{ key: "\\u52a8\\u6f2b", label: "\\u52a8\\u6f2b", pool_size: 0, matched_size: 0, visible_size: 0, batch: {{ index: 1, items: [] }} }},
              }},
            }};
            const state = reduceUiState(createEmptyUiState(), {{ type: "recommendation/sessionReceived", session }});
            const root = document.createElement("main");
            configureTonight({{ root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2: async () => ({{}}) }} }});
            renderTonight(state);
            if (!root.textContent.includes("\\u5728\\u7ebf\\u65b0\\u589e\\u8fdb\\u5165\\u63a8\\u8350\\uff1a\\u7535\\u89c6\\u5267 19")) {{
              throw new Error(`online destination was lost after reducer sanitization: ${{root.textContent}}`);
            }}
            console.log(JSON.stringify({{ copy: root.textContent, discovery: state.recommendation.discovery }}));
            '''
        )
        result = json.loads(output)
        self.assertIn('在线新增进入推荐：电视剧 19', result["copy"])

    def test_library_uses_readable_decision_card_columns_and_matching_virtual_height(self):
        source = (UI_ROOT / "js" / "features" / "library.js").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")

        self.assertIn("const ROW_HEIGHT = 400;", source)
        self.assertNotIn("return 5;", source[source.index("function columnsFor"):source.index("function itemCard")])
        self.assertRegex(css, r"\.library-window\s*\{[^}]*--library-row-height:\s*400px", re.DOTALL)
        self.assertRegex(css, r"\.library-row\s*\{[^}]*height:\s*var\(--library-row-height,\s*400px\)", re.DOTALL)
        self.assertRegex(css, r"\.library-card\s*\{[^}]*height:\s*calc\(var\(--library-row-height,\s*400px\)\s*-\s*1rem\)", re.DOTALL)
        self.assertRegex(css, r"\.library-card\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)\s+11\.75rem", re.DOTALL)
        self.assertRegex(css, r"\.library-card__copy\s*\{[^}]*grid-auto-rows:\s*max-content", re.DOTALL)
        self.assertRegex(css, r"\.library-card__title\s*\{[^}]*min-height:\s*1\.24em", re.DOTALL)
        self.assertRegex(
            css,
            r"\.library-card__link\s*\{[^}]*grid-template-columns:\s*minmax\(8\.5rem,\s*10rem\)\s+minmax\(0,\s*1fr\)",
            re.DOTALL,
        )
        self.assertRegex(css, r"\.library-card__link\s*\{[^}]*grid-template-rows:\s*minmax\(0,\s*1fr\)", re.DOTALL)
        self.assertRegex(css, r"\.library-card__visuals-rail\s*\{[^}]*grid-auto-flow:\s*column", re.DOTALL)
        self.assertRegex(css, r"\.library-card__visuals-rail\s*\{[^}]*grid-auto-columns:\s*max-content", re.DOTALL)
        self.assertRegex(css, r"\.library-card__visuals-rail\s*\{[^}]*overflow-x:\s*auto", re.DOTALL)
        self.assertRegex(css, r"\.library-card__still-frame\s*\{[^}]*width:\s*auto[^}]*aspect-ratio:\s*var\(--still-aspect,\s*16\s*/\s*9\)", re.DOTALL)
        self.assertRegex(css, r"\.library-card__still\s*\{[^}]*object-fit:\s*contain", re.DOTALL)
        still_frame_css = re.search(r"\.library-card__still-frame\s*\{[^}]*\}", css, re.DOTALL).group(0)
        self.assertNotIn("#000", still_frame_css)
        self.assertRegex(still_frame_css, r"transition:\s*transform\b")
        self.assertRegex(css, r"\.library-card__score,\s*\.library-card__state\s*\{[^}]*font-size:\s*0\.72rem", re.DOTALL)
        self.assertRegex(css, r"\.library-card__title\s*\{[^}]*font-size:\s*clamp\(1\.06rem,\s*1\.15vw,\s*1\.24rem\)", re.DOTALL)
        self.assertRegex(css, r"\.library-card__meta,\s*\.library-card__genres\s*\{[^}]*font-size:\s*0\.8rem", re.DOTALL)
        self.assertRegex(css, r"\.library-card__summary\s*\{[^}]*font-size:\s*0\.86rem[^}]*-webkit-line-clamp:\s*2", re.DOTALL)
        self.assertRegex(css, r"\.library-card__people\s*\{[^}]*font-size:\s*0\.76rem", re.DOTALL)
        self.assertRegex(css, r"\.library-card__visuals-label\s*\{[^}]*font-size:\s*0\.72rem", re.DOTALL)

    def test_mobile_media_lightbox_uses_intrinsic_image_height_without_side_column_squeeze(self):
        css = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")
        mobile = re.search(
            r"@media\s*\(max-width:\s*720px\)\s*\{(?P<body>\s*\.media-lightbox__backdrop[\s\S]*?)\r?\n\}",
            css,
        )

        self.assertIsNotNone(mobile)
        rules = mobile.group("body")
        self.assertRegex(rules, r"\.media-lightbox\s*\{[^}]*height:\s*auto[^}]*min-height:\s*0[^}]*max-height:\s*calc\(", re.DOTALL)
        self.assertRegex(rules, r"\.media-lightbox__stage\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)", re.DOTALL)
        self.assertRegex(rules, r"\.media-lightbox__nav\s*\{[^}]*position:\s*absolute", re.DOTALL)
        self.assertRegex(rules, r"\.media-lightbox__figure\s*\{[^}]*height:\s*auto", re.DOTALL)
        self.assertRegex(rules, r"\.media-lightbox__image-mount\s*\{[^}]*height:\s*auto", re.DOTALL)
        self.assertRegex(rules, r"\.media-lightbox__image\s*\{[^}]*width:\s*100%[^}]*height:\s*auto[^}]*max-height:\s*calc\(", re.DOTALL)

    def test_spaces_stylesheet_closes_taste_toggle_rule_before_later_sections(self):
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")

        self.assertIn('.taste-group[open] .taste-group__summary::after { content: "\\2212"; }', css)
        self.assertNotIn('content: "閳?', css)

    def test_mobile_taste_overview_keeps_three_compact_metrics(self):
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        mobile = css.split("@media (max-width: 720px)", 1)[1].split(
            "@media (min-width: 721px)", 1
        )[0]

        self.assertRegex(
            mobile,
            r"\.taste-overview\s*\{[^}]*grid-template-columns:\s*repeat\(3,\s*minmax\(0,\s*1fr\)\)[^}]*gap:\s*0\.65rem",
            re.DOTALL,
        )
        self.assertRegex(
            mobile,
            r"\.taste-overview__metric\s*\{[^}]*min-height:\s*8\.5rem[^}]*padding:\s*0\.8rem",
            re.DOTALL,
        )
        self.assertNotRegex(mobile, r"\.taste-overview,\s*\.taste-group__body")

    def test_shelf_resolves_per_item_actions_and_title_card_invokes_them(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderShelf }} = await import("{module_url('js/components/shelf.js')}");
            let clicked = "";
            const shelf = renderShelf({{
              title: "电影",
              items: [{{ item_key: "douban:1", title: "测试作品" }}],
              actionsForItem(item) {{ return [{{ label: "不感兴趣", onClick() {{ clicked = item.item_key; }} }}]; }},
            }});
            const button = collectNodes(shelf).find((node) => node.className === "title-card__action");
            if (!button || button.textContent !== "不感兴趣") throw new Error("per-item action was not rendered");
            button.dispatchEvent({{ type: "click" }});
            if (clicked !== "douban:1") throw new Error(`action did not receive its item: ${{clicked}}`);
            console.log(JSON.stringify({{ clicked }}));
            '''
        )
        self.assertEqual(json.loads(output)["clicked"], "douban:1")

    def test_not_interested_optimistically_removes_item_from_every_visible_channel(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createEmptyUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const initial = createEmptyUiState();
            initial.recommendation.channels.movie = {{ batch: {{ items: [{{ item_key: "douban:1" }}, {{ item_key: "douban:2" }}], item_keys: ["douban:1", "douban:2"], visible_size: 2 }} }};
            initial.recommendation.channels.series = {{ batch: {{ items: [{{ item_key: "douban:1" }}], item_keys: ["douban:1"], visible_size: 1 }} }};
            const next = reduceUiState(initial, {{ type: "recommendation/itemSuppressed", itemKey: "douban:1" }});
            if (next.recommendation.channels.movie.batch.items.length !== 1) throw new Error("movie item was not removed");
            if (next.recommendation.channels.series.batch.items.length !== 0) throw new Error("series item was not removed");
            if (next.recommendation.channels.movie.batch.visible_size !== 1 || next.recommendation.channels.series.batch.visible_size !== 0) throw new Error("visible counts were not updated");
            console.log(JSON.stringify(next.recommendation.channels));
            '''
        )
        channels = json.loads(output)
        self.assertEqual(channels["movie"]["batch"]["item_keys"], ["douban:2"])

    def test_metadata_hydration_updates_matching_cards_without_losing_ranking_evidence(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createEmptyUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const initial = createEmptyUiState();
            initial.recommendation.sessionId = "session-1";
            initial.recommendation.channels.movie = {{
              sessionId: "session-1",
              batch: {{ items: [{{ item_key: "douban:1", title: "旧标题", summary: "", score_breakdown: {{ total: 0.91 }} }}] }},
            }};
            const next = reduceUiState(initial, {{
              type: "recommendation/itemHydrated",
              expectedSessionId: "session-1",
              itemKey: "douban:1",
              item: {{ item_key: "douban:1", title: "正式标题", summary: "后台补齐后的真实简介。", directors: ["导演甲"] }},
            }});
            const item = next.recommendation.channels.movie.batch.items[0];
            if (item.title !== "正式标题" || item.summary !== "后台补齐后的真实简介。") throw new Error("hydrated metadata was not merged");
            if (item.score_breakdown?.total !== 0.91) throw new Error("ranking evidence was overwritten by metadata hydration");
            const stale = reduceUiState(next, {{
              type: "recommendation/itemHydrated",
              expectedSessionId: "session-old",
              itemKey: "douban:1",
              item: {{ summary: "过期请求不应覆盖" }},
            }});
            if (stale.recommendation.channels.movie.batch.items[0].summary !== "后台补齐后的真实简介。") throw new Error("stale metadata request mutated the active session");
            console.log(JSON.stringify(item));
            '''
        )
        item = json.loads(output)
        self.assertEqual("后台补齐后的真实简介。", item["summary"])
        self.assertEqual(0.91, item["score_breakdown"]["total"])

    def test_not_interested_immediately_redraws_current_tonight_view(self):
        source = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        subscription = re.search(
            r"const unsubscribe = store\.subscribe\(\(state, action\) => \{(?P<body>.*?)\n  \}\);",
            source,
            re.DOTALL,
        )
        self.assertIsNotNone(subscription)
        redraw = re.search(
            r'if \(state\.activePath\?\.startsWith\("/tonight"\) && \[(?P<actions>.*?)\]\.includes\(action\.type\)\) \{\s*renderTonight\(state\);',
            subscription.group("body"),
            re.DOTALL,
        )
        self.assertIsNotNone(redraw)
        actions = re.findall(r'"([^"]+)"', redraw.group("actions"))
        self.assertIn("recommendation/itemSuppressed", actions)

    def test_detail_route_remembers_and_persists_the_exact_source_space(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createEmptyUiState, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const values = new Map();
            const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            const initial = createEmptyUiState();
            initial.activePath = "/tonight/anime-series";
            const detail = reduceUiState(initial, {{ type: "route/changed", route: {{ name: "title", path: "/title/douban:1", params: {{ id: "douban:1" }} }} }});
            const related = reduceUiState(detail, {{ type: "route/changed", route: {{ name: "title", path: "/title/douban:2", params: {{ id: "douban:2" }} }} }});
            persistUiState(related, storage);
            const restored = restoreUiState(storage);
            if (detail.detailReturnPath !== "/tonight/anime-series") throw new Error(`detail source was not captured: ${{detail.detailReturnPath}}`);
            if (related.detailReturnPath !== "/tonight/anime-series") throw new Error("related-title navigation discarded the original source space");
            if (restored.detailReturnPath !== "/tonight/anime-series") throw new Error("detail source was not persisted across reload");
            console.log(JSON.stringify({{ detail: detail.detailReturnPath, related: related.detailReturnPath, restored: restored.detailReturnPath }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("/tonight/anime-series", result["restored"])

    def test_not_interested_posts_permanent_feedback_without_waiting_for_server_rerender(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const actions = []; const calls = [];
            const store = {{
              getState() {{ return {{ recommendation: {{ sessionId: "session-1", channels: {{ movie: {{ sessionId: "session-1", batch: {{ items: [] }} }} }} }} }}; }},
              dispatch(action) {{ actions.push(action); }},
            }};
            const {{ configureTonight, markItemNotInterested }} = await import("{module_url('js/features/tonight.js')}");
            configureTonight({{ store, root: null, api: {{
              async postV2(path, payload) {{ calls.push({{ path, payload }}); return {{ id: "feedback-1" }}; }},
              async getV2() {{ throw new Error("unexpected refresh"); }},
            }} }});
            const result = await markItemNotInterested({{ item_key: "douban:1", title: "测试作品", media_type: "电影", genres: ["剧情"] }});
            if (actions[0]?.type !== "recommendation/itemSuppressed") throw new Error("optimistic reducer action missing");
            if (calls[0]?.path !== "/api/v2/feedback") throw new Error("feedback endpoint mismatch");
            const payload = calls[0].payload;
            if (payload.event_type !== "permanent-avoid" || payload.scope !== "permanent" || payload.session_id !== "session-1" || payload.item_key !== "douban:1") throw new Error(`feedback payload mismatch: ${{JSON.stringify(payload)}}`);
            if (result?.id !== "feedback-1") throw new Error("feedback result missing");
            console.log(JSON.stringify({{ actions, calls }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(result["calls"][0]["payload"]["payload"]["features"]["media_type"], ["电影"])

    def test_watched_feedback_immediately_suppresses_the_item_and_refreshes_personalization(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const actions = []; const calls = [];
            const store = {{
              getState() {{ return {{ recommendation: {{ sessionId: "session-1", activeChannel: "movie", channels: {{ movie: {{ sessionId: "session-1", batch: {{ items: [] }} }} }} }} }}; }},
              dispatch(action) {{ actions.push(action); }},
            }};
            const {{ configureTonight, markItemWatched, recommendationActionsForItem }} = await import("{module_url('js/features/tonight.js')}");
            configureTonight({{ store, root: null, api: {{
              async postV2(path, payload) {{ calls.push({{ method: "POST", path, payload }}); return {{ id: "feedback-watched-1" }}; }},
              async getV2(path) {{
                calls.push({{ method: "GET", path }});
                return {{ id: "session-1", personalization: {{ watched_count: 246 }}, channels: {{}} }};
              }},
            }} }});
            const item = {{ item_key: "douban:1", title: "测试作品", media_type: "电影", genres: ["剧情"] }};
            const controls = recommendationActionsForItem(item);
            if (controls.map((control) => control.label).join(",") !== "想看,已看过,不感兴趣") throw new Error(`feedback controls mismatch: ${{controls.map((control) => control.label)}}`);
            const result = await markItemWatched(item);
            if (actions[0]?.type !== "recommendation/itemSuppressed" || actions[0]?.itemKey !== "douban:1") throw new Error("watched feedback was not optimistic");
            if (calls[0]?.path !== "/api/v2/feedback") throw new Error("feedback endpoint mismatch");
            const payload = calls[0].payload;
            if (payload.event_type !== "watched" || payload.scope !== "permanent" || payload.session_id !== "session-1" || payload.item_key !== "douban:1") throw new Error(`feedback payload mismatch: ${{JSON.stringify(payload)}}`);
            if (calls[1]?.method !== "GET" || calls[1]?.path !== "/api/v2/recommend/sessions/session-1") throw new Error("personalization was not refreshed after marking watched");
            if (actions[1]?.type !== "recommendation/sessionReceived" || actions[1]?.session?.personalization?.watched_count !== 246) throw new Error("refreshed personalization was not applied");
            if (result?.id !== "feedback-watched-1") throw new Error("feedback result missing");
            console.log(JSON.stringify({{ actions, calls }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("watched", result["calls"][0]["payload"]["event_type"])
        self.assertEqual(["剧情"], result["calls"][0]["payload"]["payload"]["features"]["genre"])

    def test_returning_to_the_app_runs_one_throttled_connected_douban_sync(self):
        output = run_node_module(
            f'''
            class EventTarget {{
              constructor() {{ this.listeners = new Map(); }}
              addEventListener(type, listener) {{
                const listeners = this.listeners.get(type) || new Set();
                listeners.add(listener); this.listeners.set(type, listeners);
              }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              dispatch(type) {{ return Promise.all([...(this.listeners.get(type) || [])].map((listener) => listener({{ type }}))); }}
            }}
            const windowTarget = new EventTarget();
            const documentTarget = new EventTarget();
            documentTarget.visibilityState = "visible";
            let now = 100000;
            let resolveJob;
            const jobResult = new Promise((resolve) => {{ resolveJob = resolve; }});
            const calls = []; const settled = [];
            const api = {{
              async getV2(path) {{
                calls.push({{ method: "GET", path }});
                if (path === "/api/v2/sync/settings") return {{ enabled: true, user_id: "123456789" }};
                if (path === "/api/v2/sync/jobs/job-1") return jobResult;
                throw new Error(`unexpected GET ${{path}}`);
              }},
              async postV2(path, payload) {{ calls.push({{ method: "POST", path, payload }}); return {{ job_id: "job-1", state: "running", reused: true }}; }},
            }};
            const {{ installDoubanReturnSync }} = await import("{module_url('js/core/douban-return-sync.js')}");
            const coordinator = installDoubanReturnSync({{
              windowTarget, documentTarget, api, now: () => now,
              onSettled(job) {{ settled.push(job); }},
            }});
            const first = windowTarget.dispatch("focus");
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            const duplicate = documentTarget.dispatch("visibilitychange");
            for (let index = 0; index < 4; index += 1) await Promise.resolve();
            if (calls.filter((call) => call.method === "POST").length !== 1) throw new Error(`concurrent focus duplicated sync: ${{JSON.stringify(calls)}}`);
            resolveJob({{ id: "job-1", state: "complete", counts: {{ collect_count: 246 }} }});
            await Promise.all([first, duplicate]);
            if (settled.length !== 1 || settled[0].state !== "complete") throw new Error("terminal sync was not published");
            await windowTarget.dispatch("focus");
            if (calls.filter((call) => call.method === "POST").length !== 1) throw new Error("focus throttle did not suppress a duplicate sync");
            now += 61000;
            coordinator.dispose();
            await windowTarget.dispatch("focus");
            if (calls.filter((call) => call.method === "POST").length !== 1) throw new Error("disposed coordinator still handled focus");
            console.log(JSON.stringify({{ calls, settled, snapshot: coordinator.snapshot() }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(
            ["/api/v2/sync/settings", "/api/v2/sync/run-now", "/api/v2/sync/jobs/job-1"],
            [call["path"] for call in result["calls"]],
        )

    def test_app_refreshes_all_live_recommendation_sessions_after_return_sync(self):
        source = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        self.assertIn("installDoubanReturnSync", source)
        self.assertIn('source: "douban-return-sync"', source)
        self.assertRegex(source, r"configureTonight\(\{\s*store,\s*api:\s*\{\s*getV2,\s*postV2\s*\}")

    def test_watched_and_not_interested_controls_use_a_compact_two_action_visual_group(self):
        source = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")
        self.assertIn(".title-card__action--watched", source)
        self.assertRegex(source, r"\.title-card__actions\s*\{[^}]*grid-template-columns", re.DOTALL)
        self.assertIn("focus-visible", source)

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

    def test_library_defaults_to_watched_but_respects_an_explicit_all_filter(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ createEmptyUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const initial = createEmptyUiState();
            if (initial.library.state !== "watched" || initial.library.explicit) throw new Error(`library default was not watched: ${{JSON.stringify(initial.library)}}`);
            const selected = reduceUiState(initial, {{ type: "library/filterChanged", state: "all" }});
            if (selected.library.state !== "all" || selected.library.explicit !== true) throw new Error(`explicit all filter was not retained: ${{JSON.stringify(selected.library)}}`);
            console.log(JSON.stringify({{ initial: initial.library, selected: selected.library }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("watched", result["initial"]["state"])
        self.assertTrue(result["selected"]["explicit"])

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
                intent: {{ free_text: "do-not-persist-structured-intent" }},
                intentSessionId: "do-not-persist-intent-session",
                channels: {{
                  movie: {{ sessionId: "session-movie", batchIndex: 1, batchIds: ["movie-1"] }},
                  series: {{ sessionId: "session-series", batchIndex: 2, batchIds: ["series-1", "https://images.example/poster.jpg"] }},
                  "anime-series": {{ sessionId: "session-anime", batchIndex: 3, batchIds: ["anime-1"] }},
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
            if (restored.recommendation.channels.movie.sessionId !== "session-movie") throw new Error("movie session pointer was not restored");
            if (restored.recommendation.channels.series.sessionId !== "session-series") throw new Error("series session pointer was not restored");
            if (restored.recommendation.channels["anime-series"].sessionId !== "session-anime") throw new Error("anime session pointer was not restored");
            if (restored.scrollByRoute["/title/douban%3A1295644"] !== 480) throw new Error("scroll state was not restored");
            if (restored.commandLens.chips.length !== 1 || restored.rail.mode !== "hidden") throw new Error("allowed UI state was not restored");
            for (const forbidden of ["must-not-persist", "https://images.example/poster.jpg", "arbitraryRootValue", "do-not-persist-structured-intent", "do-not-persist-intent-session"]) {{
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
        self.assertEqual("session-series", restored["recommendation"]["channels"]["series"]["sessionId"])
        self.assertEqual(["title-1"], restored["candidateTray"]["itemIds"])

    def test_store_scroll_cap_sanitizes_all_routes_then_retains_latest_one_hundred(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createEmptyUiState, createStore, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const values = new Map();
            const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            globalThis.localStorage = storage;
            const routes = {{ "//unsafe.example": 10, "/negative": -1 }};
            for (let index = 0; index <= 100; index += 1) routes[`/route-${{String(index).padStart(3, "0")}}`] = index;
            const persisted = persistUiState({{ ...createEmptyUiState(), scrollByRoute: routes }}, storage);
            const restored = restoreUiState(storage);
            for (const candidate of [persisted.scrollByRoute, restored.scrollByRoute]) {{
              const keys = Object.keys(candidate);
              if (keys.length !== 100) throw new Error(`scroll cap retained ${{keys.length}} entries instead of 100`);
              if (keys[0] !== "/route-001" || keys.at(-1) !== "/route-100") throw new Error(`scroll cap kept the wrong recency window: ${{keys[0]}}..${{keys.at(-1)}}`);
              if ("/route-000" in candidate || !("/route-100" in candidate)) throw new Error("latest valid route was dropped");
            }}
            const store = createStore(createEmptyUiState(), reduceUiState);
            for (let index = 0; index <= 100; index += 1) store.dispatch({{ type: "route/scrollSaved", path: `/live-${{String(index).padStart(3, "0")}}`, y: 1000 + index }});
            if (store.getState().scrollByRoute["/live-100"] !== 1100) throw new Error("in-memory store lost the latest live route");
            console.log(JSON.stringify({{ persisted: Object.keys(persisted.scrollByRoute), restored: Object.keys(restored.scrollByRoute), live: Object.keys(store.getState().scrollByRoute).slice(-2) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("/route-001", result["persisted"][0])
        self.assertEqual("/route-100", result["restored"][-1])
        self.assertEqual("/live-100", result["live"][-1])

    def test_store_scroll_updates_reinsert_existing_route_before_reducer_and_direct_persistence(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createEmptyUiState, createStore, persistUiState, restoreUiState, saveScroll }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const values = new Map();
            const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            globalThis.localStorage = storage;
            const firstHundred = Object.fromEntries(Array.from({{ length: 100 }}, (_, index) => [`/route-${{String(index).padStart(3, "0")}}`, index]));

            const store = createStore({{ ...createEmptyUiState(), scrollByRoute: firstHundred }}, reduceUiState);
            let persisted = null;
            store.subscribe((state) => {{ persisted = persistUiState(state, storage); }});
            store.dispatch({{ type: "route/scrollSaved", path: "/route-000", y: 9000 }});
            if (Object.keys(store.getState().scrollByRoute).at(-1) !== "/route-000") throw new Error("reducer update did not become the most recent route");
            store.dispatch({{ type: "route/scrollSaved", path: "/route-100", y: 100 }});
            const live = store.getState().scrollByRoute;
            const liveKeys = Object.keys(live);
            if (liveKeys.length !== 100) throw new Error(`live reducer retained ${{liveKeys.length}} routes instead of 100`);
            if ("/route-001" in live) throw new Error("live reducer did not evict the oldest non-refreshed route");
            if (liveKeys.at(-2) !== "/route-000" || liveKeys.at(-1) !== "/route-100") throw new Error(`live reducer lost refreshed/new recency: ${{liveKeys.slice(-3)}}`);
            const reducerRestored = restoreUiState(storage);
            const reducerKeys = Object.keys(reducerRestored.scrollByRoute);
            if (reducerKeys.length !== 100 || reducerKeys.at(-2) !== "/route-000" || reducerKeys.at(-1) !== "/route-100") throw new Error(`reducer persistence lost latest routes: ${{reducerKeys.slice(-3)}}`);
            if ("/route-001" in reducerRestored.scrollByRoute) throw new Error("reducer persistence evicted a newer route instead of the oldest route");
            if (JSON.stringify(live) !== JSON.stringify(persisted.scrollByRoute)) throw new Error("live and persisted scroll maps differ");
            if (JSON.stringify(live) !== JSON.stringify(reducerRestored.scrollByRoute)) throw new Error("live and persisted/restored scroll maps differ");

            persistUiState({{ ...createEmptyUiState(), scrollByRoute: firstHundred }}, storage);
            saveScroll("/route-000", 9100);
            saveScroll("/route-100", 100);
            const directRestored = restoreUiState(storage);
            const directKeys = Object.keys(directRestored.scrollByRoute);
            if (directKeys.length !== 100 || directKeys.at(-2) !== "/route-000" || directKeys.at(-1) !== "/route-100") throw new Error(`saveScroll persistence lost latest routes: ${{directKeys.slice(-3)}}`);
            if ("/route-001" in directRestored.scrollByRoute) throw new Error("saveScroll persistence evicted a newer route instead of the oldest route");
            console.log(JSON.stringify({{ live, persisted: persisted.scrollByRoute, restored: reducerRestored.scrollByRoute, direct: directRestored.scrollByRoute }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(100, len(result["live"]))
        self.assertNotIn("/route-001", result["live"])
        self.assertEqual(["/route-000", "/route-100"], list(result["live"])[-2:])
        self.assertEqual(result["live"], result["persisted"])
        self.assertEqual(result["live"], result["restored"])
        self.assertEqual(list(result["live"]), list(result["direct"]))

    def test_command_lens_runtime_and_persisted_state_reject_sensitive_text_content(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const values = new Map();
            const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            globalThis.localStorage = storage;
            const {{ containsSensitiveText, createEmptyUiState, createStore, persistUiState, UI_STATE_KEY }} = await import("{module_url('js/core/store.js')}");
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const store = createStore(createEmptyUiState(), reduceUiState);
            const secrets = [
              "Authorization: Bearer top-secret-token",
              "Cookie: bid=abc123; dbcl2=xyz987",
              "api_key = sk-1234567890abcdef",
              "password: cinema-secret",
              "ck=secret-cookie-value",
              "session=abcdef1234567890",
              "sessionid=abcdef1234567890",
              "sid=abcdef1234567890",
              "jwt=abcdef1234567890",
              "credential=abcdef1234567890",
              "subscription=abcdef1234567890",
              "private_key=abcdef1234567890",
              "auth=abcdef1234567890",
              "access_token=abcdef1234567890",
              "refresh_token=abcdef1234567890",
            ];
            for (const secret of secrets) {{
              store.dispatch({{
                type: "commandLens/grounded",
                draft: secret,
                chips: [{{ key: "mood", label: secret, value: secret, removable: true }}],
              }});
              store.dispatch({{
                type: "recommendation/sessionReceived",
                session: {{ id: "safe-session", intent: {{}}, chips: [{{ key: "mood", label: "普通标签", value: secret, removable: true }}], channels: {{}} }},
              }});
              const runtime = JSON.stringify(store.getState());
              if (runtime.includes(secret) || runtime.includes("top-secret-token") || runtime.includes("secret-cookie-value")) throw new Error(`runtime retained secret: ${{runtime}}`);
              persistUiState(store.getState(), storage);
              const serialized = values.get(UI_STATE_KEY) || "";
              if (serialized.includes(secret) || serialized.includes("top-secret-token") || serialized.includes("secret-cookie-value")) throw new Error(`localStorage retained secret: ${{serialized}}`);
            }}
            store.dispatch({{
              type: "commandLens/grounded",
              draft: "今晚的会话 session 想看九十分钟以内、温暖但不俗套的华语电影",
              chips: [{{ key: "mood", label: "温暖", value: "温暖", removable: true }}],
            }});
            persistUiState(store.getState(), storage);
            const state = store.getState();
            if (!state.commandLens.draft.includes("九十分钟") || state.commandLens.chips[0]?.value !== "温暖") throw new Error("ordinary Chinese intent was rejected");
            if (containsSensitiveText("今晚的会话 session 想看轻松电影")) throw new Error("plain session word was misclassified as a credential");
            console.log(JSON.stringify({{ draft: state.commandLens.draft, chips: state.commandLens.chips, serialized: values.get(UI_STATE_KEY) }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("九十分钟", result["draft"])
        self.assertEqual("温暖", result["chips"][0]["value"])

    def test_command_lens_refuses_secret_submission_before_recommendation_api(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const root = new FakeElement("div");
            let apiCalls = 0; const actions = [];
            const store = {{
              getState() {{ return {{ commandLens: {{ draft: "", chips: [] }}, recommendation: {{ channels: {{}} }} }}; }},
              dispatch(action) {{ actions.push(action); }},
            }};
            const {{ configureCommandLens, openCommandLens, submitIntent }} = await import("{module_url('js/features/command-lens.js')}");
            configureCommandLens({{
              root,
              store,
              api: {{ async postV2(_path, payload) {{ apiCalls += 1; return {{ id: "session-1", intent: {{ free_text: payload.intent_text }}, chips: [], channels: {{}} }}; }} }},
            }});
            openCommandLens();
            const status = collectNodes(root).find((node) => node.className === "command-lens__status");
            for (const secret of ["sessionid=abcdef1234567890", "sid=abcdef1234567890"]) {{
              const rejected = await submitIntent(secret);
              if (rejected !== null || apiCalls !== 0 || actions.length !== 0) throw new Error(`secret reached API or store: ${{secret}}`);
              if (!status?.textContent.includes("敏感")) throw new Error(`visible rejection missing: ${{status?.textContent}}`);
            }}
            await submitIntent("今晚的会话 session 想看轻松的华语喜剧");
            if (apiCalls !== 1 || !actions.some((action) => action.type === "commandLens/grounded")) throw new Error("ordinary intent was not submitted");
            console.log(JSON.stringify({{ apiCalls, status: status.textContent, actions: actions.map((action) => action.type) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["apiCalls"])
        self.assertIn("commandLens/grounded", result["actions"])

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

    def test_recommendation_copy_always_exposes_type_and_uses_a_stable_three_row_body(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ displayItem }} = await import("{module_url('js/features/tonight.js')}");
            const complete = displayItem({{
              title: "完整资料",
              media_type: "电影",
              genres: ["剧情", "悬疑"],
              douban_rating: 8.7,
              short_reason: "资料完整",
            }});
            const missingGenres = displayItem({{
              title: "只有媒体类型",
              media_type: "电视剧",
              short_reason: "资料完整",
            }});
            const globalRated = displayItem({{
              title: "全球评分条目",
              media_type: "电影",
              genres: ["科幻"],
              source_ratings: {{ imdb: 8.8, tmdb: 8.5 }},
            }});
            if (!complete.metadata.includes("电影")) throw new Error(`metadata hid media type: ${{JSON.stringify(complete)}}`);
            if (!complete.metadata.includes("豆瓣 8.7") || !complete.metadata.includes("类型：剧情 / 悬疑")) throw new Error(`metadata hid first-glance score or genres: ${{JSON.stringify(complete)}}`);
            if (!complete.reason.includes("剧情") || complete.reason === "资料完整") throw new Error(`genre copy was not informative: ${{complete.reason}}`);
            if (!missingGenres.metadata.includes("豆瓣评分待补全") || !missingGenres.metadata.includes("类型：电视剧")) throw new Error(`missing score/type fallback was not visible: ${{JSON.stringify(missingGenres)}}`);
            if (!missingGenres.reason.includes("电视剧") || missingGenres.reason === "资料完整") throw new Error(`missing genre fallback lost type: ${{missingGenres.reason}}`);
            if (!globalRated.metadata.includes("IMDb 8.8") || globalRated.metadata.includes("豆瓣评分待补全")) throw new Error(`global source ratings were hidden by a Douban-only fallback: ${{JSON.stringify(globalRated)}}`);
            console.log(JSON.stringify({{ complete, missingGenres, globalRated }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("电影", result["complete"]["metadata"])
        self.assertIn("电视剧", result["missingGenres"]["reason"])

        css = (UI_ROOT / "styles" / "components.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.title-shelf__item\s*\{[^}]*display:\s*flex", re.DOTALL)
        self.assertIn("grid-template-rows: minmax(0, 1fr) auto", css)
        self.assertRegex(css, r"\.title-card__link\s*\{[^}]*grid-template-columns", re.DOTALL)
        self.assertRegex(css, r"\.title-card__summary\s*\{[^}]*min-height:\s*4\.05em", re.DOTALL)
        self.assertRegex(css, r"\.title-card__why\s*\{[^}]*min-height:\s*2\.7em", re.DOTALL)
        self.assertRegex(css, r"\.title-card__actions\s*\{[^}]*margin-top:\s*auto", re.DOTALL)

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
                this.hidden = false;
                createdImages.push(this);
              }}
              set src(value) {{
                this._src = value;
                this.hiddenWhenAssigned = this.hidden;
                queueMicrotask(() => {{
                  if (!this.parentNode || imageMode === "load-failure") this.onerror?.(new Error("load failed"));
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
            const failedImage = createdImages[0];
            if (failedImage?.hiddenWhenAssigned !== true) {{
              throw new Error("preload exposed a native image before failure was known");
            }}
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
            if (decodedImage.hiddenWhenAssigned !== true) {{
              throw new Error("preload exposed a native image before decoding completed");
            }}
            if (decodedImage.hidden) {{
              throw new Error("decoded image remained hidden after promotion");
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

    def test_media_preload_uses_loaded_intrinsic_pixels_when_decode_never_settles(self):
        output = run_node_module(
            f'''
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

            globalThis.document = {{ createElement: (tagName) => new FakeElement(tagName) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            globalThis.Image = class FakeImage {{
              constructor() {{ this.tagName = "IMG"; this.naturalWidth = 640; this.naturalHeight = 960; }}
              set src(value) {{ this._src = value; queueMicrotask(() => this.onload?.()); }}
              get src() {{ return this._src; }}
              decode() {{ return new Promise(() => {{}}); }}
            }};

            const {{ renderMediaFrame }} = await import("{module_url('js/components/media-frame.js')}");
            const frame = renderMediaFrame({{
              localUrl: "/media/cached-poster.webp",
              kind: "poster",
              title: "Cached Poster",
              status: "ready",
            }});
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            if (frame.dataset.mediaState !== "ready") {{
              throw new Error(`loaded cached image remained ${{frame.dataset.mediaState}}`);
            }}
            if (frame.firstElementChild?.tagName !== "IMG" || frame.firstElementChild?.naturalWidth !== 640) {{
              throw new Error("loaded cached image was not promoted into the visible frame");
            }}
            console.log(JSON.stringify({{ state: frame.dataset.mediaState, width: frame.firstElementChild.naturalWidth }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("ready", result["state"])
        self.assertEqual(640, result["width"])

    def test_resilient_app_image_retries_trusted_proxy_urls_before_fallback(self):
        output = run_node_module(
            f'''
            globalThis.location = {{ origin: "https://cinescope.test" }};
            class FakeImage {{
              constructor() {{ this.listeners = new Map(); this.dataset = {{}}; this.src = ""; }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              dispatch(type) {{ for (const listener of this.listeners.get(type) || []) listener({{ type, target: this }}); }}
            }}
            const {{ attachResilientImage }} = await import("{module_url('js/core/media.js')}");
            const image = new FakeImage();
            let failures = 0;
            attachResilientImage(image, "/api/image-proxy?url=https%3A%2F%2Fimg.example%2Fstill.jpg", {{
              maxRetries: 2,
              onFailure: () => {{ failures += 1; }},
            }});
            await Promise.resolve(); await Promise.resolve();
            image.dispatch("error"); await Promise.resolve();
            const firstRetry = image.src;
            image.dispatch("error"); await Promise.resolve();
            const secondRetry = image.src;
            image.dispatch("error"); await Promise.resolve();
            if (!firstRetry.includes("_cs_retry=1")) throw new Error(`first retry missing: ${{firstRetry}}`);
            if (!secondRetry.includes("_cs_retry=2")) throw new Error(`second retry missing: ${{secondRetry}}`);
            if (failures !== 1) throw new Error(`terminal fallback count: ${{failures}}`);
            console.log(JSON.stringify({{ firstRetry, secondRetry, failures }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["failures"])

    def test_proxy_media_load_coordinator_reserves_foreground_capacity_and_cancels_work(self):
        output = run_node_module(
            f'''
            const {{ createMediaLoadCoordinator }} = await import("{module_url('js/core/media.js')}");
            const started = [];
            const stopped = [];
            const releases = new Map();
            const coordinator = createMediaLoadCoordinator({{
              maxConcurrent: 3,
              maxBackgroundConcurrent: 2,
              foregroundPriority: 50,
            }});
            const schedule = (name, priority) => coordinator.schedule((done) => {{
              started.push(name);
              releases.set(name, done);
              return () => stopped.push(name);
            }}, {{ priority }});

            const backgroundA = schedule("background-a", 0);
            const backgroundB = schedule("background-b", 0);
            const backgroundC = schedule("background-c", 0);
            await Promise.resolve(); await Promise.resolve();
            if (JSON.stringify(started) !== JSON.stringify(["background-a", "background-b"])) {{
              throw new Error("background work consumed the reserved foreground slot: " + JSON.stringify(started));
            }}

            const promoted = schedule("promoted", 0);
            promoted.promote(40);
            const cancelled = schedule("cancelled", 200);
            cancelled.cancel();
            const foreground = schedule("foreground", 100);
            await Promise.resolve(); await Promise.resolve();
            if (JSON.stringify(started) !== JSON.stringify(["background-a", "background-b", "foreground"])) {{
              throw new Error("foreground work did not use the reserved slot: " + JSON.stringify(started));
            }}

            releases.get("background-a")();
            await Promise.resolve(); await Promise.resolve();
            if (started[3] !== "promoted") throw new Error("priority promotion was ignored: " + JSON.stringify(started));
            if (started.includes("cancelled")) throw new Error("cancelled queued work started");

            foreground.cancel();
            promoted.cancel();
            backgroundB.cancel();
            backgroundC.cancel();
            await Promise.resolve(); await Promise.resolve();
            if (!stopped.includes("foreground") || !stopped.includes("promoted") || !stopped.includes("background-b")) {{
              throw new Error("active cancellation did not run abort hooks: " + JSON.stringify(stopped));
            }}
            if (stopped.includes("cancelled") || stopped.includes("background-c")) {{
              throw new Error("queued cancellation incorrectly ran an active abort hook: " + JSON.stringify(stopped));
            }}
            console.log(JSON.stringify({{ started, stopped }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["background-a", "background-b", "foreground", "promoted"], result["started"])
        self.assertIn("foreground", result["stopped"])

    def test_resilient_proxy_image_cancel_aborts_active_request_and_releases_queue_slot(self):
        output = run_node_module(
            f'''
            globalThis.location = {{ origin: "https://cinescope.test" }};
            class FakeImage {{
              constructor() {{ this.listeners = new Map(); this.dataset = {{}}; this._src = ""; }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              dispatch(type) {{ for (const listener of this.listeners.get(type) || []) listener({{ type, target: this }}); }}
              set src(value) {{ this._src = String(value || ""); }}
              get src() {{ return this._src; }}
            }}
            const {{ attachResilientImage, createMediaLoadCoordinator }} = await import("{module_url('js/core/media.js')}");
            const coordinator = createMediaLoadCoordinator({{
              maxConcurrent: 1,
              maxBackgroundConcurrent: 1,
              foregroundPriority: 50,
            }});
            const firstImage = new FakeImage();
            const secondImage = new FakeImage();
            let failures = 0;
            const first = attachResilientImage(firstImage, "/api/image-proxy?url=first", {{
              coordinator, maxRetries: 0, onFailure: () => failures += 1,
            }});
            const second = attachResilientImage(secondImage, "/api/image-proxy?url=second", {{
              coordinator, maxRetries: 0, onFailure: () => failures += 1,
            }});
            await Promise.resolve(); await Promise.resolve();
            if (!firstImage.src.includes("url=first") || secondImage.src) {{
              throw new Error("queue did not serialize proxy requests: " + firstImage.src + " / " + secondImage.src);
            }}
            first.cancel();
            await Promise.resolve(); await Promise.resolve();
            if (firstImage.src) throw new Error("cancel did not abort the active image: " + firstImage.src);
            if (!secondImage.src.includes("url=second")) throw new Error("cancel did not release the next queue slot");
            if (failures !== 0) throw new Error("cancellation was reported as a media failure: " + failures);
            secondImage.dispatch("load");
            second.cancel();
            console.log(JSON.stringify({{ first: firstImage.src, second: secondImage.src, failures }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("", result["first"])
        self.assertEqual(0, result["failures"])

    def test_media_frame_dispose_cancels_its_proxy_preload(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = String(tagName).toUpperCase(); this.children = []; this.parentNode = null;
                this.dataset = {{}}; this.attributes = new Map(); this.className = ""; this.textContent = "";
              }}
              append(...nodes) {{ nodes.forEach((node) => this.appendChild(node)); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children.forEach((node) => node.parentNode = null); this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              querySelector() {{ return null; }}
              get firstElementChild() {{ return this.children[0] || null; }}
            }}
            const createdImages = [];
            globalThis.document = {{ createElement: (tagName) => new FakeElement(tagName) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            globalThis.Image = class FakeImage {{
              constructor() {{
                this.tagName = "IMG"; this.naturalWidth = 640; this.naturalHeight = 960;
                this.className = ""; this.parentNode = null; this._src = ""; createdImages.push(this);
              }}
              setAttribute() {{}}
              removeAttribute(name) {{ if (name === "src") this._src = ""; }}
              set src(value) {{ this._src = String(value || ""); }}
              get src() {{ return this._src; }}
              decode() {{ return Promise.resolve(); }}
            }};
            const {{ disposeMediaFrame, renderMediaFrame }} = await import("{module_url('js/components/media-frame.js')}");
            const frame = renderMediaFrame({{
              localUrl: "/api/image-proxy?url=poster",
              kind: "poster",
              title: "Cancelable Poster",
              status: "ready",
            }});
            await Promise.resolve(); await Promise.resolve();
            const image = createdImages[0];
            if (!image?.src.includes("url=poster")) throw new Error("proxy preload never started: " + image?.src);
            disposeMediaFrame(frame);
            if (image.src) throw new Error("disposing the frame left its request active: " + image.src);
            image.onload?.();
            await Promise.resolve(); await Promise.resolve();
            if (frame.dataset.mediaState === "ready") throw new Error("disposed frame accepted a stale completion");
            console.log(JSON.stringify({{ state: frame.dataset.mediaState, src: image.src }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("", result["src"])
        self.assertNotEqual("ready", result["state"])

    def test_lightbox_uses_reserved_foreground_capacity_and_cancels_neighbour_preloads(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            Object.defineProperty(FakeElement.prototype, "src", {{
              configurable: true,
              get() {{ return this._src || ""; }},
              set(value) {{ this._src = String(value || ""); }},
            }});
            document.body = new FakeElement("body");
            document.body.style = {{ overflow: "" }};
            document.removeEventListener = () => {{}};
            const preloadSources = [];
            globalThis.Image = class BlockingPreloadImage {{
              constructor() {{ this.naturalWidth = 640; this.parentNode = null; this._src = ""; }}
              setAttribute() {{}}
              removeAttribute(name) {{ if (name === "src") this._src = ""; }}
              set src(value) {{
                this._src = String(value || "");
                if (this._src) preloadSources.push(this._src);
              }}
              get src() {{ return this._src; }}
              decode() {{ return new Promise(() => {{}}); }}
            }};
            const {{ attachResilientImage }} = await import("{module_url('js/core/media.js')}");
            const {{ closeMediaLightbox, openMediaLightbox }} = await import("{module_url('js/components/media-lightbox.js')}");
            const blockerA = new FakeElement("img");
            const blockerB = new FakeElement("img");
            const handleA = attachResilientImage(blockerA, "/api/image-proxy?url=blocker-a", {{ priority: 0 }});
            const handleB = attachResilientImage(blockerB, "/api/image-proxy?url=blocker-b", {{ priority: 0 }});
            await Promise.resolve(); await Promise.resolve();
            const lightbox = openMediaLightbox({{
              items: [
                {{ url: "/api/image-proxy?url=current", label: "\u5f53\u524d\u5267\u7167" }},
                {{ url: "/api/image-proxy?url=neighbour-a", label: "\u76f8\u90bb\u5267\u7167 A" }},
                {{ url: "/api/image-proxy?url=neighbour-b", label: "\u76f8\u90bb\u5267\u7167 B" }},
              ],
              title: "\u5267\u7167\u6d4f\u89c8",
              documentTarget: document,
              windowTarget: window,
            }});
            await Promise.resolve(); await Promise.resolve();
            const current = lightbox?.element?.querySelector?.(".media-lightbox__image");
            if (!current?.src.includes("url=current")) throw new Error("foreground lightbox image could not use the reserved slot");
            if (preloadSources.length) throw new Error("background neighbours bypassed the saturated queue: " + JSON.stringify(preloadSources));
            closeMediaLightbox();
            handleA.cancel();
            await Promise.resolve(); await Promise.resolve();
            if (preloadSources.length) throw new Error("closed lightbox leaked neighbour preloads: " + JSON.stringify(preloadSources));
            handleB.cancel();
            console.log(JSON.stringify({{ current: current.src, preloadSources }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual([], result["preloadSources"])

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

    def test_media_frame_decode_failure_enters_terminal_error_and_retry_can_recover(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.type = ""; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const attempts = [];
            globalThis.Image = class FakeImage {{
              constructor() {{ this.children = []; this.naturalWidth = attempts.length === 0 ? 0 : 640; }}
              set src(value) {{ this._src = value; attempts.push(value); queueMicrotask(() => this.onload?.()); }}
              get src() {{ return this._src; }}
              decode() {{ return this.naturalWidth ? Promise.resolve() : Promise.reject(new Error("decode failed")); }}
            }};
            const {{ renderMediaFrame }} = await import("{module_url('js/components/media-frame.js')}");
            const frame = renderMediaFrame({{
              localUrl: "/media/retry-poster.webp",
              kind: "poster",
              title: "Retry Poster",
              status: "ready",
            }});
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            const retry = frame.children.find((node) => node.tagName === "BUTTON");
            if (frame.dataset.mediaState !== "error") throw new Error(`decode failure stayed non-terminal: ${{frame.dataset.mediaState}}`);
            if (!retry || retry.disabled) throw new Error("terminal media error did not expose an enabled retry action");
            if (retry.textContent !== "重试") throw new Error(`retry copy was corrupted: ${{retry.textContent}}`);
            if (frame.firstElementChild?.children?.[2]?.textContent !== "媒体加载失败") throw new Error("error fallback copy was not localized");
            retry.onclick();
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            if (frame.dataset.mediaState !== "ready" || frame.firstElementChild?.tagName !== "IMG") throw new Error("retry did not recover to ready image");
            console.log(JSON.stringify({{ attempts, state: frame.dataset.mediaState, first: frame.firstElementChild.tagName }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, len(result["attempts"]))
        self.assertEqual("ready", result["state"])

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

    def test_tonight_discovery_prefers_verified_display_title_in_candidates_and_results(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            FakeElement.prototype.getBoundingClientRect = function() {{ return {{ top: 0, left: 0, width: 1000, height: 520 }}; }};
            globalThis.document.createDocumentFragment = () => new FakeElement("fragment");
            const root = new FakeElement("main");
            const candidate = {{
              id: "external:localized-tonight", item_key: "external:localized-tonight",
              title: "Mystery Map", display_title: "\u795e\u79d8\u5730\u56fe",
              original_title: "Mystery Map", title_localization_source: "douban",
              year: 2017, media_type: "\u7535\u89c6\u5267", countries: ["\u4e2d\u56fd\u5927\u9646"],
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", tone: "cyan" }},
              poster: {{ url: "", media_status: "missing" }},
              summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
            }};
            const timers = new Map(); let timerId = 0;
            const state = {{ recommendation: {{ activeChannel: "movie", channels: {{ movie: {{ batch: {{ items: [] }} }} }} }} }};
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            configureTonight({{
              root,
              store: {{ getState: () => state, dispatch() {{}} }},
              api: {{
                getV2: async () => ({{ items: [candidate] }}),
                postV2: async (path) => path === "/api/v2/discovery/query"
                  ? ({{ matched_reference: candidate, items: [candidate], chips: [] }})
                  : ({{ state: "failed" }}),
              }},
              preloadMedia: async () => true,
              setTimer(callback) {{ const id = ++timerId; timers.set(id, callback); return id; }},
              clearTimer(id) {{ timers.delete(id); }},
            }});
            renderTonight(state);
            const input = root.querySelector(".tonight-discovery__input");
            input.value = "Mystery Map";
            input.dispatchEvent({{ type: "input" }});
            for (const callback of [...timers.values()]) callback();
            timers.clear();
            await flush();
            const candidateTitle = root.querySelector(".tonight-discovery-candidate__title");
            if (candidateTitle?.textContent !== "\u795e\u79d8\u5730\u56fe") throw new Error("Tonight candidate ignored display_title: " + candidateTitle?.textContent);
            input.dispatchEvent({{ type: "keydown", key: "Enter", shiftKey: false, isComposing: false, preventDefault() {{}} }});
            await flush();
            const resultTitle = root.querySelector(".tonight-discovery-result__title");
            if (resultTitle?.textContent !== "\u795e\u79d8\u5730\u56fe") throw new Error("Tonight result ignored display_title: " + resultTitle?.textContent);
            const candidateStatus = root.querySelector(".tonight-discovery-candidates__status")?.textContent || "";
            if (!candidateStatus.includes("\u795e\u79d8\u5730\u56fe") || candidateStatus.includes("Mystery Map")) throw new Error("Tonight default-match notice ignored display_title: " + candidateStatus);
            const resultsHeading = root.querySelector(".tonight-discovery-results__title")?.textContent || "";
            if (!resultsHeading.includes("\u795e\u79d8\u5730\u56fe") || resultsHeading.includes("Mystery Map")) throw new Error("Tonight result heading ignored display_title: " + resultsHeading);
            console.log(JSON.stringify({{ candidate: candidateTitle.textContent, result: resultTitle.textContent, candidateStatus, resultsHeading }}));
            '''
        )
        rendered = json.loads(output)
        self.assertEqual("\u795e\u79d8\u5730\u56fe", rendered["candidate"])
        self.assertEqual("\u795e\u79d8\u5730\u56fe", rendered["result"])

    def test_tonight_hero_actions_and_feedback_prefer_verified_display_title(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            FakeElement.prototype.getBoundingClientRect = function() {{ return {{ top: 0, left: 0, width: 1000, height: 520 }}; }};
            globalThis.document.createDocumentFragment = () => new FakeElement("fragment");
            const root = new FakeElement("main");
            const item = {{
              id: "external:localized-hero", item_key: "external:localized-hero",
              title: "Mystery Map", display_title: "\u795e\u79d8\u5730\u56fe",
              original_title: "Mystery Map", title_localization_source: "douban",
              year: 2017, media_type: "\u7535\u89c6\u5267", genres: ["\u7eaa\u5f55\u7247"],
              summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
              stills: [{{ localUrl: "/media/localized-hero.jpg", kind: "backdrop", media_status: "ready" }}],
              poster: {{ localUrl: "/media/localized-poster.jpg", kind: "poster", media_status: "ready" }},
            }};
            const state = {{ recommendation: {{
              sessionId: "session-localized", activeChannel: "movie",
              channels: {{ movie: {{ sessionId: "session-localized", batch: {{ items: [item] }} }} }},
            }} }};
            const calls = [];
            const {{ configureTonight, renderTonight, recommendationActionsForItem, markItemNotInterested }} = await import("{module_url('js/features/tonight.js')}");
            configureTonight({{
              root,
              store: {{ getState: () => state, dispatch() {{}} }},
              api: {{
                async postV2(path, payload) {{ calls.push({{ path, payload }}); return path === "/api/v2/feedback" ? {{ id: "feedback-localized" }} : {{ state: "failed" }}; }},
                async getV2() {{ return state.recommendation; }},
              }},
              preloadMedia: async () => true,
              setTimer() {{ return 1; }}, clearTimer() {{}},
            }});
            renderTonight(state);
            const heroTitle = root.querySelector(".tonight-hero__title")?.textContent || "";
            if (heroTitle !== "\u795e\u79d8\u5730\u56fe") throw new Error("Tonight hero ignored display_title: " + heroTitle);
            const controls = recommendationActionsForItem(item);
            if (controls.some((control) => !control.ariaLabel.includes("\u795e\u79d8\u5730\u56fe") || control.ariaLabel.includes("Mystery Map"))) {{
              throw new Error("Tonight action labels ignored display_title: " + JSON.stringify(controls.map((control) => control.ariaLabel)));
            }}
            await markItemNotInterested(item);
            const toast = root.querySelector(".tonight-feedback-toast__copy")?.textContent || "";
            if (!toast.includes("\u795e\u79d8\u5730\u56fe") || toast.includes("Mystery Map")) throw new Error("Tonight feedback toast ignored display_title: " + toast);
            console.log(JSON.stringify({{ heroTitle, labels: controls.map((control) => control.ariaLabel), toast, calls }}));
            '''
        )
        rendered = json.loads(output)
        self.assertEqual("\u795e\u79d8\u5730\u56fe", rendered["heroTitle"])
        self.assertIn("\u795e\u79d8\u5730\u56fe", rendered["toast"])

    def test_title_card_prefers_verified_display_title_over_original_title(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderTitleCard }} = await import("{module_url('js/components/title-card.js')}");
            const card = renderTitleCard({{
              item_key: "external:localized-card",
              title: "Mystery Map",
              display_title: "\u795e\u79d8\u5730\u56fe",
              original_title: "Mystery Map",
              title_localization_source: "douban",
              media_type: "\u7535\u89c6\u5267",
              summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
            }});
            const heading = card.querySelector(".title-card__title");
            const link = card.querySelector(".title-card__link");
            if (heading?.textContent !== "\u795e\u79d8\u5730\u56fe") throw new Error("title card ignored display_title: " + heading?.textContent);
            if (!link?.getAttribute("aria-label")?.includes("\u795e\u79d8\u5730\u56fe")) throw new Error("title card aria label ignored display_title");
            console.log(JSON.stringify({{ heading: heading.textContent, aria: link.getAttribute("aria-label") }}));
            '''
        )
        rendered = json.loads(output)
        self.assertEqual("\u795e\u79d8\u5730\u56fe", rendered["heading"])
        self.assertIn("\u795e\u79d8\u5730\u56fe", rendered["aria"])

    def test_expandable_copy_control_uses_actual_rendered_overflow(self):
        output = run_node_module(
            f'''
            const {{ isCopyOverflowing, syncExpandableCopyControl }} = await import("{module_url('js/components/expandable-copy.js')}");
            const control = {{ hidden: true, dataset: {{}} }};
            const fits = {{ clientHeight: 48, scrollHeight: 48, clientWidth: 220, scrollWidth: 220 }};
            const wraps = {{ clientHeight: 48, scrollHeight: 82, clientWidth: 220, scrollWidth: 220 }};
            const zeroLayout = {{ clientHeight: 0, scrollHeight: 0, clientWidth: 0, scrollWidth: 0 }};
            const fitVisible = syncExpandableCopyControl(control, [fits], true);
            const fitHidden = control.hidden;
            const overflowVisible = syncExpandableCopyControl(control, [wraps], false);
            const overflowHidden = control.hidden;
            const unknownVisible = syncExpandableCopyControl(control, [{{ clientHeight: undefined, scrollHeight: undefined }}], true);
            const unknownState = control.dataset.copyOverflow;
            const zeroVisible = syncExpandableCopyControl(control, [zeroLayout], true);
            console.log(JSON.stringify({{
              fit: isCopyOverflowing(fits),
              wraps: isCopyOverflowing(wraps),
              fitVisible, fitHidden, overflowVisible, overflowHidden,
              unknownVisible, unknownState, zeroVisible, zeroHidden: control.hidden,
            }}));
            '''
        )
        rendered = json.loads(output)
        self.assertFalse(rendered["fit"])
        self.assertTrue(rendered["wraps"])
        self.assertFalse(rendered["fitVisible"])
        self.assertTrue(rendered["fitHidden"])
        self.assertTrue(rendered["overflowVisible"])
        self.assertFalse(rendered["overflowHidden"])
        self.assertTrue(rendered["unknownVisible"])
        self.assertEqual("unknown", rendered["unknownState"])
        self.assertFalse(rendered["zeroVisible"])
        self.assertTrue(rendered["zeroHidden"])

    def test_title_card_replaces_engineering_placeholder_with_human_decision_copy(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderTitleCard }} = await import("{module_url('js/components/title-card.js')}");
            const card = renderTitleCard({{
              item_key: "douban:42",
              title: "兹山鱼谱",
              media_type: "电影",
              genres: ["剧情", "历史"],
              summary: "由 CineScope 精选扩展池补入的电影候选：兹山鱼谱。优先通过 TMDb / IMDb / TVMaze / AniList / Jikan 等免费来源补图，并保留人工兜底封面。",
            }});
            const text = card.textContent;
            if (text.includes("TMDb / IMDb") || text.includes("精选扩展池补入")) throw new Error(`engineering placeholder leaked into the decision card: ${{text}}`);
            if (!text.includes("剧情 / 历史") || !text.includes("后台核对")) throw new Error(`human fallback copy is not informative: ${{text}}`);
            const generic = renderTitleCard({{
              item_key: "douban:43", title: "待补类型作品", media_type: "电影", genres: ["电影"], summary: "",
            }}).textContent;
            if (generic.includes("以电影为核心的电影") || !generic.includes("故事与人物")) throw new Error(`generic media type produced tautological fallback copy: ${{generic}}`);
            console.log(JSON.stringify({{ text, generic }}));
            '''
        )
        text = json.loads(output)["text"]
        self.assertIn("后台核对", text)
        self.assertNotIn("TMDb / IMDb", text)

    def test_shell_removes_collapsed_rail_bottom_nav_is_four_columns_and_shelves_have_empty_state(self):
        store = (UI_ROOT / "js" / "core" / "store.js").read_text(encoding="utf-8")
        app = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        shell = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")
        responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        shelf = (UI_ROOT / "js" / "components" / "shelf.js").read_text(encoding="utf-8")

        self.assertNotIn('"collapsed"', store)
        self.assertNotIn("rail-collapsed", app + shell + responsive)
        self.assertRegex(shell + responsive, r"\.bottom-nav\s*\{[\s\S]*?grid-template-columns:\s*repeat\(4,\s*minmax\(0,\s*1fr\)\)")
        self.assertNotRegex(responsive, r"grid-template-columns:\s*repeat\(5,")
        self.assertIn("title-shelf__empty", shelf)

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
            if (browser.history.state?.from !== "/title/douban%3A1295644") throw new Error(`navigation did not retain a safe app return route: ${{JSON.stringify(browser.history.state)}}`);
            console.log(JSON.stringify({{ events, active: router.currentRoute }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("person", result["active"]["name"])
        self.assertIn("render:person:person-7", result["events"])

    def test_router_overlapping_navigation_commits_only_latest_route_and_scroll(self):
        output = run_node_module(
            f'''
            import {{ createRouter }} from "{module_url('js/core/router.js')}";
            import {{ persistUiState, restoreUiState }} from "{module_url('js/core/store.js')}";
            const deferred = () => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }};
            const slow = deferred(); const values = new Map(); const listeners = new Map(); const events = []; const rafs = [];
            let deferFrames = false;
            const browser = {{
              location: {{ pathname: "/home" }}, scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }}, removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }},
              requestAnimationFrame(callback) {{ if (deferFrames) rafs.push(callback); else callback(); return rafs.length; }},
              scrollTo(options) {{ this.scrollY = options.top; events.push(`scroll:${{options.top}}`); }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser); globalThis.PopStateEvent = browser.PopStateEvent;
            persistUiState({{ activePath: "/home", scrollByRoute: {{ "/fast": 88, "/slow": 777 }} }}, browser.localStorage);
            const router = createRouter([
              {{ pattern: "/home", name: "home" }}, {{ pattern: "/slow", name: "slow" }},
              {{ pattern: "/fast", name: "fast" }}, {{ pattern: "/blocked", name: "blocked" }},
            ], {{
              async onRoute(route) {{
                events.push(`render:${{route.name}}`);
                if (route.name === "slow") return slow.promise;
                if (route.name === "blocked") return false;
                return true;
              }},
            }});
            await router.start(); events.length = 0; deferFrames = true; browser.scrollY = 31;
            const slowNavigation = router.navigate("/slow");
            await Promise.resolve();
            browser.scrollY = 44;
            const fastNavigation = router.navigate("/fast");
            for (let index = 0; index < 8 && rafs.length < 1; index += 1) await Promise.resolve();
            if (rafs.length !== 1) throw new Error(`latest navigation did not schedule one RAF: ${{rafs.length}}`);
            rafs.shift()();
            await fastNavigation;
            if (router.currentRoute?.name !== "fast" || browser.scrollY !== 88) throw new Error("fast route did not commit and restore its scroll");
            slow.resolve(true);
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            while (rafs.length) rafs.shift()();
            await slowNavigation; await Promise.resolve();
            if (router.currentRoute?.name !== "fast" || browser.scrollY !== 88) throw new Error("slow route performed stale commit or scroll");
            const saved = restoreUiState();
            if (saved.scrollByRoute["/home"] !== 44 || events.includes("scroll:777")) throw new Error(`outgoing/stale scroll was wrong: ${{JSON.stringify({{ saved, events }})}}`);
            const beforeBlocked = events.length;
            const blockedNavigation = router.navigate("/blocked");
            await blockedNavigation;
            if (router.currentRoute?.name !== "fast" || events.slice(beforeBlocked).some((event) => event.startsWith("scroll:"))) throw new Error("onRoute false committed or restored scroll");
            console.log(JSON.stringify({{ events, current: router.currentRoute.name, scrollY: browser.scrollY, saved: saved.scrollByRoute }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("fast", result["current"])
        self.assertEqual(88, result["scrollY"])
        self.assertNotIn("scroll:777", result["events"])

    def test_direct_overlapping_navigation_recaptures_last_departure_scroll(self):
        output = run_node_module(
            f'''
            import {{ createRouter }} from "{module_url('js/core/router.js')}";
            import {{ restoreUiState }} from "{module_url('js/core/store.js')}";
            const deferred = () => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }};
            const slow = deferred(); const values = new Map(); const listeners = new Map(); const events = [];
            const browser = {{
              location: {{ pathname: "/home" }}, scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }}, removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }},
              requestAnimationFrame(callback) {{ callback(); return 1; }},
              scrollTo(options) {{ this.scrollY = options.top; events.push(`scroll:${{options.top}}`); }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser); globalThis.PopStateEvent = browser.PopStateEvent;
            const router = createRouter([
              {{ pattern: "/home", name: "home" }}, {{ pattern: "/slow", name: "slow" }}, {{ pattern: "/real", name: "real" }},
            ], {{
              async onRoute(route) {{ events.push(`render:${{route.name}}`); if (route.name === "slow") return slow.promise; return true; }},
            }});
            await router.start(); events.length = 0;
            browser.scrollY = 31;
            const slowNavigation = router.navigate("/slow");
            await Promise.resolve();
            browser.scrollY = 44;
            const realNavigation = router.navigate("/real");
            await realNavigation;
            slow.resolve(true);
            await slowNavigation;
            const saved = restoreUiState();
            if (saved.scrollByRoute["/home"] !== 44) throw new Error(`last departure scroll was not recaptured: ${{JSON.stringify(saved.scrollByRoute)}}`);
            if (router.currentRoute?.name !== "real") throw new Error(`latest navigation did not retain ownership: ${{router.currentRoute?.name}}`);
            console.log(JSON.stringify({{ saved: saved.scrollByRoute, current: router.currentRoute.name, events }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(44, result["saved"]["/home"])
        self.assertEqual("real", result["current"])

    def test_blocked_and_stale_navigation_release_marker_before_real_departure(self):
        output = run_node_module(
            f'''
            import {{ createRouter }} from "{module_url('js/core/router.js')}";
            import {{ restoreUiState }} from "{module_url('js/core/store.js')}";
            const deferred = () => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }};
            const slow = deferred(); const values = new Map(); const listeners = new Map();
            const browser = {{
              location: {{ pathname: "/home" }}, scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }}, removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }},
              requestAnimationFrame(callback) {{ callback(); return 1; }},
              scrollTo(options) {{ this.scrollY = options.top; }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser); globalThis.PopStateEvent = browser.PopStateEvent;
            const router = createRouter([
              {{ pattern: "/home", name: "home" }}, {{ pattern: "/slow", name: "slow" }},
              {{ pattern: "/blocked", name: "blocked" }}, {{ pattern: "/real", name: "real" }},
            ], {{
              async onRoute(route) {{
                if (route.name === "slow") return slow.promise;
                if (route.name === "blocked") return false;
                return true;
              }},
            }});

            await router.start();
            browser.scrollY = 31;
            const staleNavigation = router.navigate("/slow");
            await Promise.resolve();
            browser.scrollY = 44;
            await router.navigate("/blocked");
            slow.resolve(true);
            await staleNavigation;
            browser.scrollY = 55;
            await router.navigate("/real");
            const saved = restoreUiState();
            if (saved.scrollByRoute["/home"] !== 55) throw new Error(`fresh departure scroll was suppressed: ${{JSON.stringify(saved.scrollByRoute)}}`);
            if (router.currentRoute?.name !== "real") throw new Error(`real navigation did not commit: ${{router.currentRoute?.name}}`);
            console.log(JSON.stringify({{ saved: saved.scrollByRoute, current: router.currentRoute.name }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(55, result["saved"]["/home"])
        self.assertEqual("real", result["current"])

    def test_router_scroll_save_updates_store_before_route_persistence(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ createRouter }} = await import("{module_url('js/core/router.js')}");
            const {{ createEmptyUiState, createStore, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const values = new Map();
            const listeners = new Map();
            const browser = {{
              location: {{ pathname: "/tonight/anime-series" }}, scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }}, removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }},
              requestAnimationFrame(callback) {{ callback(); return 1; }},
              scrollTo(options) {{ this.scrollY = options.top; }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser); globalThis.PopStateEvent = browser.PopStateEvent;

            const store = createStore(createEmptyUiState(), reduceUiState);
            store.subscribe((state) => persistUiState(state, browser.localStorage));
            const router = createRouter([
              {{ pattern: "/tonight/:channel", name: "tonight-channel" }},
              {{ pattern: "/title/:id", name: "title" }},
            ], {{
              onScrollSaved(path, y) {{ store.dispatch({{ type: "route/scrollSaved", path, y }}); }},
              onRoute(route) {{ store.dispatch({{ type: "route/changed", route }}); return true; }},
            }});

            await router.start();
            browser.scrollY = 900;
            await router.navigate("/title/douban:1938084");
            browser.scrollY = 300;
            await router.navigate("/tonight/anime-series");
            const persisted = restoreUiState(browser.localStorage);
            if (store.getState().scrollByRoute["/tonight/anime-series"] !== 900) throw new Error(`store lost outgoing scroll: ${{JSON.stringify(store.getState().scrollByRoute)}}`);
            if (persisted.scrollByRoute["/tonight/anime-series"] !== 900) throw new Error(`storage lost outgoing scroll: ${{JSON.stringify(persisted.scrollByRoute)}}`);
            if (browser.scrollY !== 900) throw new Error(`return navigation restored ${{browser.scrollY}} instead of 900`);
            console.log(JSON.stringify({{ scrollY: browser.scrollY, store: store.getState().scrollByRoute, persisted: persisted.scrollByRoute }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(900, result["scrollY"])
        self.assertEqual(900, result["persisted"]["/tonight/anime-series"])

    def test_tonight_renders_active_channel_counts_one_compact_shelf_and_batch_requests(self):
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
            if (shelfRails.length !== 1) throw new Error(`expected one active-channel shelf, got ${{shelfRails.length}}`);
            if (shelfRails.some((rail) => rail.children.length !== 12)) throw new Error("the visible batch and rendered shelf diverged");

            await requestNextBatch("series", "\u592a\u76f8\u4f3c");
            await restorePreviousBatch("anime-series");
            const batchCalls = calls.filter((call) => call.path.startsWith("/api/v2/recommend/sessions/"));
            if (batchCalls[0]?.path !== "/api/v2/recommend/sessions/session-42/batch") throw new Error(`next batch path mismatch: ${{JSON.stringify(calls)}}`);
            if (batchCalls[0].payload.channel !== "\u7535\u89c6\u5267" || batchCalls[0].payload.reason !== "\u592a\u76f8\u4f3c") throw new Error("reasoned series shuffle was not grounded");
            if (batchCalls[1]?.path !== "/api/v2/recommend/sessions/session-42/previous" || batchCalls[1].payload.channel !== "\u52a8\u6f2b") throw new Error("anime previous batch path mismatch");
            const batchActions = actions.filter((action) => action.type === "recommendation/batchReceived");
            if (batchActions.map((action) => action.channel).join(",") !== "series,anime-series") throw new Error(`channel-specific batch actions were not dispatched: ${{JSON.stringify(actions)}}`);
            console.log(JSON.stringify({{ text, shelfSizes: shelfRails.map((rail) => rail.children.length), calls: batchCalls, backgroundCalls: calls.filter((call) => !batchCalls.includes(call)), actions: batchActions, backgroundActions: actions.filter((action) => !batchActions.includes(action)) }}));
            '''
        )
        rendered = json.loads(output)
        self.assertEqual([12], rendered["shelfSizes"])
        self.assertEqual("太相似", rendered["calls"][0]["payload"]["reason"])

    def test_tonight_channel_switch_delegates_history_to_router_and_keeps_nodes_stable(self):
        output = run_node_module(
            f'''
            import {{ configureTonight, renderTonight }} from "{module_url('js/features/tonight.js')}";

            class FakeElement {{
              constructor(tagName) {{ this.tagName = tagName.toUpperCase(); this.children = []; this.dataset = {{}}; this.attributes = new Map(); this.className = ""; this.textContent = ""; this.disabled = false; this.value = ""; }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag) }};
            const historyPaths = [];
            globalThis.window = {{ history: {{ pushState(_state, _title, path) {{ historyPaths.push(path); throw new Error("Tonight bypassed router history ownership"); }} }} }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            const root = new FakeElement("main");
            let rootReplacements = 0;
            root.replaceChildren = function(...nodes) {{ rootReplacements += 1; this.children = []; this.append(...nodes); }};
            const makeChannel = (title) => ({{ pool_size: 20, matched_size: 18, visible_size: 1, active_batch: 1, batch: {{ index: 1, items: [{{ title }}] }} }});
            const state = {{ activePath: "/tonight/movie", recommendation: {{
              sessionId: "session-42",
              activeChannel: "movie",
              personalization: {{ source: "douban-sync", watched_count: 244, wish_count: 36, rated_count: 120 }},
              channels: {{ movie: makeChannel("MovieCandidate"), series: makeChannel("SeriesCandidate"), "anime-series": makeChannel("AnimeCandidate") }},
            }} }};
            const store = {{
              getState: () => state,
              dispatch(action) {{
                if (action.type === "route/changed") {{
                  state.activePath = action.route.path;
                  state.activeParams = action.route.params;
                  state.recommendation.activeChannel = action.route.params.channel;
                }}
                if (action.type === "recommendation/channelSelected") {{
                  throw new Error("channel switch should be represented by the router route/changed action");
                }}
              }},
            }};
            const routed = [];
            const calls = [];
            const navigate = async (path) => {{
              routed.push(path);
              store.dispatch({{ type: "route/changed", route: {{ name: "tonight-channel", path, params: {{ channel: path.split("/").pop() }} }} }});
              return {{ path }};
            }};
            configureTonight({{
              root,
              store,
              api: {{
                async postV2(path, payload) {{
                  calls.push({{ path, payload }});
                  return {{ session_id: "session-42", channel: payload.channel, batch: {{ id: "series-batch", index: 2, items: [] }} }};
                }},
              }},
              navigate,
            }});
            const firstPage = renderTonight(state);
            const firstStage = firstPage.children.find((node) => node.className === "tonight-stage");
            const firstHero = firstStage.firstElementChild;
            const firstToolbar = firstStage.children[1];
            const firstInput = firstToolbar.children.flatMap((node) => node.children).find((node) => node.className === "tonight-reason");
            firstInput.value = "keep my reason";
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const seriesTab = collect(firstPage).find((node) => node.dataset?.channel === "series");
            if (!seriesTab?.onclick) throw new Error("series tab was not an interactive in-place control");
            await seriesTab.onclick();
            const secondPage = renderTonight(state);
            const secondStage = secondPage.children.find((node) => node.className === "tonight-stage");
            const secondToolbar = secondStage.children[1];
            const secondInput = secondToolbar.children.flatMap((node) => node.children).find((node) => node.className === "tonight-reason");
            const visible = collect(secondPage).map((node) => node.textContent).join(" ");
            if (rootReplacements !== 1 || root.firstElementChild !== firstPage || secondPage !== firstPage) throw new Error(`Tonight root remounted: ${{rootReplacements}}`);
            if (secondStage !== firstStage || secondStage.firstElementChild !== firstHero || secondToolbar !== firstToolbar) throw new Error("Tonight replaced stable stage/hero/toolbar nodes instead of updating in place");
            if (secondInput !== firstInput || secondInput.value !== "keep my reason") throw new Error("Tonight lost focused intent input identity/value");
            if (historyPaths.length !== 0 || routed.join() !== "/tonight/series" || state.activePath !== "/tonight/series") throw new Error("channel URL/state did not flow through router");
            if (secondStage.firstElementChild.className.includes("motion-enter")) throw new Error("Tonight hero reintroduced opacity entry animation after mount");
            if (!visible.includes("SeriesCandidate") || visible.includes("MovieCandidate")) throw new Error(`active content was not atomically switched: ${{visible}}`);
            secondInput.value = "更冷门的剧集";
            const nextButton = collect(secondToolbar).find((node) => node.className === "tonight-button tonight-button--signal");
            nextButton.onclick(); await Promise.resolve(); await Promise.resolve();
            const batchCalls = calls.filter((call) => call.path.startsWith("/api/v2/recommend/sessions/"));
            if (batchCalls.length !== 1 || batchCalls[0].payload.channel !== "\u7535\u89c6\u5267" || batchCalls[0].payload.reason !== "\u66f4\u51b7\u95e8\u7684\u5267\u96c6") throw new Error(`stable toolbar kept the old channel closure: ${{JSON.stringify(calls)}}`);
            console.log(JSON.stringify({{ rootReplacements, routed, calls: batchCalls, backgroundCalls: calls.filter((call) => !batchCalls.includes(call)), activePath: state.activePath, samePage: secondPage === firstPage, stableNodes: secondStage === firstStage && secondToolbar === firstToolbar && secondInput === firstInput }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["rootReplacements"])
        self.assertTrue(result["samePage"])
        self.assertTrue(result["stableNodes"])
        self.assertEqual("/tonight/series", result["activePath"])

    def test_tonight_restoring_state_uses_private_playlist_skeleton_not_empty_recommendations(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const root = new FakeElement("main");
            const state = {{ recommendation: {{
              activeChannel: "movie", restoring: true,
              channels: {{ movie: {{}}, series: {{}}, "anime-series": {{}} }},
            }} }};
            configureTonight({{ root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2() {{}} }} }});
            const page = renderTonight(state);
            const nodes = collectNodes(page);
            const restore = nodes.find((node) => node.classList?.contains("tonight-restore"));
            if (!restore || !page.textContent.includes("正在恢复你的私人片单")) throw new Error("private restore skeleton was not visible");
            if (nodes.some((node) => node.classList?.contains("tonight-counts"))) throw new Error("empty zero-count toolbar leaked during restore");
            if (page.textContent.includes("候选池 0") || page.textContent.includes("本批可见 0")) throw new Error("restore state pretended the recommendation was empty");
            console.log(JSON.stringify({{ text: page.textContent, restoreClass: restore.className }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("正在恢复你的私人片单", result["text"])

    def test_tonight_restore_skeleton_is_removed_before_ready_toolbar_is_patched(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const root = new FakeElement("main");
            const state = {{ recommendation: {{ activeChannel: "movie", restoring: true, channels: {{ movie: {{}}, series: {{}}, "anime-series": {{}} }} }} }};
            configureTonight({{ root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2() {{}} }} }});
            renderTonight(state);
            state.recommendation.restoring = false;
            state.recommendation.channels.movie = {{ pool_size: 20, matched_size: 18, visible_size: 1, active_batch: 1, batch: {{ index: 1, items: [{{ title: "Ready" }}] }} }};
            const page = renderTonight(state);
            const nodes = collectNodes(page);
            if (nodes.some((node) => node.classList?.contains("tonight-restore") || node.classList?.contains("tonight-restore__label"))) throw new Error("restore skeleton leaked into ready toolbar");
            if (nodes.filter((node) => node.classList?.contains("tonight-counts")).length !== 1) throw new Error("ready toolbar counts were not singular");
            console.log(JSON.stringify({{ text: page.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertNotIn("私人推荐正在回到现场", result["text"])

    def test_tonight_prewarms_each_hydrated_channel_hero_once(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const warmed = [];
            const item = (slug) => ({{
              item_key: `douban:${{slug}}`, title: slug, media_type: slug,
              poster: {{ url: `/media/${{slug}}.webp`, media_status: "ready" }},
            }});
            const channel = (slug) => ({{ sessionId: "session-prewarm", batch: {{ index: 1, items: [item(slug)] }} }});
            const state = {{ recommendation: {{
              sessionId: "session-prewarm", activeChannel: "movie",
              channels: {{ movie: channel("movie"), series: channel("series"), "anime-series": channel("anime") }},
            }} }};
            const root = new FakeElement("main");
            configureTonight({{
              root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2() {{}} }},
              preloadMedia(url) {{ warmed.push(url); return Promise.resolve(null); }},
            }});
            renderTonight(state); renderTonight(state);
            if (warmed.join(",") !== "/media/movie.webp,/media/series.webp,/media/anime.webp") throw new Error(`unexpected hero prewarm: ${{warmed}}`);
            console.log(JSON.stringify(warmed));
            '''
        )
        warmed = json.loads(output)
        self.assertEqual(3, len(warmed))

    def test_tonight_hero_filmstrip_switches_only_between_ready_local_posters_in_place(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            let autoRotations = 0;
            globalThis.setInterval = () => {{ autoRotations += 1; return autoRotations; }};
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const ready = (key, title) => ({{
              item_key: key, title, media_type: "电影", douban_rating: 8.8,
              poster: {{ url: `/media/${{title}}.webp`, media_status: "ready" }},
            }});
            const state = {{ recommendation: {{
              sessionId: "session-filmstrip", activeChannel: "movie",
              channels: {{
                movie: {{ sessionId: "session-filmstrip", pool_size: 4, matched_size: 4, visible_size: 4, active_batch: 1, batch: {{ index: 1, items: [
                  ready("douban:alpha", "Alpha"),
                  {{ item_key: "douban:missing", title: "Missing", media_type: "电影", poster: {{ media_status: "missing" }} }},
                  ready("douban:beta", "Beta"),
                  ready("douban:gamma", "Gamma"),
                ] }} }},
                series: {{}}, "anime-series": {{}},
              }},
            }} }};
            const root = new FakeElement("main");
            let rootReplacements = 0;
            root.replaceChildren = function(...nodes) {{ rootReplacements += 1; this.children = []; this.append(...nodes); }};
            configureTonight({{ root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2() {{}} }} }});
            const page = renderTonight(state);
            await flush();
            const stage = page.children.find((node) => node.classList?.contains("tonight-stage"));
            const hero = stage.firstElementChild;
            const carouselStage = collectNodes(hero).find((node) => node.classList?.contains("cinema-carousel__stage"));
            const stageContent = collectNodes(hero).find((node) => node.classList?.contains("cinema-carousel__stage-content"));
            const filmstrip = collectNodes(hero).find((node) => node.classList?.contains("cinema-carousel__track"));
            const buttons = collectNodes(filmstrip).filter((node) => node.classList?.contains("cinema-carousel__slide"));
            if (!hero.classList.contains("cinema-carousel") || !carouselStage || !stageContent || !filmstrip || buttons.length !== 3) throw new Error(`cinema carousel ready-only structure missing: ${{buttons.length}}`);
            if (filmstrip.classList.contains("tonight-hero-filmstrip")) throw new Error("new carousel inherited the legacy narrow filmstrip");
            if (buttons.some((button) => button.classList.contains("tonight-hero-filmstrip__button"))) throw new Error("new carousel slides inherited the legacy button layout");
            if (buttons.some((button) => collectNodes(button).some((node) => node.classList?.contains("tonight-hero-filmstrip__title")))) throw new Error("new carousel slide titles inherited legacy truncation rules");
            if (!stageContent.textContent.includes("Alpha")) throw new Error("first ready title was not featured");
            buttons[1].dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush();
            if (stage.firstElementChild !== hero || rootReplacements !== 1) throw new Error("hero selection remounted the page or hero node");
            if (!stageContent.textContent.includes("Beta") || stageContent.textContent.includes("Missing")) throw new Error(`filmstrip selected the wrong title: ${{stageContent.textContent}}`);
            const selected = buttons.filter((node) => node.getAttribute("aria-selected") === "true" && node.getAttribute("aria-current") === "true");
            if (selected.length !== 1 || !selected[0].textContent.includes("Beta")) throw new Error("filmstrip selection state did not follow the featured title");
            await flush();
            if (!stageContent.textContent.includes("Beta") || autoRotations !== 0) throw new Error("carousel rotated without an explicit user action");
            console.log(JSON.stringify({{ buttons: buttons.length, rootReplacements, selected: selected[0].textContent, autoRotations }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(3, result["buttons"])
        self.assertEqual(1, result["rootReplacements"])
        self.assertEqual(0, result["autoRotations"])
        carousel_source = (UI_ROOT / "js" / "components" / "cinema-carousel.js").read_text(encoding="utf-8")
        self.assertNotIn("setInterval", carousel_source)

    def test_tonight_hero_selection_survives_rerender_without_provider_item_key(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const ready = (title, year) => ({{
              title, year, media_type: "电影", douban_rating: 8.8,
              poster: {{ url: `/media/${{title}}-${{year}}.webp`, media_status: "ready" }},
            }});
            const state = {{ recommendation: {{
              sessionId: "session-fallback-identity", activeChannel: "movie",
              channels: {{
                movie: {{ sessionId: "session-fallback-identity", pool_size: 3, matched_size: 3, visible_size: 3, active_batch: 1, batch: {{ index: 1, items: [
                  ready("Alpha", 2020), ready("Beta", 2021), ready("Gamma", 2022),
                ] }} }},
                series: {{}}, "anime-series": {{}},
              }},
            }} }};
            const root = new FakeElement("main");
            configureTonight({{ root, store: {{ getState: () => state, dispatch() {{}} }}, api: {{ postV2() {{}} }} }});
            let page = renderTonight(state);
            let buttons = collectNodes(page).filter((node) => node.classList?.contains("cinema-carousel__slide"));
            buttons[1].dispatchEvent({{ type: "click", preventDefault() {{}} }});
            await flush();
            state.recommendation.channels.movie.batch.items = [
              {{ ...ready("Alpha", 2020), summary: "metadata refreshed" }},
              {{ ...ready("Beta", 2021), summary: "metadata refreshed" }},
              {{ ...ready("Gamma", 2022), summary: "metadata refreshed" }},
            ];
            page = renderTonight(state);
            await flush();
            const stageContent = collectNodes(page).find((node) => node.classList?.contains("cinema-carousel__stage-content"));
            buttons = collectNodes(page).filter((node) => node.classList?.contains("cinema-carousel__slide"));
            const selected = buttons.find((node) => node.getAttribute("aria-selected") === "true");
            if (!stageContent?.textContent.includes("Beta") || !selected?.textContent.includes("Beta")) {{
              throw new Error(`fallback identity selection was lost after rerender: ${{stageContent?.textContent}} / ${{selected?.textContent}}`);
            }}
            console.log(JSON.stringify({{ stage: stageContent.textContent, selected: selected.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("Beta", result["stage"])

    def test_cinema_carousel_preserves_vertical_wheel_and_uses_explicit_horizontal_intent(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderCinemaCarousel }} = await import("{module_url('js/components/cinema-carousel.js')}");
            const carousel = renderCinemaCarousel({{ slides: [
              {{ id: "one", title: "One", media: {{ url: "/media/one.webp", status: "ready" }} }},
              {{ id: "two", title: "Two", media: {{ url: "/media/two.webp", status: "ready" }} }},
              {{ id: "three", title: "Three", media: {{ url: "/media/three.webp", status: "ready" }} }},
            ] }});
            const track = collectNodes(carousel).find((node) => node.classList?.contains("cinema-carousel__track"));
            let verticalPrevented = false;
            track.dispatchEvent({{ type: "wheel", deltaX: 0, deltaY: 160, shiftKey: false, preventDefault() {{ verticalPrevented = true; }} }});
            if (verticalPrevented || carousel.dataset.index !== "0") throw new Error(`vertical page wheel was hijacked: ${{JSON.stringify({{ verticalPrevented, index: carousel.dataset.index }})}}`);
            let horizontalPrevented = false;
            track.dispatchEvent({{ type: "wheel", deltaX: 160, deltaY: 4, shiftKey: false, preventDefault() {{ horizontalPrevented = true; }} }});
            if (!horizontalPrevented || carousel.dataset.index !== "1") throw new Error("horizontal wheel did not advance the filmstrip");
            let shiftPrevented = false;
            track.dispatchEvent({{ type: "wheel", deltaX: 0, deltaY: 160, shiftKey: true, preventDefault() {{ shiftPrevented = true; }} }});
            if (!shiftPrevented || carousel.dataset.index !== "2") throw new Error("Shift + wheel did not express horizontal filmstrip intent");
            console.log(JSON.stringify({{ verticalPrevented, horizontalPrevented, shiftPrevented, index: carousel.dataset.index }}));
            '''
        )
        result = json.loads(output)
        self.assertFalse(result["verticalPrevented"])
        self.assertTrue(result["horizontalPrevented"])
        self.assertTrue(result["shiftPrevented"])
        self.assertEqual("2", result["index"])

    def test_tonight_enriches_visible_placeholder_summaries_once_and_patches_in_place(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            let state = {{ activePath: "/tonight/movie", recommendation: {{
              sessionId: "session-meta", activeChannel: "movie",
              channels: {{
                movie: {{ sessionId: "session-meta", pool_size: 2, matched_size: 2, visible_size: 2, batch: {{ index: 1, items: [
                  {{ item_key: "douban:42", title: "待补简介", media_type: "电影", genres: ["剧情"], summary: "由 CineScope 精选扩展池补入的电影候选：待补简介。优先通过公共来源补图。", poster: {{ url: "/media/a.webp", media_status: "ready" }} }},
                  {{ item_key: "douban:43", title: "已有简介", media_type: "电影", genres: ["剧情"], summary: "这是一段已经核对的真实简介。", poster: {{ url: "/media/b.webp", media_status: "ready" }} }},
                ] }} }},
                series: {{}}, "anime-series": {{}},
              }},
            }} }};
            const posts = []; const actions = [];
            const store = {{
              getState: () => state,
              dispatch(action) {{ actions.push(action); state = reduceUiState(state, action); }},
            }};
            const root = new FakeElement("main");
            configureTonight({{
              root, store,
              api: {{
                async postV2(path, payload) {{
                  posts.push({{ path, payload }});
                  return {{ item_key: "douban:42", title: "待补简介", media_type: "电影", year: 2024, item: {{ title: "待补简介", media_type: "电影", genres: ["剧情"], summary: "后台核对后的真实剧情简介。" }}, poster: {{ url: "/media/a.webp", media_status: "ready" }} }};
                }},
              }},
              preloadMedia: async () => null,
            }});
            const page = renderTonight(state);
            await flush();
            renderTonight(state);
            await flush();
            const enrichCalls = posts.filter((call) => call.path.includes("/enrich"));
            if (enrichCalls.length !== 1 || enrichCalls[0].path !== "/api/v2/titles/douban%3A42/enrich") throw new Error(`visible metadata enrichment was not bounded and deduplicated: ${{JSON.stringify(posts)}}`);
            if (!actions.some((action) => action.type === "recommendation/itemHydrated" && action.itemKey === "douban:42")) throw new Error("enriched title was not patched into the active recommendation");
            if (!page.textContent.includes("后台核对后的真实剧情简介。")) throw new Error(`patched summary was not rendered in place: ${{page.textContent}}`);
            console.log(JSON.stringify({{ posts, actions: actions.map((action) => action.type), text: page.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, len([call for call in result["posts"] if "/enrich" in call["path"]]))
        self.assertIn("recommendation/itemHydrated", result["actions"])

    def test_tonight_queues_visible_largely_english_synopsis_for_localization(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            let state = {{ activePath: "/tonight/series", recommendation: {{
              sessionId: "session-localize", activeChannel: "series",
              channels: {{
                movie: {{}},
                series: {{ sessionId: "session-localize", pool_size: 1, matched_size: 1, visible_size: 1, batch: {{ index: 1, items: [{{
                  item_key: "external:tvmaze-3415", title: "Tomorrow's Worlds", media_type: "电视剧", genres: ["科幻", "历史"],
                  summary: "Historian Dominic Sandbrook and leading creators tell the story of science fiction across television and cinema.",
                  poster: {{ url: "/media/worlds.webp", media_status: "ready" }},
                }}] }} }},
                "anime-series": {{}},
              }},
            }} }};
            const posts = [];
            const store = {{ getState: () => state, dispatch(action) {{ state = reduceUiState(state, action); }} }};
            const root = new FakeElement("main");
            configureTonight({{
              root, store,
              api: {{ async postV2(path, payload) {{
                posts.push({{ path, payload }});
                return {{ item_key: "external:tvmaze-3415", item: {{ summary: "经过核验的中文简介。", genres: ["科幻", "历史"] }} }};
              }} }},
              preloadMedia: async () => null,
            }});
            const page = renderTonight(state); await flush();
            const enrichCalls = posts.filter((call) => call.path.includes("/enrich"));
            if (enrichCalls.length !== 1) throw new Error(`English synopsis was not queued for localization: ${{JSON.stringify(posts)}}`);
            if (page.textContent.includes("Historian Dominic")) throw new Error("English synopsis was shown before localization completed");
            console.log(JSON.stringify({{ posts, text: page.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, len([call for call in result["posts"] if "/enrich" in call["path"]]))
        self.assertNotIn("Historian Dominic", result["text"])

    def test_tonight_missing_visible_media_jobs_poll_and_refresh_session_in_place(self):
        output = run_node_module(
            f'''
            import {{ configureTonight, renderTonight }} from "{module_url('js/features/tonight.js')}";

            class FakeElement {{
              constructor(tagName) {{ this.tagName = tagName.toUpperCase(); this.children = []; this.dataset = {{}}; this.attributes = new Map(); this.className = ""; this.textContent = ""; this.disabled = false; this.value = ""; }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const timers = [];
            const posts = [];
            const gets = [];
            const actions = [];
            const makeItem = (id, title, status = "missing") => ({{ item_key: id, title, year: 2024, media_type: "movie", poster: {{ url: status === "ready" ? `/media/${{id.replace(/[^a-z0-9]/gi, "-")}}.webp` : "", media_status: status }} }});
            const state = {{ activePath: "/tonight/movie", recommendation: {{ sessionId: "session-42", activeChannel: "movie", channels: {{ movie: {{ sessionId: "session-42", active_batch: 1, batch: {{ index: 1, items: [makeItem("douban:1", "Missing One"), makeItem("douban:2", "Missing Two"), makeItem("douban:3", "Ready", "ready")] }} }}, series: {{}}, "anime-series": {{}} }} }} }};
            const refreshedSession = {{ id: "session-42", channels: {{ movie: {{ batch: {{ index: 1, items: [makeItem("douban:1", "Ready One", "ready"), makeItem("douban:2", "Degraded Two", "degraded")] }} }} }} }};
            const store = {{
              getState: () => state,
              dispatch(action) {{ actions.push(action); if (action.type === "recommendation/sessionReceived") state.recommendation.channels.movie.batch.items = Object.values(action.session.channels)[0].batch.items; }},
            }};
            const api = {{
              async postV2(path, payload) {{ posts.push({{ path, payload }}); return {{ job_id: `job-${{posts.length}}`, state: "queued" }}; }},
              async getV2(path) {{ gets.push(path); return path.startsWith("/api/v2/media/jobs/") ? {{ id: path.split("/").pop(), state: "ready", result: {{ status: "ready", local_url: "/media/ready.webp" }} }} : refreshedSession; }},
            }};
            configureTonight({{ root: new FakeElement("main"), store, api, setTimer(callback) {{ timers.push(callback); return timers.length; }}, clearTimer() {{}}, mediaPollInterval: 1 }});
            const page = renderTonight(state);
            const stage = page.children.find((node) => node.className === "tonight-stage");
            const hero = stage.firstElementChild;
            const posterPosts = posts.filter((call) => call.path === "/api/v2/media/jobs");
            if (posterPosts.length !== 2) throw new Error(`expected hero+visible missing posters to enqueue once by item identity, got ${{posterPosts.length}}`);
            if (posterPosts.some((call) => call.payload.kind !== "poster" || !call.payload.identity_key)) throw new Error("Tonight media job payload was not schema-bound");
            for (let index = 0; index < 4; index += 1) await Promise.resolve();
            await timers.shift()();
            await timers.shift()();
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            if (!gets.includes("/api/v2/recommend/sessions/session-42")) throw new Error(`ready media did not refresh session: ${{gets}}`);
            renderTonight(state);
            if (page.children.find((node) => node.className === "tonight-stage").firstElementChild !== hero) throw new Error("media refresh remounted Tonight hero instead of patching in place");
            if (!actions.some((action) => action.type === "recommendation/sessionReceived" && action.source === "media-refresh")) throw new Error("refreshed session was not dispatched with media-refresh source");
            console.log(JSON.stringify({{ posts, gets, actions: actions.map((action) => action.type), sameHero: stage.firstElementChild === hero }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, len([call for call in result["posts"] if call["path"] == "/api/v2/media/jobs"]))
        self.assertIn("/api/v2/recommend/sessions/session-42", result["gets"])

    def test_tonight_prewarms_bounded_hero_portraits_before_detail_open(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ configureTonight, renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const posts = [];
            const gets = [];
            const hero = {{
              item_key: "douban:hero",
              title: "Hero Work",
              year: 2026,
              media_type: "movie",
              poster: {{ url: "/media/hero.webp", media_status: "ready" }},
            }};
            const state = {{ activePath: "/tonight/movie", recommendation: {{
              sessionId: "session-hero",
              activeChannel: "movie",
              channels: {{ movie: {{ sessionId: "session-hero", batch: {{ index: 1, items: [hero] }} }}, series: {{}}, "anime-series": {{}} }},
            }} }};
            const title = {{
              item_key: "douban:hero",
              title: "Hero Work",
              media_type: "movie",
              people: [
                {{ id: "person-director", name: "Director", role: "director", portrait: {{ url: "", media_status: "missing" }} }},
                {{ id: "person-ready", name: "Ready Cast", role: "cast", portrait: {{ url: "/media/ready.webp", media_status: "ready" }} }},
                {{ id: "person-cast-1", name: "Cast One", role: "cast", portrait: {{ url: "", media_status: "missing" }} }},
                {{ id: "person-cast-2", name: "Cast Two", role: "cast", portrait: {{ url: "", media_status: "missing" }} }},
                {{ id: "person-outside-bound", name: "Cast Three", role: "cast", portrait: {{ url: "", media_status: "missing" }} }},
              ],
            }};
            const api = {{
              async getV2(path) {{ gets.push(path); return title; }},
              async postV2(path, payload) {{ posts.push({{ path, payload }}); return {{ job_id: `portrait-${{posts.length}}`, state: "queued" }}; }},
            }};
            configureTonight({{
              root: new FakeElement("main"),
              store: {{ getState: () => state, dispatch() {{}} }},
              api,
              preloadMedia: async () => null,
            }});
            renderTonight(state);
            await flush();
            renderTonight(state);
            await flush();
            const portraits = posts.filter((call) => call.payload.kind === "portrait");
            if (gets.filter((path) => path === "/api/v2/titles/douban%3Ahero").length !== 1) throw new Error(`hero title warmup was not deduplicated: ${{gets}}`);
            if (portraits.length !== 3) throw new Error(`expected three missing portraits inside the first four credits, got ${{JSON.stringify(portraits)}}`);
            if (portraits.some((call) => call.path !== "/api/v2/media/jobs" || !call.payload.identity_key || !call.payload.person_name)) throw new Error("portrait warmup payload was not schema-bound");
            if (portraits.some((call) => call.payload.media_type !== "movie" || call.payload.work_context?.[0] !== "Hero Work")) throw new Error("portrait warmup lost title context");
            if (portraits.some((call) => call.payload.identity_key === "person-ready" || call.payload.identity_key === "person-outside-bound")) throw new Error("portrait warmup included ready or out-of-bound credits");
            console.log(JSON.stringify({{ gets, portraits }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(3, len(result["portraits"]))

    def test_session_candidate_counts_flow_into_channels_and_persist(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ createEmptyUiState, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const values = new Map();
            const storage = {{
              getItem(key) {{ return values.get(key) ?? null; }},
              setItem(key, value) {{ values.set(key, String(value)); }},
            }};
            const channel = (pool) => ({{
              pool_size: pool, matched_size: pool - 1, visible_size: 5, active_batch: 3,
              batch: {{ id: `batch-${{pool}}`, index: 3, items: [], pool_size: pool, matched_size: pool - 1, visible_size: 5 }},
            }});
            const session = {{
              id: "session-160",
              candidate_counts: {{ target_size: 160, returned_size: 192 }},
              intent: {{}}, chips: [],
              channels: {{ "电影": channel(85), "电视剧": channel(54), "动漫": channel(53) }},
            }};
            const received = reduceUiState(createEmptyUiState(), {{ type: "recommendation/sessionReceived", session }});
            for (const slug of ["movie", "series", "anime-series"]) {{
              const counts = received.recommendation.channels[slug].candidate_counts;
              if (counts?.target_size !== 160 || counts?.returned_size !== 192) {{
                throw new Error(`session candidate counts did not enter ${{slug}} state: ${{JSON.stringify(counts)}}`);
              }}
            }}
            persistUiState(received, storage);
            const restored = restoreUiState(storage);
            const restoredCounts = restored.recommendation.channels["anime-series"].candidate_counts;
            if (restoredCounts?.target_size !== 160 || restoredCounts?.returned_size !== 192) {{
              throw new Error(`candidate counts did not survive persistence: ${{JSON.stringify(restoredCounts)}}`);
            }}
            console.log(JSON.stringify({{ received: received.recommendation.channels, restored: restored.recommendation.channels }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(160, result["restored"]["anime-series"]["candidate_counts"]["target_size"])
        self.assertEqual(192, result["restored"]["anime-series"]["candidate_counts"]["returned_size"])

    def test_legacy_unknown_target_survives_store_and_renders_dash(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const {{ createEmptyUiState, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const values = new Map();
            const storage = {{
              getItem(key) {{ return values.get(key) ?? null; }},
              setItem(key, value) {{ values.set(key, String(value)); }},
            }};
            const channel = (pool) => ({{
              pool_size: pool, matched_size: pool, visible_size: 5, active_batch: 3,
              batch: {{ id: `legacy-${{pool}}`, index: 3, items: [], pool_size: pool, matched_size: pool, visible_size: 5 }},
            }});
            const legacySession = {{
              id: "legacy-session", candidate_counts: {{ target_size: null, returned_size: 192 }},
              intent: {{}}, chips: [],
              channels: {{ "电影": channel(85), "电视剧": channel(54), "动漫": channel(53) }},
            }};
            const legacy = reduceUiState(createEmptyUiState(), {{ type: "recommendation/sessionReceived", session: legacySession }});
            persistUiState(legacy, storage);
            const restored = restoreUiState(storage);
            for (const slug of ["movie", "series", "anime-series"]) {{
              const counts = restored.recommendation.channels[slug].candidate_counts;
              if (counts?.target_size !== null || counts?.returned_size !== 192) {{
                throw new Error(`legacy unknown target was not preserved for ${{slug}}: ${{JSON.stringify(counts)}}`);
              }}
            }}
            const legacyVisible = renderTonight(legacy).textContent;
            if (!legacyVisible.includes("目标 —") || legacyVisible.includes("目标 0") || !legacyVisible.includes("实际返回 192")) {{
              throw new Error(`legacy counts were rendered inaccurately: ${{legacyVisible}}`);
            }}

            const exactSession = structuredClone(legacySession);
            exactSession.id = "exact-session";
            exactSession.candidate_counts.target_size = 160;
            const exact = reduceUiState(createEmptyUiState(), {{ type: "recommendation/sessionReceived", session: exactSession }});
            const exactVisible = renderTonight(exact).textContent;
            if (!exactVisible.includes("目标 160") || !exactVisible.includes("实际返回 192")) {{
              throw new Error(`new-session counts lost exact values: ${{exactVisible}}`);
            }}
            console.log(JSON.stringify({{ legacyVisible, exactVisible, restored: restored.recommendation.channels }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("目标 —", result["legacyVisible"])
        self.assertIn("目标 160", result["exactVisible"])
        self.assertIsNone(result["restored"]["anime-series"]["candidate_counts"]["target_size"])

    def test_same_session_target_presence_distinguishes_absent_null_and_exact(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const {{ createEmptyUiState, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const values = new Map();
            const storage = {{
              getItem(key) {{ return values.get(key) ?? null; }},
              setItem(key, value) {{ values.set(key, String(value)); }},
            }};
            const channel = (pool) => ({{
              pool_size: pool, matched_size: pool, visible_size: 5, active_batch: 3,
              batch: {{ id: `upgrade-${{pool}}`, index: 3, items: [], pool_size: pool, matched_size: pool, visible_size: 5 }},
            }});
            const session = (candidateCounts) => ({{
              id: "legacy-upgrade-session", candidate_counts: candidateCounts,
              intent: {{}}, chips: [],
              channels: {{ "电影": channel(85), "电视剧": channel(54), "动漫": channel(53) }},
            }});

            const cached = reduceUiState(createEmptyUiState(), {{
              type: "recommendation/sessionReceived",
              session: session({{ target_size: 0, returned_size: 192 }}),
            }});
            persistUiState(cached, storage);
            const restored = restoreUiState(storage);
            const routed = {{
              ...restored,
              activePath: "/tonight/anime-series",
              recommendation: {{ ...restored.recommendation, activeChannel: "anime-series" }},
            }};
            const restoreAction = (candidateCounts) => ({{
              type: "recommendation/sessionReceived", source: "restore",
              expectedSessionId: "legacy-upgrade-session", channel: "anime-series",
              route: "/tonight/anime-series", session: session(candidateCounts),
            }});

            const unknown = reduceUiState(routed, restoreAction({{ target_size: null, returned_size: 192 }}));
            for (const slug of ["movie", "series", "anime-series"]) {{
              const counts = unknown.recommendation.channels[slug].candidate_counts;
              if (counts?.target_size !== null || counts?.returned_size !== 192) {{
                throw new Error(`explicit null did not clear cached target for ${{slug}}: ${{JSON.stringify(counts)}}`);
              }}
            }}
            const unknownVisible = renderTonight(unknown).textContent;
            if (!unknownVisible.includes("目标 —") || unknownVisible.includes("目标 0")) {{
              throw new Error(`explicit null rendered a cached zero: ${{unknownVisible}}`);
            }}

            const exact = reduceUiState(unknown, restoreAction({{ target_size: 160, returned_size: 192 }}));
            const exactVisible = renderTonight(exact).textContent;
            if (exact.recommendation.channels["anime-series"].candidate_counts.target_size !== 160 || !exactVisible.includes("目标 160")) {{
              throw new Error(`exact server target was not authoritative: ${{exactVisible}}`);
            }}
            const absent = reduceUiState(exact, restoreAction({{ returned_size: 192 }}));
            if (absent.recommendation.channels["anime-series"].candidate_counts.target_size !== 160) {{
              throw new Error(`absent server target did not preserve the exact cached fallback: ${{JSON.stringify(absent.recommendation.channels)}}`);
            }}
            console.log(JSON.stringify({{
              absent: absent.recommendation.channels["anime-series"].candidate_counts,
              unknown: unknown.recommendation.channels["anime-series"].candidate_counts,
              unknownVisible, exactVisible,
            }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(160, result["absent"]["target_size"])
        self.assertIsNone(result["unknown"]["target_size"])
        self.assertIn("目标 —", result["unknownVisible"])
        self.assertIn("目标 160", result["exactVisible"])

    def test_tonight_visibly_exposes_target_returned_channel_and_batch_counts(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ renderTonight }} = await import("{module_url('js/features/tonight.js')}");
            const state = {{
              recommendation: {{
                sessionId: "session-160", activeChannel: "anime-series",
                channels: {{
                  movie: {{ candidate_counts: {{ target_size: 160, returned_size: 192 }}, pool_size: 85, matched_size: 84, visible_size: 24, active_batch: 1, batch: {{ index: 1, items: [] }} }},
                  series: {{ candidate_counts: {{ target_size: 160, returned_size: 192 }}, pool_size: 54, matched_size: 54, visible_size: 24, active_batch: 1, batch: {{ index: 1, items: [] }} }},
                  "anime-series": {{ candidate_counts: {{ target_size: 160, returned_size: 192 }}, pool_size: 53, matched_size: 53, visible_size: 5, active_batch: 3, batch: {{ index: 3, items: [] }} }},
                }},
              }},
            }};
            const visible = renderTonight(state).textContent;
            for (const expected of ["目标 160", "实际返回 192", "候选池 53", "匹配 53", "本批可见 5", "当前批次 3"]) {{
              if (!visible.includes(expected)) throw new Error(`missing visible recommendation count: ${{expected}} in ${{visible}}`);
            }}
            console.log(JSON.stringify({{ visible }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("目标 160", result["visible"])
        self.assertIn("当前批次 3", result["visible"])

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

    def test_command_lens_numeric_chip_removal_omits_field_in_replacement_intent(self):
        output = run_node_module(
            f'''
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
              focus() {{}}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            Object.defineProperty(FakeElement.prototype, "innerHTML", {{
              set() {{ throw new Error("innerHTML must not be used"); }},
            }});
            globalThis.document = {{
              createElement: (tagName) => new FakeElement(tagName),
              addEventListener() {{}},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            const {{ configureCommandLens, openCommandLens }} = await import("{module_url('js/features/command-lens.js')}");
            const root = new FakeElement("div");
            const calls = [];
            const state = {{
              recommendation: {{
                sessionId: "session-1",
                activeChannel: "movie",
                intentSessionId: "session-1",
                intent: {{}},
                channels: {{ movie: {{ sessionId: "session-1" }} }},
              }},
              commandLens: {{
                draft: "",
                chips: [],
              }},
            }};
            configureCommandLens({{
              root,
              store: {{ getState: () => state, dispatch() {{}} }},
              api: {{
                async postV2(path, payload) {{
                  calls.push({{ path, payload }});
                  return {{ id: `session-${{calls.length + 1}}`, intent: {{ genres: ["悬疑"], pace: "fast" }}, chips: [], channels: {{}} }};
                }},
              }},
            }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const numericFields = [
              ["runtime_max", 90],
              ["episode_runtime_max", 30],
              ["year_min", 2015],
              ["year_max", 2025],
              ["quality_floor", 8.5],
            ];
            for (const [field, value] of numericFields) {{
              state.recommendation.intent = {{ genres: ["悬疑"], pace: "fast", [field]: value, free_text: "server-owned" }};
              state.commandLens.chips = [{{ key: field, label: `${{field}}=${{value}}`, value, removable: true }}];
              openCommandLens();
              const remove = collect(root).find((node) => node.className === "intent-chip__remove");
              if (!remove || remove.disabled) throw new Error(`${{field}} removal was not available for matching grounded intent`);
              await remove.onclick();
              const intent = calls.at(-1).payload.intent;
              if (Object.hasOwn(intent, field)) throw new Error(`${{field}} must be omitted, got ${{intent[field]}}`);
              if (intent.pace !== "fast" || intent.genres[0] !== "悬疑") throw new Error("unrelated structured fields were not preserved");
            }}
            console.log(JSON.stringify(calls));
            '''
        )
        calls = json.loads(output)
        fields = ("runtime_max", "episode_runtime_max", "year_min", "year_max", "quality_floor")
        self.assertEqual(len(fields), len(calls))
        for field, call in zip(fields, calls):
            with self.subTest(field=field):
                self.assertNotIn(field, call["payload"]["intent"])
                self.assertEqual("fast", call["payload"]["intent"]["pace"])

    def test_command_lens_can_close_after_success_and_handoff_the_new_session(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ configureCommandLens, openCommandLens, submitIntent }} = await import("{module_url('js/features/command-lens.js')}");
            const root = new FakeElement("div");
            const received = [];
            configureCommandLens({{
              root,
              closeOnSuccess: true,
              onSession(session) {{ received.push(session.id); }},
              store: {{
                getState: () => ({{ commandLens: {{ draft: "", chips: [] }}, recommendation: {{ channels: {{}} }} }}),
                dispatch() {{}},
              }},
              api: {{
                async postV2() {{ return {{ id: "session-fresh", intent: {{ media_types: ["电影"] }}, chips: [], channels: {{}} }}; }},
              }},
            }});
            openCommandLens("高分剧情片");
            await submitIntent("高分剧情片");
            if (received.join(",") !== "session-fresh") throw new Error(`new session was not handed off: ${{received}}`);
            if (root.children.length !== 0) throw new Error("successful command lens stayed open instead of returning to recommendations");
            console.log(JSON.stringify({{ received, openChildren: root.children.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["session-fresh"], result["received"])
        self.assertEqual(0, result["openChildren"])

    def test_app_replacement_session_resets_history_while_same_session_restore_merges(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");

            const channel = (sessionId, batchId, index, pool) => ({{
              sessionId,
              batchIndex: index,
              batchIds: [batchId],
              active_batch: index,
              pool_size: pool,
              matched_size: pool - 1,
              visible_size: 2,
              batch: {{ id: batchId, index, items: [], pool_size: pool, matched_size: pool - 1, visible_size: 2 }},
            }});
            const state = {{
              activePath: "/tonight/movie",
              activeParams: {{ channel: "movie" }},
              recommendation: {{
                sessionId: "old-session",
                activeChannel: "movie",
                intent: {{ genres: ["旧类型"] }},
                intentSessionId: "old-session",
                channels: {{
                  movie: channel("old-session", "old-movie-batch", 7, 70),
                  series: channel("old-session", "old-series-batch", 6, 60),
                  "anime-series": channel("old-session", "old-anime-batch", 5, 50),
                }},
              }},
              commandLens: {{ draft: "旧意图", chips: [{{ key: "genre", label: "旧类型", value: "旧类型", removable: true }}] }},
              rail: {{ mode: "expanded" }}, scrollByRoute: {{}}, candidateTray: {{ itemIds: [], context: {{}} }},
            }};
            const session = {{
              id: "new-session",
              intent: {{ genres: ["新类型"] }},
              chips: [{{ key: "genre", label: "新类型", value: "新类型", removable: true }}],
              channels: {{
                "电影": {{ pool_size: 11, matched_size: 8, visible_size: 2, active_batch: 1, batch: {{ id: "new-movie-batch", index: 1, items: [], pool_size: 11, matched_size: 8, visible_size: 2 }} }},
                "电视剧": {{ pool_size: 12, matched_size: 9, visible_size: 2, active_batch: 1, batch: {{ id: "new-series-batch", index: 1, items: [], pool_size: 12, matched_size: 9, visible_size: 2 }} }},
                "动漫": {{ pool_size: 13, matched_size: 10, visible_size: 2, active_batch: 1, batch: {{ id: "new-anime-batch", index: 1, items: [], pool_size: 13, matched_size: 10, visible_size: 2 }} }},
              }},
            }};
            const replaced = reduceUiState(state, {{ type: "recommendation/sessionReceived", session }});
            for (const [slug, expectedBatch, expectedPool] of [["movie", "new-movie-batch", 11], ["series", "new-series-batch", 12], ["anime-series", "new-anime-batch", 13]]) {{
              const current = replaced.recommendation.channels[slug];
              if (current.sessionId !== "new-session") throw new Error(`${{slug}} did not receive the new session pointer`);
              if (current.batchIds.join(",") !== expectedBatch || current.batchIndex !== 1) throw new Error(`${{slug}} leaked old history: ${{JSON.stringify(current)}}`);
              if (current.pool_size !== expectedPool || current.batch.id !== expectedBatch) throw new Error(`${{slug}} leaked old counts or active batch`);
            }}
            if (replaced.recommendation.intentSessionId !== "new-session") throw new Error("structured intent session was not recorded in memory");

            const sameSession = structuredClone(session);
            sameSession.channels["电影"].batch = {{ id: "new-movie-restored", index: 2, items: [], pool_size: 11, matched_size: 8, visible_size: 2 }};
            sameSession.channels["电影"].active_batch = 2;
            const restored = reduceUiState(replaced, {{ type: "recommendation/sessionReceived", session: sameSession, source: "restore", expectedSessionId: "new-session", channel: "movie", route: "/tonight/movie" }});
            const movieIds = restored.recommendation.channels.movie.batchIds;
            if (movieIds.join(",") !== "new-movie-batch,new-movie-restored") throw new Error(`same-session restore did not merge history: ${{movieIds}}`);
            console.log(JSON.stringify({{ replaced: replaced.recommendation, restored: restored.recommendation }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["new-movie-batch"], result["replaced"]["channels"]["movie"]["batchIds"])
        self.assertEqual(["new-movie-batch", "new-movie-restored"], result["restored"]["channels"]["movie"]["batchIds"])

    def test_same_session_restore_preserves_other_channel_session_pointer_and_history(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
            const state = {{
              activePath: "/tonight/movie", activeParams: {{ channel: "movie" }},
              recommendation: {{
                sessionId: "movie-session", activeChannel: "movie",
                channels: {{
                  movie: {{ sessionId: "movie-session", batchIndex: 1, batchIds: ["movie-old"] }},
                  series: {{ sessionId: "series-session", batchIndex: 4, batchIds: ["series-own-history"] }},
                  "anime-series": {{ sessionId: "movie-session", batchIndex: 2, batchIds: ["anime-old"] }},
                }},
              }},
              commandLens: {{ draft: "", chips: [] }}, rail: {{ mode: "expanded" }},
              scrollByRoute: {{}}, candidateTray: {{ itemIds: [], context: {{}} }},
            }};
            const restored = reduceUiState(state, {{
              type: "recommendation/sessionReceived", source: "restore", expectedSessionId: "movie-session",
              channel: "movie", route: "/tonight/movie",
              session: {{
                id: "movie-session", intent: {{}}, chips: [],
                channels: {{
                  "电影": {{ batch: {{ id: "movie-restored", index: 2, items: [] }} }},
                  "电视剧": {{ batch: {{ id: "series-from-movie-session", index: 2, items: [] }} }},
                  "动漫": {{ batch: {{ id: "anime-restored", index: 3, items: [] }} }},
                }},
              }},
            }});
            const series = restored.recommendation.channels.series;
            if (series.sessionId !== "series-session" || series.batchIndex !== 4 || series.batchIds.join(",") !== "series-own-history") {{
              throw new Error(`other channel pointer/history was overwritten: ${{JSON.stringify(series)}}`);
            }}
            console.log(JSON.stringify(series));
            '''
        )
        series = json.loads(output)
        self.assertEqual("series-session", series["sessionId"])
        self.assertEqual(["series-own-history"], series["batchIds"])

    def test_persisted_chips_are_not_editable_until_matching_structured_intent_restores(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.dataset = {{}};
                this.attributes = new Map(); this.className = ""; this.textContent = "";
                this.value = ""; this.hidden = false; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              focus() {{}}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag), addEventListener() {{}} }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ configureCommandLens, openCommandLens, syncCommandLensState }} = await import("{module_url('js/features/command-lens.js')}");
            const root = new FakeElement("div");
            const state = {{
              recommendation: {{ sessionId: "session-1", activeChannel: "movie", channels: {{ movie: {{ sessionId: "session-1" }} }} }},
              commandLens: {{ draft: "", chips: [{{ key: "genre", label: "悬疑", value: "悬疑", removable: true }}] }},
            }};
            const store = {{ getState: () => state, dispatch() {{}} }};
            configureCommandLens({{ root, store, api: {{ postV2() {{ throw new Error("must not submit"); }} }} }});
            openCommandLens();
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            let buttons = collect(root).filter((node) => node.className === "intent-chip__edit" || node.className === "intent-chip__remove");
            if (!buttons.length || buttons.some((button) => !button.disabled)) throw new Error("persisted chips were editable without structured intent");

            state.recommendation.intent = {{ genres: ["悬疑"], free_text: "server-owned" }};
            state.recommendation.intentSessionId = "session-1";
            syncCommandLensState(state);
            buttons = collect(root).filter((node) => node.className === "intent-chip__edit" || node.className === "intent-chip__remove");
            if (buttons.some((button) => button.disabled)) throw new Error("matching restored structured intent did not unlock chips");
            console.log(JSON.stringify({{ buttonCount: buttons.length, enabled: buttons.every((button) => !button.disabled) }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["enabled"])

    def test_stale_session_restore_cannot_overwrite_new_session_or_new_route(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ createTonightRestoreGate, reduceUiState }} = await import("{module_url('js/app.js')}");
            const deferred = () => {{
              let resolve, reject;
              const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }});
              return {{ promise, resolve, reject }};
            }};
            const channelState = (sessionId, batchId) => ({{ sessionId, batchIndex: 1, batchIds: [batchId] }});
            let state = {{
              activePath: "/tonight/movie", activeParams: {{ channel: "movie" }},
              recommendation: {{
                sessionId: "old-session", activeChannel: "movie",
                channels: {{
                  movie: channelState("old-session", "old-batch"),
                  series: channelState("old-session", "old-series"),
                  "anime-series": channelState("old-session", "old-anime"),
                }},
              }},
              commandLens: {{ draft: "", chips: [] }}, rail: {{ mode: "expanded" }},
              scrollByRoute: {{}}, candidateTray: {{ itemIds: [], context: {{}} }},
            }};
            const actions = [];
            const store = {{
              getState: () => state,
              dispatch(action) {{ actions.push(action); state = reduceUiState(state, action); return action; }},
            }};
            const requests = [];
            const statuses = [];
            const gate = createTonightRestoreGate({{
              store,
              restoreSession(sessionId, options) {{
                const pending = deferred();
                requests.push({{ sessionId, signal: options.signal, pending }});
                return pending.promise;
              }},
              setStatus(message) {{ statuses.push(message); }},
            }});
            const route = {{ path: "/tonight/movie", name: "tonight-channel", params: {{ channel: "movie" }} }};
            const oldRestore = gate.restore(route, "今晚");
            store.dispatch({{
              type: "recommendation/sessionReceived",
              session: {{
                id: "new-session", intent: {{ genres: ["新"] }}, chips: [],
                channels: {{
                  "电影": {{ batch: {{ id: "new-batch", index: 1, items: [] }} }},
                  "电视剧": {{ batch: {{ id: "new-series", index: 1, items: [] }} }},
                  "动漫": {{ batch: {{ id: "new-anime", index: 1, items: [] }} }},
                }},
              }},
            }});
            gate.invalidate();
            if (!requests[0].signal.aborted) throw new Error("new session invalidation did not abort the stale GET");
            requests[0].pending.resolve({{ id: "old-session", intent: {{ genres: ["旧"] }}, chips: [], channels: {{}} }});
            await oldRestore;
            if (state.recommendation.sessionId !== "new-session") throw new Error("stale GET replaced the new session");
            if (actions.some((action) => action.source === "restore" && action.session?.id === "old-session")) throw new Error("stale GET dispatched");

            const routeRestore = gate.restore(route, "今晚");
            store.dispatch({{ type: "route/changed", route: {{ path: "/universe", name: "universe", params: {{}} }} }});
            gate.invalidate();
            if (!requests[1].signal.aborted) throw new Error("route invalidation did not abort the GET");
            requests[1].pending.resolve({{ id: "new-session", intent: {{ genres: ["新"] }}, chips: [], channels: {{}} }});
            await routeRestore;
            if (state.activePath !== "/universe") throw new Error("stale restore changed the current route");
            if (actions.filter((action) => action.source === "restore").length !== 0) throw new Error("route-stale GET dispatched");
            if (statuses.some((message) => message.includes("已恢复"))) throw new Error(`stale restore updated status: ${{statuses}}`);

            store.dispatch({{ type: "route/changed", route }});
            const failedRestore = gate.restore(route, "今晚");
            requests[2].pending.reject(new Error("restore unavailable"));
            await failedRestore;
            if (!statuses.some((message) => message.includes("无法恢复"))) throw new Error("current restore error was not visible");
            console.log(JSON.stringify({{ sessionId: state.recommendation.sessionId, activePath: state.activePath, statuses, requestCount: requests.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("new-session", result["sessionId"])
        self.assertEqual("/tonight/movie", result["activePath"])
        self.assertEqual(3, result["requestCount"])

    def test_tonight_without_local_pointer_restores_latest_server_session(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ createTonightRestoreGate, reduceUiState }} = await import("{module_url('js/app.js')}");
            let state = {{
              activePath: "/tonight/movie", activeParams: {{ channel: "movie" }},
              recommendation: {{
                sessionId: null, activeChannel: "movie", personalization: {{}},
                channels: {{ movie: {{}}, series: {{}}, "anime-series": {{}} }},
              }},
              commandLens: {{ draft: "", chips: [] }}, rail: {{ mode: "expanded" }},
              scrollByRoute: {{}}, candidateTray: {{ itemIds: [], context: {{}} }},
            }};
            const actions = [];
            const store = {{
              getState: () => state,
              dispatch(action) {{ actions.push(action); state = reduceUiState(state, action); return action; }},
            }};
            let latestCalls = 0;
            const gate = createTonightRestoreGate({{
              store,
              restoreSession() {{ throw new Error("local restore must not run"); }},
              async restoreLatestSession() {{
                latestCalls += 1;
                return {{
                  id: "latest-session", intent: {{ quality_floor: 8 }}, chips: [],
                  channels: {{
                    "电影": {{ batch: {{ id: "movie-batch", index: 1, items: [] }} }},
                    "电视剧": {{ batch: {{ id: "series-batch", index: 1, items: [] }} }},
                    "动漫": {{ batch: {{ id: "anime-batch", index: 1, items: [] }} }},
                  }},
                }};
              }},
            }});
            await gate.restore({{ path: "/tonight/movie", name: "tonight-channel", params: {{ channel: "movie" }} }}, "今晚");
            if (latestCalls !== 1) throw new Error(`latest session requests=${{latestCalls}}`);
            if (state.recommendation.sessionId !== "latest-session") throw new Error("latest session was not committed");
            if (!actions.some((action) => action.source === "restore" && !action.expectedSessionId)) throw new Error("latest restore action missing");
            console.log(JSON.stringify({{ latestCalls, sessionId: state.recommendation.sessionId }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["latestCalls"])
        self.assertEqual("latest-session", result["sessionId"])

    def test_hydrated_tonight_channel_skips_redundant_session_restore(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ createTonightRestoreGate, reduceUiState }} = await import("{module_url('js/app.js')}");
            let state = {{
              activePath: "/tonight/series", activeParams: {{ channel: "series" }},
              recommendation: {{
                sessionId: "session-ready", activeChannel: "series",
                channels: {{
                  movie: {{ sessionId: "session-ready", batch: {{ items: [{{ title: "Movie" }}] }} }},
                  series: {{ sessionId: "session-ready", batch: {{ items: [{{ title: "Series" }}] }} }},
                  "anime-series": {{ sessionId: "session-ready", batch: {{ items: [{{ title: "Anime" }}] }} }},
                }},
              }},
              commandLens: {{ draft: "", chips: [] }}, rail: {{ mode: "expanded" }},
              scrollByRoute: {{}}, candidateTray: {{ itemIds: [], context: {{}} }},
            }};
            const actions = []; let restoreCalls = 0; const statuses = [];
            const store = {{
              getState: () => state,
              dispatch(action) {{ actions.push(action); state = reduceUiState(state, action); return action; }},
            }};
            const gate = createTonightRestoreGate({{
              store,
              async restoreSession() {{ restoreCalls += 1; throw new Error("hydrated channel must not refetch"); }},
              setStatus(message) {{ statuses.push(message); }},
            }});
            await gate.restore({{ path: "/tonight/series", name: "tonight-channel", params: {{ channel: "series" }} }}, "今晚");
            if (restoreCalls !== 0) throw new Error(`redundant restores=${{restoreCalls}}`);
            if (actions.some((action) => action.type === "recommendation/restoreStarted")) throw new Error("hydrated channel entered restore skeleton");
            console.log(JSON.stringify({{ restoreCalls, statuses, actionTypes: actions.map((action) => action.type) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(0, result["restoreCalls"])

    def test_command_lens_intent_mutations_are_latest_wins_and_errors_are_visible(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.dataset = {{}};
                this.attributes = new Map(); this.className = ""; this.textContent = "";
                this.value = ""; this.hidden = false; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              focus() {{}}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag), addEventListener() {{}} }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ configureCommandLens, openCommandLens, submitIntent }} = await import("{module_url('js/features/command-lens.js')}");
            const deferred = () => {{ let resolve, reject; const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }}); return {{ promise, resolve, reject }}; }};
            const pending = [];
            const actions = [];
            const state = {{ recommendation: {{ activeChannel: "movie", channels: {{ movie: {{ sessionId: null }} }} }}, commandLens: {{ draft: "", chips: [] }} }};
            const root = new FakeElement("div");
            configureCommandLens({{
              root,
              store: {{ getState: () => state, dispatch(action) {{ actions.push(action); }} }},
              api: {{ postV2(path, payload) {{ const request = deferred(); pending.push({{ path, payload, request }}); return request.promise; }} }},
            }});
            openCommandLens();
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const first = submitIntent("旧意图");
            const second = submitIntent("新意图");
            let submit = collect(root).find((node) => node.className === "command-lens__submit");
            if (!submit.disabled) throw new Error("submit button was not disabled while latest request was pending");
            pending[1].request.resolve({{ id: "new-session", intent: {{ genres: ["新"] }}, chips: [{{ key: "genre", label: "新", value: "新", removable: true }}], channels: {{}} }});
            await second;
            pending[0].request.resolve({{ id: "old-session", intent: {{ genres: ["旧"] }}, chips: [{{ key: "genre", label: "旧", value: "旧", removable: true }}], channels: {{}} }});
            await first;
            const receivedAfterSubmit = actions.filter((action) => action.type === "recommendation/sessionReceived").map((action) => action.session.id);
            if (receivedAfterSubmit.join(",") !== "new-session") throw new Error(`stale submit dispatched: ${{receivedAfterSubmit}}`);
            if (!collect(root).some((node) => node.textContent === "新") || collect(root).some((node) => node.textContent === "旧")) throw new Error("stale submit replaced visible chips");

            const remove = collect(root).find((node) => node.className === "intent-chip__remove");
            const removal = remove.onclick();
            const newer = submitIntent("更新意图");
            pending[3].request.resolve({{ id: "updated-session", intent: {{ genres: ["更新"] }}, chips: [{{ key: "genre", label: "更新", value: "更新", removable: true }}], channels: {{}} }});
            await newer;
            pending[2].request.resolve({{ id: "stale-removal", intent: {{ genres: [] }}, chips: [], channels: {{}} }});
            await removal;
            if (actions.some((action) => action.session?.id === "stale-removal")) throw new Error("stale chip removal dispatched");

            const edit = collect(root).find((node) => node.className === "intent-chip__edit");
            edit.onclick();
            const editor = collect(root).find((node) => node.className === "intent-chip__editor");
            const save = collect(root).find((node) => node.className === "intent-chip__save");
            editor.value = "编辑后";
            save.onclick();
            const newest = submitIntent("最终意图");
            pending[5].request.resolve({{ id: "final-session", intent: {{ genres: ["最终"] }}, chips: [{{ key: "genre", label: "最终", value: "最终", removable: true }}], channels: {{}} }});
            await newest;
            pending[4].request.resolve({{ id: "stale-edit", intent: {{ genres: ["编辑后"] }}, chips: [], channels: {{}} }});
            await Promise.resolve(); await Promise.resolve();
            if (actions.some((action) => action.session?.id === "stale-edit")) throw new Error("stale chip edit dispatched");

            const failed = submitIntent("失败意图");
            pending[6].request.reject(new Error("adapter unavailable"));
            try {{ await failed; }} catch {{}}
            const status = collect(root).find((node) => node.className === "command-lens__status");
            submit = collect(root).find((node) => node.className === "command-lens__submit");
            if (status.attributes.get("aria-live") !== "polite" || !status.textContent.includes("本地结构化筛选")) throw new Error("command error was not visible in aria-live status");
            if (submit.disabled) throw new Error("submit button remained disabled after failure");
            console.log(JSON.stringify({{ received: actions.filter((action) => action.type === "recommendation/sessionReceived").map((action) => action.session.id), status: status.textContent, calls: pending.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["new-session", "updated-session", "final-session"], result["received"])
        self.assertEqual(7, result["calls"])

    def test_batch_operations_are_per_channel_latest_wins_pending_and_error_visible(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.dataset = {{}};
                this.attributes = new Map(); this.className = ""; this.textContent = "";
                this.value = ""; this.hidden = false; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              focus() {{}}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ configureTonight, renderTonight, requestNextBatch, restorePreviousBatch, syncTonightSessionState }} = await import("{module_url('js/features/tonight.js')}");
            const deferred = () => {{ let resolve, reject; const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }}); return {{ promise, resolve, reject }}; }};
            const pending = [];
            const actions = [];
            const state = {{ recommendation: {{
              sessionId: "legacy-session", activeChannel: "movie",
              channels: {{
                movie: {{ sessionId: "movie-session", active_batch: 2, batchIndex: 2, batchIds: ["movie-old"], batch: {{ index: 2, items: [] }} }},
                series: {{ sessionId: "series-session", active_batch: 2, batchIndex: 2, batchIds: ["series-old"], batch: {{ index: 2, items: [] }} }},
                "anime-series": {{ sessionId: "anime-session", active_batch: 2, batchIndex: 2, batchIds: ["anime-old"], batch: {{ index: 2, items: [] }} }},
              }},
            }} }};
            const root = new FakeElement("main");
            configureTonight({{
              root,
              store: {{ getState: () => state, dispatch(action) {{ actions.push(action); }} }},
              api: {{ postV2(path, payload) {{ const request = deferred(); pending.push({{ path, payload, request }}); return request.promise; }} }},
            }});
            renderTonight(state);
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const next = requestNextBatch("movie", "更冷门");
            const previous = restorePreviousBatch("movie");
            let controls = collect(root).filter((node) => node.className.includes("tonight-button") || node.className === "tonight-reason");
            if (!controls.filter((node) => node.className !== "tonight-button tonight-button--primary").every((node) => node.disabled)) throw new Error("batch controls were not disabled while pending");
            if (!pending[0].path.includes("movie-session") || !pending[1].path.includes("movie-session")) throw new Error("movie channel session pointer was not used");
            pending[1].request.resolve({{ session_id: "movie-session", channel: "电影", batch: {{ id: "movie-previous-new", index: 1, items: [], pool_size: 10, matched_size: 8, visible_size: 2 }} }});
            await previous;
            pending[0].request.resolve({{ session_id: "movie-session", channel: "电影", batch: {{ id: "movie-next-stale", index: 3, items: [], pool_size: 10, matched_size: 8, visible_size: 2 }} }});
            await next;
            if (actions.map((action) => action.batch.batch.id).join(",") !== "movie-previous-new") throw new Error("stale movie batch dispatched");

            const movie = requestNextBatch("movie", "再换");
            const series = requestNextBatch("series", "剧集换批");
            pending[2].request.resolve({{ session_id: "movie-session", channel: "电影", batch: {{ id: "movie-independent", index: 2, items: [] }} }});
            pending[3].request.resolve({{ session_id: "series-session", channel: "电视剧", batch: {{ id: "series-independent", index: 3, items: [] }} }});
            await Promise.all([movie, series]);
            if (!actions.some((action) => action.channel === "movie" && action.batch.batch.id === "movie-independent")) throw new Error("movie channel operation was lost");
            if (!actions.some((action) => action.channel === "series" && action.batch.batch.id === "series-independent")) throw new Error("series channel operation was lost");

            const failed = requestNextBatch("movie", "失败原因");
            pending[4].request.reject(new Error("batch unavailable"));
            try {{ await failed; }} catch {{}}
            const status = collect(root).find((node) => node.className === "tonight-batch-status");
            controls = collect(root).filter((node) => node.className === "tonight-reason" || node.className === "tonight-button" || node.className === "tonight-button tonight-button--signal");
            if (!status || status.attributes.get("aria-live") !== "polite" || !status.textContent.includes("失败")) throw new Error("batch failure was not visible");
            if (controls.some((node) => node.disabled && !node.textContent.includes("撤回"))) throw new Error("batch controls remained disabled after failure");

            const obsolete = requestNextBatch("movie", "旧会话请求");
            state.recommendation.channels.movie.sessionId = "movie-session-new";
            syncTonightSessionState(state);
            controls = collect(root).filter((node) => node.className === "tonight-reason" || node.className === "tonight-button" || node.className === "tonight-button tonight-button--signal");
            if (controls.some((node) => node.disabled && !node.textContent.includes("撤回"))) throw new Error("new session did not clear old pending batch UI");
            pending[5].request.resolve({{ session_id: "movie-session", channel: "电影", batch: {{ id: "old-session-batch", index: 9, items: [] }} }});
            await obsolete;
            if (actions.some((action) => action.batch?.batch?.id === "old-session-batch")) throw new Error("old-session batch dispatched after session replacement");
            console.log(JSON.stringify({{ actions: actions.map((action) => [action.channel, action.batch.batch.id]), status: status.textContent, calls: pending.map((item) => item.path) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["movie", "movie", "series"], [entry[0] for entry in result["actions"]])
        self.assertIn("movie-session", result["calls"][0])
        self.assertIn("series-session", result["calls"][3])

    def test_command_lens_entrance_animation_preserves_centering_transform(self):
        source = (UI_ROOT / "js" / "features" / "command-lens.js").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "tonight.css").read_text(encoding="utf-8")

        self.assertIn('element("section", "command-lens command-lens--enter")', source)
        self.assertNotIn("motion-enter", source)
        self.assertRegex(
            css,
            r"\.command-lens--enter\s*\{\s*animation:\s*command-lens-enter\s+var\(--motion-standard\)\s+[^;]+;\s*\}",
        )
        for phase in ("from", "to"):
            with self.subTest(phase=phase):
                self.assertRegex(
                    css,
                    re.compile(
                        rf"@keyframes\s+command-lens-enter\s*\{{.*?\b{phase}\s*\{{[^}}]*transform:\s*translateX\(-50%\)[^;]*;",
                        re.DOTALL,
                    ),
                )

        reduced_motion = re.search(
            r"@media\s*\(prefers-reduced-motion:\s*reduce\)\s*\{(?P<body>.*?)\n\}",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(reduced_motion)
        reduced_css = reduced_motion.group("body")
        self.assertIn(".command-lens--enter { animation-duration: 1ms; }", reduced_css)
        self.assertIn(".command-lens { transform: translateX(-50%); }", reduced_css)

    def test_title_navigation_uses_stable_item_identity_and_never_title_text(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map();
                this.className = ""; this.textContent = ""; this.dataset = {{}};
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ renderTitleCard }} = await import("{module_url('js/components/title-card.js')}");
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];

            const stable = renderTitleCard({{ title: "同名作品", item_key: "item:stable-1", douban_id: "999" }});
            const stableLink = collect(stable).find((node) => node.tagName === "A");
            if (stableLink?.attributes.get("href") !== "/title/item:stable-1") throw new Error("item_key did not win navigation identity");

            const douban = renderTitleCard({{ title: "同名作品", douban_id: "1295644" }});
            const doubanLink = collect(douban).find((node) => node.tagName === "A");
            if (doubanLink?.attributes.get("href") !== "/title/douban:1295644") throw new Error("douban id fallback was not stable");

            const titleOnly = renderTitleCard({{ title: "同名作品" }});
            if (collect(titleOnly).some((node) => node.tagName === "A")) throw new Error("title text was guessed as navigation identity");
            console.log(JSON.stringify({{ stable: stableLink.attributes.get("href"), douban: doubanLink.attributes.get("href") }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("/title/item:stable-1", result["stable"])
        self.assertEqual("/title/douban:1295644", result["douban"])

    def test_detail_translates_internal_library_states_for_people(self):
        output = run_node_module(
            f'''
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ localStateLabel }} = await import("{module_url('js/features/detail.js')}");
            const labels = {{
              candidate: localStateLabel("candidate"),
              watched: localStateLabel("watched"),
              wanted: localStateLabel("wanted"),
            }};
            if (labels.candidate !== "推荐候选" || labels.watched !== "已看过" || labels.wanted !== "想看") throw new Error(JSON.stringify(labels));
            console.log(JSON.stringify(labels));
            '''
        )
        labels = json.loads(output)
        self.assertEqual("推荐候选", labels["candidate"])

    def test_title_detail_renders_cinematic_sections_people_and_local_relationships(self):
        output = run_node_module(
            f'''
            class FakeClassList {{
              constructor(owner) {{ this.owner = owner; }}
              add(name) {{ const values = new Set(this.owner.className.split(/\\s+/).filter(Boolean)); values.add(name); this.owner.className = [...values].join(" "); }}
              remove(name) {{ this.owner.className = this.owner.className.split(/\\s+/).filter((value) => value && value !== name).join(" "); }}
              toggle(name, force) {{ if (force) this.add(name); else this.remove(name); }}
            }}
            class FakeHtmlCollection {{
              constructor(owner) {{
                this.owner = owner;
                return new Proxy(this, {{
                  get(target, property, receiver) {{
                    const index = typeof property === "string" ? Number(property) : NaN;
                    if (Number.isInteger(index) && index >= 0 && String(index) === property) return owner._children[index];
                    return Reflect.get(target, property, receiver);
                  }},
                  has(target, property) {{
                    const index = typeof property === "string" ? Number(property) : NaN;
                    if (Number.isInteger(index) && index >= 0 && String(index) === property) return index < owner._children.length;
                    return Reflect.has(target, property);
                  }},
                  set(target, property, value, receiver) {{
                    const index = typeof property === "string" ? Number(property) : NaN;
                    if (Number.isInteger(index) && index >= 0 && String(index) === property) throw new TypeError("HTMLCollection indexed property setter is not supported");
                    return Reflect.set(target, property, value, receiver);
                  }},
                }});
              }}
              get length() {{ return this.owner._children.length; }}
              item(index) {{ return this.owner._children[index] ?? null; }}
              [Symbol.iterator]() {{ return this.owner._children[Symbol.iterator](); }}
            }}
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this._children = []; this.children = new FakeHtmlCollection(this); this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.id = ""; this.hidden = false; this.disabled = false;
                this.classList = new FakeClassList(this); this.style = {{ setProperty() {{}} }};
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this._children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this._children = []; this.append(...nodes); }}
              replaceWith(node) {{
                const parent = this.parentNode;
                const index = parent?._children.indexOf(this) ?? -1;
                if (index < 0) return;
                parent._children.splice(index, 1, node); node.parentNode = parent; this.parentNode = null;
              }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              getBoundingClientRect() {{ return {{ left: 20, top: 30, width: 120, height: 180 }}; }}
              scrollIntoView(options) {{ this.scrollOptions = options; }}
              focus() {{}}
              get firstElementChild() {{ return this._children[0] ?? null; }}
            }}
            const root = new FakeElement("main");
            let indexedSetterBlocked = false;
            try {{ root.children[0] = new FakeElement("probe"); }} catch {{ indexedSetterBlocked = true; }}
            if (!indexedSetterBlocked) throw new Error("test double must reject HTMLCollection indexed assignment");
            const collectionProbe = new FakeElement("probe"); root.append(collectionProbe);
            if (root.children[0] !== collectionProbe || Array.prototype.indexOf.call(root.children, collectionProbe) !== 0) throw new Error("test double must expose indexed HTMLCollection reads");
            root.replaceChildren();
            let transitions = 0;
            globalThis.document = {{
              createElement: (tag) => new FakeElement(tag),
              createDocumentFragment: () => new FakeElement("fragment"),
              getElementById(id) {{ return collect(root).find((node) => node.id === id) || null; }},
              startViewTransition(update) {{ transitions += 1; update(); return {{ finished: Promise.resolve() }}; }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const opened = [];
            const exits = [];
            const mediaJobs = [];
            const metadataRequests = [];
            const fetchPaths = [];
            const title = {{
              id: "media-42", item_key: "douban:42", title: "银幕测试", media_type: "电影", year: 2024, state: "watched",
              poster: {{ url: "/media/detail-poster.jpg", media_status: "ready" }}, backdrop: {{ url: "", media_status: "missing" }},
              item: {{
                title: "银幕测试", year: 2024, media_type: "电影", directors: ["导演甲"], casts: ["演员乙"],
                countries: ["中国"], genres: ["剧情"], douban_rating: 8.6, vote_count: 123456, my_rating: 9, duration: 123, release_date: "2024-08-01",
                raw: {{
                  comment: "这是我同步自豆瓣的真实短评。",
                  ratings: {{ imdb: 8.4, tmdb: 8.2 }},
                  rating_votes: {{ imdb: 88000, tmdb: 12000 }},
                }},
                summary: "",
              }},
              people: [
                {{ id: "person-director", role: "director", name: "导演甲", portrait: {{ url: "/media/director.jpg", media_status: "ready" }}, media_status: "ready" }},
                {{ id: "person-cast", role: "cast", name: "演员乙", portrait: {{ url: "", media_status: "pending" }}, media_status: "pending" }},
              ],
            }};
            const universe = {{
              focus_id: "douban:42",
              nodes: [
                {{ id: "douban:42", title: "银幕测试", year: 2024, media_type: "电影", poster: {{ url: "", media_status: "missing" }} }},
                {{ id: "item:related", title: "本地关联作品", year: 2020, media_type: "电影", poster: {{ url: "/media/related.jpg", media_status: "ready" }} }},
                {{ id: "item:pending", title: "待补关联作品", year: 2021, media_type: "电影", poster: {{ url: "", media_status: "missing" }} }},
              ],
              edges: [
                {{ source: "douban:42", target: "item:related", score: 2.4, reason: "shared director: 导演甲", reasons: ["shared director: 导演甲"] }},
                {{ source: "douban:42", target: "item:pending", score: 1.8, reason: "shared genre: 剧情", reasons: ["shared genre: 剧情"] }},
              ],
            }};
            let currentTitle = title;
            let currentUniverse = universe;
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              async fetchJson(path) {{ fetchPaths.push(path); return path.startsWith("/api/v2/titles/") ? currentTitle : currentUniverse; }},
              async postV2(path, payload) {{
                if (path === "/api/v2/titles/douban:42/enrich") {{
                  metadataRequests.push(path);
                  return {{ ...title, item: {{ ...title.item, summary: "后台补齐后的可靠剧情简介。" }} }};
                }}
                mediaJobs.push({{ path, payload }}); return {{ job_id: `job-${{mediaJobs.length}}`, state: "queued" }};
              }},
              openPersonSheet(id, rect) {{ opened.push({{ id, rect }}); }},
              getDetailReturnPath() {{ return "/library"; }},
              onExitDetail(path) {{ exits.push(path); }},
            }});
            await renderTitleDetail("douban:42");
            await Promise.resolve(); await Promise.resolve();
            const collect = (node) => [node, ...[...node.children].flatMap((child) => collect(child))];
            const nodes = collect(root);
            const classes = nodes.map((node) => node.className);
            for (const required of ["detail-page", "detail-backdrop", "detail-poster", "detail-tabs", "detail-score-grid", "detail-facts", "detail-visuals", "detail-people-rail", "detail-relations"]) {{
              if (!classes.some((value) => value.split(/\\s+/).includes(required))) throw new Error(`missing detail section: ${{required}}`);
            }}
            const peopleTab = nodes.find((node) => node.tagName === "A" && node.attributes.get("href") === "#people");
            const peopleSection = nodes.find((node) => node.id === "people");
            let sectionNavigationPrevented = false;
            peopleTab.onclick({{ preventDefault() {{ sectionNavigationPrevented = true; }} }});
            if (!sectionNavigationPrevented || peopleSection.scrollOptions?.block !== "start") throw new Error("detail section navigation did not scroll the target into view");
            const exitButton = nodes.find((node) => node.className.split(/\\s+/).includes("detail-return"));
            if (!exitButton || !exitButton.textContent.includes("返回片库")) throw new Error("detail return action was missing or not contextual");
            exitButton.onclick();
            if (exits[0] !== "/library") throw new Error(`detail return escaped the configured app route: ${{JSON.stringify(exits)}}`);
            const backdrop = nodes.find((node) => node.className.split(/\\s+/).includes("detail-backdrop"));
            const backdropNodes = collect(backdrop);
            const backdropFrame = backdropNodes.find((node) => node.className.split(/\\s+/).includes("media-frame"));
            if (backdrop.className.includes("detail-backdrop--poster-fallback")) {{
              throw new Error("portrait poster leaked into the cinematic backdrop");
            }}
            if (classes.some((value) => value.split(/\\s+/).includes("media-gallery"))) {{
              throw new Error("poster-only title rendered a fake visual gallery");
            }}
            if (!nodes.map((node) => node.textContent).join("|").includes("暂未找到可核对的真实剧照")) {{
              throw new Error("detail real-visual empty state was missing");
            }}
            const personButton = nodes.find((node) => node.className.includes("person-card"));
            personButton.onclick();
            if (opened[0]?.id !== "person-director" || opened[0].rect.width !== 120) throw new Error("person sheet did not receive stable identity and origin rect");
            if (nodes.filter((node) => node.className.split(/\\s+/).includes("person-card")).length !== 2) throw new Error("all identified people were not rendered with resilient portrait fallbacks");
            const relationLink = nodes.find((node) => node.tagName === "A" && node.attributes.get("href") === "/title/item:related");
            if (!relationLink) throw new Error("local relationship did not keep stable item key navigation");
            if (nodes.some((node) => node.tagName === "A" && node.attributes.get("href") === "/title/item:pending")) throw new Error("unresolved related poster rendered as a broken visual card");
            const text = nodes.map((node) => node.textContent).join("|");
            if (!text.includes("本地关联") || !text.includes("共同导演：导演甲") || text.includes("相似作品")) throw new Error("universe semantics were overstated or left raw backend labels");
            if (!text.includes("123,456 人参与豆瓣评分") || !text.includes("IMDb 8.4") || !text.includes("TMDb 8.2") || !text.includes("这是我同步自豆瓣的真实短评。") || !classes.some((value) => value.split(/\\s+/).includes("detail-evidence"))) throw new Error("real multi-source/public/personal review evidence was not rendered");
            if (!text.includes("片长") || !text.includes("123 分钟") || !text.includes("上映日期") || !text.includes("2024-08-01")) throw new Error("verified runtime or release date was omitted from detail facts");
            if (!text.includes("正在补齐 1 张关联海报")) throw new Error("related poster hydration state was not explained");
            if (!mediaJobs.some((job) => job.payload.kind === "poster" && job.payload.identity_key === "item:pending")) throw new Error("missing related poster was not queued");
            if (!text.includes("正在匹配 1 位演职人员肖像") || !mediaJobs.some((job) => job.payload.kind === "portrait" && job.payload.identity_key === "person-cast")) throw new Error("missing portrait hydration was not visible or queued");
            if (metadataRequests.length !== 1 || !text.includes("后台补齐后的可靠剧情简介。")) throw new Error("thin title metadata was not enriched and patched in place");
            currentTitle = {{
              item_key: "douban:43", title: "主海报待补作品", media_type: "电影", year: 2022, state: "watched",
              poster: {{ url: "", media_status: "missing" }}, backdrop: {{ url: "", media_status: "missing" }},
              item: {{ title: "主海报待补作品", summary: "已有简介。", genres: ["剧情"], directors: ["导演乙"], casts: [] }}, people: [],
            }};
            currentUniverse = {{ focus_id: "douban:43", nodes: [{{ id: "douban:43", title: "主海报待补作品" }}], edges: [] }};
            await renderTitleDetail("douban:43");
            await Promise.resolve(); await Promise.resolve();
            if (!mediaJobs.some((job) => job.payload.kind === "poster" && job.payload.identity_key === "douban:43")) throw new Error("missing primary poster was not queued");
            if (!fetchPaths.includes("/api/v2/titles/douban:42")) throw new Error(`catalog path encoded the safe title identity: ${{fetchPaths}}`);
            if (transitions !== 2) throw new Error("prepared detail did not use view transition");
            console.log(JSON.stringify({{ transitions, opened: opened[0].id, mediaJobs: mediaJobs.length, relation: relationLink.attributes.get("href") }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["transitions"])
        self.assertEqual("person-director", result["opened"])
        self.assertEqual("/title/item:related", result["relation"])

    def test_title_card_prefers_media_badge_label_over_raw_media_type(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderTitleCard }} = await import("{module_url('js/components/title-card.js')}");
            const card = renderTitleCard({{
              item_key: "external:documentary-card",
              title: "Mystery Map",
              media_type: "\u7535\u89c6\u5267",
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
              year: 2017,
              genres: ["\u7eaa\u5f55\u7247", "\u5192\u9669"],
              summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
              poster: {{ url: "", media_status: "missing" }},
            }});
            const metadata = card.querySelector(".title-card__genres");
            const typePill = metadata?.children?.[0];
            if (typePill?.textContent !== "\u7eaa\u5f55\u7247\u5267\u96c6") {{
              throw new Error(`title card ignored media badge: ${{metadata?.textContent}}`);
            }}
            console.log(JSON.stringify({{ typeLabel: typePill.textContent }}));
            '''
        )
        self.assertEqual("\u7eaa\u5f55\u7247\u5267\u96c6", json.loads(output)["typeLabel"])

    def test_detail_prefers_media_badge_label_in_hero_and_verified_facts(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const root = new FakeElement("main");
            const title = {{
              item_key: "external:documentary-detail",
              title: "Mystery Map",
              display_title: "\u795e\u79d8\u5730\u56fe",
              media_type: "\u7535\u89c6\u5267",
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
              year: 2017,
              state: "candidate",
              poster: {{ url: "", media_status: "missing" }},
              backdrop: {{ url: "", media_status: "missing" }},
              stills: [],
              item: {{
                genres: ["\u7eaa\u5f55\u7247", "\u5192\u9669"],
                directors: [],
                casts: [],
                summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
                raw: {{}},
              }},
              people: [],
            }};
            const universe = {{ focus_id: title.item_key, nodes: [], edges: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson: async (path) => path.startsWith("/api/v2/titles/") ? title : universe,
              api: {{ postV2: async (path) => path.endsWith("/enrich") ? title : {{ state: "failed" }} }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail(title.item_key); await flush();
            const metadata = root.querySelector(".detail-hero__metadata");
            const facts = root.querySelector(".detail-facts__grid");
            if (!metadata?.textContent.includes("\u7eaa\u5f55\u7247\u5267\u96c6") || metadata.textContent.includes("\u7535\u89c6\u5267")) {{
              throw new Error(`detail hero ignored media badge: ${{metadata?.textContent}}`);
            }}
            if (!facts?.textContent.includes("\u7eaa\u5f55\u7247\u5267\u96c6")) {{
              throw new Error(`detail facts ignored media badge: ${{facts?.textContent}}`);
            }}
            console.log(JSON.stringify({{ metadata: metadata.textContent, facts: facts.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("\u7eaa\u5f55\u7247\u5267\u96c6", result["metadata"])
        self.assertIn("\u7eaa\u5f55\u7247\u5267\u96c6", result["facts"])

    def test_detail_relation_card_prefers_universe_media_badge_without_raw_media_type(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const root = new FakeElement("main");
            const title = {{
              item_key: "external:documentary-focus",
              title: "\u795e\u79d8\u5730\u56fe",
              media_type: "\u7535\u89c6\u5267",
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
              year: 2017,
              state: "candidate",
              poster: {{ url: "/media/focus.webp", media_status: "ready" }},
              backdrop: {{ url: "", media_status: "missing" }},
              stills: [],
              item: {{
                title: "\u795e\u79d8\u5730\u56fe",
                media_type: "\u7535\u89c6\u5267",
                genres: ["\u7eaa\u5f55\u7247", "\u5192\u9669"],
                directors: ["\u5bfc\u6f14\u7532"],
                casts: [],
                summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
                raw: {{}},
              }},
              people: [],
            }};
            const related = {{
              id: "external:documentary-related",
              item_key: "external:documentary-related",
              title: "\u79d1\u5e7b\u771f\u53f2",
              media_type: "\u7535\u89c6\u5267",
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
              year: 2014,
              poster: {{ url: "/media/related.webp", media_status: "ready" }},
            }};
            const universe = {{
              focus_id: title.item_key,
              nodes: [{{ id: title.item_key, title: title.title }}, related],
              edges: [{{ source: title.item_key, target: related.id, score: 0.9, reasons: ["\u5171\u540c\u7c7b\u578b\uff1a\u7eaa\u5f55\u7247"] }}],
            }};
            const fetchJson = async (path) => {{
              if (path.startsWith("/api/v2/titles/")) return title;
              if (path.startsWith("/api/v2/universe")) return universe;
              return {{ items: [] }};
            }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson,
              api: {{ postV2: async () => ({{ state: "failed" }}) }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail(title.item_key); await flush();
            const works = root.querySelector(".detail-related-works");
            const metadata = works?.querySelector(".title-card__genres");
            if (!metadata?.textContent.includes("\u7eaa\u5f55\u7247\u5267\u96c6")) {{
              throw new Error(`related card ignored universe media badge: ${{metadata?.textContent}}`);
            }}
            if (metadata.textContent.includes("\u7535\u89c6\u5267")) {{
              throw new Error(`related card leaked raw media type beside specific badge: ${{metadata.textContent}}`);
            }}
            console.log(JSON.stringify({{ metadata: metadata.textContent }}));
            '''
        )
        metadata = json.loads(output)["metadata"]
        self.assertIn("\u7eaa\u5f55\u7247\u5267\u96c6", metadata)
        self.assertNotIn("\u7535\u89c6\u5267", metadata)

    def test_detail_similar_card_prefers_candidate_media_badge_without_raw_media_type(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const root = new FakeElement("main");
            const title = {{
              item_key: "external:similar-focus",
              title: "\u795e\u79d8\u5730\u56fe",
              media_type: "\u7535\u89c6\u5267",
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
              year: 2017,
              state: "candidate",
              poster: {{ url: "/media/similar-focus.webp", media_status: "ready" }},
              backdrop: {{ url: "", media_status: "missing" }},
              stills: [],
              item: {{
                title: "\u795e\u79d8\u5730\u56fe",
                media_type: "\u7535\u89c6\u5267",
                genres: ["\u7eaa\u5f55\u7247", "\u5192\u9669"],
                directors: ["\u5bfc\u6f14\u7532"],
                casts: [],
                summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
                raw: {{}},
              }},
              people: [],
            }};
            const candidate = {{
              id: "external:similar-documentary",
              item_key: "external:similar-documentary",
              title: "\u79d1\u5e7b\u771f\u53f2",
              media_type: "\u7535\u89c6\u5267",
              media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
              year: 2014,
              summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
              poster: {{ url: "/media/similar-documentary.webp", media_status: "ready" }},
            }};
            const fetchJson = async (path) => {{
              if (path.startsWith("/api/v2/titles/")) return title;
              if (path.startsWith("/api/v2/universe")) return {{ focus_id: title.item_key, nodes: [], edges: [] }};
              return {{ items: [candidate] }};
            }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson,
              api: {{ postV2: async () => ({{ state: "failed" }}) }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail(title.item_key); await flush();
            const grid = root.querySelector(".detail-similar__grid");
            const metadata = grid?.querySelector(".title-card__genres");
            if (!metadata?.textContent.includes("\u7eaa\u5f55\u7247\u5267\u96c6")) {{
              throw new Error(`similar card ignored candidate media badge: ${{metadata?.textContent}}`);
            }}
            if (metadata.textContent.includes("\u7535\u89c6\u5267")) {{
              throw new Error(`similar card leaked raw media type beside specific badge: ${{metadata.textContent}}`);
            }}
            console.log(JSON.stringify({{ metadata: metadata.textContent }}));
            '''
        )
        metadata = json.loads(output)["metadata"]
        self.assertIn("\u7eaa\u5f55\u7247\u5267\u96c6", metadata)
        self.assertNotIn("\u7535\u89c6\u5267", metadata)

    def test_detail_hero_prefers_verified_display_title_over_original_title(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const root = new FakeElement("main");
            const title = {{
              item_key: "external:localized-detail",
              title: "The Real History of Science Fiction",
              display_title: "\u79d1\u5e7b\u771f\u53f2",
              original_title: "The Real History of Science Fiction",
              title_localization_source: "douban",
              media_type: "\u7535\u89c6\u5267", year: 2014, state: "candidate",
              poster: {{ url: "", media_status: "missing" }}, backdrop: {{ url: "", media_status: "missing" }}, stills: [],
              item: {{ genres: ["\u7eaa\u5f55\u7247"], directors: [], casts: [], summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002", raw: {{}} }},
              people: [],
            }};
            const universe = {{ focus_id: title.item_key, nodes: [], edges: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson: async (path) => path.startsWith("/api/v2/titles/") ? title : universe,
              api: {{ postV2: async (path) => path.endsWith("/enrich") ? title : {{ state: "failed" }} }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail(title.item_key); await flush();
            const heading = root.querySelector(".detail-hero__title");
            if (heading?.textContent !== "\u79d1\u5e7b\u771f\u53f2") throw new Error(`detail heading ignored display_title: ${{heading?.textContent}}`);
            console.log(JSON.stringify({{ heading: heading.textContent }}));
            '''
        )
        self.assertEqual("\u79d1\u5e7b\u771f\u53f2", json.loads(output)["heading"])

    def test_detail_does_not_label_generic_popularity_as_douban_votes(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f"""
            {prelude}
            const root = new FakeElement("main");
            const title = {{
              item_key: "external:tvmaze-61855", title: "Mystery Incorporated", media_type: "\u7535\u89c6\u5267", year: 2022, state: "candidate",
              poster: {{ url: "", media_status: "missing" }}, backdrop: {{ url: "", media_status: "missing" }}, stills: [],
              item: {{
                douban_rating: null,
                vote_count: 44,
                genres: ["\u72af\u7f6a", "\u60ac\u7591"],
                directors: ["Verified Director"],
                casts: ["Dade Elza"],
                summary: "\u8fd9\u662f\u4e00\u6bb5\u5df2\u7ecf\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002",
                raw: {{ ratings: {{ imdb: 7.4 }}, rating_votes: {{ imdb: 684 }} }},
              }},
              people: [],
            }};
            const universe = {{ focus_id: title.item_key, nodes: [{{ id: title.item_key, title: title.title }}], edges: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson: async (path) => path.startsWith("/api/v2/titles/") ? title : universe,
              api: {{
                postV2: async () => ({{ state: "failed" }}),
                getV2: async () => ({{ state: "failed" }}),
              }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail(title.item_key); await flush();
            const copy = root.textContent;
            if (copy.includes("44 \u4eba\u53c2\u4e0e\u8c46\u74e3\u8bc4\u5206") || copy.includes("\u8c46\u74e3\u8bc4\u5206\u4eba\u6570\u5c1a\u672a\u540c\u6b65")) {{
              throw new Error(`generic popularity was mislabeled as Douban evidence: ${{copy}}`);
            }}
            if (!copy.includes("IMDb 7.4") || !copy.includes("684 \u6761\u516c\u5f00\u8bc4\u5206\u6216\u70ed\u5ea6\u8bc1\u636e")) {{
              throw new Error(`source-specific IMDb evidence was omitted: ${{copy}}`);
            }}
            if (!copy.includes("\u672a\u53d1\u73b0\u53ef\u6838\u5bf9\u7684\u8c46\u74e3\u8bc4\u5206\u8bb0\u5f55")) {{
              throw new Error(`missing Douban evidence was not explained honestly: ${{copy}}`);
            }}
            console.log(JSON.stringify({{ copy }}));
            """
        )
        result = json.loads(output)
        self.assertIn("IMDb 7.4", result["copy"])
        self.assertNotIn("44 \u4eba\u53c2\u4e0e\u8c46\u74e3\u8bc4\u5206", result["copy"])

    def test_detail_keeps_verified_poster_out_of_still_gallery(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const root = new FakeElement("main");
            const sharedPoster = "/media/verified-poster.webp";
            const title = {{
              item_key: "external:tvmaze-poster-only", title: "\u53ea\u6709\u6d77\u62a5\u7684\u4f5c\u54c1", media_type: "\u7535\u89c6\u5267", year: 2013, state: "candidate",
              poster: {{ url: sharedPoster, media_status: "ready" }},
              backdrop: {{ url: sharedPoster, media_status: "ready" }},
              stills: [],
              item: {{
                genres: ["\u60ac\u7591"], directors: ["\u5bfc\u6f14\u7532"], casts: [],
                summary: "\u8fd9\u662f\u4e00\u6bb5\u5df2\u7ecf\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002", raw: {{ ratings: {{ imdb: 7.8 }} }},
              }},
              people: [],
            }};
            const universe = {{ focus_id: title.item_key, nodes: [{{ id: title.item_key, title: title.title }}], edges: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              detailGet: async () => title,
              fetchJson: async () => universe,
              api: {{
                postV2: async () => ({{ state: "failed" }}),
                getV2: async () => ({{ state: "failed" }}),
              }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail(title.item_key); await flush();
            const nodes = collectNodes(root);
            const gallery = nodes.find((node) => node.className.split(/\\s+/).includes("media-gallery"));
            const caption = nodes.find((node) => node.className.split(/\\s+/).includes("media-gallery__caption"));
            const visuals = nodes.find((node) => node.className.split(/\\s+/).includes("detail-visuals"));
            const heroFallback = nodes.find((node) => node.className.split(/\\s+/).includes("detail-backdrop--poster-fallback"));
            const emptyCopy = "\u6682\u672a\u627e\u5230\u53ef\u6838\u5bf9\u7684\u771f\u5b9e\u5267\u7167";
            if (gallery || caption) {{
              throw new Error("poster-only title still rendered a gallery");
            }}
            if (heroFallback) throw new Error("poster was still reused as the hero backdrop");
            if (!visuals?.textContent.includes(emptyCopy)) {{
              throw new Error(`verified-still empty state was not explained: ${{visuals?.textContent}}`);
            }}
            console.log(JSON.stringify({{ hasGallery: Boolean(gallery), hasHeroFallback: Boolean(heroFallback), visuals: visuals.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertFalse(result["hasGallery"])
        self.assertFalse(result["hasHeroFallback"])

    def test_detail_hero_prefers_a_verified_still_and_surfaces_score_and_genres_immediately(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const root = new FakeElement("main");
            const mediaJobs = [];
            const title = {{
              item_key: "douban:900", title: "完整档案", media_type: "电影", year: 2025, state: "candidate",
              poster: {{ url: "/media/poster.webp", media_status: "ready" }},
              backdrop: {{ url: "/media/backdrop.webp", media_status: "ready" }},
              stills: [{{ id: "still-0", url: "/api/image-proxy?url=https%3A%2F%2Fexample.test%2Fscene.jpg", media_status: "ready" }}],
              item: {{
                douban_rating: 8.8,
                genres: ["剧情", "悬疑"],
                directors: ["导演甲"],
                casts: ["演员乙"],
                summary: "一段完整、可信并且第一时间可见的剧情简介。",
                raw: {{ ratings: {{ imdb: 8.3 }} }},
              }},
              people: [],
            }};
            const universe = {{ focus_id: "douban:900", nodes: [{{ id: "douban:900", title: "完整档案" }}], edges: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson: async (path) => path.startsWith("/api/v2/titles/") ? title : universe,
              api: {{
                postV2: async (path, payload) => {{ mediaJobs.push({{ path, payload }}); return {{ state: "failed" }}; }},
                getV2: async () => ({{ state: "failed" }}),
              }},
              getDetailReturnPath: () => "/library",
            }});
            await renderTitleDetail("douban:900"); await flush();
            const nodes = collectNodes(root);
            const hero = nodes.find((node) => node.className.split(/\\s+/).includes("detail-hero"));
            const heroNodes = collectNodes(hero);
            const backdrop = heroNodes.find((node) => node.className.split(/\\s+/).includes("detail-backdrop"));
            const still = heroNodes.find((node) => node.className === "detail-backdrop__still");
            const quickFacts = heroNodes.find((node) => node.className === "detail-hero__quickfacts");
            const heroText = hero.textContent;
            if (!backdrop.className.includes("detail-backdrop--still") || !still?.src.includes("/api/image-proxy?url=")) throw new Error("verified still was not promoted into the hero backdrop");
            if (!quickFacts || !heroText.includes("豆瓣 8.8") || !heroText.includes("IMDb 8.3") || !heroText.includes("剧情") || !heroText.includes("悬疑")) throw new Error(`decision metadata was not visible in the hero: ${{heroText}}`);
            if (mediaJobs.some((job) => job.payload?.kind === "backdrop")) throw new Error("a redundant backdrop job was queued even though a verified still exists");
            console.log(JSON.stringify({{ heroText, still: still.src, mediaJobs }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("豆瓣 8.8", result["heroText"])
        self.assertIn("/api/image-proxy?url=", result["still"])

    def test_people_prefetch_is_bounded_exact_deduplicated_and_uses_post_v2(self):
        output = run_node_module(
            f'''
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const deferred = () => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }};
            const calls = [];
            const {{ configureDetail, prefetchVisiblePeople }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              api: {{
                postV2(path, payload) {{ const pending = deferred(); calls.push({{ path, payload, pending }}); return pending.promise; }},
              }},
            }});
            const missing = {{ url: "", media_status: "missing" }};
            const title = {{
              title: "预取边界测试",
              item: {{
                title: "预取边界测试",
                directors: ["导演甲", "共享身份", "导演丙"],
                casts: ["演员1", "演员2", "演员3", "演员4", "演员5", "演员6", "演员7", "演员8", "演员9"],
                raw: {{ original_title: "Prefetch Boundary", aliases: ["别名甲", "别名乙", "预取边界测试"] }},
              }},
              people: [
                {{ id: "p-director", name: "导演甲", role: "director", portrait: missing, metadata: {{ known_works: ["人物代表作", "别名甲"] }} }},
                {{ id: "p-shared", name: "共享身份", role: "director", portrait: missing }},
                {{ id: "p-director-3", name: "导演丙", role: "director", portrait: missing }},
                {{ id: "p-actor-1", name: "演员1", role: "cast", portrait: missing }},
                {{ id: "p-shared", name: "演员2", role: "cast", portrait: missing }},
                {{ id: "p-ready", name: "演员3", role: "cast", portrait: {{ url: "/media/ready.png", media_status: "ready" }} }},
                {{ id: "p-actor-4", name: "演员4", role: "cast", portrait: missing }},
                {{ id: "p-actor-5", name: "演员5", role: "cast", portrait: missing }},
                {{ id: "p-actor-6", name: "演员6", role: "cast", portrait: missing }},
                {{ id: "p-actor-7", name: "演员7", role: "cast", portrait: missing }},
                {{ id: "p-actor-8", name: "演员8", role: "cast", portrait: missing }},
                {{ id: "p-actor-9", name: "演员9", role: "cast", portrait: missing }},
              ],
            }};
            const first = prefetchVisiblePeople(title);
            const duplicate = prefetchVisiblePeople(title);
            if (calls.length !== 8) throw new Error(`expected 8 bounded unique jobs, received ${{calls.length}}`);
            const ids = calls.map((call) => call.payload.identity_key);
            if (new Set(ids).size !== ids.length) throw new Error("duplicate person id was enqueued");
            if (calls.some((call) => call.path !== "/api/v2/media/jobs")) throw new Error("portrait job bypassed the V2 media endpoint");
            if (calls.some((call) => call.payload.person_name === "演员9" || call.payload.identity_key === "p-ready" || call.payload.identity_key === "p-director-3")) throw new Error("prefetch exceeded visible cast/crew bounds or included ready portrait");
            const directorContext = calls.find((call) => call.payload.identity_key === "p-director")?.payload.work_context;
            const expectedContext = ["预取边界测试", "Prefetch Boundary", "别名甲", "别名乙", "人物代表作"];
            if (JSON.stringify(directorContext) !== JSON.stringify(expectedContext)) throw new Error(`portrait context payload was incomplete: ${{JSON.stringify(directorContext)}}`);
            const priorities = Object.fromEntries(calls.map((call) => [call.payload.identity_key, call.payload.priority]));
            if (priorities["p-director"] !== 120 || priorities["p-shared"] !== 120) throw new Error(`directors were not promoted ahead of cast: ${{JSON.stringify(priorities)}}`);
            if (priorities["p-actor-1"] !== 80 || priorities["p-actor-4"] !== 80 || priorities["p-actor-6"] !== 80) throw new Error(`first six cast were not promoted: ${{JSON.stringify(priorities)}}`);
            if (priorities["p-actor-7"] !== 40 || priorities["p-actor-8"] !== 40) throw new Error(`secondary cast priority was not bounded: ${{JSON.stringify(priorities)}}`);
            calls.forEach((call, index) => call.pending.resolve({{ job_id: `job-${{index}}`, state: "queued" }}));
            await Promise.all([first, duplicate]);
            await prefetchVisiblePeople(title);
            if (calls.length !== 8) throw new Error("completed prefetch was enqueued again");
            console.log(JSON.stringify({{ count: calls.length, ids, priorities, names: calls.map((call) => call.payload.person_name) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(8, result["count"])
        self.assertNotIn("p-ready", result["ids"])
        self.assertNotIn("演员9", result["names"])
        self.assertEqual(120, result["priorities"]["p-director"])

    def test_generated_detail_placeholder_and_generic_media_genre_still_trigger_metadata_enrichment(self):
        output = run_node_module(
            f'''
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const calls = [];
            const {{ configureDetail, enrichThinTitleMetadata }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              api: {{ async postV2(path, payload) {{ calls.push({{ path, payload }}); return {{ item_key: "douban:36474027" }}; }} }},
            }});
            const title = {{
              item_key: "douban:36474027", title: "镖人：风起大漠", media_type: "电影",
              item: {{
                summary: "正在补齐这部电影的剧情简介；目前已确认类型为电影。",
                genres: ["电影"], directors: ["袁和平"], casts: ["吴京"],
              }},
            }};
            await enrichThinTitleMetadata(title);
            if (calls.length !== 1 || calls[0].path !== "/api/v2/titles/douban:36474027/enrich") throw new Error(`generated placeholder blocked enrichment: ${{JSON.stringify(calls)}}`);
            console.log(JSON.stringify(calls));
            '''
        )
        calls = json.loads(output)
        self.assertEqual(1, len(calls))

    def test_degraded_portrait_attempt_can_be_retried_in_the_same_detail_session(self):
        output = run_node_module(
            f'''
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const calls = [];
            const {{ configureDetail, prefetchVisiblePeople }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              api: {{ async postV2(path, payload) {{ calls.push({{ path, payload }}); return {{ job_id: `job-${{calls.length}}`, state: "degraded" }}; }} }},
            }});
            const title = {{
              item_key: "douban:retry", title: "肖像重试",
              item: {{ directors: ["导演甲"], casts: [] }},
              people: [{{ id: "person-retry", name: "导演甲", role: "director", portrait: {{ url: "", media_status: "missing" }} }}],
            }};
            await prefetchVisiblePeople(title);
            await prefetchVisiblePeople(title);
            if (calls.length !== 2) throw new Error(`degraded portrait stayed permanently cached: ${{calls.length}}`);
            console.log(JSON.stringify(calls));
            '''
        )
        calls = json.loads(output)
        self.assertEqual(2, len(calls))

    def test_people_refresh_preserves_existing_ready_portrait_image_nodes(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            globalThis.document.createDocumentFragment = () => new FakeElement("fragment");
            const root = new FakeElement("main");
            const timers = [];
            let titleReads = 0;
            const readyPortrait = {{ url: "/media/director-ready.webp", media_status: "ready" }};
            const missingPortrait = {{ url: "", media_status: "missing" }};
            const titleMissing = {{
              item_key: "douban:portrait-stable", title: "人物节点稳定测试", year: 2024, media_type: "电影", state: "watched",
              poster: {{ url: "/media/title-ready.webp", media_status: "ready" }}, backdrop: {{ url: "", media_status: "missing" }},
              item: {{ summary: "完整简介。", genres: ["剧情"], directors: ["导演甲"], casts: ["演员乙"] }},
              people: [
                {{ id: "person-director-stable", name: "导演甲", role: "director", portrait: readyPortrait, media_status: "ready" }},
                {{ id: "person-cast-new", name: "演员乙", role: "cast", portrait: missingPortrait, media_status: "missing" }},
              ],
            }};
            const titleReady = {{
              ...titleMissing,
              people: [
                titleMissing.people[0],
                {{ id: "person-cast-new", name: "演员乙", role: "cast", portrait: {{ url: "/media/cast-ready.webp", media_status: "ready" }}, media_status: "ready" }},
              ],
            }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              async fetchJson(path) {{
                if (path.startsWith("/api/v2/titles/")) {{ titleReads += 1; return titleReads === 1 ? titleMissing : titleReady; }}
                return {{ focus_id: "douban:portrait-stable", nodes: [], edges: [] }};
              }},
              api: {{
                async postV2() {{ return {{ job_id: "portrait-job-stable", state: "queued" }}; }},
                async getV2() {{ return {{ id: "portrait-job-stable", state: "ready" }}; }},
              }},
              setTimer(callback) {{ timers.push(callback); return timers.length; }}, clearTimer() {{}}, mediaPollInterval: 1,
            }});
            await renderTitleDetail("douban:portrait-stable"); await flush();
            const cardFor = (name) => collectNodes(root).find((node) => node.classList?.contains("person-card") && node.textContent.includes(name));
            const imageFor = (card) => collectNodes(card).find((node) => node.tagName === "IMG");
            const directorCard = cardFor("导演甲");
            const directorImage = imageFor(directorCard);
            if (!directorCard || !directorImage || timers.length < 1) throw new Error("portrait test did not reach the pending refresh state");
            await timers.shift()(); await flush();
            if (cardFor("导演甲") !== directorCard || imageFor(cardFor("导演甲")) !== directorImage) {{
              throw new Error("a different person completing reloaded an already ready director portrait");
            }}
            console.log(JSON.stringify({{ sameCard: true, sameImage: true, titleReads }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["sameCard"])
        self.assertTrue(result["sameImage"])

    def test_detail_people_jobs_poll_refresh_title_and_patch_people_section(self):
        output = run_node_module(
            f'''
            class FakeClassList {{ constructor(owner) {{ this.owner = owner; }} add(name) {{ this.owner.className = [...new Set(`${{this.owner.className}} ${{name}}`.split(/\\s+/).filter(Boolean))].join(" "); }} remove(name) {{ this.owner.className = this.owner.className.split(/\\s+/).filter((value) => value && value !== name).join(" "); }} toggle(name, force) {{ if (force) this.add(name); else this.remove(name); }} }}
            class FakeElement {{
              constructor(tagName) {{ this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}}; this.className = ""; this.textContent = ""; this.id = ""; this.hidden = false; this.disabled = false; this.classList = new FakeClassList(this); this.style = {{ setProperty() {{}} }}; }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 1, height: 1 }}; }}
              focus() {{}}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag), createDocumentFragment: () => new FakeElement("fragment") }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const root = new FakeElement("main");
            const timers = [];
            const posts = [];
            const gets = [];
            const titleMissing = {{ item_key: "douban:42", title: "People Poll", media_type: "movie", year: 2024, poster: {{ url: "/media/poster.webp", media_status: "ready" }}, backdrop: {{ url: "", media_status: "missing" }}, item: {{ summary: "Complete synopsis", genres: ["Drama"], directors: ["Director A"], casts: ["Actor B"] }}, people: [{{ id: "person-director", role: "director", name: "Director A", portrait: {{ url: "", media_status: "missing" }} }}, {{ id: "person-cast", role: "cast", name: "Actor B", portrait: {{ url: "", media_status: "missing" }} }}] }};
            const titleReady = {{ ...titleMissing, people: [{{ id: "person-director", role: "director", name: "Director A", portrait: {{ url: "/media/director.webp", media_status: "ready" }} }}, {{ id: "person-cast", role: "cast", name: "Actor B", portrait: {{ url: "", media_status: "degraded" }} }}] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson: async (path) => {{ gets.push(path); return path.startsWith("/api/v2/titles/") ? (gets.filter((item) => item === "/api/v2/titles/douban:42").length > 1 ? titleReady : titleMissing) : {{ focus_id: "douban:42", nodes: [], edges: [] }}; }},
              api: {{ async postV2(path, payload) {{ posts.push({{ path, payload }}); return {{ job_id: `person-job-${{posts.length}}`, state: "queued" }}; }}, async getV2(path) {{ gets.push(path); return {{ id: path.split("/").pop(), state: path.endsWith("1") ? "ready" : "degraded" }}; }} }},
              setTimer(callback) {{ timers.push(callback); return timers.length; }}, clearTimer() {{}}, mediaPollInterval: 1,
            }});
            await renderTitleDetail("douban:42");
            const page = root.firstElementChild;
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const portraitPosts = posts.filter((post) => post.payload.kind === "portrait");
            if (portraitPosts.length !== 2) throw new Error(`expected two portrait jobs, got ${{posts.length}} total / ${{portraitPosts.length}} portrait`);
            if (!collect(page).map((node) => node.textContent).join(" ").includes("正在匹配 2 位演职人员肖像")) throw new Error("portrait controls did not enter pending state");
            const pendingJobs = collect(page).filter((node) => node.className === "person-card__job");
            const pendingText = pendingJobs.map((node) => node.textContent).join(" ");
            const pendingStates = pendingJobs.map((node) => node.dataset.state).sort();
            if (pendingJobs.length !== 2 || !pendingText.includes("正在匹配真实肖像")) throw new Error(`pending portrait status was not user-facing Chinese: ${{pendingText}}`);
            if (["in-progress", "success", "failed"].some((state) => pendingText.includes(state))) throw new Error(`pending portrait status leaked internal enum: ${{pendingText}}`);
            if (pendingStates.join(",") !== "in-progress,in-progress") throw new Error(`pending portrait data-state was lost: ${{pendingStates}}`);
            for (let index = 0; index < 4; index += 1) await Promise.resolve();
            await timers.shift()();
            await timers.shift()();
            for (let index = 0; index < 8; index += 1) await Promise.resolve();
            const titleReads = gets.filter((path) => path === "/api/v2/titles/douban:42").length;
            const nodes = collect(page);
            const text = nodes.map((node) => node.textContent).join(" ");
            const terminalJobs = nodes.filter((node) => node.className === "person-card__job");
            const terminalText = terminalJobs.map((node) => node.textContent).join(" ");
            const terminalStates = terminalJobs.map((node) => node.dataset.state).sort();
            if (titleReads < 2) throw new Error(`terminal portrait jobs did not refresh title: ${{gets}}`);
            if (root.firstElementChild !== page) throw new Error("detail refresh remounted the title page");
            if (!terminalText.includes("真实肖像已补齐") || !terminalText.includes("暂未找到可核对的肖像")) throw new Error(`terminal portrait state was not patched into people rail: ${{terminalText}}`);
            if (["in-progress", "success", "failed"].some((state) => terminalText.includes(state))) throw new Error(`terminal portrait status leaked internal enum: ${{terminalText}}`);
            if (terminalStates.join(",") !== "failed,success") throw new Error(`terminal portrait data-state was lost: ${{terminalStates}}`);
            if (!text.includes("肖像暂未命中") || !text.includes("本地肖像已就绪")) throw new Error(`portrait media availability was not preserved: ${{text}}`);
            console.log(JSON.stringify({{ posts, gets, samePage: root.firstElementChild === page, text, pendingStates, terminalStates }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, len([post for post in result["posts"] if post["payload"]["kind"] == "portrait"]))
        self.assertTrue(result["samePage"])

    def test_person_sheet_is_contextual_closable_and_restores_trigger_focus(self):
        output = run_node_module(
            f'''
            class FakeClassList {{
              constructor(owner) {{ this.owner = owner; }}
              add(name) {{ const values = new Set(this.owner.className.split(/\\s+/).filter(Boolean)); values.add(name); this.owner.className = [...values].join(" "); }}
              remove(name) {{ this.owner.className = this.owner.className.split(/\\s+/).filter((value) => value && value !== name).join(" "); }}
            }}
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.classList = new FakeClassList(this);
                this.style = {{ setProperty() {{}} }}; this.focusCount = 0;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              remove() {{ if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); }}
              focus() {{ this.focusCount += 1; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const overlayRoot = new FakeElement("div");
            const pageRoot = new FakeElement("main");
            const trigger = new FakeElement("button");
            const listeners = new Map();
            globalThis.document = {{
              activeElement: trigger,
              createElement: (tag) => new FakeElement(tag),
              getElementById(id) {{ return id === "overlay-root" ? overlayRoot : null; }},
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const person = {{
              id: "person:1", name: "演员乙", aliases: ["Actor B"], bio: "", media_status: "pending",
              portrait: {{ url: "https://external.invalid/wrong.jpg", media_status: "pending" }},
              known_for: [{{ id: "douban:77", title: "证据作品", year: 2021, media_type: "电影", poster: {{ url: "", media_status: "missing" }} }}],
              evidence: [{{ title_id: "douban:77", title: "证据作品", roles: ["cast"] }}],
            }};
            const {{ configurePeople, openPersonSheet, renderPersonPage, setPersonContext }} = await import("{module_url('js/features/people.js')}");
            const fetchPaths = [];
            configurePeople({{ overlayRoot, root: pageRoot, async fetchJson(path) {{ fetchPaths.push(path); return person; }} }});
            setPersonContext({{ item_key: "douban:42", title: "银幕测试", people: [{{ id: "person:1", name: "演员乙", role: "cast" }}] }});
            await openPersonSheet("person:1", {{ left: 12, top: 16, width: 90, height: 120 }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            let nodes = collect(overlayRoot);
            if (!nodes.some((node) => node.className.includes("person-sheet"))) throw new Error("person sheet was not mounted in overlay root");
            if (!nodes.map((node) => node.textContent).join("|").includes("银幕测试")) throw new Error("origin title context was lost");
            if (nodes.some((node) => node.tagName === "IMG")) throw new Error("unready or external portrait entered visible DOM");
            const fullPageLink = nodes.find((node) => node.tagName === "A");
            if (fullPageLink?.attributes.get("href") !== "/person/person:1") throw new Error("full person route was not exposed");
            if (fetchPaths[0] !== "/api/v2/people/person:1") throw new Error(`person API path encoded the safe identity: ${{fetchPaths[0]}}`);
            for (const listener of listeners.get("keydown") ?? []) listener({{ key: "Escape" }});
            if (overlayRoot.children.length !== 0 || trigger.focusCount !== 1) throw new Error("Escape did not close and restore trigger focus");

            await openPersonSheet("person:1", {{ left: 0, top: 0, width: 1, height: 1 }});
            const backdrop = overlayRoot.firstElementChild;
            backdrop.onclick({{ target: backdrop }});
            if (overlayRoot.children.length !== 0 || trigger.focusCount !== 2) throw new Error("backdrop did not close the sheet");

            await openPersonSheet("person:1", {{ left: 0, top: 0, width: 1, height: 1 }});
            nodes = collect(overlayRoot);
            nodes.find((node) => node.className === "person-sheet__full-link").onclick();
            if (overlayRoot.children.length !== 0 || trigger.focusCount !== 2) throw new Error("full-page navigation covered the destination or restored stale focus");

            await renderPersonPage("person:1");
            nodes = collect(pageRoot);
            if (!nodes.some((node) => node.tagName === "A" && node.attributes.get("href") === "/title/douban:77")) {{
              throw new Error("known_for credit did not use its stable backend title id");
            }}
            const limitedPerson = {{ ...person, known_for: [], evidence: [] }};
            configurePeople({{ overlayRoot, root: pageRoot, async fetchJson() {{ return limitedPerson; }} }});
            await renderPersonPage("person:1");
            nodes = collect(pageRoot);
            const pageText = nodes.map((node) => node.textContent).join("|");
            if (!nodes.some((node) => node.className.includes("person-page")) || !pageText.includes("资料有限") || !pageText.includes("银幕测试")) {{
              throw new Error("person page did not retain limited-data title context");
            }}
            console.log(JSON.stringify({{ focusCount: trigger.focusCount, href: fullPageLink.attributes.get("href"), pageText }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["focusCount"])
        self.assertEqual("/person/person:1", result["href"])
        self.assertIn("资料有限", result["pageText"])

    def test_person_sheet_route_lifecycle_aborts_fetch_cleans_listeners_and_ignores_late_response(self):
        output = run_node_module(
            f'''
            const deferred = () => {{ let resolve, reject; const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }}); return {{ promise, resolve, reject }}; }};
            class FakeClassList {{ add() {{}} }}
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.classList = new FakeClassList(); this.style = {{ setProperty() {{}} }};
                this.focusCount = 0; this.isConnected = true; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              remove() {{ if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.isConnected = false; }}
              focus() {{ this.focusCount += 1; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const overlayRoot = new FakeElement("div");
            const trigger = new FakeElement("button");
            const listeners = new Map();
            const requests = [];
            globalThis.document = {{
              readyState: "loading", activeElement: trigger,
              createElement: (tag) => new FakeElement(tag),
              getElementById(id) {{ return id === "overlay-root" ? overlayRoot : null; }},
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ configurePeople, openPersonSheet, closePersonSheet, setPersonContext }} = await import("{module_url('js/features/people.js')}");
            configurePeople({{
              overlayRoot,
              fetchJson(path, options) {{ const pending = deferred(); requests.push({{ path, signal: options?.signal, pending }}); return pending.promise; }},
            }});
            setPersonContext({{ item_key: "douban:42", title: "Origin title", people: [{{ id: "person:1", name: "Person", role: "cast" }}] }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];

            const originRequest = openPersonSheet("person:1", {{ left: 1, top: 1, width: 2, height: 2 }});
            if (!requests[0]?.signal || requests[0].signal.aborted) throw new Error("sheet fetch did not receive its own active AbortSignal");
            const originLink = collect(overlayRoot).find((node) => node.className === "person-origin__link");
            if (typeof originLink?.onclick !== "function") throw new Error("origin title link was not bound to sheet close lifecycle");
            originLink.onclick();
            if (!requests[0].signal.aborted || overlayRoot.children.length !== 0 || (listeners.get("keydown")?.size ?? 0) !== 0) throw new Error("origin navigation did not abort and fully clean the sheet");
            requests[0].pending.resolve({{ id: "person:1", name: "Late person", portrait: {{ url: "", media_status: "missing" }} }});
            await originRequest;
            if (overlayRoot.children.length !== 0) throw new Error("late origin response remounted a closed sheet");
            if (trigger.focusCount !== 0) throw new Error("origin route navigation restored stale sheet focus");

            trigger.isConnected = false;
            const routeRequest = openPersonSheet("person:1", {{ left: 1, top: 1, width: 2, height: 2 }});
            const {{ prepareRouteChange }} = await import("{module_url('js/app.js')}");
            prepareRouteChange();
            if (!requests[1].signal.aborted || overlayRoot.children.length !== 0 || (listeners.get("keydown")?.size ?? 0) !== 0) throw new Error("external route change did not invalidate active sheet resources");
            requests[1].pending.resolve({{ id: "person:1", name: "Later person", portrait: {{ url: "", media_status: "missing" }} }});
            await routeRequest;
            if (overlayRoot.children.length !== 0 || trigger.focusCount !== 0) throw new Error("detached trigger was focused or late route response mutated overlay");
            closePersonSheet();
            console.log(JSON.stringify({{ requests: requests.length, focusCount: trigger.focusCount, listeners: listeners.get("keydown")?.size ?? 0, overlay: overlayRoot.children.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["requests"])
        self.assertEqual(0, result["focusCount"])
        self.assertEqual(0, result["listeners"])
        self.assertEqual(0, result["overlay"])

    def test_person_sheet_api_failure_keeps_full_page_and_origin_navigation(self):
        output = run_node_module(
            f'''
            class FakeClassList {{ add() {{}} }}
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.classList = new FakeClassList(); this.style = {{ setProperty() {{}} }};
                this.isConnected = true; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              remove() {{ if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.isConnected = false; }}
              focus() {{}}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const overlayRoot = new FakeElement("div");
            const listeners = new Map();
            globalThis.document = {{
              activeElement: new FakeElement("button"),
              createElement: (tag) => new FakeElement(tag),
              getElementById(id) {{ return id === "overlay-root" ? overlayRoot : null; }},
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ configurePeople, openPersonSheet, setPersonContext }} = await import("{module_url('js/features/people.js')}");
            configurePeople({{ overlayRoot, async fetchJson() {{ throw new Error("person unavailable"); }} }});
            setPersonContext({{ item_key: "douban:42", title: "Origin title", people: [{{ id: "person:1", name: "Person", role: "cast" }}] }});
            await openPersonSheet("person:1", {{ left: 0, top: 0, width: 1, height: 1 }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const nodes = collect(overlayRoot);
            const fullPage = nodes.find((node) => node.className === "person-sheet__full-link");
            const origin = nodes.find((node) => node.className === "person-origin__link");
            if (fullPage?.attributes.get("href") !== "/person/person:1" || typeof fullPage.onclick !== "function") throw new Error("failure state removed full person navigation");
            if (origin?.attributes.get("href") !== "/title/douban:42" || typeof origin.onclick !== "function") throw new Error("failure state removed origin navigation");
            if (!nodes.map((node) => node.textContent).join("|").includes("Origin title")) throw new Error("failure state lost origin context copy");
            fullPage.onclick();
            if (overlayRoot.children.length !== 0 || (listeners.get("keydown")?.size ?? 0) !== 0) throw new Error("failure navigation did not close and clean sheet");
            console.log(JSON.stringify({{ full: fullPage.attributes.get("href"), origin: origin.attributes.get("href"), overlay: overlayRoot.children.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("/person/person:1", result["full"])
        self.assertEqual("/title/douban:42", result["origin"])
        self.assertEqual(0, result["overlay"])

    def test_async_view_transition_rechecks_route_and_only_current_rejection_falls_back(self):
        output = run_node_module(
            f'''
            const deferred = () => {{ let resolve, reject; const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }}); return {{ promise, resolve, reject }}; }};
            const transitions = [];
            globalThis.document = {{
              readyState: "loading", addEventListener() {{}},
              startViewTransition(update) {{
                const done = deferred();
                transitions.push({{ update, done }});
                return {{ updateCallbackDone: done.promise, finished: done.promise }};
              }},
            }};
            const {{ createExplorationRouteGate }} = await import("{module_url('js/app.js')}");
            const stable = {{ id: "stable" }};
            const root = {{ children: [stable], replaceChildren(...nodes) {{ this.children = nodes; }} }};
            let activePath = "/title/old";
            const statuses = [];
            const renderer = (id, options) => options.commit({{ id: `${{id}}-view` }}, {{ heading: id }});
            const gate = createExplorationRouteGate({{
              root,
              getActivePath: () => activePath,
              renderTitle: renderer,
              renderPerson: renderer,
              setStatus(message) {{ statuses.push(message); }},
            }});

            const oldRender = gate.render({{ path: "/title/old", name: "title", params: {{ id: "old" }} }});
            if (transitions.length !== 1 || root.children[0] !== stable) throw new Error("old transition did not defer its DOM update");
            activePath = "/tonight";
            gate.invalidate();
            transitions[0].update();
            transitions[0].done.resolve();
            await oldRender;
            if (root.children[0] !== stable || statuses.length) throw new Error("stale deferred callback committed old view or status");

            activePath = "/title/current";
            const currentRender = gate.render({{ path: activePath, name: "title", params: {{ id: "current" }} }});
            if (transitions.length !== 2 || root.children[0] !== stable) throw new Error("current transition cleared stable DOM before callback outcome");
            transitions[1].done.reject(new Error("update callback failed asynchronously"));
            await currentRender;
            if (root.children[0]?.id !== "current-view") throw new Error("current transition rejection did not use guarded fallback");
            if (statuses.length !== 1 || !statuses[0].includes("current")) throw new Error(`current commit status was not emitted exactly once: ${{statuses}}`);
            transitions[1].update();
            if (root.children[0]?.id !== "current-view" || statuses.length !== 1) throw new Error("late callback duplicated a completed fallback commit");

            activePath = "/title/stale-rejection";
            const staleRejection = gate.render({{ path: activePath, name: "title", params: {{ id: "stale-rejection" }} }});
            activePath = "/tonight";
            gate.invalidate();
            transitions[2].done.reject(new Error("stale transition failed"));
            await staleRejection;
            if (root.children[0]?.id !== "current-view" || statuses.length !== 1) throw new Error("stale transition rejection replaced the current stable DOM");
            console.log(JSON.stringify({{ transitions: transitions.length, current: root.children[0].id, statuses }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(3, result["transitions"])
        self.assertEqual("current-view", result["current"])
        self.assertEqual(1, len(result["statuses"]))

    def test_standalone_detail_and_person_deferred_transitions_recheck_current_state(self):
        output = run_node_module(
            f'''
            const deferred = () => {{ let resolve, reject; const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }}); return {{ promise, resolve, reject }}; }};
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.id = ""; this.style = {{ setProperty() {{}} }};
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const transitions = [];
            globalThis.document = {{
              createElement: (tag) => new FakeElement(tag),
              startViewTransition(update) {{
                const done = deferred(); transitions.push({{ update, done }});
                return {{ updateCallbackDone: done.promise, finished: done.promise }};
              }},
            }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const title = {{
              item_key: "douban:42", title: "Deferred title", media_type: "movie", year: 2024,
              poster: {{ url: "", media_status: "missing" }}, backdrop: {{ url: "", media_status: "missing" }},
              item: {{ directors: [], casts: [] }}, people: [],
            }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            const detailStable = {{ id: "detail-stable" }};
            const detailRoot = {{ children: [detailStable], replaceChildren(...nodes) {{ this.children = nodes; }} }};
            configureDetail({{
              root: detailRoot,
              async fetchJson(path) {{ return path.startsWith("/api/v2/titles/") ? title : {{ focus_id: "douban:42", nodes: [], edges: [] }}; }},
              api: {{ async postV2() {{ return {{ job_id: "unused" }}; }} }},
            }});
            let detailCurrent = true;
            const detailRender = renderTitleDetail("douban:42", {{ isCurrent: () => detailCurrent }});
            for (let index = 0; index < 12 && transitions.length < 1; index += 1) await Promise.resolve();
            if (transitions.length !== 1 || detailRoot.children[0] !== detailStable) throw new Error("standalone detail transition was not deferred");
            detailCurrent = false;
            transitions[0].update(); transitions[0].done.resolve();
            await detailRender;
            if (detailRoot.children[0] !== detailStable) throw new Error("stale standalone detail callback replaced stable DOM");

            const {{ configurePeople, renderPersonPage }} = await import("{module_url('js/features/people.js')}");
            const personStable = {{ id: "person-stable" }};
            const personRoot = {{ children: [personStable], replaceChildren(...nodes) {{ this.children = nodes; }} }};
            configurePeople({{
              root: personRoot,
              async fetchJson() {{ return {{ id: "person:1", name: "Deferred person", portrait: {{ url: "", media_status: "missing" }}, known_for: [], evidence: [] }}; }},
            }});
            let personCurrent = true;
            const personRender = renderPersonPage("person:1", {{ isCurrent: () => personCurrent }});
            for (let index = 0; index < 12 && transitions.length < 2; index += 1) await Promise.resolve();
            if (transitions.length !== 2 || personRoot.children[0] !== personStable) throw new Error("standalone person transition was not deferred");
            personCurrent = false;
            transitions[1].update(); transitions[1].done.resolve();
            await personRender;
            if (personRoot.children[0] !== personStable) throw new Error("stale standalone person callback replaced stable DOM");
            console.log(JSON.stringify({{ transitions: transitions.length, detail: detailRoot.children[0].id, person: personRoot.children[0].id }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["transitions"])
        self.assertEqual("detail-stable", result["detail"])
        self.assertEqual("person-stable", result["person"])

    def test_universe_lazily_draws_bounded_nodes_and_keeps_semantic_relations_in_sync(self):
        output = run_node_module(
            f'''
            class FakeClassList {{
              constructor(owner) {{ this.owner = owner; }}
              toggle(name, force) {{
                const names = new Set(this.owner.className.split(/\\s+/).filter(Boolean));
                if (force) names.add(name); else names.delete(name);
                this.owner.className = [...names].join(" ");
              }}
              add(name) {{ this.toggle(name, true); }}
              remove(name) {{ this.toggle(name, false); }}
            }}
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.style = {{ setProperty() {{}} }}; this.listeners = new Map();
                this.classList = new FakeClassList(this); this.width = 0; this.height = 0; this.disabled = false;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              dispatch(type, event = {{}}) {{ for (const listener of this.listeners.get(type) ?? []) listener({{ target: this, currentTarget: this, ...event }}); }}
              focus() {{ document.activeElement = this; }}
              getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 900, height: 560 }}; }}
              getContext() {{ return this.tagName === "CANVAS" ? context2d : null; }}
              setPointerCapture(id) {{ this.pointerCapture = id; }}
              hasPointerCapture(id) {{ return this.pointerCapture === id; }}
              releasePointerCapture(id) {{ if (this.pointerCapture === id) this.pointerCapture = null; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const drawCalls = [];
            const context2d = new Proxy({{
              canvas: null, measureText(text) {{ return {{ width: String(text).length * 7 }}; }},
            }}, {{ get(target, key) {{
              if (key in target) return target[key];
              if (key === "setTransform" || key === "clearRect" || key === "beginPath" || key === "moveTo" || key === "lineTo" || key === "stroke" || key === "arc" || key === "fill" || key === "fillText" || key === "save" || key === "restore") return (...args) => drawCalls.push([key, ...args]);
              return target[key];
            }}, set(target, key, value) {{ target[key] = value; return true; }} }});
            const observers = [];
            globalThis.IntersectionObserver = class {{ constructor(callback) {{ this.callback = callback; this.disconnected = false; observers.push(this); }} observe(target) {{ this.target = target; }} disconnect() {{ this.disconnected = true; }} }};
            globalThis.ResizeObserver = class {{ constructor(callback) {{ this.callback = callback; this.disconnected = false; }} observe(target) {{ this.target = target; }} disconnect() {{ this.disconnected = true; }} }};
            const rafs = new Map(); let rafId = 0;
            globalThis.requestAnimationFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            globalThis.cancelAnimationFrame = (id) => rafs.delete(id);
            globalThis.window = {{ devicePixelRatio: 1, addEventListener() {{}}, removeEventListener() {{}}, matchMedia: () => ({{ matches: false }}) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            globalThis.document = {{ activeElement: null, createElement: (tag) => new FakeElement(tag) }};

            const {{ configureUniverse, destroyUniverse, focusNode, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            configureUniverse({{ async fetchJson() {{ throw new Error("render must not fetch"); }} }});
            const nodes = Array.from({{ length: 12 }}, (_, index) => ({{
              id: `item:${{index}}`, title: `作品 ${{index}}`, media_type: "movie", year: 2000 + index,
              poster: {{ url: index === 1 ? "https://remote.test/poster.jpg" : "", media_status: "missing" }},
            }}));
            const edges = Array.from({{ length: 11 }}, (_, index) => ({{
              source: "item:0", target: `item:${{index + 1}}`, score: index === 0 ? 8.2 : 0.95 - index / 100,
              reason: `主理由 ${{index + 1}}`, reasons: [`共同导演 ${{index + 1}}`, `共同类型 剧情`],
            }}));
            const container = new FakeElement("main");
            const view = renderUniverse(container, {{ focus_id: "item:0", nodes, edges }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const all = collect(view);
            const canvas = all.find((node) => node.tagName === "CANVAS");
            const relationList = all.find((node) => node.className.includes("relationship-list"));
            const relationRows = all.filter((node) => node.className.includes("relationship-list__item"));
            const nodeButtons = all.filter((node) => node.className.includes("universe-node-button"));
            if (!canvas || canvas.getAttribute("tabindex") !== "0" || !canvas.getAttribute("aria-label")?.includes("口味宇宙")) throw new Error("canvas keyboard contract missing");
            if (!relationList || relationRows.length !== 8 || nodeButtons.length !== 9) throw new Error(`bounded semantic graph mismatch: ${{relationRows.length}}/${{nodeButtons.length}}`);
            const relationText = relationRows.map((row) => collect(row).map((node) => node.textContent).join(" ")).join(" | ");
            if (!relationText.includes("作品 0") || !relationText.includes("作品 1") || !relationText.includes("主理由 1") || !relationText.includes("共同导演 1") || !relationText.includes("8.2")) throw new Error("semantic relation omitted source, target, reason/reasons, or score");
            if (drawCalls.length !== 0 || rafs.size !== 0) throw new Error("canvas drew before intersection");

            observers[0].callback([{{ isIntersecting: true, target: canvas }}]);
            if (rafs.size !== 1) throw new Error("intersection did not schedule one bounded draw");
            const firstFrame = [...rafs.entries()][0]; rafs.delete(firstFrame[0]); firstFrame[1](16);
            if (!drawCalls.length || rafs.size !== 0) throw new Error("static canvas kept a resident RAF loop");

            focusNode("item:2");
            const focusedButton = nodeButtons.find((button) => button.dataset.nodeId === "item:2");
            if (focusedButton?.getAttribute("aria-current") !== "true") throw new Error("semantic list did not follow canvas focus");
            let prevented = 0;
            canvas.dispatch("wheel", {{ deltaY: -1, preventDefault() {{ prevented += 1; }} }});
            if (prevented !== 0) throw new Error("unfocused canvas blocked page scroll");
            canvas.focus();
            canvas.dispatch("wheel", {{ deltaY: -1, preventDefault() {{ prevented += 1; }} }});
            if (prevented !== 1 || rafs.size !== 1) throw new Error("focused canvas did not own wheel zoom");
            canvas.dispatch("pointerdown", {{ pointerId: 7, clientX: 20, clientY: 20 }});
            if (canvas.pointerCapture !== 7) throw new Error("pointer drag did not capture the canvas");

            destroyUniverse();
            const remainingListeners = [...canvas.listeners.values()].reduce((total, listeners) => total + listeners.size, 0);
            if (!observers[0].disconnected || rafs.size !== 0 || container.children.length !== 0 || canvas.pointerCapture !== null || remainingListeners !== 0) throw new Error("destroy left observer, RAF, capture, listeners, or DOM alive");
            const empty = renderUniverse(container, null);
            if (!empty?.className.includes("universe-empty") || container.children.length !== 1) throw new Error("bare universe did not render its designed empty state");
            destroyUniverse();
            if (container.children.length !== 0) throw new Error("destroy did not clear the focusless universe DOM");
            console.log(JSON.stringify({{ relations: relationRows.length, nodes: nodeButtons.length, prevented, draws: drawCalls.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(8, result["relations"])
        self.assertEqual(9, result["nodes"])
        self.assertEqual(1, result["prevented"])
        self.assertGreater(result["draws"], 0)

    def test_universe_to_slow_detail_preserves_static_dom_until_atomic_commit(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            FakeElement.prototype.getBoundingClientRect = function() {{ return {{ left: 0, top: 0, width: 900, height: 560 }}; }};
            FakeElement.prototype.getContext = function() {{ return null; }};
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            globalThis.requestAnimationFrame = () => 1; globalThis.cancelAnimationFrame = () => {{}};
            const root = new FakeElement("main"); let fetches = 0;
            const universe = await import("{module_url('js/features/universe.js')}");
            universe.configureUniverse({{ async fetchJson() {{ fetches += 1; throw new Error("interaction must be stopped"); }} }});
            universe.renderUniverse(root, {{ focus_id: "douban:A", nodes: [{{ id: "douban:A", title: "旧宇宙节点" }}], edges: [] }});
            const oldView = root.firstElementChild;
            const {{ prepareRouteChange, createAppRouteHandler }} = await import("{module_url('js/app.js')}");
            prepareRouteChange();
            if (root.firstElementChild !== oldView || root.children.length === 0) throw new Error("prepareRouteChange blanked Universe DOM");
            const oldNodeButton = collectNodes(oldView).find((node) => node.dataset?.nodeId === "douban:A");
            oldNodeButton?.dispatchEvent({{ type: "click" }}); await flush();
            if (fetches !== 0) throw new Error("preserved Universe DOM retained click interactions");

            let resolveDetail; const detailReady = new Promise((resolve) => {{ resolveDetail = resolve; }});
            const store = {{
              state: {{ activePath: "/universe", recommendation: {{ channels: {{}} }}, candidateTray: {{ context: {{ universeFocusId: "douban:A" }} }} }},
              getState() {{ return this.state; }}, dispatch(action) {{ if (action.type === "route/changed") this.state.activePath = action.route.path; }},
            }};
            const invalidations = [];
            const universeGate = {{ invalidate(options) {{ invalidations.push(options || {{}}); if (!options?.preserveDom) root.replaceChildren(); }} }};
            const explorationGate = {{
              invalidate() {{}},
              async render() {{ await detailReady; root.replaceChildren({{ id: "detail-view", textContent: "新详情", children: [], focus() {{}}, setAttribute() {{}} }}); }},
            }};
            const noOpGate = {{ invalidate() {{}}, async restore() {{}} }};
            const handler = createAppRouteHandler({{
              appView: root, store, restoreGate: noOpGate, explorationGate, universeGate,
              prepare() {{}}, setNavigation() {{}}, setStatus() {{}}, announceRoute() {{}},
            }});
            const navigation = handler({{ name: "title", path: "/title/douban%3AB", params: {{ id: "douban:B" }} }});
            await flush();
            if (root.firstElementChild !== oldView || root.children.length === 0) throw new Error("slow detail blanked preserved Universe DOM while pending");
            if (invalidations.length !== 1 || invalidations[0].preserveDom !== true) throw new Error("route gate did not request preserveDom invalidation");
            resolveDetail(); await navigation;
            if (root.firstElementChild?.id !== "detail-view") throw new Error("detail did not atomically replace preserved Universe DOM");
            console.log(JSON.stringify({{ fetches, invalidations, final: root.firstElementChild.id }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(0, result["fetches"])
        self.assertEqual("detail-view", result["final"])

    def test_universe_nodes_expose_stable_detail_and_tonight_actions(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            FakeElement.prototype.getBoundingClientRect = function() {{ return {{ left: 0, top: 0, width: 900, height: 560 }}; }};
            FakeElement.prototype.getContext = function() {{ return null; }};
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            globalThis.requestAnimationFrame = () => 1; globalThis.cancelAnimationFrame = () => {{}};
            const root = new FakeElement("main"); const recommended = [];
            const {{ configureUniverse, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            configureUniverse({{ onRecommendNode(node) {{ recommended.push(node); }} }});
            renderUniverse(root, {{
              focus_id: "douban:A",
              nodes: [{{ id: "douban:A", title: "绝不能拿标题猜 ID" }}, {{ id: "derived:B", title: "节点乙" }}],
              edges: [{{ source: "douban:A", target: "derived:B", score: 0.8, reasons: ["共同类型"] }}],
            }});
            const all = collectNodes(root); const rosterDetails = all.filter((node) => node.className === "universe-node-detail");
            const rosterRecommend = all.filter((node) => node.className === "universe-node-recommend");
            const relation = all.find((node) => node.className === "relationship-list__item");
            const relationNodes = collectNodes(relation);
            const relationDetail = relationNodes.find((node) => node.className === "relationship-list__detail");
            const relationRecommend = relationNodes.find((node) => node.className === "relationship-list__recommend");
            const hrefs = rosterDetails.map((node) => node.getAttribute("href")).sort();
            if (JSON.stringify(hrefs) !== JSON.stringify(["/title/derived%3AB", "/title/douban%3AA"])) throw new Error(`roster detail routes are not encoded stable IDs: ${{hrefs}}`);
            if (rosterDetails.length !== 2 || rosterRecommend.length !== 2 || !relationDetail || !relationRecommend) throw new Error("every Universe node surface lacks both actions");
            if (relationDetail.getAttribute("href") !== "/title/derived%3AB") throw new Error("relationship detail guessed a title instead of target ID");
            rosterRecommend[1].dispatchEvent({{ type: "click" }}); relationRecommend.dispatchEvent({{ type: "click" }});
            if (recommended.length !== 2 || recommended.some((node) => node.id !== "derived:B") || recommended.some((node) => node.id === node.title)) throw new Error("recommend action did not carry stable node identity");
            console.log(JSON.stringify({{ hrefs, recommended }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["/title/derived%3AB", "/title/douban%3AA"], result["hrefs"])
        self.assertEqual("derived:B", result["recommended"][0]["id"])

    def test_universe_tonight_action_updates_bounded_tray_then_opens_safe_lens(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const values = new Map(); globalThis.localStorage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            const {{ createEmptyUiState, createStore, persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const {{ createUniverseRecommendationHandler, reduceUiState }} = await import("{module_url('js/app.js')}");
            const store = createStore(createEmptyUiState(), reduceUiState); const navigations = []; const lensTexts = [];
            const handler = createUniverseRecommendationHandler({{
              store,
              navigate(path) {{
                navigations.push(path);
                store.dispatch({{ type: "route/changed", route: {{ path, name: "tonight", params: {{}} }} }});
                return Promise.resolve({{ path, name: "tonight", params: {{}} }});
              }},
              openLens(text) {{ lensTexts.push(text); }},
            }});
            for (let index = 0; index < 30; index += 1) await handler({{ id: `derived:${{index}}`, title: `安全节点 ${{index}}` }});
            await handler({{ id: "derived:29", title: "重复节点" }});
            await handler({{ id: "douban:42", title: "Authorization: Bearer sk-1234567890abcdef" }});
            await handler({{ id: "bad/id", title: "非法节点" }});
            const state = store.getState(); persistUiState(state); const restored = restoreUiState();
            if (state.candidateTray.itemIds.length !== 24 || new Set(state.candidateTray.itemIds).size !== 24) throw new Error("candidate tray was not deduped and bounded");
            if (!state.candidateTray.itemIds.includes("douban:42") || state.candidateTray.itemIds.includes("bad/id")) throw new Error("candidate tray accepted the wrong stable IDs");
            if (restored.candidateTray.itemIds.length !== 24) throw new Error("candidate tray did not survive refresh");
            if (navigations.length !== lensTexts.length || navigations.some((path) => path !== "/tonight")) throw new Error("Tonight navigation and Lens integration diverged");
            if (lensTexts.at(-1)?.includes("Authorization") || lensTexts.at(-1)?.includes("sk-")) throw new Error("unsafe title entered Command Lens prefill");
            console.log(JSON.stringify({{ tray: state.candidateTray.itemIds, restored: restored.candidateTray.itemIds, navigations: navigations.length, lastLens: lensTexts.at(-1) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(24, len(result["tray"]))
        self.assertEqual(24, len(result["restored"]))
        self.assertEqual(32, result["navigations"])

    def test_universe_tonight_handoff_requires_latest_committed_router_result(self):
        output = run_node_module(
            f'''
            const deferred = () => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }};
            const slowTonight = deferred(); const values = new Map(); const listeners = new Map();
            const browser = {{
              location: {{ pathname: "/universe" }}, scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }}, removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }}, requestAnimationFrame(callback) {{ callback(); return 1; }}, scrollTo() {{}},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser); globalThis.PopStateEvent = browser.PopStateEvent;
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createRouter }} = await import("{module_url('js/core/router.js')}");
            const {{ createEmptyUiState, createStore }} = await import("{module_url('js/core/store.js')}");
            const {{ createUniverseRecommendationHandler, reduceUiState }} = await import("{module_url('js/app.js')}");
            const store = createStore(createEmptyUiState(), reduceUiState); const lens = []; let deferTonight = true;
            const router = createRouter([
              {{ pattern: "/universe", name: "universe" }}, {{ pattern: "/tonight", name: "tonight" }}, {{ pattern: "/health", name: "health" }},
            ], {{
              async onRoute(route) {{
                store.dispatch({{ type: "route/changed", route }});
                if (route.path === "/tonight" && deferTonight) await slowTonight.promise;
                return true;
              }},
            }});
            await router.start();
            const handler = createUniverseRecommendationHandler({{ store, navigate: (path) => router.navigate(path), openLens: (text) => lens.push(text) }});
            const staleHandoff = handler({{ id: "douban:slow", title: "慢节点" }});
            await Promise.resolve();
            await router.navigate("/health");
            slowTonight.resolve(true);
            const staleResult = await staleHandoff;
            if (staleResult !== false || router.currentRoute?.path !== "/health" || store.getState().activePath !== "/health") throw new Error("slow Tonight handoff overrode committed Health");
            if (store.getState().candidateTray.itemIds.length || lens.length) throw new Error("stale Tonight handoff mutated tray or opened Lens");

            deferTonight = false;
            const success = await handler({{ id: "douban:success", title: "成功节点" }});
            if (success !== true || router.currentRoute?.path !== "/tonight" || store.getState().activePath !== "/tonight") throw new Error("committed Tonight handoff was rejected");
            if (store.getState().candidateTray.itemIds.join() !== "douban:success" || lens.length !== 1) throw new Error("successful Tonight handoff did not trigger exactly once");

            let firstResolve; let navigationCall = 0;
            const latestHandler = createUniverseRecommendationHandler({{
              store,
              navigate() {{
                navigationCall += 1;
                if (navigationCall === 1) return new Promise((resolve) => {{ firstResolve = resolve; }});
                store.dispatch({{ type: "route/changed", route: {{ path: "/tonight", name: "tonight", params: {{}} }} }});
                return Promise.resolve({{ path: "/tonight", name: "tonight", params: {{}} }});
              }},
              openLens: (text) => lens.push(text),
            }});
            const superseded = latestHandler({{ id: "douban:old", title: "旧 handoff" }});
            const latest = await latestHandler({{ id: "douban:new", title: "新 handoff" }});
            firstResolve({{ path: "/tonight", name: "tonight", params: {{}} }});
            const supersededResult = await superseded;
            if (!latest || supersededResult !== false || store.getState().candidateTray.itemIds.includes("douban:old") || !store.getState().candidateTray.itemIds.includes("douban:new")) throw new Error("handoff generation did not keep only latest completion");

            const beforeReject = JSON.stringify(store.getState().candidateTray.itemIds); const beforeLens = lens.length;
            const rejectedHandler = createUniverseRecommendationHandler({{ store, navigate: () => Promise.reject(new Error("navigation failed")), openLens: (text) => lens.push(text) }});
            const rejected = await rejectedHandler({{ id: "douban:reject", title: "拒绝节点" }});
            if (rejected !== false || JSON.stringify(store.getState().candidateTray.itemIds) !== beforeReject || lens.length !== beforeLens) throw new Error("rejected navigation mutated handoff state");
            for (const [label, navigationResult] of [["false", false], ["mismatch", {{ path: "/health", name: "health" }}]]) {{
              const guardedHandler = createUniverseRecommendationHandler({{ store, navigate: () => Promise.resolve(navigationResult), openLens: (text) => lens.push(text) }});
              const guarded = await guardedHandler({{ id: `douban:${{label}}`, title: label }});
              if (guarded !== false || JSON.stringify(store.getState().candidateTray.itemIds) !== beforeReject || lens.length !== beforeLens) throw new Error(`${{label}} navigation result mutated handoff state`);
            }}
            console.log(JSON.stringify({{ current: router.currentRoute.path, active: store.getState().activePath, tray: store.getState().candidateTray.itemIds, lens: lens.length, staleResult, success, supersededResult, rejected }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("/tonight", result["current"])
        self.assertEqual("/tonight", result["active"])
        self.assertNotIn("douban:slow", result["tray"])
        self.assertNotIn("douban:old", result["tray"])
        self.assertIn("douban:success", result["tray"])
        self.assertIn("douban:new", result["tray"])

    def test_universe_ui_expansion_error_is_visible_without_unhandled_rejection(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            FakeElement.prototype.getBoundingClientRect = function() {{ return {{ left: 0, top: 0, width: 900, height: 560 }}; }};
            FakeElement.prototype.getContext = function() {{ return null; }};
            FakeElement.prototype.removeAttribute = function(name) {{ this.attributes.delete(name); }};
            globalThis.requestAnimationFrame = () => 1; globalThis.cancelAnimationFrame = () => {{}};
            const unhandled = []; process.on("unhandledRejection", (error) => unhandled.push(error.message));
            const root = new FakeElement("main");
            const {{ configureUniverse, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            configureUniverse({{
              async fetchJson() {{ const error = new Error("expand failed"); error.status = 503; throw error; }},
              onRecommendNode() {{ return Promise.reject(new Error("recommend failed")); }},
            }});
            renderUniverse(root, {{
              focus_id: "douban:A",
              nodes: [{{ id: "douban:A", title: "节点甲" }}, {{ id: "douban:B", title: "节点乙" }}],
              edges: [{{ source: "douban:A", target: "douban:B", score: 0.8, reasons: ["共同类型"] }}],
            }});
            const expand = collectNodes(root).find((node) => node.className === "relationship-list__expand");
            const recommend = collectNodes(root).find((node) => node.className === "relationship-list__recommend");
            expand.dispatchEvent({{ type: "click" }});
            recommend.dispatchEvent({{ type: "click" }});
            await new Promise((resolve) => setTimeout(resolve, 0));
            await new Promise((resolve) => setTimeout(resolve, 0));
            const note = collectNodes(root).find((node) => node.className === "universe-limit-note");
            if (!note?.textContent.includes("暂时无法继续展开") || note.hidden) throw new Error("expandNode did not render its visible error");
            if (unhandled.length) throw new Error(`UI event leaked unhandled rejection: ${{unhandled}}`);
            console.log(JSON.stringify({{ note: note.textContent, unhandled }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual([], result["unhandled"])
        self.assertIn("暂时无法继续展开", result["note"])

    def test_universe_expansion_dedupes_requests_caps_graph_and_ignores_destroyed_responses(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{ this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}}; this.className = ""; this.textContent = ""; this.style = {{ setProperty() {{}} }}; this.listeners = new Map(); }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }} appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }} setAttribute(name, value) {{ this.attributes.set(name, String(value)); }} getAttribute(name) {{ return this.attributes.get(name) ?? null; }} removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }} removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 800, height: 500 }}; }} getContext() {{ return this.tagName === "CANVAS" ? new Proxy({{}}, {{ get: () => () => {{}} }}) : null; }}
              hasPointerCapture() {{ return false; }} get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const deferred = () => {{ let resolve, reject; const promise = new Promise((yes, no) => {{ resolve = yes; reject = no; }}); return {{ promise, resolve, reject }}; }};
            globalThis.document = {{ activeElement: null, createElement: (tag) => new FakeElement(tag) }};
            globalThis.window = {{ devicePixelRatio: 1, addEventListener() {{}}, removeEventListener() {{}}, matchMedia: () => ({{ matches: true }}) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            globalThis.requestAnimationFrame = (callback) => 1; globalThis.cancelAnimationFrame = () => {{}};
            delete globalThis.IntersectionObserver; delete globalThis.ResizeObserver;

            const requests = []; const contexts = [];
            const {{ configureUniverse, destroyUniverse, expandNode, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            configureUniverse({{
              fetchJson(path, options) {{ const pending = deferred(); requests.push({{ path, options, pending }}); return pending.promise; }},
              onContextChange(context) {{ contexts.push(context); }},
            }});
            const container = new FakeElement("main");
            renderUniverse(container, {{ focus_id: "item:0", nodes: [{{ id: "item:0", title: "起点" }}], edges: [] }});
            const first = expandNode("item:1"); const shared = expandNode("item:1");
            if (first !== shared || requests.length !== 1 || !requests[0].path.endsWith("focus=item%3A1&limit=9")) throw new Error("same-node expansion was not shared");
            const expansionNodes = Array.from({{ length: 45 }}, (_, index) => ({{ id: `item:${{index}}`, title: `作品 ${{index}}` }}));
            const expansionEdges = Array.from({{ length: 44 }}, (_, index) => ({{ source: "item:1", target: `item:${{index + 1}}`, score: 1 - index / 100, reasons: [`理由 ${{index}}`] }}));
            requests[0].pending.resolve({{ focus_id: "item:1", nodes: expansionNodes, edges: expansionEdges }});
            await first;
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const all = collect(container);
            const buttons = all.filter((node) => node.className.includes("universe-node-button"));
            if (buttons.length > 36) throw new Error(`graph exceeded cap: ${{buttons.length}}`);
            if (!all.map((node) => node.textContent).join(" ").includes("36")) throw new Error("cap explanation was not visible");
            if (!contexts.at(-1)?.expandedIds?.includes("item:1") || contexts.at(-1)?.universeFocusId !== "item:1") throw new Error("persisted context did not use stable ids");

            const late = expandNode("item:2");
            if (requests.length !== 2) throw new Error("second expansion did not start");
            destroyUniverse();
            requests[1].pending.resolve({{ focus_id: "item:2", nodes: [{{ id: "late", title: "迟到" }}], edges: [] }});
            await late;
            if (container.children.length !== 0 || !requests[1].options.signal.aborted) throw new Error("destroyed generation accepted a late response or failed to abort");
            console.log(JSON.stringify({{ requests: requests.length, nodes: buttons.length, contexts: contexts.length, aborted: requests[1].options.signal.aborted }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["requests"])
        self.assertLessEqual(result["nodes"], 36)
        self.assertGreaterEqual(result["contexts"], 1)
        self.assertTrue(result["aborted"])

    def test_universe_expansion_merge_schedules_one_visible_canvas_redraw(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.style = {{ setProperty() {{}} }}; this.listeners = new Map();
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 800, height: 500 }}; }}
              getContext() {{ return this.tagName === "CANVAS" ? context2d : null; }}
              hasPointerCapture() {{ return false; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const drawCalls = [];
            const context2d = new Proxy({{}}, {{
              get(target, key) {{ return (...args) => drawCalls.push([key, ...args]); }},
              set() {{ return true; }},
            }});
            const observers = [];
            globalThis.IntersectionObserver = class {{
              constructor(callback) {{ this.callback = callback; observers.push(this); }}
              observe(target) {{ this.target = target; }} disconnect() {{}}
            }};
            delete globalThis.ResizeObserver;
            const rafs = new Map(); let rafId = 0;
            globalThis.requestAnimationFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            globalThis.cancelAnimationFrame = (id) => rafs.delete(id);
            globalThis.document = {{ activeElement: null, createElement: (tag) => new FakeElement(tag) }};
            globalThis.window = {{ devicePixelRatio: 1, addEventListener() {{}}, removeEventListener() {{}}, matchMedia: () => ({{ matches: true }}) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};

            let resolveExpansion; const contexts = [];
            const {{ configureUniverse, destroyUniverse, expandNode, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            configureUniverse({{
              fetchJson() {{ return new Promise((resolve) => {{ resolveExpansion = resolve; }}); }},
              onContextChange(context) {{ contexts.push(context); }},
            }});
            const container = new FakeElement("main");
            const view = renderUniverse(container, {{
              focus_id: "item:A",
              nodes: [{{ id: "item:A", title: "A" }}, {{ id: "item:B", title: "B" }}],
              edges: [{{ source: "item:A", target: "item:B", score: 0.9, reasons: ["A-B"] }}],
            }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const canvas = collect(view).find((node) => node.tagName === "CANVAS");
            observers[0].callback([{{ isIntersecting: true, target: canvas }}]);
            const initialFrame = [...rafs.entries()][0];
            if (!initialFrame || rafs.size !== 1) throw new Error("visible canvas did not schedule initial draw");
            rafs.delete(initialFrame[0]); initialFrame[1](16);
            if (rafs.size !== 0) throw new Error("initial static canvas RAF did not drain");
            drawCalls.length = 0;

            const expansion = expandNode("item:B");
            resolveExpansion({{
              focus_id: "item:B",
              nodes: [{{ id: "item:B", title: "B" }}, {{ id: "item:C", title: "C" }}],
              edges: [{{ source: "item:B", target: "item:C", score: 0.8, reasons: ["B-C"] }}],
            }});
            await expansion;
            if (rafs.size !== 1) throw new Error(`expansion merge scheduled ${{rafs.size}} redraws instead of one`);
            if (contexts.length !== 1 || contexts[0].universeFocusId !== "item:B" || contexts[0].expandedIds.join(",") !== "item:B") throw new Error("expansion context was not persisted exactly once");

            const redraw = [...rafs.entries()][0]; rafs.delete(redraw[0]); redraw[1](32);
            const labels = drawCalls.filter((call) => call[0] === "fillText").map((call) => call[1]);
            const edgeDraws = drawCalls.filter((call) => call[0] === "lineTo").length;
            if (!labels.includes("C") || edgeDraws < 2) throw new Error(`redraw omitted merged node/edge: labels=${{labels}} edges=${{edgeDraws}}`);
            if (rafs.size !== 0) throw new Error("static expansion redraw left a RAF queued");
            destroyUniverse();
            console.log(JSON.stringify({{ redraws: 1, labels, edgeDraws, contexts: contexts.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["redraws"])
        self.assertIn("C", result["labels"])
        self.assertGreaterEqual(result["edgeDraws"], 2)
        self.assertEqual(1, result["contexts"])

    def test_universe_focus_controls_persist_only_real_changes_and_pointer_cancel_never_expands(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map();
                this.dataset = {{}}; this.className = ""; this.textContent = ""; this.style = {{ setProperty() {{}} }};
                this.listeners = new Map(); this.pointerCapture = null;
              }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              dispatch(type, event = {{}}) {{ for (const listener of this.listeners.get(type) ?? []) listener({{ target: this, currentTarget: this, ...event }}); }}
              focus() {{ document.activeElement = this; }}
              getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 800, height: 500 }}; }}
              getContext() {{ return this.tagName === "CANVAS" ? new Proxy({{}}, {{ get: () => () => {{}} }}) : null; }}
              setPointerCapture(id) {{ this.pointerCapture = id; }}
              hasPointerCapture(id) {{ return this.pointerCapture === id; }}
              releasePointerCapture(id) {{ if (this.pointerCapture === id) this.pointerCapture = null; }}
              get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ activeElement: null, createElement: (tag) => new FakeElement(tag) }};
            globalThis.window = {{ devicePixelRatio: 1, addEventListener() {{}}, removeEventListener() {{}}, matchMedia: () => ({{ matches: true }}) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            globalThis.requestAnimationFrame = () => 1; globalThis.cancelAnimationFrame = () => {{}};
            globalThis.IntersectionObserver = class {{ constructor(callback) {{ this.callback = callback; }} observe(target) {{ this.target = target; }} disconnect() {{}} }};
            delete globalThis.ResizeObserver;

            const contexts = []; const requests = [];
            const {{ configureUniverse, destroyUniverse, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            configureUniverse({{
              fetchJson(path, options) {{ requests.push({{ path, options }}); return new Promise(() => {{}}); }},
              onContextChange(context) {{ contexts.push(context); }},
            }});
            const container = new FakeElement("main");
            const view = renderUniverse(container, {{
              focus_id: "item:A",
              nodes: [{{ id: "item:A", title: "A" }}, {{ id: "item:B", title: "B" }}, {{ id: "item:C", title: "C" }}],
              edges: [
                {{ source: "item:A", target: "item:B", score: 0.9, reasons: ["A-B"] }},
                {{ source: "item:A", target: "item:C", score: 0.8, reasons: ["A-C"] }},
              ],
            }});
            if (contexts.length !== 0) throw new Error("initial render wrote unchanged universe context");
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const all = collect(view); const canvas = all.find((node) => node.tagName === "CANVAS");
            const nodeC = all.find((node) => node.dataset.nodeId === "item:C");
            const relationFocus = all.find((node) => node.className.includes("relationship-list__focus"));

            canvas.dispatch("keydown", {{ key: "ArrowRight", preventDefault() {{}} }});
            nodeC.dispatch("focus");
            relationFocus.dispatch("click");
            relationFocus.dispatch("click");
            if (contexts.length !== 3) throw new Error(`focus controls wrote ${{contexts.length}} contexts instead of three real changes`);
            if (contexts.map((entry) => entry.universeFocusId).join(",") !== "item:B,item:C,item:A") throw new Error("keyboard, node button, and relationship focus did not persist in order");
            if (contexts.some((entry) => !Array.isArray(entry.expandedIds) || entry.expandedIds.length > 36)) throw new Error("focus context did not keep bounded expanded ids");

            canvas.dispatch("pointerdown", {{ pointerId: 7, clientX: 400, clientY: 250 }});
            canvas.dispatch("pointercancel", {{ pointerId: 7, clientX: 400, clientY: 250 }});
            if (canvas.pointerCapture !== null || requests.length !== 0 || contexts.length !== 3) throw new Error("pointercancel focused, expanded, or retained capture");

            canvas.dispatch("pointerdown", {{ pointerId: 8, clientX: 400, clientY: 250 }});
            canvas.pointerCapture = null;
            canvas.dispatch("lostpointercapture", {{ pointerId: 8 }});
            canvas.dispatch("pointerup", {{ pointerId: 8, clientX: 400, clientY: 250 }});
            if (requests.length !== 0 || contexts.length !== 3) throw new Error("lostpointercapture left a clickable drag behind");
            destroyUniverse();
            console.log(JSON.stringify({{ contexts: contexts.map((entry) => entry.universeFocusId), requests: requests.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["item:B", "item:C", "item:A"], result["contexts"])
        self.assertEqual(0, result["requests"])

    def test_universe_fractional_dpr_keeps_backing_store_stable_until_tween_raf_drains(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.style = {{ setProperty() {{}} }}; this.listeners = new Map();
                this._width = 300; this._height = 150; this.widthWrites = 0; this.heightWrites = 0;
              }}
              get width() {{ return this._width; }} set width(value) {{ this.widthWrites += 1; this._width = Math.trunc(Number(value)); }}
              get height() {{ return this._height; }} set height(value) {{ this.heightWrites += 1; this._height = Math.trunc(Number(value)); }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }} appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }} setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }} removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              getBoundingClientRect() {{ return {{ left: 0, top: 0, width: 801, height: 501 }}; }}
              getContext() {{ return this.tagName === "CANVAS" ? context2d : null; }}
              hasPointerCapture() {{ return false; }} get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            const transforms = [];
            const context2d = new Proxy({{}}, {{ get(target, key) {{ if (key === "setTransform") return (...args) => transforms.push(args); return () => {{}}; }}, set() {{ return true; }} }});
            const rafs = new Map(); let rafId = 0;
            globalThis.requestAnimationFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            globalThis.cancelAnimationFrame = (id) => rafs.delete(id);
            globalThis.performance = {{ now: () => 0 }};
            globalThis.document = {{ activeElement: null, createElement: (tag) => new FakeElement(tag) }};
            globalThis.window = {{ devicePixelRatio: 1.25, addEventListener() {{}}, removeEventListener() {{}}, matchMedia: () => ({{ matches: false }}) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            delete globalThis.IntersectionObserver; delete globalThis.ResizeObserver;

            const {{ destroyUniverse, focusNode, renderUniverse }} = await import("{module_url('js/features/universe.js')}");
            const container = new FakeElement("main");
            const view = renderUniverse(container, {{ focus_id: "item:A", nodes: [{{ id: "item:A", title: "A" }}, {{ id: "item:B", title: "B" }}], edges: [] }});
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const canvas = collect(view).find((node) => node.tagName === "CANVAS");
            focusNode("item:B");
            for (const timestamp of [60, 140, 220, 260]) {{
              const frame = [...rafs.entries()][0];
              if (!frame) throw new Error(`tween RAF ended before ${{timestamp}}ms`);
              rafs.delete(frame[0]); frame[1](timestamp);
            }}
            if (canvas.widthWrites !== 1 || canvas.heightWrites !== 1) throw new Error(`fractional DPR reset backing store ${{canvas.widthWrites}}/${{canvas.heightWrites}} times`);
            if (canvas.width !== 1001 || canvas.height !== 626) throw new Error(`unstable integer backing size ${{canvas.width}}x${{canvas.height}}`);
            if (rafs.size !== 0) throw new Error(`tween left ${{rafs.size}} RAF callbacks queued`);
            if (!transforms.every((args) => args[0] === 1.25 && args[3] === 1.25)) throw new Error("fractional DPR transform was not stable");
            destroyUniverse();
            console.log(JSON.stringify({{ widthWrites: canvas.widthWrites, heightWrites: canvas.heightWrites, rafs: rafs.size, size: [canvas.width, canvas.height] }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["widthWrites"])
        self.assertEqual(1, result["heightWrites"])
        self.assertEqual(0, result["rafs"])
        self.assertEqual([1001, 626], result["size"])

    def test_title_universe_back_forward_restores_user_focused_universe_context(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const values = new Map();
            globalThis.localStorage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            const listeners = new Map(); const entries = [{{ path: "/title/douban:A", state: null }}]; let index = 0;
            const browser = {{
              location: {{ pathname: entries[0].path }}, scrollY: 0,
              history: {{
                state: null, scrollRestoration: "auto",
                pushState(state, _title, path) {{ entries.splice(index + 1); entries.push({{ path, state }}); index = entries.length - 1; this.state = state; browser.location.pathname = path; }},
                back() {{ if (index === 0) return Promise.resolve(); index -= 1; this.state = entries[index].state; browser.location.pathname = entries[index].path; return browser.dispatchEvent(new browser.PopStateEvent("popstate", {{ state: this.state }})); }},
                forward() {{ if (index >= entries.length - 1) return Promise.resolve(); index += 1; this.state = entries[index].state; browser.location.pathname = entries[index].path; return browser.dispatchEvent(new browser.PopStateEvent("popstate", {{ state: this.state }})); }},
              }},
              addEventListener(type, listener) {{ listeners.set(type, listener); }}, removeEventListener(type) {{ listeners.delete(type); }},
              dispatchEvent(event) {{ return listeners.get(event.type)?.(event); }}, requestAnimationFrame(callback) {{ callback(); return 1; }}, scrollTo() {{}},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.history = browser.history; globalThis.PopStateEvent = browser.PopStateEvent;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser);

            const {{ createAppRouteHandler, createUniverseExplorer, reduceUiState }} = await import("{module_url('js/app.js')}");
            const {{ createRouter }} = await import("{module_url('js/core/router.js')}");
            const {{ createEmptyUiState, createStore }} = await import("{module_url('js/core/store.js')}");
            const store = createStore(createEmptyUiState(), reduceUiState); const universes = []; const titles = [];
            const noOpGate = {{ invalidate() {{}}, async restore() {{}} }};
            const universeGate = {{ invalidate() {{}}, async render() {{ universes.push(store.getState().candidateTray.context.universeFocusId || null); }} }};
            const explorationGate = {{ invalidate() {{}}, async render(route) {{ titles.push(route.params.id); }} }};
            const appView = {{ dataset: {{}} }};
            const onRoute = createAppRouteHandler({{
              appView, store, restoreGate: noOpGate, explorationGate, universeGate,
              prepare() {{}}, setNavigation() {{}}, renderTonightView() {{}}, renderPlaceholder() {{}}, setStatus() {{}},
            }});
            const router = createRouter([
              {{ pattern: "/title/:id", name: "title" }}, {{ pattern: "/universe", name: "universe" }},
            ], {{ onRoute }});
            const exploreUniverse = createUniverseExplorer({{ store, navigate: (path) => router.navigate(path) }});

            await router.start();
            if (store.getState().candidateTray.context.universeFocusId) throw new Error("entering title route overwrote universe context");
            await exploreUniverse("douban:A");
            if (universes.at(-1) !== "douban:A") throw new Error("explicit title action did not establish universe entry focus");
            store.dispatch({{ type: "universe/contextChanged", context: {{ universeFocusId: "douban:B", expandedIds: ["douban:A", "douban:B"] }} }});
            await browser.history.back();
            if (titles.at(-1) !== "douban:A" || store.getState().candidateTray.context.universeFocusId !== "douban:B") throw new Error("back to title replaced user-focused universe B with title A");
            await browser.history.forward();
            if (universes.at(-1) !== "douban:B" || store.getState().candidateTray.context.universeFocusId !== "douban:B") throw new Error("forward universe did not restore B");
            router.destroy();
            console.log(JSON.stringify({{ titles, universes, focus: store.getState().candidateTray.context.universeFocusId, path: appView.dataset.route }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["douban:A", "douban:A"], result["titles"])
        self.assertEqual(["douban:A", "douban:B"], result["universes"])
        self.assertEqual("douban:B", result["focus"])
        self.assertEqual("/universe", result["path"])

    def test_universe_route_requires_persisted_focus_and_title_entry_uses_stable_id(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}} }};
            const {{ createUniverseRouteGate, reduceUiState }} = await import("{module_url('js/app.js')}");
            const renders = []; const expands = []; const statuses = []; let destroys = 0;
            let context = {{}};
            const gate = createUniverseRouteGate({{
              root: {{ id: "root" }}, getContext: () => context,
              render(root, graph) {{ renders.push({{ root, graph }}); return graph; }},
              expand(id) {{ expands.push(id); return Promise.resolve({{ focus_id: id }}); }},
              destroy() {{ destroys += 1; }}, setStatus(message) {{ statuses.push(message); }},
            }});
            await gate.render();
            if (expands.length !== 0 || renders[0].graph !== null) throw new Error("bare universe requested or fabricated a graph");
            context = {{ universeFocusId: "douban:42", expandedIds: ["douban:7"] }};
            await gate.render();
            if (expands[0] !== "douban:42" || renders[1].graph.focus_id !== "douban:42") throw new Error("persisted stable focus was not loaded");
            const initial = {{ candidateTray: {{ itemIds: [], context: {{ reason: "keep" }} }} }};
            const next = reduceUiState(initial, {{ type: "universe/contextChanged", context: {{ universeFocusId: "douban:42", expandedIds: ["douban:7", "douban:42"] }} }});
            if (next.candidateTray.context.reason !== "keep" || next.candidateTray.context.universeFocusId !== "douban:42" || next.candidateTray.context.expandedIds.length !== 2) throw new Error("universe context escaped the existing candidate tray context");
            console.log(JSON.stringify({{ renders: renders.length, expands, destroys, statuses, context: next.candidateTray.context }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["douban:42"], result["expands"])
        self.assertEqual("douban:42", result["context"]["universeFocusId"])
        self.assertGreaterEqual(result["destroys"], 2)

        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{ this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}}; this.className = ""; this.textContent = ""; this.style = {{ setProperty() {{}} }}; }}
              append(...nodes) {{ for (const node of nodes) this.appendChild(node); }} appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }} replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }} getAttribute(name) {{ return this.attributes.get(name) ?? null; }} addEventListener(type, listener) {{ this[`on${{type}}`] = listener; }} get firstElementChild() {{ return this.children[0] ?? null; }}
            }}
            globalThis.document = {{ createElement: (tag) => new FakeElement(tag) }}; globalThis.location = {{ origin: "https://cinescope.test" }};
            const root = new FakeElement("main"); const routed = [];
            const title = {{ item_key: "douban:42", title: "绝不能拿标题猜 ID", media_type: "movie", year: 2024, poster: {{ url: "", media_status: "missing" }}, backdrop: {{ url: "", media_status: "missing" }}, item: {{ directors: [], casts: [] }}, people: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{ root, async fetchJson(path) {{ return path.startsWith("/api/v2/titles/") ? title : {{ focus_id: "douban:42", nodes: [], edges: [] }}; }}, onExploreUniverse(id) {{ routed.push(id); }} }});
            await renderTitleDetail("douban:42");
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            const action = collect(root).find((node) => node.textContent === "在探索实验室展开");
            if (!action || typeof action.onclick !== "function") throw new Error("detail universe action missing");
            action.onclick();
            if (routed[0] !== "douban:42" || routed[0] === title.title) throw new Error("detail routed with guessed title instead of stable id");
            console.log(JSON.stringify({{ routed, label: action.textContent }}));
            '''
        )
        detail_result = json.loads(output)
        self.assertEqual(["douban:42"], detail_result["routed"])

    def test_library_cursor_filter_stale_response_virtual_spacers_and_dispose(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = []; const observers = []; const rafs = new Map(); let rafId = 0; const cancelled = [];
            class FakeObserver {{
              constructor(callback) {{ this.callback = callback; this.disconnected = false; observers.push(this); }}
              observe(target) {{ this.target = target; }} disconnect() {{ this.disconnected = true; }}
            }}
            const fetchJson = (path, options = {{}}) => new Promise((resolve, reject) => requests.push({{ path, options, resolve, reject }}));
            const requestFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            const cancelFrame = (id) => {{ cancelled.push(id); rafs.delete(id); }};
            const item = (index, prefix = "W") => ({{
              item_key: `douban:${{prefix}}${{index}}`, title: `${{prefix}} title ${{index}}`, state: "watched", year: 2000 + index,
              poster: {{ url: `/media/${{prefix}}-${{index}}.webp`, media_status: "ready" }},
              backdrop: {{ url: `/media/${{prefix}}-${{index}}-backdrop.webp`, media_status: "ready" }},
              item: {{ cover: "https://remote.invalid/forbidden-cover.jpg" }}, cover: "https://remote.invalid/also-forbidden.jpg",
            }});
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson, createObserver: (callback) => new FakeObserver(callback), requestFrame, cancelFrame }});
            const firstReady = controller.mount({{ state: "watched" }}); await flush();
            if (!requests[0].path.includes("state=watched") || requests[0].path.includes("cursor=")) throw new Error("initial filter request was wrong");
            requests[0].resolve({{ items: Array.from({{ length: 72 }}, (_v, index) => item(index)), next_cursor: "cursor-one" }});
            await firstReady; await flush();
            let snapshot = controller.snapshot();
            if (snapshot.itemCount !== 72 || snapshot.renderedItemCount >= 72) throw new Error("library did not window the fixed-row grid");
            if (snapshot.topSpacer !== 0 || snapshot.bottomSpacer <= 0) throw new Error("initial virtual spacers were not calculated");
            const viewport = root.querySelector('[data-role="library-window"]');
            const renderedImages = collectNodes(root).filter((node) => node.tagName === "IMG");
            if (!renderedImages.length || renderedImages.some((image) => !image.src.startsWith("/media/") || image.src.includes("forbidden"))) throw new Error("library used a non-catalog or external cover");

            observers[0].callback([{{ isIntersecting: true }}]); await flush();
            if (!requests[1].path.includes("cursor=cursor-one")) throw new Error("sentinel did not request the next cursor");
            const changed = controller.setFilter("wish"); await flush();
            if (!requests[1].options.signal.aborted) throw new Error("filter change did not abort the cursor request");
            if (!requests[2].path.includes("state=wish") || requests[2].path.includes("cursor=")) throw new Error("filter reset retained the old cursor");
            requests[1].resolve({{ items: [item(999, "STALE")], next_cursor: null }});
            requests[2].resolve({{ items: Array.from({{ length: 80 }}, (_v, index) => item(index, "FRESH")), next_cursor: "fresh-next" }});
            await changed; await flush();
            snapshot = controller.snapshot();
            if (snapshot.state !== "wish" || snapshot.itemKeys.some((key) => key.includes("STALE"))) throw new Error("stale cursor response overwrote the new filter");

            viewport.scrollTop = 2400; viewport.dispatchEvent({{ type: "scroll" }});
            const frame = [...rafs.entries()][0]; if (!frame) throw new Error("scroll did not schedule virtualization RAF"); rafs.delete(frame[0]); frame[1]();
            snapshot = controller.snapshot();
            if (snapshot.topSpacer <= 0 || snapshot.bottomSpacer < 0) throw new Error("scrolled virtual spacers were not updated");
            const pending = controller.loadNext(); await flush();
            controller.dispose();
            if (!requests.at(-1).options.signal.aborted) throw new Error("unmount did not abort active fetch");
            if (!observers[0].disconnected || (viewport.listeners.get("scroll")?.size || 0) !== 0) throw new Error("unmount leaked observer or scroll listener");
            if (rafs.size !== 0) throw new Error("unmount leaked RAF callbacks");
            requests.at(-1).resolve({{ items: [], next_cursor: null }}); await pending;
            console.log(JSON.stringify(snapshot));
            '''
        )
        result = json.loads(output)
        self.assertEqual("wish", result["state"])
        self.assertGreater(result["topSpacer"], 0)

    def test_library_scroll_preserves_ready_card_and_image_nodes_in_same_and_overlapping_windows(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const rafs = new Map(); let rafId = 0;
            const requestFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            const cancelFrame = (id) => rafs.delete(id);
            const items = Array.from({{ length: 80 }}, (_value, index) => ({{
              item_key: `douban:S${{index}}`, title: `Stable ${{index}}`, state: "watched", year: 2000 + index,
              poster: {{ url: `/media/stable-${{index}}.webp`, media_status: "ready" }},
              item: {{ genres: ["剧情"], summary: `Stable summary ${{index}}` }},
            }}));
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root,
              fetchJson: async () => ({{ counts: {{ watched: 80, all: 80 }}, items, next_cursor: null }}),
              createResizeObserver: () => null,
              windowTarget: null,
              requestFrame,
              cancelFrame,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const viewport = root.querySelector('[data-role="library-window"]');
            const cardFor = (key) => collectNodes(root).find((node) => node.classList?.contains("library-card") && node.firstElementChild?.getAttribute("href") === `/title/${{encodeURIComponent(key)}}`);
            const imageFor = (card) => collectNodes(card).find((node) => node.tagName === "IMG");

            const firstCard = cardFor("douban:S0");
            const firstImage = imageFor(firstCard);
            viewport.scrollTop = 60; viewport.dispatchEvent({{ type: "scroll" }});
            let frame = [...rafs.entries()][0]; rafs.delete(frame[0]); frame[1](); await flush();
            if (cardFor("douban:S0") !== firstCard || imageFor(cardFor("douban:S0")) !== firstImage) {{
              throw new Error("same virtual window remounted an already decoded card/image");
            }}

            const overlapCard = cardFor("douban:S8");
            const overlapImage = imageFor(overlapCard);
            viewport.scrollTop = 750; viewport.dispatchEvent({{ type: "scroll" }});
            frame = [...rafs.entries()][0]; rafs.delete(frame[0]); frame[1](); await flush();
            if (cardFor("douban:S8") !== overlapCard || imageFor(cardFor("douban:S8")) !== overlapImage) {{
              throw new Error("overlapping virtual rows remounted an already decoded card/image");
            }}
            controller.dispose();
            console.log(JSON.stringify({{ sameWindowStable: true, overlappingWindowStable: true, snapshot: controller.snapshot() }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["sameWindowStable"])
        self.assertTrue(result["overlappingWindowStable"])

    def test_library_restores_and_reports_its_internal_scroll_position(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const rafs = new Map(); let rafId = 0; const reported = [];
            const requestFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            const items = Array.from({{ length: 80 }}, (_value, index) => ({{ item_key: `douban:P${{index}}`, title: `Position ${{index}}`, poster: {{ url: `/media/p-${{index}}.webp`, media_status: "ready" }} }}));
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root,
              fetchJson: async () => ({{ counts: {{ watched: 80 }}, items, next_cursor: null }}),
              createResizeObserver: () => null, windowTarget: null, requestFrame,
              cancelFrame(id) {{ rafs.delete(id); }},
              onScrollChange(value) {{ reported.push(value); }},
            }});
            await controller.mount({{ state: "watched", scrollTop: 750 }}); await flush();
            const restored = controller.snapshot();
            if (restored.scrollTop !== 750 || restored.anchorItemKey !== "douban:P2") throw new Error(`internal scroll was not restored: ${{JSON.stringify(restored)}}`);
            const viewport = root.querySelector('[data-role="library-window"]');
            viewport.scrollTop = 900; viewport.dispatchEvent({{ type: "scroll" }});
            const frame = [...rafs.entries()][0]; if (!frame) throw new Error("scroll change did not schedule one frame"); rafs.delete(frame[0]); frame[1]();
            if (reported.at(-1) !== 900) throw new Error(`internal scroll was not reported: ${{JSON.stringify(reported)}}`);
            console.log(JSON.stringify({{ restored, reported }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(750, result["restored"]["scrollTop"])
        self.assertEqual(900, result["reported"][-1])

    def test_library_suspend_aborts_incremental_fetch_and_resume_restores_exact_window(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = [];
            const observers = [];
            const rafs = new Map(); let rafId = 0;
            class FakeObserver {{
              constructor(callback) {{ this.callback = callback; this.disconnected = false; observers.push(this); }}
              observe(target) {{ this.target = target; }}
              disconnect() {{ this.disconnected = true; }}
            }}
            const fetchJson = (path, options = {{}}) => new Promise((resolve, reject) => requests.push({{ path, options, resolve, reject }}));
            const requestFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            const items = Array.from({{ length: 24 }}, (_value, index) => ({{
              item_key: `douban:S${{index}}`, title: `Suspend ${{index}}`,
              poster: {{ url: `/media/suspend-${{index}}.webp`, media_status: "ready" }},
            }}));
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson, createObserver: (callback) => new FakeObserver(callback),
              createResizeObserver: () => null, windowTarget: null,
              requestFrame, cancelFrame(id) {{ rafs.delete(id); }},
            }});
            const mounted = controller.mount({{ state: "candidate" }}); await flush();
            requests[0].resolve({{ counts: {{ candidate: 48 }}, items, next_cursor: "page-2" }});
            await mounted; await flush();
            const viewport = root.querySelector('[data-role="library-window"]');
            viewport.scrollTop = 750; viewport.dispatchEvent({{ type: "scroll" }});
            for (const [id, callback] of [...rafs]) {{ rafs.delete(id); callback(); }}

            observers[0].callback([{{ isIntersecting: true }}]); await flush();
            if (requests.length !== 2) throw new Error("incremental page did not start before suspension");
            controller.suspend(); await flush();
            if (!requests[1].options.signal.aborted || !observers[0].disconnected) throw new Error("suspend did not abort fetch and observer");
            viewport.scrollTop = 0;
            controller.resume({{ scrollTop: 750 }});
            for (const [id, callback] of [...rafs]) {{ rafs.delete(id); callback(); }}
            const resumed = controller.snapshot();
            if (resumed.scrollTop !== 750 || resumed.itemCount !== 24 || resumed.suspended) throw new Error(`resume lost the exact window: ${{JSON.stringify(resumed)}}`);
            if (observers.length !== 2 || observers[1].disconnected || requests.length !== 2) throw new Error("resume leaked or eagerly refetched the next page");
            controller.dispose();
            console.log(JSON.stringify({{ resumed, observers: observers.length, requests: requests.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(750, result["resumed"]["scrollTop"])
        self.assertEqual(24, result["resumed"]["itemCount"])
        self.assertEqual(2, result["requests"])

    def test_library_loads_enough_pages_before_restoring_a_deep_internal_position(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            let reads = 0;
            const allItems = Array.from({{ length: 120 }}, (_value, index) => ({{
              item_key: `douban:D${{index}}`, title: `Deep ${{index}}`,
              poster: {{ url: `/media/deep-${{index}}.webp`, media_status: "ready" }},
            }}));
            const fetchJson = async (path) => {{
              reads += 1;
              const match = path.match(/[?&]cursor=([^&]+)/);
              const page = match ? Number(decodeURIComponent(match[1]).slice(1)) : 0;
              const start = page * 24;
              const next = start + 24 < allItems.length ? `p${{page + 1}}` : null;
              return {{ counts: {{ watched: 120 }}, items: allItems.slice(start, start + 24), next_cursor: next }};
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson, createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched", scrollTop: 5000 }}); await flush();
            const snapshot = controller.snapshot();
            if (reads !== 2 || snapshot.itemCount !== 48 || snapshot.scrollTop !== 5000) throw new Error(`deep restore did not load enough rows for the readable layout: ${{JSON.stringify({{ reads, snapshot }})}}`);
            controller.dispose();
            console.log(JSON.stringify({{ reads, snapshot }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["reads"])
        self.assertEqual(48, result["snapshot"]["itemCount"])
        self.assertEqual(5000, result["snapshot"]["scrollTop"])

    def test_library_renders_real_counts_story_metadata_and_queues_visible_missing_posters(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const mediaJobs = [];
            const payload = {{
              counts: {{ all: 280, watched: 244, wish: 36, candidate: 40 }}, next_cursor: null,
              items: [{{
                item_key: "douban:42", title: "中文片名", state: "watched", year: 2024, media_type: "电影",
                poster: {{ url: "", media_status: "missing" }},
                item: {{ douban_rating: 8.8, my_rating: 5, genres: ["剧情", "悬疑"], summary: "一段足以让人决定是否观看的剧情简介。" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root,
              fetchJson: async () => payload,
              postJson: async (path, body) => {{ mediaJobs.push({{ path, body }}); return {{ id: "poster-job", state: "queued" }}; }},
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const text = root.textContent;
            if (!["244", "36", "中文片名", "豆瓣 8.8", "剧情 / 悬疑", "一段足以让人决定是否观看的剧情简介。"].every((part) => text.includes(part))) throw new Error(`library stayed metadata-thin: ${{text}}`);
            const posterJobs = mediaJobs.filter((job) => job.path === "/api/v2/media/jobs");
            if (posterJobs.length !== 1 || posterJobs[0].body.kind !== "poster" || posterJobs[0].body.identity_key !== "douban:42") throw new Error(`visible missing poster was not queued once: ${{JSON.stringify(mediaJobs)}}`);
            controller.dispose();
            console.log(JSON.stringify({{ text, mediaJobs }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, len([job for job in result["mediaJobs"] if job["path"] == "/api/v2/media/jobs"]))

    def test_library_card_prefers_media_badge_label_over_raw_media_type(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const payload = {{
              counts: {{ all: 1, watched: 0, wish: 1, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "external:documentary-library",
                title: "Mystery Map",
                display_title: "\u795e\u79d8\u5730\u56fe",
                state: "wish",
                year: 2017,
                media_type: "\u7535\u89c6\u5267",
                media_badge: {{ label: "\u7eaa\u5f55\u7247\u5267\u96c6", icon: "tv", tone: "cyan" }},
                poster: {{ url: "", media_status: "missing" }},
                stills: [],
                item: {{ genres: ["\u7eaa\u5f55\u7247", "\u5192\u9669"], summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "wish" }}); await flush();
            const metadata = root.querySelector(".library-card__meta");
            if (metadata?.textContent !== "\u7eaa\u5f55\u7247\u5267\u96c6 \u00b7 2017") {{
              throw new Error(`library ignored media badge: ${{metadata?.textContent}}`);
            }}
            controller.dispose();
            console.log(JSON.stringify({{ metadata: metadata.textContent }}));
            '''
        )
        self.assertEqual("\u7eaa\u5f55\u7247\u5267\u96c6 \u00b7 2017", json.loads(output)["metadata"])

    def test_library_card_prefers_verified_display_title_over_original_title(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "external:localized-library",
                title: "Mystery Map",
                display_title: "\u795e\u79d8\u5730\u56fe",
                original_title: "Mystery Map",
                title_localization_source: "douban",
                state: "watched", year: 2017, media_type: "\u7535\u89c6\u5267",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }}, stills: [],
                item: {{ genres: ["\u7eaa\u5f55\u7247"], summary: "\u5df2\u6838\u5bf9\u7684\u4e2d\u6587\u7b80\u4ecb\u3002" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const heading = root.querySelector(".library-card__title");
            if (heading?.textContent !== "\u795e\u79d8\u5730\u56fe") throw new Error(`library heading ignored display_title: ${{heading?.textContent}}`);
            controller.dispose();
            console.log(JSON.stringify({{ heading: heading.textContent }}));
            '''
        )
        self.assertEqual("\u795e\u79d8\u5730\u56fe", json.loads(output)["heading"])

    def test_library_renders_verified_still_preview_without_expanding_the_card_contract(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:stills", title: "有剧照的作品", state: "watched", year: 2024, media_type: "电视剧",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: [
                  {{ id: "still-1", url: "/api/image-proxy?url=one", media_status: "ready" }},
                  {{ id: "still-2", url: "/api/image-proxy?url=two", media_status: "ready" }},
                ],
                item: {{ douban_rating: 8.9, genres: ["剧情"], summary: "有剧照预览的简介。" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const preview = root.querySelector(".library-card__visuals");
            const images = preview?.querySelectorAll?.("img") || [];
            if (!preview || images.length !== 2 || !root.textContent.includes("剧照 · 2")) throw new Error(`library still preview missing: ${{root.textContent}}`);
            if ([...images].some((image) => !image.src.includes("/api/image-proxy?url="))) throw new Error("library used an unverified still URL");
            controller.dispose();
            console.log(JSON.stringify({{ preview: Boolean(preview), imageCount: images.length }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["preview"])
        self.assertEqual(2, result["imageCount"])

    def test_library_hides_unresolved_stills_behind_designed_loading_and_failure_states(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:still-state", title: "剧照状态测试", state: "watched", year: 2026, media_type: "电影",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: [
                  {{ url: "/api/image-proxy?url=failed", media_status: "ready" }},
                  {{ url: "/api/image-proxy?url=loaded", media_status: "ready" }},
                  {{ url: "/api/image-proxy?url=deferred", media_status: "ready" }},
                ],
                item: {{ douban_rating: 8.6, genres: ["剧情"], summary: "用于验证剧照加载状态。" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const frames = root.querySelectorAll(".library-card__still-frame");
            const images = root.querySelectorAll(".library-card__still");
            const loading = root.querySelectorAll(".library-card__visual-loading");
            if (frames.length !== 3 || loading.length !== 3) throw new Error(`every unresolved still needs a designed loading surface: ${{loading.length}}/${{frames.length}}`);
            if (images.some((image) => image.hidden !== true)) throw new Error("an unresolved img could expose the browser broken-image glyph");

            images[0].dispatchEvent({{ type: "error" }}); await flush();
            if (frames[0].querySelector("img")) throw new Error("failed still kept the native img element visible");
            if (!frames[0].querySelector(".library-card__visual-fallback-mark") || !frames[0].textContent.includes("视觉资料暂缺")) throw new Error(`designed failure fallback missing: ${{frames[0].textContent}}`);

            images[1].naturalWidth = 1600; images[1].naturalHeight = 900;
            images[1].dispatchEvent({{ type: "load" }}); await flush();
            if (images[1].hidden || images[1].dataset.mediaState !== "ready") throw new Error("loaded still was not revealed as ready");
            if (frames[1].querySelector(".library-card__visual-loading")) throw new Error("loading surface remained after the still became ready");
            controller.dispose();
            console.log(JSON.stringify({{ frames: frames.length, loading: loading.length, fallback: frames[0].textContent, ready: images[1].dataset.mediaState }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("ready", result["ready"])
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.library-card__visual-loading\s*\{[^}]*animation:", re.DOTALL)
        self.assertIn("@keyframes library-still-shimmer", css)

    def test_library_horizontal_stills_use_rail_rooted_prefetch_and_scroll_loading(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const stillObservers = [];
            const createStillObserver = (callback, options) => {{
              const observer = {{
                callback, options, observed: [], disconnected: false,
                observe(target) {{ this.observed.push(target); }},
                disconnect() {{ this.disconnected = true; }},
              }};
              stillObservers.push(observer);
              return observer;
            }};
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:rail-loading", title: "\u6a2a\u5411\u52a0\u8f7d\u6d4b\u8bd5", state: "watched", year: 2026, media_type: "\u7535\u5f71",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: Array.from({{ length: 5 }}, (_, index) => ({{
                  id: "still-" + (index + 1), url: "/api/image-proxy?url=still-" + (index + 1), media_status: "ready",
                }})),
                item: {{ douban_rating: 8.8, genres: ["\u5267\u60c5"], summary: "\u7528\u4e8e\u9a8c\u8bc1\u6a2a\u5411\u5267\u7167\u6309\u9700\u52a0\u8f7d\u3002", directors: ["\u5bfc\u6f14"], casts: ["\u6f14\u5458"] }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson: async () => payload, createStillObserver,
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const rail = root.querySelector(".library-card__visuals-rail");
            const frames = root.querySelectorAll(".library-card__still-frame");
            const images = root.querySelectorAll("img");
            if (stillObservers.length !== 1 || stillObservers[0].options?.root !== rail) throw new Error("stills were not observed relative to their horizontal rail");
            if (stillObservers[0].observed.length !== 5) throw new Error("not every still frame was observed: " + stillObservers[0].observed.length);
            const initialStates = frames.map((frame) => frame.dataset.mediaState);
            if (initialStates.slice(0, 3).some((state) => state !== "loading") || initialStates.slice(3).some((state) => state !== "deferred")) {{
              throw new Error("the first three stills were not scheduled ahead of the viewport: " + initialStates.join(","));
            }}
            if (!images[0].src || !images[1].src || images.slice(2).some((image) => image.src)) throw new Error("the two-slot background lane did not hold the third prefetched still in queue");
            images[0].dispatchEvent({{ type: "load" }}); await flush();
            if (!images[2].src) throw new Error("the third still did not start immediately after the first slot completed");
            images[1].dispatchEvent({{ type: "load" }}); images[2].dispatchEvent({{ type: "load" }}); await flush();
            stillObservers[0].callback([{{ isIntersecting: true, target: frames[3] }}]); await flush();
            if (!images[3].src || !images[4].src) throw new Error("visible still and its forward neighbour were not prefetched");
            images[3].dispatchEvent({{ type: "load" }}); images[4].dispatchEvent({{ type: "load" }}); await flush();
            controller.dispose();
            if (!stillObservers[0].disconnected) throw new Error("still observer was not disconnected with the card");
            console.log(JSON.stringify({{ observed: stillObservers[0].observed.length, loaded: images.filter((image) => Boolean(image.src)).length, initialStates }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(5, result["observed"])
        self.assertEqual(5, result["loaded"])
        self.assertEqual(["loading", "loading", "loading", "deferred", "deferred"], result["initialStates"])

    def test_library_rail_pointer_interaction_warms_the_next_two_stills(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:pointer-warm", title: "\u6307\u9488\u9884\u70ed\u6d4b\u8bd5", state: "watched", year: 2026, media_type: "\u7535\u5f71",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: Array.from({{ length: 6 }}, (_, index) => ({{
                  id: "still-" + (index + 1), url: "/api/image-proxy?url=pointer-" + (index + 1), media_status: "ready",
                }})),
                item: {{ douban_rating: 8.8, genres: ["\u5267\u60c5"], summary: "\u7528\u4e8e\u9a8c\u8bc1\u62d6\u52a8\u524d\u9884\u70ed\u540e\u7eed\u5267\u7167\u3002" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson: async () => payload, createStillObserver: () => null,
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const rail = root.querySelector(".library-card__visuals-rail");
            const frames = root.querySelectorAll(".library-card__still-frame");
            const images = root.querySelectorAll("img");
            images[0].dispatchEvent({{ type: "load" }}); await flush();
            images[1].dispatchEvent({{ type: "load" }}); images[2].dispatchEvent({{ type: "load" }}); await flush();
            frames.forEach((frame, index) => {{ frame.offsetLeft = index * 220; frame.offsetWidth = 210; }});
            rail.clientWidth = 220; rail.scrollWidth = 1320; rail.scrollLeft = 440;
            rail.dispatchEvent({{ type: "pointerdown", pointerId: 9, button: 0, clientX: 180 }}); await flush();
            const states = frames.map((frame) => frame.dataset.mediaState);
            if (!images[3].src || !images[4].src) throw new Error("pointer intent did not warm the next two stills");
            if (images[5].src || states[5] !== "deferred") throw new Error("pointer warming escaped beyond the next two stills");
            const loaded = images.map((image) => Boolean(image.src));
            controller.dispose();
            console.log(JSON.stringify({{ states, loaded }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("loading", result["states"][3])
        self.assertEqual("loading", result["states"][4])
        self.assertEqual("deferred", result["states"][5])
        self.assertEqual([True, True, True, True, True, False], result["loaded"])

    def test_library_dispose_cancels_active_and_queued_still_requests_without_starting_more(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            Object.defineProperty(FakeElement.prototype, "src", {{
              configurable: true,
              get() {{ return this._src || ""; }},
              set(value) {{
                this._src = String(value || "");
                if (this._src) this.srcAssignments = (this.srcAssignments || 0) + 1;
              }},
            }});
            const observers = [];
            const createStillObserver = (callback, options) => {{
              const observer = {{
                callback, options, observed: [],
                observe(target) {{ this.observed.push(target); }},
                disconnect() {{}},
              }};
              observers.push(observer);
              return observer;
            }};
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:cancel-stills", title: "\u5267\u7167\u53d6\u6d88\u6d4b\u8bd5", state: "watched", year: 2026, media_type: "\u7535\u5f71",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: Array.from({{ length: 6 }}, (_, index) => ({{
                  id: "still-" + index,
                  url: "/api/image-proxy?url=" + encodeURIComponent("still-" + index),
                  media_status: "ready",
                }})),
                item: {{ douban_rating: 8.8, genres: ["\u5267\u60c5"], summary: "\u7528\u4e8e\u9a8c\u8bc1\u53d6\u6d88\u884c\u4e3a\u7684\u5b8c\u6574\u7b80\u4ecb" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson: async () => payload, createStillObserver,
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const images = root.querySelectorAll("img");
            const frames = root.querySelectorAll(".library-card__still-frame");
            observers[0].callback(frames.map((target) => ({{ isIntersecting: true, target }})));
            await flush();
            frames[2].dispatchEvent({{ type: "pointerenter" }});
            await flush();
            const assignmentsBeforeDispose = images.reduce((total, image) => total + Number(image.srcAssignments || 0), 0);
            if (assignmentsBeforeDispose !== 2) {{
              throw new Error("promoted library still escaped the two-slot background lane: " + assignmentsBeforeDispose);
            }}
            controller.dispose();
            await flush();
            const assignmentsAfterDispose = images.reduce((total, image) => total + Number(image.srcAssignments || 0), 0);
            if (assignmentsAfterDispose !== assignmentsBeforeDispose) {{
              throw new Error("disposing the library started queued stills: " + assignmentsBeforeDispose + " -> " + assignmentsAfterDispose);
            }}
            if (images.some((image) => image.src)) throw new Error("disposing the library left active still requests attached");
            console.log(JSON.stringify({{ assignmentsBeforeDispose, assignmentsAfterDispose }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["assignmentsBeforeDispose"])
        self.assertEqual(result["assignmentsBeforeDispose"], result["assignmentsAfterDispose"])

    def test_library_still_rail_captures_pointer_only_after_drag_threshold(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:rail-pointer", title: "\u5267\u7167\u6307\u9488\u6062\u590d", state: "watched", year: 2026, media_type: "\u7535\u5f71",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: [{{ id: "still-1", url: "/api/image-proxy?url=still-1", media_status: "ready" }}],
                item: {{ douban_rating: 8.8, genres: ["\u5267\u60c5"], summary: "\u7528\u4e8e\u9a8c\u8bc1\u8f68\u9053\u6307\u9488\u6062\u590d\u7684\u5b8c\u6574\u7b80\u4ecb", directors: ["\u5bfc\u6f14\u7532"], casts: ["\u6f14\u5458\u4e59"] }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson: async () => payload, createStillObserver: () => null,
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const rail = root.querySelector(".library-card__visuals-rail");
            const captures = []; const releases = [];
            rail.setPointerCapture = (pointerId) => captures.push(pointerId);
            rail.releasePointerCapture = (pointerId) => releases.push(pointerId);

            rail.dispatchEvent({{ type: "pointerdown", pointerId: 7, button: 0, clientX: 200 }});
            if (captures.length) throw new Error("a simple still click was captured before any drag movement");
            rail.dispatchEvent({{ type: "pointermove", pointerId: 7, clientX: 198, preventDefault() {{}} }});
            if (captures.length) throw new Error("sub-threshold pointer movement was treated as a drag");
            rail.dispatchEvent({{ type: "pointerup", pointerId: 7 }});
            if (releases.length) throw new Error("an uncaptured click pointer was released as though it were a drag");

            rail.dispatchEvent({{ type: "pointerdown", pointerId: 8, button: 0, clientX: 200 }});
            rail.dispatchEvent({{ type: "pointermove", pointerId: 8, clientX: 180, preventDefault() {{}} }});
            if (captures.length !== 1 || captures[0] !== 8) throw new Error("pointer capture did not begin when horizontal dragging crossed the threshold");
            rail.dispatchEvent({{ type: "pointerup", pointerId: 8 }});
            if (releases.length !== 1 || releases[0] !== 8) throw new Error("drag pointer capture was not released exactly once");
            controller.dispose();
            console.log(JSON.stringify({{ captures, releases }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual([8], result["captures"])
        self.assertEqual([8], result["releases"])

    def test_library_still_frame_adopts_the_loaded_image_intrinsic_aspect_ratio(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:intrinsic-still", title: "真实比例剧照", state: "watched", year: 2026, media_type: "电影",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                stills: [{{ id: "still-wide", url: "/api/image-proxy?url=wide", media_status: "ready" }}],
                item: {{ douban_rating: 8.6, genres: ["剧情"], summary: "验证剧照真实比例。", directors: ["导演"], casts: ["演员"] }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson: async () => payload, createStillObserver: () => null,
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const frame = root.querySelector(".library-card__still-frame");
            const image = root.querySelector("img");
            image.naturalWidth = 900; image.naturalHeight = 600;
            image.dispatchEvent({{ type: "load" }});
            const aspect = frame.style["--still-aspect"] || "";
            if (aspect !== "900 / 600") throw new Error("intrinsic still ratio was not applied: " + aspect);
            controller.dispose();
            console.log(JSON.stringify({{ aspect }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("900 / 600", result["aspect"])

    def test_library_preserves_each_item_still_rail_position_across_card_rebuilds(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const item = (key, title, state) => ({{
              item_key: key, title, state, year: 2026, media_type: "电影",
              poster: {{ url: "/media/" + encodeURIComponent(key) + ".webp", media_status: "ready" }},
              stills: Array.from({{ length: 4 }}, (_, index) => ({{
                id: key + "-still-" + index, url: "/api/image-proxy?url=" + encodeURIComponent(key + "-" + index), media_status: "ready",
              }})),
              item: {{ douban_rating: 8.7, genres: ["剧情"], summary: title + " 的简介。", directors: ["导演"], casts: ["演员"] }},
            }});
            const payloads = {{
              watched: {{ counts: {{ all: 2, watched: 1, wish: 1, candidate: 0 }}, next_cursor: null, items: [item("item:alpha", "影片 A", "watched")] }},
              wish: {{ counts: {{ all: 2, watched: 1, wish: 1, candidate: 0 }}, next_cursor: null, items: [item("item:beta", "影片 B", "wish")] }},
            }};
            const fetchJson = async (path) => {{
              const state = new URL(path, "https://cinescope.test").searchParams.get("state") || "watched";
              return payloads[state];
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson, createStillObserver: () => null,
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const alphaRail = root.querySelector(".library-card__visuals-rail");
            alphaRail.clientWidth = 240; alphaRail.scrollWidth = 1040; alphaRail.scrollLeft = 420;
            alphaRail.dispatchEvent({{ type: "scroll" }});

            await controller.setFilter("wish"); await flush();
            const betaRail = root.querySelector(".library-card__visuals-rail");
            if (Number(betaRail.scrollLeft || 0) !== 0) throw new Error("a different title inherited the previous rail position");
            betaRail.clientWidth = 240; betaRail.scrollWidth = 1040; betaRail.scrollLeft = 85;
            betaRail.dispatchEvent({{ type: "scroll" }});

            await controller.setFilter("watched"); await flush();
            const restoredAlpha = root.querySelector(".library-card__visuals-rail");
            if (Number(restoredAlpha.scrollLeft || 0) !== 420) throw new Error("title A rail position was not restored: " + Number(restoredAlpha.scrollLeft || 0));

            await controller.setFilter("wish"); await flush();
            const restoredBeta = root.querySelector(".library-card__visuals-rail");
            if (Number(restoredBeta.scrollLeft || 0) !== 85) throw new Error("title B rail position was not restored independently: " + Number(restoredBeta.scrollLeft || 0));
            controller.dispose();
            console.log(JSON.stringify({{ alpha: Number(restoredAlpha.scrollLeft || 0), beta: Number(restoredBeta.scrollLeft || 0) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(420, result["alpha"])
        self.assertEqual(85, result["beta"])

    def test_library_keeps_public_tv_visual_hydration_out_of_the_foreground_path(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const enrichJobs = [];
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:tv", title: "待补剧集", state: "watched", year: 2024, media_type: "电视剧",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }}, stills: [],
                item: {{ genres: ["剧情"], summary: "已有简介。" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root,
              fetchJson: async (path) => path.includes("/api/v2/library") ? payload : payload.items[0],
              postJson: async (path, body) => {{ enrichJobs.push({{ path, body }}); return {{ item_key: "item:tv", item: {{ summary: "补齐后的简介。" }}, stills: [{{ url: "/api/image-proxy?url=still" }}] }}; }},
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            if (enrichJobs.length) throw new Error(`public TV hydration blocked the foreground path: ${{JSON.stringify(enrichJobs)}}`);
            if (!root.textContent.includes("待补剧集") || !root.textContent.includes("已有简介。")) throw new Error("local TV card did not remain immediately readable");
            controller.dispose();
            console.log(JSON.stringify({{ enrichJobs }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual([], result["enrichJobs"])

    def test_library_keeps_poster_out_of_visual_rail_when_real_stills_are_missing(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "item:poster-visual", title: "海报占位作品", state: "watched", year: 2024, media_type: "电影",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }},
                backdrop: {{ url: "/media/poster.webp", media_status: "ready" }}, stills: [],
                item: {{ douban_rating: 8.5, genres: ["剧情"], summary: "已有中文简介", directors: ["导演甲"], casts: ["演员乙"] }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const preview = root.querySelector(".library-card__visuals");
            const images = preview?.querySelectorAll?.("img") || [];
            if (!preview || images.length !== 0) throw new Error(`poster leaked into real visual rail: ${{images.length}}`);
            if (!root.textContent.includes("暂未找到可核对的真实剧照")) {{
              throw new Error(`real-visual empty state was unclear: ${{root.textContent}}`);
            }}
            controller.dispose();
            console.log(JSON.stringify({{ imageCount: images.length, text: root.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(0, result["imageCount"])

    def test_library_leaves_slow_metadata_hydration_to_background_coordinator(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const posts = [];
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "douban:6985810", title: "Slow metadata title", state: "watched", year: 2012, media_type: "\u7535\u5f71",
                poster: {{ url: "/media/poster.webp", media_status: "ready" }}, stills: [],
                item: {{ genres: ["\u5267\u60c5"], summary: "本地已有的中文简介应立即可读。", directors: [], casts: [] }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson: async () => payload,
              postJson: async (path, body) => {{ posts.push({{ path, body }}); return {{}}; }},
              setTimer(callback) {{ callback(); return 1; }}, clearTimer() {{}},
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            const blockingPosts = posts.filter((entry) => entry.path.includes("/enrich"));
            if (blockingPosts.length) throw new Error("library started foreground metadata hydration: " + JSON.stringify(blockingPosts));
            if (!root.textContent.includes("Slow metadata title") || !root.textContent.includes("本地已有的中文简介应立即可读。")) throw new Error("local card did not render while background hydration remains deferred");
            controller.dispose();
            console.log(JSON.stringify({{ posts, text: root.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertFalse(any("/enrich" in post["path"] for post in result["posts"]))

    def test_library_replaces_largely_english_synopsis_with_a_chinese_localization_status(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const payload = {{
              counts: {{ all: 2, watched: 2, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [
                {{
                  item_key: "item:english-summary", title: "Tomorrow's Worlds", state: "watched", year: 2014, media_type: "电视剧",
                  poster: {{ url: "/media/english.webp", media_status: "ready" }},
                  item: {{ genres: ["科幻", "历史"], summary: "Historian Dominic Sandbrook and leading creators tell the story of science fiction across television and cinema." }},
                }},
                {{
                  item_key: "item:chinese-summary", title: "中文简介作品", state: "watched", year: 2024, media_type: "电影",
                  poster: {{ url: "/media/chinese.webp", media_status: "ready" }},
                  item: {{ genres: ["剧情"], summary: "这是一段已经核对的中文剧情简介。" }},
                }},
              ],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const text = root.textContent;
            if (text.includes("Historian Dominic")) throw new Error(`English synopsis leaked into the Chinese library: ${{text}}`);
            if (!text.includes("这是一部以科幻 / 历史为核心的电视剧；中文剧情简介正在自动补齐。")) throw new Error(`Chinese localization status missing: ${{text}}`);
            if (!text.includes("这是一段已经核对的中文剧情简介。")) throw new Error("verified Chinese synopsis was replaced");
            controller.dispose();
            console.log(JSON.stringify({{ text }}));
            '''
        )
        result = json.loads(output)
        self.assertNotIn("Historian Dominic", result["text"])
        self.assertIn("中文剧情简介正在自动补齐", result["text"])

    def test_library_without_genres_keeps_media_type_instead_of_showing_a_bare_placeholder(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{
              counts: {{ all: 1, watched: 1, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [{{
                item_key: "douban:no-genre", title: "类型缺失但有媒体类型", state: "watched",
                media_type: "电视剧", year: 2022,
                poster: {{ url: "/media/no-genre.webp", media_status: "ready" }},
                item: {{ genres: [], summary: "有媒体类型的条目。" }},
              }}],
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => payload, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const text = root.textContent;
            if (!text.includes("评分样本不足") || !text.includes("类型：电视剧") || text.includes("类型待补充")) throw new Error(`library score/type fallback was ambiguous: ${{text}}`);
            controller.dispose();
            console.log(JSON.stringify({{ text }}));
            '''
        )
        self.assertIn("类型：电视剧", json.loads(output)["text"])

    def test_library_suspension_pauses_poster_job_polling_and_resume_restores_it(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const timers = new Map(); const gets = []; let timerId = 0;
            const item = {{
              item_key: "douban:suspend-poster", title: "挂起补图作品", state: "watched",
              poster: {{ url: "", media_status: "missing" }}, item: {{ genres: ["剧情"] }},
            }};
            const fetchJson = async (path) => {{
              if (path.startsWith("/api/v2/media/jobs/")) {{
                gets.push(path);
                return {{ id: "job-suspend", state: "ready" }};
              }}
              return {{ counts: {{ watched: 1, wish: 0, all: 1, candidate: 0 }}, items: [item], next_cursor: null }};
            }};
            const runScheduledTimers = async () => {{
              const scheduled = [...timers.entries()];
              timers.clear();
              for (const [_id, callback] of scheduled) {{ await callback(); await flush(); }}
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const controller = createLibraryController({{
              root: new FakeElement("main"), fetchJson,
              postJson: async () => ({{ id: "job-suspend", state: "queued" }}),
              setTimer(callback) {{ const id = ++timerId; timers.set(id, callback); return id; }},
              clearTimer(id) {{ timers.delete(id); }},
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush(); await flush();
            if (timers.size !== 1) throw new Error(`poster poll was not scheduled before suspension: ${{timers.size}}`);
            controller.suspend(); await flush();
            await runScheduledTimers();
            if (gets.length !== 0) throw new Error(`suspended library still polled a media job: ${{JSON.stringify(gets)}}`);
            controller.resume(); await flush(); await flush();
            if (timers.size !== 1) throw new Error(`poster poll was not restored after resume: ${{timers.size}}`);
            await runScheduledTimers();
            if (gets.length !== 1 || gets[0] !== "/api/v2/media/jobs/job-suspend") throw new Error(`resumed library did not poll the retained media job once: ${{JSON.stringify(gets)}}`);
            const snapshot = controller.snapshot();
            controller.dispose();
            console.log(JSON.stringify({{ gets, snapshot }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["/api/v2/media/jobs/job-suspend"], result["gets"])
        self.assertFalse(result["snapshot"]["suspended"])

    def test_library_polls_visible_poster_jobs_and_refreshes_cards_in_place(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const timers = []; let libraryReads = 0; let titleReads = 0;
            const item = (index) => ({{ item_key: `douban:P${{index}}`, title: `作品${{index}}`, state: "watched", poster: {{ url: `/media/p-${{index}}.webp`, media_status: "ready" }}, item: {{ genres: ["剧情"] }} }});
            const firstPage = Array.from({{ length: 24 }}, (_value, index) => item(index));
            const secondPage = Array.from({{ length: 24 }}, (_value, index) => item(index + 24));
            const missing = {{ item_key: "douban:poster", title: "补图作品", state: "watched", poster: {{ url: "", media_status: "missing" }}, item: {{ genres: ["剧情"] }} }};
            firstPage[12] = missing;
            const ready = {{ ...missing, poster: {{ url: "/media/poster-ready.webp", media_status: "ready" }} }};
            const fetchJson = async (path) => {{
              if (path.startsWith("/api/v2/media/jobs/")) return {{ id: "job-poster", state: "ready" }};
              if (path === "/api/v2/titles/douban%3Aposter") {{ titleReads += 1; return ready; }}
              libraryReads += 1;
              if (path.includes("cursor=page-2")) return {{ counts: {{ watched: 48, wish: 0, all: 48, candidate: 0 }}, items: secondPage, next_cursor: null }};
              return {{ counts: {{ watched: 48, wish: 0, all: 48, candidate: 0 }}, items: firstPage, next_cursor: "page-2" }};
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{
              root, fetchJson,
              postJson: async () => ({{ id: "job-poster", state: "queued" }}),
              setTimer(callback) {{ timers.push(callback); return timers.length; }}, clearTimer() {{}},
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "watched" }}); await flush();
            await controller.loadNext(); await flush();
            const viewport = root.querySelector('[data-role="library-window"]');
            viewport.scrollTop = 900;
            if (timers.length !== 1) throw new Error(`poster poll was not scheduled: ${{timers.length}}`);
            await timers.shift()(); await flush();
            if (timers.length !== 1) throw new Error("terminal poster did not schedule one library refresh");
            await timers.shift()(); await flush();
            const snapshot = controller.snapshot();
            const target = collectNodes(root).find((node) => node.tagName === "A" && node.getAttribute("href") === "/title/douban%3Aposter");
            const frame = target && collectNodes(target).find((node) => node.classList?.contains("media-frame"));
            if (libraryReads !== 2 || titleReads !== 1 || snapshot.itemCount !== 48 || snapshot.scrollTop !== 900 || frame?.dataset?.mediaState !== "ready") throw new Error(`library poster refresh truncated or remounted the window: ${{JSON.stringify({{ libraryReads, titleReads, snapshot, mediaState: frame?.dataset?.mediaState }})}}`);
            controller.dispose();
            console.log(JSON.stringify({{ libraryReads, titleReads, snapshot, mediaState: frame.dataset.mediaState }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("ready", result["mediaState"])
        self.assertEqual(48, result["snapshot"]["itemCount"])

    def test_library_continues_poster_queue_after_the_first_visible_wave_degrades(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const posts = [];
            const items = Array.from({{ length: 14 }}, (_value, index) => ({{
              item_key: `item:M${{index}}`, title: `Missing ${{index}}`, state: "candidate",
              poster: {{ url: "", media_status: "missing" }}, item: {{}},
            }}));
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const controller = createLibraryController({{
              root: new FakeElement("main"),
              fetchJson: async () => ({{ counts: {{ all: 14, candidate: 14 }}, items, next_cursor: null }}),
              postJson: async (_path, body) => {{ posts.push(body.identity_key); return {{ state: "degraded" }}; }},
              createResizeObserver: () => null, windowTarget: null,
            }});
            await controller.mount({{ state: "candidate" }});
            for (let index = 0; index < 8; index += 1) await flush();
            if (posts.length !== 14 || new Set(posts).size !== 14) throw new Error(`poster queue stopped after first wave: ${{JSON.stringify(posts)}}`);
            controller.dispose();
            console.log(JSON.stringify({{ posts }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(14, len(result["posts"]))

    def test_taste_heading_uses_an_intentional_two_line_lockup(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderTasteDna }} = await import("{module_url('js/features/taste.js')}");
            const root = new FakeElement("main");
            const controller = renderTasteDna(root, {{ fetchJson: async () => ({{ summary: {{}}, groups: {{}} }}) }});
            await controller.ready;
            const title = collectNodes(root).find((node) => node.classList?.contains("taste-title"));
            const lines = title ? collectNodes(title).filter((node) => node.classList?.contains("taste-title__line")) : [];
            if (!title || lines.length !== 2) throw new Error(`taste title lockup missing: ${{lines.length}}`);
            if (lines[0].textContent !== "\u4f60\u7684\u53e3\u5473\uff0c" || lines[1].textContent !== "\u4e0d\u662f\u4e00\u4e32\u6807\u7b7e\u3002") throw new Error(`taste title lines changed: ${{lines.map((line) => line.textContent).join("|")}}`);
            controller.dispose();
            console.log(JSON.stringify({{ lines: lines.map((line) => line.textContent) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["\u4f60\u7684\u53e3\u5473\uff0c", "\u4e0d\u662f\u4e00\u4e32\u6807\u7b7e\u3002"], result["lines"])

        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.taste-title__line\s*\{[^}]*display:\s*block[^}]*white-space:\s*nowrap", re.DOTALL)
        self.assertRegex(
            css,
            r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.taste-title\s*\{[^}]*font-size:\s*clamp\(",
            re.DOTALL,
        )

    def test_taste_renders_all_five_groups_with_safe_local_evidence_links(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const payload = {{ summary: {{ rated_count: 123, liked_count: 119, disliked_count: 1 }}, groups: {{
              stable: [{{ feature: "genre:剧情", score: 0.9, evidence_item_ids: ["douban:1"], evidence_count: 1, evidence_titles: [{{ id: "douban:1", title: "剧情证据" }}], sources: ["library-rating"] }}],
              conflicting: [{{ feature: "country:中国大陆", score: -0.2, evidence_item_ids: ["douban:2"], evidence_count: 1, evidence_titles: [{{ id: "douban:2", title: "冲突证据" }}], sources: ["library-rating"] }}],
              recent: [{{ feature: "genre:犯罪", score: 0.4, evidence_item_ids: ["douban:3"], evidence_count: 1, evidence_titles: [{{ id: "douban:3", title: "最近证据" }}], sources: ["douban-sync"] }}],
              negative: [{{ feature: "genre:古装", score: -0.8, evidence_item_ids: ["douban:4"], evidence_count: 1, evidence_titles: [{{ id: "douban:4", title: "避雷证据" }}], sources: ["feedback"] }}],
              unexplored: [{{ feature: "稳定 <script>偏好", score: 0.1, evidence_item_ids: ["douban:5", "https://evil.test/title"], evidence_count: 2, evidence_titles: [{{ id: "douban:5", title: "未探索证据" }}, {{ id: "https://evil.test/title", title: "不安全证据" }}], sources: ["wishlist"] }}],
            }} }};
            const {{ renderTasteDna }} = await import("{module_url('js/features/taste.js')}");
            const root = new FakeElement("main");
            const controller = renderTasteDna(root, {{ fetchJson: async (path) => {{ if (path !== "/api/v2/taste?profile_key=default") throw new Error(path); return payload; }} }});
            await controller.ready;
            const groups = collectNodes(root).filter((node) => node.dataset?.tasteGroup).map((node) => node.dataset.tasteGroup);
            if (groups.join(",") !== "stable,conflicting,recent,negative,unexplored") throw new Error(`missing taste groups: ${{groups}}`);
            const links = collectNodes(root).filter((node) => node.tagName === "A");
            if (links.length !== 5 || links.some((link) => !link.getAttribute("href").startsWith("/title/") || link.getAttribute("href").includes("evil.test"))) throw new Error("unsafe evidence link rendered");
            if (!root.textContent.includes("偏爱剧情") || !root.textContent.includes("123") || root.textContent.includes("douban:1") || root.textContent.includes("近30天") || root.textContent.includes("30 天")) throw new Error("taste copy stayed machine-oriented or invented a time window");
            controller.dispose();
            console.log(JSON.stringify({{ groups, hrefs: links.map((link) => link.getAttribute("href")), text: root.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["stable", "conflicting", "recent", "negative", "unexplored"], result["groups"])
        self.assertTrue(all(href.startswith("/title/") for href in result["hrefs"]))

    def test_health_assets_dashboard_separates_actions_from_legacy_diagnostics(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const repairs = []; const posts = [];
            const fetchJson = async (path) => {{
              if (path === "/api/v2/media/health") return {{
                assets: {{ total: 12, bytes: 4096, by_kind: {{ poster: 7, backdrop: 5 }} }},
                jobs: {{ queued: 2, pending: 1, processing: 3, failed: 1, unavailable: 2, missing: 1 }},
                delivery: "local-only",
              }};
              if (path === "/api/v2/diagnostics") return {{
                app_version: "9.8.7",
                cache_bytes: 8192,
                provider_attempt_health: {{ basis: "historical_attempts", attempts_total: 7 }},
                media_audit: {{ total: 10, ready: 6, degraded: 2, ambiguous: 1, missing: 1, wrong_identity_candidates: 1 }},
                observability_limits: {{
                  media_audit_window: {{ scope: "recent_recommendation_batches", selected_batches: 2, rows_audited: 10, truncated: false }},
                  wrong_identity_candidates_scope: "global_historical_identity_rejected_hard_conflicts",
                  recommendation_media_identity_attribution: "unavailable_without_stable_foreign_key",
                }},
              }};
              return {{}};
            }};
            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const root = new FakeElement("main");
            const controller = renderHealth(root, {{
              fetchJson,
              autoSyncSettings: true,
              postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ state: "waiting_for_login", user_id: "123456789", job_id: "blocked-job" }}; }},
              onRepairAssets: () => repairs.push("repair"),
            }});
            await controller.ready;
            const nodes = collectNodes(root);
            const dashboard = nodes.find((node) => node.classList?.contains("health-assets"));
            if (!dashboard) throw new Error("actionable asset dashboard missing");
            const cards = collectNodes(dashboard).filter((node) => node.classList?.contains("health-asset-card"));
            const byLabel = Object.fromEntries(cards.map((card) => [card.children[0]?.textContent, card.textContent]));
            if (!byLabel["海报可用"]?.includes("7") || !byLabel["剧照可用"]?.includes("5")) throw new Error(`kind counts missing: ${{JSON.stringify(byLabel)}}`);
            if (!byLabel["本地缓存"]?.includes("12") || !byLabel["本地缓存"]?.includes("4 KB") || !byLabel["本地缓存"]?.includes("8 KB")) throw new Error("cache evidence was not merged");
            if (!byLabel["等待修复"]?.includes("6") || !byLabel["确认失效"]?.includes("4")) throw new Error(`action counts wrong: ${{JSON.stringify(byLabel)}}`);
            const advanced = collectNodes(dashboard).find((node) => node.classList?.contains("health-advanced"));
            if (!advanced || advanced.tagName !== "DETAILS" || advanced.open) throw new Error("legacy diagnostics were not collapsed");
            if (!advanced.textContent.includes("历史审计") || !advanced.textContent.includes("6 / 10") || !advanced.textContent.includes("身份冲突") || !advanced.textContent.includes("9.8.7")) throw new Error("advanced diagnostics lost evidence");
            const primaryText = dashboard.children.filter((node) => node !== advanced).map((node) => node.textContent).join("");
            if (primaryText.includes("6 / 10") || primaryText.includes("256")) throw new Error("historical audit leaked into the primary dashboard");
            const repair = nodes.find((node) => node.textContent === "检查并修复素材");
            const authorize = nodes.find((node) => node.textContent === "浏览器授权并自动续传");
            if (!repair || !authorize) throw new Error("asset actions missing");
            repair.dispatchEvent({{ type: "click", preventDefault() {{}} }});
            authorize.dispatchEvent({{ type: "click" }});
            await flush();
            const syncAdvanced = nodes.find((node) => node.classList?.contains("sync-advanced"));
            if (repairs.length !== 1) throw new Error("repair action did not invoke the existing workflow hook");
            if (posts.at(-1)?.path !== "/api/v2/sync/browser-auth") throw new Error(`health action did not start browser authorization: ${{JSON.stringify(posts)}}`);
            if (syncAdvanced?.open) throw new Error("manual Cookie recovery was opened by the primary action");
            controller.dispose();
            console.log(JSON.stringify({{ byLabel, repairs: repairs.length, advanced: advanced.textContent, authorizationPath: posts.at(-1)?.path }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["repairs"])
        self.assertEqual("/api/v2/sync/browser-auth", result["authorizationPath"])

    def test_health_asset_dashboard_is_symmetric_responsive_and_motion_safe(self):
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.health-assets__grid\s*\{[^}]*grid-template-columns:\s*repeat\(5,\s*minmax\(0,\s*1fr\)\)", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(min-width:\s*721px\)\s*and\s*\(max-width:\s*1100px\)[\s\S]*?\.health-assets__grid\s*\{[^}]*repeat\(6,\s*minmax\(0,\s*1fr\)\)", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.health-assets__grid\s*\{[^}]*minmax\(0,\s*1fr\)", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.health-assets__action", re.DOTALL)

    def test_health_uses_unknown_diagnostics_and_renders_media_health_with_incomplete_job(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const calls = [];
            const fetchJson = async (path) => {{
              calls.push(path);
              if (path === "/api/v2/media/health") return {{ assets: {{ total: 12, bytes: 4096 }}, jobs: {{ queued: 2, failed: 1 }}, delivery: "local-only" }};
              if (path === "/api/v2/sync/jobs/restored") return {{ id: "restored", state: "complete", user_id: "123456789" }};
              throw new Error(path);
            }};
            const timers = new Map(); let timerId = 0;
            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const root = new FakeElement("main");
            const controller = renderHealth(root, {{ fetchJson, postJson: async () => ({{}}), syncState: {{ knownJobIds: ["restored"] }}, setTimer(callback) {{ const id = ++timerId; timers.set(id, callback); return id; }}, clearTimer(id) {{ timers.delete(id); }} }});
            await controller.ready;
            const text = root.textContent;
            if (!text.includes("12") || !text.includes("4 KB") || !text.includes("排队 2") || !text.includes("失败 1")) throw new Error("media health was not rendered in human-readable Chinese");
            if (text.includes("local-only") || text.includes("queued")) throw new Error("internal media states leaked into the Chinese settings page");
            if (!text.includes("—") || !text.includes("尚未提供")) throw new Error("unknown provider diagnostics were fabricated");
            if (text.includes("0 ms") || text.includes("100%") || text.includes("healthy")) throw new Error("health fabricated latency or percentages");
            if (!text.includes("记录不完整") || text.includes("同步成功")) throw new Error("incomplete restored job was shown as success");
            controller.dispose();
            console.log(JSON.stringify({{ calls, text, timers: timers.size }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("/api/v2/media/health", result["calls"])
        self.assertIn("/api/v2/diagnostics", result["calls"])
        self.assertIn("/api/v2/sync/jobs/restored", result["calls"])

    def test_health_autofills_known_douban_identity_and_keeps_cookie_in_advanced_panel(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const root = new FakeElement("main");
            const controller = renderHealth(root, {{
              personalization: {{ source: "douban-sync", user_id: "123456789", watched_count: 244, wish_count: 36 }},
              discovery: {{ status: "partial", local_index_size: 456, live_size: 83, source_counts: {{ tmdb: 24, omdb: 12, tvmaze: 18, anilist: 15, jikan: 14 }}, config: {{ tmdb_configured: true, omdb_configured: true }} }},
              fetchJson: async (path) => path === "/api/v2/media/health" ? {{ assets: {{}}, jobs: {{}}, delivery: "local-only" }} : {{}},
              postJson: async () => ({{}}),
            }});
            await controller.ready;
            const advanced = collectNodes(root).find((node) => node.classList?.contains("sync-advanced"));
            if (controller.sync.elements.profile.value !== "123456789") throw new Error("known Douban identity was not auto-filled");
            if (!root.textContent.includes("已连接豆瓣") || !root.textContent.includes("244 部看过") || !root.textContent.includes("36 部想看")) throw new Error("connected sync state was not human-readable");
            const discoveryCopy = [
              "在线候选源与本地片库", "本机片库 456", "本次在线补充 83",
              "在线来源", "身份与质量筛选", "本次推荐", "本地片库与图片缓存",
              "搜索和详情主体优先读取本机 SQLite 片库", "TMDb 24", "IMDb 12",
            ];
            if (discoveryCopy.some((copy) => !root.textContent.includes(copy))) throw new Error(`online/local discovery boundary was not clear: ${{root.textContent}}`);
            if (!advanced || advanced.tagName !== "DETAILS" || advanced.open) throw new Error("optional Cookie controls were not collapsed as an advanced panel");
            controller.dispose();
            console.log(JSON.stringify({{ profile: "123456789", text: root.textContent, advanced: advanced.tagName }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("123456789", result["profile"])

    def test_health_merges_runtime_diagnostics_and_aborts_stale_parallel_reads(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = [];
            const fetchJson = (path, options = {{}}) => new Promise((resolve, reject) => requests.push({{ path, options, resolve, reject }}));
            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const root = new FakeElement("main");
            const first = renderHealth(root, {{ fetchJson, postJson: async () => ({{}}) }});
            await Promise.resolve();
            const firstMedia = requests.find((request) => request.path === "/api/v2/media/health");
            const firstDiagnostics = requests.find((request) => request.path === "/api/v2/diagnostics");
            if (!firstMedia || !firstDiagnostics) throw new Error("health reads were not started in parallel");
            firstDiagnostics.resolve({{
              app_version: "9.8.7",
              cache_bytes: 8192,
              provider_attempt_health: {{ basis: "historical_attempts", attempts_total: 7, status_counts: {{ ready: 3, provider_error: 1 }} }},
              persistent_queue_states: {{ queued: 4, degraded: 2 }},
              media_audit: {{ total: 10, ready: 6, degraded: 2, ambiguous: 1, missing: 1, wrong_identity_candidates: 1 }},
              observability_limits: {{
                media_audit_window: {{ scope: "recent_recommendation_batches", ordering: "created_at_desc_then_id_desc", batch_limit: 32, row_limit: 256, selected_batches: 2, rows_audited: 10, truncated: false }},
                wrong_identity_candidates_scope: "global_historical_identity_rejected_hard_conflicts",
                recommendation_media_identity_attribution: "unavailable_without_stable_foreign_key",
              }},
            }});
            firstMedia.resolve({{ assets: {{ total: 12, bytes: 4096 }}, jobs: {{ queued: 2 }}, delivery: "local-only" }});
            await first.ready;
            const mergedText = root.textContent;
            if (!mergedText.includes("8 KB") || !mergedText.includes("7") || !mergedText.includes("历史请求记录")) throw new Error("diagnostics metrics were not merged");
            const advanced = collectNodes(root).find((node) => node.classList?.contains("health-advanced"));
            if (!advanced || advanced.tagName !== "DETAILS" || advanced.open) throw new Error("historical diagnostics were not kept in the closed advanced panel");
            const metricCards = collectNodes(advanced).filter((node) => node.tagName === "ARTICLE");
            const auditCard = metricCards.find((card) => card.children[0]?.textContent === "历史审计");
            const wrongIdentityCard = metricCards.find((card) => card.children[0]?.textContent === "身份冲突");
            if (!auditCard || !auditCard.textContent.includes("6 / 10") || !auditCard.textContent.includes("仅供历史排查") || auditCard.textContent.includes("错图候选")) throw new Error("bounded row media audit scope was misleading");
            if (!wrongIdentityCard || !wrongIdentityCard.textContent.includes("1") || !wrongIdentityCard.textContent.includes("历史聚合，无法归属当前推荐卡片")) throw new Error("global historical wrong-identity scope was not explicit");

            const second = renderHealth(root, {{ fetchJson, postJson: async () => ({{}}) }});
            await Promise.resolve();
            const stale = requests.slice(2);
            if (stale.length !== 2 || stale.some((request) => !["/api/v2/media/health", "/api/v2/diagnostics"].includes(request.path))) throw new Error("second parallel reads missing");
            second.dispose();
            if (stale.some((request) => !request.options.signal?.aborted)) throw new Error("dispose did not abort both health reads");
            const beforeLate = root.textContent;
            for (const request of stale) request.resolve(request.path.endsWith("diagnostics") ? {{ cache_bytes: 999999, media_audit: {{ total: 99, ready: 99 }} }} : {{ assets: {{ total: 99, bytes: 99 }} }});
            await second.ready;
            if (root.textContent !== beforeLate || root.textContent.includes("999999")) throw new Error("late stale health response mutated the DOM");
            first.dispose();
            console.log(JSON.stringify({{ paths: requests.map((request) => request.path), mergedText, staleAborted: stale.every((request) => request.options.signal.aborted) }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["paths"].count("/api/v2/media/health"))
        self.assertEqual(2, result["paths"].count("/api/v2/diagnostics"))
        self.assertTrue(result["staleAborted"])

    def test_health_wrong_identity_scope_fails_closed_when_observability_is_unknown(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const fetchJson = async (path) => {{
              if (path === "/api/v2/media/health") return {{ assets: {{ total: 4, bytes: 1024 }}, jobs: {{}}, delivery: "local-only" }};
              if (path === "/api/v2/diagnostics") return {{
                media_audit: {{ total: 4, ready: 3, degraded: 0, ambiguous: 0, missing: 1, wrong_identity_candidates: "unknown" }},
                observability_limits: {{
                  media_audit_window: {{ scope: "recent_recommendation_batches", ordering: "created_at_desc_then_id_desc", batch_limit: 32, row_limit: 256, selected_batches: 1, rows_audited: 4, truncated: false }},
                  wrong_identity_candidates_scope: "unknown",
                  recommendation_media_identity_attribution: "unknown",
                }},
              }};
              throw new Error(path);
            }};
            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const root = new FakeElement("main");
            const controller = renderHealth(root, {{ fetchJson, postJson: async () => ({{}}) }});
            await controller.ready;
            const advanced = collectNodes(root).find((node) => node.classList?.contains("health-advanced"));
            if (!advanced || advanced.tagName !== "DETAILS" || advanced.open) throw new Error("unknown historical diagnostics escaped the closed advanced panel");
            const cards = collectNodes(advanced).filter((node) => node.tagName === "ARTICLE");
            const auditCard = cards.find((card) => card.children[0]?.textContent === "历史审计");
            const wrongIdentityCard = cards.find((card) => card.children[0]?.textContent === "身份冲突");
            if (!auditCard || !auditCard.textContent.includes("3 / 4") || auditCard.textContent.includes("错图候选")) throw new Error("row audit did not remain separate");
            if (!wrongIdentityCard || !wrongIdentityCard.textContent.includes("—") || !wrongIdentityCard.textContent.includes("尚未提供") || wrongIdentityCard.textContent.includes("0")) throw new Error("unknown global scope rendered a fabricated zero");
            controller.dispose();
            console.log(JSON.stringify({{ audit: auditCard.textContent, wrongIdentity: wrongIdentityCard.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("3 / 4", result["audit"])
        self.assertIn("—", result["wrongIdentity"])
        self.assertIn("尚未提供", result["wrongIdentity"])

    def test_sync_cookie_stays_in_tab_session_and_public_snapshots_use_auto_pagination(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const sessionValues = new Map([["cinescope.sync.cookie.tab", "bid=tab-secret; ck=hidden"]]);
            const storage = {{ getItem(key) {{ return sessionValues.get(key) ?? null; }}, setItem(key, value) {{ sessionValues.set(key, String(value)); }}, removeItem(key) {{ sessionValues.delete(key); }} }};
            const posts = []; const publicStates = []; const timers = new Map(); let timerId = 0;
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{ storage, fetchJson: async () => ({{}}), postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ job_id: "job-one", state: "queued", user_id: "123456789" }}; }}, onStateChange(state) {{ publicStates.push(JSON.parse(JSON.stringify(state))); }}, setTimer(callback) {{ const id = ++timerId; timers.set(id, callback); return id; }}, clearTimer(id) {{ timers.delete(id); }} }});
            if (controller.elements.cookie.value !== "bid=tab-secret; ck=hidden") throw new Error("tab session cookie was not auto-filled");
            controller.elements.profile.value = "https://www.douban.com/people/123456789/?cookie=profile-secret";
            await controller.start();
            if (posts[0].path !== "/api/v2/sync/jobs" || posts[0].payload.max_pages !== 250) throw new Error("sync did not default to the 250-page safety cap");
            if (posts[0].payload.user !== "https://www.douban.com/people/123456789/") throw new Error("profile URL was not reduced to its public canonical form");
            if (!root.textContent.includes("默认自动翻页到末页") || !root.textContent.includes("250")) throw new Error("auto-pagination copy was missing");
            const rawPublic = JSON.stringify({{ snapshots: publicStates, controller: controller.snapshot() }});
            if (rawPublic.includes("tab-secret") || rawPublic.includes("ck=hidden") || rawPublic.includes("profile-secret") || rawPublic.toLowerCase().includes("cookie")) throw new Error("cookie escaped into public persistence snapshots");
            if (sessionValues.get("cinescope.sync.cookie.tab") !== "bid=tab-secret; ck=hidden") throw new Error("same-tab cookie was not retained in sessionStorage");
            const visibleCopy = root.textContent;
            controller.dispose();
            console.log(JSON.stringify({{ post: {{ path: posts[0].path, maxPages: posts[0].payload.max_pages }}, publicStates, text: visibleCopy, timers: timers.size }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(250, result["post"]["maxPages"])
        self.assertIn("默认自动翻页到末页", result["text"])

    def test_sync_resume_clears_stale_tab_cookie_when_visible_field_is_empty(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const sessionValues = new Map([["cinescope.sync.cookie.tab", "bid=stale-tab-secret; ck=hidden"]]);
            const storage = {{ getItem(key) {{ return sessionValues.get(key) ?? null; }}, setItem(key, value) {{ sessionValues.set(key, String(value)); }}, removeItem(key) {{ sessionValues.delete(key); }} }};
            const posts = [];
            const postJson = async (path, payload) => {{
              posts.push({{ path, payload }});
              return {{ job_id: "job-resumed", state: "complete", user_id: "123456789", counts: {{ items: 8, collect_count: 6, wish_count: 2, pages_ok: 2, pages_failed: 0 }}, diagnostics: [] }};
            }};
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const firstRoot = new FakeElement("div");
            const first = renderSyncPanel(firstRoot, {{ storage, fetchJson: async () => ({{}}), postJson }});
            if (first.elements.cookie.value !== "bid=stale-tab-secret; ck=hidden") throw new Error("preloaded tab cookie was not visible");
            first.acceptJob({{
              id: "job-resume-source", state: "needs_cookie", user_id: "123456789",
              counts: {{ items: 0, collect_count: 0, wish_count: 0, pages_ok: 0, pages_failed: 1 }},
              diagnostics: [{{ status: "collect", start: 0, classification: "login_required" }}],
            }});
            first.elements.cookie.value = "";
            await first.resume("job-resume-source");
            if (posts.length !== 1 || posts[0].payload.cookie !== "") throw new Error("resume did not use the empty visible Cookie value");
            if (sessionValues.has("cinescope.sync.cookie.tab")) throw new Error("resume left the stale tab Cookie in sessionStorage");
            first.dispose();

            const secondRoot = new FakeElement("div");
            const second = renderSyncPanel(secondRoot, {{ storage, fetchJson: async () => ({{}}), postJson }});
            if (second.elements.cookie.value !== "") throw new Error("remount restored a Cookie the user cleared visibly");
            const publicState = JSON.stringify(second.snapshot());
            if (publicState.includes("stale-tab-secret") || secondRoot.textContent.includes("stale-tab-secret")) throw new Error("cleared Cookie escaped into remounted public state");
            second.dispose();
            console.log(JSON.stringify({{ post: posts[0], stored: sessionValues.has("cinescope.sync.cookie.tab"), remounted: second.elements }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("", result["post"]["payload"]["cookie"])
        self.assertFalse(result["stored"])
        self.assertIsNone(result["remounted"])

    def test_sync_visible_cookie_edits_immediately_replace_same_tab_storage(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const sessionValues = new Map([["cinescope.sync.cookie.tab", "bid=old-secret"]]);
            const storage = {{ getItem(key) {{ return sessionValues.get(key) ?? null; }}, setItem(key, value) {{ sessionValues.set(key, String(value)); }}, removeItem(key) {{ sessionValues.delete(key); }} }};
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");

            const clearRoot = new FakeElement("div");
            const clearPanel = renderSyncPanel(clearRoot, {{ storage, fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            clearPanel.elements.cookie.value = "";
            clearPanel.elements.cookie.dispatchEvent({{ type: "input" }});
            const removedImmediately = !sessionValues.has("cinescope.sync.cookie.tab");
            clearPanel.dispose();
            const clearRemount = renderSyncPanel(new FakeElement("div"), {{ storage, fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            const clearedValue = clearRemount.elements.cookie.value;
            clearRemount.dispose();

            sessionValues.set("cinescope.sync.cookie.tab", "bid=old-secret");
            const editPanel = renderSyncPanel(new FakeElement("div"), {{ storage, fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            editPanel.elements.cookie.value = "bid=new-secret; ck=fresh";
            editPanel.elements.cookie.dispatchEvent({{ type: "input" }});
            const editedImmediately = sessionValues.get("cinescope.sync.cookie.tab");
            editPanel.dispose();
            const editRemount = renderSyncPanel(new FakeElement("div"), {{ storage, fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            const editedValue = editRemount.elements.cookie.value;
            editRemount.dispose();
            console.log(JSON.stringify({{ removedImmediately, clearedValue, editedImmediately, editedValue }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["removedImmediately"])
        self.assertEqual("", result["clearedValue"])
        self.assertEqual("bid=new-secret; ck=fresh", result["editedImmediately"])
        self.assertEqual("bid=new-secret; ck=fresh", result["editedValue"])

    def test_sync_invalid_profile_after_visible_clear_never_revives_old_cookie(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const sessionValues = new Map([["cinescope.sync.cookie.tab", "bid=stale-secret"]]);
            const storage = {{ getItem(key) {{ return sessionValues.get(key) ?? null; }}, setItem(key, value) {{ sessionValues.set(key, String(value)); }}, removeItem(key) {{ sessionValues.delete(key); }} }};
            const posts = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const first = renderSyncPanel(new FakeElement("div"), {{ storage, fetchJson: async () => ({{}}), postJson: async (...args) => {{ posts.push(args); return {{}}; }} }});
            first.elements.cookie.value = "";
            first.elements.cookie.dispatchEvent({{ type: "input" }});
            first.elements.profile.value = "not/a/douban/profile";
            const started = await first.start();
            first.dispose();
            const second = renderSyncPanel(new FakeElement("div"), {{ storage, fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            const remounted = second.elements.cookie.value;
            second.dispose();
            console.log(JSON.stringify({{ started, posts: posts.length, stored: sessionValues.has("cinescope.sync.cookie.tab"), remounted }}));
            '''
        )
        result = json.loads(output)
        self.assertIsNone(result["started"])
        self.assertEqual(0, result["posts"])
        self.assertFalse(result["stored"])
        self.assertEqual("", result["remounted"])

    def test_sync_job_visibly_distinguishes_collect_wish_and_page_counts(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{ fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            controller.acceptJob({{
              id: "live-job", state: "complete", user_id: "123456789",
              counts: {{ items: 280, collect_count: 244, wish_count: 36, pages_ok: 22, pages_failed: 0 }},
              stopped_reason: "已到达空白分页", diagnostics: [],
            }});
            const visible = root.textContent;
            for (const expected of ["条目 280", "看过 244", "想看 36", "成功页 22", "失败页 0", "已到达列表末页"]) {{
              if (!visible.includes(expected)) throw new Error(`missing visible sync evidence: ${{expected}}`);
            }}
            controller.dispose();
            console.log(JSON.stringify({{ visible }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("看过 244", result["visible"])
        self.assertIn("想看 36", result["visible"])

    def test_sync_polling_dedupes_latest_wins_cleans_up_and_shows_resume_400(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = []; const timers = new Map(); const cleared = []; let timerId = 0;
            const fetchJson = (path, options = {{}}) => new Promise((resolve, reject) => requests.push({{ path, options, resolve, reject }}));
            const postJson = async (_path, _payload) => {{ const error = new Error("resume rejected"); error.status = 400; error.publicMessage = "sync job has no failed pages to resume"; throw error; }};
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{ knownJobIds: ["job-a", "job-a"], fetchJson, postJson, setTimer(callback) {{ const id = ++timerId; timers.set(id, callback); return id; }}, clearTimer(id) {{ cleared.push(id); timers.delete(id); }} }});
            await flush();
            if (requests.length !== 1 || requests[0].path !== "/api/v2/sync/jobs/job-a") throw new Error("restored job polling was duplicated");
            requests[0].resolve({{ id: "job-a", state: "needs_cookie", user_id: "272", counts: {{ items: 0 }}, stopped_reason: "豆瓣要求登录态", diagnostics: [{{ status: "collect", start: 0, classification: "login_required", message: "HTTP 403" }}] }});
            await controller.ready; await flush();
            if (timers.size !== 0) throw new Error("terminal resumable job kept a polling timer");
            const first = controller.refreshJob("job-a"); await flush();
            const second = controller.refreshJob("job-a"); await flush();
            if (!requests[1].options.signal.aborted) throw new Error("new poll did not abort the previous generation");
            requests[2].resolve({{ id: "job-a", state: "complete", user_id: "272", counts: {{ items: 8, pages_ok: 2, pages_failed: 0 }}, stopped_reason: "已到达空白分页", diagnostics: [] }});
            await second;
            requests[1].resolve({{ id: "job-a", state: "failed", user_id: "stale", counts: {{ items: 0 }}, stopped_reason: "stale", diagnostics: [] }});
            await first;
            if (controller.snapshot().jobs["job-a"].state !== "complete") throw new Error("stale job response won over the latest generation");

            controller.elements.cookie.value = "poll-secret";
            controller.acceptJob({{ id: "job-private", state: "failed", user_id: "272", counts: {{ items: 0 }}, stopped_reason: "poll-secret", diagnostics: [{{ status: "wish", start: 15, classification: "network_error", message: "poll-secret" }}], errors: ["poll-secret"] }});
            if (JSON.stringify(controller.snapshot()).includes("poll-secret")) throw new Error("cookie escaped into job metadata");
            const resumable = controller.acceptJob({{ id: "job-b", state: "needs_cookie", user_id: "272", counts: {{ items: 0 }}, stopped_reason: "需要 Cookie", diagnostics: [{{ status: "wish", start: 15, classification: "login_required", message: "HTTP 403" }}] }});
            if (!resumable.canResume) throw new Error("real resumable diagnostics did not expose resume");
            await controller.resume("job-b");
            if (!root.textContent.includes("HTTP 400") || !root.textContent.includes("请求不可恢复")) throw new Error("resume 400 was not visible");

            const beforeDisposeSnapshot = controller.snapshot(); const visibleError = root.textContent;
            const pending = controller.refreshJob("job-c"); await flush();
            controller.dispose();
            if (!requests.at(-1).options.signal.aborted || timers.size !== 0) throw new Error("unmount leaked polling fetch or timer");
            requests.at(-1).resolve({{ id: "job-c", state: "running", user_id: "272" }}); await pending;
            console.log(JSON.stringify({{ requests: requests.length, cleared: cleared.length, snapshot: beforeDisposeSnapshot, text: visibleError }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("complete", result["snapshot"]["jobs"]["job-a"]["state"])
        self.assertIn("HTTP 400", result["text"])

    def test_task7_dispose_clears_health_singleton_secret_elements_and_aborts_mutations(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const sessionValues = new Map([["cinescope.sync.cookie.tab", "dispose-secret"]]);
            const storage = {{ getItem(key) {{ return sessionValues.get(key) ?? null; }}, setItem(key, value) {{ sessionValues.set(key, String(value)); }}, removeItem(key) {{ sessionValues.delete(key); }} }};
            const posts = []; const emissions = [];
            const postJson = (path, payload, options = {{}}) => new Promise((resolve) => posts.push({{ path, payload, options, resolve }}));
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const syncRoot = new FakeElement("div");
            const sync = renderSyncPanel(syncRoot, {{ storage, postJson, fetchJson: async () => ({{}}), onStateChange(state) {{ emissions.push(JSON.parse(JSON.stringify(state))); }} }});
            sync.elements.profile.value = "123456789";
            sync.elements.cookie.value = "dispose-secret";
            const startPending = sync.start(); await flush();
            sync.acceptJob({{ id: "resume-source", state: "needs_cookie", user_id: "123456789", counts: {{ items: 0, collect_count: 0, wish_count: 0, pages_ok: 0, pages_failed: 1 }}, diagnostics: [{{ status: "collect", start: 0, classification: "login_required" }}] }});
            const resumePending = sync.resume("resume-source"); await flush();
            if (posts.length !== 2 || !posts.every((call) => call.options.signal && !call.options.signal.aborted)) throw new Error("start/resume did not receive controlled signals");
            const detachedSecret = sync.elements.cookie;
            const emissionsBeforeDispose = emissions.length;
            sync.dispose();
            if (!posts.every((call) => call.options.signal.aborted)) throw new Error("dispose did not abort start/resume requests");
            if (detachedSecret.value !== "" || sync.elements !== null) throw new Error("disposed element API still exposed the cookie");
            if (syncRoot.textContent.includes("dispose-secret") || syncRoot.children.length !== 0) throw new Error("disposed sync DOM retained secret-bearing nodes");
            if (sessionValues.get("cinescope.sync.cookie.tab") !== "dispose-secret") throw new Error("route dispose removed the same-tab session cookie");
            posts[0].resolve({{ job_id: "late-start", state: "queued" }}); posts[1].resolve({{ job_id: "late-resume", state: "queued" }});
            await Promise.all([startPending, resumePending]);
            const disposedSnapshot = sync.snapshot();
            if (emissions.length !== emissionsBeforeDispose || disposedSnapshot.knownJobIds.length || Object.keys(disposedSnapshot.jobs).length) throw new Error("late mutation wrote state after dispose");

            const {{ renderHealth, destroyHealth }} = await import("{module_url('js/features/health.js')}");
            const health = renderHealth(new FakeElement("main"), {{ fetchJson: async (path) => path === "/api/v2/media/health" ? {{ assets: {{}}, jobs: {{}}, delivery: "local-only" }} : {{ id: "none", state: "unknown" }}, postJson }});
            await health.ready; health.dispose();
            if (destroyHealth() !== false) throw new Error("health dispose left the module singleton active");
            console.log(JSON.stringify({{ signals: posts.map((call) => call.options.signal.aborted), disposedSnapshot, session: sessionValues.get("cinescope.sync.cookie.tab"), emissions: emissions.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual([True, True], result["signals"])
        self.assertEqual("dispose-secret", result["session"])
        self.assertEqual([], result["disposedSnapshot"]["knownJobIds"])

    def test_task7_job_payload_schema_allowlist_never_retains_free_form_secrets(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{ fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            controller.elements.cookie.value = "old-cookie-secret";
            controller.acceptJob({{
              id: "malicious-job", user_id: "old-cookie-secret", state: "old-cookie-secret",
              counts: {{ items: "0", collect_count: -1, wish_count: 1.5, pages_ok: null, pages_failed: 0 }},
              stopped_reason: "old-cookie-secret", errors: ["old-cookie-secret"],
              diagnostics: [{{ status: "old-cookie-secret", start: 0, classification: "old-cookie-secret", message: "old-cookie-secret" }}],
            }});
            controller.elements.cookie.value = "new-cookie-secret";
            controller.acceptJob({{
              id: "known-job", user_id: "123456789", state: "needs_cookie",
              counts: {{ items: 0, collect_count: 0, wish_count: 0, pages_ok: 0, pages_failed: 1 }},
              stopped_reason: "new-cookie-secret", errors: ["new-cookie-secret"],
              diagnostics: [{{ status: "collect", start: 0, classification: "login_required", message: "new-cookie-secret" }}],
            }});
            controller.elements.cookie.value = "";
            const snapshot = controller.snapshot(); const raw = JSON.stringify(snapshot); const text = root.textContent;
            for (const secret of ["old-cookie-secret", "new-cookie-secret"]) if (raw.includes(secret) || text.includes(secret)) throw new Error(`secret retained after cookie changed: ${{secret}}`);
            const malicious = snapshot.jobs["malicious-job"];
            if (malicious.user_id !== "" || malicious.state !== "unknown" || malicious.counts !== null) throw new Error("malicious identity/state/counts escaped schema allowlist");
            if (malicious.diagnostics[0].status !== "unknown" || malicious.diagnostics[0].classification !== "unknown") throw new Error("malicious diagnostic enums escaped allowlist");
            if (!text.includes("豆瓣需要登录态")) throw new Error("known classification did not map to fixed copy");
            controller.dispose();
            console.log(JSON.stringify({{ malicious, known: snapshot.jobs["known-job"], text }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("unknown", result["malicious"]["state"])
        self.assertIsNone(result["malicious"]["counts"])
        self.assertIn("豆瓣需要登录态", result["text"])

    def test_sync_panel_keeps_only_latest_job_and_can_clear_history(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const deletes = []; const emissions = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              fetchJson: async () => ({{}}), postJson: async () => ({{}}),
              deleteJson: async (path) => {{ deletes.push(path); return {{ removed: 2 }}; }},
              onStateChange(state) {{ emissions.push(JSON.parse(JSON.stringify(state))); }},
            }});
            controller.acceptJob({{ id: "old-job", state: "failed", user_id: "123456789", counts: {{ items: 0, collect_count: 0, wish_count: 0, pages_ok: 0, pages_failed: 1 }} }});
            controller.acceptJob({{ id: "latest-job", state: "complete", user_id: "123456789", counts: {{ items: 280, collect_count: 244, wish_count: 36, pages_ok: 22, pages_failed: 0 }} }}, {{ replace: true }});
            if (controller.snapshot().knownJobIds.join(",") !== "latest-job") throw new Error("latest sync did not replace stale records");
            await controller.clearHistory();
            if (deletes[0] !== "/api/v2/sync/jobs" || controller.snapshot().knownJobIds.length) throw new Error("sync history was not cleared");
            if (!root.textContent.includes("\u6682\u65e0\u540c\u6b65\u8bb0\u5f55")) throw new Error("empty sync history state was not rendered");
            controller.dispose();
            console.log(JSON.stringify({{ deletes, emissions }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["/api/v2/sync/jobs"], result["deletes"])

    def test_task7_library_resize_anchor_and_repeated_cursor_guard(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = []; const rafs = new Map(); let rafId = 0; const resizeObservers = [];
            class FakeResizeObserver {{ constructor(callback) {{ this.callback = callback; this.disconnected = false; resizeObservers.push(this); }} observe(target) {{ this.target = target; }} disconnect() {{ this.disconnected = true; }} }}
            const fetchJson = (path, options = {{}}) => new Promise((resolve) => requests.push({{ path, options, resolve }}));
            const requestFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            const cancelFrame = (id) => rafs.delete(id);
            const item = (index) => ({{ item_key: `douban:R${{index}}`, title: `Resize ${{index}}`, poster: {{ url: "", media_status: "missing" }} }});
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson, createResizeObserver: (callback) => new FakeResizeObserver(callback), requestFrame, cancelFrame }});
            const ready = controller.mount({{ state: "all" }}); await flush();
            requests[0].resolve({{ items: Array.from({{ length: 80 }}, (_v, index) => item(index)), next_cursor: "repeat-cursor" }}); await ready;
            const viewport = root.querySelector('[data-role="library-window"]');
            viewport.scrollTop = 500; viewport.dispatchEvent({{ type: "scroll" }}); let frame = [...rafs.entries()][0]; rafs.delete(frame[0]); frame[1]();
            const before = controller.snapshot();
            if (before.columns !== 2 || before.anchorItemKey !== "douban:R2") throw new Error(`unexpected readable desktop anchor ${{JSON.stringify(before)}}`);
            viewport.clientWidth = 390; resizeObservers[0].callback([{{ target: viewport, contentRect: {{ width: 390 }} }}]);
            if (rafs.size !== 1) throw new Error("resize was not merged through the existing RAF");
            frame = [...rafs.entries()][0]; rafs.delete(frame[0]); frame[1]();
            const mobile = controller.snapshot();
            if (mobile.columns !== 1 || mobile.anchorItemKey !== "douban:R2" || mobile.renderedItemCount === before.renderedItemCount) throw new Error(`resize did not preserve anchor/update window: ${{JSON.stringify(mobile)}}`);

            const next = controller.loadNext(); await flush();
            if (!requests[1].path.includes("cursor=repeat-cursor")) throw new Error("next cursor was not requested");
            requests[1].resolve({{ items: Array.from({{ length: 24 }}, (_v, index) => item(index)), next_cursor: "repeat-cursor" }}); await next;
            const guarded = controller.snapshot();
            if (guarded.nextCursor !== null) throw new Error("non-advancing duplicate cursor remained active");
            await controller.loadNext(); await flush();
            if (requests.length !== 2) throw new Error("sentinel repeated a seen cursor page");
            controller.dispose();
            const disposed = controller.snapshot(); viewport.clientWidth = 1000; resizeObservers[0].callback([{{ target: viewport, contentRect: {{ width: 1000 }} }}]);
            if (!resizeObservers[0].disconnected || rafs.size || controller.snapshot().columns !== disposed.columns) throw new Error("disposed resize observer still mutated layout");
            console.log(JSON.stringify({{ before, mobile, guarded, disposed, requests: requests.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["before"]["columns"])
        self.assertEqual(1, result["mobile"]["columns"])
        self.assertEqual("douban:R2", result["mobile"]["anchorItemKey"])
        self.assertEqual(2, result["requests"])

    def test_task7_library_failed_cursor_retries_then_successful_cycle_stops(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = [];
            const fetchJson = (path, options = {{}}) => new Promise((resolve, reject) => requests.push({{ path, options, resolve, reject }}));
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson, createResizeObserver: () => null, windowTarget: null }});
            const ready = controller.mount({{ state: "all" }}); await flush();
            requests[0].resolve({{ items: [{{ item_key: "douban:A", title: "A", poster: {{ url: "", media_status: "missing" }} }}], next_cursor: "cursor-a" }}); await ready;
            const failed = controller.loadNext(); await flush();
            if (!requests[1].path.includes("cursor=cursor-a")) throw new Error("first cursor request missing");
            const duplicateInflight = controller.loadNext(); await flush();
            if (requests.length !== 2) throw new Error("concurrent loadNext duplicated the in-flight cursor");
            requests[1].reject(new Error("temporary network failure")); await Promise.all([failed, duplicateInflight]);
            if (controller.snapshot().nextCursor !== "cursor-a") throw new Error("temporary failure discarded the retry cursor");
            const retried = controller.loadNext(); await flush();
            if (requests.length !== 3 || !requests[2].path.includes("cursor=cursor-a")) throw new Error("failed cursor was not retried");
            requests[2].resolve({{ items: [{{ item_key: "douban:A", title: "A duplicate", poster: {{ url: "", media_status: "missing" }} }}], next_cursor: "cursor-a" }}); await retried;
            if (controller.snapshot().nextCursor !== null) throw new Error("successful non-advancing cursor cycle remained active");
            await controller.loadNext(); await flush();
            if (requests.length !== 3) throw new Error("successful cursor cycle requested again");
            controller.dispose();
            console.log(JSON.stringify({{ requests: requests.map((request) => request.path), snapshot: controller.snapshot() }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(3, len(result["requests"]))
        self.assertIsNone(result["snapshot"]["nextCursor"])

    def test_task7_library_window_resize_fallback_reflows_and_dispose_unbinds(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const windowListeners = new Map(); const rafs = new Map(); let rafId = 0;
            const windowTarget = {{ addEventListener(type, listener) {{ windowListeners.set(type, listener); }}, removeEventListener(type, listener) {{ if (windowListeners.get(type) === listener) windowListeners.delete(type); }} }};
            const requestFrame = (callback) => {{ const id = ++rafId; rafs.set(id, callback); return id; }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson: async () => ({{ items: Array.from({{ length: 40 }}, (_v, index) => ({{ item_key: `douban:F${{index}}`, title: `F${{index}}`, poster: {{ url: "", media_status: "missing" }} }})), next_cursor: null }}), createResizeObserver: () => null, windowTarget, requestFrame, cancelFrame(id) {{ rafs.delete(id); }} }});
            await controller.mount({{ state: "all" }});
            const viewport = root.querySelector('[data-role="library-window"]');
            if (controller.snapshot().columns !== 2 || typeof windowListeners.get("resize") !== "function") throw new Error("window resize fallback was not installed");
            viewport.clientWidth = 390; windowListeners.get("resize")();
            const frame = [...rafs.entries()][0]; rafs.delete(frame[0]); frame[1]();
            if (controller.snapshot().columns !== 1) throw new Error("window resize fallback did not reflow columns");
            controller.dispose(); const disposedColumns = controller.snapshot().columns;
            if (windowListeners.has("resize")) throw new Error("dispose did not remove window resize fallback");
            viewport.clientWidth = 1000;
            if (rafs.size || controller.snapshot().columns !== disposedColumns) throw new Error("disposed fallback still changed layout");
            console.log(JSON.stringify({{ columns: disposedColumns, listeners: windowListeners.size, rafs: rafs.size }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["columns"])
        self.assertEqual(0, result["listeners"])

    def test_task7_missing_numeric_values_remain_unknown_and_empty_counts_are_incomplete(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const {{ renderTasteDna }} = await import("{module_url('js/features/taste.js')}");
            const tasteRoot = new FakeElement("main");
            const taste = renderTasteDna(tasteRoot, {{ fetchJson: async () => ({{ groups: {{ stable: [{{ feature: "Null score", score: null }}], conflicting: [{{ feature: "Missing score" }}], recent: [], negative: [], unexplored: [] }} }}) }}); await taste.ready;
            if (!tasteRoot.textContent.includes("探索中") || tasteRoot.textContent.includes("非常鲜明") || tasteRoot.textContent.includes("信号分数 0.00")) throw new Error("missing taste score was presented as measured strength");

            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const healthRoot = new FakeElement("main");
            const health = renderHealth(healthRoot, {{ fetchJson: async (path) => path === "/api/v2/media/health" ? {{ assets: {{ total: null, bytes: null }}, jobs: {{ queued: null }}, delivery: "local-only" }} : ({{}}), postJson: async () => ({{}}) }}); await health.ready;
            const healthText = healthRoot.textContent;
            if (healthText.includes("0 B") || healthText.includes("排队 0") || !healthText.includes("排队 —")) throw new Error("missing health values became zero");

            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const syncRoot = new FakeElement("div"); const sync = renderSyncPanel(syncRoot, {{ fetchJson: async () => ({{}}), postJson: async () => ({{}}) }});
            sync.acceptJob({{ id: "empty-counts", state: "complete", user_id: "123456789", counts: {{}} }});
            const job = sync.snapshot().jobs["empty-counts"];
            if (!job.incomplete || syncRoot.textContent.includes("同步完成")) throw new Error("complete with empty counts was shown as success");
            taste.dispose(); health.dispose(); sync.dispose();
            console.log(JSON.stringify({{ taste: tasteRoot.textContent, health: healthText, job }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["job"]["incomplete"])
        self.assertIn("排队 —", result["health"])

    def test_task7_profile_and_options_emit_immediately_but_cookie_edits_never_emit(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const emissions = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const controller = renderSyncPanel(new FakeElement("div"), {{ fetchJson: async () => ({{}}), postJson: async () => ({{}}), onStateChange(state) {{ emissions.push(JSON.parse(JSON.stringify(state))); }} }});
            controller.elements.profile.value = "123456789"; controller.elements.profile.dispatchEvent({{ type: "input" }});
            controller.elements.includeWish.checked = false; controller.elements.includeWish.dispatchEvent({{ type: "change" }});
            controller.elements.includeDo.checked = true; controller.elements.includeDo.dispatchEvent({{ type: "change" }});
            const beforeCookie = emissions.length;
            controller.elements.cookie.value = "never-persist"; controller.elements.cookie.dispatchEvent({{ type: "input" }});
            if (emissions.length !== beforeCookie || beforeCookie !== 3) throw new Error("edit emission policy was wrong");
            const last = emissions.at(-1);
            if (last.profile !== "123456789" || last.options.includeWish !== false || last.options.includeDo !== true || JSON.stringify(emissions).includes("never-persist")) throw new Error("public edit state was incomplete or secret-bearing");
            const detachedProfile = controller.elements.profile; controller.dispose(); detachedProfile.value = "after-dispose"; detachedProfile.dispatchEvent({{ type: "input" }});
            if (emissions.length !== beforeCookie) throw new Error("disposed edit listener still emitted state");
            console.log(JSON.stringify({{ emissions }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(3, len(result["emissions"]))
        self.assertTrue(result["emissions"][-1]["options"]["includeDo"])

    def test_task7_custom_douban_id_starts_and_store_round_trips_without_query_secrets(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const posts = []; const emissions = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{ fetchJson: async () => ({{}}), postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ job_id: "custom-job", state: "queued", user_id: "untrusted-custom-id" }}; }}, onStateChange(state) {{ emissions.push(JSON.parse(JSON.stringify(state))); }}, setTimer() {{ return 1; }}, clearTimer() {{}} }});
            controller.elements.profile.value = "my.douban_user-1";
            const started = await controller.start();
            if (!started || posts[0].payload.user !== "my.douban_user-1" || controller.snapshot().profile !== "my.douban_user-1") throw new Error("safe custom Douban ID was rejected");
            if (started.user_id !== "") throw new Error("untrusted job response user_id was relaxed with input validation");

            const {{ persistUiState, restoreUiState }} = await import("{module_url('js/core/store.js')}");
            const values = new Map(); const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            persistUiState({{ activePath: "/health", sync: {{ profile: controller.snapshot().profile, options: controller.snapshot().options, knownJobIds: [] }} }}, storage);
            const restored = restoreUiState(storage);
            if (restored.sync.profile !== "my.douban_user-1") throw new Error("custom ID did not survive store round-trip");

            controller.elements.profile.value = "bad/id?cookie=query-secret";
            const rejected = await controller.start();
            if (rejected !== null || posts.length !== 1 || JSON.stringify(controller.snapshot()).includes("query-secret")) throw new Error("illegal direct ID or query secret was accepted");
            controller.elements.profile.value = "https://www.douban.com/people/my.douban_user-1/?cookie=query-secret";
            await controller.start();
            if (posts[1].payload.user !== "https://www.douban.com/people/my.douban_user-1/" || JSON.stringify(controller.snapshot()).includes("query-secret")) throw new Error("profile URL query secret was not normalized away");
            controller.dispose();
            console.log(JSON.stringify({{ posts: posts.map((call) => call.payload.user), restored: restored.sync.profile, emissions }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("my.douban_user-1", result["posts"][0])
        self.assertEqual("my.douban_user-1", result["restored"])

    def test_task7_polling_retries_network_and_5xx_but_stops_on_400_404(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const requests = []; const timers = new Map(); let timerId = 0;
            const fetchJson = (path, options = {{}}) => new Promise((resolve, reject) => requests.push({{ path, options, resolve, reject }}));
            const setTimer = (callback, delay) => {{ const id = ++timerId; timers.set(id, {{ callback, delay }}); return id; }};
            const clearTimer = (id) => timers.delete(id);
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{ knownJobIds: ["retry-job"], fetchJson, postJson: async () => ({{}}), setTimer, clearTimer, pollInterval: 100 }});
            await flush(); requests[0].reject(new Error("offline secret text")); await flush();
            if (timers.size !== 1) throw new Error("network error did not keep one retry timer");
            let timerEntry = [...timers.entries()][0]; let timer = timerEntry[1]; const firstDelay = timer.delay; timers.delete(timerEntry[0]); timer.callback(); await flush();
            const serverError = new Error("server secret text"); serverError.status = 500; requests[1].reject(serverError); await flush();
            if (timers.size !== 1) throw new Error("500 did not keep one retry timer");
            timerEntry = [...timers.entries()][0]; timer = timerEntry[1]; const secondDelay = timer.delay; if (secondDelay <= firstDelay) throw new Error("retry backoff did not increase"); timers.delete(timerEntry[0]); timer.callback(); await flush();
            requests[2].resolve({{ id: "retry-job", state: "running", user_id: "123456789", counts: {{ items: 1, collect_count: 1, wish_count: 0, pages_ok: 1, pages_failed: 0 }} }}); await flush();
            if (timers.size !== 1) throw new Error("successful running poll lost its single timer");

            controller.acceptJob({{ id: "bad-400", state: "running", user_id: "123456789", counts: {{ items: 0, collect_count: 0, wish_count: 0, pages_ok: 0, pages_failed: 0 }} }});
            const bad400 = controller.refreshJob("bad-400"); await flush(); const error400 = new Error("secret 400"); error400.status = 400; requests[3].reject(error400); await bad400;
            controller.acceptJob({{ id: "bad-404", state: "running", user_id: "123456789", counts: {{ items: 0, collect_count: 0, wish_count: 0, pages_ok: 0, pages_failed: 0 }} }});
            const bad404 = controller.refreshJob("bad-404"); await flush(); const error404 = new Error("secret 404"); error404.status = 404; requests[4].reject(error404); await bad404;
            const text = root.textContent;
            if (text.includes("secret 400") || text.includes("secret 404") || !text.includes("HTTP 404") || timers.size !== 1) throw new Error("non-retryable polling error was leaked or retried");
            controller.dispose();
            console.log(JSON.stringify({{ firstDelay, secondDelay, timers: timers.size, text, requests: requests.length }}));
            '''
        )
        result = json.loads(output)
        self.assertGreater(result["secondDelay"], result["firstDelay"])
        self.assertEqual(5, result["requests"])
        self.assertIn("HTTP 404", result["text"])

    def test_task7_state_routes_static_css_and_390_overflow_contract(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const {{ createAppRouteHandler, reduceUiState }} = await import("{module_url('js/app.js')}");
            const calls = []; const disposals = [];
            const store = {{ state: {{ activePath: null, activeParams: {{}}, recommendation: {{ channels: {{}} }}, library: {{ state: "wish" }}, sync: {{ knownJobIds: ["job-1"] }} }}, getState() {{ return this.state; }}, dispatch(action) {{ this.state = reduceUiState(this.state, action); calls.push(action.type); }} }};
            const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
            const appView = {{ dataset: {{}} }};
            const renderer = (name) => (_root, options) => {{ calls.push(`${{name}}:${{options?.filters?.state || options?.syncState?.knownJobIds?.[0] || "default"}}`); return {{ dispose() {{ disposals.push(name); }} }}; }};
            const handler = createAppRouteHandler({{ appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate, prepare() {{}}, setNavigation() {{}}, renderTonightView() {{}}, renderPlaceholder() {{}}, setStatus() {{}}, renderLibraryView: renderer("library"), renderTasteView: renderer("taste"), renderHealthView: renderer("health") }});
            await handler({{ name: "library", path: "/library", params: {{}} }});
            await handler({{ name: "taste", path: "/taste", params: {{}} }});
            await handler({{ name: "health", path: "/health", params: {{}} }});
            handler.dispose();
            if (!calls.includes("library:wish") || !calls.includes("health:job-1")) throw new Error("real space renderer did not receive restored route state");
            if (disposals.join(",") !== "library,taste,health") throw new Error(`route lifecycle did not dispose all spaces: ${{disposals}}`);
            console.log(JSON.stringify({{ calls, disposals, route: appView.dataset.route }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["library", "taste", "health"], result["disposals"])

        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        app = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.assertIn('<link rel="stylesheet" href="/assets/v3/styles/spaces.css" />', html)
        self.assertNotRegex(app, r'pattern:\s*["\']/sync["\']')
        self.assertNotIn('createElement("link")', app)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)")
        self.assertIn("min-width: 0", css)
        self.assertIn("overflow-wrap: anywhere", css)
        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", css)
        for declaration in declarations:
            for transition in declaration.split(","):
                self.assertIn(transition.strip().split(maxsplit=1)[0], {"transform", "opacity"})
        self.assertIn("prefers-reduced-motion", css)

    def test_detail_round_trip_restores_the_exact_library_view_without_refetching(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            globalThis.window = {{ matchMedia: () => ({{ matches: false }}) }};
            const {{ createAppRouteHandler, reduceUiState }} = await import("{module_url('js/app.js')}");

            const heading = (text) => ({{ textContent: text, setAttribute() {{}}, focus() {{}} }});
            const libraryHeading = heading("片库");
            const detailHeading = heading("作品详情");
            const libraryViewport = {{ scrollTop: 875 }};
            const libraryNode = {{
              id: "library-node",
              dataset: {{ space: "library" }},
              querySelector(selector) {{
                if (selector === "h1") return libraryHeading;
                if (selector === ".library-window") return libraryViewport;
                return null;
              }},
            }};
            const detailNode = {{ id: "detail-node", querySelector(selector) {{ return selector === "h1" ? detailHeading : null; }} }};
            const appView = {{
              children: [], dataset: {{}},
              get childNodes() {{ return this.children; }},
              replaceChildren(...nodes) {{
                if (this.children.includes(libraryNode) && !nodes.includes(libraryNode)) libraryViewport.scrollTop = 0;
                this.children = nodes;
              }},
              querySelector(selector) {{
                if (selector === ".tonight-page") return null;
                if (selector === ".space--library" || selector === '[data-space="library"]') return this.children.find((node) => node === libraryNode) || null;
                if (selector === "h1") return this.children[0]?.querySelector?.("h1") || null;
                return null;
              }},
            }};
            const store = {{
              state: {{ activePath: null, activeParams: {{}}, detailReturnPath: "/tonight", recommendation: {{ channels: {{}} }}, library: {{ state: "candidate", explicit: true, scrollTop: 875 }} }},
              getState() {{ return this.state; }},
              dispatch(action) {{ this.state = reduceUiState(this.state, action); }},
            }};
            let libraryRenders = 0;
            let libraryDisposals = 0;
            let librarySuspends = 0;
            let libraryResumes = 0;
            const libraryController = {{
              snapshot() {{ return {{ scrollTop: libraryViewport.scrollTop }}; }},
              suspend() {{ librarySuspends += 1; }},
              resume({{ scrollTop }}) {{ libraryResumes += 1; libraryViewport.scrollTop = scrollTop; }},
              dispose() {{ libraryDisposals += 1; }},
            }};
            const renderLibraryView = async (root) => {{ libraryRenders += 1; root.replaceChildren(libraryNode); return libraryController; }};
            const explorationGate = {{
              invalidate() {{}},
              async render() {{ appView.replaceChildren(detailNode); }},
            }};
            const passiveGate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
            const handler = createAppRouteHandler({{
              appView, store, restoreGate: passiveGate, explorationGate, universeGate: passiveGate,
              prepare() {{}}, setNavigation() {{}}, renderTonightView() {{}}, renderPlaceholder() {{}},
              renderLibraryView, renderTasteView: async () => ({{ dispose() {{}} }}), renderHealthView: async () => ({{ dispose() {{}} }}),
              setStatus() {{}}, announceRoute() {{}},
            }});

            await handler({{ name: "library", path: "/library", params: {{}} }});
            await handler({{ name: "title", path: "/title/douban:1", params: {{ id: "douban:1" }} }});
            if (libraryDisposals !== 0 || librarySuspends !== 1 || appView.children[0] !== detailNode) throw new Error("library was disposed or not suspended before detail opened");
            await handler({{ name: "library", path: "/library", params: {{}} }});
            if (libraryRenders !== 1) throw new Error(`library refetched on detail return: ${{libraryRenders}}`);
            if (libraryDisposals !== 0 || libraryResumes !== 1 || appView.children[0] !== libraryNode || libraryViewport.scrollTop !== 875) {{
              throw new Error("library DOM, controller, or internal scroll position was not restored exactly");
            }}
            handler.dispose();
            if (libraryDisposals !== 1) throw new Error("restored library controller was not disposed at app teardown");
            console.log(JSON.stringify({{ libraryRenders, libraryDisposals, librarySuspends, libraryResumes, node: appView.children[0]?.id, scrollTop: libraryViewport.scrollTop }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["libraryRenders"])
        self.assertEqual(1, result["libraryDisposals"])
        self.assertEqual(875, result["scrollTop"])

    def test_store_persists_library_and_non_sensitive_sync_allowlist_without_raw_cookie(self):
        output = run_node_module(
            f'''
            import {{ persistUiState, restoreUiState, UI_STATE_KEY }} from "{module_url('js/core/store.js')}";
            const values = new Map(); const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }};
            persistUiState({{
              activePath: "/health", library: {{ state: "wish", scrollTop: 1234 }},
              sync: {{ profile: "https://www.douban.com/people/123456789/?cookie=must-not-persist", options: {{ maxPages: 250, includeWish: true, includeDo: false, expectedCollect: 244, expectedWish: 36 }}, knownJobIds: ["job-a", "job-a", "bad/id"], payload: {{ cookie: "must-not-persist" }} }},
              doubanCookie: "must-not-persist",
            }}, storage);
            const raw = values.get(UI_STATE_KEY); const restored = restoreUiState(storage);
            if (raw.includes("must-not-persist") || raw.toLowerCase().includes("cookie")) throw new Error("raw persisted snapshot contains cookie material");
            if (restored.activePath !== "/health" || restored.library.state !== "wish" || restored.library.scrollTop !== 1234) throw new Error("route or library filter/position was not restored");
            if (restored.sync.profile !== "https://www.douban.com/people/123456789/" || restored.sync.options.maxPages !== 250) throw new Error("safe sync profile/options were not restored");
            if (restored.sync.knownJobIds.join(",") !== "job-a") throw new Error("known job IDs were not allowlisted and deduplicated");
            console.log(JSON.stringify({{ raw, restored }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("wish", result["restored"]["library"]["state"])
        self.assertEqual(1234, result["restored"]["library"]["scrollTop"])
        self.assertEqual(["job-a"], result["restored"]["sync"]["knownJobIds"])

    def test_universe_stylesheet_is_static_responsive_and_motion_safe(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "universe.css").read_text(encoding="utf-8")

        self.assertIn('<link rel="stylesheet" href="/assets/v3/styles/universe.css" />', html)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*relationship-list")
        self.assertIn("prefers-reduced-motion", css)
        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", css)
        for declaration in declarations:
            for transition in declaration.split(","):
                property_name = transition.strip().split(maxsplit=1)[0]
                with self.subTest(transition=transition):
                    self.assertIn(property_name, {"transform", "opacity"})

    def test_mobile_universe_roster_entries_keep_readable_width_before_horizontal_scroll(self):
        css = (UI_ROOT / "styles" / "universe.css").read_text(encoding="utf-8")

        self.assertRegex(
            css,
            r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.universe-node-entry\s*\{[^}]*flex\s*:\s*0\s+0\s+min\(",
        )
        self.assertRegex(
            css,
            r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.universe-node-button\s*\{[^}]*width\s*:\s*100%",
        )

    def test_route_focus_target_has_no_visual_outline_and_rail_controls_wrap_without_overflow(self):
        css = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")
        tonight = (UI_ROOT / "styles" / "tonight.css").read_text(encoding="utf-8")
        responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")

        route_focus = re.search(r'#app-view\s+\[tabindex="-1"\]:focus\s*\{([^}]*)\}', css)
        self.assertIsNotNone(route_focus)
        self.assertRegex(route_focus.group(1), r"outline\s*:\s*none")

        rail_control = re.search(r"\.rail-control\s*\{([^}]*)\}", css)
        self.assertIsNotNone(rail_control)
        self.assertRegex(rail_control.group(1), r"font-size\s*:\s*0\.8rem")
        self.assertRegex(rail_control.group(1), r"overflow-wrap\s*:\s*anywhere")
        self.assertNotRegex(rail_control.group(1), r"white-space\s*:\s*nowrap")

        route_heading = re.search(r'#app-view\s+h1\[tabindex="-1"\]\s*\{([^}]*)\}', responsive)
        self.assertIsNotNone(route_heading)
        self.assertRegex(route_heading.group(1), r"text-wrap\s*:\s*balance")
        self.assertRegex(route_heading.group(1), r"overflow-wrap\s*:\s*break-word")
        self.assertRegex(route_heading.group(1), r"word-break\s*:\s*normal")

        tonight_title = re.search(r"\.tonight-intro__title\s*\{([^}]*)\}", tonight)
        self.assertIsNotNone(tonight_title)
        self.assertRegex(tonight_title.group(1), r"max-width\s*:\s*none")
        self.assertRegex(tonight_title.group(1), r"font-size\s*:\s*clamp\(2\.2rem,\s*4\.6vw,\s*4\.8rem\)")

        tablet = re.search(r"@media\s*\(max-width:\s*1200px\)\s*\{([\s\S]*?)\n\}", responsive)
        self.assertIsNotNone(tablet)
        self.assertRegex(tablet.group(1), r"\.tonight-intro\s*\{[^}]*flex-direction\s*:\s*column")
        self.assertRegex(tablet.group(1), r"\.tonight-channels\s*\{[^}]*justify-content\s*:\s*flex-start")

        source = "".join(
            (UI_ROOT / path).read_text(encoding="utf-8")
            for path in ("js/features/universe.js", "js/features/detail.js", "js/app.js")
        )
        self.assertNotIn("innerHTML", source)
        self.assertNotIn('createElement("link")', source)

    def test_route_title_contract_breaks_long_continuous_text_before_horizontal_overflow(self):
        responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        route_heading = re.search(r'#app-view\s+h1\[tabindex="-1"\]\s*\{([^}]*)\}', responsive)
        self.assertIsNotNone(route_heading)

        declarations = route_heading.group(1)
        title_without_break_opportunities = "InterstellarDirectorCutRestoredEdition" * 24
        has_emergency_wrap = re.search(
            r"(?:overflow-wrap\s*:\s*(?:break-word|anywhere)|word-break\s*:\s*(?:break-all|break-word))",
            declarations,
        )

        self.assertGreater(len(title_without_break_opportunities), 390)
        self.assertIsNotNone(
            has_emergency_wrap,
            "A route title with no whitespace must have emergency wrapping rather than overflow its mobile container.",
        )

    def test_detail_stylesheet_is_static_cinematic_and_motion_safe(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")
        responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")

        self.assertIn('<link rel="stylesheet" href="/assets/v3/styles/detail.css" />', html)
        self.assertRegex(css, r"\.detail-backdrop\s*\{[^}]*aspect-ratio:\s*16\s*/\s*7", re.DOTALL)
        self.assertRegex(css, r"\.detail-poster[^}]*\.media-frame__image\s*\{[^}]*object-fit:\s*contain", re.DOTALL)
        self.assertRegex(css, r"\.detail-return-bar\s*\{[^}]*position:\s*sticky", re.DOTALL)
        self.assertRegex(css, r"\.detail-evidence\s*\{[^}]*grid-template-columns:\s*repeat\(2", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.detail-evidence\s*\{[^}]*grid-template-columns:\s*1fr", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.detail-hero__content\s*\{[^}]*grid-template-columns:\s*1fr", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.detail-poster\s*\{[^}]*width:\s*min\(9rem,\s*42vw\)[^}]*margin:\s*-4rem\s+auto\s+0", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.detail-hero__copy\s*\{[^}]*width:\s*100%", re.DOTALL)
        responsive_mobile = re.search(
            r"@media\s*\(max-width:\s*720px\)\s*\{([\s\S]*?)\n\}\n\n@media\s*\(prefers-reduced-motion",
            responsive,
        )
        self.assertIsNotNone(responsive_mobile)
        responsive_hero = re.search(r"\.detail-hero__content\s*\{([^}]*)\}", responsive_mobile.group(1))
        self.assertIsNotNone(responsive_hero)
        self.assertRegex(responsive_hero.group(1), r"grid-template-columns:\s*1fr")
        self.assertRegex(responsive_hero.group(1), r"align-items:\s*start")
        self.assertRegex(responsive_hero.group(1), r"margin-top:\s*0")
        self.assertIn("prefers-reduced-motion", css)
        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", css)
        for declaration in declarations:
            for transition in declaration.split(","):
                property_name = transition.strip().split(maxsplit=1)[0]
                with self.subTest(transition=transition):
                    self.assertIn(property_name, {"transform", "opacity"})

        source = "".join(
            (UI_ROOT / path).read_text(encoding="utf-8")
            for path in ("js/features/detail.js", "js/features/people.js", "js/app.js")
        )
        self.assertNotIn("innerHTML", source)
        self.assertNotIn('createElement("link")', source)

    def test_tonight_stylesheet_is_static_and_motion_safe(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        css = (UI_ROOT / "styles" / "tonight.css").read_text(encoding="utf-8")

        self.assertIn('<link rel="stylesheet" href="/assets/v3/styles/tonight.css" />', html)
        self.assertIn("prefers-reduced-motion", css)
        self.assertIn(".tonight-hero-filmstrip", css)
        self.assertIn(".tonight-hero-filmstrip__button[aria-pressed=\"true\"]", css)
        self.assertRegex(css, r"@media \(max-width: 720px\)[\s\S]*?\.tonight-hero-filmstrip")
        hero_rule = re.search(r"\.tonight-hero\s*\{([^}]+)\}", css)
        self.assertIsNotNone(hero_rule)
        self.assertRegex(hero_rule.group(1), r"(?:^|\n)\s*height:\s*clamp\(")
        carousel_stage = re.search(r"\.cinema-carousel__stage\s*\{([^}]+)\}", css)
        self.assertIsNotNone(carousel_stage)
        self.assertRegex(carousel_stage.group(1), r"height:\s*clamp\(30rem,\s*58vh,\s*38rem\)")
        self.assertNotRegex(carousel_stage.group(1), r"aspect-ratio:\s*16\s*/\s*9")
        self.assertRegex(
            css,
            r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.cinema-carousel__stage\s*\{[^}]*height:\s*clamp\(24rem,\s*49vh,\s*27rem\)[^}]*min-height:\s*24rem",
            re.DOTALL,
        )
        mobile_carousel = css.rsplit("@media (max-width: 720px)", 1)[1].split(
            "@media (prefers-reduced-motion: reduce)", 1
        )[0]
        self.assertRegex(
            mobile_carousel,
            r"\.cinema-carousel__arrow\s*\{[^}]*top:\s*1rem[^}]*transform:\s*none",
            re.DOTALL,
        )
        self.assertRegex(
            mobile_carousel,
            r"\.cinema-carousel__arrow--previous\s*\{[^}]*left:\s*auto[^}]*right:\s*4\.5rem",
            re.DOTALL,
        )
        self.assertRegex(
            mobile_carousel,
            r"\.cinema-carousel__arrow--next\s*\{[^}]*right:\s*1rem",
            re.DOTALL,
        )
        self.assertRegex(
            mobile_carousel,
            r"\.cinema-carousel__arrow:hover,\s*\.cinema-carousel__arrow:focus-visible\s*\{[^}]*transform:\s*scale\(1\.06\)",
            re.DOTALL,
        )
        title_rule = re.search(r"\.tonight-hero__title\s*\{([^}]+)\}", css)
        self.assertIsNotNone(title_rule)
        self.assertRegex(title_rule.group(1), r"white-space:\s*nowrap")
        self.assertNotIn("text-overflow: ellipsis", title_rule.group(1))
        self.assertNotRegex(title_rule.group(1), r"overflow:\s*hidden")
        self.assertNotIn("-webkit-line-clamp", title_rule.group(1))
        line_height = re.search(r"line-height:\s*([0-9.]+)", title_rule.group(1))
        self.assertIsNotNone(line_height)
        self.assertGreaterEqual(float(line_height.group(1)), 1.0)
        filmstrip_title = re.search(r"\.tonight-hero-filmstrip__title\s*\{([^}]+)\}", css)
        self.assertIsNotNone(filmstrip_title)
        self.assertRegex(filmstrip_title.group(1), r"white-space:\s*nowrap")
        self.assertNotIn("text-overflow: ellipsis", filmstrip_title.group(1))
        declarations = re.findall(r"(?<![-\w])transition\s*:\s*([^;]+);", css)
        for declaration in declarations:
            for transition in declaration.split(","):
                property_name = transition.strip().split(maxsplit=1)[0]
                with self.subTest(transition=transition):
                    self.assertIn(property_name, {"transform", "opacity"})

        app_source = (UI_ROOT / "js" / "app.js").read_text(encoding="utf-8")
        self.assertNotIn("createElement(\"link\")", app_source)
        self.assertNotIn("createElement('link')", app_source)

        tonight_source = (UI_ROOT / "js" / "features" / "tonight.js").read_text(encoding="utf-8")
        self.assertIn("fitHeroTitle", tonight_source)
        self.assertIn("scrollWidth", tonight_source)
        self.assertIn("requestAnimationFrame", tonight_source)

    def test_focus_trap_cycles_dynamic_tabbables_releases_and_handles_escape(self):
        output = run_node_module(
            f'''
            const listeners = new Map();
            const announcer = {{ textContent: "", isConnected: true }};
            const document = {{
              activeElement: null,
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
              getElementById(id) {{ return id === "a11y-announcer" ? announcer : null; }},
            }};
            globalThis.document = document;
            const focusable = (name) => ({{
              name, disabled: false, hidden: false, isConnected: true,
              focusCount: 0, focus() {{ document.activeElement = this; this.focusCount += 1; }},
              getAttribute(attribute) {{ return attribute === "aria-hidden" ? null : null; }},
              matches() {{ return true; }},
            }});
            const first = focusable("first");
            const middle = focusable("middle");
            const last = focusable("last");
            const items = [first, middle];
            const dialog = {{
              isConnected: true,
              contains(node) {{ return items.includes(node); }},
              querySelectorAll() {{ return [...items]; }},
            }};
            let escapes = 0;
            const {{ announce, trapFocus }} = await import("{module_url('js/core/focus.js')}");
            const release = trapFocus(dialog, {{ onEscape() {{ escapes += 1; }} }});
            const dispatch = (event) => {{ for (const listener of listeners.get("keydown") || []) listener(event); }};
            let prevented = 0;
            middle.focus();
            dispatch({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== first) throw new Error("forward Tab did not wrap to first focusable");
            items.push(last);
            first.focus();
            dispatch({{ key: "Tab", shiftKey: true, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== last) throw new Error("Shift+Tab did not include dynamically added focusable");
            dispatch({{ key: "Escape", preventDefault() {{ prevented += 1; }} }});
            if (escapes !== 1) throw new Error("Escape handler was not invoked once");
            release(); release();
            last.focus();
            dispatch({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== last || (listeners.get("keydown")?.size || 0) !== 0) throw new Error("released trap still intercepted focus");
            announce("First route"); announce("Latest route"); await Promise.resolve();
            if (announcer.textContent !== "Latest route") throw new Error("persistent announcer did not publish only the latest message");
            console.log(JSON.stringify({{ prevented, escapes, announcement: announcer.textContent, first: first.focusCount, last: last.focusCount, listeners: listeners.get("keydown")?.size || 0 }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(3, result["prevented"])
        self.assertEqual(1, result["escapes"])
        self.assertEqual("Latest route", result["announcement"])
        self.assertEqual(0, result["listeners"])

    def test_focus_trap_filters_real_tabbables_and_restores_empty_dialog_tabindex(self):
        output = run_node_module(
            f'''
            const listeners = new Map();
            class Element {{
              constructor(tagName, name) {{
                this.tagName = tagName.toUpperCase(); this.name = name; this.children = []; this.parentElement = null;
                this.attributes = new Map(); this.disabled = false; this.hidden = false; this.inert = false; this.isConnected = true;
                this.computed = {{ display: "block", visibility: "visible" }}; this.focusCount = 0;
              }}
              append(...nodes) {{ for (const node of nodes) {{ this.children.push(node); node.parentElement = this; }} }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              hasAttribute(name) {{ return this.attributes.has(name); }}
              removeAttribute(name) {{ this.attributes.delete(name); }}
              focus() {{ document.activeElement = this; this.focusCount += 1; }}
              contains(node) {{ for (let current = node; current; current = current.parentElement) if (current === this) return true; return false; }}
              querySelectorAll() {{
                const found = [];
                const visit = (node) => {{
                  for (const child of node.children) {{
                    if (["A", "BUTTON", "INPUT", "SELECT", "TEXTAREA"].includes(child.tagName) || child.hasAttribute("tabindex") || child.hasAttribute("contenteditable")) found.push(child);
                    visit(child);
                  }}
                }};
                visit(this); return found;
              }}
            }}
            const document = {{
              activeElement: null,
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
            }};
            globalThis.document = document;
            globalThis.getComputedStyle = (node) => node.computed;
            const outside = new Element("button", "outside");
            const dialog = new Element("section", "dialog");
            const hiddenParent = new Element("div", "hidden-parent"); hiddenParent.hidden = true;
            const hiddenChild = new Element("button", "hidden-child"); hiddenParent.append(hiddenChild);
            const inertParent = new Element("div", "inert-parent"); inertParent.inert = true;
            const inertChild = new Element("button", "inert-child"); inertParent.append(inertChild);
            const ariaParent = new Element("div", "aria-parent"); ariaParent.setAttribute("aria-hidden", "true");
            const ariaChild = new Element("button", "aria-child"); ariaParent.append(ariaChild);
            const displayParent = new Element("div", "display-parent"); displayParent.computed.display = "none";
            const displayChild = new Element("button", "display-child"); displayParent.append(displayChild);
            const visibilityParent = new Element("div", "visibility-parent"); visibilityParent.computed.visibility = "hidden";
            const visibilityChild = new Element("button", "visibility-child"); visibilityParent.append(visibilityChild);
            const disconnectedParent = new Element("div", "disconnected-parent"); disconnectedParent.isConnected = false;
            const disconnectedChild = new Element("button", "disconnected-child"); disconnectedParent.append(disconnectedChild);
            const negative = new Element("button", "negative"); negative.setAttribute("tabindex", "-2");
            const disabled = new Element("button", "disabled"); disabled.disabled = true;
            const hiddenSelf = new Element("button", "hidden-self"); hiddenSelf.hidden = true;
            const visible = new Element("button", "visible");
            dialog.append(hiddenParent, inertParent, ariaParent, displayParent, visibilityParent, disconnectedParent, negative, disabled, hiddenSelf, visible);
            const {{ trapFocus }} = await import("{module_url('js/core/focus.js')}");
            const release = trapFocus(dialog);
            const dispatch = (event) => {{ for (const listener of [...(listeners.get("keydown") || [])]) listener(event); }};
            outside.focus(); let prevented = 0;
            dispatch({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== visible) throw new Error(`invalid descendant became first tabbable: ${{document.activeElement?.name}}`);
            const dynamic = new Element("button", "dynamic"); dialog.append(dynamic); dynamic.focus();
            dispatch({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== visible) throw new Error("dynamic insertion was not recomputed before wrapping");
            visible.disabled = true; dynamic.disabled = true; outside.focus();
            dispatch({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== dialog || dialog.getAttribute("tabindex") !== "-1") throw new Error("empty trap did not retain focus on a programmatically focusable dialog");
            release(); release();
            if (dialog.hasAttribute("tabindex") || (listeners.get("keydown")?.size || 0) !== 0) throw new Error("release did not restore absent tabindex or remove listener");
            const original = new Element("section", "original"); original.setAttribute("tabindex", "7");
            const releaseOriginal = trapFocus(original); outside.focus();
            dispatch({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (original.getAttribute("tabindex") !== "-1" || document.activeElement !== original) throw new Error("empty dialog with existing tabindex was not normalized");
            releaseOriginal();
            if (original.getAttribute("tabindex") !== "7") throw new Error("release did not restore original tabindex value");
            console.log(JSON.stringify({{ prevented, dialogFocus: dialog.focusCount, originalFocus: original.focusCount, listeners: listeners.get("keydown")?.size || 0 }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(4, result["prevented"])
        self.assertEqual(0, result["listeners"])

    def test_command_lens_restores_trigger_reopens_without_trap_leak_and_route_close_skips_restore(self):
        output = run_node_module(
            f'''
            class FakeElement {{
              constructor(tagName) {{
                this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}};
                this.className = ""; this.textContent = ""; this.value = ""; this.disabled = false; this.hidden = false;
                this.isConnected = true; this.focusCount = 0; this.listeners = new Map();
              }}
              append(...nodes) {{ nodes.forEach((node) => this.appendChild(node)); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children.forEach((node) => {{ node.parentNode = null; node.isConnected = false; }}); this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); this[`on${{type}}`] = listener; }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              focus() {{ document.activeElement = this; this.focusCount += 1; }}
              querySelectorAll() {{ return this.children.flatMap((child) => [child, ...child.querySelectorAll()]).filter((node) => ["BUTTON", "TEXTAREA", "INPUT", "A"].includes(node.tagName)); }}
              contains(node) {{ return node === this || this.children.some((child) => child.contains(node)); }}
              get firstElementChild() {{ return this.children[0] || null; }}
            }}
            const root = new FakeElement("div");
            const trigger = new FakeElement("button");
            const listeners = new Map();
            globalThis.document = {{
              readyState: "loading", activeElement: trigger,
              createElement: (tag) => new FakeElement(tag),
              getElementById(id) {{ return id === "command-lens-root" ? root : null; }},
              querySelectorAll() {{ return []; }},
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }},
            }};
            globalThis.window = {{ matchMedia: () => ({{ matches: false }}) }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ closeCommandLens, configureCommandLens, openCommandLens }} = await import("{module_url('js/features/command-lens.js')}");
            configureCommandLens({{ root, store: {{ getState: () => ({{ commandLens: {{ draft: "", chips: [] }}, recommendation: {{ channels: {{}} }} }}), dispatch() {{}} }} }});
            openCommandLens();
            const firstLens = root.firstElementChild;
            const firstInput = firstLens.querySelectorAll().find((node) => node.tagName === "TEXTAREA");
            firstInput.focus();
            for (const listener of listeners.get("keydown") || []) listener({{ key: "k", ctrlKey: true, metaKey: false, preventDefault() {{}} }});
            if (root.firstElementChild === firstLens) throw new Error("Ctrl+K did not reopen the lens");
            if ((listeners.get("keydown")?.size || 0) !== 2) throw new Error(`reopen leaked keydown listeners: ${{listeners.get("keydown")?.size}}`);
            for (const listener of [...(listeners.get("keydown") || [])]) listener({{ key: "Escape", preventDefault() {{}} }});
            if (root.children.length !== 0 || trigger.focusCount !== 1 || (listeners.get("keydown")?.size || 0) !== 1) throw new Error("Escape did not restore trigger or release only the trap");
            trigger.focusCount = 0; trigger.focus();
            openCommandLens();
            closeCommandLens({{ restoreFocus: false }});
            if (trigger.focusCount !== 1 || root.children.length !== 0 || (listeners.get("keydown")?.size || 0) !== 1) throw new Error("route close restored focus or leaked a trap");
            console.log(JSON.stringify({{ focusCount: trigger.focusCount, listeners: listeners.get("keydown")?.size || 0, open: root.children.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["focusCount"])
        self.assertEqual(1, result["listeners"])
        self.assertEqual(0, result["open"])

    def test_command_lens_and_person_sheet_are_mutually_exclusive_with_trigger_handoff(self):
        output = run_node_module(
            f'''
            class FakeClassList {{ add() {{}} remove() {{}} }}
            class FakeElement {{
              constructor(tagName, name = "") {{
                this.tagName = tagName.toUpperCase(); this.name = name; this.children = []; this.parentElement = null; this.parentNode = null;
                this.attributes = new Map(); this.dataset = {{}}; this.className = ""; this.textContent = ""; this.value = "";
                this.disabled = false; this.hidden = false; this.inert = false; this.isConnected = true; this.classList = new FakeClassList();
                this.style = {{ setProperty() {{}} }}; this.listeners = new Map(); this.focusCount = 0;
              }}
              append(...nodes) {{ nodes.forEach((node) => this.appendChild(node)); }}
              appendChild(node) {{ this.children.push(node); node.parentElement = this; node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children.forEach((node) => {{ node.parentElement = null; node.parentNode = null; node.isConnected = false; }}); this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }} getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              hasAttribute(name) {{ return this.attributes.has(name); }} removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); }}
              removeEventListener(type, listener) {{ this.listeners.get(type)?.delete(listener); }}
              remove() {{ if (this.contains(document.activeElement)) document.activeElement = body; if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.isConnected = false; }}
              focus() {{ document.activeElement = this; this.focusCount += 1; }}
              contains(node) {{ for (let current = node; current; current = current.parentElement) if (current === this) return true; return false; }}
              querySelectorAll() {{ const found = []; const visit = (node) => {{ for (const child of node.children) {{ if (["BUTTON", "A", "INPUT", "TEXTAREA"].includes(child.tagName)) found.push(child); visit(child); }} }}; visit(this); return found; }}
              get firstElementChild() {{ return this.children[0] || null; }}
            }}
            const body = new FakeElement("body", "body"); const commandRoot = new FakeElement("div", "command"); const overlayRoot = new FakeElement("div", "overlay");
            const originalTrigger = new FakeElement("button", "person-card"); body.append(originalTrigger, commandRoot, overlayRoot); const listeners = new Map();
            globalThis.document = {{ readyState: "loading", body, activeElement: originalTrigger, createElement: (tag) => new FakeElement(tag),
              getElementById(id) {{ if (id === "command-lens-root") return commandRoot; if (id === "overlay-root") return overlayRoot; return null; }}, querySelectorAll() {{ return []; }},
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }}, removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }} }};
            globalThis.window = {{ matchMedia: () => ({{ matches: false }}) }}; globalThis.location = {{ origin: "https://cinescope.test" }};
            const command = await import("{module_url('js/features/command-lens.js')}");
            const people = await import("{module_url('js/features/people.js')}");
            const store = {{ getState: () => ({{ commandLens: {{ draft: "", chips: [] }}, recommendation: {{ channels: {{}} }} }}), dispatch() {{}} }};
            command.configureCommandLens({{ root: commandRoot, store, onBeforeOpen: () => people.closePersonSheet() }});
            people.configurePeople({{ overlayRoot, onBeforeOpen: () => command.closeCommandLens(), fetchJson(_path, {{ signal }}) {{ return new Promise((_resolve, reject) => signal.addEventListener("abort", () => reject(new DOMException("aborted", "AbortError")), {{ once: true }})); }} }});
            originalTrigger.focus(); const firstPerson = people.openPersonSheet("person:1");
            const modalCount = () => [commandRoot, overlayRoot].flatMap((root) => collect(root)).filter((node) => node.getAttribute?.("aria-modal") === "true").length;
            const collect = (node) => [node, ...node.children.flatMap((child) => collect(child))];
            if (modalCount() !== 1 || overlayRoot.children.length !== 1) throw new Error("person sheet did not open alone");
            for (const listener of [...(listeners.get("keydown") || [])]) listener({{ key: "k", ctrlKey: true, metaKey: false, preventDefault() {{}} }});
            await Promise.resolve();
            if (modalCount() !== 1 || overlayRoot.children.length !== 0 || commandRoot.children.length !== 1) throw new Error("Ctrl+K left two modal traps active");
            command.closeCommandLens();
            if (document.activeElement !== originalTrigger) throw new Error("Lens did not capture the restored person trigger");
            command.openCommandLens();
            const secondPerson = people.openPersonSheet("person:2");
            if (modalCount() !== 1 || commandRoot.children.length !== 0 || overlayRoot.children.length !== 1) throw new Error("opening Person Sheet did not close Lens first");
            for (const listener of [...(listeners.get("keydown") || [])]) listener({{ key: "Escape", preventDefault() {{}} }});
            await Promise.all([firstPerson, secondPerson]);
            if (modalCount() !== 0 || commandRoot.children.length !== 0 || overlayRoot.children.length !== 0) throw new Error("Escape closed more than the active modal or leaked one");
            console.log(JSON.stringify({{ modalCount: modalCount(), focus: originalTrigger.focusCount, keydownListeners: listeners.get("keydown")?.size || 0 }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(0, result["modalCount"])
        self.assertEqual(1, result["keydownListeners"])

    def test_person_sheet_tabs_dynamic_content_and_route_cleanup_releases_trap(self):
        output = run_node_module(
            f'''
            const pending = (() => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }})();
            class FakeClassList {{ add() {{}} }}
            class FakeElement {{
              constructor(tagName) {{ this.tagName = tagName.toUpperCase(); this.children = []; this.attributes = new Map(); this.dataset = {{}}; this.className = ""; this.textContent = ""; this.disabled = false; this.hidden = false; this.isConnected = true; this.classList = new FakeClassList(); this.style = {{ setProperty() {{}} }}; this.listeners = new Map(); this.focusCount = 0; }}
              append(...nodes) {{ nodes.forEach((node) => this.appendChild(node)); }}
              appendChild(node) {{ this.children.push(node); node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }} getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); this[`on${{type}}`] = listener; }}
              remove() {{ if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.isConnected = false; }}
              focus() {{ document.activeElement = this; this.focusCount += 1; }}
              contains(node) {{ return node === this || this.children.some((child) => child.contains(node)); }}
              querySelectorAll() {{ return this.children.flatMap((child) => [child, ...child.querySelectorAll()]).filter((node) => ["BUTTON", "A", "INPUT"].includes(node.tagName)); }}
              get firstElementChild() {{ return this.children[0] || null; }}
            }}
            const overlayRoot = new FakeElement("div"); const trigger = new FakeElement("button"); const listeners = new Map();
            globalThis.document = {{ activeElement: trigger, createElement: (tag) => new FakeElement(tag), getElementById: () => overlayRoot,
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }}, removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }} }};
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const {{ closePersonSheet, configurePeople, openPersonSheet }} = await import("{module_url('js/features/people.js')}");
            configurePeople({{ overlayRoot, fetchJson() {{ return pending.promise; }} }});
            const opened = openPersonSheet("person:1");
            const sheet = overlayRoot.firstElementChild.firstElementChild;
            const before = sheet.querySelectorAll(); const first = before[0]; const last = before.at(-1);
            last.focus(); let prevented = 0;
            for (const listener of listeners.get("keydown") || []) listener({{ key: "Tab", shiftKey: false, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== first) throw new Error("person sheet forward Tab did not loop");
            const dynamic = new FakeElement("button"); sheet.append(dynamic); first.focus();
            for (const listener of listeners.get("keydown") || []) listener({{ key: "Tab", shiftKey: true, preventDefault() {{ prevented += 1; }} }});
            if (document.activeElement !== dynamic) throw new Error("person sheet trap did not include dynamic content");
            const routeLink = sheet.querySelectorAll().find((node) => node.className === "person-sheet__full-link");
            routeLink.onclick({{}});
            if (overlayRoot.children.length !== 0 || (listeners.get("keydown")?.size || 0) !== 0 || trigger.focusCount !== 0) throw new Error("route cleanup leaked trap or restored focus");
            pending.resolve({{ id: "person:1", name: "late", portrait: {{ url: "", media_status: "missing" }}, known_for: [], evidence: [] }}); await opened;
            if (overlayRoot.children.length !== 0) throw new Error("late person response remounted a closed sheet");
            console.log(JSON.stringify({{ prevented, listeners: listeners.get("keydown")?.size || 0, focusCount: trigger.focusCount }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["prevented"])
        self.assertEqual(0, result["listeners"])
        self.assertEqual(0, result["focusCount"])

    def test_person_sheet_reopen_preserves_first_trigger_when_removed_focus_falls_to_body(self):
        output = run_node_module(
            f'''
            class FakeClassList {{ add() {{}} }}
            class FakeElement {{
              constructor(tagName, name = "") {{ this.tagName = tagName.toUpperCase(); this.name = name; this.children = []; this.parentElement = null; this.parentNode = null; this.attributes = new Map(); this.dataset = {{}}; this.className = ""; this.textContent = ""; this.disabled = false; this.hidden = false; this.inert = false; this.isConnected = true; this.classList = new FakeClassList(); this.style = {{ setProperty() {{}} }}; this.listeners = new Map(); this.focusCount = 0; this.computed = {{ display: "block", visibility: "visible" }}; }}
              append(...nodes) {{ nodes.forEach((node) => this.appendChild(node)); }}
              appendChild(node) {{ this.children.push(node); node.parentElement = this; node.parentNode = this; return node; }}
              replaceChildren(...nodes) {{ this.children = []; this.append(...nodes); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }} getAttribute(name) {{ return this.attributes.get(name) ?? null; }} hasAttribute(name) {{ return this.attributes.has(name); }} removeAttribute(name) {{ this.attributes.delete(name); }}
              addEventListener(type, listener) {{ if (!this.listeners.has(type)) this.listeners.set(type, new Set()); this.listeners.get(type).add(listener); this[`on${{type}}`] = listener; }}
              remove() {{ if (this.contains(document.activeElement)) document.activeElement = body; if (this.parentNode) this.parentNode.children = this.parentNode.children.filter((child) => child !== this); this.isConnected = false; }}
              focus() {{ document.activeElement = this; this.focusCount += 1; }}
              contains(node) {{ for (let current = node; current; current = current.parentElement) if (current === this) return true; return false; }}
              querySelectorAll() {{ const found = []; const visit = (node) => {{ for (const child of node.children) {{ if (["BUTTON", "A", "INPUT", "TEXTAREA"].includes(child.tagName)) found.push(child); visit(child); }} }}; visit(this); return found; }}
              get firstElementChild() {{ return this.children[0] || null; }}
            }}
            const body = new FakeElement("body", "body"); const overlayRoot = new FakeElement("div", "overlay"); body.append(overlayRoot);
            const firstCard = new FakeElement("button", "first-card"); body.append(firstCard); const listeners = new Map();
            globalThis.document = {{ activeElement: firstCard, body, createElement: (tag) => new FakeElement(tag), getElementById: () => overlayRoot,
              addEventListener(type, listener) {{ if (!listeners.has(type)) listeners.set(type, new Set()); listeners.get(type).add(listener); }}, removeEventListener(type, listener) {{ listeners.get(type)?.delete(listener); }} }};
            globalThis.getComputedStyle = (node) => node.computed;
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const person = {{ id: "person:1", name: "Person", portrait: {{ url: "", media_status: "missing" }}, known_for: [], evidence: [] }};
            const {{ closePersonSheet, configurePeople, openPersonSheet }} = await import("{module_url('js/features/people.js')}");
            configurePeople({{ overlayRoot, async fetchJson() {{ return person; }} }});
            await openPersonSheet("person:1");
            await openPersonSheet("person:1");
            if (document.activeElement?.className !== "person-sheet__close") throw new Error("reopened sheet did not own focus");
            await openPersonSheet("person:1");
            for (const listener of [...(listeners.get("keydown") || [])]) listener({{ key: "Escape", preventDefault() {{}} }});
            if (firstCard.focusCount !== 1 || document.activeElement !== firstCard) throw new Error(`final close restored ${{document.activeElement?.name || document.activeElement?.tagName}} instead of first trigger`);
            const restoredCount = firstCard.focusCount; firstCard.focus();
            await openPersonSheet("person:1");
            closePersonSheet({{ restoreFocus: false }});
            if (firstCard.focusCount !== restoredCount + 1 || document.activeElement !== body) throw new Error("route close restored trigger after removed sheet focus fell to body");
            const secondCard = new FakeElement("button", "second-card"); body.append(secondCard); secondCard.focus();
            await openPersonSheet("person:1");
            for (const listener of [...(listeners.get("keydown") || [])]) listener({{ key: "Escape", preventDefault() {{}} }});
            if (secondCard.focusCount !== 2 || document.activeElement !== secondCard || firstCard.focusCount !== restoredCount + 1) throw new Error("route close retained the previous sheet trigger for a later open");
            console.log(JSON.stringify({{ focusCount: firstCard.focusCount, secondFocusCount: secondCard.focusCount, listeners: listeners.get("keydown")?.size || 0, active: document.activeElement.name }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["focusCount"])
        self.assertEqual(2, result["secondFocusCount"])
        self.assertEqual(0, result["listeners"])

    def test_index_has_one_route_live_region_and_visual_shell_status(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        shell_status = re.search(r'<p\s+id="shell-status"([^>]*)>', html)
        announcer = re.search(r'<div\s+id="a11y-announcer"([^>]*)>', html)
        self.assertIsNotNone(shell_status)
        self.assertNotIn("aria-live", shell_status.group(1))
        self.assertNotRegex(shell_status.group(1), r'role="(?:status|alert)"')
        self.assertIsNotNone(announcer)
        self.assertIn('aria-live="polite"', announcer.group(1))
        self.assertEqual(1, len(re.findall(r'aria-live="polite"', html)))

    def test_command_lens_destroy_unbinds_shortcut_and_rebootstrap_does_not_leak(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const nodes = new Map();
            for (const [id, tag] of [["app-view", "main"], ["shell-status", "p"], ["command-lens-root", "div"], ["overlay-root", "div"], ["command-lens-trigger", "button"], ["rail-collapse-toggle", "button"], ["rail-hide-toggle", "button"], ["rail-restore", "button"], ["primary-rail", "aside"], ["a11y-announcer", "div"]]) {{ const node = new FakeElement(tag); node.id = id; nodes.set(id, node); }}
            document.body = new FakeElement("body"); document.body.classList = new FakeClassList(document.body); document.activeElement = document.body;
            const documentListeners = new Map();
            document.getElementById = (id) => nodes.get(id) || null;
            document.querySelectorAll = () => [];
            document.addEventListener = (type, listener) => {{ if (!documentListeners.has(type)) documentListeners.set(type, new Set()); documentListeners.get(type).add(listener); }};
            document.removeEventListener = (type, listener) => documentListeners.get(type)?.delete(listener);
            const storage = new Map(); const windowListeners = new Map();
            const browser = {{
              location: {{ pathname: "/missing" }}, scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return storage.get(key) ?? null; }}, setItem(key, value) {{ storage.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ if (!windowListeners.has(type)) windowListeners.set(type, new Set()); windowListeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{ windowListeners.get(type)?.delete(listener); }},
              dispatchEvent(event) {{ for (const listener of [...(windowListeners.get(event.type) || [])]) listener(event); }},
              requestAnimationFrame(callback) {{ callback(); return 1; }}, scrollTo() {{}}, matchMedia() {{ return {{ matches: false }}; }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.location = browser.location; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage; globalThis.requestAnimationFrame = browser.requestAnimationFrame; globalThis.PopStateEvent = browser.PopStateEvent;
            const {{ bootstrapCineScopeShell }} = await import("{module_url('js/app.js')}");
            const keydowns = () => documentListeners.get("keydown")?.size || 0;
            const dispatchKey = (event) => {{ for (const listener of [...(documentListeners.get("keydown") || [])]) listener(event); }};
            const first = bootstrapCineScopeShell(); await flush();
            document.activeElement = nodes.get("command-lens-trigger");
            dispatchKey({{ key: "k", ctrlKey: true, metaKey: false, preventDefault() {{}} }});
            if (keydowns() !== 2 || nodes.get("command-lens-root").children.length !== 1) throw new Error("first bootstrap did not open one trapped lens");
            first.destroy();
            if (keydowns() !== 0 || nodes.get("command-lens-root").children.length !== 0) throw new Error(`destroy leaked shortcut/trap/root: ${{keydowns()}}/${{nodes.get("command-lens-root").children.length}}`);
            const second = bootstrapCineScopeShell(); await flush();
            if (keydowns() !== 1) throw new Error(`rebootstrap shortcut count was ${{keydowns()}}`);
            document.activeElement = nodes.get("command-lens-trigger"); dispatchKey({{ key: "K", metaKey: true, ctrlKey: false, preventDefault() {{}} }});
            if (keydowns() !== 2 || nodes.get("command-lens-root").children.length !== 1) throw new Error("rebootstrap did not open exactly one lens/trap");
            second.destroy();
            if (keydowns() !== 0 || nodes.get("command-lens-root").children.length !== 0) throw new Error("second destroy leaked command lifecycle");
            console.log(JSON.stringify({{ keydowns: keydowns(), root: nodes.get("command-lens-root").children.length, clickListeners: documentListeners.get("click")?.size || 0 }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(0, result["keydowns"])
        self.assertEqual(0, result["root"])

    def test_real_router_raf_scroll_restore_survives_route_focus_and_announces_once(self):
        output = run_node_module(
            f'''
            const values = new Map(); const events = []; const announcements = [];
            const status = {{ textContent: "", attributes: new Map(), getAttribute(name) {{ return this.attributes.get(name) ?? null; }} }};
            const browser = {{
              location: {{ pathname: "/library" }}, scrollY: 999,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ values.set(key, String(value)); }} }},
              addEventListener() {{}}, removeEventListener() {{}},
              requestAnimationFrame(callback) {{ events.push("raf"); callback(); return 1; }},
              scrollTo(options) {{ events.push(`scroll:${{options.top}}`); this.scrollY = options.top; }},
              matchMedia() {{ return {{ matches: false }}; }},
            }};
            globalThis.window = browser; globalThis.location = browser.location; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage; globalThis.requestAnimationFrame = browser.requestAnimationFrame.bind(browser);
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }} }};
            const heading = {{ textContent: "Library route", attributes: new Map(), setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}, focus(options) {{ events.push(`focus:${{options?.preventScroll}}`); if (!options?.preventScroll) browser.scrollY = 0; }} }};
            const appView = {{ dataset: {{}}, querySelector(selector) {{ return selector === "h1" ? heading : null; }} }};
            const store = {{ state: {{ activePath: null, recommendation: {{ channels: {{}} }}, library: {{ state: "all" }} }}, getState() {{ return this.state; }}, dispatch(action) {{ if (action.type === "route/changed") this.state.activePath = action.route.path; }} }};
            const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }};
            const {{ createAppRouteHandler }} = await import("{module_url('js/app.js')}");
            const {{ createRouter }} = await import("{module_url('js/core/router.js')}");
            const {{ persistUiState }} = await import("{module_url('js/core/store.js')}");
            persistUiState({{ activePath: "/library", scrollByRoute: {{ "/library": 345 }} }}, browser.localStorage);
            const routeHandler = createAppRouteHandler({{
              appView, store, restoreGate: gate, explorationGate: gate, universeGate: gate, prepare() {{}}, setNavigation() {{}},
              renderLibraryView() {{ events.push("render"); return {{ dispose() {{}} }}; }},
              setStatus(message) {{ status.textContent = message; events.push("status"); }},
              announceRoute(message) {{ announcements.push(message); events.push("announce"); }},
            }});
            const router = createRouter([{{ pattern: "/library", name: "library" }}], {{ onRoute: routeHandler }});
            await router.start();
            if (browser.scrollY !== 345) throw new Error(`restored scroll was disturbed: ${{browser.scrollY}}`);
            if (events.filter((event) => event === "focus:true").length !== 1 || events.indexOf("focus:true") > events.indexOf("raf") || events.indexOf("raf") > events.indexOf("scroll:345")) throw new Error(`focus/RAF/scroll order mismatch: ${{events}}`);
            if (!status.textContent.includes("片库") || status.getAttribute("aria-live") !== null) throw new Error("visual shell status was not updated as a non-live region");
            if (announcements.length !== 1 || announcements[0] !== "Library route") throw new Error(`route announced ${{announcements.length}} times`);
            console.log(JSON.stringify({{ events, announcements, scrollY: browser.scrollY, status: status.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(345, result["scrollY"])
        self.assertEqual(1, len(result["announcements"]))

    def test_reduced_motion_skips_view_transitions_and_ready_rejection_is_consumed(self):
        output = run_node_module(
            f'''
            const unhandled = []; process.on("unhandledRejection", (error) => unhandled.push(error.message));
            globalThis.window = {{ matchMedia(query) {{ return {{ matches: query.includes("prefers-reduced-motion") }}; }} }};
            let starts = 0;
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }}, startViewTransition(update) {{ starts += 1; update(); return {{ updateCallbackDone: Promise.resolve(), ready: Promise.reject(new Error("ready rejected")), finished: Promise.resolve() }}; }} }};
            const {{ createExplorationRouteGate }} = await import("{module_url('js/app.js')}");
            const root = {{ children: [{{ id: "stable" }}], replaceChildren(...nodes) {{ this.children = nodes; }} }};
            let activePath = "/title/reduced";
            const renderer = (_id, options) => options.commit({{ id: "reduced-view" }}, {{ heading: "Reduced" }});
            const gate = createExplorationRouteGate({{ root, getActivePath: () => activePath, renderTitle: renderer, renderPerson: renderer }});
            await gate.render({{ name: "title", path: activePath, params: {{ id: "reduced" }} }});
            if (starts !== 0 || root.children[0].id !== "reduced-view") throw new Error("reduced motion did not bypass ViewTransition");

            window.matchMedia = () => ({{ matches: false }});
            activePath = "/title/normal";
            await gate.render({{ name: "title", path: activePath, params: {{ id: "normal" }} }});
            await new Promise((resolve) => setTimeout(resolve, 0));
            if (starts !== 1 || unhandled.length !== 0 || root.children[0].id !== "reduced-view") throw new Error(`ready rejection was unhandled or DOM critical path changed: ${{JSON.stringify({{ starts, unhandled, root: root.children[0] }})}}`);
            console.log(JSON.stringify({{ starts, unhandled, root: root.children[0].id }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["starts"])
        self.assertEqual([], result["unhandled"])

    def test_detail_and_people_reduced_motion_skip_transitions_and_consume_ready_rejections(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const unhandled = []; process.on("unhandledRejection", (error) => unhandled.push(error.message));
            let starts = 0;
            window.matchMedia = (query) => ({{ matches: query.includes("prefers-reduced-motion") }});
            document.startViewTransition = (update) => {{ starts += 1; update(); return {{ updateCallbackDone: Promise.resolve(), ready: Promise.reject(new Error("ready failed")), finished: Promise.resolve() }}; }};
            const title = {{ item_key: "douban:42", title: "Reduced title", media_type: "movie", year: 2024, poster: {{ url: "", media_status: "missing" }}, backdrop: {{ url: "", media_status: "missing" }}, item: {{ directors: [], casts: [] }}, people: [] }};
            const person = {{ id: "person:1", name: "Reduced person", portrait: {{ url: "", media_status: "missing" }}, known_for: [], evidence: [] }};
            const detailRoot = new FakeElement("main");
            const personRoot = new FakeElement("main");
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            const {{ configurePeople, renderPersonPage }} = await import("{module_url('js/features/people.js')}");
            configureDetail({{ root: detailRoot, async fetchJson(path) {{ return path.startsWith("/api/v2/titles/") ? title : {{ focus_id: "douban:42", nodes: [], edges: [] }}; }}, api: {{ async postV2() {{ return null; }} }} }});
            configurePeople({{ root: personRoot, async fetchJson() {{ return person; }} }});
            await renderTitleDetail("douban:42");
            await renderPersonPage("person:1");
            if (starts !== 0 || detailRoot.children.length !== 1 || personRoot.children.length !== 1) throw new Error("reduced motion did not synchronously commit detail and people views");
            window.matchMedia = () => ({{ matches: false }});
            await renderTitleDetail("douban:42");
            await renderPersonPage("person:1");
            await new Promise((resolve) => setTimeout(resolve, 0));
            if (starts !== 2 || unhandled.length !== 0) throw new Error(`normal transition ready rejection leaked: ${{JSON.stringify({{ starts, unhandled }})}}`);
            console.log(JSON.stringify({{ starts, unhandled, detail: detailRoot.children.length, person: personRoot.children.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(2, result["starts"])
        self.assertEqual([], result["unhandled"])

    def test_route_commit_focuses_and_announces_once_without_scrolling(self):
        output = run_node_module(
            f'''
            const unhandled = []; process.on("unhandledRejection", (error) => unhandled.push(error.message));
            const heading = {{ tagName: "H1", textContent: "Committed heading", attributes: new Map(), focusCalls: [], setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}, focus(options) {{ this.focusCalls.push(options); }} }};
            const appView = {{ dataset: {{}}, children: [{{ id: "stable" }}], replaceChildren(...nodes) {{ this.children = nodes; }}, querySelector(selector) {{ return selector === "h1" ? heading : null; }}, setAttribute() {{}}, focus() {{ throw new Error("h1 should receive route focus"); }} }};
            let starts = 0;
            globalThis.window = {{ matchMedia: () => ({{ matches: false }}), scrollTo() {{ throw new Error("route commit must not scroll"); }} }};
            globalThis.document = {{ readyState: "loading", addEventListener() {{}}, querySelectorAll() {{ return []; }}, startViewTransition(update) {{ starts += 1; update(); return {{ updateCallbackDone: Promise.resolve(), ready: Promise.reject(new Error("not ready")), finished: Promise.resolve() }}; }} }};
            const {{ createAppRouteHandler, createExplorationRouteGate }} = await import("{module_url('js/app.js')}");
            const store = {{ state: {{ activePath: "/title/one", recommendation: {{ channels: {{}} }} }}, getState() {{ return this.state; }}, dispatch(action) {{ if (action.type === "route/changed") this.state.activePath = action.route.path; }} }};
            const renderer = (_id, options) => options.commit({{ id: "route-view" }}, {{ heading: "Committed heading" }});
            const explorationGate = createExplorationRouteGate({{ root: appView, getActivePath: () => store.state.activePath, renderTitle: renderer, renderPerson: renderer }});
            const gate = {{ invalidate() {{}}, async restore() {{}}, async render() {{}} }}; const announcements = [];
            const handler = createAppRouteHandler({{ appView, store, restoreGate: gate, explorationGate, universeGate: gate, prepare() {{}}, setNavigation() {{}}, setStatus() {{}}, announceRoute(message) {{ announcements.push(message); }} }});
            await handler({{ name: "title", path: "/title/one", params: {{ id: "one" }} }});
            await new Promise((resolve) => setTimeout(resolve, 0));
            if (heading.focusCalls.length !== 1 || heading.focusCalls[0]?.preventScroll !== true) throw new Error("route heading focus was not singular and scroll-safe");
            if (announcements.length !== 1 || !announcements[0].includes("Committed heading")) throw new Error(`route announcement mismatch: ${{announcements}}`);
            if (appView.children.length === 0 || unhandled.length !== 0 || starts !== 1) throw new Error("route recovery blanked content or leaked transition rejection");
            console.log(JSON.stringify({{ focus: heading.focusCalls.length, announcements, starts, unhandled, child: appView.children[0].id }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["focus"])
        self.assertEqual(1, len(result["announcements"]))
        self.assertEqual([], result["unhandled"])

    def test_mobile_top_bar_resets_status_flex_basis(self):
        responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        mobile = re.search(r"@media\s*\(max-width:\s*720px\)\s*\{([\s\S]*)\}\s*$", responsive)
        self.assertIsNotNone(mobile)
        status = re.search(r"\.shell-status\s*\{([^}]*)\}", mobile.group(1))
        self.assertIsNotNone(status)
        self.assertRegex(status.group(1), r"flex:\s*0\s+1\s+auto")

    def test_task8_static_shell_breakpoints_safe_area_and_long_content_contract(self):
        html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        all_css = "\n".join(path.read_text(encoding="utf-8") for path in (UI_ROOT / "styles").glob("*.css"))

        self.assertRegex(html, r'<link\s+rel="stylesheet"\s+href="/assets/v3/styles/responsive\.css"\s*/?>')
        overlay = re.search(r'<div\s+id="overlay-root"([^>]*)>', html)
        announcer = re.search(r'<div\s+id="a11y-announcer"([^>]*)>', html)
        self.assertIsNotNone(overlay)
        self.assertNotIn("aria-live", overlay.group(1))
        self.assertIsNotNone(announcer)
        self.assertIn('aria-live="polite"', announcer.group(1))
        self.assertRegex(html, r'<a[^>]+class="skip-link"[^>]+href="#app-view"')
        for breakpoint in (1200, 960, 720):
            self.assertRegex(responsive, rf"@media\s*\(max-width:\s*{breakpoint}px\)")
        mobile = re.search(r"@media\s*\(max-width:\s*720px\)\s*\{([\s\S]*)\}\s*$", responsive)
        self.assertIsNotNone(mobile)
        self.assertRegex(mobile.group(1), r"\.app-rail[\s\S]*display:\s*none")
        self.assertRegex(mobile.group(1), r"\.bottom-nav[\s\S]*display:\s*grid")
        self.assertIn("env(safe-area-inset-bottom)", mobile.group(1))
        self.assertRegex(mobile.group(1), r"\.shell-content[\s\S]*padding-bottom:\s*calc\(")
        self.assertNotRegex(all_css, r"body\s*\{[^}]*overflow-x:\s*hidden")
        required_wraps = ("command-lens", "person-sheet", "detail", "tonight", "sync", "chip", "status")
        for selector in required_wraps:
            with self.subTest(selector=selector):
                self.assertRegex(all_css, rf"[^{{}}]*{re.escape(selector)}[^{{}}]*\{{[^}}]*overflow-wrap:\s*anywhere")
        declarations = re.findall(r"(?<![-\w])(?:transition|animation)\s*:\s*([^;]+);", responsive)
        for declaration in declarations:
            for item in declaration.split(","):
                self.assertIn(item.strip().split(maxsplit=1)[0], {"transform", "opacity"})

    def test_put_v2_uses_same_origin_and_forces_schema(self):
        output = run_node_module(
            f'''
            import {{ putV2 }} from "{module_url('js/core/api.js')}";
            globalThis.location = {{ origin: "https://cinescope.test" }};
            const calls = [];
            globalThis.fetch = async (path, options) => {{ calls.push({{ path, options }}); return {{ ok: true, status: 200, json: async () => ({{ ok: true }}) }}; }};
            await putV2("/api/v2/sync/settings", {{ schema_version: 999, enabled: true }});
            const body = JSON.parse(calls[0].options.body);
            if (calls[0].options.method !== "PUT" || body.schema_version !== 2 || body.enabled !== true) throw new Error("PUT V2 contract mismatch");
            console.log(JSON.stringify({{ path: calls[0].path, method: calls[0].options.method, body }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(result["method"], "PUT")


    def test_sync_browser_authorization_panel_is_prominent_responsive_and_motion_safe(self):
        css = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.sync-browser-auth\s*\{[^}]*grid-column:\s*1\s*/\s*-1[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)\s+auto", re.DOTALL)
        self.assertRegex(css, r"\.sync-browser-auth\[hidden\]\s*\{[^}]*display:\s*none", re.DOTALL)
        self.assertRegex(css, r"\.sync-browser-auth\[data-state=\"waiting_for_login\"\]", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(max-width:\s*720px\)[\s\S]*?\.sync-browser-auth\s*\{[^}]*grid-template-columns:\s*minmax\(0,\s*1fr\)", re.DOTALL)
        self.assertRegex(css, r"@media\s*\(prefers-reduced-motion:\s*reduce\)[\s\S]*?\.sync-submit", re.DOTALL)

    def test_sync_needs_login_uses_one_click_browser_authorization_as_primary_recovery(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const posts = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              autoSettings: true,
              fetchJson: async (path) => path === "/api/v2/sync/settings"
                ? {{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "needs_cookie", last_job_id: "blocked-job", authorization: {{ state: "idle", has_session: false }} }}
                : {{ state: "idle", has_session: false }},
              postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ state: "waiting_for_login", user_id: "123456789", job_id: "blocked-job" }}; }},
              setTimer() {{ return 1; }}, clearTimer() {{}},
            }});
            await controller.ready;
            const nodes = [];
            const walk = (node) => {{ nodes.push(node); for (const child of node.children || []) walk(child); }};
            walk(root);
            const authorize = nodes.find((node) => node.tagName === "BUTTON" && node.textContent.includes("浏览器授权"));
            if (!authorize) throw new Error(`browser authorization was not the primary recovery: ${{root.textContent}}`);
            if (root.textContent.includes("从开发者工具复制 Cookie")) throw new Error("manual Cookie instructions remained primary");
            authorize.dispatchEvent({{ type: "click" }});
            await flush();
            if (posts.at(-1)?.path !== "/api/v2/sync/browser-auth") throw new Error(`wrong authorization endpoint: ${{JSON.stringify(posts)}}`);
            controller.dispose();
            console.log(JSON.stringify({{ posts, text: root.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(result["posts"][-1]["path"], "/api/v2/sync/browser-auth")


    def test_sync_browser_authorization_polls_and_adopts_the_resumed_job(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const gets = []; const posts = []; const timers = new Map(); let timerId = 0;
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              autoSettings: true,
              fetchJson: async (path) => {{
                gets.push(path);
                if (path === "/api/v2/sync/settings") return {{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "needs_cookie", last_job_id: "blocked-job", authorization: {{ state: "idle", has_session: false }} }};
                if (path === "/api/v2/sync/browser-auth") return {{ state: "queued", has_session: true, user_id: "123456789", job_id: "resumed-job", resume_of: "blocked-job", resumed: true }};
                return {{ id: "resumed-job", state: "running", user_id: "123456789" }};
              }},
              postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ state: "waiting_for_login", has_session: false, user_id: "123456789", job_id: "blocked-job" }}; }},
              setTimer(callback) {{ const id = ++timerId; timers.set(id, callback); return id; }},
              clearTimer(id) {{ timers.delete(id); }},
            }});
            await controller.ready;
            controller.elements.authorizeBrowser.dispatchEvent({{ type: "click" }});
            await flush();
            const pending = [...timers.entries()];
            if (pending.length !== 1) throw new Error(`authorization poll was not scheduled: ${{pending.length}}`);
            timers.delete(pending[0][0]); pending[0][1]();
            await flush(); await flush();
            const snapshot = controller.snapshot();
            if (!gets.includes("/api/v2/sync/browser-auth")) throw new Error(`authorization status was not polled: ${{JSON.stringify(gets)}}`);
            if (!snapshot.knownJobIds.includes("resumed-job")) throw new Error(`resumed job was not adopted: ${{JSON.stringify(snapshot)}}`);
            if (!root.textContent.includes("自动续传")) throw new Error(`resume status was not visible: ${{root.textContent}}`);
            controller.dispose();
            console.log(JSON.stringify({{ gets, posts, snapshot }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("/api/v2/sync/browser-auth", result["gets"])
        self.assertIn("resumed-job", result["snapshot"]["knownJobIds"])



    def test_sync_blocked_job_card_uses_browser_authorization_before_manual_cookie(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const posts = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              autoSettings: true,
              fetchJson: async () => ({{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "complete", authorization: {{ state: "idle", has_session: false }} }}),
              postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ state: "waiting_for_login", user_id: "123456789", job_id: "blocked-job" }}; }},
              setTimer() {{ return 1; }}, clearTimer() {{}},
            }});
            await controller.ready;
            controller.acceptJob({{ id: "blocked-job", state: "needs_cookie", user_id: "123456789", counts: {{ items: 16, collect_count: 16, wish_count: 0, pages_ok: 1, pages_failed: 1 }}, diagnostics: [{{ status: "collect", start: 15, classification: "login_required" }}] }});
            const nodes = []; const walk = (node) => {{ nodes.push(node); for (const child of node.children || []) walk(child); }}; walk(root);
            const recovery = nodes.find((node) => node.classList?.contains("sync-job__resume"));
            if (!recovery || !recovery.textContent.includes("浏览器授权")) throw new Error(`blocked job kept manual recovery primary: ${{root.textContent}}`);
            recovery.dispatchEvent({{ type: "click" }}); await flush();
            if (posts.at(-1)?.path !== "/api/v2/sync/browser-auth") throw new Error(`blocked job used wrong endpoint: ${{JSON.stringify(posts)}}`);
            controller.dispose();
            console.log(JSON.stringify({{ posts, label: recovery.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual("/api/v2/sync/browser-auth", result["posts"][-1]["path"])

    def test_sync_run_now_opens_browser_authorization_when_login_is_required(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const posts = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const controller = renderSyncPanel(new FakeElement("div"), {{
              autoSettings: true,
              fetchJson: async () => ({{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "complete", authorization: {{ state: "idle", has_session: false }} }}),
              postJson: async (path, payload) => {{
                posts.push({{ path, payload }});
                if (path === "/api/v2/sync/run-now") return {{ job_id: "blocked-job", state: "needs_cookie", user_id: "123456789", authorization_required: true }};
                if (path === "/api/v2/sync/browser-auth") return {{ state: "waiting_for_login", user_id: "123456789", job_id: "blocked-job" }};
                return {{}};
              }},
              setTimer() {{ return 1; }}, clearTimer() {{}},
            }});
            await controller.ready;
            controller.elements.runNow.dispatchEvent({{ type: "click" }});
            await flush(); await flush();
            const paths = posts.map((call) => call.path);
            if (JSON.stringify(paths) !== JSON.stringify(["/api/v2/sync/run-now", "/api/v2/sync/browser-auth"])) throw new Error(`login recovery was not automatic: ${{JSON.stringify(paths)}}`);
            controller.dispose();
            console.log(JSON.stringify({{ paths }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["/api/v2/sync/run-now", "/api/v2/sync/browser-auth"], result["paths"])

    def test_health_updates_connected_banner_from_async_auto_sync_settings(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const calls = [];
            const fetchJson = async (path) => {{
              calls.push(path);
              if (path === "/api/v2/sync/settings") return {{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "complete" }};
              if (path === "/api/v2/media/health") return {{ assets: {{}}, jobs: {{}}, delivery: "local-only" }};
              return {{}};
            }};
            const {{ renderHealth }} = await import("{module_url('js/features/health.js')}");
            const root = new FakeElement("main");
            const controller = renderHealth(root, {{
              fetchJson,
              postJson: async () => ({{}}),
              putJson: async () => ({{}}),
              autoSyncSettings: true,
              personalization: {{}},
              setTimer() {{ return 1; }},
              clearTimer() {{}},
            }});
            await controller.ready;
            const banner = collectNodes(root).find((node) => node.classList?.contains("sync-connected"));
            if (!banner || banner.dataset.state !== "connected") throw new Error("async settings did not connect the health banner");
            if (!banner.textContent.includes("已连接豆瓣") || !banner.textContent.includes("用户 123456789")) throw new Error("connected identity missing: " + banner.textContent);
            if (banner.textContent.includes("等待连接")) throw new Error("stale waiting state remained visible");
            controller.dispose();
            console.log(JSON.stringify({{ calls, banner: banner.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("/api/v2/sync/settings", result["calls"])
        self.assertIn("用户 123456789", result["banner"])

    def test_sync_auto_dashboard_uses_relative_schedule_copy(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              autoSettings: true,
              now: () => 1500000,
              fetchJson: async (path) => path === "/api/v2/sync/settings"
                ? {{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "complete", last_success_at: 1000, next_run_at: 2000 }}
                : {{}},
              postJson: async () => ({{}}),
              putJson: async () => ({{}}),
              setTimer() {{ return 1; }},
              clearTimer() {{}},
            }});
            await controller.ready;
            const meta = collectNodes(root).find((node) => node.classList?.contains("sync-automation__meta"));
            if (!meta?.textContent.includes("上次成功：约 8 分钟前")) throw new Error("relative previous time missing: " + meta?.textContent);
            if (!meta?.textContent.includes("下次检查：约 8 分钟后")) throw new Error("relative next time missing: " + meta?.textContent);
            if (meta.textContent.includes("1970") || meta.textContent.includes("/")) throw new Error("absolute local date leaked: " + meta.textContent);
            const visible = meta.textContent;
            controller.dispose();
            console.log(JSON.stringify({{ visible }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("约 8 分钟前", result["visible"])
        self.assertIn("约 8 分钟后", result["visible"])

    def test_sync_auto_dashboard_restores_only_latest_successful_job(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const gets = [];
            const fetchJson = async (path) => {{
              gets.push(path);
              if (path === "/api/v2/sync/settings") return {{
                user_id: "123456789",
                enabled: true,
                interval_minutes: 60,
                last_state: "complete",
                last_job_id: "latest-success",
              }};
              if (path === "/api/v2/sync/jobs/latest-success") return {{
                id: "latest-success",
                state: "complete",
                user_id: "123456789",
                counts: {{ items: 547, collect_count: 401, wish_count: 146, pages_ok: 28, pages_failed: 0 }},
              }};
              throw new Error("unexpected read " + path);
            }};
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              autoSettings: true,
              fetchJson,
              postJson: async () => ({{}}),
              putJson: async () => ({{}}),
              setTimer() {{ return 1; }},
              clearTimer() {{}},
            }});
            await controller.ready;
            if (JSON.stringify(gets) !== JSON.stringify(["/api/v2/sync/settings", "/api/v2/sync/jobs/latest-success"])) throw new Error("latest successful job was not restored alone: " + JSON.stringify(gets));
            if (root.textContent.includes("暂无同步记录")) throw new Error("empty history remained after restoring latest success");
            if (!root.textContent.includes("同步完成") || !root.textContent.includes("条目 547")) throw new Error("latest successful job evidence missing: " + root.textContent);
            const visible = root.textContent;
            controller.dispose();
            console.log(JSON.stringify({{ gets, visible }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["/api/v2/sync/settings", "/api/v2/sync/jobs/latest-success"], result["gets"])
        self.assertIn("条目 547", result["visible"])

    def test_sync_auto_dashboard_uses_saved_user_without_manual_profile_or_cookie(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const gets = []; const puts = []; const posts = [];
            const {{ renderSyncPanel }} = await import("{module_url('js/features/sync.js')}");
            const root = new FakeElement("div");
            const controller = renderSyncPanel(root, {{
              autoSettings: true,
              fetchJson: async (path) => {{ gets.push(path); return path === "/api/v2/sync/settings" ? {{ user_id: "123456789", enabled: true, interval_minutes: 60, last_state: "complete", last_success_at: 1000, next_run_at: 2000 }} : {{}}; }},
              putJson: async (path, payload) => {{ puts.push({{ path, payload }}); return {{ user_id: "123456789", ...payload }}; }},
              postJson: async (path, payload) => {{ posts.push({{ path, payload }}); return {{ job_id: "auto-job", state: "queued", user_id: "123456789" }}; }},
              setTimer() {{ return 1; }}, clearTimer() {{}},
            }});
            await controller.ready;
            if (controller.elements.profile.value !== "123456789") throw new Error("saved user did not hydrate recovery form");
            if (!root.textContent.includes("自动同步已开启") || !root.textContent.includes("用户 123456789")) throw new Error(`automatic connection status missing: ${{root.textContent}}`);
            controller.elements.autoEnabled.checked = false;
            controller.elements.autoEnabled.dispatchEvent({{ type: "change" }});
            await flush();
            controller.elements.runNow.dispatchEvent({{ type: "click" }});
            await flush();
            if (puts[0]?.path !== "/api/v2/sync/settings" || puts[0].payload.enabled !== false) throw new Error("settings were not saved");
            if (posts.at(-1)?.path !== "/api/v2/sync/run-now") throw new Error("run-now did not use automatic endpoint");
            const visible = root.textContent;
            controller.dispose();
            console.log(JSON.stringify({{ gets, puts, posts, visible }}));
            '''
        )
        result = json.loads(output)
        self.assertIn("/api/v2/sync/settings", result["gets"])
        self.assertIn("用户 123456789", result["visible"])


    def test_missing_people_portraits_use_compact_identity_monograms(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const title = {{
              item_key: "item:missing-people", title: "缺图人物测试", media_type: "series", year: 2021,
              poster: {{ url: "/media/poster.webp", media_status: "ready" }},
              backdrop: {{ url: "/media/backdrop.webp", media_status: "ready" }},
              item: {{ summary: "完整简介", genres: ["动画"], directors: [], casts: ["Yu-Won Pang", "Eui Jeong Kim"] }},
              people: [
                {{ id: "person:yu-won-pang", name: "Yu-Won Pang", role: "cast", portrait: {{ url: "", media_status: "missing" }} }},
                {{ id: "person:eui-jeong-kim", name: "Eui Jeong Kim", role: "cast", portrait: {{ url: "", media_status: "missing" }} }},
              ],
            }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            const root = new FakeElement("main");
            configureDetail({{
              root,
              fetchJson: async (path) => path === "/api/v2/titles/item:missing-people" ? title : {{ focus_id: "item:missing-people", nodes: [], edges: [], items: [] }},
              api: {{ postV2: () => new Promise(() => {{}}) }},
            }});
            await renderTitleDetail("item:missing-people"); await flush();
            const cards = root.querySelectorAll(".person-card");
            const monograms = cards.map((card) => card.querySelector(".person-card__monogram")?.textContent || "");
            if (cards.length !== 2 || JSON.stringify(monograms) !== JSON.stringify(["YP", "EK"])) throw new Error(`missing portraits did not retain recognizable identities: ${{JSON.stringify(monograms)}}`);
            if (cards.some((card) => card.querySelector(".media-frame"))) throw new Error("generic media fallback was still rendered inside a missing person portrait");
            if (cards.some((card) => !card.querySelector(".person-card__portrait--fallback") || !card.textContent.includes("姓名身份已保留"))) throw new Error("designed portrait fallback copy was missing");
            console.log(JSON.stringify({{ monograms, text: root.textContent }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(["YP", "EK"], result["monograms"])
        css = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")
        self.assertRegex(css, r"\.person-card__portrait--fallback\s*\{[^}]*min-height:\s*13\.5rem", re.DOTALL)
        self.assertRegex(css, r"\.person-card__monogram\s*\{[^}]*font-size:\s*clamp\(", re.DOTALL)

    def test_library_prewarms_detail_on_intent_with_bounded_deduplicated_concurrency(self):
        prelude = fake_dom_module_prelude()
        output = run_node_module(
            f'''
            {prelude}
            const detailCalls = [];
            const deferred = () => {{ let resolve; const promise = new Promise((yes) => {{ resolve = yes; }}); return {{ promise, resolve }}; }};
            const pending = new Map();
            const payload = {{
              counts: {{ all: 3, watched: 3, wish: 0, candidate: 0 }}, next_cursor: null,
              items: [1, 2, 3].map((index) => ({{
                item_key: `item:warm-${{index}}`, title: `预热作品${{index}}`, state: "watched", media_type: "电影", year: 2024,
                poster: {{ url: "", media_status: "missing" }}, item: {{ genres: ["剧情"], summary: "详情预热测试" }},
              }})),
            }};
            const fetchJson = (path) => {{
              if (!path.startsWith("/api/v2/titles/")) return Promise.resolve(payload);
              detailCalls.push(path);
              const request = deferred(); pending.set(path, request); return request.promise;
            }};
            const {{ createLibraryController }} = await import("{module_url('js/features/library.js')}");
            const root = new FakeElement("main");
            const controller = createLibraryController({{ root, fetchJson, createResizeObserver: () => null, windowTarget: null }});
            await controller.mount({{ state: "watched" }}); await flush();
            const links = root.querySelectorAll(".library-card__link");
            links[0].dispatchEvent({{ type: "pointerenter" }});
            links[0].dispatchEvent({{ type: "pointerenter" }});
            links[1].dispatchEvent({{ type: "focus" }});
            links[2].dispatchEvent({{ type: "pointerdown" }});
            await flush();
            if (detailCalls.length !== 2) throw new Error(`detail prewarm concurrency was not bounded at two: ${{JSON.stringify(detailCalls)}}`);
            if (new Set(detailCalls).size !== 2) throw new Error("duplicate intent event started duplicate detail prewarm");
            if (detailCalls.some((path) => path.includes("%3A"))) throw new Error(`item key colon was incorrectly encoded: ${{JSON.stringify(detailCalls)}}`);
            pending.get("/api/v2/titles/item:warm-1").resolve({{ item_key: "item:warm-1" }}); await flush();
            if (detailCalls.length !== 3 || detailCalls[2] !== "/api/v2/titles/item:warm-3") throw new Error(`queued detail did not start when capacity opened: ${{JSON.stringify(detailCalls)}}`);
            pending.get("/api/v2/titles/item:warm-2").resolve({{ item_key: "item:warm-2" }});
            pending.get("/api/v2/titles/item:warm-3").resolve({{ item_key: "item:warm-3" }});
            await flush(); controller.dispose();
            console.log(JSON.stringify({{ detailCalls }}));
            '''
        )
        self.assertEqual(
            ["/api/v2/titles/item:warm-1", "/api/v2/titles/item:warm-2", "/api/v2/titles/item:warm-3"],
            json.loads(output)["detailCalls"],
        )


    def test_carousel_hides_native_image_until_synchronous_load_completes(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const images = [];
            class ImmediateImage extends FakeElement {{
              constructor() {{ super("img"); this.naturalWidth = 1280; images.push(this); }}
              set src(value) {{
                this._src = String(value || "");
                this.hiddenWhenAssigned = this.hidden;
                if (this._src) this.dispatchEvent({{ type: "load" }});
              }}
              get src() {{ return this._src || ""; }}
            }}
            document.createElement = (tagName) => String(tagName).toLowerCase() === "img"
              ? new ImmediateImage()
              : new FakeElement(tagName);
            const {{ renderCinemaCarousel }} = await import("{module_url('js/components/cinema-carousel.js')}");
            const carousel = renderCinemaCarousel({{
              slides: [{{ id: "one", title: "Visual lifecycle", media: {{ url: "/media/still.webp", kind: "backdrop", status: "ready" }} }}],
            }});
            const image = images.find((candidate) => candidate.classList.contains("cinema-carousel__image"));
            const frame = image?.parentNode;
            if (!image) throw new Error("carousel image missing");
            if (image.hiddenWhenAssigned !== true) throw new Error("carousel exposed the native image before src assignment");
            if (image.hidden) throw new Error("carousel image stayed hidden after a successful load");
            if (frame?.dataset?.mediaState !== "ready") throw new Error("carousel frame did not reach ready state");
            console.log(JSON.stringify({{ hiddenWhenAssigned: image.hiddenWhenAssigned, hidden: image.hidden, state: frame.dataset.mediaState }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["hiddenWhenAssigned"])
        self.assertFalse(result["hidden"])
        self.assertEqual("ready", result["state"])

    def test_detail_backdrop_hides_native_image_until_synchronous_load_completes(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const images = [];
            class ImmediateImage extends FakeElement {{
              constructor() {{ super("img"); this.naturalWidth = 1280; images.push(this); }}
              set src(value) {{
                this._src = String(value || "");
                this.hiddenWhenAssigned = this.hidden;
                if (this._src) this.dispatchEvent({{ type: "load" }});
              }}
              get src() {{ return this._src || ""; }}
            }}
            document.createElement = (tagName) => String(tagName).toLowerCase() === "img"
              ? new ImmediateImage()
              : new FakeElement(tagName);
            const root = new FakeElement("main");
            const title = {{
              item_key: "douban:sync-still", title: "Synchronous still", media_type: "电影", year: 2025, state: "candidate",
              poster: {{ url: "/media/poster.webp", media_status: "ready" }},
              backdrop: {{ url: "", media_status: "missing" }},
              stills: [{{ id: "still-0", url: "/media/still.webp", media_status: "ready" }}],
              item: {{ summary: "这是一段完整中文简介。", genres: ["剧情"], directors: ["导演甲"], casts: ["演员乙"], raw: {{}} }},
              people: [],
            }};
            const universe = {{ focus_id: "douban:sync-still", nodes: [], edges: [] }};
            const {{ configureDetail, renderTitleDetail }} = await import("{module_url('js/features/detail.js')}");
            configureDetail({{
              root,
              fetchJson: async (path) => path.startsWith("/api/v2/titles/") ? title : universe,
              api: {{ postV2: async () => ({{ state: "failed" }}), getV2: async () => ({{ state: "failed" }}) }},
            }});
            await renderTitleDetail("douban:sync-still"); await flush();
            const image = images.find((candidate) => candidate.classList.contains("detail-backdrop__still"));
            const backdrop = image?.parentNode;
            if (!image) throw new Error("detail still missing");
            if (image.hiddenWhenAssigned !== true) throw new Error("detail exposed the native image before src assignment");
            if (image.hidden) throw new Error("detail still stayed hidden after a successful load");
            if (backdrop?.dataset?.mediaState !== "ready") throw new Error("detail backdrop did not reach ready state");
            console.log(JSON.stringify({{ hiddenWhenAssigned: image.hiddenWhenAssigned, hidden: image.hidden, state: backdrop.dataset.mediaState }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["hiddenWhenAssigned"])
        self.assertFalse(result["hidden"])
        self.assertEqual("ready", result["state"])

    def test_lightbox_hides_native_image_until_synchronous_load_completes(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const images = [];
            class ImmediateImage extends FakeElement {{
              constructor() {{ super("img"); this.naturalWidth = 1280; images.push(this); }}
              set src(value) {{
                this._src = String(value || "");
                this.hiddenWhenAssigned = this.hidden;
                if (this._src) this.dispatchEvent({{ type: "load" }});
              }}
              get src() {{ return this._src || ""; }}
            }}
            document.createElement = (tagName) => String(tagName).toLowerCase() === "img"
              ? new ImmediateImage()
              : new FakeElement(tagName);
            document.body = new FakeElement("body");
            document.body.style = {{ overflow: "" }};
            document.removeEventListener = () => {{}};
            const {{ openMediaLightbox }} = await import("{module_url('js/components/media-lightbox.js')}");
            const lightbox = openMediaLightbox({{
              items: [{{ url: "/media/still.webp", label: "Still one" }}],
              title: "Visual lifecycle",
              documentTarget: document,
              windowTarget: window,
            }});
            const image = images.find((candidate) => candidate.classList.contains("media-lightbox__image"));
            const mount = image?.parentNode;
            if (!image || !lightbox) throw new Error("lightbox image missing");
            if (image.hiddenWhenAssigned !== true) throw new Error("lightbox exposed the native image before src assignment");
            if (image.hidden) throw new Error("lightbox image stayed hidden after a successful load");
            if (mount?.dataset?.state !== "ready") throw new Error("lightbox did not reach ready state");
            console.log(JSON.stringify({{ hiddenWhenAssigned: image.hiddenWhenAssigned, hidden: image.hidden, state: mount.dataset.state }}));
            '''
        )
        result = json.loads(output)
        self.assertTrue(result["hiddenWhenAssigned"])
        self.assertFalse(result["hidden"])
        self.assertEqual("ready", result["state"])

    def test_native_broken_image_surfaces_have_explicit_hidden_guards(self):
        css = "\n".join(
            (UI_ROOT / "styles" / name).read_text(encoding="utf-8")
            for name in ("components.css", "detail.css")
        )
        for selector in (
            ".cinema-carousel__image[hidden]",
            ".detail-backdrop__still[hidden]",
            ".media-lightbox__image[hidden]",
        ):
            self.assertRegex(css, re.escape(selector) + r"\s*\{[^}]*display:\s*none", selector)


    def test_detail_related_cards_keep_a_readable_desktop_body_in_a_horizontal_rail(self):
        css = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")

        related_item = re.search(r"\.detail-related-works__item\s*\{(?P<body>[^}]*)\}", css, re.DOTALL)
        self.assertIsNotNone(related_item, "detail relations need a dedicated card-width rule")
        self.assertRegex(
            related_item.group("body"),
            r"flex:\s*0\s+0\s+clamp\(22rem,\s*28vw,\s*26rem\)",
            "desktop relation cards must not be compressed into poster-only slivers",
        )
        self.assertRegex(related_item.group("body"), r"scroll-snap-align:\s*start")

        related_link = re.search(
            r"\.detail-related-works\s+\.title-card__link\s*\{(?P<body>[^}]*)\}",
            css,
            re.DOTALL,
        )
        self.assertIsNotNone(related_link, "relation cards need their own poster-to-copy proportion")
        self.assertRegex(
            related_link.group("body"),
            r"grid-template-columns:\s*clamp\(7\.8rem,\s*10vw,\s*9rem\)\s+minmax\(11rem,\s*1fr\)",
            "relation copy needs a readable minimum column beside the poster",
        )

if __name__ == "__main__":
    unittest.main()
