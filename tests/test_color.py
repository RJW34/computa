"""Tests for color profile settings handler."""

from __future__ import annotations

import json
from ctypes import c_int
from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.data.monitor_osd import (
    OSDRecommendation,
    get_osd_recommendations,
)
from abso.settings.color import (
    ColorProfileSettingsHandler,
    DVCRange,
    _extract_model_key,
    _internal_to_user,
    _user_to_internal,
)

# =============================================================================
# Unit Tests: Vibrance Conversion
# =============================================================================


class TestVibranceConversion:
    """Test user ↔ internal vibrance level conversion.

    Conversions use the actual hardware range (DVCRange) queried from NVAPI.
    We test with two representative hardware ranges to ensure correctness
    regardless of what the GPU+display reports.
    """

    # Symmetric range (e.g. some older drivers): -1024..0..+1024
    SYM = DVCRange(min_level=-1024, max_level=1024, default_level=0, current_level=0)

    # Asymmetric range (e.g. RTX 4070 + modern drivers): 0..50..100
    ASYM = DVCRange(min_level=0, max_level=100, default_level=50, current_level=50)

    # Legacy API range (no Ex available, default inferred as midpoint): 0..31..63
    LEGACY = DVCRange(min_level=0, max_level=63, default_level=31, current_level=31)

    # --- Symmetric range tests ---

    def test_sym_default_roundtrip(self):
        """user 50 → hw default → user 50."""
        internal = _user_to_internal(50, self.SYM)
        assert internal == 0
        assert _internal_to_user(internal, self.SYM) == 50

    def test_sym_min_roundtrip(self):
        internal = _user_to_internal(0, self.SYM)
        assert internal == -1024
        assert _internal_to_user(internal, self.SYM) == 0

    def test_sym_max_roundtrip(self):
        internal = _user_to_internal(100, self.SYM)
        assert internal == 1024
        assert _internal_to_user(internal, self.SYM) == 100

    def test_sym_midpoints(self):
        assert _user_to_internal(25, self.SYM) == -512
        assert _user_to_internal(75, self.SYM) == 512

    # --- Asymmetric range tests (the bug scenario) ---

    def test_asym_default_maps_to_hw_default(self):
        """user 50 MUST map to hardware default (50), not 0!"""
        internal = _user_to_internal(50, self.ASYM)
        assert internal == 50  # Not 0!

    def test_asym_min_maps_to_hw_min(self):
        internal = _user_to_internal(0, self.ASYM)
        assert internal == 0

    def test_asym_max_maps_to_hw_max(self):
        internal = _user_to_internal(100, self.ASYM)
        assert internal == 100

    def test_asym_roundtrip_default(self):
        """Roundtrip through asymmetric range preserves user=50."""
        internal = _user_to_internal(50, self.ASYM)
        assert _internal_to_user(internal, self.ASYM) == 50

    def test_asym_roundtrip_min(self):
        internal = _user_to_internal(0, self.ASYM)
        assert _internal_to_user(internal, self.ASYM) == 0

    def test_asym_roundtrip_max(self):
        internal = _user_to_internal(100, self.ASYM)
        assert _internal_to_user(internal, self.ASYM) == 100

    # --- Clamping ---

    def test_clamping_below_min(self):
        assert _user_to_internal(-10, self.SYM) == -1024

    def test_clamping_above_max(self):
        assert _user_to_internal(150, self.SYM) == 1024

    # --- Legacy range tests (inferred midpoint default) ---

    def test_legacy_default_maps_to_midpoint(self):
        """user 50 → inferred default (midpoint of 0..63 = 31)."""
        internal = _user_to_internal(50, self.LEGACY)
        assert internal == 31

    def test_legacy_min_maps_to_zero(self):
        """user 0 → 0 (full desaturation / grayscale)."""
        internal = _user_to_internal(0, self.LEGACY)
        assert internal == 0

    def test_legacy_max_maps_to_63(self):
        internal = _user_to_internal(100, self.LEGACY)
        assert internal == 63

    def test_legacy_roundtrip(self):
        internal = _user_to_internal(50, self.LEGACY)
        user = _internal_to_user(internal, self.LEGACY)
        assert user == 50


# =============================================================================
# Unit Tests: Model Key Extraction
# =============================================================================


