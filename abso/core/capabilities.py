"""Capability graph evaluation for profile preflight checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from abso.core.detector import HardwareDetector
from abso.core.multimon_detector import MultiMonitorDetector, MultiMonitorResult
from abso.profiles.base import BaseProfile
from abso.settings.windows import WindowsSettingsHandler
from abso.utils.os_release import OsRelease, detect_os_release

logger = logging.getLogger(__name__)


def _coerce_build_pair(value: Any) -> tuple[int, int] | None:
    """Normalize a profile build-pair declaration to ``(build, ubr)``.

    Profiles may return ``None``, a 2-tuple of ints, or a Mock instance in
    tests. Anything that does not match the expected shape is treated as
    unset so capability checks never crash on a malformed profile.
    """
    if value is None:
        return None
    if isinstance(value, tuple) and len(value) == 2:
        try:
            build = int(value[0])
            ubr = int(value[1])
        except (TypeError, ValueError):
            return None
        return (build, ubr)
    return None


@dataclass
class CapabilityFinding:
    """Single capability finding."""

    code: str
    severity: str  # blocker, warning, info
    message: str
    details: str | None = None
    fallback_profile_id: str | None = None


@dataclass
class CapabilityReport:
    """Capability evaluation output for a profile."""

    profile_id: str
    findings: list[CapabilityFinding] = field(default_factory=list)

    @property
    def blockers(self) -> list[CapabilityFinding]:
        return [f for f in self.findings if f.severity == "blocker"]

    @property
    def warnings(self) -> list[CapabilityFinding]:
        return [f for f in self.findings if f.severity == "warning"]

    @property
    def info(self) -> list[CapabilityFinding]:
        return [f for f in self.findings if f.severity == "info"]

    @property
    def has_blockers(self) -> bool:
        return bool(self.blockers)

    @property
    def passed(self) -> bool:
        return not self.has_blockers

    def to_dict(self) -> dict[str, Any]:
        """Serialize report to JSON-safe dict."""
        return {
            "profile_id": self.profile_id,
            "passed": self.passed,
            "has_blockers": self.has_blockers,
            "blockers": len(self.blockers),
            "warnings": len(self.warnings),
            "findings": [
                {
                    "code": finding.code,
                    "severity": finding.severity,
                    "message": finding.message,
                    "details": finding.details,
                    "fallback_profile_id": finding.fallback_profile_id,
                }
                for finding in self.findings
            ],
        }


class CapabilityEngine:
    """Evaluates whether a profile can be safely applied on this machine."""

    def __init__(
        self,
        detector: HardwareDetector | None = None,
        multimon_detector: MultiMonitorDetector | None = None,
    ) -> None:
        self.detector = detector or HardwareDetector()
        self.multimon_detector = multimon_detector or MultiMonitorDetector()

    def evaluate(
        self,
        profile: BaseProfile,
        multimon_result: MultiMonitorResult | None = None,
    ) -> CapabilityReport:
        """Evaluate capability blockers/warnings for a profile."""
        report = CapabilityReport(profile_id=profile.profile_id)

        if multimon_result is None:
            multimon_result = self._safe_detect_multimon(report)

        monitors = self._safe_detect_monitors(report)
        gpu = self._safe_detect_gpu(report)

        self._check_os_build_requirements(profile, report)
        self._check_experimental_branch(report)
        self._check_vrr_requirements(profile, monitors, report)
        self._check_gpu_vendor(profile, gpu, report)
        self._check_monitor_presence(profile, monitors, report)
        self._check_display_path_requirements(profile, multimon_result, report)
        self._check_hdr_requirements(profile, report)
        self._check_explicit_refresh_requirements(profile, monitors, report)

        return report

    def _check_experimental_branch(self, report: CapabilityReport) -> None:
        """Surface an info finding when the OS is on the Experimental track.

        The auditor emits a banner for the Canary 29xxx / Experimental
        (Future Platforms) branch; profile preflight should mirror that
        caveat so users who run ``apply <profile>`` without first running
        ``audit`` still see it. This is informational only - the user has
        opted into the pre-release branch and ABSO does not block apply
        because of it.
        """
        try:
            release = detect_os_release()
        except Exception as e:
            logger.warning("Capability experimental-branch check failed: %s", e)
            return

        if not release.is_experimental_future_platform:
            return

        report.findings.append(
            CapabilityFinding(
                code="OS_EXPERIMENTAL_FUTURE_PLATFORMS",
                severity="info",
                message=(
                    f"Running on Experimental (Future Platforms) Insider build "
                    f"{release.build}.{release.ubr} ({release.release_branch}). "
                    "Profile is validated against the 25H2 Germanium track; "
                    "feature-flag surfaces (Xbox Mode, AI agents, Shared Audio) "
                    "may shift on this branch."
                ),
            )
        )

    def _check_os_build_requirements(
        self,
        profile: BaseProfile,
        report: CapabilityReport,
    ) -> None:
        """Evaluate ``min_os_build`` and ``validated_os_build`` against the OS.

        Profiles can declare:
          * ``min_os_build``: blocker if the current OS is older.
          * ``validated_os_build``: info finding when the OS is newer than
            the build the profile was last validated against (so users see
            the gap without being blocked).
        """
        min_build = _coerce_build_pair(getattr(profile, "min_os_build", None))
        validated = _coerce_build_pair(getattr(profile, "validated_os_build", None))
        if min_build is None and validated is None:
            return

        try:
            release: OsRelease = detect_os_release()
        except Exception as e:
            logger.warning("Capability OS release detection failed: %s", e)
            report.findings.append(
                CapabilityFinding(
                    code="DETECT_OS_RELEASE_FAILED",
                    severity="warning",
                    message="OS release detection failed",
                    details=str(e),
                )
            )
            return

        if release.build == 0:
            report.findings.append(
                CapabilityFinding(
                    code="OS_RELEASE_UNAVAILABLE",
                    severity="warning",
                    message="OS build/UBR could not be read; build-floor checks skipped.",
                )
            )
            return

        if min_build is not None and not release.at_least(*min_build):
            min_build_str = f"{min_build[0]}.{min_build[1]}"
            current_str = f"{release.build}.{release.ubr}"
            report.findings.append(
                CapabilityFinding(
                    code="OS_BUILD_BELOW_FLOOR",
                    severity="blocker",
                    message=(
                        f"Profile requires Windows build {min_build_str} or newer "
                        f"but this system reports {current_str}."
                    ),
                )
            )

        if (
            validated is not None
            and release.build_revision > validated
        ):
            validated_str = f"{validated[0]}.{validated[1]}"
            current_str = f"{release.build}.{release.ubr}"
            report.findings.append(
                CapabilityFinding(
                    code="OS_BUILD_UNTESTED_ON_PROFILE",
                    severity="info",
                    message=(
                        f"Profile last validated on Windows {validated_str}; "
                        f"running on {current_str}. Behavior should match but "
                        "has not been re-verified on this build."
                    ),
                )
            )

    def _safe_detect_multimon(
        self,
        report: CapabilityReport,
    ) -> MultiMonitorResult | None:
        try:
            return self.multimon_detector.detect()
        except Exception as e:
            logger.warning(f"Capability display environment detection failed: {e}")
            report.findings.append(
                CapabilityFinding(
                    code="DETECT_DISPLAY_ENV_FAILED",
                    severity="warning",
                    message="Display environment detection failed",
                    details=str(e),
                )
            )
            return None

    def _safe_detect_monitors(self, report: CapabilityReport) -> list[dict[str, Any]]:
        try:
            return self.detector.detect_monitors()
        except Exception as e:
            logger.warning(f"Capability monitor detection failed: {e}")
            report.findings.append(
                CapabilityFinding(
                    code="DETECT_MONITORS_FAILED",
                    severity="warning",
                    message="Monitor capability detection failed",
                    details=str(e),
                )
            )
            return []

    def _safe_detect_gpu(self, report: CapabilityReport) -> dict[str, Any] | None:
        try:
            return self.detector.detect_gpu()
        except Exception as e:
            logger.warning(f"Capability GPU detection failed: {e}")
            report.findings.append(
                CapabilityFinding(
                    code="DETECT_GPU_FAILED",
                    severity="warning",
                    message="GPU detection failed",
                    details=str(e),
                )
            )
            return None

    def _check_vrr_requirements(
        self,
        profile: BaseProfile,
        monitors: list[dict[str, Any]],
        report: CapabilityReport,
    ) -> None:
        if not getattr(profile, "requires_confirmed_vrr_support", False):
            return

        if not monitors:
            report.findings.append(
                CapabilityFinding(
                    code="VRR_REQUIRED_NO_MONITOR_DATA",
                    severity="blocker",
                    message=(
                        "Cannot confirm VRR/G-SYNC support because no monitors were detected. "
                        "Enable monitor Adaptive Sync/FreeSync in OSD, enable G-SYNC in NVIDIA Control Panel, then retry."
                    ),
                )
            )
            return

        target_monitor = self._select_target_monitor(monitors)
        if target_monitor is None:
            report.findings.append(
                CapabilityFinding(
                    code="VRR_REQUIRED_NO_MONITOR_DATA",
                    severity="blocker",
                    message=(
                        "Cannot confirm VRR/G-SYNC support because no monitors were detected. "
                        "Enable monitor Adaptive Sync/FreeSync in OSD, enable G-SYNC in NVIDIA Control Panel, then retry."
                    ),
                )
            )
            return

        target_name = str(target_monitor.get("name", "Gaming display"))
        target_status = target_monitor.get("vrr_supported")

        if target_status is True:
            return

        # ABSO targets the most likely gaming display for VRR profiles. Accept
        # "hardware" or "likely" on that display to avoid a catch-22 where a
        # no-sync profile temporarily leaves VRR disabled globally.
        if target_status in ("hardware", "likely"):
            report.findings.append(
                CapabilityFinding(
                    code="VRR_LIKELY_ACCEPTED",
                    severity="info",
                    message=(
                        f"VRR support detected as likely on target gaming display '{target_name}'. "
                        "Profile will enable G-SYNC. If you experience issues, "
                        "verify Adaptive Sync/FreeSync is enabled in your monitor OSD."
                    ),
                )
            )
            return

        secondary_vrr = [
            str(m.get("name", "Unknown"))
            for m in monitors
            if m is not target_monitor and m.get("vrr_supported") in {True, "hardware", "likely"}
        ]
        details = None
        if secondary_vrr:
            details = (
                "ABSO targets the primary gaming display for VRR profiles. "
                f"Other VRR-capable displays detected: {', '.join(secondary_vrr)}"
            )
        report.findings.append(
            CapabilityFinding(
                code="VRR_REQUIRED_NOT_CONFIRMED",
                severity="blocker",
                message=(
                    f"Target gaming display '{target_name}' does not report confirmed VRR/G-SYNC support. "
                    "Turn on Adaptive Sync/FreeSync in that monitor's OSD, make sure it is the gaming display, "
                    "enable G-SYNC in NVIDIA Control Panel, then retry."
                ),
                details=details,
            )
        )

    def _select_target_monitor(
        self,
        monitors: list[dict[str, Any]],
    ) -> dict[str, Any] | None:
        """Pick the best candidate for the user's active gaming display.

        Current heuristic:
        - prefer the highest active refresh
        - then prefer displays with stronger VRR evidence
        - then prefer the primary display as a tiebreaker
        """
        if not monitors:
            return None

        def vrr_score(monitor: dict[str, Any]) -> int:
            status = monitor.get("vrr_supported")
            if status is True:
                return 4
            if status == "hardware":
                return 3
            if status == "likely":
                return 2
            if status == "possible":
                return 1
            return 0

        def refresh_score(monitor: dict[str, Any]) -> float:
            for key in ("refresh_rate", "max_refresh_rate", "max_refresh_capability"):
                value = monitor.get(key)
                try:
                    if value is not None:
                        parsed = float(value)
                        if parsed > 0:
                            return parsed
                except (TypeError, ValueError):
                    continue
            return 0.0

        return max(
            monitors,
            key=lambda monitor: (
                refresh_score(monitor),
                vrr_score(monitor),
                1 if monitor.get("is_primary") else 0,
            ),
        )

    def _check_gpu_vendor(
        self,
        profile: BaseProfile,
        gpu: dict[str, Any] | None,
        report: CapabilityReport,
    ) -> None:
        if gpu is None:
            report.findings.append(
                CapabilityFinding(
                    code="GPU_NOT_DETECTED",
                    severity="warning",
                    message="GPU vendor could not be detected; NVIDIA profile enforcement may be incomplete.",
                )
            )
            return

        gpu_name = str(gpu.get("name") or "").lower()
        has_nvidia = any(marker in gpu_name for marker in ("nvidia", "geforce", "rtx", "gtx"))

        if has_nvidia:
            return

        report.findings.append(
            CapabilityFinding(
                code="GPU_NOT_NVIDIA",
                severity="warning",
                message=(
                    f"Detected GPU '{gpu.get('name', 'Unknown')}' is not NVIDIA; "
                    f"NVIDIA settings in profile '{profile.profile_id}' may not apply."
                ),
            )
        )

    def _check_monitor_presence(
        self,
        profile: BaseProfile,
        monitors: list[dict[str, Any]],
        report: CapabilityReport,
    ) -> None:
        if monitors:
            return
        if getattr(profile, "requires_confirmed_vrr_support", False):
            return
        report.findings.append(
            CapabilityFinding(
                code="NO_MONITOR_DATA",
                severity="warning",
                message="No monitor information detected; refresh/VRR guidance may be inaccurate.",
            )
        )

    def _check_display_path_requirements(
        self,
        profile: BaseProfile,
        multimon_result: MultiMonitorResult | None,
        report: CapabilityReport,
    ) -> None:
        """Validate runtime display-path requirements for strict profiles."""
        requirements = getattr(profile, "display_path_requirements", None)
        require_overlay_free_path = getattr(requirements, "require_overlay_free_path", False)
        if not isinstance(require_overlay_free_path, bool) or not require_overlay_free_path:
            return

        if multimon_result is None:
            report.findings.append(
                CapabilityFinding(
                    code="DISPLAY_PATH_UNVERIFIED",
                    severity="blocker",
                    message=(
                        "This profile requires a verified overlay-free display path, "
                        "but display environment detection failed."
                    ),
                )
            )
            return

        overlays = list(multimon_result.environment.detected_overlays)
        if overlays:
            fallback_profile_id = getattr(profile, "overlay_compatible_fallback_profile_id", None)
            fallback_hint = ""
            if isinstance(fallback_profile_id, str) and fallback_profile_id.strip():
                fallback_hint = (
                    f" If you need Medal/Discord/OBS-style overlays, use profile "
                    f"'{fallback_profile_id}' instead."
                )
            report.findings.append(
                CapabilityFinding(
                    code="DISPLAY_OVERLAYS_BLOCK_EXCLUSIVE_PROFILE",
                    severity="blocker",
                    message=(
                        "This fullscreen-exclusive profile requires overlays to be disabled "
                        f"on the gaming display path. Disable: {', '.join(overlays)}."
                        f"{fallback_hint}"
                    ),
                    details=(
                        "Overlays can force borderless/composited presentation or destabilize "
                        "VRR on the target display."
                    ),
                    fallback_profile_id=(
                        fallback_profile_id
                        if isinstance(fallback_profile_id, str) and fallback_profile_id.strip()
                        else None
                    ),
                )
            )

        environment = multimon_result.environment
        if (
            getattr(profile, "uses_fullscreen_only_vrr_path", False)
            and environment.is_multi_monitor
            and environment.has_mixed_refresh
        ):
            report.findings.append(
                CapabilityFinding(
                    code="DISPLAY_PATH_MIXED_REFRESH_BLOCKS_STRICT_VRR",
                    severity="warning",
                    message=(
                        "This fullscreen-only VRR profile is risky because the active "
                        f"display path has {environment.monitor_count} monitors with mixed "
                        f"refresh rates ({environment.min_refresh:g}Hz - "
                        f"{environment.max_refresh:g}Hz)."
                    ),
                    details=(
                        "Mixed-refresh multi-monitor paths with fullscreen-only G-SYNC/VRR "
                        "can trigger MPO/display pipeline black flashes during focus or "
                        "present-mode transitions. The profile is still allowed so a user "
                        "can deliberately choose the lean strict fullscreen path."
                    ),
                )
            )

    def _check_hdr_requirements(
        self,
        profile: BaseProfile,
        report: CapabilityReport,
    ) -> None:
        """Block profiles that require HDR on machines without a confirmed HDR output path."""
        try:
            windows_settings = profile.get_settings("WindowsSettingsHandler") or {}
        except Exception as e:
            logger.debug(f"Failed to read Windows settings for HDR capability checks: {e}")
            return

        if not self._profile_requests_hdr_output(windows_settings):
            return

        try:
            detected = WindowsSettingsHandler().detect()
        except Exception as e:
            logger.warning(f"Capability HDR detection failed: {e}")
            report.findings.append(
                CapabilityFinding(
                    code="HDR_REQUIRED_UNVERIFIED",
                    severity="blocker",
                    message=(
                        "This profile requires a confirmed HDR-capable active display, "
                        "but HDR capability detection failed on this machine."
                    ),
                    details=str(e),
                )
            )
            return

        hdr_capable_count = detected.get("hdr_capable_count")
        try:
            parsed_count = int(hdr_capable_count) if hdr_capable_count is not None else None
        except (TypeError, ValueError):
            parsed_count = None

        if parsed_count is None:
            report.findings.append(
                CapabilityFinding(
                    code="HDR_REQUIRED_UNVERIFIED",
                    severity="blocker",
                    message=(
                        "This profile requires a confirmed HDR-capable active display, "
                        "but HDR capability could not be verified."
                    ),
                )
            )
            return

        if parsed_count < 1:
            report.findings.append(
                CapabilityFinding(
                    code="HDR_REQUIRED_NO_CAPABLE_DISPLAY",
                    severity="blocker",
                    message=(
                        "This profile requires at least one HDR-capable active display, "
                        "but none were detected."
                    ),
                )
            )

    def _profile_requests_hdr_output(self, windows_settings: dict[str, Any]) -> bool:
        """Return True when a profile depends on an HDR-capable display path."""
        return bool(
            windows_settings.get("hdr") is True
            or windows_settings.get("auto_hdr") is True
        )

    def _check_explicit_refresh_requirements(
        self,
        profile: BaseProfile,
        monitors: list[dict[str, Any]],
        report: CapabilityReport,
    ) -> None:
        """Validate profiles that request a fixed refresh rate."""
        try:
            windows_settings = profile.get_settings("WindowsSettingsHandler") or {}
        except Exception as e:
            logger.debug(f"Failed to read Windows settings for capability checks: {e}")
            return

        requested_refresh = windows_settings.get("refresh_rate")
        try:
            target_hz = round(float(requested_refresh))
        except (TypeError, ValueError):
            return

        if target_hz <= 0:
            return

        if not monitors:
            report.findings.append(
                CapabilityFinding(
                    code="REFRESH_TARGET_UNVERIFIED",
                    severity="warning",
                    message=(
                        f"Profile requests fixed refresh {target_hz} Hz, but no monitor data was detected. "
                        "Cannot verify support on this machine."
                    ),
                )
            )
            return

        primary = self._select_target_monitor(monitors) or monitors[0]

        candidates: list[int] = []
        for key in ("max_refresh_capability", "max_refresh_rate", "refresh_rate"):
            value = primary.get(key)
            try:
                if value is not None:
                    parsed = round(float(value))
                    if parsed > 0:
                        candidates.append(parsed)
            except (TypeError, ValueError):
                continue

        if not candidates:
            report.findings.append(
                CapabilityFinding(
                    code="REFRESH_TARGET_UNVERIFIED",
                    severity="warning",
                    message=(
                        f"Profile requests fixed refresh {target_hz} Hz, but monitor refresh capability "
                        "could not be determined."
                    ),
                )
            )
            return

        max_supported = max(candidates)
        if target_hz > max_supported:
            report.findings.append(
                CapabilityFinding(
                code="REFRESH_TARGET_UNSUPPORTED",
                severity="blocker",
                message=(
                    f"Profile requests {target_hz} Hz, but the target gaming display supports up to {max_supported} Hz "
                    "at detected capabilities. Choose a profile that matches your display."
                ),
            )
        )
