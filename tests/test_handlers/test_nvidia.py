"""Tests for NvidiaSettingsHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.nvidia.nvapi_drs import DRSProfileManager as RealDRSProfileManager
from abso.settings.nvidia.parsing import (
    parse_low_latency_value,
)
from abso.settings.nvidia.profiles import get_setting_value


class TestNvidiaParsing:
    """Tests for NIP file parsing functions."""

    def test_parse_low_latency_value_off(self):
        """Test parsing low latency 'off' value."""
        assert parse_low_latency_value("0x00000000") == "off"
        assert parse_low_latency_value("0x0") == "off"

    def test_parse_low_latency_value_on(self):
        """Test parsing low latency 'on' value."""
        assert parse_low_latency_value("0x00000001") == "on"
        assert parse_low_latency_value("0x1") == "on"

    def test_parse_low_latency_value_ultra(self):
        """Test parsing low latency 'ultra' value."""
        assert parse_low_latency_value("0x00000002") == "ultra"
        assert parse_low_latency_value("0x2") == "ultra"

    def test_parse_low_latency_value_unknown(self):
        """Test parsing unknown low latency value."""
        assert parse_low_latency_value("0x99999999") == "unknown"
        assert parse_low_latency_value("invalid") == "unknown"


class TestNvidiaProfiles:
    """Tests for profile generation functions."""

    def test_get_setting_value_low_latency_off(self):
        """Test getting decimal value for low latency 'off'."""
        assert get_setting_value("off", "low_latency") == 0

    def test_get_setting_value_low_latency_on(self):
        """Test getting decimal value for low latency 'on'."""
        assert get_setting_value("on", "low_latency") == 1

    def test_get_setting_value_low_latency_ultra(self):
        """Test getting decimal value for low latency 'ultra'."""
        assert get_setting_value("ultra", "low_latency") == 2

    def test_get_setting_value_low_latency_invalid(self):
        """Test getting decimal value for invalid input defaults to 0."""
        assert get_setting_value("invalid", "low_latency") == 0

    def test_get_setting_value_power_management(self):
        """Test getting decimal values for power management settings."""
        assert get_setting_value("adaptive", "power") == 0
        assert get_setting_value("prefer_max_performance", "power") == 1
        assert get_setting_value("optimal", "power") == 2

    def test_get_setting_value_vsync(self):
        """Test getting decimal values for vsync settings."""
        assert get_setting_value("off", "vsync") == 0
        assert get_setting_value("on", "vsync") == 1
        assert get_setting_value("adaptive", "vsync") == 2

    def test_get_setting_value_shader_cache(self):
        """Test getting decimal values for shader cache settings."""
        assert get_setting_value("off", "shader_cache") == 0
        assert get_setting_value("unlimited", "shader_cache") == 4294967295


class TestNvidiaPresets:
    """Tests for Nvidia preset configurations."""

    def test_presets_exist(self):
        """Test that all expected presets exist."""
        from abso.settings.nvidia import NVIDIA_PRESETS

        assert "minimum_latency" in NVIDIA_PRESETS
        assert "low_latency_high_fps" in NVIDIA_PRESETS
        assert "balanced" in NVIDIA_PRESETS

    def test_preset_minimum_latency_settings(self):
        """Test minimum_latency preset has expected settings."""
        from abso.settings.nvidia import NVIDIA_PRESETS

        preset = NVIDIA_PRESETS["minimum_latency"]
        settings = preset.get("settings", {})
        assert settings.get("low_latency_mode") == "ultra"
        assert settings.get("vsync") == "off"
        assert settings.get("power_management") == "prefer_max_performance"

    def test_preset_balanced_settings(self):
        """Test balanced preset has expected settings."""
        from abso.settings.nvidia import NVIDIA_PRESETS

        preset = NVIDIA_PRESETS["balanced"]
        settings = preset.get("settings", {})
        assert settings.get("low_latency_mode") == "on"
        # balanced typically uses adaptive vsync
        assert "vsync" in settings


class TestNvidiaDetect:
    """Tests for detect() method."""

    def test_detect_returns_expected_keys(self):
        """Test detect returns dict with expected keys."""
        handler = NvidiaSettingsHandler()

        with (patch.object(handler, "_detect_gpu_info", return_value={"gpu_name": None}),
              patch.object(handler, "_check_npi_available", return_value=False)):
            result = handler.detect()

        assert "driver_version" in result
        assert "gpu_name" in result
        assert "npi_available" in result
        # Note: current_settings removed - NPI doesn't support headless export

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_parses_nvidia_smi(self, mock_run):
        """Test _detect_gpu_info parses nvidia-smi output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4090, 536.23, 24564\n"
        )

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") == "NVIDIA GeForce RTX 4090"
        assert result.get("driver_version") == "536.23"
        assert result.get("vram_total_mb") == 24564

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_missing_nvidia_smi(self, mock_run):
        """Test _detect_gpu_info handles missing nvidia-smi."""
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None
        assert result.get("driver_version") is None

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_timeout(self, mock_run):
        """Test _detect_gpu_info handles timeout."""
        import subprocess
        mock_run.side_effect = subprocess.TimeoutExpired("cmd", 5)

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None

    @patch("abso.settings.nvidia.subprocess.run")
    def test_detect_gpu_info_handles_empty_output(self, mock_run):
        """Test _detect_gpu_info handles empty output."""
        mock_run.return_value = MagicMock(returncode=0, stdout="")

        handler = NvidiaSettingsHandler()
        result = handler._detect_gpu_info()

        assert result.get("gpu_name") is None


