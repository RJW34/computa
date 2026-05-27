"""Tests for the display-pipeline recovery utility.

The suite patches Win32 calls and helper senders so tests never actually
re-apply the display database or send Ctrl+Win+Shift+B to the host.
"""

from __future__ import annotations

from unittest.mock import patch

import abso.utils.display_reset as dr


def _patched_database_reapply(*, status: int = 0, raise_exc: Exception | None = None):
    """Run database recovery with SetDisplayConfig patched."""
    recorded: list[tuple] = []

    def fake(num_paths, paths, num_modes, modes, flags):
        recorded.append((int(num_paths), paths, int(num_modes), modes, int(flags)))
        if raise_exc is not None:
            raise raise_exc
        return status

    with (
        patch.object(dr.ctypes.windll.user32, "SetDisplayConfig", side_effect=fake),
        patch.object(dr.time, "sleep", return_value=None),
    ):
        outcome = dr.refresh_display_pipeline(
            settle_before_s=0.0,
            post_kick_s=0.0,
            method="database",
        )
    return outcome, recorded


def test_database_method_calls_setdisplayconfig_with_apply_database_current() -> None:
    """Happy path: database method fires SetDisplayConfig with the right flags."""
    outcome, calls = _patched_database_reapply(status=0)

    assert outcome["success"] is True
    assert outcome["method"] == "database"
    assert outcome["status"] == 0
    assert outcome["error"] is None

    assert len(calls) == 1
    num_paths, paths, num_modes, modes, flags = calls[0]
    assert num_paths == 0
    assert paths is None
    assert num_modes == 0
    assert modes is None

    expected = dr._SDC_APPLY | dr._SDC_USE_DATABASE_CURRENT
    assert flags == expected


def test_database_method_reports_nonzero_status_as_failure() -> None:
    """A non-zero SetDisplayConfig return code surfaces as a failure."""
    outcome, calls = _patched_database_reapply(status=87)

    assert outcome["success"] is False
    assert outcome["status"] == 87
    assert "status 87" in (outcome["error"] or "")
    assert len(calls) == 1


def test_database_method_reports_oserror() -> None:
    """OSError from SetDisplayConfig is caught and surfaced cleanly."""
    outcome, _ = _patched_database_reapply(raise_exc=OSError("simulated kernel failure"))

    assert outcome["success"] is False
    assert outcome["status"] is None
    assert "simulated kernel failure" in (outcome["error"] or "")


def test_mode_reset_method_calls_changedisplaysettingsex_with_cds_reset() -> None:
    """mode-reset uses ChangeDisplaySettingsExW(NULL, NULL, NULL, CDS_RESET, NULL)."""
    recorded: list[tuple] = []

    def fake(device, devmode, hwnd, flags, param):
        recorded.append((device, devmode, hwnd, int(flags), param))
        return dr._DISP_CHANGE_SUCCESSFUL

    with (
        patch.object(dr.ctypes.windll.user32, "ChangeDisplaySettingsExW", side_effect=fake),
        patch.object(dr.time, "sleep", return_value=None),
    ):
        outcome = dr.refresh_display_pipeline(
            settle_before_s=0.0,
            post_kick_s=0.0,
            method="mode-reset",
        )

    assert outcome["success"] is True
    assert outcome["method"] == "mode-reset"
    assert recorded == [(None, None, None, dr._CDS_RESET, None)]


def test_driver_hotkey_builds_ctrl_win_shift_b_with_extended_lwin() -> None:
    """The hotkey chord must send LWIN as an extended key on press and release."""
    inputs = dr._build_driver_reset_hotkey_inputs()

    assert len(inputs) == 8
    assert [item.ki.wVk for item in inputs] == [
        dr._VK_LWIN,
        dr._VK_CONTROL,
        dr._VK_SHIFT,
        dr._VK_B,
        dr._VK_B,
        dr._VK_SHIFT,
        dr._VK_CONTROL,
        dr._VK_LWIN,
    ]
    assert inputs[0].ki.dwFlags & dr._KEYEVENTF_EXTENDEDKEY
    assert inputs[-1].ki.dwFlags & dr._KEYEVENTF_EXTENDEDKEY
    assert inputs[-1].ki.dwFlags & dr._KEYEVENTF_KEYUP


def test_driver_hotkey_method_repeats_without_touching_real_keyboard() -> None:
    """driver-hotkey repeats the chord and reports combo count."""
    send_lengths: list[int] = []

    def fake_send(inputs):
        send_lengths.append(len(inputs))
        return len(inputs), None

    with (
        patch.object(dr, "_send_inputs", side_effect=fake_send),
        patch.object(dr.time, "sleep", return_value=None),
    ):
        outcome = dr.refresh_display_pipeline(
            settle_before_s=0.0,
            post_kick_s=0.0,
            method="driver-hotkey",
            hotkey_repeat=2,
        )

    assert outcome["success"] is True
    assert outcome["method"] == "driver-hotkey"
    assert outcome["sent_count"] == 2
    assert outcome["sent_events"] == 16
    assert send_lengths == [8, 8]


def test_driver_hotkey_method_reports_partial_send_failure() -> None:
    """A partial SendInput insert is a failed recovery outcome."""
    with (
        patch.object(dr, "_send_inputs", return_value=(4, 5)),
        patch.object(dr.time, "sleep", return_value=None),
    ):
        outcome = dr.refresh_display_pipeline(
            settle_before_s=0.0,
            post_kick_s=0.0,
            method="driver-hotkey",
            hotkey_repeat=1,
        )

    assert outcome["success"] is False
    assert outcome["method"] == "driver-hotkey"
    assert "4/8 events" in (outcome["error"] or "")
    assert "GetLastError=5" in (outcome["error"] or "")


def test_auto_method_uses_selected_strategy() -> None:
    """auto delegates to the OS-selected method and keeps release metadata."""
    with (
        patch.object(
            dr,
            "_select_auto_method",
            return_value=("driver-hotkey", {"build": 29595}),
        ),
        patch.object(
            dr,
            "_run_driver_hotkey",
            return_value={
                "name": "driver-hotkey",
                "success": True,
                "status": 0,
                "error": None,
                "sent_count": 2,
            },
        ),
        patch.object(dr.time, "sleep", return_value=None),
    ):
        outcome = dr.refresh_display_pipeline(
            settle_before_s=0.0,
            post_kick_s=0.0,
            method="auto",
        )

    assert outcome["success"] is True
    assert outcome["requested_method"] == "auto"
    assert outcome["method"] == "driver-hotkey"
    assert outcome["sent_count"] == 2
    assert outcome["os_release"] == {"build": 29595}


def test_auto_selector_does_not_choose_driver_hotkey_on_future_builds() -> None:
    """Automatic recovery must not pick the black-screen driver reset path."""

    class FutureRelease:
        is_experimental_future_platform = True

        def to_dict(self):
            return {"build": 29595}

    with patch("abso.utils.os_release.detect_os_release", return_value=FutureRelease()):
        method, release_info = dr._select_auto_method()

    assert method == "database"
    assert release_info["build"] == 29595
    assert release_info["auto_driver_hotkey_suppressed"] is True
    assert "driver-hotkey can briefly blank" in release_info["suppressed_reason"]


def test_is_available_on_windows_returns_true() -> None:
    """At least one display recovery API is available on Windows desktop sessions."""
    assert dr.is_available() is True