class TestModelKeyExtraction:
    """Test _extract_model_key from device ID strings."""

    def test_standard_monitor_id(self):
        """Standard Windows monitor device ID."""
        assert _extract_model_key(r"MONITOR\GSM7847\{guid-here}") == "GSM7847"

    def test_dell_monitor_id(self):
        assert _extract_model_key(r"MONITOR\DELD0E6\{guid}") == "DELD0E6"

    def test_forward_slashes(self):
        """Forward slashes also work."""
        assert _extract_model_key("MONITOR/GSM7847/{guid}") == "GSM7847"

    def test_empty_string(self):
        assert _extract_model_key("") is None

    def test_none_string(self):
        assert _extract_model_key(None) is None

    def test_no_match(self):
        assert _extract_model_key(r"MONITOR\12345\{guid}") is None


# =============================================================================
# Unit Tests: ICC Profile Alias Resolution
# =============================================================================


class TestICCProfileResolution:
    def test_srgb_alias(self):
        handler = ColorProfileSettingsHandler()
        assert handler._resolve_profile_name("srgb") == "sRGB Color Space Profile.icm"

    def test_srgb_case_insensitive(self):
        handler = ColorProfileSettingsHandler()
        assert handler._resolve_profile_name("SRGB") == "sRGB Color Space Profile.icm"

    def test_native_returns_none(self):
        handler = ColorProfileSettingsHandler()
        assert handler._resolve_profile_name("native") is None

    def test_literal_filename_passthrough(self):
        handler = ColorProfileSettingsHandler()
        assert handler._resolve_profile_name("MyCustom.icm") == "MyCustom.icm"


# =============================================================================
# Unit Tests: Monitor OSD Database
# =============================================================================


class TestMonitorOSD:
    """Test the OSD recommendation database lookups."""

    def test_lg_competitive_fps(self):
        """LG 27GS95QE should have competitive_fps recommendations."""
        result = get_osd_recommendations(r"MONITOR\GSM7847\{guid}", "competitive_fps")
        assert result is not None
        display_name, recs = result
        assert "LG" in display_name
        assert len(recs) > 0
        assert all(isinstance(r, OSDRecommendation) for r in recs)

    def test_lg_cinematic(self):
        result = get_osd_recommendations(r"MONITOR\GSM7847\{guid}", "cinematic")
        assert result is not None

    def test_lg_emulator(self):
        result = get_osd_recommendations(r"MONITOR\GSM7847\{guid}", "emulator")
        assert result is not None

    def test_lg_productivity(self):
        result = get_osd_recommendations(r"MONITOR\GSM7847\{guid}", "productivity")
        assert result is not None

    def test_dell_competitive_fps(self):
        result = get_osd_recommendations(r"MONITOR\DELD0E6\{guid}", "competitive_fps")
        assert result is not None
        display_name, recs = result
        assert "Dell" in display_name

    def test_dell_unknown_game_type(self):
        """Dell only has competitive_fps; other types return None."""
        result = get_osd_recommendations(r"MONITOR\DELD0E6\{guid}", "cinematic")
        assert result is None

    def test_unknown_monitor(self):
        result = get_osd_recommendations(r"MONITOR\UNKNOWN\{guid}", "competitive_fps")
        assert result is None

    def test_empty_monitor_id(self):
        result = get_osd_recommendations("", "competitive_fps")
        assert result is None


# =============================================================================
# Handler Tests: apply() with empty/no settings
# =============================================================================


