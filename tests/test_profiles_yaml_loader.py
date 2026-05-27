from __future__ import annotations

import pytest

from abso.profiles.yaml_loader import YAMLProfileLoader


def test_yaml_balanced_profile_uses_shared_handler_pipeline(tmp_path):
    profile_path = tmp_path / "custom.yaml"
    profile_path.write_text(
        """
profile_id: custom-balanced
display_name: Custom Balanced
description: Test profile
optimization_target: stable_online
executable_hints:
  - CustomGame.exe
metadata:
  include_legacy_tweaks: true
settings:
  ProcessPriorityHandler:
    cpu_priority: 3
""".lstrip(),
        encoding="utf-8",
    )

    _profile_id, entry = YAMLProfileLoader().load_file(profile_path)
    profile = entry.profile_class()

    handler_names = [handler.__class__.__name__ for handler in profile.get_handlers()]

    assert handler_names == [
        "WindowsSettingsHandler",
        "PowerSettingsHandler",
        "RegistrySettingsHandler",
        "NvidiaSettingsHandler",
        "NetworkSettingsHandler",
        "MouseSettingsHandler",
        "GraphicsSettingsHandler",
        "MemorySettingsHandler",
        "ProcessPriorityHandler",
        "ColorProfileSettingsHandler",
        "DisplayColorRangeHandler",
    ]

    registry_settings = profile.get_settings("RegistrySettingsHandler")
    assert registry_settings["system_responsiveness"] == 10
    assert registry_settings["network_throttling"] == 0xFFFFFFFF

    memory_settings = profile.get_settings("MemorySettingsHandler")
    assert memory_settings == {
        "large_system_cache": 0,
        "disable_paging_executive": 1,
    }

    priority_settings = profile.get_settings("ProcessPriorityHandler")
    assert priority_settings == {
        "cpu_priority": 3,
        "io_priority": 2,
    }


def test_yaml_profile_normalizes_catalog_metadata(tmp_path):
    profile_path = tmp_path / "custom.yaml"
    profile_path.write_text(
        """
profile_id: custom-balanced
display_name: Custom Balanced
description: Test profile
optimization_target: stable_online
executable_hints:
  - CustomGame.exe
tray_category: Shooter
sync_mode: " OFF "
""".lstrip(),
        encoding="utf-8",
    )

    _profile_id, entry = YAMLProfileLoader().load_file(profile_path)

    assert entry.tray_category == "Shooters"
    assert entry.sync_mode == "off"


def test_yaml_profile_accepts_typed_metadata_overrides(tmp_path):
    profile_path = tmp_path / "custom.yaml"
    profile_path.write_text(
        """
profile_id: custom-balanced
display_name: Custom Balanced
description: Test profile
optimization_target: stable_online
executable_hints:
  - CustomGame.exe
metadata:
  is_online_profile: true
  network_scope: " Limited "
  graphics_api: " DX12 "
  cpu_affinity_strategy: " P_CORES_ONLY "
""".lstrip(),
        encoding="utf-8",
    )

    _profile_id, entry = YAMLProfileLoader().load_file(profile_path)
    profile = entry.profile_class()

    assert profile.is_online_profile is True
    assert profile.network_scope == "limited"
    assert profile.graphics_api == "dx12"
    assert profile.cpu_affinity_strategy == "p_cores_only"


def test_yaml_profile_returns_isolated_nested_settings(tmp_path):
    profile_path = tmp_path / "custom.yaml"
    profile_path.write_text(
        """
profile_id: custom-balanced
display_name: Custom Balanced
description: Test profile
optimization_target: stable_online
executable_hints:
  - CustomGame.exe
settings:
  RegistrySettingsHandler:
    game_priority:
      gpu_priority: 8
      priority: 6
      scheduling_category: High
in_game_settings:
  - category: Video
    setting: VSync
    value: Off
    reason: Avoid sync latency
""".lstrip(),
        encoding="utf-8",
    )

    _profile_id, entry = YAMLProfileLoader().load_file(profile_path)
    profile = entry.profile_class()

    first_settings = profile.get_settings("RegistrySettingsHandler")
    first_settings["game_priority"]["priority"] = 1
    first_guidance = profile.get_in_game_settings()
    first_guidance[0]["value"] = "On"

    second_settings = profile.get_settings("RegistrySettingsHandler")
    second_guidance = profile.get_in_game_settings()

    assert second_settings["game_priority"]["priority"] == 6
    assert second_guidance[0]["value"] == "Off"


