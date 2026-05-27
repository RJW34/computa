"""Tests for game profiles."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from abso.profiles import get_all_profiles
from abso.profiles.deadlock import (
    DeadlockGSyncHDRProfile,
    DeadlockGSyncProfile,
    DeadlockHDRProfile,
    DeadlockProfile,
)
from abso.profiles.diablo4 import Diablo4Profile, Diablo4SDRProfile
from abso.profiles.fortnite import FortniteHDRProfile, FortniteProfile
from abso.profiles.marvel_rivals import MarvelRivalsHDRProfile, MarvelRivalsSDRProfile
from abso.profiles.overwatch2 import (
    Overwatch2GSyncCaptureProfile,
    Overwatch2GSyncHDRCaptureProfile,
    Overwatch2GSyncHDRProfile,
    Overwatch2GSyncProfile,
    Overwatch2NoSyncHDRProfile,
    Overwatch2Profile,
)
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.productivity_oled import ProductivityHDRProfile, ProductivityProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_gsync import (
    Rivals2GSyncHDRProfile,
    Rivals2GSyncProfile,
    Rivals2OnlineGSyncHDRProfile,
    Rivals2OnlineGSyncProfile,
)
from abso.profiles.rivals2_offline import Rivals2OfflineHDRProfile, Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineHDRProfile, Rivals2OnlineProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityHDRProfile,
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeHDRProfile,
    SlippiMeleeProfile,
    SlippiMeleeUniversalHDRProfile,
    SlippiMeleeUniversalProfile,
)


class TestProfileLoading:
    """Test that profiles can be loaded without import errors."""

    def test_slippi_profile_loads(self):
        """Test SlippiMeleeProfile can be instantiated."""
        profile = SlippiMeleeProfile()
        assert profile.profile_id == "slippi-melee"
        assert profile.display_name == "Super Smash Bros. Melee (Slippi)"

    def test_slippi_console_parity_profile_loads(self):
        """Test SlippiMeleeConsoleParityProfile can be instantiated."""
        profile = SlippiMeleeConsoleParityProfile()
        assert profile.profile_id == "slippi-melee-console-parity"
        assert "Console-Parity" in profile.display_name

    def test_slippi_universal_profile_loads(self):
        """Test SlippiMeleeUniversalProfile can be instantiated."""
        profile = SlippiMeleeUniversalProfile()
        assert profile.profile_id == "slippi-melee-universal"
        assert "Universal" in profile.display_name

    def test_slippi_hdr_profiles_load(self):
        """Slippi should expose HDR siblings for all three SDR variants."""
        base_hdr = SlippiMeleeHDRProfile()
        universal_hdr = SlippiMeleeUniversalHDRProfile()
        parity_hdr = SlippiMeleeConsoleParityHDRProfile()

        assert base_hdr.profile_id == "slippi-melee-hdr"
        assert "HDR" in base_hdr.display_name
        assert base_hdr.is_sdr_only is False

        assert universal_hdr.profile_id == "slippi-melee-universal-hdr"
        assert "Universal HDR" in universal_hdr.display_name
        assert universal_hdr.is_sdr_only is False

        assert parity_hdr.profile_id == "slippi-melee-console-parity-hdr"
        assert "Console-Parity HDR" in parity_hdr.display_name
        assert parity_hdr.is_sdr_only is False

    def test_diablo4_profile_loads(self):
        """Diablo 4 should expose explicit HDR and SDR variants."""
        hdr = Diablo4Profile()
        sdr = Diablo4SDRProfile()
        assert hdr.profile_id == "diablo4"
        assert hdr.display_name == "Diablo 4 - HDR"
        assert sdr.profile_id == "diablo4-sdr"
        assert sdr.display_name == "Diablo 4 - SDR"

    def test_productivity_profiles_use_stable_nvidia_identity(self):
        """Productivity SDR/HDR siblings should not rely on auto-generated NVIDIA profile names."""
        sdr = ProductivityProfile()
        hdr = ProductivityHDRProfile()
        assert (
            sdr.get_settings("NvidiaSettingsHandler")["profile_name"]
            == "Productivity (SDR)"
        )
        assert (
            hdr.get_settings("NvidiaSettingsHandler")["profile_name"]
            == "Productivity (HDR)"
        )

    def test_fortnite_profiles_load(self):
        """Fortnite should expose explicit SDR and HDR variants."""
        sdr = FortniteProfile()
        hdr = FortniteHDRProfile()
        assert sdr.profile_id == "fortnite"
        assert sdr.display_name == "Fortnite - SDR"
        assert hdr.profile_id == "fortnite-hdr"
        assert hdr.display_name == "Fortnite - HDR"

    def test_pokemon_auto_chess_profile_loads(self):
        """Test PokemonAutoChessProfile can be instantiated."""
        profile = PokemonAutoChessProfile()
        assert profile.profile_id == "pokemon-auto-chess"
        assert profile.display_name == "Pokemon Auto Chess"

    def test_overwatch2_profiles_load(self):
        """Test all Overwatch 2 profiles can be instantiated."""
        no_sync = Overwatch2Profile()
        no_sync_hdr = Overwatch2NoSyncHDRProfile()
        gsync = Overwatch2GSyncProfile()
        gsync_hdr = Overwatch2GSyncHDRProfile()
        gsync_capture = Overwatch2GSyncCaptureProfile()
        gsync_hdr_capture = Overwatch2GSyncHDRCaptureProfile()
        assert no_sync.profile_id == "overwatch2"
        assert no_sync.display_name == "Overwatch 2 - No Sync SDR"
        assert no_sync.is_sdr_only is True
        assert no_sync_hdr.profile_id == "overwatch2-hdr"
        assert no_sync_hdr.display_name == "Overwatch 2 - No Sync HDR"
        assert no_sync_hdr.is_sdr_only is False
        # HDR no-sync reuses the no-sync NVIDIA preset and leaves VRR off.
        assert (
            no_sync_hdr.get_settings("NvidiaSettingsHandler")["preset"]
            == "reflex_no_sync"
        )
        ow2_hdr = no_sync_hdr.get_settings("OW2ConfigHandler")
        assert ow2_hdr["hdr"] is True
        assert ow2_hdr["window_mode"] == 0
        assert ow2_hdr["fullscreen_window"] is False
        assert ow2_hdr["fullscreen_window_enabled"] is True
        assert ow2_hdr["windowed_fullscreen"] is False
        ow2_capture = gsync_capture.get_settings("OW2ConfigHandler")
        assert ow2_capture["window_mode"] == 1
        assert ow2_capture["fullscreen_window"] is False
        assert ow2_capture["fullscreen_window_enabled"] is False
        assert ow2_capture["windowed_fullscreen"] is True
        windows_hdr = no_sync_hdr.get_settings("WindowsSettingsHandler")
        assert windows_hdr["hdr"] is True
        assert windows_hdr["auto_hdr"] is False
        assert gsync.profile_id == "overwatch2-gsync"
        assert gsync_hdr.profile_id == "overwatch2-gsync-hdr"
        assert gsync_capture.profile_id == "overwatch2-gsync-capture"
        assert gsync_hdr_capture.profile_id == "overwatch2-gsync-hdr-capture"
        assert gsync.mixed_refresh_safe_fallback_profile_id == "overwatch2-gsync-capture"
        assert (
            gsync_hdr.mixed_refresh_safe_fallback_profile_id
            == "overwatch2-gsync-hdr-capture"
        )

    def test_deadlock_profiles_load(self):
        """Deadlock should expose the full GSYNC x HDR matrix (4 variants)."""
        no_sync = DeadlockProfile()
        no_sync_hdr = DeadlockHDRProfile()
        gsync = DeadlockGSyncProfile()
        gsync_hdr = DeadlockGSyncHDRProfile()

        assert no_sync.profile_id == "deadlock"
        assert no_sync.display_name == "Deadlock - No Sync SDR"
        assert no_sync.is_sdr_only is True

        assert no_sync_hdr.profile_id == "deadlock-hdr"
        assert no_sync_hdr.display_name == "Deadlock - No Sync HDR"
        assert no_sync_hdr.is_sdr_only is False

        assert gsync.profile_id == "deadlock-gsync"
        assert gsync.display_name == "Deadlock - GSYNC SDR"
        assert gsync.is_sdr_only is True
        assert gsync.requires_confirmed_vrr_support is True

        assert gsync_hdr.profile_id == "deadlock-gsync-hdr"
        assert gsync_hdr.display_name == "Deadlock - GSYNC HDR"
        assert gsync_hdr.is_sdr_only is False
        assert gsync_hdr.requires_confirmed_vrr_support is True
        assert gsync.mixed_refresh_safe_fallback_profile_id == "deadlock"
        assert gsync_hdr.mixed_refresh_safe_fallback_profile_id == "deadlock-hdr"

    def test_deadlock_detection_tracks_aliases_but_binding_targets_current_binary(self):
        """Deadlock detection can be broad; strict NVIDIA binding must stay narrow."""
        for profile_cls in (
            DeadlockProfile,
            DeadlockHDRProfile,
            DeadlockGSyncProfile,
            DeadlockGSyncHDRProfile,
        ):
            profile = profile_cls()
            assert "project8.exe" in profile.executable_hints
            assert "deadlock.exe" in profile.executable_hints
            assert profile.nvidia_binding_executables == ["project8.exe"]

    def test_deadlock_no_sync_nvidia_settings(self):
        """Deadlock no-sync variants should disable global VRR and use reflex_no_sync preset."""
        for profile_cls in (DeadlockProfile, DeadlockHDRProfile):
            profile = profile_cls()
            settings = profile.get_settings("NvidiaSettingsHandler")
            assert settings["preset"] == "reflex_no_sync", profile_cls.__name__
            assert settings["profile_name"] == "Deadlock", profile_cls.__name__
            assert settings["global_vrr_mode"] == "off", profile_cls.__name__

    def test_deadlock_gsync_nvidia_settings(self):
        """Deadlock G-SYNC variants should run reflex_gsync on the strict VRR path."""
        for profile_cls in (DeadlockGSyncProfile, DeadlockGSyncHDRProfile):
            profile = profile_cls()
            settings = profile.get_settings("NvidiaSettingsHandler")
            assert settings["preset"] == "reflex_gsync", profile_cls.__name__
            assert settings["profile_name"] == "Deadlock", profile_cls.__name__
            assert settings["auto_vrr_fps_cap"] is True, profile_cls.__name__
            assert settings["global_vrr_mode"] == "fullscreen_only", profile_cls.__name__

    def test_deadlock_hdr_variants_enable_hdr_and_disable_auto_hdr(self):
        """Both HDR variants should enable native HDR with Auto HDR off and ACM disabled."""
        for profile_cls in (DeadlockHDRProfile, DeadlockGSyncHDRProfile):
            profile = profile_cls()
            win = profile.get_settings("WindowsSettingsHandler")
            graphics = profile.get_settings("GraphicsSettingsHandler")
            color = profile.get_settings("ColorProfileSettingsHandler")
            assert win["hdr"] is True, profile_cls.__name__
            assert win["auto_hdr"] is False, profile_cls.__name__
            assert win["advanced_color"] is True, profile_cls.__name__
            assert graphics["disable_auto_color_management"] is True, profile_cls.__name__
            assert color["icc_profile"] == "native", profile_cls.__name__

    def test_deadlock_sdr_variants_disable_hdr(self):
        """SDR variants should keep HDR off and use the sRGB color path."""
        for profile_cls in (DeadlockProfile, DeadlockGSyncProfile):
            profile = profile_cls()
            win = profile.get_settings("WindowsSettingsHandler")
            color = profile.get_settings("ColorProfileSettingsHandler")
            assert win["hdr"] is False, profile_cls.__name__
            assert win["auto_hdr"] is False, profile_cls.__name__
            assert color["icc_profile"] == "srgb", profile_cls.__name__

    def test_deadlock_variants_disable_fso_for_both_binaries(self):
        """Every Deadlock variant runs exclusive fullscreen; FSO must be disabled per-exe."""
        for profile_cls in (
            DeadlockProfile,
            DeadlockHDRProfile,
            DeadlockGSyncProfile,
            DeadlockGSyncHDRProfile,
        ):
            profile = profile_cls()
            flags = profile.fullscreen_optimizations_per_exe
            assert flags.get("project8.exe") is True, profile_cls.__name__
            assert flags.get("deadlock.exe") is True, profile_cls.__name__
            registry_settings = profile.get_settings("RegistrySettingsHandler")
            assert registry_settings["fullscreen_optimizations"]["project8.exe"] is True
            assert registry_settings["fullscreen_optimizations"]["deadlock.exe"] is True

    def test_deadlock_gsync_variants_inherit_strict_display_path_contract(self):
        """G-SYNC Deadlock variants should match OW2/Marvel Rivals strict fullscreen contract."""
        for profile_cls in (DeadlockGSyncProfile, DeadlockGSyncHDRProfile):
            profile = profile_cls()
            assert profile.uses_fullscreen_only_vrr_path is True, profile_cls.__name__
            assert profile.display_path_requirements.require_overlay_free_path is True
            assert profile.requires_exact_nvidia_binding is True, profile_cls.__name__
            assert profile.auto_disable_blocking_overlays is True, profile_cls.__name__

    def test_deadlock_is_system_only_until_native_config_handler_lands(self):
        """ABSO does not yet write Deadlock's Source 2 config; scope should reflect that."""
        for profile_cls in (
            DeadlockProfile,
            DeadlockHDRProfile,
            DeadlockGSyncProfile,
            DeadlockGSyncHDRProfile,
        ):
            profile = profile_cls()
            assert profile.application_scope == "system_only", profile_cls.__name__
            assert profile.enforces_reflex_in_config is False, profile_cls.__name__
            assert profile.requires_reflex is True, profile_cls.__name__

    def test_marvel_rivals_profiles_load(self):
        """Test both Marvel Rivals variants can be instantiated."""
        sdr = MarvelRivalsSDRProfile()
        hdr = MarvelRivalsHDRProfile()
        assert sdr.profile_id == "marvel-rivals-sdr"
        assert hdr.profile_id == "marvel-rivals-hdr"
        assert "Marvel Rivals" in sdr.display_name
        assert "Marvel Rivals" in hdr.display_name

    def test_rivals2_consolidated_profiles_load(self):
        """The canonical Rivals 2 matrix should expose SDR and HDR lanes."""
        offline = Rivals2OfflineProfile()
        offline_hdr = Rivals2OfflineHDRProfile()
        online = Rivals2OnlineProfile()
        online_hdr = Rivals2OnlineHDRProfile()
        gsync = Rivals2GSyncProfile()
        gsync_hdr = Rivals2GSyncHDRProfile()
        online_gsync = Rivals2OnlineGSyncProfile()
        online_gsync_hdr = Rivals2OnlineGSyncHDRProfile()

        assert offline.profile_id == "rivals2-offline"
        assert offline.is_sdr_only is True
        assert offline_hdr.profile_id == "rivals2-offline-hdr"
        assert offline_hdr.is_sdr_only is False
        assert online.profile_id == "rivals2-online"
        assert online.is_sdr_only is True
        assert online_hdr.profile_id == "rivals2-online-hdr"
        assert online_hdr.is_sdr_only is False
        assert gsync.profile_id == "rivals2-gsync"
        assert gsync.is_sdr_only is True
        assert gsync_hdr.profile_id == "rivals2-gsync-hdr"
        assert gsync_hdr.is_sdr_only is False
        assert online_gsync.profile_id == "rivals2-online-gsync"
        assert online_gsync.is_sdr_only is True
        assert online_gsync_hdr.profile_id == "rivals2-online-gsync-hdr"
        assert online_gsync_hdr.is_sdr_only is False
        assert gsync.mixed_refresh_safe_fallback_profile_id == "rivals2-offline"
        assert gsync_hdr.mixed_refresh_safe_fallback_profile_id == "rivals2-offline-hdr"
        assert online_gsync.mixed_refresh_safe_fallback_profile_id == "rivals2-online"
        assert (
            online_gsync_hdr.mixed_refresh_safe_fallback_profile_id
            == "rivals2-online-hdr"
        )

    def test_profiles_expose_canonical_nvidia_binding_executables(self):
        """NVIDIA binding should target canonical binaries, not broad detection aliases."""
        rivals = Rivals2OnlineGSyncProfile()
        marvel = MarvelRivalsHDRProfile()
        slippi = SlippiMeleeProfile()

        assert rivals.nvidia_binding_executables == ["Rivals2-Win64-Shipping.exe"]
        assert rivals.allow_unverified_nvidia_profile_reuse is True
        assert marvel.nvidia_binding_executables == ["Marvel-Win64-Shipping.exe"]
        assert slippi.nvidia_binding_executables == ["Slippi Dolphin.exe"]
        assert slippi.allow_unverified_nvidia_profile_reuse is True


