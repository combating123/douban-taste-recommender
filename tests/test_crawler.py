import unittest
import io
import urllib.error

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

    def test_normalize_douban_user_id_uses_readable_chinese_errors(self):
        with self.assertRaises(ValueError) as empty_error:
            normalize_douban_user_id("")
        self.assertEqual(str(empty_error.exception), "请输入豆瓣用户 ID 或主页链接")

        with self.assertRaises(ValueError) as malformed_error:
            normalize_douban_user_id("https://example.com/not/douban")
        self.assertEqual(str(malformed_error.exception), "豆瓣用户 ID 或主页链接格式不正确")

    def test_build_user_collection_url_uses_readable_chinese_status_error(self):
        with self.assertRaises(ValueError) as status_error:
            build_user_collection_url("moviefan123", "done", 0)
        self.assertEqual(str(status_error.exception), "status 只能是 collect 或 wish")

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

    def test_parse_user_collection_html_infers_series_from_title_or_intro(self):
        html = """
        <html><body>
          <div class="item">
            <a href="https://movie.douban.com/subject/33404425/"><em>隐秘的角落 第一季</em></a>
            <li class="intro">2020 / 中国大陆 / 剧情 悬疑 犯罪 / 辛爽 / 秦昊</li>
          </div>
          <div class="item">
            <a href="https://movie.douban.com/subject/99999999/"><em>漫长的季节</em></a>
            <li class="intro">2023 / 中国大陆 / 电视剧 / 剧情 / 辛爽 / 范伟</li>
          </div>
        </body></html>
        """

        items = parse_user_collection_html(html, status="collect")

        self.assertEqual([item.media_type for item in items], ["电视剧", "电视剧"])

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
        self.assertEqual(result.stopped_reason, "已到达空白分页")

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

    def test_crawl_user_collections_classifies_403_login_redirect_as_cookie_needed(self):
        from douban_recommender.crawler import crawl_user_collections

        def forbidden_fetcher(user_id, status, start, cookie="", timeout=12):
            body = "<html><title>豆瓣 - 登录跳转页</title><body>请先登录后继续浏览</body></html>".encode("utf-8")
            raise urllib.error.HTTPError(
                url="https://movie.douban.com/people/moviefan123/collect",
                code=403,
                msg="Forbidden",
                hdrs={},
                fp=io.BytesIO(body),
            )

        result = crawl_user_collections(
            "moviefan123",
            max_pages=1,
            include_wish=False,
            fetcher=forbidden_fetcher,
            sleep_seconds=0,
        )

        self.assertEqual(result.pages_failed, 1)
        self.assertEqual(result.diagnostics[0].http_status, 403)
        self.assertEqual(result.diagnostics[0].classification, "login_required")
        self.assertIn("Cookie", result.diagnostics[0].message)
        self.assertIn("登录态", result.stopped_reason)
        self.assertIn("Cookie", result.errors[0])

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


class CrawlerDiagnosticTests(unittest.TestCase):
    def test_classify_login_required_page(self):
        from douban_recommender.crawler import classify_collection_page

        classification, message = classify_collection_page("<html>登录后查看更多 请登录</html>", 0)

        self.assertEqual(classification, "login_required")
        self.assertIn("需要 Cookie", message)

    def test_classify_security_check_page(self):
        from douban_recommender.crawler import classify_collection_page

        classification, message = classify_collection_page("<html>检测到有异常请求 captcha verify</html>", 0)

        self.assertEqual(classification, "security_check")
        self.assertIn("安全验证", message)

    def test_classify_nonempty_parse_failure(self):
        from douban_recommender.crawler import classify_collection_page

        html = '<a href="https://movie.douban.com/subject/1234567/">片名</a>'
        classification, message = classify_collection_page(html, 0)

        self.assertEqual(classification, "parse_failed_nonempty")
        self.assertIn("页面有内容", message)


class CrawlerScaleTests(unittest.TestCase):
    def make_page(self, status, start, count):
        rows = []
        for index in range(count):
            subject_id = 8000000 + start + index
            title = f"{status}-{start + index}"
            rows.append(
                f'<div class="item"><a href="https://movie.douban.com/subject/{subject_id}/">'
                f"<em>{title}</em></a><img alt=\"{title}\" src=\"https://img.example/{subject_id}.jpg\">"
                '<li class="intro">2024 / 中国大陆 / 剧情 / 导演 / 演员</li>'
                '<span class="rating5-t"></span></div>'
            )
        return "<html><body>" + "".join(rows) + "</body></html>"

    def test_crawl_default_pages_cover_242_collect_and_34_wish(self):
        from douban_recommender.crawler import crawl_user_collections

        def fake_fetcher(user_id, status, start, cookie="", timeout=12):
            if status == "collect" and start < 240:
                return self.make_page(status, start, 15)
            if status == "collect" and start == 240:
                return self.make_page(status, start, 2)
            if status == "wish" and start < 30:
                return self.make_page(status, start, 15)
            if status == "wish" and start == 30:
                return self.make_page(status, start, 4)
            return "<html><body></body></html>"

        result = crawl_user_collections(
            "moviefan123",
            max_pages=40,
            include_wish=True,
            expected_collect=242,
            expected_wish=34,
            fetcher=fake_fetcher,
            sleep_seconds=0,
        )

        self.assertEqual(len([x for x in result.items if x.source.endswith(":collect")]), 242)
        self.assertEqual(len([x for x in result.items if x.source.endswith(":wish")]), 34)
        self.assertEqual(result.completeness["collect_percent"], 100)
        self.assertEqual(result.completeness["wish_percent"], 100)
        self.assertGreater(len(result.diagnostics), 0)

    def test_crawl_clamps_max_pages_to_200(self):
        from douban_recommender.crawler import crawl_user_collections

        calls = []

        def fake_fetcher(user_id, status, start, cookie="", timeout=12):
            calls.append(start)
            return self.make_page(status, start, 15)

        crawl_user_collections(
            "moviefan123",
            max_pages=999,
            include_wish=False,
            fetcher=fake_fetcher,
            sleep_seconds=0,
        )

        self.assertEqual(len(calls), 200)


class CrawlerParserVariantTests(unittest.TestCase):
    def test_parse_subject_links_when_item_class_missing(self):
        from douban_recommender.crawler import parse_user_collection_html

        html = (
            '<html><body><div class="grid-view">'
            '<a href="https://movie.douban.com/subject/1292052/">'
            '<img alt="肖申克的救赎" src="https://img.example/s.jpg"></a>'
            '<span class="rating5-t"></span></div></body></html>'
        )

        items = parse_user_collection_html(html, status="collect")

        self.assertEqual(len(items), 1)
        self.assertEqual(items[0].title, "肖申克的救赎")
        self.assertEqual(items[0].douban_id, "1292052")
        self.assertEqual(items[0].cover, "https://img.example/s.jpg")

    def test_parse_anime_media_type_from_intro(self):
        from douban_recommender.crawler import parse_user_collection_html

        html = (
            '<div class="item"><a href="https://movie.douban.com/subject/20495023/">'
            '<em>排球少年</em></a><img alt="排球少年" src="https://img.example/h.jpg">'
            '<li class="intro">2014 / 日本 / 动画 运动 / 满仲劝 / 村濑步</li></div>'
        )

        items = parse_user_collection_html(html, status="collect")

        self.assertEqual(items[0].media_type, "动漫")


if __name__ == "__main__":
    unittest.main()
