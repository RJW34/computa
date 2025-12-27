"""Timer resolution settings handler."""

from __future__ import annotations

import ctypes
import logging
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

    Note: Timer resolution changes only persist while this process is running.
    For persistent changes, a background service or game-specific launcher is needed.
    """

    # Common timer resolutions in 100ns units
    RESOLUTION_DEFAULT = 156250  # 15.625ms (Windows default)
    RESOLUTION_1MS = 10000       # 1.0ms
    RESOLUTION_0_5MS = 5000      # 0.5ms (minimum on most systems)

    def __init__(self) -> None:
        """Initialize timer settings handler."""
        self._ntdll = None
        self._original_resolution: int | None = None
        self._load_ntdll()

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
