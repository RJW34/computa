"""Monitor Adaptive Sync control via DDC/CI.

Toggles the monitor's firmware Adaptive Sync (FreeSync/VRR) setting using
the DDC/CI protocol over the display connection. This is required for
G-SYNC Compatible to work — the NVIDIA driver can only engage VRR when
the monitor's firmware has Adaptive Sync enabled.

The VCP codes used are manufacturer-specific and not part of the MCCS
standard. Currently supported: CVTE-based controllers (common in Dell,
and other monitors) using VCP 0xE6 + 0xF8 combo.
"""

from __future__ import annotations

import contextlib
import ctypes
import logging
import threading
import time
from ctypes import Structure, byref, wintypes
from typing import Any

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# DDC/CI VCP codes for Adaptive Sync control (manufacturer-specific)
# ---------------------------------------------------------------------------

# CVTE controller boards: requires setting both 0xE6 and 0xF8 to enable,
# clearing 0xF8 to disable. 0xE6 acts as an "arm" signal, 0xF8 as the
# actual toggle.
ADAPTIVE_SYNC_VCP_PROFILES: dict[str, dict[str, Any]] = {
    "CVTE": {
        "enable_sequence": [(0xE6, 1), (0xF8, 1)],
        "disable_sequence": [(0xF8, 0)],
    },
}

# Default profile used when monitor controller model can't be identified.
DEFAULT_VCP_PROFILE = {
    "enable_sequence": [(0xE6, 1), (0xF8, 1)],
    "disable_sequence": [(0xF8, 0)],
}


class PHYSICAL_MONITOR(Structure):
    """Win32 PHYSICAL_MONITOR structure."""

    _fields_ = [
        ("hPhysicalMonitor", wintypes.HANDLE),
        ("szPhysicalMonitorDescription", wintypes.WCHAR * 128),
    ]


