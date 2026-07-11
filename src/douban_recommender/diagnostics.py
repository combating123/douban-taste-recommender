from __future__ import annotations

import hashlib
import json
import os
import re
import sqlite3
from collections.abc import Iterable, Mapping
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from importlib import metadata
from pathlib import Path
from typing import Any, Iterator

from .database import AppDatabase
from .media.store import MediaStore
from .runtime_paths import resolve_database_path
from .storage import default_cache_dir


UNKNOWN = "unknown"
DIAGNOSTICS_SCHEMA_VERSION = 2
PACKAGE_NAME = "douban-taste-recommender"
LOCAL_POSTER_RE = re.compile(r"^/media/([0-9a-f]{64})(\.(?:jpg|jpeg|png|webp))$", re.I)
HARD_IDENTITY_CONFLICTS = {
    "title-conflict",
    "media-type-conflict",
    "year-conflict",
    "name-conflict",
}
KNOWN_PROVIDERS = ("existing", "tmdb", "tvmaze", "anilist", "jikan", "douban", "wikidata")
ATTEMPT_STATUSES = ("ready", "miss", "identity-rejected", "asset-rejected", "provider-error")
QUEUE_STATES = ("queued", "resolving", "downloading", "validating", "ready", "degraded", "failed", "cancelled")
SYNC_STATES = ("queued", "running", "partial", "needs_cookie", "complete", "failed", "cancelled")
SESSION_STATES = ("active", "complete", "closed", "abandoned")


@dataclass(frozen=True)
class MediaAudit:
    total: int
    ready: int
    degraded: int
    ambiguous: int
    missing: int
    wrong_identity_candidates: int

    def to_dict(self) -> dict[str, int]:
        return asdict(self)


class _ReadOnlyDatabase:
    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        with _read_only_connection(self.path) as connection:
            yield connection


@contextmanager
def _read_only_connection(path: Path | str) -> Iterator[sqlite3.Connection]:
    database_path = Path(path).expanduser().resolve(strict=False)
    connection = sqlite3.connect(f"{database_path.as_uri()}?mode=ro", uri=True, timeout=5.0)
    connection.row_factory = sqlite3.Row
    try:
        connection.execute("PRAGMA query_only = ON")
        yield connection
    finally:
        connection.close()


def _row_value(row: object, key: str) -> object:
    if isinstance(row, Mapping):
        return row.get(key)
    return getattr(row, key, None)


def _poster_status(row: object) -> str:
    value = _row_value(row, "media_status")
    if isinstance(value, Mapping):
        value = value.get("poster")
    return str(value or "").strip().lower()


def _ambiguous_evidence(value: object) -> bool:
    if isinstance(value, str):
        return value.strip().lower() == "ambiguous"
    if isinstance(value, Mapping):
        if value.get("ambiguous") is True:
            return True
        for key in ("status", "classification", "decision", "result", "poster"):
            if key in value and _ambiguous_evidence(value.get(key)):
                return True
        return False
    if isinstance(value, (list, tuple)):
        return any(_ambiguous_evidence(item) for item in value)
    return False


def _row_is_explicitly_ambiguous(row: object) -> bool:
    if _poster_status(row) == "ambiguous":
        return True
    return any(
        _ambiguous_evidence(_row_value(row, key))
        for key in ("media_evidence", "media_status_evidence", "evidence")
    )


def _attempts(connection: sqlite3.Connection) -> list[dict[str, object]]:
    rows = connection.execute("SELECT attempts_json FROM resolution_jobs").fetchall()
    attempts: list[dict[str, object]] = []
    for row in rows:
        decoded = json.loads(str(row["attempts_json"] or "[]"))
        if not isinstance(decoded, list):
            raise ValueError("invalid attempts payload")
        attempts.extend(item for item in decoded if isinstance(item, dict))
    return attempts


def _wrong_identity_candidates(connection: sqlite3.Connection) -> int:
    count = 0
    for attempt in _attempts(connection):
        if str(attempt.get("status") or "").strip().lower() != "identity-rejected":
            continue
        raw_reasons = attempt.get("reasons")
        reasons = raw_reasons if isinstance(raw_reasons, (list, tuple)) else ()
        normalized = {str(reason or "").strip().lower() for reason in reasons}
        if normalized & HARD_IDENTITY_CONFLICTS:
            count += 1
    return count


def _media_store_for(db: AppDatabase) -> MediaStore:
    store = MediaStore.__new__(MediaStore)
    store.root = (Path(db.path).expanduser().resolve(strict=False).parent / "media").resolve(strict=False)
    store.database = _ReadOnlyDatabase(db.path)
    return store


