"""Tests for ProfileLinter."""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

from abso.core.linter import ProfileLinter
from abso.profiles.catalog import get_profile_classes


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
    profile.requires_confirmed_vrr_support = kwargs.get("requires_confirmed_vrr_support", False)
    profile.graphics_api = kwargs.get("graphics_api", "unknown")

    handlers = kwargs.get("handlers", [])
    profile.get_handlers.return_value = handlers
    settings_map = kwargs.get("settings_map", {})
    profile.get_settings.side_effect = lambda name: settings_map.get(name, {})
    profile.get_in_game_settings.return_value = kwargs.get("in_game_settings", [])
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

    def test_windowed_vrr_guidance_passes_when_settings_support_it(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        windows_handler = MagicMock()
        windows_handler.__class__.__name__ = "WindowsSettingsHandler"
        profile = _make_profile(
            requires_confirmed_vrr_support=True,
            handlers=[nvidia_handler, windows_handler],
            settings_map={
                "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_and_windowed"},
                "WindowsSettingsHandler": {"vrr_optimize": True},
            },
            in_game_settings=[
                {
                    "setting": "Display Mode",
                    "value": "Borderless Windowed",
                    "reason": "Windowed VRR path",
                }
            ],
        )
        result = linter.lint(profile)
        assert result.passed
        assert not any(e.code == "VRR_DISPLAY_MODE_GUIDANCE_MISMATCH" for e in result.errors)

    def test_negative_borderless_warning_does_not_trigger_guidance_mismatch(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        windows_handler = MagicMock()
        windows_handler.__class__.__name__ = "WindowsSettingsHandler"
        profile = _make_profile(
            requires_confirmed_vrr_support=True,
            handlers=[nvidia_handler, windows_handler],
            settings_map={
                "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_only"},
                "WindowsSettingsHandler": {"vrr_optimize": False},
            },
            in_game_settings=[
                {
                    "setting": "Display Mode",
                    "value": "Exclusive Fullscreen",
                    "reason": "Do not switch to borderless/windowed mode after launch.",
                }
            ],
        )
        profile.display_path_requirements.require_overlay_free_path = True
        profile.requires_exact_nvidia_binding = True
        result = linter.lint(profile)
        assert result.passed
        assert not any(e.code == "VRR_DISPLAY_MODE_GUIDANCE_MISMATCH" for e in result.errors)

    def test_strict_fullscreen_vrr_contract_passes_when_overlay_free_and_exact_binding_enabled(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        profile = _make_profile(
            requires_confirmed_vrr_support=True,
            handlers=[nvidia_handler],
            settings_map={
                "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_only"},
            },
        )
        profile.display_path_requirements.require_overlay_free_path = True
        profile.requires_exact_nvidia_binding = True

        result = linter.lint(profile)

        assert result.passed
        assert not any(e.code.startswith("STRICT_VRR_") for e in result.errors)

    def test_strict_fullscreen_vrr_warns_when_binding_targets_reuse_all_detection_aliases(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        profile = _make_profile(
            requires_confirmed_vrr_support=True,
            executable_hints=["game-launcher.exe", "game-shipping.exe"],
            handlers=[nvidia_handler],
            settings_map={
                "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_only"},
            },
        )
        profile.display_path_requirements.require_overlay_free_path = True
        profile.requires_exact_nvidia_binding = True
        profile.nvidia_binding_executables = ["game-launcher.exe", "game-shipping.exe"]

        result = linter.lint(profile)

        assert any(w.code == "STRICT_VRR_BINDING_EXECUTABLES_TOO_BROAD" for w in result.warnings)


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

    def test_explicit_hdr_profile_not_inferred_as_sdr_from_executable_name(self):
        linter = ProfileLinter()
        win_handler = MagicMock()
        win_handler.__class__.__name__ = "WindowsSettingsHandler"
        profile = _make_profile(
            profile_id="rivals2-online-hdr-variant",
            display_name="Rivals 2: Online HDR",
            executable_hints=["Rivals2-Win64-Shipping.exe"],
            is_sdr_only=False,
            handlers=[win_handler],
            settings_map={
                "WindowsSettingsHandler": {"hdr": True, "auto_hdr": False}
            },
        )

        result = linter.lint(profile)

        assert not any(e.code == "WINDOWS_HDR_SDR_MISMATCH" for e in result.errors)

    def test_native_hdr_profile_rejects_auto_hdr(self):
        linter = ProfileLinter()
        win_handler = MagicMock()
        win_handler.__class__.__name__ = "WindowsSettingsHandler"
        profile = _make_profile(
            handlers=[win_handler],
            settings_map={
                "WindowsSettingsHandler": {"hdr": True, "auto_hdr": True}
            },
        )
        result = linter.lint(profile)
        assert result.has_errors
        assert any(e.code == "WINDOWS_NATIVE_HDR_AUTO_HDR_CONFLICT" for e in result.errors)

    def test_native_hdr_profile_rejects_srgb_clamp(self):
        linter = ProfileLinter()
        win_handler = MagicMock()
        win_handler.__class__.__name__ = "WindowsSettingsHandler"
        color_handler = MagicMock()
        color_handler.__class__.__name__ = "ColorProfileSettingsHandler"
        profile = _make_profile(
            handlers=[win_handler, color_handler],
            settings_map={
                "WindowsSettingsHandler": {"hdr": True, "auto_hdr": False},
                "ColorProfileSettingsHandler": {"icc_profile": "srgb"},
            },
        )
        result = linter.lint(profile)
        assert result.has_errors
        assert any(e.code == "COLOR_HDR_SRGB_CLAMP" for e in result.errors)


    def test_vrr_profile_borderless_guidance_requires_matching_settings(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        windows_handler = MagicMock()
        windows_handler.__class__.__name__ = "WindowsSettingsHandler"
        profile = _make_profile(
            requires_confirmed_vrr_support=True,
            handlers=[nvidia_handler, windows_handler],
            settings_map={
                "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_only"},
                "WindowsSettingsHandler": {"vrr_optimize": False},
            },
            in_game_settings=[
                {
                    "setting": "Display Mode",
                    "value": "Fullscreen -> then toggle Borderless",
                    "reason": "Switch to Borderless Windowed after launch",
                }
            ],
        )
        result = linter.lint(profile)
        assert result.has_errors
        assert any(e.code == "VRR_DISPLAY_MODE_GUIDANCE_MISMATCH" for e in result.errors)

    def test_fullscreen_only_vrr_profile_requires_overlay_free_contract(self):
        linter = ProfileLinter()
        nvidia_handler = MagicMock()
        nvidia_handler.__class__.__name__ = "NvidiaSettingsHandler"
        profile = _make_profile(
            requires_confirmed_vrr_support=True,
            handlers=[nvidia_handler],
            settings_map={
                "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_only"},
            },
        )
        profile.display_path_requirements.require_overlay_free_path = False
        profile.requires_exact_nvidia_binding = False

        result = linter.lint(profile)

        assert result.has_errors
        assert any(e.code == "STRICT_VRR_OVERLAY_PATH_REQUIRED" for e in result.errors)
        assert any(e.code == "STRICT_VRR_EXACT_BINDING_REQUIRED" for e in result.errors)


