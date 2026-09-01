from __future__ import annotations

import json
import threading
import time
from typing import Callable

from .database import AppDatabase
from .network_policy import DEFAULT_SYNC_SAFETY_CAP, normalize_douban_user


SETTINGS_META_KEY = "auto_sync_settings"
DEFAULT_INTERVAL_MINUTES = 60
MIN_INTERVAL_MINUTES = 15
MAX_INTERVAL_MINUTES = 24 * 60
TERMINAL_STATES = {"complete", "partial", "failed", "needs_cookie"}


class SyncSettingsStore:
    def __init__(self, database: AppDatabase, now: Callable[[], float] = time.time):
        self.database = database
        self.database.initialize()
        self.now = now
        self._lock = threading.RLock()

    def _defaults(self) -> dict[str, object]:
        user_id = str(self.database.get_meta("active_douban_user_id") or "").strip()
        return {
            "user_id": user_id,
            "enabled": bool(user_id),
            "interval_minutes": DEFAULT_INTERVAL_MINUTES,
            "include_wish": True,
            "include_do": False,
            "max_pages": DEFAULT_SYNC_SAFETY_CAP,
            "last_job_id": "",
            "last_attempt_at": 0.0,
            "last_success_at": 0.0,
            "last_state": "idle",
            "last_completed_job_id": "",
            "next_run_at": self.now() if user_id else 0.0,
            "failure_count": 0,
        }

    @staticmethod
    def _safe_int(value: object, default: int, minimum: int, maximum: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            parsed = default
        return max(minimum, min(maximum, parsed))

    @staticmethod
    def _safe_float(value: object, default: float = 0.0) -> float:
        try:
            return max(0.0, float(value))
        except (TypeError, ValueError):
            return default

    def _normalize(self, raw: dict[str, object] | None) -> dict[str, object]:
        defaults = self._defaults()
        source = dict(raw or {})
        raw_user = source.get("user_id", defaults["user_id"])
        try:
            user_id = normalize_douban_user(str(raw_user)) if str(raw_user or "").strip() else ""
        except ValueError:
            user_id = str(defaults["user_id"] or "")
        interval = self._safe_int(
            source.get("interval_minutes"),
            int(defaults["interval_minutes"]),
            MIN_INTERVAL_MINUTES,
            MAX_INTERVAL_MINUTES,
        )
        return {
            "user_id": user_id,
            "enabled": bool(source.get("enabled", defaults["enabled"])) and bool(user_id),
            "interval_minutes": interval,
            "include_wish": bool(source.get("include_wish", defaults["include_wish"])),
            "include_do": bool(source.get("include_do", defaults["include_do"])),
            "max_pages": self._safe_int(
                source.get("max_pages"),
                int(defaults["max_pages"]),
                1,
                DEFAULT_SYNC_SAFETY_CAP,
            ),
            "last_job_id": str(source.get("last_job_id") or "").strip(),
            "last_attempt_at": self._safe_float(source.get("last_attempt_at")),
            "last_success_at": self._safe_float(source.get("last_success_at")),
            "last_state": str(source.get("last_state") or "idle").strip() or "idle",
            "last_completed_job_id": str(source.get("last_completed_job_id") or "").strip(),
            "next_run_at": self._safe_float(source.get("next_run_at"), float(defaults["next_run_at"])),
            "failure_count": self._safe_int(source.get("failure_count"), 0, 0, 1000),
        }

    def _save(self, settings: dict[str, object]) -> dict[str, object]:
        normalized = self._normalize(settings)
        self.database.set_meta(
            SETTINGS_META_KEY,
            json.dumps(normalized, ensure_ascii=False, sort_keys=True, separators=(",", ":")),
        )
        if normalized["user_id"]:
            self.database.set_meta("active_douban_user_id", str(normalized["user_id"]))
        return dict(normalized)

    def get(self) -> dict[str, object]:
        with self._lock:
            raw = self.database.get_meta(SETTINGS_META_KEY)
            try:
                decoded = json.loads(raw) if raw else {}
            except (TypeError, ValueError, json.JSONDecodeError):
                decoded = {}
            normalized = self._normalize(decoded if isinstance(decoded, dict) else {})
            if not raw:
                normalized = self._save(normalized)
            return dict(normalized)

    def update(self, changes: dict[str, object]) -> dict[str, object]:
        with self._lock:
            current = self.get()
            allowed = {
                "user_id",
                "enabled",
                "interval_minutes",
                "include_wish",
                "include_do",
                "max_pages",
                "next_run_at",
            }
            current.update({key: value for key, value in dict(changes or {}).items() if key in allowed})
            return self._save(current)

    def mark_started(self, job_id: str) -> dict[str, object]:
        with self._lock:
            current = self.get()
            now = self.now()
            current.update(
                {
                    "last_job_id": str(job_id),
                    "last_attempt_at": now,
                    "last_state": "queued",
                    "next_run_at": now + int(current["interval_minutes"]) * 60,
                }
            )
            return self._save(current)

    def mark_terminal(self, job_id: str, state: str) -> dict[str, object]:
        with self._lock:
            current = self.get()
            if str(current.get("last_completed_job_id") or "") == str(job_id):
                return current
            now = self.now()
            clean_state = str(state or "failed")
            failures = 0 if clean_state == "complete" else int(current.get("failure_count") or 0) + 1
            delay = int(current["interval_minutes"]) * 60
            if clean_state != "complete":
                delay = min(6 * 3600, max(15 * 60, delay * (2 ** min(failures, 3))))
            current.update(
                {
                    "last_state": clean_state,
                    "last_completed_job_id": str(job_id),
                    "last_success_at": now if clean_state == "complete" else current.get("last_success_at", 0.0),
                    "failure_count": failures,
                    "next_run_at": now + delay,
                }
            )
            return self._save(current)

    def public(self) -> dict[str, object]:
        settings = self.get()
        settings.pop("last_completed_job_id", None)
        settings.pop("failure_count", None)
        return settings


class AutoSyncCoordinator:
    def __init__(
        self,
        database: AppDatabase,
        service,
        *,
        settings_store: SyncSettingsStore | None = None,
        cookie_provider: Callable[[], str] | None = None,
        cookie_invalidator: Callable[[], None] | None = None,
        authorization_launcher: Callable[[str, str], dict[str, object] | None] | None = None,
        now: Callable[[], float] = time.time,
        poll_seconds: float = 5.0,
        start_thread: bool = True,
    ):
        self.database = database
        self.service = service
        self.now = now
        self.settings_store = settings_store or SyncSettingsStore(database, now=now)
        self.cookie_provider = cookie_provider
        self.cookie_invalidator = cookie_invalidator
        self.authorization_launcher = authorization_launcher
        self.poll_seconds = max(0.2, float(poll_seconds))
        self._closed = threading.Event()
        self._wake = threading.Event()
        self._thread: threading.Thread | None = None
        self._authorization_jobs: set[str] = set()
        self._session_jobs: set[str] = set()
        if start_thread:
            self._thread = threading.Thread(target=self._loop, name="cinescope-auto-sync", daemon=True)
            self._thread.start()

    def _request(self, settings: dict[str, object]) -> dict[str, object]:
        return {
            "user": str(settings["user_id"]),
            "max_pages": int(settings["max_pages"]),
            "include_wish": bool(settings["include_wish"]),
            "include_do": bool(settings["include_do"]),
        }

    def _session_cookie(self) -> str:
        provider = getattr(self, "cookie_provider", None)
        if not callable(provider):
            return ""
        try:
            return str(provider() or "").strip()
        except Exception:
            return ""

    def _invalidate_session(self) -> None:
        invalidator = getattr(self, "cookie_invalidator", None)
        if callable(invalidator):
            try:
                invalidator()
            except Exception:
                pass

    def _blocked_status(self, settings: dict[str, object]) -> dict[str, object]:
        job_id = str(settings.get("last_job_id") or "").strip()
        if not job_id:
            return {}
        status = self.service.status(job_id) or {}
        if str(status.get("state") or "") != "needs_cookie":
            return {}
        expected_user = str(settings.get("user_id") or "").strip()
        actual_user = str(status.get("user_id") or expected_user).strip()
        if expected_user and actual_user and expected_user != actual_user:
            return {}
        return {**status, "id": str(status.get("id") or job_id), "user_id": actual_user or expected_user}

    def _authorization_required(self, settings: dict[str, object], blocked: dict[str, object]) -> dict[str, object]:
        return {
            "job_id": str(blocked.get("id") or settings.get("last_job_id") or ""),
            "state": "needs_cookie",
            "reused": True,
            "authorization_required": True,
            "user_id": str(blocked.get("user_id") or settings.get("user_id") or ""),
        }

    def _run_now(self, *, fresh_authorization: bool = False) -> dict[str, object]:
        settings = self.settings_store.get()
        user_id = str(settings.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("no Douban user is connected")
        active = str(self.service.active_job_id(user_id) or "")
        if active:
            return {"job_id": active, "state": "running", "reused": True, "user_id": user_id}

        blocked = self._blocked_status(settings)
        session_cookie = self._session_cookie()
        if blocked:
            blocked_id = str(blocked.get("id") or settings.get("last_job_id") or "")
            session_was_rejected = blocked_id in self._session_jobs or bool(blocked.get("resume_of"))
            if session_cookie and session_was_rejected and not fresh_authorization:
                self._invalidate_session()
                session_cookie = ""
            if not session_cookie:
                return self._authorization_required(settings, blocked)
            resumed_id = self.service.resume(blocked_id, cookie=session_cookie)
            self._session_jobs.add(str(resumed_id))
            self._authorization_jobs.discard(blocked_id)
            self.settings_store.mark_started(resumed_id)
            return {
                "job_id": str(resumed_id),
                "resume_of": blocked_id,
                "state": "queued",
                "reused": True,
                "resumed": True,
                "user_id": user_id,
            }

        job_id = self.service.start(self._request(settings), cookie=session_cookie)
        if session_cookie:
            self._session_jobs.add(str(job_id))
        self.settings_store.mark_started(job_id)
        return {"job_id": job_id, "state": "queued", "reused": False, "user_id": user_id}

    def run_now(self) -> dict[str, object]:
        return self._run_now(fresh_authorization=False)

    def resume_after_authorization(self) -> dict[str, object]:
        return self._run_now(fresh_authorization=True)

    def _launch_authorization(
        self,
        settings: dict[str, object],
        blocked: dict[str, object],
    ) -> dict[str, object]:
        job_id = str(blocked.get("id") or settings.get("last_job_id") or "")
        user_id = str(blocked.get("user_id") or settings.get("user_id") or "")
        launcher = getattr(self, "authorization_launcher", None)
        if not callable(launcher):
            return self._authorization_required(settings, blocked)
        launched: dict[str, object] = {}
        if job_id not in self._authorization_jobs:
            raw = launcher(user_id, job_id) or {}
            if isinstance(raw, dict):
                launched = dict(raw)
            self._authorization_jobs.add(job_id)
        state = str(launched.get("state") or "waiting_for_login")
        if state == "opening_browser":
            state = "waiting_for_login"
        return {
            "job_id": job_id,
            "user_id": user_id,
            "state": state,
            "reused": job_id in self._authorization_jobs,
            "authorization_required": True,
            **{key: value for key, value in launched.items() if key not in {"job_id", "user_id", "state"}},
        }

    def tick(self) -> dict[str, object]:
        settings = self.settings_store.get()
        last_job_id = str(settings.get("last_job_id") or "")
        status: dict[str, object] = {}
        if last_job_id:
            status = self.service.status(last_job_id) or {}
            state = str(status.get("state") or "")
            if state in TERMINAL_STATES and last_job_id != str(settings.get("last_completed_job_id") or ""):
                settings = self.settings_store.mark_terminal(last_job_id, state)
        if not bool(settings.get("enabled")) or not str(settings.get("user_id") or ""):
            return {"state": "disabled"}
        active = str(self.service.active_job_id(str(settings["user_id"])) or "")
        if active:
            return {"state": "running", "job_id": active, "reused": True}

        blocked = self._blocked_status(settings)
        if blocked:
            blocked_id = str(blocked.get("id") or last_job_id)
            cookie = self._session_cookie()
            if cookie and (blocked_id in self._session_jobs or bool(blocked.get("resume_of"))):
                self._invalidate_session()
                cookie = ""
            if cookie:
                return self._run_now(fresh_authorization=False)
            return self._launch_authorization(settings, blocked)

        if float(settings.get("next_run_at") or 0) > self.now():
            return {"state": "scheduled", "next_run_at": float(settings["next_run_at"])}
        return self.run_now()

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        while not self._closed.is_set():
            try:
                self.tick()
            except Exception:
                pass
            self._wake.wait(self.poll_seconds)
            self._wake.clear()

    def close(self) -> None:
        self._closed.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=2.0)
