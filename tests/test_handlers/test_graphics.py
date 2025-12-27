"""Tests for GraphicsSettingsHandler."""

import pytest
from unittest.mock import patch, MagicMock
import winreg

from abso.settings.graphics import GraphicsSettingsHandler
from abso.core.models import Issue


class TestGraphicsDetect:
    """Tests for GraphicsSettingsHandler.detect()."""

    @patch.object(GraphicsSettingsHandler, "_get_mpo_disabled")
    @patch.object(GraphicsSettingsHandler, "_get_global_fso_disabled")
    @patch.object(GraphicsSettingsHandler, "_get_game_dvr_behavior")
    @patch.object(GraphicsSettingsHandler, "_get_hardware_cursor")
    def test_detect_returns_expected_keys(self, mock_cursor, mock_dvr, mock_fso, mock_mpo):
        """Test detect returns dictionary with all expected keys."""
        mock_mpo.return_value = False
        mock_fso.return_value = False
        mock_dvr.return_value = 0
        mock_cursor.return_value = True

        handler = GraphicsSettingsHandler()
        result = handler.detect()

        assert "mpo_disabled" in result
        assert "global_fso_disabled" in result
        assert "game_dvr_behavior" in result
        assert "hardware_cursor" in result

    @patch("abso.settings.graphics.winreg")
    def test_get_mpo_disabled_when_disabled(self, mock_winreg):
        """Test _get_mpo_disabled returns True when MPO is disabled."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (5, winreg.REG_DWORD)
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = GraphicsSettingsHandler()
        result = handler._get_mpo_disabled()

        assert result is True

    @patch("abso.settings.graphics.winreg")
    def test_get_mpo_disabled_when_enabled(self, mock_winreg):
        """Test _get_mpo_disabled returns False when MPO is enabled."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = GraphicsSettingsHandler()
        result = handler._get_mpo_disabled()

        assert result is False

    @patch("abso.settings.graphics.winreg")
    def test_get_game_dvr_behavior_returns_value(self, mock_winreg):
        """Test _get_game_dvr_behavior returns registry value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (2, winreg.REG_DWORD)
        mock_winreg.HKEY_CURRENT_USER = winreg.HKEY_CURRENT_USER
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = GraphicsSettingsHandler()
        result = handler._get_game_dvr_behavior()

        assert result == 2


class TestGraphicsAudit:
    """Tests for GraphicsSettingsHandler.audit()."""

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_audit_mpo_enabled_creates_info(self, mock_detect):
        """Test audit creates info issue when MPO is enabled."""
        mock_detect.return_value = {
            "mpo_disabled": False,
            "global_fso_disabled": True,
            "game_dvr_behavior": 2,
            "hardware_cursor": True,
        }

        handler = GraphicsSettingsHandler()
        issues = handler.audit()

        mpo_issues = [i for i in issues if "MPO" in i.title]
        assert len(mpo_issues) == 1
        assert mpo_issues[0].severity == "info"

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_audit_fso_enabled_creates_info(self, mock_detect):
        """Test audit creates info issue when FSO is enabled."""
        mock_detect.return_value = {
            "mpo_disabled": True,
            "global_fso_disabled": False,
            "game_dvr_behavior": 0,
            "hardware_cursor": True,
        }

        handler = GraphicsSettingsHandler()
        issues = handler.audit()

        fso_issues = [i for i in issues if "Fullscreen" in i.title]
        assert len(fso_issues) == 1
        assert fso_issues[0].severity == "info"

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_audit_optimal_settings_minimal_issues(self, mock_detect):
        """Test audit returns minimal issues when settings are optimal."""
        mock_detect.return_value = {
            "mpo_disabled": True,
            "global_fso_disabled": True,
            "game_dvr_behavior": 2,
            "hardware_cursor": True,
        }

        handler = GraphicsSettingsHandler()
        issues = handler.audit()

        # Should have no issues when optimal
        assert len(issues) == 0


class TestGraphicsApply:
    """Tests for GraphicsSettingsHandler.apply()."""

    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    def test_apply_disable_mpo(self, mock_set_mpo):
        """Test apply disables MPO."""
        handler = GraphicsSettingsHandler()
        result = handler.apply({"disable_mpo": True})

        assert result["success"] is True
        assert result["requires_reboot"] is True
        mock_set_mpo.assert_called_once_with(True)

    @patch.object(GraphicsSettingsHandler, "_set_global_fso_disabled")
    def test_apply_disable_fso(self, mock_set_fso):
        """Test apply disables global FSO."""
        handler = GraphicsSettingsHandler()
        result = handler.apply({"disable_global_fso": True})

        assert result["success"] is True
        mock_set_fso.assert_called_once_with(True)

    @patch.object(GraphicsSettingsHandler, "_set_game_dvr_behavior")
    def test_apply_game_dvr_behavior(self, mock_set_dvr):
        """Test apply sets GameDVR behavior."""
        handler = GraphicsSettingsHandler()
        result = handler.apply({"game_dvr_behavior": 2})

        assert result["success"] is True
        mock_set_dvr.assert_called_once_with(2)

    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    def test_apply_handles_permission_error(self, mock_set_mpo):
        """Test apply handles permission errors."""
        mock_set_mpo.side_effect = PermissionError("Access denied")

        handler = GraphicsSettingsHandler()
        result = handler.apply({"disable_mpo": True})

        assert result["success"] is False
        assert "Permission" in result["error"]


class TestGraphicsBackupRestore:
    """Tests for GraphicsSettingsHandler backup/restore."""

    @patch.object(GraphicsSettingsHandler, "detect")
    def test_backup_returns_detected_settings(self, mock_detect):
        """Test backup returns current detected settings."""
        expected = {
            "mpo_disabled": True,
            "global_fso_disabled": False,
            "game_dvr_behavior": 0,
            "hardware_cursor": True,
        }
        mock_detect.return_value = expected

        handler = GraphicsSettingsHandler()
        result = handler.backup()

        assert result == expected

    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    @patch.object(GraphicsSettingsHandler, "_set_game_dvr_behavior")
    def test_restore_applies_settings(self, mock_set_dvr, mock_set_mpo):
        """Test restore applies backed up settings."""
        handler = GraphicsSettingsHandler()
        result = handler.restore({
            "mpo_disabled": True,
            "game_dvr_behavior": 2,
        })

        assert result is True
        mock_set_mpo.assert_called_once_with(True)
        mock_set_dvr.assert_called_once_with(2)

    @patch.object(GraphicsSettingsHandler, "_set_mpo_disabled")
    def test_restore_handles_error(self, mock_set_mpo):
        """Test restore handles errors gracefully."""
        mock_set_mpo.side_effect = PermissionError("Access denied")

        handler = GraphicsSettingsHandler()
        result = handler.restore({"mpo_disabled": True})

        assert result is False
