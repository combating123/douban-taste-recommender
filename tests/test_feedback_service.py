import tempfile
import unittest
import json
from datetime import datetime, timedelta, timezone
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.feedback_service import FeedbackEvent, FeedbackService
from douban_recommender.models import MediaItem, recommendation_item_key
from douban_recommender.profiler import build_taste_profile
from douban_recommender.recommender import score_item


UTC = timezone.utc


class FeedbackServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()
        self.service = FeedbackService(self.database)
        self.now = datetime(2026, 7, 10, 20, 0, tzinfo=UTC)

    def tearDown(self):
        self.temp.cleanup()

    def event(self, event_type, *, payload=None, session_id="s1", created_at=None):
        return FeedbackEvent(
            event_type=event_type,
            item_key="title:test",
            profile_key="profile-1",
            session_id=session_id,
            payload=payload or {},
            created_at=created_at or self.now,
        )

    def test_not_tonight_does_not_change_permanent_profile(self):
        self.service.record_feedback(
            self.event("not-tonight", payload={"pace": "slow"})
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        self.assertEqual(signals.permanent_negative, ())
        self.assertIn("pace:slow", signals.session_adjustments["s1"])

    def test_less_like_this_is_weak_and_permanent_avoid_is_strong(self):
        self.service.record_feedback(
            self.event("less-like-this", payload={"genre": "古装"})
        )
        self.service.record_feedback(
            self.event("permanent-avoid", payload={"term": "狗血"})
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        self.assertIn("genre:古装", signals.weak_negative)
        self.assertIn("term:狗血", signals.permanent_negative)

    def test_undo_removes_feedback_effect_without_deleting_original_event(self):
        event_id = self.service.record_feedback(
            self.event("less-like-this", payload={"pace": "slow"})
        )
        undo_id = self.service.undo_feedback(event_id)
        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT id, event_type, payload_json, undone_by, created_at "
                "FROM feedback_events ORDER BY created_at, rowid"
            ).fetchall()
        event_types = [row["event_type"] for row in rows]
        self.assertEqual(event_types, ["less-like-this", "undo"])
        self.assertIsNone(rows[0]["undone_by"])
        self.assertEqual(rows[1]["id"], undo_id)
        self.assertEqual(json.loads(rows[1]["payload_json"])["target_event_id"], event_id)
        before_undo = self.service.feedback_signals("profile-1", self.now)
        self.assertIn("pace:slow", before_undo.weak_negative)
        after_undo = self.service.feedback_signals(
            "profile-1", float(rows[1]["created_at"]) + 1.0
        )
        self.assertNotIn("pace:slow", after_undo.weak_negative)

    def test_session_feedback_without_features_stays_session_only(self):
        self.service.record_feedback(self.event("not-tonight", payload={}))
        self.service.record_feedback(
            self.event("tonight-candidate", payload={"mood": "warm"})
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        adjustments = signals.session_adjustments["s1"]
        self.assertIn("event:not-tonight", adjustments)
        self.assertIn("event:tonight-candidate", adjustments)
        self.assertNotIn("mood:warm", signals.positive)
        self.assertNotIn("mood:warm", signals.recent_30)

    def test_permanent_feedback_without_features_keeps_item_identity(self):
        self.service.record_feedback(self.event("more-like-this", payload={}))
        signals = self.service.feedback_signals("profile-1", self.now)
        self.assertIn("item:title:test", signals.positive)
        self.assertIn("item:title:test", signals.recent_30)
        drift = next(row for row in signals.drift_30 if row.feature == "item:title:test")
        self.assertEqual(drift.count, 1)
        profile = build_taste_profile([], feedback_signals=signals)
        self.assertGreater(profile.positive["item:title:test"], 0)
        self.assertEqual(profile.positive["tag:title:test"], 0)

    def test_item_only_feedback_changes_ranking_for_matching_item(self):
        target = MediaItem(
            title="Target",
            year=2025,
            media_type="movie",
            douban_rating=9.0,
            vote_count=10000,
        )
        other = MediaItem(
            title="Other",
            year=2025,
            media_type="movie",
            douban_rating=9.0,
            vote_count=10000,
        )
        self.service.record_feedback(
            FeedbackEvent(
                event_type="more-like-this",
                item_key=recommendation_item_key(target),
                profile_key="profile-1",
                created_at=self.now,
            )
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        profile = build_taste_profile([], feedback_signals=signals)
        self.assertGreater(score_item(target, profile).score, score_item(other, profile).score)

    def test_sensitive_feedback_payload_is_scrubbed_recursively(self):
        self.service.record_feedback(
            self.event(
                "more-like-this",
                payload={
                    "safe": {
                        "note": "keep-me",
                        "summary": "A secret garden plot stays intact.",
                        "context": "Cookie: bid=secret-cookie-value; ck=hidden-token",
                        "source_link": "https://user:pass@img.example/poster.png?api_key=secret-key#frag",
                        "cookie": "dbcl2=secret-cookie",
                        "openai_api_key": "secret-key",
                        "token": "secret-token-value",
                        "jwt": "secret-jwt",
                        "private_key": "secret-private-key",
                    },
                    "subscription_url": "https://secret.invalid/subscription",
                    "items": [
                        {
                            "authorization": "Bearer secret-token",
                            "genre": "mystery",
                            "details": "Bearer secret-token via https://user:pass@cdn.example/poster.png?token=nested-secret#frag",
                        },
                        [
                            "Cookie: dbcl2=list-secret-cookie",
                            {"url": "https://cdn.example/ok.jpg?api_key=list-secret"},
                        ],
                    ],
                },
            )
        )
        with self.database.connection() as connection:
            payload_json = connection.execute(
                "SELECT payload_json FROM feedback_events WHERE event_type = 'more-like-this'"
            ).fetchone()[0]
        self.assertNotIn("secret-cookie", payload_json)
        self.assertNotIn("secret-key", payload_json)
        self.assertNotIn("secret-token", payload_json)
        self.assertNotIn("secret-jwt", payload_json)
        self.assertNotIn("secret-private-key", payload_json)
        self.assertNotIn("subscription", payload_json)
        self.assertNotIn("user:pass", payload_json)
        self.assertNotIn("?api_key=", payload_json)
        self.assertNotIn("?token=", payload_json)
        self.assertNotIn("#frag", payload_json)
        payload = json.loads(payload_json)
        self.assertEqual(payload["safe"]["note"], "keep-me")
        self.assertEqual(payload["safe"]["summary"], "A secret garden plot stays intact.")
        self.assertEqual(payload["safe"]["source_link"], "https://img.example/poster.png")
        self.assertIn("Cookie", payload["safe"]["context"])
        self.assertEqual(payload["items"][0]["genre"], "mystery")
        self.assertIn("https://cdn.example/poster.png", payload["items"][0]["details"])
        self.assertIn("https://cdn.example/ok.jpg", payload["items"][1][1]["url"])

    def test_corrupt_json_rows_do_not_break_feedback_or_undo(self):
        event_id = self.service.record_feedback(
            self.event("more-like-this", payload={"genre": "mystery"})
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO feedback_events(
                    id, profile_key, session_id, item_key, event_type,
                    payload_json, undone_by, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    "corrupt-original",
                    "profile-1",
                    "",
                    "title:corrupt",
                    "more-like-this",
                    "{not-json",
                    self.now.timestamp() - 2,
                ),
            )
            connection.execute(
                """
                INSERT INTO feedback_events(
                    id, profile_key, session_id, item_key, event_type,
                    payload_json, undone_by, created_at
                ) VALUES(?, ?, ?, ?, 'undo', ?, NULL, ?)
                """,
                (
                    "corrupt-undo",
                    "profile-1",
                    "",
                    "title:corrupt",
                    "[]",
                    self.now.timestamp() - 1,
                ),
            )
        undo_id = self.service.undo_feedback(event_id)
        self.assertNotEqual(undo_id, "corrupt-undo")
        signals = self.service.feedback_signals(
            "profile-1", datetime.now(UTC) + timedelta(days=1)
        )
        self.assertIn("item:title:corrupt", signals.positive)

    def test_recent_drift_uses_30_and_90_day_windows(self):
        self.service.record_feedback(
            self.event(
                "more-like-this",
                payload={"mood": "温暖"},
                created_at=self.now - timedelta(days=10),
            )
        )
        self.service.record_feedback(
            self.event(
                "more-like-this",
                payload={"mood": "烧脑"},
                created_at=self.now - timedelta(days=60),
            )
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        self.assertIn("mood:温暖", signals.recent_30)
        self.assertNotIn("mood:烧脑", signals.recent_30)
        self.assertIn("mood:烧脑", signals.recent_90)

    def test_recent_drift_keeps_direction_frequency_and_profile_projection(self):
        for offset in (2, 4):
            self.service.record_feedback(
                self.event(
                    "more-like-this",
                    payload={"genre": "mystery"},
                    created_at=self.now - timedelta(days=offset),
                )
            )
        self.service.record_feedback(
            self.event(
                "less-like-this",
                payload={"genre": "mystery"},
                created_at=self.now - timedelta(days=6),
            )
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        drift = next(row for row in signals.drift_30 if row.feature == "genre:mystery")
        self.assertEqual(drift.count, 3)
        self.assertGreater(drift.positive_weight, drift.negative_weight)
        self.assertEqual(drift.direction, "positive")
        profile = build_taste_profile([], feedback_signals=signals)
        summary = profile.summary()
        projected = summary["recent_feedback"]["30d"]
        self.assertEqual(projected[0]["feature"], "genre:mystery")
        self.assertEqual(projected[0]["count"], 3)

    def test_profiler_can_consume_active_feedback_signals(self):
        self.service.record_feedback(
            self.event("less-like-this", payload={"genre": "古装"})
        )
        self.service.record_feedback(
            self.event("more-like-this", payload={"genre": "悬疑"})
        )
        signals = self.service.feedback_signals("profile-1", self.now)
        profile = build_taste_profile([], feedback_signals=signals)
        self.assertGreater(profile.positive["genre:悬疑"], 0)
        self.assertGreater(profile.negative["genre:古装"], 0)


if __name__ == "__main__":
    unittest.main()
