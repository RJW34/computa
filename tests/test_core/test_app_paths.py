"""Tests for shared application data paths."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import patch

from abso.core.app_paths import APP_DIR_NAME, STATE_FILE_NAME, app_data_dir, app_state_file


def test_app_paths_honor_localappdata_override(tmp_path: Path) -> None:
    """Installed app paths should follow redirected LocalAppData roots."""
    local_root = tmp_path / "redirected-local"

    assert app_data_dir(local_appdata=local_root) == local_root / APP_DIR_NAME
    assert app_state_file(local_appdata=local_root) == (
        local_root / APP_DIR_NAME / STATE_FILE_NAME
    )


def test_app_data_dir_can_create_directory(tmp_path: Path) -> None:
    """Packaged commands can create the app data directory through one helper."""
    local_root = tmp_path / "local"
    path = app_data_dir(create=True, local_appdata=local_root)

    assert path == local_root / APP_DIR_NAME
    assert path.is_dir()


def test_state_reconcile_uses_same_app_state_file(tmp_path: Path) -> None:
    """State mirroring should use the same LocalAppData path helper."""
    from abso.core.state_reconcile import local_appdata_state_file

    with patch.dict("os.environ", {"LOCALAPPDATA": str(tmp_path)}):
        assert local_appdata_state_file() == app_state_file(local_appdata=tmp_path)
