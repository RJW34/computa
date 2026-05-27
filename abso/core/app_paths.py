"""Shared application data paths."""

from __future__ import annotations

import os
from pathlib import Path

APP_DIR_NAME = "AdaptiveBattleStationOptimizer"
STATE_FILE_NAME = ".abso_state.json"


def local_appdata_root(local_appdata: str | Path | None = None) -> Path:
    """Return the Windows LocalAppData root, honoring redirected environments."""
    if local_appdata is None:
        local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata)
    return Path.home() / "AppData" / "Local"


def app_data_dir(
    *,
    create: bool = False,
    local_appdata: str | Path | None = None,
) -> Path:
    """Return ABSO's installed app data directory."""
    path = local_appdata_root(local_appdata) / APP_DIR_NAME
    if create:
        path.mkdir(parents=True, exist_ok=True)
    return path


def app_state_file(*, local_appdata: str | Path | None = None) -> Path:
    """Return ABSO's installed active-profile state file."""
    return app_data_dir(local_appdata=local_appdata) / STATE_FILE_NAME
