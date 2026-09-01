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


class UnifiedUiContractTests(unittest.TestCase):
    def setUp(self) -> None:
        self.html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
        self.shell = (UI_ROOT / "styles" / "shell.css").read_text(encoding="utf-8")
        self.tokens = (UI_ROOT / "styles" / "tokens.css").read_text(encoding="utf-8")
        self.tonight = (UI_ROOT / "styles" / "tonight.css").read_text(encoding="utf-8")
        self.spaces = (UI_ROOT / "styles" / "spaces.css").read_text(encoding="utf-8")
        self.responsive = (UI_ROOT / "styles" / "responsive.css").read_text(encoding="utf-8")
        self.detail = (UI_ROOT / "styles" / "detail.css").read_text(encoding="utf-8")

    def test_shell_uses_cinema_navigation_visual_language(self):
        self.assertRegex(self.html, r'<link[^>]+rel="icon"[^>]+favicon\.svg')
        self.assertGreaterEqual(len(re.findall(r'<svg[^>]+class="rail-symbol"', self.html)), 4)
        self.assertNotRegex(self.html, r'<span[^>]+class="rail-symbol"[^>]*>[^<]+</span>')
        self.assertRegex(self.shell, r'--rail-width|\.app-rail')
        self.assertRegex(self.tokens + self.shell, r'--rail-width:\s*(?:10[4-9]|11[0-9]|1[2-9][0-9])px')
        self.assertRegex(self.shell, r'\.rail-label\s*\{[^}]*font-size:\s*(?:1(?:\.0|\.1|\.2)|[2-9])rem', re.DOTALL)
        self.assertRegex(self.shell, r'\.app-rail a\[aria-current="page"\]\s*\{[^}]*background:', re.DOTALL)
        self.assertIn(".rail-symbol", self.shell)

    def test_primary_search_poster_and_hero_actions_are_visually_explicit(self):
        self.assertRegex(
            self.html,
            r'id="command-lens-trigger"[^>]*>[\s\S]*?<span[^>]+class="command-lens-trigger__label"[^>]*>在线搜索',
        )
        self.assertRegex(
            self.shell,
            r'\.top-bar \.command-lens-trigger\s*\{[^}]*display:\s*inline-flex[^}]*min-inline-size:',
            re.DOTALL,
        )
        self.assertRegex(
            self.spaces,
            r'\.library-card__poster-shell\s*\{[^}]*aspect-ratio:\s*2\s*/\s*3',
            re.DOTALL,
        )
        self.assertRegex(
            self.spaces,
            r'\.library-card__poster-shell \.media-frame__image\s*\{[^}]*object-fit:\s*contain',
            re.DOTALL,
        )
        self.assertRegex(
            self.tonight,
            r'\.tonight-button\s*\{[^}]*display:\s*inline-flex[^}]*min-inline-size:\s*8\.5rem[^}]*min-block-size:',
            re.DOTALL,
        )

    def test_cinema_carousel_component_has_accessible_interaction_contract(self):
        source_path = UI_ROOT / "js" / "components" / "cinema-carousel.js"
        self.assertTrue(source_path.exists())
        source = source_path.read_text(encoding="utf-8")
        for token in (
            'role", "region"',
            'aria-roledescription',
            'scrollIntoView',
            'ArrowLeft',
            'ArrowRight',
            'pointerdown',
            'pointermove',
            'wheel',
            'scroll-snap',
            'prefers-reduced-motion',
        ):
            with self.subTest(token=token):
                self.assertIn(token, source)
        self.assertNotIn("setInterval", source)

    def test_cinema_carousel_can_center_active_item_and_move_with_keyboard(self):
        output = run_node(
            r'''
            class ClassList { constructor(node) { this.node = node; this.values = new Set(); } add(...v) { v.forEach((x) => this.values.add(x)); } remove(...v) { v.forEach((x) => this.values.delete(x)); } }
            class Node {
              constructor(tag) { this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.attributes = {}; this.dataset = {}; this.classList = new ClassList(this); this.style = {}; this.textContent = ""; this.scrollCalls = 0; this.parentNode = null; this.clientWidth = 800; this.scrollLeft = 0; this.scrollWidth = 2400; }
              append(...nodes) { nodes.forEach((node) => { if (node) { this.children.push(node); node.parentNode = this; } }); }
              appendChild(node) { this.append(node); return node; }
              replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
              setAttribute(name, value) { this.attributes[name] = String(value); }
              getAttribute(name) { return this.attributes[name] ?? null; }
              removeAttribute(name) { delete this.attributes[name]; }
              addEventListener(type, cb) { (this.listeners[type] ||= []).push(cb); }
              dispatch(type, init = {}) { for (const cb of this.listeners[type] || []) cb({ type, target: this, preventDefault() {}, ...init }); }
              scrollIntoView() { this.scrollCalls += 1; }
              matches(selector) {
                if (selector === "[data-carousel-slide]") return Boolean(this.dataset.carouselSlide);
                if (selector === "[data-carousel-track]") return Boolean(this.dataset.carouselTrack);
                if (selector === "[data-carousel-next]") return Boolean(this.dataset.carouselNext);
                if (selector === "[data-carousel-previous]") return Boolean(this.dataset.carouselPrevious);
                return false;
              }
              querySelectorAll(selector) {
                const found = [];
                const visit = (node) => { if (node.matches?.(selector)) found.push(node); node.children?.forEach(visit); };
                this.children.forEach(visit);
                return found;
              }
              querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
            }
            globalThis.document = { createElement: (tag) => new Node(tag) };
            const { renderCinemaCarousel } = await import("./src/douban_recommender/ui/js/components/cinema-carousel.js");
            const root = renderCinemaCarousel({
              title: "今晚精选",
              slides: [
                { id: "a", title: "Alpha", media: { localUrl: "/media/a.webp", kind: "backdrop", status: "ready" } },
                { id: "b", title: "Beta", media: { localUrl: "/media/b.webp", kind: "backdrop", status: "ready" } },
                { id: "c", title: "Gamma", media: { localUrl: "/media/c.webp", kind: "backdrop", status: "ready" } },
              ],
            });
            const rail = root.querySelector("[data-carousel-track]");
            const next = root.querySelector("[data-carousel-next]");
            const previous = root.querySelector("[data-carousel-previous]");
            root.dispatch("keydown", { key: "ArrowRight" });
            const selectedAfterKey = root.dataset.index;
            next.dispatch("click");
            const selectedAfterNext = root.dataset.index;
            previous.dispatch("click");
            const selectedAfterPrevious = root.dataset.index;
            console.log(JSON.stringify({
              role: root.getAttribute("role"),
              description: root.getAttribute("aria-roledescription"),
              selectedAfterKey, selectedAfterNext, selectedAfterPrevious,
              centered: rail.children.some((node) => node.scrollCalls > 0),
            }));
            ''',
        )
        self.assertEqual(output["role"], "region")
        self.assertEqual(output["description"], "carousel")
        self.assertEqual(output["selectedAfterKey"], "1")
        self.assertEqual(output["selectedAfterNext"], "2")
        self.assertEqual(output["selectedAfterPrevious"], "1")
        self.assertTrue(output["centered"])

    def test_cinema_carousel_preserves_slide_clicks_and_only_captures_real_drags(self):
        output = run_node(
            r'''
            class ClassList { constructor() { this.values = new Set(); } add(...v) { v.forEach((x) => this.values.add(x)); } remove(...v) { v.forEach((x) => this.values.delete(x)); } }
            class Node {
              constructor(tag) {
                this.tagName = tag.toUpperCase(); this.children = []; this.listeners = {}; this.attributes = {};
                this.dataset = {}; this.classList = new ClassList(); this.style = {}; this.textContent = "";
                this.parentNode = null; this.captures = []; this.releases = [];
              }
              append(...nodes) { nodes.forEach((node) => { if (node) { this.children.push(node); node.parentNode = this; } }); }
              replaceChildren(...nodes) { this.children = []; this.append(...nodes); }
              setAttribute(name, value) { this.attributes[name] = String(value); }
              getAttribute(name) { return this.attributes[name] ?? null; }
              addEventListener(type, cb) { (this.listeners[type] ||= []).push(cb); }
              dispatch(type, init = {}) {
                const event = { type, target: this, preventDefault() {}, stopPropagation() {}, ...init };
                for (const cb of this.listeners[type] || []) cb(event);
              }
              setPointerCapture(pointerId) { this.captures.push(pointerId); }
              releasePointerCapture(pointerId) { this.releases.push(pointerId); }
              hasPointerCapture(pointerId) { return this.captures.includes(pointerId) && !this.releases.includes(pointerId); }
              scrollIntoView() {}
              matches(selector) {
                if (selector === "[data-carousel-slide]") return Boolean(this.dataset.carouselSlide);
                if (selector === "[data-carousel-track]") return Boolean(this.dataset.carouselTrack);
                return false;
              }
              querySelectorAll(selector) {
                const found = [];
                const visit = (node) => { if (node.matches?.(selector)) found.push(node); node.children?.forEach(visit); };
                this.children.forEach(visit);
                return found;
              }
              querySelector(selector) { return this.querySelectorAll(selector)[0] || null; }
            }
            globalThis.document = { createElement: (tag) => new Node(tag) };
            const { renderCinemaCarousel } = await import("./src/douban_recommender/ui/js/components/cinema-carousel.js");
            const root = renderCinemaCarousel({
              slides: [
                { id: "a", title: "Alpha", media: { localUrl: "/media/a.webp" } },
                { id: "b", title: "Beta", media: { localUrl: "/media/b.webp" } },
              ],
            });
            const rail = root.querySelector("[data-carousel-track]");
            const first = rail.children[0];
            rail.dispatch("pointerdown", { target: first, pointerId: 7, clientX: 200, clientY: 30 });
            const capturesAfterDown = rail.captures.length;
            rail.dispatch("pointermove", { target: first, pointerId: 7, clientX: 190, clientY: 30 });
            const capturesAfterSmallMove = rail.captures.length;
            rail.dispatch("pointermove", { target: first, pointerId: 7, clientX: 140, clientY: 31 });
            const capturesAfterDrag = rail.captures.length;
            rail.dispatch("pointerup", { target: rail, pointerId: 7, clientX: 140, clientY: 31 });
            const selectedAfterDrag = root.dataset.index;
            rail.dispatch("click", { target: rail });
            first.dispatch("click");
            console.log(JSON.stringify({
              capturesAfterDown, capturesAfterSmallMove, capturesAfterDrag,
              releases: rail.releases, selectedAfterDrag, selectedAfterNextClick: root.dataset.index,
            }));
            ''',
        )
        self.assertEqual(output["capturesAfterDown"], 0)
        self.assertEqual(output["capturesAfterSmallMove"], 0)
        self.assertEqual(output["capturesAfterDrag"], 1)
        self.assertEqual(output["releases"], [7])
        self.assertEqual(output["selectedAfterDrag"], "1")
        self.assertEqual(output["selectedAfterNextClick"], "0")

    def test_library_uses_balanced_columns_and_large_scrollable_stills(self):
        source = (UI_ROOT / "js" / "features" / "library.js").read_text(encoding="utf-8")
        self.assertRegex(source, r'function columnsFor\([^)]*\)[\s\S]*?return 3;[\s\S]*?return 2;[\s\S]*?return 1;')
        self.assertNotRegex(source, r'visualCandidates\(item\)\.slice\(0,\s*1\)')
        self.assertIn("评分样本不足", source)
        self.assertRegex(self.spaces, r'\.library-row\s*\{[^}]*height:\s*var\(--library-row-height', re.DOTALL)
        self.assertRegex(self.spaces, r'\.library-card\s*\{[^}]*height:\s*calc\(', re.DOTALL)
        self.assertRegex(self.spaces, r'\.library-card__visuals-rail\s*\{[^}]*overflow-x:\s*auto', re.DOTALL)
        self.assertRegex(self.spaces, r'\.library-card__still-frame\s*\{[^}]*aspect-ratio:\s*var\(--still-aspect,\s*16\s*/\s*9\)', re.DOTALL)
        self.assertRegex(self.spaces, r'\.library-card__visuals-rail\s*\{[^}]*scroll-snap-type:', re.DOTALL)
        self.assertIn("pointerdown", source)
        self.assertIn("scrollLeft", source)

    def test_detail_gallery_component_has_keyboard_and_touch_controls(self):
        source_path = UI_ROOT / "js" / "components" / "media-gallery.js"
        self.assertTrue(source_path.exists())
        source = source_path.read_text(encoding="utf-8")
        for token in ("renderMediaGallery", "ArrowLeft", "ArrowRight", "touchstart", "touchend", "media-gallery__filmstrip"):
            with self.subTest(token=token):
                self.assertIn(token, source)

    def test_proxy_backed_media_is_treated_as_trusted_same_origin_content(self):
        source = (UI_ROOT / "js" / "core" / "media.js").read_text(encoding="utf-8")
        self.assertIn('url.pathname === IMAGE_PROXY_PATH', source)

    def test_detail_gallery_has_wide_stage_and_thumbnail_rail(self):
        for token in (".media-gallery__stage", ".media-gallery__filmstrip", ".media-gallery__arrow", "aspect-ratio: 16 / 9"):
            self.assertIn(token, self.detail)
        self.assertRegex(self.detail, r'\.media-gallery__filmstrip\s*\{[^}]*overflow-x:\s*auto', re.DOTALL)
        self.assertRegex(self.detail, r'\.media-gallery__stage\s*\{[^}]*aspect-ratio:\s*16\s*/\s*9', re.DOTALL)

    def test_reduced_motion_and_mobile_navigation_remain_explicit(self):
        self.assertIn("@media (prefers-reduced-motion: reduce)", self.responsive + self.tonight + self.spaces)
        self.assertRegex(self.responsive, r'@media\s*\(max-width:\s*720px\)[\s\S]*?\.app-rail[\s\S]*?display:\s*none', re.DOTALL)
        self.assertRegex(self.responsive, r'@media\s*\(max-width:\s*720px\)[\s\S]*?\.bottom-nav[\s\S]*?display:\s*grid', re.DOTALL)


if __name__ == "__main__":
    unittest.main()
