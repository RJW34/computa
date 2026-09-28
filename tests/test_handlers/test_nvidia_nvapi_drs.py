"""Targeted tests for NVAPI DRS setting resolution helpers."""

from __future__ import annotations

import ctypes
from unittest.mock import MagicMock

import pytest

from abso.settings.nvidia import nvapi_drs
from abso.settings.nvidia.nvapi_drs import NVDRS_GLOBAL_PROFILE_NAME, DRSProfileManager


@pytest.mark.parametrize("version,size", [(1, 12296), (2, 16392), (3, 16396), (4, 20492)])
def test_application_struct_matches_official_nvapi_abi(version, size):
    """nvapi.h V1-V4 layouts/version words must match the native driver ABI."""
    structure = getattr(nvapi_drs, f"NVDRS_APPLICATION_V{version}")
    assert ctypes.sizeof(structure) == size
    assert getattr(nvapi_drs, f"NVDRS_APPLICATION_VER{version}") == (version << 16) | size
    assert structure.launcher.offset == 8200
    if version >= 2:
        assert structure.fileInFolder.offset == 12296
    if version >= 3:
        assert structure.isMetro.offset == structure.isCommandLine.offset == 16392
        app = structure()
        app.isMetro = 1
        app.isCommandLine = 1
        assert bytes(app)[16392:16396] == b"\x03\x00\x00\x00"
    if version == 4:
        assert structure.commandLine.offset == 16396


def test_resolve_vsync_on_uses_nvapi_constant():
    """vsync=on must map to NVAPI's VSYNCMODE_FORCEON constant."""
    manager = DRSProfileManager()
    setting_id, value = manager._resolve_setting("vsync", "on")
    assert setting_id == manager.SETTING_IDS["vsync_mode"]
    assert value == 0x47814940


@pytest.mark.parametrize("value,expected", [("on", 1), ("off", 0), (1, 1), (0, 0)])
def test_shader_cache_uses_only_sdk_enabled_values(value, expected):
    manager = DRSProfileManager()
    assert manager._resolve_setting("shader_cache", value) == (0x00198FFF, expected)


@pytest.mark.parametrize("value", ["unlimited", "max", 2, "2", "0x2", 1024, 0xFFFFFFFF])
def test_shader_cache_invalid_size_is_rejected_before_driver_write(value):
    manager = DRSProfileManager()
    drs = MagicMock()
    with pytest.raises(ValueError, match="global settings"):
        manager._apply_single_setting(drs, object(), "shader_cache", value)
    drs.set_setting.assert_not_called()
    drs.delete_setting.assert_not_called()
    drs.get_base_profile.assert_not_called()


def test_shader_cache_enable_replaces_invalid_legacy_value_without_global_write():
    manager = DRSProfileManager()
    drs = MagicMock()
    profile = object()
    drs.get_setting.return_value = 2
    manager._apply_single_setting(drs, profile, "shader_cache", "on")
    drs.set_setting.assert_called_once_with(profile, 0x00198FFF, 1)
    drs.get_base_profile.assert_not_called()


@pytest.mark.parametrize("value", [None, "default"])
def test_shader_cache_default_removes_enabled_override(value):
    manager = DRSProfileManager()
    drs = MagicMock()
    profile = object()
    manager._apply_single_setting(drs, profile, "shader_cache", value)
    drs.delete_setting.assert_called_once_with(profile, 0x00198FFF)
    drs.set_setting.assert_not_called()


def test_all_builtin_profiles_request_valid_shader_cache_enable_values():
    from abso.profiles import get_all_profiles
    from abso.settings.nvidia import NvidiaSettingsHandler
    from abso.settings.nvidia.presets import NVIDIA_PRESETS

    manager = DRSProfileManager()
    handler = NvidiaSettingsHandler()
    configured = [preset["settings"] for preset in NVIDIA_PRESETS.values()]
    configured.extend(
        handler._resolve_requested_nvidia_settings(profile.get_settings("NvidiaSettingsHandler"))
        for profile in get_all_profiles().values()
    )
    for settings in configured:
        if "shader_cache" in settings:
            assert manager._resolve_setting("shader_cache", settings["shader_cache"]) == (0x00198FFF, 1)


def test_resolve_vsync_tear_control_disable_uses_nvapi_constant():
    """Tear control disable must map to NVAPI's VSYNCTEARCONTROL_DISABLE."""
    manager = DRSProfileManager()
    setting_id, value = manager._resolve_setting("vsync_tear_control", "disable")
    assert setting_id == manager.SETTING_IDS["vsync_tear_control"]
    assert value == 0x96861077


def test_resolve_global_vrr_mode_alias_maps_to_vrr_mode():
    """global_vrr_mode alias should resolve to vrr_mode setting ID."""
    manager = DRSProfileManager()
    setting_id, value = manager._resolve_setting("global_vrr_mode", "fullscreen_only")
    assert setting_id == manager.SETTING_IDS["vrr_mode"]
    assert value == 0x00000001


