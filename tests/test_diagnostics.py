import hashlib
import io
import json
import os
import tempfile
import threading
import unittest
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from PIL import Image

from douban_recommender.database import AppDatabase
from douban_recommender.diagnostics import MediaAudit, audit_recommendation_media, build_diagnostics
from douban_recommender.media.store import MediaStore
from douban_recommender.media.validator import validate_image_bytes
from douban_recommender.web import Handler
import douban_recommender.diagnostics as diagnostics_module
import douban_recommender.web as web_module


def png_bytes(color="navy"):
    output = io.BytesIO()
    Image.new("RGB", (180, 270), color).save(output, format="PNG")
    return output.getvalue()


class MediaAuditTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = AppDatabase(self.root / "cinescope.db")
        self.db.initialize()
        self.store = MediaStore(self.root / "media", self.db)

    def tearDown(self):
        self.temp.cleanup()

    def put_asset(self, color="navy", kind="poster"):
        return self.store.put(
            validate_image_bytes(png_bytes(color)),
            f"https://images.invalid/{color}.png",
            kind,
        )

    def row(self, cover, status="ready", **extra):
        return {
            "title": extra.pop("title", "Audit title"),
            "cover": cover,
            "media_status": {"poster": status},
            **extra,
        }

    def test_real_png_with_consistent_ready_poster_manifest_is_ready(self):
        asset = self.put_asset()
        audit = audit_recommendation_media([self.row(asset.local_url)], self.db)
        self.assertEqual(
            audit,
            MediaAudit(total=1, ready=1, degraded=0, ambiguous=0, missing=0, wrong_identity_candidates=0),
        )

    def test_empty_external_invalid_and_unmanifested_covers_are_missing(self):
        absent = "/media/" + ("f" * 64) + ".png"
        rows = [
            self.row(""),
            self.row("https://images.invalid/poster.png"),
            self.row("/media/not-a-sha.png"),
            self.row(absent),
        ]
        audit = audit_recommendation_media(rows, self.db)
        self.assertEqual((audit.total, audit.missing), (4, 4))
        self.assertEqual(audit.ready + audit.degraded + audit.ambiguous + audit.missing, audit.total)

    def test_nonready_wrongkind_and_corrupt_local_manifests_are_degraded(self):
        nonready = self.put_asset("red")
        wrongkind = self.put_asset("green", kind="portrait")
        corrupt = self.put_asset("blue")
        with self.db.connection() as connection:
            connection.execute("UPDATE asset_files SET status = 'degraded' WHERE asset_id = ?", (nonready.asset_id,))
        corrupt.path.write_bytes(b"not-a-png")

        audit = audit_recommendation_media(
            [self.row(nonready.local_url), self.row(wrongkind.local_url), self.row(corrupt.local_url)],
            self.db,
        )
        self.assertEqual((audit.total, audit.degraded), (3, 3))
        self.assertEqual(audit.ready + audit.degraded + audit.ambiguous + audit.missing, audit.total)

    def test_explicit_ambiguous_status_or_evidence_is_ambiguous(self):
        first = self.put_asset("purple")
        second = self.put_asset("orange")
        third = self.put_asset("yellow")
        rows = [
            self.row(first.local_url, status="ambiguous"),
            self.row(
                second.local_url,
                status="ready",
                media_evidence={"poster": {"classification": "ambiguous"}},
            ),
            self.row(
                third.local_url,
                status="ready",
                evidence={"poster": {"ambiguous": True}},
            ),
        ]
        audit = audit_recommendation_media(rows, self.db)
        self.assertEqual((audit.total, audit.ambiguous), (3, 3))
        self.assertEqual(audit.ready + audit.degraded + audit.ambiguous + audit.missing, audit.total)

    def test_wrong_identity_candidates_require_identity_rejection_and_hard_conflict(self):
        attempts = [
            {"source": "tmdb", "status": "identity-rejected", "reasons": ["year-conflict"], "candidate_url": "https://secret.invalid/a"},
            {"source": "tmdb", "status": "identity-rejected", "reasons": ["title", "media-type"]},
            {"source": "tvmaze", "status": "asset-rejected", "reasons": ["title-conflict"]},
            {"source": "anilist", "status": "identity-rejected", "reasons": ["name-conflict"]},
            {"source": "jikan", "status": "identity-rejected", "reasons": ["director"]},
        ]
        with self.db.connection() as connection:
            connection.execute(
                """
                INSERT INTO resolution_jobs(
                    id, entity_kind, entity_id, kind, priority, state,
                    current_source, attempts_json, error, next_retry_at,
                    created_at, updated_at
                ) VALUES('job-a', 'media', 'title:a', 'poster', 0, 'degraded', '', ?, '', NULL, 1, 1)
                """,
                (json.dumps(attempts),),
            )
        audit = audit_recommendation_media([], self.db)
        self.assertEqual(audit.wrong_identity_candidates, 2)


class DiagnosticsPayloadTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.db = AppDatabase(self.root / "private" / "cinescope-secret.db")
        self.db.initialize()
        self.store = MediaStore(self.db.path.parent / "media", self.db)
        self.asset = self.store.put(
            validate_image_bytes(png_bytes()),
            "https://images.invalid/poster.png?token=source-secret",
            "poster",
        )
        self.cache_dir = self.root / "cache"
        self.cache_dir.mkdir()
        (self.cache_dir / "public.json").write_bytes(b"12345")
        self._seed_database()

    def tearDown(self):
        self.temp.cleanup()

    def _seed_database(self):
        attempts = [
            {"source": "tmdb", "status": "ready", "candidate_url": "https://candidate.invalid/secret"},
            {"source": "tmdb", "status": "identity-rejected", "reasons": ["title-conflict"]},
            {"source": "unknown-secret-provider", "status": "provider-error", "error": "provider-secret"},
        ]
        batch = {
            "items": [
                {"title": "Ready", "cover": self.asset.local_url, "media_status": {"poster": "ready"}},
                {"title": "Missing", "cover": "", "media_status": {"poster": "missing"}},
            ]
        }
        with self.db.connection() as connection:
            connection.execute(
                """
                INSERT INTO sync_jobs(id, user_id, state, request_json, result_json, error, created_at, updated_at)
                VALUES('sync-a', 'public-user', 'complete', ?, ?, ?, 1, 1)
                """,
                (
                    json.dumps({"cookie": "cookie-secret", "headers": {"Authorization": "header-secret"}}),
                    json.dumps({"token": "result-secret"}),
                    "exception-secret",
                ),
            )
            connection.execute(
                "INSERT INTO sync_items(job_id, item_key, payload_json, source, status) VALUES('sync-a', 'douban:1', '{}', '', 'ready')"
            )
            connection.execute(
                """
                INSERT INTO recommendation_sessions(id, profile_key, intent_json, channels_json, status, created_at, updated_at)
                VALUES('session-a', 'default', '{}', '{}', 'active', 1, 1)
                """
            )
            connection.execute(
                """
                INSERT INTO recommendation_batches(id, session_id, channel, batch_index, item_keys_json, reason, payload_json, created_at)
                VALUES('batch-a', 'session-a', 'top', 0, '["douban:1","douban:2"]', '', ?, 1)
                """,
                (json.dumps(batch),),
            )
            connection.execute(
                """
                INSERT INTO resolution_jobs(
                    id, entity_kind, entity_id, kind, priority, state,
                    current_source, attempts_json, error, next_retry_at,
                    created_at, updated_at
                ) VALUES('media-a', 'media', 'title:a', 'poster', 0, 'degraded', '', ?, 'queue-secret', NULL, 1, 1)
                """,
                (json.dumps(attempts),),
            )

    def test_build_diagnostics_returns_only_fixed_allowlisted_aggregates(self):
        with mock.patch.object(diagnostics_module.metadata, "version", return_value="9.8.7"):
            payload = build_diagnostics(
                {
                    "cookie": "argument-cookie-secret",
                    "tmdb_api_key": "argument-api-key-secret",
                    "headers": {"Authorization": "argument-header-secret"},
                    "env": {"SECRET_TOKEN": "argument-env-secret"},
                },
                db=self.db,
                cache_dir=self.cache_dir,
            )

        self.assertEqual(
            set(payload),
            {
                "schema_version",
                "app_version",
                "database_schema_version",
                "database_path_hash",
                "sync_counts",
                "session_counts",
                "batch_counts",
                "provider_attempt_health",
                "persistent_queue_states",
                "cache_bytes",
                "media_totals",
                "media_audit",
                "observability",
            },
        )
        self.assertEqual(payload["app_version"], "9.8.7")
        self.assertEqual(payload["database_schema_version"], AppDatabase.SCHEMA_VERSION)
        self.assertRegex(payload["database_path_hash"], r"^[0-9a-f]{64}$")
        self.assertEqual(payload["sync_counts"]["jobs_total"], 1)
        self.assertEqual(payload["sync_counts"]["items_total"], 1)
        self.assertEqual(payload["session_counts"]["total"], 1)
        self.assertEqual(payload["batch_counts"], {"total": 1, "recommendation_rows": 2})
        self.assertEqual(payload["provider_attempt_health"]["basis"], "historical_attempts")
        self.assertEqual(payload["provider_attempt_health"]["attempts_total"], 3)
        self.assertEqual(payload["persistent_queue_states"]["degraded"], 1)
        self.assertEqual(payload["cache_bytes"], 5)
        self.assertEqual(payload["media_totals"]["assets_total"], 1)
        self.assertEqual(payload["media_audit"]["ready"], 1)
        self.assertEqual(payload["media_audit"]["missing"], 1)
        self.assertEqual(payload["media_audit"]["wrong_identity_candidates"], 1)
        self.assertEqual(payload["observability"]["in_memory_queue_depth"], "unknown")
        self.assertEqual(payload["observability"]["recommendation_media_identity_attribution"], "unknown")

        text = json.dumps(payload, ensure_ascii=False, sort_keys=True)
        for forbidden in (
            str(self.db.path),
            "cookie-secret",
            "api-key-secret",
            "header-secret",
            "env-secret",
            "result-secret",
            "exception-secret",
            "candidate.invalid",
            "source-secret",
            "queue-secret",
            "unknown-secret-provider",
            "Authorization",
            "SECRET_TOKEN",
        ):
            self.assertNotIn(forbidden, text)
        self.assertIn('"session_counts"', text)

    def test_redaction_only_call_accepts_untrusted_context_without_exposing_it(self):
        payload = build_diagnostics(
            {
                "cookie": "context-cookie-secret",
                "tmdb_api_key": "context-key-secret",
                "headers": {"X-Token": "context-header-secret"},
                "env": {"API_TOKEN": "context-env-secret"},
            }
        )
        text = json.dumps(payload, ensure_ascii=False)
        self.assertEqual(payload["schema_version"], 2)
        for forbidden in ("context-cookie-secret", "context-key-secret", "context-header-secret", "context-env-secret"):
            self.assertNotIn(forbidden, text)

    def test_unavailable_version_cache_and_in_memory_queue_are_unknown(self):
        with (
            mock.patch.object(diagnostics_module.metadata, "version", side_effect=RuntimeError("version-secret")),
            mock.patch.object(diagnostics_module, "_cache_bytes", side_effect=PermissionError("cache-secret")),
        ):
            payload = build_diagnostics(db=self.db, cache_dir=self.cache_dir)
        self.assertEqual(payload["app_version"], "unknown")
        self.assertEqual(payload["cache_bytes"], "unknown")
        self.assertEqual(payload["observability"]["cache_bytes"], "unknown")
        self.assertEqual(payload["observability"]["in_memory_queue_depth"], "unknown")
        self.assertNotIn("secret", json.dumps(payload, ensure_ascii=False))

    def test_missing_database_returns_unknown_without_creating_files_or_directories(self):
        missing_path = self.root / "not-created" / "runtime.db"
        payload = build_diagnostics(db=AppDatabase(missing_path), cache_dir=self.root / "missing-cache")
        self.assertFalse(missing_path.parent.exists())
        self.assertEqual(payload["database_schema_version"], "unknown")
        self.assertEqual(payload["sync_counts"], "unknown")
        self.assertEqual(payload["media_audit"], "unknown")
        self.assertEqual(payload["cache_bytes"], 0)


class DiagnosticsRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.root = Path(self.temp.name)
        self.data_dir = self.root / "data"
        self.db = AppDatabase(self.data_dir / "cinescope.db")
        self.db.initialize()
        self.original_data_dir = os.environ.get("CINESCOPE_DATA_DIR")
        os.environ["CINESCOPE_DATA_DIR"] = str(self.data_dir)
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        self.thread.join(timeout=5)
        if self.original_data_dir is None:
            os.environ.pop("CINESCOPE_DATA_DIR", None)
        else:
            os.environ["CINESCOPE_DATA_DIR"] = self.original_data_dir
        self.temp.cleanup()

    def request(self):
        request = urllib.request.Request(f"http://127.0.0.1:{self.port}/api/v2/diagnostics", method="GET")
        with urllib.request.urlopen(request, timeout=5) as response:
            return response.status, json.loads(response.read().decode("utf-8"))

    def test_get_diagnostics_is_200_and_does_not_modify_database_or_queue_state(self):
        before_files = {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        status, payload = self.request()
        after_files = {
            path.relative_to(self.root).as_posix(): hashlib.sha256(path.read_bytes()).hexdigest()
            for path in self.root.rglob("*")
            if path.is_file()
        }
        self.assertEqual(status, 200)
        self.assertEqual(before_files, after_files)
        self.assertEqual(payload["persistent_queue_states"]["queued"], 0)

    def test_get_diagnostics_does_not_create_missing_runtime_directory(self):
        missing = self.root / "missing-runtime"
        os.environ["CINESCOPE_DATA_DIR"] = str(missing)
        status, payload = self.request()
        self.assertEqual(status, 200)
        self.assertFalse(missing.exists())
        self.assertEqual(payload["sync_counts"], "unknown")

    def test_route_failure_returns_fixed_unknown_payload_without_exception_text(self):
        with mock.patch.object(web_module, "build_diagnostics", side_effect=RuntimeError("token=route-secret")):
            status, payload = self.request()
        self.assertEqual(status, 200)
        self.assertEqual(payload["sync_counts"], "unknown")
        self.assertNotIn("route-secret", json.dumps(payload, ensure_ascii=False))


if __name__ == "__main__":
    unittest.main()
