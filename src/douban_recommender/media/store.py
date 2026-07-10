from __future__ import annotations

import hashlib
import os
import re
import tempfile
import time
from pathlib import Path, PurePosixPath
from typing import Any

from ..database import AppDatabase
from ..privacy import sanitize_source_url
from .models import StoredAsset, ValidatedImage
from .validator import validate_image_bytes


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_ROUTE_RE = re.compile(r"^([0-9a-f]{64})(\.(?:jpg|jpeg|png|webp))?$", re.I)


class MediaStore:
    def __init__(self, root: Path | str, database: AppDatabase):
        self.root = Path(root).resolve()
        self.database = database
        self.root.mkdir(parents=True, exist_ok=True)
        self.database.initialize()

    def put(self, validated: ValidatedImage, source_url: str, kind: str) -> StoredAsset:
        asset_id = validated.sha256.lower()
        relative_path = Path(asset_id[:2]) / f"{asset_id}{validated.extension}"
        final_path = (self.root / relative_path).resolve()
        if self.root not in final_path.parents:
            raise ValueError("unsafe media path")
        final_path.parent.mkdir(parents=True, exist_ok=True)

        if not final_path.exists():
            temporary_path: Path | None = None
            try:
                with tempfile.NamedTemporaryFile(
                    mode="wb",
                    delete=False,
                    dir=final_path.parent,
                    prefix=f".{asset_id}.",
                    suffix=".tmp",
                ) as handle:
                    handle.write(validated.data)
                    handle.flush()
                    os.fsync(handle.fileno())
                    temporary_path = Path(handle.name)
                temporary_path.replace(final_path)
            finally:
                if temporary_path and temporary_path.exists():
                    temporary_path.unlink(missing_ok=True)

        now = time.time()
        safe_source_url = sanitize_source_url(source_url)
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO asset_files(
                    asset_id, sha256, relative_path, mime_type, extension,
                    width, height, byte_size, source_url, kind, status,
                    created_at, last_verified_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?)
                ON CONFLICT(asset_id) DO UPDATE SET
                    last_verified_at = excluded.last_verified_at,
                    status = 'ready'
                """,
                (
                    asset_id,
                    asset_id,
                    relative_path.as_posix(),
                    validated.mime_type,
                    validated.extension,
                    validated.width,
                    validated.height,
                    len(validated.data),
                    safe_source_url,
                    str(kind or "image"),
                    now,
                    now,
                ),
            )
        stored = self.lookup(asset_id)
        if stored is None:
            raise RuntimeError("media asset manifest write failed")
        return stored

    def lookup(self, asset_id: str) -> StoredAsset | None:
        match = ASSET_ROUTE_RE.fullmatch(str(asset_id or "").strip())
        if not match:
            return None
        key = match.group(1).lower()
        route_extension = (match.group(2) or "").lower()
        with self.database.connection() as connection:
            row = connection.execute(
                """
                SELECT asset_id, sha256, relative_path, mime_type, extension,
                       width, height, byte_size, source_url, kind, status
                FROM asset_files
                WHERE asset_id = ?
                """,
                (key,),
            ).fetchone()
        if not row:
            return None
        return self._validated_row(row, key, route_extension)

    def _validated_row(self, row: Any, key: str, route_extension: str = "") -> StoredAsset | None:
        row_asset_id = str(row["asset_id"] or "").strip()
        row_sha256 = str(row["sha256"] or "").strip()
        extension = str(row["extension"] or "").strip().lower()
        mime_type = str(row["mime_type"] or "").strip().lower()
        relative_text = str(row["relative_path"] or "").strip()

        if (
            row_asset_id != key
            or row_sha256 != key
            or not re.fullmatch(r"[0-9a-f]{64}", row_asset_id)
            or extension not in ALLOWED_EXTENSIONS
            or (route_extension and route_extension != extension)
        ):
            return None
        expected_relative = f"{key[:2]}/{key}{extension}"
        if relative_text != expected_relative or "\\" in relative_text:
            return None
        relative_path = PurePosixPath(relative_text)
        if relative_path.is_absolute() or any(part in {"", ".", ".."} for part in relative_path.parts):
            return None

        path = (self.root / Path(*relative_path.parts)).resolve()
        if not self._is_within_root(path) or not path.is_file():
            return None
        try:
            payload = path.read_bytes()
            validated = validate_image_bytes(payload, mime_type, min_width=1, min_height=1)
            width = int(row["width"])
            height = int(row["height"])
            byte_size = int(row["byte_size"])
        except Exception:
            return None
        if (
            validated.sha256 != key
            or validated.extension != extension
            or validated.mime_type != mime_type
            or validated.width != width
            or validated.height != height
            or len(payload) != byte_size
        ):
            return None

        return StoredAsset(
            asset_id=key,
            sha256=key,
            path=path,
            local_url=f"/media/{key}{extension}",
            mime_type=mime_type,
            extension=extension,
            width=width,
            height=height,
            byte_size=byte_size,
            source_url=str(row["source_url"]),
            kind=str(row["kind"]),
            status=str(row["status"]),
        )

    def _is_within_root(self, path: Path) -> bool:
        return path == self.root or self.root in path.parents

    def _sha256_file(self, path: Path) -> str:
        digest = hashlib.sha256()
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(1024 * 1024), b""):
                digest.update(chunk)
        return digest.hexdigest()

    def path_for(self, asset_id: str) -> Path | None:
        stored = self.lookup(asset_id)
        return stored.path if stored else None
