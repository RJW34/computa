"""Display-pipeline recovery after HDR-affecting apply steps.

Windows exposes several adjacent display APIs, but they do not all do the
same job:

* ``SetDisplayConfig(SDC_APPLY | SDC_USE_DATABASE_CURRENT)`` re-applies the
  saved topology/database. This is enough for ABSO's 25H2 ``SET_HDR_STATE``
  registry-intent recovery, but it did not clear the washed-out color pipeline
  observed on Insider build 29591.
* ``ChangeDisplaySettingsExW(NULL, NULL, NULL, CDS_RESET, NULL)`` asks the
  display stack to apply the current registry mode even when it is unchanged.
  Keep it available as a diagnostic/manual strategy.
* ``Win+Ctrl+Shift+B`` is Microsoft's documented user-facing graphics-driver
  reset shortcut. On build 29591 the physical shortcut, sent twice, was the
  working baseline for restoring vivid color. ABSO keeps this as an explicit
  manual strategy only because it can blank attached displays for a second or
  two. ABSO uses ``SendInput`` rather than the superseded ``keybd_event`` API,
  and marks ``VK_LWIN`` as an extended key so the system sees the real
  Windows-logo key chord.
"""

from __future__ import annotations

import ctypes
import logging
import time
from typing import Any, Literal

logger = logging.getLogger(__name__)

DisplayResetMethod = Literal[
    "auto",
    "database",
    "mode-reset",
    "driver-hotkey",
]


# SetDisplayConfig flags (winuser.h). This re-applies the currently saved
# display configuration from the persistence database.
_SDC_TOPOLOGY_INTERNAL = 0x00000001
_SDC_TOPOLOGY_CLONE = 0x00000002
_SDC_TOPOLOGY_EXTEND = 0x00000004
_SDC_TOPOLOGY_EXTERNAL = 0x00000008
_SDC_USE_DATABASE_CURRENT = (
    _SDC_TOPOLOGY_INTERNAL
    | _SDC_TOPOLOGY_CLONE
    | _SDC_TOPOLOGY_EXTEND
    | _SDC_TOPOLOGY_EXTERNAL
)
_SDC_APPLY = 0x00000080

# ChangeDisplaySettingsExW flags/status.
_CDS_RESET = 0x40000000
_DISP_CHANGE_SUCCESSFUL = 0

# SendInput / keyboard constants.
_INPUT_KEYBOARD = 1
_KEYEVENTF_EXTENDEDKEY = 0x0001
_KEYEVENTF_KEYUP = 0x0002
_VK_CONTROL = 0x11
_VK_SHIFT = 0x10
_VK_LWIN = 0x5B
_VK_B = 0x42

# Waits around display recovery. The pre-wait lets preceding HDR/color writes
# settle into MonitorDataStore / driver state before the recovery fires.
DEFAULT_SETTLE_S = 1.0
DEFAULT_POST_KICK_S = 0.5
DEFAULT_HOTKEY_REPEAT = 2
DEFAULT_HOTKEY_INTERVAL_S = 1.75

