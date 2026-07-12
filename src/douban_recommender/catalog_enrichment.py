from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Callable

from .douban_sources import enrich_media_items
from .models import MediaItem


def enrich_media_items_parallel(
    items: list[MediaItem],
    fetcher: Callable[[str], object] | None = None,
    limit: int = 12,
    sleep_seconds: float = 0.0,
    force_people_photos: bool = False,
    max_workers: int = 6,
) -> list[MediaItem]:
    selected = list(items or [])[: max(0, int(limit))]
    if not selected:
        return items

    def enrich_one(item: MediaItem) -> None:
        enrich_media_items(
            [item],
            fetcher=fetcher,
            limit=1,
            sleep_seconds=sleep_seconds,
            force_people_photos=force_people_photos,
        )

    worker_count = max(1, min(int(max_workers), len(selected)))
    with ThreadPoolExecutor(max_workers=worker_count, thread_name_prefix="cinescope-detail") as executor:
        futures = [executor.submit(enrich_one, item) for item in selected]
        for future in as_completed(futures):
            try:
                future.result()
            except Exception:
                continue
    return items