class TestProfileHandlers:
    """Test profile handler methods."""

    def test_slippi_get_handlers_returns_list(self):
        """Test SlippiMeleeProfile.get_handlers returns handlers."""
        profile = SlippiMeleeProfile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0

        # Check handler class names
        handler_names = [h.__class__.__name__ for h in handlers]
        assert "WindowsSettingsHandler" in handler_names
        assert "NvidiaSettingsHandler" in handler_names
        assert "NetworkSettingsHandler" in handler_names

    def test_diablo4_get_handlers_returns_list(self):
        """Test Diablo4Profile.get_handlers returns handlers."""
        profile = Diablo4Profile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0
        handler_names = [h.__class__.__name__ for h in handlers]
        assert "Diablo4ConfigHandler" in handler_names

    def test_fortnite_get_handlers_returns_list(self):
        """Fortnite variants should include explicit config enforcement."""
        profile = FortniteProfile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0
        handler_names = [h.__class__.__name__ for h in handlers]
        assert "FortniteConfigHandler" in handler_names

    def test_marvel_rivals_get_handlers_returns_list(self):
        """Marvel Rivals variants should include explicit config enforcement."""
        profile = MarvelRivalsSDRProfile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0
        handler_names = [h.__class__.__name__ for h in handlers]
        assert "MarvelRivalsConfigHandler" in handler_names

    def test_pokemon_auto_chess_get_handlers_returns_list(self):
        """Test PokemonAutoChessProfile.get_handlers returns handlers."""
        profile = PokemonAutoChessProfile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0

        handler_names = [h.__class__.__name__ for h in handlers]
        assert "WindowsSettingsHandler" in handler_names
        assert "NvidiaSettingsHandler" in handler_names
        assert "NetworkSettingsHandler" in handler_names

    def test_rivals2_online_includes_game_config_handler(self):
        """Online profile should include the Rivals2ConfigHandler for INI tuning."""
        profile = Rivals2OnlineProfile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "Rivals2ConfigHandler" in handler_names

    def test_rivals2_base_profile_includes_game_config_guarded_handler(self):
        """Base Rivals2 profile includes config handler for explicit game INI tuning."""
        profile = Rivals2OfflineProfile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "Rivals2ConfigHandler" in handler_names


