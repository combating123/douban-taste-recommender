from __future__ import annotations

import copy
import inspect
import json
import threading
import time
import uuid
from concurrent.futures import ThreadPoolExecutor
from dataclasses import asdict, is_dataclass
from typing import Callable

from .catalog_registry import CatalogRegistry
from .crawler import CrawlResult, crawl_user_collections, redact_cookie_from_message
from .database import AppDatabase
from .network_policy import DEFAULT_SYNC_SAFETY_CAP, normalize_douban_user
from .privacy import scrub_sensitive
from .serialization import media_item_from_dict, media_item_to_dict


class SyncService:
    TERMINAL_STATES = {"complete", "partial", "failed", "needs_cookie"}

    def __init__(
        self,
        database: AppDatabase,
        crawler: Callable[..., CrawlResult] = crawl_user_collections,
        detail_enricher: Callable[..., list] | None = None,
        detail_fetcher: Callable[..., object] | None = None,
        enrich_limit: int = 12,
        max_workers: int = 1,
    ):
        self.database = database
        self.database.initialize()
        self.crawler = crawler
        self.detail_enricher = detail_enricher
        self.detail_fetcher = detail_fetcher
        self.enrich_limit = max(0, min(40, int(enrich_limit)))
        self.executor = ThreadPoolExecutor(max_workers=max(1, int(max_workers)), thread_name_prefix="cinescope-sync")
        self._jobs: dict[str, dict[str, object]] = {}
        self._lock = threading.Lock()

    @staticmethod
    def _public_request(payload: dict) -> dict[str, object]:
        user_value = payload.get("user") or payload.get("user_id_or_url") or payload.get("url") or ""
        return {
            "user_id": normalize_douban_user(str(user_value)),
            "max_pages": max(1, min(DEFAULT_SYNC_SAFETY_CAP, int(payload.get("max_pages") or DEFAULT_SYNC_SAFETY_CAP))),
            "include_wish": bool(payload.get("include_wish", True)),
            "include_do": bool(payload.get("include_do", False)),
            "expected_collect": int(payload["expected_collect"]) if str(payload.get("expected_collect") or "").strip() else None,
            "expected_wish": int(payload["expected_wish"]) if str(payload.get("expected_wish") or "").strip() else None,
        }

    def start(self, payload: dict, cookie: str = "") -> str:
        return self._start(self._public_request(dict(payload or {})), cookie=str(cookie or ""))

    def _start(
        self,
        public_request: dict[str, object],
        cookie: str,
        resume_of: str = "",
        resume_starts: dict[str, int] | None = None,
        seed_items=None,
    ) -> str:
        job_id = uuid.uuid4().hex
        now = time.time()
        request_payload = {**public_request, "resume_of": resume_of} if resume_of else dict(public_request)
        job: dict[str, object] = {
            "schema_version": 2,
            "id": job_id,
            "state": "queued",
            "user_id": str(public_request["user_id"]),
            "counts": {"items": 0, "collect_count": 0, "wish_count": 0, "pages_ok": 0, "pages_failed": 0},
            "diagnostics": [],
            "errors": [],
            "stopped_reason": "",
            "created_at": now,
            "updated_at": now,
            "resume_of": resume_of,
        }
        with self._lock:
            self._jobs[job_id] = job
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO sync_jobs(
                    id, user_id, state, request_json, result_json, resume_of,
                    error, created_at, updated_at
                ) VALUES(?, ?, 'queued', ?, '{}', ?, '', ?, ?)
                """,
                (
                    job_id,
                    str(public_request["user_id"]),
                    json.dumps(request_payload, ensure_ascii=False, separators=(",", ":")),
                    resume_of,
                    now,
                    now,
                ),
            )
        self.executor.submit(
            self._run,
            job_id,
            public_request,
            cookie,
            dict(resume_starts or {}) if resume_starts is not None else None,
            list(seed_items or []),
        )
        return job_id

    def _set_job(self, job_id: str, **updates) -> None:
        with self._lock:
            current = self._jobs.get(job_id)
            if current is not None:
                current.update(updates)
                current["updated_at"] = time.time()

    def _call_crawler(self, kwargs: dict) -> CrawlResult:
        signature = inspect.signature(self.crawler)
        accepts_kwargs = any(parameter.kind == inspect.Parameter.VAR_KEYWORD for parameter in signature.parameters.values())
        return self.crawler(**kwargs) if accepts_kwargs else self.crawler(**{key: value for key, value in kwargs.items() if key in signature.parameters})

    @staticmethod
    def _diagnostic(diag) -> dict[str, object]:
        if is_dataclass(diag):
            return asdict(diag)
        if isinstance(diag, dict):
            return dict(diag)
        return {"message": str(diag)}

    @staticmethod
    def _scrub_persisted(value, cookie: str):
        scrubbed = scrub_sensitive(value)
        if isinstance(scrubbed, dict):
            return {str(key): SyncService._scrub_persisted(nested, cookie) for key, nested in scrubbed.items()}
        if isinstance(scrubbed, list):
            return [SyncService._scrub_persisted(nested, cookie) for nested in scrubbed]
        if isinstance(scrubbed, str):
            return redact_cookie_from_message(scrubbed, cookie)
        return scrubbed

    @staticmethod
    def _counts(result: CrawlResult) -> dict[str, int]:
        collect = sum(1 for item in result.items if str(item.source or "").endswith(":collect"))
        wish = sum(1 for item in result.items if str(item.source or "").endswith(":wish"))
        return {
            "items": len(result.items),
            "collect_count": collect,
            "wish_count": wish,
            "pages_ok": int(result.pages_ok),
            "pages_failed": int(result.pages_failed),
        }

    def _enrich_details(self, items: list, cookie: str) -> dict[str, int]:
        if not self.detail_enricher or self.enrich_limit <= 0:
            return {"attempted": 0, "enriched": 0}
        indexed = list(enumerate(items or []))
        indexed.sort(
            key=lambda pair: (
                float(getattr(pair[1], "my_rating", None) or 0),
                str(getattr(pair[1], "source", "")).endswith(":collect"),
                bool(getattr(pair[1], "douban_id", "") or getattr(pair[1], "url", "")),
                -pair[0],
            ),
            reverse=True,
        )
        selected = [item for _, item in indexed[: self.enrich_limit]]
        before = [copy.deepcopy(media_item_to_dict(item)) for item in selected]
        fetcher = None
        if self.detail_fetcher is not None:
            fetcher = lambda url: self.detail_fetcher(url, cookie=cookie)
        try:
            self.detail_enricher(
                selected,
                fetcher=fetcher,
                limit=len(selected),
                sleep_seconds=0.0,
                force_people_photos=True,
            )
        except Exception:
            return {"attempted": len(selected), "enriched": 0}
        enriched = sum(
            1
            for previous, item in zip(before, selected)
            if media_item_to_dict(item) != previous
        )
        return {"attempted": len(selected), "enriched": enriched}

    def _run(
        self,
        job_id: str,
        request: dict[str, object],
        cookie: str,
        resume_starts: dict[str, int] | None,
        seed_items,
    ) -> None:
        self._set_job(job_id, state="running")
        with self.database.connection() as connection:
            connection.execute("UPDATE sync_jobs SET state='running', updated_at=? WHERE id=?", (time.time(), job_id))
        try:
            kwargs = {
                "user_id_or_url": str(request["user_id"]),
                "cookie": cookie,
                "max_pages": int(request["max_pages"]),
                "include_wish": bool(request["include_wish"]),
                "include_do": bool(request["include_do"]),
                "expected_collect": request.get("expected_collect"),
                "expected_wish": request.get("expected_wish"),
                "resume_starts": resume_starts,
                "seed_items": seed_items,
            }
            result = self._call_crawler(kwargs)
        except Exception as exc:
            safe_error = redact_cookie_from_message(str(exc), cookie)
            public = {
                "schema_version": 2,
                "id": job_id,
                "state": "failed",
                "user_id": str(request["user_id"]),
                "counts": {"items": 0, "collect_count": 0, "wish_count": 0, "pages_ok": 0, "pages_failed": 1},
                "diagnostics": [],
                "errors": [safe_error],
                "stopped_reason": "同步任务失败",
            }
            self._finish(job_id, public, safe_error)
            return

        diagnostics = [self._diagnostic(diag) for diag in result.diagnostics]
        errors = [redact_cookie_from_message(error, cookie) for error in result.errors]
        enrichment = self._enrich_details(result.items, cookie)
        login_required = any(diag.get("classification") == "login_required" for diag in diagnostics)
        state = "needs_cookie" if login_required and not result.items else ("partial" if result.pages_failed else "complete")
        public = {
            "schema_version": 2,
            "id": job_id,
            "state": state,
            "user_id": str(request["user_id"]),
            "counts": self._counts(result),
            "diagnostics": diagnostics,
            "errors": errors,
            "stopped_reason": str(result.stopped_reason or ""),
            "completeness": dict(result.completeness or {}),
            "enrichment": enrichment,
        }
        public = self._scrub_persisted(public, cookie)
        registration_items = []
        registration_now = time.time()
        try:
            with self.database.connection() as connection:
                for item in result.items:
                    scrubbed = self._scrub_persisted(media_item_to_dict(item), cookie)
                    payload = scrubbed if isinstance(scrubbed, dict) else {}
                    safe_item = media_item_from_dict(payload)
                    registration_items.append(safe_item)
                    item_key = safe_item.identity or uuid.uuid4().hex
                    connection.execute(
                        """
                        INSERT OR REPLACE INTO sync_items(job_id, item_key, payload_json, source, status)
                        VALUES(?, ?, ?, ?, ?)
                        """,
                        (
                            job_id,
                            item_key,
                            json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                            str(safe_item.source or ""),
                            "ready",
                        ),
                    )
                CatalogRegistry.register_sync_items(
                    connection,
                    str(request["user_id"]),
                    registration_items,
                    registration_now,
                )
        except Exception as exc:
            safe_error = redact_cookie_from_message(str(exc), cookie)
            prior_errors = public.get("errors") if isinstance(public, dict) else []
            failed_public = {
                **public,
                "state": "failed",
                "errors": [*(prior_errors if isinstance(prior_errors, list) else []), safe_error],
                "stopped_reason": "sync result registration failed",
            }
            self._finish(job_id, failed_public, safe_error)
            return
        self._finish(job_id, public, "")

    def _finish(self, job_id: str, public: dict[str, object], error: str) -> None:
        now = time.time()
        self._set_job(job_id, **public, updated_at=now)
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE sync_jobs
                SET state=?, result_json=?, error=?, updated_at=?
                WHERE id=?
                """,
                (
                    str(public["state"]),
                    json.dumps(public, ensure_ascii=False, separators=(",", ":")),
                    str(error or ""),
                    now,
                    job_id,
                ),
            )

    def status(self, job_id: str) -> dict[str, object]:
        with self._lock:
            current = self._jobs.get(str(job_id))
            if current is not None:
                return json.loads(json.dumps(current, ensure_ascii=False))
        with self.database.connection() as connection:
            row = connection.execute("SELECT result_json, state, user_id FROM sync_jobs WHERE id=?", (str(job_id),)).fetchone()
        if not row:
            return {}
        payload = json.loads(str(row["result_json"] or "{}"))
        if payload:
            return payload
        return {"schema_version": 2, "id": str(job_id), "state": str(row["state"]), "user_id": str(row["user_id"])}

    def _items_for_job(self, job_id: str):
        with self.database.connection() as connection:
            rows = connection.execute("SELECT payload_json FROM sync_items WHERE job_id=?", (job_id,)).fetchall()
        return [media_item_from_dict(json.loads(str(row["payload_json"]))) for row in rows]

    def resume(self, job_id: str, cookie: str = "") -> str:
        previous = self.status(job_id)
        if not previous:
            raise ValueError("sync job not found")
        with self.database.connection() as connection:
            row = connection.execute("SELECT request_json FROM sync_jobs WHERE id=?", (job_id,)).fetchone()
        if not row:
            raise ValueError("sync job not found")
        request = json.loads(str(row["request_json"]))
        failed_starts: dict[str, int] = {}
        for diagnostic in previous.get("diagnostics", []):
            if not isinstance(diagnostic, dict):
                continue
            classification = str(diagnostic.get("classification") or "")
            if classification in {"network_error", "login_required", "security_check", "parse_failed_nonempty"}:
                status = str(diagnostic.get("status") or "")
                start = diagnostic.get("start")
                if status and isinstance(start, int):
                    failed_starts.setdefault(status, start)
        if not failed_starts:
            raise ValueError("sync job has no failed pages to resume")
        request.pop("resume_of", None)
        return self._start(
            request,
            cookie=str(cookie or ""),
            resume_of=str(job_id),
            resume_starts=failed_starts,
            seed_items=self._items_for_job(job_id),
        )

    def close(self) -> None:
        self.executor.shutdown(wait=True, cancel_futures=False)
