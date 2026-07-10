from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass

from .database import AppDatabase
from .intent_parser import RecommendationIntent
from .models import recommendation_item_key
from .privacy import scrub_sensitive

_FEEDBACK_LIBRARY_STATES = {"watched": "watched", "want": "wanted"}
_FEEDBACK_EXCLUSION_EVENTS = {"not-tonight", "watched"}
_ALLOWED_FEEDBACK_EVENTS = set(_FEEDBACK_LIBRARY_STATES) | _FEEDBACK_EXCLUSION_EVENTS
_UNDO_METADATA_KEY = "_recommendation_undo"


@dataclass(frozen=True)
class RecommendationSession:
    id: str
    profile_key: str
    intent: RecommendationIntent
    channels: dict[str, dict[str, object]]
    status: str
    created_at: float
    updated_at: float


@dataclass(frozen=True)
class RecommendationBatch:
    id: str
    session_id: str
    channel: str
    index: int
    items: tuple[dict[str, object], ...]
    item_keys: tuple[str, ...]
    pool_size: int
    matched_size: int
    visible_size: int
    reason: str = ""
    exhausted: bool = False
    created_at: float = 0.0

    def to_dict(self) -> dict[str, object]:
        return {
            "id": self.id,
            "session_id": self.session_id,
            "channel": self.channel,
            "index": self.index,
            "items": [dict(item) for item in self.items],
            "item_keys": list(self.item_keys),
            "pool_size": self.pool_size,
            "matched_size": self.matched_size,
            "visible_size": self.visible_size,
            "reason": self.reason,
            "exhausted": self.exhausted,
            "created_at": self.created_at,
        }


def _serialize_item(value) -> dict[str, object]:
    if isinstance(value, dict):
        return dict(value)
    to_dict = getattr(value, "to_dict", None)
    if callable(to_dict):
        payload = to_dict()
        return dict(payload) if isinstance(payload, dict) else {}
    return {}


def _item_key(item: dict[str, object]) -> str:
    return recommendation_item_key(item)


def _json_dumps(payload: object) -> str:
    return json.dumps(payload, ensure_ascii=False, separators=(",", ":"))


