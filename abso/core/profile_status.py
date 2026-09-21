"""Profile verification status helpers for CLI, tray, and GUI state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any


def get_pending_manual_steps(manual_steps: Any) -> list[dict[str, Any]]:
    """Keep unmet or unverified human actions separate from profile drift."""
    if not isinstance(manual_steps, (list, tuple)):
        return []
    return [
        dict(step) for step in manual_steps
        if isinstance(step, dict) and step.get("satisfied") is not True
    ]


def format_manual_step(step: dict[str, Any]) -> str:
    """Describe saved/read-back evidence without claiming live game activation."""
    label = str(step.get("label") or step.get("key") or "Manual setup")
    current = step.get("current_label")
    if current is None or str(current).lower() == "unknown":
        current = step.get("current")
    if current is None:
        current = "not yet verified"
    expected = step.get("expected_label")
    if expected is None:
        expected = step.get("expected")
    if expected is None:
        message = f"{label}: {current}; follow the profile's setup instructions."
    else:
        message = f"{label}: current {current}; expected {expected}."
    instruction = step.get("instruction")
    if isinstance(instruction, str) and instruction.strip():
        message += " " + instruction.strip()
    return message


def summarize_profile_verification(
    profile_name: str,
    verify_result: dict[str, Any],
    *,
    checked_at: datetime | None = None,
) -> dict[str, Any]:
    """Return a compact status summary from a full profile verification payload."""
    pending_apply = list(verify_result.get("pending_apply_settings") or [])
    pending_reboot_gated = list(verify_result.get("pending_reboot_gated_settings") or [])
    manual_steps = list(verify_result.get("manual_steps") or [])
    handlers = verify_result.get("handlers", {})
    mismatched_handlers = [
        handler_name
        for handler_name, handler_result in handlers.items()
        if isinstance(handler_result, dict) and not bool(handler_result.get("all_active", True))
    ]
    all_active = bool(verify_result.get("all_active"))
    if all_active:
        status = "active"
    elif pending_apply:
        status = "pending_apply"
    elif pending_reboot_gated:
        status = "pending_reboot"
    else:
        status = "mismatch"

    return {
        "checked_at": (checked_at or datetime.now()).isoformat(),
        "profile": profile_name,
        "all_active": all_active,
        "status": status,
        "pending_apply_settings": pending_apply,
        "pending_reboot_gated_settings": pending_reboot_gated,
        "mismatched_handlers": mismatched_handlers,
        "manual_steps": manual_steps,
    }


def build_profile_verification_summary(
    profile_name: str,
    verify_profile: Callable[[str], dict[str, Any]],
    *,
    now: Callable[[], datetime] = datetime.now,
) -> dict[str, Any]:
    """Run profile verification and return the compact state-command summary."""
    checked_at = now()
    try:
        return summarize_profile_verification(
            profile_name,
            verify_profile(profile_name),
            checked_at=checked_at,
        )
    except Exception as exc:  # noqa: BLE001 - state should still be readable
        return {
            "checked_at": checked_at.isoformat(),
            "profile": profile_name,
            "all_active": False,
            "status": "error",
            "pending_apply_settings": [],
            "pending_reboot_gated_settings": [],
            "mismatched_handlers": [],
            "manual_steps": [],
            "error": str(exc),
        }
