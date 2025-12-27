"""Tests for game profiles."""

from __future__ import annotations

import pytest

from gametune.profiles.base import BaseProfile
from gametune.profiles.slippi_melee import SlippiMeleeProfile
from gametune.profiles.cod_bo7 import CodBo7Profile
from gametune.profiles.diablo4 import Diablo4Profile


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
        """Test SlippiMeleeProfile returns Nvidia settings with preset."""
        profile = SlippiMeleeProfile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["preset"] == "minimum_latency"

    def test_cod_nvidia_settings(self):
        """Test CodBo7Profile returns Nvidia settings with preset."""
        profile = CodBo7Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["preset"] == "low_latency_high_fps"

    def test_diablo4_nvidia_settings(self):
        """Test Diablo4Profile returns Nvidia settings with preset."""
        profile = Diablo4Profile()
        settings = profile.get_settings("NvidiaSettingsHandler")

        assert settings["preset"] == "balanced"

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
