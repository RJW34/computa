"""Capability graph evaluation for profile preflight checks."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any

from abso.core.detector import HardwareDetector
from abso.profiles.base import BaseProfile

logger = logging.getLogger(__name__)


@dataclass
class CapabilityFinding:
    """Single capability finding."""

    code: str
    severity: str  # blocker, warning, info
    message: str
    details: str | None = None


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
                }
                for finding in self.findings
            ],
        }


class CapabilityEngine:
    """Evaluates whether a profile can be safely applied on this machine."""

    def __init__(self, detector: HardwareDetector | None = None) -> None:
        self.detector = detector or HardwareDetector()

    def evaluate(self, profile: BaseProfile) -> CapabilityReport:
        """Evaluate capability blockers/warnings for a profile."""
        report = CapabilityReport(profile_id=profile.profile_id)

        monitors = self._safe_detect_monitors(report)
        gpu = self._safe_detect_gpu(report)

        self._check_vrr_requirements(profile, monitors, report)
        self._check_gpu_vendor(profile, gpu, report)
        self._check_monitor_presence(profile, monitors, report)
        self._check_explicit_refresh_requirements(profile, monitors, report)

        return report

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

        confirmed_vrr = [m for m in monitors if m.get("vrr_supported") is True]
        if confirmed_vrr:
            return

        # Accept "likely" or "hardware" — the profile itself will enable G-SYNC.
        # This avoids a catch-22 where a no-sync profile disables VRR globally,
        # making it impossible to switch to a G-Sync profile because VRR can't
        # be "confirmed" while it's disabled.
        likely_vrr = [
            m for m in monitors
            if m.get("vrr_supported") in ("hardware", "likely")
        ]
        if likely_vrr:
            names = ", ".join(m.get("name", "Unknown") for m in likely_vrr)
            report.findings.append(
                CapabilityFinding(
                    code="VRR_LIKELY_ACCEPTED",
                    severity="info",
                    message=(
                        f"VRR support detected as likely on {names}. "
                        "Profile will enable G-SYNC. If you experience issues, "
                        "verify Adaptive Sync/FreeSync is enabled in your monitor OSD."
                    ),
                )
            )
            return

        status_summary = ", ".join(
            f"{m.get('name', 'Unknown')}: {m.get('vrr_supported', 'unknown')}"
            for m in monitors
        )
        report.findings.append(
            CapabilityFinding(
                code="VRR_REQUIRED_NOT_CONFIRMED",
                severity="blocker",
                message=(
                    "No monitor with confirmed VRR/G-SYNC support was detected. "
                    "Turn on monitor Adaptive Sync/FreeSync in OSD, enable G-SYNC in NVIDIA Control Panel, then retry. "
                    f"Detected VRR status: {status_summary}"
                ),
            )
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

        primary = next((m for m in monitors if m.get("is_primary")), monitors[0])

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
                        f"Profile requests {target_hz} Hz, but primary monitor supports up to {max_supported} Hz "
                        "at detected capabilities. Choose a profile that matches your display."
                    ),
                )
            )
