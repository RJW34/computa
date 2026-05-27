"""Read-only display diagnostics aggregation."""

from __future__ import annotations

import time
from collections.abc import Callable, Iterator
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.display_events import collect_recent_display_events
from abso.core.display_stability import collect_display_stability_snapshot
from abso.core.state_store import read_state_snapshot

DisplayDiagnosticsCollector = Callable[..., dict[str, Any]]
SleepFunc = Callable[[float], None]

GRAPHICS_REBOOT_NEXT_ACTION = (
    "Normal reboot required before judging MPO/compositor flicker fix."
)
ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS = "reboot_to_commit_graphics_settings"
ACTION_REVIEW_SECONDARY_REFRESH_RATE = "review_secondary_refresh_rate"
ACTION_AVOID_REDUNDANT_PROFILE_APPLY = "avoid_redundant_profile_apply"
ACTION_REVIEW_CAPTURE_MPO_PERFORMANCE = "review_capture_mpo_performance"
DISPLAY_RECOMMENDED_ACTION_CODES = (
    ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
    ACTION_REVIEW_SECONDARY_REFRESH_RATE,
    ACTION_REVIEW_CAPTURE_MPO_PERFORMANCE,
    ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
)


def collect_display_diagnostics(
    *,
    lookback_minutes: int = 30,
    max_events: int = 10,
    event_timeout_seconds: int = 5,
    state_targets: list[Path] | None = None,
) -> dict[str, Any]:
    """Collect display event and topology diagnostics without display writes."""
    events = collect_recent_display_events(
        lookback_minutes=lookback_minutes,
        max_events=max_events,
        timeout_seconds=event_timeout_seconds,
    )
    stability = collect_display_stability_snapshot()
    active_state = collect_active_state_context(state_targets) if state_targets else None
    if active_state:
        stability = enrich_display_stability_with_active_state(stability, active_state)
    return {
        "generated_at": datetime.now().isoformat(),
        "read_only": True,
        "display_events": events,
        "display_stability": stability,
        "active_state": active_state,
        "summary": summarize_display_diagnostics(events, stability, active_state),
    }


def iter_display_diagnostic_samples(
    *,
    samples: int = 1,
    interval_seconds: float = 10.0,
    lookback_minutes: int = 30,
    max_events: int = 10,
    event_timeout_seconds: int = 5,
    state_targets: list[Path] | None = None,
    collector: DisplayDiagnosticsCollector | None = None,
    sleep_func: SleepFunc = time.sleep,
) -> Iterator[dict[str, Any]]:
    """Yield read-only display diagnostic samples with optional spacing."""
    sample_count = max(1, int(samples))
    interval = max(0.0, float(interval_seconds))
    active_collector = collector or collect_display_diagnostics

    for index in range(sample_count):
        yield active_collector(
            lookback_minutes=lookback_minutes,
            max_events=max_events,
            event_timeout_seconds=event_timeout_seconds,
            state_targets=state_targets,
        )
        if index < sample_count - 1 and interval > 0:
            sleep_func(interval)


def collect_active_state_context(state_targets: list[Path]) -> dict[str, Any]:
    """Return read-only active-profile state context for display diagnostics."""
    return build_active_state_context(read_state_snapshot(state_targets))


def build_active_state_context(state: dict[str, Any]) -> dict[str, Any]:
    """Return compact display-relevant state context from an active-profile state."""
    reboot_reasons = list(state.get("reboot_reasons") or [])
    reboot_pending = bool(state.get("reboot_pending"))
    graphics_reboot_pending = reboot_pending and "GraphicsSettingsHandler" in reboot_reasons
    next_action = GRAPHICS_REBOOT_NEXT_ACTION if graphics_reboot_pending else None
    current_profile = state.get("current_profile")
    profile_display_context = (
        build_active_profile_display_context(str(current_profile))
        if current_profile
        else None
    )
    return {
        "current_profile": current_profile,
        "applied_at": state.get("applied_at"),
        "reboot_pending": reboot_pending,
        "reboot_reasons": reboot_reasons,
        "graphics_reboot_pending": graphics_reboot_pending,
        "next_action": next_action,
        "profile_display_context": profile_display_context,
    }


