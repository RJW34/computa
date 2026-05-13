"""Tests for the detect-only Xbox Mode and AI Agents handlers."""

from __future__ import annotations

from unittest.mock import patch

from abso.settings import ai_agents as ai_mod
from abso.settings import xbox_mode as xm_mod
from abso.settings.ai_agents import AIAgentsSettingsHandler
from abso.settings.xbox_mode import XboxModeSettingsHandler
from abso.utils.os_release import OsRelease


def _release(build: int, ubr: int) -> OsRelease:
    return OsRelease(
        product_name="Windows 10 Home",
        display_version="25H2",
        edition_id="Core",
        installation_type="Client",
        build=build,
        ubr=ubr,
    )


class TestXboxMode:
    def test_old_build_returns_unsupported(self):
        handler = XboxModeSettingsHandler()
        with patch.object(xm_mod, "detect_os_release", return_value=_release(26100, 1000)):
            state = handler.detect()
            audit_issues = handler.audit()
        assert state["build_supported"] is False
        assert state["xbox_mode_enabled"] is None
        assert audit_issues == []

    def test_new_build_no_feature_flag(self):
        handler = XboxModeSettingsHandler()
        with (
            patch.object(xm_mod, "detect_os_release", return_value=_release(26200, 8457)),
            patch.object(xm_mod, "value_exists", return_value=False),
        ):
            state = handler.detect()
            issues = handler.audit()
        assert state["build_supported"] is True
        assert state["feature_present"] is False
        assert len(issues) == 1
        assert issues[0].category == "xbox_mode"
        assert issues[0].severity == "info"

    def test_feature_present_enabled_surfaces_info(self):
        handler = XboxModeSettingsHandler()

        def fake_value_exists(hive, subkey, name):
            return name == "XboxModeEnabled"

        with (
            patch.object(xm_mod, "detect_os_release", return_value=_release(26200, 8457)),
            patch.object(xm_mod, "value_exists", side_effect=fake_value_exists),
            patch.object(xm_mod, "read_registry_dword", return_value=1),
        ):
            state = handler.detect()
            issues = handler.audit()
        assert state["feature_present"] is True
        assert state["xbox_mode_enabled"] is True
        assert any("Xbox Mode is enabled" in i.title for i in issues)

    def test_apply_is_not_implemented(self):
        handler = XboxModeSettingsHandler()
        result = handler.apply({"xbox_mode_enabled": False})
        assert result["success"] is False
        assert "not yet implemented" in result["error"].lower()

    def test_restore_is_noop(self):
        handler = XboxModeSettingsHandler()
        assert handler.restore({"any": "state"}) is True
        assert handler.restore_guarantee == "none"


class TestAIAgents:
    def test_old_build_returns_unsupported(self):
        handler = AIAgentsSettingsHandler()
        with patch.object(ai_mod, "detect_os_release", return_value=_release(26100, 1000)):
            state = handler.detect()
            issues = handler.audit()
        assert state["build_supported"] is False
        assert issues == []

    def test_new_build_no_feature_flag_only_emits_copilot_info(self):
        handler = AIAgentsSettingsHandler()
        with (
            patch.object(ai_mod, "detect_os_release", return_value=_release(26200, 8457)),
            patch.object(ai_mod, "value_exists", return_value=False),
        ):
            issues = handler.audit()
        # No agent surface and no Copilot policy info means a single rollout-pending issue.
        assert len(issues) == 1
        assert "rollout not yet active" in issues[0].title.lower()

    def test_disable_semantic_inverts(self):
        """A 'DisableAIAgents' DWORD of 1 must report agents OFF (state=False)."""
        handler = AIAgentsSettingsHandler()

        def fake_value_exists(hive, subkey, name):
            return name == "DisableAIAgents"

        with (
            patch.object(ai_mod, "detect_os_release", return_value=_release(26200, 8457)),
            patch.object(ai_mod, "value_exists", side_effect=fake_value_exists),
            patch.object(ai_mod, "read_registry_dword", return_value=1),
        ):
            state = handler.detect()
        assert state["ai_agents_state"] is False
        assert "DisableAIAgents" in state["source"]

    def test_apply_is_not_implemented(self):
        handler = AIAgentsSettingsHandler()
        result = handler.apply({"ai_agents_state": False})
        assert result["success"] is False
