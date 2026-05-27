"""Passive display-topology stability diagnostics."""

from __future__ import annotations

from typing import Any

from abso.core.multimon_detector import (
    DisplayEnvironment,
    MonitorInfo,
    MultiMonitorDetector,
    MultiMonitorResult,
)


def _monitor_row(monitor: MonitorInfo) -> dict[str, Any]:
    """Serialize one detected monitor for compact diagnostics."""
    refresh_headroom = None
    if monitor.max_refresh_rate is not None:
        refresh_headroom = max(0.0, monitor.max_refresh_rate - monitor.refresh_rate)
    return {
        "name": monitor.name,
        "width": monitor.width,
        "height": monitor.height,
        "refresh_rate": monitor.refresh_rate,
        "max_refresh_rate": monitor.max_refresh_rate,
        "refresh_headroom_hz": refresh_headroom,
        "is_primary": monitor.is_primary,
        "is_hdr_capable": monitor.is_hdr_capable,
        "is_vrr_capable": monitor.is_vrr_capable,
        "vrr_type": monitor.vrr_type,
        "vrr_range": monitor.vrr_range,
    }


def _warning_row(warning: Any) -> dict[str, str]:
    """Serialize a MultiMonitorWarning-like object."""
    return {
        "code": str(getattr(warning, "code", "") or ""),
        "message": str(getattr(warning, "message", "") or ""),
        "recommendation": str(getattr(warning, "recommendation", "") or ""),
    }


def _risk_factors(env: DisplayEnvironment) -> list[str]:
    """Return concrete compositor risk factors in the active display topology."""
    factors: list[str] = []
    if env.monitor_count > 1:
        factors.append("multi_monitor")
    if env.has_mixed_refresh:
        factors.append("mixed_refresh")
    if env.has_mixed_resolution:
        factors.append("mixed_resolution")
    if any(monitor.is_vrr_capable for monitor in env.monitors):
        factors.append("vrr_capable_display")
    if any(
        monitor.max_refresh_rate is not None
        and monitor.max_refresh_rate - monitor.refresh_rate >= 5.0
        for monitor in env.monitors
    ):
        factors.append("monitor_below_refresh_capability")
    if env.detected_overlays:
        factors.append("active_overlay_process")
    return factors


def _risk_level(env: DisplayEnvironment, factors: list[str]) -> str:
    """Classify how likely this topology is to hit compositor black flashes."""
    if env.monitor_count > 1 and (
        env.has_mixed_refresh or any(monitor.is_vrr_capable for monitor in env.monitors)
    ):
        return "high"
    if factors:
        return "medium"
    return "low"


def summarize_display_stability(result: MultiMonitorResult) -> dict[str, Any]:
    """Build a compact, read-only display-stability summary."""
    env = result.environment
    factors = _risk_factors(env)
    risk_level = _risk_level(env, factors)
    likely_path = None
    if risk_level == "high":
        likely_path = "windows_compositor_mpo_vrr_mixed_refresh"
    elif factors:
        likely_path = "windows_compositor"

    return {
        "monitor_count": env.monitor_count,
        "is_multi_monitor": env.is_multi_monitor,
        "has_mixed_refresh": env.has_mixed_refresh,
        "has_mixed_resolution": env.has_mixed_resolution,
        "primary_refresh": env.primary_refresh,
        "min_refresh": env.min_refresh,
        "max_refresh": env.max_refresh,
        "detected_overlays": list(env.detected_overlays),
        "exclusive_fullscreen_safe": bool(result.exclusive_fullscreen_safe),
        "monitors": [_monitor_row(monitor) for monitor in env.monitors],
        "warnings": [_warning_row(warning) for warning in result.warnings],
        "risk_factors": factors,
        "risk_level": risk_level,
        "likely_black_flash_path": likely_path,
        "event_log_correlation_hint": (
            "If Display/Kernel-PnP/nvlddmkm event logs stay clean during a "
            "one-second black flash, suspect compositor/MPO/VRR/HDR state "
            "rather than a physical monitor disconnect."
        ),
    }


def collect_display_stability_snapshot(
    *,
    detector: MultiMonitorDetector | None = None,
) -> dict[str, Any]:
    """Collect passive display-topology stability data without display writes."""
    try:
        active_detector = detector or MultiMonitorDetector()
        return {
            "supported": True,
            "query_scope": "multimon_detector_read_only",
            **summarize_display_stability(active_detector.detect()),
        }
    except Exception as exc:  # noqa: BLE001 - diagnostics must not break health
        return {
            "supported": False,
            "query_scope": "multimon_detector_read_only",
            "error": str(exc),
        }