def build_active_profile_display_context(profile_name: str) -> dict[str, Any]:
    """Return read-only profile traits relevant to compositor/FPS diagnosis."""
    try:
        from abso.core.applier import ProfileApplier
        from abso.core.config import ConfigManager

        applier = ProfileApplier(
            skip_linting=True,
            skip_rollback_guard=True,
            skip_stability_gate=True,
            skip_network_scope=True,
            skip_multimon_detection=True,
            skip_capability_checks=True,
        )
        canonical = applier._canonical_profile_name(profile_name)
        profile = applier._get_profile(canonical)
        settings_map, *_ = applier._build_effective_settings_map(
            canonical,
            profile,
            ConfigManager().get_profile_overrides(canonical),
        )

        graphics = settings_map.get("GraphicsSettingsHandler", {})
        nvidia = settings_map.get("NvidiaSettingsHandler", {})
        windows = settings_map.get("WindowsSettingsHandler", {})
        ow2 = settings_map.get("OW2ConfigHandler", {})
        return {
            "profile_id": canonical,
            "display_name": profile.display_name,
            "is_capture_safe": bool(profile.is_capture_safe),
            "graphics_disable_mpo": graphics.get("disable_mpo"),
            "nvidia_global_vrr_mode": (
                nvidia.get("global_vrr_mode")
                or nvidia.get("global_gsync_mode")
                or nvidia.get("vrr_mode")
            ),
            "windows_hdr": windows.get("hdr"),
            "ow2_window_mode": ow2.get("window_mode"),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must not break health
        return {"profile_id": profile_name, "error": str(exc)}


def enrich_display_stability_with_active_state(
    stability: dict[str, Any],
    active_state: dict[str, Any],
) -> dict[str, Any]:
    """Attach state-derived display guidance without mutating detector output."""
    enriched = dict(stability)
    if active_state.get("graphics_reboot_pending"):
        enriched["graphics_reboot_pending"] = True
    if active_state.get("next_action") and not enriched.get("next_action"):
        enriched["next_action"] = active_state["next_action"]
    return enriched


def summarize_display_diagnostics(
    events: dict[str, Any],
    stability: dict[str, Any],
    active_state: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Return compact interpretation fields for display diagnostics."""
    event_count = _safe_int(events.get("count"))
    channel_error_count = _safe_int(events.get("channel_error_count"))
    risk_level = str(stability.get("risk_level") or "unknown")
    likely_path = stability.get("likely_black_flash_path")
    clean_event_log = event_count == 0 and channel_error_count == 0
    compositor_likely = bool(
        clean_event_log
        and risk_level in {"medium", "high"}
        and isinstance(likely_path, str)
        and likely_path.startswith("windows_compositor")
    )
    summary = {
        "event_count": event_count,
        "channel_error_count": channel_error_count,
        "risk_level": risk_level,
        "likely_black_flash_path": likely_path,
        "clean_event_log": clean_event_log,
        "compositor_black_flash_likely": compositor_likely,
    }
    if active_state:
        summary["current_profile"] = active_state.get("current_profile")
        summary["reboot_pending"] = bool(active_state.get("reboot_pending"))
        summary["reboot_reasons"] = list(active_state.get("reboot_reasons") or [])
        summary["next_action"] = active_state.get("next_action")
    summary["recommended_actions"] = build_recommended_actions(
        stability=stability,
        active_state=active_state,
        compositor_likely=compositor_likely,
    )
    return summary


def build_recommended_actions(
    *,
    stability: dict[str, Any],
    active_state: dict[str, Any] | None,
    compositor_likely: bool,
) -> list[dict[str, Any]]:
    """Return ordered, non-mutating next steps for display diagnostics."""
    actions: list[dict[str, Any]] = []

    if active_state and active_state.get("graphics_reboot_pending"):
        actions.append({
            "code": ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
            "label": GRAPHICS_REBOOT_NEXT_ACTION,
            "source": "active_state",
            "requires_user_action": True,
            "changes_display_state": True,
        })

    refresh_warning = _first_warning(stability, "MULTIMON_REFRESH_BELOW_CAPABILITY")
    if refresh_warning:
        actions.append({
            "code": ACTION_REVIEW_SECONDARY_REFRESH_RATE,
            "label": str(refresh_warning.get("message") or "Review display refresh rates."),
            "source": "display_stability",
            "requires_user_action": True,
            "changes_display_state": True,
            "detail": (
                "After the pending reboot, review Windows/NVIDIA display settings "
                "and set active displays to their highest stable refresh rates. "
                "ABSO does not change live display modes automatically."
            ),
        })

    if active_state and _has_capture_mpo_performance_risk(stability, active_state):
        actions.append({
            "code": ACTION_REVIEW_CAPTURE_MPO_PERFORMANCE,
            "label": (
                "MPO is disabled on a capture-safe borderless VRR profile; "
                "if FPS dropped after reboot, use the strict fullscreen profile "
                "or re-enable MPO after fixing the mixed-refresh display path."
            ),
            "source": "active_profile_settings",
            "requires_user_action": True,
            "changes_display_state": True,
            "detail": (
                "This combination can trade the one-second black flash for extra "
                "DWM/compositor cost in Overwatch's borderless HDR path. The "
                "strict Overwatch G-SYNC HDR profile avoids that borderless "
                "capture path, while re-enabling MPO requires another reboot."
            ),
        })

    if compositor_likely:
        actions.append({
            "code": ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
            "label": (
                "Do not repeatedly reapply the already-active profile to chase "
                "black flashes; that can cause avoidable display/color resets."
            ),
            "source": "diagnostic_interpretation",
            "requires_user_action": False,
            "changes_display_state": False,
        })

    return actions


def _has_capture_mpo_performance_risk(
    stability: dict[str, Any],
    active_state: dict[str, Any],
) -> bool:
    profile_context = active_state.get("profile_display_context")
    if not isinstance(profile_context, dict):
        return False
    if profile_context.get("graphics_disable_mpo") is not True:
        return False
    if profile_context.get("is_capture_safe") is not True:
        return False
    if str(profile_context.get("ow2_window_mode")) != "1":
        return False
    risk_factors = stability.get("risk_factors") or []
    return "mixed_refresh" in risk_factors or stability.get("risk_level") == "high"


def _first_warning(stability: dict[str, Any], code: str) -> dict[str, Any] | None:
    warnings = stability.get("warnings") or []
    if not isinstance(warnings, list):
        return None
    for warning in warnings:
        if isinstance(warning, dict) and warning.get("code") == code:
            return warning
    return None


def _safe_int(value: object) -> int:
    try:
        return int(value or 0)
    except (TypeError, ValueError):
        return 0
