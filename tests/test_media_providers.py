import unittest

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
        self.assertEqual(names[:2], ["anilist", "jikan"])
        self.assertLess(names.index("tmdb"), names.index("douban"))

    def test_series_people_provider_order(self):
        names = [provider.name for provider in providers_for("portrait", "电视剧")]
        self.assertEqual(names[:2], ["tvmaze", "wikidata"])

    def test_movie_poster_prefers_tmdb_before_public_fallbacks(self):
        names = [provider.name for provider in providers_for("poster", "电影")]
        self.assertEqual(names[0], "tmdb")
        self.assertLess(names.index("wikidata"), names.index("douban"))


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
