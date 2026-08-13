"""Tests for profile application module."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from abso.core.applier import ApplyResult, ProfileApplier
from abso.core.exceptions import ProfileNotFoundError
from abso.core.multimon_detector import DisplayEnvironment, MultiMonitorResult
from abso.profiles.overwatch2 import Overwatch2Profile


class TestApplyResultDataclass:
    """Tests for ApplyResult dataclass."""

    def test_apply_result_success(self):
        """Test ApplyResult with success."""
        result = ApplyResult(
            success=True,
            applied_settings=["WindowsSettingsHandler", "NvidiaSettingsHandler"],
        )

        assert result.success is True
        assert result.error is None
        assert result.requires_reboot is False
        assert len(result.applied_settings) == 2
        assert result.changed_settings == []

    def test_apply_result_failure(self):
        """Test ApplyResult with failure."""
        result = ApplyResult(
            success=False,
            error="Failed to apply settings",
            failed_settings=["WindowsSettingsHandler"],
        )

        assert result.success is False
        assert result.error == "Failed to apply settings"
        assert len(result.failed_settings) == 1

    def test_apply_result_requires_reboot(self):
        """Test ApplyResult with reboot required."""
        result = ApplyResult(
            success=True,
            requires_reboot=True,
        )

        assert result.requires_reboot is True

    def test_handler_changed_settings_prefers_explicit_keys(self):
        """Handler success and handler mutation are separate signals."""
        changed = ProfileApplier._handler_changed_settings(
            "WindowsSettingsHandler",
            {"success": True, "changed_keys": ["hdr", "advanced_color"]},
        )

        assert changed == [
            "WindowsSettingsHandler.hdr",
            "WindowsSettingsHandler.advanced_color",
        ]

    def test_handler_changed_settings_treats_already_messages_as_noop(self):
        """Compatibility parsing should not mark no-op apply notes as mutations."""
        changed = ProfileApplier._handler_changed_settings(
            "DisplayColorRangeHandler",
            {
                "success": True,
                "applied": ["Display 1: already Full (VESA/PC) (no change)"],
            },
        )

        assert changed == []


class TestProfileApplierInit:
    """Tests for ProfileApplier initialization."""

    def test_init_creates_instance(self):
        """Test ProfileApplier can be instantiated."""
        applier = ProfileApplier()
        assert applier is not None
        assert applier._profiles == {}

    def test_profiles_registry_exists(self):
        """Test PROFILES registry contains expected profiles."""
        assert "slippi-melee" in ProfileApplier.PROFILES
        assert "slippi-melee-console-parity" in ProfileApplier.PROFILES
        assert "slippi-melee-universal" in ProfileApplier.PROFILES
        assert "cod-bo7" not in ProfileApplier.PROFILES
        assert "diablo4" in ProfileApplier.PROFILES
        assert "rivals2-nosync" in ProfileApplier.PROFILES
        assert "rivals2-nosync-hdr" in ProfileApplier.PROFILES
        assert "rivals2-gsync" in ProfileApplier.PROFILES
        assert "rivals2-gsync-hdr" in ProfileApplier.PROFILES
        assert "overwatch2" in ProfileApplier.PROFILES
        assert "overwatch2-gsync" in ProfileApplier.PROFILES

    @patch("abso.core.applier.subprocess.run")
    def test_check_game_running_uses_exact_tasklist_image_names(self, mock_run):
        """Apply warnings should not trigger from tasklist substring matches."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout='"notgame.exe","1111","Console","1","10000 K"\n',
        )
        applier = ProfileApplier()

        assert applier._check_game_running(["game.exe"]) == []


