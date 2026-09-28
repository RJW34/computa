"""MultiMonitorDetector - Compositor and display edge case detection.

This module detects multi-monitor configurations and compositor conditions
that may affect profile behavior.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
from ctypes import wintypes
from dataclasses import dataclass, field
from typing import Any

from abso.core.detector import HardwareDetector
from abso.core.overlay_policy import OVERLAY_PROCESS_LABELS
from abso.core.process_list import parse_tasklist_csv_images
from abso.utils.proc import no_window_creationflags

logger = logging.getLogger(__name__)


@dataclass
class MonitorInfo:
    """Information about a connected monitor."""

    name: str
    width: int
    height: int
    refresh_rate: float
    is_primary: bool
    is_hdr_capable: bool = False
    is_vrr_capable: bool = False
    max_refresh_rate: float | None = None
    vrr_type: str | None = None
    vrr_range: str | None = None


@dataclass
class DisplayEnvironment:
    """Complete display environment state."""

    monitors: list[MonitorInfo] = field(default_factory=list)
    monitor_count: int = 0
    has_mixed_refresh: bool = False
    has_mixed_resolution: bool = False
    primary_refresh: float = 0.0
    max_refresh: float = 0.0
    min_refresh: float = 0.0
    can_guarantee_exclusive: bool = True
    detected_overlays: list[str] = field(default_factory=list)
    compositor_active: bool = True  # DWM is always active on Win11
    # False when monitor enumeration failed and the count is a fallback
    # assumption rather than a real reading. Display-recovery safety code must
    # not treat a fallback "1 monitor" as a confident single-monitor rig.
    detection_confident: bool = True

    @property
    def is_multi_monitor(self) -> bool:
        return self.monitor_count > 1


@dataclass
class MultiMonitorWarning:
    """Warning about a multi-monitor edge case."""

    code: str
    message: str
    recommendation: str


@dataclass
class MultiMonitorResult:
    """Result of multi-monitor detection."""

    environment: DisplayEnvironment
    warnings: list[MultiMonitorWarning] = field(default_factory=list)
    exclusive_fullscreen_safe: bool = True


class MultiMonitorDetector:
    """Detects multi-monitor and compositor edge cases.

    Detects:
    - Multiple active monitors
    - Mixed refresh rates
    - Borderless-forced engines
    - Active overlays (DWM, GFE, Xbox, etc.)

    Provides:
    - Recommendations for VRR settings
    - Warnings about exclusive fullscreen assumptions
    - Compositor latency estimates
    """

    # Backward-compatible alias for older callers/tests.
    OVERLAY_PROCESSES = OVERLAY_PROCESS_LABELS

    def detect(self) -> MultiMonitorResult:
        """Detect display environment and edge cases.

        Returns:
            MultiMonitorResult with environment info and warnings.
        """
        env = DisplayEnvironment()

        # Detect monitors
        self._detect_monitors(env)

        # Detect overlays
        self._detect_overlays(env)

        # Analyze for edge cases
        result = MultiMonitorResult(environment=env)
        self._analyze_edge_cases(result)

        # Log summary
        logger.info(
            f"MultiMonitorDetector: {env.monitor_count} monitor(s), "
            f"mixed_refresh={env.has_mixed_refresh}, "
            f"overlays={len(env.detected_overlays)}"
        )

        return result

    def _detect_monitors(self, env: DisplayEnvironment) -> None:
        """Detect connected monitors using Windows API."""
        try:
            # Use EnumDisplayMonitors via ctypes
            monitors = self._enum_display_monitors()
            env.monitors = monitors
            env.monitor_count = len(monitors)

            if monitors:
                refresh_rates = [m.refresh_rate for m in monitors]
                resolutions = [(m.width, m.height) for m in monitors]

                env.max_refresh = max(refresh_rates)
                env.min_refresh = min(refresh_rates)
                env.has_mixed_refresh = (
                    len({self._refresh_bucket(rate) for rate in refresh_rates}) > 1
                )
                env.has_mixed_resolution = len(set(resolutions)) > 1

                primary = next((m for m in monitors if m.is_primary), monitors[0])
                env.primary_refresh = primary.refresh_rate

        except Exception as e:
            logger.error(f"Failed to detect monitors: {e}")
            # Fallback to single monitor assumption. Mark detection as not
            # confident so display-recovery safety code does not mistake this
            # for a real single-monitor reading and auto-reset a multi-monitor rig.
            env.monitor_count = 1
            env.can_guarantee_exclusive = True
            env.detection_confident = False

    def _enum_display_monitors(self) -> list[MonitorInfo]:
        """Enumerate display monitors using Win32 API."""
        monitors: list[MonitorInfo] = []

        # Primary path: reuse HardwareDetector's monitor model, which already
        # accounts for CCD + legacy API quirks and reports active refresh.
        try:
            detected = HardwareDetector().detect_monitors()
            for i, entry in enumerate(detected):
                width, height = self._parse_resolution(entry.get("resolution"))
                refresh_rate = self._pick_refresh_rate(entry)
                monitors.append(MonitorInfo(
                    name=str(entry.get("name") or entry.get("adapter") or f"Display {i + 1}"),
                    width=width,
                    height=height,
                    refresh_rate=refresh_rate,
                    is_primary=bool(entry.get("is_primary", False)),
                    is_hdr_capable=False,
                    is_vrr_capable=entry.get("vrr_supported") in {True, "hardware", "likely", "possible"},
                    max_refresh_rate=self._pick_max_refresh_rate(entry),
                    vrr_type=self._optional_string(entry.get("vrr_type")),
                    vrr_range=self._optional_string(entry.get("vrr_range")),
                ))
            if monitors:
                desktop_monitors = self._enum_desktop_screens()
                return self._merge_monitor_sources(monitors, desktop_monitors)
        except Exception as e:
            logger.debug(f"HardwareDetector monitor enumeration failed: {e}")

        desktop_monitors = self._enum_desktop_screens()
        if desktop_monitors:
            return desktop_monitors

        try:
            # Use Windows CCD API or fallback to basic WMI
            # Try PowerShell approach for reliability
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    """
                    Add-Type -AssemblyName System.Windows.Forms
                    [System.Windows.Forms.Screen]::AllScreens | ForEach-Object {
                        $name = $_.DeviceName
                        $bounds = $_.Bounds
                        $primary = $_.Primary
                        "$name|$($bounds.Width)|$($bounds.Height)|$primary"
                    }
                    """
                ],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=no_window_creationflags(),
            )

            if result.returncode == 0:
                for line in result.stdout.strip().split("\n"):
                    if "|" in line:
                        parts = line.split("|")
                        if len(parts) >= 4:
                            monitors.append(MonitorInfo(
                                name=parts[0],
                                width=int(parts[1]),
                                height=int(parts[2]),
                                refresh_rate=60.0,  # Fallback when refresh detection is unavailable
                                is_primary=parts[3].lower() == "true",
                            ))

        except Exception as e:
            logger.debug(f"Monitor enumeration fallback: {e}")
            # Return single default monitor
            monitors = [MonitorInfo(
                name="Primary",
                width=1920,
                height=1080,
                refresh_rate=60.0,
                is_primary=True,
            )]

        return monitors

    def _enum_desktop_screens(self) -> list[MonitorInfo]:
        """Enumerate active desktop monitor rectangles via Win32 user32."""
        monitors: list[MonitorInfo] = []

        try:
            user32 = ctypes.windll.user32

            class RECT(ctypes.Structure):
                _fields_ = [
                    ("left", ctypes.c_long),
                    ("top", ctypes.c_long),
                    ("right", ctypes.c_long),
                    ("bottom", ctypes.c_long),
                ]

            class MONITORINFOEXW(ctypes.Structure):
                _fields_ = [
                    ("cbSize", ctypes.c_ulong),
                    ("rcMonitor", RECT),
                    ("rcWork", RECT),
                    ("dwFlags", ctypes.c_ulong),
                    ("szDevice", ctypes.c_wchar * 32),
                ]

            MONITORINFOF_PRIMARY = 0x00000001
            MONITORENUMPROC = ctypes.WINFUNCTYPE(
                wintypes.BOOL,
                wintypes.HMONITOR,
                wintypes.HDC,
                ctypes.POINTER(RECT),
                wintypes.LPARAM,
            )

            def callback(
                monitor_handle: wintypes.HMONITOR,
                _hdc: wintypes.HDC,
                rect: ctypes.POINTER(RECT),
                _lparam: wintypes.LPARAM,
            ) -> bool:
                info = MONITORINFOEXW()
                info.cbSize = ctypes.sizeof(MONITORINFOEXW)
                device_name = ""
                is_primary = False
                if user32.GetMonitorInfoW(monitor_handle, ctypes.byref(info)):
                    device_name = str(info.szDevice or "")
                    is_primary = bool(info.dwFlags & MONITORINFOF_PRIMARY)
                bounds = rect.contents
                width = max(0, int(bounds.right - bounds.left))
                height = max(0, int(bounds.bottom - bounds.top))
                monitors.append(MonitorInfo(
                    name=device_name or f"Display {len(monitors) + 1}",
                    width=width or 1920,
                    height=height or 1080,
                    refresh_rate=60.0,
                    is_primary=is_primary,
                ))
                return True

            user32.EnumDisplayMonitors(None, None, MONITORENUMPROC(callback), 0)
        except Exception as e:
            logger.debug(f"Desktop monitor enumeration fallback failed: {e}")

        return monitors

    @staticmethod
    def _merge_monitor_sources(
        hardware_monitors: list[MonitorInfo],
        desktop_monitors: list[MonitorInfo],
    ) -> list[MonitorInfo]:
        """Preserve rich hardware data while filling partial topology gaps."""
        if len(desktop_monitors) <= len(hardware_monitors):
            return hardware_monitors

        merged = list(hardware_monitors)
        matched_desktop_indexes: set[int] = set()
        for hardware in hardware_monitors:
            for index, desktop in enumerate(desktop_monitors):
                if index in matched_desktop_indexes:
                    continue
                if (
                    hardware.width == desktop.width
                    and hardware.height == desktop.height
                    and hardware.is_primary == desktop.is_primary
                ):
                    matched_desktop_indexes.add(index)
                    break

        for index, desktop in enumerate(desktop_monitors):
            if index not in matched_desktop_indexes:
                merged.append(desktop)
                if len(merged) >= len(desktop_monitors):
                    break

        return merged

    @staticmethod
    def _parse_resolution(value: Any) -> tuple[int, int]:
        """Parse resolution formatted like '2560x1440'."""
        try:
            text = str(value or "")
            width_str, height_str = text.lower().split("x", 1)
            width = int(width_str.strip())
            height = int(height_str.strip())
            if width > 0 and height > 0:
                return width, height
        except Exception:
            pass
        return 1920, 1080

    @staticmethod
    def _pick_refresh_rate(entry: dict[str, Any]) -> float:
        """Pick the most relevant refresh value from detector output."""
        for key in ("refresh_rate", "max_refresh_rate", "max_refresh_capability"):
            try:
                value = entry.get(key)
                if value is None:
                    continue
                rate = float(value)
                if rate > 0:
                    return rate
            except (TypeError, ValueError):
                continue
        return 60.0

    @staticmethod
    def _pick_max_refresh_rate(entry: dict[str, Any]) -> float | None:
        """Pick the best detected maximum refresh capability, if available."""
        for key in ("max_refresh_rate", "max_refresh_capability"):
            try:
                value = entry.get(key)
                if value is None:
                    continue
                rate = float(value)
                if rate > 0:
                    return rate
            except (TypeError, ValueError):
                continue
        return None

    @staticmethod
    def _optional_string(value: Any) -> str | None:
        """Return a non-empty string value, or None."""
        text = str(value or "").strip()
        return text or None

    @staticmethod
    def _refresh_bucket(refresh_rate: float) -> int:
        """Bucket refresh rates so 59.94/59.95/60.0 do not look mixed."""
        return int(round(refresh_rate))

    def _detect_overlays(self, env: DisplayEnvironment) -> None:
        """Detect running overlay processes."""
        try:
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=10,
                creationflags=no_window_creationflags(),
            )

            if result.returncode == 0:
                running_images = parse_tasklist_csv_images(result.stdout)

                for proc, name in self.OVERLAY_PROCESSES.items():
                    if proc.lower() in running_images and name not in env.detected_overlays:
                        env.detected_overlays.append(name)
                        logger.debug(f"Detected overlay: {name}")

        except Exception as e:
            logger.debug(f"Overlay detection failed: {e}")

    def _analyze_edge_cases(self, result: MultiMonitorResult) -> None:
        """Analyze environment for edge cases and generate warnings."""
        env = result.environment

        # Warning: Mixed refresh rates
        if env.has_mixed_refresh:
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_MIXED_REFRESH",
                message=f"Mixed refresh rates detected ({env.min_refresh}Hz - {env.max_refresh}Hz)",
                recommendation=(
                    "Mixed refresh can affect presentation in some configurations. "
                    "If stutter occurs, compare display layouts in a controlled test. "
                    "Topology alone does not prove a fault or a benefit from HAGS."
                ),
            ))

        underclocked = [
            monitor
            for monitor in env.monitors
            if monitor.max_refresh_rate is not None
            and monitor.max_refresh_rate - monitor.refresh_rate >= 5.0
        ]
        if underclocked:
            monitor = max(
                underclocked,
                key=lambda item: (item.max_refresh_rate or 0.0) - item.refresh_rate,
            )
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_REFRESH_BELOW_CAPABILITY",
                message=(
                    f"{monitor.name} is running at {monitor.refresh_rate:g}Hz "
                    f"below detected capability {monitor.max_refresh_rate:g}Hz"
                ),
                recommendation=(
                    "Review each active display's selected refresh rate and consider its "
                    "highest stable refresh rate in Windows/NVIDIA Control Panel. ABSO "
                    "does not change live display modes automatically."
                ),
            ))

        # Warning: Multiple monitors
        if env.is_multi_monitor:
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_MULTIPLE_DISPLAYS",
                message=f"{env.monitor_count} monitors detected",
                recommendation=(
                    "Multi-monitor setups may prevent true exclusive fullscreen. "
                    "Some games fall back to borderless windowed. Consider disabling "
                    "secondary monitors for the strict fullscreen path."
                ),
            ))
            result.exclusive_fullscreen_safe = False

        # Warning: Overlays detected
        if env.detected_overlays:
            overlays_str = ", ".join(env.detected_overlays)
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_OVERLAYS_DETECTED",
                message=f"Active overlays: {overlays_str}",
                recommendation=(
                    "Overlays can prevent exclusive fullscreen and add compositor latency. "
                    "Disable overlays for the strict fullscreen path."
                ),
            ))
            result.exclusive_fullscreen_safe = False

        # Capability detection does not establish live VRR engagement.
        # Warning: MPO glitch risk on multi-monitor with VRR capability or mixed refresh
        vrr_monitors = [m for m in env.monitors if m.is_vrr_capable]
        if env.is_multi_monitor and (vrr_monitors or env.has_mixed_refresh):
            triggers: list[str] = []
            if vrr_monitors:
                triggers.append("VRR-capable display (current VRR engagement unverified)")
            if env.has_mixed_refresh:
                triggers.append(
                    f"mixed refresh ({env.min_refresh:.0f}Hz - {env.max_refresh:.0f}Hz)"
                )
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_MPO_GLITCH_RISK",
                message=f"MPO glitch risk: {', '.join(triggers)}",
                recommendation=(
                    "Do not auto-toggle MPO for this profile. Fix the display path first "
                    "(disable overlays, simplify topology, or match refresh rates) if you "
                    "see black flashes during monitor focus transitions."
                ),
            ))

        # Warning: GeForce Experience specifically
        if any("GeForce" in o for o in env.detected_overlays):
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_GFE_DETECTED",
                message="GeForce Experience detected",
                recommendation=(
                    "GeForce Experience can add overlay hooks and interfere with exclusive "
                    "fullscreen. Consider disabling or uninstalling GFE for strict profiles. "
                    "NVIDIA drivers work fine without GFE."
                ),
            ))

    def get_mpo_recommendation(self, result: MultiMonitorResult) -> dict[str, Any]:
        """Get MPO guidance based on display environment.

        ABSO no longer auto-disables MPO based on topology detection alone.
        The safe default is to keep MPO unchanged unless a profile explicitly
        requests it or the user makes that choice knowingly.
        """
        env = result.environment

        if not env.is_multi_monitor:
            return {
                "disable_mpo": False,
                "reason": "Single monitor - no cross-monitor MPO glitch risk",
            }

        vrr_monitors = [m for m in env.monitors if m.is_vrr_capable]
        if vrr_monitors:
            return {
                "disable_mpo": False,
                "reason": (
                    "Multi-monitor with VRR-capable display(s) - keep MPO unchanged and "
                    "fix overlays/topology first if focus transitions cause black flashes"
                ),
            }

        if env.has_mixed_refresh:
            return {
                "disable_mpo": False,
                "reason": (
                    f"Mixed refresh rates ({env.min_refresh:.0f}Hz-{env.max_refresh:.0f}Hz) - "
                    "keep MPO unchanged and simplify the display path first if glitches appear"
                ),
            }

        return {
            "disable_mpo": False,
            "reason": "Multi-monitor with uniform refresh and no VRR - MPO usually safe",
        }

    def get_vrr_recommendation(self, result: MultiMonitorResult) -> dict[str, Any]:
        """Get VRR setting recommendation based on environment.

        Args:
            result: MultiMonitorResult from detection.

        Returns:
            Dict with VRR recommendations.
        """
        env = result.environment

        # Default: VRR Optimize OFF for gaming
        recommendation = {
            "vrr_optimize": False,
            "reason": "VRR Optimize adds compositor latency",
        }

        # Exception: If exclusive fullscreen cannot be guaranteed
        if not result.exclusive_fullscreen_safe:
            recommendation = {
                "vrr_optimize": True,  # Allow opt-in
                "reason": (
                    f"Exclusive fullscreen may not be guaranteed due to: "
                    f"{'multi-monitor, ' if env.is_multi_monitor else ''}"
                    f"{'overlays' if env.detected_overlays else ''}. "
                    "VRR Optimize may help in borderless mode."
                ),
                "latency_warning": True,
            }

        return recommendation