class TestColorHandlerApply:
    """Test ColorProfileSettingsHandler.apply() behavior."""

    def test_apply_empty_settings_is_noop(self):
        """Empty settings dict should succeed without doing anything."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({})
        assert result["success"] is True
        assert result["error"] is None
        assert result["requires_reboot"] is False

    def test_apply_none_equivalent(self):
        """apply({}) should be a safe no-op."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({})
        assert result["success"] is True

    @patch.object(ColorProfileSettingsHandler, "_get_current_icc_profile", return_value=None)
    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    def test_apply_icc_srgb(self, mock_apply_icc: MagicMock, mock_current_icc: MagicMock):
        """Applying sRGB should call _apply_icc_profile."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"icc_profile": "srgb"})
        assert result["success"] is True
        assert result["changed_keys"] == ["icc_profile"]
        mock_apply_icc.assert_called_once_with("srgb")

    @patch.object(
        ColorProfileSettingsHandler,
        "_get_current_icc_profile",
        return_value="sRGB Color Space Profile.icm",
    )
    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    def test_apply_icc_native(self, mock_apply_icc: MagicMock, mock_current_icc: MagicMock):
        """Applying native should call _apply_icc_profile('native')."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"icc_profile": "native"})
        assert result["success"] is True
        mock_apply_icc.assert_called_once_with("native")

    @patch.object(
        ColorProfileSettingsHandler,
        "_get_current_icc_profile",
        return_value="sRGB Color Space Profile.icm",
    )
    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    def test_apply_icc_skips_when_already_active(
        self,
        mock_apply_icc: MagicMock,
        mock_current_icc: MagicMock,
    ):
        """Already-active ICC profiles should not be re-written."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"icc_profile": "srgb"})
        assert result["success"] is True
        mock_apply_icc.assert_not_called()
        assert result["changed"] is False
        assert result["changed_keys"] == []
        assert any("already active" in item for item in result["skipped"])

    @patch.object(
        ColorProfileSettingsHandler,
        "_apply_icc_profile",
        side_effect=FileNotFoundError("not found"),
    )
    @patch.object(ColorProfileSettingsHandler, "_get_current_icc_profile", return_value=None)
    def test_apply_icc_failure_graceful(
        self,
        mock_current_icc: MagicMock,
        mock_apply_icc: MagicMock,
    ):
        """ICC failure should not crash — reports error but continues."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"icc_profile": "nonexistent.icm"})
        assert result["success"] is False
        assert "ICC profile" in result["error"]

    @patch.object(ColorProfileSettingsHandler, "_set_digital_vibrance")
    def test_apply_vibrance(self, mock_set_dv: MagicMock):
        """Vibrance setting should call _set_digital_vibrance."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"digital_vibrance": 60})
        assert result["success"] is True
        assert result["changed_keys"] == ["digital_vibrance"]
        mock_set_dv.assert_called_once_with(60)

    @patch.object(
        ColorProfileSettingsHandler, "_set_digital_vibrance", side_effect=RuntimeError("no NVAPI")
    )
    def test_apply_vibrance_unavailable_is_graceful_skip(self, mock_set_dv: MagicMock):
        """Unavailable NVAPI should gracefully skip, not fail the handler."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"digital_vibrance": 60})
        assert result["success"] is True
        assert result["error"] is None
        assert len(result["skipped"]) == 1

    @patch.object(ColorProfileSettingsHandler, "_set_digital_vibrance")
    def test_apply_vibrance_default_still_sets(self, mock_set_dv: MagicMock):
        """Vibrance=50 (default) must still SET to ensure hardware is at default.

        This is critical: a previous buggy apply might have left DVC at 0
        (full desaturation / grayscale). Skipping vibrance=50 would leave
        the screen black and white forever.
        """
        handler = ColorProfileSettingsHandler()
        result = handler.apply({"digital_vibrance": 50})
        assert result["success"] is True
        mock_set_dv.assert_called_once_with(50)

    @patch.object(ColorProfileSettingsHandler, "_get_current_icc_profile", return_value=None)
    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    @patch.object(ColorProfileSettingsHandler, "_set_digital_vibrance")
    def test_apply_multiple_settings(
        self,
        mock_dv: MagicMock,
        mock_icc: MagicMock,
        mock_current_icc: MagicMock,
    ):
        """Both ICC and vibrance applied together."""
        handler = ColorProfileSettingsHandler()
        result = handler.apply(
            {
                "icc_profile": "srgb",
                "digital_vibrance": 55,
                "show_osd_guidance": False,
                "game_type": "competitive_fps",
            }
        )
        assert result["success"] is True
        assert result["changed_keys"] == ["icc_profile", "digital_vibrance"]
        mock_icc.assert_called_once_with("srgb")
        mock_dv.assert_called_once_with(55)


# =============================================================================
# Handler Tests: backup/restore
# =============================================================================