class TestProfileSettings:
    """Test profile settings retrieval."""

    def test_slippi_windows_settings(self):
        """Test SlippiMeleeProfile returns Windows settings."""
        profile = SlippiMeleeProfile()
        settings = profile.get_settings("WindowsSettingsHandler")

        assert settings["game_mode"] is True
        assert settings["game_bar"] is False
        assert settings["game_dvr"] is False

    def test_slippi_nvidia_settings(self):
        """Test SlippiMeleeProfile returns Nvidia settings for minimum latency.

        LLM is set to 'on' (not 'ultra') per updated research - Ultra optional but test both.
        """
        profile = SlippiMeleeProfile()
        with patch.object(profile, "_detect_dolphin_backend", return_value="dx11"):
            settings = profile.get_settings("NvidiaSettingsHandler")

        # Minimum latency settings per rollback.md canonical spec
        assert settings["low_latency_mode"] == "on"  # On recommended; Ultra optional
        assert settings["vsync"] == "off"
        assert settings["vrr_app_override"] == "force_off"
        assert settings["threaded_optimization"] == "off"

    def test_slippi_nvidia_settings_vulkan_disables_llm(self):
        """Vulkan backend should disable driver LLM."""
        profile = SlippiMeleeProfile()
        with patch.object(profile, "_detect_dolphin_backend", return_value="vulkan"):
            settings = profile.get_settings("NvidiaSettingsHandler")
        assert settings["low_latency_mode"] == "off"

    def test_slippi_nvidia_settings_dx12_keeps_llm_on(self):
        """DX12 backend should keep LLM enabled on current NVIDIA drivers."""
        profile = SlippiMeleeProfile()
        with patch.object(profile, "_detect_dolphin_backend", return_value="dx12"):
            settings = profile.get_settings("NvidiaSettingsHandler")
        assert settings["low_latency_mode"] == "on"

    def test_slippi_windows_settings_dx11_disables_hags(self):
        """DX11 backend should disable HAGS for stability."""
        profile = SlippiMeleeProfile()
        with patch.object(profile, "_detect_dolphin_backend", return_value="dx11"):
            settings = profile.get_settings("WindowsSettingsHandler")
        assert settings["hags"] is False

    def test_slippi_universal_windows_settings_keep_hags_on(self):
        """Universal Slippi profile should keep HAGS on for no-reboot reapply."""
        profile = SlippiMeleeUniversalProfile()
        with patch.object(profile, "_detect_dolphin_backend", return_value="dx11"):
            settings = profile.get_settings("WindowsSettingsHandler")
        assert settings["hags"] is True

    def test_slippi_competitive_dolphin_settings_clear_vrr_presentation_flags(self):
        """Competitive Slippi should explicitly clear VRR-lab presentation toggles."""
        profile = SlippiMeleeProfile()
        settings = profile.get_settings("DolphinConfigHandler")
        assert settings["rush_presentation"] == "False"
        assert settings["smooth_presentation"] == "False"

    def test_slippi_console_parity_nvidia_settings(self):
        """Console-parity Slippi should bias for pacing consistency over minimum latency."""
        profile = SlippiMeleeConsoleParityProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["low_latency_mode"] == "off"
        assert settings["vsync"] == "on"
        assert settings["vrr_app_override"] == "force_off"
        assert settings["max_frame_rate"] == "off"

    def test_slippi_console_parity_windows_refresh(self):
        """Console-parity profile should force 60 Hz desktop cadence."""
        profile = SlippiMeleeConsoleParityProfile()
        settings = profile.get_settings("WindowsSettingsHandler")
        assert settings["refresh_rate"] == 60

    def test_slippi_hdr_variants_enable_hdr_and_disable_acm(self):
        """All three Slippi HDR siblings enable native HDR + WCG, disable Auto HDR / ACM,
        and use the native ICC path (matches the OW2-HDR convention; empirically the
        sRGB clamp looked MORE washed-out on the real LG-OLED + QD-OLED hardware)."""
        for profile_cls in (
            SlippiMeleeHDRProfile,
            SlippiMeleeUniversalHDRProfile,
            SlippiMeleeConsoleParityHDRProfile,
        ):
            profile = profile_cls()
            win = profile.get_settings("WindowsSettingsHandler")
            graphics = profile.get_settings("GraphicsSettingsHandler")
            color = profile.get_settings("ColorProfileSettingsHandler")
            assert win["hdr"] is True, profile_cls.__name__
            assert win["advanced_color"] is True, profile_cls.__name__
            assert win["auto_hdr"] is False, profile_cls.__name__
            assert win["sdr_white_level_nits"] == 200, profile_cls.__name__
            assert graphics["disable_auto_color_management"] is True, profile_cls.__name__
            assert color["icc_profile"] == "native", profile_cls.__name__

    def test_slippi_hdr_variants_preserve_sdr_latency_choices(self):
        """HDR variants must inherit every latency choice from their SDR parents unchanged."""
        # No-sync competitive: backend-aware LLM, VSync OFF, exclusive fullscreen
        base_sdr = SlippiMeleeProfile()
        base_hdr = SlippiMeleeHDRProfile()
        for handler in (
            "NvidiaSettingsHandler",
            "DolphinConfigHandler",
            "RegistrySettingsHandler",
            "PowerSettingsHandler",
        ):
            assert base_hdr.get_settings(handler) == base_sdr.get_settings(handler), handler

        # Universal: HAGS stays True regardless of backend on the HDR sibling too
        universal_hdr = SlippiMeleeUniversalHDRProfile()
        with patch.object(universal_hdr, "_detect_dolphin_backend", return_value="dx11"):
            win = universal_hdr.get_settings("WindowsSettingsHandler")
        assert win["hags"] is True
        assert win["hdr"] is True

        # Console-parity: 60 Hz + VSync cadence is preserved
        parity_hdr = SlippiMeleeConsoleParityHDRProfile()
        parity_win = parity_hdr.get_settings("WindowsSettingsHandler")
        parity_nv = parity_hdr.get_settings("NvidiaSettingsHandler")
        assert parity_win["refresh_rate"] == 60
        assert parity_win["hdr"] is True
        assert parity_nv["vsync"] == "on"
        assert parity_nv["low_latency_mode"] == "off"

    def test_slippi_hdr_in_game_guidance_includes_paper_white(self):
        """HDR profiles must surface the SDR-in-HDR paper-white setup note."""
        for profile_cls in (
            SlippiMeleeHDRProfile,
            SlippiMeleeUniversalHDRProfile,
            SlippiMeleeConsoleParityHDRProfile,
        ):
            profile = profile_cls()
            guidance = profile.get_in_game_settings()
            settings_named = {entry.get("setting") for entry in guidance}
            assert "SDR content brightness" in settings_named, profile_cls.__name__
            assert "Use HDR (Settings > System > Display)" in settings_named, profile_cls.__name__

    def test_diablo4_nvidia_settings(self):
        """Test Diablo4Profile returns Nvidia settings with Reflex preset (LLM OFF)."""
        profile = Diablo4Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        # Diablo 4 has native Reflex — uses vrr_diablo4 preset (LLM OFF).
        # Driver-side FPS cap is intentionally OFF; the in-game Foreground FPS
        # limiter is the single VRR cap per Blur Busters G-SYNC 101.
        assert settings["preset"] == "vrr_diablo4"
        assert settings["profile_name"] == "Diablo IV"
        assert settings["auto_vrr_fps_cap"] is False

    def test_diablo4_variants_drive_native_game_config(self):
        """Diablo IV variants should enforce the matching LocalPrefs path."""
        hdr = Diablo4Profile()
        sdr = Diablo4SDRProfile()

        hdr_windows = hdr.get_settings("WindowsSettingsHandler")
        hdr_config = hdr.get_settings("Diablo4ConfigHandler")
        sdr_windows = sdr.get_settings("WindowsSettingsHandler")
        sdr_config = sdr.get_settings("Diablo4ConfigHandler")

        assert hdr.requires_reflex is True
        assert hdr_windows["hdr"] is True
        assert hdr_config["window_mode"] == 1
        assert hdr_config["reflex"] is True
        assert hdr_config["auto_refresh_rate"] is True
        # In-game foreground cap at refresh - 3 is the single VRR limiter.
        assert hdr_config["auto_vrr_fps_cap"] is True
        assert "limit_foreground_fps" not in hdr_config
        assert "foreground_fps_limit" not in hdr_config
        assert hdr_config["hdr_output"] is True

        assert sdr_windows["hdr"] is False
        assert sdr_config["window_mode"] == 1
        assert sdr_config["auto_vrr_fps_cap"] is True
        assert sdr_config["hdr_output"] is False

    def test_pokemon_auto_chess_nvidia_settings(self):
        """Test PokemonAutoChessProfile returns explicit Nvidia settings."""
        profile = PokemonAutoChessProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        # WebGL benefits from low latency settings with VSync disabled
        assert settings["low_latency_mode"] == "on"
        assert settings["vsync"] == "off"

    def test_overwatch2_no_sync_nvidia_settings(self):
        """No-sync Overwatch profile should explicitly disable VRR/G-SYNC."""
        profile = Overwatch2Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")
        assert settings["preset"] == "reflex_no_sync"
        assert settings["profile_name"] == "Overwatch 2"
        assert settings["global_vrr_mode"] == "off"

    def test_overwatch2_gsync_nvidia_settings(self):
        """G-SYNC Overwatch profile should use reflex VRR preset."""
        profile = Overwatch2GSyncProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")
        assert settings["preset"] == "reflex_gsync"
        assert settings["profile_name"] == "Overwatch 2"
        assert settings["auto_vrr_fps_cap"] is True
        assert settings["global_vrr_mode"] == "fullscreen_only"

    def test_overwatch2_gsync_in_game_display_mode_matches_fullscreen_vrr_path(self):
        """G-SYNC Overwatch guidance should match the fullscreen-only driver path."""
        profile = Overwatch2GSyncProfile()
        display_mode = next(
            item for item in profile.get_in_game_settings()
            if item["setting"] == "Display Mode"
        )
        assert display_mode["value"] == "Fullscreen (Exclusive)"
        assert "fullscreen-only g-sync" in display_mode["reason"].lower()
        assert "do not switch to borderless/windowed" in display_mode["reason"].lower()

    def test_overwatch2_gsync_hdr_settings(self):
        """G-SYNC HDR Overwatch profile should enable HDR, disable auto-HDR, use native ICC."""
        profile = Overwatch2GSyncHDRProfile()
        win = profile.get_settings("WindowsSettingsHandler")
        assert win["hdr"] is True
        assert win["auto_hdr"] is False

        nvidia = profile.get_settings("NvidiaSettingsHandler")
        assert nvidia["preset"] == "reflex_gsync"
        assert nvidia["profile_name"] == "Overwatch 2"
        assert nvidia["auto_vrr_fps_cap"] is True
        assert nvidia["global_vrr_mode"] == "fullscreen_only"

        color = profile.get_settings("ColorProfileSettingsHandler")
        assert color["icc_profile"] == "native"
        assert color["game_type"] == "competitive_fps"

    def test_overwatch2_gsync_hdr_in_game_display_mode_matches_fullscreen_vrr_path(self):
        """G-SYNC HDR guidance should stay aligned with fullscreen-only VRR settings."""
        profile = Overwatch2GSyncHDRProfile()
        display_mode = next(
            item for item in profile.get_in_game_settings()
            if item["setting"] == "Display Mode"
        )
        assert display_mode["value"] == "Fullscreen (Exclusive)"
        assert "fullscreen-only g-sync" in display_mode["reason"].lower()
        assert "do not switch to borderless/windowed" in display_mode["reason"].lower()

    def test_overwatch2_capture_profile_uses_windowed_vrr_path(self):
        """Capture-safe OW2 should explicitly use the borderless/windowed VRR path."""
        profile = Overwatch2GSyncCaptureProfile()
        windows = profile.get_settings("WindowsSettingsHandler")
        graphics = profile.get_settings("GraphicsSettingsHandler")
        nvidia = profile.get_settings("NvidiaSettingsHandler")
        ow2 = profile.get_settings("OW2ConfigHandler")

        assert windows["windowed_optimizations"] is True
        assert windows["vrr_optimize"] is True
        assert graphics["disable_global_fso"] is False
        assert graphics["disable_mpo"] is False
        assert nvidia["global_vrr_mode"] == "fullscreen_and_windowed"
        assert nvidia["profile_name"] == "Overwatch 2"
        assert ow2["window_mode"] == 1

    def test_overwatch2_hdr_capture_profile_uses_windowed_hdr_vrr_path(self):
        """HDR capture-safe OW2 should keep HDR while using the borderless/windowed VRR path."""
        profile = Overwatch2GSyncHDRCaptureProfile()
        windows = profile.get_settings("WindowsSettingsHandler")
        graphics = profile.get_settings("GraphicsSettingsHandler")
        nvidia = profile.get_settings("NvidiaSettingsHandler")
        ow2 = profile.get_settings("OW2ConfigHandler")

        assert windows["hdr"] is True
        assert windows["auto_hdr"] is False
        assert windows["windowed_optimizations"] is True
        assert windows["vrr_optimize"] is True
        assert graphics["disable_mpo"] is False
        assert nvidia["global_vrr_mode"] == "fullscreen_and_windowed"
        assert ow2["window_mode"] == 1

    def test_overwatch2_capture_profile_allows_overlays(self):
        """Capture-safe OW2 should not require the strict overlay-free path."""
        strict = Overwatch2GSyncProfile()
        capture = Overwatch2GSyncCaptureProfile()
        hdr_capture = Overwatch2GSyncHDRCaptureProfile()

        assert strict.display_path_requirements.require_overlay_free_path is True
        assert capture.display_path_requirements.require_overlay_free_path is False
        assert hdr_capture.display_path_requirements.require_overlay_free_path is False

    def test_overwatch2_capture_profile_requires_exact_binding_preflight(self):
        """Capture-safe OW2 still needs the real Overwatch NVIDIA profile binding."""
        strict = Overwatch2GSyncProfile()
        capture = Overwatch2GSyncCaptureProfile()
        hdr_capture = Overwatch2GSyncHDRCaptureProfile()

        assert strict.requires_exact_nvidia_binding is True
        assert capture.requires_exact_nvidia_binding is True
        assert hdr_capture.requires_exact_nvidia_binding is True

    def test_overwatch2_strict_profiles_auto_disable_blocking_overlays(self):
        """Strict exclusive OW2 profiles should auto-shut overlay blockers before failing."""
        strict = Overwatch2GSyncProfile()
        strict_hdr = Overwatch2GSyncHDRProfile()
        capture = Overwatch2GSyncCaptureProfile()

        assert strict.auto_disable_blocking_overlays is True
        assert strict_hdr.auto_disable_blocking_overlays is True
        assert capture.auto_disable_blocking_overlays is False

    def test_all_fullscreen_only_vrr_profiles_inherit_strict_display_path_contract(self):
        """Fullscreen-only VRR profiles should share the hardened Overwatch strict path behavior."""
        strict_profiles = [
            Overwatch2GSyncProfile(),
            Overwatch2GSyncHDRProfile(),
            MarvelRivalsSDRProfile(),
            MarvelRivalsHDRProfile(),
            Rivals2GSyncProfile(),
            Rivals2GSyncHDRProfile(),
            Rivals2OnlineGSyncProfile(),
            Rivals2OnlineGSyncHDRProfile(),
        ]

        for profile in strict_profiles:
            assert profile.uses_fullscreen_only_vrr_path is True
            assert profile.display_path_requirements.require_overlay_free_path is True
            assert profile.requires_exact_nvidia_binding is True
            assert profile.auto_disable_blocking_overlays is True

    def test_marvel_rivals_sdr_settings(self):
        """SDR Marvel Rivals profile should keep the Reflex + VRR SDR path."""
        profile = MarvelRivalsSDRProfile()

        win = profile.get_settings("WindowsSettingsHandler")
        assert win["hdr"] is False
        assert win["auto_hdr"] is False

        nvidia = profile.get_settings("NvidiaSettingsHandler")
        assert nvidia["preset"] == "reflex_gsync"
        assert nvidia["profile_name"] == "Marvel Rivals"
        assert nvidia["auto_vrr_fps_cap"] is True
        assert nvidia["global_vrr_mode"] == "fullscreen_only"

        color = profile.get_settings("ColorProfileSettingsHandler")
        assert color["icc_profile"] == "srgb"
        assert color["digital_vibrance"] == 45
        assert color["game_type"] == "competitive_fps"

    def test_marvel_rivals_hdr_settings(self):
        """HDR Marvel Rivals profile should preserve HDR while keeping Reflex + VRR."""
        profile = MarvelRivalsHDRProfile()

        win = profile.get_settings("WindowsSettingsHandler")
        assert win["hdr"] is True
        assert win["auto_hdr"] is False

        nvidia = profile.get_settings("NvidiaSettingsHandler")
        assert nvidia["preset"] == "reflex_gsync"
        assert nvidia["profile_name"] == "Marvel Rivals"
        assert nvidia["auto_vrr_fps_cap"] is True
        assert nvidia["global_vrr_mode"] == "fullscreen_only"

        color = profile.get_settings("ColorProfileSettingsHandler")
        assert color["icc_profile"] == "native"
        assert color["digital_vibrance"] == 50
        assert color["game_type"] == "competitive_fps"

    def test_diablo4_sdr_uses_srgb_color(self):
        """The SDR Diablo 4 variant should explicitly stay on the SDR path."""
        profile = Diablo4SDRProfile()
        win = profile.get_settings("WindowsSettingsHandler")
        color = profile.get_settings("ColorProfileSettingsHandler")

        assert win["hdr"] is False
        assert win["auto_hdr"] is False
        assert color["icc_profile"] == "srgb"

    def test_application_scope_reflects_native_config_coverage(self):
        """Profiles should expose whether ABSO can enforce title config directly."""
        from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile

        assert Diablo4Profile().application_scope == "system_plus_native_config"
        assert FortniteProfile().application_scope == "system_plus_native_config"
        assert RyujinxSSBUProfile().application_scope == "system_only"

    def test_fortnite_sdr_and_hdr_variants_drive_native_game_config(self):
        """Fortnite variants should enforce the matching SDR/HDR game config path."""
        sdr = FortniteProfile()
        hdr = FortniteHDRProfile()

        sdr_windows = sdr.get_settings("WindowsSettingsHandler")
        sdr_color = sdr.get_settings("ColorProfileSettingsHandler")
        sdr_config = sdr.get_settings("FortniteConfigHandler")
        hdr_windows = hdr.get_settings("WindowsSettingsHandler")
        hdr_color = hdr.get_settings("ColorProfileSettingsHandler")
        hdr_config = hdr.get_settings("FortniteConfigHandler")

        assert sdr_windows["hdr"] is False
        assert sdr_windows["auto_hdr"] is False
        assert sdr_color["icc_profile"] == "srgb"
        assert sdr_config["hdr_output"] is False
        assert sdr_config["fullscreen_mode"] == 0
        assert sdr_config["frame_rate_limit"] == 0

        assert hdr_windows["hdr"] is True
        assert hdr_windows["auto_hdr"] is False
        assert hdr_color["icc_profile"] == "native"
        assert hdr_config["hdr_output"] is True
        assert hdr_config["fullscreen_mode"] == 0
        assert hdr_config["frame_rate_limit"] == 0

    def test_marvel_rivals_variants_drive_native_game_config(self):
        """Marvel Rivals variants should set native HDR and Reflex in GameUserSettings."""
        sdr = MarvelRivalsSDRProfile()
        hdr = MarvelRivalsHDRProfile()

        sdr_config = sdr.get_settings("MarvelRivalsConfigHandler")
        hdr_config = hdr.get_settings("MarvelRivalsConfigHandler")

        assert sdr_config["fullscreen_mode"] == 0
        assert sdr_config["vsync"] is False
        assert sdr_config["nvidia_reflex"] is True
        assert sdr_config["dynamic_resolution"] is False
        assert sdr_config["dlss_frame_generation"] is False
        assert sdr_config["fsr_frame_generation"] is False
        assert sdr_config["xe_frame_generation"] is False
        assert sdr_config["auto_vrr_fps_cap"] is True
        assert sdr_config["hdr_output"] is False

        assert hdr_config["fullscreen_mode"] == 0
        assert hdr_config["vsync"] is False
        assert hdr_config["nvidia_reflex"] is True
        assert hdr_config["dynamic_resolution"] is False
        assert hdr_config["dlss_frame_generation"] is False
        assert hdr_config["fsr_frame_generation"] is False
        assert hdr_config["xe_frame_generation"] is False
        assert hdr_config["auto_vrr_fps_cap"] is True
        assert hdr_config["hdr_output"] is True

    def test_pokemon_auto_chess_windows_settings(self):
        """Test PokemonAutoChessProfile returns Windows settings."""
        profile = PokemonAutoChessProfile()
        settings = profile.get_settings("WindowsSettingsHandler")

        assert settings["game_mode"] is True
        assert settings["game_bar"] is False
        assert settings["game_dvr"] is False

    def test_pokemon_auto_chess_network_settings(self):
        """Test PokemonAutoChessProfile returns Network settings for online play."""
        profile = PokemonAutoChessProfile()
        settings = profile.get_settings("NetworkSettingsHandler")

        assert settings["disable_nagle"] is False
        assert settings["preset"] == "default"

    def test_rivals2_nvidia_settings_use_stable_profile_identity(self):
        """Offline/general Rivals profiles should target a shared stable NVIDIA profile."""
        profile = Rivals2OfflineProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["profile_name"] == "Rivals 2"
        assert "Rivals2-Win64-Shipping.exe" in settings["profile_aliases"]

    def test_rivals2_legacy_alias_still_resolves_to_offline_behavior(self):
        """Legacy generic Rivals alias should preserve offline handler behavior."""
        profile = Rivals2Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert profile.profile_id == "rivals2"
        assert settings["profile_name"] == "Rivals 2"
        assert "Rivals2-Win64-Shipping.exe" in settings["profile_aliases"]

    def test_rivals2_online_nvidia_settings_use_stable_profile_identity(self):
        """Online Rivals profiles should target a separate stable NVIDIA profile family."""
        profile = Rivals2OnlineProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["profile_name"] == "Rivals 2 Online"
        assert "Rivals 2: Online G-SYNC" in settings["profile_aliases"]

    def test_rivals2_gsync_nvidia_settings_use_stable_profile_identity(self):
        """Rivals 2 G-SYNC should not create a variant-named NVIDIA profile."""
        profile = Rivals2GSyncProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["profile_name"] == "Rivals 2"
        assert settings["preset"] == "vrr_fighting_game"
        assert settings["threaded_optimization"] == "off"
        assert "Rivals2-Win64-Shipping.exe" in settings["profile_aliases"]

    def test_rivals2_online_gsync_nvidia_settings_use_stable_profile_identity(self):
        """Rivals 2 online G-SYNC should reuse the online Rivals NVIDIA profile family."""
        profile = Rivals2OnlineGSyncProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["profile_name"] == "Rivals 2 Online"
        assert settings["preset"] == "vrr_fighting_game"
        assert "Rivals 2: Online / Matchmaking" in settings["profile_aliases"]

    def test_rivals2_hdr_variants_enable_windows_hdr_not_native_hdr(self):
        """Rivals 2 HDR lanes are Windows SDR-in-HDR composition, not native game HDR."""
        for profile_cls in (
            Rivals2OfflineHDRProfile,
            Rivals2OnlineHDRProfile,
            Rivals2GSyncHDRProfile,
            Rivals2OnlineGSyncHDRProfile,
        ):
            profile = profile_cls()
            win = profile.get_settings("WindowsSettingsHandler")
            graphics = profile.get_settings("GraphicsSettingsHandler")
            color = profile.get_settings("ColorProfileSettingsHandler")
            config = profile.get_settings("Rivals2ConfigHandler")

            assert win["hdr"] is True, profile_cls.__name__
            assert win["advanced_color"] is True, profile_cls.__name__
            assert win["auto_hdr"] is False, profile_cls.__name__
            assert win["sdr_white_level_nits"] == 200, profile_cls.__name__
            assert graphics["disable_auto_color_management"] is True, profile_cls.__name__
            assert color["icc_profile"] == "native", profile_cls.__name__
            assert color["digital_vibrance"] == 50, profile_cls.__name__
            assert config["hdr_output"] is False, profile_cls.__name__

    def test_rivals2_hdr_variants_preserve_parent_latency_knobs(self):
        """HDR variants should differ from SDR only on Windows/color/HDR composition knobs."""
        pairs = (
            (Rivals2OfflineProfile(), Rivals2OfflineHDRProfile()),
            (Rivals2OnlineProfile(), Rivals2OnlineHDRProfile()),
            (Rivals2GSyncProfile(), Rivals2GSyncHDRProfile()),
            (Rivals2OnlineGSyncProfile(), Rivals2OnlineGSyncHDRProfile()),
        )
        preserved_handlers = (
            "NvidiaSettingsHandler",
            "RegistrySettingsHandler",
            "PowerSettingsHandler",
            "ProcessPriorityHandler",
            "Rivals2ConfigHandler",
            "DisplayColorRangeHandler",
        )

        for sdr, hdr in pairs:
            for handler in preserved_handlers:
                assert hdr.get_settings(handler) == sdr.get_settings(handler), (
                    hdr.profile_id,
                    handler,
                )

    def test_rivals2_hdr_guidance_is_honest_about_native_hdr(self):
        """HDR guidance should not claim native Rivals 2 HDR support."""
        profile = Rivals2OfflineHDRProfile()
        guidance = profile.get_in_game_settings()
        settings_named = {entry.get("setting") for entry in guidance}
        combined = " ".join(
            f"{entry.get('value', '')} {entry.get('reason', '')}"
            for entry in guidance
        ).lower()

        assert "Use HDR (Settings > System > Display)" in settings_named
        assert "SDR content brightness" in settings_named
        assert "HDR Output" in settings_named
        assert "no native hdr support" in combined
        assert "not native game hdr" in combined
        assert "does not force unreal" in combined

    def test_rivals2_gsync_profile_sets_in_game_vrr_cap_automatically(self):
        """VRR Rivals profiles should drive the lower-latency in-game cap, not just NVCP."""
        profile = Rivals2GSyncProfile()
        config = profile.get_settings("Rivals2ConfigHandler")

        assert config["auto_vrr_fps_cap"] is True
        assert config["hdr_output"] is False

    def test_unknown_handler_returns_empty(self):
        """Test that unknown handler name returns empty dict."""
        profile = SlippiMeleeProfile()
        settings = profile.get_settings("UnknownHandler")

        assert settings == {}