def _json_object(value: object) -> dict[str, object]:
    try:
        decoded = json.loads(str(value or "{}"))
    except (TypeError, ValueError, json.JSONDecodeError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _scrub_dict(value: object) -> dict[str, object]:
    scrubbed = scrub_sensitive(value)
    return scrubbed if isinstance(scrubbed, dict) else {}


def _undone_event_ids(connection) -> set[str]:
    rows = connection.execute(
        "SELECT payload_json FROM feedback_events WHERE event_type = 'undo'"
    ).fetchall()
    return {
        target
        for row in rows
        for payload in [_json_object(row["payload_json"])]
        for target in [str(payload.get("target_event_id") or "")]
        if target
    }


def _next_feedback_timestamp(connection) -> float:
    row = connection.execute("SELECT MAX(created_at) AS latest FROM feedback_events").fetchone()
    latest = float(row["latest"] or 0) if row else 0.0
    return max(time.time(), latest + 1e-6)


class RecommendationSessionService:
    def __init__(self, database: AppDatabase):
        self.database = database
        self.database.initialize()
        self._lock = threading.RLock()

    def create_session(
        self,
        profile_key: str,
        intent: RecommendationIntent,
        ranked_by_channel: dict[str, object],
        batch_size_by_channel: dict[str, int],
    ) -> RecommendationSession:
        session_id = uuid.uuid4().hex
        now = time.time()
        channels: dict[str, dict[str, object]] = {}
        for channel, value in ranked_by_channel.items():
            if isinstance(value, dict):
                raw_items = value.get("items") or []
                pool_size = int(value.get("pool_size") or len(raw_items))
                matched_size = int(value.get("matched_size") or len(raw_items))
            else:
                raw_items = value or []
                pool_size = len(raw_items)
                matched_size = len(raw_items)
            items = [item for raw in raw_items for item in [_scrub_dict(_serialize_item(raw))] if item]
            channels[str(channel)] = {
                "items": items,
                "pool_size": max(pool_size, len(items)),
                "matched_size": max(matched_size, len(items)),
                "batch_size": max(1, int(batch_size_by_channel.get(channel) or 9)),
                "cursor": 0,
                "active_batch": 0,
                "last_batch": 0,
                "excluded_keys": [],
            }
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            connection.execute(
                """
                INSERT INTO recommendation_sessions(
                    id, profile_key, intent_json, channels_json, status,
                    created_at, updated_at
                ) VALUES(?, ?, ?, ?, 'active', ?, ?)
                """,
                (
                    session_id,
                    str(profile_key or "default"),
                    _json_dumps(intent.to_dict()),
                    _json_dumps(channels),
                    now,
                    now,
                ),
            )
            for state in channels.values():
                for item in state.get("items", []):
                    if isinstance(item, dict):
                        self._upsert_library_item(
                            connection,
                            _item_key(item),
                            item,
                            "candidate",
                            "recommendation",
                            now,
                        )
        return RecommendationSession(
            id=session_id,
            profile_key=str(profile_key or "default"),
            intent=intent,
            channels=channels,
            status="active",
            created_at=now,
            updated_at=now,
        )

    def _session_row(self, session_id: str):
        with self.database.connection() as connection:
            row = self._session_row_in_connection(connection, session_id)
        return row

    def _session_row_in_connection(self, connection, session_id: str):
        row = connection.execute(
            """
            SELECT id, profile_key, intent_json, channels_json, status,
                   created_at, updated_at
            FROM recommendation_sessions WHERE id = ?
            """,
            (str(session_id),),
        ).fetchone()
        if not row:
            raise ValueError("recommendation session not found")
        return row

    def _session_from_row(self, row) -> RecommendationSession:
        return RecommendationSession(
            id=str(row["id"]),
            profile_key=str(row["profile_key"]),
            intent=RecommendationIntent.from_dict(json.loads(str(row["intent_json"]))),
            channels=json.loads(str(row["channels_json"])),
            status=str(row["status"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def restore_session(self, session_id: str) -> RecommendationSession:
        row = self._session_row(session_id)
        return self._session_from_row(row)

    def _save_channels(self, connection, session_id: str, channels: dict[str, dict[str, object]], now: float | None = None) -> None:
        connection.execute(
            "UPDATE recommendation_sessions SET channels_json = ?, updated_at = ? WHERE id = ?",
            (
                _json_dumps(channels),
                time.time() if now is None else now,
                str(session_id),
            ),
        )

    def _batch_from_row(self, row) -> RecommendationBatch:
        payload = _json_object(row["payload_json"])
        return RecommendationBatch(
            id=str(row["id"]),
            session_id=str(row["session_id"]),
            channel=str(row["channel"]),
            index=int(row["batch_index"]),
            items=tuple(dict(item) for item in payload.get("items", []) if isinstance(item, dict)),
            item_keys=tuple(json.loads(str(row["item_keys_json"] or "[]"))),
            pool_size=int(payload.get("pool_size") or 0),
            matched_size=int(payload.get("matched_size") or 0),
            visible_size=int(payload.get("visible_size") or 0),
            reason=str(row["reason"] or ""),
            exhausted=bool(payload.get("exhausted", False)),
            created_at=float(row["created_at"]),
        )

    def _load_batch(self, session_id: str, channel: str, index: int) -> RecommendationBatch:
        with self.database.connection() as connection:
            row = self._load_batch_row(connection, session_id, channel, index)
        return self._batch_from_row(row)

    def _load_batch_row(self, connection, session_id: str, channel: str, index: int):
        row = connection.execute(
            """
            SELECT id, session_id, channel, batch_index, item_keys_json,
                   reason, payload_json, created_at
            FROM recommendation_batches
            WHERE session_id = ? AND channel = ? AND batch_index = ?
            """,
            (str(session_id), str(channel), int(index)),
        ).fetchone()
        if not row:
            raise ValueError("recommendation batch not found")
        return row

    def _store_batch(
        self,
        connection,
        session_id: str,
        channel: str,
        index: int,
        item_keys: list[str],
        reason: str,
        payload: dict[str, object],
    ) -> RecommendationBatch:
        clean_payload = dict(payload)
        clean_payload["items"] = [
            clean_item
            for item in payload.get("items", [])
            if isinstance(item, dict)
            for clean_item in [_scrub_dict(item)]
            if clean_item
        ]
        batch_id = uuid.uuid4().hex
        now = time.time()
        connection.execute(
            """
            INSERT INTO recommendation_batches(
                id, session_id, channel, batch_index, item_keys_json,
                reason, payload_json, created_at
            ) VALUES(?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                batch_id,
                session_id,
                channel,
                index,
                _json_dumps(item_keys),
                str(reason or ""),
                _json_dumps(clean_payload),
                now,
            ),
        )
        return RecommendationBatch(
            id=batch_id,
            session_id=session_id,
            channel=channel,
            index=index,
            items=tuple(dict(item) for item in clean_payload.get("items", []) if isinstance(item, dict)),
            item_keys=tuple(item_keys),
            pool_size=int(clean_payload.get("pool_size") or 0),
            matched_size=int(clean_payload.get("matched_size") or 0),
            visible_size=int(clean_payload.get("visible_size") or 0),
            reason=str(reason or ""),
            exhausted=bool(clean_payload.get("exhausted", False)),
            created_at=now,
        )

    def _upsert_library_item(
        self,
        connection,
        item_key: str,
        payload: dict[str, object],
        state: str,
        source: str,
        now: float | None = None,
    ) -> None:
        timestamp = time.time() if now is None else now
        connection.execute(
            """
            INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
            VALUES(?, ?, ?, ?, ?, ?)
            ON CONFLICT(item_key) DO UPDATE SET
                payload_json = excluded.payload_json,
                state = CASE
                    WHEN excluded.state = 'candidate'
                         AND library_items.state IN ('watched', 'wanted')
                    THEN library_items.state
                    WHEN excluded.state = 'wanted'
                         AND library_items.state = 'watched'
                    THEN library_items.state
                    ELSE excluded.state
                END,
                source = excluded.source,
                updated_at = excluded.updated_at
            """,
            (
                str(item_key),
                _json_dumps(_scrub_dict(dict(payload))),
                str(state),
                str(source or ""),
                timestamp,
                timestamp,
            ),
        )

    def _find_session_item(self, channels: dict[str, dict[str, object]], item_key: str) -> dict[str, object] | None:
        for state in channels.values():
            for item in state.get("items", []):
                if isinstance(item, dict) and _item_key(item) == item_key:
                    return dict(item)
        return None

    def _exclude_key(self, channels: dict[str, dict[str, object]], item_key: str) -> bool:
        changed = False
        for state in channels.values():
            excluded = [str(key) for key in state.get("excluded_keys", []) if str(key)]
            if item_key not in excluded:
                excluded.append(item_key)
                state["excluded_keys"] = excluded
                changed = True
            elif state.get("excluded_keys") != excluded:
                state["excluded_keys"] = excluded
                changed = True
        return changed

    def library_items(self, states: list[str] | tuple[str, ...] | set[str] | None = None) -> list[dict[str, object]]:
        state_values = [str(state) for state in (states or []) if str(state)]
        params: list[str] = []
        where = ""
        if state_values:
            placeholders = ",".join("?" for _ in state_values)
            where = f" WHERE state IN ({placeholders})"
            params.extend(state_values)
        with self.database.connection() as connection:
            rows = connection.execute(
                f"""
                SELECT item_key, payload_json, state, source, created_at, updated_at
                FROM library_items{where}
                ORDER BY updated_at DESC, item_key DESC
                """,
                params,
            ).fetchall()
        return [
            {
                "item_key": str(row["item_key"]),
                "payload": _json_object(row["payload_json"]),
                "state": str(row["state"] or ""),
                "source": str(row["source"] or ""),
                "created_at": float(row["created_at"] or 0),
                "updated_at": float(row["updated_at"] or 0),
            }
            for row in rows
        ]

    def apply_feedback(
        self,
        session_id: str,
        event_type: str,
        item_key: str,
        payload: dict[str, object] | None = None,
    ) -> dict[str, object]:
        clean_event_type = str(event_type or "").strip()
        clean_item_key = str(item_key or "").strip()
        if clean_event_type not in _ALLOWED_FEEDBACK_EVENTS:
            raise ValueError("unsupported feedback event")
        if not clean_item_key:
            raise ValueError("recommendation item not found")

        with self._lock:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = self._session_row_in_connection(connection, session_id)
                session = self._session_from_row(row)
                channels = session.channels
                item_payload = self._find_session_item(channels, clean_item_key)
                if item_payload is None:
                    raise ValueError("recommendation item not found")

                state = _FEEDBACK_LIBRARY_STATES.get(clean_event_type, "")
                excluded = clean_event_type in _FEEDBACK_EXCLUSION_EVENTS
                undone_ids = _undone_event_ids(connection)
                existing_rows = connection.execute(
                    """
                    SELECT id, undone_by FROM feedback_events
                    WHERE session_id = ? AND item_key = ? AND event_type = ?
                    ORDER BY created_at DESC, id DESC
                    """,
                    (session.id, clean_item_key, clean_event_type),
                ).fetchall()
                existing = next(
                    (
                        candidate
                        for candidate in existing_rows
                        if not str(candidate["undone_by"] or "") and str(candidate["id"]) not in undone_ids
                    ),
                    None,
                )
                if existing:
                    event_id = str(existing["id"])
                else:
                    prior_excluded_channels = [
                        channel
                        for channel, channel_state in channels.items()
                        if clean_item_key in {str(key) for key in channel_state.get("excluded_keys", [])}
                    ]
                    prior_library = None
                    if state:
                        library_row = connection.execute(
                            """
                            SELECT payload_json, state, source, created_at, updated_at
                            FROM library_items WHERE item_key = ?
                            """,
                            (clean_item_key,),
                        ).fetchone()
                        if library_row:
                            prior_library = {
                                "exists": True,
                                "payload": _json_object(library_row["payload_json"]),
                                "state": str(library_row["state"] or ""),
                                "source": str(library_row["source"] or ""),
                                "created_at": float(library_row["created_at"] or 0),
                                "updated_at": float(library_row["updated_at"] or 0),
                            }
                        else:
                            prior_library = {"exists": False}
                    if state:
                        self._upsert_library_item(
                            connection,
                            clean_item_key,
                            item_payload,
                            state,
                            f"feedback:{clean_event_type}",
                        )

                    if excluded and self._exclude_key(channels, clean_item_key):
                        self._save_channels(connection, session.id, channels)

                    event_payload = _scrub_dict(dict(payload or {}))
                    event_payload["item"] = item_payload
                    event_payload[_UNDO_METADATA_KEY] = {
                        "prior_excluded_channels": prior_excluded_channels,
                        "prior_library": prior_library,
                    }
                    event_id = uuid.uuid4().hex
                    connection.execute(
                        """
                        INSERT INTO feedback_events(
                            id, profile_key, session_id, item_key, event_type,
                            payload_json, undone_by, created_at
                        ) VALUES(?, ?, ?, ?, ?, ?, NULL, ?)
                        """,
                        (
                            event_id,
                            session.profile_key,
                            session.id,
                            clean_item_key,
                            clean_event_type,
                            _json_dumps(event_payload),
                            _next_feedback_timestamp(connection),
                        ),
                    )

        return {
            "event_id": event_id,
            "session_id": str(session_id),
            "event_type": clean_event_type,
            "item_key": clean_item_key,
            "state": state,
            "excluded": excluded,
            "payload": item_payload,
        }

    def undo_feedback(self, event_id: str) -> str | None:
        target_id = str(event_id or "").strip()
        with self._lock:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                row = connection.execute(
                    """
                    SELECT id, profile_key, session_id, item_key, event_type,
                           payload_json, undone_by, created_at
                    FROM feedback_events
                    WHERE id = ? AND event_type != 'undo'
                    """,
                    (target_id,),
                ).fetchone()
                if not row:
                    raise ValueError("feedback event not found")
                session_id = str(row["session_id"] or "")
                event_type = str(row["event_type"] or "")
                if not session_id or event_type not in _ALLOWED_FEEDBACK_EVENTS:
                    return None
                if str(row["undone_by"] or ""):
                    return str(row["undone_by"])

                existing_undo = connection.execute(
                    "SELECT id, payload_json FROM feedback_events WHERE event_type = 'undo' ORDER BY created_at, id"
                ).fetchall()
                for undo_row in existing_undo:
                    undo_payload = _json_object(undo_row["payload_json"])
                    if str(undo_payload.get("target_event_id") or "") == target_id:
                        undo_id = str(undo_row["id"])
                        connection.execute("UPDATE feedback_events SET undone_by = ? WHERE id = ?", (undo_id, target_id))
                        return undo_id

                session = self._session_from_row(self._session_row_in_connection(connection, session_id))
                item_key = str(row["item_key"] or "")
                target_created_at = float(row["created_at"] or 0)
                undone_ids = _undone_event_ids(connection)
                later_session_rows = connection.execute(
                    """
                    SELECT id, event_type, undone_by, created_at
                    FROM feedback_events
                    WHERE session_id = ? AND item_key = ? AND event_type != 'undo'
                      AND (created_at > ? OR (created_at = ? AND id > ?))
                    ORDER BY created_at, id
                    """,
                    (session_id, item_key, target_created_at, target_created_at, target_id),
                ).fetchall()
                later_library_rows = connection.execute(
                    """
                    SELECT id, event_type, undone_by, created_at
                    FROM feedback_events
                    WHERE item_key = ? AND event_type IN ('watched', 'want')
                      AND COALESCE(session_id, '') != ''
                      AND (created_at > ? OR (created_at = ? AND id > ?))
                    ORDER BY created_at, id
                    """,
                    (item_key, target_created_at, target_created_at, target_id),
                ).fetchall()
                active_later_session_types = {
                    str(candidate["event_type"])
                    for candidate in later_session_rows
                    if not str(candidate["undone_by"] or "") and str(candidate["id"]) not in undone_ids
                }
                has_later_library_update = any(
                    not str(candidate["undone_by"] or "") and str(candidate["id"]) not in undone_ids
                    for candidate in later_library_rows
                )

                payload = _json_object(row["payload_json"])
                metadata = payload.get(_UNDO_METADATA_KEY)
                metadata = metadata if isinstance(metadata, dict) else {}
                channels = session.channels
                if (
                    event_type in _FEEDBACK_EXCLUSION_EVENTS
                    and not (active_later_session_types & _FEEDBACK_EXCLUSION_EVENTS)
                    and "prior_excluded_channels" in metadata
                ):
                    prior_channels = {str(channel) for channel in metadata.get("prior_excluded_channels", [])}
                    for channel, state in channels.items():
                        excluded = [str(key) for key in state.get("excluded_keys", []) if str(key)]
                        excluded = [key for key in excluded if key != item_key]
                        if channel in prior_channels:
                            excluded.append(item_key)
                        state["excluded_keys"] = list(dict.fromkeys(excluded))
                    self._save_channels(connection, session_id, channels)

                if event_type in _FEEDBACK_LIBRARY_STATES and not has_later_library_update:
                    prior_library = metadata.get("prior_library")
                    if isinstance(prior_library, dict) and prior_library.get("exists") is True:
                        connection.execute(
                            """
                            INSERT INTO library_items(item_key, payload_json, state, source, created_at, updated_at)
                            VALUES(?, ?, ?, ?, ?, ?)
                            ON CONFLICT(item_key) DO UPDATE SET
                                payload_json = excluded.payload_json,
                                state = excluded.state,
                                source = excluded.source,
                                created_at = excluded.created_at,
                                updated_at = excluded.updated_at
                            """,
                            (
                                item_key,
                                _json_dumps(_scrub_dict(prior_library.get("payload") or {})),
                                str(prior_library.get("state") or "candidate"),
                                str(prior_library.get("source") or ""),
                                float(prior_library.get("created_at") or 0),
                                float(prior_library.get("updated_at") or 0),
                            ),
                        )
                    elif isinstance(prior_library, dict) and prior_library.get("exists") is False:
                        connection.execute("DELETE FROM library_items WHERE item_key = ?", (item_key,))

                undo_id = uuid.uuid4().hex
                connection.execute(
                    """
                    INSERT INTO feedback_events(
                        id, profile_key, session_id, item_key, event_type,
                        payload_json, undone_by, created_at
                    ) VALUES(?, ?, ?, ?, 'undo', ?, NULL, ?)
                    """,
                    (
                        undo_id,
                        str(row["profile_key"]),
                        session_id,
                        item_key,
                        _json_dumps({"target_event_id": target_id}),
                        _next_feedback_timestamp(connection),
                    ),
                )
                connection.execute("UPDATE feedback_events SET undone_by = ? WHERE id = ?", (undo_id, target_id))
                return undo_id

    def next_batch(self, session_id: str, channel: str, reason: str = "") -> RecommendationBatch:
        with self._lock:
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                session = self._session_from_row(self._session_row_in_connection(connection, session_id))
                if channel not in session.channels:
                    raise ValueError("recommendation channel not found")
                channels = session.channels
                state = channels[channel]
                state.setdefault("excluded_keys", [])
                active_batch = int(state.get("active_batch") or 0)
                last_batch = int(state.get("last_batch") or 0)
                if active_batch < last_batch:
                    active_batch += 1
                    state["active_batch"] = active_batch
                    self._save_channels(connection, session_id, channels)
                    return self._batch_from_row(self._load_batch_row(connection, session_id, channel, active_batch))

                items = [dict(item) for item in state.get("items", []) if isinstance(item, dict)]
                cursor = int(state.get("cursor") or 0)
                batch_size = max(1, int(state.get("batch_size") or 9))
                pool_size = int(state.get("pool_size") or len(items))
                matched_size = int(state.get("matched_size") or len(items))
                if cursor >= len(items):
                    if active_batch > 0:
                        current = self._batch_from_row(self._load_batch_row(connection, session_id, channel, active_batch))
                        if current.exhausted and current.visible_size == 0:
                            return current
                    index = last_batch + 1
                    batch = self._store_batch(
                        connection,
                        session_id,
                        channel,
                        index,
                        [],
                        str(reason or ""),
                        {
                            "items": [],
                            "pool_size": pool_size,
                            "matched_size": matched_size,
                            "visible_size": 0,
                            "exhausted": True,
                        },
                    )
                    state["active_batch"] = index
                    state["last_batch"] = index
                    self._save_channels(connection, session_id, channels)
                    return batch

                excluded_keys = {str(key) for key in state.get("excluded_keys", []) if str(key)}
                selected: list[dict[str, object]] = []
                next_cursor = cursor
                while next_cursor < len(items) and len(selected) < batch_size:
                    item = items[next_cursor]
                    next_cursor += 1
                    if _item_key(item) in excluded_keys:
                        continue
                    selected.append(item)

                index = last_batch + 1
                item_keys = [_item_key(item) for item in selected]
                payload = {
                    "items": selected,
                    "pool_size": pool_size,
                    "matched_size": matched_size,
                    "visible_size": len(selected),
                    "exhausted": next_cursor >= len(items),
                }
                batch = self._store_batch(connection, session_id, channel, index, item_keys, str(reason or ""), payload)
                state["cursor"] = next_cursor
                state["active_batch"] = index
                state["last_batch"] = index
                self._save_channels(connection, session_id, channels)
                return batch

    def current_batch(self, session_id: str, channel: str) -> RecommendationBatch:
        with self._lock:
            with self.database.connection() as connection:
                session = self._session_from_row(self._session_row_in_connection(connection, session_id))
                state = session.channels.get(channel)
                if state is None:
                    raise ValueError("recommendation channel not found")
                active = int(state.get("active_batch") or 0)
                if active > 0:
                    return self._batch_from_row(self._load_batch_row(connection, session_id, channel, active))
        return self.next_batch(session_id, channel)

    def previous_batch(self, session_id: str, channel: str) -> RecommendationBatch:
        with self._lock:
            needs_first_batch = False
            with self.database.connection() as connection:
                connection.execute("BEGIN IMMEDIATE")
                session = self._session_from_row(self._session_row_in_connection(connection, session_id))
                if channel not in session.channels:
                    raise ValueError("recommendation channel not found")
                channels = session.channels
                state = channels[channel]
                active = int(state.get("active_batch") or 0)
                if active <= 1:
                    if active <= 0:
                        needs_first_batch = True
                    else:
                        return self._batch_from_row(self._load_batch_row(connection, session_id, channel, active))
                else:
                    active -= 1
                    state["active_batch"] = active
                    self._save_channels(connection, session_id, channels)
                    return self._batch_from_row(self._load_batch_row(connection, session_id, channel, active))
            if needs_first_batch:
                return self.next_batch(session_id, channel)
