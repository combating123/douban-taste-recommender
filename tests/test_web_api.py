import json
import threading
import unittest
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
        with urllib.request.urlopen(request, timeout=10) as response:
            return json.loads(response.read().decode("utf-8"))

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
        self.assertEqual(response["items"][0]["title"], "\u9690\u79d8\u7684\u89d2\u843d")
        self.assertNotIn("secret-cookie-value", serialized)
        self.assertNotIn("hidden", serialized)

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


if __name__ == "__main__":
    unittest.main()
