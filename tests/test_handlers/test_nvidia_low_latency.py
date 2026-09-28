"""Native driver values are evidence of configuration, not runtime activation."""

import xml.etree.ElementTree as ET
from unittest.mock import MagicMock

import pytest

from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.nvidia.nvapi_drs import DRSProfileManager
from abso.settings.nvidia.parsing import parse_nip_file, parse_vsync_value
from abso.settings.nvidia.profiles import _build_settings_xml, generate_custom_profile


@pytest.mark.parametrize("mode,queue,ull,cpl", [("off", 0, 0, 0), ("on", 1, 0, 1), ("ultra", 1, 1, 2)])
def test_mode_writes_distinct_native_queue_and_ull_controls(mode, queue, ull, cpl):
    manager = DRSProfileManager()
    drs = MagicMock()
    drs.get_setting.return_value = 1
    assert manager._apply_single_setting(drs, 42, "low_latency_mode", mode) == []
    writes = {call.args[1]: call.args[2] for call in drs.set_setting.call_args_list}
    assert writes == {0x007BA09E: queue, 0x10835000: ull, 0x0005F543: cpl}


def test_unknown_private_controls_are_not_written_or_reported_applied():
    manager = DRSProfileManager()
    drs = MagicMock()
    drs.get_setting.return_value = None
    result = {"settings_applied": {}}
    manager._record_setting_apply(drs, 42, "low_latency_mode", "off", result)
    drs.set_setting.assert_called_once_with(42, 0x007BA09E, 0)
    assert result["settings_applied"] == {}
    assert result["manual_steps"][0]["satisfied"] is None
    assert result["manual_steps"][0]["expected_label"] == "Off"


def test_default_deletes_available_overrides():
    manager = DRSProfileManager()
    drs = MagicMock()
    drs.get_setting.return_value = 1
    manager._apply_single_setting(drs, 42, "low_latency_mode", "default")
    assert {call.args[1] for call in drs.delete_setting.call_args_list} == {0x007BA09E, 0x10835000, 0x0005F543}
    drs.set_setting.assert_not_called()


@pytest.mark.parametrize("value", ["nonsense", 3, 1.5])
def test_invalid_mode_cannot_be_written(value):
    drs = MagicMock()
    with pytest.raises(ValueError, match="Low Latency Mode"):
        DRSProfileManager()._apply_single_setting(drs, 42, "low_latency_mode", value)
    drs.set_setting.assert_not_called()


def test_reflex_is_not_a_driver_ull_alias():
    drs = MagicMock()
    with pytest.raises(ValueError, match="in-game"):
        DRSProfileManager()._apply_single_setting(drs, 42, "nvidia_reflex", "on")
    drs.set_setting.assert_not_called()


@pytest.fixture
def driver(monkeypatch):
    manager = DRSProfileManager()
    manager._drs = MagicMock()
    manager._get_application_owner_profile_name = MagicMock(return_value="Game")
    manager.get_app_settings = MagicMock(return_value={"_profile": "Game", "prerendered_frames": 0})
    monkeypatch.setattr("abso.settings.nvidia.nvapi_drs.DRSProfileManager", lambda: manager)
    return manager


def verify_settings(mode="off", **extra):
    return {"low_latency_mode": mode, "executables": ["game.exe"], "profile_name": "Game", **extra}


def test_unknown_private_controls_require_manual_confirmation_without_reapply(driver):
    result = NvidiaSettingsHandler().verify_active(verify_settings())
    assert result["all_active"] is True
    assert result["setting_failures"] == []
    assert result["manual_steps"][0]["satisfied"] is None
    driver._drs.save_settings.assert_not_called()


@pytest.mark.parametrize("readback", [
    {"prerendered_frames": 2},  # Historical bug: two frames are not Ultra.
    {"prerendered_frames": 1, "ultra_low_latency": 0},
    {"prerendered_frames": 1, "low_latency_mode": 0},
])
def test_known_contradiction_is_a_mismatch_even_if_other_private_controls_unknown(driver, readback):
    driver.get_app_settings.return_value.update(readback)
    result = NvidiaSettingsHandler().verify_active(verify_settings("ultra"))
    assert result["all_active"] is False
    assert result["setting_failures"]


def test_successful_private_readbacks_need_no_manual_confirmation(driver):
    driver.get_app_settings.return_value.update(prerendered_frames=1, ultra_low_latency=1, low_latency_mode=2)
    result = NvidiaSettingsHandler().verify_active(verify_settings("ultra"))
    assert result["all_active"] is True
    assert not result.get("manual_steps")


