"""StabilityGate - Conditional enablement of aggressive settings.

This module gates aggressive optimizations based on profile type, linter
results, and historical runtime validation outcomes.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from abso.settings.registry import (
    WIN32_PRIORITY_GAMING_OFFLINE,
    WIN32_PRIORITY_GAMING_ONLINE,
)

if TYPE_CHECKING:
    from abso.core.fallback_controller import FallbackController
    from abso.core.linter import LintResult
    from abso.profiles.base import BaseProfile

logger = logging.getLogger(__name__)


class SettingClass(Enum):
    """Classification of setting aggressiveness."""
    SAFE = "safe"              # Always safe to apply
    GATED = "gated"            # Requires passing gate checks
    DANGEROUS = "dangerous"    # Only with explicit user override


@dataclass
class GatedSetting:
    """Definition of a gated setting."""

    handler: str
    setting: str
    aggressive_value: Any
    safe_value: Any
    description: str
    allowed_targets: set[str] = field(default_factory=set)  # Empty = all targets


@dataclass
class GateDecision:
    """Result of a stability gate check for a single setting."""

    setting: GatedSetting
    allowed: bool
    reason: str
    applied_value: Any


@dataclass
class StabilityGateResult:
    """Result of stability gate processing."""

    profile_id: str
    decisions: list[GateDecision] = field(default_factory=list)
    gated_count: int = 0
    allowed_count: int = 0
    blocked_count: int = 0

    def add_decision(self, decision: GateDecision) -> None:
        """Add a gate decision."""
        self.decisions.append(decision)
        self.gated_count += 1
        if decision.allowed:
            self.allowed_count += 1
        else:
            self.blocked_count += 1


class StabilityGate:
    """Gates aggressive settings based on profile and runtime state.

    Gated settings are classified as potentially destabilizing:
    - Low Latency Mode = Ultra
    - HAGS = On
    - Win32PrioritySeparation = 0x2A (fixed quantum)
    - Disable Paging Executive = 1

    These settings are ONLY applied if:
    1. Profile type explicitly allows them
    2. Linter passes with no related errors
    3. FallbackController has no prior failure record

    Otherwise, fallback (safe) values are applied instead.
    """

    # Definition of all gated settings
    GATED_SETTINGS: list[GatedSetting] = [
        GatedSetting(
            handler="NvidiaSettingsHandler",
            setting="low_latency_mode",
            aggressive_value="ultra",
            safe_value="on",
            description="LLM Ultra - aggressive frame queue reduction",
            allowed_targets={"minimum_latency", "minimum_latency_offline"},
        ),
        GatedSetting(
            handler="WindowsSettingsHandler",
            setting="hags",
            aggressive_value=True,
            safe_value=False,
            description="Hardware Accelerated GPU Scheduling",
            allowed_targets=set(),  # Allowed for all, but gated on failures
        ),
        GatedSetting(
            handler="RegistrySettingsHandler",
            setting="win32_priority_separation",
            aggressive_value=WIN32_PRIORITY_GAMING_OFFLINE,
            safe_value=WIN32_PRIORITY_GAMING_ONLINE,
            description="Fixed short quantum with max foreground boost",
            allowed_targets={"minimum_latency", "minimum_latency_offline", "low_latency_high_fps", "stable_online"},
        ),
        GatedSetting(
            handler="MemorySettingsHandler",
            setting="disable_paging_executive",
            aggressive_value=1,
            safe_value=0,
            description="Keep kernel in RAM (requires sufficient memory)",
            allowed_targets=set(),  # Allowed for all, but gated on RAM check
        ),
    ]

    def __init__(
        self,
        fallback_controller: FallbackController | None = None,
    ) -> None:
        """Initialize StabilityGate.

        Args:
            fallback_controller: Optional FallbackController for failure history.
        """
        self.fallback_controller = fallback_controller
        self._settings_index = self._build_settings_index()

    def _build_settings_index(self) -> dict[str, dict[str, GatedSetting]]:
        """Build index of gated settings by handler and setting name."""
        index: dict[str, dict[str, GatedSetting]] = {}
        for gs in self.GATED_SETTINGS:
            if gs.handler not in index:
                index[gs.handler] = {}
            index[gs.handler][gs.setting] = gs
        return index

    def process(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        lint_result: LintResult | None = None,
    ) -> tuple[dict[str, dict[str, Any]], StabilityGateResult]:
        """Process settings through stability gates.

        Args:
            profile: The profile being applied.
            settings_map: Collected settings from all handlers.
            lint_result: Optional lint result for additional gating.

        Returns:
            Tuple of (modified settings map, StabilityGateResult).
        """
        result = StabilityGateResult(profile_id=profile.profile_id)
        modified_settings = {k: v.copy() for k, v in settings_map.items()}

        optimization_target = profile.optimization_target

        for handler_name, settings in settings_map.items():
            if handler_name not in self._settings_index:
                continue

            handler_gates = self._settings_index[handler_name]

            for setting_name, setting_value in settings.items():
                if setting_name not in handler_gates:
                    continue

                gated = handler_gates[setting_name]

                # Check if this is the aggressive value
                if setting_value != gated.aggressive_value:
                    continue

                # Check gate conditions
                decision = self._check_gate(
                    profile=profile,
                    gated=gated,
                    optimization_target=optimization_target,
                    lint_result=lint_result,
                )

                result.add_decision(decision)

                # Apply decision
                if not decision.allowed:
                    modified_settings[handler_name][setting_name] = decision.applied_value
                    logger.warning(
                        f"StabilityGate blocked {handler_name}.{setting_name}="
                        f"{setting_value}, using {decision.applied_value}: {decision.reason}"
                    )
                else:
                    logger.debug(
                        f"StabilityGate allowed {handler_name}.{setting_name}="
                        f"{setting_value}: {decision.reason}"
                    )

        # Log summary
        if result.blocked_count > 0:
            logger.info(
                f"StabilityGate: {result.allowed_count}/{result.gated_count} aggressive "
                f"settings allowed, {result.blocked_count} blocked for '{profile.profile_id}'"
            )

        return modified_settings, result

    def _check_gate(
        self,
        profile: BaseProfile,
        gated: GatedSetting,
        optimization_target: str,
        lint_result: LintResult | None,
    ) -> GateDecision:
        """Check if an aggressive setting should be allowed.

        Args:
            profile: The profile being applied.
            gated: The gated setting definition.
            optimization_target: Profile's optimization target.
            lint_result: Optional lint result.

        Returns:
            GateDecision with allowed status and reason.
        """
        # Check 1: Is target allowed?
        if gated.allowed_targets and optimization_target not in gated.allowed_targets:
            return GateDecision(
                setting=gated,
                allowed=False,
                reason=f"Optimization target '{optimization_target}' not in allowed targets",
                applied_value=gated.safe_value,
            )

        # Check 2: Lint errors for this handler?
        if lint_result and lint_result.has_errors:
            for error in lint_result.errors:
                if error.setting_path and gated.handler in error.setting_path:
                    return GateDecision(
                        setting=gated,
                        allowed=False,
                        reason=f"Linter error: {error.code}",
                        applied_value=gated.safe_value,
                    )

        # Check 3: Prior runtime failures?
        if self.fallback_controller:
            for exe in profile.executable_hints:
                failure = self.fallback_controller.get_failure(
                    exe, f"{gated.handler}.{gated.setting}"
                )
                if failure:
                    return GateDecision(
                        setting=gated,
                        allowed=False,
                        reason=f"Prior runtime failure for {exe}: {failure.reason}",
                        applied_value=gated.safe_value,
                    )

        # All checks passed
        return GateDecision(
            setting=gated,
            allowed=True,
            reason="All gate checks passed",
            applied_value=gated.aggressive_value,
        )

    def is_gated(self, handler: str, setting: str) -> bool:
        """Check if a setting is gated.

        Args:
            handler: Handler class name.
            setting: Setting name.

        Returns:
            True if the setting is gated.
        """
        return (
            handler in self._settings_index and
            setting in self._settings_index[handler]
        )

    def get_safe_value(self, handler: str, setting: str) -> Any:
        """Get the safe fallback value for a gated setting.

        Args:
            handler: Handler class name.
            setting: Setting name.

        Returns:
            The safe value, or None if not gated.
        """
        if not self.is_gated(handler, setting):
            return None
        return self._settings_index[handler][setting].safe_value
