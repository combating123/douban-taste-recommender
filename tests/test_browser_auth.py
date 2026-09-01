import json
import tempfile
import threading
import time
import unittest
from pathlib import Path


class BrowserAuthTests(unittest.TestCase):
    @staticmethod
    def browser_auth_module():
        try:
            from douban_recommender import browser_auth
        except ModuleNotFoundError:
            raise AssertionError("browser authorization module is missing")
        return browser_auth

    def test_cookie_header_keeps_only_douban_session_cookies(self):
        browser_auth = self.browser_auth_module()

        header = browser_auth.douban_cookie_header(
            [
                {"name": "dbcl2", "value": "session-value", "domain": ".douban.com"},
                {"name": "ck", "value": "abc", "domain": "movie.douban.com"},
                {"name": "bid", "value": "public", "domain": ".douban.com"},
                {"name": "foreign", "value": "nope", "domain": ".example.com"},
            ]
        )

        self.assertIn("dbcl2=session-value", header)
        self.assertIn("ck=abc", header)
        self.assertNotIn("foreign", header)
        self.assertTrue(browser_auth.is_authenticated_cookie(header))

    def test_protected_cookie_store_never_writes_plaintext(self):
        browser_auth = self.browser_auth_module()
        with tempfile.TemporaryDirectory() as temp_dir:
            path = Path(temp_dir) / "session.dat"
            store = browser_auth.ProtectedCookieStore(
                path,
                protect=lambda value: b"protected:" + value[::-1],
                unprotect=lambda value: value.removeprefix(b"protected:")[::-1],
            )

            store.save("dbcl2=session-value; ck=abc")

            self.assertNotIn("session-value", path.read_text(encoding="utf-8"))
            self.assertEqual(store.load(), "dbcl2=session-value; ck=abc")
            self.assertTrue(store.has_session())
            store.clear()
            self.assertFalse(path.exists())

    def test_manager_persists_session_resumes_job_and_never_exposes_cookie(self):
        browser_auth = self.browser_auth_module()
        resumed = []
        finished = threading.Event()

        class Process:
            def poll(self):
                return None

            def terminate(self):
                finished.set()

        with tempfile.TemporaryDirectory() as temp_dir:
            store = browser_auth.ProtectedCookieStore(
                Path(temp_dir) / "session.dat",
                protect=lambda value: value[::-1],
                unprotect=lambda value: value[::-1],
            )
            manager = browser_auth.BrowserAuthManager(
                store,
                Path(temp_dir) / "profile",
                browser_locator=lambda: ("Edge", Path("edge.exe")),
                process_launcher=lambda *_args: Process(),
                cookie_capture=lambda *_args: "dbcl2=session-value; ck=abc",
                on_authorized=lambda: resumed.append("resumed") or {"state": "queued", "job_id": "resume-job"},
            )
            try:
                started = manager.start("123456789", "blocked-job")
                self.assertIn(started["state"], {"opening_browser", "waiting_for_login"})
                deadline = time.time() + 2
                status = manager.status()
                while status["state"] not in {"queued", "error"} and time.time() < deadline:
                    time.sleep(0.01)
                    status = manager.status()

                self.assertEqual(status["state"], "queued")
                self.assertEqual(status["job_id"], "resume-job")
                self.assertEqual(resumed, ["resumed"])
                self.assertTrue(store.has_session())
                self.assertNotIn("session-value", json.dumps(status, ensure_ascii=False))
            finally:
                manager.close()

    def test_manager_reuses_inflight_authorization_window(self):
        browser_auth = self.browser_auth_module()
        capture_release = threading.Event()
        launches = []

        class Process:
            def poll(self):
                return None

            def terminate(self):
                capture_release.set()

        def capture(*_args):
            capture_release.wait(2)
            return ""

        with tempfile.TemporaryDirectory() as temp_dir:
            store = browser_auth.ProtectedCookieStore(
                Path(temp_dir) / "session.dat",
                protect=lambda value: value,
                unprotect=lambda value: value,
            )
            manager = browser_auth.BrowserAuthManager(
                store,
                Path(temp_dir) / "profile",
                browser_locator=lambda: ("Edge", Path("edge.exe")),
                process_launcher=lambda *_args: launches.append(1) or Process(),
                cookie_capture=capture,
            )
            try:
                first = manager.start("123456789", "blocked-job")
                second = manager.start("123456789", "blocked-job")
                self.assertEqual(first["job_id"], second["job_id"])
                deadline = time.time() + 1
                while not launches and time.time() < deadline:
                    time.sleep(0.01)
                self.assertEqual(launches, [1])
            finally:
                capture_release.set()
                manager.close()


if __name__ == "__main__":
    unittest.main()