class TestGetProfile:
    """Tests for _get_profile method."""

    def test_get_profile_valid(self):
        """Test getting a valid profile."""
        applier = ProfileApplier()
        profile = applier._get_profile("slippi-melee")

        assert profile is not None
        assert profile.profile_id == "slippi-melee"

    def test_get_profile_caches(self):
        """Test profile instances are cached."""
        applier = ProfileApplier()
        profile1 = applier._get_profile("slippi-melee")
        profile2 = applier._get_profile("slippi-melee")

        assert profile1 is profile2

    def test_get_profile_unknown_raises(self):
        """Test getting unknown profile raises ProfileNotFoundError."""
        applier = ProfileApplier()

        with pytest.raises(ProfileNotFoundError) as exc_info:
            applier._get_profile("nonexistent-profile")

        assert "Unknown profile" in str(exc_info.value)
        assert "slippi-melee" in str(exc_info.value)  # Lists available profiles


class TestApplyProfile:
    """Tests for apply_profile method."""

    def test_apply_profile_unknown(self):
        """Test applying unknown profile returns error."""
        applier = ProfileApplier()
        result = applier.apply_profile("nonexistent")

        assert result.success is False
        assert "Unknown profile" in result.error

    def test_apply_profile_success(self):
        """Test successful profile application."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [mock_handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is True
            assert "TestHandler" in result.applied_settings
            assert "TestHandler" in result.changed_settings
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_uses_canonical_id_for_profile_overrides(self):
        """Alias applies should use the canonical profile id for config lookups."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [mock_handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier(
            skip_linting=True,
            skip_rollback_guard=True,
            skip_stability_gate=True,
            skip_network_scope=True,
            skip_multimon_detection=True,
            skip_capability_checks=True,
        )
        applier._profiles["canonical-profile"] = mock_profile
        ProfileApplier.PROFILES["canonical-profile"] = type(mock_profile)

        def resolve_alias(name):
            if name in {"alias-profile", "canonical-profile"}:
                return "canonical-profile"
            return None

        try:
            with (
                patch("abso.core.applier.resolve_profile_id", side_effect=resolve_alias),
                patch("abso.core.applier.ConfigManager") as mock_config_cls,
            ):
                mock_config = mock_config_cls.return_value
                mock_config.get_profile_overrides.return_value = None
                mock_config.is_handler_disabled.return_value = False

                result = applier.apply_profile("alias-profile")

            assert result.success is True
            mock_config.get_profile_overrides.assert_called_once_with("canonical-profile")
        finally:
            del ProfileApplier.PROFILES["canonical-profile"]

    def test_apply_profile_rejects_vbs_config_override_before_handler_apply(self):
        """Config overrides cannot bypass the explicit HVCI acknowledgement gate."""
        from abso.core.config import ProfileOverrides
        from abso.settings.windows import WindowsSettingsHandler

        handler = WindowsSettingsHandler()
        mock_profile = MagicMock()
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {"game_mode": True}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier(
            skip_linting=True,
            skip_rollback_guard=True,
            skip_stability_gate=True,
            skip_network_scope=True,
            skip_multimon_detection=True,
            skip_capability_checks=True,
        )
        applier._profiles["test-vbs-override"] = mock_profile
        ProfileApplier.PROFILES["test-vbs-override"] = type(mock_profile)

        try:
            with (
                patch.object(handler, "apply") as mock_apply,
                patch("abso.core.applier.ConfigManager") as mock_config_cls,
            ):
                mock_config = mock_config_cls.return_value
                mock_config.get_profile_overrides.return_value = ProfileOverrides(
                    windows={"vbs": False}
                )

                result = applier.apply_profile("test-vbs-override")

            assert result.success is False
            assert "VBSOptInHandler" in (result.error or "")
            mock_apply.assert_not_called()
        finally:
            del ProfileApplier.PROFILES["test-vbs-override"]

    def test_apply_profile_partial_failure(self):
        """Test profile application with some handlers failing."""
        handler1 = MagicMock()
        handler1.__class__.__name__ = "Handler1"
        handler1.apply.return_value = {"success": True}

        handler2 = MagicMock()
        handler2.__class__.__name__ = "Handler2"
        handler2.apply.return_value = {"success": False, "error": "Failed"}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [handler1, handler2]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is False
            assert "Handler1" in result.applied_settings
            assert "Handler1" in result.changed_settings
            assert any("Handler2" in f for f in result.failed_settings)
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_handles_permission_error(self):
        """Test profile application handles PermissionError."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.side_effect = PermissionError("Access denied")

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is False
            assert "Permission denied" in str(result.failed_settings)
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_reboot_required(self):
        """Test profile application with reboot required."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.return_value = {"success": True, "requires_reboot": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is True
            assert result.requires_reboot is True
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_verify_profile_aggregates_pending_apply_settings(self):
        """Verify output should identify settings that still need an apply."""

        class PendingApplyHandler:
            def verify_active(self, settings):
                return {
                    "all_active": False,
                    "pending_apply_settings": ["mpo_disabled"],
                    "settings": {
                        "mpo_disabled": {
                            "target": True,
                            "current": False,
                            "active": False,
                        }
                    },
                }

        class VerifyProfile:
            def get_handlers(self):
                return [PendingApplyHandler()]

        applier = ProfileApplier()
        applier._profiles["verify-profile"] = VerifyProfile()

        with (
            patch("abso.core.applier.ConfigManager") as mock_config_cls,
            patch.object(
                applier,
                "_build_effective_settings_map",
                return_value=(
                    {"PendingApplyHandler": {"disable_mpo": True}},
                    None,
                    None,
                    None,
                ),
            ),
        ):
            mock_config_cls.return_value.get_profile_overrides.return_value = {}
            result = applier.verify_profile("verify-profile")

        assert result["all_active"] is False
        assert result["pending_apply_settings"] == ["PendingApplyHandler.mpo_disabled"]
        assert "pending_reboot_gated_settings" not in result

    def test_verify_profile_uses_reboot_pending_override(self):
        """Profile-switch verification should not read stale active-profile reboot state."""

        class RebootAwareHandler:
            def verify_active(self, settings):
                if settings.get("_reboot_pending"):
                    return {
                        "all_active": False,
                        "pending_reboot_gated_settings": ["mpo_disabled"],
                        "settings": {
                            "mpo_disabled": {
                                "active": True,
                                "reboot_gated": True,
                                "registry_target_written": True,
                            }
                        },
                    }
                return {
                    "all_active": True,
                    "settings": {
                        "mpo_disabled": {
                            "active": True,
                            "reboot_gated": True,
                            "registry_target_written": True,
                        }
                    },
                }

        class VerifyProfile:
            def get_handlers(self):
                return [RebootAwareHandler()]

        applier = ProfileApplier()
        applier._profiles["verify-profile"] = VerifyProfile()

        with (
            patch("abso.core.applier.ConfigManager") as mock_config_cls,
            patch("abso.core.state_store.read_state_snapshot") as mock_read_state,
            patch.object(
                applier,
                "_build_effective_settings_map",
                return_value=(
                    {"RebootAwareHandler": {"disable_mpo": False}},
                    None,
                    None,
                    None,
                ),
            ),
        ):
            mock_config_cls.return_value.get_profile_overrides.return_value = {}
            result = applier.verify_profile("verify-profile", reboot_pending=False)

        mock_read_state.assert_not_called()
        assert result["all_active"] is True
        assert "pending_reboot_gated_settings" not in result

    def test_apply_profile_collects_handler_notices(self):
        """Handler notices should be propagated to the apply result."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.return_value = {
            "success": True,
            "notices": ["Reused existing bound NVIDIA profile"],
        }

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []
        mock_profile.validate_settings.return_value = []
        mock_profile.validate_settings.return_value = []
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is True
            assert result.notices == ["Reused existing bound NVIDIA profile"]
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_finalize_handler_settings_uses_canonical_nvidia_binding_executables(self):
        """NVIDIA handler settings should use canonical binding executables, not all hints."""
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"

        profile = MagicMock()
        profile.get_handlers.return_value = [nvidia_handler]
        profile.get_settings.return_value = {"preset": "vrr_fighting_game"}
        profile.display_name = "Rivals 2: Online G-SYNC HDR"
        profile.executable_hints = [
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        ]
        profile.nvidia_binding_executables = ["Rivals2-Win64-Shipping.exe"]
        profile.nvidia_profile_name = "Rivals 2 Online"
        profile.nvidia_profile_aliases = ["Rivals 2: Online G-SYNC"]
        profile.requires_exact_nvidia_binding = True
        profile.allow_unverified_nvidia_profile_reuse = True

        applier = ProfileApplier()
        final = applier._finalize_handler_settings(profile, "test-profile", {}, None)

        assert final["NvidiaSettingsHandler"]["executables"] == ["Rivals2-Win64-Shipping.exe"]
        assert final["NvidiaSettingsHandler"]["profile_name"] == "Rivals 2 Online"
        assert final["NvidiaSettingsHandler"]["profile_aliases"] == ["Rivals 2: Online G-SYNC"]
        assert final["NvidiaSettingsHandler"]["require_exact_binding"] is True
        assert final["NvidiaSettingsHandler"]["allow_unverified_existing_profile_reuse"] is True

    def test_finalize_nvidia_identity_preserves_user_profile_name_override(self):
        """Shared NVIDIA identity injection must not clobber explicit config overrides."""
        from abso.core.config import ProfileOverrides

        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"

        profile = MagicMock()
        profile.get_handlers.return_value = [nvidia_handler]
        profile.get_settings.return_value = {"preset": "vrr_fighting_game"}
        profile.display_name = "Game Profile"
        profile.nvidia_binding_executables = ["Game.exe"]
        profile.nvidia_profile_name = "Profile Default"
        profile.nvidia_profile_aliases = ["Default Alias"]
        profile.requires_exact_nvidia_binding = False
        profile.allow_unverified_nvidia_profile_reuse = False

        overrides = ProfileOverrides(
            nvidia={
                "profile_name": "User Override",
                "profile_aliases": ["User Alias"],
            }
        )

        applier = ProfileApplier()
        final = applier._finalize_handler_settings(profile, "test-profile", {}, overrides)

        assert final["NvidiaSettingsHandler"]["profile_name"] == "User Override"
        assert final["NvidiaSettingsHandler"]["profile_aliases"] == ["User Alias"]

    def test_finalize_expands_overwatch_fso_paths_at_runtime_only(self):
        """OW2 snapshots stay deterministic while apply/verify gets full FSO paths."""
        profile = Overwatch2Profile()
        settings = profile.get_settings("RegistrySettingsHandler")

        assert settings["fullscreen_optimizations"] == {"Overwatch.exe": True}

        applier = ProfileApplier()
        local_path = r"C:\Games\Overwatch\_retail_\Overwatch.exe"
        with patch.object(profile, "_overwatch_install_paths", return_value=[local_path]):
            final = applier._finalize_handler_settings(
                profile,
                profile.profile_id,
                {"RegistrySettingsHandler": settings},
                None,
            )

        fso = final["RegistrySettingsHandler"]["fullscreen_optimizations"]
        assert fso["Overwatch.exe"] is True
        assert fso[local_path] is True

    def test_apply_profile_blocks_on_profile_contract_violation(self):
        """Profile-specific validation must abort before handlers run."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []
        mock_profile.validate_settings.return_value = []
        mock_profile.validate_settings.return_value = []
        mock_profile.validate_settings.return_value = ["VRR path must remain disabled"]

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is False
            assert "Profile contract violations" in (result.error or "")
            assert result.failed_settings == ["ProfileContract: VRR path must remain disabled"]
            handler.apply.assert_not_called()
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    @patch("abso.core.applier.MultiMonitorDetector.detect")
    @patch("abso.core.capabilities.HardwareDetector.detect_monitors")
    def test_apply_profile_blocks_when_confirmed_vrr_not_detected(
        self, mock_detect_monitors, mock_multimon_detect
    ):
        """VRR-required profiles should fail when VRR is not confirmed or likely."""
        mock_multimon_detect.return_value = MultiMonitorResult(
            environment=DisplayEnvironment(monitor_count=1),
            warnings=[],
        )
        mock_detect_monitors.return_value = [
            {"name": "Test Monitor", "vrr_supported": "possible", "refresh_rate": 240}
        ]

        applier = ProfileApplier()
        result = applier.apply_profile("overwatch2-gsync")

        assert result.success is False
        assert "does not report confirmed VRR/G-SYNC support" in (result.error or "")

    @patch("abso.core.capabilities.WindowsSettingsHandler.detect")
    @patch("abso.core.capabilities.HardwareDetector.detect_gpu")
    @patch("abso.core.capabilities.HardwareDetector.detect_monitors")
    @patch("abso.core.applier.MultiMonitorDetector.detect")
    def test_apply_profile_blocks_hdr_profile_when_no_hdr_capable_display(
        self,
        mock_multimon_detect,
        mock_detect_monitors,
        mock_detect_gpu,
        mock_windows_detect,
    ):
        """HDR-native profiles should fail before handler apply when no HDR-capable output exists."""
        mock_multimon_detect.return_value = MultiMonitorResult(
            environment=DisplayEnvironment(monitor_count=1),
            warnings=[],
        )
        mock_detect_monitors.return_value = [
            {"name": "Test Monitor", "vrr_supported": True, "refresh_rate": 240}
        ]
        mock_detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
        mock_windows_detect.return_value = {
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
        }

        applier = ProfileApplier()
        result = applier.apply_profile("overwatch2-gsync-hdr")

        assert result.success is False
        assert "requires at least one HDR-capable active display" in (result.error or "")

    @patch("abso.core.applier.MultiMonitorDetector.detect")
    @patch("abso.core.capabilities.HardwareDetector.detect_monitors")
    def test_apply_profile_allows_when_confirmed_vrr_detected(
        self, mock_detect_monitors, mock_multimon_detect
    ):
        """VRR-required mock profile should apply when a confirmed VRR monitor is detected."""
        mock_multimon_detect.return_value = MultiMonitorResult(
            environment=DisplayEnvironment(monitor_count=1),
            warnings=[],
        )
        mock_detect_monitors.return_value = [
            {"name": "Test Monitor", "vrr_supported": True, "refresh_rate": 240}
        ]

        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = True
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier()
        applier._profiles["test-gsync-profile"] = mock_profile
        ProfileApplier.PROFILES["test-gsync-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-gsync-profile")
            assert result.success is True
            assert "TestHandler" in result.applied_settings
        finally:
            del ProfileApplier.PROFILES["test-gsync-profile"]

    def test_apply_profile_does_not_auto_inject_mpo_disable(self):
        """Multi-monitor warnings should not silently force an MPO reboot anymore."""
        handler = MagicMock()
        handler.__class__.__name__ = "GraphicsSettingsHandler"
        handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier(skip_capability_checks=True)
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)
        applier._multimon_detector.detect = MagicMock(
            return_value=MultiMonitorResult(
                environment=DisplayEnvironment(
                    monitor_count=2,
                    has_mixed_refresh=True,
                    detected_overlays=["Discord Overlay"],
                ),
                warnings=[],
            )
        )

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is True
            handler.apply.assert_called_once_with({})
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_blocks_on_handler_preflight_failure(self):
        """Handler preflight failures should abort before apply side effects."""
        handler = MagicMock()
        handler.__class__.__name__ = "NvidiaSettingsHandler"
        handler.preflight.return_value = {
            "success": False,
            "error": "Exact NVIDIA executable binding could not be confirmed.",
        }

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.requires_exact_nvidia_binding = False
        mock_profile.nvidia_profile_name = None
        mock_profile.nvidia_profile_aliases = []
        mock_profile.executable_hints = ["Overwatch.exe"]
        mock_profile.display_name = "Overwatch 2 - GSYNC"
        mock_profile.profile_id = "test-preflight-profile"
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {"preset": "reflex_gsync"}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier(skip_capability_checks=True)
        applier._profiles["test-preflight-profile"] = mock_profile
        ProfileApplier.PROFILES["test-preflight-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-preflight-profile")

            assert result.success is False
            assert "Exact NVIDIA executable binding could not be confirmed" in (result.error or "")
            handler.apply.assert_not_called()
        finally:
            del ProfileApplier.PROFILES["test-preflight-profile"]

    @patch("abso.core.applier.MultiMonitorDetector.detect")
    def test_apply_profile_auto_disables_blocking_overlays_for_strict_profile(
        self,
        mock_multimon_detect,
    ):
        """Strict overlay-free profiles should remediate known overlays before blocking."""
        mock_multimon_detect.side_effect = [
            MultiMonitorResult(
                environment=DisplayEnvironment(
                    monitor_count=2,
                    detected_overlays=["Discord Overlay", "Xbox Game Bar"],
                ),
                warnings=[],
            ),
            MultiMonitorResult(
                environment=DisplayEnvironment(
                    monitor_count=2,
                    detected_overlays=[],
                ),
                warnings=[],
            ),
        ]

        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.display_path_requirements.require_overlay_free_path = True
        mock_profile.auto_disable_blocking_overlays = True
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier(skip_capability_checks=True)
        applier._profiles["strict-profile"] = mock_profile
        ProfileApplier.PROFILES["strict-profile"] = type(mock_profile)

        with patch.object(applier._overlay_manager, "remediate") as mock_remediate:
            mock_remediate.return_value.notices = [
                "ABSO disabled Discord Overlay automatically so the strict fullscreen path could be applied."
            ]
            mock_remediate.return_value.warnings = []
            mock_remediate.return_value.attempted_labels = [
                "Discord Overlay",
                "Xbox Game Bar",
            ]

            try:
                result = applier.apply_profile("strict-profile")

                assert result.success is True
                assert any("Discord Overlay" in notice for notice in result.notices)
                mock_remediate.assert_called_once_with(["Discord Overlay", "Xbox Game Bar"])
            finally:
                del ProfileApplier.PROFILES["strict-profile"]

    @patch("abso.core.applier.MultiMonitorDetector.detect")
    def test_validate_profile_prerequisites_caches_overlay_remediation_for_transaction_flow(
        self,
        mock_multimon_detect,
    ):
        """Transaction pre-validation should preserve remediation notices for the later apply."""
        mock_multimon_detect.side_effect = [
            MultiMonitorResult(
                environment=DisplayEnvironment(
                    monitor_count=2,
                    detected_overlays=["Discord Overlay"],
                ),
                warnings=[],
            ),
            MultiMonitorResult(
                environment=DisplayEnvironment(
                    monitor_count=2,
                    detected_overlays=[],
                ),
                warnings=[],
            ),
        ]

        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.profile_id = "strict-profile"
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.display_path_requirements.require_overlay_free_path = True
        mock_profile.auto_disable_blocking_overlays = True
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier(skip_capability_checks=True)
        applier._profiles["strict-profile"] = mock_profile
        ProfileApplier.PROFILES["strict-profile"] = type(mock_profile)

        with patch.object(applier._overlay_manager, "remediate") as mock_remediate:
            mock_remediate.return_value.notices = [
                "ABSO disabled Discord Overlay automatically so the strict fullscreen path could be applied."
            ]
            mock_remediate.return_value.warnings = []
            mock_remediate.return_value.attempted_labels = ["Discord Overlay"]

            try:
                error = applier.validate_profile_prerequisites("strict-profile")
                assert error is None

                result = applier.apply_profile("strict-profile")
                assert result.success is True
                assert any("Discord Overlay" in notice for notice in result.notices)
                assert mock_remediate.call_count == 1
            finally:
                del ProfileApplier.PROFILES["strict-profile"]


