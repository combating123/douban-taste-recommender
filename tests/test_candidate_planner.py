import unittest

from douban_recommender.candidate_planner import build_candidate_plan
from douban_recommender.models import MediaItem
from douban_recommender.profiler import build_taste_profile


class CandidatePlannerTests(unittest.TestCase):
    def test_plan_contains_movie_series_and_anime_channels(self):
        profile = build_taste_profile([], like_terms="评分高，剧情好", dislike_terms="电视剧古装")

        plan = build_candidate_plan(
            profile,
            include_movies=True,
            include_series=True,
            include_anime=True,
            depth="deep",
        )
        channels = {query.channel for query in plan}
        tags = " ".join(query.tags for query in plan)

        self.assertIn("movie_quality", channels)
        self.assertIn("series_quality", channels)
        self.assertIn("anime_quality", channels)
        self.assertIn("电影", tags)
        self.assertIn("电视剧", tags)
        self.assertIn("动画", tags)
        self.assertTrue(any(query.start > 0 for query in plan))

    def test_plan_uses_wishlist_boost(self):
        profile = build_taste_profile([], like_terms="剧情", dislike_terms="")
        wishlist = [MediaItem(title="排球少年", media_type="动漫", tags=["想看", "运动"])]

        plan = build_candidate_plan(profile, wishlist=wishlist)

        self.assertTrue(any(query.channel == "wishlist_boost" for query in plan))


if __name__ == "__main__":
    unittest.main()
