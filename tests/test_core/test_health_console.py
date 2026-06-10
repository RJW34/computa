"""Tests for human-readable health output helpers."""

from __future__ import annotations

from abso.core.display_diagnostics import (
    ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
    ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
    ACTION_REVIEW_SECONDARY_REFRESH_RATE,
)
from abso.core.health_console import (
    build_active_state_context_lines,
    build_display_context_lines,
    build_display_context_lines_from_payload,
    build_display_diagnostic_report_lines,
    build_health_check_lines,
    format_hz,
)


def test_format_hz_trims_fractional_rates() -> None:
    assert format_hz(300.0) == "300 Hz"
    assert format_hz(59.95) == "59.95 Hz"
    assert format_hz("bad") == "unknown"


def test_build_health_check_lines_lists_known_and_extra_checks_with_details() -> None:
    lines = build_health_check_lines(
        {
            "display_stability": {
                "status": "warning",
                "warnings": ["display topology has high compositor black-flash risk"],
            },
            "custom_probe": {"status": "error", "error": "custom probe failed"},
            "tray_runtime": {"status": "ok"},
        }
    )

    assert lines == [
        "  [green]tray_runtime: ok[/green]",
        "  [yellow]display_stability: warning[/yellow]",
        "    [yellow]- display topology has high compositor black-flash risk[/yellow]",
        "  [red]custom_probe: error[/red]",
        "    [red]- custom probe failed[/red]",
    ]


def test_build_active_state_context_lines_summarizes_reboot_pending_state() -> None:
    lines = build_active_state_context_lines(
        {
            "current_profile": "overwatch2-gsync-hdr-capture",
            "reboot_pending": True,
            "reboot_reasons": ["GraphicsSettingsHandler"],
        }
    )

    assert lines == [
        "Active profile: overwatch2-gsync-hdr-capture",
        "Profile state: reboot pending (GraphicsSettingsHandler)",
    ]


def test_build_active_state_context_lines_handles_missing_state() -> None:
    assert build_active_state_context_lines(None) == []
    assert build_active_state_context_lines({"current_profile": None}) == [
        "Active profile: (none)",
        "Profile state: no reboot pending",
    ]


def test_build_display_diagnostic_report_lines_builds_complete_sample_body() -> None:
    lines = build_display_diagnostic_report_lines(
        {
            "generated_at": "2026-05-26T13:30:00",
            "active_state": {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            },
            "display_events": {"count": 0, "channel_error_count": 0},
            "display_stability": {
                "monitor_count": 2,
                "min_refresh": 59.95,
                "max_refresh": 300.0,
                "risk_level": "high",
                "likely_black_flash_path": (
                    "windows_compositor_mpo_vrr_mixed_refresh"
                ),
                "next_action": "Normal reboot required.",
            },
            "summary": {
                "compositor_black_flash_likely": True,
                "recommended_actions": [
                    {
                        "code": ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
                        "label": "Do not repeatedly reapply the active profile.",
                    }
                ],
            },
        }
    )

    assert lines == [
        "Generated: 2026-05-26T13:30:00",
        "Active profile: overwatch2-gsync-hdr-capture",
        "Profile state: reboot pending (GraphicsSettingsHandler)",
        "",
        "[bold]Display diagnostics:[/bold]",
        "  Event log: 0 recent display/driver/power event(s), 0 channel error(s)",
        "  Topology: 2 monitor(s), 59.95 Hz - 300 Hz, risk high",
        "  Likely black-flash path: windows_compositor_mpo_vrr_mixed_refresh",
        "  Next action: Normal reboot required.",
        (
            "[yellow]Interpretation: clean actionable event logs plus the "
            "display/profile evidence point at the Windows compositor/MPO/VRR "
            "path.[/yellow]"
        ),
        "[bold]Recommended actions:[/bold]",
        "  - Do not repeatedly reapply the active profile.",
    ]


def test_build_display_context_lines_splits_actionable_and_benign_events() -> None:
    lines = build_display_context_lines_from_payload(
        {
            "count": 5,
            "actionable_count": 0,
            "benign_count": 5,
            "channel_error_count": 0,
        },
        {},
    )

    assert lines == [
        "",
        "[bold]Display diagnostics:[/bold]",
        (
            "  Event log: 0 actionable display/driver/power event(s), "
            "5 benign event(s), 0 channel error(s)"
        ),
    ]


def test_build_display_context_lines_summarizes_black_flash_evidence() -> None:
    lines = build_display_context_lines(
        {
            "display_events": {
                "data": {
                    "count": 0,
                    "channel_error_count": 0,
                }
            },
            "display_stability": {
                "data": {
                    "monitor_count": 2,
                    "min_refresh": 59.95,
                    "max_refresh": 300.0,
                    "risk_level": "high",
                    "likely_black_flash_path": (
                        "windows_compositor_mpo_vrr_mixed_refresh"
                    ),
                    "warnings": [
                        {
                            "code": "MULTIMON_REFRESH_BELOW_CAPABILITY",
                            "message": (
                                "Dell S2719DGF(Displayport) is running at "
                                "59.95Hz below detected capability 144Hz"
                            ),
                        },
                        {
                            "code": "MULTIMON_MPO_GLITCH_RISK",
                            "message": (
                                "MPO glitch risk: VRR/G-Sync active, mixed refresh"
                            ),
                        },
                    ],
                    "next_action": (
                        "Normal reboot required before judging MPO/compositor "
                        "flicker fix."
                    ),
                    "recommended_actions": [
                        {"code": ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS},
                        {"code": ACTION_REVIEW_SECONDARY_REFRESH_RATE},
                        {"code": ACTION_AVOID_REDUNDANT_PROFILE_APPLY},
                    ],
                }
            },
        }
    )

    assert lines == [
        "",
        "[bold]Display diagnostics:[/bold]",
        "  Event log: 0 recent display/driver/power event(s), 0 channel error(s)",
        "  Topology: 2 monitor(s), 59.95 Hz - 300 Hz, risk high",
        "  Likely black-flash path: windows_compositor_mpo_vrr_mixed_refresh",
        (
            "  Display warning: Dell S2719DGF(Displayport) is running at "
            "59.95Hz below detected capability 144Hz"
        ),
        "  Display warning: MPO glitch risk: VRR/G-Sync active, mixed refresh",
        "  Next action: Normal reboot required before judging MPO/compositor flicker fix.",
        (
            f"  Recommended actions: {ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS}, "
            f"{ACTION_REVIEW_SECONDARY_REFRESH_RATE}, "
            f"{ACTION_AVOID_REDUNDANT_PROFILE_APPLY}"
        ),
    ]


def test_build_display_context_lines_handles_missing_checks() -> None:
    assert build_display_context_lines({}) == []


def test_build_display_context_lines_from_payload_skips_empty_payloads() -> None:
    assert build_display_context_lines_from_payload({}, {}) == []
