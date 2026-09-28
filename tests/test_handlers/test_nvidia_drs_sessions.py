"""DRS reads must not commit the driver database or leak session state.

Exercise the real wrapper and high-level callers with fake native endpoints;
these tests never load NVAPI or access the installed driver.
"""

from unittest.mock import MagicMock

import pytest

from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.nvidia.nvapi_drs import (
    NVAPIDRS,
    DRSProfileManager,
    NVAPIError,
    NvAPIStatus,
    _str_to_nvapi_unicode,
)


@pytest.fixture
def native_drs(monkeypatch):
    drs = NVAPIDRS()
    drs._initialized = True
    monkeypatch.setattr(drs, "initialize", lambda: True)

    def handle_result(*args):
        args[-1]._obj.value = 0x102
        return NvAPIStatus.OK

    def setting_result(session, profile, setting_id, setting_ptr):
        setting_ptr._obj.currentValue.u32Value = 1
        return NvAPIStatus.OK

    def profile_result(session, profile, info_ptr):
        _str_to_nvapi_unicode("Test Game", info_ptr._obj.profileName)
        info_ptr._obj.numOfApps = 1
        return NvAPIStatus.OK

    def application_result(session, app_name, profile_ptr, app_ptr):
        profile_ptr._obj.value = 0x102
        _str_to_nvapi_unicode("game.exe", app_ptr._obj.appName)
        return NvAPIStatus.OK

    def enum_result(session, index, profile_ptr):
        if index:
            return NvAPIStatus.END_ENUMERATION
        return handle_result(profile_ptr)

    endpoints = {
        name: MagicMock(return_value=NvAPIStatus.OK)
        for name in (
            "CreateSession", "LoadSettings", "SaveSettings", "DestroySession",
            "SetSetting", "DeleteProfileSetting", "CreateProfile", "DeleteProfile",
            "CreateApplication", "FindProfileByName", "GetBaseProfile", "GetSetting",
            "GetProfileInfo", "FindApplicationByName", "EnumProfiles",
        )
    }
    for name in ("CreateSession", "CreateProfile", "FindProfileByName", "GetBaseProfile"):
        endpoints[name].side_effect = handle_result
    endpoints["GetSetting"].side_effect = setting_result
    endpoints["GetProfileInfo"].side_effect = profile_result
    endpoints["FindApplicationByName"].side_effect = application_result
    endpoints["EnumProfiles"].side_effect = enum_result
    monkeypatch.setattr(
        drs, "_get_function", lambda name, *args: endpoints[name.removeprefix("NvAPI_DRS_")]
    )
    return drs, endpoints


def test_read_context_and_explicit_clean_save_do_not_commit(native_drs):
    drs, endpoints = native_drs
    with drs:
        profile = drs.find_profile_by_name("Test Game")
        assert drs.get_setting(profile, 123) == 1
        drs.save_settings()
    endpoints["SaveSettings"].assert_not_called()
    endpoints["DestroySession"].assert_called_once()
    assert drs._session is None


@pytest.mark.parametrize("operation", [
    lambda manager: manager.get_app_settings(),
    lambda manager: manager.get_app_settings("game.exe", "Test Game"),
    lambda manager: manager.list_profiles(),
    lambda manager: manager.probe_profile_binding(["game.exe"], "Test Game"),
    lambda manager: manager.delete_profiles_by_name(["Test Game"], dry_run=True),
    lambda manager: manager.cleanup_unused_profiles(dry_run=True),
], ids=["global-read", "app-read", "list", "binding-probe", "delete-dry-run", "cleanup-dry-run"])
def test_manager_read_paths_never_commit(native_drs, operation):
    drs, endpoints = native_drs
    manager = DRSProfileManager()
    manager._drs = drs
    assert operation(manager)
    endpoints["SaveSettings"].assert_not_called()
    assert endpoints["DestroySession"].call_count >= 1


def test_handler_verification_including_binding_never_commits(native_drs, monkeypatch):
    drs, endpoints = native_drs
    manager = DRSProfileManager()
    manager._drs = drs
    monkeypatch.setattr("abso.settings.nvidia.nvapi_drs.DRSProfileManager", lambda: manager)
    result = NvidiaSettingsHandler().verify_active({
        "executables": ["game.exe"],
        "profile_name": "Test Game",
        "require_exact_binding": True,
        "shader_cache": "on",
        "global_vrr_mode": "fullscreen_only",
    })
    assert result["all_active"] is True, result
    assert result["scope"] == "profile_and_binding_readback"
    endpoints["SaveSettings"].assert_not_called()
    assert endpoints["DestroySession"].call_count >= 3


MUTATORS = [
    ("SetSetting", lambda drs: drs.set_setting(0x102, 123, 1)),
    ("DeleteProfileSetting", lambda drs: drs.delete_setting(0x102, 123)),
    ("CreateProfile", lambda drs: drs.create_profile("New Profile")),
    ("DeleteProfile", lambda drs: drs.delete_profile(0x102)),
    ("CreateApplication", lambda drs: drs.add_application_to_profile(0x102, "game.exe")),
]


