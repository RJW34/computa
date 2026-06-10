"""Tests for passive display-topology stability diagnostics."""

from __future__ import annotations

from abso.core.display_stability import (
    collect_display_stability_snapshot,
    summarize_display_stability,
)
from abso.core.multimon_detector import (
    DisplayEnvironment,
    MonitorInfo,
    MultiMonitorResult,
    MultiMonitorWarning,
)


class FakeDetector:
    def __init__(self, result: MultiMonitorResult | Exception):
        self._result = result

    def detect(self) -> MultiMonitorResult:
        if isinstance(self._result, Exception):
            raise self._result
        return self._result


def test_summarize_display_stability_flags_mixed_refresh_vrr_risk() -> None:
    result = MultiMonitorResult(
        environment=DisplayEnvironment(
            monitors=[
                MonitorInfo(
                    name="Primary 300Hz",
                    width=2560,
                    height=1440,
                    refresh_rate=300.0,
                    is_primary=True,
                    is_vrr_capable=True,
                ),
                MonitorInfo(
                    name="Secondary 60Hz",
                    width=2560,
                    height=1440,
                    refresh_rate=60.0,
                    is_primary=False,
                    max_refresh_rate=144.0,
                ),
            ],
            monitor_count=2,
            has_mixed_refresh=True,
            has_mixed_resolution=False,
            primary_refresh=300.0,
            min_refresh=60.0,
            max_refresh=300.0,
            detected_overlays=["OBS Studio"],
        ),
        exclusive_fullscreen_safe=False,
        warnings=[
            MultiMonitorWarning(
                code="MULTIMON_MPO_GLITCH_RISK",
                message="MPO glitch risk: VRR/G-Sync active, mixed refresh",
                recommendation="Reboot after MPO target is written.",
            )
        ],
    )

    summary = summarize_display_stability(result)

    assert summary["risk_level"] == "high"
    assert summary["likely_black_flash_path"] == "windows_compositor_mpo_vrr_mixed_refresh"
    assert summary["risk_factors"] == [
        "multi_monitor",
        "mixed_refresh",
        "vrr_capable_display",
        "monitor_below_refresh_capability",
        "active_overlay_process",
    ]
    assert summary["monitors"][0]["name"] == "Primary 300Hz"
    assert summary["monitors"][1]["max_refresh_rate"] == 144.0
    assert summary["monitors"][1]["refresh_headroom_hz"] == 84.0
    assert summary["warnings"][0]["code"] == "MULTIMON_MPO_GLITCH_RISK"


def test_collect_display_stability_snapshot_is_best_effort() -> None:
    snapshot = collect_display_stability_snapshot(
        detector=FakeDetector(RuntimeError("display probe failed"))
    )

    assert snapshot == {
        "supported": False,
        "query_scope": "multimon_detector_read_only",
        "error": "display probe failed",
    }


def test_collect_display_stability_snapshot_marks_supported_payload() -> None:
    result = MultiMonitorResult(
        environment=DisplayEnvironment(
            monitors=[
                MonitorInfo(
                    name="Primary",
                    width=1920,
                    height=1080,
                    refresh_rate=60.0,
                    is_primary=True,
                )
            ],
            monitor_count=1,
            primary_refresh=60.0,
            min_refresh=60.0,
            max_refresh=60.0,
        )
    )

    snapshot = collect_display_stability_snapshot(detector=FakeDetector(result))

    assert snapshot["supported"] is True
    assert snapshot["query_scope"] == "multimon_detector_read_only"
    assert snapshot["risk_level"] == "low"
    assert snapshot["risk_factors"] == []


def test_single_vrr_display_is_context_not_health_warning_risk() -> None:
    result = MultiMonitorResult(
        environment=DisplayEnvironment(
            monitors=[
                MonitorInfo(
                    name="Primary VRR",
                    width=2560,
                    height=1440,
                    refresh_rate=300.0,
                    is_primary=True,
                    is_vrr_capable=True,
                    vrr_type="gsync_compatible",
                )
            ],
            monitor_count=1,
            primary_refresh=300.0,
            min_refresh=300.0,
            max_refresh=300.0,
        ),
        exclusive_fullscreen_safe=True,
        warnings=[],
    )

    summary = summarize_display_stability(result)

    assert summary["risk_factors"] == ["vrr_capable_display"]
    assert summary["risk_level"] == "low"
    assert summary["likely_black_flash_path"] is None
    assert summary["warnings"] == []
