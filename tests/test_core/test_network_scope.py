"""Tests for profile network scoping."""

from __future__ import annotations

from typing import Any, Literal

from abso.core.network_scope import NetworkScopeManager
from abso.profiles.base import BaseProfile


class _NetworkProfile(BaseProfile):
    def __init__(self, scope: Literal["full", "limited", "none"] = "none") -> None:
        self._scope = scope

    @property
    def profile_id(self) -> str:
        return f"network-{self._scope}"

    @property
    def display_name(self) -> str:
        return "Network Test"

    @property
    def description(self) -> str:
        return "Network scoping test profile"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return ["Game.exe"]

    @property
    def network_scope(self) -> Literal["full", "limited", "none"]:
        return self._scope

    def get_handlers(self):
        return []

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return {}

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return []


def test_network_scope_blocks_gaming_preset_for_default_scope() -> None:
    """The gaming network preset writes global TCP state, so default profiles get OS defaults."""
    manager = NetworkScopeManager()
    settings_map = {
        "NetworkSettingsHandler": {
            "preset": "gaming",
            "disable_nagle": True,
            "tcp_global": {"autotuninglevel": "disabled"},
        }
    }

    result = manager.apply_scope(_NetworkProfile("none"), settings_map)

    assert result.scoped_settings == {
        "preset": "default",
        "disable_nagle": False,
    }
    assert result.changes_made


def test_network_scope_allows_explicit_full_scope() -> None:
    """Explicit full scope preserves network tuning for specialized profiles."""
    manager = NetworkScopeManager()
    settings_map = {
        "NetworkSettingsHandler": {
            "preset": "gaming",
            "disable_nagle": True,
            "tcp_global": {"autotuninglevel": "disabled"},
        }
    }

    result = manager.apply_scope(_NetworkProfile("full"), settings_map)

    assert result.scoped_settings == settings_map["NetworkSettingsHandler"]
    assert result.changes_made == []


def test_get_scoped_settings_does_not_fall_back_when_scope_strips_all_keys() -> None:
    """Consumers must see the stripped map even when scoping leaves it empty."""
    manager = NetworkScopeManager()
    settings_map = {
        "NetworkSettingsHandler": {
            "tcp_global": {"autotuninglevel": "disabled"},
            "tcp_nodelay": True,
            "tcp_ack_frequency": 1,
        }
    }

    result = manager.apply_scope(_NetworkProfile("none"), settings_map)
    scoped_map = manager.get_scoped_settings(settings_map, result)

    assert scoped_map["NetworkSettingsHandler"] == {}
    assert "tcp_global" not in scoped_map["NetworkSettingsHandler"]


def test_get_scoped_settings_passthrough_when_no_network_handler_present() -> None:
    """Profiles that never request network handling should see the map unchanged."""
    manager = NetworkScopeManager()
    settings_map = {"WindowsSettingsHandler": {"game_mode": True}}

    result = manager.apply_scope(_NetworkProfile("none"), settings_map)
    scoped_map = manager.get_scoped_settings(settings_map, result)

    assert scoped_map is settings_map
