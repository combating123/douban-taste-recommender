import json
import sqlite3
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

from douban_recommender.catalog_api import CatalogApi
from douban_recommender.database import AppDatabase, SCHEMA_V1
from douban_recommender.models import recommendation_item_key
from douban_recommender.recommendation_service import RecommendationSessionService
from douban_recommender.runtime_paths import resolve_data_dir


class RuntimePathTests(unittest.TestCase):
    def test_explicit_data_dir_wins(self):
        with tempfile.TemporaryDirectory() as tmp:
            self.assertEqual(resolve_data_dir({"CINESCOPE_DATA_DIR": tmp}), Path(tmp).resolve())

    def test_relative_explicit_data_dir_is_resolved(self):
        value = resolve_data_dir({"CINESCOPE_DATA_DIR": "."})
        self.assertTrue(value.is_absolute())


class DatabaseTests(unittest.TestCase):
    EXPECTED_TABLES = {
        "schema_meta",
        "ui_snapshots",
        "recommendation_sessions",
        "recommendation_batches",
        "feedback_events",
        "media_identities",
        "person_identities",
        "provider_identities",
        "asset_files",
        "asset_candidates",
        "resolution_jobs",
        "user_asset_overrides",
    }

    def test_initialize_creates_versioned_core_tables(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AppDatabase(Path(tmp) / "cinescope.db")
            db.initialize()
            with db.connection() as conn:
                names = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='table'"
                    )
                }
                version = conn.execute(
                    "SELECT value FROM schema_meta WHERE key='version'"
                ).fetchone()[0]
                foreign_keys = conn.execute("PRAGMA foreign_keys").fetchone()[0]
                indexes = {
                    row[0]
                    for row in conn.execute(
                        "SELECT name FROM sqlite_master WHERE type='index'"
                    )
                }
            self.assertTrue(self.EXPECTED_TABLES <= names)
            self.assertEqual(version, str(AppDatabase.SCHEMA_VERSION))
            self.assertEqual(foreign_keys, 1)
            self.assertIn("idx_feedback_item_event_session_time", indexes)

    def test_ui_snapshot_round_trip_uses_json(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AppDatabase(Path(tmp) / "cinescope.db")
            db.initialize()
            db.upsert_ui_snapshot("primary", {"space": "tonight", "batch": 3})
            self.assertEqual(
                db.get_ui_snapshot("primary"),
                {"space": "tonight", "batch": 3},
            )

    def test_ui_snapshot_update_replaces_previous_payload(self):
        with tempfile.TemporaryDirectory() as tmp:
            db = AppDatabase(Path(tmp) / "cinescope.db")
            db.initialize()
            db.upsert_ui_snapshot("primary", {"space": "tonight"})
            db.upsert_ui_snapshot("primary", {"space": "health"})
            self.assertEqual(db.get_ui_snapshot("primary"), {"space": "health"})

    def _seed_legacy_identity_database(
        self,
        path: Path,
        *,
        identifier: str,
        legacy_key: str,
        include_canonical_conflict: bool = False,
    ) -> tuple[dict[str, object], str]:
        item = {
            "title": "Legacy external title",
            "year": 2024,
            "media_type": "movie",
            "douban_id": identifier,
            "item_key": legacy_key,
            "summary": "legacy summary",
        }
        canonical_key = recommendation_item_key(item)
        channels = {
            "电影": {
                "items": [item],
                "pool_size": 1,
                "matched_size": 1,
                "batch_size": 1,
                "cursor": 1,
                "active_batch": 1,
                "last_batch": 1,
                "excluded_keys": [legacy_key],
            }
        }
        batch_payload = {
            "items": [item],
            "pool_size": 1,
            "matched_size": 1,
            "visible_size": 1,
            "exhausted": True,
        }
        identity_id = legacy_key if include_canonical_conflict else "legacy-media"
        connection = sqlite3.connect(path)
        try:
            connection.executescript(SCHEMA_V1)
            connection.execute(
                """
                INSERT INTO recommendation_sessions(
                    id, profile_key, intent_json, channels_json, status, created_at, updated_at
                ) VALUES('legacy-session', 'profile-1', '{}', ?, 'active', 10, 10)
                """,
                (json.dumps(channels, ensure_ascii=False),),
            )
            connection.execute(
                """
                INSERT INTO recommendation_batches(
                    id, session_id, channel, batch_index, item_keys_json,
                    reason, payload_json, created_at
                ) VALUES('legacy-batch', 'legacy-session', '电影', 1, ?, '', ?, 11)
                """,
                (json.dumps([legacy_key]), json.dumps(batch_payload, ensure_ascii=False)),
            )
            connection.execute(
                """
                INSERT INTO feedback_events(
                    id, profile_key, session_id, item_key, event_type,
                    payload_json, undone_by, created_at
                ) VALUES('legacy-feedback', 'profile-1', 'legacy-session', ?, 'not-tonight', ?, NULL, 12)
                """,
                (legacy_key, json.dumps({"item": item}, ensure_ascii=False)),
            )
            connection.execute(
                """
                INSERT INTO library_items(
                    item_key, payload_json, state, source, created_at, updated_at
                ) VALUES(?, ?, 'watched', 'legacy', 9, 12)
                """,
                (legacy_key, json.dumps(item, ensure_ascii=False)),
            )
            if include_canonical_conflict and canonical_key != legacy_key:
                newer = dict(item)
                newer["item_key"] = canonical_key
                newer["summary"] = "newer canonical summary"
                connection.execute(
                    """
                    INSERT INTO library_items(
                        item_key, payload_json, state, source, created_at, updated_at
                    ) VALUES(?, ?, 'candidate', 'recommendation', 10, 20)
                    """,
                    (canonical_key, json.dumps(newer, ensure_ascii=False)),
                )
            connection.execute(
                """
                INSERT INTO media_identities(
                    id, title, original_titles_json, year, media_type,
                    countries_json, metadata_json, created_at, updated_at
                ) VALUES(?, ?, '[]', 2024, 'movie', '[]', ?, 9, 12)
                """,
                (identity_id, item["title"], json.dumps({"item_key": legacy_key})),
            )
            connection.execute(
                """
                INSERT INTO provider_identities(
                    entity_kind, entity_id, provider, provider_id, confidence,
                    metadata_json, created_at, updated_at
                ) VALUES('media', ?, 'legacy', ?, 1, ?, 9, 12)
                """,
                (identity_id, identifier, json.dumps({"item_key": legacy_key})),
            )
            connection.execute(
                """
                INSERT INTO asset_candidates(
                    id, entity_kind, entity_id, kind, source, url, confidence,
                    status, metadata_json, created_at, updated_at
                ) VALUES('legacy-candidate', 'media', ?, 'poster', 'legacy', '', 0,
                         'missing', '{}', 9, 12)
                """,
                (identity_id,),
            )
            connection.execute(
                """
                INSERT INTO resolution_jobs(
                    id, entity_kind, entity_id, kind, priority, state,
                    current_source, attempts_json, error, next_retry_at, created_at, updated_at
                ) VALUES('legacy-resolution', 'media', ?, 'poster', 0, 'done',
                         '', '[]', '', NULL, 9, 12)
                """,
                (identity_id,),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(
                    id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at
                ) VALUES('legacy-override', 'media', ?, 'poster', NULL, 'rejected', 9, 12)
                """,
                (identity_id,),
            )
            connection.commit()
        finally:
            connection.close()
        return item, canonical_key

    def test_initialize_preserves_safe_legacy_external_key_across_session_batch_feedback_and_catalog(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy-safe.db"
            item, key = self._seed_legacy_identity_database(
                path,
                identifier="movie-1",
                legacy_key="external:movie-1",
            )

            database = AppDatabase(path)
            database.initialize()
            service = RecommendationSessionService(database)
            restored = service.restore_session("legacy-session")
            batch = service.current_batch("legacy-session", "电影")
            replayed = service.apply_feedback("legacy-session", "not-tonight", key)
            title = CatalogApi(database).get_title(key)
            with database.connection() as connection:
                stored_item_keys = json.loads(
                    connection.execute(
                        "SELECT item_keys_json FROM recommendation_batches WHERE session_id='legacy-session'"
                    ).fetchone()[0]
                )

            self.assertEqual(key, "external:movie-1")
            self.assertEqual(stored_item_keys, [key])
            self.assertEqual(batch.item_keys, ())
            self.assertEqual(batch.items, ())
            self.assertEqual(restored.channels["电影"]["excluded_keys"], [key])
            self.assertNotEqual(replayed["event_id"], "legacy-feedback")
            self.assertEqual((title["title"], title["year"]), (item["title"], item["year"]))

    def test_initialize_migrates_unsafe_legacy_identity_across_relational_and_json_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy-unsafe.db"
            identifier = "provider/..\\title?x#y%2F"
            legacy_key = f"external:{identifier}"
            item, canonical_key = self._seed_legacy_identity_database(
                path,
                identifier=identifier,
                legacy_key=legacy_key,
                include_canonical_conflict=True,
            )

            database = AppDatabase(path)
            database.initialize()
            service = RecommendationSessionService(database)
            restored = service.restore_session("legacy-session")
            batch = service.current_batch("legacy-session", "电影")
            replayed = service.apply_feedback("legacy-session", "not-tonight", canonical_key)
            title = CatalogApi(database).get_title(canonical_key)
            with database.connection() as connection:
                library = connection.execute(
                    "SELECT item_key, payload_json, state FROM library_items"
                ).fetchall()
                feedback_key = connection.execute(
                    "SELECT item_key FROM feedback_events WHERE id = 'legacy-feedback'"
                ).fetchone()["item_key"]
                identity = connection.execute(
                    "SELECT id, metadata_json FROM media_identities"
                ).fetchone()
                provider = connection.execute(
                    "SELECT entity_id, metadata_json FROM provider_identities"
                ).fetchone()
                referenced_entity_ids = {
                    connection.execute(f"SELECT entity_id FROM {table}").fetchone()["entity_id"]
                    for table in ("asset_candidates", "resolution_jobs", "user_asset_overrides")
                }

            serialized = json.dumps(
                {
                    "channels": restored.channels,
                    "batch_keys": batch.item_keys,
                    "batch_items": batch.items,
                    "library": [dict(row) for row in library],
                    "feedback_key": feedback_key,
                    "identity": dict(identity),
                    "provider": dict(provider),
                    "referenced_entity_ids": sorted(referenced_entity_ids),
                },
                ensure_ascii=False,
            )
            self.assertNotEqual(canonical_key, legacy_key)
            self.assertNotIn(legacy_key, serialized)
            self.assertEqual(len(library), 1)
            self.assertEqual(library[0]["item_key"], canonical_key)
            self.assertEqual(library[0]["state"], "watched")
            self.assertEqual(json.loads(library[0]["payload_json"])["summary"], "newer canonical summary")
            self.assertEqual(identity["id"], canonical_key)
            self.assertEqual(provider["entity_id"], canonical_key)
            self.assertEqual(referenced_entity_ids, {canonical_key})
            self.assertEqual(restored.channels["电影"]["excluded_keys"], [canonical_key])
            self.assertNotEqual(replayed["event_id"], "legacy-feedback")
            self.assertEqual((title["title"], title["year"]), (item["title"], item["year"]))

    def test_legacy_identity_migration_is_idempotent(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "legacy-idempotent.db"
            identifier = "provider/title?unsafe"
            legacy_key = f"external:{identifier}"
            self._seed_legacy_identity_database(
                path,
                identifier=identifier,
                legacy_key=legacy_key,
                include_canonical_conflict=True,
            )
            database = AppDatabase(path)

            database.initialize()
            with database.connection() as connection:
                first = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in (
                        "library_items",
                        "media_identities",
                        "provider_identities",
                        "feedback_events",
                        "recommendation_sessions",
                        "recommendation_batches",
                    )
                }
            database.initialize()
            with database.connection() as connection:
                second = {
                    table: connection.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
                    for table in first
                }

            self.assertEqual(second, first)
            self.assertEqual(first["library_items"], 1)

    def test_identity_migration_rewrites_only_schema_identity_positions(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "schema-aware.db"
            legacy_key = "external:provider/foo"
            canonical_key = recommendation_item_key({"douban_id": "provider/foo"})
            connection = sqlite3.connect(path)
            try:
                connection.executescript(SCHEMA_V1)
                connection.execute("INSERT INTO schema_meta(key, value) VALUES('version', '3')")
                connection.execute(
                    "INSERT INTO ui_snapshots(key, payload_json, updated_at) VALUES('primary', ?, 1)",
                    (
                        json.dumps(
                            {
                                "note": legacy_key,
                                "items_by_key": {
                                    legacy_key: {"item_key": legacy_key, "title": "Mapped item"}
                                },
                            },
                            ensure_ascii=False,
                        ),
                    ),
                )
                connection.commit()
            finally:
                connection.close()

            database = AppDatabase(path)
            database.initialize()
            snapshot = database.get_ui_snapshot("primary")

            self.assertEqual(snapshot["note"], legacy_key)
            self.assertNotIn(legacy_key, snapshot["items_by_key"])
            self.assertEqual(snapshot["items_by_key"][canonical_key]["item_key"], canonical_key)

    def test_identity_migration_discovers_orphan_media_references(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "orphan-identities.db"
            legacy_key = "external:orphan/provider"
            canonical_key = recommendation_item_key({"douban_id": "orphan/provider"})
            connection = sqlite3.connect(path)
            try:
                connection.executescript(SCHEMA_V1)
                connection.execute("INSERT INTO schema_meta(key, value) VALUES('version', '3')")
                connection.execute(
                    """
                    INSERT INTO provider_identities(
                        entity_kind, entity_id, provider, provider_id, confidence,
                        metadata_json, created_at, updated_at
                    ) VALUES('media', ?, 'orphan', 'provider-id', 1, '{}', 1, 1)
                    """,
                    (legacy_key,),
                )
                connection.execute(
                    """
                    INSERT INTO asset_candidates(
                        id, entity_kind, entity_id, kind, source, url, confidence,
                        status, metadata_json, created_at, updated_at
                    ) VALUES('orphan-asset', 'media', ?, 'poster', 'test', '', 0, 'missing', '{}', 1, 1)
                    """,
                    (legacy_key,),
                )
                connection.execute(
                    """
                    INSERT INTO resolution_jobs(
                        id, entity_kind, entity_id, kind, priority, state,
                        current_source, attempts_json, error, next_retry_at, created_at, updated_at
                    ) VALUES('orphan-job', 'media', ?, 'poster', 0, 'done', '', '[]', '', NULL, 1, 1)
                    """,
                    (legacy_key,),
                )
                connection.execute(
                    """
                    INSERT INTO user_asset_overrides(
                        id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at
                    ) VALUES('orphan-override', 'media', ?, 'poster', NULL, 'rejected', 1, 1)
                    """,
                    (legacy_key,),
                )
                connection.commit()
            finally:
                connection.close()

            database = AppDatabase(path)
            database.initialize()
            with database.connection() as connection:
                entity_ids = {
                    connection.execute(f"SELECT entity_id FROM {table}").fetchone()["entity_id"]
                    for table in (
                        "provider_identities",
                        "asset_candidates",
                        "resolution_jobs",
                        "user_asset_overrides",
                    )
                }

            self.assertEqual(entity_ids, {canonical_key})

    def test_initialize_runs_v4_identity_migration_only_for_older_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "version-gate.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(SCHEMA_V1)
                connection.execute("INSERT INTO schema_meta(key, value) VALUES('version', '3')")
                connection.commit()
            finally:
                connection.close()

            from douban_recommender import migrations as migrations_module

            database = AppDatabase(path)
            with patch.object(
                migrations_module,
                "migrate_recommendation_item_keys",
                wraps=migrations_module.migrate_recommendation_item_keys,
            ) as migration:
                database.initialize()
                self.assertEqual(migration.call_count, 1)
                migration.reset_mock()
                database.initialize()
                migration.assert_not_called()

    def test_initialize_skips_v4_migration_for_current_schema(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "current-version.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(SCHEMA_V1)
                connection.execute(
                    "INSERT INTO schema_meta(key, value) VALUES('version', ?)",
                    (str(AppDatabase.SCHEMA_VERSION),),
                )
                connection.commit()
            finally:
                connection.close()

            with patch(
                "douban_recommender.migrations.migrate_recommendation_item_keys",
                side_effect=AssertionError("migration must be skipped"),
            ) as migration:
                AppDatabase(path).initialize()
                migration.assert_not_called()

    def test_failed_v4_migration_rolls_back_without_upgrading_version(self):
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "failed-version.db"
            connection = sqlite3.connect(path)
            try:
                connection.executescript(SCHEMA_V1)
                connection.execute("INSERT INTO schema_meta(key, value) VALUES('version', '3')")
                connection.commit()
            finally:
                connection.close()

            def fail_migration(connection):
                connection.execute(
                    "INSERT INTO ui_snapshots(key, payload_json, updated_at) VALUES('partial', '{}', 1)"
                )
                raise RuntimeError("migration failed")

            with patch(
                "douban_recommender.migrations.migrate_recommendation_item_keys",
                side_effect=fail_migration,
            ):
                with self.assertRaisesRegex(RuntimeError, "migration failed"):
                    AppDatabase(path).initialize()

            connection = sqlite3.connect(path)
            try:
                version = connection.execute(
                    "SELECT value FROM schema_meta WHERE key = 'version'"
                ).fetchone()[0]
                partial = connection.execute(
                    "SELECT COUNT(*) FROM ui_snapshots WHERE key = 'partial'"
                ).fetchone()[0]
            finally:
                connection.close()

            self.assertEqual(version, "3")
            self.assertEqual(partial, 0)


if __name__ == "__main__":
    unittest.main()