class TestGenerateReport:
    """Tests for generate_report method."""

    def test_generate_report_creates_file(self, tmp_path):
        """Test generate_report creates markdown file."""
        mock_profile = MagicMock()
        mock_profile.generate_in_game_report.return_value = "# Report\nContent"

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            report_path = applier.generate_report("test-profile", tmp_path)

            assert report_path.exists()
            assert report_path.suffix == ".md"
            assert "Report" in report_path.read_text()
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_generate_report_unknown_profile(self, tmp_path):
        """Test generate_report raises for unknown profile."""
        applier = ProfileApplier()

        with pytest.raises(ProfileNotFoundError):
            applier.generate_report("nonexistent", tmp_path)


class TestListProfiles:
    """Tests for list_profiles method."""

    def test_list_profiles_returns_all(self):
        """Test list_profiles returns all registered profiles."""
        applier = ProfileApplier()
        profiles = applier.list_profiles()

        assert len(profiles) >= 4  # At least the 4 default profiles
        profile_ids = [p["id"] for p in profiles]
        assert "slippi-melee" in profile_ids
        assert "cod-bo7" not in profile_ids

    def test_list_profiles_structure(self):
        """Test list_profiles returns correct structure."""
        applier = ProfileApplier()
        profiles = applier.list_profiles()

        for profile in profiles:
            assert "id" in profile
            assert "display_name" in profile
            assert "description" in profile
            assert "optimization_target" in profile


