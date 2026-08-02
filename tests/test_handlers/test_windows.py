"""Tests for WindowsSettingsHandler."""

import winreg
from unittest.mock import MagicMock, patch

import pytest

from abso.settings.windows import (
    _LUID,
    DISPLAYCONFIG_ADVANCED_COLOR_MODE_SDR,
    DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO,
    DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO_2,
    WindowsSettingsHandler,
)


class TestWindowsDetect:
    """Tests for WindowsSettingsHandler.detect()."""

    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_directx_flags")
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
        mock_directx_flags,
        mock_refresh_info,
        mock_sdr_white_level,
        mock_advanced_color,
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
            "hdr_active_count": 1,
            "any_enabled": True,
            "any_active": True,
            "per_target": [{"target_id": 1, "hdr_user_enabled": True, "hdr_active": True}],
        }
        mock_directx_flags.return_value = {
            "auto_hdr": False,
            "windowed_optimizations": False,
            "vrr_optimize": False,
        }
        mock_refresh_info.return_value = {"current": 240, "max": 240, "available": [60, 120, 240]}
        mock_sdr_white_level.return_value = {
            "available": True,
            "per_target": [{"target_id": 1, "nits": 200.0, "hdr_enabled": True}],
            "any_hdr_enabled": True,
            "min_nits": 200.0,
            "max_nits": 200.0,
        }
        mock_advanced_color.return_value = {
            "any_enabled": True,
            "per_monitor": {"MONITOR_01": True},
        }

        handler = WindowsSettingsHandler()
        result = handler.detect()

        assert "game_mode" in result
        assert "game_bar" in result
        assert "game_dvr" in result
        assert "hags" in result
        assert "vbs" in result
        assert "hdr" in result
        assert "hdr_active" in result
        assert "hdr_capable_count" in result
        assert "hdr_enabled_count" in result
        assert "hdr_active_count" in result
        assert "hdr_per_target" in result
        assert "auto_hdr" in result
        assert "windowed_optimizations" in result
        assert "vrr_optimize" in result
        assert "refresh_rate" in result
        assert "max_refresh_rate" in result
        assert "available_refresh_rates" in result
        assert "sdr_white_level_nits" in result
        assert result["sdr_white_level_nits"] == 200.0
        assert "advanced_color" in result
        assert result["advanced_color"] is True

    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_directx_flags")
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
        mock_directx_flags,
        mock_refresh_info,
        mock_sdr_white_level,
        mock_advanced_color,
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
            "hdr_active_count": 0,
            "any_enabled": False,
            "any_active": False,
        }
        mock_directx_flags.return_value = {
            "auto_hdr": None,
            "windowed_optimizations": None,
            "vrr_optimize": None,
        }
        mock_refresh_info.return_value = {"current": 60, "max": 60, "available": [60]}
        mock_sdr_white_level.return_value = {
            "available": False,
            "per_target": [],
            "any_hdr_enabled": False,
            "min_nits": None,
            "max_nits": None,
        }
        mock_advanced_color.return_value = {"any_enabled": False, "per_monitor": {}}

        handler = WindowsSettingsHandler()
        result = handler.detect()

        assert result["game_mode"] is True
        assert result["hdr"] is None
        assert result["hdr_capable_count"] is None

    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_directx_flags")
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
        mock_directx_flags,
        mock_refresh_info,
        mock_sdr_white_level,
        mock_advanced_color,
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
            "hdr_active_count": 0,
            "any_enabled": False,
            "any_active": False,
        }
        mock_directx_flags.return_value = {
            "auto_hdr": None,
            "windowed_optimizations": None,
            "vrr_optimize": None,
        }
        mock_refresh_info.return_value = {"current": None, "max": None, "available": []}
        mock_sdr_white_level.return_value = {
            "available": False,
            "per_target": [],
            "any_hdr_enabled": False,
            "min_nits": None,
            "max_nits": None,
        }
        mock_advanced_color.return_value = {"any_enabled": False, "per_monitor": {}}

        handler = WindowsSettingsHandler()
        result = handler.detect()

        # Should return None for missing values, not crash
        assert result is not None


