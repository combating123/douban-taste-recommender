import json
import tempfile
import unittest
from pathlib import Path

from douban_recommender.database import AppDatabase
from douban_recommender.migrations import migrate_legacy_recommendations
from douban_recommender.models import recommendation_item_key


class LegacyRecommendationMigrationTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def test_drops_numbered_placeholder_and_clears_stale_premium_cover(self):
        rows = [
            {"title": "电影候选 17", "source": "curated-placeholder"},
            {
                "title": "社交网络",
                "media_type": "电影",
                "year": 2010,
                "cover": "https://img9.doubanio.com/view/photo/wrong.jpg",
                "source": "premium-expansion",
            },
        ]
        report = migrate_legacy_recommendations(rows, self.database)
        self.assertEqual(report.dropped_placeholders, 1)
        self.assertEqual(report.dropped_stale_assets, 1)
        self.assertEqual(report.imported, 1)
        with self.database.connection() as connection:
            payload = json.loads(
                connection.execute("SELECT payload_json FROM library_items").fetchone()[0]
            )
        self.assertEqual(payload["title"], "社交网络")
        self.assertEqual(payload["cover"], "")

    def test_migration_is_idempotent_by_fingerprint(self):
        rows = [{"title": "十二怒汉", "media_type": "电影", "year": 1957}]
        first = migrate_legacy_recommendations(rows, self.database)
        second = migrate_legacy_recommendations(rows, self.database)
        self.assertEqual(first.imported, 1)
        self.assertTrue(second.skipped)
        self.assertEqual(second.imported, 0)
        with self.database.connection() as connection:
            count = connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0]
        self.assertEqual(count, 1)

    def test_sensitive_legacy_fields_are_not_persisted(self):
        rows = [
            {
                "title": "测试片",
                "media_type": "电影",
                "cookie": "bid=secret-cookie-value",
                "tmdb_api_key": "secret-api-key",
            }
        ]
        migrate_legacy_recommendations(rows, self.database)
        with self.database.connection() as connection:
            stored = connection.execute("SELECT payload_json FROM library_items").fetchone()[0]
        self.assertNotIn("secret-cookie-value", stored)
        self.assertNotIn("secret-api-key", stored)

    def test_nested_recommendation_item_is_flattened(self):
        rows = [
            {
                "score": 94,
                "item": {
                    "title": "奇巧计程车",
                    "media_type": "动漫",
                    "year": 2021,
                    "douban_id": "35280649",
                },
            }
        ]
        report = migrate_legacy_recommendations(rows, self.database)
        self.assertEqual(report.imported, 1)
        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT item_key, payload_json FROM library_items"
            ).fetchone()
        self.assertEqual(row["item_key"], "douban:35280649")
        self.assertEqual(json.loads(row["payload_json"])["title"], "奇巧计程车")

    def test_legacy_rows_use_canonical_recommendation_item_key_not_legacy_prefix(self):
        rows = [
            {"title": "同名作品", "media_type": "movie", "year": 1999},
            {"title": "同名作品", "media_type": "电影", "year": 2024},
        ]

        report = migrate_legacy_recommendations(rows, self.database)

        self.assertEqual(report.imported, 2)
        with self.database.connection() as connection:
            keys = [
                row["item_key"]
                for row in connection.execute("SELECT item_key FROM library_items ORDER BY item_key").fetchall()
            ]
        self.assertEqual(
            sorted(keys),
            sorted(recommendation_item_key(row) for row in rows),
        )
        self.assertTrue(all(not key.startswith("legacy:") for key in keys))


if __name__ == "__main__":
    unittest.main()
