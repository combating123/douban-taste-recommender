import importlib
import importlib.util
import unittest
from dataclasses import fields
from unittest.mock import patch

from douban_recommender.media import public_people
from douban_recommender.media.providers.base import AssetQuery
from douban_recommender.media.providers.existing import (
    AniListProvider,
    WikidataProvider,
    providers_for,
)
from douban_recommender.identity_service import WorkIdentity, match_work_identity
from douban_recommender.models import MediaItem


class ProviderOrderTests(unittest.TestCase):
    def test_anime_series_poster_provider_order(self):
        names = [provider.name for provider in providers_for("poster", "动漫")]
        self.assertEqual(names[:3], ["inline", "anilist", "jikan"])
        self.assertLess(names.index("tmdb"), names.index("douban"))

    def test_series_people_provider_order(self):
        names = [provider.name for provider in providers_for("portrait", "电视剧")]
        self.assertEqual(names[:3], ["inline", "tvmaze", "wikidata"])

    def test_movie_poster_prefers_tmdb_before_public_fallbacks(self):
        names = [provider.name for provider in providers_for("poster", "电影")]
        self.assertEqual(names[:2], ["inline", "tmdb"])
        self.assertLess(names.index("wikidata"), names.index("douban"))


class PublicPeopleResolverTests(unittest.TestCase):
    def tearDown(self):
        public_people._CACHE.clear()
        public_people._NEGATIVE_CACHE.clear()

    def test_temporary_negative_cache_expires_and_allows_a_real_retry(self):
        public_people._CACHE.clear()
        public_people._NEGATIVE_CACHE.clear()
        calls = []
        with (
            patch.object(public_people, "build_url_opener", return_value=object()),
            patch.object(public_people, "_wikipedia_photo", side_effect=lambda *_args: calls.append("wiki") or ""),
            patch.object(public_people, "_tmdb_photo", side_effect=lambda *_args: calls.append("tmdb") or ""),
            patch.object(public_people, "_tvmaze_photo", side_effect=lambda *_args: calls.append("tvmaze") or ""),
            patch.object(public_people, "_jikan_photo", side_effect=lambda *_args: calls.append("jikan") or ""),
            patch.object(public_people.time, "monotonic", side_effect=[100.0, 110.0, 100.0 + public_people.NEGATIVE_CACHE_TTL_SECONDS + 1]),
        ):
            self.assertEqual(public_people.resolve_public_people_photos(["Retry Person"]), {})
            self.assertEqual(public_people.resolve_public_people_photos(["Retry Person"]), {})
            self.assertEqual(public_people.resolve_public_people_photos(["Retry Person"]), {})

        self.assertEqual(["tmdb", "wiki", "tvmaze", "jikan", "tmdb", "wiki", "tvmaze", "jikan"], calls)

    def test_contextual_miss_falls_back_through_strict_public_person_sources(self):
        calls = []
        expected = "https://upload.wikimedia.org/people/yu-won-pang.jpg"
        with (
            patch.object(public_people, "build_url_opener", return_value=object()),
            patch.object(public_people, "_tmdb_contextual_photo", side_effect=lambda *_args: calls.append("contextual") or ""),
            patch.object(public_people, "_tmdb_photo", side_effect=lambda *_args: calls.append("tmdb") or ""),
            patch.object(public_people, "_wikipedia_photo", side_effect=lambda *_args: calls.append("wikipedia") or expected),
            patch.object(public_people, "_tvmaze_photo", side_effect=lambda *_args: calls.append("tvmaze") or ""),
            patch.object(public_people, "_jikan_photo", side_effect=lambda *_args: calls.append("jikan") or ""),
        ):
            resolved = public_people.resolve_public_people_photos(
                ["Yu-Won Pang"],
                work_context=["DOTA: Dragon's Blood"],
            )

        self.assertEqual({"Yu-Won Pang": expected}, resolved)
        self.assertEqual(["contextual", "tmdb", "wikipedia"], calls)

    def test_tmdb_people_search_requires_exact_name_and_promotes_high_resolution_portrait(self):
        html = '''
        <img class="profile w-full" src="https://media.themoviedb.org/t/p/w90_and_h90_face/wrong.jpg" alt="李进荣">
        <img class="profile w-full" src="https://media.themoviedb.org/t/p/w90_and_h90_face/right.jpg" alt="李璟荣">
        '''

        class Response:
            def __enter__(self):
                return self

            def __exit__(self, *_args):
                return False

            def read(self):
                return html.encode("utf-8")

        class Opener:
            def open(self, request, timeout=0):
                self.url = request.full_url
                self.timeout = timeout
                return Response()

        opener = Opener()
        resolved = public_people._tmdb_photo("李璟荣", opener)

        self.assertIn("query=%E6%9D%8E%E7%92%9F%E8%8D%A3", opener.url)
        self.assertEqual("https://media.themoviedb.org/t/p/h632/right.jpg", resolved)

    def test_tmdb_contextual_people_search_requires_a_matching_known_work(self):
        page = '''
        <div class="item profile list_item">
          <img class="profile w-full" src="https://media.themoviedb.org/t/p/w90_and_h90_face/wrong.jpg" alt="Bernadette Janssen">
          <p class="name">Bernadette Janssen</p>
          <p class="sub"><a title="The Bad Orphan">The Bad Orphan</a></p>
        </div>
        '''

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return page.encode("utf-8")

        class Opener:
            def open(self, _request, timeout=0): return Response()

        self.assertEqual(
            "",
            public_people._tmdb_contextual_photo(
                "Bernadette Janssen",
                ("Asteroid Hunters",),
                Opener(),
            ),
        )

    def test_tmdb_contextual_people_search_accepts_exact_person_and_work(self):
        page = '''
        <div class="item profile list_item">
          <img class="profile w-full" src="https://media.themoviedb.org/t/p/w90_and_h90_face/right.jpg" alt="Tetsuro Araki">
          <p class="name">Tetsuro Araki</p>
          <p class="sub"><a title="Attack on Titan">Attack on Titan</a><a title="Death Note">Death Note</a></p>
        </div>
        '''

        class Response:
            def __enter__(self): return self
            def __exit__(self, *_args): return False
            def read(self): return page.encode("utf-8")

        class Opener:
            def open(self, _request, timeout=0): return Response()

        self.assertEqual(
            "https://media.themoviedb.org/t/p/h632/right.jpg",
            public_people._tmdb_contextual_photo(
                "Tetsuro Araki",
                ("Attack on Titan",),
                Opener(),
            ),
        )


