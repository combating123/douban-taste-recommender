from __future__ import annotations

import os
from collections.abc import Mapping
from pathlib import Path


def resolve_data_dir(env: Mapping[str, str] | None = None) -> Path:
    """Return the local CineScope data directory without creating it.

    An explicit ``CINESCOPE_DATA_DIR`` always wins. The default follows the
    platform's user-data convention and intentionally lives outside the git
    checkout so media/cache state cannot pollute the repository.
    """

    values = os.environ if env is None else env
    explicit = str(values.get("CINESCOPE_DATA_DIR") or "").strip()
    if explicit:
        return Path(explicit).expanduser().resolve()

    if os.name == "nt":
        local_app_data = str(values.get("LOCALAPPDATA") or "").strip()
        if local_app_data:
            return (Path(local_app_data).expanduser() / "CineScope").resolve()
        return (Path.home() / "AppData" / "Local" / "CineScope").resolve()

    xdg_data_home = str(values.get("XDG_DATA_HOME") or "").strip()
    if xdg_data_home:
        return (Path(xdg_data_home).expanduser() / "cinescope").resolve()
    return (Path.home() / ".local" / "share" / "cinescope").resolve()


def resolve_database_path(env: Mapping[str, str] | None = None) -> Path:
    return resolve_data_dir(env) / "cinescope.db"


def resolve_media_dir(env: Mapping[str, str] | None = None) -> Path:
    return resolve_data_dir(env) / "media"
