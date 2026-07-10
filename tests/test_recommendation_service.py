import tempfile
import unittest
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.recommendation_service import RecommendationSessionService


def rows(prefix, count, media_type):
    return [
        {
            "title": f"{prefix}{index}",
            "media_type": media_type,
            "douban_id": f"{prefix}-{index}",
            "score": 90 - index,
        }
        for index in range(count)
    ]


def pools():
    return {
        "电影": {"items": rows("电影", 7, "电影"), "pool_size": 80, "matched_size": 7},
        "电视剧": {"items": rows("剧集", 6, "电视剧"), "pool_size": 55, "matched_size": 6},
        "动漫": {"items": rows("动画", 8, "动漫"), "pool_size": 160, "matched_size": 47},
    }


class RecommendationSessionServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()
        self.service = RecommendationSessionService(self.database)

    def tearDown(self):
        self.temp.cleanup()

    def create(self):
        return self.service.create_session(
            "profile-1",
            RecommendationIntent(media_types=("电影", "电视剧", "动漫")),
            pools(),
            {"电影": 3, "电视剧": 3, "动漫": 3},
        )

    def test_movie_and_anime_batches_have_independent_cursors(self):
        session = self.create()
        first_movie = self.service.next_batch(session.id, "电影")
        first_anime = self.service.next_batch(session.id, "动漫")
        second_movie = self.service.next_batch(session.id, "电影")
        self.assertEqual(first_anime.index, 1)
        self.assertEqual(second_movie.index, 2)
        self.assertFalse(set(first_movie.item_keys) & set(second_movie.item_keys))
        restored = self.service.restore_session(session.id)
        self.assertEqual(restored.channels["电影"]["active_batch"], 2)
        self.assertEqual(restored.channels["动漫"]["active_batch"], 1)

    def test_pool_match_and_visible_counts_are_distinct(self):
        session = self.create()
        batch = self.service.next_batch(session.id, "动漫")
        self.assertEqual((batch.pool_size, batch.matched_size, batch.visible_size), (160, 47, 3))

    def test_no_repeat_until_pool_is_exhausted(self):
        session = self.create()
        batches = [self.service.next_batch(session.id, "电影") for _ in range(3)]
        all_keys = [key for batch in batches for key in batch.item_keys]
        self.assertEqual(len(all_keys), len(set(all_keys)))
        self.assertEqual([batch.visible_size for batch in batches], [3, 3, 1])
        exhausted = self.service.next_batch(session.id, "电影")
        self.assertTrue(exhausted.exhausted)
        self.assertEqual(exhausted.visible_size, 0)

    def test_previous_batch_restores_history_without_recomputing(self):
        session = self.create()
        first = self.service.next_batch(session.id, "动漫")
        second = self.service.next_batch(session.id, "动漫", reason="太相似")
        previous = self.service.previous_batch(session.id, "动漫")
        self.assertEqual(previous.id, first.id)
        forward = self.service.next_batch(session.id, "动漫")
        self.assertEqual(forward.id, second.id)
        self.assertEqual(forward.reason, "太相似")

    def test_session_restores_from_new_service_instance(self):
        session = self.create()
        batch = self.service.next_batch(session.id, "电视剧")
        restored_service = RecommendationSessionService(self.database)
        restored = restored_service.restore_session(session.id)
        self.assertEqual(restored.id, session.id)
        self.assertEqual(restored.intent.media_types, ("电影", "电视剧", "动漫"))
        current = restored_service.current_batch(session.id, "电视剧")
        self.assertEqual(current.id, batch.id)


if __name__ == "__main__":
    unittest.main()