class TestProfileInGameSettings:
    """Test in-game settings recommendations."""

    def test_slippi_in_game_settings(self):
        """Test SlippiMeleeProfile returns in-game settings."""
        profile = SlippiMeleeProfile()
        settings = profile.get_in_game_settings()

        assert isinstance(settings, list)
        assert len(settings) > 0

        # Check structure of first setting
        first = settings[0]
        assert "category" in first
        assert "setting" in first
        assert "value" in first
        assert "reason" in first

    def test_slippi_console_parity_in_game_settings(self):
        """Console-parity Slippi profile should return guidance settings."""
        profile = SlippiMeleeConsoleParityProfile()
        settings = profile.get_in_game_settings()

        assert isinstance(settings, list)
        assert len(settings) > 0
        assert any(s.get("setting") == "V-SYNC (global/per-game)" for s in settings)


    def test_pokemon_auto_chess_in_game_settings(self):
        """Test PokemonAutoChessProfile returns Chrome-specific settings."""
        profile = PokemonAutoChessProfile()
        settings = profile.get_in_game_settings()

        assert isinstance(settings, list)
        assert len(settings) > 0

        # Should have Chrome settings category
        chrome_settings = [s for s in settings if "Chrome" in s.get("category", "")]
        assert len(chrome_settings) > 0

        # Check hardware acceleration recommendation
        hw_accel = [s for s in settings if "Hardware Acceleration" in s.get("setting", "")]
        assert len(hw_accel) > 0
        assert hw_accel[0]["value"] == "Enabled"

    def test_pokemon_auto_chess_has_browser_optimization(self):
        """Test PokemonAutoChessProfile includes browser optimization tips."""
        profile = PokemonAutoChessProfile()
        settings = profile.get_in_game_settings()

        browser_opts = [s for s in settings if "Browser" in s.get("category", "")]
        assert len(browser_opts) > 0


