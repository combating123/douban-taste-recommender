import unittest

from douban_recommender.candidate_planner import CandidateQuery
from douban_recommender.douban_sources import fetch_candidates_from_plan, fetch_explore, subject_detail_urls
from douban_recommender.models import MediaItem


class SubjectDetailParseTests(unittest.TestCase):
    def test_parse_subject_detail_html_extracts_summary_people_and_metadata(self):
        from douban_recommender.douban_sources import parse_subject_detail_html

        html = """
        <html><head><meta property="og:image" content="https://img.example/poster.jpg"></head>
        <body>
          <span property="v:itemreviewed">隐秘的角落</span>
          <a rel="v:directedBy">辛爽</a>
          <a rel="v:starring">秦昊</a><a rel="v:starring">王景春</a>
          <span property="v:genre">剧情</span><span property="v:genre">悬疑</span>
          <span class="pl">制片国家/地区:</span> 中国大陆<br/>
          <span property="v:initialReleaseDate" content="2020-06-16">2020</span>
          <span property="v:summary">孩子、家庭与犯罪的阴影。</span>
        </body></html>
        """

        item = parse_subject_detail_html(html, url="https://movie.douban.com/subject/33404425/")

        self.assertEqual(item.title, "隐秘的角落")
        self.assertEqual(item.douban_id, "33404425")
        self.assertEqual(item.cover, "https://img.example/poster.jpg")
        self.assertEqual(item.summary, "孩子、家庭与犯罪的阴影。")
        self.assertEqual(item.directors, ["辛爽"])
        self.assertEqual(item.casts, ["秦昊", "王景春"])
        self.assertEqual(item.genres, ["剧情", "悬疑"])
        self.assertEqual(item.countries, ["中国大陆"])
        self.assertEqual(item.year, 2020)


class CandidateFetchPlanTests(unittest.TestCase):
    def test_fetch_candidates_from_plan_dedupes_and_keeps_partial_success(self):
        plan = [
            CandidateQuery("movie_quality", "电影,剧情", media_type="电影"),
            CandidateQuery("anime_quality", "动画", media_type="动漫"),
            CandidateQuery("bad", "bad"),
        ]

        def fake_fetcher(tags, sort="U", start=0, limit=20):
            if tags == "bad":
                raise RuntimeError("network failed")
            return [
                MediaItem(title="共同条目", douban_id="1", media_type="电影"),
                MediaItem(
                    title=tags,
                    douban_id=tags,
                    media_type="动漫" if tags == "动画" else "电影",
                ),
            ]

        report = fetch_candidates_from_plan(plan, fetcher=fake_fetcher, sleep_seconds=0)

        self.assertEqual(len([item for item in report.items if item.douban_id == "1"]), 1)
        self.assertTrue(any(item.media_type == "动漫" for item in report.items))
        self.assertEqual(report.failed_queries, 1)
        self.assertGreaterEqual(report.successful_queries, 2)

    def test_fetch_explore_surfaces_douban_security_message_as_failure(self):
        def fake_fetcher(url, accept_json=True):
            return '{"msg":"检测到有异常请求从您的IP发出，请登录再试!","r":1}'.encode("utf-8")

        with self.assertRaisesRegex(RuntimeError, "豆瓣探索接口返回风控"):
            fetch_explore("动漫", fetcher=fake_fetcher)

    def test_candidate_plan_stops_after_repeated_security_failures(self):
        plan = [CandidateQuery(f"q{i}", "动漫", media_type="动漫") for i in range(30)]
        calls = []

        def blocked_fetcher(tags, sort="U", start=0, limit=20):
            calls.append(tags)
            raise RuntimeError("豆瓣探索接口返回风控或错误：检测到异常请求")

        report = fetch_candidates_from_plan(plan, fetcher=blocked_fetcher, sleep_seconds=0)

        self.assertLess(len(calls), len(plan))
        self.assertEqual(report.failed_queries, len(calls))
        self.assertTrue(any("已提前停止" in error for error in report.errors))

    def test_subject_detail_urls_prioritize_mobile_douban_page(self):
        item = MediaItem(
            title="隐秘的角落",
            douban_id="33404425",
            url="https://movie.douban.com/subject/33404425/",
        )

        urls = subject_detail_urls(item)

        self.assertEqual(urls[0], "https://m.douban.com/movie/subject/33404425/")
        self.assertIn("https://movie.douban.com/subject/33404425/", urls)


if __name__ == "__main__":
    unittest.main()
