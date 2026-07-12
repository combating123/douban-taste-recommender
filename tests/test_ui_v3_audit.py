import json
import subprocess
import textwrap
import threading
import time
import unittest
from contextlib import contextmanager
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from urllib.parse import unquote, urlsplit

from tests.test_ui_v3_contract import fake_dom_module_prelude


ROOT = Path(__file__).resolve().parents[1]
UI_ROOT = ROOT / "src" / "douban_recommender" / "ui"


def module_url(relative_path):
    return (UI_ROOT / relative_path).resolve().as_uri()


def ui_text(relative_path):
    return (UI_ROOT / relative_path).read_text(encoding="utf-8")


def run_node_module(script, timeout=15):
    result = subprocess.run(
        ["node", "--input-type=module", "--eval", textwrap.dedent(script)],
        cwd=ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        timeout=timeout,
        check=False,
    )
    if result.returncode:
        raise AssertionError(
            "Node module test failed:\n"
            f"stdout:\n{result.stdout}\n"
            f"stderr:\n{result.stderr}"
        )
    return result.stdout


@contextmanager
def http_fixture(responder):
    records = []
    lock = threading.Lock()

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, _format, *_args):
            return

        def _handle(self):
            length = int(self.headers.get("Content-Length") or 0)
            raw_body = self.rfile.read(length) if length else b""
            try:
                body = json.loads(raw_body.decode("utf-8")) if raw_body else None
            except json.JSONDecodeError:
                body = None
            record = {
                "method": self.command,
                "path": self.path,
                "body": body,
            }
            with lock:
                records.append(record)
                index = len(records)
            status, payload, delay = responder(record, index)
            if delay:
                time.sleep(delay)
            encoded = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            try:
                self.send_response(status)
                self.send_header("Content-Type", "application/json; charset=utf-8")
                self.send_header("Content-Length", str(len(encoded)))
                self.end_headers()
                self.wfile.write(encoded)
            except OSError:
                pass

        do_GET = _handle
        do_POST = _handle

    server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    try:
        yield f"http://127.0.0.1:{server.server_port}", records
    finally:
        server.shutdown()
        server.server_close()
        thread.join(timeout=2)


def browser_prelude(origin):
    return f'''
        globalThis.location = new URL("{origin}/tonight?private=query#private-hash");
        globalThis.window = {{
          location: globalThis.location,
          addEventListener() {{}}, removeEventListener() {{}},
          matchMedia() {{ return {{ matches: false }}; }},
        }};
        globalThis.document = {{
          readyState: "loading", activeElement: null,
          addEventListener() {{}}, removeEventListener() {{}},
          querySelectorAll() {{ return []; }}, querySelector() {{ return null; }},
        }};
        const nativeFetch = globalThis.fetch;
        globalThis.fetch = (path, options) => nativeFetch(new URL(path, globalThis.location.origin), options);
    '''


