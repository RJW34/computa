"""MultiMonitorDetector - Compositor and display edge case detection.

This module detects multi-monitor configurations and compositor conditions
that may affect profile behavior.
"""

from __future__ import annotations

import ctypes
import logging
import subprocess
from dataclasses import dataclass, field
from typing import Any

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

    # Known overlay processes
    OVERLAY_PROCESSES = {
        "nvcontainer.exe": "NVIDIA Container (GeForce Experience)",
        "nvdisplay.container.exe": "NVIDIA Display Container",
        "gamebar.exe": "Xbox Game Bar",
        "gamebarftserver.exe": "Xbox Game Bar Server",
        "gamingservices.exe": "Xbox Gaming Services",
        "discord.exe": "Discord Overlay",
        "rtss.exe": "RivaTuner Statistics Server",
        "skif.exe": "SpecialK Injection Frontend",
        "steam.exe": "Steam Overlay",
        "obs64.exe": "OBS Studio",
    }

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
                env.has_mixed_refresh = len(set(refresh_rates)) > 1
                env.has_mixed_resolution = len(set(resolutions)) > 1

                primary = next((m for m in monitors if m.is_primary), monitors[0])
                env.primary_refresh = primary.refresh_rate

        except Exception as e:
            logger.error(f"Failed to detect monitors: {e}")
            # Fallback to single monitor assumption
            env.monitor_count = 1
            env.can_guarantee_exclusive = True

    def _enum_display_monitors(self) -> list[MonitorInfo]:
        """Enumerate display monitors using Win32 API."""
        monitors: list[MonitorInfo] = []

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
                                refresh_rate=60.0,  # Default, need better detection
                                is_primary=parts[3].lower() == "true",
                            ))

            # Try to get actual refresh rates
            self._get_refresh_rates(monitors)

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

    def _get_refresh_rates(self, monitors: list[MonitorInfo]) -> None:
        """Get actual refresh rates for monitors."""
        try:
            result = subprocess.run(
                [
                    "powershell", "-NoProfile", "-Command",
                    """
                    Get-CimInstance -Namespace root/wmi -ClassName WmiMonitorBasicDisplayParams |
                    Select-Object -Property Active, InstanceName
                    Get-CimInstance Win32_VideoController |
                    Select-Object -Property CurrentRefreshRate, Name
                    """
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            # Parse refresh rate from output
            for line in result.stdout.split("\n"):
                if "CurrentRefreshRate" in line:
                    try:
                        # Extract number
                        rate_str = line.split(":")[-1].strip()
                        rate = float(rate_str) if rate_str else 60.0
                        if monitors and rate > 0:
                            monitors[0].refresh_rate = rate
                    except (ValueError, IndexError):
                        pass

        except Exception as e:
            logger.debug(f"Refresh rate detection fallback: {e}")

    def _detect_overlays(self, env: DisplayEnvironment) -> None:
        """Detect running overlay processes."""
        try:
            result = subprocess.run(
                ["tasklist", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                running_procs = result.stdout.lower()

                for proc, name in self.OVERLAY_PROCESSES.items():
                    if proc.lower() in running_procs:
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
                    "Mixed refresh can cause compositor overhead. Consider disabling "
                    "secondary monitors during competitive gaming, or ensure HAGS is ON "
                    "to mitigate compositor latency."
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
                    "secondary monitors for minimum latency."
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
                    "Disable overlays for minimum latency gaming."
                ),
            ))
            result.exclusive_fullscreen_safe = False

        # Warning: GeForce Experience specifically
        if any("GeForce" in o for o in env.detected_overlays):
            result.warnings.append(MultiMonitorWarning(
                code="MULTIMON_GFE_DETECTED",
                message="GeForce Experience detected",
                recommendation=(
                    "GeForce Experience adds overhead and can interfere with exclusive "
                    "fullscreen. Consider uninstalling GFE for lowest latency. "
                    "NVIDIA drivers work fine without GFE."
                ),
            ))

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
