"""Tests for game profiles."""

from __future__ import annotations

import pytest

from abso.profiles import get_all_profiles
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_online import Rivals2OnlineProfile
from abso.profiles.slippi_melee import SlippiMeleeProfile


class TestProfileLoading:
    """Test that profiles can be loaded without import errors."""

    def test_slippi_profile_loads(self):
        """Test SlippiMeleeProfile can be instantiated."""
        profile = SlippiMeleeProfile()
        assert profile.profile_id == "slippi-melee"
        assert profile.display_name == "Super Smash Bros. Melee (Slippi)"

    def test_cod_profile_loads(self):
        """Test CodBo7Profile can be instantiated."""
        profile = CodBo7Profile()
        assert profile.profile_id == "cod-bo7"
        assert profile.display_name == "Call of Duty: Black Ops 7"

    def test_diablo4_profile_loads(self):
        """Test Diablo4Profile can be instantiated."""
        profile = Diablo4Profile()
        assert profile.profile_id == "diablo4"
        assert profile.display_name == "Diablo 4"

    def test_pokemon_auto_chess_profile_loads(self):
        """Test PokemonAutoChessProfile can be instantiated."""
        profile = PokemonAutoChessProfile()
        assert profile.profile_id == "pokemon-auto-chess"
        assert profile.display_name == "Pokemon Auto Chess"


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

    def test_cod_get_handlers_returns_list(self):
        """Test CodBo7Profile.get_handlers returns handlers."""
        profile = CodBo7Profile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0

    def test_diablo4_get_handlers_returns_list(self):
        """Test Diablo4Profile.get_handlers returns handlers."""
        profile = Diablo4Profile()
        handlers = profile.get_handlers()

        assert isinstance(handlers, list)
        assert len(handlers) > 0

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

    def test_rivals2_online_does_not_touch_game_config_file(self):
        """Online profile should not include the Rivals2ConfigHandler."""
        profile = Rivals2OnlineProfile()
        handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
        assert "Rivals2ConfigHandler" not in handler_names

    def test_rivals2_base_profile_includes_game_config_guarded_handler(self):
        """Base Rivals2 profile includes config handler for explicit game INI tuning."""
        profile = Rivals2Profile()
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
        settings = profile.get_settings("NvidiaSettingsHandler")

        # Minimum latency settings per rollback.md canonical spec
        assert settings["low_latency_mode"] == "on"  # On recommended; Ultra optional
        assert settings["vsync"] == "off"
        assert settings["vrr_app_override"] == "force_off"
        assert settings["threaded_optimization"] == "off"

    def test_cod_nvidia_settings(self):
        """Test CodBo7Profile returns Nvidia settings with reflex_game preset."""
        profile = CodBo7Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        # CoD has built-in NVIDIA Reflex - uses reflex_game preset (LLM OFF)
        assert settings["preset"] == "reflex_game"

    def test_diablo4_nvidia_settings(self):
        """Test Diablo4Profile returns Nvidia settings with preset."""
        profile = Diablo4Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["preset"] == "balanced"

    def test_pokemon_auto_chess_nvidia_settings(self):
        """Test PokemonAutoChessProfile returns explicit Nvidia settings."""
        profile = PokemonAutoChessProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        # WebGL benefits from low latency settings with VSync disabled
        assert settings["low_latency_mode"] == "on"
        assert settings["vsync"] == "off"

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

    def test_cod_in_game_has_reflex_setting(self):
        """Test CodBo7Profile recommends Nvidia Reflex."""
        profile = CodBo7Profile()
        settings = profile.get_in_game_settings()

        reflex_settings = [s for s in settings if "Reflex" in s.get("setting", "")]
        assert len(reflex_settings) > 0

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

    def test_cod_profile_description(self):
        """Test CodBo7Profile has description."""
        profile = CodBo7Profile()
        assert isinstance(profile.description, str)
        assert len(profile.description) > 0

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
