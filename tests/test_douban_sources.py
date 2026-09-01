import io
import json
import os
import threading
import unittest
import urllib.error
import urllib.parse
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from unittest import mock

from douban_recommender.candidate_planner import CandidateQuery
from douban_recommender.douban_sources import (
    enrich_public_metadata,
    enrich_media_items,
    enrich_missing_posters_from_web_sources,
    enrich_missing_posters_from_subject_suggest,
    fetch_anilist_suggestions,
    fetch_candidates_from_plan,
    fetch_douban_detail_html,
    fetch_douban_rexxar_detail,
    fetch_douban_rexxar_search_detail,
    fetch_explore,
    fetch_jikan_suggestions,
    fetch_omdb_suggestions,
    fetch_tmdb_api_suggestions,
    fetch_themoviedb_metadata_suggestions,
    fetch_tvmaze_suggestions,
    fetch_wikipedia_image_suggestions,
    build_url_opener,
    build_retry_url_opener,
    configured_proxy_url,
    merge_subject_detail,
    parse_anilist_results,
    parse_jikan_results,
    parse_douban_rexxar_celebrities,
    parse_douban_rexxar_photos,
    parse_douban_rexxar_search,
    parse_douban_rexxar_subject,
    parse_subject_detail_html,
    parse_subject_search_html,
    parse_subject_suggestions,
    parse_themoviedb_search_html,
    parse_themoviedb_detail_html,
    parse_tmdb_api_results,
    parse_tvmaze_result,
    PosterSourceConfig,
    subject_detail_urls,
)
from douban_recommender.models import MediaItem
import douban_recommender.douban_sources as douban_sources_module


