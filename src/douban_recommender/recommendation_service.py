from __future__ import annotations

import json
import threading
import time
import uuid
from dataclasses import dataclass

from .database import AppDatabase
from .intent_parser import RecommendationIntent
from .models import recommendation_item_key


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
            items = [item for raw in raw_items for item in [_serialize_item(raw)] if item]
            channels[str(channel)] = {
                "items": items,
                "pool_size": max(pool_size, len(items)),
                "matched_size": max(matched_size, len(items)),
                "batch_size": max(1, int(batch_size_by_channel.get(channel) or 9)),
                "cursor": 0,
                "active_batch": 0,
                "last_batch": 0,
            }
        with self.database.connection() as connection:
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
                    json.dumps(intent.to_dict(), ensure_ascii=False, separators=(",", ":")),
                    json.dumps(channels, ensure_ascii=False, separators=(",", ":")),
                    now,
                    now,
                ),
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

    def restore_session(self, session_id: str) -> RecommendationSession:
        row = self._session_row(session_id)
        return RecommendationSession(
            id=str(row["id"]),
            profile_key=str(row["profile_key"]),
            intent=RecommendationIntent.from_dict(json.loads(str(row["intent_json"]))),
            channels=json.loads(str(row["channels_json"])),
            status=str(row["status"]),
            created_at=float(row["created_at"]),
            updated_at=float(row["updated_at"]),
        )

    def _save_channels(self, session_id: str, channels: dict[str, dict[str, object]]) -> None:
        with self.database.connection() as connection:
            connection.execute(
                "UPDATE recommendation_sessions SET channels_json = ?, updated_at = ? WHERE id = ?",
                (
                    json.dumps(channels, ensure_ascii=False, separators=(",", ":")),
                    time.time(),
                    str(session_id),
                ),
            )

    def _load_batch(self, session_id: str, channel: str, index: int) -> RecommendationBatch:
        with self.database.connection() as connection:
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
        payload = json.loads(str(row["payload_json"] or "{}"))
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

    def next_batch(self, session_id: str, channel: str, reason: str = "") -> RecommendationBatch:
        with self._lock:
            session = self.restore_session(session_id)
            if channel not in session.channels:
                raise ValueError("recommendation channel not found")
            channels = session.channels
            state = channels[channel]
            active_batch = int(state.get("active_batch") or 0)
            last_batch = int(state.get("last_batch") or 0)
            if active_batch < last_batch:
                active_batch += 1
                state["active_batch"] = active_batch
                self._save_channels(session_id, channels)
                return self._load_batch(session_id, channel, active_batch)

            items = [dict(item) for item in state.get("items", []) if isinstance(item, dict)]
            cursor = int(state.get("cursor") or 0)
            batch_size = max(1, int(state.get("batch_size") or 9))
            pool_size = int(state.get("pool_size") or len(items))
            matched_size = int(state.get("matched_size") or len(items))
            if cursor >= len(items):
                return RecommendationBatch(
                    id=f"exhausted:{session_id}:{channel}:{last_batch + 1}",
                    session_id=session_id,
                    channel=channel,
                    index=last_batch + 1,
                    items=(),
                    item_keys=(),
                    pool_size=pool_size,
                    matched_size=matched_size,
                    visible_size=0,
                    reason=str(reason or ""),
                    exhausted=True,
                    created_at=time.time(),
                )

            selected = items[cursor : cursor + batch_size]
            index = last_batch + 1
            batch_id = uuid.uuid4().hex
            item_keys = [_item_key(item) for item in selected]
            now = time.time()
            payload = {
                "items": selected,
                "pool_size": pool_size,
                "matched_size": matched_size,
                "visible_size": len(selected),
                "exhausted": cursor + len(selected) >= len(items),
            }
            with self.database.connection() as connection:
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
                        json.dumps(item_keys, ensure_ascii=False, separators=(",", ":")),
                        str(reason or ""),
                        json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                        now,
                    ),
                )
            state["cursor"] = cursor + len(selected)
            state["active_batch"] = index
            state["last_batch"] = index
            self._save_channels(session_id, channels)
            return RecommendationBatch(
                id=batch_id,
                session_id=session_id,
                channel=channel,
                index=index,
                items=tuple(selected),
                item_keys=tuple(item_keys),
                pool_size=pool_size,
                matched_size=matched_size,
                visible_size=len(selected),
                reason=str(reason or ""),
                exhausted=bool(payload["exhausted"]),
                created_at=now,
            )

    def current_batch(self, session_id: str, channel: str) -> RecommendationBatch:
        session = self.restore_session(session_id)
        state = session.channels.get(channel)
        if state is None:
            raise ValueError("recommendation channel not found")
        active = int(state.get("active_batch") or 0)
        if active <= 0:
            return self.next_batch(session_id, channel)
        return self._load_batch(session_id, channel, active)

    def previous_batch(self, session_id: str, channel: str) -> RecommendationBatch:
        with self._lock:
            session = self.restore_session(session_id)
            if channel not in session.channels:
                raise ValueError("recommendation channel not found")
            channels = session.channels
            state = channels[channel]
            active = int(state.get("active_batch") or 0)
            if active <= 1:
                return self.current_batch(session_id, channel)
            active -= 1
            state["active_batch"] = active
            self._save_channels(session_id, channels)
            return self._load_batch(session_id, channel, active)