@pytest.mark.parametrize(
    ("field", "yaml_value", "message"),
    [
        ("profile_id", "[]", "Expected 'profile_id' to be a non-empty string"),
        ("profile_id", "Bad Id", "Expected 'profile_id' to be a lowercase slug"),
        ("executable_hints", "CustomGame.exe", "Expected 'executable_hints'"),
        ("settings", "[]", "Expected 'settings' to be a mapping"),
        ("settings", "\n  ProcessPriorityHandler: 4", "Expected 'settings.ProcessPriorityHandler'"),
        ("metadata", "[]", "Expected 'metadata' to be a mapping"),
        ("metadata", "\n  1: true", "Expected 'metadata'"),
        ("in_game_settings", "not-a-list", "Expected 'in_game_settings'"),
        ("in_game_settings", "\n  - loose item", "Expected 'in_game_settings'"),
        (
            "in_game_settings",
            "\n  - setting:",
            "Expected 'in_game_settings'",
        ),
        ("tray_visible", "maybe", "Expected 'tray_visible' to be a boolean"),
        ("tray_rank", "high", "Expected 'tray_rank' to be an integer"),
        ("tray_category", "FPS", "Expected 'tray_category' to be one of"),
        ("sync_mode", "adaptive", "Expected 'sync_mode' to be one of"),
        ("tray_descriptin", "Typo", "Expected 'tray_descriptin' to be one of"),
    ],
)
def test_yaml_profile_rejects_malformed_field_types(
    tmp_path,
    field,
    yaml_value,
    message,
):
    defaults = {
        "profile_id": "custom-balanced",
        "display_name": "Custom Balanced",
        "description": "Test profile",
        "optimization_target": "stable_online",
        "executable_hints": "\n  - CustomGame.exe",
    }
    defaults[field] = yaml_value

    profile_path = tmp_path / "custom.yaml"
    profile_path.write_text(
        "\n".join(f"{key}: {value}" for key, value in defaults.items()),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        YAMLProfileLoader().load_file(profile_path)


@pytest.mark.parametrize(
    ("metadata_yaml", "message"),
    [
        ("is_online_profile: maybe", "Expected 'metadata.is_online_profile'"),
        ("is_online_profile:", "Expected 'metadata.is_online_profile'"),
        ("include_legacy_tweaks: 1", "Expected 'metadata.include_legacy_tweaks'"),
        ("is_online_profiel: true", "Expected 'metadata.is_online_profiel'"),
        ("network_scope: global", "Expected 'metadata.network_scope'"),
        ("network_scope:", "Expected 'metadata.network_scope'"),
        ("graphics_api: metal", "Expected 'metadata.graphics_api'"),
        ("graphics_api:", "Expected 'metadata.graphics_api'"),
        ("cpu_affinity_strategy: e_cores_only", "Expected 'metadata.cpu_affinity_strategy'"),
        ("cpu_affinity_strategy: 1", "Expected 'metadata.cpu_affinity_strategy'"),
    ],
)
def test_yaml_profile_rejects_invalid_metadata_values(
    tmp_path,
    metadata_yaml,
    message,
):
    profile_path = tmp_path / "custom.yaml"
    profile_path.write_text(
        f"""
profile_id: custom-balanced
display_name: Custom Balanced
description: Test profile
optimization_target: stable_online
executable_hints:
  - CustomGame.exe
metadata:
  {metadata_yaml}
""".lstrip(),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match=message):
        YAMLProfileLoader().load_file(profile_path)
