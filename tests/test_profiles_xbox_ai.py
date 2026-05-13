"""Per-profile decision tests for Xbox Mode and AI Agents.

These tests pin the Phase 3 decision matrix:

* Latency-critical families (Reflex shooters, emulators, Rivals 2) must
  declare ``xbox_mode = "off"`` and ``ai_agents = "off"``.
* Productivity / casual families keep the default ``"leave"`` so we don't
  surprise users with shell-level changes outside the gaming session.
"""

from __future__ import annotations

import pytest

from abso.core.linter import LintSeverity, ProfileLinter
from abso.profiles import catalog


@pytest.fixture(scope="module")
def all_profiles():
    return list(catalog.get_profile_classes().values())


def _profile_ids(profiles):
    return {cls().profile_id for cls in profiles}


# Reflex / FSE / emulator families that must take Xbox Mode off.
XBOX_MODE_OFF_PREFIXES: tuple[str, ...] = (
    "slippi-melee",
    "ryujinx",
    "rivals2",
    "fortnite",
    "marvel-rivals",
    "overwatch2",
)
# Families that must take AI agents off (latency-sensitive but possibly
# latency-tolerant for shell mode, e.g. Diablo 4).
AI_AGENTS_OFF_PREFIXES: tuple[str, ...] = XBOX_MODE_OFF_PREFIXES + ("diablo4",)
LEAVE_PROFILE_IDS: set[str] = {
    "productivity",
    "pokemon-auto-chess",
    "pacdeluxe",
}


def test_latency_profiles_set_xbox_mode_off(all_profiles):
    for cls in all_profiles:
        profile = cls()
        if not profile.profile_id.startswith(XBOX_MODE_OFF_PREFIXES):
            continue
        assert profile.xbox_mode == "off", (
            f"{profile.profile_id} is FSE/Reflex-critical but xbox_mode={profile.xbox_mode!r}"
        )


def test_latency_profiles_set_ai_agents_off(all_profiles):
    for cls in all_profiles:
        profile = cls()
        if not profile.profile_id.startswith(AI_AGENTS_OFF_PREFIXES):
            continue
        assert profile.ai_agents == "off", (
            f"{profile.profile_id} is latency-critical but ai_agents={profile.ai_agents!r}"
        )


def test_non_latency_profiles_leave_defaults(all_profiles):
    for cls in all_profiles:
        profile = cls()
        if profile.profile_id not in LEAVE_PROFILE_IDS:
            continue
        assert profile.xbox_mode == "leave", profile.profile_id
        assert profile.ai_agents == "leave", profile.profile_id


def test_linter_blocks_xbox_mode_on_for_fullscreen_only_vrr_profile():
    """Synthetic profile combining xbox_mode='on' with strict FSE VRR must fail lint."""
    from typing import Any

    from abso.profiles.base import BaseProfile

    class _BadProfile(BaseProfile):
        @property
        def profile_id(self) -> str:
            return "bad-xbox-fse"

        @property
        def display_name(self) -> str:
            return "Bad Xbox FSE profile"

        @property
        def description(self) -> str:
            return "Synthetic profile for linter coverage"

        @property
        def optimization_target(self) -> str:
            return "low_latency_high_fps"

        @property
        def executable_hints(self) -> list[str]:
            return ["fake.exe"]

        @property
        def xbox_mode(self):
            return "on"

        @property
        def uses_fullscreen_only_vrr_path(self) -> bool:
            return True

        def get_handlers(self):
            return []

        def get_settings(self, handler_name: str) -> dict[str, Any]:
            return {}

        def get_in_game_settings(self) -> list[dict[str, str]]:
            return []

    linter = ProfileLinter()
    result = linter.lint(_BadProfile())
    assert any(
        issue.code == "XBOX_MODE_FSE_CONFLICT" and issue.severity == LintSeverity.ERROR
        for issue in result.errors
    )


def test_linter_passes_xbox_mode_off_for_fullscreen_only_vrr_profile(all_profiles):
    """The existing OW2 G-SYNC profiles already declare xbox_mode='off' and must pass."""
    linter = ProfileLinter()
    for cls in all_profiles:
        profile = cls()
        if not profile.profile_id.startswith("overwatch2-gsync"):
            continue
        result = linter.lint(profile)
        assert not any(
            issue.code == "XBOX_MODE_FSE_CONFLICT" for issue in result.errors
        ), f"{profile.profile_id} should not fail XBOX_MODE_FSE_CONFLICT"
