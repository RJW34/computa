"""Console formatting helpers for health diagnostics."""

from __future__ import annotations

from typing import Any

HEALTH_CHECK_ORDER = (
    "tray_startup",
    "tray_runtime",
    "tray_runtime_marker",
    "state_file",
    "backups",
    "config",
    "profile_verify",
    "fallback",
    "display_events",
    "display_stability",
)

STATUS_COLORS = {"ok": "green", "warning": "yellow", "error": "red"}
DISPLAY_WARNING_CODES = (
    "MULTIMON_REFRESH_BELOW_CAPABILITY",
    "MULTIMON_MPO_GLITCH_RISK",
)


def format_hz(value: object) -> str:
    """Format a refresh-rate value for compact health output."""
    try:
        rate = float(value)
    except (TypeError, ValueError):
        return "unknown"
    if rate.is_integer():
        return f"{int(rate)} Hz"
    return f"{rate:.2f}".rstrip("0").rstrip(".") + " Hz"


def _int_or_zero(value: object) -> int:
    """Return a non-throwing integer for diagnostic counters."""
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0


def build_health_check_lines(checks: dict[str, Any]) -> list[str]:
    """Build plain health check rows, including future checks and details."""
    check_names = [name for name in HEALTH_CHECK_ORDER if name in checks]
    known_names = set(HEALTH_CHECK_ORDER)
    check_names.extend(sorted(name for name in checks if name not in known_names))

    lines: list[str] = []
    for check_name in check_names:
        check = checks.get(check_name) or {}
        status = check.get("status", "error")
        color = STATUS_COLORS.get(str(status), "white")
        lines.append(f"  [{color}]{check_name}: {status}[/{color}]")
        lines.extend(_build_check_detail_lines(check))
    return lines


def _build_check_detail_lines(check: dict[str, Any]) -> list[str]:
    """Return concise warning/error detail rows for a health check."""
    lines: list[str] = []
    warnings = check.get("warnings") or []
    if isinstance(warnings, list):
        for warning in warnings:
            lines.append(f"    [yellow]- {warning}[/yellow]")
    error = check.get("error")
    if error:
        lines.append(f"    [red]- {error}[/red]")
    return lines


def build_active_state_context_lines(active_state: dict[str, Any] | None) -> list[str]:
    """Build concise active-profile state rows for display diagnostics."""
    if not active_state:
        return []

    current_profile = active_state.get("current_profile") or "(none)"
    lines = [f"Active profile: {current_profile}"]
    if active_state.get("reboot_pending"):
        reasons = list(active_state.get("reboot_reasons") or [])
        reason_text = ", ".join(str(reason) for reason in reasons) or "unknown"
        lines.append(f"Profile state: reboot pending ({reason_text})")
    else:
        lines.append("Profile state: no reboot pending")
    return lines


def build_display_diagnostic_report_lines(payload: dict[str, Any]) -> list[str]:
    """Build the human-readable body for one display-diagnostics sample."""
    lines = [f"Generated: {payload.get('generated_at')}"]
    lines.extend(build_active_state_context_lines(payload.get("active_state")))
    lines.extend(
        build_display_context_lines_from_payload(
            payload.get("display_events") or {},
            payload.get("display_stability") or {},
        )
    )
    summary = payload.get("summary") or {}
    if summary.get("compositor_black_flash_likely"):
        lines.append(
            "[yellow]Interpretation: clean actionable event logs plus the "
            "display/profile evidence point at the Windows compositor/MPO/VRR "
            "path.[/yellow]"
        )
    actions = summary.get("recommended_actions") or []
    if actions:
        lines.append("[bold]Recommended actions:[/bold]")
        for action in actions:
            if not isinstance(action, dict):
                continue
            label = action.get("label")
            if label:
                lines.append(f"  - {label}")
    return lines


def build_display_context_lines(checks: dict[str, Any]) -> list[str]:
    """Build concise display diagnostics for plain health output."""
    events = checks.get("display_events", {}).get("data") or {}
    stability = checks.get("display_stability", {}).get("data") or {}
    return build_display_context_lines_from_payload(events, stability)


def build_display_context_lines_from_payload(
    events: dict[str, Any],
    stability: dict[str, Any],
) -> list[str]:
    """Build concise display diagnostics from direct event/topology payloads."""
    if not events and not stability:
        return []

    lines = ["", "[bold]Display diagnostics:[/bold]"]
    if events:
        event_count = _int_or_zero(events.get("count"))
        actionable_event_count = _int_or_zero(
            events.get("actionable_count")
            if "actionable_count" in events
            else event_count
        )
        benign_event_count = _int_or_zero(events.get("benign_count"))
        channel_error_count = _int_or_zero(events.get("channel_error_count"))
        if "actionable_count" in events or "benign_count" in events:
            lines.append(
                "  Event log: "
                f"{actionable_event_count} actionable display/driver/power event(s), "
                f"{benign_event_count} benign event(s), "
                f"{channel_error_count} channel error(s)"
            )
        else:
            lines.append(
                f"  Event log: {event_count} recent display/driver/power event(s), "
                f"{channel_error_count} channel error(s)"
            )

    if stability:
        monitor_count = stability.get("monitor_count", "unknown")
        risk_level = stability.get("risk_level") or "unknown"
        min_refresh = format_hz(stability.get("min_refresh"))
        max_refresh = format_hz(stability.get("max_refresh"))
        lines.append(
            f"  Topology: {monitor_count} monitor(s), "
            f"{min_refresh} - {max_refresh}, risk {risk_level}"
        )
        likely_path = stability.get("likely_black_flash_path")
        if likely_path:
            lines.append(f"  Likely black-flash path: {likely_path}")
        lines.extend(_build_display_warning_lines(stability))
        next_action = stability.get("next_action")
        if next_action:
            lines.append(f"  Next action: {next_action}")
        lines.extend(_build_recommended_action_lines(stability))

    return lines


def _build_display_warning_lines(stability: dict[str, Any]) -> list[str]:
    """Return compact, high-signal display warning rows."""
    warnings = stability.get("warnings") or []
    if not isinstance(warnings, list):
        return []

    rows: list[str] = []
    seen_codes: set[str] = set()
    for code in DISPLAY_WARNING_CODES:
        if code in seen_codes:
            continue
        for warning in warnings:
            if not isinstance(warning, dict) or warning.get("code") != code:
                continue
            message = warning.get("message")
            if message:
                rows.append(f"  Display warning: {message}")
                seen_codes.add(code)
            break
    return rows


def _build_recommended_action_lines(stability: dict[str, Any]) -> list[str]:
    """Return stable recommended action codes from structured diagnostics."""
    actions = stability.get("recommended_actions") or []
    if not isinstance(actions, list):
        return []

    codes: list[str] = []
    seen: set[str] = set()
    for action in actions:
        if not isinstance(action, dict):
            continue
        code = str(action.get("code") or "").strip()
        if not code or code in seen:
            continue
        codes.append(code)
        seen.add(code)

    if not codes:
        return []
    return ["  Recommended actions: " + ", ".join(codes)]
