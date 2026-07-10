import io
import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.catalog_api import CatalogApi
from douban_recommender.intent_parser import RecommendationIntent, parse_recommendation_intent
from douban_recommender.media.orchestrator import MediaOrchestrator
from douban_recommender.media.store import MediaStore
from douban_recommender.media.validator import validate_image_bytes
from douban_recommender.media_api import MediaApi
from douban_recommender.models import MediaItem, recommendation_item_key
from douban_recommender.web import Handler
import douban_recommender.web as web_module


RATED_ITEMS = [
    {
        "title": "已看动画",
        "my_rating": 5,
        "media_type": "动漫",
        "genres": ["剧情", "悬疑"],
        "tags": ["看过"],
        "douban_id": "anime-seen",
    }
]

CANDIDATES_CSV = """title,media_type,douban_rating,vote_count,genres,tags,douban_id,summary
暗河来信,电影,9.2,200000,剧情 / 犯罪,高分,movie-1,人物塑造扎实
夜航手册,电影,9.0,150000,剧情 / 悬疑,高分,movie-2,叙事强
旧城烟火,电影,8.8,90000,剧情 / 犯罪,现实主义,movie-3,氛围稳
雪线回声,电影,8.6,70000,剧情 / 惊悚,高分,movie-4,制作完整
雾港档案,电视剧,9.1,210000,剧情 / 悬疑,高分,series-1,人物关系复杂
北岸讯号,电视剧,8.9,170000,剧情 / 犯罪,高分,series-2,节奏扎实
春夜纪事,电视剧,8.7,120000,剧情 / 悬疑,现实主义,series-3,信息密度高
群山侧写,电视剧,8.5,90000,剧情 / 犯罪,高分,series-4,结构清晰
星潮备忘录,动漫,9.3,230000,剧情 / 悬疑,高分,anime-1,群像精彩
回声旅团,动漫,9.0,180000,剧情 / 犯罪,高分,anime-2,叙事强
白塔观测站,动漫,8.8,140000,剧情 / 悬疑,现实主义,anime-3,设定完整
岚谷事件簿,动漫,8.6,95000,剧情 / 犯罪,高分,anime-4,人物关系稳
已看动画重复条目,动漫,8.5,50000,剧情 / 悬疑,高分,anime-seen,应该被过滤
"""


