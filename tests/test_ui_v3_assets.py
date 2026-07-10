import os
import threading
import unittest
import urllib.request
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

    def test_v3_shell_uses_native_modules_and_five_spaces(self):
        html = load_index_html()

        self.assertIn('type="module"', html)
        for route in ("/tonight", "/universe", "/library", "/taste", "/health"):
            self.assertIn(route, html)

    def test_v3_shell_exposes_required_semantic_regions(self):
        html = load_index_html()
        stylesheet, _ = asset_response("styles/tokens.css")
        shell = html + stylesheet.decode("utf-8")

        for token in (
            "skip-link",
            "72px",
            "top-bar",
            'id="command-lens-root"',
            'id="app-view"',
            'id="overlay-root"',
            "<noscript>",
        ):
            with self.subTest(token=token):
                self.assertIn(token, shell)

    def test_asset_loader_rejects_parent_traversal(self):
        with self.assertRaises(FileNotFoundError):
            asset_response("../web.py")

    def test_asset_loader_returns_packaged_native_module(self):
        body, content_type = asset_response("js/app.js")

        self.assertIn("javascript", content_type)
        self.assertIn(b"bootstrapCineScopeShell", body)

    def test_v3_route_classifier_supports_deep_links_without_shadowing_services(self):
        for path in ("/tonight", "/tonight/anime-series", "/title/douban:1295644", "/person/person-1"):
            with self.subTest(path=path):
                self.assertTrue(is_v3_frontend_route(path))
        for path in ("/api/v2/taste", "/media/hash.png", "/assets/v3/js/app.js", "/title/../web.py"):
            with self.subTest(path=path):
                self.assertFalse(is_v3_frontend_route(path))

    def test_selected_ui_version_defaults_to_legacy_and_accepts_v3(self):
        self.assertEqual("legacy", selected_ui_version({}))
        self.assertEqual("legacy", selected_ui_version({"CINESCOPE_UI_VERSION": "unexpected"}))
        self.assertEqual("v3", selected_ui_version({"CINESCOPE_UI_VERSION": "v3"}))

    def test_v3_deep_link_refresh_returns_shell(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "v3"}, clear=False):
            status, content_type, body = self.get_raw("/title/douban:1295644")

        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertIn(b'id="app-view"', body)

    def test_v3_asset_route_serves_native_module(self):
        status, content_type, body = self.get_raw("/assets/v3/js/app.js")

        self.assertEqual(200, status)
        self.assertIn("javascript", content_type)
        self.assertIn(b"bootstrapCineScopeShell", body)

    def test_legacy_root_keeps_current_index_html(self):
        with mock.patch.dict(os.environ, {"CINESCOPE_UI_VERSION": "legacy"}, clear=False):
            status, content_type, body = self.get_raw("/")

        self.assertEqual(200, status)
        self.assertIn("text/html", content_type)
        self.assertEqual(INDEX_HTML.encode("utf-8"), body)


if __name__ == "__main__":
    unittest.main()
