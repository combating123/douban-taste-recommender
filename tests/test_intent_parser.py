import unittest

from douban_recommender.intent_parser import (
    RecommendationIntent,
    intent_to_chips,
    parse_recommendation_intent,
)


class RecommendationIntentParserTests(unittest.TestCase):
    def test_parses_anime_runtime_mood_and_avoidance(self):
        intent = parse_recommendation_intent(
            "今晚想看聪明、悬疑、群像，但不要太压抑的动画剧集，最好一集30分钟以内"
        )
        self.assertEqual(intent.media_types, ("动漫",))
        self.assertEqual(intent.episode_runtime_max, 30)
        self.assertIn("悬疑", intent.genres)
        self.assertIn("群像", intent.moods)
        self.assertIn("聪明叙事", intent.moods)
        self.assertIn("过度压抑", intent.avoid)

    def test_not_tonight_is_session_only(self):
        intent = parse_recommendation_intent("今晚不想看慢热的")
        self.assertIn("慢热", intent.session_only_adjustments)
        self.assertNotIn("慢热", intent.permanent_avoid)

    def test_permanent_avoid_requires_explicit_long_term_language(self):
        intent = parse_recommendation_intent("以后电视剧永久不要古装和注水剧")
        self.assertEqual(intent.media_types, ("电视剧",))
        self.assertIn("古装", intent.permanent_avoid)
        self.assertIn("注水", intent.permanent_avoid)

    def test_parses_quality_year_country_and_feature_runtime(self):
        intent = parse_recommendation_intent(
            "想看2015年以后的韩国电影，评分至少8.5，两个小时以内"
        )
        self.assertEqual(intent.media_types, ("电影",))
        self.assertEqual(intent.countries, ("韩国",))
        self.assertEqual(intent.year_min, 2015)
        self.assertEqual(intent.quality_floor, 8.5)
        self.assertEqual(intent.runtime_max, 120)

    def test_base_intent_is_merged_without_losing_existing_media(self):
        base = RecommendationIntent(media_types=("电影",), exploration_level=0.2)
        intent = parse_recommendation_intent("更轻松一点", base=base)
        self.assertEqual(intent.media_types, ("电影",))
        self.assertIn("轻松", intent.moods)
        self.assertEqual(intent.exploration_level, 0.2)

    def test_intent_round_trip_and_chips_are_stable(self):
        original = parse_recommendation_intent("悬疑动画剧集，一集25分钟以内，不要太压抑")
        restored = RecommendationIntent.from_dict(original.to_dict())
        self.assertEqual(restored, original)
        labels = [chip.label for chip in intent_to_chips(restored)]
        self.assertIn("动画剧集", labels)
        self.assertIn("单集 ≤ 25 分钟", labels)
        self.assertIn("避开：过度压抑", labels)

    def test_unknown_language_is_preserved_as_free_text(self):
        intent = parse_recommendation_intent("想看有雨夜霓虹感、城市孤独气质的作品")
        self.assertIn("雨夜霓虹", intent.free_text)
        self.assertIn("城市孤独", intent.free_text)


if __name__ == "__main__":
    unittest.main()
