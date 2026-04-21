"""Timer resolution settings handler.

Includes TimerSettingsHandler for one-shot apply/audit and
TimerResolutionGuard for holding a resolution while a game process runs.
"""

from __future__ import annotations

import ctypes
import json
import logging
import os
import subprocess
import time
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class TimerSettingsHandler(SettingsHandler):
    """Handles Windows timer resolution settings.

    IMPORTANT: Timer resolution is NOT the same as input/render latency.
    - Timer resolution = System scheduling granularity (thread wake precision)
    - Input latency = What Nvidia overlay shows (controlled by Reflex, frame queue, etc.)

    Windows default timer resolution is ~15.6ms (156250 in 100ns units).
    Setting it to 0.5-1ms improves:
    - Frame pacing consistency (less microstutter)
    - More precise sleep() calls in game loops
    - Tighter multimedia thread scheduling

    This does NOT directly reduce input latency. Most modern games automatically
    request higher timer resolution when running.

    Note: NtSetTimerResolution changes only persist while the calling process is
    alive. The apply() method here is therefore ephemeral -- the resolution reverts
    the moment the ABSO CLI exits.  For persistent resolution during a game session,
    use ``TimerResolutionGuard`` (defined below) or the companion service at
    ``abso.core.timer_guard_service``, which the tray app can spawn as a child
    process to hold the resolution for the lifetime of a game.
    """

    # Common timer resolutions in 100ns units
    RESOLUTION_DEFAULT = 156250  # 15.625ms (Windows default)
    RESOLUTION_1MS = 10000       # 1.0ms
    RESOLUTION_0_5MS = 5000      # 0.5ms (minimum on most systems)

    def __init__(self) -> None:
        """Initialize timer settings handler."""
        self._ntdll: ctypes.WinDLL | None = None
        self._original_resolution: int | None = None
        self._load_ntdll()

    @property
    def is_persistent(self) -> bool:
        """Whether timer resolution changes survive process exit.

        Always returns False. NtSetTimerResolution is per-process; when the
        calling process terminates, Windows drops the resolution request.
        Use ``TimerResolutionGuard`` or ``abso.core.timer_guard_service``
        to hold the resolution for the duration of a game session.
        """
        return False

    @property
    def restore_guarantee(self) -> str:
        """Timer resolution is ephemeral.

        NtSetTimerResolution requests evaporate when the requesting process
        exits, so by the time a restore runs there is no persistent state
        to put back. Declaring "ephemeral" here lets BackupManager report
        honest summaries instead of lying about a full-guarantee restore.
        """
        return "ephemeral"

    def _load_ntdll(self) -> bool:
        """Load ntdll.dll for timer resolution functions.

        Returns:
            True if ntdll was loaded successfully.
        """
        try:
            self._ntdll = ctypes.WinDLL('ntdll')
            return True
        except Exception as e:
            logger.error(f"Failed to load ntdll.dll: {e}")
            return False

    def _query_timer_resolution(self) -> tuple[int, int, int] | None:
        """Query current timer resolution.

        Returns:
            Tuple of (minimum, maximum, current) resolution in 100ns units,
            or None if query failed.
        """
        if not self._ntdll:
            return None

        try:
            minimum = ctypes.c_ulong()
            maximum = ctypes.c_ulong()
            current = ctypes.c_ulong()

            # NtQueryTimerResolution(MinimumResolution, MaximumResolution, CurrentResolution)
            status = self._ntdll.NtQueryTimerResolution(
                ctypes.byref(minimum),
                ctypes.byref(maximum),
                ctypes.byref(current)
            )

            if status == 0:  # STATUS_SUCCESS
                return (minimum.value, maximum.value, current.value)
            else:
                logger.warning(f"NtQueryTimerResolution returned status: {status}")
                return None

        except Exception as e:
            logger.error(f"Failed to query timer resolution: {e}")
            return None

    def _set_timer_resolution(self, resolution: int, enable: bool = True) -> int | None:
        """Set system timer resolution.

        Args:
            resolution: Desired resolution in 100ns units.
            enable: True to set resolution, False to release it.

        Returns:
            The actual resolution set, or None if failed.
        """
        if not self._ntdll:
            return None

        try:
            current = ctypes.c_ulong()

            # NtSetTimerResolution(DesiredResolution, SetResolution, CurrentResolution)
            status = self._ntdll.NtSetTimerResolution(
                ctypes.c_ulong(resolution),
                ctypes.c_bool(enable),
                ctypes.byref(current)
            )

            if status == 0:  # STATUS_SUCCESS
                return current.value
            else:
                logger.warning(f"NtSetTimerResolution returned status: {status}")
                return None

        except Exception as e:
            logger.error(f"Failed to set timer resolution: {e}")
            return None

    def _resolution_to_ms(self, resolution: int) -> float:
        """Convert 100ns units to milliseconds.

        Args:
            resolution: Resolution in 100ns units.

        Returns:
            Resolution in milliseconds.
        """
        return resolution / 10000.0

    def _ms_to_resolution(self, ms: float) -> int:
        """Convert milliseconds to 100ns units.

        Args:
            ms: Resolution in milliseconds.

        Returns:
            Resolution in 100ns units.
        """
        return int(ms * 10000)

    def detect(self) -> dict[str, Any]:
        """Detect current timer resolution settings.

        Returns:
            Dictionary with timer resolution info.
        """
        result: dict[str, Any] = {
            "available": self._ntdll is not None,
            "current_resolution_100ns": None,
            "current_resolution_ms": None,
            "minimum_resolution_100ns": None,
            "minimum_resolution_ms": None,
            "maximum_resolution_100ns": None,
            "maximum_resolution_ms": None,
            "is_optimized": False,
        }

        timer_info = self._query_timer_resolution()
        if timer_info:
            minimum, maximum, current = timer_info
            result["minimum_resolution_100ns"] = minimum
            result["minimum_resolution_ms"] = self._resolution_to_ms(minimum)
            result["maximum_resolution_100ns"] = maximum
            result["maximum_resolution_ms"] = self._resolution_to_ms(maximum)
            result["current_resolution_100ns"] = current
            result["current_resolution_ms"] = self._resolution_to_ms(current)
            # Consider optimized if <= 1ms
            result["is_optimized"] = current <= self.RESOLUTION_1MS

        return result

    def audit(self) -> list[Issue]:
        """Audit timer resolution for gaming optimization issues.

        Returns:
            List of issues found.
        """
        issues: list[Issue] = []

        if not self._ntdll:
            issues.append(Issue(
                title="Timer resolution API unavailable",
                severity="warning",
                current_value="ntdll.dll not loaded",
                optimal_value="ntdll.dll available",
                explanation="Cannot query or set timer resolution. This may indicate a restricted environment.",
                category="timer",
            ))
            return issues

        timer_info = self._query_timer_resolution()
        if not timer_info:
            issues.append(Issue(
                title="Unable to query timer resolution",
                severity="info",
                current_value="Unknown",
                optimal_value="Known",
                explanation="Could not query current timer resolution.",
                category="timer",
            ))
            return issues

        minimum, maximum, current = timer_info
        current_ms = self._resolution_to_ms(current)
        min_ms = self._resolution_to_ms(maximum)  # Note: "maximum" is the minimum allowed value

        if current > self.RESOLUTION_1MS:
            issues.append(Issue(
                title="Timer resolution at default",
                severity="info",
                current_value=f"{current_ms:.3f}ms",
                optimal_value=f"{min_ms:.3f}ms (0.5-1.0ms)",
                explanation=(
                    "Lower timer resolution improves frame pacing and scheduling precision. "
                    "Note: This is NOT input latency - most games set this automatically when running."
                ),
                category="timer",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply timer resolution settings.

        Args:
            settings: Dictionary with settings. Supported keys:
                - resolution_ms: Target resolution in milliseconds (e.g., 0.5, 1.0)
                - resolution_100ns: Target resolution in 100ns units

        Returns:
            Result dict with success status.
        """
        errors: list[str] = []

        if not self._ntdll:
            return {
                "success": False,
                "error": "ntdll.dll not available",
                "requires_reboot": False,
            }

        try:
            # Determine target resolution
            if "resolution_ms" in settings:
                target = self._ms_to_resolution(settings["resolution_ms"])
            elif "resolution_100ns" in settings:
                target = settings["resolution_100ns"]
            else:
                # Default to 0.5ms for gaming
                target = self.RESOLUTION_0_5MS

            # Store original resolution for potential restore
            timer_info = self._query_timer_resolution()
            if timer_info and self._original_resolution is None:
                self._original_resolution = timer_info[2]

            # Set the new resolution
            actual = self._set_timer_resolution(target, enable=True)
            if actual is None:
                errors.append("Failed to set timer resolution")
            else:
                logger.info(
                    f"Timer resolution set to {self._resolution_to_ms(actual):.3f}ms "
                    f"(requested: {self._resolution_to_ms(target):.3f}ms)"
                )

        except Exception as e:
            errors.append(str(e))
            logger.error(f"Failed to apply timer settings: {e}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
            "note": "Timer resolution only persists while ABSO is running",
        }

    def backup(self) -> dict[str, Any]:
        """Backup current timer resolution.

        Returns:
            Dictionary with current timer settings.
        """
        current = self.detect()
        return {
            "resolution_100ns": current.get("current_resolution_100ns"),
            "resolution_ms": current.get("current_resolution_ms"),
        }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore timer resolution from backup.

        Note: This releases the resolution request made by this process,
        allowing the system to return to default if no other process
        has requested a higher resolution.

        Args:
            data: Previously backed up timer settings.

        Returns:
            True if restore succeeded.
        """
        if not self._ntdll:
            logger.warning("Cannot restore timer resolution: ntdll not available")
            return False

        try:
            # Get the original resolution from backup or stored value
            original = data.get("resolution_100ns") or self._original_resolution

            if original:
                # Release our resolution request by setting enable=False
                # This allows the system to use a higher (slower) resolution
                # if no other process is requesting a lower one
                self._set_timer_resolution(original, enable=False)
                logger.info("Released timer resolution request")
                return True
            else:
                logger.warning("No original resolution to restore")
                return True

        except Exception as e:
            logger.error(f"Failed to restore timer resolution: {e}")
            return False

    def set_gaming_resolution(self, target_ms: float = 0.5) -> bool:
        """Convenience method to set gaming-optimized timer resolution.

        Args:
            target_ms: Target resolution in milliseconds. Default 0.5ms.

        Returns:
            True if resolution was set successfully.
        """
        result = self.apply({"resolution_ms": target_ms})
        return result.get("success", False)

    def release_resolution(self) -> bool:
        """Release any timer resolution request made by this handler.

        Returns:
            True if release succeeded.
        """
        return self.restore({})


# ---------------------------------------------------------------------------
# TimerResolutionGuard — holds resolution for the lifetime of a game process
# ---------------------------------------------------------------------------

_STATUS_FILE = Path(os.environ.get("TEMP", "/tmp")) / "abso_timer_guard.json"


class TimerResolutionGuard:
    """Context manager that holds an NtSetTimerResolution request alive.

    Because NtSetTimerResolution is per-process, the resolution reverts the
    instant the calling process exits.  This guard keeps the calling process
    alive (or a dedicated child process) so the resolution is held for as
    long as a game is running.

    Usage as a context manager::

        with TimerResolutionGuard(resolution_100ns=5000) as guard:
            guard.hold_for_process("game.exe")

    The guard also exposes a simple JSON status file at
    ``%TEMP%\\abso_timer_guard.json`` so the PowerShell tray app can read
    current state without needing a full IPC channel.
    """

    DEFAULT_POLL_INTERVAL: float = 5.0  # seconds
    DEFAULT_TIMEOUT: float = 8 * 60 * 60  # 8 hours in seconds

    def __init__(self, resolution_100ns: int = 5000) -> None:
        """Initialize the guard.

        Args:
            resolution_100ns: Desired timer resolution in 100-nanosecond units.
                Default 5000 (0.5 ms).
        """
        self._resolution_100ns = resolution_100ns
        self._ntdll: ctypes.WinDLL | None = None
        self._original_resolution: int | None = None
        self._active = False
        self._load_ntdll()

    # -- ntdll helpers (mirror the handler but self-contained) --------------

    def _load_ntdll(self) -> bool:
        """Load ntdll.dll for timer resolution functions."""
        try:
            self._ntdll = ctypes.WinDLL("ntdll")
            return True
        except Exception as e:
            logger.error("Failed to load ntdll.dll: %s", e)
            return False

    def _query_resolution(self) -> tuple[int, int, int] | None:
        """Return (min, max, current) in 100ns units, or None."""
        if not self._ntdll:
            return None
        try:
            lo = ctypes.c_ulong()
            hi = ctypes.c_ulong()
            cur = ctypes.c_ulong()
            status = self._ntdll.NtQueryTimerResolution(
                ctypes.byref(lo), ctypes.byref(hi), ctypes.byref(cur)
            )
            if status == 0:
                return (lo.value, hi.value, cur.value)
            return None
        except Exception:
            return None

    def _set_resolution(self, resolution: int, enable: bool = True) -> int | None:
        """Call NtSetTimerResolution. Returns actual resolution or None."""
        if not self._ntdll:
            return None
        try:
            cur = ctypes.c_ulong()
            status = self._ntdll.NtSetTimerResolution(
                ctypes.c_ulong(resolution),
                ctypes.c_bool(enable),
                ctypes.byref(cur),
            )
            if status == 0:
                return cur.value
            logger.warning("NtSetTimerResolution status: %s", status)
            return None
        except Exception as e:
            logger.error("NtSetTimerResolution failed: %s", e)
            return None

    # -- status file --------------------------------------------------------

    def _write_status(self, status: str, process_name: str = "") -> None:
        """Write a JSON status file so the tray app can read state."""
        payload = {
            "pid": os.getpid(),
            "process_name": process_name,
            "resolution_100ns": self._resolution_100ns,
            "resolution_ms": self._resolution_100ns / 10000.0,
            "start_time": time.time(),
            "status": status,
        }
        try:
            _STATUS_FILE.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        except Exception as e:
            logger.warning("Could not write status file: %s", e)

    def _remove_status(self) -> None:
        """Clean up the status file."""
        try:
            _STATUS_FILE.unlink(missing_ok=True)
        except Exception:
            pass

    # -- context manager ----------------------------------------------------

    def __enter__(self) -> TimerResolutionGuard:
        """Set the requested timer resolution."""
        info = self._query_resolution()
        if info:
            self._original_resolution = info[2]

        actual = self._set_resolution(self._resolution_100ns, enable=True)
        if actual is not None:
            self._active = True
            logger.info(
                "Timer resolution set to %.3f ms (requested %.3f ms)",
                actual / 10000.0,
                self._resolution_100ns / 10000.0,
            )
        else:
            logger.error("Failed to set timer resolution on enter")

        return self

    def __exit__(self, exc_type: Any, exc_val: Any, exc_tb: Any) -> None:
        """Restore the original timer resolution."""
        self._release()
        return None

    def _release(self) -> None:
        """Release the resolution request and clean up."""
        if self._active:
            self._set_resolution(
                self._original_resolution or TimerSettingsHandler.RESOLUTION_DEFAULT,
                enable=False,
            )
            self._active = False
            logger.info("Timer resolution released")
        self._write_status("released")
        self._remove_status()

    # -- process-lifetime hold ----------------------------------------------

    @staticmethod
    def _is_process_running(process_name: str) -> bool:
        """Check if a process with the given name is running.

        Uses ``tasklist`` so no extra dependencies are needed.

        Args:
            process_name: Executable name, e.g. ``"game.exe"``.

        Returns:
            True if at least one instance is found.
        """
        try:
            result = subprocess.run(
                ["tasklist", "/FI", f"IMAGENAME eq {process_name}", "/NH"],
                capture_output=True,
                text=True,
                timeout=10,
            )
            # tasklist prints "INFO: No tasks are running..." when nothing matches
            return process_name.lower() in result.stdout.lower()
        except Exception as e:
            logger.warning("tasklist check failed: %s", e)
            return False

    def hold_for_process(
        self,
        process_name: str,
        resolution_100ns: int | None = None,
        poll_interval: float = DEFAULT_POLL_INTERVAL,
        timeout: float = DEFAULT_TIMEOUT,
    ) -> None:
        """Hold the timer resolution until *process_name* exits.

        If the guard was not already entered as a context manager, this method
        will set the resolution itself.

        Args:
            process_name: Executable name to watch (e.g. ``"game.exe"``).
            resolution_100ns: Override the resolution set at init time.
                If ``None``, uses the value from ``__init__``.
            poll_interval: Seconds between process-alive checks.
            timeout: Maximum seconds to hold before giving up.
        """
        if resolution_100ns is not None:
            self._resolution_100ns = resolution_100ns

        # Ensure resolution is set (idempotent if already entered)
        if not self._active:
            self.__enter__()

        self._write_status("waiting", process_name)
        logger.info("Waiting for %s to start...", process_name)

        # Wait for the game to appear (up to 5 minutes)
        startup_deadline = time.time() + 300
        while time.time() < startup_deadline:
            if self._is_process_running(process_name):
                break
            time.sleep(poll_interval)
        else:
            logger.warning(
                "%s did not start within 5 minutes; holding anyway until timeout",
                process_name,
            )

        self._write_status("active", process_name)
        logger.info("Holding timer resolution for %s", process_name)

        deadline = time.time() + timeout
        try:
            while time.time() < deadline:
                if not self._is_process_running(process_name):
                    logger.info("%s exited; releasing timer resolution", process_name)
                    break
                time.sleep(poll_interval)
            else:
                logger.warning(
                    "Timeout (%.0f h) reached while holding for %s",
                    timeout / 3600,
                    process_name,
                )
        finally:
            self._release()