class TestBaseProfileImplementation:
    """Test BaseProfile abstract class through concrete implementations."""

    def test_has_in_game_settings_true(self):
        """Test has_in_game_settings returns True when settings exist."""
        profile = SlippiMeleeProfile()
        assert profile.has_in_game_settings() is True

    def test_executable_hints_contains_expected(self):
        """Test executable_hints property returns list."""
        profile = SlippiMeleeProfile()
        hints = profile.executable_hints

        assert isinstance(hints, list)
        assert len(hints) > 0
        assert any("Dolphin" in hint for hint in hints)

    def test_pokemon_auto_chess_executable_hints_browsers(self):
        """Test PokemonAutoChessProfile executable hints include browsers."""
        profile = PokemonAutoChessProfile()
        hints = profile.executable_hints

        assert isinstance(hints, list)
        assert "chrome.exe" in hints
        assert "msedge.exe" in hints
        assert "firefox.exe" in hints

    def test_overwatch2_executable_hints(self):
        """Both Overwatch variants should target Overwatch.exe."""
        no_sync = Overwatch2Profile()
        gsync = Overwatch2GSyncProfile()
        assert no_sync.executable_hints == ["Overwatch.exe"]
        assert gsync.executable_hints == ["Overwatch.exe"]

    def test_overwatch2_gsync_requires_confirmed_vrr(self):
        """G-SYNC variants should require confirmed VRR support preflight."""
        no_sync = Overwatch2Profile()
        gsync = Overwatch2GSyncProfile()
        gsync_hdr = Overwatch2GSyncHDRProfile()
        marvel_sdr = MarvelRivalsSDRProfile()
        marvel_hdr = MarvelRivalsHDRProfile()
        assert no_sync.requires_confirmed_vrr_support is False
        assert gsync.requires_confirmed_vrr_support is True
        assert gsync_hdr.requires_confirmed_vrr_support is True
        assert marvel_sdr.requires_confirmed_vrr_support is True
        assert marvel_hdr.requires_confirmed_vrr_support is True

    def test_pokemon_auto_chess_optimization_target(self):
        """Test PokemonAutoChessProfile has balanced optimization target."""
        profile = PokemonAutoChessProfile()
        assert profile.optimization_target == "balanced"

    def test_optimization_target_is_string(self):
        """Test optimization_target returns valid string."""
        profile = SlippiMeleeProfile()
        assert isinstance(profile.optimization_target, str)
        assert profile.optimization_target == "minimum_latency"

    def test_generate_in_game_report_has_header(self):
        """Test generate_in_game_report includes header."""
        profile = SlippiMeleeProfile()
        report = profile.generate_in_game_report()

        assert profile.display_name in report
        assert "Optimization Target" in report

    def test_generate_in_game_report_has_settings(self):
        """Test generate_in_game_report includes settings."""
        profile = SlippiMeleeProfile()
        report = profile.generate_in_game_report()

        # Should have category headers
        assert "##" in report

    def test_diablo4_profile_target(self):
        """Test Diablo4Profile has balanced optimization target."""
        profile = Diablo4Profile()
        assert profile.optimization_target == "balanced"