@pytest.mark.parametrize("endpoint,mutate", MUTATORS, ids=[item[0] for item in MUTATORS])
def test_successful_mutator_commits_once(native_drs, endpoint, mutate):
    drs, endpoints = native_drs
    with drs:
        mutate(drs)
    endpoints[endpoint].assert_called_once()
    endpoints["SaveSettings"].assert_called_once()
    endpoints["DestroySession"].assert_called_once()


@pytest.mark.parametrize("endpoint,mutate", MUTATORS, ids=[item[0] for item in MUTATORS])
def test_failed_mutator_does_not_commit_when_caller_handles_error(native_drs, endpoint, mutate):
    drs, endpoints = native_drs
    endpoints[endpoint].side_effect = None
    endpoints[endpoint].return_value = NvAPIStatus.ERROR
    with drs:
        if endpoint == "DeleteProfile":
            assert mutate(drs) is False
        else:
            with pytest.raises(NVAPIError):
                mutate(drs)
    endpoints["SaveSettings"].assert_not_called()


@pytest.mark.parametrize("endpoint,status,mutate", [
    ("CreateProfile", NvAPIStatus.PROFILE_NAME_IN_USE, MUTATORS[2][1]),
    ("DeleteProfile", NvAPIStatus.PROFILE_NOT_FOUND, MUTATORS[3][1]),
    ("DeleteProfileSetting", NvAPIStatus.SETTING_NOT_FOUND, MUTATORS[1][1]),
    ("CreateApplication", NvAPIStatus.EXECUTABLE_ALREADY_IN_USE, MUTATORS[4][1]),
    ("CreateApplication", NvAPIStatus.INCOMPATIBLE_STRUCT_VERSION, MUTATORS[4][1]),
])
def test_unchanged_mutation_outcome_does_not_commit(native_drs, endpoint, status, mutate):
    drs, endpoints = native_drs
    endpoints[endpoint].side_effect = None
    endpoints[endpoint].return_value = status
    with drs:
        mutate(drs)
    endpoints["SaveSettings"].assert_not_called()


def test_explicit_save_is_not_repeated_on_exit(native_drs):
    drs, endpoints = native_drs
    manager = DRSProfileManager()
    manager._drs = drs
    assert manager.delete_profiles_by_name(["Test Game"])["deleted"] == ["Test Game"]
    endpoints["SaveSettings"].assert_called_once()
    with drs:
        drs.get_base_profile()
    endpoints["SaveSettings"].assert_called_once()


def test_mutations_after_explicit_save_commit_again_on_exit(native_drs):
    drs, endpoints = native_drs
    with drs:
        drs.set_setting(0x102, 123, 1)
        drs.set_setting(0x102, 124, 2)
        drs.save_settings()
        drs.save_settings()
        assert endpoints["SaveSettings"].call_count == 1
        drs.set_setting(0x102, 125, 3)
    assert endpoints["SaveSettings"].call_count == 2


def test_body_exception_discards_writes_and_next_read_stays_clean(native_drs):
    drs, endpoints = native_drs
    with pytest.raises(ValueError, match="body failure"), drs:
        drs.set_setting(0x102, 123, 1)
        raise ValueError("body failure")
    with drs:
        drs.get_base_profile()
    endpoints["SaveSettings"].assert_not_called()
    assert endpoints["DestroySession"].call_count == 2


def test_reloading_discards_unsaved_changes(native_drs):
    drs, endpoints = native_drs
    with drs:
        drs.set_setting(0x102, 123, 1)
        drs.load_settings()
    endpoints["SaveSettings"].assert_not_called()


def test_failed_save_still_cleans_up_without_retry(native_drs, caplog):
    drs, endpoints = native_drs
    endpoints["SaveSettings"].return_value = NvAPIStatus.ERROR
    with drs:
        drs.set_setting(0x102, 123, 1)
    endpoints["SaveSettings"].assert_called_once()
    endpoints["DestroySession"].assert_called_once()
    assert "Failed to save settings" in caplog.text
    with drs:
        drs.get_base_profile()
    endpoints["SaveSettings"].assert_called_once()


@pytest.mark.parametrize("cleanup_fails", [False, True])
def test_failed_entry_cleans_up_and_preserves_load_error(native_drs, cleanup_fails):
    drs, endpoints = native_drs
    endpoints["LoadSettings"].return_value = NvAPIStatus.ERROR
    if cleanup_fails:
        endpoints["DestroySession"].side_effect = RuntimeError("cleanup failure")
    with pytest.raises(NVAPIError, match="Failed to load DRS settings"), drs:
        pytest.fail("entry must fail")
    endpoints["SaveSettings"].assert_not_called()
    endpoints["DestroySession"].assert_called_once()
    assert drs._session is None


def test_cleanup_exception_does_not_replace_body_exception(native_drs):
    drs, endpoints = native_drs
    endpoints["DestroySession"].side_effect = RuntimeError("cleanup failure")
    with pytest.raises(ValueError, match="body failure"), drs:
        drs.set_setting(0x102, 123, 1)
        raise ValueError("body failure")
    endpoints["SaveSettings"].assert_not_called()
    assert drs._session is None
