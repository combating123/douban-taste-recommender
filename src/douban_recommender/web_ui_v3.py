from __future__ import annotations

import mimetypes
import os
from collections.abc import Mapping
from pathlib import Path

from .models import is_safe_route_segment


UI_ROOT = Path(__file__).with_name("ui")
_V3_SPACES = frozenset({"/tonight", "/universe", "/library", "/taste", "/health"})
_TONIGHT_CHANNELS = frozenset({"movie", "series", "anime-series"})


def load_index_html() -> str:
    """Return the packaged CineScope V3 application shell."""

    return (UI_ROOT / "index.html").read_text(encoding="utf-8")


def asset_response(relative_path: str) -> tuple[bytes, str]:
    """Load a packaged V3 asset without allowing requests to escape ``UI_ROOT``."""

    ui_root = UI_ROOT.resolve()
    candidate = (ui_root / relative_path).resolve()
    if ui_root not in candidate.parents or not candidate.is_file():
        raise FileNotFoundError(relative_path)
    content_type = mimetypes.guess_type(candidate.name)[0] or "application/octet-stream"
    return candidate.read_bytes(), content_type


def selected_ui_version(env: Mapping[str, str] | None = None) -> str:
    """Select the rollout-safe frontend version, defaulting to the legacy UI."""

    source = os.environ if env is None else env
    return "v3" if source.get("CINESCOPE_UI_VERSION", "").strip().lower() == "v3" else "legacy"


def is_v3_frontend_route(path: str) -> bool:
    """Return whether a non-service path is a supported V3 shell deep link."""

    if not isinstance(path, str) or path.startswith(("/api/", "/media/", "/assets/")):
        return False
    if path in {"/", "/index.html"} | _V3_SPACES:
        return True

    parts = path.split("/")
    if len(parts) != 3 or parts[0] != "" or not is_safe_route_segment(parts[2]):
        return False
    if parts[1] in {"title", "person"}:
        return True
    return parts[1] == "tonight" and parts[2] in _TONIGHT_CHANNELS
