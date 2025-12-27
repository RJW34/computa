"""Tests for WindowsSettingsHandler."""

import pytest
from unittest.mock import patch, MagicMock
import winreg

from gametune.settings.windows import WindowsSettingsHandler
from gametune.core.models import Issue


class TestWindowsDetect:
    """Tests for WindowsSettingsHandler.detect()."""

    @patch("gametune.settings.windows.winreg")
    def test_detect_returns_expected_keys(self, mock_winreg):
        """Test detect returns dictionary with all expected keys."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (1, winreg.REG_DWORD)
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = WindowsSettingsHandler()
        result = handler.detect()

        assert "game_mode" in result
        assert "game_bar" in result
        assert "game_dvr" in result
        assert "hags" in result
        assert "vbs" in result

    @patch("gametune.settings.windows.winreg")
    def test_detect_game_mode_enabled(self, mock_winreg):
        """Test detecting game mode when enabled."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (1, winreg.REG_DWORD)
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = WindowsSettingsHandler()
        result = handler.detect()

        assert result["game_mode"] is True

    @patch("gametune.settings.windows.winreg")
    def test_detect_handles_missing_keys(self, mock_winreg):
        """Test detect handles missing registry keys gracefully."""
        mock_winreg.OpenKey.side_effect = FileNotFoundError()
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = WindowsSettingsHandler()
        result = handler.detect()

        # Should return None for missing values, not crash
        assert result is not None


class TestWindowsAudit:
    """Tests for WindowsSettingsHandler.audit()."""

    @patch.object(WindowsSettingsHandler, "detect")
    def test_audit_game_mode_disabled_creates_issue(self, mock_detect):
        """Test audit creates issue when game mode is disabled."""
        mock_detect.return_value = {
            "game_mode": False,
            "game_bar": False,
            "game_dvr": False,
            "hags": None,
            "vbs": False,
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        game_mode_issues = [i for i in issues if "Game Mode" in i.title]
        assert len(game_mode_issues) == 1
        assert game_mode_issues[0].severity == "warning"

    @patch.object(WindowsSettingsHandler, "detect")
    def test_audit_game_bar_enabled_creates_issue(self, mock_detect):
        """Test audit creates issue when game bar is enabled."""
        mock_detect.return_value = {
            "game_mode": True,
            "game_bar": True,
            "game_dvr": False,
            "hags": None,
            "vbs": False,
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        game_bar_issues = [i for i in issues if "Game Bar" in i.title]
        assert len(game_bar_issues) == 1
        assert game_bar_issues[0].severity == "info"

    @patch.object(WindowsSettingsHandler, "detect")
    def test_audit_game_dvr_enabled_creates_warning(self, mock_detect):
        """Test audit creates warning when game DVR is enabled."""
        mock_detect.return_value = {
            "game_mode": True,
            "game_bar": False,
            "game_dvr": True,
            "hags": None,
            "vbs": False,
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        dvr_issues = [i for i in issues if "recording" in i.title.lower()]
        assert len(dvr_issues) == 1
        assert dvr_issues[0].severity == "warning"

    @patch.object(WindowsSettingsHandler, "detect")
    def test_audit_vbs_enabled_creates_issue(self, mock_detect):
        """Test audit creates issue when VBS is enabled."""
        mock_detect.return_value = {
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
            "hags": None,
            "vbs": True,
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        vbs_issues = [i for i in issues if "VBS" in i.title]
        assert len(vbs_issues) == 1
        assert vbs_issues[0].severity == "info"

    @patch.object(WindowsSettingsHandler, "detect")
    def test_audit_optimal_settings_no_issues(self, mock_detect):
        """Test audit returns no issues when all settings are optimal."""
        mock_detect.return_value = {
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
            "hags": True,
            "vbs": False,
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0


class TestWindowsApply:
    """Tests for WindowsSettingsHandler.apply()."""

    @patch("gametune.settings.windows.winreg")
    def test_apply_game_mode(self, mock_winreg):
        """Test applying game mode setting."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.CreateKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        handler = WindowsSettingsHandler()
        result = handler.apply({"game_mode": True})

        assert result["success"] is True
        mock_winreg.SetValueEx.assert_called()

    @patch("gametune.settings.windows.winreg")
    def test_apply_multiple_settings(self, mock_winreg):
        """Test applying multiple settings at once."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.CreateKey.return_value = mock_key
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        handler = WindowsSettingsHandler()
        result = handler.apply({
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
        })

        assert result["success"] is True

    @patch("gametune.settings.windows.winreg")
    def test_apply_permission_error(self, mock_winreg):
        """Test apply handles permission errors."""
        mock_winreg.OpenKey.side_effect = PermissionError("Access denied")
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS

        handler = WindowsSettingsHandler()
        result = handler.apply({"game_mode": True})

        assert result["success"] is False
        assert "Permission" in result["error"] or "denied" in result["error"].lower()

    @patch("gametune.settings.windows.winreg")
    def test_apply_vbs_requires_reboot(self, mock_winreg):
        """Test that VBS changes require reboot."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.CreateKey.return_value = mock_key
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        handler = WindowsSettingsHandler()
        result = handler.apply({"vbs": False})

        assert result["requires_reboot"] is True


class TestWindowsBackupRestore:
    """Tests for WindowsSettingsHandler backup/restore."""

    @patch.object(WindowsSettingsHandler, "detect")
    def test_backup_returns_current_settings(self, mock_detect):
        """Test backup returns current detected settings."""
        expected = {
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
            "hags": True,
            "vbs": False,
        }
        mock_detect.return_value = expected

        handler = WindowsSettingsHandler()
        result = handler.backup()

        assert result == expected

    @patch.object(WindowsSettingsHandler, "apply")
    def test_restore_applies_settings(self, mock_apply):
        """Test restore applies backed up settings."""
        mock_apply.return_value = {"success": True}
        backup_data = {
            "game_mode": True,
            "game_bar": False,
        }

        handler = WindowsSettingsHandler()
        result = handler.restore(backup_data)

        assert result is True

    @patch.object(WindowsSettingsHandler, "apply")
    def test_restore_returns_false_on_apply_failure(self, mock_apply):
        """Test restore returns False when apply fails."""
        mock_apply.return_value = {"success": False, "error": "Apply failed"}

        handler = WindowsSettingsHandler()
        result = handler.restore({"game_mode": True})

        assert result is False