class InlineProviderTests(unittest.TestCase):
    def _inline_provider_class(self):
        module_name = "douban_recommender.media.providers.inline"
        self.assertIsNotNone(importlib.util.find_spec(module_name), "inline provider module must exist")
        module = importlib.import_module(module_name)
        provider_class = getattr(module, "InlineProvider", None)
        self.assertIsNotNone(provider_class, "InlineProvider must be exported")
        return provider_class

    def test_asset_query_exposes_embedded_source_urls(self):
        field_names = {field.name for field in fields(AssetQuery)}
        self.assertIn("source_urls", field_names)

    def test_embedded_poster_candidate_carries_exact_work_identity(self):
        provider = self._inline_provider_class()()
        query = AssetQuery(
            kind="poster",
            title="奇巧计程车",
            year=2021,
            media_type="动漫",
            source_urls=("https://img9.doubanio.com/poster.jpg", "file:///tmp/nope.jpg"),
        )

        candidates = provider.search(query)

        self.assertEqual([candidate.url for candidate in candidates], ["https://img9.doubanio.com/poster.jpg"])
        self.assertEqual(candidates[0].work_identity.title, "奇巧计程车")
        self.assertEqual(candidates[0].work_identity.year, 2021)
        self.assertTrue(candidates[0].metadata["embedded"])

    def test_embedded_portrait_candidate_carries_visible_person_context(self):
        provider = self._inline_provider_class()()
        query = AssetQuery(
            kind="portrait",
            person_name="演员甲",
            occupations=("演员",),
            work_context=("作品甲",),
            source_urls=("https://upload.wikimedia.org/actor.jpg",),
        )

        candidates = provider.search(query)

        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].person_identity.name, "演员甲")
        self.assertEqual(candidates[0].person_identity.known_works, ("作品甲",))
        self.assertTrue(candidates[0].metadata["embedded"])

    def test_douban_default_artwork_is_not_accepted_as_a_real_poster(self):
        provider = self._inline_provider_class()()
        query = AssetQuery(
            kind="poster",
            title="未验证的新条目",
            media_type="电影",
            source_urls=(
                "https://img2.doubanio.com/cuphead/movie-static/pics/movie_default_large.png",
                "https://img2.doubanio.com/cuphead/movie-static/pics/movie_default_medium.png",
                "https://img2.doubanio.com/cuphead/movie-static/pics/movie_default_small.png",
                "https://img2.doubanio.com/cuphead/movie-static/pics/tv_default_large.png",
                "https://img2.doubanio.com/cuphead/movie-static/pics/tv_default_medium.png",
                "https://img2.doubanio.com/cuphead/movie-static/pics/tv_default_small.png",
            ),
        )

        self.assertEqual(provider.search(query), [])


