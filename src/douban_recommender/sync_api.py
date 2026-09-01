from __future__ import annotations

from collections.abc import Mapping

from .auto_sync import AutoSyncCoordinator, SyncSettingsStore
from .browser_auth import BrowserAuthManager, ProtectedCookieStore
from .catalog_enrichment import enrich_media_items_parallel
from .database import AppDatabase
from .douban_sources import fetch_douban_detail_html
from .privacy import scrub_sensitive
from .runtime_paths import resolve_data_dir, resolve_database_path
from .sync_service import SyncService


class SyncApi:
    def __init__(
        self,
        service: SyncService,
        coordinator: AutoSyncCoordinator | None = None,
        browser_auth: BrowserAuthManager | None = None,
    ):
        self.service = service
        self.settings_store = coordinator.settings_store if coordinator else SyncSettingsStore(service.database)
        self.coordinator = coordinator or AutoSyncCoordinator(
            service.database,
            service,
            settings_store=self.settings_store,
            start_thread=False,
        )
        self.browser_auth = browser_auth

    @staticmethod
    def _reject_subscription_fields(payload: dict) -> None:
        for key, value in payload.items():
            lowered = str(key).lower()
            if "subscription" in lowered or "subscribe" in lowered:
                raise ValueError("proxy subscription URLs are not accepted")
            if isinstance(value, str) and "/api/v1/" in value and value.startswith(("http://", "https://")):
                raise ValueError("proxy subscription URLs are not accepted")

    @staticmethod
    def _safe_authorization_status(value: object) -> dict[str, object]:
        if not isinstance(value, Mapping):
            return {"state": "idle", "has_session": False}
        allowed = {
            "state",
            "has_session",
            "user_id",
            "job_id",
            "browser",
            "error",
            "started_at",
            "updated_at",
            "reused",
            "resume_of",
            "resumed",
            "authorization_required",
        }
        payload: dict[str, object] = {}
        for key, nested in value.items():
            name = str(key)
            if name not in allowed:
                continue
            if name in {"has_session", "authorization_required"}:
                payload[name] = bool(nested)
            else:
                payload[name] = scrub_sensitive(nested)
        return payload

    def create_job(self, payload: dict) -> dict[str, object]:
        clean_payload = dict(payload or {})
        self._reject_subscription_fields(clean_payload)
        cookie = str(clean_payload.pop("cookie", "") or "")
        job_id = self.service.start(clean_payload, cookie=cookie)
        status = self.service.status(job_id)
        return {
            "schema_version": 2,
            "job_id": job_id,
            "state": str(status.get("state") or "queued"),
            "user_id": str(status.get("user_id") or ""),
        }

    def get_job(self, job_id: str) -> dict[str, object]:
        status = self.service.status(job_id)
        return status or {"error": "sync job not found", "job_id": str(job_id)}

    def resume_job(self, job_id: str, payload: dict) -> dict[str, object]:
        clean_payload = dict(payload or {})
        self._reject_subscription_fields(clean_payload)
        cookie = str(clean_payload.pop("cookie", "") or "")
        resumed_id = self.service.resume(job_id, cookie=cookie)
        status = self.service.status(resumed_id)
        return {
            "schema_version": 2,
            "job_id": resumed_id,
            "resume_of": str(job_id),
            "state": str(status.get("state") or "queued"),
        }

    def clear_history(self) -> dict[str, object]:
        return {"schema_version": 2, **self.service.clear_history()}

    def get_settings(self) -> dict[str, object]:
        authorization = self.get_browser_authorization()
        authorization.pop("schema_version", None)
        return {"schema_version": 2, **self.settings_store.public(), "authorization": authorization}

    def update_settings(self, payload: dict) -> dict[str, object]:
        clean_payload = dict(payload or {})
        self._reject_subscription_fields(clean_payload)
        clean_payload.pop("cookie", None)
        settings = self.settings_store.update(clean_payload)
        self.coordinator.wake()
        public = dict(settings)
        public.pop("last_completed_job_id", None)
        public.pop("failure_count", None)
        authorization = self.get_browser_authorization()
        authorization.pop("schema_version", None)
        return {"schema_version": 2, **public, "authorization": authorization}

    def run_now(self) -> dict[str, object]:
        return {"schema_version": 2, **self.coordinator.run_now()}

    def get_browser_authorization(self) -> dict[str, object]:
        if self.browser_auth is None:
            status = {"state": "idle", "has_session": False}
        else:
            status = self._safe_authorization_status(self.browser_auth.status())
        return {"schema_version": 2, **status}

    def start_browser_authorization(self, payload: dict | None = None) -> dict[str, object]:
        clean_payload = dict(payload or {})
        self._reject_subscription_fields(clean_payload)
        clean_payload.pop("cookie", None)
        settings = self.settings_store.get()
        user_id = str(settings.get("user_id") or "").strip()
        if not user_id:
            raise ValueError("no Douban user is connected")
        if self.browser_auth is None:
            raise RuntimeError("browser authorization is unavailable")
        raw = self.browser_auth.start(user_id, str(settings.get("last_job_id") or ""))
        if not isinstance(raw, Mapping):
            raw = self.browser_auth.status()
        return {"schema_version": 2, **self._safe_authorization_status(raw)}

    def close(self) -> None:
        if self.browser_auth is not None:
            self.browser_auth.close()
        self.coordinator.close()
        self.service.close()


def build_default_sync_api() -> SyncApi:
    database = AppDatabase(resolve_database_path())
    database.initialize()
    service = SyncService(
        database,
        detail_enricher=enrich_media_items_parallel,
        detail_fetcher=lambda url, cookie="": fetch_douban_detail_html(url, cookie=cookie, timeout=5),
        enrich_limit=24,
    )
    data_dir = resolve_data_dir()
    session_store = ProtectedCookieStore(data_dir / "douban-session.dat")
    coordinator_holder: dict[str, AutoSyncCoordinator] = {}

    def resume_authorized_job() -> dict[str, object]:
        coordinator = coordinator_holder.get("coordinator")
        if coordinator is None:
            return {"state": "waiting_for_login"}
        return coordinator.resume_after_authorization()

    browser_auth = BrowserAuthManager(
        session_store,
        data_dir / "browser-profile",
        on_authorized=resume_authorized_job,
    )
    coordinator = AutoSyncCoordinator(
        database,
        service,
        cookie_provider=session_store.load,
        cookie_invalidator=browser_auth.invalidate,
        authorization_launcher=browser_auth.start,
        start_thread=True,
    )
    coordinator_holder["coordinator"] = coordinator
    return SyncApi(service, coordinator=coordinator, browser_auth=browser_auth)