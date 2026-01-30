"""Tests for RollbackGuard."""

from __future__ import annotations

from unittest.mock import MagicMock

from abso.core.rollback_guard import RollbackGuard


def _make_profile(**kwargs):
    profile = MagicMock()
    profile.profile_id = kwargs.get("profile_id", "test")
    profile.display_name = kwargs.get("display_name", "Test")
    profile.description = kwargs.get("description", "Test")
    profile.optimization_target = kwargs.get("optimization_target", "minimum_latency")
    profile.executable_hints = kwargs.get("executable_hints", ["test.exe"])
    profile.is_online_profile = kwargs.get("is_online_profile", False)
    return profile


class TestRollbackGuardSkipsOffline:
    """Offline profiles should pass without violations."""

    def test_offline_profile_passes(self):
        guard = RollbackGuard(mode="block")
        profile = _make_profile(is_online_profile=False)
        result = guard.check(profile, {
            "NvidiaSettingsHandler": {"low_latency_mode": "ultra"},
        })
        assert result.passed
        assert len(result.violations) == 0
        assert not result.is_rollback_profile


class TestRollbackGuardBlocks:
    """Online profiles should be blocked for prohibited settings."""

    def test_llm_ultra_blocked(self):
        guard = RollbackGuard(mode="block")
        profile = _make_profile(
            profile_id="rivals2-online",
            display_name="Rivals 2: Online",
            optimization_target="stable_online",
            is_online_profile=True,
        )
        result = guard.check(profile, {
            "NvidiaSettingsHandler": {"low_latency_mode": "ultra"},
        })
        assert not result.passed
        assert any("LOW_LATENCY_MODE" in v.code for v in result.violations)

    def test_fast_sync_blocked(self):
        guard = RollbackGuard(mode="block")
        profile = _make_profile(
            display_name="Online",
            optimization_target="stable_online",
            is_online_profile=True,
        )
        result = guard.check(profile, {
            "NvidiaSettingsHandler": {"vsync": "fast"},
        })
        assert not result.passed
        assert any("VSYNC" in v.code for v in result.violations)


class TestRollbackGuardOverride:
    """Override mode should fix violations automatically."""

    def test_override_downgrades_llm(self):
        guard = RollbackGuard(mode="override")
        profile = _make_profile(
            profile_id="rivals2-online",
            display_name="Rivals 2: Online",
            optimization_target="stable_online",
            is_online_profile=True,
        )
        settings = {"NvidiaSettingsHandler": {"low_latency_mode": "ultra"}}
        result = guard.check(profile, settings)
        assert result.passed  # override mode allows continuation
        assert "NvidiaSettingsHandler" in result.enforced_overrides
        assert result.enforced_overrides["NvidiaSettingsHandler"]["low_latency_mode"] == "on"

    def test_apply_overrides(self):
        guard = RollbackGuard(mode="override")
        profile = _make_profile(
            display_name="Online",
            optimization_target="stable_online",
            is_online_profile=True,
        )
        settings = {"NvidiaSettingsHandler": {"low_latency_mode": "ultra", "vsync": "off"}}
        result = guard.check(profile, settings)
        modified = guard.apply_overrides(settings, result)
        assert modified["NvidiaSettingsHandler"]["low_latency_mode"] == "on"
        assert modified["NvidiaSettingsHandler"]["vsync"] == "off"  # not prohibited
