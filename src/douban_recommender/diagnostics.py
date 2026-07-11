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
from typing import Iterator

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
MEDIA_AUDIT_BATCH_LIMIT = 32
MEDIA_AUDIT_ROW_LIMIT = 256
MANIFEST_QUERY_CHUNK = 400
MEDIA_AUDIT_SCOPE = "recent_recommendation_batches"
MEDIA_AUDIT_ORDERING = "created_at_desc_then_id_desc"
WRONG_IDENTITY_SCOPE = "global_historical_identity_rejected_hard_conflicts"
MISSING_IDENTITY_FOREIGN_KEY = "unavailable_without_stable_foreign_key"


@dataclass(frozen=True)
class MediaAudit:
    total: int
    ready: int
    degraded: int
    ambiguous: int
    missing: int
    wrong_identity_candidates: int | str

    def to_dict(self) -> dict[str, int | str]:
        return asdict(self)


@dataclass(frozen=True)
class HistoricalAttemptMetrics:
    provider_health: dict[str, object] | str = UNKNOWN
    wrong_identity_candidates: int | str = UNKNOWN
    observed: bool = False


class _SingleRowCursor:
    def __init__(self, row: object | None):
        self._row = row

    def fetchone(self) -> object | None:
        return self._row


class _PreloadedManifestConnection:
    def __init__(self, manifests: Mapping[str, object]):
        self._manifests = manifests

    def execute(self, _sql: str, parameters: tuple[object, ...] = ()) -> _SingleRowCursor:
        asset_id = str(parameters[0] if parameters else "").strip().lower()
        return _SingleRowCursor(self._manifests.get(asset_id))


class _PreloadedManifestDatabase:
    def __init__(self, manifests: Mapping[str, object]):
        self._manifests = manifests

    @contextmanager
    def connection(self) -> Iterator[_PreloadedManifestConnection]:
        yield _PreloadedManifestConnection(self._manifests)


class _ReadOnlyManifestMediaStore(MediaStore):
    """MediaStore lookup backed by a request-local, read-only manifest snapshot."""

    def __init__(self, root: Path | str, manifests: Mapping[str, object]):
        self.root = Path(root).expanduser().resolve(strict=False)
        self.database = _PreloadedManifestDatabase(manifests)


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


def _wrong_identity_candidates(connection: sqlite3.Connection) -> int | str:
    return _historical_attempt_metrics(connection).wrong_identity_candidates


def _read_only_media_store(db: AppDatabase, manifests: Mapping[str, object]) -> MediaStore:
    root = Path(db.path).expanduser().resolve(strict=False).parent / "media"
    return _ReadOnlyManifestMediaStore(root, manifests)


def _load_asset_manifests(
    connection: sqlite3.Connection,
    asset_ids: Iterable[str],
) -> dict[str, object]:
    unique_ids = sorted(
        {
            str(asset_id).strip().lower()
            for asset_id in asset_ids
            if str(asset_id).strip()
        }
    )
    manifests: dict[str, object] = {}
    for offset in range(0, len(unique_ids), MANIFEST_QUERY_CHUNK):
        chunk = unique_ids[offset : offset + MANIFEST_QUERY_CHUNK]
        placeholders = ",".join("?" for _ in chunk)
        rows = connection.execute(
            f"""
            SELECT asset_id, sha256, relative_path, mime_type, extension,
                   width, height, byte_size, source_url, kind, status
            FROM asset_files
            WHERE asset_id IN ({placeholders})
            """,
            tuple(chunk),
        ).fetchall()
        for row in rows:
            manifests[str(row["asset_id"] or "").strip().lower()] = row
    return manifests


def _audit_recommendation_media(
    rows: Iterable[object],
    db: AppDatabase,
    connection: sqlite3.Connection,
    wrong_identity_candidates: int | str,
) -> MediaAudit:
    recommendation_rows = list(rows)
    prepared_rows: list[tuple[object, str, re.Match[str] | None]] = []
    asset_ids: set[str] = set()
    for row in recommendation_rows:
        cover = str(_row_value(row, "cover") or "").strip()
        route_match = LOCAL_POSTER_RE.fullmatch(cover)
        prepared_rows.append((row, cover, route_match))
        if route_match:
            asset_ids.add(route_match.group(1).lower())

    manifests = _load_asset_manifests(connection, asset_ids)
    store = _read_only_media_store(db, manifests)
    lookup_cache: dict[str, object | None] = {}
    counts = {"ready": 0, "degraded": 0, "ambiguous": 0, "missing": 0}

    for row, cover, route_match in prepared_rows:
        if not route_match:
            counts["missing"] += 1
            continue

        asset_id = route_match.group(1).lower()
        if asset_id not in manifests:
            counts["missing"] += 1
            continue

        route_filename = f"{asset_id}{route_match.group(2).lower()}"
        if route_filename not in lookup_cache:
            lookup_cache[route_filename] = store.lookup(route_filename)
        stored = lookup_cache[route_filename]
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


