from __future__ import annotations

import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .models import MediaItem


GENERATED_SUMMARY_PREFIXES = (
    "正在补齐这部",
    "资料有限：本地片库暂未记录作品简介",
    "由 CineScope 精选扩展池补入的",
    "详情：点击卡片查看简介",
)
GENERIC_GENRES = {"", "作品", "媒体", "电影", "电视剧", "动漫"}
PERSONAL_STATES = {"watched", "wish", "wanted", "collect", "rated"}
PLACEHOLDER_PORTRAIT_MARKERS = (
    "personage-default",
    "celebrity-default",
    "default-avatar",
    "default_portrait",
)


def _primary_people_have_verified_photos(item: MediaItem) -> bool:
    directors = [str(value).strip() for value in item.directors or [] if str(value).strip()]
    casts = [str(value).strip() for value in item.casts or [] if str(value).strip()]
    if not directors or not casts:
        return False
    raw = item.raw if isinstance(item.raw, dict) else {}
    photos = raw.get("people_photos") if isinstance(raw.get("people_photos"), dict) else {}
    required = [*directors[:1], *casts[:5]]
    for name in required:
        url = str(photos.get(name) or "").strip()
        lowered = url.casefold()
        if not url.startswith(("http://", "https://")):
            return False
        if any(marker in lowered for marker in PLACEHOLDER_PORTRAIT_MARKERS):
            return False
    return True


def _is_largely_latin_summary(value: object) -> bool:
    text = str(value or "").strip()
    if not text:
        return False
    cjk_count = sum("\u3400" <= character <= "\u9fff" for character in text)
    latin_count = sum("a" <= character.casefold() <= "z" for character in text)
    return cjk_count == 0 and latin_count >= 24 and latin_count >= len(text) * 0.45


def metadata_quality(item: MediaItem) -> dict[str, object]:
    raw = item.raw if isinstance(item.raw, dict) else {}
    summary = str(item.summary or "").strip()
    summary_ready = (
        bool(summary)
        and not summary.startswith(GENERATED_SUMMARY_PREFIXES)
        and not _is_largely_latin_summary(summary)
    )
    media_type = str(item.media_type or "").strip()
    genres_ready = any(str(value or "").strip() not in GENERIC_GENRES | {media_type} for value in item.genres or [])
    ratings = raw.get("ratings") if isinstance(raw.get("ratings"), dict) else {}
    normalized_ratings = []
    for value in ratings.values():
        try:
            normalized_ratings.append(float(value))
        except (TypeError, ValueError):
            continue
    rating_ready = item.douban_rating is not None or any(value > 0 for value in normalized_ratings)
    people_ready = _primary_people_have_verified_photos(item)
    stills = raw.get("stills") if isinstance(raw.get("stills"), list) else []
    stills_ready = any(str(value or "").startswith(("http://", "https://")) for value in stills)
    fields = {
        "summary": summary_ready,
        "genres": genres_ready,
        "rating": rating_ready,
        "people": people_ready,
        "stills": stills_ready,
    }
    missing = [name for name, ready in fields.items() if not ready]
    return {
        "complete": not missing,
        "score": len(fields) - len(missing),
        "missing": missing,
        "fields": fields,
    }


