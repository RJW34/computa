"""Tests for StabilityGate."""

from __future__ import annotations

from unittest.mock import MagicMock

from abso.core.stability_gate import StabilityGate


def _make_profile(**kwargs):
    profile = MagicMock()
    profile.profile_id = kwargs.get("profile_id", "test")
    profile.display_name = kwargs.get("display_name", "Test")
    profile.description = kwargs.get("description", "Test")
    profile.optimization_target = kwargs.get("optimization_target", "minimum_latency")
    profile.executable_hints = kwargs.get("executable_hints", ["test.exe"])
    return profile


class TestStabilityGateAllows:
    """Aggressive settings should be allowed for appropriate targets."""

    def test_llm_ultra_allowed_for_minimum_latency(self):
        gate = StabilityGate()
        profile = _make_profile(optimization_target="minimum_latency")
        settings = {"NvidiaSettingsHandler": {"low_latency_mode": "ultra"}}
        modified, result = gate.process(profile, settings)
        assert modified["NvidiaSettingsHandler"]["low_latency_mode"] == "ultra"
        assert result.allowed_count >= 1

    def test_safe_value_unchanged(self):
        gate = StabilityGate()
        profile = _make_profile(optimization_target="minimum_latency")
        settings = {"NvidiaSettingsHandler": {"low_latency_mode": "on"}}
        modified, result = gate.process(profile, settings)
        assert modified["NvidiaSettingsHandler"]["low_latency_mode"] == "on"
        assert result.gated_count == 0  # "on" is not the aggressive value


class TestStabilityGateBlocks:
    """Aggressive settings should be blocked for non-allowed targets."""

    def test_llm_ultra_blocked_for_balanced(self):
        gate = StabilityGate()
        profile = _make_profile(optimization_target="balanced")
        settings = {"NvidiaSettingsHandler": {"low_latency_mode": "ultra"}}
        modified, result = gate.process(profile, settings)
        assert modified["NvidiaSettingsHandler"]["low_latency_mode"] == "on"
        assert result.blocked_count >= 1

    def test_ultimate_perf_blocked_for_stable_online(self):
        gate = StabilityGate()
        profile = _make_profile(optimization_target="stable_online")
        settings = {"PowerSettingsHandler": {"active_plan": "ultimate_performance"}}
        modified, result = gate.process(profile, settings)
        assert modified["PowerSettingsHandler"]["active_plan"] == "high_performance"

    def test_fixed_quantum_blocked_for_balanced(self):
        gate = StabilityGate()
        profile = _make_profile(optimization_target="balanced")
        settings = {"RegistrySettingsHandler": {"win32_priority_separation": 0x2A}}
        modified, result = gate.process(profile, settings)
        assert modified["RegistrySettingsHandler"]["win32_priority_separation"] == 0x26


class TestStabilityGateWithLintErrors:
    """Lint errors should cause gated settings to be blocked."""

    def test_lint_error_blocks_setting(self):
        gate = StabilityGate()
        profile = _make_profile(optimization_target="minimum_latency")
        settings = {"NvidiaSettingsHandler": {"low_latency_mode": "ultra"}}

        lint_result = MagicMock()
        lint_result.has_errors = True
        error = MagicMock()
        error.setting_path = "NvidiaSettingsHandler.low_latency_mode"
        error.code = "NVIDIA_REFLEX_LLM_CONFLICT"
        lint_result.errors = [error]

        modified, result = gate.process(profile, settings, lint_result=lint_result)
        assert modified["NvidiaSettingsHandler"]["low_latency_mode"] == "on"
        assert result.blocked_count >= 1


class TestStabilityGateHelpers:
    """Test helper methods."""

    def test_is_gated(self):
        gate = StabilityGate()
        assert gate.is_gated("NvidiaSettingsHandler", "low_latency_mode")
        assert not gate.is_gated("NvidiaSettingsHandler", "some_random_setting")

    def test_get_safe_value(self):
        gate = StabilityGate()
        assert gate.get_safe_value("NvidiaSettingsHandler", "low_latency_mode") == "on"
        assert gate.get_safe_value("NvidiaSettingsHandler", "nonexistent") is None
