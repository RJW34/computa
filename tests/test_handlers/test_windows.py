"""Tests for WindowsSettingsHandler."""

import winreg
from unittest.mock import MagicMock, patch

import pytest

from abso.settings.windows import WindowsSettingsHandler


class TestWindowsDetect:
    """Tests for WindowsSettingsHandler.detect()."""

    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_vrr_optimize")
    @patch.object(WindowsSettingsHandler, "_get_windowed_optimizations")
    @patch.object(WindowsSettingsHandler, "_get_auto_hdr")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_vbs")
    @patch.object(WindowsSettingsHandler, "_get_hags")
    @patch.object(WindowsSettingsHandler, "_get_game_dvr")
    @patch.object(WindowsSettingsHandler, "_get_game_bar")
    @patch.object(WindowsSettingsHandler, "_get_game_mode")
    def test_detect_returns_expected_keys(
        self,
        mock_game_mode,
        mock_game_bar,
        mock_game_dvr,
        mock_hags,
        mock_vbs,
        mock_hdr_summary,
        mock_auto_hdr,
        mock_windowed_optimizations,
        mock_vrr_optimize,
        mock_refresh_info,
    ):
        """Test detect returns dictionary with all expected keys."""
        mock_game_mode.return_value = True
        mock_game_bar.return_value = False
        mock_game_dvr.return_value = False
        mock_hags.return_value = True
        mock_vbs.return_value = False
        mock_hdr_summary.return_value = {
            "available": True,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "any_enabled": True,
        }
        mock_auto_hdr.return_value = False
        mock_windowed_optimizations.return_value = False
        mock_vrr_optimize.return_value = False
        mock_refresh_info.return_value = {"current": 240, "max": 240, "available": [60, 120, 240]}

        handler = WindowsSettingsHandler()
        result = handler.detect()

        assert "game_mode" in result
        assert "game_bar" in result
        assert "game_dvr" in result
        assert "hags" in result
        assert "vbs" in result
        assert "hdr" in result
        assert "hdr_capable_count" in result
        assert "hdr_enabled_count" in result
        assert "auto_hdr" in result
        assert "windowed_optimizations" in result
        assert "vrr_optimize" in result
        assert "refresh_rate" in result
        assert "max_refresh_rate" in result
        assert "available_refresh_rates" in result

    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_vrr_optimize")
    @patch.object(WindowsSettingsHandler, "_get_windowed_optimizations")
    @patch.object(WindowsSettingsHandler, "_get_auto_hdr")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_vbs")
    @patch.object(WindowsSettingsHandler, "_get_hags")
    @patch.object(WindowsSettingsHandler, "_get_game_dvr")
    @patch.object(WindowsSettingsHandler, "_get_game_bar")
    @patch.object(WindowsSettingsHandler, "_get_game_mode")
    def test_detect_game_mode_enabled(
        self,
        mock_game_mode,
        mock_game_bar,
        mock_game_dvr,
        mock_hags,
        mock_vbs,
        mock_hdr_summary,
        mock_auto_hdr,
        mock_windowed_optimizations,
        mock_vrr_optimize,
        mock_refresh_info,
    ):
        """Test detecting game mode when enabled."""
        mock_game_mode.return_value = True
        mock_game_bar.return_value = False
        mock_game_dvr.return_value = False
        mock_hags.return_value = None
        mock_vbs.return_value = False
        mock_hdr_summary.return_value = {
            "available": False,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "any_enabled": False,
        }
        mock_auto_hdr.return_value = None
        mock_windowed_optimizations.return_value = None
        mock_vrr_optimize.return_value = None
        mock_refresh_info.return_value = {"current": 60, "max": 60, "available": [60]}

        handler = WindowsSettingsHandler()
        result = handler.detect()

        assert result["game_mode"] is True
        assert result["hdr"] is None
        assert result["hdr_capable_count"] is None

    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_vrr_optimize")
    @patch.object(WindowsSettingsHandler, "_get_windowed_optimizations")
    @patch.object(WindowsSettingsHandler, "_get_auto_hdr")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_vbs")
    @patch.object(WindowsSettingsHandler, "_get_hags")
    @patch.object(WindowsSettingsHandler, "_get_game_dvr")
    @patch.object(WindowsSettingsHandler, "_get_game_bar")
    @patch.object(WindowsSettingsHandler, "_get_game_mode")
    def test_detect_handles_missing_keys(
        self,
        mock_game_mode,
        mock_game_bar,
        mock_game_dvr,
        mock_hags,
        mock_vbs,
        mock_hdr_summary,
        mock_auto_hdr,
        mock_windowed_optimizations,
        mock_vrr_optimize,
        mock_refresh_info,
    ):
        """Test detect handles missing registry keys gracefully."""
        mock_game_mode.return_value = None
        mock_game_bar.return_value = None
        mock_game_dvr.return_value = None
        mock_hags.return_value = None
        mock_vbs.return_value = None
        mock_hdr_summary.return_value = {
            "available": False,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "any_enabled": False,
        }
        mock_auto_hdr.return_value = None
        mock_windowed_optimizations.return_value = None
        mock_vrr_optimize.return_value = None
        mock_refresh_info.return_value = {"current": None, "max": None, "available": []}

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
            "hdr": None,
            "auto_hdr": None,
            "refresh_rate": 60,
            "max_refresh_rate": 60,
            "available_refresh_rates": [60],
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
            "hdr": None,
            "auto_hdr": None,
            "refresh_rate": 60,
            "max_refresh_rate": 60,
            "available_refresh_rates": [60],
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
            "hdr": None,
            "auto_hdr": None,
            "refresh_rate": 60,
            "max_refresh_rate": 60,
            "available_refresh_rates": [60],
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
            "hdr": None,
            "auto_hdr": None,
            "refresh_rate": 60,
            "max_refresh_rate": 60,
            "available_refresh_rates": [60],
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
            "hdr": None,
            "auto_hdr": None,
            "refresh_rate": 240,
            "max_refresh_rate": 240,
            "available_refresh_rates": [60, 120, 240],
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0

    @patch.object(WindowsSettingsHandler, "detect")
    def test_audit_refresh_rate_suboptimal_creates_issue(self, mock_detect):
        """Test audit creates issue when refresh rate is below maximum."""
        mock_detect.return_value = {
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
            "hags": True,
            "vbs": False,
            "hdr": None,
            "auto_hdr": None,
            "refresh_rate": 60,
            "max_refresh_rate": 240,
            "available_refresh_rates": [60, 120, 240],
        }

        handler = WindowsSettingsHandler()
        issues = handler.audit()

        refresh_issues = [i for i in issues if "refresh rate" in i.title.lower()]
        assert len(refresh_issues) == 1
        assert refresh_issues[0].severity == "warning"


