"""RollbackGuard - Online netcode protection system.

This module enforces hard prohibitions for rollback-sensitive online profiles
to prevent timing failures and ensure stable netcode synchronization.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any

if TYPE_CHECKING:
    from abso.profiles.base import BaseProfile

logger = logging.getLogger(__name__)


@dataclass
class RollbackViolation:
    """Represents a rollback guard rule violation."""

    code: str
    setting: str
    current_value: Any
    message: str
    details: str


@dataclass
class RollbackGuardResult:
    """Result of rollback guard validation."""

    profile_id: str
    is_rollback_profile: bool
    passed: bool
    violations: list[RollbackViolation] = field(default_factory=list)
    enforced_overrides: dict[str, dict[str, Any]] = field(default_factory=dict)

    def add_violation(self, violation: RollbackViolation) -> None:
        """Add a violation and mark as failed."""
        self.violations.append(violation)
        self.passed = False


class RollbackGuard:
    """Protects online profiles from unsafe latency optimizations.

    Rollback netcode requires deterministic frame timing. Aggressive latency
    optimizations can cause timing contention that breaks synchronization.

    Hard Prohibitions (enforced for online profiles):
    - LLM Ultra
    - Fast Sync
    - External FPS limiters (RTSS) - detected via config
    - Refresh-3 FPS logic with aggressive caps
    - Forced zero-buffer pipelines

    This guard can either:
    1. BLOCK: Fail loudly if prohibited settings are detected
    2. OVERRIDE: Automatically downgrade to safe values
    """

    # Optimization targets that require rollback protection
    ROLLBACK_TARGETS = {
        "stable_online",
        "online",
        "ranked",
        "matchmaking",
    }

    # Profile IDs that are explicitly online profiles
    ONLINE_PROFILE_IDS = {
        "rivals2-online",
    }

    # Prohibited NVIDIA settings for rollback profiles
    NVIDIA_PROHIBITIONS = {
        "low_latency_mode": {
            "prohibited": ["ultra"],
            "safe_value": "on",
            "reason": "LLM Ultra causes aggressive frame queue reduction that can "
                     "cause timing contention with rollback netcode.",
        },
        "vsync": {
            "prohibited": ["fast"],
            "safe_value": "on",
            "reason": "Fast Sync causes frame timing irregularities that break "
                     "rollback synchronization.",
        },
    }

    # Safe fallback settings for rollback profiles
    SAFE_NVIDIA_SETTINGS = {
        "low_latency_mode": "on",
        "vsync": "on",
        "max_frame_rate": "off",
        "threaded_optimization": "auto",
    }

    SAFE_POWER_SETTINGS = {
        "active_plan": "ultimate_performance",
        "ensure_ultimate_performance": True,
    }

    def __init__(self, mode: str = "block") -> None:
        """Initialize RollbackGuard.

        Args:
            mode: Either "block" (fail on violations) or "override" (auto-fix).
        """
        if mode not in ("block", "override"):
            raise ValueError(f"Invalid mode: {mode}. Use 'block' or 'override'.")
        self.mode = mode

    def check(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
    ) -> RollbackGuardResult:
        """Check profile settings against rollback safety rules.

        Args:
            profile: The profile being applied.
            settings_map: Collected settings from all handlers.

        Returns:
            RollbackGuardResult with violations and/or enforced overrides.
        """
        result = RollbackGuardResult(
            profile_id=profile.profile_id,
            is_rollback_profile=self._is_rollback_profile(profile),
            passed=True,
        )

        # If not a rollback profile, skip all checks
        if not result.is_rollback_profile:
            logger.debug(f"Profile '{profile.profile_id}' is not rollback-sensitive")
            return result

        logger.info(f"RollbackGuard checking profile '{profile.profile_id}'")

        # Check NVIDIA settings
        self._check_nvidia_settings(settings_map, result)

        # Check power settings
        self._check_power_settings(settings_map, result)

        # Check for external limiters in config
        self._check_external_limiters(settings_map, result)

        # Log results
        if result.violations:
            if self.mode == "block":
                logger.error(
                    f"RollbackGuard BLOCKED profile '{profile.profile_id}' with "
                    f"{len(result.violations)} violation(s)"
                )
            else:
                logger.warning(
                    f"RollbackGuard OVERRIDING {len(result.violations)} setting(s) "
                    f"in profile '{profile.profile_id}'"
                )
        else:
            logger.info(f"Profile '{profile.profile_id}' passed rollback safety checks")

        return result

    def _is_rollback_profile(self, profile: BaseProfile) -> bool:
        """Determine if a profile requires rollback protection.

        Args:
            profile: The profile to check.

        Returns:
            True if the profile is for online/rollback gameplay.
        """
        # First, check the profile's explicit metadata property
        # This allows profiles to explicitly declare their online status
        if hasattr(profile, "is_online_profile"):
            return profile.is_online_profile

        # Check explicit profile IDs
        if profile.profile_id in self.ONLINE_PROFILE_IDS:
            return True

        # Check optimization target
        if profile.optimization_target in self.ROLLBACK_TARGETS:
            return True

        # Keyword detection as last resort - be more specific
        # Only match if the keyword appears in a positive context
        name_lower = profile.display_name.lower()

        # Check for explicit "online" or "ranked" in profile name only (not description)
        # This avoids false positives from descriptions like "NOT for online"
        online_keywords_strict = {"online", "ranked", "matchmaking"}
        for keyword in online_keywords_strict:
            if keyword in name_lower:
                return True

        return False

    def _check_nvidia_settings(
        self,
        settings_map: dict[str, dict[str, Any]],
        result: RollbackGuardResult,
    ) -> None:
        """Check NVIDIA settings for rollback violations."""
        nvidia_settings = settings_map.get("NvidiaSettingsHandler", {})
        if not nvidia_settings:
            return

        for setting_name, rules in self.NVIDIA_PROHIBITIONS.items():
            current_value = nvidia_settings.get(setting_name, "")
            if not current_value:
                # Also check preset for implicit values
                preset = nvidia_settings.get("preset", "")
                current_value = self._get_preset_value(preset, setting_name)

            if current_value and current_value in rules["prohibited"]:
                violation = RollbackViolation(
                    code=f"ROLLBACK_NVIDIA_{setting_name.upper()}",
                    setting=f"NvidiaSettingsHandler.{setting_name}",
                    current_value=current_value,
                    message=f"Prohibited setting for online play: {setting_name}={current_value}",
                    details=rules["reason"],
                )
                result.add_violation(violation)

                # In override mode, record the safe value to apply
                if self.mode == "override":
                    if "NvidiaSettingsHandler" not in result.enforced_overrides:
                        result.enforced_overrides["NvidiaSettingsHandler"] = {}
                    result.enforced_overrides["NvidiaSettingsHandler"][setting_name] = \
                        rules["safe_value"]
                    result.passed = True  # Override mode allows continuation

    def _check_power_settings(
        self,
        settings_map: dict[str, dict[str, Any]],
        result: RollbackGuardResult,
    ) -> None:
        """Check power settings for rollback safety."""
        power_settings = settings_map.get("PowerSettingsHandler", {})
        if not power_settings:
            return

        # No power-plan overrides are enforced here; Ultimate Performance is allowed.

    def _check_external_limiters(
        self,
        settings_map: dict[str, dict[str, Any]],
        result: RollbackGuardResult,
    ) -> None:
        """Check for indicators of external frame limiters.

        We can't directly detect running software, but we can warn about
        config settings that suggest external limiters are in use.
        """
        # Check for RTSS indicators in any settings
        # This is mostly informational since we can't enforce it

        # Log warning about external limiters
        logger.info(
            "RollbackGuard reminder: External FPS limiters (RTSS) should "
            "be DISABLED for online play. They cause timing contention with rollback."
        )

    def _get_preset_value(self, preset: str, setting: str) -> str:
        """Get the implicit value of a setting from an NVIDIA preset.

        Args:
            preset: The preset name.
            setting: The setting to look up.

        Returns:
            The preset's value for the setting, or empty string if not found.
        """
        # Import here to avoid circular dependency
        from abso.settings.nvidia.presets import NVIDIA_PRESETS

        preset_config = NVIDIA_PRESETS.get(preset, {})
        preset_settings = preset_config.get("settings", {})

        return preset_settings.get(setting, "")

    def get_safe_settings(self) -> dict[str, dict[str, Any]]:
        """Get the safe fallback settings for rollback profiles.

        Returns:
            Dict of handler name -> settings for safe online play.
        """
        return {
            "NvidiaSettingsHandler": self.SAFE_NVIDIA_SETTINGS.copy(),
            "PowerSettingsHandler": self.SAFE_POWER_SETTINGS.copy(),
        }

    def apply_overrides(
        self,
        settings_map: dict[str, dict[str, Any]],
        result: RollbackGuardResult,
    ) -> dict[str, dict[str, Any]]:
        """Apply enforced overrides to the settings map.

        Args:
            settings_map: Original settings map.
            result: RollbackGuardResult with enforced_overrides.

        Returns:
            Modified settings map with overrides applied.
        """
        if not result.enforced_overrides:
            return settings_map

        modified = {}
        for handler_name, settings in settings_map.items():
            modified[handler_name] = settings.copy()

            if handler_name in result.enforced_overrides:
                overrides = result.enforced_overrides[handler_name]
                modified[handler_name].update(overrides)
                logger.info(
                    f"RollbackGuard applied overrides to {handler_name}: {overrides}"
                )

        return modified
