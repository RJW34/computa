"""Post-apply compliance evaluation.

Converts apply/verify outcomes into actionable compliance issues and
criticality for commit/rollback decisions.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any

from abso.core.applier import ApplyResult


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
    """Evaluates post-apply compliance and criticality."""

    # Handlers where verify mismatches are treated as critical by default.
    CRITICAL_VERIFY_HANDLERS: set[str] = {
        "WindowsSettingsHandler",
        "Rivals2ConfigHandler",
    }

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
            handlers = verify_result.get("handlers", {})
            for handler_name, handler_data in handlers.items():
                if not isinstance(handler_data, dict):
                    continue

                all_active = handler_data.get("all_active", True)
                if all_active:
                    continue

                severity = (
                    ComplianceSeverity.CRITICAL
                    if handler_name in self.CRITICAL_VERIFY_HANDLERS
                    else ComplianceSeverity.WARNING
                )
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
