import json
import tempfile
import threading
import unittest
import urllib.error
import urllib.request
from unittest import mock
from http.server import ThreadingHTTPServer
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.models import MediaItem
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
        try:
            from douban_recommender.recommendation_api import RecommendationApi
        except ImportError:
            self.api = None
        else:
            database = AppDatabase(Path(self.temp.name) / "cinescope.db")
            database.initialize()
            self.api = RecommendationApi(database)
            web_module.RECOMMENDATION_API = self.api
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        web_module.RECOMMENDATION_API = self.original_api
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
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
            return error.code, json.loads(error.read().decode("utf-8"))

    def post_json(self, path, payload):
        status, body = self.request(path, method="POST", payload=payload)
        self.assertEqual(status, 200, body)
        return body

    def post_json_status(self, path, payload):
        return self.request(path, method="POST", payload=payload)

    def get_json(self, path):
        status, body = self.request(path, method="GET")
        self.assertEqual(status, 200, body)
        return body

    def assert_no_secret_echo(self, payload, *secrets):
        serialized = json.dumps(payload, ensure_ascii=False)
        for secret in secrets:
            self.assertNotIn(secret, serialized)

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

    def test_create_session_returns_three_distinct_counts(self):
        response = self.post_json("/api/v2/recommend/sessions", self.session_payload(limit=160))
        anime = response["channels"]["动漫"]
        self.assertIn("pool_size", anime)
        self.assertIn("matched_size", anime)
        self.assertIn("visible_size", anime)
        self.assertGreater(anime["pool_size"], anime["matched_size"])
        self.assertGreater(anime["matched_size"], anime["visible_size"])

    def test_feedback_api_does_not_accept_unknown_permanent_scope(self):
        status, payload = self.post_json_status("/api/v2/feedback", {
            "schema_version": 2,
            "event_type": "not-tonight",
            "scope": "permanent",
            "item_key": "x",
        })
        self.assertEqual(status, 400)
        self.assertIn("scope", payload["error"])

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

    def test_create_session_sanitizes_candidate_item_urls_cover_and_source(self):
        channel_name, _ = self.first_nonempty_channel(self.create_session())
        secret_url = "https://viewer:session-secret@example.com/subject/42/?token=url-secret#frag-url"
        secret_cover = "https://cdn.example/poster.jpg?signature=cover-secret#frag-cover"
        secret_source = "https://source.example/list?token=source-secret#frag-source"

        response = self.create_session(
            candidates_csv="",
            candidate_items=[
                {
                    "title": "sanitized candidate",
                    "media_type": channel_name,
                    "douban_id": "sanitized-item",
                    "url": secret_url,
                    "cover": secret_cover,
                    "source": secret_source,
                    "summary": "safe summary",
                }
            ],
            use_sample_candidates=False,
            batch_size=1,
        )

        _, channel = self.first_nonempty_channel(response)
        item = channel["batch"]["items"][0]
        self.assertEqual(item["url"], "https://example.com/subject/42/")
        self.assertEqual(item["cover"], "https://cdn.example/poster.jpg")
        self.assertEqual(item["source"], "external_url")
        self.assert_no_secret_echo(
            response,
            "session-secret",
            "url-secret",
            "frag-url",
            "cover-secret",
            "frag-cover",
            "source-secret",
            "frag-source",
        )

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
        self.assertEqual(first_item["cover"], "https://img.example/poster.jpg")
        self.assertEqual(first_item["source"], "douban_page")
        self.assertEqual(first_item["people_photos"]["Actor"], "https://photos.example/actor.jpg")

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
