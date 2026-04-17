"""NetworkScopeManager - profile-scoped network safety.

This module prevents profiles from applying global TCP changes unless they
explicitly declare that those changes are required for the target workload.
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
    """Manages profile network tuning to prevent global side effects.

    Key principle: global Nagle/TCP tuning is opt-in only.

    The network handler's ``preset="gaming"`` writes TCPNoDelay,
    TcpAckFrequency, and several netsh global TCP values. Those are not
    harmless per-game switches, so the scope manager rewrites them to OS
    defaults unless a profile explicitly declares a network scope.
    """

    # Settings that should be scoped (not applied globally)
    SCOPED_SETTINGS = {
        "disable_nagle",
        "tcp_nodelay",
    }

    def evaluate_scope(self, profile: BaseProfile) -> NetworkScope:
        """Evaluate what network optimizations are allowed for a profile.

        Args:
            profile: The profile to evaluate.

        Returns:
            NetworkScope with allowed optimizations.
        """
        # Source of truth: profile metadata.
        # BaseProfile.network_scope returns one of: full, limited, none.
        network_scope = getattr(profile, "network_scope", "none")
        if network_scope == "full":
            return NetworkScope(
                allow_nagle_disable=True,
                allow_tcp_optimizations=True,
                scope_reason=f"Profile '{profile.profile_id}' declares network_scope=full",
            )
        if network_scope == "limited":
            return NetworkScope(
                allow_nagle_disable=False,
                allow_tcp_optimizations=True,
                scope_reason=f"Profile '{profile.profile_id}' declares network_scope=limited",
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

            if scoped.get("preset") == "gaming":
                scoped["preset"] = "default"
                result.changes_made.append(
                    "Replaced NetworkSettingsHandler preset 'gaming' with 'default' "
                    "(gaming preset disables Nagle globally)"
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

            if "tcp_global" in scoped:
                del scoped["tcp_global"]
                result.changes_made.append(
                    "Removed 'tcp_global' settings (profile does not allow TCP global tuning)"
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
        # Distinguish "no scope evaluation" (no NetworkSettingsHandler in map,
        # so apply_scope returned early) from "scope evaluated and stripped
        # every key". In the stripped-to-empty case we must still replace the
        # handler's settings or disallowed writes would survive silently.
        if result.scope is None:
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
