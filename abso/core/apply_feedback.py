"""Shared apply/restore feedback classification helpers."""

from __future__ import annotations

import re
from typing import Any


def describe_restore_summary(
    summary: dict[str, Any], *, blocking_only: bool = False
) -> str | None:
    """Build a concise message for an incomplete restore summary."""
    incomplete = summary.get("failed_components", []) + summary.get("skipped_components", [])
    if blocking_only:
        incomplete = [item for item in incomplete if bool(item.get("blocking", True))]
    if not incomplete:
        return None

    handlers = ", ".join(item.get("handler", "unknown") for item in incomplete)
    return f"Restore incomplete for: {handlers}"


def append_unique_message(messages: list[str], message: str | None) -> None:
    """Append a non-empty message if it has not already been recorded."""
    if not message:
        return

    normalized = message.strip()
    if not normalized or normalized in messages:
        return

    messages.append(normalized)


def collect_apply_warnings(tx: Any, result: Any | None) -> list[str]:
    """Collect user-facing warnings from apply result and transaction state."""
    warnings: list[str] = []

    if result:
        for warning in result.warnings or []:
            append_unique_message(warnings, warning)

    transaction = getattr(tx, "checkpoints", None) or []
    for checkpoint in transaction:
        if getattr(checkpoint, "status", "") == "warn":
            append_unique_message(warnings, getattr(checkpoint, "message", None))

    compliance_report = getattr(tx, "compliance_report", None)
    if compliance_report:
        for issue in compliance_report.warnings:
            detail = f"{issue.message}: {issue.details}" if issue.details else issue.message
            append_unique_message(warnings, detail)

    return warnings


def collect_apply_notices(result: Any | None) -> list[str]:
    """Collect non-warning informational notices from an apply result."""
    notices: list[str] = []
    if not result:
        return notices

    for notice in getattr(result, "notices", []) or []:
        append_unique_message(notices, notice)

    return notices


_SOFT_APPLY_WARNING_PATTERNS = (
    re.compile(r"mixed refresh rates detected", re.IGNORECASE),
    re.compile(r"\b\d+\s+monitors detected\b", re.IGNORECASE),
    re.compile(r"mpo glitch risk", re.IGNORECASE),
    re.compile(
        r"baseline restore incomplete for known non-restorable handlers",
        re.IGNORECASE,
    ),
)


def is_soft_apply_warning(message: str | None) -> bool:
    """Return True when a warning is an environmental caution, not an action blocker."""
    if not message:
        return False

    normalized = message.strip()
    if not normalized:
        return False

    return any(pattern.search(normalized) for pattern in _SOFT_APPLY_WARNING_PATTERNS)


def determine_apply_summary_level(
    warnings: list[str],
    notices: list[str],
) -> str:
    """Classify apply UX severity for tray/gui surfaces."""
    if warnings:
        if all(is_soft_apply_warning(warning) for warning in warnings):
            return "caution"
        return "warning"

    if notices:
        return "notice"

    return "success"
