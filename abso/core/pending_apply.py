"""Narrow remediation for verifier-reported pending apply settings."""

from __future__ import annotations

from collections.abc import Callable
from typing import Any

from abso.profiles.catalog import resolve_profile_id
from abso.utils.admin import is_admin

SUPPORTED_PENDING_APPLY_SETTINGS = frozenset(
    {
        "GraphicsSettingsHandler.mpo_disabled",
        "GraphicsSettingsHandler.disable_global_fso",
    }
)


def build_pending_apply_actions(
    profile_name: str,
    verify_result: dict[str, Any],
) -> tuple[list[dict[str, Any]], list[str], str | None]:
    """Translate verifier pending-apply items into narrow, safe write actions."""
    pending_apply = list(verify_result.get("pending_apply_settings") or [])
    unsupported = [
        str(setting)
        for setting in pending_apply
        if str(setting) not in SUPPORTED_PENDING_APPLY_SETTINGS
    ]

    actions: list[dict[str, Any]] = []
    handler_result = (verify_result.get("handlers") or {}).get("GraphicsSettingsHandler") or {}
    if "GraphicsSettingsHandler.mpo_disabled" in pending_apply:
        setting_info = (handler_result.get("settings") or {}).get("mpo_disabled") or {}
        target = setting_info.get("target")
        if not isinstance(target, bool):
            return (
                [],
                unsupported,
                "Verifier did not provide a boolean MPO target for GraphicsSettingsHandler.mpo_disabled",
            )
        actions.append(
            {
                "profile": profile_name,
                "pending_setting": "GraphicsSettingsHandler.mpo_disabled",
                "handler": "GraphicsSettingsHandler",
                "apply_setting": "disable_mpo",
                "target": target,
                "reboot_gated": True,
                "description": "Write the Windows MPO registry target only",
            }
        )

    if "GraphicsSettingsHandler.disable_global_fso" in pending_apply:
        # The verifier's pending key uses the apply name, but its readback
        # details use global_fso_disabled. Do not infer or coerce a target.
        setting_info = (handler_result.get("settings") or {}).get("global_fso_disabled") or {}
        target = setting_info.get("target")
        if not isinstance(target, bool):
            return (
                [],
                unsupported,
                "Verifier did not provide a boolean global FSO target for "
                "GraphicsSettingsHandler.disable_global_fso",
            )
        actions.append(
            {
                "profile": profile_name,
                "pending_setting": "GraphicsSettingsHandler.disable_global_fso",
                "handler": "GraphicsSettingsHandler",
                "apply_setting": "disable_global_fso",
                "target": target,
                "reboot_gated": False,
                "description": "Write the Windows global fullscreen optimization registry target only",
            }
        )

    return actions, unsupported, None


def apply_pending_profile_settings(
    profile_name: str,
    *,
    dry_run: bool = False,
    applier: Any | None = None,
    is_admin_func: Callable[[], bool] = is_admin,
    set_current_profile_func: Callable[..., None] | None = None,
    graphics_handler_factory: Callable[[], Any] | None = None,
) -> dict[str, Any]:
    """Apply narrowly-supported pending verifier fixes without a full transaction."""
    profile_name = resolve_profile_id(profile_name) or profile_name
    if applier is None:
        from abso.core.applier import ProfileApplier

        applier = ProfileApplier()
    verify_result = applier.verify_profile(profile_name)
    pending_apply = list(verify_result.get("pending_apply_settings") or [])
    actions, unsupported, action_error = build_pending_apply_actions(
        profile_name,
        verify_result,
    )

    result: dict[str, Any] = {
        "success": False,
        "profile": profile_name,
        "dry_run": dry_run,
        "pending_apply_settings": pending_apply,
        "supported_pending_settings": [action["pending_setting"] for action in actions],
        "unsupported_pending_settings": unsupported,
        "actions": actions,
        "changed": False,
        "changed_settings": [],
        "requires_reboot": False,
        "reboot_reasons": [],
        "handler_results": {},
        "verify_before": verify_result,
        "verify_after": None,
        "notices": [],
        "warnings": [],
        "error": None,
    }

    if action_error:
        result["error"] = action_error
        return result

    if unsupported:
        result["error"] = "Unsupported pending apply setting(s): " + ", ".join(unsupported)
        return result

    if not pending_apply:
        result["success"] = True
        result["notices"].append("No pending apply settings found.")
        return result

    if not actions:
        result["error"] = "No supported pending apply actions were found."
        return result

    if dry_run:
        result["success"] = True
        result["notices"].append("Dry run only; no settings were written.")
        return result

    if not is_admin_func():
        result["error"] = "Admin privileges required to apply pending profile settings"
        return result

    if graphics_handler_factory is None:
        from abso.settings.graphics import GraphicsSettingsHandler

        graphics_handler_factory = GraphicsSettingsHandler

    handler_result = graphics_handler_factory().apply(
        {action["apply_setting"]: action["target"] for action in actions}
    )
    result["handler_results"]["GraphicsSettingsHandler"] = handler_result

    changed_keys = list(handler_result.get("changed_keys") or [])
    changed_settings = [f"GraphicsSettingsHandler.{key}" for key in changed_keys]
    result["changed"] = bool(changed_settings)
    result["changed_settings"] = changed_settings
    result["requires_reboot"] = bool(handler_result.get("requires_reboot", False))
    result["notices"].extend(str(item) for item in (handler_result.get("notices") or []))
    result["warnings"].extend(str(item) for item in (handler_result.get("warnings") or []))

    # The handler can change MPO and then fail a later FSO write. Preserve
    # those effects and the reboot requirement even though the action failed.
    # Persist before readback so verification sees the new reboot gate.
    if result["requires_reboot"]:
        result["reboot_reasons"] = ["GraphicsSettingsHandler"]
        if set_current_profile_func is not None:
            set_current_profile_func(
                profile_name,
                requires_reboot=True,
                reboot_reasons=result["reboot_reasons"],
            )

    if not handler_result.get("success", False):
        result["error"] = handler_result.get("error") or "GraphicsSettingsHandler failed"
        return result

    try:
        verify_after = applier.verify_profile(profile_name)
    except Exception as exc:
        result["error"] = f"Pending apply verification failed: {exc}"
        return result
    result["verify_after"] = verify_after
    if not isinstance(verify_after, dict):
        result["error"] = "Pending apply verification returned an invalid result"
        return result
    result["pending_apply_settings_after"] = list(
        verify_after.get("pending_apply_settings") or []
    )
    result["pending_reboot_gated_settings_after"] = list(
        verify_after.get("pending_reboot_gated_settings") or []
    )

    # Handler success is not proof that its writes took effect. Confirm the
    # requested pending keys cleared, without requiring unrelated settings,
    # manual steps, or reboot-gated activation to be resolved here.
    verification_error = verify_after.get("error")
    graphics_verification = (verify_after.get("handlers") or {}).get("GraphicsSettingsHandler") or {}
    if not verification_error:
        verification_error = graphics_verification.get("error")
    if verification_error:
        result["error"] = f"Pending apply verification failed: {verification_error}"
        return result
    remaining = [
        action["pending_setting"]
        for action in actions
        if action["pending_setting"] in result["pending_apply_settings_after"]
    ]
    if remaining:
        result["error"] = "Pending apply settings remain after remediation: " + ", ".join(remaining)
        return result

    result["success"] = True
    return result