def audit_recommendation_media(rows: Iterable[object], db: AppDatabase) -> MediaAudit:
    with _read_only_connection(db.path) as connection:
        wrong_identity_candidates = _wrong_identity_candidates(connection)
        return _audit_recommendation_media(
            rows,
            db,
            connection,
            wrong_identity_candidates,
        )


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


def _recommendation_audit_window(
    connection: sqlite3.Connection,
) -> tuple[dict[str, int], list[dict[str, object]], dict[str, object]]:
    total_row = connection.execute("SELECT COUNT(*) AS count FROM recommendation_batches").fetchone()
    total_batches = _nonnegative_int(total_row["count"])
    fetched = connection.execute(
        """
        SELECT id, payload_json
        FROM recommendation_batches
        ORDER BY created_at DESC, id DESC
        LIMIT ?
        """,
        (MEDIA_AUDIT_BATCH_LIMIT + 1,),
    ).fetchall()
    selected = fetched[:MEDIA_AUDIT_BATCH_LIMIT]
    recommendation_rows: list[dict[str, object]] = []
    row_truncated = False
    for batch_offset, row in enumerate(selected):
        payload = json.loads(str(row["payload_json"] or "{}"))
        if not isinstance(payload, dict):
            raise ValueError("invalid batch payload")
        items = payload.get("items")
        if isinstance(items, list):
            for item in items:
                if not isinstance(item, dict):
                    continue
                if len(recommendation_rows) >= MEDIA_AUDIT_ROW_LIMIT:
                    row_truncated = True
                    break
                recommendation_rows.append(item)
        if len(recommendation_rows) >= MEDIA_AUDIT_ROW_LIMIT:
            if batch_offset < len(selected) - 1:
                row_truncated = True
            break

    truncated = total_batches > len(selected) or row_truncated
    batch_counts = {
        "total": total_batches,
        "audit_window_batches": len(selected),
        "audit_window_rows": len(recommendation_rows),
    }
    window = {
        "scope": MEDIA_AUDIT_SCOPE,
        "ordering": MEDIA_AUDIT_ORDERING,
        "batch_limit": MEDIA_AUDIT_BATCH_LIMIT,
        "row_limit": MEDIA_AUDIT_ROW_LIMIT,
        "selected_batches": len(selected),
        "rows_audited": len(recommendation_rows),
        "truncated": truncated,
    }
    return batch_counts, recommendation_rows, window


def _historical_attempt_metrics(
    connection: sqlite3.Connection,
) -> HistoricalAttemptMetrics:
    status_counts = {status.replace("-", "_"): 0 for status in ATTEMPT_STATUSES}
    status_counts[UNKNOWN] = 0
    provider_counts = {provider: 0 for provider in KNOWN_PROVIDERS}
    provider_counts[UNKNOWN] = 0
    attempts_total = 0
    wrong_identity_candidates = 0
    invalid_history = False
    try:
        rows = connection.execute("SELECT attempts_json FROM resolution_jobs")
        for row in rows:
            try:
                decoded = json.loads(str(row["attempts_json"] or "[]"))
            except (TypeError, ValueError, json.JSONDecodeError):
                invalid_history = True
                continue
            if not isinstance(decoded, list):
                invalid_history = True
                continue
            for attempt in decoded:
                if not isinstance(attempt, dict):
                    invalid_history = True
                    continue
                status = str(attempt.get("status") or "").strip().lower()
                if not status:
                    invalid_history = True
                    continue
                attempts_total += 1
                status_key = status.replace("-", "_") if status in ATTEMPT_STATUSES else UNKNOWN
                status_counts[status_key] += 1
                provider = str(attempt.get("source") or "").strip().lower()
                provider_counts[
                    provider if provider in provider_counts and provider != UNKNOWN else UNKNOWN
                ] += 1
                raw_reasons = attempt.get("reasons")
                reasons = raw_reasons if isinstance(raw_reasons, (list, tuple)) else ()
                normalized = {str(reason or "").strip().lower() for reason in reasons}
                if status == "identity-rejected" and normalized & HARD_IDENTITY_CONFLICTS:
                    wrong_identity_candidates += 1
    except Exception:
        return HistoricalAttemptMetrics()

    if invalid_history or attempts_total == 0:
        return HistoricalAttemptMetrics()
    return HistoricalAttemptMetrics(
        provider_health={
            "basis": "historical_attempts",
            "attempts_total": attempts_total,
            "status_counts": status_counts,
            "provider_counts": provider_counts,
        },
        wrong_identity_candidates=wrong_identity_candidates,
        observed=True,
    )


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


