"""Hermetic tests for the AMD Radeon settings handler and intent mapping."""

from __future__ import annotations

from typing import Any

import pytest

import abso.settings.amd as amd_module
from abso.settings.amd import (
    _AMD_CN_KEY,
    _AMD_DRIVER_KEY,
    AmdSettingsHandler,
    amd_settings_from_nvidia_intent,
)

# The Radeon competitive baseline every gaming lane derives on AMD machines.
COMPETITIVE_BASELINE = {
    "disable_ulps": True,
    "anti_lag": True,
    "enhanced_sync": False,
    "radeon_chill": False,
    "radeon_boost": False,
}


class FakeRegistry:
    """In-memory stand-in for the module's registry read/write helpers."""

    def __init__(self, values: dict[tuple[str, str], int] | None = None) -> None:
        self.values: dict[tuple[str, str], int] = dict(values or {})
        self.writes: list[tuple[str, str, int]] = []

    def read(self, hive: int, subkey: str, name: str) -> int | None:
        return self.values.get((subkey, name))

    def write(self, hive: int, subkey: str, name: str, value: int) -> None:
        self.values[(subkey, name)] = value
        self.writes.append((subkey, name, value))


@pytest.fixture
def fake_registry(monkeypatch) -> FakeRegistry:
    registry = FakeRegistry()
    monkeypatch.setattr(amd_module, "_read_reg_dword", registry.read)
    monkeypatch.setattr(amd_module, "_write_reg_dword", registry.write)
    return registry


@pytest.fixture
def amd_present(monkeypatch) -> None:
    monkeypatch.setattr(AmdSettingsHandler, "_amd_present_cached", True)


@pytest.fixture
def amd_absent(monkeypatch) -> None:
    monkeypatch.setattr(AmdSettingsHandler, "_amd_present_cached", False)


# --- presence gating ---------------------------------------------------------


def test_detect_without_amd_gpu_reports_absence(amd_absent) -> None:
    assert AmdSettingsHandler().detect() == {"is_amd_present": False}


def test_audit_without_amd_gpu_is_empty(amd_absent) -> None:
    assert AmdSettingsHandler().audit() == []


def test_apply_without_amd_gpu_is_a_successful_noop(amd_absent, fake_registry) -> None:
    result = AmdSettingsHandler().apply(dict(COMPETITIVE_BASELINE))
    assert result["success"] is True
    assert result["applied"] == []
    assert fake_registry.writes == []


def test_restore_without_amd_gpu_succeeds_without_writes(amd_absent, fake_registry) -> None:
    assert AmdSettingsHandler().restore({"enable_ulps": 1}) is True
    assert fake_registry.writes == []


# --- detect / audit ----------------------------------------------------------


def test_detect_reads_driver_and_software_settings(amd_present, fake_registry) -> None:
    fake_registry.values[(_AMD_DRIVER_KEY, "EnableUlps")] = 1
    fake_registry.values[(_AMD_CN_KEY, "AntiLag")] = 0
    fake_registry.values[(_AMD_CN_KEY, "EnhancedSync")] = 1

    state = AmdSettingsHandler().detect()

    assert state["is_amd_present"] is True
    assert state["enable_ulps"] == 1
    assert state["anti_lag"] == 0
    assert state["enhanced_sync"] == 1
    assert state["radeon_chill_enabled"] is None


def test_audit_flags_latency_hostile_radeon_state(amd_present, fake_registry) -> None:
    fake_registry.values[(_AMD_DRIVER_KEY, "EnableUlps")] = 1
    fake_registry.values[(_AMD_CN_KEY, "EnhancedSync")] = 1
    fake_registry.values[(_AMD_CN_KEY, "ChillEnabled")] = 1
    fake_registry.values[(_AMD_CN_KEY, "AntiLag")] = 0

    titles = [issue.title for issue in AmdSettingsHandler().audit()]

    assert any("ULPS" in title for title in titles)
    assert any("Enhanced Sync" in title for title in titles)
    assert any("Radeon Chill" in title for title in titles)
    assert any("Anti-Lag" in title for title in titles)


# --- apply / backup / restore ------------------------------------------------


def test_apply_competitive_baseline_writes_expected_values(amd_present, fake_registry) -> None:
    result = AmdSettingsHandler().apply(dict(COMPETITIVE_BASELINE))

    assert result["success"] is True
    assert fake_registry.values[(_AMD_DRIVER_KEY, "EnableUlps")] == 0
    assert fake_registry.values[(_AMD_CN_KEY, "AntiLag")] == 1
    assert fake_registry.values[(_AMD_CN_KEY, "EnhancedSync")] == 0
    assert fake_registry.values[(_AMD_CN_KEY, "ChillEnabled")] == 0
    assert fake_registry.values[(_AMD_CN_KEY, "BoostEnabled")] == 0


