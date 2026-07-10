import tempfile
import unittest
from pathlib import Path

from douban_recommender.database import AppDatabase
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
            self.assertTrue(self.EXPECTED_TABLES <= names)
            self.assertEqual(version, str(AppDatabase.SCHEMA_VERSION))
            self.assertEqual(foreign_keys, 1)

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


if __name__ == "__main__":
    unittest.main()
