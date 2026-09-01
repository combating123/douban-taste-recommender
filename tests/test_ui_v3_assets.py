import os
import threading
import unittest
import urllib.request
from urllib.error import HTTPError
from http.server import ThreadingHTTPServer
from unittest import mock

from douban_recommender.web import Handler
from douban_recommender.web_ui import INDEX_HTML
from douban_recommender.web_ui_v3 import (
    asset_response,
    is_v3_frontend_route,
    load_index_html,
    selected_ui_version,
)


class UiV3AssetTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def get_raw(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers.get("Content-Type", ""), response.read()

    def get_response(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, dict(response.headers.items()), response.read()
        except HTTPError as error:
            try:
                return error.code, dict(error.headers.items()), error.read()
            finally:
                error.close()

    def get_status(self, path):
        try:
            return self.get_raw(path)
        except HTTPError as error:
            try:
                return error.code, error.headers.get("Content-Type", ""), error.read()
            finally:
                error.close()

    def test_v3_shell_uses_native_modules_and_four_clear_primary_spaces(self):
        html = load_index_html()

        self.assertIn('type="module"', html)
        for route in ("/tonight", "/library", "/taste", "/health"):
            self.assertIn(route, html)
        self.assertNotIn('<a href="/universe" data-route>', html)
        self.assertIn("隐藏侧栏", html)

    def test_v3_shell_exposes_required_semantic_regions(self):
        html = load_index_html()
        stylesheet, _ = asset_response("styles/tokens.css")
        shell = html + stylesheet.decode("utf-8")

        for token in (
            "skip-link",
            "112px",
            "top-bar",
            'id="command-lens-root"',
            'id="app-view"',
            'id="overlay-root"',
            "<noscript>",
        ):
            with self.subTest(token=token):
                self.assertIn(token, shell)

    def test_v3_shell_cache_busts_every_static_asset_with_one_build_revision(self):
        html = load_index_html()
        references = []
        for marker in ('href="', 'src="'):
            for fragment in html.split(marker)[1:]:
                reference = fragment.split('"', 1)[0]
                if reference.startswith("/assets/v3/"):
                    references.append(reference)

        self.assertGreater(len(references), 5)
        revisions = {
            reference.split("/", 5)[3]
            for reference in references
        }
        self.assertEqual(1, len(revisions))
        revision = revisions.pop()
        self.assertRegex(revision, r"^build-[0-9a-f]{12}$")
        self.assertTrue(all("?" not in reference for reference in references))

    def test_versioned_asset_route_preserves_revision_for_relative_module_imports(self):
        html = load_index_html()
        app_reference = next(
            fragment.split('"', 1)[0]
            for fragment in html.split('src="')[1:]
            if "/js/app.js" in fragment
        )
        revision_root = app_reference.rsplit("/js/app.js", 1)[0]
        self.assertRegex(revision_root, r"^/assets/v3/build-[0-9a-f]{12}$")

        status, content_type, body = self.get_raw(app_reference)
        nested_status, nested_content_type, nested_body = self.get_raw(f"{revision_root}/js/core/api.js")

        self.assertEqual(200, status)
        self.assertIn("javascript", content_type)
        self.assertIn(b"bootstrapCineScopeShell", body)
        self.assertEqual(200, nested_status)
        self.assertIn("javascript", nested_content_type)
        self.assertIn(b"getV2", nested_body)

    def test_asset_loader_rejects_parent_traversal(self):
        with self.assertRaises(FileNotFoundError):
            asset_response("../web.py")

    def test_asset_loader_returns_packaged_native_module(self):
        body, content_type = asset_response("js/app.js")

        self.assertIn("javascript", content_type)
        self.assertIn(b"bootstrapCineScopeShell", body)

    def test_v3_route_classifier_supports_deep_links_without_shadowing_services(self):
        for path in (
            "/tonight",
            "/tonight/anime-series",
            "/observatory",
            "/title/douban:1295644",
            "/title/douban%3A1295644",
            "/person/person-1",
            "/person/derived%3Aperson-1",
        ):
            with self.subTest(path=path):
                self.assertTrue(is_v3_frontend_route(path))
        for path in (
            "/api/v2/taste",
            "/media/hash.png",
            "/assets/v3/js/app.js",
            "/title/../web.py",
            "/title/douban%2F1295644",
            "/title/%ZZ",
            "/%61pi/v2/taste",
        ):
            with self.subTest(path=path):
                self.assertFalse(is_v3_frontend_route(path))

    def test_v3_is_default_and_legacy_is_explicit_opt_in(self):
        self.assertEqual(selected_ui_version({}), "v3")
        self.assertEqual(selected_ui_version({"CINESCOPE_UI_VERSION": "legacy"}), "legacy")
        self.assertEqual(selected_ui_version({"CINESCOPE_UI_VERSION": "unexpected"}), "v3")

    def test_v3_deep_link_refresh_returns_shell(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "v3"}, clear=False):
            status, content_type, body = self.get_raw("/title/douban:1295644")

        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertIn(b'id="app-view"', body)

    def test_observatory_deep_link_refresh_returns_shell(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "v3"}, clear=False):
            status, content_type, body = self.get_raw("/observatory")

        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertIn(b'id="app-view"', body)
        self.assertIn(b"observatory.css", body)

    def test_v3_encoded_deep_links_refresh_without_swallowing_unsafe_paths(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "v3"}, clear=False):
            for path in ("/title/douban%3A1295644", "/person/derived%3Aperson-1"):
                with self.subTest(path=path):
                    status, content_type, body = self.get_status(path)
                    self.assertEqual(200, status)
                    self.assertIn("text/html", content_type)
                    self.assertIn(b'id="app-view"', body)

            for path in (
                "/title/douban%2F1295644",
                "/title/%2e%2e",
                "/title/%ZZ",
                "/%61pi/v2/taste",
                "/%61ssets/v3/js/app.js",
                "/%6dedia/hash.png",
            ):
                with self.subTest(path=path):
                    status, content_type, body = self.get_status(path)
                    self.assertEqual(404, status)
                    self.assertIn("application/json", content_type)
                    self.assertNotIn(b'id="app-view"', body)

    def test_v3_asset_route_serves_native_module(self):
        status, content_type, body = self.get_raw("/assets/v3/js/app.js")

        self.assertEqual(200, status)
        self.assertIn("javascript", content_type)
        self.assertIn(b"bootstrapCineScopeShell", body)

    def test_v3_shell_and_fixed_module_graph_cannot_be_reused_as_immutable(self):
        expected = "no-cache, no-store, must-revalidate"
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "v3"}, clear=False):
            for path in ("/", "/title/douban:1291879", "/assets/v3/js/app.js"):
                with self.subTest(path=path):
                    status, headers, body = self.get_response(path)
                    self.assertEqual(200, status)
                    self.assertEqual(expected, headers.get("Cache-Control"))
                    self.assertNotIn("immutable", headers.get("Cache-Control", ""))
                    self.assertTrue(body)

    def test_legacy_root_keeps_current_index_html(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "legacy"}, clear=False):
            status, content_type, body = self.get_raw("/")

        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertEqual(INDEX_HTML.encode("utf-8"), body)

    def test_legacy_mode_recovers_legal_v3_deep_links_without_shadowing_service_or_unsafe_paths(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "legacy"}, clear=False):
            for path in (
                "/tonight/anime-series",
                "/title/douban:1291879",
                "/person/derived:6buR5rO95piO",
            ):
                with self.subTest(path=path):
                    status, headers, body = self.get_response(path)
                    self.assertEqual(200, status)
                    self.assertIn("text/html", headers.get("Content-Type", ""))
                    self.assertEqual(INDEX_HTML.encode("utf-8"), body)

            for path in (
                "/api/v2/not-a-service",
                "/assets/v3/not-found.js",
                "/media/not-a-sha.png",
                "/title/douban%2F1291879",
                "/title/%2e%2e",
                "/%61pi/v2/taste",
            ):
                with self.subTest(path=path):
                    status, headers, body = self.get_response(path)
                    self.assertEqual(404, status)
                    self.assertIn("application/json", headers.get("Content-Type", ""))
                    self.assertNotEqual(INDEX_HTML.encode("utf-8"), body)


if __name__ == "__main__":
    unittest.main()
