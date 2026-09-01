import base64
import hashlib
import inspect
import io
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
from unittest import mock

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.feedback_service import FeedbackEvent, FeedbackService
from douban_recommender.global_discovery import GlobalDiscoveryReport
from douban_recommender.migrations import migrate_legacy_recommendations
from douban_recommender.models import MediaItem
from douban_recommender.web import Handler
import douban_recommender.web as web_module

try:
    from douban_recommender.catalog_api import CatalogApi, CatalogApiNotFound
except ImportError:  # RED: implementation intentionally absent at first.
    CatalogApi = None
    CatalogApiNotFound = ValueError


PNG_BYTES = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x01\x00\x00\x00\x01\x08\x02\x00\x00\x00\x90wS\xde\x00\x00\x00\x0cIDATx\x9cc``\x00\x00\x00\x04\x00\x01\xf6\x178U\x00\x00\x00\x00IEND\xaeB`\x82"
TRUSTED_STILL_URL = "https://static.tvmaze.com/uploads/images/original_untouched/fixture/scene.jpg"


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
        self.thread.join(timeout=5)
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

    def _insert_asset(self, asset_id, kind="poster", present=True, status="ready", relative=None):
        width, height = {"poster": (240, 360), "portrait": (128, 128)}.get(kind, (1, 1))
        output = io.BytesIO()
        Image.new("RGB", (width, height), f"#{asset_id[:6]}").save(output, format="PNG")
        data = output.getvalue()
        actual_asset_id = hashlib.sha256(data).hexdigest()
        relative = relative or (Path(actual_asset_id[:2]) / f"{actual_asset_id}.png")
        relative = Path(relative)
        path = self.media_root / relative
        if present:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(data)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO asset_files(
                    asset_id, sha256, relative_path, mime_type, extension, width, height,
                    byte_size, source_url, kind, status, created_at, last_verified_at
                ) VALUES(?, ?, ?, 'image/png', '.png', ?, ?, ?, 'https://secret.example/source.png', ?, ?, ?, ?)
                """,
                (
                    actual_asset_id,
                    actual_asset_id,
                    relative.as_posix(),
                    width,
                    height,
                    len(data),
                    kind,
                    status,
                    self.now,
                    self.now,
                ),
            )
        return actual_asset_id

    def _bind_item_poster(self, key, asset_id=None):
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO user_asset_overrides(
                    id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at
                ) VALUES(?, 'media', ?, 'poster', ?, 'selected', ?, ?)
                """,
                (f"poster:{key}", key, asset_id or self.poster_asset, self.now, self.now),
            )

    def _seed_catalog(self):
        poster_asset = self._insert_asset("a" * 64, "poster", present=True)
        portrait_asset = self._insert_asset("b" * 64, "portrait", present=True)
        missing_asset = self._insert_asset("c" * 64, "backdrop", present=False)
        self.poster_asset = poster_asset
        self.portrait_asset = portrait_asset
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
            "raw": {
                "comment": "My grounded short review",
                "people": [
                    {
                        "name": "Actor External",
                        "photo": "Headshot http://cdn.example/actor.jpg?api_key=secret should disappear",
                        "bearer": "abc123",
                        "api_key": "stripe-test-key-placeholder",
                        "nested": {"authorization": "Bearer tokenvalue"},
                    }
                ],
                "credits": {
                    "text": "Credit page https://example.test/credit?token=secret and jwt abc.def.ghi",
                    "cookie": "session=secret",
                },
            },
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
        legacy_missing = {
            "title": "Forged Legacy Poster",
            "media_type": "movie",
            "douban_id": "1005",
            "cover": f"/media/{'d' * 64}.png",
        }
        self._insert_library(item_key("1001"), alpha, "watched", 40)
        self._insert_library(item_key("1002"), beta, "watched", 30)
        self._insert_library(item_key("1003"), gamma, "watched", 20)
        self._insert_library(item_key("1004"), wish, "wish", 10)
        self._insert_library(item_key("1005"), legacy_missing, "candidate", 5)
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
        feedback.record_feedback(FeedbackEvent("tonight-candidate", item_key("1002"), "default", session_id="session-1", payload={"genre": "TonightOnly"}, created_at=self.now + 53))

    def request(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def post(self, path, payload):
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=json.dumps(payload).encode("utf-8"),
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def assert_local_only_media(self, payload):
        serialized = json.dumps(payload, ensure_ascii=False)
        self.assertNotIn("https://", serialized)
        self.assertNotIn("http://", serialized)
        self.assertNotIn("secret", serialized)

    def assert_catalog_payload_sanitized(self, payload):
        sensitive_words = (
            "http://",
            "https://",
            "secret",
            "cookie",
            "token",
            "api_key",
            "jwt",
            "private_key",
            "subscription",
            "password",
            "authorization",
            "bearer",
            "stripe-test-key-placeholder",
        )
        serialized = json.dumps(payload, ensure_ascii=False).lower()
        for word in sensitive_words:
            self.assertNotIn(word, serialized)

        def walk(value):
            if isinstance(value, dict):
                for key, nested in value.items():
                    key_text = str(key).lower()
                    for word in sensitive_words[3:]:
                        self.assertNotIn(word, key_text)
                    walk(nested)
            elif isinstance(value, list):
                for nested in value:
                    walk(nested)
            elif isinstance(value, str):
                text = value.lower()
                for word in sensitive_words:
                    self.assertNotIn(word, text)

        walk(payload)

    def test_http_routes_are_registered_and_unknowns_map_to_404(self):
        status, payload = self.request("/api/v2/titles/media-alpha")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["schema_version"], 2)

        status, payload = self.request("/api/v2/titles/does-not-exist")
        self.assertEqual(status, 404)
        self.assertIn("not found", payload["error"])

    def test_catalog_api_uses_shared_safe_route_segment_validator(self):
        class EchoService:
            def title(self, value):
                return {"value": value}

        api = CatalogApi(self.database, service=EchoService())
        for unsafe in ("external:movie%201", "douban:1001?query", "item:abc#fragment", "derived:bad\x00segment"):
            with self.subTest(unsafe=unsafe):
                with self.assertRaises(CatalogApiNotFound):
                    api.get_title(unsafe)
        for safe in ("external:movie-1", "douban:1001", "item:abc_1", "derived:related-item"):
            with self.subTest(safe=safe):
                self.assertEqual(api.get_title(safe), {"value": safe})

    def test_title_lookup_normalizes_local_and_fallback_media_and_people(self):
        status, payload = self.request("/api/v2/titles/douban:1001")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["item_key"], item_key("1001"))
        self.assertEqual(payload["poster"]["url"], f"/media/{self.poster_asset}.png")
        self.assertEqual(payload["poster"]["media_status"], "ready")
        self.assertEqual(payload["backdrop"]["url"], "")
        self.assertIn(payload["backdrop"]["media_status"], {"missing", "designed-fallback"})
        people = {person["name"]: person for person in payload["people"]}
        self.assertEqual(payload["item"]["raw"]["comment"], "My grounded short review")
        self.assertEqual(people["Director A"]["role"], "director")
        self.assertEqual(people["Director A"]["media_status"], "ready")
        self.assertEqual(people["Director A"]["portrait"]["url"], f"/media/{self.portrait_asset}.png")
        self.assertEqual(people["Actor External"]["portrait"]["url"], "")
        self.assertIn(people["Actor External"]["media_status"], {"missing", "designed-fallback"})
        self.assertEqual(people["Actor External"]["evidence_title_ids"], [item_key("1001")])
        self.assert_local_only_media(payload)

    def test_title_serialization_uses_sourced_chinese_alias_and_keeps_original_title(self):
        key = "external:localized-title"
        original_title = "The Real History of Science Fiction"
        localized_title = "\u79d1\u5e7b\u771f\u53f2"
        self._insert_library(
            key,
            {
                "title": original_title,
                "media_type": "series",
                "year": 2014,
                "raw": {
                    "original_title": original_title,
                    "aliases": [localized_title],
                    "provider_ids": {"douban": "25851561"},
                },
            },
            "candidate",
            55,
        )

        payload = self.api.get_title(key)

        self.assertEqual(original_title, payload["title"])
        self.assertEqual(localized_title, payload["display_title"])
        self.assertEqual(original_title, payload["original_title"])
        self.assertEqual("douban", payload["title_localization_source"])

    def test_title_serialization_uses_curated_chinese_names_for_verified_tvmaze_ids(self):
        verified_titles = {
            "61855": ("Mystery Incorporated", "\u795e\u79d8\u516c\u53f8"),
            "53397": ("Mystery Island", "\u795e\u79d8\u5c9b"),
            "1602": ("Prophets of Science Fiction", "\u79d1\u5e7b\u5148\u77e5"),
            "28400": ("Mystery Map", "\u795e\u79d8\u5730\u56fe"),
        }

        for offset, (provider_id, (original_title, localized_title)) in enumerate(verified_titles.items(), start=1):
            key = f"external:tvmaze-{provider_id}"
            self._insert_library(
                key,
                {
                    "title": original_title,
                    "media_type": "series",
                    "year": 2000 + offset,
                    "raw": {
                        "original_title": original_title,
                        "provider_ids": {"tvmaze": provider_id},
                    },
                },
                "candidate",
                60 + offset,
            )

            with self.subTest(provider_id=provider_id):
                payload = self.api.get_title(key)
                self.assertEqual(original_title, payload["title"])
                self.assertEqual(localized_title, payload["display_title"])
                self.assertEqual(original_title, payload["original_title"])
                self.assertEqual("curated_catalog", payload["title_localization_source"])

    def test_title_serialization_does_not_promote_unsourced_chinese_alias(self):
        key = "external:unsourced-title"
        original_title = "Mystery Without Verified Localization"
        self._insert_library(
            key,
            {
                "title": original_title,
                "media_type": "movie",
                "raw": {
                    "original_title": original_title,
                    "aliases": ["\u672a\u6838\u5bf9\u7684\u4e2d\u6587\u540d"],
                },
            },
            "candidate",
            56,
        )

        payload = self.api.get_title(key)

        self.assertEqual(original_title, payload["display_title"])
        self.assertEqual(original_title, payload["original_title"])
        self.assertEqual("", payload["title_localization_source"])

    def test_title_search_matches_single_original_title_field(self):
        key = "external:single-original-title"
        self._insert_library(
            key,
            {
                "title": "\u79d1\u5e7b\u771f\u53f2",
                "media_type": "series",
                "raw": {
                    "original_title": "The Real History of Science Fiction",
                    "provider_ids": {"douban": "25851561"},
                },
            },
            "candidate",
            57,
        )

        payload = self.api.search_titles({"q": ["The Real History of Science Fiction"]})

        self.assertEqual(key, payload["items"][0]["id"])
        self.assertEqual("alias", payload["items"][0]["match_kind"])

    def test_title_people_use_verified_proxied_portraits_when_local_assets_are_not_ready(self):
        key = "douban:portrait-proxy"
        self._insert_library(
            key,
            {
                "title": "人物补图作品",
                "media_type": "电视剧",
                "directors": ["导演甲"],
                "casts": ["演员乙"],
                "raw": {
                    "people_photos": {
                        "导演甲": "https://img3.doubanio.com/view/celebrity/m/public/p100.jpg",
                        "演员乙": "https://img1.doubanio.com/view/celebrity/m/public/p200.jpg",
                    }
                },
            },
            "watched",
            54,
        )

        payload = self.api.get_title(key)
        people = {person["name"]: person for person in payload["people"]}

        self.assertEqual("ready", people["导演甲"]["portrait"]["media_status"])
        self.assertEqual("ready", people["演员乙"]["portrait"]["media_status"])
        self.assertTrue(people["导演甲"]["portrait"]["url"].startswith("/api/image-proxy?url="))
        self.assertTrue(people["演员乙"]["portrait"]["url"].startswith("/api/image-proxy?url="))
        self.assert_local_only_media(payload)

    def test_title_people_do_not_present_provider_default_avatar_as_real_portrait(self):
        key = "douban:portrait-default"
        self._insert_library(
            key,
            {
                "title": "默认头像过滤",
                "media_type": "电视剧",
                "directors": ["导演甲"],
                "casts": ["演员乙"],
                "raw": {
                    "people_photos": {
                        "导演甲": "https://img1.doubanio.com/f/vendors/pics/personage-default-medium.png",
                        "演员乙": "https://img1.doubanio.com/view/celebrity/m/public/p200.jpg",
                    }
                },
            },
            "watched",
            54,
        )

        payload = self.api.get_title(key)
        people = {person["name"]: person for person in payload["people"]}

        self.assertNotEqual("ready", people["导演甲"]["portrait"]["media_status"])
        self.assertEqual("", people["导演甲"]["portrait"]["url"])
        self.assertEqual("ready", people["演员乙"]["portrait"]["media_status"])

    def test_title_uses_verified_proxied_poster_when_local_asset_is_not_ready(self):
        key = "douban:poster-proxy"
        self._insert_library(
            key,
            {
                "title": "海报补图作品",
                "media_type": "电影",
                "cover": "https://img3.doubanio.com/view/photo/m_ratio_poster/public/p300.jpg",
            },
            "watched",
            53,
        )

        payload = self.api.get_title(key)

        self.assertEqual("ready", payload["poster"]["media_status"])
        self.assertTrue(payload["poster"]["url"].startswith("/api/image-proxy?url="))
        self.assert_local_only_media(payload)

    def test_title_enrichment_route_persists_summary_without_changing_library_state(self):
        def enrich(items, **_kwargs):
            items[0].summary = "Fresh verified synopsis"
            items[0].douban_rating = 8.7
            items[0].genres = [*items[0].genres, "Thriller"]
            items[0].raw.update({
                "stills": ["https://qnmob3.doubanio.com/view/photo/large/public/p1002.jpg"],
                "ratings": {"douban": 8.7, "imdb": 8.2},
                "rating_votes": {"douban": 1234},
                "comment_count": 321,
                "review_count": 45,
            })
            return items

        with mock.patch("douban_recommender.catalog_api.enrich_media_items", side_effect=enrich):
            status, payload = self.post("/api/v2/titles/douban:1002/enrich", {})

        self.assertEqual(200, status, payload)
        self.assertEqual("Fresh verified synopsis", payload["item"]["summary"])
        self.assertEqual(8.7, payload["item"]["douban_rating"])
        self.assertEqual(8.2, payload["item"]["raw"]["ratings"]["imdb"])
        self.assertEqual(321, payload["item"]["raw"]["comment_count"])
        self.assertEqual(45, payload["item"]["raw"]["review_count"])
        self.assertEqual(1, len(payload["stills"]))
        self.assertTrue(payload["stills"][0]["url"].startswith("/api/image-proxy?url="))
        self.assertEqual("watched", payload["state"])
        persisted = self.api.get_title("douban:1002")
        self.assertEqual("Fresh verified synopsis", persisted["item"]["summary"])
        self.assertIn("Thriller", persisted["item"]["genres"])

    def test_title_enrichment_localizes_and_persists_an_english_provider_summary(self):
        english = "Historian Dominic Sandbrook and leading creators tell the story of science fiction."
        chinese = "\u5386\u53f2\u5b66\u5bb6\u591a\u7c73\u5c3c\u514b\u00b7\u6851\u5fb7\u5e03\u9c81\u514b\u548c\u4e3b\u8981\u521b\u4f5c\u8005\u8bb2\u8ff0\u4e86\u79d1\u5e7b\u5c0f\u8bf4\u7684\u6545\u4e8b\u3002"

        def enrich(items, **_kwargs):
            item = items[0]
            item.summary = english
            item.douban_rating = 8.5
            item.genres = ["\u79d1\u5e7b", "\u5386\u53f2"]
            item.directors = ["Ben Southwell"]
            item.casts = ["Dominic Sandbrook"]
            item.raw.update({
                "stills": ["https://img.example/science-fiction.jpg"],
                "people_photos": {
                    "Ben Southwell": "https://img.example/ben.jpg",
                    "Dominic Sandbrook": "https://img.example/dominic.jpg",
                },
            })
            return items

        def localize(item):
            item.raw["summary_original"] = item.summary
            item.raw["summary_source"] = "machine_translation:google"
            item.raw["summary_generated"] = True
            item.summary = chinese
            return True

        with (
            mock.patch("douban_recommender.catalog_api.enrich_media_items", side_effect=enrich),
            mock.patch("douban_recommender.catalog_api.enrich_public_metadata", side_effect=localize) as public_enrich,
        ):
            payload = self.api.enrich_title("douban:1002")

        public_enrich.assert_called_once()
        self.assertEqual(chinese, payload["item"]["summary"])
        self.assertEqual("machine_translation:google", payload["item"]["raw"]["summary_source"])
        persisted = self.api.get_title("douban:1002")
        self.assertEqual(chinese, persisted["item"]["summary"])
        self.assertEqual(english, persisted["item"]["raw"]["summary_original"])

    def test_title_enrichment_skips_public_fallback_when_verified_core_metadata_is_complete(self):
        def enrich(items, **_kwargs):
            item = items[0]
            item.summary = "Verified synopsis"
            item.douban_rating = 8.7
            item.genres = ["Drama", "Thriller"]
            item.directors = ["Director A"]
            item.casts = ["Actor C"]
            item.raw["stills"] = ["https://qnmob3.doubanio.com/view/photo/large/public/p1002.jpg"]
            return items

        with (
            mock.patch("douban_recommender.catalog_api.enrich_media_items", side_effect=enrich),
            mock.patch("douban_recommender.catalog_api.enrich_public_metadata", return_value=False) as public_enrich,
        ):
            payload = self.api.enrich_title("douban:1002")

        public_enrich.assert_not_called()
        self.assertEqual("Verified synopsis", payload["item"]["summary"])
        self.assertEqual(["Director A"], payload["item"]["directors"])
        self.assertEqual(["Actor C"], payload["item"]["casts"])
        self.assertEqual(1, len(payload["stills"]))

    def test_title_enrichment_keeps_an_unbound_library_key_stable_when_douban_identity_is_found(self):
        key = "item:unbound-enrichment"
        self._insert_library(
            key,
            {"title": "待绑定作品", "media_type": "电影", "douban_id": "", "summary": ""},
            "wish",
            56,
        )

        def enrich(items, **_kwargs):
            items[0].douban_id = "424242"
            items[0].url = "https://movie.douban.com/subject/424242/"
            items[0].summary = "已核验的新剧情简介"
            return items

        with mock.patch("douban_recommender.catalog_api.enrich_media_items", side_effect=enrich):
            payload = self.api.enrich_title(key)

        self.assertEqual(key, payload["item_key"])
        self.assertEqual("wish", payload["state"])
        self.assertEqual("424242", payload["item"]["douban_id"])
        self.assertEqual("已核验的新剧情简介", payload["item"]["summary"])
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT item_key FROM library_items WHERE item_key IN (?, ?) ORDER BY item_key",
                (key, "douban:424242"),
            ).fetchall()
        self.assertEqual([key], [str(row["item_key"]) for row in rows])
        self.assertEqual(key, self.api.get_title("douban:424242")["item_key"])

    def test_title_enrichment_does_not_resurrect_metadata_from_a_repaired_wrong_identity(self):
        key = "douban:34943015"
        self._insert_library(
            key,
            {
                "title": "机智医生生活",
                "year": 2020,
                "media_type": "电视剧",
                "douban_id": "34943015",
                "source": "title_seed",
                "douban_rating": 6.6,
                "genres": ["剧情", "喜剧", "动画", "冒险"],
                "countries": ["韩国", "日本"],
                "languages": ["日语"],
                "directors": ["申元浩", "错误导演"],
                "casts": ["曹政奭", "错误演员"],
                "summary": "错误的宝可梦剧情简介",
                "raw": {
                    "aliases": ["精灵宝可梦：可可"],
                    "stills": ["https://img.example/pokemon.jpg"],
                    "ratings": {"douban": 6.6},
                    "provider_ids": {"douban": "34943015"},
                    "people_photos": {"错误演员": "https://img.example/wrong-person.jpg"},
                },
            },
            "candidate",
            57,
        )
        self._bind_item_poster(key)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO asset_candidates(
                    id, entity_kind, entity_id, kind, source, url, confidence,
                    status, metadata_json, created_at, updated_at
                ) VALUES('wrong-poster-candidate', 'media', ?, 'poster', 'fixture',
                         'https://img.example/pokemon.jpg', 1.0, 'ready', '{}', ?, ?)
                """,
                (key, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO resolution_jobs(
                    id, entity_kind, entity_id, kind, priority, state, current_source,
                    attempts_json, error, created_at, updated_at
                ) VALUES('wrong-poster-job', 'media', ?, 'poster', 1, 'queued',
                         'fixture', '[]', '', ?, ?)
                """,
                (key, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO provider_identities(
                    entity_kind, entity_id, provider, provider_id, confidence,
                    metadata_json, created_at, updated_at
                ) VALUES('media', ?, 'douban', '34943015', 1.0, '{}', ?, ?)
                """,
                (key, self.now, self.now),
            )

        with (
            mock.patch("douban_recommender.catalog_api.enrich_media_items", side_effect=lambda items, **_kwargs: items),
            mock.patch("douban_recommender.catalog_api.enrich_public_metadata", return_value=False),
        ):
            payload = self.api.enrich_title(key)

        item = payload["item"]
        self.assertEqual("33464863", item["douban_id"])
        self.assertEqual(["剧情", "喜剧"], item["genres"])
        self.assertEqual(["韩国"], item["countries"])
        self.assertNotIn("日语", item["languages"])
        self.assertNotIn("错误导演", item["directors"])
        self.assertNotIn("错误演员", item["casts"])
        self.assertNotIn("宝可梦", item["summary"])
        self.assertNotIn("精灵宝可梦：可可", item["raw"].get("aliases", []))
        self.assertNotIn("https://img.example/pokemon.jpg", item["raw"].get("stills", []))
        self.assertNotEqual("34943015", item["raw"].get("provider_ids", {}).get("douban"))
        self.assertNotEqual(f"/media/{self.poster_asset}.png", payload["poster"]["url"])
        if payload["poster"]["media_status"] == "ready":
            self.assertTrue(payload["poster"]["url"].startswith("/api/image-proxy?url="))
        with self.database.connection() as connection:
            stale_provider = connection.execute(
                """
                SELECT 1 FROM provider_identities
                WHERE entity_kind='media' AND entity_id=? AND provider='douban' AND provider_id='34943015'
                """,
                (key,),
            ).fetchone()
            stale_candidates = connection.execute(
                "SELECT COUNT(*) AS count FROM asset_candidates WHERE entity_kind='media' AND entity_id=?",
                (key,),
            ).fetchone()["count"]
            stale_jobs = connection.execute(
                "SELECT COUNT(*) AS count FROM resolution_jobs WHERE entity_kind='media' AND entity_id=?",
                (key,),
            ).fetchone()["count"]
            stale_overrides = connection.execute(
                "SELECT COUNT(*) AS count FROM user_asset_overrides WHERE entity_kind='media' AND entity_id=?",
                (key,),
            ).fetchone()["count"]
        self.assertIsNone(stale_provider)
        self.assertEqual(0, stale_candidates)
        self.assertEqual(0, stale_jobs)
        self.assertEqual(0, stale_overrides)

    def test_title_without_media_identity_uses_item_key_asset_binding(self):
        key = "item:no-identity"
        self._insert_library(
            key,
            {"title": "No identity title", "media_type": "电影", "cover": "https://img.example/external.jpg"},
            "watched",
            55,
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('override-no-identity', 'media', ?, 'poster', ?, 'selected', ?, ?)
                """,
                (key, self.poster_asset, self.now, self.now),
            )

        payload = self.api.get_title(key)

        self.assertEqual(payload["poster"]["media_status"], "ready")
        self.assertTrue(payload["poster"]["url"].startswith("/media/"))

    def test_title_lookup_accepts_frontend_encoded_item_key(self):
        status, payload = self.request("/api/v2/titles/douban%3A1001")

        self.assertEqual(status, 200)
        self.assertEqual(payload["item_key"], "douban:1001")

    def test_person_lookup_returns_identity_and_derived_known_for_with_local_portrait(self):
        status, payload = self.request("/api/v2/people/person-director")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(payload["name"], "Director A")
        self.assertEqual(payload["bio"], "Known seeded director")
        self.assertEqual(payload["portrait"]["url"], f"/media/{self.portrait_asset}.png")
        self.assertEqual(payload["portrait"]["media_status"], "ready")
        self.assertTrue({item_key("1001"), item_key("1002")}.issubset(set(payload["evidence_title_ids"])))
        self.assertTrue(payload["known_for"])
        self.assert_local_only_media(payload)

    def test_library_cursor_is_seek_based_stable_and_validates_inputs(self):
        first_status, first = self.request("/api/v2/library?state=watched&limit=2")
        self.assertEqual(first_status, 200, first)
        self.assertEqual([row["item_key"] for row in first["items"]], [item_key("1001"), item_key("1002")])
        self.assertEqual(first["counts"]["watched"], 3)
        self.assertGreaterEqual(first["counts"]["all"], first["counts"]["watched"])
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

    def test_recent_history_prefers_douban_activity_date_and_exposes_episode_progress(self):
        key = item_key("1080")
        self._insert_library(
            key,
            {
                "title": "最近追剧样本",
                "media_type": "series",
                "year": 2026,
                "douban_id": "1080",
                "genres": ["剧情"],
                "raw": {
                    "activity_date": "2026-07-07",
                    "watched_date": "2026-07-07",
                    "episodes_watched": 3,
                    "total_episodes": 12,
                },
            },
            "watched",
            120,
        )

        status, payload = self.request("/api/v2/recent?limit=20")

        self.assertEqual(200, status, payload)
        recent = next(row for row in payload["items"] if row["item_key"] == key)
        self.assertEqual("2026-07-07", recent["watched_date"])
        self.assertEqual("douban", recent["watch_source"])
        self.assertEqual("豆瓣看过日期", recent["watch_source_label"])
        self.assertEqual("第 3 / 12 集", recent["watch_progress"]["label"])
        self.assertEqual(25.0, recent["watch_progress"]["percent"])

    def test_recent_history_uses_feedback_aliases_and_ignores_undone_event_only_items(self):
        key = item_key("1081")
        self._insert_library(
            key,
            {
                "title": "别名关联样本",
                "media_type": "movie",
                "year": 2025,
                "douban_id": "1081",
            },
            "watched",
            121,
        )
        feedback = FeedbackService(self.database)
        watched_at = self.now + 900
        feedback.record_feedback(FeedbackEvent(
            "watched",
            "external:alias-only",
            "default",
            payload={"identity_aliases": [key]},
            created_at=watched_at,
        ))
        event_only_id = feedback.record_feedback(FeedbackEvent(
            "watched",
            "external:event-only",
            "default",
            payload={
                "item": {
                    "title": "已撤销的临时记录",
                    "media_type": "movie",
                    "douban_id": "event-only-1082",
                }
            },
            created_at=self.now + 901,
        ))
        feedback.undo_feedback(event_only_id)

        payload = self.api.recent({"limit": ["100"]})

        recent = next(row for row in payload["items"] if row["item_key"] == key)
        self.assertEqual("feedback", recent["watch_source"])
        self.assertEqual(watched_at, recent["watched_at"])
        self.assertNotIn("已撤销的临时记录", {row["title"] for row in payload["items"]})

    def test_recent_history_serializes_only_the_requested_window(self):
        with mock.patch.object(
            self.api.service,
            "serialize_title",
            wraps=self.api.service.serialize_title,
        ) as serializer:
            payload = self.api.service.recent_history(limit=2)

        self.assertEqual(2, len(payload["items"]))
        self.assertGreater(payload["count"], 2)
        self.assertTrue(payload["has_more"])
        self.assertEqual(2, serializer.call_count)

    def test_observatory_loads_recent_history_and_online_discovery_concurrently(self):
        barrier = threading.Barrier(2, timeout=1.0)

        def recent_history(profile_key, limit):
            barrier.wait()
            return {"count": 0, "items": [], "has_more": False}

        def latest_discovery(profile_key, limit, *, refresh=False):
            barrier.wait()
            return {"status": "live", "live_count": 1, "items": [{"item_key": "external:fixture"}]}

        with (
            mock.patch.object(self.api.service, "recent_history", side_effect=recent_history),
            mock.patch.object(self.api.service, "latest_discovery", side_effect=latest_discovery),
        ):
            payload = self.api.service.observatory(limit=8, refresh=True)

        self.assertEqual(0, payload["summary"]["recent_count"])
        self.assertEqual(1, payload["summary"]["live_count"])
        self.assertEqual("live", payload["summary"]["latest_status"])

    def test_latest_discovery_caches_live_results_and_refresh_forces_provider_call(self):
        live = MediaItem(
            title="实时新片样本",
            media_type="movie",
            year=2026,
            genres=["科幻"],
            countries=["中国大陆"],
            douban_id="tvmaze-90001",
            cover="https://static.tvmaze.com/uploads/images/original_untouched/1/1.jpg",
            summary="一部用于验证在线新片聚合的中文简介。",
            source="global:tvmaze",
            vote_count=4321,
            raw={
                "premiered": "2026-08-29",
                "ratings": {"tvmaze": 8.7},
                "rating_votes": {"tvmaze_weight": 4321},
                "discovery_sources": ["tvmaze"],
                "discovered_at": self.now,
            },
        )
        report = GlobalDiscoveryReport(
            items=[live],
            source_counts={"tvmaze": 1},
            source_status={"tvmaze": {"state": "ready", "count": 1}},
            status="complete",
            generated_at=self.now,
        )

        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ) as discover:
            first = self.api.latest({"limit": ["8"]})
            second = self.api.latest({"limit": ["8"]})
            refreshed = self.api.latest({"limit": ["8"], "refresh": ["1"]})

        self.assertEqual(2, discover.call_count)
        self.assertEqual(first["items"], second["items"])
        self.assertEqual("live", refreshed["status"])
        self.assertEqual("2026-08-29", refreshed["items"][0]["release_date"])
        self.assertEqual(8.7, refreshed["items"][0]["source_ratings"]["tvmaze"])
        self.assertTrue(refreshed["items"][0]["poster"]["url"].startswith("/api/image-proxy?url="))
        self.assert_catalog_payload_sanitized(refreshed)

    def test_latest_discovery_hides_unlocalized_latin_and_japanese_titles(self):
        def live(title, provider_id, source):
            return MediaItem(
                title=title,
                media_type="动漫" if source == "anilist" else "电视剧",
                year=2026,
                douban_id=f"{source}-{provider_id}",
                cover="https://static.tvmaze.com/uploads/images/original_untouched/fixture/poster.jpg",
                source=f"global:{source}",
                raw={
                    "provider_ids": {source: provider_id},
                    "discovery_sources": [source],
                },
            )

        report = GlobalDiscoveryReport(
            items=[
                live("Action Pack", "latin-only", "tvmaze"),
                live("人生切割术", "localized", "tvmaze"),
                live("リコリス・リコイル", "kana-only", "anilist"),
            ],
            source_counts={"tvmaze": 2, "anilist": 1},
            source_status={
                "tvmaze": {"state": "ready", "count": 2},
                "anilist": {"state": "ready", "count": 1},
            },
            status="complete",
            generated_at=self.now,
        )

        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            payload = self.api.latest({"limit": ["8"], "refresh": ["1"]})

        live_titles = {
            item["display_title"]
            for item in payload["items"]
            if item.get("is_live")
        }
        self.assertNotIn("Action Pack", live_titles)
        self.assertIn("人生切割术", live_titles)
        self.assertNotIn("リコリス・リコイル", live_titles)
        self.assertEqual(1, payload["live_count"])

    def test_latest_discovery_uses_verified_mainland_title_for_apple_provider_id(self):
        live = MediaItem(
            title="星際效應",
            media_type="movie",
            year=2014,
            genres=["Science Fiction"],
            douban_id="apple-movie-965491522",
            cover="https://is1-ssl.mzstatic.com/image/thumb/movie.png/600x900bb.jpg",
            summary="一群探險家穿越蟲洞，尋找人類未來的可能。",
            source="global:apple_movies",
            raw={
                "provider_ids": {"apple_movies": "965491522"},
                "discovery_sources": ["apple_movies"],
            },
        )
        report = GlobalDiscoveryReport(
            items=[live],
            source_counts={"apple_movies": 1},
            source_status={"apple_movies": {"state": "ready", "count": 1}},
            status="complete",
            generated_at=self.now,
        )

        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            payload = self.api.latest({"limit": ["8"], "refresh": ["1"]})

        self.assertEqual("星际穿越", payload["items"][0]["display_title"])
        self.assertEqual("科幻", payload["items"][0]["genres"][0])

    def test_latest_discovery_balances_sources_in_the_combined_feed(self):
        def live(title, provider_id, source, release_date, rating=None):
            ratings = {source: rating} if rating else {}
            return MediaItem(
                title=title,
                media_type={"apple_movies": "电影", "tvmaze": "电视剧", "anilist": "动漫"}[source],
                year=int(release_date[:4]),
                douban_id=f"{source}-{provider_id}",
                cover="https://static.tvmaze.com/uploads/images/original_untouched/fixture/poster.jpg",
                source=f"global:{source}",
                raw={
                    "release_date": release_date,
                    "provider_ids": {source: provider_id},
                    "discovery_sources": [source],
                    "ratings": ratings,
                },
            )

        items = [
            live(f"热门电影{i}", f"movie-{i}", "apple_movies", f"2026-12-{20 - i:02d}")
            for i in range(6)
        ]
        items.extend([
            live("在线剧集甲", "series-a", "tvmaze", "2026-08-30", 8.4),
            live("在线剧集乙", "series-b", "tvmaze", "2026-08-29", 8.1),
            live("在线动画甲", "anime-a", "anilist", "2026-08-28", 9.1),
            live("在线动画乙", "anime-b", "anilist", "2026-08-27", 8.9),
        ])
        report = GlobalDiscoveryReport(
            items=items,
            source_counts={"apple_movies": 6, "tvmaze": 2, "anilist": 2},
            source_status={
                "apple_movies": {"state": "ready", "count": 6},
                "tvmaze": {"state": "ready", "count": 2},
                "anilist": {"state": "ready", "count": 2},
            },
            status="complete",
            generated_at=self.now,
        )

        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            payload = self.api.latest({"limit": ["6"], "refresh": ["1"]})

        displayed_sources = {
            item["discovery_sources"][0]
            for item in payload["items"][:6]
            if item.get("is_live") and item.get("discovery_sources")
        }
        self.assertEqual({"apple_movies", "tvmaze", "anilist"}, displayed_sources)
        self.assertEqual("热门电影0", payload["items"][0]["display_title"])

    def test_latest_discovery_merges_local_duplicate_into_live_card(self):
        local_key = item_key("36962219")
        self._insert_library(
            local_key,
            {
                "title": "小黄人与大怪兽",
                "media_type": "movie",
                "year": 2026,
                "douban_rating": 6.7,
                "vote_count": 39147,
                "genres": ["动画", "喜剧"],
                "countries": ["美国"],
                "directors": ["皮埃尔·柯芬"],
                "casts": ["特雷·帕克"],
                "summary": "本地资料中的完整中文简介。",
                "douban_id": "36962219",
                "raw": {
                    "aliases": ["小小兵&大怪兽(台)"],
                    "original_title": "Minions & Monsters",
                    "ratings": {"douban": 6.7},
                    "rating_votes": {"douban": 39147},
                    "stills": [TRUSTED_STILL_URL],
                },
            },
            "candidate",
            60,
        )
        self._bind_item_poster(local_key)

        live = MediaItem(
            title="小小兵&大怪兽",
            media_type="movie",
            year=2026,
            douban_id="apple-movie-6781935910",
            cover="https://is1-ssl.mzstatic.com/image/thumb/movie.png/600x900bb.jpg",
            source="global:apple_movies",
            raw={
                "provider_ids": {"apple_movies": "6781935910"},
                "discovery_sources": ["apple_movies"],
                "release_date": "2026-07-01",
            },
        )
        report = GlobalDiscoveryReport(
            items=[live],
            source_counts={"apple_movies": 1},
            source_status={"apple_movies": {"state": "ready", "count": 1}},
            status="complete",
            generated_at=self.now,
        )

        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            payload = self.api.latest({"limit": ["8"], "refresh": ["1"]})

        matches = [item for item in payload["items"] if item.get("display_title") == "小黄人与大怪兽"]
        self.assertEqual(1, len(matches))
        self.assertTrue(matches[0]["is_live"])
        self.assertEqual(6.7, matches[0]["douban_rating"])
        self.assertEqual(6.7, matches[0]["source_ratings"]["douban"])
        self.assertNotIn(local_key, [item.get("item_key") for item in payload["items"]])

    def test_latest_discovery_caps_each_provider_batch_for_interactive_latency(self):
        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=GlobalDiscoveryReport(status="empty", generated_at=self.now),
        ) as discover:
            self.api.latest({"limit": ["30"], "refresh": ["1"]})

        config = discover.call_args.kwargs["config"]
        self.assertEqual(24, config.max_per_source)

    def test_latest_discovery_restores_persisted_online_results_immediately_after_restart(self):
        live = MediaItem(
            title="重启缓存新片",
            media_type="movie",
            year=2026,
            genres=["剧情"],
            douban_id="apple-movie-90002",
            cover="https://is1-ssl.mzstatic.com/image/thumb/movie.png/600x900bb.jpg",
            summary="用于验证服务重启后立即恢复在线结果。",
            source="global:apple_movies",
            raw={
                "release_date": "2026-08-30",
                "discovery_sources": ["apple_movies"],
                "provider_ids": {"apple_movies": "90002"},
            },
        )
        report = GlobalDiscoveryReport(
            items=[live],
            source_counts={"apple_movies": 1},
            source_status={"apple_movies": {"state": "ready", "count": 1}},
            status="complete",
            generated_at=self.now,
        )

        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            first = self.api.latest({"limit": ["8"]})

        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT key, payload_json FROM ui_snapshots WHERE key LIKE 'latest-discovery:%' LIMIT 1"
            ).fetchone()
            self.assertIsNotNone(row)
            self.assertTrue(row["key"].startswith("latest-discovery:v6:"))
            snapshot = json.loads(row["payload_json"])
            snapshot["expires_at"] = 0
            snapshot["fetched_at"] = time.time() - 600
            connection.execute(
                "UPDATE ui_snapshots SET payload_json = ? WHERE key = ?",
                (json.dumps(snapshot, ensure_ascii=False), row["key"]),
            )

        restarted = CatalogApi(self.database, media_root=self.media_root)
        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            side_effect=AssertionError("persistent startup cache should avoid a blocking provider call"),
        ) as discover:
            restored = restarted.latest({"limit": ["8"]})

        self.assertEqual(0, discover.call_count)
        self.assertTrue(restored["is_stale"])
        self.assertEqual(first["items"], restored["items"])
        self.assertEqual("Apple TV 热门电影", restored["items"][0]["source_labels"][0])
        self.assertTrue(restored["items"][0]["poster"]["url"].startswith("/api/image-proxy?url="))

    def test_online_discovery_title_opens_from_snapshot_without_polluting_library(self):
        live = MediaItem(
            title="我的鯨魚老爸",
            media_type="movie",
            year=2022,
            genres=["Drama"],
            countries=["United States"],
            languages=["English"],
            directors=["Darren Aronofsky"],
            douban_id="apple-movie-1687094414",
            cover="https://is1-ssl.mzstatic.com/image/thumb/movie.png/600x900bb.jpg",
            summary="一名隱居教師試圖重新修補與女兒的關係。",
            source="global:apple_movies",
            vote_count=12345,
            raw={
                "provider_ids": {"apple_movies": "1687094414"},
                "discovery_sources": ["apple_movies"],
                "ratings": {"imdb": 7.6},
                "rating_votes": {"imdb": 12345},
                "release_date": "2022-12-09",
            },
        )
        report = GlobalDiscoveryReport(
            items=[live],
            source_counts={"apple_movies": 1},
            source_status={"apple_movies": {"state": "ready", "count": 1}},
            status="complete",
            generated_at=self.now,
        )
        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            latest = self.api.latest({"limit": ["8"], "refresh": ["1"]})

        key = latest["items"][0]["item_key"]
        detail = self.api.get_title(key)
        self.assertEqual("鲸", detail["display_title"])
        self.assertTrue(detail["is_live"])
        self.assertEqual("online", detail["state"])
        self.assertEqual("达伦·阿伦诺夫斯基", detail["item"]["directors"][0])
        self.assertEqual(["Darren Aronofsky"], detail["item"]["raw"]["original_directors"])
        self.assertEqual(7.6, detail["item"]["raw"]["ratings"]["imdb"])
        self.assertEqual("2022-12-09", detail["item"]["release_date"])

        restarted = CatalogApi(self.database, media_root=self.media_root)
        restored = restarted.get_title(key)
        self.assertEqual("鲸", restored["display_title"])
        self.assertEqual(key, restarted.service.similar_titles(key, limit=2)["focus"]["item_key"])
        self.assertEqual(key, restarted.service.build_universe_graph(key, limit=4)["focus_id"])
        with self.database.connection() as connection:
            count = connection.execute(
                "SELECT COUNT(*) FROM library_items WHERE item_key = ?",
                (key,),
            ).fetchone()[0]
        self.assertEqual(0, count)

    def test_observatory_route_aggregates_recent_latest_and_graph(self):
        report = GlobalDiscoveryReport(status="empty", generated_at=self.now)
        with mock.patch(
            "douban_recommender.exploration_service.discover_global_candidates",
            return_value=report,
        ):
            status, payload = self.request("/api/v2/observatory?limit=6")

        self.assertEqual(200, status, payload)
        self.assertEqual(2, payload["schema_version"])
        self.assertIn("recent", payload)
        self.assertIn("latest", payload)
        self.assertIn("graph", payload)
        self.assertEqual(item_key("1001"), payload["graph"]["focus_id"])
        self.assert_catalog_payload_sanitized(payload)

    def test_catalog_hydration_status_endpoint_reports_background_completeness(self):
        original = getattr(web_module, "CATALOG_HYDRATOR", None)

        class FakeHydrator:
            def status(self):
                return {
                    "state": "running",
                    "total": 463,
                    "complete": 320,
                    "pending": 143,
                    "running": 3,
                }

        try:
            web_module.CATALOG_HYDRATOR = FakeHydrator()
            status, payload = self.request("/api/v2/catalog/hydration")
        finally:
            web_module.CATALOG_HYDRATOR = original

        self.assertEqual(200, status)
        self.assertEqual(2, payload["schema_version"])
        self.assertEqual(320, payload["complete"])
        self.assertEqual(143, payload["pending"])

    def test_candidate_visibility_requires_a_trusted_real_still_but_keeps_personal_records(self):
        baseline = self.api.list_library({"state": ["all"], "limit": ["100"]})
        visible_candidate = "item:candidate-with-real-still"
        poster_only_candidate = "item:candidate-with-poster-and-backdrop-only"
        untrusted_still_candidate = "item:candidate-with-untrusted-still"
        watched_without_stills = "item:watched-without-stills"
        wish_without_stills = "item:wish-without-stills"

        self._insert_library(
            visible_candidate,
            {
                "title": "Candidate With Real Still",
                "media_type": "movie",
                "douban_rating": 8.6,
                "raw": {
                    "stills": [TRUSTED_STILL_URL]
                },
            },
            "candidate",
            104,
        )
        self._bind_item_poster(visible_candidate)
        self._insert_library(
            poster_only_candidate,
            {
                "title": "Candidate With Poster And Backdrop Only",
                "media_type": "movie",
                "douban_rating": 8.4,
                "cover": "https://static.tvmaze.com/uploads/images/original_untouched/fixture/poster.jpg",
                "backdrop": "https://static.tvmaze.com/uploads/images/original_untouched/fixture/backdrop.jpg",
                "raw": {"stills": []},
            },
            "candidate",
            103,
        )
        self._bind_item_poster(poster_only_candidate)
        self._insert_library(
            untrusted_still_candidate,
            {
                "title": "Candidate With Untrusted Still",
                "media_type": "movie",
                "douban_rating": 8.3,
                "raw": {"stills": ["https://img.example/untrusted-still.jpg"]},
            },
            "candidate",
            102.5,
        )
        self._bind_item_poster(untrusted_still_candidate)
        self._insert_library(
            watched_without_stills,
            {"title": "Watched Without Stills", "media_type": "movie", "raw": {"stills": []}},
            "watched",
            102,
        )
        self._insert_library(
            wish_without_stills,
            {"title": "Wish Without Stills", "media_type": "movie", "raw": {"stills": []}},
            "wish",
            101,
        )

        candidate = self.api.list_library({"state": ["candidate"], "limit": ["100"]})
        library = self.api.list_library({"state": ["all"], "limit": ["100"]})
        watched = self.api.list_library({"state": ["watched"], "limit": ["100"]})
        wish = self.api.list_library({"state": ["wish"], "limit": ["100"]})

        candidate_keys = {row["item_key"] for row in candidate["items"]}
        all_keys = {row["item_key"] for row in library["items"]}
        self.assertIn(visible_candidate, candidate_keys)
        self.assertNotIn(poster_only_candidate, candidate_keys)
        self.assertNotIn(untrusted_still_candidate, candidate_keys)
        self.assertIn(visible_candidate, all_keys)
        self.assertNotIn(poster_only_candidate, all_keys)
        self.assertNotIn(untrusted_still_candidate, all_keys)
        self.assertIn(watched_without_stills, {row["item_key"] for row in watched["items"]})
        self.assertIn(wish_without_stills, {row["item_key"] for row in wish["items"]})
        self.assertEqual(baseline["counts"]["candidate"] + 1, library["counts"]["candidate"])
        self.assertEqual(baseline["counts"]["all"] + 3, library["counts"]["all"])
        self.assertEqual(baseline["hidden_candidates"] + 2, library["hidden_candidates"])

        self._insert_library(
            poster_only_candidate,
            {
                "title": "Candidate With Poster And Backdrop Only",
                "media_type": "movie",
                "douban_rating": 8.4,
                "raw": {"stills": [TRUSTED_STILL_URL]},
            },
            "candidate",
            105,
        )
        restored = self.api.list_library({"state": ["candidate"], "limit": ["100"]})

        self.assertIn(poster_only_candidate, {row["item_key"] for row in restored["items"]})
        self.assertEqual(library["counts"]["candidate"] + 1, restored["counts"]["candidate"])
        self.assertEqual(library["hidden_candidates"] - 1, restored["hidden_candidates"])

    def test_library_keeps_user_history_without_posters_and_hides_unqualified_candidates(self):
        visible_candidate = "item:visible-candidate"
        low_quality_candidate = "item:placeholder-cover-candidate"
        self._insert_library(
            visible_candidate,
            {"title": "Visible Candidate", "media_type": "movie", "douban_rating": 8.2, "raw": {"stills": [TRUSTED_STILL_URL]}},
            "candidate",
            60,
        )
        self._bind_item_poster(visible_candidate)
        self._insert_library(
            low_quality_candidate,
            {
                "title": "Placeholder Cover Candidate",
                "media_type": "movie",
                "douban_rating": 8.1,
                "cover": "https://img.example/_default_/poster.jpg",
                "raw": {"stills": [TRUSTED_STILL_URL]},
            },
            "candidate",
            50,
        )
        self._bind_item_poster(low_quality_candidate)

        watched_status, watched = self.request("/api/v2/library?state=watched&limit=100")
        wish_status, wish = self.request("/api/v2/library?state=wish&limit=100")
        all_status, library = self.request("/api/v2/library?state=all&limit=100")

        self.assertEqual(watched_status, 200, watched)
        self.assertEqual(wish_status, 200, wish)
        self.assertEqual(all_status, 200, library)
        watched_by_key = {row["item_key"]: row for row in watched["items"]}
        self.assertEqual(set(watched_by_key), {item_key("1001"), item_key("1002"), item_key("1003")})
        self.assertNotEqual(watched_by_key[item_key("1002")]["poster"]["media_status"], "ready")
        self.assertNotEqual(watched_by_key[item_key("1003")]["poster"]["media_status"], "ready")
        self.assertEqual([row["item_key"] for row in wish["items"]], [item_key("1004")])
        self.assertNotEqual(wish["items"][0]["poster"]["media_status"], "ready")

        visible_by_key = {row["item_key"]: row for row in library["items"]}
        self.assertIn(visible_candidate, visible_by_key)
        self.assertNotIn(low_quality_candidate, visible_by_key)
        self.assertNotIn(item_key("1005"), visible_by_key)
        self.assertNotIn("item:custom", visible_by_key)
        self.assertEqual(visible_by_key[visible_candidate]["poster"]["media_status"], "ready")
        self.assertEqual(
            visible_by_key[visible_candidate]["poster"]["url"],
            f"/media/{self.poster_asset}.png",
        )
        self.assertEqual(library["counts"]["watched"], 3)
        self.assertEqual(library["counts"]["wish"], 1)
        self.assertEqual(library["counts"]["candidate"], 1)
        self.assertEqual(library["counts"]["all"], 5)
        self.assertEqual(set(library["counts"]), {"all", "watched", "wish", "candidate", "rated"})
        self.assertEqual(library["hidden_candidates"], 3)

    def test_candidate_visibility_filters_before_pagination_and_cursors_point_to_visible_records(self):
        visible_candidates = [
            ("item:candidate-a", 100),
            ("item:candidate-b", 70),
            ("item:candidate-c", 60),
        ]
        for key, updated_offset in visible_candidates:
            self._insert_library(
                key,
                {"title": key.rsplit(":", 1)[-1], "media_type": "movie", "douban_rating": 8.0, "raw": {"stills": [TRUSTED_STILL_URL]}},
                "candidate",
                updated_offset,
            )
            self._bind_item_poster(key)
        self._insert_library(
            "item:hidden-missing-poster",
            {"title": "Hidden Missing Poster", "media_type": "movie", "douban_rating": 8.0, "raw": {"stills": [TRUSTED_STILL_URL]}},
            "candidate",
            90,
        )
        self._insert_library(
            "item:hidden-placeholder-cover",
            {
                "title": "Hidden Placeholder Cover",
                "media_type": "movie",
                "douban_rating": 8.0,
                "cover": "https://img.example/default_poster.jpg",
                "raw": {"stills": [TRUSTED_STILL_URL]},
            },
            "candidate",
            80,
        )
        self._bind_item_poster("item:hidden-placeholder-cover")

        first_status, first = self.request("/api/v2/library?state=candidate&limit=2")

        self.assertEqual(first_status, 200, first)
        self.assertEqual(
            [row["item_key"] for row in first["items"]],
            [visible_candidates[0][0], visible_candidates[1][0]],
        )
        self.assertTrue(first["next_cursor"])
        padded = first["next_cursor"] + "=" * (-len(first["next_cursor"]) % 4)
        decoded_cursor = json.loads(base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8"))
        self.assertEqual(decoded_cursor["item_key"], visible_candidates[1][0])
        self.assertEqual(decoded_cursor["updated_at"], self.now + visible_candidates[1][1])
        self.assertEqual(first["counts"]["candidate"], 3)
        self.assertEqual(first["counts"]["all"], 7)
        self.assertEqual(first["hidden_candidates"], 4)

        second_status, second = self.request(
            "/api/v2/library?state=candidate&limit=2&cursor=" + urllib.parse.quote(first["next_cursor"])
        )

        self.assertEqual(second_status, 200, second)
        self.assertEqual([row["item_key"] for row in second["items"]], [visible_candidates[2][0]])
        self.assertEqual(second["next_cursor"], "")
        self.assertEqual(second["counts"], first["counts"])
        self.assertEqual(second["hidden_candidates"], first["hidden_candidates"])

    def test_candidate_visibility_hides_duplicate_of_personal_douban_record(self):
        self._insert_library(
            "douban:1292064",
            {
                "title": "\u695a\u95e8\u7684\u4e16\u754c",
                "media_type": "movie",
                "douban_id": "1292064",
                "douban_rating": 9.4,
            },
            "watched",
            100,
        )
        duplicate = "external:truman-duplicate"
        self._insert_library(
            duplicate,
            {
                "title": "\u695a\u95e8\u7684\u4e16\u754c",
                "media_type": "movie",
                "douban_id": "1292064",
                "douban_rating": 9.4,
                "raw": {"stills": [TRUSTED_STILL_URL]},
            },
            "candidate",
            90,
        )
        self._bind_item_poster(duplicate)

        status, payload = self.request("/api/v2/library?state=all&limit=100")

        self.assertEqual(200, status, payload)
        visible_keys = [row["item_key"] for row in payload["items"]]
        self.assertIn("douban:1292064", visible_keys)
        self.assertNotIn(duplicate, visible_keys)

    def test_candidate_library_batches_media_lookup_after_paging_without_decoding_assets(self):
        for index in range(8):
            key = f"item:performance-{index}"
            self._insert_library(
                key,
                {"title": f"Performance {index}", "media_type": "movie", "douban_rating": 8.0, "raw": {"stills": [TRUSTED_STILL_URL]}},
                "candidate",
                200 + index,
            )
            self._bind_item_poster(key)

        self.api.service.visible_library_records()

        with (
            mock.patch.object(
                self.api.service,
                "serialize_title",
                wraps=self.api.service.serialize_title,
            ) as serialize_title,
            mock.patch.object(
                self.api.service.repository,
                "media_identity_for_item",
                wraps=self.api.service.repository.media_identity_for_item,
            ) as media_identity_for_item,
            mock.patch.object(
                self.api.service.repository,
                "media_entity_ids_for_records",
                wraps=self.api.service.repository.media_entity_ids_for_records,
            ) as media_entity_ids_for_records,
            mock.patch.object(
                self.api.service.repository,
                "asset_override",
                wraps=self.api.service.repository.asset_override,
            ) as asset_override,
            mock.patch.object(
                self.api.service.repository,
                "asset_overrides_for_kind",
                wraps=self.api.service.repository.asset_overrides_for_kind,
            ) as asset_overrides_for_kind,
            mock.patch.object(
                self.api.service.media_store,
                "lookup",
                wraps=self.api.service.media_store.lookup,
            ) as media_lookup,
        ):
            payload = self.api.list_library({"state": ["candidate"], "limit": ["2"]})

        self.assertEqual(2, len(payload["items"]))
        self.assertEqual(len(payload["items"]), serialize_title.call_count)
        self.assertEqual(0, media_identity_for_item.call_count)
        self.assertEqual(1, media_entity_ids_for_records.call_count)
        self.assertEqual(0, asset_override.call_count)
        self.assertEqual(2, asset_overrides_for_kind.call_count)
        self.assertEqual(0, media_lookup.call_count)

    def test_library_list_skips_expensive_portrait_expansion_but_title_detail_keeps_it(self):
        with mock.patch.object(
            self.api.service,
            "_people_for_title",
            wraps=self.api.service._people_for_title,
        ) as people_for_title:
            library = self.api.list_library({"state": ["watched"], "limit": ["2"]})

            self.assertEqual(2, len(library["items"]))
            self.assertEqual(0, people_for_title.call_count)
            self.assertTrue(all(row.get("people") == [] for row in library["items"]))

            detail = self.api.get_title(item_key("1001"))

        self.assertGreater(people_for_title.call_count, 0)
        self.assertTrue(detail["people"])

    def test_library_reuses_visibility_snapshot_until_catalog_revision_changes(self):
        with mock.patch.object(
            self.api.service,
            "_visible_library_records",
            wraps=self.api.service._visible_library_records,
        ) as build_visibility:
            first = self.api.list_library({"state": ["all"], "limit": ["2"]})
            second = self.api.list_library({"state": ["all"], "limit": ["2"]})

            self.assertEqual(first["counts"], second["counts"])
            self.assertEqual(1, build_visibility.call_count)

            self._insert_library(
                "douban:1099",
                {
                    "title": "Newly Synced Film",
                    "media_type": "movie",
                    "douban_id": "1099",
                    "douban_rating": 8.4,
                },
                "watched",
                99,
            )
            refreshed = self.api.list_library({"state": ["all"], "limit": ["2"]})

        self.assertEqual(first["counts"]["all"] + 1, refreshed["counts"]["all"])
        self.assertEqual(2, build_visibility.call_count)

    def test_taste_returns_five_groups_with_evidence_and_session_feedback_isolated(self):
        status, payload = self.request("/api/v2/taste")
        self.assertEqual(status, 200, payload)
        self.assertEqual(payload["schema_version"], 2)
        self.assertEqual(set(payload["groups"]), {"stable", "conflicting", "recent", "negative", "unexplored"})
        for group_name, signals in payload["groups"].items():
            self.assertTrue(signals, group_name)
            self.assertTrue(all(signal["evidence_item_ids"] for signal in signals), group_name)
            self.assertTrue(all(signal["evidence_count"] == len(signal["evidence_item_ids"]) for signal in signals), group_name)
            self.assertTrue(all(signal["evidence_titles"] for signal in signals), group_name)
            self.assertTrue(all(len(signal["evidence_titles"]) <= 4 for signal in signals), group_name)
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


    def test_catalog_routes_recursively_sanitize_urls_and_secrets(self):
        paths = [
            "/api/v2/titles/douban:1001",
            "/api/v2/people/person-director",
            "/api/v2/library?state=all&limit=5",
            "/api/v2/universe?focus=douban:1001&limit=9",
            "/api/v2/taste",
        ]
        for path in paths:
            with self.subTest(path=path):
                status, payload = self.request(path)
                self.assertEqual(status, 200, payload)
                self.assertEqual(payload["schema_version"], 2)
                self.assert_catalog_payload_sanitized(payload)

    def test_library_title_serialization_repairs_missing_genres_for_known_and_unknown_items(self):
        self._insert_library(
            item_key("1010"),
            {
                "title": "控方证人",
                "media_type": "movie",
                "douban_id": "1296141",
                "genres": [],
            },
            "watched",
            50,
        )
        self._insert_library(
            item_key("1011"),
            {
                "title": "未补全剧集",
                "media_type": "series",
                "douban_id": "1011",
                "genres": [],
            },
            "watched",
            49,
        )

        payload = self.api.list_library({"state": ["watched"], "limit": ["10"]})
        by_title = {item["title"]: item for item in payload["items"]}
        self.assertEqual(["剧情", "悬疑", "犯罪"], by_title["控方证人"]["item"]["genres"])
        self.assertEqual(["电视剧"], by_title["未补全剧集"]["item"]["genres"])

    def test_library_title_serialization_prefers_curated_chinese_synopsis_over_provider_english(self):
        self._insert_library(
            item_key("1012"),
            {
                "title": "去他*的世界",
                "media_type": "电视剧",
                "douban_id": "27031389",
                "summary": "Based on the award-winning series of comic books by Charles Forsman.",
                "genres": ["剧情", "喜剧", "爱情"],
            },
            "watched",
            51,
        )

        payload = self.api.list_library({"state": ["watched"], "limit": ["20"]})
        title = next(item for item in payload["items"] if item["title"] == "去他*的世界")
        summary = title["item"]["summary"]
        self.assertIn("边缘少年", summary)
        self.assertNotIn("award-winning series", summary)

    def test_title_serialization_exposes_verified_runtime_and_release_date_from_public_metadata(self):
        self._insert_library(
            item_key("1013"),
            {
                "title": "公开资料电影",
                "media_type": "电影",
                "douban_id": "1013",
                "summary": "经过标题校验的剧情简介。",
                "genres": ["动作"],
                "raw": {"duration": 126, "release_date": "2026-02-17"},
            },
            "watched",
            52,
        )

        payload = self.api.get_title(item_key("1013"))

        self.assertEqual(126, payload["item"]["duration"])
        self.assertEqual("2026-02-17", payload["item"]["release_date"])

    def test_catalog_sanitizer_removes_bearer_keys_from_raw_people_without_dropping_actor_names(self):
        status, payload = self.request("/api/v2/titles/douban:1001")
        self.assertEqual(status, 200, payload)
        raw_people = payload["item"]["raw"]["people"]
        serialized = json.dumps(raw_people, ensure_ascii=False).lower()
        self.assertIn("actor external", serialized)
        self.assertNotIn("bearer", serialized)
        self.assertNotIn("abc123", serialized)

    def test_session_only_feedback_is_excluded_from_all_taste_profile_groups(self):
        status, payload = self.request("/api/v2/taste")
        self.assertEqual(status, 200, payload)
        groups_text = json.dumps(payload["groups"], ensure_ascii=False)
        self.assertNotIn("SessionOnly", groups_text)
        self.assertNotIn("TonightOnly", groups_text)
        self.assertNotIn("session-feedback", groups_text)

    def test_catalog_error_responses_include_schema_version_for_all_validation_paths(self):
        invalid_cursor_empty_key = base64.urlsafe_b64encode(json.dumps({"updated_at": self.now, "item_key": ""}).encode()).decode().rstrip("=")
        invalid_cursor_nan = base64.urlsafe_b64encode(b'{"updated_at":NaN,"item_key":"douban:1001"}').decode().rstrip("=")
        invalid_cursor_extra = base64.urlsafe_b64encode(json.dumps({"updated_at": self.now, "item_key": "douban:1001", "extra": {"bad": []}}).encode()).decode().rstrip("=")
        paths = [
            ("/api/v2/titles/bad/segment", 404),
            ("/api/v2/titles/does-not-exist", 404),
            ("/api/v2/people/bad/segment", 404),
            ("/api/v2/people/does-not-exist", 404),
            (f"/api/v2/library?state=watched&cursor={invalid_cursor_empty_key}", 400),
            (f"/api/v2/library?state=watched&cursor={invalid_cursor_nan}", 400),
            (f"/api/v2/library?state=watched&cursor={invalid_cursor_extra}", 400),
            ("/api/v2/library?state=bad/state", 400),
            ("/api/v2/library?limit=0", 400),
            ("/api/v2/universe", 400),
        ]
        for path, expected_status in paths:
            with self.subTest(path=path):
                status, payload = self.request(path)
                self.assertEqual(status, expected_status, payload)
                self.assertEqual(payload["schema_version"], 2)
                self.assertIn("error", payload)

    def test_asset_overrides_and_legacy_media_are_ready_only_when_manifest_kind_decision_and_file_match(self):
        wrong_kind_asset = self._insert_asset("e" * 64, "portrait", present=True)
        rejected_asset = self._insert_asset("f" * 64, "poster", present=True)
        pending_asset = self._insert_asset("1" * 64, "poster", present=True, status="pending")
        outside_asset = self._insert_asset("2" * 64, "poster", present=False, relative="../outside.png")
        corrupt_asset = self._insert_asset("3" * 64, "poster", present=True)
        (self.media_root / corrupt_asset[:2] / f"{corrupt_asset}.png").write_bytes(b"corrupt replacement")
        self._insert_library(
            item_key("1006"),
            {
                "title": "Corrupt Legacy Poster",
                "media_type": "movie",
                "douban_id": "1006",
                "cover": f"/media/{corrupt_asset}.png",
            },
            "candidate",
            6,
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO media_identities(id, title, original_titles_json, year, media_type, countries_json, metadata_json, created_at, updated_at)
                VALUES('media-beta', 'Shared Director Film', '[]', 2021, 'movie', '[]', '{"item_key":"douban:1002"}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO media_identities(id, title, original_titles_json, year, media_type, countries_json, metadata_json, created_at, updated_at)
                VALUES('media-gamma', 'Negative Noir', '[]', 2020, 'movie', '[]', '{"item_key":"douban:1003"}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO media_identities(id, title, original_titles_json, year, media_type, countries_json, metadata_json, created_at, updated_at)
                VALUES('media-wish', 'Unexplored Space', '[]', 2010, 'series', '[]', '{"item_key":"douban:1004"}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO media_identities(id, title, original_titles_json, year, media_type, countries_json, metadata_json, created_at, updated_at)
                VALUES('media-forged', 'Forged Legacy Poster', '[]', 2022, 'movie', '[]', '{"item_key":"douban:1005"}', ?, ?)
                """,
                (self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('wrong-kind-poster', 'media', 'media-beta', 'poster', ?, 'selected', ?, ?)
                """,
                (wrong_kind_asset, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('rejected-poster', 'media', 'media-gamma', 'poster', ?, 'rejected', ?, ?)
                """,
                (rejected_asset, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('pending-poster', 'media', 'media-wish', 'poster', ?, 'selected', ?, ?)
                """,
                (pending_asset, self.now, self.now),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at)
                VALUES('outside-poster', 'media', 'media-forged', 'poster', ?, 'selected', ?, ?)
                """,
                (outside_asset, self.now, self.now),
            )

        expectations = [
            ("/api/v2/titles/douban:1002", "poster", ""),
            ("/api/v2/titles/douban:1003", "poster", ""),
            ("/api/v2/titles/douban:1004", "poster", ""),
            ("/api/v2/titles/douban:1005", "poster", ""),
            ("/api/v2/titles/douban:1006", "poster", ""),
        ]
        for path, field, expected_url in expectations:
            with self.subTest(path=path):
                status, payload = self.request(path)
                self.assertEqual(status, 200, payload)
                self.assertEqual(payload[field]["url"], expected_url)
                self.assertNotEqual(payload[field]["media_status"], "ready")

    def test_shared_manifest_asset_remains_ready_for_its_bound_kind(self):
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE asset_files SET kind='shared' WHERE asset_id=?",
                (self.poster_asset,),
            )

        status, payload = self.request("/api/v2/titles/douban:1001")

        self.assertEqual(status, 200)
        self.assertEqual(payload["poster"]["media_status"], "ready")
        self.assertTrue(payload["poster"]["url"].startswith("/media/"))

    def test_person_lookup_and_legacy_asset_lookup_stay_inside_repository_boundary(self):
        class NoServiceSql:
            def connection(self):
                raise AssertionError("service must use ExplorationRepository for SQL lookups")

        self.api.service.database = NoServiceSql()
        record = self.api.service.find_title("douban:1001")
        payload = self.api.service.serialize_title(record)
        people = {person["name"]: person for person in payload["people"]}
        self.assertEqual(people["Director A"]["id"], "person-director")
        self.assertNotIn("connection.execute", inspect.getsource(type(self.api.service)._person_id_for_name))
        self.assertNotIn("connection.execute", inspect.getsource(type(self.api.service)._media_asset))

    def test_exact_title_key_uses_direct_repository_lookup_without_scanning_catalog(self):
        original_repository = self.api.service.repository
        expected = original_repository.library_records()[0]

        class DirectRepository:
            def __init__(self):
                self.direct_calls = []

            def library_record(self, item_key):
                self.direct_calls.append(item_key)
                return expected if item_key == expected.item_key else None

            def library_records(self):
                raise AssertionError("exact item keys must not scan the full catalog")

        direct = DirectRepository()
        self.api.service.repository = direct
        try:
            record = self.api.service.find_title(expected.item_key)
        finally:
            self.api.service.repository = original_repository

        self.assertIs(record, expected)
        self.assertEqual([expected.item_key], direct.direct_calls)

    def test_migrated_wanted_library_state_is_supported_and_counts_as_unexplored(self):
        database = AppDatabase(self.root / "migrated.db")
        database.initialize()
        migrate_legacy_recommendations(
            [
                {
                    "title": "Migrated Wish",
                    "media_type": "movie",
                    "douban_id": "9001",
                    "source": "douban_sync:wish",
                    "tags": ["??"],
                    "genres": ["Mystery"],
                }
            ],
            database,
        )
        api = CatalogApi(database, media_root=self.media_root)
        library = api.list_library({"state": ["wanted"], "limit": ["10"]})
        self.assertEqual(library["schema_version"], 2)
        self.assertEqual([item["state"] for item in library["items"]], ["wanted"])
        taste = api.taste({})
        unexplored = json.dumps(taste["groups"]["unexplored"], ensure_ascii=False)
        self.assertIn("Mystery", unexplored)

    def test_service_build_universe_graph_clamps_limit(self):
        self.assertIsNotNone(CatalogApi, "catalog api module should exist")
        graph = self.api.service.build_universe_graph("douban:1001", limit=999)
        self.assertLessEqual(len(graph["nodes"]), 25)
        graph = self.api.service.build_universe_graph("douban:1001", limit=1)
        self.assertLessEqual(len(graph["nodes"]), 3)


    def test_title_enrichment_upgrades_legacy_translation_and_persists_imdb_metadata(self):
        key = "item:legacy-imdb-enrichment"
        original = "A complete English synopsis that must replace the truncated legacy translation cache."
        self._insert_library(
            key,
            {
                "title": "神秘公司",
                "media_type": "电视剧",
                "year": 2022,
                "summary": "这是一段被截断的旧翻译。",
                "genres": ["悬疑"],
                "directors": ["导演甲"],
                "casts": ["演员乙"],
                "raw": {
                    "ratings": {"tvmaze": 7.1},
                    "rating_votes": {"tvmaze": 80},
                    "provider_ids": {"tvmaze": "61855"},
                    "stills": ["https://img.example/legacy-still.jpg"],
                    "summary_original": original,
                    "summary_source": "machine_translation:mymemory",
                    "summary_generated": True,
                },
            },
            "candidate",
            57,
        )

        def public_enrich(item):
            item.summary = "这是重新生成并完整保留的中文简介。"
            item.raw["summary_source"] = "machine_translation:google"
            item.raw["summary_translation_version"] = 2
            item.raw["ratings"]["imdb"] = 7.9
            item.raw["rating_votes"]["imdb"] = 726
            item.raw["provider_ids"]["imdb"] = "tt2091018"
            item.raw["stills"] = [
                "https://m.media-amazon.com/images/scene-one.jpg",
                "https://m.media-amazon.com/images/scene-two.jpg",
            ]
            return True

        with (
            mock.patch("douban_recommender.catalog_api.enrich_media_items", side_effect=lambda items, **_kwargs: items),
            mock.patch("douban_recommender.catalog_api.enrich_public_metadata", side_effect=public_enrich) as fallback,
        ):
            payload = self.api.enrich_title(key)

        fallback.assert_called_once()
        self.assertEqual(2, payload["item"]["raw"]["summary_translation_version"])
        self.assertEqual(7.9, payload["item"]["raw"]["ratings"]["imdb"])
        self.assertEqual(726, payload["item"]["raw"]["rating_votes"]["imdb"])
        self.assertEqual("tt2091018", payload["item"]["raw"]["provider_ids"]["imdb"])
        self.assertEqual(2, len(payload["stills"]))

        persisted = self.api.get_title(key)
        self.assertEqual("这是重新生成并完整保留的中文简介。", persisted["item"]["summary"])
        self.assertEqual(2, persisted["item"]["raw"]["summary_translation_version"])
        self.assertEqual(7.9, persisted["item"]["raw"]["ratings"]["imdb"])
        self.assertEqual(726, persisted["item"]["raw"]["rating_votes"]["imdb"])
        self.assertEqual("tt2091018", persisted["item"]["raw"]["provider_ids"]["imdb"])
        self.assertEqual(2, len(persisted["stills"]))


if __name__ == "__main__":
    unittest.main()
