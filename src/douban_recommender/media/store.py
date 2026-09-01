from __future__ import annotations

import hashlib
import json
import os
import re
import tempfile
import threading
import time
from pathlib import Path, PurePosixPath
from typing import Any, Mapping

from ..database import AppDatabase
from ..privacy import sanitize_source_url, scrub_sensitive
from .models import StoredAsset, ValidatedImage
from .validator import validate_image_bytes, validate_image_kind


ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png", ".webp"}
ASSET_ROUTE_RE = re.compile(r"^([0-9a-f]{64})(\.(?:jpg|jpeg|png|webp))?$", re.I)
LOOKUP_CACHE_TTL_SECONDS = 30.0


class MediaStore:
    def __init__(self, root: Path | str, database: AppDatabase):
        self.root = Path(root).resolve()
        self.database = database
        self.root.mkdir(parents=True, exist_ok=True)
        self.database.initialize()
        self._lookup_cache: dict[tuple[str, str], tuple[tuple[object, ...], float, StoredAsset | None]] = {}
        self._lookup_cache_lock = threading.Lock()

    def put(self, validated: ValidatedImage, source_url: str, kind: str) -> StoredAsset:
        validate_image_kind(validated, kind)
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
                    source_url = excluded.source_url,
                    kind = CASE
                        WHEN asset_files.kind = excluded.kind THEN asset_files.kind
                        ELSE 'shared'
                    END,
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
        cache_lock = getattr(self, "_lookup_cache_lock", None)
        if cache_lock is None:
            cache_lock = threading.Lock()
            self._lookup_cache_lock = cache_lock
            self._lookup_cache = {}
        lookup_cache = getattr(self, "_lookup_cache", None)
        if not isinstance(lookup_cache, dict):
            lookup_cache = {}
            self._lookup_cache = lookup_cache
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
            with cache_lock:
                lookup_cache.pop((key, route_extension), None)
            return None
        fingerprint = self._lookup_fingerprint(row)
        cache_key = (key, route_extension)
        now = time.monotonic()
        with cache_lock:
            cached = lookup_cache.get(cache_key)
            if cached and cached[0] == fingerprint and now - cached[1] < LOOKUP_CACHE_TTL_SECONDS:
                return cached[2]
        stored = self._validated_row(row, key, route_extension)
        with cache_lock:
            lookup_cache[cache_key] = (fingerprint, now, stored)
            if len(lookup_cache) > 2048:
                lookup_cache.pop(next(iter(lookup_cache)))
        return stored

    def bind_asset(
        self,
        entity_kind: str,
        entity_id: str,
        kind: str,
        stored: StoredAsset,
        source: str,
        confidence: float,
        metadata: Mapping[str, object] | None,
    ) -> None:
        clean_entity_kind = str(entity_kind or "").strip().lower()
        clean_entity_id = str(entity_id or "").strip()
        clean_kind = str(kind or "").strip().lower()
        clean_source = str(source or "unknown").strip() or "unknown"
        if clean_entity_kind not in {"media", "person"} or not clean_entity_id:
            raise ValueError("invalid asset binding identity")
        if clean_kind not in {"poster", "backdrop", "portrait"}:
            raise ValueError("invalid asset binding kind")
        if stored.status != "ready":
            raise ValueError("stored asset is not ready")
        if not str(stored.local_url or "").startswith("/media/"):
            raise ValueError("stored asset must use a local /media route")
        if stored.kind not in {clean_kind, "shared"}:
            raise ValueError("stored asset kind does not match binding")

        verified = self.lookup(stored.asset_id)
        if verified is None or verified.local_url != stored.local_url or verified.status != "ready":
            raise ValueError("stored asset is not locally verified")
        if verified.kind not in {clean_kind, "shared"}:
            raise ValueError("verified asset kind does not match binding")

        try:
            clean_confidence = max(0.0, min(1.0, float(confidence)))
        except (TypeError, ValueError):
            clean_confidence = 0.0
        safe_metadata = scrub_sensitive(dict(metadata or {}))
        if not isinstance(safe_metadata, dict):
            safe_metadata = {}
        safe_metadata.update(
            {
                "asset_id": verified.asset_id,
                "local_url": verified.local_url,
                "mime_type": verified.mime_type,
                "width": verified.width,
                "height": verified.height,
                "byte_size": verified.byte_size,
            }
        )
        metadata_json = json.dumps(
            safe_metadata,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )
        candidate_id = hashlib.sha256(
            f"candidate\0{clean_entity_kind}\0{clean_entity_id}\0{clean_kind}\0{clean_source}\0{verified.asset_id}".encode(
                "utf-8"
            )
        ).hexdigest()
        override_id = hashlib.sha256(
            f"override\0{clean_entity_kind}\0{clean_entity_id}\0{clean_kind}".encode("utf-8")
        ).hexdigest()
        now = time.time()
        with self.database.connection() as connection:
            connection.execute(
                """
                INSERT INTO asset_candidates(
                    id, entity_kind, entity_id, kind, source, url, confidence,
                    status, metadata_json, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, ?, ?, 'ready', ?, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    url = excluded.url,
                    confidence = excluded.confidence,
                    status = 'ready',
                    metadata_json = excluded.metadata_json,
                    updated_at = excluded.updated_at
                """,
                (
                    candidate_id,
                    clean_entity_kind,
                    clean_entity_id,
                    clean_kind,
                    clean_source,
                    verified.source_url,
                    clean_confidence,
                    metadata_json,
                    now,
                    now,
                ),
            )
            connection.execute(
                """
                INSERT INTO user_asset_overrides(
                    id, entity_kind, entity_id, kind, asset_id, decision, created_at, updated_at
                ) VALUES(?, ?, ?, ?, ?, 'selected', ?, ?)
                ON CONFLICT(entity_kind, entity_id, kind) DO UPDATE SET
                    asset_id = excluded.asset_id,
                    decision = 'selected',
                    updated_at = excluded.updated_at
                """,
                (
                    override_id,
                    clean_entity_kind,
                    clean_entity_id,
                    clean_kind,
                    verified.asset_id,
                    now,
                    now,
                ),
            )

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
            validate_image_kind(validated, str(row["kind"] or ""))
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

    def _lookup_fingerprint(self, row: Any) -> tuple[object, ...]:
        relative_text = str(row["relative_path"] or "").strip()
        try:
            relative_path = PurePosixPath(relative_text)
            path = (self.root / Path(*relative_path.parts)).resolve()
            stat = path.stat() if self._is_within_root(path) and path.is_file() else None
        except (OSError, RuntimeError, ValueError):
            stat = None
        return (
            str(row["asset_id"] or ""),
            str(row["sha256"] or ""),
            relative_text,
            str(row["mime_type"] or ""),
            str(row["extension"] or ""),
            int(row["width"] or 0),
            int(row["height"] or 0),
            int(row["byte_size"] or 0),
            str(row["source_url"] or ""),
            str(row["kind"] or ""),
            str(row["status"] or ""),
            None if stat is None else int(stat.st_size),
            None if stat is None else int(stat.st_mtime_ns),
            None if stat is None else int(stat.st_ctime_ns),
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