class RecommendationApiV2Tests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.original_api = getattr(web_module, "RECOMMENDATION_API", None)
        self.original_catalog_api = getattr(web_module, "CATALOG_API", None)
        self.original_media_api = getattr(web_module, "MEDIA_API", None)
        try:
            from douban_recommender.recommendation_api import RecommendationApi
        except ImportError:
            self.api = None
        else:
            database = AppDatabase(Path(self.temp.name) / "cinescope.db")
            database.initialize()
            self.media_store = MediaStore(Path(self.temp.name) / "media", database)
            self.api = RecommendationApi(database, media_store=self.media_store)
            web_module.RECOMMENDATION_API = self.api
            web_module.CATALOG_API = CatalogApi(database, media_root=Path(self.temp.name) / "media")
            web_module.MEDIA_API = MediaApi(self.media_store, MediaOrchestrator(self.media_store))
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        web_module.RECOMMENDATION_API = self.original_api
        web_module.CATALOG_API = self.original_catalog_api
        web_module.MEDIA_API = self.original_media_api
        self.thread.join(timeout=5)
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None, raw_json=None):
        data = None
        headers = {}
        if raw_json is not None:
            data = raw_json.encode("utf-8")
            headers["Content-Type"] = "application/json"
        elif payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def post_json(self, path, payload):
        status, body = self.request(path, method="POST", payload=payload)
        self.assertEqual(status, 200, body)
        return body

    def post_json_status(self, path, payload):
        return self.request(path, method="POST", payload=payload)

    def post_raw_json_status(self, path, raw_json):
        return self.request(path, method="POST", raw_json=raw_json)

    def get_json(self, path):
        status, body = self.request(path, method="GET")
        self.assertEqual(status, 200, body)
        return body

    def assert_no_secret_echo(self, payload, *secrets):
        serialized = json.dumps(payload, ensure_ascii=False)
        for secret in secrets:
            self.assertNotIn(secret, serialized)

    def create_verified_media_asset(self):
        output = io.BytesIO()
        Image.new("RGB", (160, 240), "navy").save(output, format="PNG")
        validated = validate_image_bytes(output.getvalue(), "image/png")
        return self.media_store.put(validated, "https://source.example/poster.png", "poster")

    def first_nonempty_channel(self, response):
        for name, channel in response["channels"].items():
            if channel["batch"]["items"]:
                return name, channel
        self.fail("expected at least one non-empty recommendation channel")

    def find_item_by_id(self, response, douban_id):
        channels = response.get("channels")
        if isinstance(channels, dict):
            for channel in channels.values():
                for item in channel.get("batch", {}).get("items", []):
                    if item.get("douban_id") == douban_id:
                        return item
        batch = response.get("batch")
        if isinstance(batch, dict):
            for item in batch.get("items", []):
                if item.get("douban_id") == douban_id:
                    return item
        self.fail(f"expected item with douban_id={douban_id}")

    def session_payload(self, **overrides):
        payload = {
            "schema_version": 2,
            "profile_key": "profile-1",
            "rated_items": list(RATED_ITEMS),
            "candidates_csv": CANDIDATES_CSV,
            "fetch_douban": False,
            "use_sample_candidates": False,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "like_terms": "评分高，剧情好，叙事强",
            "dislike_terms": "电视剧古装，注水剧",
            "batch_size": 2,
            "limit": 160,
        }
        payload.update(overrides)
        return payload

    def create_session(self, **overrides):
        return self.post_json("/api/v2/recommend/sessions", self.session_payload(**overrides))

    def item_payload(self, **overrides):
        payload = {
            "title": "合法条目",
            "my_rating": 4.5,
            "douban_rating": 8.8,
            "vote_count": 12345,
            "year": 2024,
            "media_type": "电影",
            "genres": ["剧情"],
            "countries": ["中国大陆"],
            "languages": ["汉语普通话"],
            "directors": ["导演甲"],
            "casts": ["演员甲"],
            "tags": ["想看"],
            "url": "https://example.invalid/items/1",
            "douban_id": "valid-item",
            "cover": "https://example.invalid/items/1.jpg",
            "summary": "一条合法的测试条目",
            "source": "manual",
        }
        payload.update(overrides)
        return payload

    def assert_bad_request_field(self, path, payload, field):
        status, body = self.post_json_status(path, payload)
        self.assertEqual(status, 400, body)
        self.assertIn(field, body["error"])

    def test_request_helper_closes_http_error_response(self):
        body = io.BytesIO(b'{"error":"bad request"}')
        error = urllib.error.HTTPError(
            "http://127.0.0.1/test",
            400,
            "Bad Request",
            hdrs=None,
            fp=body,
        )

        with mock.patch("urllib.request.urlopen", side_effect=error):
            status, payload = self.request("/test")

        self.assertEqual((status, payload), (400, {"error": "bad request"}))
        self.assertTrue(body.closed)

    def test_create_session_rejects_malformed_known_fields(self):
        invalid_cases = [
            ("intent must be object", self.session_payload(intent=[]), "intent"),
            ("intent list field must be string or string array", self.session_payload(intent={"genres": [123]}), "intent.genres[0]"),
            ("intent text field must be string", self.session_payload(intent={"pace": 123}), "intent.pace"),
            ("intent number field rejects bool", self.session_payload(intent={"runtime_max": True}), "intent.runtime_max"),
            ("rated_items must be array of objects", self.session_payload(rated_items={}), "rated_items"),
            ("rated_items entry must be object", self.session_payload(rated_items=[self.item_payload(), "oops"]), "rated_items[1]"),
            ("rated_items text field must be string", self.session_payload(rated_items=[self.item_payload(title=123)]), "rated_items[0].title"),
            ("rated_items numeric field must be number", self.session_payload(rated_items=[self.item_payload(my_rating=True)]), "rated_items[0].my_rating"),
            ("rated_items list field must be string or string array", self.session_payload(rated_items=[self.item_payload(genres=[1])]), "rated_items[0].genres[0]"),
            ("candidate_items must be array of objects", self.session_payload(candidate_items="x", candidates_csv=""), "candidate_items"),
            ("candidate_items entry must be object", self.session_payload(candidate_items=[self.item_payload(), "oops"], candidates_csv=""), "candidate_items[1]"),
            ("candidate_items text field must be string", self.session_payload(candidate_items=[self.item_payload(summary=123)], candidates_csv=""), "candidate_items[0].summary"),
            ("candidate_urls must be string or string array", self.session_payload(candidate_urls=123), "candidate_urls"),
            ("candidate_urls entries must be strings", self.session_payload(candidate_urls=["https://example.invalid/list", 123]), "candidate_urls[1]"),
            ("batch_size_by_channel must be object", self.session_payload(batch_size_by_channel=[]), "batch_size_by_channel"),
            ("batch_size_by_channel limits channel names", self.session_payload(batch_size_by_channel={"纪录片": 2}), "batch_size_by_channel.纪录片"),
            ("batch_size_by_channel values must be integers", self.session_payload(batch_size_by_channel={"电影": True}), "batch_size_by_channel.电影"),
            ("batch_size must be integer", self.session_payload(batch_size="oops"), "batch_size"),
            ("visible_size must be integer", self.session_payload(visible_size="oops"), "visible_size"),
            ("limit must be integer", self.session_payload(limit=1.5), "limit"),
            ("per_query must be integer", self.session_payload(per_query=True), "per_query"),
            ("include_movies must be bool", self.session_payload(include_movies="yes"), "include_movies"),
            ("include_series must be bool", self.session_payload(include_series="yes"), "include_series"),
            ("include_anime must be bool", self.session_payload(include_anime="yes"), "include_anime"),
            ("fetch_douban must be bool", self.session_payload(fetch_douban="yes"), "fetch_douban"),
            ("use_sample_ratings must be bool", self.session_payload(use_sample_ratings="yes"), "use_sample_ratings"),
            ("use_sample_candidates must be bool", self.session_payload(use_sample_candidates="yes"), "use_sample_candidates"),
            ("ratings_csv must be string", self.session_payload(ratings_csv=123), "ratings_csv"),
            ("candidates_csv must be string", self.session_payload(candidates_csv=123), "candidates_csv"),
            ("profile_key null is invalid", self.session_payload(profile_key=None), "profile_key"),
            ("intent_text must be string", self.session_payload(intent_text=123), "intent_text"),
            ("text must be string", self.session_payload(text=123), "text"),
            ("like_terms must be string or string array", self.session_payload(like_terms=123), "like_terms"),
            ("dislike_terms entries must be strings", self.session_payload(dislike_terms=["注水", 123]), "dislike_terms[1]"),
        ]

        for label, payload, field in invalid_cases:
            with self.subTest(case=label):
                self.assert_bad_request_field("/api/v2/recommend/sessions", payload, field)

    def test_batch_and_previous_routes_reject_malformed_fields(self):
        created = self.create_session()
        cases = [
            (
                "batch channel must be string",
                f"/api/v2/recommend/sessions/{created['id']}/batch",
                {"schema_version": 2, "channel": ["电影"]},
                "channel",
            ),
            (
                "batch reason must be string",
                f"/api/v2/recommend/sessions/{created['id']}/batch",
                {"schema_version": 2, "channel": "电影", "reason": 123},
                "reason",
            ),
            (
                "previous channel must be string",
                f"/api/v2/recommend/sessions/{created['id']}/previous",
                {"schema_version": 2, "channel": False},
                "channel",
            ),
            (
                "previous reason must be string when provided",
                f"/api/v2/recommend/sessions/{created['id']}/previous",
                {"schema_version": 2, "channel": "电影", "reason": ["retry"]},
                "reason",
            ),
        ]

        for label, path, payload, field in cases:
            with self.subTest(case=label):
                self.assert_bad_request_field(path, payload, field)

    def test_feedback_route_rejects_malformed_known_fields(self):
        feedback_cases = [
            (
                "event_type must be string",
                {
                    "schema_version": 2,
                    "event_type": [],
                    "scope": "permanent",
                    "item_key": "item-1",
                },
                "event_type",
            ),
            (
                "scope must be string",
                {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": [],
                    "item_key": "item-1",
                },
                "scope",
            ),
            (
                "item_key must be string",
                {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": "permanent",
                    "item_key": 123,
                },
                "item_key",
            ),
            (
                "session_id must be string",
                {
                    "schema_version": 2,
                    "event_type": "not-tonight",
                    "scope": "session",
                    "session_id": 123,
                    "item_key": "item-1",
                },
                "session_id",
            ),
            (
                "profile_key must be string",
                {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": "permanent",
                    "profile_key": 123,
                    "item_key": "item-1",
                },
                "profile_key",
            ),
            (
                "feedback item must be object",
                {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": "permanent",
                    "item": "x",
                },
                "item",
            ),
            (
                "feedback item obeys item schema",
                {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": "permanent",
                    "item": self.item_payload(title=123),
                },
                "item.title",
            ),
            (
                "payload must be object",
                {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": "permanent",
                    "item_key": "item-1",
                    "payload": "oops",
                },
                "payload",
            ),
        ]

        for label, payload, field in feedback_cases:
            with self.subTest(case=label):
                self.assert_bad_request_field("/api/v2/feedback", payload, field)

    def test_create_session_returns_three_distinct_counts(self):
        explicit_anime_series = [
            self.item_payload(
                title=f"明确格式动画{index}",
                media_type="动漫",
                douban_id=f"explicit-anime-{index}",
                genres=["动画", "剧情"],
                raw={"format": "SERIES"},
            )
            for index in range(3)
        ]
        response = self.post_json(
            "/api/v2/recommend/sessions",
            self.session_payload(limit=160, candidate_items=explicit_anime_series),
        )
        anime = response["channels"]["动漫"]
        self.assertIn("pool_size", anime)
        self.assertIn("matched_size", anime)
        self.assertIn("visible_size", anime)
        self.assertGreater(anime["pool_size"], anime["matched_size"])
        self.assertGreater(anime["matched_size"], anime["visible_size"])

    def test_session_response_returns_grounded_intent_chips(self):
        created = self.create_session(intent_text="90分钟内的悬疑电影")

        self.assertTrue(created["chips"])
        self.assertEqual(
            {"key", "label", "value", "removable"},
            set(created["chips"][0]),
        )
        self.assertIn(
            {"key": "media_type", "label": "电影", "value": "电影", "removable": True},
            created["chips"],
        )
        self.assertIn(
            {"key": "genre", "label": "悬疑", "value": "悬疑", "removable": True},
            created["chips"],
        )
        self.assertIn(
            {"key": "runtime_max", "label": "片长 ≤ 90 分钟", "value": 90, "removable": True},
            created["chips"],
        )

        restored = self.get_json(f"/api/v2/recommend/sessions/{created['id']}")
        self.assertEqual(restored["chips"], created["chips"])

    def test_feedback_api_does_not_accept_unknown_permanent_scope(self):
        status, payload = self.post_json_status("/api/v2/feedback", {
            "schema_version": 2,
            "event_type": "not-tonight",
            "scope": "permanent",
            "item_key": "x",
        })
        self.assertEqual(status, 400)
        self.assertIn("scope", payload["error"])

    def test_feedback_api_rejects_non_object_payload(self):
        invalid_payloads = ("oops", ["oops"], 123)
        for value in invalid_payloads:
            with self.subTest(payload_type=type(value).__name__):
                status, payload = self.post_json_status("/api/v2/feedback", {
                    "schema_version": 2,
                    "event_type": "more-like-this",
                    "scope": "permanent",
                    "item_key": "x",
                    "payload": value,
                })
                self.assertEqual(status, 400)
                self.assertIn("payload", payload["error"])
                self.assertIn("object", payload["error"])

    def test_v2_post_routes_reject_top_level_non_object_json_bodies(self):
        created = self.create_session()
        channel_name, channel_state = self.first_nonempty_channel(created)
        item_key = channel_state["batch"]["items"][0]["item_key"]

        recorded = self.post_json(
            "/api/v2/feedback",
            {
                "schema_version": 2,
                "profile_key": "profile-1",
                "session_id": created["id"],
                "event_type": "not-tonight",
                "scope": "session",
                "item_key": item_key,
            },
        )

        mutation_paths = [
            "/api/v2/recommend/sessions",
            f"/api/v2/recommend/sessions/{created['id']}/batch",
            f"/api/v2/recommend/sessions/{created['id']}/previous",
            "/api/v2/feedback",
            f"/api/v2/feedback/{recorded['id']}/undo",
        ]
        invalid_payloads = [
            ("int", 123, self.post_json_status),
            ("list", ["oops"], self.post_json_status),
            ("bool", True, self.post_json_status),
            ("null", "null", self.post_raw_json_status),
        ]

        for path in mutation_paths:
            for label, value, sender in invalid_payloads:
                with self.subTest(path=path, payload_type=label):
                    status, payload = sender(path, value)
                    self.assertEqual(status, 400)
                    self.assertIn("JSON body", payload["error"])
                    self.assertIn("object", payload["error"])

    def test_create_restore_next_and_previous_keep_three_channels_independent(self):
        created = self.create_session()
        self.assertEqual(created["schema_version"], 2)
        self.assertEqual(set(created["channels"]), {"电影", "电视剧", "动漫"})

        movie_first = created["channels"]["电影"]["batch"]
        anime_first = created["channels"]["动漫"]["batch"]
        self.assertEqual(movie_first["index"], 1)
        self.assertEqual(anime_first["index"], 1)

        movie_next = self.post_json(
            f"/api/v2/recommend/sessions/{created['id']}/batch",
            {"schema_version": 2, "channel": "电影", "reason": "太相似"},
        )
        self.assertEqual(movie_next["batch"]["index"], 2)
        self.assertEqual(movie_next["restore"]["channels"]["电影"]["active_batch"], 2)
        self.assertEqual(movie_next["restore"]["channels"]["动漫"]["active_batch"], 1)
        self.assertFalse(set(movie_first["item_keys"]) & set(movie_next["batch"]["item_keys"]))
        self.assertEqual(movie_next["batch"]["reason_adjustment"]["mode"], "novelty")
        self.assertNotIn("profile", movie_next["batch"]["reason_adjustment"])

        movie_previous = self.post_json(
            f"/api/v2/recommend/sessions/{created['id']}/previous",
            {"schema_version": 2, "channel": "电影"},
        )
        self.assertEqual(movie_previous["batch"]["id"], movie_first["id"])

        restored = self.get_json(f"/api/v2/recommend/sessions/{created['id']}")
        self.assertEqual(restored["channels"]["电影"]["batch"]["id"], movie_first["id"])
        self.assertEqual(restored["channels"]["动漫"]["batch"]["id"], anime_first["id"])
        sample_item = restored["channels"]["电影"]["batch"]["items"][0]
        self.assertIn("score_breakdown", sample_item)
        self.assertIn("short_reason", sample_item)
        self.assertIn("conflicts", sample_item)
        self.assertIn("media_status", sample_item)

    def test_feedback_and_undo_round_trip_returns_restore_metadata(self):
        created = self.create_session()
        movie_item_key = created["channels"]["电影"]["batch"]["items"][0]["item_key"]

        recorded = self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "profile_key": "profile-1",
            "session_id": created["id"],
            "event_type": "not-tonight",
            "scope": "session",
            "item_key": movie_item_key,
            "payload": {"pace": "slow", "cookie": "secret-cookie"},
        })
        self.assertEqual(recorded["schema_version"], 2)
        self.assertEqual(recorded["event_type"], "not-tonight")
        self.assertIn("restore", recorded)
        self.assertNotIn("secret-cookie", json.dumps(recorded, ensure_ascii=False))

        undone = self.post_json(
            f"/api/v2/feedback/{recorded['id']}/undo",
            {"schema_version": 2},
        )
        self.assertEqual(undone["schema_version"], 2)
        self.assertEqual(undone["undone_event_id"], recorded["id"])
        self.assertIn("restore", undone)
        restored = self.api.session_service.restore_session(created["id"])
        channel_name = next(
            name
            for name, state in restored.channels.items()
            if any(recommendation_item_key(item) == movie_item_key for item in state["items"])
        )
        self.assertNotIn(movie_item_key, restored.channels[channel_name]["excluded_keys"])
        rerecorded = self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "profile_key": "profile-1",
            "session_id": created["id"],
            "event_type": "not-tonight",
            "scope": "session",
            "item_key": movie_item_key,
        })
        self.assertNotEqual(rerecorded["id"], recorded["id"])

    def test_permanent_feedback_without_session_still_uses_feedback_service_contract(self):
        recorded = self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "profile_key": "profile-1",
            "event_type": "more-like-this",
            "scope": "permanent",
            "item_key": "external:standalone-item",
            "payload": {"feature": "genre:drama"},
        })

        self.assertEqual(recorded["event_type"], "more-like-this")
        self.assertEqual(recorded["session_id"], "")
        with self.api.database.connection() as connection:
            row = connection.execute(
                "SELECT event_type, item_key FROM feedback_events WHERE id = ?",
                (recorded["id"],),
            ).fetchone()
        self.assertEqual((row["event_type"], row["item_key"]), ("more-like-this", "external:standalone-item"))

    def test_not_tonight_feedback_skips_exact_future_item_and_preserves_history(self):
        created = self.create_session(batch_size=1)
        channel_name, channel = self.first_nonempty_channel(created)
        first_batch = channel["batch"]
        session = self.api.session_service.restore_session(created["id"])
        future_item = session.channels[channel_name]["items"][1]
        excluded_key = recommendation_item_key(future_item)

        self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "session_id": created["id"],
            "event_type": "not-tonight",
            "scope": "session",
            "item_key": excluded_key,
        })
        next_batch = self.post_json(
            f"/api/v2/recommend/sessions/{created['id']}/batch",
            {"schema_version": 2, "channel": channel_name},
        )
        restored_previous = self.post_json(
            f"/api/v2/recommend/sessions/{created['id']}/previous",
            {"schema_version": 2, "channel": channel_name},
        )

        self.assertNotIn(excluded_key, next_batch["batch"]["item_keys"])
        self.assertEqual(restored_previous["batch"]["id"], first_batch["id"])

    def test_watched_feedback_updates_library_and_seeds_new_session_seen_items(self):
        created = self.create_session(batch_size=4)
        _, channel = self.first_nonempty_channel(created)
        watched_key = channel["batch"]["items"][0]["item_key"]

        self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "session_id": created["id"],
            "event_type": "watched",
            "scope": "permanent",
            "item_key": watched_key,
        })
        watched_records = self.api.session_service.library_items(states=["watched"])
        fresh = self.create_session(rated_items=[], batch_size=4)
        fresh_keys = {
            item_key
            for state in fresh["channels"].values()
            for item_key in state["batch"]["item_keys"]
        }

        self.assertEqual([record["item_key"] for record in watched_records], [watched_key])
        self.assertNotIn(watched_key, fresh_keys)

    def test_watched_seen_semantics_merge_into_duplicate_caller_rated_item(self):
        created = self.create_session(batch_size=4)
        _, channel = self.first_nonempty_channel(created)
        watched_item = channel["batch"]["items"][0]
        watched_key = watched_item["item_key"]
        self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "session_id": created["id"],
            "event_type": "watched",
            "scope": "permanent",
            "item_key": watched_key,
        })
        caller_item = {
            "title": watched_item["title"],
            "media_type": watched_item["media_type"],
            "douban_id": watched_item["douban_id"],
            "summary": "caller richer summary",
            "tags": ["caller-tag"],
        }

        merged = self.api._rated_items({"rated_items": [caller_item]})
        fresh = self.create_session(rated_items=[caller_item], batch_size=4)
        fresh_keys = {
            item_key
            for state in fresh["channels"].values()
            for item_key in state["batch"]["item_keys"]
        }

        self.assertEqual(len(merged), 1)
        self.assertEqual(merged[0].summary, "caller richer summary")
        self.assertIn("caller-tag", merged[0].tags)
        self.assertIn("看过", merged[0].tags)
        self.assertNotIn(watched_key, fresh_keys)

    def test_want_feedback_updates_library_state_to_wanted(self):
        created = self.create_session()
        _, channel = self.first_nonempty_channel(created)
        wanted_key = channel["batch"]["items"][0]["item_key"]

        self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "session_id": created["id"],
            "event_type": "want",
            "scope": "permanent",
            "item_key": wanted_key,
        })

        wanted_records = self.api.session_service.library_items(states=["wanted"])
        self.assertEqual([record["item_key"] for record in wanted_records], [wanted_key])

    def test_undo_watched_and_want_restore_prior_candidate_library_state(self):
        for event_type, expected_state in (("watched", "watched"), ("want", "wanted")):
            with self.subTest(event_type=event_type):
                created = self.create_session()
                _, channel = self.first_nonempty_channel(created)
                item_key = channel["batch"]["items"][0]["item_key"]
                recorded = self.post_json("/api/v2/feedback", {
                    "schema_version": 2,
                    "session_id": created["id"],
                    "event_type": event_type,
                    "scope": "permanent",
                    "item_key": item_key,
                })
                self.assertEqual(self.api.session_service.library_items(states=[expected_state])[0]["item_key"], item_key)

                self.post_json(
                    f"/api/v2/feedback/{recorded['id']}/undo",
                    {"schema_version": 2},
                )
                restored = {
                    row["item_key"]: row
                    for row in self.api.session_service.library_items(states=["candidate"])
                }
                self.assertEqual(restored[item_key]["state"], "candidate")

    def test_every_recommendation_item_key_resolves_to_same_catalog_title_identity(self):
        channel_name = next(iter(self.create_session()["channels"]))
        created = self.create_session(
            rated_items=[],
            candidates_csv="",
            candidate_items=[
                {
                    "title": "Same title",
                    "year": 2001,
                    "media_type": channel_name,
                    "douban_rating": 9.1,
                    "vote_count": 1000,
                },
                {
                    "title": "Same title",
                    "year": 2024,
                    "media_type": channel_name,
                    "douban_rating": 9.0,
                    "vote_count": 900,
                },
            ],
            use_sample_candidates=False,
            batch_size=2,
        )
        returned = created["channels"][channel_name]["batch"]["items"]

        self.assertEqual(len(returned), 2)
        self.assertEqual(len({item["item_key"] for item in returned}), 2)
        for item in returned:
            title = self.get_json(f"/api/v2/titles/{item['item_key']}")
            self.assertEqual((title["title"], title["year"]), (item["title"], item["year"]))

    def test_unsafe_external_identifier_returns_single_segment_catalog_key(self):
        channel_name = next(iter(self.create_session()["channels"]))
        for index, identifier in enumerate(
            ("provider/..\\title?token=secret#fragment%2F", "foo..bar", "..."),
            start=1,
        ):
            with self.subTest(identifier=identifier):
                created = self.create_session(
                    rated_items=[],
                    candidates_csv="",
                    candidate_items=[
                        {
                            "title": f"Unsafe external identity {index}",
                            "year": 2024,
                            "media_type": channel_name,
                            "douban_id": identifier,
                            "douban_rating": 9.0,
                            "vote_count": 1000,
                        }
                    ],
                    use_sample_candidates=False,
                    batch_size=1,
                )
                item = created["channels"][channel_name]["batch"]["items"][0]

                self.assertRegex(item["item_key"], r"^external:[0-9a-f]{24}$")
                self.assertFalse(any(marker in item["item_key"] for marker in ("/", "\\", "..", "?", "#", "%")))
                title = self.get_json(f"/api/v2/titles/{item['item_key']}")
                self.assertEqual((title["title"], title["year"]), (item["title"], item["year"]))

    def test_create_session_rejects_malformed_language_configuration(self):
        cases = [
            ("language", "not-an-object"),
            ("language.endpoint", {"endpoint": 123, "model": "demo"}),
            ("language.model", {"endpoint": "http://127.0.0.1:11434", "model": 123}),
            ("language.api_key", {"endpoint": "http://127.0.0.1:11434", "model": "demo", "api_key": 123}),
            ("language.model", {"endpoint": "http://127.0.0.1:11434"}),
            ("language.endpoint", {"model": "demo"}),
        ]
        for field, language in cases:
            with self.subTest(field=field, language=language):
                self.assert_bad_request_field(
                    "/api/v2/recommend/sessions",
                    self.session_payload(language=language),
                    field,
                )

    def test_omitted_language_config_parses_locally_without_building_remote_adapter(self):
        def unexpected_factory(**_kwargs):
            self.fail("remote language adapter must not be built")

        self.api.language_adapter_factory = unexpected_factory
        text = "悬疑电影"
        expected = json.loads(json.dumps(parse_recommendation_intent(text).to_dict(), ensure_ascii=False))
        for language in (None, {}):
            with self.subTest(language=language):
                overrides = {"intent_text": text}
                if language is not None:
                    overrides["language"] = language
                created = self.create_session(**overrides)
                self.assertEqual(created["intent"], expected)

    def test_explicit_language_adapter_changes_intent_and_api_key_is_memory_only(self):
        secret = "language-api-secret"
        captured = {}

        class FakeAdapter:
            def parse(self, text, evidence_catalog):
                captured["parse"] = (text, evidence_catalog)
                return RecommendationIntent(genres=("remote-genre",), free_text=text)

        def factory(**kwargs):
            captured["config"] = kwargs
            return FakeAdapter()

        self.api.language_adapter_factory = factory
        created = self.create_session(
            intent_text="model-owned parsing",
            language={
                "endpoint": "http://127.0.0.1:11434/v1/chat/completions",
                "model": "demo",
                "api_key": secret,
            },
        )

        self.assertEqual(created["intent"]["genres"], ["remote-genre"])
        self.assertEqual(captured["config"]["api_key"], secret)
        self.assertEqual(captured["parse"], ("model-owned parsing", {}))
        self.assertNotIn(secret, json.dumps(created, ensure_ascii=False))
        with self.api.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT intent_json AS payload FROM recommendation_sessions
                UNION ALL SELECT channels_json FROM recommendation_sessions
                UNION ALL SELECT payload_json FROM recommendation_batches
                UNION ALL SELECT payload_json FROM library_items
                UNION ALL SELECT payload_json FROM feedback_events
                """
            ).fetchall()
        self.assertNotIn(secret, "\n".join(str(row["payload"] or "") for row in rows))

    def test_explicit_language_failure_falls_back_to_local_parser(self):
        class FailingAdapter:
            def parse(self, text, evidence_catalog):
                raise RuntimeError("model failed")

        self.api.language_adapter_factory = lambda **_kwargs: FailingAdapter()
        text = "悬疑电影"
        created = self.create_session(
            intent_text=text,
            language={"endpoint": "http://127.0.0.1:11434", "model": "demo"},
        )

        expected = json.loads(json.dumps(parse_recommendation_intent(text).to_dict(), ensure_ascii=False))
        self.assertEqual(created["intent"], expected)

    def test_intent_user_text_secrets_are_scrubbed_from_response_and_sqlite(self):
        intent_text = (
            "悬疑电影 token=intent-token Authorization: Bearer intent-bearer "
            "https://intent-user:intent-password@example.com/path?api_key=intent-url-secret#intent-fragment"
        )

        created = self.create_session(intent_text=intent_text)
        with self.api.database.connection() as connection:
            intent_json = connection.execute(
                "SELECT intent_json FROM recommendation_sessions WHERE id = ?",
                (created["id"],),
            ).fetchone()["intent_json"]

        self.assertTrue(created["id"])
        self.assertIn("https://example.com/path", created["intent"]["free_text"])
        for secret in (
            "intent-token",
            "intent-bearer",
            "intent-user",
            "intent-password",
            "intent-url-secret",
            "intent-fragment",
        ):
            self.assertNotIn(secret, json.dumps(created["intent"], ensure_ascii=False))
            self.assertNotIn(secret, intent_json)

    def test_v2_routes_reject_unsupported_schema_version(self):
        status, payload = self.post_json_status(
            "/api/v2/recommend/sessions",
            self.session_payload(schema_version=1),
        )
        self.assertEqual(status, 400)
        self.assertIn("schema_version", payload["error"])

    def test_create_session_does_not_echo_cookie_or_secret_fields(self):
        response = self.create_session(
            cookie="bid=secret-cookie-value; ck=hidden",
            openai_api_key="secret-api-key",
            subscription_url="https://secret.invalid/subscription",
        )
        serialized = json.dumps(response, ensure_ascii=False)
        self.assertNotIn("secret-cookie-value", serialized)
        self.assertNotIn("hidden", serialized)
        self.assertNotIn("secret-api-key", serialized)
        self.assertNotIn("subscription", serialized)

    def test_unknown_session_and_feedback_event_return_404(self):
        status, payload = self.request("/api/v2/recommend/sessions/missing-session", method="GET")
        self.assertEqual(status, 404)
        self.assertIn("not found", payload["error"])

        created = self.create_session()
        status, payload = self.post_json_status(
            "/api/v2/feedback",
            {
                "schema_version": 2,
                "session_id": created["id"],
                "event_type": "not-tonight",
                "scope": "session",
                "item_key": "missing-item",
            },
        )
        self.assertEqual(status, 404)
        self.assertIn("not found", payload["error"])

        status, payload = self.post_json_status(
            "/api/v2/feedback/missing-event/undo",
            {"schema_version": 2},
        )
        self.assertEqual(status, 404)
        self.assertIn("not found", payload["error"])

    def test_v2_post_routes_require_explicit_schema_version_2(self):
        created = self.create_session()
        channel_name, channel_state = self.first_nonempty_channel(created)
        item_key = channel_state["batch"]["items"][0]["item_key"]

        recorded = self.post_json(
            "/api/v2/feedback",
            {
                "schema_version": 2,
                "profile_key": "profile-1",
                "session_id": created["id"],
                "event_type": "not-tonight",
                "scope": "session",
                "item_key": item_key,
            },
        )

        invalid_requests = [
            (
                "/api/v2/recommend/sessions",
                {key: value for key, value in self.session_payload().items() if key != "schema_version"},
                "missing",
            ),
            ("/api/v2/recommend/sessions", self.session_payload(schema_version="2"), "string"),
            (
                f"/api/v2/recommend/sessions/{created['id']}/batch",
                {"channel": channel_name},
                "missing",
            ),
            (
                f"/api/v2/recommend/sessions/{created['id']}/batch",
                {"schema_version": "2", "channel": channel_name},
                "string",
            ),
            (
                f"/api/v2/recommend/sessions/{created['id']}/previous",
                {"channel": channel_name},
                "missing",
            ),
            (
                f"/api/v2/recommend/sessions/{created['id']}/previous",
                {"schema_version": "2", "channel": channel_name},
                "string",
            ),
            (
                "/api/v2/feedback",
                {
                    "profile_key": "profile-1",
                    "session_id": created["id"],
                    "event_type": "not-tonight",
                    "scope": "session",
                    "item_key": item_key,
                },
                "missing",
            ),
            (
                "/api/v2/feedback",
                {
                    "schema_version": "2",
                    "profile_key": "profile-1",
                    "session_id": created["id"],
                    "event_type": "not-tonight",
                    "scope": "session",
                    "item_key": item_key,
                },
                "string",
            ),
            (f"/api/v2/feedback/{recorded['id']}/undo", {}, "missing"),
            (f"/api/v2/feedback/{recorded['id']}/undo", {"schema_version": "2"}, "string"),
        ]

        for path, payload, label in invalid_requests:
            with self.subTest(path=path, label=label):
                status, body = self.post_json_status(path, payload)
                self.assertEqual(status, 400)
                self.assertIn("schema_version", body["error"])

        restored = self.get_json(f"/api/v2/recommend/sessions/{created['id']}")
        self.assertEqual(restored["schema_version"], 2)

    def test_create_session_keeps_only_local_media_and_scrubs_response_and_database_secrets(self):
        channel_name, _ = self.first_nonempty_channel(self.create_session())
        secret_url = "https://viewer:session-secret@example.com/subject/42/?token=url-secret#frag-url"
        secret_cover = "https://cdn.example/poster.jpg?signature=cover-secret#frag-cover"
        secret_source = "https://source.example/list?token=source-secret#frag-source"
        secret_photo = "https://photos.example/actor.jpg?token=photo-secret#frag-photo"

        response = self.create_session(
            candidates_csv="",
            candidate_items=[
                {
                    "title": "external media candidate",
                    "media_type": channel_name,
                    "douban_id": "external-media-item",
                    "url": secret_url,
                    "cover": secret_cover,
                    "source": secret_source,
                    "summary": "safe summary token=summary-secret",
                    "raw": {
                        "people_photos": {"Actor": secret_photo},
                        "authorization": "Bearer nested-auth-secret",
                    },
                },
                {
                    "title": "fake local media candidate",
                    "media_type": channel_name,
                    "douban_id": "fake-local-media-item",
                    "cover": "/media/not-a-real-asset.png",
                    "raw": {"people_photos": {"Actor": "/media/not-a-real-person.png"}},
                },
            ],
            use_sample_candidates=False,
            batch_size=2,
        )

        external = self.find_item_by_id(response, "external-media-item")
        fake_local = self.find_item_by_id(response, "fake-local-media-item")
        self.assertEqual(external["url"], "https://example.com/subject/42/")
        self.assertEqual(external["cover"], "")
        self.assertEqual(external["source"], "external_url")
        self.assertEqual(external["people_photos"], {})
        self.assertEqual(external["media_status"]["poster"], "designed-fallback")
        self.assertEqual(fake_local["cover"], "")
        self.assertEqual(fake_local["people_photos"], {})
        self.assertEqual(fake_local["media_status"]["poster"], "designed-fallback")
        self.assertTrue(response["id"])

        self.post_json("/api/v2/feedback", {
            "schema_version": 2,
            "session_id": response["id"],
            "event_type": "watched",
            "scope": "permanent",
            "item_key": external["item_key"],
            "payload": {
                "cookie": "db-cookie-secret",
                "nested": {
                    "api_key": "db-api-secret",
                    "url": "https://user:db-password@example.com/path?token=db-url-secret#db-fragment",
                },
            },
        })
        with self.api.database.connection() as connection:
            stored = connection.execute(
                """
                SELECT channels_json AS payload FROM recommendation_sessions
                UNION ALL SELECT payload_json FROM recommendation_batches
                UNION ALL SELECT payload_json FROM library_items
                UNION ALL SELECT payload_json FROM feedback_events
                """
            ).fetchall()

        self.assert_no_secret_echo(
            response,
            "session-secret",
            "url-secret",
            "frag-url",
            "cover-secret",
            "frag-cover",
            "source-secret",
            "frag-source",
            "summary-secret",
            "photo-secret",
            "frag-photo",
            "nested-auth-secret",
        )
        serialized_db = "\n".join(str(row["payload"] or "") for row in stored)
        for secret in (
            "session-secret",
            "url-secret",
            "frag-url",
            "cover-secret",
            "frag-cover",
            "source-secret",
            "frag-source",
            "summary-secret",
            "photo-secret",
            "frag-photo",
            "nested-auth-secret",
            "db-cookie-secret",
            "db-api-secret",
            "db-password",
            "db-url-secret",
            "db-fragment",
        ):
            self.assertNotIn(secret, serialized_db)

    def test_create_session_retains_only_media_store_verified_local_assets(self):
        stored = self.create_verified_media_asset()
        channel_name = next(iter(self.create_session()["channels"]))

        response = self.create_session(
            rated_items=[],
            candidates_csv="",
            candidate_items=[
                {
                    "title": "verified local media candidate",
                    "media_type": channel_name,
                    "douban_id": "verified-local-media-item",
                    "cover": stored.local_url,
                    "raw": {"people_photos": {"Actor": stored.local_url}},
                }
            ],
            use_sample_candidates=False,
            batch_size=1,
        )

        item = self.find_item_by_id(response, "verified-local-media-item")
        self.assertEqual(item["cover"], stored.local_url)
        self.assertEqual(item["people_photos"], {"Actor": stored.local_url})
        self.assertEqual(item["media_status"]["poster"], "ready")
        with urllib.request.urlopen(f"http://127.0.0.1:{self.port}{stored.local_url}", timeout=5) as media_response:
            self.assertEqual(media_response.status, 200)
            self.assertEqual(media_response.read(), stored.path.read_bytes())

    def test_candidate_url_fetch_results_do_not_echo_input_secrets_in_session_or_batch(self):
        secret_input_url = "https://viewer:input-secret@example.com/list?token=input-token#input-fragment"
        secret_item_url = "https://service:result-secret@example.com/subject/200/?token=result-token#result-fragment"
        secret_cover = "https://img.example/poster.jpg?signature=cover-token#cover-fragment"
        secret_photo = "https://photos.example/actor.jpg?token=photo-token#photo-fragment"
        module_name = "douban_recommender.recommendation_api.fetch_url_candidates"

        channel_name, _ = self.first_nonempty_channel(self.create_session())
        with mock.patch(module_name, side_effect=lambda urls: [
            MediaItem(
                title="url candidate one",
                media_type=channel_name,
                douban_rating=9.9,
                vote_count=999999,
                summary="quality candidate",
                douban_id="url-candidate-1",
                url=secret_item_url,
                cover=secret_cover,
                source=f"douban_page:{secret_input_url}",
                raw={"people_photos": {"Actor": secret_photo}},
            ),
            MediaItem(
                title="url candidate two",
                media_type=channel_name,
                douban_rating=9.8,
                vote_count=999998,
                summary="quality candidate",
                douban_id="url-candidate-2",
                url=secret_item_url,
                cover=secret_cover,
                source=f"douban_page:{secret_input_url}",
                raw={"people_photos": {"Actor": secret_photo}},
            ),
        ]) as fake_fetch:
            created = self.create_session(
                candidates_csv="",
                candidate_urls=[secret_input_url],
                use_sample_candidates=False,
                batch_size=1,
            )
            fake_fetch.assert_called_once_with([secret_input_url])

        first_item = self.find_item_by_id(created, "url-candidate-1")
        self.assertEqual(first_item["url"], "https://example.com/subject/200/")
        self.assertEqual(first_item["cover"], "")
        self.assertEqual(first_item["source"], "douban_page")
        self.assertEqual(first_item["people_photos"], {})
        self.assertEqual(first_item["media_status"]["poster"], "designed-fallback")

        next_batch = self.post_json(
            f"/api/v2/recommend/sessions/{created['id']}/batch",
            {"schema_version": 2, "channel": channel_name},
        )
        restored = self.get_json(f"/api/v2/recommend/sessions/{created['id']}")

        for payload in (created, next_batch, restored):
            self.assert_no_secret_echo(
                payload,
                "input-secret",
                "input-token",
                "input-fragment",
                "result-secret",
                "result-token",
                "result-fragment",
                "cover-token",
                "cover-fragment",
                "photo-token",
                "photo-fragment",
            )


if __name__ == "__main__":
    unittest.main()