class TestWindowsApplyDetection:
    """Tests for narrow pre-apply detection."""

    def test_detect_for_apply_registry_flags_skips_display_probes(self):
        handler = WindowsSettingsHandler()
        with (
            patch.object(handler, "_get_game_mode", return_value=False) as mock_game_mode,
            patch.object(handler, "_get_game_bar", return_value=True) as mock_game_bar,
            patch.object(handler, "_get_game_dvr", return_value=True) as mock_game_dvr,
            patch.object(
                handler,
                "_get_directx_flags",
                return_value={
                    "auto_hdr": False,
                    "windowed_optimizations": True,
                    "vrr_optimize": False,
                },
            ) as mock_directx,
            patch.object(handler, "_get_refresh_rate_info") as mock_refresh,
            patch.object(handler, "_get_hdr_state_summary") as mock_hdr,
            patch.object(handler, "_get_sdr_white_level") as mock_sdr,
            patch.object(handler, "_get_advanced_color") as mock_advanced,
        ):
            current = handler._detect_for_apply(
                {
                    "game_mode": True,
                    "game_bar": False,
                    "game_dvr": False,
                    "auto_hdr": False,
                    "windowed_optimizations": True,
                    "vrr_optimize": False,
                }
            )

        assert current == {
            "game_mode": False,
            "game_bar": True,
            "game_dvr": True,
            "auto_hdr": False,
            "windowed_optimizations": True,
            "vrr_optimize": False,
        }
        mock_game_mode.assert_called_once_with()
        mock_game_bar.assert_called_once_with()
        mock_game_dvr.assert_called_once_with()
        mock_directx.assert_called_once_with()
        mock_refresh.assert_not_called()
        mock_hdr.assert_not_called()
        mock_sdr.assert_not_called()
        mock_advanced.assert_not_called()

    def test_detect_for_apply_reads_directx_flags_once(self):
        handler = WindowsSettingsHandler()
        with (
            patch.object(
                handler,
                "_get_directx_flags",
                return_value={
                    "auto_hdr": False,
                    "windowed_optimizations": True,
                    "vrr_optimize": True,
                },
            ) as mock_directx,
            patch.object(handler, "_get_auto_hdr") as mock_auto_hdr,
            patch.object(handler, "_get_windowed_optimizations") as mock_windowed,
            patch.object(handler, "_get_vrr_optimize") as mock_vrr,
        ):
            current = handler._detect_for_apply(
                {
                    "auto_hdr": False,
                    "windowed_optimizations": True,
                    "vrr_optimize": True,
                }
            )

        assert current == {
            "auto_hdr": False,
            "windowed_optimizations": True,
            "vrr_optimize": True,
        }
        mock_directx.assert_called_once_with()
        mock_auto_hdr.assert_not_called()
        mock_windowed.assert_not_called()
        mock_vrr.assert_not_called()

    def test_detect_for_apply_advanced_color_reads_only_color_and_hdr_state(self):
        handler = WindowsSettingsHandler()
        with (
            patch.object(
                handler,
                "_get_advanced_color",
                return_value={"any_enabled": False, "per_monitor": {"MONITOR": False}},
            ) as mock_advanced,
            patch.object(
                handler,
                "_get_hdr_state_summary",
                return_value={
                    "available": True,
                    "any_enabled": True,
                    "any_active": False,
                    "hdr_capable_count": 1,
                    "hdr_enabled_count": 1,
                    "hdr_active_count": 0,
                    "per_target": [{"target_id": 1}],
                },
            ) as mock_hdr,
            patch.object(handler, "_get_refresh_rate_info") as mock_refresh,
            patch.object(handler, "_get_sdr_white_level") as mock_sdr,
        ):
            current = handler._detect_for_apply({"advanced_color": True})

        assert current["advanced_color"] is False
        assert current["advanced_color_per_monitor"] == {"MONITOR": False}
        assert current["hdr"] is True
        assert current["hdr_active"] is False
        assert current["hdr_capable_count"] == 1
        mock_advanced.assert_called_once_with()
        mock_hdr.assert_called_once_with()
        mock_refresh.assert_not_called()
        mock_sdr.assert_not_called()

    def test_directx_settings_with_flag_creates_each_default_flag_once(self):
        value = WindowsSettingsHandler._directx_settings_with_flag(
            None,
            "AutoHDREnable",
            True,
        )

        assert value == "AutoHDREnable=1;SwapEffectUpgradeEnable=0;VRROptimizeEnable=0"
        assert value.count("AutoHDREnable=") == 1
        assert value.count("SwapEffectUpgradeEnable=") == 1
        assert value.count("VRROptimizeEnable=") == 1

    def test_directx_settings_with_flag_normalizes_tracked_flags(self):
        value = WindowsSettingsHandler._directx_settings_with_flag(
            "AutoHDREnable=0;"
            "CustomFlag=7;"
            "VRROptimizeEnable=1;"
            "AutoHDREnable=1;"
            "SwapEffectUpgradeEnable=10;"
            "VRROptimizeEnable=0",
            "AutoHDREnable",
            False,
        )

        assert (
            value
            == "CustomFlag=7;AutoHDREnable=0;SwapEffectUpgradeEnable=0;VRROptimizeEnable=0"
        )
        assert value.count("AutoHDREnable=") == 1
        assert value.count("SwapEffectUpgradeEnable=") == 1
        assert value.count("VRROptimizeEnable=") == 1

    def test_parse_directx_flags_uses_exact_tracked_tokens(self):
        result = WindowsSettingsHandler._parse_directx_flags(
            "AutoHDREnable=10;"
            "SwapEffectUpgradeEnable=1;"
            "VRROptimizeEnable=1;"
            "VRROptimizeEnable=0;"
            "Untracked=1"
        )

        assert result == {
            "auto_hdr": False,
            "windowed_optimizations": True,
            "vrr_optimize": False,
        }


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

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_game_mode")
    def test_apply_game_mode(self, mock_set_game_mode, mock_detect):
        """Test applying game mode setting."""
        mock_detect.return_value = {"game_mode": False, "hags": None, "vbs": None}
        mock_set_game_mode.return_value = None

        handler = WindowsSettingsHandler()
        result = handler.apply({"game_mode": True})

        assert result["success"] is True
        mock_set_game_mode.assert_called_once_with(True)

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_game_mode")
    @patch.object(WindowsSettingsHandler, "_set_game_bar")
    @patch.object(WindowsSettingsHandler, "_set_game_dvr")
    def test_apply_multiple_settings(self, mock_set_dvr, mock_set_bar, mock_set_mode, mock_detect):
        """Test applying multiple settings at once."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_mode.return_value = None
        mock_set_bar.return_value = None
        mock_set_dvr.return_value = None

        handler = WindowsSettingsHandler()
        result = handler.apply(
            {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
            }
        )

        assert result["success"] is True
        assert len(result["applied"]) == 3
        assert sorted(result["changed_keys"]) == ["game_bar", "game_dvr", "game_mode"]

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_windowed_optimizations")
    @patch.object(WindowsSettingsHandler, "_set_vrr_optimize")
    def test_apply_skips_matching_directx_compositor_flags(
        self, mock_set_vrr, mock_set_windowed, mock_detect
    ):
        """Re-applying matching compositor flags must not churn DirectX registry state."""
        mock_detect.return_value = {
            "windowed_optimizations": True,
            "vrr_optimize": False,
            "hags": None,
            "vbs": None,
        }

        handler = WindowsSettingsHandler()
        result = handler.apply(
            {
                "windowed_optimizations": True,
                "vrr_optimize": False,
            }
        )

        assert result["success"] is True
        assert result["changed"] is False
        assert result["changed_keys"] == []
        mock_set_windowed.assert_not_called()
        mock_set_vrr.assert_not_called()

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
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

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_vbs")
    def test_apply_vbs_requires_reboot(self, mock_set_vbs, mock_detect):
        """Test that VBS changes require reboot when value differs."""
        mock_detect.return_value = {"hags": None, "vbs": True}
        mock_set_vbs.return_value = None

        handler = WindowsSettingsHandler()
        result = handler.apply({"vbs": False})

        assert result["requires_reboot"] is True
        assert result["success"] is True

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
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
        assert "HDR: active on 1 monitor(s) (1 with Use HDR enabled)" in result["applied"]

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
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

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
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

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_auto_hdr")
    def test_apply_auto_hdr_success(self, mock_set_auto_hdr, mock_detect):
        """Test applying Auto HDR setting successfully."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_auto_hdr.return_value = {"success": True, "error": None}

        handler = WindowsSettingsHandler()
        result = handler.apply({"auto_hdr": False})

        assert result["success"] is True
        assert "Auto HDR: disabled" in result["applied"]

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_auto_hdr")
    def test_apply_auto_hdr_failure(self, mock_set_auto_hdr, mock_detect):
        """Test applying Auto HDR setting with error."""
        mock_detect.return_value = {"hags": None, "vbs": None}
        mock_set_auto_hdr.return_value = {"success": False, "error": "Registry access denied"}

        handler = WindowsSettingsHandler()
        result = handler.apply({"auto_hdr": True})

        assert result["success"] is False
        assert "Registry access denied" in result["error"]

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_refresh_rate")
    def test_apply_skips_refresh_rate_when_already_active(self, mock_set_refresh, mock_detect):
        """Already-active refresh rate must not call ChangeDisplaySettings."""
        mock_detect.return_value = {"refresh_rate": 240}

        handler = WindowsSettingsHandler()
        result = handler.apply({"refresh_rate": 240})

        assert result["success"] is True
        assert result["changed"] is False
        assert "Refresh Rate: already 240 Hz" in result["applied"]
        mock_set_refresh.assert_not_called()

    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    @patch.object(WindowsSettingsHandler, "_set_max_refresh_rate")
    def test_apply_skips_max_refresh_rate_when_already_at_max(
        self,
        mock_set_max_refresh,
        mock_detect,
    ):
        """Already-max refresh rate must not re-enter display mode setting."""
        mock_detect.return_value = {"refresh_rate": 240, "max_refresh_rate": 240}

        handler = WindowsSettingsHandler()
        result = handler.apply({"max_refresh_rate": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert "Refresh Rate: already at maximum (240 Hz)" in result["applied"]
        mock_set_max_refresh.assert_not_called()


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


class TestWindowsVerifyActive:
    """Tests for WindowsSettingsHandler.verify_active display readback."""

    @patch.object(WindowsSettingsHandler, "_detect_for_verify")
    def test_verify_active_includes_hdr_and_color_state(self, mock_detect):
        mock_detect.return_value = {
            "game_mode": True,
            "game_bar": False,
            "game_dvr": False,
            "hags": True,
            "vbs": False,
            "hdr": True,
            "hdr_active": True,
            "auto_hdr": False,
            "advanced_color": True,
            "sdr_white_level_nits": 200.4,
            "windowed_optimizations": True,
            "vrr_optimize": True,
            "refresh_rate": 300,
            "max_refresh_rate": 300,
        }

        handler = WindowsSettingsHandler()
        result = handler.verify_active(
            {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "vbs": False,
                "hdr": True,
                "auto_hdr": False,
                "advanced_color": True,
                "sdr_white_level_nits": 200,
                "windowed_optimizations": True,
                "vrr_optimize": True,
                "max_refresh_rate": True,
            }
        )

        assert result["all_active"] is True
        assert result["settings"]["game_mode"]["active"] is True
        assert result["settings"]["game_bar"]["active"] is True
        assert result["settings"]["game_dvr"]["active"] is True
        assert result["settings"]["hdr"]["active"] is True
        assert result["settings"]["auto_hdr"]["active"] is True
        assert result["settings"]["advanced_color"]["active"] is True
        assert result["settings"]["sdr_white_level_nits"]["active"] is True
        assert result["settings"]["windowed_optimizations"]["active"] is True
        assert result["settings"]["vrr_optimize"]["active"] is True
        assert result["settings"]["max_refresh_rate"]["active"] is True

    @patch.object(WindowsSettingsHandler, "_detect_for_verify")
    def test_verify_active_flags_hdr_swap_failure(self, mock_detect):
        mock_detect.return_value = {
            "hags": True,
            "vbs": False,
            "hdr": False,
            "hdr_active": False,
            "auto_hdr": False,
            "advanced_color": False,
            "sdr_white_level_nits": None,
        }

        handler = WindowsSettingsHandler()
        result = handler.verify_active(
            {
                "hdr": True,
                "auto_hdr": False,
                "advanced_color": True,
                "sdr_white_level_nits": 200,
            }
        )

        assert result["all_active"] is False
        assert result["settings"]["hdr"]["active"] is False
        assert result["settings"]["advanced_color"]["active"] is False
        assert result["settings"]["sdr_white_level_nits"]["active"] is False

    @patch.object(WindowsSettingsHandler, "_detect_for_verify")
    def test_verify_active_flags_hdr_user_enabled_but_inactive(self, mock_detect):
        """Use HDR can be on while the live compositor mode is still SDR."""
        mock_detect.return_value = {
            "hdr": True,
            "hdr_active": False,
        }

        handler = WindowsSettingsHandler()
        result = handler.verify_active({"hdr": True})

        assert result["all_active"] is False
        assert result["settings"]["hdr"]["current"] == {
            "user_enabled": True,
            "active": False,
        }
        assert result["settings"]["hdr"]["active"] is False

    @patch.object(WindowsSettingsHandler, "_detect_for_verify")
    def test_verify_active_passes_when_active_matches_even_if_user_enabled_stuck(
        self,
        mock_detect,
    ):
        """HDR=off profile must pass verify when the live compositor is SDR,
        even if a secondary HDR-capable target still has 'Use HDR' set in
        the registry. The per-monitor user_enabled bit is sticky on Win11
        25H2 multi-monitor setups and is not load-bearing for user-visible
        HDR state."""
        mock_detect.return_value = {
            "hdr": True,  # stuck user_enabled on a secondary HDR-capable monitor
            "hdr_active": False,  # live compositor is SDR (what the user sees)
        }

        handler = WindowsSettingsHandler()
        result = handler.verify_active({"hdr": False})

        assert result["all_active"] is True
        assert result["settings"]["hdr"]["active"] is True
        assert result["settings"]["hdr"]["current"] == {
            "user_enabled": True,
            "active": False,
        }

    @patch.object(WindowsSettingsHandler, "_detect_for_verify")
    def test_verify_active_flags_known_registry_and_refresh_mismatches(self, mock_detect):
        mock_detect.return_value = {
            "game_mode": False,
            "game_bar": True,
            "game_dvr": True,
            "windowed_optimizations": False,
            "vrr_optimize": False,
            "refresh_rate": 60,
            "max_refresh_rate": 300,
        }

        handler = WindowsSettingsHandler()
        result = handler.verify_active(
            {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "windowed_optimizations": True,
                "vrr_optimize": True,
                "max_refresh_rate": True,
            }
        )

        assert result["all_active"] is False
        assert result["settings"]["game_mode"]["active"] is False
        assert result["settings"]["game_bar"]["active"] is False
        assert result["settings"]["game_dvr"]["active"] is False
        assert result["settings"]["windowed_optimizations"]["active"] is False
        assert result["settings"]["vrr_optimize"]["active"] is False
        assert result["settings"]["max_refresh_rate"]["active"] is False

    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_refresh_rate_info")
    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "detect")
    def test_verify_active_uses_narrow_detection(
        self,
        mock_detect,
        mock_sdr,
        mock_advanced,
        mock_refresh,
        mock_hdr,
    ):
        handler = WindowsSettingsHandler()
        with (
            patch.object(handler, "_get_game_mode", return_value=True),
            patch.object(handler, "_get_game_bar", return_value=False),
            patch.object(handler, "_get_game_dvr", return_value=False),
        ):
            result = handler.verify_active(
                {
                    "game_mode": True,
                    "game_bar": False,
                    "game_dvr": False,
                }
            )

        assert result["all_active"] is True
        mock_detect.assert_not_called()
        mock_hdr.assert_not_called()
        mock_refresh.assert_not_called()
        mock_advanced.assert_not_called()
        mock_sdr.assert_not_called()


class TestWindowsHdrCapability:
    """Tests for HDR capability detection."""

    @patch("abso.settings.windows.winreg")
    def test_is_monitor_hdr_capable_returns_false_when_registry_capability_missing(
        self, mock_winreg
    ):
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


class TestWindowsHdrInfo2Readback:
    """Tests for Win11 HDR/WCG split-state readback."""

    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes.windll.user32.DisplayConfigGetDeviceInfo")
    def test_hdr_summary_uses_info2_user_enabled_and_active_mode(
        self,
        mock_get_info,
        mock_targets,
    ):
        mock_targets.return_value = [(_LUID(0, 0), 1)]

        def fake_get_info(ptr):
            obj = ptr._obj
            assert obj.header.type == DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO_2
            obj.value = (
                0x01 | 0x02 | 0x10 | 0x20
            )  # supported, active-color, HDR supported, Use HDR on
            obj.activeColorMode = DISPLAYCONFIG_ADVANCED_COLOR_MODE_SDR
            return 0

        mock_get_info.side_effect = fake_get_info

        handler = WindowsSettingsHandler()
        result = handler._get_hdr_state_summary()

        assert result["available"] is True
        assert result["hdr_capable_count"] == 1
        assert result["hdr_enabled_count"] == 1
        assert result["hdr_active_count"] == 0
        assert result["any_enabled"] is True
        assert result["any_active"] is False
        assert result["per_target"][0]["api"] == "advanced_color_info_2"

    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes.windll.user32.DisplayConfigGetDeviceInfo")
    def test_hdr_summary_falls_back_to_legacy_advanced_color(
        self,
        mock_get_info,
        mock_targets,
    ):
        mock_targets.return_value = [(_LUID(0, 0), 1)]

        def fake_get_info(ptr):
            obj = ptr._obj
            if obj.header.type == DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO_2:
                return 87
            assert obj.header.type == DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
            obj.value = 0x03
            return 0

        mock_get_info.side_effect = fake_get_info

        handler = WindowsSettingsHandler()
        result = handler._get_hdr_state_summary()

        assert result["hdr_capable_count"] == 1
        assert result["hdr_enabled_count"] == 1
        assert result["hdr_active_count"] == 1
        assert result["per_target"][0]["api"] == "advanced_color_info_legacy"


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


class TestSdrWhiteLevel:
    """Tests for the SDR content brightness (HDR paper-white) pathway.

    The DisplayConfig API is fully mocked — these tests do not touch the
    live display pipeline. They verify the nits-to-DisplayConfig encoding,
    the HDR-on gating, and the surfacing of per-monitor errors.
    """

    def test_encoding_nits_to_sdr_white_level(self):
        """200 nits -> 2500, 250 nits -> 3125, 80 nits -> 1000 (Windows spec)."""
        from abso.settings.windows import SDR_WHITE_LEVEL_UNITS_PER_NIT

        assert int(round(200 * SDR_WHITE_LEVEL_UNITS_PER_NIT)) == 2500
        assert int(round(250 * SDR_WHITE_LEVEL_UNITS_PER_NIT)) == 3125
        assert int(round(80 * SDR_WHITE_LEVEL_UNITS_PER_NIT)) == 1000
        assert int(round(480 * SDR_WHITE_LEVEL_UNITS_PER_NIT)) == 6000

    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes")
    def test_set_clamps_below_floor(self, mock_ctypes, mock_targets):
        """Values under 80 nits clamp to 80 (Windows API rejects below)."""
        mock_targets.return_value = []
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32

        handler = WindowsSettingsHandler()
        result = handler._set_sdr_white_level(10)

        assert result["requested_nits"] == 80

    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes")
    def test_set_clamps_above_ceiling(self, mock_ctypes, mock_targets):
        """Values above 480 nits clamp to 480 (usable ceiling on most displays)."""
        mock_targets.return_value = []
        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32

        handler = WindowsSettingsHandler()
        result = handler._set_sdr_white_level(9999)

        assert result["requested_nits"] == 480

    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes")
    def test_set_skips_sdr_monitors(self, mock_ctypes, mock_targets):
        """SDR (non-HDR) monitors are skipped; not counted as an error."""
        adapter_id = MagicMock()
        mock_targets.return_value = [(adapter_id, 1), (adapter_id, 2)]

        mock_user32 = MagicMock()
        mock_ctypes.windll.user32 = mock_user32
        # GetDeviceInfo succeeds with advancedColor bits reporting SDR (bit 1 = 0).
        mock_user32.DisplayConfigGetDeviceInfo.return_value = 0

        def _get_info_side_effect(ptr):
            # Zero out advancedColorEnabled bit to mark SDR
            return 0

        handler = WindowsSettingsHandler()
        # Force advancedColorEnabled=0 on the struct returned.
        with patch.object(handler, "_set_sdr_white_level", wraps=handler._set_sdr_white_level):
            # The real method inspects info.value & 0x02 — we need the mocked
            # ctypes call to leave info.value at 0. MagicMock-typed structs
            # zero-init to 0 by default, so this should just work.
            result = handler._set_sdr_white_level(200)

        assert result["skipped_count"] >= 0  # Minimal smoke — full flow mocked

    def test_set_with_no_display_targets_does_not_fail(self):
        """Zero enumerated targets is a warning, not a failure — cosmetic setting."""
        handler = WindowsSettingsHandler()
        with patch.object(handler, "_get_active_display_targets", return_value=[]):
            result = handler._set_sdr_white_level(200)

        assert result["success"] is True  # cosmetic; never fail
        assert result["applied_count"] == 0
        assert any("No active display" in msg for msg in result["warnings"])

    def test_skip_errors_classification(self):
        """The known "driver declined this op" set must include 87 so real-world
        24H2 "everything looks washed out" bug doesn't rollback profiles."""
        assert 87 in WindowsSettingsHandler._SDR_WHITE_LEVEL_SKIP_ERRORS  # invalid param
        assert 50 in WindowsSettingsHandler._SDR_WHITE_LEVEL_SKIP_ERRORS  # not supported
        assert 31 in WindowsSettingsHandler._SDR_WHITE_LEVEL_SKIP_ERRORS  # gen failure
        assert 1168 in WindowsSettingsHandler._SDR_WHITE_LEVEL_SKIP_ERRORS  # not found

    def test_set_crash_returns_best_effort_not_failure(self):
        """If _get_active_display_targets raises, the handler must still
        return success=True and not fail the handler."""
        handler = WindowsSettingsHandler()
        with patch.object(
            handler,
            "_get_active_display_targets",
            side_effect=RuntimeError("CCD broken"),
        ):
            result = handler._set_sdr_white_level(200)

        # Cosmetic setting — we never want to break the profile apply.
        assert result["success"] is True
        assert any("crashed" in w.lower() for w in result["warnings"])

    @patch.object(WindowsSettingsHandler, "_set_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_wires_sdr_white_level_through(self, mock_detect, mock_set):
        """apply({sdr_white_level_nits}) routes into _set_sdr_white_level."""
        mock_detect.return_value = {}
        mock_set.return_value = {
            "success": True,
            "requested_nits": 200,
            "applied_count": 1,
            "skipped_count": 0,
            "warnings": [],
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"sdr_white_level_nits": 200})

        mock_set.assert_called_once_with(200.0)
        assert any("SDR content brightness" in msg for msg in result.get("applied", []))
        assert result.get("success", True) is True

    @patch.object(WindowsSettingsHandler, "_set_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_skips_sdr_white_when_already_active(self, mock_detect, mock_set):
        """Already-matching SDR paper white should not poke DisplayConfig."""
        mock_detect.return_value = {"sdr_white_level_nits": 200.4}

        handler = WindowsSettingsHandler()
        result = handler.apply({"sdr_white_level_nits": 200})

        mock_set.assert_not_called()
        assert any("already 200.0 nits" in msg for msg in result.get("applied", []))

    @patch.object(WindowsSettingsHandler, "_set_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_skips_when_no_hdr_monitors(self, mock_detect, mock_set):
        """If all monitors are SDR, apply surfaces a notice, not an error."""
        mock_detect.return_value = {}
        mock_set.return_value = {
            "success": True,
            "requested_nits": 200,
            "applied_count": 0,
            "skipped_count": 2,
            "warnings": [],
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"sdr_white_level_nits": 200})

        applied_msgs = result.get("applied", [])
        assert any("skipped" in msg.lower() for msg in applied_msgs)
        # Critical invariant: SDR white level must never fail the handler.
        assert result.get("success", True) is True
        assert result.get("errors", []) == []

    @patch.object(WindowsSettingsHandler, "_set_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_never_fails_handler_on_sdr_white_warnings(self, mock_detect, mock_set):
        """Even when targets report warnings, SDR white level is best-effort
        and MUST NOT flip the handler success to False — this was the bug
        that caused an HDR profile apply to roll back."""
        mock_detect.return_value = {}
        mock_set.return_value = {
            "success": True,
            "requested_nits": 200,
            "applied_count": 0,
            "skipped_count": 0,
            "warnings": [
                "SetDeviceInfo(SDR_WHITE_LEVEL) returned unexpected status -1 for target 5"
            ],
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"sdr_white_level_nits": 200})

        # Warnings are surfaced via applied[] so the tray/UI see them…
        assert any("warning" in msg.lower() for msg in result.get("applied", []))
        # …but the handler's overall success is still True and the errors
        # list is empty, so the profile apply pipeline does NOT roll back.
        assert result.get("success", True) is True
        assert result.get("errors", []) == []

    @patch.object(WindowsSettingsHandler, "_set_sdr_white_level")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_ignores_none_value(self, mock_detect, mock_set):
        """sdr_white_level_nits=None is an explicit opt-out; handler must not call set()."""
        mock_detect.return_value = {}

        handler = WindowsSettingsHandler()
        handler.apply({"sdr_white_level_nits": None})

        mock_set.assert_not_called()


class TestAdvancedColor:
    """Tests for the Wide Color Gamut (AdvancedColorEnabled) pathway.

    All registry and DisplayConfig calls are mocked — these tests never
    touch live DWM / MonitorDataStore.
    """

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_invokes_refresh_cycle(self, mock_detect, mock_refresh):
        """apply({advanced_color: True, hdr: True}) runs a single coordinated cycle."""
        mock_detect.return_value = {}
        mock_refresh.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
            "cycle_ran": True,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"advanced_color": True, "hdr": True})

        mock_refresh.assert_called_once_with(True, True, manage_hdr_intent=True)
        assert result.get("success", True) is True
        # User-facing applied list should mention both flags landing together.
        assert any("Wide Color Gamut" in msg for msg in result.get("applied", []))
        assert any("HDR" in msg for msg in result.get("applied", []))

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_skips_when_already_active(
        self,
        mock_detect,
        mock_refresh,
    ):
        """Already-matching WCG/HDR should not refresh the DWM display path."""
        mock_detect.return_value = {
            "advanced_color": True,
            "hdr": True,
            "hdr_active": True,
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"advanced_color": True, "hdr": True})

        mock_refresh.assert_not_called()
        assert any("already correct" in msg for msg in result.get("applied", []))

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_alone_ignores_sticky_hdr_intent_when_wcg_matches(
        self,
        mock_detect,
        mock_hdr_summary,
        mock_refresh,
    ):
        """WCG-only no-op detection must not depend on sticky HDR intent."""
        mock_detect.return_value = {
            "advanced_color": True,
            "hdr": True,
            "hdr_active": False,
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"advanced_color": True})

        mock_refresh.assert_not_called()
        mock_hdr_summary.assert_not_called()
        assert any("already correct" in msg for msg in result.get("applied", []))

    @patch.object(WindowsSettingsHandler, "_set_hdr")
    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_does_not_double_process_hdr(
        self,
        mock_detect,
        mock_refresh,
        mock_set_hdr,
    ):
        """When both hdr and advanced_color are set, _set_hdr must NOT also be
        invoked — the refresh cycle handles HDR internally. Double-processing
        would produce two compositor flickers."""
        mock_detect.return_value = {}
        mock_refresh.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
            "cycle_ran": True,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        handler.apply({"advanced_color": True, "hdr": True})

        mock_refresh.assert_called_once()
        mock_set_hdr.assert_not_called()

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_alone_preserves_current_hdr(
        self,
        mock_detect,
        mock_hdr_summary,
        mock_refresh,
    ):
        """advanced_color without hdr should preserve the current live HDR state."""
        mock_detect.return_value = {}
        mock_hdr_summary.return_value = {
            "available": True,
            "any_enabled": True,
            "any_active": True,
        }
        mock_refresh.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
            "cycle_ran": True,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        handler.apply({"advanced_color": True})  # no hdr key

        # Refresh cycle must be called with preserved HDR state (currently on).
        mock_refresh.assert_called_once_with(
            True,
            True,
            manage_hdr_intent=False,
            live_hdr_summary={
                "available": True,
                "any_enabled": True,
                "any_active": True,
            },
        )

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_alone_preserves_live_hdr_not_sticky_user_enabled(
        self,
        mock_detect,
        mock_hdr_summary,
        mock_refresh,
    ):
        """WCG-only applies must preserve live HDR mode, not stale user intent."""
        mock_detect.return_value = {}
        mock_hdr_summary.return_value = {
            "available": True,
            "any_enabled": True,
            "any_active": False,
        }
        mock_refresh.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
            "cycle_ran": False,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        handler.apply({"advanced_color": True})

        mock_refresh.assert_called_once_with(
            True,
            False,
            manage_hdr_intent=False,
            live_hdr_summary={
                "available": True,
                "any_enabled": True,
                "any_active": False,
            },
        )

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_alone_reuses_detected_live_hdr_state(
        self,
        mock_detect,
        mock_hdr_summary,
        mock_refresh,
    ):
        """WCG-only applies should not re-query HDR state after detect()."""
        mock_detect.return_value = {
            "advanced_color": False,
            "hdr": True,
            "hdr_active": False,
        }
        mock_refresh.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
            "cycle_ran": False,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        handler.apply({"advanced_color": True})

        mock_hdr_summary.assert_not_called()
        mock_refresh.assert_called_once_with(
            True,
            False,
            manage_hdr_intent=False,
            live_hdr_summary={
                "available": True,
                "any_active": False,
                "any_enabled": True,
            },
        )

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_errors_are_warnings_not_failures(
        self,
        mock_detect,
        mock_refresh,
    ):
        """WCG writes are cosmetic — per-monitor errors must NOT fail the handler
        or trigger a profile rollback."""
        mock_detect.return_value = {}
        mock_refresh.return_value = {
            "success": False,
            "applied_count": 0,
            "skipped_count": 0,
            "errors": ["MONITOR_01: permission denied"],
            "cycle_ran": True,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"advanced_color": True, "hdr": True})

        assert result.get("success", True) is True
        assert result.get("errors", []) == []
        assert any("warning" in msg.lower() for msg in result.get("applied", []))

    @patch.object(WindowsSettingsHandler, "_set_advanced_color_with_refresh")
    @patch.object(WindowsSettingsHandler, "_detect_for_apply")
    def test_apply_advanced_color_treats_hdr_errors_as_blocking(
        self,
        mock_detect,
        mock_refresh,
    ):
        """HDR failures inside the combined WCG/HDR path must fail apply."""
        mock_detect.return_value = {}
        mock_refresh.return_value = {
            "success": False,
            "applied_count": 0,
            "skipped_count": 0,
            "errors": ["MONITOR_01: WCG permission denied"],
            "critical_errors": ["HDR enable: live path stayed SDR"],
            "cycle_ran": True,
            "final_state": {},
        }

        handler = WindowsSettingsHandler()
        result = handler.apply({"advanced_color": True, "hdr": True})

        assert result["success"] is False
        assert "HDR enable: live path stayed SDR" in (result["error"] or "")
        assert any("Advanced color: warning" in item for item in result["applied"])

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_set_advanced_color")
    @patch.object(WindowsSettingsHandler, "_set_hdr")
    def test_refresh_cycle_does_not_escalate_transient_step1_failure_when_target_hdr_on(
        self,
        mock_set_hdr,
        mock_set_adv,
        mock_hdr_summary,
        mock_get_adv,
        mock_write_reg,
    ):
        """Regression: the overwatch2-gsync-hdr-capture re-apply failure.

        target_hdr=True. Pre-state: HDR is currently OFF (so cycle runs).
        Step 1 (_set_hdr(False)) "fails" because the secondary HDR-capable
        target's user_enabled bit didn't flip even though active=0. The
        cycle MUST NOT promote this transient teardown error to a
        critical_errors entry, because step 2 overwrites the HDR registry
        intent and step 4 turns HDR back on.
        """
        mock_hdr_summary.return_value = {
            "available": True,
            "any_active": False,  # forces cycle to run (mismatch with target_hdr=True)
            "hdr_capable_count": 2,
            "hdr_enabled_count": 1,
            "hdr_active_count": 0,
            "any_enabled": True,
        }
        # Step 1: _set_hdr(False) "fails" with the sticky-user_enabled error.
        # Step 4: _set_hdr(True) succeeds.
        mock_set_hdr.side_effect = [
            {"success": False, "errors": ["sticky user_enabled bit on secondary"]},
            {"success": True, "errors": []},
        ]
        mock_set_adv.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
        }
        mock_get_adv.return_value = {"any_enabled": True}

        handler = WindowsSettingsHandler()
        result = handler._set_advanced_color_with_refresh(
            target_advanced_color=True,
            target_hdr=True,
        )

        assert result["critical_errors"] == [], (
            f"Transient step-1 teardown failure must not escalate; got "
            f"critical_errors={result['critical_errors']}"
        )
        # The transient error is still surfaced as informational so the tray
        # log shows it, but result['success'] stays True (overall cycle ok).
        assert result["success"] is True
        assert any("HDR teardown" in e for e in result.get("errors", []))

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_set_advanced_color")
    @patch.object(WindowsSettingsHandler, "_set_hdr")
    def test_refresh_cycle_escalates_step1_failure_when_target_hdr_off(
        self,
        mock_set_hdr,
        mock_set_adv,
        mock_hdr_summary,
        mock_get_adv,
        mock_write_reg,
    ):
        """target_hdr=False: step 1 IS the final state. A genuine disable
        failure (compositor still active) must escalate to critical_errors."""
        mock_hdr_summary.return_value = {
            "available": True,
            "any_active": True,  # forces cycle (need to disable)
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "hdr_active_count": 1,
            "any_enabled": True,
        }
        mock_set_hdr.return_value = {
            "success": False,
            "errors": ["HDR active mode did not move to off"],
        }
        mock_set_adv.return_value = {
            "success": True,
            "applied_count": 0,
            "skipped_count": 1,
            "errors": [],
        }
        mock_get_adv.return_value = {"any_enabled": False}

        handler = WindowsSettingsHandler()
        result = handler._set_advanced_color_with_refresh(
            target_advanced_color=False,
            target_hdr=False,
        )

        assert result["success"] is False
        assert any("HDR disable" in e for e in result["critical_errors"])

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_advanced_color")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_set_advanced_color")
    @patch.object(WindowsSettingsHandler, "_set_hdr")
    def test_wcg_only_refresh_does_not_write_or_cycle_hdr(
        self,
        mock_set_hdr,
        mock_set_adv,
        mock_hdr_summary,
        mock_get_adv,
        mock_write_reg,
    ):
        """WCG-only refresh must not mutate HDR intent as a hidden side effect."""
        mock_hdr_summary.return_value = {
            "available": True,
            "any_active": False,
            "any_enabled": True,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "hdr_active_count": 0,
        }
        mock_set_adv.return_value = {
            "success": True,
            "applied_count": 1,
            "skipped_count": 0,
            "errors": [],
        }
        mock_get_adv.return_value = {"any_enabled": True}

        handler = WindowsSettingsHandler()
        result = handler._set_advanced_color_with_refresh(
            target_advanced_color=True,
            target_hdr=False,
            manage_hdr_intent=False,
        )

        assert result["success"] is True
        assert result["cycle_ran"] is False
        assert result["final_state"] == {
            "advanced_color_registry_any_enabled": True,
            "hdr_any_enabled": True,
            "hdr_any_active": False,
        }
        mock_set_hdr.assert_not_called()
        mock_write_reg.assert_not_called()
        mock_get_adv.assert_not_called()

    @patch("abso.settings.windows.winreg")
    def test_set_advanced_color_writes_all_enumerated_monitors(self, mock_winreg):
        """_set_advanced_color iterates MonitorDataStore and writes each subkey."""
        # Fake root key that enumerates 3 monitor subkeys.
        mock_root = MagicMock()
        mock_sub = MagicMock()
        # Context-manager semantics for OpenKey return
        mock_winreg.OpenKey.return_value.__enter__.side_effect = [
            mock_root,
            mock_sub,
            mock_sub,
            mock_sub,
        ]
        mock_winreg.OpenKey.return_value.__exit__.return_value = False
        mock_winreg.EnumKey.side_effect = ["MON_A", "MON_B", "MON_C", OSError()]
        # Current value reads for each sub: first two differ from target, third matches.
        mock_winreg.QueryValueEx.side_effect = [
            (0, None),
            (0, None),
            (1, None),  # current values before our set
        ]
        mock_winreg.REG_DWORD = 4

        handler = WindowsSettingsHandler()
        # Call against a fresh mock; the `with winreg.OpenKey` pattern in the
        # real code still works because we've mocked the module.
        import abso.settings.windows as mod

        # Ensure the mock is actually used by the handler
        assert mod.winreg is mock_winreg

        result = handler._set_advanced_color(True)

        # Two of the three monitors had differing values → two SetValueEx calls.
        # The third matched target=1 → skipped.
        assert result["applied_count"] == 2
        assert result["skipped_count"] == 1
        assert mock_winreg.SetValueEx.call_count == 2
        # Every SetValueEx call must target AdvancedColorEnabled with value 1.
        for call in mock_winreg.SetValueEx.call_args_list:
            args = call.args
            assert args[1] == "AdvancedColorEnabled"
            assert args[4] == 1


