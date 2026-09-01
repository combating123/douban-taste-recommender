import json
import os
import threading
import time
import unittest
from unittest.mock import patch

from douban_recommender.global_discovery import (
    GlobalDiscoveryConfig,
    _anime_title,
    _apple_movie_item,
    _discover_tvmaze,
    _tvmaze_item,
    discover_global_candidates,
)
from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.profiler import TasteProfile


class FixtureTransport:
    def __init__(self):
        self.urls = []

    def __call__(self, request, timeout=8):
        url = request.full_url
        self.urls.append(url)
        if "api.themoviedb.org/3/trending/movie" in url:
            return self._json({
                "results": [{
                    "id": 101,
                    "title": "沙丘：第二部",
                    "original_title": "Dune: Part Two",
                    "release_date": "2024-03-01",
                    "genre_ids": [18, 878, 12],
                    "overview": "保罗继续踏上复仇与选择命运的旅程。",
                    "poster_path": "/dune.jpg",
                    "backdrop_path": "/dune-wide.jpg",
                    "vote_average": 8.3,
                    "vote_count": 6200,
                    "popularity": 900.0,
                    "original_language": "en",
                }],
            })
        if "api.themoviedb.org/3/discover/movie" in url:
            return self._json({"results": []})
        if "api.themoviedb.org/3/trending/tv" in url:
            return self._json({"results": [{
                "id": 202,
                "name": "幕府将军",
                "original_name": "Shogun",
                "first_air_date": "2024-02-27",
                "genre_ids": [18],
                "overview": "权力与文化冲突交织的历史剧集。",
                "poster_path": "/shogun.jpg",
                "backdrop_path": "/shogun-wide.jpg",
                "vote_average": 8.6,
                "vote_count": 1900,
                "popularity": 500.0,
                "origin_country": ["US"],
                "original_language": "en",
            }]})
        if "api.themoviedb.org/3/discover/tv" in url:
            return self._json({"results": []})
        if "api.tvmaze.com/search/shows" in url:
            return self._json([{"score": 0.95, "show": {
                "id": 303,
                "name": "Severance",
                "premiered": "2022-02-18",
                "genres": ["Drama", "Science-Fiction", "Thriller"],
                "summary": "<p>办公室记忆被切开的悬疑故事。</p>",
                "image": {"original": "https://img.example/severance.jpg"},
                "rating": {"average": 8.4},
                "weight": 97,
                "language": "English",
                "network": {"country": {"code": "US", "name": "United States"}},
                "url": "https://www.tvmaze.com/shows/303/severance",
            }}])
        if "api.tvmaze.com/schedule" in url:
            return self._json([])
        if "graphql.anilist.co" in url:
            return self._json({"data": {"Page": {"media": [{
                "id": 404,
                "title": {"romaji": "Frieren", "english": "Frieren", "native": "葬送のフリーレン"},
                "synonyms": ["葬送的芙莉蓮"],
                "format": "TV",
                "seasonYear": 2023,
                "genres": ["Adventure", "Drama", "Fantasy"],
                "description": "<p>精灵魔法使重新理解时间与羁绊。</p>",
                "coverImage": {"extraLarge": "https://img.example/frieren.jpg"},
                "bannerImage": "https://img.example/frieren-wide.jpg",
                "siteUrl": "https://anilist.co/anime/404",
                "averageScore": 91,
                "popularity": 200000,
                "episodes": 28,
                "countryOfOrigin": "JP",
            }, {
                "id": 405,
                "title": {"romaji": "Anime Movie", "english": "Anime Movie", "native": "动画电影"},
                "format": "MOVIE",
                "seasonYear": 2024,
                "coverImage": {"extraLarge": "https://img.example/movie.jpg"},
                "averageScore": 88,
            }]}}})
        if "api.jikan.moe/v4/top/anime" in url:
            return self._json({"data": [{
                "mal_id": 505,
                "title": "Arcane Season 2",
                "title_english": "Arcane Season 2",
                "type": "TV",
                "year": 2024,
                "genres": [{"name": "Action"}, {"name": "Drama"}],
                "synopsis": "城市与姐妹命运再次交错。",
                "images": {"jpg": {"large_image_url": "https://img.example/arcane.jpg"}},
                "trailer": {"images": {"maximum_image_url": "https://img.example/arcane-wide.jpg"}},
                "url": "https://myanimelist.net/anime/505",
                "score": 8.9,
                "scored_by": 120000,
                "members": 500000,
                "episodes": 9,
            }]})
        if "api.jikan.moe/v4/seasons/now" in url:
            return self._json({"data": []})
        raise AssertionError(f"unexpected URL: {url}")

    @staticmethod
    def _json(value):
        return json.dumps(value, ensure_ascii=False).encode("utf-8")


