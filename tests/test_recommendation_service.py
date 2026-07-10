import json
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.intent_parser import RecommendationIntent
from douban_recommender.models import recommendation_item_key
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

    def test_previous_batch_on_new_session_returns_first_batch_without_self_lock(self):
        session = self.create()
        started = time.perf_counter()

        batch = self.service.previous_batch(session.id, "电影")

        self.assertLess(time.perf_counter() - started, 2.0)
        self.assertEqual(batch.index, 1)
        self.assertEqual(batch.visible_size, 3)

    def test_session_restores_from_new_service_instance(self):
        session = self.create()
        batch = self.service.next_batch(session.id, "电视剧")
        restored_service = RecommendationSessionService(self.database)
        restored = restored_service.restore_session(session.id)
        self.assertEqual(restored.id, session.id)
        self.assertEqual(restored.intent.media_types, ("电影", "电视剧", "动漫"))
        current = restored_service.current_batch(session.id, "电视剧")
        self.assertEqual(current.id, batch.id)

    def test_exhausted_batch_is_persisted_and_restorable(self):
        session = self.create()
        channel = next(iter(pools()))
        first = self.service.next_batch(session.id, channel)
        second = self.service.next_batch(session.id, channel)
        third = self.service.next_batch(session.id, channel)
        exhausted = self.service.next_batch(session.id, channel, reason="exhausted")

        self.assertTrue(exhausted.exhausted)
        self.assertEqual(exhausted.visible_size, 0)
        self.assertEqual(exhausted.index, third.index + 1)

        repeated = self.service.next_batch(session.id, channel)
        self.assertEqual(repeated.id, exhausted.id)
        self.assertEqual(repeated.index, exhausted.index)

        restored = self.service.restore_session(session.id)
        self.assertEqual(restored.channels[channel]["active_batch"], exhausted.index)
        self.assertEqual(restored.channels[channel]["last_batch"], exhausted.index)
        self.assertEqual(restored.channels[channel]["cursor"], 7)

        current = RecommendationSessionService(self.database).current_batch(session.id, channel)
        self.assertEqual(current.id, exhausted.id)

        previous = self.service.previous_batch(session.id, channel)
        self.assertEqual(previous.id, third.id)

        resumed = self.service.next_batch(session.id, channel)
        self.assertEqual(resumed.id, exhausted.id)
        self.assertEqual(resumed.reason, "exhausted")

    def test_next_batch_rolls_back_batch_when_session_update_fails(self):
        session = self.create()
        with self.database.connection() as connection:
            connection.execute(
                """
                CREATE TRIGGER fail_recommendation_session_update
                BEFORE UPDATE ON recommendation_sessions
                BEGIN
                    SELECT RAISE(FAIL, 'session update failed');
                END
                """
            )

        with self.assertRaisesRegex(sqlite3.IntegrityError, "session update failed"):
            self.service.next_batch(session.id, "电影")

        with self.database.connection() as connection:
            batch_count = connection.execute(
                "SELECT COUNT(*) FROM recommendation_batches WHERE session_id = ?",
                (session.id,),
            ).fetchone()[0]
            stored = connection.execute(
                "SELECT channels_json FROM recommendation_sessions WHERE id = ?",
                (session.id,),
            ).fetchone()[0]
            connection.execute("DROP TRIGGER fail_recommendation_session_update")

        self.assertEqual(batch_count, 0)
        self.assertEqual(json.loads(stored)["电影"]["active_batch"], 0)

        retried = self.service.next_batch(session.id, "电影")
        self.assertEqual(retried.index, 1)
        with self.database.connection() as connection:
            self.assertEqual(
                connection.execute(
                    "SELECT COUNT(*) FROM recommendation_batches WHERE session_id = ?",
                    (session.id,),
                ).fetchone()[0],
                1,
            )

    def test_feedback_excludes_future_exact_key_and_still_fills_batch(self):
        session = self.create()
        first = self.service.next_batch(session.id, "电影")
        future_item = pools()["电影"]["items"][3]
        excluded_key = recommendation_item_key(future_item)

        result = self.service.apply_feedback(session.id, "not-tonight", excluded_key)
        self.assertEqual(result["item_key"], excluded_key)
        self.assertEqual(result["event_type"], "not-tonight")

        second = self.service.next_batch(session.id, "电影")
        self.assertNotIn(excluded_key, second.item_keys)
        self.assertEqual(second.visible_size, 3)
        self.assertEqual([item["title"] for item in second.items], ["电影4", "电影5", "电影6"])
        restored = self.service.restore_session(session.id)
        self.assertEqual(restored.channels["电影"]["cursor"], 7)
        self.assertEqual(restored.channels["电影"]["excluded_keys"], [excluded_key])

        previous = self.service.previous_batch(session.id, "电影")
        self.assertEqual(previous.id, first.id)
        forward = self.service.next_batch(session.id, "电影")
        self.assertEqual(forward.id, second.id)

    def test_watched_feedback_upserts_library_item_and_is_idempotent(self):
        session = self.create()
        batch = self.service.next_batch(session.id, "动漫")
        item = dict(batch.items[0])
        key = batch.item_keys[0]

        first = self.service.apply_feedback(session.id, "watched", key, {"source": "card"})
        second = self.service.apply_feedback(session.id, "watched", key, {"source": "card"})

        self.assertEqual(first["state"], "watched")
        self.assertEqual(second["state"], "watched")
        watched = self.service.library_items(states=["watched"])
        self.assertEqual([row["item_key"] for row in watched], [key])
        self.assertEqual(watched[0]["state"], "watched")
        self.assertEqual(watched[0]["payload"]["title"], item["title"])
        self.assertIn(key, self.service.restore_session(session.id).channels["动漫"]["excluded_keys"])

    def test_repeated_stable_feedback_does_not_replay_library_writes(self):
        cases = [("watched", "watched", "动漫", 0), ("want", "wanted", "电视剧", 1)]
        for event_type, state, channel, item_index in cases:
            with self.subTest(event_type=event_type):
                session = self.create()
                batch = self.service.next_batch(session.id, channel)
                key = batch.item_keys[item_index]

                first = self.service.apply_feedback(session.id, event_type, key)
                before = self._library_row(key)
                time.sleep(0.01)
                second = self.service.apply_feedback(session.id, event_type, key)
                after = self._library_row(key)

                self.assertEqual(second["event_id"], first["event_id"])
                self.assertEqual(before["state"], state)
                self.assertEqual(after["updated_at"], before["updated_at"])
                self.assertEqual(after["source"], before["source"])
                self.assertEqual(after["payload_json"], before["payload_json"])

    def _library_row(self, item_key: str):
        with self.database.connection() as connection:
            return connection.execute(
                """
                SELECT item_key, payload_json, state, source, created_at, updated_at
                FROM library_items WHERE item_key = ?
                """,
                (item_key,),
            ).fetchone()

    def test_want_feedback_upserts_wanted_library_item(self):
        session = self.create()
        batch = self.service.next_batch(session.id, "电视剧")
        key = batch.item_keys[1]

        result = self.service.apply_feedback(session.id, "want", key)

        self.assertEqual(result["state"], "wanted")
        wanted = self.service.library_items(states=["wanted"])
        self.assertEqual(len(wanted), 1)
        self.assertEqual(wanted[0]["item_key"], key)
        self.assertEqual(wanted[0]["payload"]["title"], batch.items[1]["title"])

    def test_create_session_registers_candidates_without_downgrading_watched(self):
        watched_item = pools()["电影"]["items"][0]
        watched_key = recommendation_item_key(watched_item)
        now = 123.0
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, 'watched', 'fixture', ?, ?)
                """,
                (watched_key, json.dumps({"title": "already watched"}, ensure_ascii=False), now, now),
            )

        self.create()

        movie_keys = [recommendation_item_key(item) for item in pools()["电影"]["items"]]
        catalog = {row["item_key"]: row for row in self.service.library_items(states=["candidate", "watched"])}
        self.assertTrue(set(movie_keys).issubset(catalog))
        self.assertEqual(catalog[watched_key]["state"], "watched")
        self.assertEqual(catalog[watched_key]["payload"]["title"], watched_item["title"])

    def test_apply_feedback_unknown_session_and_key_raise_value_error(self):
        session = self.create()

        with self.assertRaisesRegex(ValueError, "recommendation session not found"):
            self.service.apply_feedback("missing", "watched", "douban:missing")
        with self.assertRaisesRegex(ValueError, "recommendation item not found"):
            self.service.apply_feedback(session.id, "watched", "douban:missing")
        with self.assertRaisesRegex(ValueError, "unsupported feedback event"):
            self.service.apply_feedback(session.id, "unknown", recommendation_item_key(pools()["电影"]["items"][0]))

    def test_concurrent_next_batch_keeps_unique_history_indexes(self):
        session = self.create()
        barrier = threading.Barrier(4)
        results = []
        errors = []

        def worker():
            try:
                barrier.wait(timeout=5)
                results.append(self.service.next_batch(session.id, "动漫").index)
            except Exception as exc:  # pragma: no cover - surfaced below
                errors.append(exc)

        threads = [threading.Thread(target=worker) for _ in range(4)]
        for thread in threads:
            thread.start()
        for thread in threads:
            thread.join()

        self.assertEqual(errors, [])
        self.assertEqual(sorted(results), [1, 2, 3, 4])
        with self.database.connection() as connection:
            stored_indexes = [
                row[0]
                for row in connection.execute(
                    """
                    SELECT batch_index FROM recommendation_batches
                    WHERE session_id = ? AND channel = '动漫'
                    ORDER BY batch_index
                    """,
                    (session.id,),
                ).fetchall()
            ]
        self.assertEqual(stored_indexes, [1, 2, 3, 4])


if __name__ == "__main__":
    unittest.main()
