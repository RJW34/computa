"""Tests for compact profile verification status summaries."""

from __future__ import annotations

from datetime import datetime

import pytest

from abso.core.profile_status import (
    build_profile_verification_summary,
    format_manual_step,
    get_pending_manual_steps,
    summarize_profile_verification,
)


def test_summarize_profile_verification_reports_pending_apply_first() -> None:
    """Pending apply settings are the highest-action status for tray/GUI state."""
    summary = summarize_profile_verification(
        "overwatch2-gsync-hdr-capture",
        {
            "all_active": False,
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "pending_reboot_gated_settings": ["OtherHandler.setting"],
            "handlers": {
                "GraphicsSettingsHandler": {"all_active": False},
            },
        },
        checked_at=datetime(2026, 5, 26, 5, 50),
    )

    assert summary == {
        "checked_at": "2026-05-26T05:50:00",
        "profile": "overwatch2-gsync-hdr-capture",
        "all_active": False,
        "status": "pending_apply",
        "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
        "pending_reboot_gated_settings": ["OtherHandler.setting"],
        "mismatched_handlers": ["GraphicsSettingsHandler"],
        "manual_steps": [],
    }


def test_summarize_profile_verification_passes_through_manual_steps() -> None:
    """Non-blocking manual steps (e.g. OW2 Reflex) surface without changing status."""
    step = {
        "handler": "OW2ConfigHandler",
        "key": "reflex_mode",
        "satisfied": True,
        "expected": 2,
        "current": 2,
    }
    summary = summarize_profile_verification(
        "overwatch2-gsync-hdr",
        {"all_active": True, "handlers": {}, "manual_steps": [step]},
        checked_at=datetime(2026, 5, 26, 5, 50),
    )

    assert summary["status"] == "active"
    assert summary["all_active"] is True
    assert summary["manual_steps"] == [step]


@pytest.mark.parametrize("satisfied", [True, False, None])
def test_manual_setup_is_separate_from_machine_setting_status(satisfied) -> None:
    step = {"key": "reflex_mode", "satisfied": satisfied}
    summary = summarize_profile_verification(
        "overwatch2", {"all_active": True, "manual_steps": [step]},
    )
    assert summary["status"] == "active"
    assert summary["all_active"] is True
    assert summary["pending_apply_settings"] == []
    assert summary["pending_reboot_gated_settings"] == []
    assert get_pending_manual_steps(summary["manual_steps"]) == ([] if satisfied is True else [step])


def test_manual_step_description_explains_unknown_and_preserves_generic_instructions() -> None:
    step = {
        "label": "NVIDIA profile binding", "current_label": "unknown",
        "expected_label": "Overwatch 2", "instruction": "Check the executable in NPI.",
    }
    assert format_manual_step(step) == (
        "NVIDIA profile binding: current not yet verified; expected Overwatch 2. "
        "Check the executable in NPI."
    )
    assert get_pending_manual_steps([None, "invalid", step]) == [step]


def test_summarize_profile_verification_reports_pending_reboot() -> None:
    """Reboot-gated settings should remain visible when no write is pending."""
    summary = summarize_profile_verification(
        "overwatch2-gsync-hdr-capture",
        {
            "all_active": False,
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "handlers": {},
        },
        checked_at=datetime(2026, 5, 26, 5, 50),
    )

    assert summary["status"] == "pending_reboot"
    assert summary["pending_apply_settings"] == []
    assert summary["pending_reboot_gated_settings"] == [
        "GraphicsSettingsHandler.mpo_disabled"
    ]


def test_build_profile_verification_summary_surfaces_verify_errors() -> None:
    """State reads should still work even when live verification fails."""
    summary = build_profile_verification_summary(
        "overwatch2-gsync-hdr-capture",
        lambda _profile: (_ for _ in ()).throw(RuntimeError("verify failed")),
        now=lambda: datetime(2026, 5, 26, 5, 50),
    )

    assert summary["checked_at"] == "2026-05-26T05:50:00"
    assert summary["profile"] == "overwatch2-gsync-hdr-capture"
    assert summary["all_active"] is False
    assert summary["status"] == "error"
    assert summary["error"] == "verify failed"