def audit_recommendation_media(rows: Iterable[object], db: AppDatabase) -> MediaAudit:
    recommendation_rows = list(rows)
    store = _media_store_for(db)
    counts = {"ready": 0, "degraded": 0, "ambiguous": 0, "missing": 0}

    with _read_only_connection(db.path) as connection:
        for row in recommendation_rows:
            cover = str(_row_value(row, "cover") or "").strip()
            route_match = LOCAL_POSTER_RE.fullmatch(cover)
            if not route_match:
                counts["missing"] += 1
                continue

            asset_id = route_match.group(1).lower()
            manifest = connection.execute(
                "SELECT asset_id FROM asset_files WHERE asset_id = ?",
                (asset_id,),
            ).fetchone()
            if manifest is None:
                counts["missing"] += 1
                continue

            stored = store.lookup(cover.removeprefix("/media/"))
            if stored is None or stored.status != "ready" or stored.kind != "poster":
                counts["degraded"] += 1
                continue

            if _row_is_explicitly_ambiguous(row):
                counts["ambiguous"] += 1
                continue

            status = _poster_status(row)
            if status and status != "ready":
                counts["degraded"] += 1
                continue
            counts["ready"] += 1

        wrong_identity_candidates = _wrong_identity_candidates(connection)

    audit = MediaAudit(
        total=len(recommendation_rows),
        ready=counts["ready"],
        degraded=counts["degraded"],
        ambiguous=counts["ambiguous"],
        missing=counts["missing"],
        wrong_identity_candidates=wrong_identity_candidates,
    )
    if audit.ready + audit.degraded + audit.ambiguous + audit.missing != audit.total:
        raise AssertionError("media audit categories must be mutually exclusive")
    return audit


def _database_path_hash(path: Path | str) -> str:
    normalized = str(Path(path).expanduser().resolve(strict=False))
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


def _nonnegative_int(value: object) -> int:
    return max(0, int(value or 0))


def _fixed_state_counts(
    connection: sqlite3.Connection,
    table: str,
    states: tuple[str, ...],
    *,
    column: str = "state",
) -> dict[str, int]:
    counts = {state: 0 for state in states}
    counts[UNKNOWN] = 0
    rows = connection.execute(
        f"SELECT {column} AS state, COUNT(*) AS count FROM {table} GROUP BY {column}"
    ).fetchall()
    for row in rows:
        state = str(row["state"] or "").strip().lower()
        key = state if state in counts and state != UNKNOWN else UNKNOWN
        counts[key] += _nonnegative_int(row["count"])
    return counts


def _database_schema_version(connection: sqlite3.Connection) -> int | str:
    row = connection.execute("SELECT value FROM schema_meta WHERE key = 'version'").fetchone()
    if row is None:
        return UNKNOWN
    try:
        return _nonnegative_int(row["value"])
    except (TypeError, ValueError):
        return UNKNOWN


def _sync_counts(connection: sqlite3.Connection) -> dict[str, object]:
    jobs = connection.execute("SELECT COUNT(*) AS count FROM sync_jobs").fetchone()
    items = connection.execute("SELECT COUNT(*) AS count FROM sync_items").fetchone()
    return {
        "jobs_total": _nonnegative_int(jobs["count"]),
        "items_total": _nonnegative_int(items["count"]),
        "states": _fixed_state_counts(connection, "sync_jobs", SYNC_STATES),
    }


def _session_counts(connection: sqlite3.Connection) -> dict[str, int]:
    states = _fixed_state_counts(
        connection,
        "recommendation_sessions",
        SESSION_STATES,
        column="status",
    )
    return {"total": sum(states.values()), **states}


def _recommendation_rows(connection: sqlite3.Connection) -> tuple[dict[str, int], list[dict[str, object]]]:
    rows = connection.execute("SELECT payload_json FROM recommendation_batches").fetchall()
    recommendation_rows: list[dict[str, object]] = []
    for row in rows:
        payload = json.loads(str(row["payload_json"] or "{}"))
        if not isinstance(payload, dict):
            raise ValueError("invalid batch payload")
        items = payload.get("items")
        if isinstance(items, list):
            recommendation_rows.extend(item for item in items if isinstance(item, dict))
    return {"total": len(rows), "recommendation_rows": len(recommendation_rows)}, recommendation_rows


def _provider_attempt_health(connection: sqlite3.Connection) -> dict[str, object] | str:
    attempts = _attempts(connection)
    if not attempts:
        return UNKNOWN

    status_counts = {status.replace("-", "_"): 0 for status in ATTEMPT_STATUSES}
    status_counts[UNKNOWN] = 0
    provider_counts = {provider: 0 for provider in KNOWN_PROVIDERS}
    provider_counts[UNKNOWN] = 0
    for attempt in attempts:
        status = str(attempt.get("status") or "").strip().lower()
        status_key = status.replace("-", "_") if status in ATTEMPT_STATUSES else UNKNOWN
        status_counts[status_key] += 1
        provider = str(attempt.get("source") or "").strip().lower()
        provider_counts[provider if provider in provider_counts and provider != UNKNOWN else UNKNOWN] += 1
    return {
        "basis": "historical_attempts",
        "attempts_total": len(attempts),
        "status_counts": status_counts,
        "provider_counts": provider_counts,
    }


