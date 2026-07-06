import unittest

from douban_recommender.candidate_planner import CandidateQuery
from douban_recommender.douban_sources import fetch_candidates_from_plan
from douban_recommender.models import MediaItem


class CandidateFetchPlanTests(unittest.TestCase):
    def test_fetch_candidates_from_plan_dedupes_and_keeps_partial_success(self):
        plan = [
            CandidateQuery("movie_quality", "电影,剧情", media_type="电影"),
            CandidateQuery("anime_quality", "动画", media_type="动漫"),
            CandidateQuery("bad", "bad"),
        ]

        def fake_fetcher(tags, sort="U", start=0, limit=20):
            if tags == "bad":
                raise RuntimeError("network failed")
            return [
                MediaItem(title="共同条目", douban_id="1", media_type="电影"),
                MediaItem(
                    title=tags,
                    douban_id=tags,
                    media_type="动漫" if tags == "动画" else "电影",
                ),
            ]

        report = fetch_candidates_from_plan(plan, fetcher=fake_fetcher, sleep_seconds=0)

        self.assertEqual(len([item for item in report.items if item.douban_id == "1"]), 1)
        self.assertTrue(any(item.media_type == "动漫" for item in report.items))
        self.assertEqual(report.failed_queries, 1)
        self.assertGreaterEqual(report.successful_queries, 2)


if __name__ == "__main__":
    unittest.main()