class TestColorHandlerBackupRestore:
    """Test backup and restore flows."""

    @patch.object(ColorProfileSettingsHandler, "_get_primary_monitor_info", return_value=None)
    @patch.object(ColorProfileSettingsHandler, "_get_digital_vibrance", return_value=50)
    @patch.object(
        ColorProfileSettingsHandler,
        "_get_current_icc_profile",
        return_value="sRGB Color Space Profile.icm",
    )
    def test_backup_returns_current_state(self, mock_icc, mock_dv, mock_mon):
        handler = ColorProfileSettingsHandler()
        data = handler.backup()
        assert data["icc_profile"] == "sRGB Color Space Profile.icm"
        assert data["digital_vibrance"] == 50

    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    @patch.object(ColorProfileSettingsHandler, "_set_digital_vibrance")
    def test_restore_calls_apply(self, mock_dv, mock_icc):
        handler = ColorProfileSettingsHandler()
        success = handler.restore(
            {
                "icc_profile": "sRGB Color Space Profile.icm",
                "digital_vibrance": 75,  # Non-default to exercise restore path
            }
        )
        assert success is True
        mock_icc.assert_called_once_with("sRGB Color Space Profile.icm")
        mock_dv.assert_called_once_with(75)

    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    @patch.object(ColorProfileSettingsHandler, "_set_digital_vibrance")
    def test_restore_sets_default_vibrance(self, mock_dv, mock_icc):
        """Restoring vibrance=50 must still set hardware to default."""
        handler = ColorProfileSettingsHandler()
        success = handler.restore(
            {
                "icc_profile": "sRGB Color Space Profile.icm",
                "digital_vibrance": 50,
            }
        )
        assert success is True
        mock_icc.assert_called_once()
        mock_dv.assert_called_once_with(50)

    def test_restore_guarantee_is_partial(self):
        """ICC list round-trips, but vibrance is NVAPI/display dependent."""
        assert ColorProfileSettingsHandler().restore_guarantee == "partial"

    @patch.object(ColorProfileSettingsHandler, "_get_primary_monitor_info", return_value=None)
    @patch.object(ColorProfileSettingsHandler, "_get_digital_vibrance", return_value=50)
    @patch.object(
        ColorProfileSettingsHandler,
        "_get_icc_profile_list",
        return_value=["sRGB Color Space Profile.icm", "CalibratedNative.icm"],
    )
    @patch.object(
        ColorProfileSettingsHandler,
        "_get_current_icc_profile",
        return_value="sRGB Color Space Profile.icm",
    )
    def test_backup_captures_full_icc_list(self, mock_icc, mock_list, mock_dv, mock_mon):
        """Backup must capture every ICC association, not just the active one."""
        data = ColorProfileSettingsHandler().backup()
        assert data["icc_profile_list"] == [
            "sRGB Color Space Profile.icm",
            "CalibratedNative.icm",
        ]

    @patch.object(ColorProfileSettingsHandler, "_apply_icc_profile")
    @patch.object(ColorProfileSettingsHandler, "_restore_icc_profile_list")
    @patch.object(ColorProfileSettingsHandler, "_set_digital_vibrance")
    def test_restore_full_list_uses_list_path(self, mock_dv, mock_restore_list, mock_apply):
        """New backups restore the whole list and never go through apply()."""
        handler = ColorProfileSettingsHandler()
        success = handler.restore(
            {
                "icc_profile": "sRGB Color Space Profile.icm",
                "icc_profile_list": [
                    "sRGB Color Space Profile.icm",
                    "CalibratedNative.icm",
                ],
                "digital_vibrance": 50,
            }
        )
        assert success is True
        mock_restore_list.assert_called_once_with(
            ["sRGB Color Space Profile.icm", "CalibratedNative.icm"]
        )
        mock_apply.assert_not_called()


# =============================================================================
# Handler Tests: detect (mocked)
# =============================================================================


