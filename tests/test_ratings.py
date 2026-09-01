import unittest

from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.models import MediaItem
from douban_recommender.profiler import TasteProfile
from douban_recommender.ranking import rank_candidates
from douban_recommender.ratings import fused_rating


class MultiSourceRatingTests(unittest.TestCase):
    def test_movie_without_douban_rating_uses_imdb_and_tmdb_evidence(self):
        item = MediaItem(
            title="全网高口碑电影",
            media_type="电影",
            year=2025,
            vote_count=180000,
            genres=["剧情", "科幻"],
            summary="完整的故事简介。",
            raw={
                "ratings": {"imdb": 8.8, "tmdb": 8.5},
                "rating_votes": {"imdb": 150000, "tmdb": 30000},
            },
        )

        fused = fused_rating(item)

        self.assertGreaterEqual(fused.rating, 8.4)
        self.assertGreater(fused.confidence, 0.65)
        self.assertEqual(fused.providers, ("imdb", "tmdb"))

    def test_anime_uses_anilist_and_jikan_without_pretending_they_are_douban(self):
        item = MediaItem(
            title="全球动画剧集",
            media_type="动漫",
            vote_count=90000,
            raw={
                "ratings": {"anilist": 86, "jikan": 8.7, "tmdb": 8.1},
                "rating_votes": {"anilist_popularity": 60000, "jikan": 30000},
            },
        )

        fused = fused_rating(item)

        self.assertGreater(fused.rating, 8.4)
        self.assertIn("anilist", fused.providers)
        self.assertIn("jikan", fused.providers)
        self.assertIsNone(item.douban_rating)

    def test_quality_floor_and_ranking_accept_reliable_global_rating(self):
        global_item = MediaItem(
            title="在线发现佳作",
            douban_id="tmdb-movie-9001",
            media_type="电影",
            year=2025,
            vote_count=210000,
            genres=["剧情", "悬疑"],
            countries=["美国"],
            summary="一部人物和叙事都很扎实的新作。",
            raw={
                "ratings": {"imdb": 8.9, "tmdb": 8.6},
                "rating_votes": {"imdb": 180000, "tmdb": 30000},
            },
        )
        low_item = MediaItem(
            title="较低评分旧候选",
            douban_id="douban-low-1",
            media_type="电影",
            year=2024,
            douban_rating=8.0,
            vote_count=100000,
            genres=["剧情", "悬疑"],
            countries=["美国"],
            summary="资料完整但评分更低。",
        )

        ranked = rank_candidates(
            [],
            [low_item, global_item],
            TasteProfile(),
            RecommendationIntent(media_types=("电影",), quality_floor=8.5),
        )

        self.assertEqual([row.item.title for row in ranked], ["在线发现佳作"])
        signals = ranked[0].score_breakdown["signals"]
        self.assertTrue(any(signal["code"] == "multi-source-quality" for signal in signals))
        self.assertFalse(any(signal["code"] in {"rating-unknown", "quality-rating-missing"} for signal in signals))


if __name__ == "__main__":
    unittest.main()
