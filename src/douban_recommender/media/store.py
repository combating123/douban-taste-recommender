from __future__ import annotations

import os
import re
import tempfile
import time
from pathlib import Path

from ..database import AppDatabase
from .models import StoredAsset, ValidatedImage


ASSET_ROUTE_RE = re.compile(r"^([0-9a-f]{64})(?:\.(?:jpg|jpeg|png|webp))?$", re.I)


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
                    str(source_url or ""),
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
        path = (self.root / str(row["relative_path"])).resolve()
        if self.root not in path.parents or not path.is_file():
            return None
        return StoredAsset(
            asset_id=str(row["asset_id"]),
            sha256=str(row["sha256"]),
            path=path,
            local_url=f"/media/{row['asset_id']}{row['extension']}",
            mime_type=str(row["mime_type"]),
            extension=str(row["extension"]),
            width=int(row["width"]),
            height=int(row["height"]),
            byte_size=int(row["byte_size"]),
            source_url=str(row["source_url"]),
            kind=str(row["kind"]),
            status=str(row["status"]),
        )

    def path_for(self, asset_id: str) -> Path | None:
        stored = self.lookup(asset_id)
        return stored.path if stored else None