class TestRealProfiles:
    """Integration tests with real profile classes."""

    def test_slippi_melee_profile_loads(self):
        """Test Slippi Melee profile can be loaded."""
        applier = ProfileApplier()
        profile = applier._get_profile("slippi-melee")

        assert profile.profile_id == "slippi-melee"
        assert "Melee" in profile.display_name

    def test_diablo4_profile_loads(self):
        """Test Diablo 4 profile can be loaded."""
        applier = ProfileApplier()
        profile = applier._get_profile("diablo4")

        assert profile.profile_id == "diablo4"
        assert "Diablo" in profile.display_name

    def test_rivals2_profile_loads(self):
        """Legacy Rivals 2 id should canonicalize to the merged no-sync profile."""
        applier = ProfileApplier()
        profile = applier._get_profile("rivals2")

        assert profile.profile_id == "rivals2-nosync"

    def test_rivals2_300hz_alias_loads_nosync_profile(self):
        """Retired 300 Hz alias should canonicalize to the merged no-sync profile."""
        applier = ProfileApplier()
        profile = applier._get_profile("rivals2-300hz-max")

        assert profile.profile_id == "rivals2-nosync"

    def test_retired_online_gsync_hdr_id_loads_merged_gsync_hdr(self):
        """The pre-merge daily-driver ID must keep resolving (live tray configs use it)."""
        applier = ProfileApplier()
        profile = applier._get_profile("rivals2-online-gsync-hdr")

        assert profile.profile_id == "rivals2-gsync-hdr"