def test_default_does_not_compare_inherited_numeric_value_to_none(driver):
    result = NvidiaSettingsHandler().verify_active(verify_settings("default"))
    assert result["all_active"] is True
    assert result["manual_steps"][0]["expected_label"] == "Default"
    assert result["manual_steps"][0]["satisfied"] is None


def test_global_and_app_manual_targets_stay_distinct(driver):
    result = NvidiaSettingsHandler().verify_active(verify_settings(global_settings={"low_latency_mode": "default"}))
    assert {step["key"] for step in result["manual_steps"]} == {"low_latency_mode", "global.low_latency_mode"}


def test_apply_carries_manual_reminder_and_verifies_partial_queue_write(driver, monkeypatch):
    handler = NvidiaSettingsHandler()
    monkeypatch.setattr(handler, "_cleanup_stale_profiles", lambda *args: None)
    driver.apply_settings_to_app = MagicMock(return_value={
        "settings_applied": {}, "errors": [], "app_bound": True,
        "manual_steps": [DRSProfileManager.low_latency_manual_step("off")],
    })
    result = handler.apply(verify_settings())
    assert result["success"] is True
    assert len(result["manual_steps"]) == 1
    assert result["manual_steps"][0]["instruction"] in result["notices"]
    assert not any(line == "low_latency_mode: off" for line in result["applied"])
    driver.get_app_settings.return_value["prerendered_frames"] = 2
    assert handler.apply(verify_settings())["success"] is False


@pytest.mark.parametrize("mode,mode_value,tear_value", [
    ("on", 0x47814940, 0x96861077),
    ("fast", 0x18888888, 0x96861077),
    ("adaptive", 0x47814940, 0x99941284),
    ("adaptive_half", 0x32610244, 0x99941284),
])
def test_compound_vsync_values_match_inspector_and_verify_companion(mode, mode_value, tear_value):
    manager = DRSProfileManager()
    drs = MagicMock()
    manager._apply_single_setting(drs, 42, "vsync", mode)
    assert {call.args[1]: call.args[2] for call in drs.set_setting.call_args_list} == {
        0x00A879CF: mode_value, 0x005A375C: tear_value,
    }
    xml = ET.fromstring("<Settings>" + _build_settings_xml({"vsync": mode}) + "</Settings>")
    assert {int(item.findtext("SettingID")): int(item.findtext("SettingValue")) for item in xml} == {
        0x00A879CF: mode_value, 0x005A375C: tear_value,
    }
    handler = NvidiaSettingsHandler()
    readback = {"vsync_mode": mode_value, "vsync_tear_control": tear_value}
    assert handler._collect_verification_failures(manager, readback, {"vsync": mode}) == []
    readback["vsync_tear_control"] = 0
    assert handler._collect_verification_failures(manager, readback, {"vsync": mode})


def test_real_nip_roundtrip_preserves_separate_ull_and_native_vsync():
    path = generate_custom_profile({"low_latency_mode": "ultra", "vsync": "adaptive"}, "native-values-regression")
    parsed = parse_nip_file(path)
    assert parsed["prerendered_frames"] == "1"
    assert parsed["low_latency_mode"] == "ultra"
    assert parsed["ultra_low_latency"] == "1"
    assert parsed["vsync"] == "adaptive"
    assert parse_vsync_value("0") == "unknown"  # Historical wrong ordinal is not a native mode.


def test_vsync_on_rejects_inherited_adaptive_tear_control():
    failures = NvidiaSettingsHandler()._collect_verification_failures(
        DRSProfileManager(), {"vsync_mode": 0x47814940, "vsync_tear_control": 0x99941284}, {"vsync": "on"},
    )
    assert any("vsync_tear_control" in failure for failure in failures)


@pytest.mark.parametrize("explicit_first", [True, False])
def test_explicit_tear_control_wins_regardless_of_input_order(explicit_first):
    settings = {"vsync_tear_control": "enable", "vsync": "on"} if explicit_first else {"vsync": "on", "vsync_tear_control": "enable"}
    manager = DRSProfileManager()
    manager._drs = MagicMock()
    drs = manager._drs.__enter__.return_value
    result = manager.apply_settings_to_global(settings)
    assert result["errors"] == []
    writes = {call.args[1]: call.args[2] for call in drs.set_setting.call_args_list}
    assert writes == {0x00A879CF: 0x47814940, 0x005A375C: 0x99941284}
    readback = {"vsync_mode": writes[0x00A879CF], "vsync_tear_control": writes[0x005A375C]}
    assert NvidiaSettingsHandler()._collect_verification_failures(manager, readback, settings) == []
    xml = ET.fromstring("<Settings>" + _build_settings_xml(settings) + "</Settings>")
    assert {int(item.findtext("SettingID")): int(item.findtext("SettingValue")) for item in xml} == writes
