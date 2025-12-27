"""Pytest configuration and fixtures."""

from __future__ import annotations

import pytest
from pathlib import Path
from unittest.mock import MagicMock


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
