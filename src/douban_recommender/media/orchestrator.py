from __future__ import annotations

import itertools
import json
import queue
import threading
import time
import urllib.request
import uuid
from dataclasses import asdict, dataclass
from typing import Callable, Iterable

from ..douban_sources import build_url_opener
from ..identity_service import (
    MatchDecision,
    PersonIdentity,
    WorkIdentity,
    match_person_identity,
    match_work_identity,
)
from .providers.base import AssetCandidate, AssetQuery, MediaProvider
from .providers.existing import providers_for
from .store import MediaStore
from .url_candidates import image_request_headers, image_url_candidates
from .validator import MediaValidationError, validate_image_bytes


@dataclass(frozen=True)
class MediaResolutionRequest:
    identity_key: str
    kind: str
    priority: int
    query: AssetQuery


@dataclass(frozen=True)
class MediaResolutionResult:
    status: str
    asset_id: str = ""
    local_url: str = ""
    source: str = ""
    confidence: float = 0.0
    attempts: tuple[dict[str, object], ...] = ()

    def to_dict(self) -> dict[str, object]:
        return {
            "status": self.status,
            "asset_id": self.asset_id,
            "local_url": self.local_url,
            "source": self.source,
            "confidence": round(float(self.confidence), 4),
            "attempts": [dict(attempt) for attempt in self.attempts],
        }


FetchImage = Callable[[str], tuple[bytes, str]]


def _default_fetch(url: str) -> tuple[bytes, str]:
    request = urllib.request.Request(
        str(url),
        headers=image_request_headers(url),
    )
    with build_url_opener().open(request, timeout=12) as response:
        return response.read(), str(response.headers.get("Content-Type") or "")