class TestWindowsApply:
    """Tests for WindowsSettingsHandler.apply()."""

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_game_mode")
    def test_apply_game_mode(self, mock_set_game_mode, mock_detect):
        """Test applying game mode setting."""
        mock_detect.return_value = {"game_mode": False, "hags": None, "vbs": None}
        mock_set_game_mode.return_value = None

        handler = WindowsSettingsHandler()
        result = handler.apply({"game_mode": True})

        assert result["success"] is True
        mock_set_game_mode.assert_called_once_with(True)

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_game_mode")
    @patch.object(WindowsSettingsHandler, "_set_game_bar")
    @patch.object(WindowsSettingsHandler, "_set_game_dvr")
    def test_apply_multiple_settings(
        self, mock_set_dvr, mock_set_bar, mock_set_mode, mock_detect
    ):
        """Test applying multiple settings at once."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_mode.return_value = None
        mock_set_bar.return_value = None
        mock_set_dvr.return_value = None

        handler = WindowsSettingsHandler()
        result = handler.apply({
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
        })

        assert result["success"] is True
        assert len(result["applied"]) == 3

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_game_mode")
    def test_apply_permission_error(self, mock_set_game_mode, mock_detect):
        """Test apply handles permission errors."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_game_mode.side_effect = PermissionError("Access denied")

        handler = WindowsSettingsHandler()
        result = handler.apply({"game_mode": True})

        assert result["success"] is False
        assert len(result["failed"]) == 1
        assert "Access denied" in result["error"]

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_vbs")
    def test_apply_vbs_requires_reboot(self, mock_set_vbs, mock_detect):
        """Test that VBS changes require reboot when value differs."""
        mock_detect.return_value = {"hags": None, "vbs": True}
        mock_set_vbs.return_value = None

        handler = WindowsSettingsHandler()
        result = handler.apply({"vbs": False})

        assert result["requires_reboot"] is True
        assert result["success"] is True

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_hdr")
    def test_apply_hdr_success(self, mock_set_hdr, mock_detect):
        """Test applying HDR setting successfully."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_hdr.return_value = {
            "success": True,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "errors": [],
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"hdr": True})

        assert result["success"] is True
        assert "HDR: enabled on 1 monitor(s)" in result["applied"]

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_hdr")
    def test_apply_hdr_failure(self, mock_set_hdr, mock_detect):
        """Test applying HDR setting with error."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_hdr.return_value = {
            "success": False,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "errors": ["Permission denied for monitor ABC123"],
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"hdr": True})

        assert result["success"] is False
        assert "Permission denied" in result["error"]

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_hdr")
    def test_apply_hdr_enable_fails_when_windows_reports_zero_hdr_outputs(
        self, mock_set_hdr, mock_detect
    ):
        """HDR enable should fail if Windows reports no HDR-capable/enabled outputs."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_hdr.return_value = {
            "success": True,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "errors": [],
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"hdr": True})

        assert result["success"] is False
        assert "no HDR-capable active displays" in (result["error"] or "")

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_auto_hdr")
    def test_apply_auto_hdr_success(self, mock_set_auto_hdr, mock_detect):
        """Test applying Auto HDR setting successfully."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_auto_hdr.return_value = {"success": True, "error": None}

        handler = WindowsSettingsHandler()
        result = handler.apply({"auto_hdr": False})

        assert result["success"] is True
        assert "Auto HDR: disabled" in result["applied"]

    @patch.object(WindowsSettingsHandler, "detect")
    @patch.object(WindowsSettingsHandler, "_set_auto_hdr")
    def test_apply_auto_hdr_failure(self, mock_set_auto_hdr, mock_detect):
        """Test applying Auto HDR setting with error."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_auto_hdr.return_value = {"success": False, "error": "Registry access denied"}

        handler = WindowsSettingsHandler()
        result = handler.apply({"auto_hdr": True})

        assert result["success"] is False
        assert "Registry access denied" in result["error"]


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
            "hdr": True,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "auto_hdr": False,
            "windowed_optimizations": False,
            "vrr_optimize": False,
            "refresh_rate": 240,
            "max_refresh_rate": 240,
            "available_refresh_rates": [60, 120, 240],
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


class TestWindowsHdrCapability:
    """Tests for HDR capability detection."""

    @patch("abso.settings.windows.winreg")
    def test_is_monitor_hdr_capable_returns_false_when_registry_capability_missing(self, mock_winreg):
        """HDR capability should not be guessed when Windows has no capability flag."""
        mock_winreg.OpenKey.side_effect = FileNotFoundError()

        handler = WindowsSettingsHandler()
        assert handler._is_monitor_hdr_capable("GSM784C_12345") is False

    @patch("abso.settings.windows.winreg")
    def test_is_monitor_hdr_capable_registry_check(self, mock_winreg):
        """Test HDR capability via registry AdvancedColorSupported."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (1, winreg.REG_DWORD)
        mock_winreg.HKEY_LOCAL_MACHINE = winreg.HKEY_LOCAL_MACHINE
        mock_winreg.KEY_READ = winreg.KEY_READ

        handler = WindowsSettingsHandler()

        # Unknown monitor with AdvancedColorSupported=1
        result = handler._is_monitor_hdr_capable("UNKNOWN_MONITOR")
        assert result is True


