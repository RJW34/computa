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
import subprocess
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abso.core.capabilities import CapabilityEngine, CapabilityReport
from abso.core.config import ConfigManager, merge_profile_override_settings
from abso.core.exceptions import (
    ProfileNotFoundError,
)
from abso.core.fallback_controller import FallbackController
from abso.core.linter import LintResult, ProfileLinter
from abso.core.multimon_detector import MultiMonitorDetector, MultiMonitorResult
from abso.core.network_scope import NetworkScopeManager, NetworkScopeResult
from abso.core.overlay_manager import OverlayManager
from abso.core.process_list import parse_tasklist_csv_images
from abso.core.rollback_guard import RollbackGuard, RollbackGuardResult
from abso.core.stability_gate import StabilityGate, StabilityGateResult
from abso.profiles.base import BaseProfile
from abso.profiles.catalog import get_profile_classes, resolve_profile_id
from abso.profiles.profile_bases import inject_nvidia_profile_identity

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
    changed_settings: list[str] = field(default_factory=list)
    failed_settings: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)

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


@dataclass
class ProfilePreparationResult:
    """Pre-apply environment preparation and capability evaluation."""

    success: bool
    error: str | None = None
    fallback_profile_id: str | None = None
    fallback_reason: str | None = None
    multimon_result: MultiMonitorResult | None = None
    capability_report: CapabilityReport | None = None
    warnings: list[str] = field(default_factory=list)
    notices: list[str] = field(default_factory=list)


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
        self._stability_gate = StabilityGate(fallback_controller=self._fallback_controller)
        self._network_scope = NetworkScopeManager()
        self._multimon_detector = MultiMonitorDetector()
        self._overlay_manager = OverlayManager()
        self._prepared_profiles: dict[str, ProfilePreparationResult] = {}

    @staticmethod
    def _canonical_profile_name(profile_name: str) -> str:
        return resolve_profile_id(profile_name) or profile_name

    def _get_profile(self, profile_name: str) -> BaseProfile:
        """Get or create a profile instance.

        Args:
            profile_name: Name of the profile.

        Returns:
            Profile instance.

        Raises:
            ValueError: If profile not found.
        """
        canonical_profile_name = self._canonical_profile_name(profile_name)

        if canonical_profile_name not in self._profiles:
            profile_class = self.PROFILES.get(canonical_profile_name)
            if not profile_class:
                available = ", ".join(self.PROFILES.keys())
                raise ProfileNotFoundError(
                    f"Unknown profile: {profile_name}", details=f"Available profiles: {available}"
                )
            self._profiles[canonical_profile_name] = profile_class()

        return self._profiles[canonical_profile_name]

    def apply_profile(self, profile_name: str) -> ApplyResult:
        """Apply a game optimization profile with full validation.

        Validation pipeline:
        1. MultiMonitorDetector - Environment detection
        2. CapabilityEngine - Hardware/display prerequisites
        3. ProfileLinter - Static validation (abort on hard errors)
        4. RollbackGuard - Online netcode protection
        5. StabilityGate - Gate aggressive settings
        6. NetworkScopeManager - Scope network settings
        7. Apply handlers

        Args:
            profile_name: Name of the profile to apply.

        Returns:
            ApplyResult with status and validation details.
        """
        profile_name = self._canonical_profile_name(profile_name)
        try:
            profile = self._get_profile(profile_name)
        except ProfileNotFoundError as e:
            return ApplyResult(success=False, error=str(e))

        # Initialize result
        result = ApplyResult(
            success=True,
            in_game_settings=profile.has_in_game_settings(),
        )

        # === PHASE 0/1: Display prep + capability graph ===
        preparation = self._prepared_profiles.get(profile_name, None)
        if preparation is None:
            preparation = self._prepare_profile_environment(profile_name, profile)

        result.multimon_result = preparation.multimon_result
        result.capability_report = preparation.capability_report
        for warning in preparation.warnings:
            self._append_unique(result.warnings, warning)
        for notice in preparation.notices:
            self._append_unique(result.notices, notice)

        if preparation.capability_report:
            result.capability_blockers = len(preparation.capability_report.blockers)
            result.capability_warnings = len(preparation.capability_report.warnings)

        if not preparation.success and not self.force_aggressive:
            result.success = False
            result.error = preparation.error
            return result

        # Collect all settings from profile
        settings_map = self._collect_settings(profile)

        # === PHASE 2: Profile Linting ===
        if not self.skip_linting:
            lint_result = self._linter.lint(profile)
            result.lint_result = lint_result
            result.lint_warnings = len(lint_result.warnings)

            if lint_result.has_errors and not self.force_aggressive:
                error_codes = [e.code for e in lint_result.errors]
                logger.error(f"Profile '{profile_name}' failed linting: {error_codes}")
                result.success = False
                result.error = f"Lint failed: {', '.join(error_codes)}"
                return result

        # === PHASE 3: RollbackGuard ===
        if not self.skip_rollback_guard:
            rollback_result = self._rollback_guard.check(profile, settings_map)
            result.rollback_guard_result = rollback_result

            if rollback_result.violations:
                if self._rollback_guard.mode == "block" and not self.force_aggressive:
                    violation_codes = [v.code for v in rollback_result.violations]
                    logger.error(f"RollbackGuard blocked profile: {violation_codes}")
                    result.success = False
                    result.error = f"Rollback violations: {', '.join(violation_codes)}"
                    return result
                else:
                    # Override mode: apply safe settings
                    settings_map = self._rollback_guard.apply_overrides(
                        settings_map, rollback_result
                    )
                    result.rollback_overrides_applied = len(rollback_result.enforced_overrides)

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
            settings_map = self._network_scope.get_scoped_settings(settings_map, network_result)

        # === PHASE 6: Build final settings / preflight ===
        config_manager = ConfigManager()
        profile_overrides = config_manager.get_profile_overrides(profile_name)
        final_settings_map = self._finalize_handler_settings(
            profile,
            profile_name,
            settings_map,
            profile_overrides,
        )

        preflight_failures = self._run_handler_preflight(
            profile_name,
            profile,
            final_settings_map,
        )
        if preflight_failures and not self.force_aggressive:
            result.success = False
            result.error = preflight_failures[0]
            result.failed_settings = [f"Preflight: {issue}" for issue in preflight_failures]
            return result

        contract_violations = self._validate_profile_contract(
            profile_name,
            profile,
            final_settings_map,
        )
        if contract_violations and not self.force_aggressive:
            result.success = False
            result.error = "Profile contract violations: " + "; ".join(contract_violations)
            result.failed_settings = [f"ProfileContract: {issue}" for issue in contract_violations]
            return result

        # === PHASE 7: Apply Handlers ===
        applied: list[str] = []
        changed: list[str] = []
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
                settings = final_settings_map.get(handler_name, {}).copy()

                handler_result = handler.apply(settings)

                if handler_result.get("success", False):
                    applied.append(handler_name)
                    changed.extend(self._handler_changed_settings(handler_name, handler_result))
                    if handler_result.get("requires_reboot", False) or handler_result.get(
                        "requires_restart", False
                    ):
                        requires_reboot = True
                        reboot_reasons.append(handler_name)
                else:
                    failed.append(f"{handler_name}: {handler_result.get('error', 'Unknown error')}")

                for warning in handler_result.get("warnings", []) or []:
                    self._append_unique(result.warnings, str(warning))
                for notice in handler_result.get("notices", []) or []:
                    self._append_unique(result.notices, str(notice))

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
        result.changed_settings = changed
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

        # === Post-apply: Game-running detection ===
        game_warnings = self._check_game_running(profile.executable_hints)
        if game_warnings:
            for warning in game_warnings:
                self._append_unique(result.warnings, warning)

        # Log summary
        logger.info(
            f"Profile '{profile_name}' applied: "
            f"{len(applied)} succeeded, {len(failed)} failed, "
            f"{result.lint_warnings} lint warnings, "
            f"{result.gated_settings_blocked} gated settings blocked"
        )

        return result

    def _prepare_profile_environment(
        self,
        profile_name: str,
        profile: BaseProfile,
    ) -> ProfilePreparationResult:
        """Prepare display environment and evaluate capability blockers."""
        warnings: list[str] = []
        notices: list[str] = []
        multimon_result = None

        if not self.skip_multimon_detection:
            multimon_result = self._multimon_detector.detect()
            multimon_result, remediation = self._remediate_blocking_overlays(
                profile,
                multimon_result,
            )
            for warning in remediation.warnings:
                self._append_unique(warnings, warning)
            for notice in remediation.notices:
                self._append_unique(notices, notice)

            if multimon_result and multimon_result.warnings:
                for warning in multimon_result.warnings:
                    logger.warning("MultiMon: %s", warning.message)
                    self._append_unique(warnings, warning.message)

        capability_report = None
        if not self.skip_capability_checks:
            capability_report = self._capability_engine.evaluate(
                profile,
                multimon_result=multimon_result,
            )
            if capability_report.has_blockers:
                fallback_profile_id = self._select_capability_fallback(
                    profile_name,
                    capability_report,
                )
                return ProfilePreparationResult(
                    success=False,
                    error=capability_report.blockers[0].message,
                    fallback_profile_id=fallback_profile_id,
                    fallback_reason=capability_report.blockers[0].message,
                    multimon_result=multimon_result,
                    capability_report=capability_report,
                    warnings=warnings,
                    notices=notices,
                )

        return ProfilePreparationResult(
            success=True,
            multimon_result=multimon_result,
            capability_report=capability_report,
            warnings=warnings,
            notices=notices,
        )

    def _select_capability_fallback(
        self,
        profile_name: str,
        capability_report: CapabilityReport,
    ) -> str | None:
        """Return a canonical fallback profile when every blocker agrees.

        Falling back is only safe when the capability engine emits structured
        profile metadata. ABSO never guesses a fallback from names here.
        """
        canonical_profile_name = resolve_profile_id(profile_name) or profile_name
        candidates: list[str] = []
        for finding in capability_report.blockers:
            raw = getattr(finding, "fallback_profile_id", None)
            if not isinstance(raw, str) or not raw.strip():
                return None
            canonical = resolve_profile_id(raw.strip()) or raw.strip()
            if canonical == canonical_profile_name or canonical not in self.PROFILES:
                return None
            candidates.append(canonical)

        if not candidates:
            return None

        first = candidates[0]
        if any(candidate != first for candidate in candidates):
            return None
        return first

    def get_prepared_transition_fallback(self, profile_name: str) -> str | None:
        """Return a safe fallback discovered during prerequisite validation."""
        canonical_profile_name = resolve_profile_id(profile_name) or profile_name
        preparation = self._prepared_profiles.get(canonical_profile_name)
        if preparation is None:
            return None
        return preparation.fallback_profile_id

    def get_prepared_failure_result(
        self,
        profile_name: str,
        error: str,
    ) -> ApplyResult:
        """Build an ApplyResult for failures that happen before apply begins."""
        canonical_profile_name = resolve_profile_id(profile_name) or profile_name
        preparation = self._prepared_profiles.get(canonical_profile_name)
        result = ApplyResult(success=False, error=error)
        if preparation is None:
            return result

        result.multimon_result = preparation.multimon_result
        result.capability_report = preparation.capability_report
        result.warnings = list(preparation.warnings)
        result.notices = list(preparation.notices)
        if preparation.capability_report:
            result.capability_blockers = len(preparation.capability_report.blockers)
            result.capability_warnings = len(preparation.capability_report.warnings)
        return result

    def _remediate_blocking_overlays(
        self,
        profile: BaseProfile,
        multimon_result: MultiMonitorResult | None,
    ) -> tuple[MultiMonitorResult | None, Any]:
        """Disable strict-profile overlay blockers and re-detect the display path."""
        from abso.core.overlay_manager import OverlayRemediationResult

        empty = OverlayRemediationResult()
        if multimon_result is None:
            return multimon_result, empty

        requirements = getattr(profile, "display_path_requirements", None)
        require_overlay_free_path = getattr(requirements, "require_overlay_free_path", False)
        auto_disable = getattr(profile, "auto_disable_blocking_overlays", False)
        overlays = list(multimon_result.environment.detected_overlays)

        if (
            not isinstance(require_overlay_free_path, bool)
            or not require_overlay_free_path
            or not isinstance(auto_disable, bool)
            or not auto_disable
            or not overlays
        ):
            return multimon_result, empty

        remediation = self._overlay_manager.remediate(overlays)
        if remediation.attempted_labels:
            multimon_result = self._multimon_detector.detect()

        return multimon_result, remediation

    def validate_profile_prerequisites(self, profile_name: str) -> str | None:
        """Validate a named profile before any transactional side effects begin."""
        profile_name = self._canonical_profile_name(profile_name)
        profile = self._get_profile(profile_name)
        preparation = self._prepare_profile_environment(profile_name, profile)
        self._prepared_profiles[profile_name] = preparation

        if not preparation.success:
            return preparation.error

        config_manager = ConfigManager()
        settings_map = self._collect_settings(profile)
        final_settings = self._finalize_handler_settings(
            profile,
            profile_name,
            settings_map,
            config_manager.get_profile_overrides(profile_name),
        )
        preflight_failures = self._run_handler_preflight(
            profile_name,
            profile,
            final_settings,
        )
        if preflight_failures:
            return preflight_failures[0]
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

    def _finalize_handler_settings(
        self,
        profile: BaseProfile,
        profile_name: str,
        settings_map: dict[str, dict[str, Any]],
        profile_overrides: Any | None,
    ) -> dict[str, dict[str, Any]]:
        """Build the final per-handler settings map before apply/verify."""
        final_settings: dict[str, dict[str, Any]] = {}

        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__
            if handler_name in settings_map:
                settings = settings_map[handler_name].copy()
            else:
                settings = (profile.get_settings(handler_name) or {}).copy()

            if profile_overrides:
                settings = self._merge_overrides(settings, handler_name, profile_overrides)

            if handler_name == "NvidiaSettingsHandler":
                settings["executables"] = list(profile.nvidia_binding_executables)
                settings["game_name"] = profile.display_name
                settings = inject_nvidia_profile_identity(profile, handler_name, settings)
                if profile.requires_exact_nvidia_binding:
                    settings.setdefault("require_exact_binding", True)
                if profile.allow_unverified_nvidia_profile_reuse:
                    settings.setdefault("allow_unverified_existing_profile_reuse", True)

            if isinstance(profile, BaseProfile):
                settings = profile.resolve_runtime_settings(handler_name, settings.copy())

            final_settings[handler_name] = settings

        return final_settings

    def _build_effective_settings_map(
        self,
        profile_name: str,
        profile: BaseProfile,
        profile_overrides: Any | None,
    ) -> tuple[
        dict[str, dict[str, Any]],
        LintResult | None,
        StabilityGateResult | None,
        NetworkScopeResult | None,
    ]:
        """Build the effective handler settings after the same transforms apply() uses.

        This keeps verification aligned with the real applied path so compliance
        is based on the settings ABSO actually attempted to enforce, not the
        ungated profile defaults.
        """
        settings_map = self._collect_settings(profile)

        lint_result: LintResult | None = None
        if not self.skip_linting:
            lint_result = self._linter.lint(profile)

        stability_gate_result: StabilityGateResult | None = None
        if not self.skip_stability_gate and not self.force_aggressive:
            settings_map, stability_gate_result = self._stability_gate.process(
                profile, settings_map, lint_result
            )

        network_scope_result: NetworkScopeResult | None = None
        if not self.skip_network_scope:
            network_scope_result = self._network_scope.apply_scope(profile, settings_map)
            settings_map = self._network_scope.get_scoped_settings(
                settings_map, network_scope_result
            )

        final_settings = self._finalize_handler_settings(
            profile,
            profile_name,
            settings_map,
            profile_overrides,
        )
        return final_settings, lint_result, stability_gate_result, network_scope_result

    def _validate_profile_contract(
        self,
        profile_name: str,
        profile: BaseProfile,
        final_settings: dict[str, dict[str, Any]],
    ) -> list[str]:
        """Validate final settings against profile-specific invariants."""
        try:
            violations = profile.validate_settings(final_settings)
        except Exception as e:
            logger.error("Profile contract validation crashed for %s: %s", profile_name, e)
            return [f"Profile contract validation crashed: {e}"]

        return [str(item).strip() for item in violations if str(item).strip()]

    def _run_handler_preflight(
        self,
        profile_name: str,
        profile: BaseProfile,
        final_settings: dict[str, dict[str, Any]],
    ) -> list[str]:
        """Run handler preflight checks before any apply side effects."""
        failures: list[str] = []

        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__
            settings = final_settings.get(handler_name, {})
            if not settings:
                continue

            try:
                preflight_result = handler.preflight(settings.copy())
            except Exception as e:
                logger.error(
                    "Handler preflight crashed for %s/%s: %s", profile_name, handler_name, e
                )
                failures.append(f"{handler_name}: preflight crashed: {e}")
                continue

            if not preflight_result.get("success", True):
                error = str(preflight_result.get("error") or "preflight failed").strip()
                failures.append(f"{handler_name}: {error}")

        return failures

    @staticmethod
    def _append_unique(messages: list[str], candidate: str | None) -> None:
        """Append a message if it is non-empty and not already present."""
        if not candidate:
            return

        normalized = str(candidate).strip()
        if not normalized or normalized in messages:
            return

        messages.append(normalized)

    @staticmethod
    def _handler_changed_settings(
        handler_name: str,
        handler_result: dict[str, Any],
    ) -> list[str]:
        """Return settings that actually changed, if the handler reported them.

        ``applied_settings`` is an API compatibility field meaning "handler
        succeeded." Rollback decisions need a stricter signal: did the handler
        mutate state? Newer handlers can report ``changed_settings`` or
        ``changed_keys``. Older handlers are interpreted conservatively so
        failures still roll back if we cannot prove a no-op.
        """
        explicit_settings = handler_result.get("changed_settings")
        if isinstance(explicit_settings, list):
            out: list[str] = []
            for item in explicit_settings:
                text = str(item).strip()
                if not text:
                    continue
                out.append(text if "." in text else f"{handler_name}.{text}")
            return out

        explicit_keys = handler_result.get("changed_keys")
        if isinstance(explicit_keys, list):
            return [
                f"{handler_name}.{str(item).strip()}" for item in explicit_keys if str(item).strip()
            ]

        if "changed" in handler_result:
            return [handler_name] if bool(handler_result.get("changed")) else []

        applied = handler_result.get("applied")
        if isinstance(applied, list):
            if not applied:
                return []
            no_op_markers = ("already", "no change", "skipped")
            for item in applied:
                text = str(item).lower()
                if not any(marker in text for marker in no_op_markers):
                    return [handler_name]
            return []

        return [handler_name]

    def _check_game_running(self, executable_hints: list[str]) -> list[str]:
        """Check if any of the profile's game executables are currently running.

        Args:
            executable_hints: List of executable filenames to check.

        Returns:
            List of warning strings for each running executable found.
        """
        if not executable_hints:
            return []

        warnings: list[str] = []
        try:
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=30,
            )
            if result.returncode == 0:
                running_procs = parse_tasklist_csv_images(result.stdout or "")
                for exe in executable_hints:
                    if exe.lower() in running_procs:
                        warnings.append(
                            f"{exe} is currently running. "
                            f"Restart the game for new settings to take effect."
                        )
                        logger.warning(f"Game executable running during apply: {exe}")
        except Exception as e:
            logger.warning(
                f"Could not determine if game is running (tasklist timed out); "
                f"assuming safe to apply: {e}"
            )

        return warnings

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
        merged = merge_profile_override_settings(settings, handler_name, overrides)
        if merged is settings:
            return settings
        logger.debug("Applied overrides for %s", handler_name)
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
        profile_name = self._canonical_profile_name(profile_name)
        profile = self._get_profile(profile_name)

        report_path = output_dir / f"{profile_name}_settings.md"
        report_content = profile.generate_in_game_report()

        report_path.write_text(report_content, encoding="utf-8")

        return report_path

    def verify_profile(self, profile_name: str) -> dict[str, Any]:
        """Verify that a profile's verifiable settings are active.

        This checks every handler that implements ``verify_active`` and lets
        ABSO prove more than just reboot-gated state after an apply.

        Args:
            profile_name: Name of the profile to verify.

        Returns:
            Dict with 'all_active' bool and per-handler verification results.
        """
        profile_name = self._canonical_profile_name(profile_name)
        profile = self._get_profile(profile_name)
        config_manager = ConfigManager()
        profile_overrides = config_manager.get_profile_overrides(profile_name)
        final_settings_map, lint_result, stability_gate_result, network_scope_result = (
            self._build_effective_settings_map(
                profile_name,
                profile,
                profile_overrides,
            )
        )

        results: dict[str, Any] = {
            "profile": profile_name,
            "all_active": True,
            "handlers": {},
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": [],
        }
        if lint_result is not None:
            results["lint_warnings"] = len(lint_result.warnings)
        if stability_gate_result is not None:
            results["stability_gate_blocked"] = stability_gate_result.blocked_count
        if network_scope_result is not None and network_scope_result.changes_made:
            results["network_scope_changes"] = list(network_scope_result.changes_made)

        # Check handlers that have reboot-requiring settings
        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__

            # Only check handlers that have verify_active method
            if not hasattr(handler, "verify_active"):
                continue

            settings = final_settings_map.get(handler_name, {})
            if not settings:
                continue

            try:
                handler_result = handler.verify_active(settings)
                results["handlers"][handler_name] = handler_result

                if not handler_result.get("all_active", True):
                    results["all_active"] = False
                    for setting_name in handler_result.get("pending_apply_settings", []):
                        results["pending_apply_settings"].append(f"{handler_name}.{setting_name}")
                    for setting_name in handler_result.get("pending_reboot_gated_settings", []):
                        results["pending_reboot_gated_settings"].append(
                            f"{handler_name}.{setting_name}"
                        )

            except Exception as e:
                logger.error(f"Error verifying {handler_name}: {e}")
                results["handlers"][handler_name] = {
                    "error": str(e),
                    "all_active": False,
                }
                results["all_active"] = False

        if not results["pending_apply_settings"]:
            results.pop("pending_apply_settings", None)
        if not results["pending_reboot_gated_settings"]:
            results.pop("pending_reboot_gated_settings", None)

        return results

    def list_profiles(self) -> list[dict[str, Any]]:
        """List all available profiles.

        Returns:
            List of profile info dicts.
        """
        profiles = []

        for name, profile_class in self.PROFILES.items():
            profile = profile_class()
            profiles.append(
                {
                    "id": name,
                    "display_name": profile.display_name,
                    "description": profile.description,
                    "optimization_target": profile.optimization_target,
                }
            )

        return profiles