def _media_totals(connection: sqlite3.Connection) -> dict[str, int]:
    row = connection.execute(
        "SELECT COUNT(*) AS total, COALESCE(SUM(byte_size), 0) AS bytes FROM asset_files"
    ).fetchone()
    return {
        "assets_total": _nonnegative_int(row["total"]),
        "bytes": _nonnegative_int(row["bytes"]),
    }


def _cache_bytes(cache_dir: Path | str) -> int:
    root = Path(cache_dir)
    if not root.exists():
        return 0
    if not root.is_dir():
        raise OSError("cache root is not a directory")
    total = 0
    pending = [root]
    while pending:
        current = pending.pop()
        with os.scandir(current) as entries:
            for entry in entries:
                if entry.is_symlink():
                    continue
                if entry.is_dir(follow_symlinks=False):
                    pending.append(Path(entry.path))
                elif entry.is_file(follow_symlinks=False):
                    total += max(0, entry.stat(follow_symlinks=False).st_size)
    return total


def _app_version() -> str:
    try:
        value = str(metadata.version(PACKAGE_NAME) or "").strip()
    except Exception:
        return UNKNOWN
    return value or UNKNOWN


def _unknown_observability() -> dict[str, str]:
    return {
        "app_version": UNKNOWN,
        "provider_health": UNKNOWN,
        "persistent_queue_states": UNKNOWN,
        "in_memory_queue_depth": UNKNOWN,
        "cache_bytes": UNKNOWN,
        "recommendation_media_identity_attribution": UNKNOWN,
        "wrong_identity_candidates_scope": UNKNOWN,
    }


def unknown_diagnostics() -> dict[str, object]:
    return {
        "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
        "app_version": UNKNOWN,
        "database_schema_version": UNKNOWN,
        "database_path_hash": UNKNOWN,
        "sync_counts": UNKNOWN,
        "session_counts": UNKNOWN,
        "batch_counts": UNKNOWN,
        "provider_attempt_health": UNKNOWN,
        "persistent_queue_states": UNKNOWN,
        "cache_bytes": UNKNOWN,
        "media_totals": UNKNOWN,
        "media_audit": UNKNOWN,
        "observability": _unknown_observability(),
    }


def build_diagnostics(
    _context: Mapping[str, object] | None = None,
    *,
    db: AppDatabase | None = None,
    cache_dir: Path | str | None = None,
) -> dict[str, object]:
    if db is None:
        db = AppDatabase(resolve_database_path())
    if cache_dir is None:
        cache_dir = default_cache_dir(Path(__file__).resolve().parents[2])
    payload = unknown_diagnostics()
    payload["database_path_hash"] = _database_path_hash(db.path)

    app_version = _app_version()
    payload["app_version"] = app_version
    observability = dict(payload["observability"])
    observability["app_version"] = "observed" if app_version != UNKNOWN else UNKNOWN

    try:
        cache_bytes = _cache_bytes(cache_dir)
    except Exception:
        cache_bytes = UNKNOWN
    payload["cache_bytes"] = cache_bytes
    observability["cache_bytes"] = "observed" if cache_bytes != UNKNOWN else UNKNOWN

    recommendation_rows: list[dict[str, object]] | None = None
    try:
        with _read_only_connection(db.path) as connection:
            try:
                payload["database_schema_version"] = _database_schema_version(connection)
            except Exception:
                payload["database_schema_version"] = UNKNOWN
            try:
                payload["sync_counts"] = _sync_counts(connection)
            except Exception:
                payload["sync_counts"] = UNKNOWN
            try:
                payload["session_counts"] = _session_counts(connection)
            except Exception:
                payload["session_counts"] = UNKNOWN
            try:
                batch_counts, recommendation_rows = _recommendation_rows(connection)
                payload["batch_counts"] = batch_counts
            except Exception:
                payload["batch_counts"] = UNKNOWN
                recommendation_rows = None
            try:
                provider_health = _provider_attempt_health(connection)
                payload["provider_attempt_health"] = provider_health
                observability["provider_health"] = (
                    "historical_attempts" if provider_health != UNKNOWN else UNKNOWN
                )
            except Exception:
                payload["provider_attempt_health"] = UNKNOWN
            try:
                payload["persistent_queue_states"] = _fixed_state_counts(
                    connection, "resolution_jobs", QUEUE_STATES
                )
                observability["persistent_queue_states"] = "observed"
            except Exception:
                payload["persistent_queue_states"] = UNKNOWN
            try:
                payload["media_totals"] = _media_totals(connection)
            except Exception:
                payload["media_totals"] = UNKNOWN
    except Exception:
        recommendation_rows = None

    if recommendation_rows is not None:
        try:
            payload["media_audit"] = audit_recommendation_media(recommendation_rows, db).to_dict()
            observability["wrong_identity_candidates_scope"] = "aggregate_historical_attempts"
        except Exception:
            payload["media_audit"] = UNKNOWN

    observability["in_memory_queue_depth"] = UNKNOWN
    observability["recommendation_media_identity_attribution"] = UNKNOWN
    payload["observability"] = observability
    return payload