class UrlCandidateTests(unittest.TestCase):
    def _module(self):
        module_name = "douban_recommender.media.url_candidates"
        self.assertIsNotNone(importlib.util.find_spec(module_name), "URL candidate module must exist")
        return importlib.import_module(module_name)

    def test_douban_candidate_rotates_img9_img1_img2_img3(self):
        candidates = self._module().image_url_candidates(
            "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg"
        )
        self.assertEqual(candidates[0], "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg")
        self.assertIn("https://img2.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg", candidates)
        self.assertIn("https://img3.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg", candidates)
        self.assertEqual(candidates[-1], "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg")

    def test_default_artwork_never_generates_download_candidates(self):
        candidates = self._module().image_url_candidates(
            "https://img2.doubanio.com/cuphead/movie-static/pics/movie_default_medium.png"
        )
        self.assertEqual(candidates, ())

    def test_wikimedia_candidate_adds_practical_thumbnail_variants(self):
        candidates = self._module().image_url_candidates(
            "https://upload.wikimedia.org/wikipedia/commons/8/81/Masami_Nagasawa.jpg"
        )
        self.assertEqual(candidates[0], "https://upload.wikimedia.org/wikipedia/commons/8/81/Masami_Nagasawa.jpg")
        self.assertIn(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/8/81/Masami_Nagasawa.jpg/640px-Masami_Nagasawa.jpg",
            candidates,
        )
        self.assertIn(
            "https://upload.wikimedia.org/wikipedia/commons/thumb/8/81/Masami_Nagasawa.jpg/330px-Masami_Nagasawa.jpg",
            candidates,
        )

    def test_image_headers_are_source_specific_and_browser_like(self):
        headers_for = self._module().image_request_headers
        douban = headers_for("https://img9.doubanio.com/poster.jpg")
        wikimedia = headers_for("https://upload.wikimedia.org/actor.jpg")
        tmdb_person = headers_for("https://media.themoviedb.org/t/p/h632/person.jpg")

        self.assertTrue(douban["User-Agent"].startswith("Mozilla/5.0"))
        self.assertEqual(douban["Referer"], "https://movie.douban.com/")
        self.assertEqual(wikimedia["Referer"], "https://commons.wikimedia.org/")
        self.assertEqual(tmdb_person["Referer"], "https://www.themoviedb.org/")