class TestAllProfilesLoad:
    """Parametrized test that loads every profile and validates metadata."""

    @pytest.fixture(params=list(get_all_profiles().items()), ids=lambda p: p[0])
    def profile_entry(self, request):
        return request.param

    def test_required_metadata(self, profile_entry):
        """Every profile must have required metadata fields."""
        profile_id, profile = profile_entry
        assert profile.profile_id == profile_id
        assert isinstance(profile.display_name, str) and len(profile.display_name) > 0
        assert isinstance(profile.description, str) and len(profile.description) > 0
        assert isinstance(profile.optimization_target, str) and len(profile.optimization_target) > 0
        assert isinstance(profile.executable_hints, list) and len(profile.executable_hints) > 0
        assert isinstance(profile.is_online_profile, bool)
        assert isinstance(profile.is_emulator_profile, bool)
        assert isinstance(profile.requires_reflex, bool)
        assert isinstance(profile.requires_confirmed_vrr_support, bool)
        assert isinstance(profile.is_sdr_only, bool)
        assert profile.network_scope in {"full", "limited", "none"}
        assert profile.graphics_api in {"dx11", "dx12", "vulkan", "opengl", "unknown"}

    def test_get_handlers(self, profile_entry):
        """get_handlers() must return a non-empty list without exception."""
        _, profile = profile_entry
        handlers = profile.get_handlers()
        assert isinstance(handlers, list) and len(handlers) > 0

    def test_get_settings(self, profile_entry):
        """get_settings() must return a dict for each handler without exception."""
        _, profile = profile_entry
        for handler in profile.get_handlers():
            settings = profile.get_settings(handler.__class__.__name__)
            assert isinstance(settings, dict)


