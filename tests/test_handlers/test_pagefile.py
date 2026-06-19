"""Tests for PagefileHandler — acknowledgement gating + hermetic CIM access.

Every test mocks the injectable ``_run_ps`` seam (or the higher-level write
helpers) so no real powershell / WMI / CIM call is ever made and the live
pagefile is never touched.
"""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

from abso.core.models import Issue
from abso.settings.pagefile import (
    ACK_KEY,
    PagefileHandler,
    _recommended_sizes,
)

# ----------------------------------------------------------------------
# Pure sizing helper
# ----------------------------------------------------------------------


@pytest.mark.parametrize(
    ("ram_gb", "expected_initial", "expected_maximum"),
    [
        (8, 12288, 16384),  # 1.5x / 2x, under the cap
        (16, 24576, 32768),  # 2x hits the 32 GB cap exactly
        (32, 32768, 32768),  # both clamped: max capped, initial floored to cap
        (64, 32768, 32768),  # huge RAM stays capped at 32 GB
    ],
)
def test_recommended_sizes_rule_and_cap(
    ram_gb: float, expected_initial: int, expected_maximum: int
) -> None:
    sizes = _recommended_sizes(ram_gb)
    assert sizes["initial_mb"] == expected_initial
    assert sizes["maximum_mb"] == expected_maximum
    # Cap invariant: max never exceeds 32 GB and initial never exceeds max.
    assert sizes["maximum_mb"] <= 32768
    assert sizes["initial_mb"] <= sizes["maximum_mb"]


def test_recommended_sizes_unknown_ram_falls_back_safely() -> None:
    for bad in (None, 0, -4):
        sizes = _recommended_sizes(bad)  # type: ignore[arg-type]
        assert sizes == {"initial_mb": 4096, "maximum_mb": 8192}


# ----------------------------------------------------------------------
# detect()
# ----------------------------------------------------------------------


def _ps_responder(*, auto: bool, ram_bytes: int, pagefiles: object) -> object:
    """Build a fake _run_ps that routes by the script content."""

    def fake(script: str) -> str:
        if "Win32_ComputerSystem" in script and "AutomaticManagedPagefile" in script:
            return json.dumps({"AutomaticManagedPagefile": auto})
        if "TotalPhysicalMemory" in script:
            return str(ram_bytes)
        if "Win32_PageFileSetting" in script:
            return json.dumps(pagefiles)
        return ""

    return fake


def test_detect_parses_state() -> None:
    handler = PagefileHandler()
    responder = _ps_responder(
        auto=True,
        ram_bytes=16 * 1024**3,
        pagefiles={"Name": "C:\\pagefile.sys", "InitialSize": 0, "MaximumSize": 0},
    )
    with patch.object(PagefileHandler, "_run_ps", side_effect=responder):
        state = handler.detect()

    assert state["automatic_managed"] is True
    assert state["total_ram_gb"] == 16.0
    # A single CIM object is normalised into a one-element list.
    assert isinstance(state["pagefiles"], list)
    assert state["pagefiles"][0]["Name"] == "C:\\pagefile.sys"


def test_detect_handles_unknown_state() -> None:
    handler = PagefileHandler()
    with patch.object(PagefileHandler, "_run_ps", return_value=""):
        state = handler.detect()
    assert state["automatic_managed"] is None
    assert state["pagefiles"] == []
    assert state["total_ram_gb"] is None


# ----------------------------------------------------------------------
# audit()
# ----------------------------------------------------------------------


def test_audit_emits_single_info_issue_when_auto_managed() -> None:
    handler = PagefileHandler()
    responder = _ps_responder(auto=True, ram_bytes=16 * 1024**3, pagefiles=[])
    with patch.object(PagefileHandler, "_run_ps", side_effect=responder):
        issues = handler.audit()

    assert len(issues) == 1
    issue = issues[0]
    assert isinstance(issue, Issue)
    assert issue.severity == "info"  # never warning
    assert issue.category == "memory"
    assert "opt-in" in issue.optimal_value.lower()


def test_audit_silent_when_not_auto_managed() -> None:
    handler = PagefileHandler()
    responder = _ps_responder(auto=False, ram_bytes=16 * 1024**3, pagefiles=[])
    with patch.object(PagefileHandler, "_run_ps", side_effect=responder):
        issues = handler.audit()
    assert issues == []


# ----------------------------------------------------------------------
# apply() — acknowledgement gate
# ----------------------------------------------------------------------


def test_apply_refuses_without_acknowledgement() -> None:
    """Missing acknowledgement returns success=False and mutates nothing."""
    handler = PagefileHandler()
    with (
        patch.object(PagefileHandler, "_set_automatic_managed") as set_auto,
        patch.object(PagefileHandler, "_set_fixed_pagefile") as set_fixed,
    ):
        result = handler.apply({})

    assert result["success"] is False
    assert result["requires_reboot"] is False
    assert "acknowledge_pagefile_change=True" in result["error"]
    set_auto.assert_not_called()
    set_fixed.assert_not_called()


def test_apply_rejects_truthy_non_true_ack() -> None:
    """Only the literal boolean True opens the gate."""
    handler = PagefileHandler()
    for sneaky in ("true", 1, "yes", [True]):
        with (
            patch.object(PagefileHandler, "_set_automatic_managed") as set_auto,
            patch.object(PagefileHandler, "_set_fixed_pagefile") as set_fixed,
        ):
            result = handler.apply({ACK_KEY: sneaky})
        assert result["success"] is False, f"{sneaky!r} should be refused"
        set_auto.assert_not_called()
        set_fixed.assert_not_called()


