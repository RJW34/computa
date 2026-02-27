"""Profile application engine.

Integrates validation subsystems:
- ProfileLinter: Static validation before apply
- RollbackGuard: Online netcode protection
- StabilityGate: Conditional aggressive settings
- NetworkScopeManager: Per-game network tuning
- MultiMonitorDetector: Compositor edge cases
- FallbackController: Failure persistence
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abso.core.capabilities import CapabilityEngine, CapabilityReport
from abso.core.config import ConfigManager
from abso.core.exceptions import (
    ProfileNotFoundError,
)
from abso.core.fallback_controller import FallbackController
from abso.core.linter import LintResult, ProfileLinter
from abso.core.multimon_detector import MultiMonitorDetector, MultiMonitorResult
from abso.core.network_scope import NetworkScopeManager, NetworkScopeResult
from abso.core.rollback_guard import RollbackGuard, RollbackGuardResult
from abso.core.stability_gate import StabilityGate, StabilityGateResult
from abso.profiles.base import BaseProfile
from abso.profiles.catalog import get_profile_classes

logger = logging.getLogger(__name__)


@dataclass
class ApplyResult:
    """Result of applying a profile."""

    success: bool
    error: str | None = None
    requires_reboot: bool = False
    reboot_reasons: list[str] = field(default_factory=list)
    in_game_settings: bool = False
    applied_settings: list[str] = field(default_factory=list)
    failed_settings: list[str] = field(default_factory=list)

    # Validation subsystem results
    lint_result: LintResult | None = None
    rollback_guard_result: RollbackGuardResult | None = None
    stability_gate_result: StabilityGateResult | None = None
    network_scope_result: NetworkScopeResult | None = None
    multimon_result: MultiMonitorResult | None = None
    capability_report: CapabilityReport | None = None

    # Validation summary
    lint_warnings: int = 0
    gated_settings_blocked: int = 0
    rollback_overrides_applied: int = 0
    capability_blockers: int = 0
    capability_warnings: int = 0


class ProfileApplier:
    """Applies game optimization profiles to the system."""

    # Registry of available profiles
    PROFILES: dict[str, type[BaseProfile]] = get_profile_classes()

    def __init__(
        self,
        skip_linting: bool = False,
        skip_rollback_guard: bool = False,
        skip_stability_gate: bool = False,
        skip_network_scope: bool = False,
        skip_multimon_detection: bool = False,
        skip_capability_checks: bool = False,
        rollback_guard_mode: str = "block",
        force_aggressive: bool = False,
    ) -> None:
        """Initialize ProfileApplier with validation subsystems.

        WARNING: The skip_* and force_* flags bypass safety checks designed
        to prevent system instability and online gaming issues. Only use
        these flags if you understand the risks:

        - skip_linting: Bypasses static validation. May apply invalid settings.
        - skip_rollback_guard: Allows unsafe settings for online rollback games.
          Can cause rollback failures, desyncs, and bans.
        - skip_stability_gate: Applies aggressive settings without stability checks.
          May cause system instability on some hardware.
        - force_aggressive: Ignores all gating. Combines all risks above.

        The CLI does not expose these flags directly. They are for programmatic
        use only by advanced users who accept full responsibility.

        Args:
            skip_linting: Skip ProfileLinter validation. Risk: invalid settings.
            skip_rollback_guard: Skip RollbackGuard checks. Risk: online issues.
            skip_stability_gate: Skip StabilityGate processing. Risk: instability.
            skip_network_scope: Skip NetworkScopeManager. Risk: network issues.
            skip_multimon_detection: Skip MultiMonitorDetector. Risk: display issues.
            rollback_guard_mode: "block" (safe) or "override" (apply safe alternatives).
            force_aggressive: Force aggressive settings even if gated. HIGH RISK.
        """
        self._profiles: dict[str, BaseProfile] = {}

        # Configuration
        self.skip_linting = skip_linting
        self.skip_rollback_guard = skip_rollback_guard
        self.skip_stability_gate = skip_stability_gate
        self.skip_network_scope = skip_network_scope
        self.skip_multimon_detection = skip_multimon_detection
        self.skip_capability_checks = skip_capability_checks
        self.force_aggressive = force_aggressive

        # Initialize subsystems
        self._fallback_controller = FallbackController()
        self._capability_engine = CapabilityEngine()
        self._linter = ProfileLinter()
        self._rollback_guard = RollbackGuard(mode=rollback_guard_mode)
        self._stability_gate = StabilityGate(
            fallback_controller=self._fallback_controller
        )
        self._network_scope = NetworkScopeManager()
        self._multimon_detector = MultiMonitorDetector()

    def _get_profile(self, profile_name: str) -> BaseProfile:
        """Get or create a profile instance.

        Args:
            profile_name: Name of the profile.

        Returns:
            Profile instance.

        Raises:
            ValueError: If profile not found.
        """
        if profile_name not in self._profiles:
            profile_class = self.PROFILES.get(profile_name)
            if not profile_class:
                available = ", ".join(self.PROFILES.keys())
                raise ProfileNotFoundError(
                    f"Unknown profile: {profile_name}",
                    details=f"Available profiles: {available}"
                )
            self._profiles[profile_name] = profile_class()

        return self._profiles[profile_name]

    def apply_profile(self, profile_name: str) -> ApplyResult:
        """Apply a game optimization profile with full validation.

        Validation pipeline:
        1. ProfileLinter - Static validation (abort on hard errors)
        2. MultiMonitorDetector - Environment detection
        3. RollbackGuard - Online netcode protection
        4. StabilityGate - Gate aggressive settings
        5. NetworkScopeManager - Scope network settings
        6. Apply handlers

        Args:
            profile_name: Name of the profile to apply.

        Returns:
            ApplyResult with status and validation details.
        """
        try:
            profile = self._get_profile(profile_name)
        except ProfileNotFoundError as e:
            return ApplyResult(success=False, error=str(e))

        # Initialize result
        result = ApplyResult(
            success=True,
            in_game_settings=profile.has_in_game_settings(),
        )

        # === PHASE 0: Capability Graph ===
        if not self.skip_capability_checks:
            capability_report = self._capability_engine.evaluate(profile)
            result.capability_report = capability_report
            result.capability_blockers = len(capability_report.blockers)
            result.capability_warnings = len(capability_report.warnings)
            if capability_report.has_blockers and not self.force_aggressive:
                result.success = False
                result.error = capability_report.blockers[0].message
                return result

        # Collect all settings from profile
        settings_map = self._collect_settings(profile)

        # === PHASE 1: Profile Linting ===
        if not self.skip_linting:
            lint_result = self._linter.lint(profile)
            result.lint_result = lint_result
            result.lint_warnings = len(lint_result.warnings)

            if lint_result.has_errors and not self.force_aggressive:
                error_codes = [e.code for e in lint_result.errors]
                logger.error(
                    f"Profile '{profile_name}' failed linting: {error_codes}"
                )
                result.success = False
                result.error = f"Lint failed: {', '.join(error_codes)}"
                return result

        # === PHASE 2: Multi-Monitor Detection ===
        if not self.skip_multimon_detection:
            multimon_result = self._multimon_detector.detect()
            result.multimon_result = multimon_result

            if multimon_result.warnings:
                for warning in multimon_result.warnings:
                    logger.warning(f"MultiMon: {warning.message}")

        # === PHASE 3: RollbackGuard ===
        if not self.skip_rollback_guard:
            rollback_result = self._rollback_guard.check(profile, settings_map)
            result.rollback_guard_result = rollback_result

            if rollback_result.violations:
                if self._rollback_guard.mode == "block" and not self.force_aggressive:
                    violation_codes = [v.code for v in rollback_result.violations]
                    logger.error(
                        f"RollbackGuard blocked profile: {violation_codes}"
                    )
                    result.success = False
                    result.error = f"Rollback violations: {', '.join(violation_codes)}"
                    return result
                else:
                    # Override mode: apply safe settings
                    settings_map = self._rollback_guard.apply_overrides(
                        settings_map, rollback_result
                    )
                    result.rollback_overrides_applied = len(
                        rollback_result.enforced_overrides
                    )

        # === PHASE 4: StabilityGate ===
        if not self.skip_stability_gate and not self.force_aggressive:
            settings_map, gate_result = self._stability_gate.process(
                profile, settings_map, result.lint_result
            )
            result.stability_gate_result = gate_result
            result.gated_settings_blocked = gate_result.blocked_count

        # === PHASE 5: NetworkScopeManager ===
        if not self.skip_network_scope:
            network_result = self._network_scope.apply_scope(profile, settings_map)
            result.network_scope_result = network_result
            settings_map = self._network_scope.get_scoped_settings(
                settings_map, network_result
            )

        # === PHASE 6: Apply Handlers ===
        config_manager = ConfigManager()
        profile_overrides = config_manager.get_profile_overrides(profile_name)

        applied: list[str] = []
        failed: list[str] = []
        skipped: list[str] = []
        requires_reboot = False
        reboot_reasons: list[str] = []

        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__

            # Skip disabled handlers
            if config_manager.is_handler_disabled(handler_name):
                logger.info(f"Skipping disabled handler: {handler_name}")
                skipped.append(handler_name)
                continue

            try:
                # Get processed settings from our settings_map
                if handler_name in settings_map:
                    settings = settings_map[handler_name]
                else:
                    # Not in our map (e.g. empty dict was skipped), get from profile directly
                    settings = profile.get_settings(handler_name) or {}

                # Merge with user overrides from config
                if profile_overrides:
                    settings = self._merge_overrides(
                        settings, handler_name, profile_overrides
                    )

                # Inject game info for per-game Nvidia profiles
                if handler_name == "NvidiaSettingsHandler":
                    settings["executables"] = profile.executable_hints
                    settings["game_name"] = profile.display_name

                handler_result = handler.apply(settings)

                if handler_result.get("success", False):
                    applied.append(handler_name)
                    if handler_result.get("requires_reboot", False) or handler_result.get("requires_restart", False):
                        requires_reboot = True
                        reboot_reasons.append(handler_name)
                else:
                    failed.append(
                        f"{handler_name}: {handler_result.get('error', 'Unknown error')}"
                    )

            except PermissionError as e:
                logger.error(f"Permission denied applying {handler_name}: {e}")
                failed.append(f"{handler_name}: Permission denied - {e}")
            except OSError as e:
                logger.error(f"OS error applying {handler_name}: {e}")
                failed.append(f"{handler_name}: OS error - {e}")
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Configuration error applying {handler_name}: {e}")
                failed.append(f"{handler_name}: Configuration error - {e}")
            except Exception as e:
                logger.error(f"Unexpected error applying {handler_name}: {e}")
                failed.append(f"{handler_name}: Unexpected error - {e}")

        result.applied_settings = applied
        result.failed_settings = failed
        result.requires_reboot = requires_reboot
        result.reboot_reasons = reboot_reasons

        if failed:
            result.success = False
            result.error = "; ".join(failed)
            logger.warning(
                f"Profile '{profile_name}' partially failed ({len(failed)}/{len(applied) + len(failed)} handlers). "
                f"Run 'python -m abso restore latest' to revert."
            )

        if skipped:
            logger.info(f"Skipped handlers (disabled in config): {', '.join(skipped)}")

        # Log summary
        logger.info(
            f"Profile '{profile_name}' applied: "
            f"{len(applied)} succeeded, {len(failed)} failed, "
            f"{result.lint_warnings} lint warnings, "
            f"{result.gated_settings_blocked} gated settings blocked"
        )

        return result

    def _validate_profile_prerequisites(self, profile: BaseProfile) -> str | None:
        """Validate hardware prerequisites before applying any settings.

        Returns:
            Error message string when prerequisites are not met, otherwise None.
        """
        capability_report = self._capability_engine.evaluate(profile)
        if capability_report.has_blockers:
            return capability_report.blockers[0].message
        return None

    def _collect_settings(self, profile: BaseProfile) -> dict[str, dict[str, Any]]:
        """Collect all settings from a profile's handlers.

        Args:
            profile: The profile to collect settings from.

        Returns:
            Dict mapping handler names to their settings.
        """
        settings_map: dict[str, dict[str, Any]] = {}

        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__
            settings = profile.get_settings(handler_name)
            if settings is not None:
                settings_map[handler_name] = settings.copy()

        return settings_map

    def _merge_overrides(
        self,
        settings: dict[str, Any],
        handler_name: str,
        overrides: Any,
    ) -> dict[str, Any]:
        """Merge profile settings with user overrides from config.

        Args:
            settings: Base settings from profile.
            handler_name: Name of the handler class.
            overrides: ProfileOverrides object from config.

        Returns:
            Merged settings dictionary.
        """
        # Map handler names to override attribute names
        handler_to_attr = {
            "NvidiaSettingsHandler": "nvidia",
            "WindowsSettingsHandler": "windows",
            "NetworkSettingsHandler": "network",
            "PowerSettingsHandler": "power",
            "TimerSettingsHandler": "timer",
            "MouseSettingsHandler": "mouse",
            "ColorProfileSettingsHandler": "color",
        }

        attr_name = handler_to_attr.get(handler_name)
        if not attr_name:
            return settings

        # Get handler-specific overrides
        handler_overrides = getattr(overrides, attr_name, {})
        if not handler_overrides:
            return settings

        # Deep merge: overrides take precedence
        merged = settings.copy()
        merged.update(handler_overrides)
        logger.debug(f"Applied overrides for {handler_name}: {handler_overrides}")

        return merged

    def generate_report(self, profile_name: str, output_dir: Path) -> Path:
        """Generate in-game settings report for a profile.

        Args:
            profile_name: Name of the profile.
            output_dir: Directory to save the report.

        Returns:
            Path to the generated report.

        Raises:
            ValueError: If profile not found.
        """
        profile = self._get_profile(profile_name)

        report_path = output_dir / f"{profile_name}_settings.md"
        report_content = profile.generate_in_game_report()

        report_path.write_text(report_content, encoding="utf-8")

        return report_path

    def verify_profile(self, profile_name: str) -> dict[str, Any]:
        """Verify that a profile's reboot-requiring settings are active.

        This checks if settings that normally require a reboot are already
        in effect. Useful for determining if a reboot is actually needed
        after applying a profile.

        Args:
            profile_name: Name of the profile to verify.

        Returns:
            Dict with 'all_active' bool and per-handler verification results.
        """
        profile = self._get_profile(profile_name)

        results: dict[str, Any] = {
            "profile": profile_name,
            "all_active": True,
            "handlers": {},
        }

        # Check handlers that have reboot-requiring settings
        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__

            # Only check handlers that have verify_active method
            if not hasattr(handler, "verify_active"):
                continue

            settings = profile.get_settings(handler_name)
            if not settings:
                continue

            try:
                handler_result = handler.verify_active(settings)
                results["handlers"][handler_name] = handler_result

                if not handler_result.get("all_active", True):
                    results["all_active"] = False

            except Exception as e:
                logger.error(f"Error verifying {handler_name}: {e}")
                results["handlers"][handler_name] = {
                    "error": str(e),
                    "all_active": False,
                }
                results["all_active"] = False

        return results

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all available profiles.

        Returns:
            List of profile info dicts.
        """
        profiles = []

        for name, profile_class in self.PROFILES.items():
            profile = profile_class()
            profiles.append({
                "id": name,
                "display_name": profile.display_name,
                "description": profile.description,
                "optimization_target": profile.optimization_target,
            })

        return profiles
