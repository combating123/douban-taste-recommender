import base64
import json
import tempfile
import unittest
from pathlib import Path

from douban_recommender.catalog_registry import CatalogRegistry
from douban_recommender.database import AppDatabase
from douban_recommender.models import MediaItem


def derived_person_id(name: str) -> str:
    encoded = base64.urlsafe_b64encode(name.encode("utf-8")).decode("ascii").rstrip("=")
    return f"derived:{encoded}"


class CatalogRegistryTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()

    def tearDown(self):
        self.temp.cleanup()

    def register(self, items, now=100.0, user_id="272042071"):
        with self.database.connection() as connection:
            return CatalogRegistry.register_sync_items(connection, user_id, items, now)

    def test_collect_maps_to_watched_wish_maps_to_wish_and_watched_wins(self):
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, 'candidate', 'recommendation:candidate', 1, 1)
                """,
                (
                    "douban:101",
                    json.dumps(
                        {
                            "title": "Shared title",
                            "douban_id": "101",
                            "media_type": "movie",
                            "genres": ["Drama"],
                            "source": "recommendation:candidate",
                        }
                    ),
                ),
            )
        shared_wish = MediaItem(
            title="Shared title",
            douban_id="101",
            source="douban_user:wish",
            tags=["wish"],
            summary="weaker wish payload",
        )
        shared_watched = MediaItem(
            title="Shared title",
            douban_id="101",
            source="douban_user:collect",
            tags=["watched"],
            my_rating=5,
            summary="authoritative watched payload",
        )
        wish_only = MediaItem(
            title="Wish only",
            douban_id="102",
            source="douban_user:wish",
            tags=["wish"],
        )
        candidate = MediaItem(
            title="Candidate only",
            douban_id="103",
            source="recommendation:candidate",
        )

        report = self.register([shared_wish, candidate, shared_watched, wish_only])

        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT item_key, payload_json, state, source FROM library_items ORDER BY item_key"
            ).fetchall()
        by_key = {str(row["item_key"]): row for row in rows}
        self.assertEqual(report["library_items"], 3)
        self.assertEqual(by_key["douban:101"]["state"], "watched")
        self.assertEqual(by_key["douban:102"]["state"], "wish")
        self.assertEqual(by_key["douban:103"]["state"], "candidate")
        self.assertEqual(by_key["douban:101"]["source"], "douban_user:collect")
        self.assertEqual(
            json.loads(str(by_key["douban:101"]["payload_json"]))["summary"],
            "authoritative watched payload",
        )
        self.assertEqual(json.loads(str(by_key["douban:101"]["payload_json"]))["genres"], ["Drama"])

        self.register(
            [
                MediaItem(
                    title="Shared title",
                    douban_id="101",
                    source="douban_user:wish",
                    summary="later weaker payload",
                ),
                MediaItem(
                    title="Shared title",
                    douban_id="101",
                    source="recommendation:candidate",
                    summary="later candidate payload",
                ),
            ],
            now=200.0,
        )

        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT payload_json, state, source FROM library_items WHERE item_key='douban:101'"
            ).fetchone()
        self.assertEqual(row["state"], "watched")
        self.assertEqual(row["source"], "douban_user:collect")
        self.assertEqual(json.loads(str(row["payload_json"]))["summary"], "authoritative watched payload")

    def test_creates_deterministic_media_people_and_douban_provider_identities(self):
        item = MediaItem(
            title="Identity Film",
            year=2024,
            media_type="movie",
            countries=["China"],
            directors=["Director One"],
            casts=["Actor Two", "Director One"],
            douban_id="9001",
            url="https://movie.douban.com/subject/9001/?from=collect",
            source="douban_user:collect",
            raw={"aliases": ["Original Identity Film"]},
        )
        without_provider = MediaItem(
            title="Providerless Film",
            year=2020,
            media_type="movie",
            directors=["Director One"],
            source="douban_user:wish",
        )

        self.register([item, without_provider])
        self.register([without_provider, item], now=200.0)

        with self.database.connection() as connection:
            media_rows = connection.execute(
                "SELECT id, original_titles_json, metadata_json FROM media_identities ORDER BY id"
            ).fetchall()
            people_rows = connection.execute(
                "SELECT id, name, metadata_json FROM person_identities ORDER BY name"
            ).fetchall()
            provider_rows = connection.execute(
                """
                SELECT entity_kind, entity_id, provider, provider_id, confidence
                FROM provider_identities ORDER BY provider, provider_id
                """
            ).fetchall()

        self.assertEqual({str(row["id"]) for row in media_rows}, {item.identity, without_provider.identity})
        douban_media = next(row for row in media_rows if row["id"] == "douban:9001")
        self.assertEqual(json.loads(str(douban_media["original_titles_json"])), ["Original Identity Film"])
        self.assertEqual(json.loads(str(douban_media["metadata_json"]))["item_key"], "douban:9001")

        people = {str(row["name"]): row for row in people_rows}
        self.assertEqual(set(people), {"Actor Two", "Director One"})
        self.assertEqual(people["Actor Two"]["id"], derived_person_id("Actor Two"))
        self.assertEqual(people["Director One"]["id"], derived_person_id("Director One"))
        director_metadata = json.loads(str(people["Director One"]["metadata_json"]))
        self.assertEqual(director_metadata["roles"], ["cast", "director"])
        self.assertEqual(
            director_metadata["evidence_title_ids"],
            sorted([item.identity, without_provider.identity]),
        )

        self.assertEqual(len(provider_rows), 1)
        provider = provider_rows[0]
        self.assertEqual(
            (provider["entity_kind"], provider["entity_id"], provider["provider"], provider["provider_id"]),
            ("media", "douban:9001", "douban", "9001"),
        )
        self.assertEqual(provider["confidence"], 1.0)

    def test_repeated_registration_is_idempotent_and_records_active_profile(self):
        item = MediaItem(
            title="Idempotent Film",
            douban_id="7001",
            directors=["Director One"],
            casts=["Actor Two"],
            source="douban_user:collect",
        )

        first = self.register([item], now=10.0)
        second = self.register([item], now=20.0)

        with self.database.connection() as connection:
            counts = {
                table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                for table in (
                    "library_items",
                    "media_identities",
                    "person_identities",
                    "provider_identities",
                )
            }
            library_times = connection.execute(
                "SELECT created_at, updated_at FROM library_items WHERE item_key=?",
                (item.identity,),
            ).fetchone()
            active_user = connection.execute(
                "SELECT value FROM schema_meta WHERE key='active_douban_user_id'"
            ).fetchone()[0]

        self.assertEqual(first, second)
        self.assertEqual(
            counts,
            {
                "library_items": 1,
                "media_identities": 1,
                "person_identities": 2,
                "provider_identities": 1,
            },
        )
        self.assertEqual(library_times["created_at"], 10.0)
        self.assertEqual(library_times["updated_at"], 20.0)
        self.assertEqual(active_user, "272042071")

    def test_registry_does_not_commit_outside_the_callers_sync_transaction(self):
        item = MediaItem(
            title="Atomic Film",
            douban_id="8001",
            source="douban_user:collect",
        )

        with self.assertRaisesRegex(RuntimeError, "abort sync"):
            with self.database.connection() as connection:
                connection.execute(
                    """
                    INSERT INTO sync_jobs(id, user_id, state, request_json, result_json, created_at, updated_at)
                    VALUES('job-1', '272042071', 'running', '{}', '{}', 1, 1)
                    """
                )
                connection.execute(
                    """
                    INSERT INTO sync_items(job_id, item_key, payload_json, source, status)
                    VALUES('job-1', 'douban:8001', '{}', 'douban_user:collect', 'ready')
                    """
                )
                CatalogRegistry.register_sync_items(connection, "272042071", [item], 1.0)
                raise RuntimeError("abort sync")

        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sync_items").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM media_identities").fetchone()[0], 0)
            self.assertIsNone(
                connection.execute(
                    "SELECT value FROM schema_meta WHERE key='active_douban_user_id'"
                ).fetchone()
            )


if __name__ == "__main__":
    unittest.main()
