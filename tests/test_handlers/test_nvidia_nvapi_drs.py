"""Targeted tests for NVAPI DRS setting resolution helpers."""

from __future__ import annotations

from unittest.mock import MagicMock

from abso.settings.nvidia.nvapi_drs import DRSProfileManager, NVDRS_GLOBAL_PROFILE_NAME


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