_ULONG_PTR = ctypes.c_ulonglong if ctypes.sizeof(ctypes.c_void_p) == 8 else ctypes.c_ulong


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = [
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = [
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", _ULONG_PTR),
    ]


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = [
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    ]


class _INPUT_UNION(ctypes.Union):
    _fields_ = [
        ("mi", _MOUSEINPUT),
        ("ki", _KEYBDINPUT),
        ("hi", _HARDWAREINPUT),
    ]


class _INPUT(ctypes.Structure):
    _anonymous_ = ("u",)
    _fields_ = [
        ("type", ctypes.c_ulong),
        ("u", _INPUT_UNION),
    ]


def _keyboard_input(vk: int, *, key_up: bool = False, extended: bool = False) -> _INPUT:
    flags = 0
    if extended:
        flags |= _KEYEVENTF_EXTENDEDKEY
    if key_up:
        flags |= _KEYEVENTF_KEYUP
    return _INPUT(
        type=_INPUT_KEYBOARD,
        ki=_KEYBDINPUT(
            wVk=vk,
            wScan=0,
            dwFlags=flags,
            time=0,
            dwExtraInfo=0,
        ),
    )


def _build_driver_reset_hotkey_inputs() -> list[_INPUT]:
    """Build Win+Ctrl+Shift+B press/release events for ``SendInput``."""
    return [
        _keyboard_input(_VK_LWIN, extended=True),
        _keyboard_input(_VK_CONTROL),
        _keyboard_input(_VK_SHIFT),
        _keyboard_input(_VK_B),
        _keyboard_input(_VK_B, key_up=True),
        _keyboard_input(_VK_SHIFT, key_up=True),
        _keyboard_input(_VK_CONTROL, key_up=True),
        _keyboard_input(_VK_LWIN, key_up=True, extended=True),
    ]


def _send_inputs(inputs: list[_INPUT]) -> tuple[int, int | None]:
    """Send INPUT records and return (events_sent, last_error)."""
    if not inputs:
        return 0, None

    input_array_type = _INPUT * len(inputs)
    input_array = input_array_type(*inputs)
    sent = ctypes.windll.user32.SendInput(
        len(input_array),
        input_array,
        ctypes.sizeof(_INPUT),
    )
    sent_int = int(sent)
    last_error = None
    if sent_int != len(inputs):
        try:
            last_error = int(ctypes.windll.kernel32.GetLastError())
        except Exception:
            last_error = None
    return sent_int, last_error


def _run_database_reapply(post_kick_s: float) -> dict[str, Any]:
    """Run ``SetDisplayConfig(..., SDC_APPLY | SDC_USE_DATABASE_CURRENT)``."""
    try:
        status = ctypes.windll.user32.SetDisplayConfig(
            0,
            None,
            0,
            None,
            _SDC_APPLY | _SDC_USE_DATABASE_CURRENT,
        )
    except (OSError, AttributeError) as exc:
        logger.error("SetDisplayConfig database reapply raised: %s", exc)
        return {
            "name": "database",
            "success": False,
            "status": None,
            "error": f"SetDisplayConfig raised: {exc}",
        }

    if post_kick_s > 0:
        time.sleep(post_kick_s)

    if int(status) != 0:
        logger.warning("SetDisplayConfig database reapply returned status %s", status)
        return {
            "name": "database",
            "success": False,
            "status": int(status),
            "error": f"SetDisplayConfig returned status {status}",
        }

    return {
        "name": "database",
        "success": True,
        "status": 0,
        "error": None,
    }


def _run_mode_reset(post_kick_s: float) -> dict[str, Any]:
    """Run ``ChangeDisplaySettingsExW(NULL, NULL, NULL, CDS_RESET, NULL)``."""
    try:
        status = ctypes.windll.user32.ChangeDisplaySettingsExW(
            None,
            None,
            None,
            _CDS_RESET,
            None,
        )
    except (OSError, AttributeError) as exc:
        logger.error("ChangeDisplaySettingsExW mode reset raised: %s", exc)
        return {
            "name": "mode-reset",
            "success": False,
            "status": None,
            "error": f"ChangeDisplaySettingsExW raised: {exc}",
        }

    if post_kick_s > 0:
        time.sleep(post_kick_s)

    if int(status) != _DISP_CHANGE_SUCCESSFUL:
        logger.warning("ChangeDisplaySettingsExW mode reset returned status %s", status)
        return {
            "name": "mode-reset",
            "success": False,
            "status": int(status),
            "error": f"ChangeDisplaySettingsExW returned status {status}",
        }

    return {
        "name": "mode-reset",
        "success": True,
        "status": 0,
        "error": None,
    }


def _run_driver_hotkey(
    repeat: int,
    interval_s: float,
    post_kick_s: float,
) -> dict[str, Any]:
    """Send the documented graphics-driver reset hotkey via ``SendInput``."""
    repeat = max(1, int(repeat))
    total_sent = 0
    expected_per_combo = len(_build_driver_reset_hotkey_inputs())
    errors: list[str] = []

    for index in range(repeat):
        inputs = _build_driver_reset_hotkey_inputs()
        sent, last_error = _send_inputs(inputs)
        total_sent += sent
        if sent != len(inputs):
            detail = (
                f"combo {index + 1}: SendInput inserted {sent}/{len(inputs)} events"
            )
            if last_error is not None:
                detail += f" (GetLastError={last_error})"
            errors.append(detail)
            break

        if index < repeat - 1 and interval_s > 0:
            time.sleep(interval_s)

    if post_kick_s > 0:
        time.sleep(post_kick_s)

    if errors:
        return {
            "name": "driver-hotkey",
            "success": False,
            "status": None,
            "error": "; ".join(errors),
            "sent_count": total_sent // expected_per_combo,
            "sent_events": total_sent,
            "expected_events": expected_per_combo * repeat,
        }

    return {
        "name": "driver-hotkey",
        "success": True,
        "status": 0,
        "error": None,
        "sent_count": repeat,
        "sent_events": total_sent,
        "expected_events": expected_per_combo * repeat,
    }


def _select_auto_method() -> tuple[str, dict[str, Any]]:
    """Pick the least disruptive automatic display recovery method.

    The driver-hotkey path is intentionally excluded from ``auto``. It fixes
    stale color state on some Insider builds, but it is disruptive enough to
    require explicit user intent via ``method="driver-hotkey"``.
    """
    try:
        from abso.utils.os_release import detect_os_release

        release = detect_os_release()
        release_info = release.to_dict()
        if release.is_experimental_future_platform:
            release_info["auto_driver_hotkey_suppressed"] = True
            release_info["suppressed_reason"] = (
                "driver-hotkey can briefly blank attached displays; "
                "use method='driver-hotkey' explicitly when needed"
            )
        return "database", release_info
    except Exception as exc:  # noqa: BLE001 - recovery must stay best-effort
        logger.debug("Could not detect OS release for display reset method: %s", exc)
        return "database", {"error": str(exc)}


def refresh_display_pipeline(
    settle_before_s: float = DEFAULT_SETTLE_S,
    post_kick_s: float = DEFAULT_POST_KICK_S,
    *,
    method: DisplayResetMethod = "auto",
    hotkey_repeat: int = DEFAULT_HOTKEY_REPEAT,
    hotkey_interval_s: float = DEFAULT_HOTKEY_INTERVAL_S,
) -> dict[str, Any]:
    """Recover the DWM / graphics-driver display pipeline.

    Args:
        settle_before_s: Pause before recovery so preceding HDR/color writes
            flush to the driver and MonitorDataStore.
        post_kick_s: Pause after the selected recovery step.
        method: ``auto`` chooses the least disruptive ``database`` path.
            Explicit values force one path, including the disruptive
            ``driver-hotkey`` strategy.
        hotkey_repeat: Number of Win+Ctrl+Shift+B chords for ``driver-hotkey``.
        hotkey_interval_s: Delay between repeated hotkey chords.

    Returns:
        JSON-safe dict with ``success``, ``method``, ``status``, ``error``,
        ``elapsed_seconds``, and method-specific details such as
        ``sent_count`` for the hotkey path.
    """
    start = time.monotonic()
    selected_method = str(method)
    os_release: dict[str, Any] | None = None

    if method == "auto":
        selected_method, os_release = _select_auto_method()

    if settle_before_s > 0:
        logger.info(
            "Letting display state settle %.1fs before %s display recovery",
            settle_before_s,
            selected_method,
        )
        time.sleep(settle_before_s)

    if selected_method == "database":
        step = _run_database_reapply(post_kick_s)
    elif selected_method == "mode-reset":
        step = _run_mode_reset(post_kick_s)
    elif selected_method == "driver-hotkey":
        step = _run_driver_hotkey(hotkey_repeat, hotkey_interval_s, post_kick_s)
    else:
        step = {
            "name": selected_method,
            "success": False,
            "status": None,
            "error": f"Unknown display reset method: {selected_method}",
        }

    elapsed = time.monotonic() - start
    outcome: dict[str, Any] = {
        "success": bool(step.get("success")),
        "method": selected_method,
        "requested_method": method,
        "status": step.get("status"),
        "error": step.get("error"),
        "elapsed_seconds": elapsed,
        "steps": [step],
    }
    if os_release is not None:
        outcome["os_release"] = os_release
    for key in ("sent_count", "sent_events", "expected_events"):
        if key in step:
            outcome[key] = step[key]
    return outcome


def is_available() -> bool:
    """Whether at least one display recovery entry point exists."""
    try:
        user32 = ctypes.windll.user32
        return any(
            hasattr(user32, attr)
            for attr in ("SetDisplayConfig", "ChangeDisplaySettingsExW", "SendInput")
        )
    except (AttributeError, OSError):
        return False
