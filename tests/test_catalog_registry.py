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

    def register(self, items, now=100.0, user_id="123456789"):
        with self.database.connection() as connection:
            return CatalogRegistry.register_sync_items(connection, user_id, items, now)

    def test_enriched_people_photo_map_replaces_stale_provider_placeholders(self):
        item_key = "douban:42"
        existing = MediaItem(
            title="Portrait cleanup",
            douban_id="42",
            directors=["Director A"],
            casts=["Actor B"],
            raw={
                "people_photos": {
                    "Director A": "https://img1.doubanio.com/f/vendors/pics/personage-default-medium.png",
                    "Actor B": "https://img1.doubanio.com/actor.jpg",
                }
            },
        )
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, 'candidate', 'test', 1, 1)
                """,
                (item_key, json.dumps(existing.__dict__, ensure_ascii=False)),
            )
            enriched = MediaItem(
                title="Portrait cleanup",
                douban_id="42",
                directors=["Director A"],
                casts=["Actor B"],
                raw={"people_photos": {"Actor B": "https://img1.doubanio.com/actor.jpg"}},
            )
            CatalogRegistry.register_enriched_item(connection, item_key, enriched, 2.0)
            row = connection.execute(
                "SELECT payload_json FROM library_items WHERE item_key=?",
                (item_key,),
            ).fetchone()

        photos = json.loads(str(row["payload_json"]))["raw"]["people_photos"]
        self.assertEqual({"Actor B": "https://img1.doubanio.com/actor.jpg"}, photos)

    def test_verified_douban_people_lists_replace_stale_library_people(self):
        item_key = "douban:1304102"
        existing = MediaItem(
            title="谍影重重",
            douban_id="1304102",
            directors=["捷克", "道格·里曼"],
            casts=["马特·达蒙", "弗朗卡·波滕特", "克里斯·库珀"],
            raw={},
        )
        enriched = MediaItem(
            title="谍影重重",
            douban_id="1304102",
            directors=["道格·里曼"],
            casts=["马特·达蒙", "弗朗卡·波滕特", "克里斯·库珀"],
            raw={"people_credit_source": "douban:1304102"},
        )

        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES(?, ?, 'watched', 'douban_user:collect', 1, 1)
                """,
                (item_key, json.dumps(existing.__dict__, ensure_ascii=False)),
            )
            CatalogRegistry.register_enriched_item(connection, item_key, enriched, 2.0)
            row = connection.execute(
                "SELECT payload_json FROM library_items WHERE item_key=?",
                (item_key,),
            ).fetchone()

        payload = json.loads(str(row["payload_json"]))
        self.assertEqual(["道格·里曼"], payload["directors"])
        self.assertEqual(["马特·达蒙", "弗朗卡·波滕特", "克里斯·库珀"], payload["casts"])

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
        self.assertEqual(by_key["douban:101"]["source"], "douban-sync:123456789:watched")
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
        self.assertEqual(row["source"], "douban-sync:123456789:watched")
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

    def test_person_identity_keeps_only_matching_credit_portrait_sources(self):
        item = MediaItem(
            title="Portrait source film",
            directors=["Director One"],
            casts=["Actor Two"],
            source="douban_user:collect",
            raw={
                "people_photos": {
                    "导演:Director One": "https://img9.doubanio.com/director.jpg",
                    "Actor Two": "https://upload.wikimedia.org/actor.jpg",
                    "剧照:Director One": "https://img9.doubanio.com/director-still.jpg",
                    "Unrelated Still": "https://img9.doubanio.com/wrong-film.jpg",
                }
            },
        )

        self.register([item])

        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT name, metadata_json FROM person_identities ORDER BY name"
            ).fetchall()
        metadata = {row["name"]: json.loads(row["metadata_json"]) for row in rows}
        self.assertEqual(
            metadata["Director One"]["portrait_source_urls"],
            ["https://img9.doubanio.com/director.jpg"],
        )
        self.assertEqual(
            metadata["Actor Two"]["portrait_source_urls"],
            ["https://upload.wikimedia.org/actor.jpg"],
        )
        self.assertNotIn("https://img9.doubanio.com/director-still.jpg", json.dumps(metadata))
        self.assertNotIn("https://img9.doubanio.com/wrong-film.jpg", json.dumps(metadata))

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
        self.assertEqual(active_user, "123456789")

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
                    VALUES('job-1', '123456789', 'running', '{}', '{}', 1, 1)
                    """
                )
                connection.execute(
                    """
                    INSERT INTO sync_items(job_id, item_key, payload_json, source, status)
                    VALUES('job-1', 'douban:8001', '{}', 'douban_user:collect', 'ready')
                    """
                )
                CatalogRegistry.register_sync_items(connection, "123456789", [item], 1.0)
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

    def test_switching_profiles_replaces_only_prior_synced_library_and_empty_sync_does_not_switch(self):
        first = MediaItem(title="First user title", douban_id="8101", source="douban_user:collect")
        second = MediaItem(title="Second user title", douban_id="8102", source="douban_user:wish")
        self.register([first], user_id="first-user")
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                VALUES('manual:keep', '{"title":"Manual keep"}', 'candidate', 'manual', 1, 1)
                """
            )

        self.register([], now=150.0, user_id="empty-user")
        with self.database.connection() as connection:
            active_after_empty = connection.execute(
                "SELECT value FROM schema_meta WHERE key='active_douban_user_id'"
            ).fetchone()[0]
        self.assertEqual(active_after_empty, "first-user")

        self.register([second], now=200.0, user_id="second-user")
        with self.database.connection() as connection:
            rows = connection.execute("SELECT item_key, source FROM library_items ORDER BY item_key").fetchall()
            active = connection.execute(
                "SELECT value FROM schema_meta WHERE key='active_douban_user_id'"
            ).fetchone()[0]
        self.assertEqual(active, "second-user")
        self.assertEqual([row["item_key"] for row in rows], ["douban:8102", "manual:keep"])
        self.assertTrue(str(rows[0]["source"]).startswith("douban-sync:second-user:"))

    def test_lower_state_richer_payload_merges_without_downgrading_state_or_source(self):
        watched = MediaItem(
            title="Merge title",
            douban_id="8201",
            my_rating=5,
            source="douban_user:collect",
        )
        self.register([watched])
        richer_candidate = MediaItem(
            title="Merge title",
            douban_id="8201",
            douban_rating=9.1,
            summary="Rich public synopsis",
            directors=["Director Rich"],
            source="recommendation:candidate",
        )

        self.register([richer_candidate], now=200.0)

        with self.database.connection() as connection:
            row = connection.execute(
                "SELECT payload_json, state, source FROM library_items WHERE item_key='douban:8201'"
            ).fetchone()
        payload = json.loads(row["payload_json"])
        self.assertEqual(row["state"], "watched")
        self.assertTrue(str(row["source"]).startswith("douban-sync:123456789:watched"))
        self.assertEqual(payload["my_rating"], 5)
        self.assertEqual(payload["douban_rating"], 9.1)
        self.assertEqual(payload["summary"], "Rich public synopsis")
        self.assertEqual(payload["directors"], ["Director Rich"])


if __name__ == "__main__":
    unittest.main()