class UiV3AuditTests(unittest.TestCase):
    def test_audit_exposes_visual_viewport_bottom_nav_and_clipped_essential_rects(self):
        output = run_node_module(
            f'''
            function node(tagName, rect, options = {{}}) {{
              return {{
                tagName: tagName.toUpperCase(), hidden: false, parentElement: options.parentElement || null,
                clientWidth: options.clientWidth ?? rect.width, clientHeight: options.clientHeight ?? rect.height,
                scrollWidth: options.scrollWidth ?? rect.width, scrollHeight: options.scrollHeight ?? rect.height,
                classList: {{ contains(name) {{ return (options.classes || []).includes(name); }} }},
                getClientRects() {{ return [rect]; }}, getBoundingClientRect() {{ return rect; }},
                getAttribute() {{ return null; }}, hasAttribute() {{ return false; }},
              }};
            }}
            const inside = node("h1", {{ left: 16, right: 374, top: 20, bottom: 72, width: 358, height: 52 }});
            const clipped = node("p", {{ left: 16, right: 410, top: 80, bottom: 120, width: 394, height: 40 }});
            const rail = node("div", {{ left: 0, right: 390, top: 140, bottom: 300, width: 390, height: 160 }}, {{ classes: ["title-shelf__rail"] }});
            const intentional = node("h1", {{ left: 380, right: 700, top: 150, bottom: 210, width: 320, height: 60 }}, {{ parentElement: rail }});
            const bottomNav = node("nav", {{ left: 0, right: 390, top: 776, bottom: 844, width: 390, height: 68 }});
            const main = {{ textContent: "ready" }};
            globalThis.document = {{
              images: [], activeElement: null,
              documentElement: {{ clientWidth: 390, clientHeight: 844, scrollWidth: 390, scrollHeight: 1600 }},
              querySelector(selector) {{ if (selector === "#app-view") return main; if (selector === "#bottom-nav") return bottomNav; return null; }},
              querySelectorAll(selector) {{
                if (selector === "body *") return [inside, clipped, rail, intentional, bottomNav];
                if (selector.includes(".tonight-intro__title")) return [inside, clipped, intentional];
                return [];
              }},
            }};
            globalThis.location = new URL("http://localhost/health");
            globalThis.window = {{
              location: globalThis.location, innerWidth: 390, innerHeight: 844, devicePixelRatio: 1.5,
              visualViewport: {{ width: 390, height: 844, scale: 1, offsetLeft: 0, offsetTop: 0 }},
              matchMedia() {{ return {{ matches: false }}; }},
            }};
            globalThis.getComputedStyle = (target) => ({{ display: target === bottomNav ? "grid" : "block", visibility: "visible", overflowX: target === rail ? "auto" : "visible" }});
            const {{ runAudit }} = await import("{module_url('js/core/audit.js')}");
            console.log(JSON.stringify(runAudit()));
            '''
        )
        result = json.loads(output)
        self.assertEqual({"width": 390, "height": 844, "scale": 1, "offsetLeft": 0, "offsetTop": 0}, result["visualViewport"])
        self.assertEqual(1.5, result["devicePixelRatio"])
        self.assertEqual([390, 844], result["documentViewport"]["client"])
        self.assertEqual([390, 1600], result["documentViewport"]["scroll"])
        self.assertTrue(result["bottomNav"]["visible"])
        self.assertTrue(result["bottomNav"]["withinViewport"])
        self.assertEqual(844, result["bottomNav"]["rect"]["bottom"])
        self.assertEqual(3, len(result["essentialRects"]))
        self.assertEqual(1, len(result["clippedEssentials"]))
        self.assertEqual(410, result["clippedEssentials"][0]["rect"]["right"])

    def test_audit_keeps_visually_rendered_aria_hidden_images_in_scope(self):
        output = run_node_module(
            f'''
            const image = {{
              tagName: "IMG", hidden: false, complete: true, naturalWidth: 0,
              src: "https://cdn.example/media/private-aria-hidden.png?secret=query#hash",
              clientWidth: 120, clientHeight: 180, scrollWidth: 120, scrollHeight: 180,
              parentElement: null, classList: {{ contains() {{ return false; }} }},
              closest(selector) {{ return selector === '[aria-hidden="true"]' ? this : null; }},
              getClientRects() {{ return [{{ width: 120, height: 180 }}]; }},
            }};
            const overflow = {{
              tagName: "DIV", id: "private-aria-overflow", hidden: false,
              clientWidth: 100, clientHeight: 40, scrollWidth: 240, scrollHeight: 40,
              parentElement: null, classList: {{ contains() {{ return false; }} }},
              closest(selector) {{ return selector === '[aria-hidden="true"]' ? this : null; }},
              getClientRects() {{ return [{{ width: 100, height: 40 }}]; }},
            }};
            const main = {{ textContent: "ready" }};
            globalThis.document = {{
              images: [image], activeElement: null,
              querySelector(selector) {{ return selector === "#app-view" ? main : null; }},
              querySelectorAll(selector) {{ return selector === "body *" ? [overflow] : []; }},
            }};
            globalThis.location = new URL("http://localhost/tonight");
            globalThis.window = {{ location: globalThis.location, innerWidth: 390, innerHeight: 844, matchMedia() {{ return {{ matches: false }}; }} }};
            globalThis.getComputedStyle = () => ({{ display: "block", visibility: "visible", overflowX: "visible" }});
            const {{ runAudit }} = await import("{module_url('js/core/audit.js')}");
            console.log(JSON.stringify(runAudit()));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, len(result["brokenImages"]))
        self.assertEqual(1, len(result["externalImages"]))
        self.assertEqual(1, len(result["overflowNodes"]))
        self.assertNotIn("private-aria-hidden", json.dumps(result))
        self.assertNotIn("private-aria-overflow", json.dumps(result))

    def test_audit_checks_responsive_image_current_src_without_leaking_it(self):
        output = run_node_module(
            f'''
            const image = {{
              tagName: "IMG", hidden: false, complete: true, naturalWidth: 640,
              src: "http://localhost/media/fallback.png",
              currentSrc: "https://cdn.example/media/private-current.png?secret=query#hash",
              clientWidth: 120, clientHeight: 180, scrollWidth: 120, scrollHeight: 180,
              parentElement: null, classList: {{ contains() {{ return false; }} }},
              closest() {{ return null; }}, getClientRects() {{ return [{{ width: 120, height: 180 }}]; }},
            }};
            globalThis.document = {{
              images: [image], activeElement: null,
              querySelector() {{ return {{ textContent: "ready" }}; }}, querySelectorAll() {{ return []; }},
            }};
            globalThis.location = new URL("http://localhost/tonight");
            globalThis.window = {{ location: globalThis.location, innerWidth: 1280, innerHeight: 800, matchMedia() {{ return {{ matches: false }}; }} }};
            globalThis.getComputedStyle = () => ({{ display: "block", visibility: "visible", overflowX: "visible" }});
            const {{ runAudit }} = await import("{module_url('js/core/audit.js')}");
            console.log(JSON.stringify(runAudit()));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, len(result["externalImages"]))
        serialized = json.dumps(result)
        self.assertNotIn("private-current", serialized)
        self.assertNotIn("cdn.example", serialized)

    def test_audit_uses_real_tab_index_and_excludes_inert_disabled_or_hidden_targets(self):
        output = run_node_module(
            f'''
            const visibleStyle = {{ display: "block", visibility: "visible", overflowX: "visible" }};
            function target(tagName, options = {{}}) {{
              const node = {{
                tagName: tagName.toUpperCase(), tabIndex: options.tabIndex ?? 0,
                disabled: Boolean(options.disabled), hidden: Boolean(options.hidden), inert: Boolean(options.inert),
                type: options.type || "", parentElement: null, children: [], attributes: new Map(),
                getAttribute(name) {{ return this.attributes.get(name) ?? null; }},
                hasAttribute(name) {{ return this.attributes.has(name); }},
                closest(selector) {{
                  if (selector === "[hidden]" && this.hidden) return this;
                  if (selector === "[inert]" && this.inert) return this;
                  return this.parentElement?.closest?.(selector) || null;
                }},
                getClientRects() {{ return this.hidden ? [] : [{{ width: 20, height: 20 }}]; }},
              }};
              if (options.contenteditable) node.attributes.set("contenteditable", "true");
              if (options.disabled) node.attributes.set("disabled", "");
              return node;
            }}
            function auditFor(focusTarget, activeElement = focusTarget) {{
              const modal = {{
                tagName: "SECTION", hidden: false, tabIndex: -1, parentElement: null, children: [focusTarget],
                getAttribute(name) {{ return name === "aria-modal" ? "true" : (name === "role" ? "dialog" : null); }},
                hasAttribute() {{ return false; }}, closest() {{ return null; }}, matches() {{ return false; }},
                getClientRects() {{ return [{{ width: 320, height: 240 }}]; }},
                querySelectorAll() {{ return this.children; }},
                contains(node) {{ return node === this || node === focusTarget; }},
              }};
              focusTarget.parentElement = modal;
              globalThis.document = {{
                images: [], activeElement,
                querySelector() {{ return {{ textContent: "ready" }}; }},
                querySelectorAll(selector) {{ return selector.includes("dialog") ? [modal] : []; }},
              }};
              return runAudit();
            }}
            globalThis.location = new URL("http://localhost/tonight");
            globalThis.window = {{ location: globalThis.location, innerWidth: 1024, innerHeight: 768, matchMedia() {{ return {{ matches: false }}; }} }};
            globalThis.getComputedStyle = () => visibleStyle;
            const {{ runAudit }} = await import("{module_url('js/core/audit.js')}");
            const valid = [
              auditFor(target("div", {{ contenteditable: true }})),
              auditFor(target("summary")),
              auditFor(target("iframe")),
              auditFor(target("audio")),
            ];
            const inert = auditFor(target("div", {{ inert: true }}));
            const outsideTarget = target("summary");
            const outside = auditFor(outsideTarget, {{ tagName: "BUTTON", parentElement: null }});
            const disabled = auditFor(target("button", {{ disabled: true }}));
            const hidden = auditFor(target("input", {{ hidden: true }}));
            console.log(JSON.stringify({{
              valid: valid.map((audit) => audit.focusFailures.length),
              inert: inert.focusFailures.length,
              outside: outside.focusFailures.length,
              disabled: disabled.focusFailures.length,
              hidden: hidden.focusFailures.length,
            }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual([0, 0, 0, 0], result["valid"])
        self.assertEqual(1, result["inert"])
        self.assertEqual(1, result["outside"])
        self.assertEqual(1, result["disabled"])
        self.assertEqual(1, result["hidden"])

    def test_audit_focus_eligibility_excludes_aria_hidden_and_disabled_fieldset_subtrees(self):
        output = run_node_module(
            f'''
            function element(tagName, options = {{}}) {{
              const attributes = new Map(Object.entries(options.attributes || {{}}));
              return {{
                tagName: tagName.toUpperCase(), tabIndex: options.tabIndex ?? -1,
                disabled: Boolean(options.disabled), hidden: Boolean(options.hidden), inert: Boolean(options.inert),
                parentElement: null, children: [], attributes,
                append(...nodes) {{ for (const node of nodes) {{ this.children.push(node); node.parentElement = this; }} }},
                getAttribute(name) {{ return attributes.get(name) ?? null; }},
                hasAttribute(name) {{ return attributes.has(name); }},
                getClientRects() {{ return this.hidden ? [] : [{{ width: 20, height: 20 }}]; }},
              }};
            }}
            function modalAudit(root, focusTarget, image = null) {{
              const modal = element("section", {{ attributes: {{ role: "dialog", "aria-modal": "true" }} }});
              modal.append(root);
              const descendants = [];
              const visit = (node) => {{ for (const child of node.children || []) {{ descendants.push(child); visit(child); }} }};
              visit(modal);
              modal.querySelectorAll = () => descendants;
              modal.contains = (node) => {{ for (let current = node; current; current = current.parentElement) if (current === modal) return true; return false; }};
              globalThis.document = {{
                images: image ? [image] : [], activeElement: focusTarget,
                querySelector() {{ return {{ textContent: "ready" }}; }},
                querySelectorAll(selector) {{ return selector.includes("dialog") ? [modal] : []; }},
              }};
              return runAudit();
            }}
            globalThis.location = new URL("http://localhost/tonight");
            globalThis.window = {{ location: globalThis.location, innerWidth: 390, innerHeight: 844, matchMedia() {{ return {{ matches: false }}; }} }};
            globalThis.getComputedStyle = () => ({{ display: "block", visibility: "visible", overflowX: "visible" }});
            const {{ runAudit }} = await import("{module_url('js/core/audit.js')}");

            const ariaWrapper = element("div", {{ attributes: {{ "aria-hidden": "true" }} }});
            const ariaFocusable = element("button", {{ tabIndex: 0 }}); ariaWrapper.append(ariaFocusable);
            const ariaImage = element("img", {{ attributes: {{ "aria-hidden": "true" }} }});
            Object.assign(ariaImage, {{ complete: true, naturalWidth: 0, src: "https://cdn.example/media/private-focus-regression.png", currentSrc: "", clientWidth: 90, clientHeight: 130, scrollWidth: 90, scrollHeight: 130, classList: {{ contains() {{ return false; }} }} }});
            const ariaAudit = modalAudit(ariaWrapper, ariaFocusable, ariaImage);

            const fieldset = element("fieldset", {{ attributes: {{ disabled: "" }}, disabled: true }});
            const fieldsetFocusable = element("input", {{ tabIndex: 0 }});
            fieldsetFocusable.matches = () => {{ throw new Error("selector unsupported"); }};
            fieldset.append(fieldsetFocusable);
            const fieldsetAudit = modalAudit(fieldset, fieldsetFocusable);

            console.log(JSON.stringify({{
              ariaFocusFailures: ariaAudit.focusFailures.length,
              ariaBrokenImages: ariaAudit.brokenImages.length,
              ariaExternalImages: ariaAudit.externalImages.length,
              fieldsetFocusFailures: fieldsetAudit.focusFailures.length,
            }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual(1, result["ariaFocusFailures"])
        self.assertEqual(1, result["fieldsetFocusFailures"])
        self.assertEqual(1, result["ariaBrokenImages"])
        self.assertEqual(1, result["ariaExternalImages"])

    def test_browser_audit_executes_image_overflow_empty_main_and_focus_rules(self):
        output = run_node_module(
            f'''
            class FakeClassList {{
              constructor(value = "") {{ this._values = new Set(String(value).split(/\\s+/).filter(Boolean)); }}
              contains(value) {{ return this._values.has(value); }}
              values() {{ return this._values.values(); }}
            }}
            class FakeElement {{
              constructor(tagName, options = {{}}) {{
                this.tagName = String(tagName).toUpperCase();
                this.children = []; this.parentElement = null; this.parentNode = null;
                this.className = options.className || ""; this.classList = new FakeClassList(this.className);
                this.id = options.id || ""; this.hidden = Boolean(options.hidden);
                this.textContent = options.textContent || ""; this.src = options.src || "";
                this.complete = options.complete ?? true; this.naturalWidth = options.naturalWidth ?? 640;
                this.tabIndex = options.tabIndex ?? (this.tagName === "BUTTON" ? 0 : -1);
                this.clientWidth = options.clientWidth ?? 320; this.clientHeight = options.clientHeight ?? 180;
                this.scrollWidth = options.scrollWidth ?? this.clientWidth; this.scrollHeight = options.scrollHeight ?? this.clientHeight;
                this._rectVisible = options.rectVisible ?? true;
                this._style = {{ display: options.display || "block", visibility: options.visibility || "visible", overflowX: options.overflowX || "visible" }};
                this.attributes = new Map(Object.entries(options.attributes || {{}}));
                if (this.id) this.attributes.set("id", this.id);
                if (this.className) this.attributes.set("class", this.className);
              }}
              append(...nodes) {{ for (const node of nodes) {{ this.children.push(node); node.parentElement = this; node.parentNode = this; }} }}
              getAttribute(name) {{ return this.attributes.get(name) ?? null; }}
              hasAttribute(name) {{ return this.attributes.has(name); }}
              setAttribute(name, value) {{ this.attributes.set(name, String(value)); }}
              getClientRects() {{ return this._rectVisible && !this.hidden ? [{{ width: this.clientWidth, height: this.clientHeight }}] : []; }}
              contains(node) {{ for (let current = node; current; current = current.parentElement) if (current === this) return true; return false; }}
              closest(selector) {{ for (let current = this; current; current = current.parentElement) if (current.matches(selector)) return current; return null; }}
              matches(selector) {{
                if (selector === "#app-view") return this.id === "app-view";
                if (selector === "[hidden]") return this.hidden || this.hasAttribute("hidden");
                if (selector === '[aria-hidden="true"]') return this.getAttribute("aria-hidden") === "true";
                if (selector === '[role="dialog"][aria-modal="true"]') return this.getAttribute("role") === "dialog" && this.getAttribute("aria-modal") === "true";
                if (selector === "dialog[open]") return this.tagName === "DIALOG" && this.hasAttribute("open");
                if (selector === ":modal") return this.getAttribute("data-modal") === "true";
                return this.tagName === selector.toUpperCase();
              }}
              querySelectorAll(selector) {{
                const descendants = this.children.flatMap((child) => [child, ...child.querySelectorAll("*")]);
                if (selector === "*") return descendants;
                return descendants.filter((node) => selector.split(",").some((part) => node.matches(part.trim())));
              }}
            }}

            const html = new FakeElement("html");
            const body = new FakeElement("body");
            const main = new FakeElement("main", {{ id: "app-view", textContent: "   " }});
            html.append(body); body.append(main);
            const valid = new FakeElement("img", {{ src: "https://cinescope.test/media/ok.png", className: "safe-but-private-class" }});
            const broken = new FakeElement("img", {{ src: "/media/broken-private.png?token=private-query#private-hash", naturalWidth: 0, id: "private-broken-id" }});
            const wrongPath = new FakeElement("img", {{ src: "/assets/private-poster.png", attributes: {{ "data-secret": "private-attribute" }} }});
            const externalSamePath = new FakeElement("img", {{ src: "https://cdn.example/media/private-poster.png?token=private-query#private-hash", textContent: "private-dom-text" }});
            const hiddenBrokenExternal = new FakeElement("img", {{ src: "https://cdn.example/media/private-hidden.png", naturalWidth: 0, hidden: true }});
            main.append(valid, broken, wrongPath, externalSamePath, hiddenBrokenExternal);

            const allowedClasses = [
              "title-shelf__rail", "detail-tabs", "detail-people-rail", "library-window",
              "universe-evidence", "universe-roster", "universe-node-roster", "command-lens", "person-sheet__body",
            ];
            for (const className of allowedClasses) main.append(new FakeElement("div", {{ className, clientWidth: 200, scrollWidth: 700 }}));
            const overflow = new FakeElement("section", {{ id: "private-overflow-id", className: "private-overflow-class", clientWidth: 300, scrollWidth: 701 }});
            const scrollContainer = new FakeElement("div", {{ clientWidth: 300, scrollWidth: 900, overflowX: "auto" }});
            main.append(overflow, scrollContainer);

            const modal = new FakeElement("section", {{ attributes: {{ role: "dialog", "aria-modal": "true", "data-private": "private-modal-attribute" }} }});
            const focusButton = new FakeElement("button");
            modal.append(focusButton); body.append(modal);
            const outside = new FakeElement("button"); body.append(outside);
            const nonModalDialog = new FakeElement("dialog", {{ attributes: {{ open: "" }} }}); body.append(nonModalDialog);

            const all = [html, body, ...body.querySelectorAll("*")];
            globalThis.document = {{
              images: [valid, broken, wrongPath, externalSamePath, hiddenBrokenExternal],
              body, activeElement: outside,
              querySelector(selector) {{ return selector === "#app-view" ? main : null; }},
              querySelectorAll(selector) {{
                if (selector === "body *") return body.querySelectorAll("*");
                return all.filter((node) => selector.split(",").some((part) => node.matches(part.trim())));
              }},
            }};
            globalThis.location = new URL("https://cinescope.test/tonight?private=query#private-hash");
            globalThis.innerWidth = 1280; globalThis.innerHeight = 800;
            globalThis.window = {{ location: globalThis.location, matchMedia() {{ return {{ matches: true }}; }} }};
            globalThis.getComputedStyle = (node) => node._style;

            const {{ runAudit }} = await import("{module_url('js/core/audit.js')}");
            const outsideFocus = runAudit();
            document.activeElement = focusButton;
            const insideFocus = runAudit();
            modal.children = []; focusButton.parentElement = null; document.activeElement = modal;
            const noTarget = runAudit();
            console.log(JSON.stringify({{ outsideFocus, insideFocus, noTarget }}));
            '''
        )
        result = json.loads(output)
        audit = result["outsideFocus"]
        self.assertEqual("/tonight", audit["route"])
        self.assertEqual([1280, 800], audit["viewport"])
        self.assertEqual(1, len(audit["brokenImages"]))
        self.assertEqual(2, len(audit["externalImages"]))
        self.assertEqual(1, len(audit["overflowNodes"]))
        self.assertTrue(audit["emptyMain"])
        self.assertEqual(1, len(audit["focusFailures"]))
        self.assertEqual([], result["insideFocus"]["focusFailures"])
        self.assertEqual(1, len(result["noTarget"]["focusFailures"]))
        self.assertTrue(audit["reducedMotion"])
        serialized = json.dumps(result, ensure_ascii=False)
        for forbidden in (
            "private-dom-text", "private-poster", "private-query", "private-hash",
            "private-broken-id", "private-overflow-id", "private-overflow-class",
            "safe-but-private-class", "private-attribute", "private-modal-attribute",
        ):
            self.assertNotIn(forbidden, serialized)

    def test_hook_hosts_and_exact_owner_teardown(self):
        output = run_node_module(
            f'''
            globalThis.document = {{ images: [], body: null, querySelector() {{ return null; }}, querySelectorAll() {{ return []; }} }};
            globalThis.getComputedStyle = () => ({{ display: "block", visibility: "visible", overflowX: "visible" }});
            const {{ installAuditHook }} = await import("{module_url('js/core/audit.js')}");
            const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
            const store = {{ getState() {{ return {{}}; }}, dispatch() {{}} }};
            const allowed = [
              "http://localhost:8000/", "https://dev.localhost/", "http://127.0.0.1/",
              "https://127.255.255.255/", "http://[::1]/",
            ];
            const rejected = [
              "http://0.0.0.0/", "http://10.0.0.1/", "http://172.16.0.1/", "http://192.168.1.2/",
              "file:///tmp/index.html", "ftp://localhost/", "https://localhost.example/",
            ];
            const check = (url) => {{
              const browser = {{ location: new URL(url), matchMedia() {{ return {{ matches: false }}; }} }};
              const removeAudit = installAuditHook({{ browser }});
              const removeAcceptance = installAcceptanceHook({{ browser, store }});
              const installed = typeof browser.__CINESCOPE_AUDIT__ === "function" && typeof browser.__CINESCOPE_SEED_ACCEPTANCE__ === "function";
              removeAcceptance(); removeAudit();
              return installed;
            }};
            if (allowed.some((url) => !check(url))) throw new Error("allowed loopback host was rejected");
            if (rejected.some((url) => check(url))) throw new Error("non-loopback host was accepted");
            const plainBrowser = {{ location: {{ protocol: "http:", hostname: "localhost", port: "8123", pathname: "/" }}, matchMedia() {{ return {{ matches: false }}; }} }};
            const removePlainAudit = installAuditHook({{ browser: plainBrowser }});
            const removePlainSeed = installAcceptanceHook({{ browser: plainBrowser, store }});
            if (typeof plainBrowser.__CINESCOPE_AUDIT__ !== "function" || typeof plainBrowser.__CINESCOPE_SEED_ACCEPTANCE__ !== "function") {{
              throw new Error("plain Location-like loopback host was rejected");
            }}
            removePlainSeed(); removePlainAudit();

            const browser = {{ location: new URL("http://localhost:8000/"), matchMedia() {{ return {{ matches: false }}; }} }};
            const removeAudit1 = installAuditHook({{ browser }}); const audit1 = browser.__CINESCOPE_AUDIT__;
            const removeAudit2 = installAuditHook({{ browser }}); const audit2 = browser.__CINESCOPE_AUDIT__;
            if (audit1 === audit2) throw new Error("audit owner did not receive an exact hook ref");
            removeAudit1();
            if (browser.__CINESCOPE_AUDIT__ !== audit2) throw new Error("old audit owner deleted replacement");
            removeAudit2();
            if ("__CINESCOPE_AUDIT__" in browser) throw new Error("audit hook survived owner destroy");

            const removeSeed1 = installAcceptanceHook({{ browser, store }}); const seed1 = browser.__CINESCOPE_SEED_ACCEPTANCE__;
            const removeSeed2 = installAcceptanceHook({{ browser, store }}); const seed2 = browser.__CINESCOPE_SEED_ACCEPTANCE__;
            if (seed1 === seed2) throw new Error("acceptance owner did not receive an exact hook ref");
            removeSeed1();
            if (browser.__CINESCOPE_SEED_ACCEPTANCE__ !== seed2) throw new Error("old acceptance owner deleted replacement");
            removeSeed2();
            if ("__CINESCOPE_SEED_ACCEPTANCE__" in browser) throw new Error("acceptance hook survived owner destroy");
            console.log(JSON.stringify({{ allowed: allowed.length, rejected: rejected.length }}));
            '''
        )
        result = json.loads(output)
        self.assertEqual({"allowed": 5, "rejected": 7}, result)

    def test_acceptance_seed_uses_real_http_dedupes_and_persists_allowlisted_state(self):
        session = {
            "id": "session-seed-1",
            "intent": {"free_text": "raw-session-private-text"},
            "chips": [],
            "channels": {
                "电影": {
                    "batch": {
                        "id": "movie-batch-1",
                        "index": 0,
                        "items": [{"item_key": "douban:1001", "title": "raw-title-private-text"}],
                    }
                },
                "电视剧": {"batch": {"id": "series-batch-1", "index": 0, "items": []}},
                "动漫": {"batch": {"id": "anime-batch-1", "index": 0, "items": []}},
            },
        }

        def responder(record, _index):
            path = unquote(urlsplit(record["path"]).path)
            if record["method"] == "POST" and path == "/api/v2/recommend/sessions":
                return 200, session, 0
            if path == "/api/v2/titles/douban:1001":
                return 200, {"item_key": "douban:1001", "people": [{"id": "bad/id"}, {"id": "person:1"}]}, 0
            if path == "/api/v2/people/person:1":
                return 200, {"id": "person:1", "name": "raw-person-private-text"}, 0
            return 404, {"error": "unexpected fixture URL private-server-text"}, 0

        with http_fixture(responder) as (origin, records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const values = new Map(); let writes = 0;
                const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ writes += 1; values.set(key, String(value)); }} }};
                globalThis.localStorage = storage;
                const {{ createEmptyUiState, createStore, persistUiState, UI_STATE_KEY }} = await import("{module_url('js/core/store.js')}");
                const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const store = createStore(createEmptyUiState(), reduceUiState);
                const actions = [];
                const originalDispatch = store.dispatch.bind(store);
                store.dispatch = (action) => {{ actions.push(action); return originalDispatch(action); }};
                store.subscribe((state) => persistUiState(state, storage));
                const uninstall = installAcceptanceHook({{ browser: globalThis.window, store }});
                const first = window.__CINESCOPE_SEED_ACCEPTANCE__();
                const second = window.__CINESCOPE_SEED_ACCEPTANCE__();
                if (first !== second) throw new Error("concurrent calls did not share one promise");
                const [firstResult, secondResult] = await Promise.all([first, second]);
                const cachedResult = await window.__CINESCOPE_SEED_ACCEPTANCE__();
                const persisted = values.get(UI_STATE_KEY) || "";
                uninstall();
                console.log(JSON.stringify({{
                  firstResult, secondResult, cachedResult, persisted, writes,
                  actionTypes: actions.map((action) => action.type),
                  state: store.getState(),
                }}));
                '''
            )

        result = json.loads(output)
        expected = {"sessionId": "session-seed-1", "titleId": "douban:1001", "personId": "person:1"}
        self.assertEqual(expected, result["firstResult"])
        self.assertEqual(expected, result["secondResult"])
        self.assertEqual(expected, result["cachedResult"])
        self.assertEqual(["recommendation/sessionReceived"], result["actionTypes"])
        self.assertEqual(1, result["writes"])
        self.assertEqual("session-seed-1", result["state"]["recommendation"]["sessionId"])
        persisted = result["persisted"]
        self.assertIn("session-seed-1", persisted)
        for forbidden in ("raw-session-private-text", "raw-title-private-text", "raw-person-private-text"):
            self.assertNotIn(forbidden, persisted)

        posts = [record for record in records if record["method"] == "POST"]
        raw_gets = [urlsplit(record["path"]).path for record in records if record["method"] == "GET"]
        gets = [unquote(urlsplit(record["path"]).path) for record in records if record["method"] == "GET"]
        self.assertEqual(1, len(posts))
        self.assertEqual(["/api/v2/titles/douban:1001", "/api/v2/people/person:1"], raw_gets)
        self.assertEqual(["/api/v2/titles/douban:1001", "/api/v2/people/person:1"], gets)
        self.assertEqual(
            {
                "schema_version": 2,
                "use_sample_ratings": True,
                "use_sample_candidates": True,
                "fetch_douban": False,
                "include_movies": True,
                "include_series": True,
                "include_anime": True,
                "batch_size": 24,
                "limit": 160,
            },
            posts[0]["body"],
        )

    def test_acceptance_rejects_dot_title_segment_before_http_normalisation(self):
        session = {
            "id": "session-dot-title",
            "channels": {
                "电影": {"batch": {"items": [{"item_key": "."}]}},
                "电视剧": {"batch": {"items": []}},
                "动漫": {"batch": {"items": []}},
            },
        }

        def responder(record, _index):
            if record["method"] == "POST":
                return 200, session, 0
            return 200, {"people": []}, 0

        with http_fixture(responder) as (origin, records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const store = {{ getState() {{ return {{}}; }}, dispatch() {{ throw new Error("dot title dispatched"); }} }};
                const uninstall = installAcceptanceHook({{ browser: window, store }});
                let errorResult;
                try {{ await window.__CINESCOPE_SEED_ACCEPTANCE__(); }} catch (error) {{
                  errorResult = {{ code: error.code, message: error.message, stack: error.stack }};
                }}
                uninstall();
                console.log(JSON.stringify(errorResult));
                '''
            )

        result = json.loads(output)
        self.assertEqual("CINESCOPE_ACCEPTANCE_NO_TITLE", result["code"])
        self.assertEqual(result["code"], result["message"])
        self.assertEqual(["/api/v2/recommend/sessions"], [unquote(urlsplit(record["path"]).path) for record in records])
        self.assertNotIn(origin, json.dumps(result))

    def test_acceptance_rejects_dot_dot_person_segment_before_http_normalisation(self):
        session = {
            "id": "session-dot-person",
            "channels": {
                "电影": {"batch": {"items": [{"item_key": "douban:1001"}]}},
                "电视剧": {"batch": {"items": []}},
                "动漫": {"batch": {"items": []}},
            },
        }

        def responder(record, _index):
            path = unquote(urlsplit(record["path"]).path)
            if record["method"] == "POST":
                return 200, session, 0
            if path == "/api/v2/titles/douban:1001":
                return 200, {"people": [{"id": ".."}]}, 0
            return 200, {"id": "parent-endpoint-must-not-resolve"}, 0

        with http_fixture(responder) as (origin, records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const store = {{ getState() {{ return {{ recommendation: {{ sessionId: null }} }}; }}, dispatch() {{}} }};
                const uninstall = installAcceptanceHook({{ browser: window, store }});
                let result;
                try {{
                  result = {{ success: true, value: await window.__CINESCOPE_SEED_ACCEPTANCE__() }};
                }} catch (error) {{
                  result = {{ success: false, code: error.code, message: error.message, stack: error.stack }};
                }}
                uninstall();
                console.log(JSON.stringify(result));
                '''
            )

        result = json.loads(output)
        self.assertFalse(result["success"])
        self.assertEqual("CINESCOPE_ACCEPTANCE_NO_PERSON", result["code"])
        self.assertEqual(result["code"], result["message"])
        self.assertEqual(
            ["/api/v2/recommend/sessions", "/api/v2/titles/douban:1001"],
            [unquote(urlsplit(record["path"]).path) for record in records],
        )
        self.assertNotIn(origin, json.dumps(result))

    def test_acceptance_treats_listener_throw_after_real_store_commit_as_cached_success(self):
        session = {
            "id": "session-listener-commit",
            "intent": {"free_text": "raw-listener-private-text"},
            "chips": [],
            "channels": {
                "电影": {"batch": {"id": "movie-listener-batch", "index": 0, "items": [{"item_key": "douban:2001", "title": "raw-listener-title"}]}},
                "电视剧": {"batch": {"id": "series-listener-batch", "index": 0, "items": []}},
                "动漫": {"batch": {"id": "anime-listener-batch", "index": 0, "items": []}},
            },
        }

        def responder(record, _index):
            path = unquote(urlsplit(record["path"]).path)
            if record["method"] == "POST":
                return 200, session, 0
            if path == "/api/v2/titles/douban:2001":
                return 200, {"people": [{"id": "person-listener"}]}, 0
            if path == "/api/v2/people/person-listener":
                return 200, {"id": "person-listener", "name": "raw-listener-person"}, 0
            return 404, {"error": "unexpected-listener-fixture"}, 0

        with http_fixture(responder) as (origin, records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const values = new Map(); let writes = 0;
                const storage = {{ getItem(key) {{ return values.get(key) ?? null; }}, setItem(key, value) {{ writes += 1; values.set(key, String(value)); }} }};
                const {{ createEmptyUiState, createStore, persistUiState, UI_STATE_KEY }} = await import("{module_url('js/core/store.js')}");
                const {{ reduceUiState }} = await import("{module_url('js/app.js')}");
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const store = createStore(createEmptyUiState(), reduceUiState);
                store.subscribe((state, action) => {{
                  persistUiState(state, storage);
                  if (action.type === "recommendation/sessionReceived") throw new Error("listener-private-text");
                }});
                const uninstall = installAcceptanceHook({{ browser: window, store }});
                const first = await window.__CINESCOPE_SEED_ACCEPTANCE__();
                const second = await window.__CINESCOPE_SEED_ACCEPTANCE__();
                const persisted = values.get(UI_STATE_KEY) || "";
                uninstall();
                console.log(JSON.stringify({{
                  first, second, sameResult: first === second, writes, persisted,
                  sessionId: store.getState().recommendation.sessionId,
                }}));
                '''
            )

        result = json.loads(output)
        expected = {"sessionId": "session-listener-commit", "titleId": "douban:2001", "personId": "person-listener"}
        self.assertEqual(expected, result["first"])
        self.assertEqual(expected, result["second"])
        self.assertTrue(result["sameResult"])
        self.assertEqual(1, result["writes"])
        self.assertEqual("session-listener-commit", result["sessionId"])
        self.assertEqual(1, sum(record["method"] == "POST" for record in records))
        for forbidden in ("raw-listener-private-text", "raw-listener-title", "raw-listener-person", "listener-private-text"):
            self.assertNotIn(forbidden, result["persisted"])

    def test_acceptance_reports_commit_failure_only_when_store_state_did_not_change(self):
        session = {
            "id": "session-uncommitted",
            "channels": {
                "电影": {"batch": {"id": "movie-uncommitted", "index": 1, "items": [{"item_key": "douban:3001"}]}},
                "电视剧": {"batch": {"id": "series-uncommitted", "index": 2, "items": []}},
                "动漫": {"batch": {"id": "anime-uncommitted", "index": 3, "items": []}},
            },
        }

        def responder(record, _index):
            path = unquote(urlsplit(record["path"]).path)
            if record["method"] == "POST":
                return 200, session, 0
            if path == "/api/v2/titles/douban:3001":
                return 200, {"people": [{"id": "person-uncommitted"}]}, 0
            if path == "/api/v2/people/person-uncommitted":
                return 200, {"id": "person-uncommitted"}, 0
            return 404, {"error": "unexpected-uncommitted-fixture"}, 0

        with http_fixture(responder) as (origin, records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const {{ createStore }} = await import("{module_url('js/core/store.js')}");
                const initialState = {{ recommendation: {{
                  sessionId: "session-uncommitted",
                  channels: {{
                    movie: {{ sessionId: "session-uncommitted", batchIndex: 1, batchIds: ["movie-uncommitted"] }},
                    series: {{ sessionId: "session-uncommitted", batchIndex: 2, batchIds: ["series-uncommitted"] }},
                    "anime-series": {{ sessionId: "session-uncommitted", batchIndex: 3, batchIds: ["anime-uncommitted"] }},
                  }},
                }} }};
                const store = createStore(initialState, () => {{ throw new Error("reducer-private-failure"); }});
                const uninstall = installAcceptanceHook({{ browser: window, store }});
                const attempt = async () => {{
                  try {{ return {{ success: true, value: await window.__CINESCOPE_SEED_ACCEPTANCE__() }}; }}
                  catch (error) {{ return {{ success: false, code: error.code, message: error.message, stack: error.stack }}; }}
                }};
                const first = await attempt(); const second = await attempt();
                uninstall();
                console.log(JSON.stringify({{ first, second, unchanged: store.getState() === initialState }}));
                '''
            )

        result = json.loads(output)
        self.assertFalse(result["first"]["success"])
        self.assertFalse(result["second"]["success"])
        self.assertEqual("CINESCOPE_ACCEPTANCE_COMMIT_FAILED", result["first"]["code"])
        self.assertEqual("CINESCOPE_ACCEPTANCE_COMMIT_FAILED", result["second"]["code"])
        self.assertEqual(result["first"]["code"], result["first"]["message"])
        self.assertEqual(result["second"]["code"], result["second"]["message"])
        self.assertTrue(result["unchanged"])
        self.assertEqual(2, sum(record["method"] == "POST" for record in records))
        self.assertNotIn("reducer-private-failure", json.dumps(result))

    def test_acceptance_abort_generation_and_reinstall_prevent_stale_dispatch(self):
        post_count = 0
        post_lock = threading.Lock()

        def responder(record, _index):
            nonlocal post_count
            path = unquote(urlsplit(record["path"]).path)
            if record["method"] == "POST" and path == "/api/v2/recommend/sessions":
                with post_lock:
                    post_count += 1
                    current = post_count
                session_id = f"session-{current}"
                payload = {
                    "id": session_id,
                    "channels": {
                        "电影": {"batch": {"id": f"batch-{current}", "index": 0, "items": [{"item_key": f"douban:{1000 + current}"}]}},
                        "电视剧": {"batch": {"items": []}},
                        "动漫": {"batch": {"items": []}},
                    },
                }
                return 200, payload, 0.35 if current == 1 else 0
            if path.startswith("/api/v2/titles/douban:"):
                suffix = path.rsplit(":", 1)[-1]
                return 200, {"people": [{"id": f"person-{suffix}"}]}, 0
            if path.startswith("/api/v2/people/person-"):
                return 200, {"id": path.rsplit("/", 1)[-1]}, 0
            return 404, {"error": "private unexpected fixture text"}, 0

        with http_fixture(responder) as (origin, _records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const {{ createStore }} = await import("{module_url('js/core/store.js')}");
                const actions = []; const persists = [];
                const store = createStore({{}}, (state, action) => action.type === "recommendation/sessionReceived" ? {{ sessionId: action.session.id }} : state);
                const originalDispatch = store.dispatch.bind(store);
                store.dispatch = (action) => {{ actions.push(action); return originalDispatch(action); }};
                store.subscribe((state) => persists.push(state.sessionId));
                const uninstallFirst = installAcceptanceHook({{ browser: window, store }});
                const firstPromise = window.__CINESCOPE_SEED_ACCEPTANCE__().catch((error) => error.code);
                await new Promise((resolve) => setTimeout(resolve, 40));
                uninstallFirst();
                const uninstallSecond = installAcceptanceHook({{ browser: window, store }});
                const replacementHook = window.__CINESCOPE_SEED_ACCEPTANCE__;
                uninstallFirst();
                if (window.__CINESCOPE_SEED_ACCEPTANCE__ !== replacementHook) throw new Error("stale owner deleted replacement hook");
                const secondResult = await replacementHook();
                const firstCode = await firstPromise;
                await new Promise((resolve) => setTimeout(resolve, 420));
                uninstallSecond();
                console.log(JSON.stringify({{ firstCode, secondResult, sessions: actions.map((action) => action.session?.id), persists }}));
                ''',
                timeout=20,
            )

        result = json.loads(output)
        self.assertEqual("CINESCOPE_ACCEPTANCE_STALE", result["firstCode"])
        self.assertEqual("session-2", result["secondResult"]["sessionId"])
        self.assertEqual(["session-2"], result["sessions"])
        self.assertEqual(["session-2"], result["persists"])

    def test_acceptance_errors_are_stable_and_redacted(self):
        def responder(_record, _index):
            return 500, {
                "error": "private-server-text http://127.0.0.1/private?payload=secret",
                "payload": {"cookie": "private-cookie-value"},
            }, 0

        with http_fixture(responder) as (origin, _records):
            output = run_node_module(
                f'''
                {browser_prelude(origin)}
                const {{ installAcceptanceHook }} = await import("{module_url('js/core/acceptance.js')}");
                const store = {{ getState() {{ return {{}}; }}, dispatch() {{ throw new Error("dispatch must not run"); }} }};
                const uninstall = installAcceptanceHook({{ browser: window, store }});
                let result;
                try {{ await window.__CINESCOPE_SEED_ACCEPTANCE__(); }} catch (error) {{
                  result = {{ name: error.name, code: error.code, message: error.message, stack: error.stack, keys: Object.keys(error) }};
                }}
                uninstall();
                console.log(JSON.stringify(result));
                '''
            )

        result = json.loads(output)
        self.assertEqual("CINESCOPE_ACCEPTANCE_SESSION_FAILED", result["code"])
        self.assertEqual(result["code"], result["message"])
        serialized = json.dumps(result)
        for forbidden in (origin, "private-server-text", "payload", "private-cookie-value", "/api/v2/", "file:"):
            self.assertNotIn(forbidden, serialized)

    def test_app_installs_hooks_after_router_creation_and_uninstalls_first(self):
        source = ui_text("js/app.js")
        router_index = source.index("router = createRouter")
        audit_index = source.index("installAuditHook", router_index)
        acceptance_index = source.index("installAcceptanceHook", router_index)
        navigation_index = source.index("bindNavigation(router)", router_index)
        start_index = source.index("router.start()", router_index)
        self.assertLess(router_index, audit_index)
        self.assertLess(router_index, acceptance_index)
        self.assertLess(audit_index, navigation_index)
        self.assertLess(acceptance_index, navigation_index)
        self.assertLess(navigation_index, start_index)
        destroy_body = source[source.index("destroy() {") :]
        first_statement = destroy_body.split("{", 1)[1].strip().splitlines()[0].strip()
        self.assertEqual("uninstallBrowserHooks();", first_statement)

    def test_app_runtime_hook_lifecycle_preserves_replacement_and_uninstalls_before_cleanup(self):
        output = run_node_module(
            f'''
            {fake_dom_module_prelude()}
            const nodes = new Map();
            for (const [id, tag] of [["app-view", "main"], ["shell-status", "p"], ["command-lens-root", "div"], ["overlay-root", "div"], ["command-lens-trigger", "button"], ["rail-collapse-toggle", "button"], ["rail-hide-toggle", "button"], ["rail-restore", "button"], ["primary-rail", "aside"], ["a11y-announcer", "div"]]) {{
              const node = new FakeElement(tag); node.id = id; nodes.set(id, node);
            }}
            document.body = new FakeElement("body"); document.body.classList = new FakeClassList(document.body); document.activeElement = document.body;
            const documentListeners = new Map(); const cleanupSnapshots = []; let destroyPhase = "";
            document.getElementById = (id) => nodes.get(id) || null;
            document.querySelectorAll = () => [];
            document.addEventListener = (type, listener) => {{ if (!documentListeners.has(type)) documentListeners.set(type, new Set()); documentListeners.get(type).add(listener); }};
            document.removeEventListener = (type, listener) => {{
              if (destroyPhase) cleanupSnapshots.push({{ phase: destroyPhase, surface: `document:${{type}}`, audit: window.__CINESCOPE_AUDIT__, seed: window.__CINESCOPE_SEED_ACCEPTANCE__ }});
              documentListeners.get(type)?.delete(listener);
            }};
            const storage = new Map(); const windowListeners = new Map();
            const browser = {{
              location: new URL("http://localhost/missing"), scrollY: 0,
              history: {{ state: null, scrollRestoration: "auto", pushState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }}, replaceState(state, _title, path) {{ this.state = state; browser.location.pathname = path; }} }},
              localStorage: {{ getItem(key) {{ return storage.get(key) ?? null; }}, setItem(key, value) {{ storage.set(key, String(value)); }} }},
              addEventListener(type, listener) {{ if (!windowListeners.has(type)) windowListeners.set(type, new Set()); windowListeners.get(type).add(listener); }},
              removeEventListener(type, listener) {{
                if (destroyPhase) cleanupSnapshots.push({{ phase: destroyPhase, surface: `window:${{type}}`, audit: browser.__CINESCOPE_AUDIT__, seed: browser.__CINESCOPE_SEED_ACCEPTANCE__ }});
                windowListeners.get(type)?.delete(listener);
              }},
              dispatchEvent(event) {{ for (const listener of [...(windowListeners.get(event.type) || [])]) listener(event); }},
              requestAnimationFrame(callback) {{ callback(); return 1; }}, scrollTo() {{}}, matchMedia() {{ return {{ matches: false }}; }},
              PopStateEvent: class {{ constructor(type, init) {{ this.type = type; this.state = init.state; }} }},
            }};
            globalThis.window = browser; globalThis.location = browser.location; globalThis.history = browser.history; globalThis.localStorage = browser.localStorage;
            globalThis.requestAnimationFrame = browser.requestAnimationFrame; globalThis.PopStateEvent = browser.PopStateEvent;
            const {{ bootstrapCineScopeShell }} = await import("{module_url('js/app.js')}");
            const first = bootstrapCineScopeShell(); await flush();
            const firstAudit = browser.__CINESCOPE_AUDIT__; const firstSeed = browser.__CINESCOPE_SEED_ACCEPTANCE__;
            if (typeof firstAudit !== "function" || typeof firstSeed !== "function") throw new Error("first bootstrap did not install hooks");
            const second = bootstrapCineScopeShell(); await flush();
            const secondAudit = browser.__CINESCOPE_AUDIT__; const secondSeed = browser.__CINESCOPE_SEED_ACCEPTANCE__;
            if (secondAudit === firstAudit || secondSeed === firstSeed) throw new Error("replacement bootstrap reused owner refs");
            destroyPhase = "old"; first.destroy(); destroyPhase = "";
            if (browser.__CINESCOPE_AUDIT__ !== secondAudit || browser.__CINESCOPE_SEED_ACCEPTANCE__ !== secondSeed) throw new Error("old destroy deleted replacement globals");
            destroyPhase = "replacement"; second.destroy(); destroyPhase = "";
            if ("__CINESCOPE_AUDIT__" in browser || "__CINESCOPE_SEED_ACCEPTANCE__" in browser) throw new Error("replacement destroy left hooks installed");
            const oldSnapshots = cleanupSnapshots.filter((entry) => entry.phase === "old");
            const replacementSnapshots = cleanupSnapshots.filter((entry) => entry.phase === "replacement");
            if (!oldSnapshots.length || oldSnapshots.some((entry) => entry.audit !== secondAudit || entry.seed !== secondSeed)) throw new Error("old destroy teardown ordering was not exact-owner safe");
            if (!replacementSnapshots.length || replacementSnapshots.some((entry) => entry.audit !== undefined || entry.seed !== undefined)) throw new Error("replacement hooks were not removed before later cleanup");
            console.log(JSON.stringify({{ oldSnapshots: oldSnapshots.length, replacementSnapshots: replacementSnapshots.length }}));
            '''
        )
        result = json.loads(output)
        self.assertGreater(result["oldSnapshots"], 0)
        self.assertGreater(result["replacementSnapshots"], 0)


if __name__ == "__main__":
    unittest.main()
