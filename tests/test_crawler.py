import unittest

from douban_recommender.crawler import (
    build_user_collection_url,
    normalize_douban_user_id,
    parse_user_collection_html,
)


COLLECT_HTML = """
<html><body>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/33404425/">
        <img alt="隐秘的角落" src="https://img.example/cover.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/33404425/"><em>隐秘的角落</em></a>
        </li>
        <li class="intro">2020 / 中国大陆 / 剧情 悬疑 犯罪 / 辛爽 / 秦昊 王景春</li>
        <li>
          <span class="rating5-t"></span>
          <span class="date">2024-01-01</span>
        </li>
        <li><span class="comment">孩子、家庭与犯罪的阴影</span></li>
      </ul>
    </div>
  </div>
  <div class="item">
    <div class="pic">
      <a href="https://movie.douban.com/subject/30468961/">
        <img alt="想见你" src="https://img.example/want.jpg">
      </a>
    </div>
    <div class="info">
      <ul>
        <li class="title">
          <a href="https://movie.douban.com/subject/30468961/"><em>想见你</em></a>
        </li>
        <li class="intro">2019 / 中国台湾 / 爱情 悬疑 奇幻 / 黄天仁 / 柯佳嬿 许光汉</li>
        <li><span class="date">2024-02-02</span></li>
      </ul>
    </div>
  </div>
</body></html>
"""


class CrawlerParserTests(unittest.TestCase):
    def test_normalize_douban_user_id_accepts_plain_id(self):
        self.assertEqual(normalize_douban_user_id("moviefan123"), "moviefan123")

    def test_normalize_douban_user_id_extracts_people_url(self):
        url = "https://www.douban.com/people/moviefan123/collect"
        self.assertEqual(normalize_douban_user_id(url), "moviefan123")

    def test_build_user_collection_url_for_collect(self):
        url = build_user_collection_url("moviefan123", "collect", 30)
        self.assertEqual(url, "https://movie.douban.com/people/moviefan123/collect?start=30&sort=time&rating=all&filter=all&mode=grid")

    def test_parse_user_collection_html_extracts_title_rating_and_url(self):
        items = parse_user_collection_html(COLLECT_HTML, status="collect")

        self.assertEqual(len(items), 2)
        first = items[0]
        self.assertEqual(first.title, "隐秘的角落")
        self.assertEqual(first.my_rating, 5)
        self.assertEqual(first.year, 2020)
        self.assertEqual(first.media_type, "电影")
        self.assertIn("剧情", first.genres)
        self.assertIn("悬疑", first.genres)
        self.assertIn("犯罪", first.genres)
        self.assertIn("中国大陆", first.countries)
        self.assertIn("看过", first.tags)
        self.assertEqual(first.douban_id, "33404425")
        self.assertEqual(first.cover, "https://img.example/cover.jpg")
        self.assertEqual(first.summary, "孩子、家庭与犯罪的阴影")

    def test_parse_user_collection_html_handles_no_rating(self):
        items = parse_user_collection_html(COLLECT_HTML, status="wish")

        second = items[1]
        self.assertEqual(second.title, "想见你")
        self.assertIsNone(second.my_rating)
        self.assertIn("想看", second.tags)

    def test_crawl_user_collections_uses_collect_and_wish_until_empty_page(self):
        from douban_recommender.crawler import crawl_user_collections

        calls = []

        def fake_fetcher(user_id, status, start, cookie="", timeout=12):
            calls.append((user_id, status, start, cookie))
            if start == 0:
                return COLLECT_HTML
            return "<html><body></body></html>"

        result = crawl_user_collections(
            "https://www.douban.com/people/moviefan123/",
            cookie="bid=secret",
            max_pages=2,
            include_wish=True,
            fetcher=fake_fetcher,
            sleep_seconds=0,
        )

        self.assertEqual(result.pages_ok, 4)
        self.assertEqual(result.pages_failed, 0)
        self.assertGreaterEqual(len(result.items), 4)
        self.assertEqual(calls[0], ("moviefan123", "collect", 0, "bid=secret"))
        self.assertEqual(calls[2], ("moviefan123", "wish", 0, "bid=secret"))
        self.assertEqual(result.stopped_reason, "\u5df2\u5230\u8fbe\u7a7a\u767d\u5206\u9875")

    def test_crawl_user_collections_redacts_cookie_from_errors(self):
        from douban_recommender.crawler import crawl_user_collections

        def failing_fetcher(user_id, status, start, cookie="", timeout=12):
            raise RuntimeError(f"request failed with {cookie}")

        result = crawl_user_collections(
            "moviefan123",
            cookie="bid=secret-cookie-value; ck=hidden",
            max_pages=1,
            include_wish=False,
            fetcher=failing_fetcher,
            sleep_seconds=0,
        )

        joined = "\n".join(result.errors)
        self.assertEqual(result.pages_failed, 1)
        self.assertNotIn("secret-cookie-value", joined)
        self.assertNotIn("hidden", joined)
        self.assertIn("<redacted>", joined)

    def test_crawl_user_collections_redacts_cookie_values_and_partial_headers_from_errors(self):
        from douban_recommender.crawler import crawl_user_collections

        cookie = "bid=secret-cookie-value; ck=hidden-token"

        leak_messages = [
            "request failed: secret-cookie-value",
            "request failed: ck=hidden-token",
            "request failed: bid=secret-cookie-value;ck=hidden-token",
            "request failed: Cookie: bid=secret-cookie-value",
        ]

        for leak_message in leak_messages:
            with self.subTest(leak_message=leak_message):
                def failing_fetcher(user_id, status, start, cookie="", timeout=12):
                    raise RuntimeError(leak_message)

                result = crawl_user_collections(
                    "moviefan123",
                    cookie=cookie,
                    max_pages=1,
                    include_wish=False,
                    fetcher=failing_fetcher,
                    sleep_seconds=0,
                )

                joined = "\n".join(result.errors)
                self.assertEqual(result.pages_failed, 1)
                self.assertNotIn("secret-cookie-value", joined)
                self.assertNotIn("hidden-token", joined)
                self.assertNotIn("bid=secret-cookie-value", joined)
                self.assertNotIn("ck=hidden-token", joined)
                self.assertIn("<redacted>", joined)

    def test_crawl_user_collections_clamps_zero_max_pages_to_one_page(self):
        from douban_recommender.crawler import crawl_user_collections

        calls = []

        def fake_fetcher(user_id, status, start, cookie="", timeout=12):
            calls.append((status, start, timeout))
            return COLLECT_HTML

        result = crawl_user_collections(
            "moviefan123",
            max_pages=0,
            include_wish=False,
            fetcher=fake_fetcher,
            sleep_seconds=0,
        )

        self.assertEqual(calls, [("collect", 0, 12)])
        self.assertEqual(result.pages_ok, 1)
        self.assertEqual(result.pages_failed, 0)


if __name__ == "__main__":
    unittest.main()
