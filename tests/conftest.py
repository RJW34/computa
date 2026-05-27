"""Pytest configuration and fixtures."""

from __future__ import annotations

import os
from pathlib import Path
from unittest.mock import MagicMock

import pytest


def pytest_configure(config):
    """Use a per-process temp root so parallel pytest invocations do not collide."""
    if getattr(config.option, "basetemp", None):
        return
    runtime_root = Path(__file__).resolve().parents[1] / ".pytest-runtime"
    config.option.basetemp = str(runtime_root / f"pytest-{os.getpid()}")


@pytest.fixture(autouse=True)
def isolate_abso_user_state(tmp_path, monkeypatch):
    """Keep tests from touching this PC's real ABSO app-data/state roots."""
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "LocalAppData"))
    monkeypatch.setenv("APPDATA", str(tmp_path / "RoamingAppData"))

    import abso.main as abso_main

    monkeypatch.setattr(abso_main, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(abso_main, "BACKUPS_DIR", tmp_path / "backups")
    monkeypatch.setattr(abso_main, "REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(abso_main, "STATE_FILE", tmp_path / ".abso_state.json")

    yield


@pytest.fixture
def mock_winreg(monkeypatch):
    """Mock winreg for tests that don't need real registry access."""
    mock = MagicMock()
    mock.HKEY_LOCAL_MACHINE = 0x80000002
    mock.HKEY_CURRENT_USER = 0x80000001
    mock.KEY_READ = 0x20019
    mock.KEY_ALL_ACCESS = 0xF003F
    mock.REG_DWORD = 4
    monkeypatch.setattr("winreg.OpenKey", mock.OpenKey)
    monkeypatch.setattr("winreg.QueryValueEx", mock.QueryValueEx)
    monkeypatch.setattr("winreg.SetValueEx", mock.SetValueEx)
    monkeypatch.setattr("winreg.CloseKey", mock.CloseKey)
    return mock


@pytest.fixture
def temp_backup_dir(tmp_path):
    """Create a temporary backup directory."""
    backup_dir = tmp_path / "backups"
    backup_dir.mkdir()
    return backup_dir
