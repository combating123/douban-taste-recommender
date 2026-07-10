from __future__ import annotations

import json
import sqlite3
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Iterator


SCHEMA_V1 = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS ui_snapshots (
    key TEXT PRIMARY KEY,
    payload_json TEXT NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_sessions (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    intent_json TEXT NOT NULL,
    channels_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'active',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS recommendation_batches (
    id TEXT PRIMARY KEY,
    session_id TEXT NOT NULL REFERENCES recommendation_sessions(id) ON DELETE CASCADE,
    channel TEXT NOT NULL,
    batch_index INTEGER NOT NULL,
    item_keys_json TEXT NOT NULL,
    reason TEXT NOT NULL DEFAULT '',
    payload_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    UNIQUE(session_id, channel, batch_index)
);

CREATE TABLE IF NOT EXISTS feedback_events (
    id TEXT PRIMARY KEY,
    profile_key TEXT NOT NULL,
    session_id TEXT,
    item_key TEXT NOT NULL,
    event_type TEXT NOT NULL,
    payload_json TEXT NOT NULL DEFAULT '{}',
    undone_by TEXT,
    created_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS media_identities (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    original_titles_json TEXT NOT NULL DEFAULT '[]',
    year INTEGER,
    media_type TEXT NOT NULL DEFAULT '',
    countries_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS person_identities (
    id TEXT PRIMARY KEY,
    name TEXT NOT NULL,
    aliases_json TEXT NOT NULL DEFAULT '[]',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS provider_identities (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    provider TEXT NOT NULL,
    provider_id TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(entity_kind, provider, provider_id)
);

CREATE TABLE IF NOT EXISTS asset_files (
    asset_id TEXT PRIMARY KEY,
    sha256 TEXT NOT NULL UNIQUE,
    relative_path TEXT NOT NULL UNIQUE,
    mime_type TEXT NOT NULL,
    extension TEXT NOT NULL,
    width INTEGER NOT NULL,
    height INTEGER NOT NULL,
    byte_size INTEGER NOT NULL,
    source_url TEXT NOT NULL DEFAULT '',
    kind TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'ready',
    created_at REAL NOT NULL,
    last_verified_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS asset_candidates (
    id TEXT PRIMARY KEY,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    source TEXT NOT NULL,
    url TEXT NOT NULL,
    confidence REAL NOT NULL DEFAULT 0,
    status TEXT NOT NULL DEFAULT 'unknown',
    metadata_json TEXT NOT NULL DEFAULT '{}',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS resolution_jobs (
    id TEXT PRIMARY KEY,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    priority INTEGER NOT NULL DEFAULT 0,
    state TEXT NOT NULL DEFAULT 'queued',
    current_source TEXT NOT NULL DEFAULT '',
    attempts_json TEXT NOT NULL DEFAULT '[]',
    error TEXT NOT NULL DEFAULT '',
    next_retry_at REAL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS user_asset_overrides (
    id TEXT PRIMARY KEY,
    entity_kind TEXT NOT NULL,
    entity_id TEXT NOT NULL,
    kind TEXT NOT NULL,
    asset_id TEXT,
    decision TEXT NOT NULL,
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL,
    UNIQUE(entity_kind, entity_id, kind)
);

CREATE TABLE IF NOT EXISTS sync_jobs (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    state TEXT NOT NULL DEFAULT 'queued',
    request_json TEXT NOT NULL DEFAULT '{}',
    result_json TEXT NOT NULL DEFAULT '{}',
    resume_of TEXT NOT NULL DEFAULT '',
    error TEXT NOT NULL DEFAULT '',
    created_at REAL NOT NULL,
    updated_at REAL NOT NULL
);

CREATE TABLE IF NOT EXISTS sync_items (
    job_id TEXT NOT NULL REFERENCES sync_jobs(id) ON DELETE CASCADE,
    item_key TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    source TEXT NOT NULL DEFAULT '',
    status TEXT NOT NULL DEFAULT 'ready',
    PRIMARY KEY(job_id, item_key)
);

CREATE INDEX IF NOT EXISTS idx_batches_session_channel
    ON recommendation_batches(session_id, channel, batch_index);
CREATE INDEX IF NOT EXISTS idx_feedback_profile_time
    ON feedback_events(profile_key, created_at);
CREATE INDEX IF NOT EXISTS idx_provider_entity
    ON provider_identities(entity_kind, entity_id);
CREATE INDEX IF NOT EXISTS idx_candidates_entity
    ON asset_candidates(entity_kind, entity_id, kind);
CREATE INDEX IF NOT EXISTS idx_resolution_state_priority
    ON resolution_jobs(state, priority DESC, created_at);
CREATE INDEX IF NOT EXISTS idx_sync_jobs_user_time
    ON sync_jobs(user_id, created_at DESC);
"""


class AppDatabase:
    SCHEMA_VERSION = 2

    def __init__(self, path: Path | str):
        self.path = Path(path)

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30.0)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        connection.execute("PRAGMA busy_timeout = 30000")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def initialize(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        with self.connection() as connection:
            connection.executescript(SCHEMA_V1)
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES('version', ?)",
                (str(self.SCHEMA_VERSION),),
            )

    def set_meta(self, key: str, value: str) -> None:
        self.initialize()
        with self.connection() as connection:
            connection.execute(
                "INSERT OR REPLACE INTO schema_meta(key, value) VALUES(?, ?)",
                (str(key), str(value)),
            )

    def get_meta(self, key: str) -> str | None:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT value FROM schema_meta WHERE key = ?",
                (str(key),),
            ).fetchone()
        return str(row[0]) if row else None

    def upsert_ui_snapshot(self, key: str, payload: dict[str, Any]) -> None:
        self.initialize()
        encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        with self.connection() as connection:
            connection.execute(
                """
                INSERT INTO ui_snapshots(key, payload_json, updated_at)
                VALUES(?, ?, ?)
                ON CONFLICT(key) DO UPDATE SET
                    payload_json = excluded.payload_json,
                    updated_at = excluded.updated_at
                """,
                (str(key), encoded, time.time()),
            )

    def get_ui_snapshot(self, key: str) -> dict[str, Any] | None:
        self.initialize()
        with self.connection() as connection:
            row = connection.execute(
                "SELECT payload_json FROM ui_snapshots WHERE key = ?",
                (str(key),),
            ).fetchone()
        if not row:
            return None
        payload = json.loads(str(row[0]))
        return payload if isinstance(payload, dict) else None