def _get_primary_physical_monitor() -> tuple[wintypes.HANDLE, str] | None:
    """Get the primary monitor's physical monitor handle and description.

    Returns:
        Tuple of (handle, description) or None if unavailable.
    """
    try:
        dxva2 = ctypes.windll.dxva2
        user32 = ctypes.windll.user32
    except OSError:
        logger.debug("dxva2.dll not available")
        return None

    try:
        h_monitor = user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
        count = wintypes.DWORD()
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(h_monitor, byref(count)):
            return None
        if count.value == 0:
            return None

        monitors = (PHYSICAL_MONITOR * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(h_monitor, count.value, monitors):
            return None

        return monitors[0].hPhysicalMonitor, monitors[0].szPhysicalMonitorDescription
    except Exception as e:
        logger.debug(f"Failed to get physical monitor: {e}")
        return None


def _detect_controller_model(h_physical: wintypes.HANDLE) -> str | None:
    """Detect monitor controller model from DDC/CI capabilities string.

    Returns:
        Model string (e.g. "CVTE") or None.
    """
    try:
        dxva2 = ctypes.windll.dxva2
        cap_len = wintypes.DWORD()
        if not dxva2.GetCapabilitiesStringLength(h_physical, byref(cap_len)):
            return None

        cap_buf = ctypes.create_string_buffer(cap_len.value + 1)
        if not dxva2.CapabilitiesRequestAndCapabilitiesReply(
            h_physical, cap_buf, cap_len.value + 1
        ):
            return None

        caps = cap_buf.value.decode("ascii", errors="replace")
        # Parse model(...) from capabilities string
        import re

        match = re.search(r"model\((\w+)\)", caps)
        return match.group(1) if match else None
    except Exception as e:
        logger.debug(f"Failed to read monitor capabilities: {e}")
        return None


def _set_vcp(
    h_physical: wintypes.HANDLE, code: int, value: int, timeout: float = 5.0,
) -> bool:
    """Set a VCP feature on the monitor with timeout.

    DDC/CI calls can hang if the monitor is mid-transition (e.g. after an
    HDR mode switch). A thread-based timeout prevents blocking the apply.
    """
    result_box: list[bool] = [False]

    def _do_set() -> None:
        try:
            result_box[0] = bool(
                ctypes.windll.dxva2.SetVCPFeature(h_physical, code, value)
            )
        except Exception:
            result_box[0] = False

    t = threading.Thread(target=_do_set, daemon=True)
    t.start()
    t.join(timeout=timeout)
    if t.is_alive():
        logger.warning(f"SetVCPFeature 0x{code:02X}={value} timed out after {timeout}s")
        return False
    return result_box[0]


def _destroy_physical_monitors(
    count: int, monitors: ctypes.Array[PHYSICAL_MONITOR],
) -> None:
    """Clean up physical monitor handles."""
    with contextlib.suppress(Exception):
        ctypes.windll.dxva2.DestroyPhysicalMonitors(count, monitors)


def _try_adaptive_sync_toggle(
    enable: bool, controller_override: str | None = None,
) -> dict[str, Any]:
    """Single attempt to toggle Adaptive Sync. Internal helper."""
    result: dict[str, Any] = {"success": False, "error": None}

    try:
        dxva2 = ctypes.windll.dxva2
        user32 = ctypes.windll.user32
    except OSError:
        result["error"] = "dxva2.dll not available"
        return result

    monitors = None
    count = wintypes.DWORD()

    try:
        h_monitor = user32.MonitorFromPoint(wintypes.POINT(0, 0), 1)
        if not dxva2.GetNumberOfPhysicalMonitorsFromHMONITOR(h_monitor, byref(count)):
            result["error"] = "Failed to enumerate physical monitors"
            return result

        if count.value == 0:
            result["error"] = "No physical monitors found"
            return result

        monitors = (PHYSICAL_MONITOR * count.value)()
        if not dxva2.GetPhysicalMonitorsFromHMONITOR(h_monitor, count.value, monitors):
            result["error"] = "Failed to get physical monitor handles"
            return result

        h_physical = monitors[0].hPhysicalMonitor

        # Detect controller model and select VCP profile
        model = controller_override or _detect_controller_model(h_physical)
        vcp_profile = ADAPTIVE_SYNC_VCP_PROFILES.get(model) if model else None

        if vcp_profile is None:
            result["error"] = (
                f"Unknown monitor controller: {model or 'undetected'}. "
                "Set ddci.controller_override in abso.yaml to your controller model "
                f"(supported: {', '.join(ADAPTIVE_SYNC_VCP_PROFILES.keys())})"
            )
            return result

        logger.info(
            f"Monitor controller: {model or 'unknown'}, "
            f"{'enabling' if enable else 'disabling'} Adaptive Sync"
        )

        # Execute the VCP sequence
        sequence = vcp_profile["enable_sequence" if enable else "disable_sequence"]
        for code, value in sequence:
            if not _set_vcp(h_physical, code, value):
                result["error"] = f"SetVCPFeature 0x{code:02X}={value} timed out or failed"
                return result

        result["success"] = True
        return result

    except Exception as e:
        result["error"] = str(e)
        return result
    finally:
        if monitors is not None:
            _destroy_physical_monitors(count.value, monitors)


def set_monitor_adaptive_sync(
    enable: bool,
    retries: int = 3,
    retry_delay: float = 3.0,
    controller_override: str | None = None,
) -> dict[str, Any]:
    """Toggle the primary monitor's Adaptive Sync via DDC/CI.

    Retries with a delay if the monitor is unresponsive (e.g. during an
    HDR mode switch the display briefly resets and DDC/CI hangs).

    Args:
        enable: True to enable Adaptive Sync, False to disable.
        retries: Number of attempts before giving up.
        retry_delay: Seconds to wait between retries.
        controller_override: Force a specific VCP profile (e.g., "CVTE").

    Returns:
        Dict with 'success' bool and optional 'error' string.
    """
    last_result: dict[str, Any] = {"success": False, "error": "No attempts made"}

    for attempt in range(retries):
        last_result = _try_adaptive_sync_toggle(enable, controller_override)
        if last_result["success"]:
            return last_result
        if attempt < retries - 1:
            logger.info(
                f"Monitor DDC/CI attempt {attempt + 1} failed, "
                f"retrying in {retry_delay}s..."
            )
            time.sleep(retry_delay)

    logger.warning(f"Monitor Adaptive Sync toggle failed after {retries} attempts")
    return last_result
