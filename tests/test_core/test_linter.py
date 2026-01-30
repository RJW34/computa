"""Tests for ProfileLinter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from abso.core.linter import LintSeverity, ProfileLinter


def _make_profile(**kwargs):
    """Create a mock profile with given attributes."""
    profile = MagicMock()
    profile.profile_id = kwargs.get("profile_id", "test-profile")
    profile.display_name = kwargs.get("display_name", "Test Profile")
    profile.description = kwargs.get("description", "A test profile")
    profile.optimization_target = kwargs.get("optimization_target", "minimum_latency")
    profile.executable_hints = kwargs.get("executable_hints", ["test.exe"])
    profile.is_online_profile = kwargs.get("is_online_profile", False)
    profile.is_emulator_profile = kwargs.get("is_emulator_profile", False)
    profile.requires_reflex = kwargs.get("requires_reflex", False)
    profile.is_sdr_only = kwargs.get("is_sdr_only", False)
    profile.allows_aggressive_settings = kwargs.get("allows_aggressive_settings", True)

    handlers = kwargs.get("handlers", [])
    profile.get_handlers.return_value = handlers
    settings_map = kwargs.get("settings_map", {})
    profile.get_settings.side_effect = lambda name: settings_map.get(name, {})
    return profile


class TestProfileLinterValid:
    """Test that valid profiles pass linting."""

    def test_valid_minimum_latency_profile(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        profile = _make_profile(
            handlers=[nvidia_handler],
            settings_map={
                "NvidiaSettingsHandler": {
                    "low_latency_mode": "ultra",
                    "vsync": "off",
                    "preset": "minimum_latency",
                }
            },
        )
        result = linter.lint(profile)
        assert result.passed
        assert not result.has_errors

    def test_empty_settings_passes(self):
        linter = ProfileLinter()
        profile = _make_profile(handlers=[])
        result = linter.lint(profile)
        assert result.passed


class TestProfileLinterErrors:
    """Test that invalid profiles produce errors."""

    def test_reflex_with_llm_not_off(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        profile = _make_profile(
            handlers=[nvidia_handler],
            settings_map={
                "NvidiaSettingsHandler": {
                    "preset": "reflex_game",
                    "low_latency_mode": "on",
                }
            },
        )
        result = linter.lint(profile)
        assert result.has_errors
        assert any(e.code == "NVIDIA_REFLEX_LLM_CONFLICT" for e in result.errors)

    def test_fast_sync_rollback(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        profile = _make_profile(
            optimization_target="stable_online",
            handlers=[nvidia_handler],
            settings_map={
                "NvidiaSettingsHandler": {"vsync": "fast"}
            },
        )
        result = linter.lint(profile)
        assert result.has_errors
        assert any(e.code == "NVIDIA_FAST_SYNC_ROLLBACK" for e in result.errors)

    def test_hdr_on_sdr_profile(self):
        linter = ProfileLinter()
        win_handler = MagicMock()
        win_handler.__class__.__name__ = "WindowsSettingsHandler"
        profile = _make_profile(
            display_name="Slippi Melee",
            description="Melee",
            executable_hints=["Slippi Dolphin.exe"],
            is_sdr_only=True,
            handlers=[win_handler],
            settings_map={
                "WindowsSettingsHandler": {"hdr": True}
            },
        )
        result = linter.lint(profile)
        assert result.has_errors
        assert any(e.code == "WINDOWS_HDR_SDR_MISMATCH" for e in result.errors)