class MediaOrchestrator:
    def __init__(
        self,
        store: MediaStore,
        providers: Iterable[MediaProvider] | None = None,
        fetch: FetchImage | None = None,
        max_workers: int = 3,
    ):
        self.store = store
        self.database = store.database
        self._providers = list(providers) if providers is not None else None
        self.fetch = fetch or _default_fetch
        self.max_workers = max(1, int(max_workers))
        self._provider_semaphores: dict[str, threading.BoundedSemaphore] = {}
        self._provider_lock = threading.Lock()
        self._jobs: dict[str, dict[str, object]] = {}
        self._active_job_by_identity: dict[tuple[str, str], str] = {}
        self._jobs_lock = threading.Lock()
        self._queue: queue.PriorityQueue[tuple[int, int, str, MediaResolutionRequest | None]] = queue.PriorityQueue()
        self._sequence = itertools.count()
        self._closed = threading.Event()
        self._workers: list[threading.Thread] = []
        self._reconcile_interrupted_jobs()
        for index in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"cinescope-media-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

    def _reconcile_interrupted_jobs(self) -> None:
        now = time.time()
        interrupted_states = (
            "queued",
            "pending",
            "processing",
            "resolving",
            "downloading",
            "validating",
        )
        placeholders = ",".join("?" for _ in interrupted_states)
        with self.database.connection() as connection:
            connection.execute(
                f"""
                UPDATE resolution_jobs
                SET state = 'degraded', error = 'interrupted_by_restart',
                    next_retry_at = ?, updated_at = ?
                WHERE state IN ({placeholders})
                """,
                (now, now, *interrupted_states),
            )

    def _providers_for(self, query: AssetQuery) -> list[MediaProvider]:
        if self._providers is not None:
            return list(self._providers)
        return list(providers_for(query.kind, query.media_type))

    def _provider_semaphore(self, name: str) -> threading.BoundedSemaphore:
        with self._provider_lock:
            return self._provider_semaphores.setdefault(name, threading.BoundedSemaphore(2))

    @staticmethod
    def _expected_work(query: AssetQuery) -> WorkIdentity:
        return WorkIdentity(
            title=query.title,
            original_titles=tuple(query.original_titles),
            year=query.year,
            media_type=query.media_type,
            countries=tuple(query.countries),
            directors=tuple(query.directors),
            casts=tuple(query.casts),
            episode_count=query.episode_count,
            provider_ids=dict(query.provider_ids),
        )

    @staticmethod
    def _expected_person(query: AssetQuery) -> PersonIdentity:
        return PersonIdentity(
            name=query.person_name,
            aliases=tuple(query.aliases),
            occupations=tuple(query.occupations),
            known_works=tuple(query.work_context),
            provider_ids=dict(query.provider_ids),
        )

    def _match(self, query: AssetQuery, candidate: AssetCandidate) -> MatchDecision:
        if query.kind == "portrait":
            if candidate.person_identity is None:
                return MatchDecision(False, 0.0, ("missing-person-identity",), False)
            decision = match_person_identity(
                self._expected_person(query),
                candidate.person_identity,
                set(query.work_context),
            )
            if (
                not decision.accepted
                and bool(candidate.metadata.get("embedded"))
                and "name-or-alias" in decision.reasons
            ):
                return MatchDecision(
                    True,
                    max(decision.confidence, 0.96),
                    (*decision.reasons, "embedded-source"),
                    False,
                )
            return decision
        if candidate.work_identity is None:
            return MatchDecision(False, 0.0, ("missing-work-identity",), False)
        decision = match_work_identity(self._expected_work(query), candidate.work_identity)
        if decision.accepted:
            return decision
        exact_year = (
            query.year is not None
            and candidate.work_identity.year is not None
            and int(query.year) == int(candidate.work_identity.year)
        )
        if exact_year and "title" in decision.reasons and "year" in decision.reasons:
            return MatchDecision(
                True,
                max(decision.confidence, 0.94),
                (*decision.reasons, "exact-title-year"),
                False,
            )
        if bool(candidate.metadata.get("embedded")) and "title" in decision.reasons:
            return MatchDecision(
                True,
                max(decision.confidence, 0.96),
                (*decision.reasons, "embedded-source"),
                False,
            )
        return decision

    def resolve(self, request: MediaResolutionRequest) -> MediaResolutionResult:
        attempts: list[dict[str, object]] = []
        for provider in self._providers_for(request.query):
            provider_name = str(getattr(provider, "name", provider.__class__.__name__)).strip() or "unknown"
            try:
                with self._provider_semaphore(provider_name):
                    candidates = list(provider.search(request.query) or [])
            except Exception as exc:
                attempts.append(
                    {
                        "source": provider_name,
                        "status": "provider-error",
                        "error": str(exc),
                    }
                )
                continue

            if not candidates:
                attempts.append({"source": provider_name, "status": "miss"})
                continue

            for candidate in candidates:
                decision = self._match(request.query, candidate)
                identity_attempt: dict[str, object] = {
                    "source": provider_name,
                    "candidate_source": candidate.source,
                    "confidence": round(decision.confidence, 4),
                    "reasons": list(decision.reasons),
                }
                if not decision.accepted:
                    identity_attempt["status"] = "identity-rejected"
                    attempts.append(identity_attempt)
                    continue
                fallback_urls = image_url_candidates(candidate.url)
                if not fallback_urls:
                    identity_attempt["status"] = "asset-rejected"
                    identity_attempt["error"] = "invalid image url"
                    attempts.append(identity_attempt)
                    continue
                candidate_urls = (
                    str(candidate.url),
                    *(url for url in fallback_urls if url != str(candidate.url)),
                )
                for candidate_url in candidate_urls:
                    attempt = dict(identity_attempt)
                    try:
                        data, content_type = self.fetch(candidate_url)
                        min_width, min_height = (64, 64) if request.kind == "portrait" else (80, 80)
                        validated = validate_image_bytes(
                            data,
                            content_type or candidate.declared_type,
                            min_width=min_width,
                            min_height=min_height,
                            kind=request.kind,
                        )
                        stored = self.store.put(validated, candidate_url, request.kind)
                        self.store.bind_asset(
                            "person" if request.kind == "portrait" else "media",
                            request.identity_key,
                            request.kind,
                            stored,
                            candidate.source or provider_name,
                            decision.confidence,
                            {
                                **dict(candidate.metadata),
                                "provider": provider_name,
                                "identity_reasons": list(decision.reasons),
                            },
                        )
                    except (OSError, ValueError, MediaValidationError) as exc:
                        attempt["status"] = "asset-rejected"
                        attempt["error"] = str(exc)
                        attempts.append(attempt)
                        continue
                    attempt["status"] = "ready"
                    attempts.append(attempt)
                    return MediaResolutionResult(
                        status="ready",
                        asset_id=stored.asset_id,
                        local_url=stored.local_url,
                        source=provider_name,
                        confidence=decision.confidence,
                        attempts=tuple(attempts),
                    )
        return MediaResolutionResult(status="degraded", attempts=tuple(attempts))

    def enqueue(self, request: MediaResolutionRequest) -> str:
        if self._closed.is_set():
            raise RuntimeError("media orchestrator is closed")
        active_key = (str(request.kind or "").strip().lower(), str(request.identity_key or "").strip())
        job_id = uuid.uuid4().hex
        now = time.time()
        job = {
            "id": job_id,
            "state": "queued",
            "identity_key": request.identity_key,
            "kind": request.kind,
            "priority": int(request.priority),
            "created_at": now,
            "updated_at": now,
            "result": {},
            "attempts": [],
            "error": "",
        }
        with self._jobs_lock:
            existing_id = self._active_job_by_identity.get(active_key)
            existing = self._jobs.get(existing_id or "")
            if existing and str(existing.get("state") or "") in {"queued", "resolving"}:
                return str(existing_id)
            self._active_job_by_identity.pop(active_key, None)
            self._jobs[job_id] = job
            self._active_job_by_identity[active_key] = job_id
            try:
                with self.database.connection() as connection:
                    connection.execute(
                        """
                        INSERT INTO resolution_jobs(
                            id, entity_kind, entity_id, kind, priority, state,
                            current_source, attempts_json, error, next_retry_at,
                            created_at, updated_at
                        ) VALUES(?, ?, ?, ?, ?, 'queued', '', '[]', '', NULL, ?, ?)
                        """,
                        (
                            job_id,
                            "person" if request.kind == "portrait" else "media",
                            request.identity_key,
                            request.kind,
                            int(request.priority),
                            now,
                            now,
                        ),
                    )
            except Exception:
                self._jobs.pop(job_id, None)
                if self._active_job_by_identity.get(active_key) == job_id:
                    self._active_job_by_identity.pop(active_key, None)
                raise
        self._queue.put((-int(request.priority), next(self._sequence), job_id, request))
        return job_id

    def _set_job_state(
        self,
        job_id: str,
        state: str,
        result: MediaResolutionResult | None = None,
    ) -> None:
        now = time.time()
        result_dict = result.to_dict() if result else {}
        attempts = result_dict.get("attempts", []) if result else []
        error = ""
        if result and result.status != "ready" and attempts:
            error = str(attempts[-1].get("error") or attempts[-1].get("status") or "")
        next_retry_at = now + 30.0 if state == "degraded" else None
        with self.database.connection() as connection:
            connection.execute(
                """
                UPDATE resolution_jobs
                SET state = ?, attempts_json = ?, error = ?, next_retry_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (
                    state,
                    json.dumps(attempts, ensure_ascii=False, separators=(",", ":")),
                    error,
                    next_retry_at,
                    now,
                    job_id,
                ),
            )
        with self._jobs_lock:
            current = self._jobs.get(job_id)
            if current is not None:
                current.update(
                    {
                        "state": state,
                        "updated_at": now,
                        "result": result_dict,
                        "attempts": attempts,
                        "error": error,
                    }
                )
                if state not in {"queued", "resolving"}:
                    active_key = (
                        str(current.get("kind") or "").strip().lower(),
                        str(current.get("identity_key") or "").strip(),
                    )
                    if self._active_job_by_identity.get(active_key) == job_id:
                        self._active_job_by_identity.pop(active_key, None)

    def _worker_loop(self) -> None:
        while not self._closed.is_set():
            try:
                _priority, _sequence, job_id, request = self._queue.get(timeout=0.2)
            except queue.Empty:
                continue
            try:
                if request is None:
                    return
                self._set_job_state(job_id, "resolving")
                result = self.resolve(request)
                self._set_job_state(job_id, result.status, result)
            finally:
                self._queue.task_done()

    def job(self, job_id: str) -> dict[str, object]:
        with self._jobs_lock:
            current = self._jobs.get(str(job_id))
            if current is not None:
                return json.loads(json.dumps(current, ensure_ascii=False))
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT id, entity_id, kind, priority, state, attempts_json,
                       error, created_at, updated_at
                FROM resolution_jobs WHERE id = ?
                """,
                (str(job_id),),
            ).fetchone()
        if not row:
            return {}
        return {
            "id": str(row["id"]),
            "identity_key": str(row["entity_id"]),
            "kind": str(row["kind"]),
            "priority": int(row["priority"]),
            "state": str(row["state"]),
            "attempts": json.loads(str(row["attempts_json"] or "[]")),
            "error": str(row["error"] or ""),
            "created_at": float(row["created_at"]),
            "updated_at": float(row["updated_at"]),
            "result": {},
        }

    def close(self) -> None:
        if self._closed.is_set():
            return
        self._closed.set()
        for _ in self._workers:
            self._queue.put((0, next(self._sequence), "", None))
        for worker in self._workers:
            worker.join(timeout=1.0)
