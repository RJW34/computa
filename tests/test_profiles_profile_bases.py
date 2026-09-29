from __future__ import annotations

from abso.profiles.productivity_oled import ProductivityHDRProfile
from abso.profiles.profile_bases import fso_overrides, merge_settings_map
from abso.profiles.rivals2_nosync import Rivals2NoSyncProfile


def test_merge_settings_map_returns_isolated_nested_values() -> None:
    base_map = {
        "RegistrySettingsHandler": {
            "game_priority": {
                "gpu_priority": 8,
                "priority": 6,
            },
            "flags": ["base"],
        },
    }
    overrides_map = {
        "RegistrySettingsHandler": {
            "game_priority": {
                "gpu_priority": 8,
                "priority": 3,
            },
            "flags": ["override"],
        },
    }

    merged = merge_settings_map(base_map, overrides_map)
    merged["RegistrySettingsHandler"]["game_priority"]["priority"] = 1
    merged["RegistrySettingsHandler"]["flags"].append("mutated")

    assert overrides_map["RegistrySettingsHandler"]["game_priority"]["priority"] == 3
    assert overrides_map["RegistrySettingsHandler"]["flags"] == ["override"]


def test_fso_overrides_preserves_order_and_requested_flag() -> None:
    overrides = fso_overrides(
        ["Game-Win64-Shipping.exe", "GameLauncher.exe"],
        disabled=False,
    )

    assert list(overrides) == ["Game-Win64-Shipping.exe", "GameLauncher.exe"]
    assert overrides == {
        "Game-Win64-Shipping.exe": False,
        "GameLauncher.exe": False,
    }


def test_shared_profile_settings_are_isolated_between_calls() -> None:
    profile = Rivals2NoSyncProfile()

    first = profile.get_settings("RegistrySettingsHandler")
    first["fullscreen_optimizations"]["Rivals2-Win64-Shipping.exe"] = False

    second = profile.get_settings("RegistrySettingsHandler")

    assert second["fullscreen_optimizations"]["Rivals2-Win64-Shipping.exe"] is True


def test_productivity_profile_settings_are_isolated_between_calls() -> None:
    profile = ProductivityHDRProfile()

    first = profile.get_settings("WindowsSettingsHandler")
    first["hdr"] = False

    second = profile.get_settings("WindowsSettingsHandler")

    assert second["hdr"] is True
