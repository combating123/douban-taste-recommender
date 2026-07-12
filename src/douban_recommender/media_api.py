from __future__ import annotations

import hashlib
from pathlib import Path
from typing import Any

from .database import AppDatabase
from .media.orchestrator import MediaOrchestrator, MediaResolutionRequest
from .media.providers.base import AssetQuery
from .media.store import MediaStore, StoredAsset
from .runtime_paths import resolve_database_path, resolve_media_dir


def _strings(value: object) -> tuple[str, ...]:
    if isinstance(value, str):
        values = value.replace("\n", ",").split(",")
    elif isinstance(value, (list, tuple, set)):
        values = value
    else:
        values = ()
    out: list[str] = []
    for raw in values:
        text = str(raw or "").strip()
        if text and text not in out:
            out.append(text)
    return tuple(out)


def _optional_int(value: object) -> int | None:
    try:
        return int(value) if value not in (None, "") else None
    except (TypeError, ValueError):
        return None


def _provider_ids(value: object) -> dict[str, str]:
    if not isinstance(value, dict):
        return {}
    return {
        str(provider).strip(): str(identifier).strip()
        for provider, identifier in value.items()
        if str(provider).strip() and str(identifier).strip()
    }


class MediaApi:
    def __init__(self, store: MediaStore, orchestrator: MediaOrchestrator):
        self.store = store
        self.orchestrator = orchestrator

    def create_job(self, payload: dict[str, Any]) -> dict[str, object]:
        kind = str(payload.get("kind") or "poster").strip().lower()
        if kind not in {"poster", "backdrop", "portrait"}:
            raise ValueError("unsupported media kind")
        title = str(payload.get("title") or "").strip()
        person_name = str(payload.get("person_name") or payload.get("personName") or "").strip()
        if kind == "portrait" and not person_name:
            raise ValueError("person_name is required for portrait jobs")
        if kind != "portrait" and not title:
            raise ValueError("title is required for work media jobs")
        identity_key = str(payload.get("identity_key") or payload.get("identityKey") or "").strip()
        if not identity_key:
            raw_identity = f"{kind}:{person_name or title}:{payload.get('year') or ''}"
            identity_key = hashlib.sha256(raw_identity.encode("utf-8")).hexdigest()[:24]

        query = AssetQuery(
            kind=kind,
            title=title,
            original_titles=_strings(payload.get("original_titles") or payload.get("originalTitles")),
            year=_optional_int(payload.get("year")),
            media_type=str(payload.get("media_type") or payload.get("mediaType") or "").strip(),
            countries=_strings(payload.get("countries")),
            directors=_strings(payload.get("directors")),
            casts=_strings(payload.get("casts")),
            episode_count=_optional_int(payload.get("episode_count") or payload.get("episodeCount")),
            person_name=person_name,
            aliases=_strings(payload.get("aliases")),
            occupations=_strings(payload.get("occupations")),
            work_context=_strings(payload.get("work_context") or payload.get("workContext")),
            source_urls=_strings(
                payload.get("source_urls")
                or payload.get("sourceUrls")
                or payload.get("source_url")
                or payload.get("sourceUrl")
            ),
            provider_ids=_provider_ids(payload.get("provider_ids") or payload.get("providerIds")),
        )
        request = MediaResolutionRequest(
            identity_key=identity_key,
            kind=kind,
            priority=max(0, min(1000, int(payload.get("priority") or 0))),
            query=query,
        )
        job_id = self.orchestrator.enqueue(request)
        job = self._public_job(self.orchestrator.job(job_id))
        return {
            "schema_version": 2,
            "job_id": job_id,
            "state": str(job.get("state") or "queued"),
            "kind": kind,
            "identity_key": identity_key,
        }

    def get_job(self, job_id: str) -> dict[str, object]:
        job = self.orchestrator.job(str(job_id or "").strip())
        if not job:
            return {"error": "media job not found", "job_id": str(job_id or "")}
        return {"schema_version": 2, **self._public_job(job)}

    def _public_job(self, job: dict[str, object]) -> dict[str, object]:
        public = dict(job or {})
        result_value = public.get("result")
        result = dict(result_value) if isinstance(result_value, dict) else {}
        if str(public.get("state") or "") != "ready":
            public["result"] = result
            return public

        local_url = str(result.get("local_url") or "").strip()
        stored = self.store.lookup(local_url.removeprefix("/media/")) if local_url.startswith("/media/") else None
        expected_asset_id = str(result.get("asset_id") or "").strip().lower()
        expected_kind = str(public.get("kind") or "").strip().lower()
        if (
            stored is None
            or stored.status != "ready"
            or stored.local_url != local_url
            or (expected_asset_id and stored.asset_id != expected_asset_id)
            or (expected_kind and stored.kind != expected_kind)
        ):
            public["state"] = "degraded"
            public["error"] = ""
            public["degradation_reason"] = "ready asset is not a verified local /media asset"
            public["result"] = {
                "status": "degraded",
                "asset_id": "",
                "local_url": "",
                "source": "",
                "confidence": 0.0,
                "attempts": [],
            }
            return public

        result.update(
            {
                "status": "ready",
                "asset_id": stored.asset_id,
                "local_url": stored.local_url,
            }
        )
        public["result"] = result
        return public

    def health(self) -> dict[str, object]:
        with self.store.database.connection() as connection:
            asset_row = connection.execute(
                "SELECT COUNT(*) AS total, COALESCE(SUM(byte_size), 0) AS bytes FROM asset_files"
            ).fetchone()
            job_rows = connection.execute(
                "SELECT state, COUNT(*) AS count FROM resolution_jobs GROUP BY state"
            ).fetchall()
        return {
            "schema_version": 2,
            "assets": {
                "total": int(asset_row["total"]),
                "bytes": int(asset_row["bytes"]),
            },
            "jobs": {str(row["state"]): int(row["count"]) for row in job_rows},
            "delivery": "local-only",
        }

    def asset(self, route_filename: str) -> StoredAsset | None:
        return self.store.lookup(route_filename)


def build_default_media_api() -> MediaApi:
    database = AppDatabase(resolve_database_path())
    database.initialize()
    store = MediaStore(resolve_media_dir(), database)
    return MediaApi(store, MediaOrchestrator(store))
