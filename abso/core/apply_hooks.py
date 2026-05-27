"""Post-apply hooks shared by CLI, tray-facing flows, and tests."""

from __future__ import annotations

import logging
import os
import re
from typing import Any

from abso.profiles.catalog import resolve_profile_id

logger = logging.getLogger(__name__)


def run_post_apply_sweep(
    profile_name: str,
    tx: Any,
    result: Any | None,
) -> dict[str, Any] | None:
    """Run the launch-time process janitor sweep after a successful apply."""
    if not (tx.success and result and result.success):
        return None

    try:
        from abso.core.process_janitor import ProcessJanitor
        from abso.profiles.catalog import get_profile_instances

        canonical = resolve_profile_id(profile_name) or profile_name
        profile = get_profile_instances().get(canonical)
        if profile is None:
            return None

        killset = profile.launch_process_killset()
        # Post-apply is not an explicit opt-in surface. Keep this aligned with
        # launch-sweep's default and tray aggressiveProcessJanitor=false.
        resolved = killset.resolve(include_opt_in=False)
        if not resolved:
            return None

        janitor = ProcessJanitor()
        sweep = janitor.sweep(resolved, dry_run=False)
        return sweep.to_dict()
    except Exception as exc:  # noqa: BLE001 - apply must stay authoritative
        logger.warning("Post-apply launch sweep failed: %s", exc)
        return {
            "stopped": [],
            "not_running": [],
            "failed": [],
            "warnings": [f"Post-apply sweep failed: {exc}"],
            "error": str(exc),
        }


# Handler-level settings keys whose mutation can leave the desktop color / HDR
# composition pipeline in a stale state on modern NVIDIA driver branches
# (verified Windows Insider build 29591 + NVIDIA 5xx). Automatic recovery is
# disabled by default because recovery APIs can briefly blank attached displays.
HDR_PIPELINE_KEYS: dict[str, frozenset[str]] = {
    "WindowsSettingsHandler": frozenset(
        {
            "hdr",
            "auto_hdr",
            "advanced_color",
            "sdr_white_level_nits",
        }
    ),
    "GraphicsSettingsHandler": frozenset(
        {
            "disable_auto_color_management",
        }
    ),
    "ColorProfileSettingsHandler": frozenset(
        {
            "icc_profile",
        }
    ),
    "DisplayColorRangeHandler": frozenset(
        {
            "dynamic_range",
        }
    ),
}


def profile_touches_hdr_pipeline(profile: Any) -> tuple[bool, list[str]]:
    """Return whether a profile requests settings that can stale the HDR pipeline."""
    reasons: list[str] = []
    for handler_name, keys in HDR_PIPELINE_KEYS.items():
        try:
            requested = profile.get_settings(handler_name) or {}
        except Exception:  # noqa: BLE001 - profile probing is best effort
            continue
        hit_keys = sorted(k for k in keys if k in requested)
        if hit_keys:
            reasons.append(f"{handler_name}: {', '.join(hit_keys)}")
    return bool(reasons), reasons


_MONITOR_COUNT_WARNING_RE = re.compile(r"\b(\d+)\s+monitors detected\b", re.IGNORECASE)