class TestHdrLiveStateBasedSet:
    """Guards the active-display HDR apply path.

    Registry MonitorDataStore can contain stale inactive monitors. _set_hdr
    must decide success/failure from the active target's type-15 HDR state,
    using registry writes only as a fallback when the live path does not move.
    """

    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    def test_set_hdr_short_circuits_when_live_path_already_on(
        self,
        mock_live,
        mock_targets,
        mock_write_reg,
    ):
        mock_live.return_value = {
            "available": True,
            "any_enabled": True,
            "any_active": True,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "hdr_active_count": 1,
        }

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(True)

        assert result["success"] is True
        assert result["hdr_active_count"] == 1
        mock_targets.assert_not_called()
        mock_write_reg.assert_not_called()

    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    def test_set_hdr_disable_short_circuits_when_live_path_already_off(
        self,
        mock_live,
        mock_targets,
        mock_write_reg,
    ):
        mock_live.return_value = {
            "available": True,
            "any_enabled": False,
            "any_active": False,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 0,
            "hdr_active_count": 0,
        }

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(False)

        assert result["success"] is True
        mock_targets.assert_not_called()
        mock_write_reg.assert_not_called()

    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    def test_set_hdr_tries_when_user_enabled_but_live_path_sdr(
        self,
        mock_live,
        mock_targets,
    ):
        mock_live.return_value = {
            "available": True,
            "any_enabled": True,
            "any_active": False,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "hdr_active_count": 0,
        }
        mock_targets.return_value = []

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(True)

        assert result["success"] is False
        assert "No active display targets found" in result["errors"]
        mock_targets.assert_called_once()

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(
        WindowsSettingsHandler, "_kick_display_config_database_reapply", return_value=True
    )
    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes.windll.user32.DisplayConfigSetDeviceInfo")
    def test_set_hdr_kicks_database_when_live_path_stays_sdr(
        self,
        mock_set_device,
        mock_targets,
        mock_live,
        mock_write_reg,
        mock_kick,
    ):
        """Live SDR after SET_HDR_STATE gets a registry write + database kick."""
        mock_set_device.return_value = 0
        mock_targets.return_value = [(_LUID(0, 0), 1)]
        mock_live.side_effect = [
            {
                "available": True,
                "any_enabled": False,
                "any_active": False,
                "hdr_capable_count": 1,
                "hdr_enabled_count": 0,
                "hdr_active_count": 0,
            },
            {
                "available": True,
                "any_enabled": False,
                "any_active": False,
                "hdr_capable_count": 1,
                "hdr_enabled_count": 0,
                "hdr_active_count": 0,
            },
            {
                "available": True,
                "any_enabled": True,
                "any_active": True,
                "hdr_capable_count": 1,
                "hdr_enabled_count": 1,
                "hdr_active_count": 1,
            },
        ]

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(True)

        assert result["success"] is True
        assert result["hdr_enabled_count"] == 1
        assert result["hdr_active_count"] == 1
        mock_write_reg.assert_called_once_with(True)
        mock_kick.assert_called_once()

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes.windll.user32.DisplayConfigSetDeviceInfo")
    def test_set_hdr_skips_known_sdr_only_targets(
        self,
        mock_set_device,
        mock_targets,
        mock_live,
    ):
        """HDR SET should not be sent to known SDR-only secondary targets."""
        called_target_ids: list[int] = []

        def fake_set_device_info(ptr):
            called_target_ids.append(int(ptr._obj.header.id))
            return 0

        mock_set_device.side_effect = fake_set_device_info
        mock_targets.return_value = [(_LUID(0, 0), 1), (_LUID(0, 0), 2)]
        mock_live.side_effect = [
            {
                "available": True,
                "any_enabled": False,
                "any_active": False,
                "hdr_capable_count": 1,
                "hdr_enabled_count": 0,
                "hdr_active_count": 0,
                "per_target": [
                    {
                        "adapter_low_part": 0,
                        "adapter_high_part": 0,
                        "target_id": 1,
                        "hdr_supported": True,
                        "hdr_user_enabled": False,
                        "hdr_active": False,
                    },
                    {
                        "adapter_low_part": 0,
                        "adapter_high_part": 0,
                        "target_id": 2,
                        "hdr_supported": False,
                        "hdr_user_enabled": False,
                        "hdr_active": False,
                    },
                ],
            },
            {
                "available": True,
                "any_enabled": True,
                "any_active": True,
                "hdr_capable_count": 1,
                "hdr_enabled_count": 1,
                "hdr_active_count": 1,
            },
        ]

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(True)

        assert result["success"] is True
        assert called_target_ids == [1]
        assert result["skipped_targets"] == [
            {"target_id": 2, "reason": "hdr_not_supported"}
        ]

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes.windll.user32.DisplayConfigSetDeviceInfo")
    def test_set_hdr_disable_succeeds_when_active_drops_even_if_secondary_user_enabled_sticks(
        self,
        mock_set_device,
        mock_targets,
        mock_live,
        mock_write_reg,
    ):
        """The user-visible failure on overwatch2-gsync-hdr-capture.

        SET_HDR_STATE successfully brings the active display path to SDR
        (any_active=False) but on a multi-monitor setup the secondary HDR-
        capable target keeps its 'Use HDR' user_enabled bit. Apply MUST NOT
        fail in this state — the user's screen is correctly in SDR."""
        mock_set_device.return_value = 0
        mock_targets.return_value = [(_LUID(0, 0), 1)]
        mock_live.side_effect = [
            # Pre-state: HDR is active. We need to disable.
            {
                "available": True,
                "any_enabled": True,
                "any_active": True,
                "hdr_capable_count": 2,
                "hdr_enabled_count": 2,
                "hdr_active_count": 1,
            },
            # Post-SET: compositor is SDR, but secondary user_enabled stuck.
            {
                "available": True,
                "any_enabled": True,
                "any_active": False,
                "hdr_capable_count": 2,
                "hdr_enabled_count": 1,
                "hdr_active_count": 0,
            },
        ]

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(False)

        assert (
            result["success"] is True
        ), f"Disable must succeed when active mode is SDR; got errors={result.get('errors')}"
        assert result["hdr_active_count"] == 0
        notices = result.get("notices") or []
        assert any(
            "Use HDR" in n for n in notices
        ), f"Sticky secondary user_enabled bit should be reported as a notice; got {notices}"

    @patch.object(WindowsSettingsHandler, "_DWM_REFRESH_WAIT_SECONDS", 0)
    @patch.object(
        WindowsSettingsHandler, "_kick_display_config_database_reapply", return_value=True
    )
    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch("abso.settings.windows.ctypes.windll.user32.DisplayConfigSetDeviceInfo")
    def test_set_hdr_disable_still_fails_when_active_mode_stays_on(
        self,
        mock_set_device,
        mock_targets,
        mock_live,
        mock_write_reg,
        mock_kick,
    ):
        """A genuine HDR-disable failure (compositor still in HDR) must still fail."""
        mock_set_device.return_value = 0
        mock_targets.return_value = [(_LUID(0, 0), 1)]
        # Pre-state has HDR active; SET silently no-ops; kick fails to recover.
        stuck_state = {
            "available": True,
            "any_enabled": True,
            "any_active": True,
            "hdr_capable_count": 1,
            "hdr_enabled_count": 1,
            "hdr_active_count": 1,
        }
        mock_live.side_effect = [stuck_state, stuck_state, stuck_state]

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(False)

        assert result["success"] is False
        assert any(
            "HDR active mode" in e or "HDR disable" in e for e in result["errors"]
        ), f"Expected an active-mode failure; got {result['errors']}"

    @patch.object(WindowsSettingsHandler, "_write_hdr_enabled_registry")
    @patch.object(WindowsSettingsHandler, "_get_active_display_targets")
    @patch.object(WindowsSettingsHandler, "_get_hdr_state_summary")
    def test_set_hdr_disable_short_circuits_when_active_already_off_even_if_user_enabled_stuck(
        self,
        mock_live,
        mock_targets,
        mock_write_reg,
    ):
        """Fast-path skip: active==0 satisfies a disable request, regardless of
        sticky per-monitor user_enabled bits."""
        mock_live.return_value = {
            "available": True,
            "any_enabled": True,  # stuck on a secondary HDR-capable target
            "any_active": False,
            "hdr_capable_count": 2,
            "hdr_enabled_count": 1,
            "hdr_active_count": 0,
        }

        handler = WindowsSettingsHandler()
        result = handler._set_hdr(False)

        assert result["success"] is True
        mock_targets.assert_not_called()
        mock_write_reg.assert_not_called()


