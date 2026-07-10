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
        headers={
            "User-Agent": "CineScopeLocalPersonalRecommender/3.0",
            "Accept": "image/avif,image/webp,image/apng,image/*,*/*;q=0.8",
        },
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
        self._jobs_lock = threading.Lock()
        self._queue: queue.PriorityQueue[tuple[int, int, str, MediaResolutionRequest | None]] = queue.PriorityQueue()
        self._sequence = itertools.count()
        self._closed = threading.Event()
        self._workers: list[threading.Thread] = []
        for index in range(self.max_workers):
            worker = threading.Thread(
                target=self._worker_loop,
                name=f"cinescope-media-{index + 1}",
                daemon=True,
            )
            worker.start()
            self._workers.append(worker)

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
            return match_person_identity(
                self._expected_person(query),
                candidate.person_identity,
                set(query.work_context),
            )
        if candidate.work_identity is None:
            return MatchDecision(False, 0.0, ("missing-work-identity",), False)
        return match_work_identity(self._expected_work(query), candidate.work_identity)

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
                attempt: dict[str, object] = {
                    "source": provider_name,
                    "candidate_source": candidate.source,
                    "confidence": round(decision.confidence, 4),
                    "reasons": list(decision.reasons),
                }
                if not decision.accepted:
                    attempt["status"] = "identity-rejected"
                    attempts.append(attempt)
                    continue
                try:
                    data, content_type = self.fetch(candidate.url)
                    min_width, min_height = (64, 64) if request.kind == "portrait" else (80, 80)
                    validated = validate_image_bytes(
                        data,
                        content_type or candidate.declared_type,
                        min_width=min_width,
                        min_height=min_height,
                    )
                    stored = self.store.put(validated, candidate.url, request.kind)
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
            self._jobs[job_id] = job
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
