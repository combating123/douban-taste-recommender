import base64
import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.feedback_service import FeedbackEvent, FeedbackService
from douban_recommender.web import Handler
import douban_recommender.web as web_module

try:
    from douban_recommender.catalog_api import CatalogApi
except ImportError:  # RED: implementation intentionally absent at first.
    CatalogApi = None


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"


def item_key(douban_id):
    return f"douban:{douban_id}"


class CatalogApiV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.database = AppDatabase(self.root / "cinescope.db")
        self.database.initialize()
        self.media_root = self.root / "media"
        self.media_root.mkdir()
        self.now = 1_800_000_000.0
        self._seed_catalog()
        self.original_catalog_api = getattr(web_module, "CATALOG_API", None)
        if CatalogApi is not None:
            self.api = CatalogApi(self.database, media_root=self.media_root)
            web_module.CATALOG_API = self.api
        else:
            self.api = None
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        if hasattr(web_module, "CATALOG_API"):
            web_module.CATALOG_API = self.original_catalog_api
        self.temp.cleanup()

    def _insert_library(self, key, payload, state="watched", updated_offset=0):
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, ?, 'fixture', ?, ?)
                """,
                (key, json.dumps(payload, ensure_ascii=False), state, self.now + updated_offset, self.now + updated_offset),
            )

    def _insert_asset(self, asset_id, kind="poster", present=True):
        relative = Path(asset_id[:2]) / f"{asset_id}.png"
        path = self.media_root / relative
        if present:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(PNG_BYTES)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO asset_files(
                    asset_id, sha256, relative_path, mime_type, extension, width, height,
                    byte_size, source_url, kind, status, created_at, last_verified_at
                ) VALUES(?, ?, ?, 'image/png', '.png', 1, 1, ?, 'https://secret.example/source.png', ?, 'ready', ?, ?)
                """,
                (asset_id, asset_id, relative.as_posix(), len(PNG_BYTES), kind, self.now, self.now),
            )
        return asset_id

    def _seed_catalog(self):
        poster_asset = self._insert_asset("a" * 64, "poster", present=True)
        portrait_asset = self._insert_asset("b" * 64, "portrait", present=True)
        missing_asset = self._insert_asset("c" * 64, "backdrop", present=False)
        alpha = {
            "title": "Local Poster Film",
            "media_type": "movie",
            "year": 2020,
            "my_rating": 5,
            "douban_rating": 8.9,
            "genres": ["Drama", "Noir"],
            "countries": ["China"],
            "directors": ["Director A"],
            "casts": ["Actor External", "Actor B"],
            "tags": ["watched"],
            "douban_id": "1001",
            "url": "https://movie.douban.com/subject/1001/?token=secret",
            "cover": "https://img.example/poster.jpg?token=secret",
            "summary": "A seeded title",
            "source": "https://source.example/list?secret=1",
            "people_photos": {"Actor External": "https://img.example/actor.jpg?token=secret"},
            "backdrop": "https://img.example/backdrop.jpg?token=secret",
        }
        beta = {
            "title": "Shared Director Film",
            "media_type": "movie",
            "year": 2021,
            "my_rating": 4,
            "genres": ["Drama"],
            "countries": ["China"],
            "directors": ["Director A"],
            "casts": ["Actor C"],
            "douban_id": "1002",
        }
        gamma = {
            "title": "Negative Noir",
            "media_type": "movie",
            "year": 2020,
            "my_rating": 1,
            "genres": ["Noir", "Horror"],
            "countries": ["Japan"],
            "directors": ["Director Z"],
            "casts": ["Actor B"],
            "douban_id": "1003",
        }
        wish = {
            "title": "Unexplored Space",
            "media_type": "series",
            "year": 2010,
            "genres": ["Sci-Fi"],
            "countries": ["USA"],
            "tags": ["wish"],
            "douban_id": "1004",
        }
        self._insert_library(item_key("1001"), alpha, "watched", 40)
        self._insert_library(item_key("1002"), beta, "watched", 30)
        self._insert_library(item_key("1003"), gamma, "watched", 20)
        self._insert_library(item_key("1004"), wish, "wish", 10)
        self._insert_library("item:custom", {"title": "No Relations", "media_type": "movie", "douban_id": ""}, "candidate", 0)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO media_identities(id, title, original_titles_json, year, media_type, countries_json, metadata_json, created_at, updated_at)
                VALUES('media-alpha', 'Local Poster Film', '[]', 2020, 'movie', '["China"]', '{"item_key":"douban:1001"}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO provider_identities(entity_kind, entity_id, provider, provider_id, confidence, metadata_json, created_at, updated_at)
                VALUES('media', 'media-alpha', 'douban', '1001', 1, '{}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO person_identities(id, name, aliases_json, metadata_json, created_at, updated_at)
                VALUES('person-director', 'Director A', '["D. A."]', '{"bio":"Known seeded director"}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('poster-override', 'media', 'media-alpha', 'poster', ?, 'selected', ?, ?)
                """,
                (poster_asset, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('backdrop-override', 'media', 'media-alpha', 'backdrop', ?, 'selected', ?, ?)
                """,
                (missing_asset, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('portrait-override', 'person', 'person-director', 'portrait', ?, 'selected', ?, ?)
                """,
                (portrait_asset, self.now, self.now),
            )
        feedback = FeedbackService(self.database)
        feedback.record_feedback(FeedbackEvent("more-like-this", item_key("1001"), "default", payload={"genre": "Drama"}, created_at=self.now + 50))
        feedback.record_feedback(FeedbackEvent("less-like-this", item_key("1003"), "default", payload={"genre": "Horror"}, created_at=self.now + 51))
        feedback.record_feedback(FeedbackEvent("not-tonight", item_key("1002"), "default", session_id="session-1", payload={"genre": "SessionOnly"}, created_at=self.now + 52))

    def request(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            return error.code, json.loads(error.read().decode("utf-8"))

    def assert_local_only_media(self, payload):
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("https://", serialized)
        self.assertNotIn("http://", serialized)
        self.assertNotIn("secret", serialized)

    def test_http_routes_are_registered_and_unknowns_map_to_404(self):
        status, payload = self.request("/api/v2/titles/media-alpha")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["schema_version"], 2)

        status, payload = self.request("/api/v2/titles/does-not-exist")
        self.assertEqual(status, 404)
        self.assertIn("not found", payload["error"])

    def test_title_lookup_normalizes_local_and_fallback_media_and_people(self):
        status, payload = self.request("/api/v2/titles/douban:1001")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["item_key"], item_key("1001"))
        self.assertEqual(payload["poster"]["url"], f"/media/{'a' * 64}.png")
        self.assertEqual(payload["poster"]["media_status"], "ready")
        self.assertEqual(payload["backdrop"]["url"], "")
        self.assertIn(payload["backdrop"]["media_status"], {"missing", "designed-fallback"})
        people = {person["name"]: person for person in payload["people"]}
        self.assertEqual(people["Director A"]["role"], "director")
        self.assertEqual(people["Director A"]["media_status"], "ready")
        self.assertEqual(people["Director A"]["portrait"]["url"], f"/media/{'b' * 64}.png")
        self.assertEqual(people["Actor External"]["portrait"]["url"], "")
        self.assertIn(people["Actor External"]["media_status"], {"missing", "designed-fallback"})
        self.assertEqual(people["Actor External"]["evidence_title_ids"], [item_key("1001")])
        self.assert_local_only_media(payload)

    def test_person_lookup_returns_identity_and_derived_known_for_with_local_portrait(self):
        status, payload = self.request("/api/v2/people/person-director")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["name"], "Director A")
        self.assertEqual(payload["bio"], "Known seeded director")
        self.assertEqual(payload["portrait"]["url"], f"/media/{'b' * 64}.png")
        self.assertEqual(payload["portrait"]["media_status"], "ready")
        self.assertTrue({item_key("1001"), item_key("1002")}.issubset(set(payload["evidence_title_ids"])))
        self.assertTrue(payload["known_for"])
        self.assert_local_only_media(payload)

    def test_library_cursor_is_seek_based_stable_and_validates_inputs(self):
        first_status, first = self.request("/api/v2/library?state=watched&limit=2")
        self.assertEqual(first_status, 200, first)
        self.assertEqual([row["item_key"] for row in first["items"]], [item_key("1001"), item_key("1002")])
        self.assertTrue(first["next_cursor"])
        second_status, second = self.request("/api/v2/library?state=watched&limit=2&cursor=" + urllib.parse.quote(first["next_cursor"]))
        self.assertEqual(second_status, 200, second)
        self.assertEqual([row["item_key"] for row in second["items"]], [item_key("1003")])
        self.assertFalse(set(row["item_key"] for row in first["items"]) & set(row["item_key"] for row in second["items"]))
        self.assert_local_only_media(first)
        for path in [
            "/api/v2/library?state=watched&cursor=not-a-cursor",
            "/api/v2/library?state=watched&limit=0",
            "/api/v2/library?state=bad/state",
        ]:
            with self.subTest(path=path):
                status, payload = self.request(path)
                self.assertEqual(status, 400, payload)

    def test_taste_returns_five_groups_with_evidence_and_session_feedback_isolated(self):
        status, payload = self.request("/api/v2/taste")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(set(payload["groups"]), {"stable", "conflicting", "recent", "negative", "unexplored"})
        for group_name, signals in payload["groups"].items():
            self.assertTrue(signals, group_name)
            self.assertTrue(all(signal["evidence_item_ids"] for signal in signals), group_name)
        stable_text = json.dumps(payload["groups"]["stable"], ensure_ascii=False)
        self.assertIn("Drama", stable_text)
        self.assertNotIn("SessionOnly", stable_text)
        self.assertIn("Noir", json.dumps(payload["groups"]["conflicting"], ensure_ascii=False))

    def test_universe_is_bounded_deterministic_and_explains_edges(self):
        first_status, first = self.request("/api/v2/universe?focus=douban:1001&limit=99")
        second_status, second = self.request("/api/v2/universe?focus=douban:1001&limit=99")
        self.assertEqual(first_status, 200, first)
        self.assertEqual(second_status, 200, second)
        self.assertEqual(first, second)
        self.assertLessEqual(len(first["nodes"]), 25)
        self.assertEqual(first["focus_id"], item_key("1001"))
        self.assertTrue(first["edges"])
        self.assertTrue(all(edge["score"] > 0 and edge["reasons"] and edge["reason"] for edge in first["edges"]))
        low_status, low = self.request("/api/v2/universe?focus=douban:1001&limit=2")
        self.assertEqual(low_status, 200, low)
        self.assertLessEqual(len(low["nodes"]), 3)
        lonely_status, lonely = self.request("/api/v2/universe?focus=item:custom&limit=9")
        self.assertEqual(lonely_status, 200, lonely)
        self.assertEqual(len(lonely["nodes"]), 1)
        self.assertEqual(lonely["edges"], [])
        missing_status, missing = self.request("/api/v2/universe?focus=missing&limit=9")
        self.assertEqual(missing_status, 404)
        self.assertIn("not found", missing["error"])

    def test_service_build_universe_graph_clamps_limit(self):
        self.assertIsNotNone(CatalogApi, "catalog api module should exist")
        graph = self.api.service.build_universe_graph("douban:1001", limit=999)
        self.assertLessEqual(len(graph["nodes"]), 25)
        graph = self.api.service.build_universe_graph("douban:1001", limit=1)
        self.assertLessEqual(len(graph["nodes"]), 3)


if __name__ == "__main__":
    unittest.main()