def test_apply_settings_to_global_applies_all_settings():
    """Global apply should call _apply_single_setting for each requested setting."""
    manager = DRSProfileManager()

    fake_profile = object()
    fake_drs = MagicMock()
    fake_drs.get_base_profile.return_value = fake_profile

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    manager._apply_single_setting = MagicMock(return_value=[])

    result = manager.apply_settings_to_global({
        "vrr_mode": "off",
        "vsync": "off",
    })

    assert result["profile_name"] == NVDRS_GLOBAL_PROFILE_NAME
    assert result["errors"] == []
    assert result["settings_applied"]["vrr_mode"] == "off"
    assert result["settings_applied"]["vsync"] == "off"
    assert manager._apply_single_setting.call_count == 2


def test_get_app_settings_prefers_explicit_profile_name():
    """Explicit profile_name should be used for readback instead of ABSO auto name."""
    manager = DRSProfileManager()

    fake_profile = object()
    fake_drs = MagicMock()
    fake_drs.find_profile_by_name.return_value = fake_profile
    fake_drs.get_setting.return_value = None

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    result = manager.get_app_settings("Overwatch.exe", profile_name="Overwatch 2")

    fake_drs.find_profile_by_name.assert_called_once_with("Overwatch 2")
    fake_drs.get_base_profile.assert_not_called()
    assert result["_profile"] == "Overwatch 2"


def test_apply_settings_to_app_reuses_bound_legacy_alias_when_requested_profile_is_unbound():
    """Prefer an already-bound legacy profile over a zero-app requested variant profile."""
    manager = DRSProfileManager()

    requested_profile = object()
    legacy_profile = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [
        {"name": "Rivals 2: Online G-SYNC", "num_apps": 0},
        {"name": "Rivals 2 Online", "num_apps": 1},
    ]
    fake_drs.find_profile_by_name.side_effect = lambda name: {
        "Rivals 2: Online G-SYNC": requested_profile,
        "Rivals 2 Online": legacy_profile,
    }.get(name)
    fake_drs.add_application_to_profile.side_effect = (
        lambda profile, exe: setattr(fake_drs, "_app_binding_failures", [exe])
    )

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    manager._apply_single_setting = MagicMock(return_value=[])

    result = manager.apply_settings_to_app(
        "Rivals2-Win64-Shipping.exe",
        {"vsync": "on"},
        profile_name="Rivals 2: Online G-SYNC",
        profile_aliases=["Rivals 2 Online"],
    )

    assert result["requested_profile_name"] == "Rivals 2: Online G-SYNC"
    assert result["profile_name"] == "Rivals 2 Online"
    assert result["app_bound"] is True
    assert "Reusing existing bound NVIDIA profile" in result["profile_selection_note"]
    fake_drs.find_profile_by_name.assert_called_with("Rivals 2 Online")


def test_probe_profile_binding_reuses_bound_case_variant_before_empty_exact_duplicate():
    """Case-only NVIDIA profile name drift should not strand a strict profile on an empty duplicate."""
    manager = DRSProfileManager()

    empty_duplicate = object()
    bound_predefined = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [
        {"name": "Counter-Strike 2", "num_apps": 0, "is_predefined": False},
        {"name": "Counter-strike 2", "num_apps": 2, "is_predefined": True},
    ]
    fake_drs.find_profile_by_name.side_effect = lambda name: {
        "Counter-Strike 2": empty_duplicate,
        "Counter-strike 2": bound_predefined,
    }.get(name)
    fake_drs.find_application_owner.return_value = None
    fake_drs.get_application_info.return_value = None

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()

    result = manager.probe_profile_binding(
        ["cs2.exe"],
        profile_name="Counter-Strike 2",
    )

    assert result["profile_name"] == "Counter-strike 2"
    assert result["app_binding_safe"] is True
    assert result["app_binding_state"] == "predefined_profile_trusted"
    assert "Reusing existing bound NVIDIA profile 'Counter-strike 2'" in (
        result["profile_selection_note"]
    )


def test_apply_settings_to_app_reuses_bound_case_variant_before_empty_exact_duplicate():
    """Apply should update the bound driver profile instead of an empty case-variant duplicate."""
    manager = DRSProfileManager()

    empty_duplicate = object()
    bound_predefined = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [
        {"name": "Counter-Strike 2", "num_apps": 0, "is_predefined": False},
        {"name": "Counter-strike 2", "num_apps": 2, "is_predefined": True},
    ]
    fake_drs.find_profile_by_name.side_effect = lambda name: {
        "Counter-Strike 2": empty_duplicate,
        "Counter-strike 2": bound_predefined,
    }.get(name)
    fake_drs.add_application_to_profile.side_effect = (
        lambda profile, exe: setattr(fake_drs, "_app_binding_statuses", {exe: "already_in_use"})
    )
    fake_drs.find_application_owner.return_value = None
    fake_drs.get_application_info.return_value = None

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    manager._apply_single_setting = MagicMock(return_value=[])

    result = manager.apply_settings_to_app(
        "cs2.exe",
        {"vsync": "on"},
        profile_name="Counter-Strike 2",
    )

    assert result["profile_name"] == "Counter-strike 2"
    assert result["app_bound"] is True
    assert result["app_binding_safe"] is True
    assert result["app_binding_state"] == "predefined_profile_trusted"
    assert result["settings_applied"]["vsync"] == "on"
    fake_drs.find_profile_by_name.assert_called_with("Counter-strike 2")


