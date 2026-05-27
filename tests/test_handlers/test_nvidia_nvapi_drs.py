"""Targeted tests for NVAPI DRS setting resolution helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from abso.settings.nvidia.nvapi_drs import NVDRS_GLOBAL_PROFILE_NAME, DRSProfileManager


def test_resolve_vsync_on_uses_nvapi_constant():
    """vsync=on must map to NVAPI's VSYNCMODE_FORCEON constant."""
    manager = DRSProfileManager()
    setting_id, value = manager._resolve_setting("vsync", "on")
    assert setting_id == manager.SETTING_IDS["vsync_mode"]
    assert value == 0x47814940


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
    manager._apply_single_setting = MagicMock()

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
    manager._apply_single_setting = MagicMock()

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
    manager._apply_single_setting = MagicMock()

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
    manager._apply_single_setting = MagicMock()

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
    manager._apply_single_setting = MagicMock()

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
