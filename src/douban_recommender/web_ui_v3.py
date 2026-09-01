from __future__ import annotations

import hashlib
import mimetypes
import os
import re
from collections.abc import Mapping
from pathlib import Path
from urllib.parse import unquote

from .models import is_safe_route_segment


UI_ROOT = Path(__file__).with_name("ui")
_V3_SPACES = frozenset({"/tonight", "/universe", "/observatory", "/library", "/taste", "/health"})
_TONIGHT_CHANNELS = frozenset({"movie", "series", "anime-series"})
_SERVICE_ROOTS = frozenset({"api", "assets", "media"})
_INVALID_PERCENT_ESCAPE = re.compile(r"%(?![0-9A-Fa-f]{2})")
_ASSET_ATTRIBUTE = re.compile(r'(?P<prefix>\b(?:href|src)=")(?P<path>/assets/v3/[^"?]+)(?P<suffix>")')
_VERSIONED_ASSET_PREFIX = re.compile(r"^build-[0-9a-f]{12}/")


def _asset_build_revision() -> str:
    digest = hashlib.sha256()
    assets = sorted(
        path for path in UI_ROOT.rglob("*")
        if path.is_file() and path.name != "index.html"
    )
    for path in assets:
        digest.update(path.relative_to(UI_ROOT).as_posix().encode("utf-8"))
        digest.update(b"\0")
        digest.update(path.read_bytes())
        digest.update(b"\0")
    return digest.hexdigest()[:12]


def load_index_html() -> str:
    """Return the packaged CineScope V3 application shell."""

    html = (UI_ROOT / "index.html").read_text(encoding="utf-8")
    revision = f"build-{_asset_build_revision()}"
    return _ASSET_ATTRIBUTE.sub(
        lambda match: (
            f'{match.group("prefix")}'
            f'{match.group("path").replace("/assets/v3/", f"/assets/v3/{revision}/", 1)}'
            f'{match.group("suffix")}'
        ),
        html,
    )


def asset_response(relative_path: str) -> tuple[bytes, str]:
    """Load a packaged V3 asset without allowing requests to escape ``UI_ROOT``."""

    relative_path = _VERSIONED_ASSET_PREFIX.sub("", str(relative_path or ""), count=1)
    ui_root = UI_ROOT.resolve()
    candidate = (ui_root / relative_path).resolve()
    if ui_root not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError(relative_path)
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return candidate.read_bytes(), content_type


def selected_ui_version(env: Mapping[str, str] | None = None) -> str:
    """Select V3 unless the legacy UI is explicitly requested."""

    value = str((os.environ if env is None else env).get("CINESCOPE_UI_VERSION", "v3")).lower()
    return "legacy" if value == "legacy" else "v3"


def is_v3_frontend_route(path: str) -> bool:
    """Return whether a non-service path is a supported V3 shell deep link."""

    if not isinstance(path, str) or not path.startswith("/") or _INVALID_PERCENT_ESCAPE.search(path):
        return False
    raw_parts = path.split("/")
    try:
        parts = [unquote(part, errors="strict") for part in raw_parts]
    except UnicodeDecodeError:
        return False
    if any("/" in part or "\\" in part for part in parts):
        return False
    if len(parts) > 1 and parts[1].lower() in _SERVICE_ROOTS:
        return False

    decoded_path = "/".join(parts)
    if decoded_path in {"/", "/index.html"} | _V3_SPACES:
        return True

    if len(parts) != 3 or parts[0] != "" or not is_safe_route_segment(parts[2]):
        return False
    if parts[1] in {"title", "person"}:
        return True
    return parts[1] == "tonight" and parts[2] in _TONIGHT_CHANNELS
