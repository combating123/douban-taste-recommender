from __future__ import annotations

import json
import time
import uuid
from dataclasses import dataclass, field
from datetime import datetime, timezone

from .database import AppDatabase
from .privacy import scrub_sensitive


ALLOWED_EVENT_TYPES = {
    "want",
    "watched",
    "tonight-candidate",
    "not-tonight",
    "less-like-this",
    "more-like-this",
    "permanent-avoid",
    "data-error",
    "undo",
}
DRIFT_WEIGHTS = {
    "want": 0.4,
    "more-like-this": 1.0,
    "less-like-this": -0.7,
    "permanent-avoid": -1.6,
}


@dataclass(frozen=True)
class FeedbackEvent:
    event_type: str
    item_key: str
    profile_key: str = "default"
    session_id: str = ""
    payload: dict[str, object] = field(default_factory=dict)
    created_at: datetime | float | None = None


@dataclass(frozen=True)
class FeedbackDriftSignal:
    feature: str
    positive_weight: float = 0.0
    negative_weight: float = 0.0
    count: int = 0

    @property
    def net_weight(self) -> float:
        return round(self.positive_weight - self.negative_weight, 4)

    @property
    def direction(self) -> str:
        if self.net_weight > 0:
            return "positive"
        if self.net_weight < 0:
            return "negative"
        return "mixed"

    def as_dict(self) -> dict[str, object]:
        return {
            "feature": self.feature,
            "direction": self.direction,
            "net_weight": self.net_weight,
            "positive_weight": round(self.positive_weight, 4),
            "negative_weight": round(self.negative_weight, 4),
            "count": self.count,
        }


@dataclass(frozen=True)
class FeedbackSignals:
    positive: tuple[str, ...] = ()
    weak_negative: tuple[str, ...] = ()
    permanent_negative: tuple[str, ...] = ()
    permanent_excluded_item_keys: tuple[str, ...] = ()
    session_adjustments: dict[str, tuple[str, ...]] = field(default_factory=dict)
    recent_30: tuple[str, ...] = ()
    recent_90: tuple[str, ...] = ()
    drift_30: tuple[FeedbackDriftSignal, ...] = ()
    drift_90: tuple[FeedbackDriftSignal, ...] = ()


def _timestamp(value: datetime | float | None) -> float:
    if isinstance(value, datetime):
        moment = value if value.tzinfo else value.replace(tzinfo=timezone.utc)
        return moment.timestamp()
    if value is None:
        return time.time()
    return float(value)
def _scrub_payload(payload: dict[str, object]) -> dict[str, object]:
    scrubbed = scrub_sensitive(dict(payload or {}))
    if not isinstance(scrubbed, dict):
        return {}
    scrubbed.pop("_recommendation_undo", None)
    return scrubbed


def _json_object(value: object) -> dict[str, object]:
    try:
        decoded = json.loads(str(value or "{}"))
    except (json.JSONDecodeError, TypeError, ValueError):
        return {}
    return decoded if isinstance(decoded, dict) else {}


def _drift_rows(accumulator: dict[str, dict[str, float | int]]) -> tuple[FeedbackDriftSignal, ...]:
    rows = [
        FeedbackDriftSignal(
            feature=feature,
            positive_weight=float(values["positive"]),
            negative_weight=float(values["negative"]),
            count=int(values["count"]),
        )
        for feature, values in accumulator.items()
    ]
    rows.sort(key=lambda row: (-abs(row.net_weight), -row.count, row.feature))
    return tuple(rows)


def _features(payload: dict[str, object]) -> tuple[str, ...]:
    values: list[str] = []
    field_names = ("genre", "mood", "pace", "term", "country", "director", "cast", "media_type")
    for field_name in field_names:
        raw = payload.get(field_name)
        candidates = raw if isinstance(raw, (list, tuple, set)) else [raw]
        for candidate in candidates:
            text = str(candidate or "").strip()
            if text:
                values.append(f"{field_name}:{text}")
    nested = payload.get("features")
    if isinstance(nested, dict):
        for field_name, raw in nested.items():
            candidates = raw if isinstance(raw, (list, tuple, set)) else [raw]
            for candidate in candidates:
                text = str(candidate or "").strip()
                if text:
                    values.append(f"{field_name}:{text}")
    return tuple(dict.fromkeys(values))