def test_backup_then_restore_round_trips_prior_state(amd_present, fake_registry) -> None:
    fake_registry.values[(_AMD_DRIVER_KEY, "EnableUlps")] = 1
    fake_registry.values[(_AMD_CN_KEY, "AntiLag")] = 0

    handler = AmdSettingsHandler()
    saved = handler.backup()
    handler.apply(dict(COMPETITIVE_BASELINE))
    assert fake_registry.values[(_AMD_DRIVER_KEY, "EnableUlps")] == 0

    assert handler.restore(saved) is True
    assert fake_registry.values[(_AMD_DRIVER_KEY, "EnableUlps")] == 1
    assert fake_registry.values[(_AMD_CN_KEY, "AntiLag")] == 0


def test_restore_guarantee_is_partial() -> None:
    assert AmdSettingsHandler().restore_guarantee == "partial"


def test_apply_reports_errors_without_raising(amd_present, monkeypatch) -> None:
    def broken_write(hive: int, subkey: str, name: str, value: int) -> None:
        raise PermissionError("registry locked")

    monkeypatch.setattr(amd_module, "_write_reg_dword", broken_write)
    result = AmdSettingsHandler().apply({"disable_ulps": True})

    assert result["success"] is False
    assert "Permission denied" in result["error"]


# --- NVIDIA-intent translation ----------------------------------------------


def test_gaming_preset_derives_competitive_baseline() -> None:
    derived = amd_settings_from_nvidia_intent({"preset": "reflex_game"})
    assert derived == COMPETITIVE_BASELINE


@pytest.mark.parametrize(
    "nvidia_settings",
    [
        {"power_management": "prefer_max_performance"},
        {"low_latency_mode": "on"},
        {"low_latency_mode": "ultra"},
    ],
)
def test_explicit_latency_intent_derives_competitive_baseline(
    nvidia_settings: dict[str, Any],
) -> None:
    assert amd_settings_from_nvidia_intent(nvidia_settings) == COMPETITIVE_BASELINE


def test_productivity_style_intent_derives_nothing() -> None:
    """Stock-pacing lanes (LLM off, adaptive power) must not touch Radeon."""
    derived = amd_settings_from_nvidia_intent(
        {"low_latency_mode": "off", "power_management": "adaptive", "vsync": "adaptive"}
    )
    assert derived == {}


def test_empty_intent_derives_nothing() -> None:
    assert amd_settings_from_nvidia_intent({}) == {}


# --- profile / registry wiring ----------------------------------------------


def test_standard_gaming_profiles_carry_the_amd_handler() -> None:
    from abso.profiles.counter_strike_2 import CounterStrike2Profile

    handler_names = [
        type(handler).__name__ for handler in CounterStrike2Profile().get_handlers()
    ]
    assert "NvidiaSettingsHandler" in handler_names
    assert "AmdSettingsHandler" in handler_names
    # AMD sits directly after NVIDIA so vendor tuning stays adjacent in the chain.
    assert handler_names.index("AmdSettingsHandler") == (
        handler_names.index("NvidiaSettingsHandler") + 1
    )


def test_gaming_profile_derives_amd_settings_from_nvidia_intent() -> None:
    from abso.profiles.counter_strike_2 import CounterStrike2Profile

    assert CounterStrike2Profile().get_settings("AmdSettingsHandler") == (
        COMPETITIVE_BASELINE
    )


def test_handler_registry_includes_amd_in_audit_and_backup() -> None:
    from abso.core.handler_registry import get_audit_handlers, get_backup_handlers

    audit_names = {type(h).__name__ for h in get_audit_handlers()}
    backup_names = {type(h).__name__ for h in get_backup_handlers()}
    assert "AmdSettingsHandler" in audit_names
    assert "AmdSettingsHandler" in backup_names


# --- FreeSync VRR confirmation ----------------------------------------------


def test_vrr_promotion_confirms_freesync_on_amd_machines(amd_present) -> None:
    from abso.core.detector import _promote_vrr_via_amd_driver

    vrr_info = {"vrr_supported": "hardware", "vrr_type": "freesync"}
    _promote_vrr_via_amd_driver(vrr_info)
    assert vrr_info["vrr_supported"] is True
    assert vrr_info["vrr_type"] == "freesync"


def test_vrr_promotion_defaults_type_to_freesync(amd_present) -> None:
    from abso.core.detector import _promote_vrr_via_amd_driver

    vrr_info = {"vrr_supported": "hardware", "vrr_type": None}
    _promote_vrr_via_amd_driver(vrr_info)
    assert vrr_info["vrr_supported"] is True
    assert vrr_info["vrr_type"] == "freesync"


def test_vrr_promotion_requires_amd_gpu(amd_absent) -> None:
    from abso.core.detector import _promote_vrr_via_amd_driver

    vrr_info = {"vrr_supported": "hardware", "vrr_type": "freesync"}
    _promote_vrr_via_amd_driver(vrr_info)
    assert vrr_info["vrr_supported"] == "hardware"


def test_vrr_promotion_only_upgrades_edid_hardware_state(amd_present) -> None:
    from abso.core.detector import _promote_vrr_via_amd_driver

    for state in (True, "likely", "possible", "unknown", None):
        vrr_info = {"vrr_supported": state, "vrr_type": None}
        _promote_vrr_via_amd_driver(vrr_info)
        assert vrr_info["vrr_supported"] == state
        assert vrr_info["vrr_type"] is None
