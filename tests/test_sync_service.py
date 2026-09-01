import json
import tempfile
import threading
import time
import unittest
import urllib.error
import urllib.request
from http.server import ThreadingHTTPServer
from pathlib import Path
from unittest import mock

from douban_recommender.catalog_registry import CatalogRegistry
from douban_recommender.auto_sync import AutoSyncCoordinator, SyncSettingsStore
from douban_recommender.crawler import CrawlResult, PageDiagnostic
from douban_recommender.database import AppDatabase
from douban_recommender.models import MediaItem
from douban_recommender.network_policy import (
    DEFAULT_SYNC_SAFETY_CAP,
    detect_local_http_proxy,
    normalize_douban_user,
    normalize_local_proxy_endpoint,
)
from douban_recommender.sync_api import SyncApi
from douban_recommender.sync_service import SyncService
from douban_recommender.web import Handler
import douban_recommender.web as web_module


class NetworkPolicyTests(unittest.TestCase):
    def test_profile_url_normalizes_user_id(self):
        value = "https://www.douban.com/people/123456789/?_dtcc=1&_i=fixture"
        self.assertEqual(normalize_douban_user(value), "123456789")

    def test_proxy_detection_only_returns_local_http_endpoint(self):
        endpoint = detect_local_http_proxy(lambda port: port == 7897)
        self.assertEqual(endpoint, "http://127.0.0.1:7897")

    def test_non_loopback_proxy_and_subscription_urls_are_rejected(self):
        with self.assertRaisesRegex(ValueError, "loopback"):
            normalize_local_proxy_endpoint("https://proxy.example.com:7890")
        with self.assertRaisesRegex(ValueError, "loopback"):
            normalize_local_proxy_endpoint("https://liangxin.example/api/v1/subscription")

    def test_default_sync_cap_is_high_safety_valve(self):
        self.assertGreaterEqual(DEFAULT_SYNC_SAFETY_CAP, 250)


class SyncServiceTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()
        self.calls = []

        def fake_crawler(**kwargs):
            self.calls.append(kwargs)
            return CrawlResult(
                items=[
                    MediaItem(
                        title="测试电影",
                        media_type="电影",
                        douban_id="100",
                        source="douban_user:collect",
                        tags=["看过"],
                    )
                ],
                pages_ok=1,
                pages_failed=1,
                errors=["wish start=15: temporary failure"],
                stopped_reason="部分分页抓取失败",
                diagnostics=[
                    PageDiagnostic(
                        status="wish",
                        start=15,
                        url="https://movie.douban.com/people/123456789/wish?start=15",
                        classification="network_error",
                        message="temporary failure",
                    )
                ],
            )

        self.service = SyncService(self.database, crawler=fake_crawler, max_workers=1)

    def tearDown(self):
        self.service.close()
        self.temp.cleanup()

    def wait_for_terminal(self, job_id, service=None):
        service = service or self.service
        deadline = time.time() + 3
        status = service.status(job_id)
        while status.get("state") in {"queued", "running"} and time.time() < deadline:
            time.sleep(0.02)
            status = service.status(job_id)
        return status

    def test_start_uses_safety_cap_persists_items_and_never_persists_cookie(self):
        job_id = self.service.start(
            {"user": "https://www.douban.com/people/123456789/", "include_wish": True},
            cookie="bid=secret-cookie-value",
        )
        status = self.wait_for_terminal(job_id)
        self.assertEqual(status["user_id"], "123456789")
        self.assertEqual(status["counts"]["items"], 1)
        self.assertEqual(self.calls[0]["max_pages"], DEFAULT_SYNC_SAFETY_CAP)
        self.assertEqual(self.calls[0]["cookie"], "bid=secret-cookie-value")
        with self.database.connection() as connection:
            stored = "\n".join(
                str(value)
                for row in connection.execute("SELECT request_json, result_json FROM sync_jobs")
                for value in row
            )
            item_count = connection.execute("SELECT COUNT(*) FROM sync_items").fetchone()[0]
        self.assertNotIn("secret-cookie-value", stored)
        self.assertEqual(item_count, 1)

    def test_short_cookie_values_do_not_corrupt_public_job_identifiers(self):
        fixed_job_id = "11111111111111111111111111111111"
        with mock.patch("douban_recommender.sync_service.uuid.uuid4") as uuid4:
            uuid4.return_value.hex = fixed_job_id
            job_id = self.service.start(
                {"user": "123456789"},
                cookie="bid=secret-cookie-value; push_noty_num=1",
            )

        status = self.wait_for_terminal(job_id)

        self.assertEqual(job_id, fixed_job_id)
        self.assertEqual(status["id"], fixed_job_id)
        self.assertEqual(status["user_id"], "123456789")
        serialized = json.dumps(status, ensure_ascii=False)
        self.assertNotIn("secret-cookie-value", serialized)

    def test_clear_history_removes_terminal_jobs_without_touching_library(self):
        first_id = self.service.start({"user": "123456789"})
        second_id = self.service.start({"user": "123456789"})
        self.wait_for_terminal(first_id)
        self.wait_for_terminal(second_id)

        result = self.service.clear_history()

        self.assertEqual(result["removed"], 2)
        self.assertEqual(self.service.status(first_id), {})
        self.assertEqual(self.service.status(second_id), {})
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sync_jobs").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sync_items").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0], 1)

    def test_completed_job_registers_library_and_identities_in_the_sync_items_transaction(self):
        secret = "bid=secret-cookie-value"

        def complete_crawler(**kwargs):
            return CrawlResult(
                items=[
                    MediaItem(
                        title="Registered Film",
                        media_type="movie",
                        douban_id="200",
                        source="douban_user:collect",
                        tags=["watched"],
                        directors=["Director One"],
                        casts=["Actor Two"],
                        summary=kwargs["cookie"].split("=", 1)[1],
                        raw={
                            "cookie": kwargs["cookie"],
                            "diagnostic": f"Cookie: {kwargs['cookie']}",
                        },
                    )
                ],
                pages_ok=1,
                pages_failed=0,
                stopped_reason=f"done with {kwargs['cookie']}",
                diagnostics=[
                    {
                        "classification": "ok_with_items",
                        "message": f"Cookie: {kwargs['cookie']}",
                        "cookie": kwargs["cookie"],
                    }
                ],
                completeness={
                    "is_complete": True,
                    "cookie": kwargs["cookie"],
                    "note": f"Cookie: {kwargs['cookie']}",
                },
            )

        service = SyncService(self.database, crawler=complete_crawler, max_workers=1)
        original_register = CatalogRegistry.register_sync_items
        observations = []

        def observing_register(connection, user_id, items, now):
            observations.append(
                (
                    connection.in_transaction,
                    connection.execute("SELECT COUNT(*) FROM sync_items").fetchone()[0],
                )
            )
            return original_register(connection, user_id, items, now)

        try:
            with mock.patch.object(CatalogRegistry, "register_sync_items", side_effect=observing_register):
                job_id = service.start({"user": "123456789"}, cookie=secret)
                status = self.wait_for_terminal(job_id, service=service)
        finally:
            service.close()

        self.assertEqual(status["state"], "complete")
        self.assertEqual(observations, [(True, 1)])
        with self.database.connection() as connection:
            dump = "\n".join(connection.iterdump())
            sync_count = connection.execute("SELECT COUNT(*) FROM sync_items").fetchone()[0]
            library = connection.execute(
                "SELECT item_key, state FROM library_items WHERE item_key='douban:200'"
            ).fetchone()
            media_count = connection.execute("SELECT COUNT(*) FROM media_identities").fetchone()[0]
            people_count = connection.execute("SELECT COUNT(*) FROM person_identities").fetchone()[0]
            provider = connection.execute(
                """
                SELECT entity_id, provider_id FROM provider_identities
                WHERE entity_kind='media' AND provider='douban'
                """
            ).fetchone()
            active_user = connection.execute(
                "SELECT value FROM schema_meta WHERE key='active_douban_user_id'"
            ).fetchone()[0]

        self.assertEqual(sync_count, 1)
        self.assertEqual((library["item_key"], library["state"]), ("douban:200", "watched"))
        self.assertEqual(media_count, 1)
        self.assertEqual(people_count, 2)
        self.assertEqual((provider["entity_id"], provider["provider_id"]), ("douban:200", "200"))
        self.assertEqual(active_user, "123456789")
        self.assertNotIn("secret-cookie-value", dump)

    def test_sync_enrichment_persists_synopsis_credits_and_portrait_sources_without_cookie(self):
        secret = "bid=visible-session-cookie"
        fetched = []

        def crawler(**_kwargs):
            return CrawlResult(
                items=[
                    MediaItem(
                        title="Enrichment Film",
                        media_type="电影",
                        douban_id="9201",
                        source="douban_user:collect",
                    )
                ],
                pages_ok=1,
            )

        def detail_fetcher(url, cookie=""):
            fetched.append((url, cookie))
            return b"detail"

        def detail_enricher(items, fetcher=None, limit=1, sleep_seconds=0, force_people_photos=False):
            self.assertEqual(fetcher("https://movie.douban.com/subject/9201/"), b"detail")
            self.assertEqual(limit, 1)
            self.assertTrue(force_people_photos)
            items[0].summary = "Persisted real synopsis"
            items[0].genres = ["剧情", "悬疑"]
            items[0].directors = ["导演甲"]
            items[0].casts = ["演员乙"]
            items[0].cover = "https://img9.doubanio.com/poster-9201.jpg"
            items[0].raw["people_photos"] = {
                "导演甲": "https://img9.doubanio.com/director-9201.jpg",
                "演员乙": "https://upload.wikimedia.org/actor-9201.jpg",
            }
            return items

        service = SyncService(
            self.database,
            crawler=crawler,
            detail_enricher=detail_enricher,
            detail_fetcher=detail_fetcher,
            enrich_limit=1,
            max_workers=1,
        )
        try:
            job_id = service.start({"user": "123456789"}, cookie=secret)
            status = self.wait_for_terminal(job_id, service=service)
        finally:
            service.close()

        self.assertEqual(status["enrichment"], {"attempted": 1, "enriched": 1})
        self.assertEqual(fetched, [("https://movie.douban.com/subject/9201/", secret)])
        with self.database.connection() as connection:
            library = json.loads(connection.execute(
                "SELECT payload_json FROM library_items WHERE item_key='douban:9201'"
            ).fetchone()[0])
            sync_item = json.loads(connection.execute(
                "SELECT payload_json FROM sync_items WHERE item_key='douban:9201'"
            ).fetchone()[0])
            people = {
                row["name"]: json.loads(row["metadata_json"])
                for row in connection.execute("SELECT name, metadata_json FROM person_identities")
            }
            dump = "\n".join(connection.iterdump())
        self.assertEqual(library["summary"], "Persisted real synopsis")
        self.assertEqual(sync_item["genres"], ["剧情", "悬疑"])
        self.assertEqual(
            people["导演甲"]["portrait_source_urls"],
            ["https://img9.doubanio.com/director-9201.jpg"],
        )
        self.assertNotIn(secret, dump)

    def test_sync_enrichment_counts_nested_people_photo_only_change(self):
        def crawler(**_kwargs):
            return CrawlResult(items=[MediaItem(title="Nested only", douban_id="9202", source="douban_user:collect")], pages_ok=1)

        def detail_enricher(items, **_kwargs):
            items[0].raw["people_photos"] = {"演员甲": "https://upload.wikimedia.org/actor.jpg"}
            return items

        service = SyncService(
            self.database,
            crawler=crawler,
            detail_enricher=detail_enricher,
            enrich_limit=1,
            max_workers=1,
        )
        try:
            job_id = service.start({"user": "123456789"})
            status = self.wait_for_terminal(job_id, service=service)
        finally:
            service.close()

        self.assertEqual(status["enrichment"], {"attempted": 1, "enriched": 1})

    def test_registry_failure_rolls_back_sync_items_and_marks_the_job_failed(self):
        def complete_crawler(**_kwargs):
            return CrawlResult(
                items=[
                    MediaItem(
                        title="Atomic Failure Film",
                        douban_id="201",
                        source="douban_user:collect",
                    )
                ],
                pages_ok=1,
            )

        service = SyncService(self.database, crawler=complete_crawler, max_workers=1)
        try:
            with mock.patch.object(
                CatalogRegistry,
                "register_sync_items",
                side_effect=RuntimeError("registry write failed"),
            ):
                job_id = service.start({"user": "123456789"})
                service.close()
            status = service.status(job_id)
        finally:
            service.close()

        self.assertEqual(status["state"], "failed")
        self.assertIn("registry write failed", status["errors"][-1])
        with self.database.connection() as connection:
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM sync_items").fetchone()[0], 0)
            self.assertEqual(connection.execute("SELECT COUNT(*) FROM library_items").fetchone()[0], 0)

    def test_resume_uses_failed_page_offsets_and_seed_items(self):
        first_id = self.service.start({"user": "123456789"})
        self.wait_for_terminal(first_id)
        resumed_id = self.service.resume(first_id, cookie="session-only")
        self.wait_for_terminal(resumed_id)
        resume_call = self.calls[-1]
        self.assertEqual(resume_call["resume_starts"], {"wish": 15})
        self.assertEqual(len(resume_call["seed_items"]), 1)

    def test_sync_api_rejects_subscription_fields_and_never_echoes_cookie(self):
        api = SyncApi(self.service)
        with self.assertRaisesRegex(ValueError, "subscription"):
            api.create_job({"user": "123456789", "subscription": "https://example/sub"})
        payload = api.create_job({"user": "123456789", "cookie": "secret-cookie-value"})
        self.assertNotIn("secret-cookie-value", json.dumps(payload, ensure_ascii=False))

    def test_complete_sync_reconciles_removed_items_and_allows_watched_to_wish_transition(self):
        snapshots = [
            CrawlResult(
                items=[
                    MediaItem(title="A", douban_id="501", source="douban_user:collect", tags=["看过"]),
                    MediaItem(title="B", douban_id="502", source="douban_user:wish", tags=["想看"]),
                ],
                pages_ok=2,
                completeness={"is_complete": True},
            ),
            CrawlResult(
                items=[MediaItem(title="A", douban_id="501", source="douban_user:wish", tags=["想看"])],
                pages_ok=2,
                completeness={"is_complete": True},
            ),
        ]

        def crawler(**_kwargs):
            return snapshots.pop(0)

        service = SyncService(self.database, crawler=crawler, max_workers=1)
        try:
            first = service.start({"user": "123456789"})
            self.wait_for_terminal(first, service)
            second = service.start({"user": "123456789"})
            self.assertEqual(self.wait_for_terminal(second, service)["state"], "complete")
        finally:
            service.close()

        with self.database.connection() as connection:
            rows = connection.execute(
                "SELECT item_key, state FROM library_items ORDER BY item_key"
            ).fetchall()
        self.assertEqual([(row["item_key"], row["state"]) for row in rows], [("douban:501", "wish")])

    def test_partial_sync_never_deletes_previous_complete_snapshot(self):
        snapshots = [
            CrawlResult(
                items=[MediaItem(title="A", douban_id="601", source="douban_user:collect", tags=["看过"])],
                pages_ok=1,
                completeness={"is_complete": True},
            ),
            CrawlResult(items=[], pages_ok=1, pages_failed=1, completeness={"is_complete": False}),
        ]
        service = SyncService(self.database, crawler=lambda **_kwargs: snapshots.pop(0), max_workers=1)
        try:
            self.wait_for_terminal(service.start({"user": "123456789"}), service)
            status = self.wait_for_terminal(service.start({"user": "123456789"}), service)
        finally:
            service.close()
        self.assertEqual(status["state"], "partial")
        with self.database.connection() as connection:
            row = connection.execute("SELECT state FROM library_items WHERE item_key='douban:601'").fetchone()
        self.assertIsNotNone(row)
        self.assertEqual(row["state"], "watched")


class AutoSyncTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()
        self.database.set_meta("active_douban_user_id", "123456789")

    def tearDown(self):
        self.temp.cleanup()

    def test_settings_inherit_saved_user_and_never_persist_or_return_cookie(self):
        store = SyncSettingsStore(self.database)

        settings = store.update({"enabled": True, "interval_minutes": 30, "cookie": "secret-cookie"})

        self.assertEqual(settings["user_id"], "123456789")
        self.assertTrue(settings["enabled"])
        self.assertEqual(settings["interval_minutes"], 30)
        with self.database.connection() as connection:
            dump = "\n".join(connection.iterdump())
        self.assertNotIn("secret-cookie", dump)
        self.assertNotIn("cookie", json.dumps(settings, ensure_ascii=False).casefold())

    def test_run_now_uses_saved_user_without_url_and_reuses_active_job(self):
        release = threading.Event()

        def crawler(**kwargs):
            release.wait(2)
            return CrawlResult(items=[], pages_ok=1, completeness={"is_complete": True})

        service = SyncService(self.database, crawler=crawler, max_workers=1)
        coordinator = AutoSyncCoordinator(
            self.database,
            service,
            settings_store=SyncSettingsStore(self.database),
            start_thread=False,
        )
        api = SyncApi(service, coordinator=coordinator)
        try:
            first = api.run_now()
            second = api.run_now()
            self.assertEqual(first["job_id"], second["job_id"])
            self.assertTrue(second["reused"])
            with self.database.connection() as connection:
                request = json.loads(connection.execute(
                    "SELECT request_json FROM sync_jobs WHERE id=?", (first["job_id"],)
                ).fetchone()[0])
            self.assertEqual(request["user_id"], "123456789")
            self.assertNotIn("cookie", request)
        finally:
            release.set()
            service.close()

    def test_run_now_reuses_needs_cookie_job_instead_of_creating_duplicates(self):
        calls = []

        class Service:
            database = self.database

            def active_job_id(self, _user_id):
                return ""

            def status(self, job_id):
                self.last_status_id = job_id
                return {"id": job_id, "state": "needs_cookie", "user_id": "123456789", "resume_of": ""}

            def start(self, payload, cookie=""):
                calls.append(("start", payload, cookie))
                return "unexpected-new-job"

            def resume(self, job_id, cookie=""):
                calls.append(("resume", job_id, cookie))
                return "unexpected-resume"

        store = SyncSettingsStore(self.database, now=lambda: 1000.0)
        store.mark_started("blocked-job")
        store.mark_terminal("blocked-job", "needs_cookie")
        coordinator = AutoSyncCoordinator(
            self.database, Service(), settings_store=store, now=lambda: 1000.0, start_thread=False
        )

        result = coordinator.run_now()

        self.assertEqual(result["job_id"], "blocked-job")
        self.assertEqual(result["state"], "needs_cookie")
        self.assertTrue(result["reused"])
        self.assertTrue(result["authorization_required"])
        self.assertEqual(calls, [])

    def test_run_now_resumes_failed_pages_with_saved_browser_session(self):
        calls = []

        class Service:
            database = self.database

            def active_job_id(self, _user_id):
                return ""

            def status(self, job_id):
                return {"id": job_id, "state": "needs_cookie", "user_id": "123456789", "resume_of": ""}

            def start(self, payload, cookie=""):
                calls.append(("start", payload, cookie))
                return "unexpected-new-job"

            def resume(self, job_id, cookie=""):
                calls.append(("resume", job_id, cookie))
                return "resumed-job"

        store = SyncSettingsStore(self.database, now=lambda: 1000.0)
        store.mark_started("blocked-job")
        store.mark_terminal("blocked-job", "needs_cookie")
        coordinator = AutoSyncCoordinator(
            self.database, Service(), settings_store=store, now=lambda: 1000.0, start_thread=False
        )
        coordinator.cookie_provider = lambda: "dbcl2=encrypted-session; ck=abc"

        result = coordinator.run_now()

        self.assertEqual(result["job_id"], "resumed-job")
        self.assertTrue(result["resumed"])
        self.assertEqual(calls, [("resume", "blocked-job", "dbcl2=encrypted-session; ck=abc")])
        self.assertNotIn("encrypted-session", json.dumps(result, ensure_ascii=False))

    def test_tick_launches_browser_authorization_only_once_for_blocked_job(self):
        launches = []

        class Service:
            database = self.database

            def active_job_id(self, _user_id):
                return ""

            def status(self, job_id):
                return {"id": job_id, "state": "needs_cookie", "user_id": "123456789", "resume_of": ""}

        store = SyncSettingsStore(self.database, now=lambda: 1000.0)
        store.mark_started("blocked-job")
        store.mark_terminal("blocked-job", "needs_cookie")
        coordinator = AutoSyncCoordinator(
            self.database, Service(), settings_store=store, now=lambda: 1000.0, start_thread=False
        )
        coordinator.authorization_launcher = lambda user_id, job_id: launches.append((user_id, job_id)) or {"state": "waiting_for_login"}

        first = coordinator.tick()
        second = coordinator.tick()

        self.assertEqual(first["state"], "waiting_for_login")
        self.assertEqual(second["state"], "waiting_for_login")
        self.assertEqual(launches, [("123456789", "blocked-job")])

    def test_sync_api_exposes_browser_authorization_without_cookie_input(self):
        service = mock.Mock()
        service.database = self.database
        coordinator = mock.Mock()
        coordinator.settings_store = SyncSettingsStore(self.database)
        browser_auth = mock.Mock()
        browser_auth.status.return_value = {"state": "idle", "has_session": False}
        api = SyncApi(service, coordinator=coordinator, browser_auth=browser_auth)

        status = api.get_browser_authorization()
        started = api.start_browser_authorization({})

        self.assertEqual(status["state"], "idle")
        browser_auth.start.assert_called_once()
        self.assertNotIn("cookie", json.dumps(started, ensure_ascii=False).casefold())

    def test_due_tick_starts_anonymous_sync_and_updates_schedule(self):
        calls = []

        class Service:
            database = self.database

            def active_job_id(self, user_id):
                return ""

            def start(self, payload, cookie=""):
                calls.append((payload, cookie))
                return "job-1"

            def status(self, _job_id):
                return {"state": "queued"}

        store = SyncSettingsStore(self.database, now=lambda: 1000.0)
        store.update({"enabled": True, "interval_minutes": 60, "next_run_at": 0})
        coordinator = AutoSyncCoordinator(
            self.database,
            Service(),
            settings_store=store,
            now=lambda: 1000.0,
            start_thread=False,
        )

        result = coordinator.tick()

        self.assertEqual(result["job_id"], "job-1")
        self.assertEqual(calls, [({"user": "123456789", "max_pages": DEFAULT_SYNC_SAFETY_CAP, "include_wish": True, "include_do": False}, "")])
        self.assertGreater(store.get()["next_run_at"], 1000.0)


class SyncApiRouteTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.database = AppDatabase(Path(self.temp.name) / "cinescope.db")
        self.database.initialize()

        def fake_crawler(**kwargs):
            return CrawlResult(
                items=[MediaItem(title="测试电影", media_type="电影", douban_id="100", source="douban_user:collect")],
                pages_ok=1,
                pages_failed=1,
                errors=["wish start=15: temporary failure"],
                stopped_reason="部分分页抓取失败",
                diagnostics=[
                    PageDiagnostic(
                        status="wish",
                        start=15,
                        url="https://movie.douban.com/people/123456789/wish?start=15",
                        classification="network_error",
                        message="temporary failure",
                    )
                ],
            )

        self.service = SyncService(self.database, crawler=fake_crawler, max_workers=1)
        self.api = SyncApi(self.service)
        self.original_sync_api = getattr(web_module, "SYNC_API", None)
        web_module.SYNC_API = self.api
        self.server = ThreadingHTTPServer(("127.0.0.1", 0), Handler)
        self.port = self.server.server_address[1]
        self.thread = threading.Thread(target=self.server.serve_forever, daemon=True)
        self.thread.start()

    def tearDown(self):
        self.server.shutdown()
        self.server.server_close()
        web_module.SYNC_API = self.original_sync_api
        self.service.close()
        self.temp.cleanup()

    def request(self, path, method="GET", payload=None):
        data = None
        headers = {}
        if payload is not None:
            data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
            headers["Content-Type"] = "application/json"
        request = urllib.request.Request(
            f"http://127.0.0.1:{self.port}{path}",
            data=data,
            headers=headers,
            method=method,
        )
        try:
            with urllib.request.urlopen(request, timeout=5) as response:
                return response.status, json.loads(response.read().decode("utf-8"))
        except urllib.error.HTTPError as error:
            try:
                return error.code, json.loads(error.read().decode("utf-8"))
            finally:
                error.close()

    def wait_for_terminal(self, job_id):
        deadline = time.time() + 3
        status = self.service.status(job_id)
        while status.get("state") in {"queued", "running"} and time.time() < deadline:
            time.sleep(0.02)
            status = self.service.status(job_id)
        return status

    def test_v2_sync_routes_create_report_and_resume_without_cookie_echo(self):
        status, created = self.request(
            "/api/v2/sync/jobs",
            method="POST",
            payload={"user": "123456789", "cookie": "secret-cookie-value"},
        )
        self.assertEqual(status, 200)
        self.assertNotIn("secret-cookie-value", json.dumps(created, ensure_ascii=False))
        first_id = created["job_id"]
        self.wait_for_terminal(first_id)

        status, report = self.request(f"/api/v2/sync/jobs/{first_id}")
        self.assertEqual(status, 200)
        self.assertEqual(report["counts"]["items"], 1)

        status, resumed = self.request(
            f"/api/v2/sync/jobs/{first_id}/resume",
            method="POST",
            payload={"cookie": "second-session-secret"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(resumed["resume_of"], first_id)
        self.assertNotIn("second-session-secret", json.dumps(resumed, ensure_ascii=False))

    def test_v2_sync_history_can_be_cleared(self):
        status, created = self.request(
            "/api/v2/sync/jobs",
            method="POST",
            payload={"user": "123456789"},
        )
        self.assertEqual(status, 200)
        self.wait_for_terminal(created["job_id"])

        status, payload = self.request("/api/v2/sync/jobs", method="DELETE")

        self.assertEqual(status, 200)
        self.assertEqual(payload["removed"], 1)

    def test_v2_sync_route_rejects_subscription_url_as_bad_request(self):
        errors = []
        original_urlopen = urllib.request.urlopen

        def recording_urlopen(*args, **kwargs):
            try:
                return original_urlopen(*args, **kwargs)
            except urllib.error.HTTPError as error:
                errors.append(error)
                raise

        with mock.patch("urllib.request.urlopen", side_effect=recording_urlopen):
            status, payload = self.request(
                "/api/v2/sync/jobs",
                method="POST",
                payload={"user": "123456789", "subscription": "https://example.com/api/v1/sub"},
            )

        self.assertEqual(status, 400)
        self.assertIn("subscription", payload["error"])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].closed)

    def test_v2_auto_sync_settings_and_run_now_need_no_profile_or_cookie(self):
        self.database.set_meta("active_douban_user_id", "123456789")

        status, settings = self.request("/api/v2/sync/settings")
        self.assertEqual(status, 200)
        self.assertEqual(settings["user_id"], "123456789")
        self.assertNotIn("cookie", json.dumps(settings, ensure_ascii=False).casefold())

        status, updated = self.request(
            "/api/v2/sync/settings",
            method="PUT",
            payload={"enabled": True, "interval_minutes": 30, "cookie": "must-not-persist"},
        )
        self.assertEqual(status, 200)
        self.assertEqual(updated["interval_minutes"], 30)
        self.assertNotIn("cookie", json.dumps(updated, ensure_ascii=False).casefold())

        status, started = self.request("/api/v2/sync/run-now", method="POST", payload={})
        self.assertEqual(status, 200)
        self.assertEqual(started["user_id"], "123456789")
        self.assertTrue(started["job_id"])

    def test_v2_browser_authorization_routes_need_no_cookie_payload(self):
        self.database.set_meta("active_douban_user_id", "123456789")
        self.api.settings_store.update({"user_id": "123456789", "enabled": True})
        browser_auth = mock.Mock()
        browser_auth.status.return_value = {"state": "idle", "has_session": False}
        browser_auth.start.return_value = {
            "state": "waiting_for_login",
            "has_session": False,
            "user_id": "123456789",
            "job_id": "blocked-job",
        }
        self.api.browser_auth = browser_auth

        status, current = self.request("/api/v2/sync/browser-auth")
        self.assertEqual(status, 200)
        self.assertEqual(current["state"], "idle")

        status, started = self.request("/api/v2/sync/browser-auth", method="POST", payload={})
        self.assertEqual(status, 200)
        self.assertEqual(started["state"], "waiting_for_login")
        self.assertNotIn("cookie", json.dumps(started, ensure_ascii=False).casefold())
        browser_auth.start.assert_called_once_with("123456789", "")


    def test_v2_browser_authorization_status_preserves_session_availability_without_secret(self):
        self.database.set_meta("active_douban_user_id", "123456789")
        self.api.settings_store.update({"user_id": "123456789", "enabled": True})
        browser_auth = mock.Mock()
        browser_auth.status.return_value = {
            "state": "authorized",
            "has_session": True,
            "user_id": "123456789",
            "error": "cookie=dbcl2=browser-session-secret",
        }
        self.api.browser_auth = browser_auth

        status, current = self.request("/api/v2/sync/browser-auth")
        self.assertEqual(status, 200)
        self.assertIs(current["has_session"], True)

        status, settings = self.request("/api/v2/sync/settings")
        self.assertEqual(status, 200)
        self.assertIs(settings["authorization"]["has_session"], True)
        serialized = json.dumps({"current": current, "settings": settings}, ensure_ascii=False)
        self.assertNotIn("browser-session-secret", serialized)


if __name__ == "__main__":
    unittest.main()
