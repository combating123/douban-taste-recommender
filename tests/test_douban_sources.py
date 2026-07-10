import io
import json
import unittest
import urllib.error
from unittest import mock

from douban_recommender.candidate_planner import CandidateQuery
from douban_recommender.douban_sources import (
    enrich_media_items,
    enrich_missing_posters_from_web_sources,
    enrich_missing_posters_from_subject_suggest,
    fetch_anilist_suggestions,
    fetch_candidates_from_plan,
    fetch_explore,
    fetch_jikan_suggestions,
    fetch_omdb_suggestions,
    fetch_tmdb_api_suggestions,
    fetch_tvmaze_suggestions,
    fetch_wikipedia_image_suggestions,
    parse_anilist_results,
    parse_jikan_results,
    parse_subject_search_html,
    parse_subject_suggestions,
    parse_themoviedb_search_html,
    parse_tmdb_api_results,
    parse_tvmaze_result,
    PosterSourceConfig,
    subject_detail_urls,
)
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

    def test_parse_subject_detail_html_extracts_public_people_photos_when_present(self):
        from douban_recommender.douban_sources import parse_subject_detail_html

        html = """
        <html><body>
          <span property="v:itemreviewed">测试片</span>
          <a rel="v:directedBy">辛爽</a>
          <a rel="v:starring">秦昊</a>
          <li class="celebrity">
            <a href="/celebrity/1/">
              <img src="https://img.example/director.jpg" alt="辛爽">
              <span class="name">辛爽</span><span class="role">导演</span>
            </a>
          </li>
          <li class="celebrity">
            <a href="/celebrity/2/">
              <img src="https://img.example/cast.jpg" alt="秦昊">
              <span class="name">秦昊</span><span class="role">演员</span>
            </a>
          </li>
        </body></html>
        """

        item = parse_subject_detail_html(html, url="https://movie.douban.com/subject/1/")

        self.assertEqual(item.raw["people_photos"]["辛爽"], "https://img.example/director.jpg")
        self.assertEqual(item.raw["people_photos"]["秦昊"], "https://img.example/cast.jpg")

    def test_parse_subject_detail_html_does_not_treat_generic_stills_as_people_photos(self):
        from douban_recommender.douban_sources import parse_subject_detail_html

        html = """
        <html><body>
          <span property="v:itemreviewed">海街日记</span>
          <meta property="og:image" content="https://img.example/poster.jpg">
          <img alt="海街日记的剧照_1" src="https://img.example/still.jpg">
          <img alt="步履不停" src="https://img.example/related-poster.jpg">
        </body></html>
        """

        item = parse_subject_detail_html(html, url="https://m.douban.com/movie/subject/25895901/")

        self.assertNotIn("people_photos", item.raw)


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

    def test_enrich_media_items_can_force_fetch_when_people_photos_are_missing(self):
        calls = []
        item = MediaItem(
            title="人物补图测试",
            media_type="电视剧",
            douban_id="33404425",
            url="https://movie.douban.com/subject/33404425/",
            cover="https://img.example/poster.jpg",
            summary="已有剧情简介",
            genres=["剧情"],
            directors=["辛爽"],
            casts=["秦昊"],
        )
        html = """
        <html><head><meta property="og:image" content="https://img.example/poster.jpg"></head>
        <body>
          <span property="v:itemreviewed">人物补图测试</span>
          <a rel="v:directedBy">辛爽</a>
          <a rel="v:starring">秦昊</a>
          <span property="v:genre">剧情</span>
          <li class="celebrity">
            <img src="https://img.example/xinshuang.jpg" alt="辛爽">
            <span class="name">辛爽</span>
          </li>
          <li class="celebrity">
            <img src="https://img.example/qinhao.jpg" alt="秦昊">
            <span class="name">秦昊</span>
          </li>
        </body></html>
        """.encode("utf-8")

        def fake_fetcher(url):
            calls.append(url)
            return html

        enrich_media_items([item], fetcher=fake_fetcher, limit=1, sleep_seconds=0, force_people_photos=True)

        self.assertTrue(calls)
        self.assertEqual(item.raw["people_photos"]["辛爽"], "https://img.example/xinshuang.jpg")
        self.assertEqual(item.raw["people_photos"]["秦昊"], "https://img.example/qinhao.jpg")

    def test_enrich_media_items_resolves_premium_subject_before_people_fetch(self):
        from douban_recommender import douban_sources

        original_suggest = douban_sources.fetch_subject_suggestions
        calls = []
        item = MediaItem(
            title="\u6d77\u8857\u65e5\u8bb0",
            media_type="\u7535\u5f71",
            douban_id="premium-\u7535\u5f71-001",
            url="https://movie.douban.com/subject_search?search_text=%E6%B5%B7%E8%A1%97%E6%97%A5%E8%AE%B0",
            directors=["\u955c\u5934\u8bed\u8a00\u4e13\u5bb6"],
            casts=["\u620f\u5267\u5f20\u529b\u62c5\u5f53"],
            raw={},
        )

        def fake_suggest(title, fetcher=None, timeout=4):
            self.assertEqual(title, "\u6d77\u8857\u65e5\u8bb0")
            return [
                MediaItem(
                    title="\u6d77\u8857\u65e5\u8bb0",
                    media_type="\u7535\u5f71",
                    douban_id="25895901",
                    url="https://movie.douban.com/subject/25895901/",
                    cover="https://img.example/poster.jpg",
                    year=2015,
                )
            ]

        def fake_fetcher(url):
            calls.append(url)
            return b"""
            <html><head><meta property="og:image" content="https://img.example/poster.jpg"></head>
            <body>
              <span property="v:itemreviewed">\xe6\xb5\xb7\xe8\xa1\x97\xe6\x97\xa5\xe8\xae\xb0</span>
              <a rel="v:directedBy">\xe6\x98\xaf\xe6\x9e\x9d\xe8\xa3\x95\xe5\x92\x8c</a>
              <a rel="v:starring">\xe7\xbb\xab\xe6\xbf\x91\xe9\x81\xa5</a>
              <a rel="v:starring">\xe9\x95\xbf\xe6\xb3\xbd\xe9\x9b\x85\xe7\xbe\x8e</a>
              <li class="celebrity"><img alt="\xe6\x98\xaf\xe6\x9e\x9d\xe8\xa3\x95\xe5\x92\x8c" src="https://img.example/koreeda.jpg"><span class="name">\xe6\x98\xaf\xe6\x9e\x9d\xe8\xa3\x95\xe5\x92\x8c</span></li>
              <li class="celebrity"><img alt="\xe7\xbb\xab\xe6\xbf\x91\xe9\x81\xa5" src="https://img.example/ayase.jpg"><span class="name">\xe7\xbb\xab\xe6\xbf\x91\xe9\x81\xa5</span></li>
            </body></html>
            """

        try:
            douban_sources.fetch_subject_suggestions = fake_suggest
            douban_sources.enrich_media_items([item], fetcher=fake_fetcher, limit=1, sleep_seconds=0, force_people_photos=True)
        finally:
            douban_sources.fetch_subject_suggestions = original_suggest

        self.assertTrue(calls)
        self.assertEqual(item.douban_id, "25895901")
        self.assertEqual(item.directors, ["\u662f\u679d\u88d5\u548c"])
        self.assertEqual(item.casts[:2], ["\u7eeb\u6fd1\u9065", "\u957f\u6cfd\u96c5\u7f8e"])
        self.assertEqual(item.raw["people_photos"]["\u662f\u679d\u88d5\u548c"], "https://img.example/koreeda.jpg")
        self.assertEqual(item.raw["people_photos"]["\u7eeb\u6fd1\u9065"], "https://img.example/ayase.jpg")

    def test_force_people_enrichment_continues_from_mobile_to_desktop_when_mobile_lacks_people(self):
        from douban_recommender import douban_sources

        original_suggest = douban_sources.fetch_subject_suggestions
        calls = []
        item = MediaItem(
            title="\u6d77\u8857\u65e5\u8bb0",
            media_type="\u7535\u5f71",
            douban_id="premium-movie-59",
            directors=["\u955c\u5934\u8bed\u8a00\u4e13\u5bb6"],
            casts=["\u620f\u5267\u5f20\u529b\u62c5\u5f53"],
        )

        def fake_suggest(title):
            return [
                MediaItem(
                    title=title,
                    media_type="\u7535\u5f71",
                    douban_id="25895901",
                    url="https://movie.douban.com/subject/25895901/",
                    cover="https://img.example/poster.jpg",
                )
            ]

        def fake_fetcher(url):
            calls.append(url)
            if "m.douban.com" in url:
                return """
                <html><body>
                  <span property="v:itemreviewed">\u6d77\u8857\u65e5\u8bb0</span>
                  <meta property="og:image" content="https://img.example/mobile-poster.jpg">
                  <span property="v:summary">\u79fb\u52a8\u9875\u7b80\u4ecb</span>
                  <img alt="\u6d77\u8857\u65e5\u8bb0\u7684\u5267\u7167_1" src="https://img.example/still.jpg">
                </body></html>
                """
            return """
            <html><body>
              <span property="v:itemreviewed">\u6d77\u8857\u65e5\u8bb0</span>
              <a rel="v:directedBy">\u662f\u679d\u88d5\u548c</a>
              <a rel="v:starring">\u7eeb\u6fd1\u9065</a>
              <div class="celebrity"><span class="name">\u662f\u679d\u88d5\u548c</span><img src="https://img.example/koreeda.jpg"></div>
              <div class="celebrity"><span class="name">\u7eeb\u6fd1\u9065</span><img src="https://img.example/ayase.jpg"></div>
            </body></html>
            """

        try:
            douban_sources.fetch_subject_suggestions = fake_suggest
            douban_sources.enrich_media_items([item], fetcher=fake_fetcher, limit=1, sleep_seconds=0, force_people_photos=True)
        finally:
            douban_sources.fetch_subject_suggestions = original_suggest

        self.assertTrue(any("m.douban.com" in url for url in calls))
        self.assertTrue(any("movie.douban.com" in url for url in calls))
        self.assertEqual(item.directors, ["\u662f\u679d\u88d5\u548c"])
        self.assertEqual(item.casts, ["\u7eeb\u6fd1\u9065"])
        self.assertEqual(item.raw["people_photos"], {
            "\u662f\u679d\u88d5\u548c": "https://img.example/koreeda.jpg",
            "\u7eeb\u6fd1\u9065": "https://img.example/ayase.jpg",
        })


    def test_subject_suggest_parser_keeps_only_exact_title_match(self):
        title = "\u6559\u7236"
        payload = """
        [
          {"img":"https:\\/\\/img9.doubanio.com\\/view\\/photo\\/s_ratio_poster\\/public\\/p616779645.jpg","title":"\u6559\u7236","url":"https:\\/\\/movie.douban.com\\/subject\\/1291841\\/?suggest=x","type":"movie","year":"1972","id":"1291841"},
          {"img":"https:\\/\\/img3.doubanio.com\\/view\\/photo\\/s_ratio_poster\\/public\\/p2194138787.jpg","title":"\u6559\u72362","url":"https:\\/\\/movie.douban.com\\/subject\\/1299131\\/","type":"movie","year":"1974","id":"1299131"}
        ]
        """

        suggestions = parse_subject_suggestions(payload.encode("utf-8"), expected_title=title)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, title)
        self.assertEqual(suggestions[0].douban_id, "1291841")
        self.assertEqual(suggestions[0].cover, "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg")
        self.assertEqual(suggestions[0].year, 1972)

    def test_subject_search_html_parser_uses_window_data_exact_primary_title(self):
        title = "\u6559\u7236"
        html = """
        <script>
        window.__DATA__ = {"items":[
          {"tpl_name":"search_subject","id":1291841,"title":"\u6559\u7236 The Godfather\u200e (1972)","cover_url":"https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg","url":"https://movie.douban.com/subject/1291841/"},
          {"tpl_name":"search_subject","id":1299131,"title":"\u6559\u72362 The Godfather: Part II\u200e (1974)","cover_url":"https://img3.doubanio.com/view/photo/s_ratio_poster/public/p2194138787.jpg","url":"https://movie.douban.com/subject/1299131/"}
        ]};
        </script>
        """

        suggestions = parse_subject_search_html(html, expected_title=title)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, title)
        self.assertEqual(suggestions[0].douban_id, "1291841")
        self.assertEqual(suggestions[0].cover, "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg")
        self.assertEqual(suggestions[0].year, 1972)

    def test_enrich_missing_posters_from_subject_suggest_replaces_designed_cover_safely(self):
        title = "\u6559\u7236"
        payload = """
        [
          {"img":"https:\\/\\/img9.doubanio.com\\/view\\/photo\\/s_ratio_poster\\/public\\/p616779645.jpg","title":"\u6559\u7236","url":"https:\\/\\/movie.douban.com\\/subject\\/1291841\\/","type":"movie","year":"1972","id":"1291841"}
        ]
        """.encode("utf-8")
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append(url)
            return payload

        items = [
            MediaItem(
                title=title,
                media_type="\u7535\u5f71",
                douban_id="premium-movie-001",
                cover="data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C/svg%3E",
            )
        ]

        enriched = enrich_missing_posters_from_subject_suggest(items, fetcher=fake_fetcher, sleep_seconds=0)

        self.assertEqual(enriched, 1)
        self.assertEqual(items[0].douban_id, "1291841")
        self.assertEqual(items[0].cover, "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg")
        self.assertEqual(items[0].url, "https://movie.douban.com/subject/1291841/")
        self.assertEqual(items[0].year, 1972)
        self.assertEqual(len(calls), 1)

    def test_themoviedb_search_parser_keeps_exact_title_and_extracts_poster(self):
        html = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/238-the-godfather">
            <img alt="\u6559\u7236" srcset="https://media.themoviedb.org/t/p/w94_and_h141_face/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg 1x, https://media.themoviedb.org/t/p/w188_and_h282_face/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg 2x" src="https://media.themoviedb.org/t/p/w94_and_h141_face/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg" />
          </a>
          <h2><span>\u6559\u7236</span><span class="font-light"> (The Godfather)</span></h2>
        </div>
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/240-the-godfather-part-ii">
            <img alt="\u6559\u72362" src="https://media.themoviedb.org/t/p/w94_and_h141_face/other.jpg" />
          </a>
          <h2><span>\u6559\u72362</span><span> (The Godfather Part II)</span></h2>
        </div>
        """

        suggestions = parse_themoviedb_search_html(html, expected_title="\u6559\u7236", expected_media_type="\u7535\u5f71")

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u6559\u7236")
        self.assertEqual(suggestions[0].media_type, "\u7535\u5f71")
        self.assertEqual(suggestions[0].douban_id, "tmdb-movie-238")
        self.assertEqual(suggestions[0].cover, "https://media.themoviedb.org/t/p/w500/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg")

    def test_web_poster_enrichment_falls_back_to_themoviedb_when_douban_is_empty(self):
        title = "\u793e\u4ea4\u7f51\u7edc\u6d4b\u8bd5"
        tmdb_html = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/37799-the-social-network">
            <img alt="\u793e\u4ea4\u7f51\u7edc\u6d4b\u8bd5" src="https://media.themoviedb.org/t/p/w94_and_h141_face/n0ybibhJtQ5icDqTp8eRytcIHJx.jpg" />
          </a>
          <h2><span>\u793e\u4ea4\u7f51\u7edc\u6d4b\u8bd5</span><span> (The Social Network)</span></h2>
        </div>
        """.encode("utf-8")
        calls = []

        def fake_fetcher(url, accept_json=False):
            calls.append(url)
            if "themoviedb.org" in url:
                return tmdb_html
            return b"[]"

        items = [
            MediaItem(
                title=title,
                media_type="\u7535\u5f71",
                douban_id="premium-\u7535\u5f71-055",
                cover="data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C/svg%3E",
            )
        ]

        enriched = enrich_missing_posters_from_web_sources(items, fetcher=fake_fetcher, sleep_seconds=0)

        self.assertEqual(enriched, 1)
        self.assertEqual(items[0].douban_id, "tmdb-movie-37799")
        self.assertEqual(items[0].cover, "https://media.themoviedb.org/t/p/w500/n0ybibhJtQ5icDqTp8eRytcIHJx.jpg")
        self.assertTrue(any("themoviedb.org/search" in url for url in calls))

    def test_themoviedb_fetch_uses_known_alias_but_preserves_original_title(self):
        alias_html = """
        <div class="comp:media-card">
          <a data-media-type="tv" href="/tv/124834-heartstopper">
            <img alt="Heartstopper" src="https://media.themoviedb.org/t/p/w94_and_h141_face/heart.jpg" />
          </a>
          <h2><span>Heartstopper</span></h2>
        </div>
        """.encode("utf-8")
        calls = []

        def fake_fetcher(url, accept_json=False):
            calls.append(url)
            if "Heartstopper" in url:
                return alias_html
            return b"<html></html>"

        from douban_recommender.douban_sources import fetch_themoviedb_suggestions

        suggestions = fetch_themoviedb_suggestions("\u5fc3\u8df3\u6f0f\u4e00\u62cd", media_type="\u7535\u89c6\u5267", fetcher=fake_fetcher)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u5fc3\u8df3\u6f0f\u4e00\u62cd")
        self.assertEqual(suggestions[0].media_type, "\u7535\u89c6\u5267")
        self.assertEqual(suggestions[0].douban_id, "tmdb-tv-124834")
        self.assertTrue(any("Heartstopper" in url for url in calls))

    def test_themoviedb_parser_does_not_use_movie_card_for_series_request(self):
        html = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/464727-dark">
            <img alt="Dark" src="https://media.themoviedb.org/t/p/w94_and_h141_face/movie.jpg" />
          </a>
          <h2><span>Dark</span></h2>
        </div>
        <div class="comp:media-card">
          <a data-media-type="tv" href="/tv/70523-dark">
            <img alt="Dark" src="https://media.themoviedb.org/t/p/w94_and_h141_face/tv.jpg" />
          </a>
          <h2><span>Dark</span></h2>
        </div>
        """

        suggestions = parse_themoviedb_search_html(html, expected_title="Dark", expected_media_type="\u7535\u89c6\u5267")

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].douban_id, "tmdb-tv-70523")
        self.assertEqual(suggestions[0].cover, "https://media.themoviedb.org/t/p/w500/tv.jpg")

    def test_web_poster_enrichment_replaces_douban_cdn_cover_with_external_source(self):
        title = "外部补图测试片"
        tmdb_html = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/238-poster-test">
            <img alt="外部补图测试片" src="https://media.themoviedb.org/t/p/w94_and_h141_face/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg" />
          </a>
          <h2><span>外部补图测试片</span></h2>
        </div>
        """.encode("utf-8")
        calls = []

        def fake_fetcher(url, accept_json=False):
            calls.append(url)
            if "themoviedb.org" in url:
                return tmdb_html
            return b"[]"

        items = [
            MediaItem(
                title=title,
                media_type="\u7535\u5f71",
                douban_id="1291841",
                cover="https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
            )
        ]

        enriched = enrich_missing_posters_from_web_sources(items, fetcher=fake_fetcher, sleep_seconds=0)

        self.assertEqual(enriched, 1)
        self.assertEqual(items[0].douban_id, "1291841")
        self.assertEqual(items[0].cover, "https://media.themoviedb.org/t/p/w500/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg")
        self.assertTrue(any("themoviedb.org/search" in url for url in calls))

    def test_tmdb_api_parser_extracts_exact_localized_poster(self):
        payload = {
            "results": [
                {
                    "id": 238,
                    "media_type": "movie",
                    "title": "\u6559\u7236",
                    "original_title": "The Godfather",
                    "release_date": "1972-03-14",
                    "poster_path": "/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg",
                },
                {
                    "id": 240,
                    "media_type": "movie",
                    "title": "\u6559\u72362",
                    "poster_path": "/wrong.jpg",
                },
            ]
        }

        suggestions = parse_tmdb_api_results(payload, expected_title="\u6559\u7236", expected_media_type="\u7535\u5f71")

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u6559\u7236")
        self.assertEqual(suggestions[0].douban_id, "tmdb-movie-238")
        self.assertEqual(suggestions[0].cover, "https://image.tmdb.org/t/p/w500/y03tzUKvkRCYwJ5NWys4W4bnS9m.jpg")
        self.assertEqual(suggestions[0].year, 1972)

    def test_tmdb_api_fetch_uses_key_and_alias_before_html_fallback(self):
        payload = {
            "results": [
                {
                    "id": 124834,
                    "media_type": "tv",
                    "name": "Heartstopper",
                    "first_air_date": "2022-04-22",
                    "poster_path": "/7eoUOODzupvoGHaB10HprIByGY1.jpg",
                }
            ]
        }
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append((url, accept_json))
            return json.dumps(payload).encode("utf-8")

        suggestions = fetch_tmdb_api_suggestions(
            "\u5fc3\u8df3\u6f0f\u4e00\u62cd",
            media_type="\u7535\u89c6\u5267",
            api_key="tmdb-key",
            fetcher=fake_fetcher,
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u5fc3\u8df3\u6f0f\u4e00\u62cd")
        self.assertEqual(suggestions[0].douban_id, "tmdb-tv-124834")
        self.assertTrue(any("api_key=tmdb-key" in url for url, _ in calls))
        self.assertTrue(any("Heartstopper" in url for url, _ in calls))

    def test_omdb_fetch_extracts_imdb_poster_for_alias(self):
        payload = {
            "Response": "True",
            "Title": "Heartstopper",
            "Year": "2022\u2013",
            "Type": "series",
            "imdbID": "tt10638036",
            "Poster": "https://m.media-amazon.com/images/M/heartstopper.jpg",
        }
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append(url)
            return json.dumps(payload).encode("utf-8")

        suggestions = fetch_omdb_suggestions(
            "\u5fc3\u8df3\u6f0f\u4e00\u62cd",
            media_type="\u7535\u89c6\u5267",
            api_key="omdb-key",
            fetcher=fake_fetcher,
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u5fc3\u8df3\u6f0f\u4e00\u62cd")
        self.assertEqual(suggestions[0].douban_id, "imdb-tt10638036")
        self.assertEqual(suggestions[0].cover, "https://m.media-amazon.com/images/M/heartstopper.jpg")
        self.assertTrue(any("apikey=omdb-key" in url for url in calls))

    def test_tvmaze_parser_extracts_series_poster_without_key(self):
        payload = {
            "id": 44933,
            "name": "Severance",
            "premiered": "2022-02-18",
            "url": "https://www.tvmaze.com/shows/44933/severance",
            "officialSite": "https://tv.apple.com/show/severance/example",
            "image": {
                "medium": "https://static.tvmaze.com/uploads/images/medium_portrait/548/1371406.jpg",
                "original": "https://static.tvmaze.com/uploads/images/original_untouched/548/1371406.jpg",
            },
        }

        suggestions = parse_tvmaze_result(payload, expected_title="Severance", expected_media_type="电视剧")

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "Severance")
        self.assertEqual(suggestions[0].media_type, "电视剧")
        self.assertEqual(suggestions[0].year, 2022)
        self.assertEqual(suggestions[0].douban_id, "tvmaze-44933")
        self.assertEqual(suggestions[0].cover, "https://static.tvmaze.com/uploads/images/original_untouched/548/1371406.jpg")
        self.assertEqual(suggestions[0].source, "tvmaze_api")

    def test_tvmaze_fetch_uses_alias_for_series_and_preserves_original_title(self):
        payload = {
            "id": 28866,
            "name": "The End of the F***ing World",
            "premiered": "2017-10-24",
            "url": "https://www.tvmaze.com/shows/28866/the-end-of-the-fing-world",
            "image": {"original": "https://static.tvmaze.com/uploads/images/original_untouched/348/870850.jpg"},
        }
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append(url)
            return json.dumps(payload).encode("utf-8")

        suggestions = fetch_tvmaze_suggestions("去他妈的世界", media_type="电视剧", fetcher=fake_fetcher)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "去他妈的世界")
        self.assertEqual(suggestions[0].douban_id, "tvmaze-28866")
        self.assertTrue(any("The+End" in url or "The%20End" in url for url in calls))

    def test_tvmaze_fetch_closes_open_stage_http_error_before_reraising(self):
        body = io.BytesIO(b'{"message":"Not Found"}')
        error = urllib.error.HTTPError(
            url="https://api.tvmaze.com/singlesearch/shows?q=Missing",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=body,
        )

        class FailingOpener:
            def open(self, request, timeout=0):
                raise error

        with mock.patch("douban_recommender.douban_sources.build_url_opener", return_value=FailingOpener()):
            with self.assertRaises(urllib.error.HTTPError) as raised:
                fetch_tvmaze_suggestions("Missing", media_type="电视剧")

        self.assertIs(raised.exception, error)
        self.assertTrue(body.closed)

    def test_source_config_controls_api_source_order(self):
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append(url)
            if "api.themoviedb.org" in url:
                return json.dumps({
                    "results": [{
                        "id": 238,
                        "media_type": "movie",
                        "title": "API\u6d4b\u8bd5\u7247",
                        "poster_path": "/api.jpg",
                    }]
                }).encode("utf-8")
            return b""

        items = [
            MediaItem(
                title="API\u6d4b\u8bd5\u7247",
                media_type="\u7535\u5f71",
                cover="https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
            )
        ]

        enriched = enrich_missing_posters_from_web_sources(
            items,
            fetcher=fake_fetcher,
            sleep_seconds=0,
            source_config=PosterSourceConfig(tmdb_api_key="tmdb-key", enable_tmdb_html=False, enable_douban=False),
        )

        self.assertEqual(enriched, 1)
        self.assertEqual(items[0].cover, "https://image.tmdb.org/t/p/w500/api.jpg")
        self.assertTrue(any("api.themoviedb.org" in url for url in calls))

    def test_wikipedia_image_source_can_fill_when_enabled(self):
        payload = {
            "query": {
                "pages": {
                    "123": {
                        "title": "Wiki Poster",
                        "thumbnail": {"source": "https://upload.wikimedia.org/example/poster.jpg"},
                    }
                }
            }
        }
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append(url)
            return json.dumps(payload).encode("utf-8")

        suggestions = fetch_wikipedia_image_suggestions("Wiki Poster", media_type="\u7535\u5f71", fetcher=fake_fetcher)

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].cover, "https://upload.wikimedia.org/example/poster.jpg")
        self.assertEqual(suggestions[0].source, "wikipedia_pageimage")
        self.assertTrue(any("wikipedia.org/w/api.php" in url for url in calls))

    def test_anilist_parser_extracts_exact_anime_series_cover(self):
        payload = {
            "data": {
                "Page": {
                    "media": [
                        {
                            "id": 127230,
                            "title": {
                                "romaji": "Chainsaw Man",
                                "english": "Chainsaw Man",
                                "native": "\u30c1\u30a7\u30f3\u30bd\u30fc\u30de\u30f3",
                            },
                            "format": "TV",
                            "seasonYear": 2022,
                            "coverImage": {
                                "large": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/chainsaw.png",
                                "extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/chainsaw-xl.png",
                            },
                            "siteUrl": "https://anilist.co/anime/127230",
                        },
                        {
                            "id": 171627,
                            "title": {"english": "Chainsaw Man \u2013 The Movie: Reze Arc"},
                            "format": "MOVIE",
                            "coverImage": {"extraLarge": "https://wrong.example/movie.png"},
                        },
                    ]
                }
            }
        }

        suggestions = parse_anilist_results(payload, expected_title="Chainsaw Man", expected_media_type="\u52a8\u6f2b")

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "Chainsaw Man")
        self.assertEqual(suggestions[0].media_type, "\u52a8\u6f2b")
        self.assertEqual(suggestions[0].year, 2022)
        self.assertEqual(suggestions[0].douban_id, "anilist-127230")
        self.assertEqual(suggestions[0].cover, "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/chainsaw-xl.png")

    def test_free_anime_sources_use_aliases_before_douban_fallback(self):
        calls = []

        def fake_fetcher(url, accept_json=True, data=None, headers=None):
            calls.append((url, data))
            if "graphql.anilist.co" in url:
                return json.dumps({
                    "data": {
                        "Page": {
                            "media": [{
                                "id": 99426,
                                "title": {
                                    "english": "A Place Further Than the Universe",
                                    "romaji": "Sora yori mo Tooi Basho",
                                    "native": "\u5b87\u5b99\u3088\u308a\u3082\u9060\u3044\u5834\u6240",
                                },
                                "format": "TV",
                                "seasonYear": 2018,
                                "coverImage": {"extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/universe.png"},
                                "siteUrl": "https://anilist.co/anime/99426",
                            }]
                        }
                    }
                }).encode("utf-8")
            return b"{}"

        suggestions = fetch_anilist_suggestions(
            "\u6bd4\u5b87\u5b99\u66f4\u8fdc\u7684\u5730\u65b9",
            media_type="\u52a8\u6f2b",
            fetcher=fake_fetcher,
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u6bd4\u5b87\u5b99\u66f4\u8fdc\u7684\u5730\u65b9")
        self.assertEqual(suggestions[0].source, "anilist_api")
        self.assertTrue(any("A+Place+Further" in url or "A%20Place%20Further" in url for url, _ in calls))

    def test_jikan_fetch_extracts_myanimelist_large_cover_for_alias(self):
        payload = {
            "data": [
                {
                    "mal_id": 5114,
                    "title": "Fullmetal Alchemist: Brotherhood",
                    "title_english": "Fullmetal Alchemist: Brotherhood",
                    "type": "TV",
                    "year": 2009,
                    "url": "https://myanimelist.net/anime/5114/Fullmetal_Alchemist__Brotherhood",
                    "images": {"jpg": {"large_image_url": "https://cdn.myanimelist.net/images/anime/1208/94745l.jpg"}},
                }
            ]
        }
        calls = []

        def fake_fetcher(url, accept_json=True):
            calls.append(url)
            return json.dumps(payload).encode("utf-8")

        suggestions = fetch_jikan_suggestions(
            "\u94a2\u4e4b\u70bc\u91d1\u672f\u5e08 FULLMETAL ALCHEMIST",
            media_type="\u52a8\u6f2b",
            fetcher=fake_fetcher,
        )

        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0].title, "\u94a2\u4e4b\u70bc\u91d1\u672f\u5e08 FULLMETAL ALCHEMIST")
        self.assertEqual(suggestions[0].douban_id, "mal-5114")
        self.assertEqual(suggestions[0].source, "jikan_myanimelist")
        self.assertTrue(any("api.jikan.moe/v4/anime" in url for url in calls))

    def test_web_source_uses_anilist_for_anime_without_api_key(self):
        calls = []

        def fake_fetcher(url, accept_json=True, data=None, headers=None):
            calls.append(url)
            if "graphql.anilist.co" in url:
                return json.dumps({
                    "data": {
                        "Page": {
                            "media": [{
                                "id": 127230,
                                "title": {"english": "Chainsaw Man", "romaji": "Chainsaw Man"},
                                "format": "TV",
                                "seasonYear": 2022,
                                "coverImage": {"extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/chainsaw.png"},
                                "siteUrl": "https://anilist.co/anime/127230",
                            }]
                        }
                    }
                }).encode("utf-8")
            return b"{}"

        items = [
            MediaItem(
                title="\u94fe\u952f\u4eba",
                media_type="\u52a8\u6f2b",
                cover="data:image/svg+xml;charset=utf-8,%3Csvg%3E%3C/svg%3E",
                douban_id="premium-anime-001",
            )
        ]

        enriched = enrich_missing_posters_from_web_sources(
            items,
            fetcher=fake_fetcher,
            sleep_seconds=0,
            source_config=PosterSourceConfig(enable_tmdb_html=False, enable_douban=False),
        )

        self.assertEqual(enriched, 1)
        self.assertEqual(items[0].cover, "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/chainsaw.png")
        self.assertEqual(items[0].douban_id, "anilist-127230")
        self.assertTrue(any("graphql.anilist.co" in url for url in calls))


    def test_static_poster_map_covers_current_missed_titles(self):
        from douban_recommender.douban_sources import STATIC_POSTER_URLS_BY_TITLE

        for title in [
            "\u602a\u5316\u732b",
            "\u4f0d\u516d\u4e03",
            "\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba",
            "\u96fe\u5c71\u4e94\u884c",
            "\u4e2d\u56fd\u5947\u8c2d",
            "\u547d\u8fd0\u77f3\u4e4b\u95e8",
            "\u5c11\u5973\u7ec8\u672b\u65c5\u884c",
            "\u6211\u4eec\u7684\u7236\u8f88",
            "\u5179\u5c71\u9c7c\u8c31",
            "\u9a7e\u9a76\u6211\u7684\u8f66",
            "\u8bb0\u5fc6\u788e\u7247",
        ]:
            with self.subTest(title=title):
                self.assertIn(title, STATIC_POSTER_URLS_BY_TITLE)
                self.assertTrue(STATIC_POSTER_URLS_BY_TITLE[title].startswith("https://"))

    def test_poster_aliases_keep_chinese_titles_for_external_search(self):
        from douban_recommender.douban_sources import POSTER_SEARCH_ALIASES

        expected_aliases = {
            "\u8bb0\u5fc6\u788e\u7247": "Memento",
            "\u9a7e\u9a76\u6211\u7684\u8f66": "Drive My Car",
            "\u5179\u5c71\u9c7c\u8c31": "The Book of Fish",
            "\u6211\u4eec\u7684\u7236\u8f88": "Generation War",
            "\u7231\uff0c\u6b7b\u4ea1\u548c\u673a\u5668\u4eba": "Love Death and Robots",
            "\u96fe\u5c71\u4e94\u884c": "Fog Hill of Five Elements",
            "\u4e2d\u56fd\u5947\u8c2d": "Yao Chinese Folktales",
            "\u547d\u8fd0\u77f3\u4e4b\u95e8": "Steins Gate",
            "\u5c11\u5973\u7ec8\u672b\u65c5\u884c": "Girls Last Tour",
        }
        for title, alias in expected_aliases.items():
            with self.subTest(title=title):
                self.assertIn(alias, POSTER_SEARCH_ALIASES.get(title, []))



if __name__ == "__main__":
    unittest.main()