class TestNvidiaAudit:
    """Tests for audit() method."""

    def test_audit_returns_npi_not_found_issue(self):
        """Test audit returns issue when NPI not available."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={"npi_available": False}):
            issues = handler.audit()

        npi_issues = [i for i in issues if "Profile Inspector not found" in i.title]
        assert len(npi_issues) == 1

    def test_audit_npi_available_no_issues(self):
        """Test audit returns no issues when NPI is available.

        Note: Nvidia audit cannot check current settings because NPI doesn't
        support headless export (opens GUI). When NPI is available, we return
        no issues - users should apply a profile to ensure optimal settings.
        """
        handler = NvidiaSettingsHandler()

        with patch.object(handler, "detect", return_value={"npi_available": True}):
            issues = handler.audit()

        # No issues returned when NPI is available (can't read settings headlessly)
        assert len(issues) == 0

    def test_audit_no_detailed_checks_without_headless_support(self):
        """Test that audit doesn't check individual settings.

        NPI doesn't support headless export, so we can't read current 3D settings.
        The audit only checks NPI availability and provides general guidance.
        """
        handler = NvidiaSettingsHandler()

        # Even with suboptimal "current_settings" mocked, no issues are created
        # because the code that checks them is disabled (unreachable)
        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {
                "power_management": "adaptive",
                "low_latency_mode": "off",
                "vsync": "on",
                "shader_cache": "1024MB",
            }
        }):
            issues = handler.audit()

        # All detailed checks are disabled - only NPI availability is checked
        assert len(issues) == 0

    def test_audit_no_issues_when_optimal(self):
        """Test audit returns no issues when settings are optimal."""
        handler = NvidiaSettingsHandler()

        # VRR-optimal settings: VSync ON is correct with G-SYNC (acts as safety net)
        # See: abso/core/vrr.py for VRR knowledge base
        with patch.object(handler, "detect", return_value={
            "npi_available": True,
            "current_settings": {
                "power_management": "prefer_max_performance",
                "low_latency_mode": "on",  # "on" not "ultra" - ultra overrides FPS caps
                "vsync": "on",  # VRR safety net - doesn't add latency with proper FPS cap
                "shader_cache": "unlimited"
            }
        }):
            issues = handler.audit()

        # VSync "on" still produces an info issue (reminder about FPS cap)
        # but no warnings/criticals - that's the expected optimal state
        warnings_or_higher = [i for i in issues if i.severity in ("warning", "critical")]
        assert len(warnings_or_higher) == 0


class TestNvidiaApply:
    """Tests for apply() method.

    Note: NPI import is DISABLED because it wipes all existing profiles.
    Apply now logs settings for manual application instead.
    """

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_logs_preset_settings(self, mock_manager_cls):
        """Test apply logs preset settings for manual application."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {
                "low_latency_mode": "ultra",
                "power_management": "prefer_max_performance",
                "vsync": "off",
            },
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {}
        mock_manager._resolve_setting.return_value = None
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()

        result = handler.apply({
            "preset": "minimum_latency",
            "executables": ["Game.exe"],
            "game_name": "Test Game",
        })

        assert result["success"] is True
        # With NVAPI integration, settings are applied directly
        # The result should contain the profile name or settings applied
        assert len(result["applied"]) > 0
        assert any("Test Game" in line or "low_latency_mode" in line for line in result["applied"])

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_logs_individual_settings(self, mock_manager_cls):
        """Test apply individual settings via NVAPI."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {
                "low_latency_mode": "ultra",
                "vsync": "off",
            },
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {}
        mock_manager._resolve_setting.return_value = None
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()

        result = handler.apply({
            "low_latency_mode": "ultra",
            "vsync": "off",
            "executables": ["Game.exe"],
            "game_name": "Test Game",
        })

        assert result["success"] is True
        # With NVAPI integration, settings are applied and reported
        # The format is now "setting_name: value" instead of "Setting Name: value"
        assert any("low_latency_mode" in line.lower() for line in result["applied"])
        assert any("ultra" in line.lower() for line in result["applied"])

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_without_global_settings_does_not_touch_base_profile(self, mock_manager_cls):
        """Per-app-only applies should not mutate the global NVIDIA profile."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vsync": "off"},
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {}
        mock_manager._resolve_setting.return_value = None
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "vsync": "off",
            "executables": ["Game.exe"],
            "game_name": "Test Game",
        })

        assert result["success"] is True
        mock_manager.apply_settings_to_global.assert_not_called()

    def test_apply_without_settings_succeeds(self):
        """Test apply with no NVIDIA settings succeeds."""
        handler = NvidiaSettingsHandler()

        result = handler.apply({
            "executables": ["Game.exe"],
            "game_name": "Test Game",
        })

        assert result["success"] is True

    def test_apply_unknown_preset_still_succeeds(self):
        """Test apply with unknown preset succeeds (logs nothing)."""
        handler = NvidiaSettingsHandler()

        result = handler.apply({
            "preset": "nonexistent_preset",
            "executables": ["Game.exe"],
        })

        # Unknown preset means no settings to log, but still succeeds
        assert result["success"] is True

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_global_vrr_mode_calls_global_profile_path(self, mock_manager_cls):
        """global_vrr_mode should be applied to the base profile path."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_global.return_value = {
            "profile_name": "Base Profile",
            "settings_applied": {"vrr_mode": "off"},
            "errors": [],
        }
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vsync": "off"},
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {}
        mock_manager._resolve_setting.return_value = (0x00A879CF, 0x08416747)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "reflex_no_sync",
            "global_vrr_mode": "off",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2 - No-Sync",
        })

        mock_manager.apply_settings_to_global.assert_called_once_with({"vrr_mode": "off", "max_frame_rate": "off"})
        assert result["success"] is True
        assert any("NVIDIA global profile configured:" in line for line in result["applied"])

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_auto_vrr_fps_cap_overrides_preset(self, mock_manager_cls):
        """auto_vrr_fps_cap sets max_frame_rate using the refresh-scaled formula.

        At 280Hz the new (2026-05) value is 0.97 * 280 = 272 (was refresh - 3 = 277).
        See abso/core/vrr.py.
        """
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {
                "max_frame_rate": 272,
                "vsync": "on",
                "vrr_app_override": "allow",
            },
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {}
        mock_manager._resolve_setting.return_value = (0x10835002, 272)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        with patch.object(handler, "_detect_primary_refresh_rate", return_value=280):
            result = handler.apply({
                "preset": "reflex_gsync",
                "auto_vrr_fps_cap": True,
                "executables": ["Overwatch.exe"],
                "game_name": "Overwatch 2 - GSYNC",
                "profile_name": "Overwatch 2",
            })

        args, kwargs = mock_manager.apply_settings_to_app.call_args
        sent_settings = args[1]
        assert sent_settings["max_frame_rate"] == 272
        assert result["success"] is True
        assert any("Auto VRR FPS cap: 272 (from 280 Hz)" in line for line in result["applied"])

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_verification_uses_explicit_profile_name(self, mock_manager_cls):
        """Verification should read back from explicit profile name when provided."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vsync": "on"},
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {"vsync_mode": 0x47814940}
        mock_manager._resolve_setting.return_value = (0x00A879CF, 0x47814940)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        handler.apply({
            "preset": "reflex_gsync",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2 - GSYNC",
            "profile_name": "Overwatch 2",
        })

        mock_manager.get_app_settings.assert_called_once_with(
            "Overwatch.exe",
            profile_name="Overwatch 2",
        )

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_verification_uses_alias_readback_for_vsync_and_frame_cap(self, mock_manager_cls):
        """Verification should understand driver readback aliases like vsync_mode and frame_rate_limiter_v3."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vsync": "on", "max_frame_rate": 277},
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {
            "vsync_mode": 0x47814940,
            "frame_rate_limiter_v3": 277,
        }

        def resolve_side_effect(name, value):
            mapping = {
                ("vsync", "on"): (0x00A879CF, 0x47814940),
                ("max_frame_rate", 277): (0x10835002, 277),
            }
            return mapping[(name, value)]

        mock_manager._resolve_setting.side_effect = resolve_side_effect
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "vsync": "on",
            "max_frame_rate": 277,
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2 - GSYNC",
            "profile_name": "Overwatch 2",
        })

        assert result["success"] is True
        assert result["verification_failures"] is None

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_global_vrr_mode_readback_mismatch_fails(self, mock_manager_cls):
        """Global G-SYNC mode should fail the apply if driver readback does not match."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_global.return_value = {
            "profile_name": "Base Profile",
            "settings_applied": {"vrr_mode": "fullscreen_only", "max_frame_rate": "off"},
            "errors": [],
        }
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vrr_app_override": "allow"},
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.side_effect = [
            {"vrr_mode": 0x00000000, "frame_rate_limiter_v3": 0},
            {"vrr_app_override": 0x00000000},
        ]

        def resolve_side_effect(name, value):
            mapping = {
                ("vrr_mode", "fullscreen_only"): (0x1194F158, 0x00000001),
                ("max_frame_rate", "off"): (0x10835002, 0),
                ("vrr_app_override", "allow"): (0x10A879CF, 0x00000000),
            }
            return mapping[(name, value)]

        mock_manager._resolve_setting.side_effect = resolve_side_effect
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "reflex_gsync",
            "global_vrr_mode": "fullscreen_only",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2 - GSYNC",
            "profile_name": "Overwatch 2",
        })

        assert result["success"] is False
        assert "global verification failed" in (result["error"] or "")

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_surfaces_manual_binding_required_as_warning(self, mock_manager_cls):
        """manual_required: settings written, only per-exe binding needs NVCP — warning, not fail."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vrr_app_override": "allow"},
            "errors": [],
            "app_bound": False,
            "app_binding_state": "manual_required",
            "npi_launched": False,
            "app_binding_note": (
                "Profile 'Super Smash Bros. Melee (Slippi)' created with all settings "
                "configured. Automatic app binding unavailable on this driver version. "
                "To activate: NVCP > Manage 3D Settings > Program Settings > "
                "Add 'Slippi Dolphin.exe' > Select 'Super Smash Bros. Melee (Slippi)'"
            ),
        }
        mock_manager.get_app_settings.return_value = {"vrr_app_override": 0x00000000}
        mock_manager._resolve_setting.return_value = (0x10A879CF, 0x00000000)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "minimum_latency",
            "executables": ["Slippi Dolphin.exe"],
            "game_name": "Super Smash Bros. Melee (Slippi)",
            "profile_name": "Super Smash Bros. Melee (Slippi)",
        })

        # Apply must succeed: settings are on the profile, and the user has a
        # clear NVCP action. Triggering critical-compliance rollback over this
        # tears down the rest of the profile switch and leaves the system in a
        # half-restored baseline state.
        assert result["success"] is True
        assert result["app_bound"] is False
        assert any(
            "NVIDIA app binding requires manual action" in w
            for w in result.get("warnings") or []
        )

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_fails_when_exe_is_bound_to_conflicting_profile(self, mock_manager_cls):
        """bound_elsewhere: driver refuses to write settings — must stay a hard failure."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {},
            "errors": [],
            "app_bound": False,
            "app_binding_state": "bound_elsewhere",
            "npi_launched": False,
            "app_binding_note": (
                "'Overwatch.exe' is currently owned by NVIDIA profile 'Custom - OW2', "
                "not 'Overwatch 2'. ABSO will not count this as a successful binding."
            ),
        }
        mock_manager.get_app_settings.return_value = {"vrr_app_override": 0x00000000}
        mock_manager._resolve_setting.return_value = (0x10A879CF, 0x00000000)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "reflex_gsync",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2 - GSYNC",
            "profile_name": "Overwatch 2",
        })

        assert result["success"] is False
        assert "App binding failed" in (result["error"] or "")

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_verifies_against_effective_profile_when_legacy_alias_is_reused(self, mock_manager_cls):
        """Verification must read back from the profile actually updated by NVAPI."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "requested_profile_name": "Rivals 2",
            "profile_name": "Rivals2-Win64-Shipping.exe",
            "profile_selection_note": (
                "Reusing existing bound NVIDIA profile 'Rivals2-Win64-Shipping.exe' "
                "instead of unbound requested profile 'Rivals 2'."
            ),
            "settings_applied": {"vrr_app_override": "allow"},
            "errors": [],
            "app_bound": True,
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {"vrr_app_override": 0x00000000}
        mock_manager._resolve_setting.return_value = (0x10A879CF, 0x00000000)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "vrr_fighting_game",
            "executables": ["Rivals2-Win64-Shipping.exe"],
            "game_name": "Rivals 2: G-SYNC",
            "profile_name": "Rivals 2",
            "profile_aliases": ["Rivals2-Win64-Shipping.exe"],
        })

        assert result["success"] is True
        mock_manager.get_app_settings.assert_called_once_with(
            "Rivals2-Win64-Shipping.exe",
            profile_name="Rivals2-Win64-Shipping.exe",
        )

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_surfaces_unverified_binding_as_warning(self, mock_manager_cls):
        """Successful-but-unverified binding reuse must be exposed as a warning."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vrr_app_override": "allow"},
            "errors": [],
            "app_bound": True,
            "app_binding_exact": False,
            "app_binding_note": (
                "Profile 'Rivals 2 Online' already exists and has bound applications, but "
                "NVAPI could not prove every executable belongs to it."
            ),
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {"vrr_app_override": 0x00000000}
        mock_manager._resolve_setting.return_value = (0x10A879CF, 0x00000000)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "vrr_fighting_game",
            "executables": ["Rivals2-Win64-Shipping.exe"],
            "game_name": "Rivals 2 Online",
            "profile_name": "Rivals 2 Online",
        })

        assert result["success"] is True
        assert result["warnings"] == [
            "Profile 'Rivals 2 Online' already exists and has bound applications, but "
            "NVAPI could not prove every executable belongs to it."
        ]

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_surfaces_confirmed_existing_binding_as_notice(self, mock_manager_cls):
        """Confirmed existing membership should be informational, not a warning."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vrr_app_override": "allow"},
            "errors": [],
            "app_bound": True,
            "app_binding_exact": True,
            "app_binding_note": (
                "'Overwatch.exe' was already associated with NVIDIA profile 'Overwatch 2'."
            ),
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {"vrr_app_override": 0x00000000}
        mock_manager._resolve_setting.return_value = (0x10A879CF, 0x00000000)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "reflex_gsync",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2",
            "profile_name": "Overwatch 2",
        })

        assert result["success"] is True
        assert result["warnings"] == []
        assert result["notices"] == [
            "'Overwatch.exe' was already associated with NVIDIA profile 'Overwatch 2'."
        ]

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_apply_surfaces_safe_predefined_profile_as_notice(self, mock_manager_cls):
        """Trusted predefined NVIDIA profiles should surface as notices, not warnings."""
        mock_manager = MagicMock()
        mock_manager.apply_settings_to_app.return_value = {
            "settings_applied": {"vrr_app_override": "allow"},
            "errors": [],
            "app_bound": True,
            "app_binding_exact": False,
            "app_binding_safe": True,
            "app_binding_note": (
                "NVIDIA predefined profile 'Overwatch 2' already exists and has bound applications. "
                "NVAPI could not enumerate exact ownership for 'Overwatch.exe', but ABSO found no "
                "conflicting owner and updated the predefined profile in place."
            ),
            "npi_launched": False,
        }
        mock_manager.get_app_settings.return_value = {"vrr_app_override": 0x00000000}
        mock_manager._resolve_setting.return_value = (0x10A879CF, 0x00000000)
        mock_manager_cls.return_value = mock_manager

        handler = NvidiaSettingsHandler()
        result = handler.apply({
            "preset": "reflex_gsync",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2",
            "profile_name": "Overwatch 2",
        })

        assert result["success"] is True
        assert result["warnings"] == []
        assert any("NVIDIA predefined profile 'Overwatch 2'" in notice for notice in result["notices"])

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_verify_active_confirms_binding_membership_when_owner_matches(self, mock_manager_cls):
        """verify_active should upgrade scope when it can prove executable ownership."""
        manager = RealDRSProfileManager()
        fake_drs = MagicMock()
        fake_drs.find_profile_by_name.return_value = object()
        fake_drs.find_application_owner.return_value = {"profile_name": "Overwatch 2"}
        fake_drs.get_application_info.return_value = {"app_name": "Overwatch.exe"}

        class _Ctx:
            def __enter__(self_inner):
                return fake_drs

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        manager._drs = _Ctx()
        manager.get_app_settings = MagicMock(
            return_value={"_profile": "Overwatch 2", "vrr_app_override": 0x00000000}
        )
        manager._resolve_setting = MagicMock(return_value=(0x10A879CF, 0x00000000))
        mock_manager_cls.return_value = manager

        handler = NvidiaSettingsHandler()
        verify = handler.verify_active({
            "vrr_app_override": "allow",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2",
            "profile_name": "Overwatch 2",
        })

        assert verify["all_active"] is True
        assert verify["scope"] == "profile_and_binding_readback"
        assert verify["binding_owner_profiles"] == {"Overwatch.exe": "Overwatch 2"}

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager")
    def test_verify_active_reports_binding_mismatch(self, mock_manager_cls):
        """verify_active should fail when the executable is owned by a different profile."""
        manager = RealDRSProfileManager()
        fake_drs = MagicMock()
        fake_drs.find_profile_by_name.return_value = object()
        fake_drs.find_application_owner.return_value = {"profile_name": "Legacy Wrong Profile"}
        fake_drs.get_application_info.return_value = None

        class _Ctx:
            def __enter__(self_inner):
                return fake_drs

            def __exit__(self_inner, exc_type, exc, tb):
                return False

        manager._drs = _Ctx()
        manager.get_app_settings = MagicMock(
            return_value={"_profile": "Overwatch 2", "vrr_app_override": 0x00000000}
        )
        manager._resolve_setting = MagicMock(return_value=(0x10A879CF, 0x00000000))
        mock_manager_cls.return_value = manager

        handler = NvidiaSettingsHandler()
        verify = handler.verify_active({
            "vrr_app_override": "allow",
            "executables": ["Overwatch.exe"],
            "game_name": "Overwatch 2",
            "profile_name": "Overwatch 2",
        })

        assert verify["all_active"] is False
        assert any("Executable binding mismatch" in item for item in verify["setting_failures"])

    @patch("abso.settings.windows.WindowsSettingsHandler._get_refresh_rate_info")
    @patch("abso.core.detector.HardwareDetector.detect_monitors")
    def test_detect_primary_refresh_rate_falls_back_to_windows_handler(
        self,
        mock_detect_monitors,
        mock_refresh_info,
    ):
        """Refresh rate detection should fallback when pywin32 monitor detection is unavailable."""
        mock_detect_monitors.return_value = []
        mock_refresh_info.return_value = {"current": 300, "max": None, "available": []}

        handler = NvidiaSettingsHandler()
        rate = handler._detect_primary_refresh_rate()
        assert rate == 300

    @patch("abso.core.detector.HardwareDetector.detect_monitors")
    def test_detect_primary_refresh_rate_prefers_active_mode_over_capability(
        self,
        mock_detect_monitors,
    ):
        """Use active/current mode refresh for VRR cap calculations."""
        mock_detect_monitors.return_value = [
            {
                "is_primary": True,
                "refresh_rate": 240,
                "max_refresh_rate": 240,
                "max_refresh_capability": 280,
            },
        ]

        handler = NvidiaSettingsHandler()
        rate = handler._detect_primary_refresh_rate()
        assert rate == 240

    @patch("abso.core.detector.HardwareDetector.detect_monitors")
    def test_detect_primary_refresh_rate_uses_capability_when_mode_missing(
        self,
        mock_detect_monitors,
    ):
        """Fallback to capability when no active/max mode refresh is available."""
        mock_detect_monitors.return_value = [
            {
                "is_primary": True,
                "refresh_rate": None,
                "max_refresh_rate": None,
                "max_refresh_capability": 280,
            },
        ]

        handler = NvidiaSettingsHandler()
        rate = handler._detect_primary_refresh_rate()
        assert rate == 280

    @patch("abso.core.detector.HardwareDetector.detect_monitors")
    def test_detect_primary_refresh_rate_prefers_target_gaming_display_over_primary(
        self,
        mock_detect_monitors,
    ):
        """Choose the likely gaming display, not just the Windows primary monitor."""
        mock_detect_monitors.return_value = [
            {
                "name": "Office Display",
                "is_primary": True,
                "refresh_rate": 60,
                "max_refresh_rate": 60,
                "max_refresh_capability": 60,
                "vrr_supported": "possible",
            },
            {
                "name": "LG UltraGear",
                "is_primary": False,
                "refresh_rate": 300,
                "max_refresh_rate": 300,
                "max_refresh_capability": 300,
                "vrr_supported": True,
            },
        ]

        handler = NvidiaSettingsHandler()
        rate = handler._detect_primary_refresh_rate()
        assert rate == 300


class TestNvidiaBackupRestore:
    """Tests for backup() and restore() methods."""

    def test_backup_when_npi_unavailable(self):
        """Test backup is marked incomplete when an NVIDIA GPU is present but NPI is unavailable."""
        handler = NvidiaSettingsHandler()

        with (
            patch.object(handler, "_detect_gpu_info", return_value={"gpu_name": "NVIDIA GeForce RTX 4090"}),
            patch.object(handler._npi, "is_available", return_value=False),
        ):
            result = handler.backup()

        assert result["success"] is False
        assert result["nvidia_present"] is True
        assert result["profile_path"] is None
        assert "cannot be captured safely" in result["note"]

    def test_backup_succeeds_when_no_nvidia_gpu_is_present(self, tmp_path):
        """Test backup reports success when the handler is not applicable on this machine."""
        handler = NvidiaSettingsHandler()
        handler.BACKUP_DIR = tmp_path

        with patch.object(handler, "_detect_gpu_info", return_value={"gpu_name": None}):
            result = handler.backup()

        assert result["success"] is True
        assert result["nvidia_present"] is False
        assert result["profile_path"] is None
        assert "No NVIDIA GPU detected" in result["note"]

    def test_backup_marks_restore_unavailable_when_imports_are_disabled(self):
        """Test backup does not pretend to be restorable when safe imports are disabled."""
        handler = NvidiaSettingsHandler()

        with (
            patch.object(handler, "_detect_gpu_info", return_value={"gpu_name": "NVIDIA GeForce RTX 4090"}),
            patch.object(handler._npi, "is_available", return_value=True),
        ):
            result = handler.backup()

        assert result["success"] is False
        assert result["profile_path"] is None
        assert "cannot be restored safely" in result["note"]

    def test_restore_without_profile_path(self):
        """Test restore with no profile_path returns False."""
        handler = NvidiaSettingsHandler()
        result = handler.restore({})

        assert result is False

    def test_restore_missing_file_returns_false(self, tmp_path):
        """Test restore with missing file returns False."""
        handler = NvidiaSettingsHandler()
        result = handler.restore({"profile_path": str(tmp_path / "nonexistent.nip")})

        assert result is False

    def test_restore_applies_profile(self, tmp_path):
        """Test restore applies backup profile."""
        profile_file = tmp_path / "backup.nip"
        profile_file.write_text("test", encoding="utf-8")

        handler = NvidiaSettingsHandler()

        with (
            patch("abso.settings.nvidia.NPI_IMPORTS_DISABLED", False),
            patch.object(handler._npi, "is_available", return_value=True),
            patch.object(handler._npi, "import_profile"),
        ):
            result = handler.restore({"profile_path": str(profile_file)})

        assert result is True


class TestNvidiaPreflight:
    """Tests for strict NVIDIA preflight behavior."""

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager.probe_profile_binding")
    def test_preflight_blocks_when_exact_binding_cannot_be_confirmed(self, mock_probe):
        mock_probe.return_value = {
            "app_binding_exact": False,
            "app_binding_safe": False,
            "app_binding_note": (
                "Profile 'Rivals 2 Online' already exists and has bound applications, but "
                "NVAPI could not prove every executable belongs to it."
            ),
        }

        handler = NvidiaSettingsHandler()
        result = handler.preflight({
            "preset": "vrr_fighting_game",
            "executables": ["Rivals2-Win64-Shipping.exe"],
            "profile_name": "Rivals 2 Online",
            "require_exact_binding": True,
        })

        assert result["success"] is False
        assert "NVAPI could not prove every executable belongs to it" in result["error"]

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager.probe_profile_binding")
    def test_preflight_allows_safe_predefined_profile_when_no_conflicting_owner_exists(self, mock_probe):
        mock_probe.return_value = {
            "app_binding_exact": False,
            "app_binding_safe": True,
            "app_binding_note": (
                "NVIDIA predefined profile 'Overwatch 2' already exists and has bound applications. "
                "NVAPI could not enumerate exact ownership for every requested executable, but ABSO "
                "found no conflicting owner."
            ),
        }

        handler = NvidiaSettingsHandler()
        result = handler.preflight({
            "preset": "reflex_gsync",
            "executables": ["Overwatch.exe"],
            "profile_name": "Overwatch 2",
            "require_exact_binding": True,
        })

        assert result["success"] is True
        assert any("NVIDIA predefined profile 'Overwatch 2'" in notice for notice in result["notices"])

    @patch("abso.settings.nvidia.nvapi_drs.DRSProfileManager.probe_profile_binding")
    def test_preflight_allows_stable_existing_profile_reuse_when_opted_in(self, mock_probe):
        mock_probe.return_value = {
            "app_binding_exact": False,
            "app_binding_safe": False,
            "app_binding_state": "existing_profile_unverified",
            "app_binding_note": (
                "Profile 'Rivals 2 Online' already exists and has bound applications, but "
                "NVAPI could not prove every executable belongs to it."
            ),
        }

        handler = NvidiaSettingsHandler()
        result = handler.preflight({
            "preset": "vrr_fighting_game",
            "executables": ["Rivals2-Win64-Shipping.exe"],
            "profile_name": "Rivals 2 Online",
            "require_exact_binding": True,
            "allow_unverified_existing_profile_reuse": True,
        })

        assert result["success"] is True
        assert any("Proceeding with stable NVIDIA profile reuse" in notice for notice in result["notices"])


class TestNvidiaBackwardsCompatibility:
    """Tests for backwards compatibility methods."""

    def test_npi_path_property(self):
        """Test NPI_PATH property returns path."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "get_path", return_value=None):
            assert handler.NPI_PATH is None

    def test_check_npi_available(self):
        """Test _check_npi_available returns boolean."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "is_available", return_value=True):
            assert handler._check_npi_available() is True

    def test_get_setting_value_method(self):
        """Test _get_setting_value method works."""
        handler = NvidiaSettingsHandler()
        assert handler._get_setting_value("ultra", "low_latency") == 2

    def test_import_profile_method(self):
        """Test _import_profile method works."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "import_profile") as mock:
            from pathlib import Path
            handler._import_profile(Path("test.nip"))
            mock.assert_called_once()

    def test_export_profile_method(self):
        """Test _export_profile method works."""
        handler = NvidiaSettingsHandler()

        with patch.object(handler._npi, "export_profile") as mock:
            from pathlib import Path
            handler._export_profile(Path("test.nip"))
            mock.assert_called_once()
