import unittest

from douban_recommender.eligibility import evaluate_eligibility, is_animated_series
from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.models import MediaItem


class AnimatedSeriesEligibilityTests(unittest.TestCase):
    def test_anime_movie_is_ineligible_for_anime_series_channel(self):
        item = MediaItem(
            title="千与千寻",
            media_type="动漫",
            raw={"format": "MOVIE"},
        )
        intent = RecommendationIntent(media_types=("动漫",))
        decision = evaluate_eligibility(item, set(), intent)
        self.assertFalse(decision.eligible)
        self.assertIn("not-animated-series", decision.reasons)

    def test_curated_anime_without_format_is_treated_as_series(self):
        item = MediaItem(title="奇巧计程车", media_type="动漫", raw={})
        self.assertTrue(is_animated_series(item))
        self.assertTrue(
            evaluate_eligibility(
                item,
                set(),
                RecommendationIntent(media_types=("动漫",)),
            ).eligible
        )

    def test_ova_requires_multiple_episodes(self):
        single = MediaItem(title="单集 OVA", media_type="动漫", raw={"format": "OVA", "episodes": 1})
        series = MediaItem(title="多集 OVA", media_type="动漫", raw={"format": "OVA", "episodes": 6})
        self.assertFalse(is_animated_series(single))
        self.assertTrue(is_animated_series(series))


class GeneralEligibilityTests(unittest.TestCase):
    def test_seen_item_is_rejected_by_identity_or_title(self):
        item = MediaItem(title="暗黑", media_type="电视剧", douban_id="70523")
        decision = evaluate_eligibility(
            item,
            {"douban:70523", "暗黑"},
            RecommendationIntent(media_types=("电视剧",)),
        )
        self.assertFalse(decision.eligible)
        self.assertIn("already-seen", decision.reasons)

    def test_requested_media_type_is_a_hard_gate(self):
        item = MediaItem(title="寄生虫", media_type="电影")
        decision = evaluate_eligibility(
            item,
            set(),
            RecommendationIntent(media_types=("电视剧",)),
        )
        self.assertFalse(decision.eligible)
        self.assertIn("media-type-mismatch", decision.reasons)

    def test_costume_series_is_penalized_not_removed_by_default(self):
        item = MediaItem(title="古装测试", media_type="电视剧", genres=["古装"])
        decision = evaluate_eligibility(
            item,
            set(),
            RecommendationIntent(media_types=("电视剧",)),
        )
        self.assertTrue(decision.eligible)
        self.assertTrue(
            any(signal.code == "costume-series" and signal.value < 0 for signal in decision.penalties)
        )

    def test_explicit_permanent_avoid_is_a_hard_gate(self):
        item = MediaItem(title="古装测试", media_type="电视剧", genres=["古装"])
        decision = evaluate_eligibility(
            item,
            set(),
            RecommendationIntent(
                media_types=("电视剧",),
                avoid=("古装",),
                permanent_avoid=("古装",),
            ),
        )
        self.assertFalse(decision.eligible)
        self.assertIn("explicit-avoid", decision.reasons)

    def test_quality_floor_rejects_known_low_rating_but_not_unknown_rating(self):
        intent = RecommendationIntent(quality_floor=8.5)
        low = evaluate_eligibility(
            MediaItem(title="低分", douban_rating=6.0, media_type="电影"),
            set(),
            intent,
        )
        unknown = evaluate_eligibility(
            MediaItem(title="未知", douban_rating=None, media_type="电影"),
            set(),
            intent,
        )
        self.assertFalse(low.eligible)
        self.assertTrue(unknown.eligible)
        self.assertTrue(any(signal.code == "rating-unknown" for signal in unknown.penalties))


if __name__ == "__main__":
    unittest.main()