class TestProfileOverrides:
    """Tests for profile override functionality via config."""

    def test_merge_overrides_nvidia(self):
        """Test _merge_overrides with NVIDIA overrides."""
        from abso.core.config import ProfileOverrides

        applier = ProfileApplier()
        base_settings = {"preset": "balanced", "vsync": False}
        overrides = ProfileOverrides(nvidia={"preset": "minimum_latency"})

        result = applier._merge_overrides(base_settings, "NvidiaSettingsHandler", overrides)

        assert result["preset"] == "minimum_latency"  # Override applied
        assert result["vsync"] is False  # Base setting preserved

    def test_merge_overrides_windows(self):
        """Test _merge_overrides with Windows overrides."""
        from abso.core.config import ProfileOverrides

        applier = ProfileApplier()
        base_settings = {"game_mode": True, "game_bar": False}
        overrides = ProfileOverrides(windows={"game_bar": True})

        result = applier._merge_overrides(base_settings, "WindowsSettingsHandler", overrides)

        assert result["game_mode"] is True  # Base setting preserved
        assert result["game_bar"] is True  # Override applied

    def test_merge_overrides_graphics(self):
        """Test _merge_overrides with graphics compositor overrides."""
        from abso.core.config import ProfileOverrides

        applier = ProfileApplier()
        base_settings = {
            "disable_global_fso": False,
            "disable_mpo": False,
        }
        overrides = ProfileOverrides(graphics={"disable_mpo": True})

        result = applier._merge_overrides(base_settings, "GraphicsSettingsHandler", overrides)

        assert result["disable_global_fso"] is False  # Base setting preserved
        assert result["disable_mpo"] is True  # Override applied

    def test_merge_overrides_registry_nested_values(self):
        """Registry overrides should preserve nested defaults unless explicitly replaced."""
        from abso.core.config import ProfileOverrides

        applier = ProfileApplier()
        base_settings = {
            "game_priority": {
                "gpu_priority": 8,
                "priority": 2,
                "scheduling_category": "Medium",
            },
            "system_responsiveness": 20,
        }
        overrides = ProfileOverrides(
            registry={
                "game_priority": {
                    "priority": 6,
                },
            }
        )

        result = applier._merge_overrides(
            base_settings,
            "RegistrySettingsHandler",
            overrides,
        )

        assert result["game_priority"] == {
            "gpu_priority": 8,
            "priority": 6,
            "scheduling_category": "Medium",
        }
        assert result["system_responsiveness"] == 20

        result["game_priority"]["gpu_priority"] = 1
        assert base_settings["game_priority"]["gpu_priority"] == 8

    def test_merge_overrides_no_handler_match(self):
        """Test _merge_overrides returns original settings for unknown handler."""
        from abso.core.config import ProfileOverrides

        applier = ProfileApplier()
        base_settings = {"some_setting": True}
        overrides = ProfileOverrides(nvidia={"preset": "minimum_latency"})

        result = applier._merge_overrides(base_settings, "UnknownHandler", overrides)

        # Should return original settings unchanged
        assert result == base_settings

    def test_merge_overrides_empty_overrides(self):
        """Test _merge_overrides with empty overrides returns original."""
        from abso.core.config import ProfileOverrides

        applier = ProfileApplier()
        base_settings = {"preset": "balanced"}
        overrides = ProfileOverrides()

        result = applier._merge_overrides(base_settings, "NvidiaSettingsHandler", overrides)

        assert result == base_settings

    def test_apply_with_disabled_handler(self, tmp_path):
        """Test profile application skips disabled handlers."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "WindowsSettingsHandler"
        mock_handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [mock_handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        # Create a config that disables WindowsSettingsHandler
        config_yaml = tmp_path / "abso.yaml"
        config_yaml.write_text("""