class TestColorHandlerDetect:

    @patch.object(
        ColorProfileSettingsHandler,
        "_get_display_color_info",
        return_value={"bits_per_channel": 10, "encoding": "RGB"},
    )
    @patch.object(ColorProfileSettingsHandler, "_get_digital_vibrance", return_value=50)
    @patch.object(
        ColorProfileSettingsHandler,
        "_get_current_icc_profile",
        return_value="sRGB Color Space Profile.icm",
    )
    @patch.object(
        ColorProfileSettingsHandler,
        "_get_primary_monitor_info",
        return_value={
            "device_name": r"\\.\DISPLAY1",
            "class_index": "0001",
            "monitor_id": r"MONITOR\GSM7847\{guid}",
            "monitor_string": "LG OLED",
        },
    )
    def test_detect_full(self, mock_mon, mock_icc, mock_dv, mock_color):
        handler = ColorProfileSettingsHandler()
        result = handler.detect()
        assert result["icc_profile"] == "sRGB Color Space Profile.icm"
        assert result["digital_vibrance"] == 50
        assert result["color_depth_bits"] == 10
        assert result["color_encoding"] == "RGB"
        assert result["monitor_device"] == r"\\.\DISPLAY1"
        assert result["monitor_id"] == r"MONITOR\GSM7847\{guid}"

    def test_select_primary_target_prefers_matching_source(self):
        targets = [
            {
                "adapter_id": object(),
                "target_id": 1,
                "source_id": 1,
                "source_device_name": r"\\.\DISPLAY2",
            },
            {
                "adapter_id": object(),
                "target_id": 2,
                "source_id": 2,
                "source_device_name": r"\\.\DISPLAY1",
            },
        ]

        selected = ColorProfileSettingsHandler._select_primary_target(
            targets=targets,
            primary_device_name=r"\\.\DISPLAY1",
        )

        assert selected is not None
        assert selected["target_id"] == 2

    def test_select_primary_target_falls_back_to_first(self):
        targets = [
            {
                "adapter_id": object(),
                "target_id": 7,
                "source_id": 7,
                "source_device_name": r"\\.\DISPLAY9",
            },
            {
                "adapter_id": object(),
                "target_id": 8,
                "source_id": 8,
                "source_device_name": r"\\.\DISPLAY8",
            },
        ]

        selected = ColorProfileSettingsHandler._select_primary_target(
            targets=targets,
            primary_device_name=r"\\.\DISPLAY1",
        )

        assert selected is not None
        assert selected["target_id"] == 7

    @patch.object(ColorProfileSettingsHandler, "_init_nvapi", return_value=True)
    @patch.object(ColorProfileSettingsHandler, "_get_primary_monitor_info")
    @patch.object(ColorProfileSettingsHandler, "_get_associated_nvidia_display_handle")
    @patch.object(ColorProfileSettingsHandler, "_enumerate_nvidia_display_handles")
    def test_get_nvidia_display_handle_prefers_associated_primary(
        self,
        mock_enumerate,
        mock_associated,
        mock_primary,
        mock_init,
    ):
        handler = ColorProfileSettingsHandler()
        mock_primary.return_value = {"device_name": r"\\.\DISPLAY1"}
        mock_associated.return_value = c_int(9)
        mock_enumerate.return_value = [c_int(1)]

        handle = handler._get_nvidia_display_handle()

        assert handle is not None
        assert handle.value == 9
        mock_associated.assert_called_once_with(r"\\.\DISPLAY1")

    @patch.object(ColorProfileSettingsHandler, "_init_nvapi", return_value=True)
    @patch.object(ColorProfileSettingsHandler, "_get_primary_monitor_info")
    @patch.object(ColorProfileSettingsHandler, "_get_associated_nvidia_display_handle")
    @patch.object(ColorProfileSettingsHandler, "_enumerate_nvidia_display_handles")
    def test_get_nvidia_display_handle_falls_back_to_first_enumerated(
        self,
        mock_enumerate,
        mock_associated,
        mock_primary,
        mock_init,
    ):
        handler = ColorProfileSettingsHandler()
        mock_primary.return_value = {"device_name": r"\\.\DISPLAY1"}
        mock_associated.return_value = None
        mock_enumerate.return_value = [c_int(4), c_int(6)]

        handle = handler._get_nvidia_display_handle()

        assert handle is not None
        assert handle.value == 4


# =============================================================================
# Handler Tests: audit
# =============================================================================


class TestColorHandlerAudit:

    @patch.object(
        ColorProfileSettingsHandler,
        "detect",
        return_value={
            "icc_profile": None,
            "digital_vibrance": 75,
        },
    )
    def test_audit_finds_issues(self, mock_detect):
        handler = ColorProfileSettingsHandler()
        issues = handler.audit()
        assert len(issues) == 2
        categories = [i.category for i in issues]
        assert all(c == "color" for c in categories)

    @patch.object(
        ColorProfileSettingsHandler,
        "detect",
        return_value={
            "icc_profile": "sRGB Color Space Profile.icm",
            "digital_vibrance": 50,
        },
    )
    def test_audit_no_issues_when_default(self, mock_detect):
        handler = ColorProfileSettingsHandler()
        issues = handler.audit()
        assert len(issues) == 0


