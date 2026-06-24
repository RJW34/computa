"""Profile verification status helpers for CLI, tray, and GUI state."""

from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any


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
