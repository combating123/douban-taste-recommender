import unittest
import re

from douban_recommender.models import (
    MediaItem,
    canonical_media_type,
    is_safe_route_segment,
    recommendation_identity_tokens,
    recommendation_item_key,
)


class MediaModelCanonicalizationTests(unittest.TestCase):
    def test_public_media_type_canonicalizer_normalizes_supported_aliases(self):
        aliases = {
            "movie": "电影",
            "film": "电影",
            "电影": "电影",
            "tv": "电视剧",
            "series": "电视剧",
            "电视剧": "电视剧",
            "剧集": "电视剧",
            "anime": "动漫",
            "animation": "动漫",
            "动画": "动漫",
            "动漫": "动漫",
            "动画剧集": "动漫",
        }

        for raw, expected in aliases.items():
            with self.subTest(raw=raw):
                self.assertEqual(canonical_media_type(raw), expected)
                self.assertEqual(MediaItem(title="测试", media_type=raw).media_type, expected)

    def test_identity_uses_recommendation_item_key_and_preserves_year_for_title_fallback(self):
        first = MediaItem(title="同名作品", year=1999, media_type="movie")
        second = MediaItem(title="同名作品", year=2024, media_type="电影")
        without_year = MediaItem(title="同名作品", media_type="电影")

        self.assertEqual(first.identity, recommendation_item_key(first))
        self.assertEqual(second.identity, recommendation_item_key(second))
        self.assertNotEqual(first.identity, second.identity)
        self.assertNotEqual(first.identity, without_year.identity)

    def test_identity_tokens_include_shared_provider_ids_across_catalog_sources(self):
        first = MediaItem(
            title="科幻真史",
            year=2014,
            media_type="电视剧",
            douban_id="tvmaze-3415",
            raw={"provider_ids": {"douban": "25851561", "imdb": "tt4136828"}},
        )
        second = MediaItem(
            title="The Real History of Science Fiction",
            year=2014,
            media_type="电视剧",
            douban_id="tvmaze-11054",
            raw={"provider_ids": {"douban": "25851561", "imdb": "tt4136828"}},
        )

        first_tokens = set(recommendation_identity_tokens(first))
        second_tokens = set(recommendation_identity_tokens(second))

        self.assertIn("provider:douban:25851561", first_tokens)
        self.assertIn("provider:imdb:tt4136828", first_tokens)
        self.assertIn("provider:douban:25851561", second_tokens)
        self.assertTrue(first_tokens & second_tokens)

    def test_identity_tokens_include_single_original_title_alias(self):
        item = MediaItem(
            title="科幻真史",
            year=2014,
            media_type="电视剧",
            raw={"original_title": "The Real History of Science Fiction"},
        )

        self.assertIn(
            "title-year-type:therealhistoryofsciencefiction|2014|电视剧",
            recommendation_identity_tokens(item),
        )

    def test_non_numeric_external_identifier_uses_stable_url_safe_opaque_key(self):
        unsafe = "provider/..\\title?token=secret#fragment%2F"
        first = MediaItem(title="Unsafe external", year=2024, media_type="movie", douban_id=unsafe)
        second = MediaItem(title="Renamed external", year=1999, media_type="series", douban_id=unsafe)

        first_key = recommendation_item_key(first)
        second_key = recommendation_item_key(second)

        self.assertEqual(first_key, second_key)
        self.assertRegex(first_key, r"^external:[0-9a-f]{24}$")
        self.assertFalse(re.search(r"[/\\?#%]", first_key))
        self.assertEqual(
            recommendation_item_key(MediaItem(title="Numeric", douban_id="35280649")),
            "douban:35280649",
        )

    def test_url_safe_external_identifier_preserves_legacy_key(self):
        item = MediaItem(title="Legacy safe external", douban_id="movie-1")

        self.assertEqual(recommendation_item_key(item), "external:movie-1")

    def test_route_segment_validation_matches_external_key_preservation(self):
        self.assertTrue(is_safe_route_segment("external:movie-1"))
        self.assertTrue(is_safe_route_segment("douban:35280649"))

        for unsafe in ("foo..bar", "...", ".", "..", "a/b", "a\\b", "a?b", "a#b", "a%b", "a\x00b"):
            with self.subTest(unsafe=unsafe):
                self.assertFalse(is_safe_route_segment(unsafe))
                key = recommendation_item_key(MediaItem(title="Unsafe", douban_id=unsafe))
                self.assertRegex(key, r"^external:[0-9a-f]{24}$")
                self.assertTrue(is_safe_route_segment(key))


if __name__ == "__main__":
    unittest.main()
