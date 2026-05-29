"""Post-apply compliance evaluation.

Converts apply/verify outcomes into actionable compliance issues and
criticality for commit/rollback decisions.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from abso.core.applier import ApplyResult

logger = logging.getLogger(__name__)


class ComplianceSeverity(Enum):
    """Compliance issue severities."""

    CRITICAL = "critical"
    WARNING = "warning"
    INFO = "info"


@dataclass
class ComplianceIssue:
    """Single compliance finding."""

    code: str
    severity: ComplianceSeverity
    message: str
    details: str | None = None
    source: str | None = None


@dataclass
class ComplianceReport:
    """Aggregated compliance result."""

    profile_id: str
    issues: list[ComplianceIssue] = field(default_factory=list)

    @property
    def passed(self) -> bool:
        return not self.has_critical

    @property
    def has_critical(self) -> bool:
        return any(issue.severity == ComplianceSeverity.CRITICAL for issue in self.issues)

    @property
    def warnings(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == ComplianceSeverity.WARNING]

    @property
    def critical(self) -> list[ComplianceIssue]:
        return [i for i in self.issues if i.severity == ComplianceSeverity.CRITICAL]

    def to_dict(self) -> dict[str, Any]:
        """Convert to JSON-safe dictionary."""
        return {
            "profile_id": self.profile_id,
            "passed": self.passed,
            "has_critical": self.has_critical,
            "issues": [
                {
                    "code": issue.code,
                    "severity": issue.severity.value,
                    "message": issue.message,
                    "details": issue.details,
                    "source": issue.source,
                }
                for issue in self.issues
            ],
        }


class ComplianceEngine:
    """Evaluates post-apply compliance and criticality.

    Criticality of a post-apply verify mismatch is derived from
    ``SettingsHandler.is_critical_verify`` instead of a hardcoded
    class-name set, so handler renames cannot silently downgrade
    severity. The resolved set is cached per process.
    """

    _critical_handler_names: set[str] | None = None

    @classmethod
    def _resolve_critical_handler_names(cls) -> set[str]:
        """Build the critical-verify class-name set lazily from the handler factory."""
        if cls._critical_handler_names is not None:
            return cls._critical_handler_names

        names: set[str] = set()
        try:
            from abso.core.backup import _get_backup_handlers

            for handler in _get_backup_handlers():
                try:
                    if getattr(handler, "is_critical_verify", False):
                        names.add(handler.__class__.__name__)
                except Exception as exc:  # noqa: BLE001 — never let one handler poison the set
                    logger.debug(
                        "Skipping handler %s while resolving critical-verify set: %s",
                        handler.__class__.__name__,
                        exc,
                    )
        except Exception as exc:  # noqa: BLE001
            logger.warning(
                "Failed to resolve critical-verify handler set; falling back to "
                "ConfigHandler suffix heuristic: %s",
                exc,
            )

        cls._critical_handler_names = names
        return names

    @classmethod
    def invalidate_critical_handler_cache(cls) -> None:
        """Drop the cached set so the next call re-derives it (tests only)."""
        cls._critical_handler_names = None

    @staticmethod
    def _is_reboot_gated_only_mismatch(handler_data: dict[str, Any]) -> bool:
        """Return True when the only verify gap is a written reboot-gated target."""
        pending_apply = handler_data.get("pending_apply_settings") or []
        if pending_apply:
            return False

        pending_reboot = handler_data.get("pending_reboot_gated_settings") or []
        pending_reboot_names = {
            str(setting).strip() for setting in pending_reboot if str(setting).strip()
        }
        if not pending_reboot_names:
            return False

        settings = handler_data.get("settings")
        if not isinstance(settings, dict):
            return True

        for setting_name, setting_data in settings.items():
            if not isinstance(setting_data, dict):
                continue

            if str(setting_name) in pending_reboot_names:
                if not bool(setting_data.get("reboot_gated", False)):
                    return False
                if setting_data.get("registry_target_written") is False:
                    return False
                continue

            # Any unrelated explicit inactive setting means this is not a pure
            # reboot wait. Missing "active" stays non-blocking for older
            # verifier payloads.
            if setting_data.get("active") is False:
                return False
            if setting_data.get("registry_target_written") is False:
                return False

        return True

    def evaluate(
        self,
        profile_id: str,
        apply_result: ApplyResult,
        verify_result: dict[str, Any] | None,
    ) -> ComplianceReport:
        """Generate compliance report from apply/verify outputs."""
        report = ComplianceReport(profile_id=profile_id)

        if not apply_result.success and apply_result.error:
            report.issues.append(
                ComplianceIssue(
                    code="APPLY_FAILED",
                    severity=ComplianceSeverity.CRITICAL,
                    message="Profile apply reported failure",
                    details=apply_result.error,
                    source="ProfileApplier",
                )
            )

        for failed in apply_result.failed_settings:
            handler_name = failed.split(":", 1)[0].strip() if ":" in failed else failed
            report.issues.append(
                ComplianceIssue(
                    code="APPLY_HANDLER_FAILED",
                    severity=ComplianceSeverity.CRITICAL,
                    message=f"Handler apply failed: {handler_name}",
                    details=failed,
                    source=handler_name,
                )
            )

        if verify_result:
            critical_names = self._resolve_critical_handler_names()
            handlers = verify_result.get("handlers", {})
            for handler_name, handler_data in handlers.items():
                if not isinstance(handler_data, dict):
                    continue

                all_active = handler_data.get("all_active", True)
                if all_active:
                    continue

                if self._is_reboot_gated_only_mismatch(handler_data):
                    report.issues.append(
                        ComplianceIssue(
                            code="VERIFY_PENDING_REBOOT",
                            severity=ComplianceSeverity.WARNING,
                            message=f"Verification pending reboot in {handler_name}",
                            details=str(handler_data),
                            source=handler_name,
                        )
                    )
                    continue

                severity = ComplianceSeverity.WARNING
                if (
                    handler_name in critical_names
                    or handler_name.endswith("ConfigHandler")
                ):
                    severity = ComplianceSeverity.CRITICAL
                report.issues.append(
                    ComplianceIssue(
                        code="VERIFY_MISMATCH",
                        severity=severity,
                        message=f"Verification mismatch in {handler_name}",
                        details=str(handler_data),
                        source=handler_name,
                    )
                )

        return report
