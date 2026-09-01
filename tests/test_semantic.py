import unittest

from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.models import MediaItem
from douban_recommender.profiler import build_taste_profile
from douban_recommender.ranking import rank_candidates
from douban_recommender.semantic import build_semantic_taste_model, feature_vector


def item(title, summary, *, my_rating=None, douban_rating=8.7, douban_id=""):
    return MediaItem(
        title=title,
        my_rating=my_rating,
        douban_rating=douban_rating,
        vote_count=100000,
        year=2024,
        media_type="电影",
        genres=["剧情", "悬疑"],
        countries=["韩国"],
        douban_id=douban_id or title,
        summary=summary,
    )


class SemanticTasteTests(unittest.TestCase):
    def test_feature_hashing_is_local_deterministic_and_normalized(self):
        first = feature_vector("非线性叙事中的失踪案件与心理谜团")
        second = feature_vector("非线性叙事中的失踪案件与心理谜团")

        self.assertEqual(first, second)
        self.assertEqual(len(first), 384)
        self.assertAlmostEqual(sum(value * value for value in first) ** 0.5, 1.0, places=6)

    def test_semantic_model_combines_history_and_current_natural_language_intent(self):
        liked = item("高分样本", "失踪案件、心理谜团和层层反转的非线性叙事。", my_rating=5)
        profile = build_taste_profile([liked])
        intent = RecommendationIntent(free_text="今晚想看心理谜团，最好有失踪案和反转")
        model = build_semantic_taste_model([liked], profile, intent)

        close = item("接近口味", "一宗失踪案牵出心理谜团，叙事不断反转。")
        distant = item("距离较远", "一家人在海边小镇修复亲情并经营温暖餐厅。")

        self.assertGreater(model.score(close).score, model.score(distant).score + 12)

    def test_semantic_affinity_changes_order_when_metadata_and_quality_are_equal(self):
        liked = item("喜欢的作品", "密闭空间里的失踪案，人物互相猜疑并揭开心理真相。", my_rating=5)
        close = item(
            "语义接近候选",
            "密闭空间发生失踪案，人物互相猜疑，真相多次反转。",
            douban_id="semantic-close",
        )
        distant = item(
            "语义较远候选",
            "几位朋友在海边开餐厅，重新理解家庭和日常生活。",
            douban_id="semantic-distant",
        )
        profile = build_taste_profile([liked])

        ranked = rank_candidates(
            [liked],
            [distant, close],
            profile,
            RecommendationIntent(media_types=("电影",), free_text="想看失踪悬案和心理反转"),
        )

        self.assertEqual(ranked[0].item.title, "语义接近候选")
        self.assertGreater(
            ranked[0].score_breakdown["semantic"],
            ranked[1].score_breakdown["semantic"],
        )
        self.assertTrue(any(
            signal["code"] == "semantic-affinity"
            for signal in ranked[0].score_breakdown["signals"]
        ))


if __name__ == "__main__":
    unittest.main()