def auto_display_recovery_enabled() -> bool:
    """Whether profile apply may run display recovery without direct user action."""
    value = os.environ.get("ABSO_ENABLE_AUTO_DISPLAY_RECOVERY", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


def result_monitor_count(result: Any | None) -> int | None:
    """Best-effort active monitor count from the apply result."""
    if result is None:
        return None

    multimon_result = getattr(result, "multimon_result", None)
    environment = getattr(multimon_result, "environment", None)
    monitor_count = getattr(environment, "monitor_count", None)
    if isinstance(monitor_count, int):
        return monitor_count
    if isinstance(monitor_count, float):
        return int(monitor_count)

    monitors = getattr(environment, "monitors", None)
    if isinstance(monitors, list):
        return len(monitors)

    for warning in getattr(result, "warnings", []) or []:
        match = _MONITOR_COUNT_WARNING_RE.search(str(warning))
        if match:
            return int(match.group(1))

    return None


def live_monitor_count() -> tuple[int | None, str | None]:
    """Best-effort read-only live monitor count for display-recovery safety."""
    try:
        from abso.core.multimon_detector import MultiMonitorDetector

        detected = MultiMonitorDetector().detect()
        monitor_count = getattr(getattr(detected, "environment", None), "monitor_count", None)
        if isinstance(monitor_count, int) and monitor_count > 0:
            return monitor_count, None
        if isinstance(monitor_count, float) and monitor_count > 0:
            return int(monitor_count), None
        return None, "live monitor detector returned no positive monitor count"
    except Exception as exc:  # noqa: BLE001 - this is a fail-closed safety probe
        return None, str(exc)


def run_post_apply_display_reset(
    profile_name: str,
    tx: Any,
    result: Any | None,
) -> dict[str, Any] | None:
    """Recover the display pipeline after a successful apply that touched HDR."""
    if not (tx.success and result and result.success):
        return None

    try:
        from abso.profiles.catalog import get_profile_instances

        canonical = resolve_profile_id(profile_name) or profile_name
        profile = get_profile_instances().get(canonical)
        if profile is None:
            return None

        touches_hdr, reasons = profile_touches_hdr_pipeline(profile)
        if not touches_hdr:
            return None

        if not auto_display_recovery_enabled():
            return {
                "fired": False,
                "skipped_reason": "auto_display_recovery_disabled",
                "triggered_by": reasons,
                "manual_command": "abso reset-display --method driver-hotkey",
            }

        if hasattr(result, "changed_settings"):
            changed_settings = list(getattr(result, "changed_settings", []) or [])
            if not changed_settings:
                return {
                    "fired": False,
                    "skipped_reason": "no_settings_changed",
                    "triggered_by": reasons,
                    "changed_settings": [],
                }
            hdr_sensitive_prefixes = tuple(f"{handler}." for handler in HDR_PIPELINE_KEYS)
            if not any(str(item).startswith(hdr_sensitive_prefixes) for item in changed_settings):
                return {
                    "fired": False,
                    "skipped_reason": "no_display_pipeline_changes",
                    "triggered_by": reasons,
                    "changed_settings": changed_settings,
                }

        monitor_count = result_monitor_count(result)
        monitor_count_source = "apply_result" if monitor_count is not None else None
        monitor_count_error = None
        if monitor_count is None:
            monitor_count, monitor_count_error = live_monitor_count()
            monitor_count_source = "live_probe" if monitor_count is not None else None

        if monitor_count and monitor_count > 1:
            logger.info(
                "Skipping automatic post-apply display recovery for %s because "
                "%s active monitors were detected; use 'abso reset-display' "
                "explicitly if stale HDR/color state needs recovery.",
                profile_name,
                monitor_count,
            )
            return {
                "fired": False,
                "skipped_reason": "multi_monitor_auto_reset_suppressed",
                "triggered_by": reasons,
                "monitor_count": monitor_count,
                "monitor_count_source": monitor_count_source,
                "manual_command": "abso reset-display --method driver-hotkey",
            }
        if monitor_count is None:
            logger.info(
                "Skipping automatic post-apply display recovery for %s because "
                "monitor count could not be proven; use 'abso reset-display' "
                "explicitly if stale HDR/color state needs recovery.",
                profile_name,
            )
            return {
                "fired": False,
                "skipped_reason": "monitor_count_unknown_auto_reset_suppressed",
                "triggered_by": reasons,
                "monitor_count": None,
                "monitor_count_error": monitor_count_error,
                "manual_command": "abso reset-display --method driver-hotkey",
            }

        from abso.utils.display_reset import is_available, refresh_display_pipeline

        if not is_available():
            logger.info(
                "Skipping post-apply display recovery for %s - "
                "no display recovery API is available in this session.",
                profile_name,
            )
            return {
                "fired": False,
                "skipped_reason": "display_refresh_unavailable",
                "triggered_by": reasons,
            }

        logger.info(
            "Running post-apply display recovery (%s) to commit HDR pipeline: %s",
            profile_name,
            "; ".join(reasons),
        )
        outcome = refresh_display_pipeline()
        return {
            "fired": bool(outcome.get("success")),
            "method": outcome.get("method"),
            "status": outcome.get("status"),
            "elapsed_seconds": outcome.get("elapsed_seconds"),
            "triggered_by": reasons,
            "error": outcome.get("error"),
            "sent_count": outcome.get("sent_count"),
            "steps": outcome.get("steps"),
        }
    except Exception as exc:  # noqa: BLE001 - apply must stay authoritative
        logger.warning("Post-apply display refresh failed: %s", exc)
        return {
            "fired": False,
            "error": str(exc),
            "triggered_by": [],
        }


def enforce_running_process_priority(profile: Any) -> dict[str, Any] | None:
    """Re-assert IFEO process priority on running game instances."""
    try:
        executables = list(getattr(profile, "executable_hints", []) or [])
        if not executables:
            return None

        from abso.settings.process_priority import ProcessPriorityHandler

        priority_settings = profile.get_settings("ProcessPriorityHandler") or {}
        cpu_priority = priority_settings.get(
            "cpu_priority", ProcessPriorityHandler.CPU_PRIORITY_HIGH
        )

        handler = ProcessPriorityHandler(executables)
        handler._set_running_processes_priority(cpu_priority)

        priority_map = {
            ProcessPriorityHandler.CPU_PRIORITY_IDLE: "Idle",
            ProcessPriorityHandler.CPU_PRIORITY_NORMAL: "Normal",
            ProcessPriorityHandler.CPU_PRIORITY_HIGH: "High",
            ProcessPriorityHandler.CPU_PRIORITY_REALTIME: "RealTime",
        }
        return {
            "targeted": executables,
            "cpu_priority": cpu_priority,
            "priority_name": priority_map.get(cpu_priority, "High"),
            "errors": [],
        }
    except Exception as exc:  # noqa: BLE001 - launch-sweep must stay non-fatal
        logger.warning("Live priority enforcement failed: %s", exc)
        return {
            "targeted": [],
            "cpu_priority": None,
            "priority_name": None,
            "errors": [str(exc)],
        }