def test_apply_settings_to_app_confirms_existing_binding_when_owner_matches_selected_profile():
    """Existing binding should count as exact when ownership resolves to the selected profile."""
    manager = DRSProfileManager()

    selected_profile = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [{"name": "Overwatch 2", "num_apps": 1}]
    fake_drs.find_profile_by_name.return_value = selected_profile
    fake_drs.add_application_to_profile.side_effect = (
        lambda profile, exe: setattr(fake_drs, "_app_binding_statuses", {exe: "already_in_use"})
    )
    fake_drs.find_application_owner.return_value = {"profile_name": "Overwatch 2"}
    fake_drs.get_application_info.return_value = {"app_name": "Overwatch.exe"}

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    manager._apply_single_setting = MagicMock(return_value=[])

    result = manager.apply_settings_to_app(
        "Overwatch.exe",
        {"vsync": "on"},
        profile_name="Overwatch 2",
    )

    assert result["app_bound"] is True
    assert result["app_binding_exact"] is True
    assert result["app_binding_state"] == "existing_binding_confirmed"
    assert result["app_binding_owner_profile"] == "Overwatch 2"


def test_apply_settings_to_app_fails_when_executable_is_bound_to_different_profile():
    """ABSO should fail closed when NVAPI proves the executable belongs elsewhere."""
    manager = DRSProfileManager()

    selected_profile = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [{"name": "Overwatch 2", "num_apps": 0}]
    fake_drs.find_profile_by_name.return_value = selected_profile
    fake_drs.add_application_to_profile.side_effect = (
        lambda profile, exe: setattr(fake_drs, "_app_binding_statuses", {exe: "already_in_use"})
    )
    fake_drs.find_application_owner.return_value = {"profile_name": "Legacy Wrong Profile"}
    fake_drs.get_application_info.return_value = None

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    manager._apply_single_setting = MagicMock(return_value=[])

    result = manager.apply_settings_to_app(
        "Overwatch.exe",
        {"vsync": "on"},
        profile_name="Overwatch 2",
    )

    assert result["app_bound"] is False
    assert result["app_binding_exact"] is False
    assert result["app_binding_state"] == "bound_elsewhere"
    assert result["app_binding_owner_profile"] == "Legacy Wrong Profile"
    assert result["settings_applied"] == {}


def test_probe_profile_binding_trusts_predefined_profile_without_conflicting_owner():
    """Predefined NVIDIA profiles should be safe when NVAPI shows no conflicting owner."""
    manager = DRSProfileManager()

    predefined_profile = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [
        {"name": "Overwatch 2", "num_apps": 2, "is_predefined": True},
    ]
    fake_drs.find_profile_by_name.return_value = predefined_profile
    fake_drs.find_application_owner.return_value = None
    fake_drs.get_application_info.return_value = None

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()

    result = manager.probe_profile_binding(
        ["Overwatch.exe"],
        profile_name="Overwatch 2",
    )

    assert result["app_binding_exact"] is False
    assert result["app_binding_safe"] is True
    assert result["app_binding_state"] == "predefined_profile_trusted"
    assert "NVIDIA predefined profile 'Overwatch 2'" in result["app_binding_note"]


def test_apply_settings_to_app_trusts_predefined_profile_without_conflicting_owner():
    """Applying to a predefined NVIDIA profile should proceed when no conflicting owner exists."""
    manager = DRSProfileManager()

    selected_profile = object()
    fake_drs = MagicMock()
    fake_drs.enumerate_profiles.return_value = [{"name": "Overwatch 2", "num_apps": 2, "is_predefined": True}]
    fake_drs.find_profile_by_name.return_value = selected_profile
    fake_drs.add_application_to_profile.side_effect = (
        lambda profile, exe: setattr(fake_drs, "_app_binding_statuses", {exe: "already_in_use"})
    )
    fake_drs.find_application_owner.return_value = None
    fake_drs.get_application_info.return_value = None

    class _Ctx:
        def __enter__(self):
            return fake_drs

        def __exit__(self, exc_type, exc, tb):
            return False

    manager._drs = _Ctx()
    manager._apply_single_setting = MagicMock(return_value=[])

    result = manager.apply_settings_to_app(
        "Overwatch.exe",
        {"vsync": "on"},
        profile_name="Overwatch 2",
    )

    assert result["app_bound"] is True
    assert result["app_binding_exact"] is False
    assert result["app_binding_safe"] is True
    assert result["app_binding_state"] == "predefined_profile_trusted"
    assert result["settings_applied"]["vsync"] == "on"