class SubjectDetailParseTests(unittest.TestCase):
    def test_static_poster_metadata_has_no_corrupted_question_mark_title_keys(self):
        for mapping in (
            douban_sources_module.POSTER_SEARCH_ALIASES,
            douban_sources_module.STATIC_POSTER_URLS_BY_TITLE,
            douban_sources_module.STATIC_POSTER_IDS_BY_TITLE,
        ):
            corrupted = [key for key in mapping if key and set(key) == {"?"}]
            self.assertEqual([], corrupted)

    def test_title_matcher_handles_spaced_titles_without_accepting_same_first_word(self):
        matcher = douban_sources_module._title_matches_expected

        self.assertTrue(matcher("毛骗 终结篇", "毛骗 终结篇"))
        self.assertTrue(matcher("教父 The Godfather‎ (1972)", "教父"))
        self.assertTrue(
            matcher(
                "Tomorrow’s Worlds: The Unearthly History Of Science Fiction",
                "Tomorrow's Worlds: The Unearthly History of Science Fiction",
            )
        )
        self.assertFalse(matcher("The Godfather", "The Crown"))

    def test_explicit_cinescope_socks_proxy_is_used_by_the_shared_url_opener(self):
        class FakeResponse:
            status_code = 200
            status = 200
            reason = "OK"
            headers = {"Content-Type": "application/json"}
            content = b'{"ok":true}'
            is_redirect = False

            def close(self):
                return None

        with mock.patch.dict(os.environ, {"CINESCOPE_OUTBOUND_PROXY": "socks5h://127.0.0.1:10808"}, clear=False):
            with mock.patch("requests.Session.request", return_value=FakeResponse()) as request:
                opener = build_url_opener()
                with opener.open(urllib.request.Request("https://example.test/data"), timeout=3) as response:
                    payload = response.read()

        self.assertEqual("socks5h://127.0.0.1:10808", configured_proxy_url({"CINESCOPE_OUTBOUND_PROXY": "socks5h://127.0.0.1:10808"}))
        self.assertEqual(b'{"ok":true}', payload)
        self.assertEqual(
            {"http": "socks5h://127.0.0.1:10808", "https": "socks5h://127.0.0.1:10808"},
            request.call_args.kwargs["proxies"],
        )

    def test_fallback_proxy_mode_keeps_metadata_direct_and_reserves_proxy_for_retry(self):
        class FakeResponse:
            status_code = 200
            status = 200
            reason = "OK"
            headers = {"Content-Type": "application/json"}
            content = b'{"ok":true}'
            is_redirect = False

            def close(self):
                return None

        direct = object()
        environment = {
            "CINESCOPE_OUTBOUND_PROXY": "socks5h://127.0.0.1:10808",
            "CINESCOPE_PROXY_MODE": "fallback",
        }
        with mock.patch.dict(os.environ, environment, clear=False):
            with mock.patch("urllib.request.build_opener", return_value=direct):
                self.assertIs(direct, build_url_opener())
            with mock.patch("requests.Session.request", return_value=FakeResponse()) as request:
                opener = build_retry_url_opener()
                with opener.open(urllib.request.Request("https://example.test/data"), timeout=3) as response:
                    self.assertEqual(b'{"ok":true}', response.read())

        self.assertEqual(
            {"http": "socks5h://127.0.0.1:10808", "https": "socks5h://127.0.0.1:10808"},
            request.call_args.kwargs["proxies"],
        )

    def test_rexxar_subject_photos_and_celebrities_build_complete_verified_detail(self):
        subject = {
            "id": "6985810",
            "title": "狩猎",
            "original_title": "Jagten",
            "aka": ["诬网(港)", "The Hunt"],
            "year": 2012,
            "is_tv": False,
            "genres": ["剧情"],
            "countries": ["丹麦", "瑞典"],
            "languages": ["丹麦语", "英语"],
            "directors": [{"name": "托马斯·温特伯格"}],
            "actors": [{"name": "麦斯·米科尔森"}, {"name": "托玛斯·博·拉森"}],
            "intro": "一场谎言让善良教师被整个小镇排斥。",
            "rating": {"value": 9.1, "count": 476374},
            "cover_url": "https://img3.doubanio.com/view/photo/m_ratio_poster/public/p1546987967.jpg",
            "durations": ["115分钟"],
            "pubdate": ["2012-05-20(戛纳电影节)"],
            "comment_count": 137324,
            "review_count": 2596,
            "url": "https://movie.douban.com/subject/6985810/",
        }
        photos = {
            "photos": [
                {"id": "1561796193", "image": {"large": {"url": "https://qnmob3.doubanio.com/view/photo/large/public/p1561796193.jpg?imageView2/2/q/80"}}},
                {"id": "1561796194", "image": {"normal": {"url": "https://img3.doubanio.com/view/photo/l/public/p1561796194.jpg"}}},
            ]
        }
        celebrities = {
            "directors": [{"name": "托马斯·温特伯格", "avatar": {"large": "https://img3.doubanio.com/view/celebrity/m/public/p50973.jpg"}}],
            "actors": [{"name": "麦斯·米科尔森", "avatar": {"normal": "https://img1.doubanio.com/view/celebrity/m/public/p57893.jpg"}}],
        }

        detail = parse_douban_rexxar_subject(subject)
        detail.raw["stills"] = parse_douban_rexxar_photos(photos)
        detail.raw["people_photos"] = parse_douban_rexxar_celebrities(celebrities)

        self.assertEqual("狩猎", detail.title)
        self.assertEqual(2012, detail.year)
        self.assertEqual(9.1, detail.douban_rating)
        self.assertEqual(476374, detail.vote_count)
        self.assertEqual(["剧情"], detail.genres)
        self.assertEqual(["托马斯·温特伯格"], detail.directors)
        self.assertEqual(["麦斯·米科尔森", "托玛斯·博·拉森"], detail.casts)
        self.assertEqual(115, detail.raw["duration"])
        self.assertEqual("2012-05-20", detail.raw["release_date"])
        self.assertEqual(2, len(detail.raw["stills"]))
        self.assertEqual(
            "https://img1.doubanio.com/view/photo/l/public/p1561796193.jpg",
            detail.raw["stills"][0],
        )
        self.assertEqual(
            "https://img1.doubanio.com/view/celebrity/m/public/p50973.jpg",
            detail.raw["people_photos"]["托马斯·温特伯格"],
        )
        self.assertEqual(137324, detail.raw["comment_count"])
        self.assertEqual(2596, detail.raw["review_count"])
        self.assertIn("Jagten", detail.raw["aliases"])

    def test_rexxar_celebrities_ignores_douban_default_portraits(self):
        payload = {
            "directors": [{
                "name": "\u5bfc\u6f14\u7532",
                "avatar": {"large": "https://img1.doubanio.com/f/vendors/pics/personage-default-medium.png"},
            }],
            "actors": [{
                "name": "\u6f14\u5458\u4e59",
                "avatar": {"large": "https://img1.doubanio.com/view/celebrity/m/public/actor.jpg"},
            }],
        }

        photos = parse_douban_rexxar_celebrities(payload)

        self.assertNotIn("\u5bfc\u6f14\u7532", photos)
        self.assertEqual("https://img1.doubanio.com/view/celebrity/m/public/actor.jpg", photos["\u6f14\u5458\u4e59"])

    def test_rexxar_people_photos_map_latin_and_mixed_credit_aliases(self):
        payloads = {
            "https://m.douban.com/rexxar/api/v2/subject/37435796": {
                "id": "37435796",
                "title": "\u68c0\u5bdf\u5b98\u5ba4\u7684\u63d0\u6848",
                "year": 2026,
                "is_tv": True,
                "subtype": "tv",
                "genres": ["\u5267\u60c5"],
                "directors": [{"name": "\u6768\u5e86\u7199"}],
                "actors": [{"name": "\uc11c\ud55c\uacb0 Han Gyeol Seo"}],
            },
            "https://m.douban.com/rexxar/api/v2/tv/37435796/photos?type=S&start=0&count=8&sortby=like": {"photos": []},
            "https://m.douban.com/rexxar/api/v2/tv/37435796/celebrities": {
                "directors": [],
                "actors": [{
                    "name": "\u5f90\u6db5\u6d01",
                    "latin_name": "Han Gyeol Seo",
                    "avatar": {"large": "https://img1.doubanio.com/view/celebrity/m/public/han.jpg"},
                }],
            },
        }

        detail = fetch_douban_rexxar_detail(
            MediaItem(
                title="\u68c0\u5bdf\u5b98\u5ba4\u7684\u63d0\u6848",
                douban_id="37435796",
                year=2026,
                media_type="\u7535\u89c6\u5267",
            ),
            fetcher=lambda url, **_kwargs: payloads[url],
        )

        self.assertIsNotNone(detail)
        self.assertEqual(
            "https://img1.doubanio.com/view/celebrity/m/public/han.jpg",
            detail.raw["people_photos"]["Han Gyeol Seo"],
        )
        self.assertEqual(
            "https://img1.doubanio.com/view/celebrity/m/public/han.jpg",
            detail.raw["people_photos"]["\uc11c\ud55c\uacb0 Han Gyeol Seo"],
        )

    def test_rexxar_detail_uses_celebrity_credit_names_when_subject_cast_is_empty(self):
        payloads = {
            "https://m.douban.com/rexxar/api/v2/subject/35674355": {
                "id": "35674355",
                "title": "\u4e2d\u56fd\u5947\u8c2d",
                "year": 2023,
                "is_tv": True,
                "subtype": "tv",
                "genres": ["\u52a8\u753b"],
                "directors": [{"name": "\u9648\u5ed6\u5b87"}],
                "actors": [],
            },
            "https://m.douban.com/rexxar/api/v2/tv/35674355/photos?type=S&start=0&count=8&sortby=like": {"photos": []},
            "https://m.douban.com/rexxar/api/v2/tv/35674355/celebrities": {
                "directors": [{"name": "\u9648\u5ed6\u5b87", "avatar": {}}],
                "actors": [
                    {"name": "\u90a2\u97f5\u5609", "avatar": {"large": "https://img1.doubanio.com/xing.jpg"}},
                    {"name": "\u6797\u5f3a", "avatar": {"large": "https://img1.doubanio.com/lin.jpg"}},
                ],
            },
        }

        detail = fetch_douban_rexxar_detail(
            MediaItem(title="\u4e2d\u56fd\u5947\u8c2d", douban_id="35674355", year=2023, media_type="\u52a8\u6f2b"),
            fetcher=lambda url, **_kwargs: payloads[url],
        )

        self.assertIsNotNone(detail)
        self.assertEqual(["\u90a2\u97f5\u5609", "\u6797\u5f3a"], detail.casts)

    def test_rexxar_fetch_uses_numeric_douban_identity_and_merges_all_three_endpoints(self):
        payloads = {
            "https://m.douban.com/rexxar/api/v2/subject/6985810": {
                "id": "6985810", "title": "狩猎", "year": 2012, "genres": ["剧情"],
                "intro": "经过豆瓣公开接口核验的简介。", "rating": {"value": 9.1, "count": 10},
                "cover_url": "https://img3.doubanio.com/view/photo/m_ratio_poster/public/p1546987967.jpg",
            },
            "https://m.douban.com/rexxar/api/v2/movie/6985810/photos?type=S&start=0&count=8&sortby=like": {
                "photos": [{"image": {"large": {"url": "https://img3.doubanio.com/view/photo/l/public/p1.jpg"}}}],
            },
            "https://m.douban.com/rexxar/api/v2/movie/6985810/celebrities": {
                "directors": [{"name": "导演甲", "avatar": {"large": "https://img3.doubanio.com/view/celebrity/m/public/p2.jpg"}}],
                "actors": [],
            },
        }
        calls = []

        def fetcher(url, **_kwargs):
            calls.append(url)
            return json.dumps(payloads[url], ensure_ascii=False).encode("utf-8")

        detail = fetch_douban_rexxar_detail(MediaItem(title="狩猎", douban_id="6985810", year=2012), fetcher=fetcher)

        self.assertIsNotNone(detail)
        self.assertEqual(set(payloads), set(calls))
        self.assertEqual("经过豆瓣公开接口核验的简介。", detail.summary)
        self.assertEqual(["https://img1.doubanio.com/view/photo/l/public/p1.jpg"], detail.raw["stills"])
        self.assertEqual("https://img1.doubanio.com/view/celebrity/m/public/p2.jpg", detail.raw["people_photos"]["导演甲"])

    def test_rexxar_fetch_uses_tv_routes_for_series_photos_and_people(self):
        payloads = {
            "https://m.douban.com/rexxar/api/v2/subject/1419297": {
                "id": "1419297", "title": "越狱 第一季", "year": 2005,
                "is_tv": True, "subtype": "tv",
                "genres": ["剧情", "动作"], "intro": "第一季剧情简介。",
                "rating": {"value": 9.4, "count": 100},
                "directors": [{"name": "Brett Ratner"}],
                "actors": [{"name": "温特沃斯·米勒"}],
                "cover_url": "https://img3.doubanio.com/prison-break.jpg",
            },
            "https://m.douban.com/rexxar/api/v2/tv/1419297/photos?type=S&start=0&count=8&sortby=like": {
                "photos": [{"image": {"large": {"url": "https://img3.doubanio.com/prison-break-still.jpg"}}}],
            },
            "https://m.douban.com/rexxar/api/v2/tv/1419297/celebrities": {
                "directors": [{
                    "name": "Brett Ratner",
                    "avatar": {"large": "https://img3.doubanio.com/brett-ratner.jpg"},
                }],
                "actors": [{
                    "name": "温特沃斯·米勒",
                    "avatar": {"large": "https://img3.doubanio.com/wentworth-miller.jpg"},
                }],
            },
        }
        calls = []

        def fetcher(url, **_kwargs):
            calls.append(url)
            return json.dumps(payloads[url], ensure_ascii=False).encode("utf-8")

        detail = fetch_douban_rexxar_detail(
            MediaItem(title="越狱 第一季", media_type="电视剧", douban_id="1419297", year=2005),
            fetcher=fetcher,
        )

        self.assertIsNotNone(detail)
        self.assertEqual(set(payloads), set(calls))
        self.assertEqual(1, len(detail.raw["stills"]))
        self.assertEqual("https://img3.doubanio.com/brett-ratner.jpg", detail.raw["people_photos"]["Brett Ratner"])
        self.assertEqual("https://img3.doubanio.com/wentworth-miller.jpg", detail.raw["people_photos"]["温特沃斯·米勒"])

    def test_rexxar_fetch_uses_verified_subject_type_when_seed_media_type_is_wrong(self):
        payloads = {
            "https://m.douban.com/rexxar/api/v2/subject/34973705": {
                "id": "34973705", "title": "小行星猎人", "year": 2020,
                "is_tv": False, "subtype": "movie", "genres": ["纪录片"],
                "intro": "追踪小行星防御任务。", "rating": {"value": 7.4, "count": 100},
            },
            "https://m.douban.com/rexxar/api/v2/movie/34973705/photos?type=S&start=0&count=8&sortby=like": {
                "photos": [{"image": {"large": {"url": "https://img3.doubanio.com/asteroid-still.jpg"}}}],
            },
            "https://m.douban.com/rexxar/api/v2/movie/34973705/celebrities": {
                "directors": [], "actors": [],
            },
        }
        calls = []

        def fetcher(url, **_kwargs):
            calls.append(url)
            return json.dumps(payloads[url], ensure_ascii=False).encode("utf-8")

        detail = fetch_douban_rexxar_detail(
            MediaItem(title="小行星猎人", media_type="电视剧", douban_id="34973705", year=2020),
            fetcher=fetcher,
        )

        self.assertIsNotNone(detail)
        self.assertEqual("电影", detail.media_type)
        self.assertEqual(set(payloads), set(calls))
        self.assertEqual(["https://img3.doubanio.com/asteroid-still.jpg"], detail.raw["stills"])

    def test_rexxar_fetch_rejects_same_year_title_mismatch_before_merging_visuals(self):
        payloads = {
            "https://m.douban.com/rexxar/api/v2/subject/34943015": {
                "id": "34943015",
                "title": "宝可梦：皮卡丘和可可的冒险",
                "year": 2020,
                "genres": ["动画", "冒险"],
                "intro": "不属于目标剧集的简介。",
                "rating": {"value": 6.6, "count": 10},
            },
            "https://m.douban.com/rexxar/api/v2/movie/34943015/photos?type=S&start=0&count=8&sortby=like": {
                "photos": [{"image": {"large": {"url": "https://img1.doubanio.com/view/photo/l/public/wrong.jpg"}}}],
            },
            "https://m.douban.com/rexxar/api/v2/movie/34943015/celebrities": {
                "directors": [],
                "actors": [],
            },
        }

        def fetcher(url, **_kwargs):
            return json.dumps(payloads[url], ensure_ascii=False).encode("utf-8")

        detail = fetch_douban_rexxar_detail(
            MediaItem(title="机智医生生活", douban_id="34943015", year=2020),
            fetcher=fetcher,
        )

        self.assertIsNone(detail)

    def test_rexxar_search_parser_keeps_numeric_movie_and_tv_subjects(self):
        payload = {
            "subjects": {
                "items": [
                    {
                        "layout": "subject",
                        "target": {
                            "id": "30174419",
                            "title": "\u51b0\u6d77\u6218\u8bb0",
                            "year": "2019",
                            "uri": "douban://douban.com/tv/30174419",
                            "cover_url": "https://qnmob3.doubanio.com/view/photo/large/public/p2558471577.jpg?imageView2/0/q/80",
                            "rating": {"value": 9.3, "count": 41341},
                        },
                    },
                    {
                        "layout": "subject",
                        "target": {
                            "id": "collection-id",
                            "title": "\u4e3b\u9898\u5408\u96c6",
                            "uri": "douban://douban.com/subject_collection/collection-id",
                        },
                    },
                ]
            }
        }

        rows = parse_douban_rexxar_search(payload)

        self.assertEqual(1, len(rows))
        self.assertEqual("30174419", rows[0].douban_id)
        self.assertEqual("\u51b0\u6d77\u6218\u8bb0", rows[0].title)
        self.assertEqual("\u7535\u89c6\u5267", rows[0].media_type)
        self.assertEqual(2019, rows[0].year)
        self.assertEqual(9.3, rows[0].douban_rating)
        self.assertIn("doubanio.com", rows[0].cover)

    def test_rexxar_search_resolves_alias_then_fetches_verified_stills_and_people(self):
        item = MediaItem(
            title="\u6d77\u76d7\u6218\u8bb0",
            media_type="\u52a8\u6f2b",
            douban_id="anilist-101348",
            raw={"aliases": ["Vinland Saga"]},
        )
        search_payload = {
            "subjects": {
                "items": [{
                    "layout": "subject",
                    "target": {
                        "id": "30174419",
                        "title": "\u51b0\u6d77\u6218\u8bb0",
                        "year": "2019",
                        "uri": "douban://douban.com/tv/30174419",
                        "cover_url": "https://img3.doubanio.com/view/photo/l/public/poster.jpg",
                        "rating": {"value": 9.3, "count": 41341},
                    },
                }]
            }
        }
        subject = {
            "id": "30174419",
            "title": "\u51b0\u6d77\u6218\u8bb0",
            "original_title": "\u30f4\u30a3\u30f3\u30e9\u30f3\u30c9\u30fb\u30b5\u30ac",
            "aka": ["\u6d77\u76d7\u6218\u8bb0", "VINLAND SAGA"],
            "year": 2019,
            "is_tv": True,
            "genres": ["\u5267\u60c5", "\u52a8\u753b"],
            "intro": "\u4e00\u540d\u5c11\u5e74\u5728\u5317\u6b27\u6218\u4e89\u4e2d\u5bfb\u627e\u771f\u6b63\u7684\u6218\u58eb\u4e4b\u8def\u3002",
            "rating": {"value": 9.3, "count": 41341},
            "directors": [{"name": "\u85ae\u7530\u4fee\u5e73"}],
            "actors": [{"name": "\u4e0a\u6751\u7950\u7fd4"}],
            "cover_url": "https://img3.doubanio.com/view/photo/l/public/poster.jpg",
        }
        photos = {
            "photos": [{"image": {"large": {"url": "https://img3.doubanio.com/view/photo/l/public/still.jpg"}}}]
        }
        celebrities = {
            "directors": [{"name": "\u85ae\u7530\u4fee\u5e73", "avatar": {"large": "https://img3.doubanio.com/director.jpg"}}],
            "actors": [{"name": "\u4e0a\u6751\u7950\u7fd4", "avatar": {"large": "https://img3.doubanio.com/actor.jpg"}}],
        }
        calls = []

        def fetcher(url, **_kwargs):
            calls.append(url)
            if "/search/subjects?" in url:
                return json.dumps(search_payload, ensure_ascii=False).encode("utf-8")
            if url.endswith("/subject/30174419"):
                return json.dumps(subject, ensure_ascii=False).encode("utf-8")
            if "/tv/30174419/photos?" in url:
                return json.dumps(photos, ensure_ascii=False).encode("utf-8")
            if url.endswith("/tv/30174419/celebrities"):
                return json.dumps(celebrities, ensure_ascii=False).encode("utf-8")
            raise AssertionError(url)

        detail = fetch_douban_rexxar_search_detail(item, fetcher=fetcher)

        self.assertIsNotNone(detail)
        self.assertEqual("30174419", detail.douban_id)
        self.assertEqual(9.3, detail.douban_rating)
        self.assertEqual(["https://img1.doubanio.com/view/photo/l/public/still.jpg"], detail.raw["stills"])
        self.assertEqual("https://img3.doubanio.com/director.jpg", detail.raw["people_photos"]["\u85ae\u7530\u4fee\u5e73"])
        self.assertTrue(any("q=%E6%B5%B7%E7%9B%97%E6%88%98%E8%AE%B0" in url for url in calls))

    def test_default_enrichment_repairs_external_identity_after_verified_rexxar_search(self):
        item = MediaItem(
            title="\u6d77\u76d7\u6218\u8bb0",
            media_type="\u52a8\u6f2b",
            douban_id="anilist-101348",
            raw={"provider_ids": {"anilist": "101348"}},
        )
        detail = MediaItem(
            title="\u51b0\u6d77\u6218\u8bb0",
            media_type="\u52a8\u6f2b",
            year=2019,
            douban_id="30174419",
            douban_rating=9.3,
            genres=["\u5267\u60c5", "\u52a8\u753b"],
            directors=["\u85ae\u7530\u4fee\u5e73"],
            casts=["\u4e0a\u6751\u7950\u7fd4"],
            summary="\u7ecf\u8fc7\u9a8c\u8bc1\u7684\u5267\u60c5\u7b80\u4ecb\u3002",
            url="https://movie.douban.com/subject/30174419/",
            cover="https://img3.doubanio.com/poster.jpg",
            raw={
                "aliases": ["\u6d77\u76d7\u6218\u8bb0", "VINLAND SAGA"],
                "stills": ["https://img3.doubanio.com/still.jpg"],
                "people_photos": {
                    "\u85ae\u7530\u4fee\u5e73": "https://img3.doubanio.com/director.jpg",
                    "\u4e0a\u6751\u7950\u7fd4": "https://img3.doubanio.com/actor.jpg",
                },
                "provider_ids": {"douban": "30174419"},
            },
        )

        with (
            mock.patch.object(douban_sources_module, "fetch_douban_rexxar_detail", return_value=None),
            mock.patch.object(douban_sources_module, "fetch_douban_rexxar_search_detail", return_value=detail),
        ):
            enrich_media_items([item], limit=1, sleep_seconds=0, force_people_photos=True)

        self.assertEqual("30174419", item.douban_id)
        self.assertEqual("https://movie.douban.com/subject/30174419/", item.url)
        self.assertEqual("101348", item.raw["provider_ids"]["anilist"])
        self.assertEqual("30174419", item.raw["provider_ids"]["douban"])
        self.assertEqual(9.3, item.douban_rating)

    def test_merge_subject_detail_refuses_mismatched_title_even_when_identity_url_is_present(self):
        item = MediaItem(title="目标剧集", douban_id="100", year=2020, media_type="电视剧", raw={})
        detail = MediaItem(
            title="另一部动画电影",
            douban_id="100",
            year=2020,
            media_type="电影",
            douban_rating=9.9,
            genres=["动画"],
            summary="错误简介。",
            raw={"stills": ["https://img1.doubanio.com/view/photo/l/public/wrong.jpg"]},
        )

        merge_subject_detail(item, detail)

        self.assertIsNone(item.douban_rating)
        self.assertEqual([], item.genres)
        self.assertEqual("", item.summary)
        self.assertNotIn("stills", item.raw)

    def test_verified_same_identity_douban_detail_replaces_stale_people_order(self):
        item = MediaItem(
            title="谍影重重",
            douban_id="1304102",
            year=2002,
            media_type="电影",
            directors=["捷克", "道格·里曼"],
            casts=["马特·达蒙", "弗朗卡·波滕特", "克里斯·库珀"],
            source="douban_user:collect",
            raw={
                "people_photos": {
                    "道格·里曼": "https://img1.doubanio.com/director.jpg",
                    "马特·达蒙": "https://img1.doubanio.com/matt.jpg",
                    "弗朗卡·波滕特": "https://img1.doubanio.com/franka.jpg",
                    "克里斯·库珀": "https://img1.doubanio.com/chris.jpg",
                }
            },
        )
        detail = MediaItem(
            title="谍影重重",
            douban_id="1304102",
            year=2002,
            media_type="电影",
            directors=["道格·里曼"],
            casts=["马特·达蒙", "弗朗卡·波滕特", "克里斯·库珀"],
            source="douban_rexxar",
            raw={},
        )

        merge_subject_detail(item, detail)

        self.assertEqual(["道格·里曼"], item.directors)
        self.assertEqual(["马特·达蒙", "弗朗卡·波滕特", "克里斯·库珀"], item.casts)

    def test_external_supplement_does_not_replace_existing_people_order(self):
        item = MediaItem(
            title="示例剧集",
            douban_id="100",
            year=2020,
            media_type="电视剧",
            directors=["主导演"],
            casts=["主演甲"],
            source="title_seed",
            raw={},
        )
        detail = MediaItem(
            title="示例剧集",
            douban_id="tmdb-tv-100",
            year=2020,
            media_type="电视剧",
            directors=["分集导演"],
            casts=["主演乙"],
            source="themoviedb_detail",
            raw={},
        )

        merge_subject_detail(item, detail)

        self.assertEqual(["主导演", "分集导演"], item.directors)
        self.assertEqual(["主演甲", "主演乙"], item.casts)

    def test_verified_douban_repair_prefers_chinese_title_summary_and_marks_external_identity(self):
        item = MediaItem(
            title="NARUTO -\u30ca\u30eb\u30c8-",
            media_type="\u52a8\u6f2b",
            year=2002,
            douban_id="anilist-20",
            summary="Naruto is a young ninja searching for recognition in his village.",
            source="global:anilist",
            raw={"aliases": ["Naruto", "\u706b\u5f71\u5fcd\u8005"], "provider_ids": {"anilist": "20"}},
        )
        detail = MediaItem(
            title="\u706b\u5f71\u5fcd\u8005",
            media_type="\u52a8\u6f2b",
            year=2002,
            douban_id="1427318",
            douban_rating=9.2,
            genres=["\u52a8\u753b"],
            directors=["\u4f0a\u8fbe\u52c7\u767b"],
            casts=["\u7af9\u5185\u987a\u5b50"],
            summary="\u6728\u53f6\u6751\u5c11\u5e74\u6f29\u6da1\u9e23\u4eba\u4e3a\u6210\u4e3a\u706b\u5f71\u800c\u594b\u6597\u3002",
            source="douban_rexxar",
            raw={"aliases": ["Naruto", "NARUTO"], "provider_ids": {"douban": "1427318"}},
        )

        merge_subject_detail(item, detail)

        self.assertEqual("\u706b\u5f71\u5fcd\u8005", item.title)
        self.assertEqual("\u6728\u53f6\u6751\u5c11\u5e74\u6f29\u6da1\u9e23\u4eba\u4e3a\u6210\u4e3a\u706b\u5f71\u800c\u594b\u6597\u3002", item.summary)
        self.assertEqual("1427318", item.douban_id)
        self.assertEqual("anilist-20", item.raw["resolved_from_provider"])
        self.assertIn("NARUTO -\u30ca\u30eb\u30c8-", item.raw["aliases"])
        self.assertEqual("20", item.raw["provider_ids"]["anilist"])
        self.assertEqual("1427318", item.raw["provider_ids"]["douban"])

    def test_complete_global_item_still_refreshes_verified_chinese_douban_copy(self):
        item = MediaItem(
            title="NARUTO -\u30ca\u30eb\u30c8-",
            media_type="\u52a8\u6f2b",
            year=2002,
            douban_id="1427318",
            douban_rating=9.2,
            genres=["\u52a8\u753b"],
            directors=["\u4f0a\u8fbe\u52c7\u767b"],
            casts=["\u7af9\u5185\u987a\u5b50"],
            cover="https://s4.anilist.co/poster.jpg",
            summary="Naruto is a young ninja searching for recognition in his village.",
            source="global:anilist",
            raw={
                "aliases": ["Naruto", "\u706b\u5f71\u5fcd\u8005"],
                "stills": ["https://img1.doubanio.com/still.jpg"],
                "people_photos": {
                    "\u4f0a\u8fbe\u52c7\u767b": "https://img1.doubanio.com/director.jpg",
                    "\u7af9\u5185\u987a\u5b50": "https://img1.doubanio.com/actor.jpg",
                },
            },
        )
        detail = MediaItem(
            title="\u706b\u5f71\u5fcd\u8005",
            media_type="\u52a8\u6f2b",
            year=2002,
            douban_id="1427318",
            douban_rating=9.2,
            genres=["\u52a8\u753b"],
            directors=["\u4f0a\u8fbe\u52c7\u767b"],
            casts=["\u7af9\u5185\u987a\u5b50"],
            summary="\u6728\u53f6\u6751\u5c11\u5e74\u6f29\u6da1\u9e23\u4eba\u4e3a\u6210\u4e3a\u706b\u5f71\u800c\u594b\u6597\u3002",
            source="douban_rexxar",
            raw={"aliases": ["Naruto"], "stills": ["https://img1.doubanio.com/still.jpg"]},
        )

        with mock.patch.object(douban_sources_module, "fetch_douban_rexxar_detail", return_value=detail) as rexxar:
            enrich_media_items([item], limit=1, sleep_seconds=0, force_people_photos=True)

        rexxar.assert_called_once()
        self.assertEqual("\u706b\u5f71\u5fcd\u8005", item.title)
        self.assertEqual("\u6728\u53f6\u6751\u5c11\u5e74\u6f29\u6da1\u9e23\u4eba\u4e3a\u6210\u4e3a\u706b\u5f71\u800c\u594b\u6597\u3002", item.summary)

    def test_verified_douban_detail_replaces_premium_synthetic_year_rating_and_people(self):
        item = MediaItem(
            title="\u695a\u95e8\u7684\u4e16\u754c",
            media_type="\u7535\u5f71",
            year=2018,
            douban_id="1292064",
            douban_rating=8.5,
            genres=["\u5267\u60c5"],
            directors=["\u955c\u5934\u8bed\u8a00\u4e13\u5bb6"],
            casts=["\u620f\u5267\u5f20\u529b\u62c5\u5f53"],
            source="premium_expansion",
            summary="\u7531 CineScope \u7cbe\u9009\u6269\u5c55\u6c60\u8865\u5165\u7684\u7535\u5f71\u5019\u9009\u3002",
            raw={},
        )
        detail = MediaItem(
            title="\u695a\u95e8\u7684\u4e16\u754c",
            media_type="\u7535\u5f71",
            year=1998,
            douban_id="1292064",
            douban_rating=9.4,
            genres=["\u5267\u60c5", "\u79d1\u5e7b"],
            directors=["\u5f7c\u5f97\u00b7\u5a01\u5c14"],
            casts=["\u91d1\u00b7\u51ef\u745e"],
            summary="\u695a\u95e8\u9010\u6e10\u53d1\u73b0\u81ea\u5df1\u7684\u6574\u4e2a\u4eba\u751f\u90fd\u662f\u4e00\u573a\u771f\u4eba\u79c0\u3002",
            source="douban_rexxar",
            raw={},
        )

        merge_subject_detail(item, detail)

        self.assertEqual(1998, item.year)
        self.assertEqual(9.4, item.douban_rating)
        self.assertEqual(["\u5f7c\u5f97\u00b7\u5a01\u5c14"], item.directors)
        self.assertEqual(["\u91d1\u00b7\u51ef\u745e"], item.casts)
        self.assertEqual("1292064", item.raw["identity_repaired_from"])

    def test_default_media_enrichment_prefers_rexxar_before_blocked_subject_html(self):
        item = MediaItem(title="狩猎", douban_id="6985810", year=2012, media_type="电影")
        detail = MediaItem(
            title="狩猎",
            douban_id="6985810",
            year=2012,
            media_type="电影",
            douban_rating=9.1,
            vote_count=476374,
            genres=["剧情"],
            directors=["托马斯·温特伯格"],
            casts=["麦斯·米科尔森"],
            cover="https://img3.doubanio.com/view/photo/m_ratio_poster/public/p1546987967.jpg",
            summary="一场谎言让善良教师被整个小镇排斥。",
            raw={
                "stills": ["https://img3.doubanio.com/view/photo/l/public/p1.jpg"],
                "people_photos": {
                    "托马斯·温特伯格": "https://img3.doubanio.com/view/celebrity/m/public/p50973.jpg",
                    "麦斯·米科尔森": "https://img1.doubanio.com/view/celebrity/m/public/p57893.jpg",
                },
            },
        )

        with mock.patch.object(douban_sources_module, "fetch_douban_rexxar_detail", return_value=detail) as rexxar:
            with mock.patch.object(douban_sources_module, "http_get", side_effect=AssertionError("HTML fallback should not run")):
                enrich_media_items([item], limit=1, sleep_seconds=0, force_people_photos=True)

        rexxar.assert_called_once()
        self.assertEqual(9.1, item.douban_rating)
        self.assertEqual("一场谎言让善良教师被整个小镇排斥。", item.summary)
        self.assertEqual(["https://img3.doubanio.com/view/photo/l/public/p1.jpg"], item.raw["stills"])
        self.assertTrue(douban_sources_module.has_people_photo_coverage(item))

    def test_parse_themoviedb_detail_extracts_verified_chinese_synopsis_facts_and_backdrop(self):
        page = """
        <meta property="og:title" content="镖人：风起大漠">
        <meta property="og:description" content="大漠之上，多方势力围绕一场特殊押镖任务展开争夺。">
        <meta property="og:image" content="https://media.themoviedb.org/t/p/w500/poster.jpg">
        <meta property="og:image" content="https://media.themoviedb.org/t/p/w780/backdrop.jpg">
        <script type="application/ld+json">
        {"@type":"Movie","name":"镖人：风起大漠","description":"大漠之上，多方势力围绕一场特殊押镖任务展开争夺。","countryOfOrigin":[{"name":"中国"}],"duration":"PT2H6M","genre":["动作","冒险"],"releasedEvent":[{"startDate":"2026-02-17"}]}
        </script>
        <ol class="people no_image">
          <li class="profile"><p><a href="/person/18899">袁和平</a></p><p class="character">Director</p></li>
        </ol>
        <section class="panel top_billed scroller">
          <div id="cast_scroller"><ol class="people scroller">
            <li class="card">
              <a href="/person/20001"><img class="profile" src="https://media.themoviedb.org/t/p/w276_and_h350_face/actor.jpg" alt="演员甲"></a>
              <p><a href="/person/20001">演员甲</a></p><p class="character">刀马</p>
            </li>
          </ol></div>
        </section>
        """

        results = parse_themoviedb_detail_html(
            page,
            expected_title="镖人：风起大漠",
            expected_media_type="电影",
            source_url="https://www.themoviedb.org/movie/1305781",
        )

        self.assertEqual(1, len(results))
        item = results[0]
        self.assertEqual("大漠之上，多方势力围绕一场特殊押镖任务展开争夺。", item.summary)
        self.assertEqual(2026, item.year)
        self.assertEqual(["动作", "冒险"], item.genres)
        self.assertEqual(["中国"], item.countries)
        self.assertEqual(["袁和平"], item.directors)
        self.assertEqual(["演员甲"], item.casts)
        self.assertEqual(
            "https://media.themoviedb.org/t/p/w500/actor.jpg",
            item.raw["people_photos"]["演员甲"],
        )
        self.assertEqual(126, item.raw["duration"])
        self.assertIn("backdrop.jpg", item.raw["stills"][0])

    def test_themoviedb_detail_normalizes_public_rating_for_card_display(self):
        page = """
        <script type="application/ld+json">
        {
          "@type": "Movie",
          "name": "测试电影",
          "description": "可靠简介。",
          "releasedEvent": [{"startDate": "2024-01-01"}],
          "aggregateRating": {"ratingValue": "8.1", "ratingCount": "12345"}
        }
        </script>
        """

        items = parse_themoviedb_detail_html(
            page,
            expected_title="测试电影",
            expected_media_type="电影",
            source_url="https://www.themoviedb.org/movie/42-test",
            expected_year=2024,
        )

        self.assertEqual(1, len(items))
        self.assertEqual(8.1, items[0].raw["ratings"]["tmdb"])
        self.assertEqual(12345, items[0].raw["rating_votes"]["tmdb"])

    def test_tvmaze_result_normalizes_public_rating_for_card_display(self):
        payload = {
            "id": 42,
            "name": "测试剧集",
            "premiered": "2024-01-01",
            "image": {"original": "https://static.tvmaze.com/poster.jpg"},
            "rating": {"average": 8.7},
            "summary": "<p>可靠简介。</p>",
        }

        items = parse_tvmaze_result(payload, expected_title="测试剧集", expected_media_type="电视剧")

        self.assertEqual(1, len(items))
        self.assertEqual(8.7, items[0].raw["ratings"]["tvmaze"])

    def test_tvmaze_documentary_type_is_preserved_during_detail_hydration(self):
        payload = {
            "id": 83363,
            "name": "Science Fiction in the Atomic Age",
            "type": "Documentary",
            "premiered": "2025-04-03",
            "genres": ["History"],
            "image": {"original": "https://static.tvmaze.com/atomic-age.jpg"},
        }

        items = parse_tvmaze_result(
            payload,
            expected_title="Science Fiction in the Atomic Age",
            expected_media_type="\u7535\u89c6\u5267",
        )

        self.assertEqual(1, len(items))
        self.assertIn("\u7eaa\u5f55\u7247", items[0].genres)
        self.assertEqual("Documentary", items[0].raw["provider_format"])

    def test_merge_subject_detail_persists_verified_provider_format(self):
        item = MediaItem(
            title="Science Fiction in the Atomic Age",
            media_type="\u7535\u89c6\u5267",
            genres=["\u7535\u89c6\u5267"],
            raw={"provider_ids": {"tvmaze": "83363"}},
        )
        detail = MediaItem(
            title=item.title,
            media_type="\u7535\u89c6\u5267",
            genres=["\u7eaa\u5f55\u7247"],
            source="tvmaze_api",
            raw={"provider_format": "Documentary"},
        )

        merge_subject_detail(item, detail)

        self.assertEqual("Documentary", item.raw["provider_format"])
        self.assertIn("\u7eaa\u5f55\u7247", item.genres)

    def test_tmdb_public_search_uses_year_to_disambiguate_same_title_movies(self):
        page = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/514847"><img alt="狩猎" src="https://media.themoviedb.org/t/p/w94_and_h141_face/wrong.jpg"></a>
          <h2><span>狩猎</span></h2><span>2020</span>
        </div>
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/103663"><img alt="狩猎" src="https://media.themoviedb.org/t/p/w94_and_h141_face/correct.jpg"></a>
          <h2><span>狩猎</span></h2><span>2012</span>
        </div>
        """

        results = parse_themoviedb_search_html(
            page,
            expected_title="狩猎",
            expected_media_type="电影",
            expected_year=2012,
        )

        self.assertEqual(1, len(results))
        self.assertEqual(2012, results[0].year)
        self.assertIn("/movie/103663", results[0].url)
        self.assertIn("correct.jpg", results[0].cover)

    def test_public_tmdb_metadata_fetch_adds_multiple_exact_title_stills_without_api_key(self):
        search_page = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/1305781"><img alt="镖人：风起大漠" src="https://media.themoviedb.org/t/p/w94_and_h141_face/poster.jpg"></a>
          <h2><span>镖人：风起大漠</span></h2>
        </div>
        """.encode("utf-8")
        detail_page = """
        <meta property="og:title" content="镖人：风起大漠">
        <meta property="og:description" content="刀马接下特殊押镖任务，与同伴从西域远赴长安。">
        <meta property="og:image" content="https://media.themoviedb.org/t/p/w500/poster.jpg">
        <meta property="og:image" content="https://media.themoviedb.org/t/p/w780/hero.jpg">
        <script type="application/ld+json">{"@type":"Movie","name":"镖人：风起大漠","description":"刀马接下特殊押镖任务，与同伴从西域远赴长安。","genre":["动作","冒险"],"releasedEvent":[{"startDate":"2026-02-17"}]}</script>
        """.encode("utf-8")
        backdrops_page = """
        <img class="backdrop" src="https://media.themoviedb.org/t/p/w533_and_h300_face/still-a.jpg">
        <img class="backdrop" src="https://media.themoviedb.org/t/p/w533_and_h300_face/still-b.jpg">
        """.encode("utf-8")
        calls = []

        def fake_fetcher(url, accept_json=False):
            calls.append(url)
            if "/search?" in url:
                return search_page
            if "/remote/media_panel/backdrops" in url:
                return backdrops_page
            if "/movie/1305781" in url:
                return detail_page
            return b""

        results = fetch_themoviedb_metadata_suggestions(
            "镖人：风起大漠",
            media_type="电影",
            fetcher=fake_fetcher,
        )

        self.assertEqual(1, len(results))
        item = results[0]
        self.assertIn("特殊押镖任务", item.summary)
        self.assertEqual(["动作", "冒险"], item.genres)
        self.assertGreaterEqual(len(item.raw["stills"]), 3)
        self.assertTrue(all("media.themoviedb.org" in url for url in item.raw["stills"]))
        self.assertTrue(any("remote/media_panel/backdrops" in url for url in calls))

    def test_public_tmdb_metadata_fetch_adds_cast_director_and_verified_people_photos(self):
        search_page = """
        <div class="comp:media-card">
          <a data-media-type="tv" href="/tv/87108"><img alt="切尔诺贝利" src="https://media.themoviedb.org/t/p/w94_and_h141_face/poster.jpg"></a>
          <h2><span>切尔诺贝利</span></h2><span>2019</span>
        </div>
        """.encode("utf-8")
        detail_page = """
        <meta property="og:title" content="切尔诺贝利">
        <script type="application/ld+json">
        {"@type":"TVSeries","name":"切尔诺贝利","description":"核事故背后的真实代价。","startDate":"2019-05-06","genre":["剧情","历史"],"aggregateRating":{"ratingValue":"8.7"}}
        </script>
        <ol class="people no_image">
          <li class="profile"><p><a href="/person/35796">克雷格·马津</a></p><p class="character">原创作者</p></li>
        </ol>
        <section class="panel top_billed scroller"><div id="cast_scroller"><ol class="people scroller">
          <li class="card"><a href="/person/15440"><img class="profile" src="https://media.themoviedb.org/t/p/w276_and_h350_face/actor.jpg" alt="杰瑞德·哈里斯"></a><p><a href="/person/15440">杰瑞德·哈里斯</a></p></li>
        </ol></div></section>
        """.encode("utf-8")
        cast_page = """
        <div class="crew_wrapper"><h4>导演</h4><ol class="people credits crew">
          <li><a href="/person/10000"><img class="profile" src="https://media.themoviedb.org/t/p/w132_and_h132_face/assistant.jpg" alt="助理导演"></a><div><p><a href="/person/10000">助理导演</a></p><p class="episode_count_crew">First Assistant Director</p></div></li>
          <li><a href="/person/212408"><img class="profile" src="https://media.themoviedb.org/t/p/w132_and_h132_face/director.jpg" alt="约翰·伦克"></a><div><p><a href="/person/212408">约翰·伦克</a></p><p class="episode_count_crew">Director</p></div></li>
        </ol></div>
        """.encode("utf-8")
        calls = []

        def fake_fetcher(url, **_kwargs):
            calls.append(url)
            if "/search" in url:
                return search_page
            if "/cast?" in url:
                return cast_page
            if "/remote/media_panel/backdrops" in url:
                return b""
            if "/tv/87108" in url:
                return detail_page
            return b""

        results = fetch_themoviedb_metadata_suggestions(
            "切尔诺贝利",
            media_type="电视剧",
            expected_year=2019,
            fetcher=fake_fetcher,
        )

        self.assertEqual(1, len(results))
        item = results[0]
        self.assertIn("约翰·伦克", item.directors)
        self.assertNotIn("助理导演", item.directors)
        self.assertIn("杰瑞德·哈里斯", item.casts)
        self.assertEqual("https://media.themoviedb.org/t/p/w500/director.jpg", item.raw["people_photos"]["约翰·伦克"])
        self.assertEqual("https://media.themoviedb.org/t/p/w500/actor.jpg", item.raw["people_photos"]["杰瑞德·哈里斯"])
        self.assertTrue(any("/tv/87108/cast?" in url for url in calls))

    def test_public_tmdb_metadata_uses_detail_year_when_search_shows_a_local_rerelease(self):
        search_page = """
        <div class="comp:media-card">
          <a data-media-type="movie" href="/movie/238-the-godfather"><img alt="教父" src="https://media.themoviedb.org/t/p/w94_and_h141_face/godfather.jpg"></a>
          <h2><span>教父</span></h2><span class="release_date">2022 年 02 月 25 日</span>
        </div>
        """.encode("utf-8")
        detail_page = """
        <meta property="og:title" content="教父">
        <script type="application/ld+json">
        {"@type":"Movie","name":"教父","description":"柯里昂家族的权力史诗。","releasedEvent":[{"startDate":"1972-03-14"}],"aggregateRating":{"ratingValue":"8.7"}}
        </script>
        """.encode("utf-8")

        def fake_fetcher(url, **_kwargs):
            if "/search" in url:
                return search_page
            if "/movie/238" in url and "/cast?" not in url and "/remote/" not in url:
                return detail_page
            return b""

        results = fetch_themoviedb_metadata_suggestions(
            "教父",
            media_type="电影",
            expected_year=1972,
            fetcher=fake_fetcher,
        )

        self.assertEqual(1, len(results))
        self.assertEqual(1972, results[0].year)
        self.assertEqual(8.7, results[0].raw["ratings"]["tmdb"])

    def test_summary_translation_parses_google_result_and_records_provider(self):
        translate = getattr(douban_sources_module, "fetch_chinese_summary_translation", None)
        self.assertIsNotNone(translate)
        original = "Historian Dominic Sandbrook and leading creators tell the story of science fiction."
        calls = []

        def fake_fetcher(url, **_kwargs):
            calls.append(url)
            return json.dumps([[["\u5386\u53f2\u5b66\u5bb6\u591a\u7c73\u5c3c\u514b\u00b7\u6851\u5fb7\u5e03\u9c81\u514b\u548c\u4e3b\u8981\u521b\u4f5c\u8005\u8bb2\u8ff0\u4e86\u79d1\u5e7b\u5c0f\u8bf4\u7684\u6545\u4e8b\u3002",
                original,
                None,
                None,
            ]]]).encode("utf-8")

        translated, source = translate(original, fetcher=fake_fetcher)

        self.assertEqual("\u5386\u53f2\u5b66\u5bb6\u591a\u7c73\u5c3c\u514b\u00b7\u6851\u5fb7\u5e03\u9c81\u514b\u548c\u4e3b\u8981\u521b\u4f5c\u8005\u8bb2\u8ff0\u4e86\u79d1\u5e7b\u5c0f\u8bf4\u7684\u6545\u4e8b\u3002", translated)
        self.assertEqual("machine_translation:google", source)
        self.assertTrue(any("translate.googleapis.com" in url for url in calls))

    def test_summary_translation_falls_back_to_mymemory_when_google_has_no_usable_chinese(self):
        translate = getattr(douban_sources_module, "fetch_chinese_summary_translation", None)
        self.assertIsNotNone(translate)
        original = "A mysterious journey across forgotten places and unexplained events."
        calls = []

        def fake_fetcher(url, **_kwargs):
            calls.append(url)
            if "translate.googleapis.com" in url:
                return b"[]"
            return json.dumps({
                "responseStatus": 200,
                "responseData": {"translatedText": "\u4e00\u6b21\u7a7f\u8d8a\u88ab\u9057\u5fd8\u4e4b\u5730\u4e0e\u672a\u89e3\u4e8b\u4ef6\u7684\u795e\u79d8\u65c5\u7a0b\u3002"},
            }).encode("utf-8")

        translated, source = translate(original, fetcher=fake_fetcher)

        self.assertEqual("\u4e00\u6b21\u7a7f\u8d8a\u88ab\u9057\u5fd8\u4e4b\u5730\u4e0e\u672a\u89e3\u4e8b\u4ef6\u7684\u795e\u79d8\u65c5\u7a0b\u3002", translated)
        self.assertEqual("machine_translation:mymemory", source)
        self.assertEqual(2, len(calls))

    def test_summary_translation_default_transport_uses_requests_instead_of_slow_urllib(self):
        translate = getattr(douban_sources_module, "fetch_chinese_summary_translation", None)
        self.assertIsNotNone(translate)
        original = "Historian Dominic Sandbrook and leading creators tell the story of science fiction."

        class FakeResponse:
            content = json.dumps([[["\u5386\u53f2\u5b66\u5bb6\u8bb2\u8ff0\u79d1\u5e7b\u5c0f\u8bf4\u7684\u6545\u4e8b\u3002", original, None, None]]]).encode("utf-8")

            def raise_for_status(self):
                return None

            def close(self):
                return None

        with (
            mock.patch("requests.Session.get", return_value=FakeResponse()) as request,
            mock.patch.object(douban_sources_module, "http_get", side_effect=AssertionError("urllib transport used")),
        ):
            translated, source = translate(original)

        self.assertEqual("\u5386\u53f2\u5b66\u5bb6\u8bb2\u8ff0\u79d1\u5e7b\u5c0f\u8bf4\u7684\u6545\u4e8b\u3002", translated)
        self.assertEqual("machine_translation:google", source)
        request.assert_called_once()

    def test_summary_translation_chunks_long_mymemory_fallback_without_truncating_copy(self):
        translate = getattr(douban_sources_module, "fetch_chinese_summary_translation", None)
        self.assertIsNotNone(translate)
        first = ("Alpha explorers investigate forgotten places and unexplained events. " * 5).strip()
        second = ("Beta historians reconstruct witness accounts and possible explanations. " * 5).strip()
        original = first + " " + second
        mymemory_queries = []
        translations = ["\u7b2c\u4e00\u6bb5\u4e2d\u6587\u3002", "\u7b2c\u4e8c\u6bb5\u4e2d\u6587\u3002"]

        def fake_fetcher(url, **_kwargs):
            if "translate.googleapis.com" in url:
                return b"[]"
            query = urllib.parse.parse_qs(urllib.parse.urlsplit(url).query).get("q", [""])[0]
            mymemory_queries.append(query)
            translated = translations[min(len(mymemory_queries) - 1, len(translations) - 1)]
            return json.dumps({
                "responseStatus": 200,
                "responseData": {"translatedText": translated},
            }).encode("utf-8")

        translated, source = translate(original, fetcher=fake_fetcher)

        self.assertEqual("".join(translations), translated)
        self.assertEqual("machine_translation:mymemory", source)
        self.assertEqual(2, len(mymemory_queries))
        self.assertTrue(all(len(query) <= 420 for query in mymemory_queries))

    def test_merge_subject_detail_replaces_english_summary_with_verified_chinese_copy(self):
        item = MediaItem(
            title="\u79d1\u5e7b\u771f\u53f2",
            media_type="\u7535\u89c6\u5267",
            year=2014,
            summary="Historian Dominic Sandbrook and leading creators tell the story of science fiction.",
            source="global:tvmaze",
            raw={"aliases": ["The Real History of Science Fiction"]},
        )
        detail = MediaItem(
            title="\u79d1\u5e7b\u771f\u53f2",
            media_type="\u7535\u89c6\u5267",
            year=2014,
            summary="\u5386\u53f2\u5b66\u5bb6\u591a\u7c73\u5c3c\u514b\u00b7\u6851\u5fb7\u5e03\u9c81\u514b\u4e0e\u4e3b\u8981\u521b\u4f5c\u8005\u5171\u540c\u8bb2\u8ff0\u79d1\u5e7b\u4f5c\u54c1\u7684\u5386\u53f2\u3002",
            source="themoviedb_detail",
        )

        merge_subject_detail(item, detail)

        self.assertEqual(detail.summary, item.summary)
        self.assertEqual("themoviedb_detail", item.raw["summary_source"])

    def test_public_metadata_enrichment_localizes_an_existing_english_summary_and_caches_provenance(self):
        series = MediaItem(
            title="\u79d1\u5e7b\u771f\u53f2",
            media_type="\u7535\u89c6\u5267",
            year=2014,
            summary="Historian Dominic Sandbrook and leading creators tell the story of science fiction.",
            genres=["\u79d1\u5e7b", "\u5386\u53f2"],
            directors=["Ben Southwell"],
            casts=["Dominic Sandbrook"],
            raw={
                "ratings": {"douban": 8.5},
                "stills": ["https://img.example/science-fiction.jpg"],
                "people_photos": {
                    "Ben Southwell": "https://img.example/ben.jpg",
                    "Dominic Sandbrook": "https://img.example/dominic.jpg",
                },
            },
        )
        translated = "\u5386\u53f2\u5b66\u5bb6\u591a\u7c73\u5c3c\u514b\u00b7\u6851\u5fb7\u5e03\u9c81\u514b\u548c\u4e3b\u8981\u521b\u4f5c\u8005\u8bb2\u8ff0\u4e86\u79d1\u5e7b\u5c0f\u8bf4\u7684\u6545\u4e8b\u3002"
        with (
            mock.patch.object(
                douban_sources_module,
                "fetch_chinese_summary_translation",
                return_value=(translated, "machine_translation:google"),
                create=True,
            ) as translator,
            mock.patch.object(
                douban_sources_module,
                "fetch_themoviedb_metadata_suggestions",
                return_value=[],
            ) as tmdb_provider,
        ):
            changed = enrich_public_metadata(series)

        self.assertTrue(changed)
        translator.assert_called_once()
        tmdb_provider.assert_not_called()
        self.assertEqual(translated, series.summary)
        self.assertEqual(
            "Historian Dominic Sandbrook and leading creators tell the story of science fiction.",
            series.raw["summary_original"],
        )
        self.assertEqual("machine_translation:google", series.raw["summary_source"])
        self.assertTrue(series.raw["summary_generated"])
        self.assertEqual(2, series.raw["summary_translation_version"])

    def test_public_metadata_hydrates_tvmaze_format_before_summary_translation(self):
        series = MediaItem(
            title="Science Fiction in the Atomic Age",
            media_type="\u7535\u89c6\u5267",
            year=2025,
            summary="A complete English synopsis about science fiction in the atomic age.",
            genres=["\u7535\u89c6\u5267"],
            douban_id="tvmaze-83363",
            raw={"provider_ids": {"tvmaze": "83363"}},
        )
        detail = MediaItem(
            title=series.title,
            media_type="\u7535\u89c6\u5267",
            year=2025,
            genres=["\u7eaa\u5f55\u7247"],
            directors=["Director One"],
            casts=["Presenter One"],
            summary=series.summary,
            source="tvmaze_api",
            raw={
                "provider_format": "Documentary",
                "ratings": {"tvmaze": 8.0},
                "stills": ["https://static.tvmaze.com/atomic-age-still.jpg"],
                "people_photos": {
                    "Director One": "https://static.tvmaze.com/director-one.jpg",
                    "Presenter One": "https://static.tvmaze.com/presenter-one.jpg",
                },
            },
        )
        localized = "\u8fd9\u90e8\u7eaa\u5f55\u7247\u5267\u96c6\u56de\u987e\u4e86\u539f\u5b50\u65f6\u4ee3\u7684\u79d1\u5e7b\u53d1\u5c55\u3002"
        calls = []

        def tvmaze_provider(*_args, **_kwargs):
            calls.append("tvmaze")
            return [detail]

        def translate(_summary):
            calls.append("translate")
            return localized, "machine_translation:google"

        with (
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", side_effect=tvmaze_provider),
            mock.patch.object(douban_sources_module, "fetch_chinese_summary_translation", side_effect=translate),
        ):
            changed = enrich_public_metadata(series)

        self.assertTrue(changed)
        self.assertEqual(["tvmaze", "translate"], calls)
        self.assertIn("\u7eaa\u5f55\u7247", series.genres)
        self.assertEqual(localized, series.summary)

    def test_public_metadata_enrichment_uses_tmdb_for_movies(self):
        movie = MediaItem(title="镖人：风起大漠", media_type="电影", douban_id="36474027")
        detail = MediaItem(
            title=movie.title,
            media_type="电影",
            year=2026,
            genres=["动作", "冒险"],
            summary="刀马接下特殊押镖任务，与同伴从西域远赴长安。",
            source="themoviedb_detail",
            raw={"stills": ["https://media.themoviedb.org/t/p/w1280/still.jpg"]},
        )
        with mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", return_value=[detail]):
            changed = enrich_public_metadata(movie)

        self.assertTrue(changed)
        self.assertEqual(2026, movie.year)
        self.assertEqual(["动作", "冒险"], movie.genres)
        self.assertIn("特殊押镖任务", movie.summary)
        self.assertEqual(detail.raw["stills"], movie.raw["stills"])

    def test_public_metadata_enrichment_still_queries_rating_when_synopsis_and_stills_exist(self):
        movie = MediaItem(
            title="测试电影",
            media_type="电影",
            year=2024,
            summary="已有可靠简介。",
            raw={"stills": ["https://img.example/still.jpg"]},
        )
        detail = MediaItem(
            title="测试电影",
            media_type="电影",
            year=2024,
            summary="已有可靠简介。",
            raw={"ratings": {"tmdb": 8.1}, "rating_votes": {"tmdb": 12345}},
        )
        with mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", return_value=[detail]) as provider:
            changed = enrich_public_metadata(movie)

        self.assertTrue(changed)
        provider.assert_called_once()
        self.assertEqual(8.1, movie.raw["ratings"]["tmdb"])

    def test_public_metadata_enrichment_still_queries_people_when_other_metadata_is_complete(self):
        series = MediaItem(
            title="测试剧集",
            media_type="电视剧",
            year=2024,
            summary="已有可靠简介。",
            raw={
                "stills": ["https://img.example/still.jpg"],
                "ratings": {"tmdb": 8.6},
            },
        )
        detail = MediaItem(
            title="测试剧集",
            media_type="电视剧",
            year=2024,
            summary="已有可靠简介。",
            directors=["导演甲"],
            casts=["演员乙"],
            raw={
                "people_photos": {
                    "导演甲": "https://media.themoviedb.org/t/p/w500/director.jpg",
                    "演员乙": "https://media.themoviedb.org/t/p/w500/actor.jpg",
                }
            },
        )
        with mock.patch.object(
            douban_sources_module,
            "fetch_themoviedb_metadata_suggestions",
            return_value=[detail],
        ) as provider:
            changed = enrich_public_metadata(series)

        self.assertTrue(changed)
        provider.assert_called_once()
        self.assertEqual(["导演甲"], series.directors)
        self.assertEqual(["演员乙"], series.casts)
        self.assertEqual(detail.raw["people_photos"], series.raw["people_photos"])

    def test_public_metadata_enrichment_uses_verified_item_aliases_for_global_sources(self):
        series = MediaItem(
            title="机智医生生活",
            media_type="电视剧",
            year=2020,
            douban_id="33464863",
            raw={"aliases": ["Hospital Playlist", "슬기로운 의사생활"]},
        )
        detail = MediaItem(
            title="Hospital Playlist",
            media_type="电视剧",
            year=2020,
            cover="https://static.tvmaze.com/hospital-playlist.jpg",
            summary="Five doctors balance friendship, music and life in a busy hospital.",
            source="tvmaze_api",
            raw={
                "stills": ["https://static.tvmaze.com/hospital-playlist-still.jpg"],
                "ratings": {"tvmaze": 6.9},
            },
        )
        tmdb_queries = []
        tvmaze_queries = []

        def tmdb_provider(title, **_kwargs):
            tmdb_queries.append(title)
            return []

        def tvmaze_provider(title, **_kwargs):
            tvmaze_queries.append(title)
            return [detail] if title == "Hospital Playlist" else []

        localized_summary = "\u4e94\u4f4d\u533b\u751f\u5728\u7e41\u5fd9\u7684\u533b\u9662\u4e2d\u5e73\u8861\u53cb\u8c0a\u3001\u97f3\u4e50\u548c\u751f\u6d3b\u3002"
        with (
            mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", side_effect=tmdb_provider),
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", side_effect=tvmaze_provider),
            mock.patch.object(
                douban_sources_module,
                "fetch_chinese_summary_translation",
                return_value=(localized_summary, "machine_translation:google"),
            ) as translator,
        ):
            changed = enrich_public_metadata(series)

        self.assertTrue(changed)
        self.assertEqual("机智医生生活", series.title)
        self.assertEqual("33464863", series.douban_id)
        self.assertEqual(2020, series.year)
        self.assertIn("Hospital Playlist", tmdb_queries)
        self.assertIn("Hospital Playlist", tvmaze_queries)
        self.assertEqual(localized_summary, series.summary)
        translator.assert_called_once_with(detail.summary)
        self.assertEqual(detail.summary, series.raw["summary_original"])
        self.assertEqual("machine_translation:google", series.raw["summary_source"])
        self.assertEqual(detail.raw["stills"], series.raw["stills"])
        self.assertEqual(6.9, series.raw["ratings"]["tvmaze"])

    def test_public_metadata_enrichment_continues_until_missing_visuals_and_people_are_added(self):
        anime = MediaItem(
            title="\u672a\u6765\u52a8\u753b",
            media_type="\u52a8\u6f2b",
            year=2026,
            genres=["\u5947\u5e7b"],
            summary="\u5df2\u6709\u7b80\u4ecb\u3002",
            raw={"ratings": {"anilist": 8.2}},
        )
        no_improvement = MediaItem(
            title="\u672a\u6765\u52a8\u753b",
            media_type="\u52a8\u6f2b",
            year=2026,
            summary="\u53ea\u6709\u91cd\u590d\u7b80\u4ecb\u3002",
            raw={"ratings": {"anilist": 8.2}},
        )
        complete_detail = MediaItem(
            title="\u672a\u6765\u52a8\u753b",
            media_type="\u52a8\u6f2b",
            year=2026,
            directors=["\u5bfc\u6f14\u7532"],
            casts=["\u58f0\u4f18\u4e59"],
            raw={
                "stills": ["https://s4.anilist.co/file/anilistcdn/media/anime/banner/future.jpg"],
                "people_photos": {
                    "\u5bfc\u6f14\u7532": "https://s4.anilist.co/file/anilistcdn/staff/director.jpg",
                    "\u58f0\u4f18\u4e59": "https://s4.anilist.co/file/anilistcdn/staff/actor.jpg",
                },
            },
        )

        with (
            mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", return_value=[no_improvement]),
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", return_value=[]),
            mock.patch.object(douban_sources_module, "fetch_anilist_suggestions", return_value=[complete_detail]) as anilist,
            mock.patch.object(douban_sources_module, "fetch_jikan_suggestions", return_value=[]),
        ):
            changed = enrich_public_metadata(anime)

        self.assertTrue(changed)
        anilist.assert_called_once()
        self.assertEqual(["\u5bfc\u6f14\u7532"], anime.directors)
        self.assertEqual(["\u58f0\u4f18\u4e59"], anime.casts)
        self.assertEqual(complete_detail.raw["stills"], anime.raw["stills"])
        self.assertTrue(douban_sources_module.has_people_photo_coverage(anime))

    def test_people_photo_coverage_rejects_provider_default_portrait(self):
        item = MediaItem(
            title="\u4eba\u7269\u56fe\u9ed8\u8ba4\u503c\u6d4b\u8bd5",
            directors=["\u5bfc\u6f14\u7532"],
            casts=["\u6f14\u5458\u4e59"],
            raw={
                "people_photos": {
                    "\u5bfc\u6f14\u7532": "https://img1.doubanio.com/f/vendors/pics/personage-default-medium.png",
                    "\u6f14\u5458\u4e59": "https://img1.doubanio.com/view/celebrity/m/public/actor.jpg",
                }
            },
        )

        self.assertFalse(douban_sources_module.has_people_photo_coverage(item))

    def test_public_metadata_accepts_parent_series_people_for_a_later_animation_season(self):
        season = MediaItem(
            title="\u745e\u514b\u548c\u83ab\u8482",
            media_type="\u52a8\u6f2b",
            year=2026,
            genres=["\u559c\u5267", "\u52a8\u753b"],
            casts=["Ian Cardoni"],
            summary="\u7b2c\u4e5d\u5b63\u5267\u60c5\u7b80\u4ecb\u3002",
            raw={
                "aliases": ["Rick and Morty", "Rick and Morty Season 9"],
                "ratings": {"douban": 9.1},
                "stills": ["https://img1.doubanio.com/season-nine.jpg"],
                "people_photos": {"Ian Cardoni": "https://img1.doubanio.com/ian.jpg"},
            },
        )
        parent = MediaItem(
            title="Rick and Morty",
            media_type="\u52a8\u6f2b",
            year=2013,
            directors=["Dan Harmon"],
            casts=["Ian Cardoni"],
            source="tvmaze_api",
            raw={
                "ratings": {"tvmaze": 9.8},
                "provider_ids": {"tvmaze": "216"},
                "stills": ["https://static.tvmaze.com/parent-series-still.jpg"],
                "people_photos": {
                    "Dan Harmon": "https://static.tvmaze.com/dan-harmon.jpg",
                    "Ian Cardoni": "https://static.tvmaze.com/ian-cardoni.jpg",
                },
            },
        )

        def tvmaze_provider(title, **_kwargs):
            return [parent] if title == "Rick and Morty" else []

        with (
            mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", return_value=[]),
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", side_effect=tvmaze_provider),
            mock.patch.object(douban_sources_module, "fetch_anilist_suggestions", return_value=[]),
            mock.patch.object(douban_sources_module, "fetch_jikan_suggestions", return_value=[]),
        ):
            changed = enrich_public_metadata(season)

        self.assertTrue(changed)
        self.assertEqual(2026, season.year)
        self.assertEqual(["Dan Harmon"], season.directors)
        self.assertEqual(["Ian Cardoni"], season.casts)
        self.assertEqual("https://static.tvmaze.com/dan-harmon.jpg", season.raw["people_photos"]["Dan Harmon"])
        self.assertEqual({"douban": 9.1}, season.raw["ratings"])
        self.assertEqual(["https://img1.doubanio.com/season-nine.jpg"], season.raw["stills"])
        self.assertNotIn("provider_ids", season.raw)

    def test_public_metadata_rejects_unrelated_same_title_tvmaze_result_across_years(self):
        original = MediaItem(
            title="Mystery Island",
            media_type="\u7535\u89c6\u5267",
            year=1977,
            genres=["\u5192\u9669", "\u79d1\u5e7b"],
            summary="1977 \u5e74\u539f\u4f5c\u7b80\u4ecb\u3002",
            source="tvmaze_api",
            douban_id="tvmaze-53397",
            raw={
                "provider_ids": {"tvmaze": "53397"},
                "ratings": {"tvmaze": 7.9},
                "stills": ["https://static.tvmaze.com/1977-original-still.jpg"],
            },
        )
        unrelated = MediaItem(
            title="Mystery Island",
            media_type="\u7535\u89c6\u5267",
            year=2023,
            directors=["Nicholas Humphries"],
            casts=["Elizabeth Henstridge", "Charlie Weber", "Kezia Burrows"],
            douban_rating=8.7,
            source="tvmaze_api",
            douban_id="tvmaze-83671",
            raw={
                "provider_ids": {"tvmaze": "83671", "imdb": "tt27634231"},
                "ratings": {"tvmaze": 8.7},
                "stills": ["https://static.tvmaze.com/2023-unrelated-still.jpg"],
                "people_photos": {
                    "Nicholas Humphries": "https://static.tvmaze.com/nicholas.jpg",
                    "Elizabeth Henstridge": "https://static.tvmaze.com/elizabeth.jpg",
                    "Charlie Weber": "https://static.tvmaze.com/charlie.jpg",
                    "Kezia Burrows": "https://static.tvmaze.com/kezia.jpg",
                },
            },
        )

        with (
            mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", return_value=[]),
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", return_value=[unrelated]),
            mock.patch.object(douban_sources_module, "fetch_imdb_metadata_suggestions", return_value=[]),
        ):
            changed = enrich_public_metadata(original)

        self.assertFalse(changed)
        self.assertEqual(1977, original.year)
        self.assertEqual([], original.directors)
        self.assertEqual([], original.casts)
        self.assertEqual("tvmaze-53397", original.douban_id)
        self.assertEqual({"tvmaze": "53397"}, original.raw["provider_ids"])
        self.assertEqual({"tvmaze": 7.9}, original.raw["ratings"])
        self.assertEqual(["https://static.tvmaze.com/1977-original-still.jpg"], original.raw["stills"])
        self.assertNotIn("people_photos", original.raw)

    def test_parse_mobile_subject_detail_extracts_rating_votes_year_aliases_and_metadata(self):
        page = """
        <meta property="og:title" content="人生切割术 第一季 - 电视剧" />
        <meta property="og:image" content="https://img.example/severance.jpg" />
        <meta itemprop="reviewCount" content="182947" />
        <meta itemprop="ratingValue" content="9.0" />
        <div class="sub-original-title">Severance Season 1（2022）</div>
        <div class="sub-meta">美国 / 剧情 / 科幻 / 悬疑 / 2022-02-18(美国)上映 / 片长60分钟</div>
        <section class="subject-intro"><p>一段真实剧情简介。</p></section>
        """

        detail = parse_subject_detail_html(page, url="https://m.douban.com/movie/subject/34885342/")

        self.assertEqual(detail.title, "人生切割术 第一季")
        self.assertEqual(detail.year, 2022)
        self.assertEqual(detail.douban_rating, 9.0)
        self.assertEqual(detail.vote_count, 182947)
        self.assertEqual(detail.genres, ["剧情", "科幻", "悬疑"])
        self.assertEqual(detail.countries, ["美国"])
        self.assertIn("Severance Season 1", detail.raw["aliases"])

    def test_merge_subject_detail_preserves_user_comment_separately_and_uses_real_synopsis(self):
        item = MediaItem(
            title="同步作品",
            summary="这是我的短评",
            source="douban_user:collect",
            raw={},
        )
        detail = MediaItem(title="同步作品", summary="这是作品的官方剧情简介", source="douban_subject_detail")

        merge_subject_detail(item, detail)

        self.assertEqual(item.summary, "这是作品的官方剧情简介")
        self.assertEqual(item.raw["user_comment"], "这是我的短评")

    def test_merge_subject_detail_replaces_generated_catalog_copy_with_verified_synopsis(self):
        item = MediaItem(
            title="待补作品",
            media_type="电影",
            summary="由 CineScope 精选扩展池补入的电影候选：待补作品。优先通过公共来源补图。",
            source="premium_expansion",
        )
        detail = MediaItem(
            title="待补作品",
            media_type="电影",
            summary="这是经过标题校验的真实剧情简介。",
            source="themoviedb_detail",
        )

        merge_subject_detail(item, detail)

        self.assertEqual("这是经过标题校验的真实剧情简介。", item.summary)

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

    def test_douban_detail_fetch_rejects_untrusted_hosts_before_opening(self):
        malicious = "http://127.0.0.1/private/movie.douban.com/subject/33404425/"

        with mock.patch("douban_recommender.douban_sources.build_url_opener") as opener:
            with self.assertRaisesRegex(ValueError, "Douban subject URL"):
                fetch_douban_detail_html(malicious, "bid=secret-cookie")

        opener.assert_not_called()

    def test_subject_detail_urls_never_reuse_an_untrusted_item_url(self):
        malicious = MediaItem(
            title="恶意本地条目",
            url="http://127.0.0.1/private/movie.douban.com/subject/33404425/",
        )

        urls = subject_detail_urls(malicious)

        self.assertEqual(
            urls,
            [
                "https://m.douban.com/movie/subject/33404425/",
                "https://movie.douban.com/subject/33404425/",
            ],
        )

    def test_douban_detail_fetch_revalidates_redirects_before_forwarding_cookie(self):
        received_cookies = []

        class RedirectHandler(BaseHTTPRequestHandler):
            def do_GET(self):
                if self.path == "/start":
                    self.send_response(302)
                    self.send_header("Location", f"http://localhost:{self.server.server_address[1]}/target")
                    self.end_headers()
                    return
                received_cookies.append(self.headers.get("Cookie"))
                self.send_response(200)
                self.end_headers()
                self.wfile.write(b"ok")

            def log_message(self, *_args):
                return

        server = ThreadingHTTPServer(("127.0.0.1", 0), RedirectHandler)
        thread = threading.Thread(target=server.serve_forever, daemon=True)
        thread.start()
        initial = f"http://127.0.0.1:{server.server_address[1]}/start"

        def allow_only_initial(url):
            parsed = urllib.parse.urlparse(str(url))
            if parsed.hostname == "127.0.0.1" and parsed.path == "/start":
                return str(url)
            raise ValueError("Douban subject URL redirect rejected")

        try:
            with mock.patch.object(douban_sources_module, "_validated_douban_subject_url", side_effect=allow_only_initial):
                with self.assertRaisesRegex(ValueError, "redirect rejected"):
                    fetch_douban_detail_html(initial, "bid=secret-cookie")
        finally:
            server.shutdown()
            server.server_close()
            thread.join(timeout=5)

        self.assertEqual([], received_cookies)

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
            <img alt="心跳漏一拍" src="https://media.themoviedb.org/t/p/w94_and_h141_face/heart.jpg" />
          </a>
          <h2><span>心跳漏一拍</span></h2>
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

    def test_tvmaze_parser_keeps_synopsis_and_episode_stills_for_detail_visuals(self):
        payload = {
            "id": 28866,
            "name": "The End of the F***ing World",
            "premiered": "2017-10-24",
            "summary": "<p>两个年轻人踏上一段失控的旅程。</p>",
            "image": {"original": "https://static.tvmaze.com/uploads/images/original_untouched/348/870850.jpg"},
            "_embedded": {
                "episodes": [
                    {"image": {"original": "https://static.tvmaze.com/uploads/images/original_untouched/1/1001.jpg"}},
                    {"image": {"original": "https://static.tvmaze.com/uploads/images/original_untouched/2/2002.jpg"}},
                ],
            },
        }

        item = parse_tvmaze_result(payload, expected_title="The End of the F***ing World", expected_media_type="电视剧")[0]

        self.assertEqual(item.summary, "两个年轻人踏上一段失控的旅程。")
        self.assertEqual(item.raw["stills"], [
            "https://static.tvmaze.com/uploads/images/original_untouched/1/1001.jpg",
            "https://static.tvmaze.com/uploads/images/original_untouched/2/2002.jpg",
        ])

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

    def test_tvmaze_fetch_continues_to_curated_alias_after_original_title_404(self):
        payload = {
            "id": 44933,
            "name": "Severance",
            "premiered": "2022-02-18",
            "url": "https://www.tvmaze.com/shows/44933/severance",
            "image": {"original": "https://static.tvmaze.com/uploads/images/original_untouched/548/1371406.jpg"},
        }
        body = io.BytesIO(b'{"message":"Not Found"}')
        missing = urllib.error.HTTPError(
            url="https://api.tvmaze.com/singlesearch/shows?q=%E4%BA%BA%E7%94%9F%E5%88%87%E5%89%B2%E6%9C%AF",
            code=404,
            msg="Not Found",
            hdrs={},
            fp=body,
        )

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return json.dumps(payload).encode("utf-8")

        class AliasOpener:
            def __init__(self):
                self.calls = 0

            def open(self, request, timeout=0):
                self.calls += 1
                if self.calls == 1:
                    raise missing
                return Response()

        opener = AliasOpener()
        with mock.patch("douban_recommender.douban_sources.build_url_opener", return_value=opener):
            suggestions = fetch_tvmaze_suggestions("人生切割术", media_type="电视剧")

        self.assertTrue(body.closed)
        self.assertEqual(opener.calls, 2)
        self.assertEqual(suggestions[0].title, "人生切割术")
        self.assertEqual(suggestions[0].douban_id, "tvmaze-44933")

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

    def test_anilist_parser_extracts_rating_genres_banner_director_and_voice_cast(self):
        payload = {
            "data": {
                "Page": {
                    "media": [{
                        "id": 182300,
                        "title": {
                            "romaji": "Tsue to Tsurugi no Wistoria Season 2",
                            "english": "Wistoria: Wand and Sword Season 2",
                            "native": "\u6756\u3068\u5263\u306e\u30a6\u30a3\u30b9\u30c8\u30ea\u30a2 Season2",
                        },
                        "format": "TV",
                        "seasonYear": 2026,
                        "description": "A verified fantasy series synopsis.",
                        "genres": ["Action", "Fantasy"],
                        "averageScore": 82,
                        "bannerImage": "https://s4.anilist.co/file/anilistcdn/media/anime/banner/182300.jpg",
                        "coverImage": {
                            "extraLarge": "https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/182300.jpg"
                        },
                        "siteUrl": "https://anilist.co/anime/182300",
                        "staff": {
                            "edges": [{
                                "role": "Director",
                                "node": {
                                    "name": {"full": "Tatsuya Yoshihara", "native": "\u5409\u539f\u9054\u77e2"},
                                    "image": {"large": "https://s4.anilist.co/file/anilistcdn/staff/director.jpg"},
                                },
                            }]
                        },
                        "characters": {
                            "edges": [{
                                "voiceActors": [{
                                    "name": {"full": "Kohei Amasaki", "native": "\u5929\u5d0e\u6edd\u5e73"},
                                    "image": {"large": "https://s4.anilist.co/file/anilistcdn/staff/actor.jpg"},
                                }]
                            }]
                        },
                    }]
                }
            }
        }

        rows = parse_anilist_results(
            payload,
            expected_title="Wistoria: Wand and Sword Season 2",
            expected_media_type="\u52a8\u6f2b",
        )

        self.assertEqual(1, len(rows))
        anime = rows[0]
        self.assertEqual(["Action", "Fantasy"], anime.genres)
        self.assertEqual(["\u5409\u539f\u9054\u77e2"], anime.directors)
        self.assertEqual(["\u5929\u5d0e\u6edd\u5e73"], anime.casts)
        self.assertFalse(any(alias.startswith("{") for alias in anime.raw.get("aliases", [])))
        self.assertEqual(8.2, anime.raw["ratings"]["anilist"])
        self.assertEqual(["https://s4.anilist.co/file/anilistcdn/media/anime/banner/182300.jpg"], anime.raw["stills"])
        self.assertEqual(
            "https://s4.anilist.co/file/anilistcdn/staff/director.jpg",
            anime.raw["people_photos"]["\u5409\u539f\u9054\u77e2"],
        )

    def test_tvmaze_parser_supports_animation_with_creator_cast_portraits_and_episode_stills(self):
        payload = {
            "id": 216,
            "name": "Rick and Morty",
            "premiered": "2013-12-02",
            "summary": "<p>An animated science-fiction comedy.</p>",
            "genres": ["Comedy", "Science-Fiction"],
            "image": {"original": "https://static.tvmaze.com/poster.jpg"},
            "rating": {"average": 8.7},
            "_embedded": {
                "episodes": [{"image": {"original": "https://static.tvmaze.com/episode.jpg"}}],
                "crew": [
                    {
                        "type": "Creator",
                        "person": {
                            "name": "Dan Harmon",
                            "image": {"original": "https://static.tvmaze.com/dan-harmon.jpg"},
                        },
                    },
                    {
                        "type": "Assistant Director",
                        "person": {"name": "Wrong Person", "image": {"original": "https://static.tvmaze.com/wrong.jpg"}},
                    },
                ],
                "cast": [{
                    "person": {
                        "name": "Ian Cardoni",
                        "image": {"original": "https://static.tvmaze.com/ian-cardoni.jpg"},
                    }
                }],
            },
        }

        rows = parse_tvmaze_result(
            payload,
            expected_title="Rick and Morty",
            expected_media_type="\u52a8\u6f2b",
        )

        self.assertEqual(1, len(rows))
        series = rows[0]
        self.assertEqual("\u52a8\u6f2b", series.media_type)
        self.assertEqual(["Dan Harmon"], series.directors)
        self.assertEqual(["Ian Cardoni"], series.casts)
        self.assertEqual(["https://static.tvmaze.com/episode.jpg"], series.raw["stills"])
        self.assertEqual("https://static.tvmaze.com/dan-harmon.jpg", series.raw["people_photos"]["Dan Harmon"])
        self.assertEqual("https://static.tvmaze.com/ian-cardoni.jpg", series.raw["people_photos"]["Ian Cardoni"])

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



