from __future__ import annotations

from .database import AppDatabase
from .catalog_enrichment import enrich_media_items_parallel
from .douban_sources import fetch_douban_detail_html
from .runtime_paths import resolve_database_path
from .sync_service import SyncService


class SyncApi:
    def __init__(self, service: SyncService):
        self.service = service

    @staticmethod
    def _reject_subscription_fields(payload: dict) -> None:
        for key, value in payload.items():
            lowered = str(key).lower()
            if "subscription" in lowered or "subscribe" in lowered:
                raise ValueError("proxy subscription URLs are not accepted")
            if isinstance(value, str) and "/api/v1/" in value and value.startswith(("http://", "https://")):
                raise ValueError("proxy subscription URLs are not accepted")

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


def build_default_sync_api() -> SyncApi:
    database = AppDatabase(resolve_database_path())
    database.initialize()
    return SyncApi(SyncService(
        database,
        detail_enricher=enrich_media_items_parallel,
        detail_fetcher=lambda url, cookie="": fetch_douban_detail_html(url, cookie=cookie, timeout=5),
        enrich_limit=12,
    ))
