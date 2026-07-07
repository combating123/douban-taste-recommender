import json
import threading
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer

from douban_recommender.crawler import CrawlResult
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
            return json.loads(error.read().decode("utf-8"))

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

        def fake_crawl(user_id_or_url, cookie="", max_pages=8, include_wish=True):
            raise RuntimeError(f"crawler failed with Cookie: {cookie}")

        web_module.crawl_user_collections = fake_crawl
        try:
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


class WebApiShapeTests(unittest.TestCase):
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

    def test_handler_has_cache_methods(self):
        self.assertTrue(hasattr(Handler, "handle_cache_get"))
        self.assertTrue(hasattr(Handler, "handle_cache_delete"))


if __name__ == "__main__":
    unittest.main()
