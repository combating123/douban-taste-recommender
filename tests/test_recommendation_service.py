import json
import copy
import sqlite3
import tempfile
import threading
import time
import unittest
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.feedback_service import FeedbackEvent, FeedbackService
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


def reason_pools():
    return {
        "电影": {
            "items": [
                {"title": "剧情开场", "media_type": "电影", "douban_id": "reason-1", "score": 100, "genres": ["剧情"], "tags": ["黑色电影"]},
                {"title": "剧情尾项", "media_type": "电影", "douban_id": "reason-2", "score": 99, "genres": ["剧情"], "tags": ["人物"]},
                {"title": "喜剧候选", "media_type": "电影", "douban_id": "reason-3", "score": 98, "genres": ["喜剧"], "tags": ["轻松"]},
                {"title": "动作候选", "media_type": "电影", "douban_id": "reason-4", "score": 97, "genres": ["动作"], "tags": ["冒险"]},
            ],
            "pool_size": 4,
            "matched_size": 4,
        }
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

    def test_permanent_avoid_filters_current_and_historical_batches_until_undo(self):
        session = self.create()
        first = self.service.next_batch(session.id, "电影")
        rejected_key = first.item_keys[0]

        applied = self.service.apply_feedback(session.id, "permanent-avoid", rejected_key)

        current = self.service.current_batch(session.id, "电影")
        self.assertNotIn(rejected_key, current.item_keys)
        self.assertEqual(current.visible_size, 2)
        second = self.service.next_batch(session.id, "电影")
        previous = self.service.previous_batch(session.id, "电影")
        self.assertNotIn(rejected_key, previous.item_keys)
        self.assertEqual(previous.visible_size, 2)
        self.assertNotIn(rejected_key, second.item_keys)

        self.service.undo_feedback(applied["event_id"])

        restored = self.service.current_batch(session.id, "电影")
        self.assertIn(rejected_key, restored.item_keys)
        self.assertEqual(restored.visible_size, 3)

    def test_watched_library_alias_filters_old_session_item_with_different_primary_key(self):
        ranked = {
            "电影": {
                "items": [
                    {
                        "title": "同一部电影",
                        "year": 2024,
                        "media_type": "电影",
                        "douban_id": "123456",
                        "douban_rating": 8.7,
                        "summary": "完整剧情简介",
                        "genres": ["剧情"],
                    }
                ],
                "pool_size": 1,
                "matched_size": 1,
            }
        }
        session = self.service.create_session(
            "profile-1",
            RecommendationIntent(media_types=("电影",)),
            ranked,
            {"电影": 1},
        )
        self.service.next_batch(session.id, "电影")
        watched_payload = {
            "title": "同一部电影",
            "year": 2024,
            "media_type": "电影",
            "source": "douban_user:collect",
            "tags": ["看过"],
        }
        watched_key = recommendation_item_key(watched_payload)
        now = time.time()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT OR REPLACE INTO library_items(
                    item_key, payload_json, state, source, created_at, updated_at
                ) VALUES(?, ?, 'watched', 'douban_user:collect', ?, ?)
                """,
                (watched_key, json.dumps(watched_payload, ensure_ascii=False), now, now),
            )

        current = self.service.current_batch(session.id, "电影")

        self.assertEqual(current.item_keys, ())
        self.assertEqual(current.visible_size, 0)

    def test_undo_not_tonight_restores_exclusion_and_reapply_creates_new_event(self):
        session = self.create()
        channel = next(iter(pools()))
        key = recommendation_item_key(pools()[channel]["items"][3])
        first = self.service.apply_feedback(session.id, "not-tonight", key)
        self.assertIn(key, self.service.restore_session(session.id).channels[channel]["excluded_keys"])

        undo_id = self.service.undo_feedback(first["event_id"])
        restored = self.service.restore_session(session.id)
        second = self.service.apply_feedback(session.id, "not-tonight", key)

        self.assertTrue(undo_id)
        self.assertNotIn(key, restored.channels[channel]["excluded_keys"])
        self.assertNotEqual(second["event_id"], first["event_id"])

    def test_undo_library_feedback_restores_candidate_missing_and_existing_states(self):
        channel = list(pools())[2]
        for prior in ("candidate", "missing", "wanted"):
            with self.subTest(prior=prior):
                session = self.create()
                batch = self.service.next_batch(session.id, channel)
                key = batch.item_keys[0]
                if prior == "missing":
                    with self.database.connection() as connection:
                        connection.execute("DELETE FROM library_items WHERE item_key = ?", (key,))
                    event_type = "want"
                elif prior == "wanted":
                    with self.database.connection() as connection:
                        connection.execute(
                            "UPDATE library_items SET state = 'wanted', source = 'fixture-prior' WHERE item_key = ?",
                            (key,),
                        )
                    event_type = "watched"
                else:
                    event_type = "watched"

                applied = self.service.apply_feedback(session.id, event_type, key)
                self.service.undo_feedback(applied["event_id"])
                row = self._library_row(key)

                if prior == "missing":
                    self.assertIsNone(row)
                else:
                    self.assertEqual(row["state"], prior)
                    if prior == "wanted":
                        self.assertEqual(row["source"], "fixture-prior")

    def test_undo_older_feedback_does_not_overwrite_later_active_event(self):
        session = self.create()
        channel = list(pools())[2]
        batch = self.service.next_batch(session.id, channel)
        key = batch.item_keys[0]
        first = self.service.apply_feedback(session.id, "want", key)
        time.sleep(0.002)
        later_session = self.create()
        later = self.service.apply_feedback(later_session.id, "watched", key)

        self.service.undo_feedback(first["event_id"])
        row = self._library_row(key)
        reapplied = self.service.apply_feedback(session.id, "want", key)

        self.assertEqual(row["state"], "watched")
        self.assertIn(key, self.service.restore_session(later_session.id).channels[channel]["excluded_keys"])
        self.assertNotEqual(reapplied["event_id"], first["event_id"])
        self.assertNotEqual(reapplied["event_id"], later["event_id"])

    def test_undo_recomputes_effective_state_from_remaining_active_feedback_chain(self):
        session = self.create()
        channel = list(pools())[2]
        key = self.service.next_batch(session.id, channel).item_keys[0]
        watched = self.service.apply_feedback(session.id, "watched", key)
        wanted = self.service.apply_feedback(session.id, "want", key)

        self.service.undo_feedback(watched["event_id"])
        after_watched_undo = self._library_row(key)
        self.service.undo_feedback(wanted["event_id"])
        after_all_undo = self._library_row(key)

        self.assertEqual(after_watched_undo["state"], "wanted")
        self.assertEqual(after_all_undo["state"], "candidate")

    def test_undo_preserves_newer_candidate_payload_and_metadata(self):
        original_pools = pools()
        session = self.service.create_session(
            "profile-1",
            RecommendationIntent(),
            original_pools,
            {channel: 3 for channel in original_pools},
        )
        channel = next(iter(original_pools))
        key = recommendation_item_key(original_pools[channel]["items"][0])
        watched = self.service.apply_feedback(session.id, "watched", key)

        refreshed_pools = copy.deepcopy(original_pools)
        refreshed_pools[channel]["items"][0]["summary"] = "newer candidate summary"
        time.sleep(0.002)
        self.service.create_session(
            "profile-1",
            RecommendationIntent(),
            refreshed_pools,
            {name: 3 for name in refreshed_pools},
        )
        refreshed = self._library_row(key)

        self.service.undo_feedback(watched["event_id"])
        restored = self._library_row(key)

        self.assertEqual(restored["state"], "candidate")
        self.assertEqual(json.loads(restored["payload_json"])["summary"], "newer candidate summary")
        self.assertEqual(restored["source"], refreshed["source"])
        self.assertEqual(restored["updated_at"], refreshed["updated_at"])

    def create_reason_session(self):
        return self.service.create_session(
            "profile-reason",
            RecommendationIntent(media_types=("电影",)),
            reason_pools(),
            {"电影": 1},
        )

    def test_known_reason_reorders_only_the_unseen_tail_and_persists_session_metadata(self):
        baseline = self.create_reason_session()
        reasoned = self.create_reason_session()
        self.service.next_batch(baseline.id, "电影")
        baseline_next = self.service.next_batch(baseline.id, "电影")
        first = self.service.next_batch(reasoned.id, "电影")
        reason = "想看喜剧 token=should-not-persist " + "x" * 200

        adjusted = self.service.next_batch(reasoned.id, "电影", reason=reason)

        self.assertEqual(first.items[0]["title"], "剧情开场")
        self.assertEqual(baseline_next.items[0]["title"], "剧情尾项")
        self.assertEqual(adjusted.items[0]["title"], "喜剧候选")
        self.assertNotEqual(adjusted.item_keys, baseline_next.item_keys)
        self.assertEqual(adjusted.reason, reason)
        adjustment = adjusted.to_dict()["reason_adjustment"]
        self.assertEqual(adjustment["mode"], "preference")
        self.assertEqual(adjustment["matched_terms"], ["喜剧"])
        self.assertLessEqual(len(adjustment["reason"]), 160)
        self.assertIn("token=<redacted>", adjustment["reason"])
        self.assertNotIn("should-not-persist", adjustment["reason"])
        self.assertNotIn("profile", adjustment)
        self.assertNotIn("permanent", json.dumps(adjustment, ensure_ascii=False).casefold())

        restored = RecommendationSessionService(self.database)
        restored_session = restored.restore_session(reasoned.id)
        self.assertEqual(restored_session.intent.to_dict(), RecommendationIntent(media_types=("电影",)).to_dict())
        self.assertEqual(restored_session.channels["电影"]["reason_adjustments"]["2"], adjustment)
        self.assertEqual(restored.current_batch(reasoned.id, "电影").to_dict()["reason_adjustment"], adjustment)
        with self.database.connection() as connection:
            payload = json.loads(
                connection.execute(
                    "SELECT payload_json FROM recommendation_batches WHERE session_id = ? AND channel = ? AND batch_index = 2",
                    (reasoned.id, "电影"),
                ).fetchone()["payload_json"]
            )
        self.assertEqual(payload["reason_adjustment"], adjustment)

    def test_novelty_reason_penalizes_overlap_without_repeats_or_forward_recomputation(self):
        session = self.create_reason_session()
        first = self.service.next_batch(session.id, "电影")
        adjusted = self.service.next_batch(session.id, "电影", reason="太相似")

        self.assertEqual(adjusted.items[0]["title"], "喜剧候选")
        self.assertEqual(adjusted.to_dict()["reason_adjustment"]["mode"], "novelty")
        previous = self.service.previous_batch(session.id, "电影")
        forward = self.service.next_batch(session.id, "电影", reason="想看动作")
        self.assertEqual(previous.id, first.id)
        self.assertEqual(forward.id, adjusted.id)
        self.assertEqual(forward.to_dict()["reason_adjustment"], adjusted.to_dict()["reason_adjustment"])

        remaining = [self.service.next_batch(session.id, "电影") for _ in range(2)]
        all_keys = [key for batch in [first, adjusted, *remaining] for key in batch.item_keys]
        self.assertEqual(len(all_keys), len(set(all_keys)))

    def test_undo_recomputes_exclusion_from_all_remaining_active_events(self):
        session = self.create()
        channel = next(iter(pools()))
        key = recommendation_item_key(pools()[channel]["items"][0])
        watched = self.service.apply_feedback(session.id, "watched", key)
        not_tonight = self.service.apply_feedback(session.id, "not-tonight", key)

        self.service.undo_feedback(watched["event_id"])
        self.assertIn(key, self.service.restore_session(session.id).channels[channel]["excluded_keys"])
        self.service.undo_feedback(not_tonight["event_id"])

        self.assertNotIn(key, self.service.restore_session(session.id).channels[channel]["excluded_keys"])

    def test_undo_ignores_inert_no_session_library_feedback(self):
        cases = (("watched", "want"), ("want", "watched"))
        feedback = FeedbackService(self.database)
        for index, (inert_type, materialized_type) in enumerate(cases):
            with self.subTest(inert_type=inert_type, materialized_type=materialized_type):
                session = self.create()
                channel = list(pools())[index]
                key = self.service.next_batch(session.id, channel).item_keys[0]
                feedback.record_feedback(
                    FeedbackEvent(
                        event_type=inert_type,
                        item_key=key,
                        profile_key="profile-1",
                        payload={
                            "source": "inert-profile-feedback",
                            "_recommendation_undo": (
                                {
                                    "state_effect": {
                                        "source": "recommendation-session-service",
                                        "version": 1,
                                    }
                                }
                                if index == 0
                                else {
                                    "prior_excluded_channels": [],
                                    "prior_library": {"exists": False},
                                    "state_origin": {"exists": False},
                                    "exclusion_origin_channels": [],
                                }
                            ),
                        },
                        created_at=time.time(),
                    )
                )

                applied = self.service.apply_feedback(session.id, materialized_type, key)
                self.service.undo_feedback(applied["event_id"])

                self.assertEqual(self._library_row(key)["state"], "candidate")

    def test_inert_legacy_session_feedback_is_not_reused_or_materialized(self):
        session = self.create()
        channel = next(iter(pools()))
        key = recommendation_item_key(pools()[channel]["items"][0])
        inert_id = "legacy-inert-not-tonight"
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO feedback_events(
                    id, profile_key, session_id, item_key, event_type,
                    payload_json, undone_by, created_at
                ) VALUES(?, 'profile-1', ?, ?, 'not-tonight', ?, NULL, ?)
                """,
                (
                    inert_id,
                    session.id,
                    key,
                    json.dumps(
                        {
                            "item": pools()[channel]["items"][0],
                            "_recommendation_undo": {
                                "state_effect": {
                                    "source": "recommendation-session-service",
                                    "version": "not-a-number",
                                }
                            },
                        },
                        ensure_ascii=False,
                    ),
                    time.time(),
                ),
            )

        applied = self.service.apply_feedback(session.id, "not-tonight", key)
        self.assertNotEqual(applied["event_id"], inert_id)
        self.assertIn(key, self.service.restore_session(session.id).channels[channel]["excluded_keys"])

        self.service.undo_feedback(applied["event_id"])
        self.assertNotIn(key, self.service.restore_session(session.id).channels[channel]["excluded_keys"])

    def test_legacy_materialized_feedback_metadata_remains_undoable(self):
        session = self.create()
        channel = next(iter(pools()))
        key = recommendation_item_key(pools()[channel]["items"][0])
        event_id = "legacy-materialized-not-tonight"
        restored = self.service.restore_session(session.id)
        channels = restored.channels
        channels[channel]["excluded_keys"] = [key]
        metadata = {
            "prior_excluded_channels": [],
            "prior_library": None,
            "state_origin": None,
            "exclusion_origin_channels": [],
        }
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE recommendation_sessions SET channels_json = ? WHERE id = ?",
                (json.dumps(channels, ensure_ascii=False), session.id),
            )
            connection.execute(
                """
                INSERT INTO feedback_events(
                    id, profile_key, session_id, item_key, event_type,
                    payload_json, undone_by, created_at
                ) VALUES(?, 'profile-1', ?, ?, 'not-tonight', ?, NULL, ?)
                """,
                (
                    event_id,
                    session.id,
                    key,
                    json.dumps({"item": pools()[channel]["items"][0], "_recommendation_undo": metadata}, ensure_ascii=False),
                    time.time(),
                ),
            )

        self.service.undo_feedback(event_id)

        self.assertNotIn(key, self.service.restore_session(session.id).channels[channel]["excluded_keys"])

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
        self.assertIn(key, self.service.restore_session(session.id).channels["电视剧"]["excluded_keys"])

    def test_create_session_registers_candidates_without_downgrading_watched(self):
        watched_item = pools()["电影"]["items"][0]
        watched_key = recommendation_item_key(watched_item)
        now = 123.0
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, 'watched', 'douban-sync:user:watched', ?, ?)
                """,
                (watched_key, json.dumps({"title": "already watched"}, ensure_ascii=False), now, now),
            )

        self.create()

        movie_keys = [recommendation_item_key(item) for item in pools()["电影"]["items"]]
        catalog = {row["item_key"]: row for row in self.service.library_items(states=["candidate", "watched"])}
        self.assertTrue(set(movie_keys).issubset(catalog))
        self.assertEqual(catalog[watched_key]["state"], "watched")
        self.assertEqual(catalog[watched_key]["payload"]["title"], "already watched")
        self.assertEqual(catalog[watched_key]["source"], "douban-sync:user:watched")

    def test_create_session_does_not_downgrade_or_overwrite_synced_wish(self):
        wished_item = pools()["电影"][0] if isinstance(pools()["电影"], list) else pools()["电影"]["items"][0]
        wished_key = recommendation_item_key(wished_item)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, 'wish', 'douban-sync:user:wish', 1, 1)
                """,
                (wished_key, json.dumps({"title": "synced wish", "tags": ["想看"]}, ensure_ascii=False)),
            )

        self.create()

        row = self._library_row(wished_key)
        self.assertEqual(row["state"], "wish")
        self.assertEqual(row["source"], "douban-sync:user:wish")
        self.assertEqual(json.loads(row["payload_json"])["title"], "synced wish")

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