class ImdbMetadataRecoveryTests(unittest.TestCase):
    def test_legacy_mymemory_summary_is_retranslated_even_when_other_metadata_is_complete(self):
        original = (
            "Historian Dominic Sandbrook and leading creators tell the story of science fiction, "
            "from speculative literature to film and television."
        )
        legacy = MediaItem(
            title="科幻真史",
            media_type="电视剧",
            year=2014,
            summary="这是一段被旧翻译服务截断的中文简介。",
            genres=["科幻", "纪录片"],
            directors=["Ben Southwell"],
            casts=["Dominic Sandbrook"],
            raw={
                "ratings": {"douban": 8.5},
                "stills": ["https://img.example/science-fiction.jpg"],
                "people_photos": {
                    "Ben Southwell": "https://img.example/ben.jpg",
                    "Dominic Sandbrook": "https://img.example/dominic.jpg",
                },
                "summary_original": original,
                "summary_source": "machine_translation:mymemory",
                "summary_generated": True,
            },
        )
        upgraded = "历史学家多米尼克·桑德布鲁克与主创人员完整梳理科幻文学、电影和电视的发展。"

        with mock.patch.object(
            douban_sources_module,
            "fetch_chinese_summary_translation",
            return_value=(upgraded, "machine_translation:google"),
        ) as translator:
            changed = enrich_public_metadata(legacy)

        self.assertTrue(changed)
        translator.assert_called_once_with(original)
        self.assertEqual(upgraded, legacy.summary)
        self.assertEqual(original, legacy.raw["summary_original"])
        self.assertEqual("machine_translation:google", legacy.raw["summary_source"])
        self.assertEqual(2, legacy.raw["summary_translation_version"])

    def test_version_two_summary_translation_cache_is_not_requested_again(self):
        original = "A complete English synopsis that was already translated and cached."
        cached = MediaItem(
            title="已翻译作品",
            media_type="电视剧",
            summary="这是已经完整缓存的中文简介。",
            genres=["剧情"],
            directors=["导演甲"],
            casts=["演员乙"],
            raw={
                "ratings": {"imdb": 8.0},
                "stills": ["https://img.example/still.jpg"],
                "people_photos": {
                    "导演甲": "https://img.example/director.jpg",
                    "演员乙": "https://img.example/actor.jpg",
                },
                "summary_original": original,
                "summary_source": "machine_translation:mymemory",
                "summary_generated": True,
                "summary_translation_version": 2,
            },
        )

        with mock.patch.object(douban_sources_module, "fetch_chinese_summary_translation") as translator:
            changed = enrich_public_metadata(cached)

        self.assertFalse(changed)
        translator.assert_not_called()
        self.assertEqual("这是已经完整缓存的中文简介。", cached.summary)

    def test_imdb_suggestion_matcher_selects_the_exact_year_and_series_instead_of_the_2010_title(self):
        parser = getattr(douban_sources_module, "parse_imdb_suggestion_results", None)
        self.assertIsNotNone(parser)
        payload = {
            "d": [
                {
                    "id": "tt1660055",
                    "l": "Scooby-Doo! Mystery Incorporated",
                    "y": 2010,
                    "qid": "tvSeries",
                    "s": "Frank Welker, Mindy Cohn",
                },
                {
                    "id": "tt12048470",
                    "l": "Mystery Incorporated",
                    "y": 2022,
                    "qid": "tvSeries",
                    "s": "Dade Elza, Jessica Chancellor",
                },
                {
                    "id": "tt99999999",
                    "l": "Mystery Incorporated",
                    "y": 2022,
                    "qid": "feature",
                    "s": "Different Cast",
                },
            ]
        }

        matches = parser(
            payload,
            expected_title="Mystery Incorporated",
            expected_year=2022,
            expected_media_type="电视剧",
            expected_cast=["Dade Elza", "Jessica Chancellor"],
        )

        self.assertEqual(1, len(matches))
        self.assertEqual("tt12048470", matches[0].raw["provider_ids"]["imdb"])
        self.assertEqual(2022, matches[0].year)
        self.assertEqual("电视剧", matches[0].media_type)

    def test_imdb_graphql_parser_keeps_verified_rating_and_only_landscape_stills(self):
        parser = getattr(douban_sources_module, "parse_imdb_graphql_title", None)
        self.assertIsNotNone(parser)
        payload = {
            "data": {
                "title": {
                    "id": "tt2091018",
                    "titleText": {"text": "Prophets of Science Fiction"},
                    "releaseYear": {"year": 2011},
                    "titleType": {"id": "tvSeries", "text": "TV Series"},
                    "ratingsSummary": {"aggregateRating": 7.9, "voteCount": 726},
                    "primaryImage": {
                        "url": "https://m.media-amazon.com/images/poster.jpg",
                        "width": 680,
                        "height": 1000,
                    },
                    "plots": {
                        "edges": [
                            {"node": {"plotText": {"plainText": "Leading storytellers explore science-fiction ideas."}}}
                        ]
                    },
                    "images": {
                        "edges": [
                            {"node": {"id": "portrait", "url": "https://m.media-amazon.com/images/portrait.jpg", "width": 680, "height": 1000}},
                            {"node": {"id": "scene", "url": "https://m.media-amazon.com/images/scene.jpg", "width": 1280, "height": 720}},
                            {"node": {"id": "scene-copy", "url": "https://m.media-amazon.com/images/scene.jpg", "width": 1920, "height": 1080}},
                        ]
                    },
                    "episodes": {
                        "episodes": {
                            "edges": [
                                {"node": {"id": "tt-episode", "primaryImage": {"url": "https://m.media-amazon.com/images/episode.jpg", "width": 1280, "height": 720}}}
                            ]
                        }
                    },
                }
            }
        }

        matches = parser(
            payload,
            expected_id="tt2091018",
            expected_title="Prophets of Science Fiction",
            expected_year=2011,
            expected_media_type="电视剧",
        )

        self.assertEqual(1, len(matches))
        item = matches[0]
        self.assertEqual(7.9, item.raw["ratings"]["imdb"])
        self.assertEqual(726, item.raw["rating_votes"]["imdb"])
        self.assertEqual("tt2091018", item.raw["provider_ids"]["imdb"])
        self.assertEqual("https://m.media-amazon.com/images/poster.jpg", item.cover)
        self.assertEqual(
            [
                "https://m.media-amazon.com/images/scene.jpg",
                "https://m.media-amazon.com/images/episode.jpg",
            ],
            item.raw["stills"],
        )
        self.assertEqual([], parser(payload, expected_id="tt0000001", expected_title="Prophets of Science Fiction", expected_year=2011, expected_media_type="电视剧"))
        self.assertEqual([], parser(payload, expected_id="tt2091018", expected_title="Different Title", expected_year=2011, expected_media_type="电视剧"))
        self.assertEqual([], parser(payload, expected_id="tt2091018", expected_title="Prophets of Science Fiction", expected_year=1999, expected_media_type="电视剧"))

    def test_tvmaze_parser_preserves_its_verified_imdb_identifier(self):
        payload = {
            "id": 61855,
            "name": "Mystery Incorporated",
            "type": "Scripted",
            "premiered": "2022-04-27",
            "genres": ["Crime", "Mystery"],
            "externals": {"imdb": "tt12048470"},
            "image": {"original": "https://static.tvmaze.com/poster.jpg"},
            "summary": "A fresh new series.",
            "_embedded": {"episodes": [], "cast": [], "crew": []},
        }

        matches = parse_tvmaze_result(payload, expected_title="Mystery Incorporated", expected_media_type="电视剧")

        self.assertEqual(1, len(matches))
        self.assertEqual("tt12048470", matches[0].raw["provider_ids"]["imdb"])
        self.assertEqual("61855", matches[0].raw["provider_ids"]["tvmaze"])

    def test_public_metadata_prioritizes_verified_imdb_id_before_slower_discovery_providers(self):
        series = MediaItem(
            title="Prophets of Science Fiction",
            media_type="电视剧",
            year=2011,
            genres=["Science-Fiction"],
            directors=["Ridley Scott"],
            casts=["Ridley Scott"],
            summary="这是一段已经本地化的完整简介。",
            raw={
                "provider_ids": {"tvmaze": "1602", "imdb": "tt2091018"},
                "people_photos": {"Ridley Scott": "https://img.example/ridley.jpg"},
            },
        )
        imdb_detail = MediaItem(
            title="Prophets of Science Fiction",
            media_type="电视剧",
            year=2011,
            source="imdb_graphql",
            raw={
                "ratings": {"imdb": 7.9},
                "rating_votes": {"imdb": 726},
                "provider_ids": {"imdb": "tt2091018"},
                "stills": ["https://m.media-amazon.com/images/prophets-scene.jpg"],
            },
        )
        calls = []

        def imdb_provider(*_args, **_kwargs):
            calls.append("imdb")
            return [imdb_detail]

        def tmdb_provider(*_args, **_kwargs):
            calls.append("tmdb")
            return []

        def tvmaze_provider(*_args, **_kwargs):
            calls.append("tvmaze")
            return []

        with (
            mock.patch.object(douban_sources_module, "fetch_imdb_metadata_suggestions", side_effect=imdb_provider),
            mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", side_effect=tmdb_provider),
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", side_effect=tvmaze_provider),
        ):
            changed = enrich_public_metadata(series)

        self.assertTrue(changed)
        self.assertEqual(["imdb"], calls)
        self.assertEqual(7.9, series.raw["ratings"]["imdb"])

    def test_public_metadata_uses_imdb_to_fill_a_missing_verified_rating_and_stills(self):
        series = MediaItem(
            title="Mystery Incorporated",
            media_type="电视剧",
            year=2022,
            genres=["犯罪", "悬疑"],
            directors=["Dante Yore"],
            casts=["Dade Elza"],
            summary="一群年轻人调查一系列离奇事件。",
            raw={
                "provider_ids": {"tvmaze": "61855", "imdb": "tt12048470"},
                "people_photos": {
                    "Dante Yore": "https://img.example/director.jpg",
                    "Dade Elza": "https://img.example/actor.jpg",
                },
            },
        )
        imdb_detail = MediaItem(
            title="Mystery Incorporated",
            media_type="电视剧",
            year=2022,
            source="imdb_graphql",
            raw={
                "ratings": {"imdb": 7.4},
                "rating_votes": {"imdb": 684},
                "provider_ids": {"imdb": "tt12048470"},
                "stills": ["https://m.media-amazon.com/images/mystery-scene.jpg"],
            },
        )

        with (
            mock.patch.object(douban_sources_module, "fetch_imdb_metadata_suggestions", return_value=[imdb_detail], create=True) as imdb_provider,
            mock.patch.object(douban_sources_module, "fetch_themoviedb_metadata_suggestions", return_value=[]),
            mock.patch.object(douban_sources_module, "fetch_tvmaze_suggestions", return_value=[]),
        ):
            changed = enrich_public_metadata(series)

        self.assertTrue(changed)
        imdb_provider.assert_called()
        self.assertEqual(7.4, series.raw["ratings"]["imdb"])
        self.assertEqual(684, series.raw["rating_votes"]["imdb"])
        self.assertEqual(["https://m.media-amazon.com/images/mystery-scene.jpg"], series.raw["stills"])


if __name__ == "__main__":
    unittest.main()