class TestWindowsRefreshRate:
    """Tests for refresh rate detection and setting."""

    @patch("abso.settings.windows.ctypes")
    def test_get_refresh_rate_info(self, mock_ctypes):
        """Test getting refresh rate information."""
        # Mock user32 and EnumDisplaySettingsW
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_ctypes.sizeof.return_value = 220
        mock_ctypes.byref.side_effect = lambda x: x

        # Current settings call returns True, subsequent calls enumerate modes
        call_count = [0]
        def enum_side_effect(device, mode_num, devmode):
            call_count[0] += 1
            if call_count[0] == 1:  # Current settings
                devmode.dmDisplayFrequency = 144
                devmode.dmPelsWidth = 2560
                devmode.dmPelsHeight = 1440
                return True
            elif call_count[0] <= 4:  # Available modes
                devmode.dmDisplayFrequency = [60, 120, 144][call_count[0] - 2]
                devmode.dmPelsWidth = 2560
                devmode.dmPelsHeight = 1440
                return True
            return False

        mock_user32.EnumDisplaySettingsW.side_effect = enum_side_effect

        handler = WindowsSettingsHandler()
        result = handler._get_refresh_rate_info()

        assert result["current"] == 144
        assert result["max"] == 144
        assert 60 in result["available"]
        assert 120 in result["available"]

    @patch("abso.settings.windows.ctypes")
    def test_get_refresh_rate_info_failure(self, mock_ctypes):
        """Test graceful handling when refresh rate detection fails."""
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        mock_user32.EnumDisplaySettingsW.return_value = False

        handler = WindowsSettingsHandler()
        result = handler._get_refresh_rate_info()

        assert result["current"] is None
        assert result["max"] is None
        assert result["available"] == []