def _unknown_observability_limits() -> dict[str, object]:
    return {
        "app_version": UNKNOWN,
        "provider_health": UNKNOWN,
        "persistent_queue_states": UNKNOWN,
        "in_memory_queue_depth": UNKNOWN,
        "cache_bytes": UNKNOWN,
        "recommendation_media_identity_attribution": UNKNOWN,
        "wrong_identity_candidates_scope": UNKNOWN,
        "media_audit_window": {
            "scope": MEDIA_AUDIT_SCOPE,
            "ordering": MEDIA_AUDIT_ORDERING,
            "batch_limit": MEDIA_AUDIT_BATCH_LIMIT,
            "row_limit": MEDIA_AUDIT_ROW_LIMIT,
            "selected_batches": UNKNOWN,
            "rows_audited": UNKNOWN,
            "truncated": UNKNOWN,
        },
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
        "observability_limits": _unknown_observability_limits(),
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
    observability_limits = dict(payload["observability_limits"])
    observability_limits["app_version"] = "observed" if app_version != UNKNOWN else UNKNOWN

    try:
        cache_bytes = _cache_bytes(cache_dir)
    except Exception:
        cache_bytes = UNKNOWN
    payload["cache_bytes"] = cache_bytes
    observability_limits["cache_bytes"] = "observed" if cache_bytes != UNKNOWN else UNKNOWN

    recommendation_rows: list[dict[str, object]] | None = None
    attempt_metrics = HistoricalAttemptMetrics()
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
                batch_counts, recommendation_rows, media_audit_window = _recommendation_audit_window(connection)
                payload["batch_counts"] = batch_counts
                observability_limits["media_audit_window"] = media_audit_window
            except Exception:
                payload["batch_counts"] = UNKNOWN
                recommendation_rows = None
            try:
                attempt_metrics = _historical_attempt_metrics(connection)
                payload["provider_attempt_health"] = attempt_metrics.provider_health
                observability_limits["provider_health"] = (
                    "historical_attempts" if attempt_metrics.observed else UNKNOWN
                )
            except Exception:
                attempt_metrics = HistoricalAttemptMetrics()
                payload["provider_attempt_health"] = UNKNOWN
            try:
                payload["persistent_queue_states"] = _fixed_state_counts(
                    connection, "resolution_jobs", QUEUE_STATES
                )
                observability_limits["persistent_queue_states"] = "observed"
            except Exception:
                payload["persistent_queue_states"] = UNKNOWN
            try:
                payload["media_totals"] = _media_totals(connection)
            except Exception:
                payload["media_totals"] = UNKNOWN
            if recommendation_rows is not None:
                try:
                    payload["media_audit"] = _audit_recommendation_media(
                        recommendation_rows,
                        db,
                        connection,
                        attempt_metrics.wrong_identity_candidates,
                    ).to_dict()
                    if attempt_metrics.observed:
                        observability_limits["wrong_identity_candidates_scope"] = WRONG_IDENTITY_SCOPE
                        observability_limits["recommendation_media_identity_attribution"] = (
                            MISSING_IDENTITY_FOREIGN_KEY
                        )
                except Exception:
                    payload["media_audit"] = UNKNOWN
    except Exception:
        recommendation_rows = None

    observability_limits["in_memory_queue_depth"] = UNKNOWN
    payload["observability_limits"] = observability_limits
    return payload
