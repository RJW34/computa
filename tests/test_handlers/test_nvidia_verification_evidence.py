"""Verification must distinguish matching driver evidence from unavailable state."""

from unittest.mock import MagicMock

import pytest

from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.nvidia.nvapi_drs import DRSProfileManager


@pytest.fixture
def driver_manager(monkeypatch):
    manager = DRSProfileManager()
    manager._drs = MagicMock()
    manager._drs.__enter__.return_value.find_profile_by_name.return_value = object()
    manager._get_application_owner_profile_name = MagicMock(return_value="Fortnite")
    manager._profile_contains_application = MagicMock(return_value=False)
    manager.get_app_settings = MagicMock(return_value={
        "_profile": "Fortnite", "frame_rate_limiter_v3": 297,
    })
    monkeypatch.setattr("abso.settings.nvidia.nvapi_drs.DRSProfileManager", lambda: manager)
    return manager


def game_settings(**overrides):
    return {
        "executables": ["FortniteClient-Win64-Shipping.exe"],
        "profile_name": "Fortnite",
        "max_frame_rate": 297,
        "require_exact_binding": True,
        **overrides,
    }


@pytest.mark.parametrize("readback", [
    {"_profile": "Fortnite"},
    {"_profile": "Fortnite", "frame_rate_limiter_v3": None},
])
def test_unreadable_requested_setting_fails_verification(driver_manager, readback):
    driver_manager.get_app_settings.return_value = readback

    result = NvidiaSettingsHandler().verify_active(game_settings())

    assert result["all_active"] is False
    assert any("max_frame_rate: driver readback unavailable" in item for item in result["setting_failures"])


def test_unreadable_global_setting_fails_verification(driver_manager):
    driver_manager.get_app_settings.side_effect = [
        {"_profile": "Base Profile"},
        {"_profile": "Fortnite", "frame_rate_limiter_v3": 297},
    ]

    result = NvidiaSettingsHandler().verify_active(game_settings(global_vrr_mode="fullscreen_and_windowed"))

    assert result["all_active"] is False
    assert any("vrr_mode: driver readback unavailable" in item for item in result["global_failures"]), result


@pytest.mark.parametrize("profile_name", ["Base Profile", None])
def test_matching_values_from_unproven_profile_do_not_pass(driver_manager, profile_name):
    driver_manager.get_app_settings.return_value = {
        "_profile": profile_name, "frame_rate_limiter_v3": 297,
    }

    result = NvidiaSettingsHandler().verify_active(game_settings())

    assert result["all_active"] is False
    assert any("readback profile could not be confirmed" in item for item in result["setting_failures"])


def test_matching_alias_setting_value_is_valid_evidence(driver_manager):
    driver_manager.get_app_settings.return_value = {
        "_profile": "Fortnite", "frame_rate_limiter": 297,
    }

    result = NvidiaSettingsHandler().verify_active(game_settings())

    assert result["all_active"] is True
    assert result["scope"] == "profile_and_binding_readback"


def test_auto_cap_without_refresh_cannot_accept_current_60_cap(driver_manager, monkeypatch):
    driver_manager.get_app_settings.return_value = {
        "_profile": "Fortnite", "frame_rate_limiter_v3": 60,
    }
    monkeypatch.setattr(NvidiaSettingsHandler, "_detect_primary_refresh_rate", lambda self: None)

    result = NvidiaSettingsHandler().verify_active(game_settings(max_frame_rate=60, auto_vrr_fps_cap=True))

    assert result["all_active"] is False
    assert any("refresh rate is unavailable" in item for item in result["setting_failures"])


def test_probe_can_supply_real_owner_evidence(driver_manager):
    driver_manager._get_application_owner_profile_name.return_value = None
    driver_manager.probe_profile_binding = MagicMock(return_value={
        "app_binding_state": "confirmed",
        "app_binding_exact": True,
        "app_binding_owner_profiles": {"FortniteClient-Win64-Shipping.exe": "Fortnite"},
    })

    result = NvidiaSettingsHandler().verify_active(game_settings())

    assert result["all_active"] is True
    assert result["scope"] == "profile_and_binding_readback"
    assert result["binding_owner_profiles"] == {"FortniteClient-Win64-Shipping.exe": "Fortnite"}


def test_probe_cannot_replace_a_conflicting_observed_owner(driver_manager):
    driver_manager._get_application_owner_profile_name.return_value = "Wrong Profile"
    driver_manager.probe_profile_binding = MagicMock(return_value={
        "app_binding_safe": True,
        "app_binding_owner_profiles": {"FortniteClient-Win64-Shipping.exe": "Fortnite"},
    })

    result = NvidiaSettingsHandler().verify_active(game_settings())

    assert result["all_active"] is False
    assert any("Wrong Profile" in item for item in result["setting_failures"])


def test_missing_explicit_profile_never_reads_base_or_generated_profile():
    manager = DRSProfileManager()
    manager._drs = MagicMock()
    drs = manager._drs.__enter__.return_value
    drs.find_profile_by_name.return_value = None

    result = manager.get_app_settings("FortniteClient-Win64-Shipping.exe", profile_name="Fortnite")

    assert result == {"_profile": "Fortnite", "_error": "NVIDIA profile 'Fortnite' was not found."}
    drs.find_profile_by_name.assert_called_once_with("Fortnite")
    drs.get_base_profile.assert_not_called()
    drs.get_setting.assert_not_called()


def test_post_apply_verification_rejects_missing_readback():
    failures = NvidiaSettingsHandler()._collect_verification_failures(
        DRSProfileManager(), {"_profile": "Fortnite"}, {"max_frame_rate": 297},
    )

    assert failures == ["max_frame_rate: driver readback unavailable; expected=297"]