def test_all_shipped_profiles_pass_linter_without_errors():
    """Every shipped profile should lint cleanly at error severity."""
    linter = ProfileLinter()
    failures = []

    for profile_id, profile_cls in sorted(get_profile_classes().items()):
        profile = profile_cls()
        result = linter.lint(profile)
        if result.errors:
            failures.append((profile_id, [issue.code for issue in result.errors]))

    assert not failures, f"Profiles failed linting: {failures}"


@pytest.mark.parametrize("profile_id", ["diablo4", "diablo4-sdr"])
def test_dx12_diablo_borderless_path_does_not_require_legacy_windows_vrr_switch(profile_id):
    profile = get_profile_classes()[profile_id]()
    assert profile.graphics_api == "dx12"
    assert profile.get_settings("WindowsSettingsHandler")["vrr_optimize"] is False
    result = ProfileLinter().lint(profile)
    assert result.passed, result.errors


@pytest.mark.parametrize("profile_id", ["diablo4", "diablo4-sdr"])
def test_dx12_borderless_path_still_rejects_fullscreen_only_driver_vrr(profile_id, monkeypatch):
    profile = get_profile_classes()[profile_id]()
    original_settings = profile.get_settings

    def mismatched_settings(handler_name):
        settings = original_settings(handler_name)
        if handler_name == "NvidiaSettingsHandler":
            return {**settings, "global_vrr_mode": "fullscreen_only"}
        return settings

    monkeypatch.setattr(profile, "get_settings", mismatched_settings)
    result = ProfileLinter().lint(profile)
    issue = next(e for e in result.errors if e.code == "VRR_DISPLAY_MODE_GUIDANCE_MISMATCH")
    assert "global_vrr_mode='fullscreen_and_windowed'" in issue.details
    assert "vrr_optimize=True" not in issue.details


@pytest.mark.parametrize("graphics_api", ["dx11", "unknown"])
def test_other_windowed_paths_retain_existing_windows_vrr_requirement(graphics_api):
    nvidia = MagicMock()
    nvidia.__class__.__name__ = "NvidiaSettingsHandler"
    windows = MagicMock()
    windows.__class__.__name__ = "WindowsSettingsHandler"
    profile = _make_profile(
        graphics_api=graphics_api,
        requires_confirmed_vrr_support=True,
        handlers=[nvidia, windows],
        settings_map={
            "NvidiaSettingsHandler": {"global_vrr_mode": "fullscreen_and_windowed"},
            "WindowsSettingsHandler": {"vrr_optimize": False},
        },
        in_game_settings=[{"setting": "Display Mode", "value": "Borderless Windowed"}],
    )
    result = ProfileLinter().lint(profile)
    issue = next(e for e in result.errors if e.code == "VRR_DISPLAY_MODE_GUIDANCE_MISMATCH")
    assert "vrr_optimize=True" in issue.details