disabled_handlers:
  - WindowsSettingsHandler
""")

        try:
            with patch("abso.core.applier.ConfigManager") as mock_config_manager:
                mock_config = MagicMock()
                mock_config.disabled_handlers = ["WindowsSettingsHandler"]
                mock_config_manager.return_value.config = mock_config
                mock_config_manager.return_value.is_handler_disabled.return_value = True
                mock_config_manager.return_value.get_profile_overrides.return_value = None

                result = applier.apply_profile("test-profile")

                # Handler should not have been called
                mock_handler.apply.assert_not_called()
                assert result.success is True
                assert "WindowsSettingsHandler" not in result.applied_settings
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_with_profile_overrides(self):
        """Test profile application applies overrides from config."""
        from abso.core.config import ProfileOverrides

        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "NvidiaSettingsHandler"
        mock_handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.requires_confirmed_vrr_support = False
        mock_profile.get_handlers.return_value = [mock_handler]
        mock_profile.get_settings.return_value = {"preset": "balanced"}
        mock_profile.has_in_game_settings.return_value = False
        mock_profile.validate_settings.return_value = []

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            with patch("abso.core.applier.ConfigManager") as mock_config_manager:
                mock_config = MagicMock()
                mock_config.disabled_handlers = []
                mock_config_manager.return_value.config = mock_config
                mock_config_manager.return_value.is_handler_disabled.return_value = False
                mock_config_manager.return_value.get_profile_overrides.return_value = (
                    ProfileOverrides(nvidia={"preset": "minimum_latency"})
                )

                result = applier.apply_profile("test-profile")

                # Handler should have been called with merged settings
                mock_handler.apply.assert_called_once()
                called_settings = mock_handler.apply.call_args[0][0]
                assert called_settings["preset"] == "minimum_latency"
                assert result.success is True
        finally:
            del ProfileApplier.PROFILES["test-profile"]