class CatalogHydrationCoordinator:
    """Continuously fills trustworthy decision metadata without blocking UI requests."""

    def __init__(
        self,
        catalog_api,
        *,
        batch_size: int = 6,
        max_workers: int = 2,
        poll_seconds: float = 15 * 60,
        retry_seconds: float = 30 * 60,
        batch_pause_seconds: float = 1.2,
        initial_delay_seconds: float = 20.0,
        now: Callable[[], float] = time.time,
        start_thread: bool = True,
    ):
        self.catalog_api = catalog_api
        self.batch_size = max(1, min(48, int(batch_size)))
        self.max_workers = max(1, min(6, int(max_workers)))
        self.poll_seconds = max(10.0, float(poll_seconds))
        self.retry_seconds = max(60.0, float(retry_seconds))
        self.batch_pause_seconds = max(0.1, float(batch_pause_seconds))
        self.initial_delay_seconds = max(0.0, float(initial_delay_seconds))
        self.now = now
        self._closed = threading.Event()
        self._wake = threading.Event()
        self._lock = threading.RLock()
        self._attempted_at: dict[str, float] = {}
        self._thread: threading.Thread | None = None
        self._state: dict[str, object] = {
            "state": "idle",
            "total": 0,
            "complete": 0,
            "pending": 0,
            "running": 0,
            "attempted": 0,
            "succeeded": 0,
            "failed": 0,
            "current_keys": [],
            "updated_at": 0.0,
        }
        if start_thread:
            self._thread = threading.Thread(target=self._loop, name="cinescope-catalog-hydration", daemon=True)
            self._thread.start()

    def _records(self):
        visible = getattr(self.catalog_api.service, "visible_library_records", None)
        if callable(visible):
            return list(visible())
        return list(self.catalog_api.service.repository.library_records())

    @staticmethod
    def _priority(record) -> tuple[int, int, int, float, str]:
        quality = metadata_quality(record.item)
        personal = 1 if str(record.state or "") in PERSONAL_STATES else 0
        numeric_identity = 1 if str(record.item.douban_id or "").isdigit() else 0
        return (
            personal,
            len(quality["missing"]),
            numeric_identity,
            -float(getattr(record, "updated_at", 0.0) or 0.0),
            str(record.item_key),
        )

    def _snapshot(self, records) -> dict[str, object]:
        total = len(records)
        complete = sum(1 for record in records if metadata_quality(record.item)["complete"])
        with self._lock:
            self._state.update(
                {
                    "total": total,
                    "complete": complete,
                    "pending": max(0, total - complete),
                    "updated_at": self.now(),
                }
            )
            return dict(self._state)

    def status(self) -> dict[str, object]:
        try:
            records = self._records()
        except Exception:
            with self._lock:
                return dict(self._state)
        return self._snapshot(records)

    def run_once(self, limit: int | None = None) -> dict[str, object]:
        records = self._records()
        now = self.now()
        candidates = []
        for record in records:
            if metadata_quality(record.item)["complete"]:
                continue
            last_attempt = self._attempted_at.get(str(record.item_key), 0.0)
            if last_attempt and now - last_attempt < self.retry_seconds:
                continue
            candidates.append(record)
        candidates.sort(key=self._priority, reverse=True)
        selected = candidates[: max(1, int(limit or self.batch_size))]
        if not selected:
            with self._lock:
                self._state.update({"state": "idle", "running": 0, "current_keys": []})
            return self._snapshot(records)

        keys = [str(record.item_key) for record in selected]
        with self._lock:
            self._state.update({"state": "running", "running": len(keys), "current_keys": keys})
            self._state["attempted"] = int(self._state["attempted"]) + len(keys)
        for key in keys:
            self._attempted_at[key] = now

        succeeded = 0
        failed = 0
        with ThreadPoolExecutor(max_workers=min(self.max_workers, len(keys)), thread_name_prefix="cinescope-hydrate") as executor:
            futures = {executor.submit(self.catalog_api.enrich_title, key): key for key in keys}
            for future in as_completed(futures):
                try:
                    future.result()
                    succeeded += 1
                except Exception:
                    failed += 1

        refreshed = self._records()
        with self._lock:
            self._state["succeeded"] = int(self._state["succeeded"]) + succeeded
            self._state["failed"] = int(self._state["failed"]) + failed
            self._state.update({"state": "idle", "running": 0, "current_keys": []})
        return self._snapshot(refreshed)

    def wake(self) -> None:
        self._wake.set()

    def _loop(self) -> None:
        if self.initial_delay_seconds and self._closed.wait(self.initial_delay_seconds):
            return
        while not self._closed.is_set():
            try:
                status = self.run_once()
                delay = self.batch_pause_seconds if int(status.get("pending") or 0) else self.poll_seconds
            except Exception:
                delay = min(self.poll_seconds, 60.0)
            self._wake.wait(delay)
            self._wake.clear()

    def close(self) -> None:
        self._closed.set()
        self._wake.set()
        if self._thread is not None:
            self._thread.join(timeout=3.0)
