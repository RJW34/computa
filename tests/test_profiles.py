"""Tests for game profiles."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from abso.profiles import get_all_profiles
from abso.profiles.diablo4 import Diablo4Profile, Diablo4SDRProfile
from abso.profiles.fortnite import FortniteHDRProfile, FortniteProfile
from abso.profiles.marvel_rivals import MarvelRivalsHDRProfile, MarvelRivalsSDRProfile
from abso.profiles.overwatch2 import (
    Overwatch2GSyncCaptureProfile,
    Overwatch2GSyncHDRCaptureProfile,
    Overwatch2GSyncHDRProfile,
    Overwatch2GSyncProfile,
    Overwatch2Profile,
)
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_gsync import (
    Rivals2GSyncHDRProfile,
    Rivals2GSyncProfile,
    Rivals2OnlineGSyncHDRProfile,
    Rivals2OnlineGSyncProfile,
)
from abso.profiles.rivals2_offline import Rivals2OfflineHDRProfile, Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineHDRProfile, Rivals2OnlineProfile
from abso.profiles.streaming_profiles import (
    FortniteHDRStreamingProfile,
    FortniteStreamingProfile,
    Overwatch2GSyncStreamingProfile,
    Rivals2HDRStreamingProfile,
    Rivals2StreamingProfile,
)
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeProfile,
    SlippiMeleeUniversalProfile,
    SlippiMeleeVRRLabProfile,
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

    def test_slippi_vrr_lab_profile_loads(self):
        """Test SlippiMeleeVRRLabProfile can be instantiated."""
        profile = SlippiMeleeVRRLabProfile()
        assert profile.profile_id == "slippi-melee-vrr-lab"
        assert "VRR Lab" in profile.display_name

    def test_diablo4_profile_loads(self):
        """Diablo 4 should expose explicit HDR and SDR variants."""
        hdr = Diablo4Profile()
        sdr = Diablo4SDRProfile()
        assert hdr.profile_id == "diablo4"
        assert hdr.display_name == "Diablo 4 - HDR"
        assert sdr.profile_id == "diablo4-sdr"
        assert sdr.display_name == "Diablo 4 - SDR"

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
        gsync = Overwatch2GSyncProfile()
        gsync_hdr = Overwatch2GSyncHDRProfile()
        gsync_capture = Overwatch2GSyncCaptureProfile()
        gsync_hdr_capture = Overwatch2GSyncHDRCaptureProfile()
        assert no_sync.profile_id == "overwatch2"
        assert gsync.profile_id == "overwatch2-gsync"
        assert gsync_hdr.profile_id == "overwatch2-gsync-hdr"
        assert gsync_capture.profile_id == "overwatch2-gsync-capture"
        assert gsync_hdr_capture.profile_id == "overwatch2-gsync-hdr-capture"

    def test_marvel_rivals_profiles_load(self):
        """Test both Marvel Rivals variants can be instantiated."""
        sdr = MarvelRivalsSDRProfile()
        hdr = MarvelRivalsHDRProfile()
        assert sdr.profile_id == "marvel-rivals-sdr"
        assert hdr.profile_id == "marvel-rivals-hdr"
        assert "Marvel Rivals" in sdr.display_name
        assert "Marvel Rivals" in hdr.display_name

    def test_rivals2_consolidated_profiles_load(self):
        """The canonical Rivals 2 matrix should expose explicit SDR/HDR lanes."""
        offline = Rivals2OfflineProfile()
        offline_hdr = Rivals2OfflineHDRProfile()
        online = Rivals2OnlineProfile()
        online_hdr = Rivals2OnlineHDRProfile()
        gsync = Rivals2GSyncProfile()
        gsync_hdr = Rivals2GSyncHDRProfile()
        online_gsync = Rivals2OnlineGSyncProfile()
        online_gsync_hdr = Rivals2OnlineGSyncHDRProfile()
        streaming = Rivals2StreamingProfile()
        streaming_hdr = Rivals2HDRStreamingProfile()

        assert offline.profile_id == "rivals2-offline"
        assert offline_hdr.profile_id == "rivals2-offline-hdr"
        assert online.profile_id == "rivals2-online"
        assert online_hdr.profile_id == "rivals2-online-hdr"
        assert gsync.profile_id == "rivals2-gsync"
        assert gsync_hdr.profile_id == "rivals2-gsync-hdr"
        assert online_gsync.profile_id == "rivals2-online-gsync"
        assert online_gsync_hdr.profile_id == "rivals2-online-gsync-hdr"
        assert streaming.profile_id == "rivals2-streaming"
        assert streaming_hdr.profile_id == "rivals2-streaming-hdr"

    def test_profiles_expose_canonical_nvidia_binding_executables(self):
        """NVIDIA binding should target canonical binaries, not broad detection aliases."""
        rivals = Rivals2OnlineGSyncHDRProfile()
        marvel = MarvelRivalsHDRProfile()
        slippi = SlippiMeleeVRRLabProfile()

        assert rivals.nvidia_binding_executables == ["Rivals2-Win64-Shipping.exe"]
        assert rivals.allow_unverified_nvidia_profile_reuse is True
        assert marvel.nvidia_binding_executables == ["Marvel-Win64-Shipping.exe"]
        assert slippi.nvidia_binding_executables == ["Slippi Dolphin.exe"]
        assert slippi.allow_unverified_nvidia_profile_reuse is True

    def test_streaming_variants_load(self):
        """Streaming families should expose the expected explicit HDR/SDR lanes."""
        fortnite_stream = FortniteStreamingProfile()
        fortnite_stream_hdr = FortniteHDRStreamingProfile()
        ow2_stream = Overwatch2GSyncStreamingProfile()

        assert fortnite_stream.profile_id == "fortnite-streaming"
        assert fortnite_stream_hdr.profile_id == "fortnite-streaming-hdr"
        assert ow2_stream.profile_id == "overwatch2-gsync-streaming"


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

    def test_slippi_vrr_lab_nvidia_settings(self):
        """VRR lab profile should explicitly enable VRR test path."""
        profile = SlippiMeleeVRRLabProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["vsync"] == "on"
        assert settings["vrr_app_override"] == "allow"
        assert settings["global_vrr_mode"] == "fullscreen_only"

    def test_diablo4_nvidia_settings(self):
        """Test Diablo4Profile returns Nvidia settings with Reflex preset (LLM OFF)."""
        profile = Diablo4Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        # Diablo 4 has native Reflex — uses vrr_diablo4 preset (LLM OFF)
        assert settings["preset"] == "vrr_diablo4"

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
        assert hdr_config["limit_foreground_fps"] is False
        assert hdr_config["hdr_output"] is True

        assert sdr_windows["hdr"] is False
        assert sdr_config["window_mode"] == 1
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

    def test_overwatch2_capture_profile_does_not_require_exact_binding_preflight(self):
        """Capture-safe OW2 should not hard-block on exact NVIDIA binding proof."""
        strict = Overwatch2GSyncProfile()
        capture = Overwatch2GSyncCaptureProfile()
        hdr_capture = Overwatch2GSyncHDRCaptureProfile()

        assert strict.requires_exact_nvidia_binding is True
        assert capture.requires_exact_nvidia_binding is False
        assert hdr_capture.requires_exact_nvidia_binding is False

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
            Rivals2OnlineGSyncProfile(),
            SlippiMeleeVRRLabProfile(),
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
        assert sdr_config["auto_vrr_fps_cap"] is True
        assert sdr_config["hdr_output"] is False

        assert hdr_config["fullscreen_mode"] == 0
        assert hdr_config["vsync"] is False
        assert hdr_config["nvidia_reflex"] is True
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
        assert "Rivals2-Win64-Shipping.exe" in settings["profile_aliases"]

    def test_rivals2_online_gsync_nvidia_settings_use_stable_profile_identity(self):
        """Rivals 2 online G-SYNC should reuse the online Rivals NVIDIA profile family."""
        profile = Rivals2OnlineGSyncProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["profile_name"] == "Rivals 2 Online"
        assert settings["preset"] == "vrr_fighting_game"
        assert "Rivals 2: Online / Matchmaking" in settings["profile_aliases"]

    def test_rivals2_offline_hdr_enables_native_hdr_path(self):
        """Offline HDR profile should enable native Windows + game HDR."""
        profile = Rivals2OfflineHDRProfile()

        windows = profile.get_settings("WindowsSettingsHandler")
        color = profile.get_settings("ColorProfileSettingsHandler")
        config = profile.get_settings("Rivals2ConfigHandler")

        assert windows["hdr"] is True
        assert windows["auto_hdr"] is False
        assert color["icc_profile"] == "native"
        assert config["hdr_output"] is True
        assert config["hdr_nits"] == 1000

    def test_rivals2_online_hdr_enables_native_hdr_path(self):
        """Online HDR profile should preserve rollback-safe behavior while enabling HDR."""
        profile = Rivals2OnlineHDRProfile()

        windows = profile.get_settings("WindowsSettingsHandler")
        nvidia = profile.get_settings("NvidiaSettingsHandler")
        config = profile.get_settings("Rivals2ConfigHandler")

        assert windows["hdr"] is True
        assert windows["auto_hdr"] is False
        assert nvidia["global_vrr_mode"] == "off"
        assert config["hdr_output"] is True
        assert config["frame_rate_limit"] == 999

    def test_rivals2_gsync_profile_sets_in_game_vrr_cap_automatically(self):
        """VRR Rivals profiles should drive the lower-latency in-game cap, not just NVCP."""
        profile = Rivals2GSyncProfile()
        config = profile.get_settings("Rivals2ConfigHandler")

        assert config["auto_vrr_fps_cap"] is True
        assert config["hdr_output"] is False

    def test_rivals2_gsync_hdr_profile_enables_native_hdr_and_auto_vrr_cap(self):
        """HDR VRR Rivals profile should layer native HDR onto the VRR lane."""
        profile = Rivals2GSyncHDRProfile()

        windows = profile.get_settings("WindowsSettingsHandler")
        nvidia = profile.get_settings("NvidiaSettingsHandler")
        config = profile.get_settings("Rivals2ConfigHandler")

        assert windows["hdr"] is True
        assert windows["auto_hdr"] is False
        assert nvidia["global_vrr_mode"] == "fullscreen_only"
        assert nvidia["auto_vrr_fps_cap"] is True
        assert config["auto_vrr_fps_cap"] is True
        assert config["hdr_output"] is True

    def test_rivals2_online_gsync_hdr_profile_stays_on_online_nvidia_family(self):
        """Online HDR VRR profile should keep the online NVIDIA family identity."""
        profile = Rivals2OnlineGSyncHDRProfile()
        nvidia = profile.get_settings("NvidiaSettingsHandler")

        assert nvidia["profile_name"] == "Rivals 2 Online"
        assert "Rivals 2: Online / Matchmaking" in nvidia["profile_aliases"]

    def test_rivals2_streaming_profiles_share_online_core_behavior(self):
        """Streaming Rivals profiles should inherit the online stability lane plus OBS tuning."""
        sdr = Rivals2StreamingProfile()
        hdr = Rivals2HDRStreamingProfile()

        sdr_config = sdr.get_settings("Rivals2ConfigHandler")
        hdr_config = hdr.get_settings("Rivals2ConfigHandler")

        assert sdr_config["frame_rate_limit"] == 999
        assert sdr_config["hdr_output"] is False
        assert hdr_config["frame_rate_limit"] == 999
        assert hdr_config["hdr_output"] is True

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

    def test_slippi_vrr_lab_in_game_settings(self):
        """VRR lab profile should include explicit A/B measurement guidance."""
        profile = SlippiMeleeVRRLabProfile()
        settings = profile.get_in_game_settings()

        assert isinstance(settings, list)
        assert len(settings) > 0
        assert any("A/B" in s.get("value", "") for s in settings)

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
        slippi_vrr_lab = SlippiMeleeVRRLabProfile()
        assert no_sync.requires_confirmed_vrr_support is False
        assert gsync.requires_confirmed_vrr_support is True
        assert gsync_hdr.requires_confirmed_vrr_support is True
        assert marvel_sdr.requires_confirmed_vrr_support is True
        assert marvel_hdr.requires_confirmed_vrr_support is True
        assert slippi_vrr_lab.requires_confirmed_vrr_support is True

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
