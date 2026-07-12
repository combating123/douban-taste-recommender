import unittest
from datetime import datetime

from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.models import MediaItem
from douban_recommender.profiler import TasteProfile
from douban_recommender.ranking import rank_candidates


def media(
    title,
    *,
    rating=8.5,
    votes=10000,
    media_type="电影",
    country="美国",
    genres=None,
    episode_runtime=None,
    year=None,
    raw=None,
):
    payload = dict(raw or {})
    if episode_runtime is not None:
        payload["episode_runtime"] = episode_runtime
    return MediaItem(
        title=title,
        douban_rating=rating,
        vote_count=votes,
        media_type=media_type,
        countries=[country] if country else [],
        genres=list(genres or ["剧情"]),
        summary="剧情完整，人物关系扎实。",
        year=year,
        raw=payload,
    )


class ExplainableRankingTests(unittest.TestCase):
    def test_recent_high_quality_title_gets_current_relevance_without_excluding_classics(self):
        current_year = datetime.now().year
        recent = media("Recent acclaimed", rating=8.9, votes=120000, year=current_year - 1)
        classic = media("Classic acclaimed", rating=8.9, votes=120000, year=1995)

        ranked = rank_candidates([], [classic, recent], TasteProfile(), RecommendationIntent())

        self.assertEqual(ranked[0].item.title, "Recent acclaimed")
        self.assertTrue(any(signal["code"] == "current-relevance" for signal in ranked[0].score_breakdown["signals"]))
        self.assertEqual({row.item.title for row in ranked}, {"Recent acclaimed", "Classic acclaimed"})

    def test_high_vote_quality_beats_tiny_vote_perfect_rating(self):
        stable = media("稳定高分", rating=9.1, votes=200000)
        tiny = media("小样本满分", rating=9.8, votes=12)
        ranked = rank_candidates([], [tiny, stable], TasteProfile(), RecommendationIntent())
        self.assertEqual(ranked[0].item.title, "稳定高分")
        self.assertGreater(
            ranked[0].score_breakdown["quality"],
            ranked[1].score_breakdown["quality"],
        )

    def test_context_changes_current_order_without_mutating_profile(self):
        profile = TasteProfile()
        before = profile.summary()
        short = media(
            "短剧",
            rating=9.0,
            media_type="动漫",
            country="日本",
            episode_runtime=24,
            raw={"format": "TV", "episodes": 12},
        )
        long = media(
            "长剧",
            rating=9.2,
            media_type="动漫",
            country="日本",
            episode_runtime=60,
            raw={"format": "TV", "episodes": 12},
        )
        intent = RecommendationIntent(media_types=("动漫",), episode_runtime_max=30)
        ranked = rank_candidates([], [long, short], profile, intent)
        self.assertEqual(ranked[0].item.title, "短剧")
        self.assertEqual(profile.summary(), before)

    def test_breakdown_exposes_four_dimensions_confidence_signals_and_conflicts(self):
        item = media(
            "古装长剧",
            rating=9.0,
            media_type="电视剧",
            country="中国大陆",
            genres=["剧情", "古装"],
            raw={"episode_runtime": 60},
        )
        ranked = rank_candidates(
            [],
            [item],
            TasteProfile(),
            RecommendationIntent(media_types=("电视剧",), episode_runtime_max=30),
        )
        breakdown = ranked[0].score_breakdown
        self.assertTrue({"quality", "taste", "context", "exploration", "total", "confidence", "signals", "conflicts"} <= set(breakdown))
        self.assertTrue(any(signal["code"] == "costume-series" for signal in breakdown["signals"]))
        self.assertTrue(breakdown["conflicts"])

    def test_costume_default_penalty_opt_in_removes_penalty_and_avoid_penalizes(self):
        costume = media("古装长剧", rating=9.0, media_type="电视剧", country="中国大陆", genres=["剧情", "古装"])
        modern = media("现代剧", rating=8.8, media_type="电视剧", country="中国大陆", genres=["剧情", "悬疑"])

        default_ranked = rank_candidates(
            [],
            [costume, modern],
            TasteProfile(),
            RecommendationIntent(media_types=("电视剧",)),
        )
        opt_in_ranked = rank_candidates(
            [],
            [costume, modern],
            TasteProfile(),
            RecommendationIntent(media_types=("电视剧",), genres=("古装",), free_text="想看古装剧"),
        )
        avoid_ranked = rank_candidates(
            [],
            [costume, modern],
            TasteProfile(),
            RecommendationIntent(media_types=("电视剧",), avoid=("古装",), free_text="不要古装"),
        )

        self.assertEqual(default_ranked[0].item.title, "现代剧")
        self.assertTrue(any("古装" in warning for warning in default_ranked[1].warnings))
        self.assertEqual(opt_in_ranked[0].item.title, "古装长剧")
        self.assertFalse(any("古装" in warning for warning in opt_in_ranked[0].warnings))
        self.assertEqual([row.item.title for row in avoid_ranked], ["现代剧"])

    def test_animated_movie_is_removed_before_scoring(self):
        film = media(
            "动画电影",
            media_type="动漫",
            country="日本",
            raw={"format": "MOVIE"},
        )
        series = media(
            "动画剧集",
            media_type="动漫",
            country="日本",
            raw={"format": "TV", "episodes": 12},
        )
        ranked = rank_candidates(
            [],
            [film, series],
            TasteProfile(),
            RecommendationIntent(media_types=("动漫",)),
        )
        self.assertEqual([row.item.title for row in ranked], ["动画剧集"])

    def test_diversity_rerank_breaks_country_monotony_without_promoting_low_quality(self):
        candidates = [
            media(f"日本佳作{i}", rating=9.2 - i * 0.02, votes=100000, media_type="动漫", country="日本", raw={"format": "TV", "episodes": 12})
            for i in range(5)
        ] + [
            media("中国佳作", rating=9.0, votes=80000, media_type="动漫", country="中国大陆", raw={"format": "TV", "episodes": 12}),
            media("低质补位", rating=6.0, votes=500, media_type="动漫", country="美国", raw={"format": "TV", "episodes": 12}),
        ]
        ranked = rank_candidates(
            [],
            candidates,
            TasteProfile(),
            RecommendationIntent(media_types=("动漫",)),
            limit=6,
        )
        top_countries = [row.item.countries[0] for row in ranked[:4]]
        self.assertIn("中国大陆", top_countries)
        self.assertNotIn("低质补位", [row.item.title for row in ranked[:4]])


if __name__ == "__main__":
    unittest.main()
