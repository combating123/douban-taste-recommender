from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class ValidatedImage:
    data: bytes
    mime_type: str
    extension: str
    width: int
    height: int
    sha256: str


@dataclass(frozen=True)
class StoredAsset:
    asset_id: str
    sha256: str
    path: Path
    local_url: str
    mime_type: str
    extension: str
    width: int
    height: int
    byte_size: int
    source_url: str
    kind: str
    status: str = "ready"