class TestFullscreenOptimizationsPerExe:
    """Profile-declared FSO per-exe overrides must flow into RegistrySettingsHandler."""

    def test_base_profile_default_is_empty(self):
        """Profiles that don't opt in should surface no FSO overrides."""
        profile = PokemonAutoChessProfile()
        assert profile.fullscreen_optimizations_per_exe == {}
        registry_settings = profile.get_settings("RegistrySettingsHandler") or {}
        assert "fullscreen_optimizations" not in registry_settings

    def test_overwatch2_exclusive_variants_disable_fso(self):
        """All exclusive-fullscreen OW2 variants must disable FSO for Overwatch.exe."""
        for profile_cls in (
            Overwatch2Profile,
            Overwatch2GSyncProfile,
            Overwatch2GSyncHDRProfile,
        ):
            profile = profile_cls()
            assert profile.fullscreen_optimizations_per_exe == {"Overwatch.exe": True}
            registry_settings = profile.get_settings("RegistrySettingsHandler")
            assert registry_settings["fullscreen_optimizations"] == {"Overwatch.exe": True}

    def test_overwatch2_capture_variants_clear_fso(self):
        """Capture/borderless OW2 variants must clear any prior FSO disable."""
        for profile_cls in (
            Overwatch2GSyncCaptureProfile,
            Overwatch2GSyncHDRCaptureProfile,
        ):
            profile = profile_cls()
            assert profile.fullscreen_optimizations_per_exe == {"Overwatch.exe": False}
            registry_settings = profile.get_settings("RegistrySettingsHandler")
            assert registry_settings["fullscreen_optimizations"] == {"Overwatch.exe": False}

    def test_fortnite_variants_disable_fso_for_all_shipping_binaries(self):
        """Fortnite's competitive lane is exclusive-fullscreen; all aliases must be locked."""
        for profile_cls in (FortniteProfile, FortniteHDRProfile):
            profile = profile_cls()
            flags = profile.fullscreen_optimizations_per_exe
            assert "FortniteClient-Win64-Shipping.exe" in flags
            assert all(v is True for v in flags.values())

    def test_marvel_rivals_variants_disable_fso(self):
        """Marvel Rivals SDR and HDR variants both run exclusive-fullscreen."""
        for profile_cls in (MarvelRivalsSDRProfile, MarvelRivalsHDRProfile):
            profile = profile_cls()
            flags = profile.fullscreen_optimizations_per_exe
            assert flags.get("Marvel-Win64-Shipping.exe") is True

    def test_rivals2_family_disables_fso(self):
        """Every Rivals 2 variant ships fullscreen_mode=0 and wants true exclusive."""
        for profile_cls in (
            Rivals2Profile,
            Rivals2OfflineProfile,
            Rivals2OfflineHDRProfile,
            Rivals2OnlineProfile,
            Rivals2OnlineHDRProfile,
            Rivals2GSyncProfile,
            Rivals2GSyncHDRProfile,
            Rivals2OnlineGSyncProfile,
            Rivals2OnlineGSyncHDRProfile,
        ):
            profile = profile_cls()
            flags = profile.fullscreen_optimizations_per_exe
            assert flags.get("Rivals2-Win64-Shipping.exe") is True

    def test_slippi_family_disables_fso(self):
        """All Slippi variants should disable FSO for Slippi Dolphin.exe and Dolphin.exe."""
        for profile_cls in (
            SlippiMeleeProfile,
            SlippiMeleeUniversalProfile,
            SlippiMeleeConsoleParityProfile,
            SlippiMeleeHDRProfile,
            SlippiMeleeUniversalHDRProfile,
            SlippiMeleeConsoleParityHDRProfile,
        ):
            profile = profile_cls()
            flags = profile.fullscreen_optimizations_per_exe
            assert flags.get("Slippi Dolphin.exe") is True
            assert flags.get("Dolphin.exe") is True

    def test_diablo4_variants_disable_fso(self):
        """Diablo 4 HDR and SDR lanes both want the true exclusive path for native HDR."""
        for profile_cls in (Diablo4Profile, Diablo4SDRProfile):
            profile = profile_cls()
            flags = profile.fullscreen_optimizations_per_exe
            assert flags.get("Diablo IV.exe") is True