class FeedbackService:
    def __init__(self, database: AppDatabase):
        self.database = database
        self.database.initialize()

    def record_feedback(self, event: FeedbackEvent) -> str:
        event_type = str(event.event_type or "").strip()
        if event_type not in ALLOWED_EVENT_TYPES or event_type == "undo":
            raise ValueError("unsupported feedback event")
        event_id = uuid.uuid4().hex
        created_at = _timestamp(event.created_at)
        raw_identity_aliases = event.payload.get("identity_aliases", event.payload.get("identity_tokens", ()))
        payload = _scrub_payload(event.payload)
        if isinstance(raw_identity_aliases, (list, tuple, set)):
            identity_aliases = [str(alias).strip() for alias in raw_identity_aliases if str(alias).strip()]
            if identity_aliases:
                payload["identity_aliases"] = identity_aliases
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO feedback_events(
                    id, profile_key, session_id, item_key, event_type,
                    payload_json, undone_by, created_at
                ) VALUES(?, ?, ?, ?, ?, ?, NULL, ?)
                """,
                (
                    event_id,
                    str(event.profile_key or "default"),
                    str(event.session_id or ""),
                    str(event.item_key or ""),
                    event_type,
                    json.dumps(payload, ensure_ascii=False, separators=(",", ":")),
                    created_at,
                ),
            )
        return event_id

    def undo_feedback(self, event_id: str) -> str:
        with self.database.connection() as connection:
            connection.execute("BEGIN IMMEDIATE")
            row = connection.execute(
                """
                SELECT id, profile_key, session_id, item_key, created_at
                FROM feedback_events WHERE id = ? AND event_type != 'undo'
                """,
                (str(event_id),),
            ).fetchone()
            if not row:
                raise ValueError("feedback event not found")
            undo_rows = connection.execute(
                """
                SELECT id, payload_json FROM feedback_events
                WHERE profile_key = ? AND event_type = 'undo'
                ORDER BY created_at, id
                """,
                (str(row["profile_key"]),),
            ).fetchall()
            for undo_row in undo_rows:
                payload = _json_object(undo_row["payload_json"])
                if str(payload.get("target_event_id") or "") == str(event_id):
                    return str(undo_row["id"])
            undo_id = uuid.uuid4().hex
            now = max(time.time(), float(row["created_at"]) + 1e-6)
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
                    str(row["session_id"] or ""),
                    str(row["item_key"]),
                    json.dumps({"target_event_id": str(event_id)}, separators=(",", ":")),
                    now,
                ),
            )
        return undo_id

    def feedback_signals(self, profile_key: str, at: datetime | float | None = None) -> FeedbackSignals:
        at_timestamp = _timestamp(at)
        with self.database.connection() as connection:
            rows = connection.execute(
                """
                SELECT id, event_type, session_id, item_key, payload_json, created_at
                FROM feedback_events
                WHERE profile_key = ? AND created_at <= ?
                ORDER BY created_at, id
                """,
                (str(profile_key or "default"), at_timestamp),
            ).fetchall()

        undone_event_ids: set[str] = set()
        for row in rows:
            if str(row["event_type"]) != "undo":
                continue
            payload = _json_object(row["payload_json"])
            target_event_id = str(payload.get("target_event_id") or "")
            if target_event_id:
                undone_event_ids.add(target_event_id)

        positive: list[str] = []
        weak_negative: list[str] = []
        permanent_negative: list[str] = []
        permanent_excluded_item_keys: list[str] = []
        session_adjustments: dict[str, list[str]] = {}
        recent_30: list[str] = []
        recent_90: list[str] = []
        drift_30: dict[str, dict[str, float | int]] = {}
        drift_90: dict[str, dict[str, float | int]] = {}
        for row in rows:
            if str(row["event_type"]) == "undo" or str(row["id"]) in undone_event_ids:
                continue
            payload = _json_object(row["payload_json"])
            features = _features(payload)
            event_type = str(row["event_type"])
            item_key = str(row["item_key"] or "")
            preference_features = features
            if event_type in DRIFT_WEIGHTS and not preference_features and item_key:
                preference_features = (f"item:{item_key}",)
            if event_type in {"more-like-this", "want"}:
                positive.extend(preference_features)
            elif event_type == "less-like-this":
                weak_negative.extend(preference_features)
            elif event_type == "permanent-avoid":
                permanent_negative.extend(preference_features)
                if item_key:
                    permanent_excluded_item_keys.append(item_key)
                identity_tokens = payload.get("identity_aliases", payload.get("identity_tokens"))
                if isinstance(identity_tokens, (list, tuple, set)):
                    permanent_excluded_item_keys.extend(
                        str(token).strip() for token in identity_tokens if str(token).strip()
                    )
            elif event_type in {"not-tonight", "tonight-candidate"}:
                session_id = str(row["session_id"] or "session")
                adjustments = session_adjustments.setdefault(session_id, [])
                adjustments.append(f"event:{event_type}")
                if item_key:
                    adjustments.append(f"item:{item_key}")
                adjustments.extend(features)

            age_days = max(0.0, (at_timestamp - float(row["created_at"])) / 86400.0)
            drift_weight = DRIFT_WEIGHTS.get(event_type)
            if drift_weight is not None:
                if age_days <= 30:
                    recent_30.extend(preference_features)
                    self._accumulate_drift(drift_30, preference_features, drift_weight)
                if age_days <= 90:
                    recent_90.extend(preference_features)
                    self._accumulate_drift(drift_90, preference_features, drift_weight)

        return FeedbackSignals(
            positive=tuple(dict.fromkeys(positive)),
            weak_negative=tuple(dict.fromkeys(weak_negative)),
            permanent_negative=tuple(dict.fromkeys(permanent_negative)),
            permanent_excluded_item_keys=tuple(dict.fromkeys(permanent_excluded_item_keys)),
            session_adjustments={
                key: tuple(dict.fromkeys(values)) for key, values in session_adjustments.items()
            },
            recent_30=tuple(dict.fromkeys(recent_30)),
            recent_90=tuple(dict.fromkeys(recent_90)),
            drift_30=_drift_rows(drift_30),
            drift_90=_drift_rows(drift_90),
        )

    @staticmethod
    def _accumulate_drift(
        accumulator: dict[str, dict[str, float | int]],
        features: tuple[str, ...],
        weight: float,
    ) -> None:
        for feature in features:
            values = accumulator.setdefault(
                feature,
                {"positive": 0.0, "negative": 0.0, "count": 0},
            )
            if weight >= 0:
                values["positive"] = float(values["positive"]) + weight
            else:
                values["negative"] = float(values["negative"]) + abs(weight)
            values["count"] = int(values["count"]) + 1
