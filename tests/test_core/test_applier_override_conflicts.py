"""Tests for config profile_override contradiction surfacing in the applier.

A stale abso.yaml profile_override that inverts an explicit profile
declaration (the 2026-06-09 ``graphics.disable_mpo: true`` incident that
half-refresh-locked Overwatch 2) must be loudly reported on every apply
instead of silently winning.
"""

from __future__ import annotations

from abso.core.applier import _collect_override_conflicts
from abso.core.config import ProfileOverrides, merge_profile_override_settings


class TestCollectOverrideConflicts:
    def test_flags_value_replaced_by_override(self):
        profile_settings = {"disable_mpo": False, "disable_global_fso": False}
        overrides = ProfileOverrides(graphics={"disable_mpo": True})
        merged = merge_profile_override_settings(
            profile_settings, "GraphicsSettingsHandler", overrides
        )

        conflicts: list[str] = []
        _collect_override_conflicts(
            "GraphicsSettingsHandler", profile_settings, merged, conflicts
        )

        assert conflicts == [
            "GraphicsSettingsHandler.disable_mpo: config override True "
            "replaces profile value False"
        ]

    def test_ignores_override_keys_the_profile_does_not_declare(self):
        profile_settings = {"disable_mpo": False}
        overrides = ProfileOverrides(graphics={"hardware_cursor": True})
        merged = merge_profile_override_settings(
            profile_settings, "GraphicsSettingsHandler", overrides
        )

        conflicts: list[str] = []
        _collect_override_conflicts(
            "GraphicsSettingsHandler", profile_settings, merged, conflicts
        )

        assert conflicts == []

    def test_ignores_override_that_matches_profile_value(self):
        profile_settings = {"disable_mpo": False}
        overrides = ProfileOverrides(graphics={"disable_mpo": False})
        merged = merge_profile_override_settings(
            profile_settings, "GraphicsSettingsHandler", overrides
        )

        conflicts: list[str] = []
        _collect_override_conflicts(
            "GraphicsSettingsHandler", profile_settings, merged, conflicts
        )

        assert conflicts == []

    def test_descends_into_nested_settings(self):
        profile_settings = {"nested": {"keep": 1, "flip": False}}
        overrides = ProfileOverrides(graphics={"nested": {"flip": True, "added": 9}})
        merged = merge_profile_override_settings(
            profile_settings, "GraphicsSettingsHandler", overrides
        )

        conflicts: list[str] = []
        _collect_override_conflicts(
            "GraphicsSettingsHandler", profile_settings, merged, conflicts
        )

        assert conflicts == [
            "GraphicsSettingsHandler.nested.flip: config override True "
            "replaces profile value False"
        ]
