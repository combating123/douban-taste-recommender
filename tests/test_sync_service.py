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
        value = "https://www.douban.com/people/272042071/?_dtcc=1&_i=fixture"
        self.assertEqual(normalize_douban_user(value), "272042071")

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
                        url="https://movie.douban.com/people/272042071/wish?start=15",
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
            {"user": "https://www.douban.com/people/272042071/", "include_wish": True},
            cookie="bid=secret-cookie-value",
        )
        status = self.wait_for_terminal(job_id)
        self.assertEqual(status["user_id"], "272042071")
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
                job_id = service.start({"user": "272042071"}, cookie=secret)
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
        self.assertEqual(active_user, "272042071")
        self.assertNotIn("secret-cookie-value", dump)

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
                job_id = service.start({"user": "272042071"})
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
        first_id = self.service.start({"user": "272042071"})
        self.wait_for_terminal(first_id)
        resumed_id = self.service.resume(first_id, cookie="session-only")
        self.wait_for_terminal(resumed_id)
        resume_call = self.calls[-1]
        self.assertEqual(resume_call["resume_starts"], {"wish": 15})
        self.assertEqual(len(resume_call["seed_items"]), 1)

    def test_sync_api_rejects_subscription_fields_and_never_echoes_cookie(self):
        api = SyncApi(self.service)
        with self.assertRaisesRegex(ValueError, "subscription"):
            api.create_job({"user": "272042071", "subscription": "https://example/sub"})
        payload = api.create_job({"user": "272042071", "cookie": "secret-cookie-value"})
        self.assertNotIn("secret-cookie-value", json.dumps(payload, ensure_ascii=False))


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
                        url="https://movie.douban.com/people/272042071/wish?start=15",
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
            payload={"user": "272042071", "cookie": "secret-cookie-value"},
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
                payload={"user": "272042071", "subscription": "https://example.com/api/v1/sub"},
            )

        self.assertEqual(status, 400)
        self.assertIn("subscription", payload["error"])
        self.assertEqual(len(errors), 1)
        self.assertTrue(errors[0].closed)


if __name__ == "__main__":
    unittest.main()
