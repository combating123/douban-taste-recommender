import importlib
import importlib.util
import unittest
from dataclasses import fields

from douban_recommender.media.providers.base import AssetQuery
from douban_recommender.media.providers.existing import (
    AniListProvider,
    WikidataProvider,
    providers_for,
)
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


class UrlCandidateTests(unittest.TestCase):
    def _module(self):
        module_name = "douban_recommender.media.url_candidates"
        self.assertIsNotNone(importlib.util.find_spec(module_name), "URL candidate module must exist")
        return importlib.import_module(module_name)

    def test_douban_candidate_rotates_img9_img1_img2_img3(self):
        candidates = self._module().image_url_candidates(
            "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg"
        )
        self.assertEqual(
            candidates,
            (
                "https://img9.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
                "https://img1.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
                "https://img2.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
                "https://img3.doubanio.com/view/photo/s_ratio_poster/public/p616779645.jpg",
            ),
        )

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

        self.assertTrue(douban["User-Agent"].startswith("Mozilla/5.0"))
        self.assertEqual(douban["Referer"], "https://movie.douban.com/")
        self.assertEqual(wikimedia["Referer"], "https://commons.wikimedia.org/")


class ExistingProviderAdapterTests(unittest.TestCase):
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