class TestSingleLimiterPolicy:
    """Invariant: no profile layers an in-game and a driver FPS cap without opt-in.

    Blur Busters G-SYNC 101 recommends a single authoritative limiter (in-game
    preferred). ABSO enforces this via ``BaseProfile.allow_dual_limiter``:
    profiles that deliberately layer both an NVIDIA driver ``auto_vrr_fps_cap``
    and a native game-config ``auto_vrr_fps_cap`` must opt in explicitly and
    document the rationale in-code.
    """

    GAME_CONFIG_HANDLERS = (
        "OW2ConfigHandler",
        "MarvelRivalsConfigHandler",
        "Rivals2ConfigHandler",
        "Diablo4ConfigHandler",
        "FortniteConfigHandler",
    )

    def test_no_implicit_dual_limiter(self) -> None:
        """Flag any built-in profile with both caps enabled and no opt-in."""
        violations: list[str] = []
        for profile in get_all_profiles().values():
            nvidia_settings = profile.get_settings("NvidiaSettingsHandler")
            driver_cap = bool(nvidia_settings.get("auto_vrr_fps_cap"))
            if not driver_cap:
                continue

            game_caps: list[str] = []
            for handler in self.GAME_CONFIG_HANDLERS:
                handler_settings = profile.get_settings(handler)
                if handler_settings.get("auto_vrr_fps_cap"):
                    game_caps.append(handler)

            if game_caps and not profile.allow_dual_limiter:
                violations.append(
                    f"{profile.profile_id}: driver auto_vrr_fps_cap=True "
                    f"AND {', '.join(game_caps)}.auto_vrr_fps_cap=True "
                    "without allow_dual_limiter override"
                )

        assert not violations, (
            "Single-limiter policy violations:\n  "
            + "\n  ".join(violations)
        )

    def test_diablo4_uses_single_in_game_limiter(self) -> None:
        """Diablo 4 profiles own a single in-game limiter (driver cap off)."""
        for profile_cls in (Diablo4Profile, Diablo4SDRProfile):
            profile = profile_cls()
            nvidia = profile.get_settings("NvidiaSettingsHandler")
            d4 = profile.get_settings("Diablo4ConfigHandler")
            assert nvidia["auto_vrr_fps_cap"] is False, profile_cls.__name__
            assert d4["auto_vrr_fps_cap"] is True, profile_cls.__name__
            assert profile.allow_dual_limiter is False, profile_cls.__name__


class TestReflexContract:
    """Invariant: Reflex-requiring profiles must be honest about enforcement.

    ``BaseProfile.requires_reflex`` means "this game uses Reflex, so driver LLM
    should stay off." It does NOT mean ABSO enables Reflex for the user. Only
    profiles whose config handler writes the in-game Reflex key can set
    ``enforces_reflex_in_config = True``. Profiles without that enforcement
    must not advertise Reflex as "applied" in their description or in-game
    text.
    """

    CONFIG_HANDLER_REFLEX_KEYS: dict[str, tuple[str, ...]] = {
        "Diablo4ConfigHandler": ("reflex",),
        "MarvelRivalsConfigHandler": ("nvidia_reflex",),
        "OW2ConfigHandler": (),
        "FortniteConfigHandler": (),
        "Rivals2ConfigHandler": (),
    }

    def test_enforces_reflex_claim_matches_implementation(self) -> None:
        """enforces_reflex_in_config must be True iff a handler writes Reflex."""
        mismatches: list[str] = []
        for profile in get_all_profiles().values():
            if not profile.requires_reflex:
                continue

            wrote_reflex = False
            for handler_name, reflex_keys in self.CONFIG_HANDLER_REFLEX_KEYS.items():
                settings = profile.get_settings(handler_name)
                if any(k in settings for k in reflex_keys):
                    wrote_reflex = True
                    break

            if profile.enforces_reflex_in_config != wrote_reflex:
                mismatches.append(
                    f"{profile.profile_id}: enforces_reflex_in_config="
                    f"{profile.enforces_reflex_in_config} but handler writes "
                    f"Reflex = {wrote_reflex}"
                )

        assert not mismatches, (
            "Reflex contract mismatches:\n  " + "\n  ".join(mismatches)
        )

    def test_reflex_not_claimed_when_not_enforced(self) -> None:
        """Profiles that don't enforce Reflex must not claim it is 'applied'."""
        violations: list[str] = []
        banned_fragments = (
            "reflex applied",
            "reflex on+boost by abso",
            "abso enables reflex",
            "abso applies reflex",
        )
        # Explicit "Reflex is OFF" entries are honest non-enforcement statements
        # (e.g., OW2 no-sync is tuned around LLM-on with Reflex OFF). They should
        # not be forced to include "manually" — they are not claiming enforcement.
        reflex_off_markers = ("off", "disabled", "do not enable")

        for profile in get_all_profiles().values():
            if not profile.requires_reflex:
                continue
            if profile.enforces_reflex_in_config:
                continue

            # Description and in-game guidance must acknowledge manual setup.
            text = (profile.description or "").lower()
            for fragment in banned_fragments:
                if fragment in text:
                    violations.append(
                        f"{profile.profile_id}.description claims Reflex "
                        f"enforcement: contains {fragment!r}"
                    )

            for entry in profile.get_in_game_settings():
                if "reflex" not in entry.get("setting", "").lower():
                    continue

                value = entry.get("value", "").lower()
                reason = entry.get("reason", "").lower()

                explicitly_off = any(
                    marker in value for marker in reflex_off_markers
                )
                says_manually = "manually" in value or "manually" in reason

                if not explicitly_off and not says_manually:
                    violations.append(
                        f"{profile.profile_id} Reflex in-game entry must "
                        "mention manual setup (value or reason), OR state "
                        "Reflex is OFF: "
                        f"{entry!r}"
                    )

        assert not violations, (
            "Reflex honesty violations:\n  " + "\n  ".join(violations)
        )
