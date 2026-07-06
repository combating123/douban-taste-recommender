from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any

from .models import MediaItem
from .serialization import media_item_from_dict, media_item_to_dict

SENSITIVE_KEYS = {"cookie", "Cookie", "set-cookie", "Set-Cookie"}


def default_cache_dir(root: Path) -> Path:
    return root / "output" / "cache"


def scrub_sensitive(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: scrub_sensitive(item) for key, item in value.items() if key not in SENSITIVE_KEYS}
    if isinstance(value, list):
        return [scrub_sensitive(item) for item in value]
    if isinstance(value, str) and ("bid=" in value or "ck=" in value or "dbcl2=" in value):
        return "<redacted>"
    return value


@dataclass
class CacheSummary:
    cache_dir: str
    files: list[str]


class CacheStore:
    def __init__(self, cache_dir: Path):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def path(self, name: str) -> Path:
        return self.cache_dir / name

    def save_json(self, name: str, payload: dict[str, Any]) -> None:
        self.path(name).write_text(
            json.dumps(scrub_sensitive(payload), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )

    def load_json(self, name: str) -> dict[str, Any]:
        try:
            path = self.path(name)
            if not path.exists():
                return {}
            data = json.loads(path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except Exception:
            return {}

    def save_library(self, items: list[MediaItem], sync_report: dict[str, Any]) -> None:
        self.save_json("library.json", {"items": [media_item_to_dict(item) for item in items]})
        self.save_json("sync_report.json", sync_report)

    def load_library(self) -> tuple[list[MediaItem], dict[str, Any]]:
        data = self.load_json("library.json")
        report = self.load_json("sync_report.json")
        items = [media_item_from_dict(row) for row in data.get("items", []) if isinstance(row, dict)]
        return items, report

    def summary(self) -> CacheSummary:
        return CacheSummary(
            cache_dir=str(self.cache_dir),
            files=sorted(path.name for path in self.cache_dir.glob("*.json")),
        )

    def clear(self) -> int:
        removed = 0
        for path in self.cache_dir.glob("*.json"):
            path.unlink()
            removed += 1
        return removed