# =============================================================================
# OSD Acknowledgment Tests
# =============================================================================


class TestOSDAcknowledgment:

    def test_is_osd_acknowledged_no_file(self, tmp_path: Path):
        """No ack file → not acknowledged."""
        with patch("abso.settings.color.OSD_ACK_FILE", tmp_path / "nonexistent.json"):
            assert (
                ColorProfileSettingsHandler._is_osd_acknowledged(r"MONITOR\GSM7847\{guid}") is False
            )

    def test_acknowledge_and_check(self, tmp_path: Path):
        """Acknowledge then verify it's marked."""
        ack_file = tmp_path / "osd_acknowledged.json"
        with (
            patch("abso.settings.color.OSD_ACK_FILE", ack_file),
            patch("abso.settings.color.OSD_ACK_DIR", tmp_path),
        ):
            ColorProfileSettingsHandler._acknowledge_osd(r"MONITOR\GSM7847\{guid}")
            assert ack_file.exists()
            data = json.loads(ack_file.read_text())
            assert data.get("GSM7847") is True

            assert (
                ColorProfileSettingsHandler._is_osd_acknowledged(r"MONITOR\GSM7847\{guid}") is True
            )


# =============================================================================
# Profile Integration Tests
# =============================================================================


class TestProfileIntegration:
    """Test that profiles include the color handler and settings."""

    def test_rivals2_has_color_handler(self):
        from abso.profiles.rivals2 import Rivals2Profile

        profile = Rivals2Profile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "ColorProfileSettingsHandler" in handler_names

    def test_rivals2_color_settings(self):
        from abso.profiles.rivals2 import Rivals2Profile

        profile = Rivals2Profile()
        settings = profile.get_settings("ColorProfileSettingsHandler")
        assert settings["icc_profile"] == "srgb"
        # SDR profiles use the wide-gamut compensation (-5) per the
        # documented policy in profile_bases.SDR_WIDE_GAMUT_VIBRANCE.
        assert settings["digital_vibrance"] == 45
        assert settings["game_type"] == "competitive_fps"

    def test_diablo4_has_color_handler(self):
        from abso.profiles.diablo4 import Diablo4Profile

        profile = Diablo4Profile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "ColorProfileSettingsHandler" in handler_names

    def test_diablo4_color_settings(self):
        from abso.profiles.diablo4 import Diablo4Profile

        profile = Diablo4Profile()
        settings = profile.get_settings("ColorProfileSettingsHandler")
        assert settings["icc_profile"] == "native"
        assert settings["game_type"] == "cinematic"

    def test_productivity_has_color_handler(self):
        from abso.profiles.productivity_oled import ProductivityOLEDProfile

        profile = ProductivityOLEDProfile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "ColorProfileSettingsHandler" in handler_names

    def test_productivity_color_settings(self):
        from abso.profiles.productivity_oled import ProductivityOLEDProfile

        profile = ProductivityOLEDProfile()
        settings = profile.get_settings("ColorProfileSettingsHandler")
        assert settings["icc_profile"] == "native"
        assert settings["game_type"] == "productivity"

    def test_slippi_has_color_handler(self):
        from abso.profiles.slippi_melee import SlippiMeleeProfile

        profile = SlippiMeleeProfile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "ColorProfileSettingsHandler" in handler_names

    def test_overwatch2_gsync_hdr_has_color_handler(self):
        from abso.profiles.overwatch2 import Overwatch2GSyncHDRProfile

        profile = Overwatch2GSyncHDRProfile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "ColorProfileSettingsHandler" in handler_names

    def test_overwatch2_gsync_hdr_color_settings(self):
        from abso.profiles.overwatch2 import Overwatch2GSyncHDRProfile

        profile = Overwatch2GSyncHDRProfile()
        settings = profile.get_settings("ColorProfileSettingsHandler")
        assert settings["icc_profile"] == "native"
        assert settings["game_type"] == "competitive_fps"
