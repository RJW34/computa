"""Tests for read-only display diagnostics aggregation."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

from abso.core.display_diagnostics import (
    ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
    ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
    ACTION_REVIEW_CAPTURE_MPO_PERFORMANCE,
    ACTION_REVIEW_SECONDARY_REFRESH_RATE,
    GRAPHICS_REBOOT_NEXT_ACTION,
    build_active_state_context,
    build_recommended_actions,
    collect_active_state_context,
    collect_display_diagnostics,
    enrich_display_stability_with_active_state,
    iter_display_diagnostic_samples,
    summarize_display_diagnostics,
)


def test_summarize_display_diagnostics_marks_compositor_path_likely() -> None:
    summary = summarize_display_diagnostics(
        {"count": 0, "channel_error_count": 0},
        {
            "risk_level": "high",
            "likely_black_flash_path": "windows_compositor_mpo_vrr_mixed_refresh",
        },
    )

    assert summary == {
        "event_count": 0,
        "channel_error_count": 0,
        "risk_level": "high",
        "likely_black_flash_path": "windows_compositor_mpo_vrr_mixed_refresh",
        "clean_event_log": True,
        "compositor_black_flash_likely": True,
        "recommended_actions": [
            {
                "code": ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
                "label": (
                    "Do not repeatedly reapply the already-active profile to chase "
                    "black flashes; that can cause avoidable display/color resets."
                ),
                "source": "diagnostic_interpretation",
                "requires_user_action": False,
                "changes_display_state": False,
            }
        ],
    }


def test_summarize_display_diagnostics_does_not_hide_driver_events() -> None:
    summary = summarize_display_diagnostics(
        {"count": 1, "channel_error_count": 0},
        {
            "risk_level": "high",
            "likely_black_flash_path": "windows_compositor_mpo_vrr_mixed_refresh",
        },
    )

    assert summary["clean_event_log"] is False
    assert summary["compositor_black_flash_likely"] is False
    assert summary["recommended_actions"] == []


def test_collect_display_diagnostics_uses_read_only_collectors() -> None:
    event_payload = {"count": 0, "channel_error_count": 0}
    stability_payload = {
        "risk_level": "high",
        "likely_black_flash_path": "windows_compositor_mpo_vrr_mixed_refresh",
    }

    with (
        patch(
            "abso.core.display_diagnostics.collect_recent_display_events",
            return_value=event_payload,
        ) as mock_events,
        patch(
            "abso.core.display_diagnostics.collect_display_stability_snapshot",
            return_value=stability_payload,
        ) as mock_stability,
    ):
        payload = collect_display_diagnostics(
            lookback_minutes=45,
            max_events=7,
            event_timeout_seconds=3,
        )

    mock_events.assert_called_once_with(
        lookback_minutes=45,
        max_events=7,
        timeout_seconds=3,
    )
    mock_stability.assert_called_once_with()
    assert payload["read_only"] is True
    assert payload["display_events"] == event_payload
    assert payload["display_stability"] == stability_payload
    assert payload["active_state"] is None
    assert payload["summary"]["compositor_black_flash_likely"] is True


def test_collect_display_diagnostics_includes_reboot_pending_state(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T04:40:55",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )
    event_payload = {"count": 0, "channel_error_count": 0}
    stability_payload = {
        "risk_level": "high",
        "likely_black_flash_path": "windows_compositor_mpo_vrr_mixed_refresh",
    }

    with (
        patch(
            "abso.core.display_diagnostics.collect_recent_display_events",
            return_value=event_payload,
        ),
        patch(
            "abso.core.display_diagnostics.collect_display_stability_snapshot",
            return_value=stability_payload,
        ),
        patch(
            "abso.core.display_diagnostics.build_active_profile_display_context",
            return_value={
                "profile_id": "overwatch2-gsync-hdr-capture",
                "is_capture_safe": True,
                "graphics_disable_mpo": True,
                "ow2_window_mode": 1,
            },
        ),
    ):
        payload = collect_display_diagnostics(state_targets=[state_file])

    assert payload["active_state"] == {
        "current_profile": "overwatch2-gsync-hdr-capture",
        "applied_at": "2026-05-26T04:40:55",
        "reboot_pending": True,
        "reboot_reasons": ["GraphicsSettingsHandler"],
        "graphics_reboot_pending": True,
        "next_action": GRAPHICS_REBOOT_NEXT_ACTION,
        "profile_display_context": {
            "profile_id": "overwatch2-gsync-hdr-capture",
            "is_capture_safe": True,
            "graphics_disable_mpo": True,
            "ow2_window_mode": 1,
        },
    }
    assert payload["display_stability"]["graphics_reboot_pending"] is True
    assert payload["display_stability"]["next_action"] == GRAPHICS_REBOOT_NEXT_ACTION
    assert payload["summary"]["reboot_pending"] is True
    assert payload["summary"]["next_action"] == GRAPHICS_REBOOT_NEXT_ACTION
    assert payload["summary"]["recommended_actions"][0]["code"] == (
        ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS
    )


def test_build_recommended_actions_prioritizes_reboot_and_refresh_review() -> None:
    actions = build_recommended_actions(
        stability={
            "warnings": [
                {
                    "code": "MULTIMON_REFRESH_BELOW_CAPABILITY",
                    "message": (
                        "Dell S2719DGF(Displayport) is running at 59.95Hz "
                        "below detected capability 144Hz"
                    ),
                }
            ]
        },
        active_state={
            "graphics_reboot_pending": True,
            "next_action": GRAPHICS_REBOOT_NEXT_ACTION,
        },
        compositor_likely=True,
    )

    assert [action["code"] for action in actions] == [
        ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
        ACTION_REVIEW_SECONDARY_REFRESH_RATE,
        ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
    ]
    assert actions[1]["changes_display_state"] is True
    assert "59.95Hz" in actions[1]["label"]


def test_build_recommended_actions_flags_capture_mpo_performance_risk() -> None:
    actions = build_recommended_actions(
        stability={
            "risk_level": "high",
            "risk_factors": ["multi_monitor", "mixed_refresh"],
        },
        active_state={
            "graphics_reboot_pending": False,
            "profile_display_context": {
                "profile_id": "overwatch2-gsync-hdr-capture",
                "is_capture_safe": True,
                "graphics_disable_mpo": True,
                "ow2_window_mode": 1,
            },
        },
        compositor_likely=True,
    )

    assert [action["code"] for action in actions] == [
        ACTION_REVIEW_CAPTURE_MPO_PERFORMANCE,
        ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
    ]
    assert actions[0]["changes_display_state"] is True


def test_collect_active_state_context_handles_missing_state(tmp_path: Path) -> None:
    state = collect_active_state_context([tmp_path / "missing.json"])

    assert state["current_profile"] is None
    assert state["reboot_pending"] is False
    assert state["reboot_reasons"] == []
    assert state["graphics_reboot_pending"] is False
    assert state["next_action"] is None
    assert state["profile_display_context"] is None


def test_build_active_state_context_identifies_graphics_reboot_pending() -> None:
    with patch(
        "abso.core.display_diagnostics.build_active_profile_display_context",
        return_value={"profile_id": "overwatch2-gsync-hdr-capture"},
    ):
        state = build_active_state_context(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T04:40:55",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        )

    assert state["graphics_reboot_pending"] is True
    assert state["next_action"] == GRAPHICS_REBOOT_NEXT_ACTION
    assert state["profile_display_context"] == {
        "profile_id": "overwatch2-gsync-hdr-capture"
    }


def test_enrich_display_stability_with_active_state_does_not_clobber_next_action() -> None:
    enriched = enrich_display_stability_with_active_state(
        {"next_action": "existing action"},
        {
            "graphics_reboot_pending": True,
            "next_action": GRAPHICS_REBOOT_NEXT_ACTION,
        },
    )

    assert enriched == {
        "graphics_reboot_pending": True,
        "next_action": "existing action",
    }


def test_iter_display_diagnostic_samples_spaces_samples_without_trailing_sleep() -> None:
    calls: list[dict[str, object]] = []
    sleeps: list[float] = []

    def collector(**kwargs: object) -> dict[str, int]:
        calls.append(kwargs)
        return {"sample": len(calls)}

    samples = list(
        iter_display_diagnostic_samples(
            samples=3,
            interval_seconds=0.5,
            lookback_minutes=12,
            max_events=4,
            event_timeout_seconds=2,
            collector=collector,
            sleep_func=sleeps.append,
        )
    )

    assert samples == [{"sample": 1}, {"sample": 2}, {"sample": 3}]
    assert sleeps == [0.5, 0.5]
    assert calls == [
        {
            "lookback_minutes": 12,
            "max_events": 4,
            "event_timeout_seconds": 2,
            "state_targets": None,
        },
        {
            "lookback_minutes": 12,
            "max_events": 4,
            "event_timeout_seconds": 2,
            "state_targets": None,
        },
        {
            "lookback_minutes": 12,
            "max_events": 4,
            "event_timeout_seconds": 2,
            "state_targets": None,
        },
    ]
