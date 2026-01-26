"""NetworkScopeManager - Per-game network tuning.

This module enforces scoped network optimizations rather than global changes,
preventing side effects on non-gaming applications.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from abso.profiles.base import BaseProfile

logger = logging.getLogger(__name__)


@dataclass
class NetworkScope:
    """Network optimization scope for a profile."""

    allow_nagle_disable: bool = False
    allow_tcp_optimizations: bool = False
    scope_reason: str = ""


@dataclass
class NetworkScopeResult:
    """Result of network scope evaluation."""

    profile_id: str
    original_settings: dict[str, Any] = field(default_factory=dict)
    scoped_settings: dict[str, Any] = field(default_factory=dict)
    scope: NetworkScope | None = None
    changes_made: list[str] = field(default_factory=list)


class NetworkScopeManager:
    """Manages per-game network tuning to prevent global side effects.

    Key principle: Global Nagle disable is PROHIBITED.

    Network optimizations are only applied to profiles explicitly tagged:
    - Rollback netcode games
    - Twitch shooters (FPS with tick-rate sensitivity)

    All other profiles retain OS defaults for network settings to prevent
    side effects on streaming, downloads, and general internet usage.
    """

    # Profile types that allow Nagle disable
    NAGLE_ALLOWED_TYPES = {
        "minimum_latency",
        "minimum_latency_offline",
        "low_latency_high_fps",
        "stable_online",
    }

    # Keywords that indicate network-sensitive games
    NETWORK_SENSITIVE_KEYWORDS = {
        "rollback",
        "netcode",
        "online",
        "multiplayer",
        "competitive",
        "shooter",
        "fps",
        "fighting",
    }

    # Profile IDs that are known network-sensitive
    NETWORK_SENSITIVE_PROFILES = {
        "rivals2",
        "rivals2-online",
        "rivals2-offline",
        "rivals2-oled",
        "rivals2-oled-vrr",
        "rivals2-oled-vrr-multimon",
        "cod-bo7",
        "cod-bo7-oled",
        "slippi-melee",
        "slippi-melee-oled",
        "slippi-melee-vrr",
    }

    # Settings that should be scoped (not applied globally)
    SCOPED_SETTINGS = {
        "disable_nagle",
        "tcp_nodelay",
    }

    # Settings that are safe to apply globally
    GLOBAL_SAFE_SETTINGS = {
        "preset",  # Gaming preset is generally safe
    }

    def evaluate_scope(self, profile: BaseProfile) -> NetworkScope:
        """Evaluate what network optimizations are allowed for a profile.

        Args:
            profile: The profile to evaluate.

        Returns:
            NetworkScope with allowed optimizations.
        """
        # Check explicit profile ID
        if profile.profile_id in self.NETWORK_SENSITIVE_PROFILES:
            return NetworkScope(
                allow_nagle_disable=True,
                allow_tcp_optimizations=True,
                scope_reason=f"Profile '{profile.profile_id}' is network-sensitive",
            )

        # Check optimization target
        if profile.optimization_target in self.NAGLE_ALLOWED_TYPES:
            return NetworkScope(
                allow_nagle_disable=True,
                allow_tcp_optimizations=True,
                scope_reason=f"Target '{profile.optimization_target}' allows network tuning",
            )

        # Check profile name/description for keywords
        name_lower = profile.display_name.lower()
        desc_lower = profile.description.lower()

        for keyword in self.NETWORK_SENSITIVE_KEYWORDS:
            if keyword in name_lower or keyword in desc_lower:
                return NetworkScope(
                    allow_nagle_disable=True,
                    allow_tcp_optimizations=True,
                    scope_reason=f"Profile contains network keyword: '{keyword}'",
                )

        # Default: No aggressive network tuning
        return NetworkScope(
            allow_nagle_disable=False,
            allow_tcp_optimizations=False,
            scope_reason="Profile is not network-sensitive, using OS defaults",
        )

    def apply_scope(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
    ) -> NetworkScopeResult:
        """Apply network scoping to settings.

        Args:
            profile: The profile being applied.
            settings_map: All settings from handlers.

        Returns:
            NetworkScopeResult with scoped settings.
        """
        result = NetworkScopeResult(profile_id=profile.profile_id)

        network_settings = settings_map.get("NetworkSettingsHandler", {})
        if not network_settings:
            return result

        result.original_settings = network_settings.copy()
        scope = self.evaluate_scope(profile)
        result.scope = scope

        # Apply scoping
        scoped = network_settings.copy()

        if not scope.allow_nagle_disable:
            # Remove Nagle disable if not allowed
            if scoped.get("disable_nagle", False):
                scoped["disable_nagle"] = False
                result.changes_made.append(
                    "Blocked 'disable_nagle' (profile not network-sensitive)"
                )
                logger.info(
                    f"NetworkScopeManager: Blocked Nagle disable for "
                    f"'{profile.profile_id}' - {scope.scope_reason}"
                )

        if not scope.allow_tcp_optimizations:
            # Remove aggressive TCP settings if not allowed
            tcp_settings = ["tcp_nodelay", "tcp_ack_frequency"]
            for setting in tcp_settings:
                if setting in scoped:
                    del scoped[setting]
                    result.changes_made.append(
                        f"Removed '{setting}' (profile not network-sensitive)"
                    )

        result.scoped_settings = scoped

        # Log summary
        if result.changes_made:
            logger.info(
                f"NetworkScopeManager: Made {len(result.changes_made)} scope change(s) "
                f"for '{profile.profile_id}'"
            )
        else:
            logger.debug(
                f"NetworkScopeManager: No scope changes for '{profile.profile_id}' - "
                f"{scope.scope_reason}"
            )

        return result

    def get_scoped_settings(
        self,
        settings_map: dict[str, dict[str, Any]],
        result: NetworkScopeResult,
    ) -> dict[str, dict[str, Any]]:
        """Get settings map with network settings replaced by scoped version.

        Args:
            settings_map: Original settings map.
            result: NetworkScopeResult from apply_scope.

        Returns:
            Modified settings map.
        """
        if not result.scoped_settings:
            return settings_map

        modified = {k: v.copy() for k, v in settings_map.items()}
        modified["NetworkSettingsHandler"] = result.scoped_settings

        return modified

    def verify_scope(
        self,
        profile: BaseProfile,
    ) -> dict[str, Any]:
        """Verify network settings are properly scoped.

        This can be called post-apply to verify registry state matches
        expected scoped behavior.

        Args:
            profile: The profile that was applied.

        Returns:
            Dict with verification results.
        """
        # Import here to avoid circular dependency
        from abso.settings.network import NetworkSettingsHandler

        handler = NetworkSettingsHandler()
        current = handler.detect()

        scope = self.evaluate_scope(profile)

        result = {
            "profile_id": profile.profile_id,
            "scope": {
                "allow_nagle_disable": scope.allow_nagle_disable,
                "reason": scope.scope_reason,
            },
            "current_state": current,
            "compliant": True,
            "issues": [],
        }

        # If Nagle is disabled but shouldn't be, flag it
        nagle_disabled = current.get("nagle_disabled", False)
        if nagle_disabled and not scope.allow_nagle_disable:
            result["compliant"] = False
            result["issues"].append(
                "Nagle is disabled globally but profile doesn't allow it"
            )

        return result

    @staticmethod
    def get_safe_defaults() -> dict[str, Any]:
        """Get safe default network settings.

        Returns:
            Network settings that are safe for all profiles.
        """
        return {
            "disable_nagle": False,
            "preset": "default",  # Use OS defaults
        }