class ExistingProviderAdapterTests(unittest.TestCase):
    def test_localized_tmdb_result_uses_exact_original_title_slug_as_identity_evidence(self):
        def searcher(title, media_type=""):
            if title == "Castlevania":
                return []
            return [
                MediaItem(
                    title="\u6076\u9b54\u57ce",
                    media_type="\u52a8\u6f2b",
                    year=2017,
                    url="https://www.themoviedb.org/tv/71024-castlevania",
                    cover="https://image.tmdb.org/t/p/w500/castlevania.jpg",
                )
            ]

        query = AssetQuery(
            kind="poster",
            title="\u6076\u9b54\u57ce",
            original_titles=("Castlevania",),
            media_type="\u52a8\u6f2b",
        )
        candidate = AniListProvider(searcher=searcher).search(query)[0]

        self.assertIn("Castlevania", candidate.work_identity.original_titles)
        self.assertTrue(
            match_work_identity(
                WorkIdentity(title=query.title, original_titles=query.original_titles, media_type=query.media_type),
                candidate.work_identity,
            ).accepted
        )

    def test_provider_searches_registered_original_titles_and_preserves_alias_evidence(self):
        calls = []

        def searcher(title, media_type=""):
            calls.append((title, media_type))
            if title != "Castlevania":
                return []
            return [
                MediaItem(
                    title="Castlevania",
                    media_type="\u52a8\u6f2b",
                    cover="https://image.tmdb.org/t/p/w500/castlevania.jpg",
                )
            ]

        query = AssetQuery(
            kind="poster",
            title="\u6076\u9b54\u57ce",
            original_titles=("Castlevania",),
            media_type="\u52a8\u6f2b",
        )
        candidates = AniListProvider(searcher=searcher).search(query)

        self.assertEqual([title for title, _ in calls], ["Castlevania", "\u6076\u9b54\u57ce"])
        self.assertEqual(len(candidates), 1)
        self.assertIn("Castlevania", candidates[0].work_identity.original_titles)
        decision = match_work_identity(
            WorkIdentity(title="\u6076\u9b54\u57ce", original_titles=("Castlevania",), media_type="\u52a8\u6f2b"),
            candidates[0].work_identity,
        )
        self.assertTrue(decision.accepted)

    def test_anilist_adapter_preserves_identity_evidence(self):
        item = MediaItem(
            title="奇巧计程车",
            year=2021,
            media_type="动漫",
            countries=["日本"],
            directors=["木下麦"],
            douban_id="anilist-46102",
            cover="https://s4.anilist.co/file/anilistcdn/media/anime/cover/large/example.jpg",
            source="anilist_api",
            raw={
                "format": "TV",
                "episodes": 13,
                "title": {"romaji": "Odd Taxi", "english": "ODDTAXI", "native": "オッドタクシー"},
            },
        )
        provider = AniListProvider(searcher=lambda title, media_type="": [item])
        candidates = provider.search(
            AssetQuery(kind="poster", title="奇巧计程车", year=2021, media_type="动漫")
        )
        self.assertEqual(len(candidates), 1)
        candidate = candidates[0]
        self.assertEqual(candidate.source, "anilist")
        self.assertEqual(candidate.work_identity.episode_count, 13)
        self.assertIn("ODDTAXI", candidate.work_identity.original_titles)
        self.assertEqual(candidate.work_identity.provider_ids["anilist"], "46102")

    def test_wikidata_portrait_adapter_uses_visible_person_and_work_context(self):
        provider = WikidataProvider(
            people_resolver=lambda names: {"演员甲": "https://upload.wikimedia.org/actor.jpg"}
        )
        candidates = provider.search(
            AssetQuery(
                kind="portrait",
                person_name="演员甲",
                work_context=("作品甲",),
                occupations=("演员",),
            )
        )
        self.assertEqual(len(candidates), 1)
        self.assertEqual(candidates[0].person_identity.name, "演员甲")
        self.assertEqual(candidates[0].person_identity.known_works, ("作品甲",))
        self.assertEqual(candidates[0].url, "https://upload.wikimedia.org/actor.jpg")

    def test_wikidata_portrait_adapter_has_a_real_default_public_resolver(self):
        provider = WikidataProvider()
        self.assertTrue(callable(provider.people_resolver))
        self.assertEqual(provider.people_resolver.__name__, "resolve_public_people_photos")

    def test_provider_drops_rows_without_image_url(self):
        provider = AniListProvider(
            searcher=lambda title, media_type="": [
                MediaItem(title=title, media_type="动漫", year=2021, cover="")
            ]
        )
        self.assertEqual(
            provider.search(AssetQuery(kind="poster", title="无图", media_type="动漫")),
            [],
        )


if __name__ == "__main__":
    unittest.main()