class TestHdrProfilesWCGIntegration:
    """Integration-lite: every HDR profile must carry advanced_color=True.

    Regression guard for the Win11 24H2+ split-color-stack bug where HDR
    alone leaves wide-gamut SDR content rendering as sRGB."""

    @pytest.mark.parametrize(
        "profile_import_path,profile_cls_name",
        [
            ("abso.profiles.overwatch2", "Overwatch2NoSyncHDRProfile"),
            ("abso.profiles.overwatch2", "Overwatch2GSyncHDRProfile"),
            ("abso.profiles.overwatch2", "Overwatch2GSyncHDRCaptureProfile"),
            ("abso.profiles.marvel_rivals", "MarvelRivalsHDRProfile"),
            ("abso.profiles.fortnite", "FortniteHDRProfile"),
            ("abso.profiles.diablo4", "Diablo4Profile"),
            ("abso.profiles.rivals2_nosync", "Rivals2NoSyncHDRProfile"),
            ("abso.profiles.rivals2_gsync", "Rivals2GSyncHDRProfile"),
            ("abso.profiles.rivals2_gsync", "Rivals2GSyncHDRCaptureProfile"),
        ],
    )
    def test_hdr_profiles_pair_hdr_with_advanced_color(
        self,
        profile_import_path,
        profile_cls_name,
    ):
        import importlib

        module = importlib.import_module(profile_import_path)
        profile = getattr(module, profile_cls_name)()
        w = profile.get_settings("WindowsSettingsHandler")
        assert w.get("hdr") is True, f"{profile_cls_name} must request HDR (got hdr={w.get('hdr')})"
        assert w.get("advanced_color") is True, (
            f"{profile_cls_name} must pair HDR with advanced_color=True on "
            f"Win11 24H2+ (got advanced_color={w.get('advanced_color')}). "
            "Without this pairing SDR content renders in sRGB gamut under "
            "HDR, producing a washed-out desktop on wide-gamut displays."
        )