class GlobalDiscoveryTests(unittest.TestCase):
    def test_config_reads_environment_without_exposing_secret_values(self):
        with patch.dict(os.environ, {
            "CINESCOPE_TMDB_API_KEY": "tmdb-private-value",
            "CINESCOPE_OMDB_API_KEY": "omdb-private-value",
        }, clear=False):
            config = GlobalDiscoveryConfig.from_payload({"enabled": True})

        self.assertEqual(config.tmdb_api_key, "tmdb-private-value")
        self.assertEqual(config.omdb_api_key, "omdb-private-value")
        summary = config.public_summary()
        self.assertTrue(summary["tmdb_configured"])
        self.assertTrue(summary["omdb_configured"])
        self.assertNotIn("tmdb-private-value", json.dumps(summary))
        self.assertNotIn("omdb-private-value", json.dumps(summary))

    def test_discovers_multi_source_candidates_and_keeps_anime_to_series(self):
        transport = FixtureTransport()
        profile = TasteProfile()
        profile.positive["genre:剧情"] = 5.0
        intent = RecommendationIntent(
            media_types=("电影", "电视剧", "动漫"),
            genres=("剧情", "科幻"),
            free_text="想看近期高口碑、人物关系扎实的作品",
        )
        config = GlobalDiscoveryConfig(
            tmdb_api_key="tmdb-secret-value",
            enable_apple_movies=False,
            max_per_source=12,
            max_total=60,
        )

        report = discover_global_candidates(
            intent,
            profile,
            include_movies=True,
            include_series=True,
            include_anime=True,
            config=config,
            transport=transport,
            now=lambda: 1_720_000_000.0,
        )

        by_title = {item.title: item for item in report.items}
        self.assertIn("沙丘：第二部", by_title)
        self.assertIn("幕府将军", by_title)
        self.assertIn("Severance", by_title)
        self.assertIn("葬送的芙莉莲", by_title)
        self.assertIn("英雄联盟：双城之战 第2季", by_title)
        self.assertNotIn("Anime Movie", by_title)

        dune = by_title["沙丘：第二部"]
        self.assertEqual(dune.media_type, "电影")
        self.assertEqual(dune.genres[:2], ["剧情", "科幻"])
        self.assertEqual(dune.raw["ratings"]["tmdb"], 8.3)
        self.assertEqual(dune.raw["backdrop"], "https://image.tmdb.org/t/p/w1280/dune-wide.jpg")

        frieren = by_title["葬送的芙莉莲"]
        self.assertEqual(frieren.media_type, "动漫")
        self.assertEqual(frieren.raw["ratings"]["anilist"], 9.1)
        self.assertEqual(frieren.raw["episodes"], 28)

        severance = by_title["Severance"]
        self.assertEqual(severance.media_type, "电视剧")
        self.assertEqual(severance.raw["ratings"]["tvmaze"], 8.4)
        self.assertIn("科幻", severance.genres)

        self.assertGreaterEqual(report.source_counts["tmdb"], 2)
        self.assertGreaterEqual(report.source_counts["tvmaze"], 1)
        self.assertGreaterEqual(report.source_counts["anilist"], 1)
        self.assertGreaterEqual(report.source_counts["jikan"], 1)
        self.assertEqual(report.config["tmdb_configured"], True)
        self.assertNotIn("tmdb-secret-value", json.dumps(report.to_dict()))

    def test_tvmaze_documentary_type_is_preserved_as_a_normalized_genre(self):
        item = _tvmaze_item(
            {
                "score": 0.98,
                "show": {
                    "id": 83363,
                    "name": "Science Fiction in the Atomic Age",
                    "type": "Documentary",
                    "premiered": "2025-04-03",
                    "genres": ["History"],
                    "image": {"original": "https://img.example/atomic-age.jpg"},
                },
            },
            include_series=True,
            include_anime=True,
            now=1_720_000_000.0,
        )

        self.assertIsNotNone(item)
        self.assertEqual("\u7535\u89c6\u5267", item.media_type)
        self.assertIn("\u7eaa\u5f55\u7247", item.genres)
        self.assertEqual("Documentary", item.raw["provider_format"])

    def test_tvmaze_fetches_keyword_searches_and_current_schedule_concurrently(self):
        barrier = threading.Barrier(4, timeout=1.0)
        calls = []
        lock = threading.Lock()

        def transport(request, timeout=8):
            with lock:
                calls.append(request.full_url)
            barrier.wait()
            return FixtureTransport._json([])

        items = _discover_tvmaze(
            ("drama", "mystery", "science fiction"),
            GlobalDiscoveryConfig(
                enable_tmdb=False,
                enable_omdb=False,
                enable_anilist=False,
                enable_jikan=False,
                enable_apple_movies=False,
                include_current=True,
                max_per_source=8,
            ),
            transport,
            include_series=True,
            include_anime=True,
            now=1_788_067_200.0,
        )

        self.assertEqual([], items)
        self.assertEqual(4, len(calls))
        self.assertEqual(3, sum("search/shows" in url for url in calls))
        self.assertEqual(1, sum("schedule/web" in url for url in calls))

    def test_source_elapsed_time_covers_the_actual_provider_request(self):
        def transport(request, timeout=8):
            time.sleep(0.05)
            return FixtureTransport._json({"feed": {"entry": []}})

        report = discover_global_candidates(
            RecommendationIntent(media_types=("电影",)),
            TasteProfile(),
            include_movies=True,
            include_series=False,
            include_anime=False,
            config=GlobalDiscoveryConfig(
                enable_tmdb=False,
                enable_omdb=False,
                enable_tvmaze=False,
                enable_anilist=False,
                enable_jikan=False,
                enable_apple_movies=True,
                max_per_source=8,
            ),
            transport=transport,
            now=lambda: 1_788_067_200.0,
        )

        self.assertGreaterEqual(report.source_status["apple_movies"]["elapsed_ms"], 40.0)

    def test_apple_top_movies_provides_keyless_chinese_movie_discovery(self):
        row = {
            "im:name": {"label": "极限返航 - Project Hail Mary"},
            "im:image": [
                {"label": "https://is1-ssl.mzstatic.com/image/thumb/movie.png/113x170bb.png", "attributes": {"height": "170"}},
            ],
            "summary": {"label": "一名宇航员在深空中承担拯救地球的任务。"},
            "id": {"label": "https://itunes.apple.com/tw/movie/id123", "attributes": {"im:id": "123"}},
            "im:artist": {"label": "Phil Lord"},
            "category": {"attributes": {"term": "Science Fiction", "label": "科幻片"}},
            "im:releaseDate": {"label": "2026-03-20T00:00:00-07:00"},
            "link": [{"attributes": {"rel": "alternate", "href": "https://itunes.apple.com/tw/movie/id123"}}],
        }
        item = _apple_movie_item(row, rank=2, now=1_788_067_200.0, storefront="tw")

        self.assertIsNotNone(item)
        self.assertEqual("极限返航", item.title)
        self.assertEqual("电影", item.media_type)
        self.assertEqual(2026, item.year)
        self.assertEqual(["科幻"], item.genres)
        self.assertTrue(item.cover.endswith("/600x900bb.jpg"))
        self.assertEqual("2026-03-20", item.raw["release_date"])
        self.assertEqual("apple_movies", item.raw["discovery_sources"][0])
        self.assertEqual("tw", item.raw["storefront"])

        def transport(request, timeout=8):
            self.assertIn("itunes.apple.com/tw/rss/topmovies", request.full_url)
            return json.dumps({
                "feed": {
                    "entry": [
                        row,
                        {"im:name": {"label": "English Only"}, "im:image": row["im:image"]},
                    ]
                }
            }, ensure_ascii=False).encode("utf-8")

        report = discover_global_candidates(
            RecommendationIntent(media_types=("电影",)),
            TasteProfile(),
            include_movies=True,
            include_series=False,
            include_anime=False,
            config=GlobalDiscoveryConfig(
                enable_tmdb=False,
                enable_omdb=False,
                enable_tvmaze=False,
                enable_anilist=False,
                enable_jikan=False,
                enable_apple_movies=True,
                max_per_source=8,
            ),
            transport=transport,
            now=lambda: 1_788_067_200.0,
        )

        self.assertEqual("complete", report.status)
        self.assertEqual(1, report.source_counts["apple_movies"])
        self.assertEqual(["极限返航"], [candidate.title for candidate in report.items])

    def test_apple_movie_localizes_traditional_text_and_english_genre(self):
        row = {
            "im:name": {"label": "穿著Prada的惡魔2"},
            "im:image": [
                {"label": "https://is1-ssl.mzstatic.com/image/thumb/prada.png/113x170bb.png", "attributes": {"height": "170"}},
            ],
            "summary": {"label": "時隔多年，她們帶著全新的選擇回到時尚產業。"},
            "id": {"label": "https://itunes.apple.com/tw/movie/id456", "attributes": {"im:id": "456"}},
            "category": {"attributes": {"term": "Action & Adventure"}},
            "im:releaseDate": {"label": "2026-05-01T00:00:00-07:00"},
        }

        item = _apple_movie_item(row, rank=1, now=1_788_067_200.0, storefront="tw")

        self.assertIsNotNone(item)
        self.assertEqual("穿着Prada的恶魔2", item.title)
        self.assertEqual(["动作 / 冒险"], item.genres)
        self.assertEqual("时隔多年，她们带着全新的选择回到时尚产业。", item.summary)

    def test_anime_title_prefers_simplified_chinese_alias_over_japanese_native_title(self):
        title, aliases = _anime_title({
            "id": 21,
            "title": {"romaji": "ONE PIECE", "english": "ONE PIECE", "native": "ONE PIECE"},
            "synonyms": ["ワンピース", "海賊王"],
            "countryOfOrigin": "JP",
        })

        self.assertEqual("海贼王", title)
        self.assertIn("ワンピース", aliases)

    def test_anime_title_uses_verified_curated_localization_and_preserves_season(self):
        title, aliases = _anime_title({
            "mal_id": 505,
            "title": "Arcane Season 2",
            "title_english": "Arcane Season 2",
            "title_japanese": "Arcane Season 2",
        })

        self.assertEqual("英雄联盟：双城之战 第2季", title)
        self.assertIn("Arcane Season 2", aliases)

    def test_anime_title_without_reliable_chinese_localization_is_hidden(self):
        title, aliases = _anime_title({
            "id": 999999,
            "title": {
                "romaji": "Unmapped New Anime",
                "english": "Unmapped New Anime",
                "native": "新作のアニメ",
            },
            "synonyms": ["อนิเมะใหม่"],
            "countryOfOrigin": "JP",
        })

        self.assertEqual("", title)
        self.assertIn("新作のアニメ", aliases)

    def test_disabled_discovery_does_not_call_network(self):
        transport = FixtureTransport()
        report = discover_global_candidates(
            RecommendationIntent(),
            TasteProfile(),
            config=GlobalDiscoveryConfig(enabled=False),
            transport=transport,
        )
        self.assertEqual(report.items, [])
        self.assertEqual(transport.urls, [])
        self.assertEqual(report.status, "disabled")

    def test_omdb_is_a_real_candidate_source_for_movies_and_series(self):
        calls = []

        def transport(request, timeout=8):
            url = request.full_url
            calls.append(url)
            if "&s=" in url and "type=movie" in url:
                return FixtureTransport._json({
                    "Search": [{
                        "Title": "The Global Mystery",
                        "Year": "2025",
                        "imdbID": "tt9000001",
                        "Type": "movie",
                        "Poster": "https://img.example/global-mystery.jpg",
                    }],
                    "Response": "True",
                })
            if "&s=" in url and "type=series" in url:
                return FixtureTransport._json({
                    "Search": [{
                        "Title": "Worldwide Animation",
                        "Year": "2024–",
                        "imdbID": "tt9000002",
                        "Type": "series",
                        "Poster": "https://img.example/worldwide-animation.jpg",
                    }],
                    "Response": "True",
                })
            if "i=tt9000001" in url:
                return FixtureTransport._json({
                    "Title": "The Global Mystery",
                    "Year": "2025",
                    "imdbID": "tt9000001",
                    "Type": "movie",
                    "Genre": "Drama, Mystery",
                    "Plot": "A layered missing-person mystery.",
                    "Poster": "https://img.example/global-mystery.jpg",
                    "imdbRating": "8.7",
                    "imdbVotes": "145,000",
                    "Director": "Director One",
                    "Actors": "Actor One, Actor Two",
                    "Country": "United States",
                    "Language": "English",
                    "Runtime": "126 min",
                    "Response": "True",
                })
            if "i=tt9000002" in url:
                return FixtureTransport._json({
                    "Title": "Worldwide Animation",
                    "Year": "2024–",
                    "imdbID": "tt9000002",
                    "Type": "series",
                    "Genre": "Animation, Drama, Science Fiction",
                    "Plot": "An international animated serial drama.",
                    "Poster": "https://img.example/worldwide-animation.jpg",
                    "imdbRating": "8.6",
                    "imdbVotes": "82,000",
                    "Country": "France, United States",
                    "Language": "French, English",
                    "Runtime": "24 min",
                    "totalSeasons": "2",
                    "Response": "True",
                })
            raise AssertionError(f"unexpected URL: {url}")

        report = discover_global_candidates(
            RecommendationIntent(genres=("悬疑",)),
            TasteProfile(),
            include_movies=True,
            include_series=True,
            include_anime=True,
            config=GlobalDiscoveryConfig(
                omdb_api_key="omdb-secret",
                enable_tmdb=False,
                enable_tvmaze=False,
                enable_anilist=False,
                enable_jikan=False,
                enable_apple_movies=False,
                max_per_source=8,
            ),
            transport=transport,
            now=lambda: 1_720_000_000.0,
        )

        by_title = {item.title: item for item in report.items}
        self.assertEqual(by_title["The Global Mystery"].media_type, "电影")
        self.assertEqual(by_title["Worldwide Animation"].media_type, "动漫")
        self.assertEqual(by_title["The Global Mystery"].raw["ratings"]["imdb"], 8.7)
        self.assertEqual(by_title["The Global Mystery"].raw["runtime"], 126)
        self.assertEqual(by_title["Worldwide Animation"].raw["episode_runtime"], 24)
        self.assertEqual(report.source_counts["omdb"], 2)
        self.assertNotIn("omdb-secret", json.dumps(report.to_dict()))
        self.assertTrue(any("apikey=omdb-secret" in url for url in calls))


if __name__ == "__main__":
    unittest.main()