def test_apply_with_acknowledgement_pins_fixed_pagefile() -> None:
    """Explicit opt-in disables auto management and pins computed sizes."""
    handler = PagefileHandler()
    with (
        patch.object(PagefileHandler, "_read_total_ram_gb", return_value=16.0),
        patch.object(PagefileHandler, "_set_automatic_managed") as set_auto,
        patch.object(PagefileHandler, "_set_fixed_pagefile") as set_fixed,
    ):
        result = handler.apply({ACK_KEY: True})

    assert result["success"] is True
    assert result["requires_reboot"] is True
    assert result["initial_mb"] == 24576
    assert result["maximum_mb"] == 32768
    set_auto.assert_called_once_with(False)
    set_fixed.assert_called_once_with(24576, 32768)


def test_apply_reports_failure_when_write_raises() -> None:
    handler = PagefileHandler()
    with (
        patch.object(PagefileHandler, "_read_total_ram_gb", return_value=16.0),
        patch.object(
            PagefileHandler, "_set_automatic_managed", side_effect=OSError("boom")
        ),
        patch.object(PagefileHandler, "_set_fixed_pagefile"),
    ):
        result = handler.apply({ACK_KEY: True})
    assert result["success"] is False
    assert "boom" in result["error"]
    # Reboot is still required for whatever did get written.
    assert result["requires_reboot"] is True


# ----------------------------------------------------------------------
# backup() / restore()
# ----------------------------------------------------------------------


def test_backup_captures_state() -> None:
    handler = PagefileHandler()
    responder = _ps_responder(
        auto=False,
        ram_bytes=16 * 1024**3,
        pagefiles={"Name": "C:\\pagefile.sys", "InitialSize": 4096, "MaximumSize": 8192},
    )
    with patch.object(PagefileHandler, "_run_ps", side_effect=responder):
        data = handler.backup()
    assert data["automatic_managed"] is False
    assert data["pagefiles"][0]["InitialSize"] == 4096


def test_restore_reenables_automatic_management() -> None:
    handler = PagefileHandler()
    with (
        patch.object(PagefileHandler, "_set_automatic_managed") as set_auto,
        patch.object(PagefileHandler, "_set_fixed_pagefile") as set_fixed,
    ):
        ok = handler.restore({"automatic_managed": True, "pagefiles": []})
    assert ok is True
    set_auto.assert_called_once_with(True)
    set_fixed.assert_not_called()


def test_restore_repins_captured_fixed_sizes() -> None:
    handler = PagefileHandler()
    with (
        patch.object(PagefileHandler, "_set_automatic_managed") as set_auto,
        patch.object(PagefileHandler, "_set_fixed_pagefile") as set_fixed,
    ):
        ok = handler.restore(
            {
                "automatic_managed": False,
                "pagefiles": [
                    {"Name": "C:\\pagefile.sys", "InitialSize": 4096, "MaximumSize": 8192}
                ],
            }
        )
    assert ok is True
    set_auto.assert_called_once_with(False)
    set_fixed.assert_called_once_with(4096, 8192, name="C:\\pagefile.sys")


def test_restore_is_non_fatal_on_error() -> None:
    handler = PagefileHandler()
    with patch.object(
        PagefileHandler, "_set_automatic_managed", side_effect=OSError("nope")
    ):
        ok = handler.restore({"automatic_managed": True})
    assert ok is False


# ----------------------------------------------------------------------
# verify_active() — reboot-gated
# ----------------------------------------------------------------------


def test_verify_active_noop_without_acknowledgement() -> None:
    handler = PagefileHandler()
    with patch.object(PagefileHandler, "_run_ps", return_value="") as run_ps:
        result = handler.verify_active({})
    assert result == {"all_active": True, "settings": {}}
    run_ps.assert_not_called()


def test_verify_active_passes_when_fixed_pagefile_present() -> None:
    handler = PagefileHandler()
    responder = _ps_responder(
        auto=False,
        ram_bytes=16 * 1024**3,
        pagefiles={
            "Name": "C:\\pagefile.sys",
            "InitialSize": 24576,
            "MaximumSize": 32768,
        },
    )
    with patch.object(PagefileHandler, "_run_ps", side_effect=responder):
        result = handler.verify_active({ACK_KEY: True})
    assert result["all_active"] is True
    assert result["settings"]["automatic_managed"]["active"] is True
    assert result["settings"]["fixed_pagefile"]["active"] is True


def test_verify_active_fails_when_still_auto_managed() -> None:
    handler = PagefileHandler()
    responder = _ps_responder(auto=True, ram_bytes=16 * 1024**3, pagefiles=[])
    with patch.object(PagefileHandler, "_run_ps", side_effect=responder):
        result = handler.verify_active({ACK_KEY: True})
    assert result["all_active"] is False
    assert result["settings"]["automatic_managed"]["active"] is False


# ----------------------------------------------------------------------
# Handler metadata
# ----------------------------------------------------------------------


def test_handler_metadata_contract() -> None:
    handler = PagefileHandler()
    # Aggressive, reboot-gated, opt-in: must not escalate verify mismatches.
    assert handler.is_critical_verify is False
    # Restore is best-effort across reboots.
    assert handler.restore_guarantee == "partial"
