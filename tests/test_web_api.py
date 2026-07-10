import io
import json
import time
import threading
import unittest
import urllib.error
import urllib.parse
import urllib.request
from http.server import ThreadingHTTPServer
from unittest import mock

from douban_recommender.crawler import CrawlResult
from douban_recommender.douban_sources import PosterSourceConfig
from douban_recommender.models import MediaItem
from douban_recommender.web import Handler
import douban_recommender.web as web_module


class WebApiTests(unittest.TestCase):
    def setUp(self):
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()

    def post_json(self, path, payload):
        data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )
        try:
            with urllib.request.urlopen(request, timeout=10) as response:
                return json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def get_raw(self, path):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}{path}", method="GET")
        with urllib.request.urlopen(request, timeout=10) as response:
            return response.status, response.headers.get("Content-Type"), response.read()

    def test_crawl_api_returns_items_and_never_echoes_cookie(self):
        original = web_module.crawl_user_collections

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            return CrawlResult(
                items=[
                    MediaItem(
                        title="\u9690\u79d8\u7684\u89d2\u843d",
                        my_rating=5,
                        media_type="\u7535\u89c6\u5267",
                        genres=["\u5267\u60c5", "\u60ac\u7591", "\u72af\u7f6a"],
                        url="https://movie.douban.com/subject/33404425/",
                        douban_id="33404425",
                        source="douban_user:collect",
                    )
                ],
                pages_ok=1,
                pages_failed=0,
                errors=["collect start=15: 页面结构变化"],
                stopped_reason="\u5df2\u5230\u8fbe\u7a7a\u767d\u5206\u9875",
            )

        web_module.crawl_user_collections = fake_crawl
        try:
            response = self.post_json("/api/crawl-douban", {
                "user_id_or_url": "moviefan123",
                "cookie": "bid=secret-cookie-value; ck=hidden",
                "max_pages": 1,
                "include_wish": True,
            })
        finally:
            web_module.crawl_user_collections = original

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertEqual(response["counts"]["items"], 1)
        self.assertEqual(response["counts"]["collect_count"], 1)
        self.assertEqual(response["counts"]["wish_count"], 0)
        self.assertEqual(response["counts"]["stopped_reason"], "\u5df2\u5230\u8fbe\u7a7a\u767d\u5206\u9875")
        self.assertEqual(response["errors"], ["collect start=15: 页面结构变化"])
        self.assertEqual(response["items"][0]["title"], "\u9690\u79d8\u7684\u89d2\u843d")
        self.assertNotIn("secret-cookie-value", serialized)
        self.assertNotIn("hidden", serialized)

    def test_crawl_api_counts_collect_and_wish_from_sources_and_tags(self):
        original = web_module.crawl_user_collections

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            return CrawlResult(
                items=[
                    MediaItem(title="看过影片", source="douban_user:collect", tags=["看过"]),
                    MediaItem(title="想看影片", source="douban_user:wish", tags=["想看"]),
                    MediaItem(title="标签想看", source="", tags=["想看"]),
                ],
                pages_ok=2,
                pages_failed=1,
                errors=["wish start=15: 超时"],
                stopped_reason="部分分页抓取失败",
            )

        web_module.crawl_user_collections = fake_crawl
        try:
            response = self.post_json("/api/crawl-douban", {"user_id_or_url": "moviefan123"})
        finally:
            web_module.crawl_user_collections = original

        self.assertEqual(response["counts"]["items"], 3)
        self.assertEqual(response["counts"]["collect_count"], 1)
        self.assertEqual(response["counts"]["wish_count"], 2)
        self.assertEqual(response["counts"]["pages_ok"], 2)
        self.assertEqual(response["counts"]["pages_failed"], 1)
        self.assertEqual(response["counts"]["stopped_reason"], "部分分页抓取失败")
        self.assertEqual(response["errors"], ["wish start=15: 超时"])

    def test_crawl_api_returns_recovery_plan_when_douban_requires_cookie(self):
        original = web_module.crawl_user_collections

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            from douban_recommender.crawler import PageDiagnostic

            return CrawlResult(
                items=[],
                pages_ok=0,
                pages_failed=2,
                errors=["collect start=0: HTTP 403：豆瓣要求登录态或 Cookie", "wish start=0: HTTP 403：豆瓣要求登录态或 Cookie"],
                stopped_reason="豆瓣要求登录态或 Cookie",
                diagnostics=[
                    PageDiagnostic(status="collect", start=0, url="https://movie.douban.com/people/x/collect", http_status=403, classification="login_required", message="HTTP 403：豆瓣要求登录态或 Cookie"),
                    PageDiagnostic(status="wish", start=0, url="https://movie.douban.com/people/x/wish", http_status=403, classification="login_required", message="HTTP 403：豆瓣要求登录态或 Cookie"),
                ],
            )

        web_module.crawl_user_collections = fake_crawl
        try:
            response = self.post_json("/api/crawl-douban", {"user_id_or_url": "moviefan123"})
        finally:
            web_module.crawl_user_collections = original

        self.assertEqual(response["recovery"]["status"], "needs_cookie")
        self.assertTrue(response["recovery"]["can_continue_without_sync"])
        self.assertIn("Cookie", response["recovery"]["headline"])
        self.assertIn("继续用高质量片库生成推荐", " ".join(response["recovery"]["actions"]))

    def test_blank_page_stop_with_expected_counts_is_success_not_cookie_recovery(self):
        original = web_module.crawl_user_collections

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True, expected_collect=None, expected_wish=None):
            items = [
                MediaItem(
                    title=f"看过{i}",
                    media_type="电影",
                    source="douban_user:collect",
                    tags=["看过"],
                )
                for i in range(244)
            ] + [
                MediaItem(
                    title=f"想看{i}",
                    media_type="电影",
                    source="douban_user:wish",
                    tags=["想看"],
                )
                for i in range(36)
            ]
            return CrawlResult(
                items=items,
                pages_ok=22,
                pages_failed=0,
                errors=[],
                stopped_reason="已到达空白分页",
            )

        web_module.crawl_user_collections = fake_crawl
        try:
            response = self.post_json("/api/sync-douban", {
                "user_id_or_url": "272042071",
                "cookie": "",
                "max_pages": 160,
                "include_wish": True,
                "expected_collect": 244,
                "expected_wish": 36,
            })
        finally:
            web_module.crawl_user_collections = original

        self.assertEqual(response["counts"]["collect_count"], 244)
        self.assertEqual(response["counts"]["wish_count"], 36)
        self.assertEqual(response["counts"]["pages_ok"], 22)
        self.assertEqual(response["counts"]["pages_failed"], 0)
        self.assertEqual(response["counts"]["stopped_reason"], "已到达空白分页")
        self.assertEqual(response["recovery"]["status"], "complete")
        self.assertFalse(response["recovery"]["can_continue_without_sync"])
        self.assertIn("同步完成", response["recovery"]["headline"])
        self.assertIn("空白分页", " ".join(response["recovery"]["actions"]))
        self.assertNotIn("Cookie", response["recovery"]["headline"])

    def test_sync_api_reports_input_analysis_for_tracked_profile_url(self):
        original = web_module.crawl_user_collections

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            from douban_recommender.crawler import PageDiagnostic

            self.assertEqual(
                user_id_or_url,
                "https://www.douban.com/people/272042071/?_dtcc=1&_i=33953249Yxbr5m",
            )
            self.assertEqual(cookie, "")
            return CrawlResult(
                items=[],
                pages_ok=0,
                pages_failed=2,
                stopped_reason="豆瓣要求登录态或 Cookie",
                diagnostics=[
                    PageDiagnostic(
                        status="collect",
                        start=0,
                        url="https://movie.douban.com/people/272042071/collect",
                        http_status=403,
                        classification="login_required",
                        message="HTTP 403：豆瓣要求登录态或 Cookie",
                    )
                ],
            )

        web_module.crawl_user_collections = fake_crawl
        try:
            response = self.post_json("/api/sync-douban", {
                "user_id_or_url": "https://www.douban.com/people/272042071/?_dtcc=1&_i=33953249Yxbr5m",
                "cookie": "",
                "max_pages": 1,
                "include_wish": True,
            })
        finally:
            web_module.crawl_user_collections = original

        self.assertNotIn("error", response)
        self.assertEqual(response["input_analysis"]["user_id"], "272042071")
        self.assertTrue(response["input_analysis"]["profile_url"])
        self.assertFalse(response["input_analysis"]["cookie_provided"])
        self.assertTrue(response["input_analysis"]["profile_url_is_not_cookie"])
        self.assertEqual(response["recovery"]["status"], "needs_cookie")

    def test_crawl_api_top_level_exception_redacts_cookie(self):
        original = web_module.crawl_user_collections
        errors = []
        original_urlopen = urllib.request.urlopen

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            raise RuntimeError(f"crawler failed with Cookie: {cookie}")

        def recording_urlopen(*args, **kwargs):
            try:
                return original_urlopen(*args, **kwargs)
            except urllib.error.HTTPError as error:
                errors.append(error)
                raise

        web_module.crawl_user_collections = fake_crawl
        try:
            with mock.patch("urllib.request.urlopen", side_effect=recording_urlopen):
                response = self.post_json("/api/crawl-douban", {
                    "user_id_or_url": "moviefan123",
                    "cookie": "bid=secret-cookie-value; ck=hidden-token",
                })
        finally:
            web_module.crawl_user_collections = original

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertIn("error", response)
        self.assertIn("<redacted>", response["error"])
        self.assertNotIn("secret-cookie-value", serialized)
        self.assertNotIn("hidden-token", serialized)
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].closed)

    def test_recommend_api_accepts_json_rated_items(self):
        response = self.post_json("/api/recommend", {
            "rated_items": [
                {
                    "title": "\u9690\u79d8\u7684\u89d2\u843d",
                    "my_rating": 5,
                    "media_type": "\u7535\u89c6\u5267",
                    "genres": ["\u5267\u60c5", "\u60ac\u7591", "\u72af\u7f6a"],
                    "tags": ["\u770b\u8fc7"],
                    "douban_id": "33404425",
                }
            ],
            "candidates_csv": "title,media_type,douban_rating,genres,tags\n\u65b0\u7247,\u7535\u5f71,8.1,\u5267\u60c5 / \u72af\u7f6a,\u73b0\u5b9e\u4e3b\u4e49\n",
            "fetch_douban": False,
            "use_sample_candidates": False,
            "include_movies": True,
            "include_series": True,
            "like_terms": "\u72af\u7f6a,\u73b0\u5b9e\u4e3b\u4e49",
            "dislike_terms": "\u751c\u5ba0",
            "limit": 5,
        })

        self.assertEqual(response["counts"]["rated"], 1)
        self.assertEqual(response["results"][0]["title"], "\u65b0\u7247")

    def test_recommend_api_uses_legacy_ratings_csv_without_crawled_items(self):
        response = self.post_json("/api/recommend", {
            "ratings_csv": "title,my_rating,media_type,genres,tags\n我的旧评分,5,电影,剧情,看过\n",
            "candidates_csv": "title,media_type,douban_rating,genres,tags\nCSV候选,电影,8.5,剧情,现实主义\n",
            "fetch_douban": False,
            "use_sample_candidates": False,
            "include_movies": True,
            "include_series": True,
            "like_terms": "剧情",
            "dislike_terms": "",
            "limit": 5,
        })

        self.assertEqual(response["counts"]["rated"], 1)
        self.assertEqual(response["counts"]["candidates"], 1)
        self.assertEqual(response["results"][0]["title"], "CSV候选")

    def test_recommend_api_does_not_double_count_sample_candidates_when_csv_candidates_exist(self):
        csv_text = (
            "title,media_type,douban_rating,genres,tags\n"
            "CSV候选A,电影,8.5,剧情,现实主义\n"
            "CSV候选B,电视剧,8.6,悬疑,剧集\n"
        )

        response = self.post_json("/api/recommend", {
            "ratings_csv": "title,my_rating,media_type,genres,tags\n我的旧评分,5,电影,剧情,看过\n",
            "candidates_csv": csv_text,
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "like_terms": "剧情,悬疑",
            "dislike_terms": "",
            "limit": 5,
        })

        self.assertEqual(response["counts"]["candidates"], 2)
        self.assertEqual({item["title"] for item in response["results"]}, {"CSV候选A", "CSV候选B"})

    def test_recommend_api_can_enrich_top_recommendations_with_subject_details(self):
        original = getattr(web_module, "enrich_media_items", None)
        calls = []

        def fake_enrich(items, limit=12, sleep_seconds=0.05):
            calls.append((len(items), limit))
            items[0].summary = "补全后的剧情简介"
            items[0].directors = ["辛爽"]
            items[0].casts = ["秦昊"]
            return items

        web_module.enrich_media_items = fake_enrich
        try:
            response = self.post_json("/api/recommend", {
                "ratings_csv": "title,my_rating,media_type,genres,tags\n我看过的片,5,电影,剧情,看过\n",
                "candidates_csv": "title,media_type,douban_rating,genres,tags,url,douban_id\n候选片,电影,8.6,剧情,现实主义,https://movie.douban.com/subject/33404425/,33404425\n",
                "fetch_douban": False,
                "use_sample_candidates": False,
                "include_movies": True,
                "include_series": True,
                "enrich_details": True,
                "limit": 5,
            })
        finally:
            if original is None:
                delattr(web_module, "enrich_media_items")
            else:
                web_module.enrich_media_items = original

        self.assertEqual(calls, [(1, 1)])
        self.assertEqual(response["results"][0]["summary"], "补全后的剧情简介")
        self.assertEqual(response["results"][0]["directors"], ["辛爽"])
        self.assertEqual(response["results"][0]["casts"], ["秦昊"])

    def test_recommend_api_defers_slow_enrichment_for_large_lists(self):
        original_poster_enrich = web_module.enrich_missing_posters_from_web_sources
        original_detail_enrich = web_module.enrich_media_items
        original_plan_fetch = web_module.fetch_candidates_from_plan
        original_legacy_fetch = web_module.fetch_douban_candidates
        poster_calls = []
        detail_calls = []
        douban_calls = []

        def fake_poster_enrich(items, limit=120, sleep_seconds=0.03, fetcher=None, max_seconds=14.0):
            poster_calls.append((len(items), limit, sleep_seconds, max_seconds))
            return 0

        def fake_detail_enrich(items, limit=12, sleep_seconds=0.05):
            detail_calls.append((len(items), limit, sleep_seconds))
            return items

        def fake_plan_fetch(*args, **kwargs):
            douban_calls.append(("plan", args, kwargs))
            return type("Report", (), {"items": []})()

        def fake_legacy_fetch(*args, **kwargs):
            douban_calls.append(("legacy", args, kwargs))
            return []

        try:
            web_module.enrich_missing_posters_from_web_sources = fake_poster_enrich
            web_module.enrich_media_items = fake_detail_enrich
            web_module.fetch_candidates_from_plan = fake_plan_fetch
            web_module.fetch_douban_candidates = fake_legacy_fetch
            response = self.post_json("/api/recommend", {
                "ratings_csv": "",
                "candidates_csv": "",
                "fetch_douban": True,
                "use_sample_candidates": True,
                "include_movies": True,
                "include_series": True,
                "include_anime": True,
                "enrich_details": True,
                "limit": 160,
            })
        finally:
            web_module.enrich_missing_posters_from_web_sources = original_poster_enrich
            web_module.enrich_media_items = original_detail_enrich
            web_module.fetch_candidates_from_plan = original_plan_fetch
            web_module.fetch_douban_candidates = original_legacy_fetch

        self.assertEqual(response["counts"]["target_limit"], 160)
        self.assertEqual(len(response["results"]), 160)
        self.assertEqual(douban_calls, [])
        self.assertEqual(poster_calls, [])
        self.assertEqual(detail_calls, [])
        self.assertTrue(response["counts"]["deferred_douban_fetch"])
        self.assertTrue(response["counts"]["deferred_enrichment"])
        self.assertGreaterEqual(response["counts"]["poster_rescue_pending"], 1)

    def test_enrich_posters_api_repairs_existing_snapshot_items(self):
        original_web_enrich = web_module.enrich_missing_posters_from_web_sources
        calls = []

        def fake_web_enrich(items, limit=120, sleep_seconds=0.03, fetcher=None, max_seconds=14.0):
            calls.append((len(items), limit, sleep_seconds, max_seconds))
            items[0].cover = "https://media.themoviedb.org/t/p/w500/social.jpg"
            items[0].douban_id = "tmdb-movie-37799"
            return 1

        try:
            web_module.enrich_missing_posters_from_web_sources = fake_web_enrich
            response = self.post_json("/api/enrich-posters", {
                "items": [{
                    "title": "\u793e\u4ea4\u7f51\u7edc",
                    "media_type": "\u7535\u5f71",
                    "douban_id": "premium-\u7535\u5f71-055",
                    "cover": "data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C/svg%3E",
                }],
                "limit": 160,
            })
        finally:
            web_module.enrich_missing_posters_from_web_sources = original_web_enrich

        self.assertEqual(response["counts"]["enriched"], 1)
        self.assertEqual(response["items"][0]["douban_id"], "tmdb-movie-37799")
        self.assertEqual(response["items"][0]["cover"], "https://media.themoviedb.org/t/p/w500/social.jpg")
        self.assertTrue(calls)
        self.assertLessEqual(calls[0][1], 160)

    def test_enrich_people_api_updates_single_detail_people_photos(self):
        original_detail_enrich = web_module.enrich_media_items
        calls = []

        def fake_detail_enrich(items, limit=1, sleep_seconds=0.05):
            calls.append((len(items), limit, sleep_seconds))
            items[0].directors = ["辛爽"]
            items[0].casts = ["秦昊", "王景春"]
            items[0].summary = "人物资料已补全。"
            items[0].raw = {
                "people_photos": {
                    "辛爽": "https://img.example/xinshuang.jpg",
                    "秦昊": "https://img.example/qinhao.jpg",
                }
            }
            return items

        try:
            web_module.enrich_media_items = fake_detail_enrich
            response = self.post_json("/api/enrich-people", {
                "item": {
                    "title": "人物可见过滤测试",
                    "media_type": "电视剧",
                    "douban_id": "12345",
                    "url": "https://movie.douban.com/subject/12345/",
                    "directors": ["辛爽"],
                    "casts": ["秦昊", "王景春"],
                }
            })
        finally:
            web_module.enrich_media_items = original_detail_enrich

        self.assertEqual(calls, [(1, 1, 0.01)])
        self.assertGreaterEqual(response["counts"]["people_photos"], 2)
        self.assertEqual(response["item"]["people_photos"]["辛爽"], "https://img.example/xinshuang.jpg")
        self.assertEqual(response["item"]["directors"], ["辛爽"])
        self.assertEqual(response["item"]["casts"], ["秦昊", "王景春"])

    def test_enrich_people_api_counts_only_current_visible_people_photos(self):
        original_detail_enrich = web_module.enrich_media_items

        def fake_detail_enrich(items, fetcher=None, limit=1, sleep_seconds=0.05, force_people_photos=False):
            items[0].directors = ["辛爽"]
            items[0].casts = ["秦昊"]
            items[0].raw = {
                "people_photos": {
                    "辛爽": "https://img.example/xinshuang.jpg",
                    "海街日记的剧照_1": "https://img.example/still.jpg",
                    "步履不停": "https://img.example/related-poster.jpg",
                }
            }
            return items

        try:
            web_module.enrich_media_items = fake_detail_enrich
            response = self.post_json("/api/enrich-people", {
                "item": {
                    "title": "人物可见过滤测试",
                    "media_type": "电视剧",
                    "douban_id": "12345",
                    "url": "https://movie.douban.com/subject/12345/",
                    "directors": ["镜头语言专家"],
                    "casts": ["戏剧张力担当"],
                    "people_photos": {
                        "无关缓存人物": "https://img.example/noise.jpg",
                    },
                }
            })
        finally:
            web_module.enrich_media_items = original_detail_enrich

        self.assertEqual(response["counts"]["people_photos"], 1)
        self.assertEqual(response["item"]["people_photos"], {"辛爽": "https://img.example/xinshuang.jpg"})
        self.assertNotIn("海街日记的剧照_1", response["item"]["people_photos"])

    def test_enrich_people_api_forces_people_photo_fetch_when_supported(self):
        original_detail_enrich = web_module.enrich_media_items
        seen = {}

        def fake_detail_enrich(items, limit=1, sleep_seconds=0.05, force_people_photos=False):
            seen["force_people_photos"] = force_people_photos
            items[0].raw["people_photos"] = {"导演甲": "https://img.example/director.jpg"}
            return items

        try:
            web_module.enrich_media_items = fake_detail_enrich
            response = self.post_json("/api/enrich-people", {
                "item": {
                    "title": "人物补图测试",
                    "media_type": "电视剧",
                    "douban_id": "subject-people-test",
                    "url": "https://movie.douban.com/subject/123/",
                    "summary": "已有简介",
                    "cover": "https://img.example/poster.jpg",
                    "genres": ["剧情"],
                    "directors": ["导演甲"],
                    "casts": ["演员乙"],
                }
            })
        finally:
            web_module.enrich_media_items = original_detail_enrich

        self.assertTrue(seen["force_people_photos"])
        self.assertEqual(response["item"]["people_photos"]["导演甲"], "https://img.example/director.jpg")

    def test_enrich_people_api_falls_back_to_public_portrait_resolver_when_douban_has_no_photos(self):
        original_detail_enrich = web_module.enrich_media_items
        original_resolver = getattr(web_module, "resolve_public_people_photos", None)
        seen = {}

        def fake_detail_enrich(items, fetcher=None, limit=1, sleep_seconds=0.05, force_people_photos=False):
            items[0].directors = ["导演甲"]
            items[0].casts = ["演员乙"]
            items[0].raw["people_photos"] = {}
            return items

        def fake_public_resolver(names):
            seen["names"] = list(names)
            return {
                "导演甲": "https://upload.wikimedia.org/director.jpg",
                "演员乙": "https://upload.wikimedia.org/cast.jpg",
            }

        try:
            web_module.enrich_media_items = fake_detail_enrich
            web_module.resolve_public_people_photos = fake_public_resolver
            response = self.post_json("/api/enrich-people", {
                "item": {
                    "title": "公共头像兜底测试",
                    "media_type": "电影",
                    "douban_id": "public-photo-test",
                    "url": "https://movie.douban.com/subject/999/",
                    "directors": ["导演甲"],
                    "casts": ["演员乙"],
                }
            })
        finally:
            web_module.enrich_media_items = original_detail_enrich
            if original_resolver is None:
                delattr(web_module, "resolve_public_people_photos")
            else:
                web_module.resolve_public_people_photos = original_resolver

        self.assertEqual(seen["names"], ["导演甲", "演员乙"])
        self.assertEqual(response["counts"]["people_photos"], 2)
        self.assertEqual(response["item"]["people_photos"]["导演甲"], "https://upload.wikimedia.org/director.jpg")
        self.assertEqual(response["item"]["people_photos"]["演员乙"], "https://upload.wikimedia.org/cast.jpg")

    def test_enrich_people_api_uses_public_resolver_for_partial_people_photo_gap(self):
        original_detail_enrich = web_module.enrich_media_items
        original_resolver = getattr(web_module, "resolve_public_people_photos", None)
        seen = {}

        def fake_detail_enrich(items, fetcher=None, limit=1, sleep_seconds=0.05, force_people_photos=False):
            items[0].directors = ["导演甲"]
            items[0].casts = ["演员乙"]
            items[0].raw["people_photos"] = {"导演甲": "https://img.example/director.jpg"}
            return items

        def fake_public_resolver(names):
            seen["names"] = list(names)
            return {"演员乙": "https://cdn.myanimelist.net/images/voiceactors/2/cast.jpg"}

        try:
            web_module.enrich_media_items = fake_detail_enrich
            web_module.resolve_public_people_photos = fake_public_resolver
            response = self.post_json("/api/enrich-people", {
                "item": {
                    "title": "部分人物补图测试",
                    "media_type": "动漫",
                    "douban_id": "partial-people-test",
                    "url": "https://movie.douban.com/subject/999/",
                    "directors": ["导演甲"],
                    "casts": ["演员乙"],
                }
            })
        finally:
            web_module.enrich_media_items = original_detail_enrich
            if original_resolver is None:
                delattr(web_module, "resolve_public_people_photos")
            else:
                web_module.resolve_public_people_photos = original_resolver

        self.assertEqual(seen["names"], ["演员乙"])
        self.assertEqual(response["counts"]["people_photos"], 2)
        self.assertEqual(response["item"]["people_photos"]["导演甲"], "https://img.example/director.jpg")
        self.assertEqual(response["item"]["people_photos"]["演员乙"], "https://cdn.myanimelist.net/images/voiceactors/2/cast.jpg")

    def test_enrich_people_api_uses_cookie_fetcher_without_echoing_cookie(self):
        original_detail_enrich = web_module.enrich_media_items
        original_fetch_detail = getattr(web_module, "fetch_douban_detail_html", None)
        seen = {}

        def fake_fetch_detail(url, cookie=""):
            seen["url"] = url
            seen["cookie"] = cookie
            return b"<html></html>"

        def fake_detail_enrich(items, fetcher=None, limit=1, sleep_seconds=0.05, force_people_photos=False):
            self.assertTrue(callable(fetcher))
            fetcher("https://movie.douban.com/subject/123/")
            items[0].raw["people_photos"] = {"导演甲": "https://img.example/director.jpg"}
            return items

        try:
            web_module.fetch_douban_detail_html = fake_fetch_detail
            web_module.enrich_media_items = fake_detail_enrich
            response = self.post_json("/api/enrich-people", {
                "cookie": "bid=secret-cookie; ck=hidden-token",
                "item": {
                    "title": "人物补图 Cookie 测试",
                    "media_type": "电视剧",
                    "douban_id": "123",
                    "url": "https://movie.douban.com/subject/123/",
                    "directors": ["导演甲"],
                    "casts": ["演员乙"],
                }
            })
        finally:
            web_module.enrich_media_items = original_detail_enrich
            if original_fetch_detail is None:
                delattr(web_module, "fetch_douban_detail_html")
            else:
                web_module.fetch_douban_detail_html = original_fetch_detail

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertEqual(seen["cookie"], "bid=secret-cookie; ck=hidden-token")
        self.assertNotIn("secret-cookie", serialized)
        self.assertNotIn("hidden-token", serialized)

    def test_enrich_posters_api_passes_optional_poster_source_config_without_echoing_keys(self):
        original_web_enrich = web_module.enrich_missing_posters_from_web_sources
        seen = {}

        def fake_web_enrich(items, limit=120, sleep_seconds=0.03, fetcher=None, max_seconds=14.0, source_config=None, progress_callback=None):
            seen["tmdb_api_key"] = source_config.tmdb_api_key
            seen["omdb_api_key"] = source_config.omdb_api_key
            seen["enable_omdb"] = source_config.enable_omdb
            seen["enable_anilist"] = source_config.enable_anilist
            seen["enable_jikan"] = source_config.enable_jikan
            seen["enable_tvmaze"] = source_config.enable_tvmaze
            items[0].cover = "https://image.tmdb.org/t/p/w500/api.jpg"
            return 1

        try:
            web_module.enrich_missing_posters_from_web_sources = fake_web_enrich
            response = self.post_json("/api/enrich-posters", {
                "items": [{
                    "title": "\u6559\u7236",
                    "media_type": "\u7535\u5f71",
                    "cover": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
                }],
                "poster_sources": {
                    "tmdb_api_key": "secret-tmdb",
                    "omdb_api_key": "secret-omdb",
                    "enable_omdb": True,
                    "enable_anilist": False,
                    "enable_jikan": True,
                    "enable_tvmaze": False,
                },
            })
        finally:
            web_module.enrich_missing_posters_from_web_sources = original_web_enrich

        serialized = json.dumps(response, ensure_ascii=False)
        self.assertEqual(seen["tmdb_api_key"], "secret-tmdb")
        self.assertEqual(seen["omdb_api_key"], "secret-omdb")
        self.assertTrue(seen["enable_omdb"])
        self.assertFalse(seen["enable_anilist"])
        self.assertTrue(seen["enable_jikan"])
        self.assertFalse(seen["enable_tvmaze"])
        self.assertNotIn("secret-tmdb", serialized)
        self.assertNotIn("secret-omdb", serialized)

    def test_poster_source_summary_reports_tvmaze_without_api_key(self):
        config = PosterSourceConfig(enable_tvmaze=True)

        summary = web_module.poster_config_public_summary(config)

        self.assertIn("tvmaze_enabled", summary)
        self.assertTrue(summary["tvmaze_enabled"])

    def test_poster_jobs_api_reports_live_progress_and_repaired_items(self):
        original_web_enrich = web_module.enrich_missing_posters_from_web_sources

        def fake_web_enrich(items, limit=120, sleep_seconds=0.03, fetcher=None, max_seconds=14.0, source_config=None, progress_callback=None):
            items[0].cover = "https://image.tmdb.org/t/p/w500/job.jpg"
            if progress_callback:
                progress_callback({
                    "title": items[0].title,
                    "source": "TMDb API",
                    "status": "found",
                    "cover": items[0].cover,
                })
            return 1

        try:
            web_module.enrich_missing_posters_from_web_sources = fake_web_enrich
            created = self.post_json("/api/poster-jobs", {
                "items": [{
                    "title": "\u6559\u7236",
                    "media_type": "\u7535\u5f71",
                    "cover": "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
                }],
                "limit": 1,
            })
            job_id = created["job_id"]
            final = None
            for _ in range(20):
                status, _, body = self.get_raw(f"/api/poster-jobs/{job_id}")
                self.assertEqual(status, 200)
                final = json.loads(body.decode("utf-8"))
                if final["state"] == "done":
                    break
                time.sleep(0.05)
        finally:
            web_module.enrich_missing_posters_from_web_sources = original_web_enrich

        self.assertIsNotNone(final)
        self.assertEqual(final["state"], "done")
        self.assertEqual(final["done"], 1)
        self.assertEqual(final["found"], 1)
        self.assertEqual(final["events"][0]["source"], "TMDb API")
        self.assertEqual(final["items"][0]["cover"], "https://image.tmdb.org/t/p/w500/job.jpg")

    def test_recommend_api_backfills_anime_when_default_pool_lacks_it(self):
        response = self.post_json("/api/recommend", {
            "ratings_csv": "",
            "candidates_csv": "",
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "like_terms": "评分高，剧情好，叙事强，人物塑造扎实",
            "dislike_terms": "电视剧古装，注水剧",
            "enrich_details": False,
            "limit": 80,
        })

        media_types = {item["media_type"] for item in response["results"]}
        section_names = {section["name"] for section in response["sections"]}
        anime_titles = [item["title"] for item in response["results"] if item["media_type"] == "动漫"]

        self.assertIn("动漫", media_types)
        self.assertIn("动漫", section_names)
        self.assertGreaterEqual(len(anime_titles), 12)
        self.assertFalse({"千与千寻", "机器人总动员", "疯狂动物城", "寻梦环游记", "头脑特工队"} & set(anime_titles))
        self.assertGreater(response["counts"]["curated_candidates"], 0)

    def test_recommend_api_backfills_real_poster_urls_for_default_pool(self):
        response = self.post_json("/api/recommend", {
            "ratings_csv": "",
            "candidates_csv": "",
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "enrich_details": False,
            "limit": 30,
        })

        poster_urls = [item.get("cover") for item in response["results"] if item.get("cover")]

        self.assertGreaterEqual(len(poster_urls), 18)
        self.assertTrue(all("doubanio.com/view/photo" in url for url in poster_urls))

    def test_recommend_api_treats_large_limit_as_target_with_quality_expansion(self):
        response = self.post_json("/api/recommend", {
            "ratings_csv": "",
            "candidates_csv": "",
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "like_terms": "评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以",
            "dislike_terms": "电视剧古装，注水剧，低分狗血，粗制滥造",
            "enrich_details": False,
            "limit": 160,
        })

        self.assertEqual(response["counts"]["target_limit"], 160)
        self.assertEqual(response["counts"]["returned"], 160)
        self.assertGreaterEqual(response["counts"]["candidates"], 190)
        self.assertEqual(len(response["results"]), 160)
        media_types = {item["media_type"] for item in response["results"]}
        self.assertTrue({"电影", "电视剧", "动漫"}.issubset(media_types))
        self.assertGreaterEqual(sum(1 for item in response["results"] if item.get("cover")), 150)

    def test_large_recommend_api_balances_movie_series_and_anime(self):
        response = self.post_json("/api/recommend", {
            "ratings_csv": "",
            "candidates_csv": "",
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "like_terms": "评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以",
            "dislike_terms": "电视剧古装，注水剧，低分狗血，粗制滥造",
            "enrich_details": False,
            "limit": 160,
        })

        counts = {media_type: sum(1 for item in response["results"] if item["media_type"] == media_type) for media_type in ["电影", "电视剧", "动漫"]}
        self.assertGreaterEqual(counts["电影"], 40)
        self.assertGreaterEqual(counts["电视剧"], 40)
        self.assertGreaterEqual(counts["动漫"], 40)

    def test_large_recommend_api_avoids_stale_premium_poster_mismatches(self):
        response = self.post_json("/api/recommend", {
            "ratings_csv": "",
            "candidates_csv": "",
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "like_terms": "评分高，剧情好，叙事强，人物塑造扎实，电影/电视剧/动漫都可以",
            "dislike_terms": "电视剧古装，注水剧，低分狗血，粗制滥造",
            "enrich_details": False,
            "limit": 160,
        })

        covers = [item.get("cover", "") for item in response["results"]]
        real_posters = [url for url in covers if "doubanio.com" in url and not url.startswith("data:image/svg+xml")]
        designed_posters = [url for url in covers if url.startswith("data:image/svg+xml")]
        stale_premium_posters = [
            item
            for item in response["results"]
            if str(item.get("douban_id", "")).startswith("premium-")
            and "doubanio.com" in item.get("cover", "")
        ]

        self.assertTrue(all(covers))
        self.assertGreaterEqual(len(real_posters), 20)
        self.assertGreaterEqual(len(designed_posters), 100)
        self.assertEqual(stale_premium_posters, [])

    def test_image_proxy_streams_remote_image_without_cookie(self):
        original = getattr(web_module, "fetch_proxy_image", None)
        requested = []

        def fake_fetch(url):
            requested.append(url)
            return b"fake-image", "image/jpeg"

        web_module.fetch_proxy_image = fake_fetch
        try:
            status, content_type, body = self.get_raw("/api/image-proxy?url=https%3A%2F%2Fimg.example%2Fposter.jpg")
        finally:
            if original is None:
                delattr(web_module, "fetch_proxy_image")
            else:
                web_module.fetch_proxy_image = original

        self.assertEqual(status, 200)
        self.assertEqual(content_type, "image/jpeg")
        self.assertEqual(body, b"fake-image")
        self.assertEqual(requested, ["https://img.example/poster.jpg"])

    def test_fetch_proxy_image_reuses_memory_cache_to_avoid_remote_rate_limits(self):
        original_build_url_opener = web_module.build_url_opener
        original_cache = dict(getattr(web_module, "IMAGE_PROXY_CACHE", {}))
        calls = []

        class FakeResponse:
            headers = {"Content-Type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"\xff\xd8\xff\xe0cached-image"

        class FakeOpener:
            def open(self, request, timeout=0):
                calls.append(request.full_url)
                if len(calls) > 1:
                    raise urllib.error.HTTPError(
                        url=request.full_url,
                        code=429,
                        msg="Too Many Requests",
                        hdrs={},
                        fp=None,
                    )
                return FakeResponse()

        try:
            web_module.IMAGE_PROXY_CACHE.clear()
            web_module.build_url_opener = lambda: FakeOpener()
            first_data, first_type = web_module.fetch_proxy_image("https://img.example/cached.jpg")
            second_data, second_type = web_module.fetch_proxy_image("https://img.example/cached.jpg")
        finally:
            web_module.build_url_opener = original_build_url_opener
            web_module.IMAGE_PROXY_CACHE.clear()
            web_module.IMAGE_PROXY_CACHE.update(original_cache)

        self.assertEqual(len(calls), 1)
        self.assertEqual(first_data, second_data)
        self.assertEqual(first_type, second_type)

    def test_fetch_proxy_image_retries_direct_after_http_error_from_proxy_path(self):
        original_build_url_opener = web_module.build_url_opener
        original_build_opener = web_module.urllib.request.build_opener
        original_cache = dict(getattr(web_module, "IMAGE_PROXY_CACHE", {}))
        calls = []
        errors = []
        bodies = []

        class FakeResponse:
            headers = {"Content-Type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"\xff\xd8\xff\xe0direct-image"

        class ProxyOpener:
            def open(self, request, timeout=0):
                calls.append(("proxy", request.full_url))
                body = io.BytesIO(b"proxy throttled")
                error = urllib.error.HTTPError(
                    url=request.full_url,
                    code=429,
                    msg="Too Many Requests",
                    hdrs={},
                    fp=body,
                )
                bodies.append(body)
                errors.append(error)
                raise error

        class DirectOpener:
            def open(self, request, timeout=0):
                calls.append(("direct", request.full_url))
                return FakeResponse()

        try:
            web_module.IMAGE_PROXY_CACHE.clear()
            web_module.build_url_opener = lambda: ProxyOpener()
            web_module.urllib.request.build_opener = lambda *args, **kwargs: DirectOpener()
            data, content_type = web_module.fetch_proxy_image("https://upload.wikimedia.org/example.jpg")
        finally:
            web_module.build_url_opener = original_build_url_opener
            web_module.urllib.request.build_opener = original_build_opener
            web_module.IMAGE_PROXY_CACHE.clear()
            web_module.IMAGE_PROXY_CACHE.update(original_cache)

        self.assertEqual([kind for kind, _ in calls], ["proxy", "direct"])
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8"))
        self.assertTrue(all(error.closed for error in errors))
        self.assertTrue(all(body.closed for body in bodies))

    def test_fetch_proxy_image_tries_wikimedia_thumbnail_candidate_when_original_fails(self):
        original_build_url_opener = web_module.build_url_opener
        original_build_opener = web_module.urllib.request.build_opener
        original_cache = dict(getattr(web_module, "IMAGE_PROXY_CACHE", {}))
        calls = []
        errors = []
        bodies = []

        class FakeResponse:
            headers = {"Content-Type": "image/jpeg"}

            def __enter__(self):
                return self

            def __exit__(self, exc_type, exc, tb):
                return False

            def read(self):
                return b"\xff\xd8\xff\xe0thumb-image"

        class FallbackAwareOpener:
            def __init__(self, kind):
                self.kind = kind

            def open(self, request, timeout=0):
                calls.append((self.kind, request.full_url))
                if "/thumb/" in request.full_url:
                    return FakeResponse()
                body = io.BytesIO(b"service unavailable")
                error = urllib.error.HTTPError(
                    url=request.full_url,
                    code=503,
                    msg="temporarily unavailable",
                    hdrs={},
                    fp=body,
                )
                bodies.append(body)
                errors.append(error)
                raise error

        try:
            web_module.IMAGE_PROXY_CACHE.clear()
            web_module.build_url_opener = lambda: FallbackAwareOpener("proxy")
            web_module.urllib.request.build_opener = lambda *args, **kwargs: FallbackAwareOpener("direct")
            data, content_type = web_module.fetch_proxy_image(
                "https://upload.wikimedia.org/wikipedia/commons/8/81/Masami_Nagasawa_%40_Japan_Cuts_2012_-_10.jpg"
            )
        finally:
            web_module.build_url_opener = original_build_url_opener
            web_module.urllib.request.build_opener = original_build_opener
            web_module.IMAGE_PROXY_CACHE.clear()
            web_module.IMAGE_PROXY_CACHE.update(original_cache)

        tried_urls = [url for _, url in calls]
        self.assertTrue(any("/wikipedia/commons/thumb/8/81/" in url for url in tried_urls))
        self.assertEqual(content_type, "image/jpeg")
        self.assertTrue(data.startswith(b"\xff\xd8"))
        self.assertEqual(len(errors), 2)
        self.assertTrue(all(error.closed for error in errors))
        self.assertTrue(all(body.closed for body in bodies))

    def test_fetch_proxy_image_retries_direct_when_configured_proxy_refuses_connection(self):
        original_build_url_opener = web_module.build_url_opener
        original_build_opener = web_module.urllib.request.build_opener
        calls = []

        class FailingProxyOpener:
            def open(self, request, timeout=0):
                request.set_proxy("127.0.0.1:9", "https")
                calls.append(("proxy", request.host, timeout))
                raise urllib.error.URLError(ConnectionRefusedError(10061, "proxy refused"))

        class FakeResponse:
            headers = {"Content-Type": "image/webp; charset=binary"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"direct-image"

        class DirectOpener:
            def open(self, request, timeout=0):
                calls.append(("direct", request.host, timeout))
                return FakeResponse()

        try:
            web_module.build_url_opener = lambda: FailingProxyOpener()
            web_module.urllib.request.build_opener = lambda *handlers: DirectOpener()

            data, content_type = web_module.fetch_proxy_image("https://img.example/poster.webp")
        finally:
            web_module.build_url_opener = original_build_url_opener
            web_module.urllib.request.build_opener = original_build_opener

        self.assertEqual(data, b"direct-image")
        self.assertEqual(content_type, "image/webp")
        self.assertEqual([kind for kind, _, _ in calls], ["proxy", "direct"])
        self.assertEqual(calls[-1][1], "img.example")

    def test_fetch_proxy_image_rejects_douban_antibot_html_instead_of_serving_it_as_image(self):
        original_build_url_opener = web_module.build_url_opener

        class FakeResponse:
            headers = {"Content-Type": "text/html; charset=utf-8"}

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return b"<script>document.cookie='__tst_status=1'</script>"

        class HtmlOpener:
            def open(self, request, timeout=0):
                return FakeResponse()

        try:
            web_module.build_url_opener = lambda: HtmlOpener()
            with self.assertRaisesRegex(ValueError, "non-image"):
                web_module.fetch_proxy_image("https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg")
        finally:
            web_module.build_url_opener = original_build_url_opener

    def test_enrich_people_api_can_fill_better_days_known_people_photos_without_cookie(self):
        response = self.post_json("/api/enrich-people", {
            "item": {
                "title": "\u5c11\u5e74\u7684\u4f60",
                "media_type": "\u7535\u5f71",
                "douban_id": "30166972",
                "url": "https://movie.douban.com/subject/30166972/",
                "directors": ["\u66fe\u56fd\u7965"],
                "casts": ["\u5468\u51ac\u96e8", "\u6613\u70ca\u5343\u73ba", "\u5c39\u6609", "\u5468\u4e5f"],
            }
        })

        self.assertGreaterEqual(response["counts"]["people_photos"], 5)
        for name in ["\u66fe\u56fd\u7965", "\u5468\u51ac\u96e8", "\u6613\u70ca\u5343\u73ba", "\u5c39\u6609", "\u5468\u4e5f"]:
            self.assertIn(name, response["item"]["people_photos"])


    def test_large_recommend_api_does_not_return_numbered_placeholder_titles(self):
        import re

        response = self.post_json("/api/recommend", {
            "ratings_csv": "",
            "candidates_csv": "",
            "fetch_douban": False,
            "use_sample_candidates": True,
            "include_movies": True,
            "include_series": True,
            "include_anime": True,
            "like_terms": "??????????????????",
            "dislike_terms": "??????????????",
            "enrich_details": False,
            "limit": 160,
        })
        bad_titles = [item["title"] for item in response["results"] if re.match(r"^(?:\u7535\u5f71\u7b56\u5c55|\u5267\u96c6\u7b56\u5c55|\u52a8\u6f2b\u5267\u96c6\u7b56\u5c55)\d+$", item.get("title") or "")]

        self.assertEqual(bad_titles, [])


class WebApiShapeTests(unittest.TestCase):
    def test_public_people_resolver_uses_jikan_when_wikipedia_has_no_thumbnail(self):
        original_build_url_opener = web_module.build_url_opener
        web_module.PUBLIC_PEOPLE_PHOTO_CACHE.clear()
        web_module.PUBLIC_PEOPLE_PHOTO_NEGATIVE_CACHE.clear()
        calls = []

        class FakeResponse:
            def __init__(self, payload: bytes):
                self.payload = payload

            def __enter__(self):
                return self

            def __exit__(self, *args):
                return False

            def read(self):
                return self.payload

        class FakeOpener:
            def open(self, request, timeout=0):
                url = request.full_url if hasattr(request, "full_url") else str(request)
                calls.append(url)
                if "wikipedia.org" in url:
                    raise urllib.error.URLError("not found")
                if "api.jikan.moe/v4/people" in url:
                    return FakeResponse(json.dumps({
                        "data": [{
                            "name": "Shinichirou Watanabe",
                            "images": {"jpg": {"image_url": "https://cdn.myanimelist.net/images/voiceactors/3/48770.jpg"}},
                        }]
                    }).encode("utf-8"))
                raise AssertionError(url)

        try:
            web_module.build_url_opener = lambda: FakeOpener()
            photos = web_module.resolve_public_people_photos(["\u6e21\u8fb9\u4fe1\u4e00\u90ce"])
        finally:
            web_module.build_url_opener = original_build_url_opener
            web_module.PUBLIC_PEOPLE_PHOTO_CACHE.clear()
            web_module.PUBLIC_PEOPLE_PHOTO_NEGATIVE_CACHE.clear()

        self.assertEqual(photos, {
            "\u6e21\u8fb9\u4fe1\u4e00\u90ce": "https://cdn.myanimelist.net/images/voiceactors/3/48770.jpg"
        })
        self.assertTrue(any("api.jikan.moe/v4/people" in url for url in calls))
        self.assertTrue(any("Shinichirou+Watanabe" in url or "Shinichiro+Watanabe" in url for url in calls))

    def test_filtered_people_photos_accepts_role_prefixed_keys(self):
        item = MediaItem(
            title="\u4eba\u7269\u524d\u7f00\u6d4b\u8bd5",
            directors=["\u8f9b\u723d"],
            casts=["\u79e6\u660a"],
            raw={
                "people_photos": {
                    "\u5bfc\u6f14:\u8f9b\u723d": "https://img.example/director.jpg",
                    "\u4e3b\u6f14:\u79e6\u660a": "https://img.example/cast.jpg",
                }
            },
        )

        self.assertEqual(web_module.filtered_people_photos_for_item(item), {
            "\u8f9b\u723d": "https://img.example/director.jpg",
            "\u79e6\u660a": "https://img.example/cast.jpg",
        })

    def test_build_recommendation_sections_groups_by_section(self):
        from douban_recommender.web import build_recommendation_sections
        from douban_recommender.recommender import Recommendation

        recs = [
            Recommendation(item=MediaItem(title="电影A"), score=90, section="必看 Top Picks"),
            Recommendation(item=MediaItem(title="动画B"), score=88, section="动漫"),
        ]

        sections = build_recommendation_sections(recs)

        self.assertEqual(sections[0]["name"], "必看 Top Picks")
        self.assertEqual(sections[0]["count"], 1)
        self.assertEqual(sections[1]["name"], "动漫")


    def test_sections_include_global_anime_subchannels(self):
        from douban_recommender.web import build_recommendation_sections
        from douban_recommender.recommender import Recommendation

        recs = [
            Recommendation(item=MediaItem(title="中国奇谭", media_type="动漫", countries=["中国大陆"]), score=90, section="动漫"),
            Recommendation(item=MediaItem(title="Arcane", media_type="动漫", countries=["美国"]), score=89, section="动漫"),
            Recommendation(item=MediaItem(title="虫师", media_type="动漫", countries=["日本"]), score=88, section="动漫"),
        ]

        names = [section["name"] for section in build_recommendation_sections(recs)]

        self.assertIn("动漫 · 国创动画", names)
        self.assertIn("动漫 · 欧美动画", names)
        self.assertIn("动漫 · 日漫精品", names)

    def test_quality_gate_drops_unrated_public_douban_noise_but_keeps_custom_items(self):
        from douban_recommender.web import filter_low_confidence_public_candidates

        rows = [
            MediaItem(title="无评分探索噪声", source="douban_plan:movie_quality:电影,犯罪", douban_rating=None),
            MediaItem(title="自定义无评分", source="csv", douban_rating=None),
            MediaItem(title="有评分豆瓣候选", source="douban_explore:电影:sort=U", douban_rating=8.2),
        ]

        filtered, removed = filter_low_confidence_public_candidates(rows)

        self.assertEqual(removed, 1)
        self.assertEqual([item.title for item in filtered], ["自定义无评分", "有评分豆瓣候选"])

    def test_handler_has_cache_methods(self):
        self.assertTrue(hasattr(Handler, "handle_cache_get"))
        self.assertTrue(hasattr(Handler, "handle_cache_delete"))


if __name__ == "__main__":
    unittest.main()
