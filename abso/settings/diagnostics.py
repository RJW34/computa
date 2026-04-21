"""Diagnostic, audit-only performance checks.

This handler surfaces things that affect real-world gaming performance but
that ABSO does NOT modify: per-app GPU preference, capture/overlay apps,
active downloads, driver/firmware freshness, XMP/EXPO, Resizable BAR,
DirectStorage readiness, and mixed-refresh multi-monitor setups.

It is deliberately read-only. ``apply`` and ``restore`` are no-ops; every
check surfaces state as an ``Issue`` with appropriate severity and
``EvidenceTier``. These checks are best-effort: when detection fails the
handler stays silent rather than producing a false positive.
"""

from __future__ import annotations

import logging
import os
import re
import subprocess
import winreg
from datetime import datetime, timezone
from typing import Any

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


# DirectX per-app GPU preference key. Values look like:
#   GpuPreference=2;    # 0=System default, 1=Power saving, 2=High performance
_GPU_PREF_KEY = r"Software\Microsoft\DirectX\UserGpuPreferences"

# Background capture policy (per-user).
_GAME_CONFIG_STORE_KEY = r"System\GameConfigStore"

# Windows Update / Store activity indicators (service names).
_DOWNLOAD_RELATED_SERVICES = ("wuauserv", "DoSvc", "BITS")

# Overlay processes to warn about when detected.
_OVERLAY_PROCESS_HINTS = (
    "GameBar.exe",
    "GameBarPresenceWriter.exe",
    "overwolf.exe",
    "discord.exe",  # Discord overlay
    "nahimicsvc32.exe",
    "nahimicsvc64.exe",
)


class DiagnosticsSettingsHandler(SettingsHandler):
    """Read-only diagnostic checks for gaming-adjacent system state."""

    def detect(self) -> dict[str, Any]:
        return {
            "gpu_preferences": self._read_gpu_preferences(),
            "background_capture_enabled": self._read_background_capture(),
            "active_downloads": self._detect_active_downloads(),
            "running_overlays": self._detect_running_overlays(),
            "nvidia_driver": self._read_nvidia_driver_info(),
            "memory_profile": self._read_memory_profile(),
            "resizable_bar": self._read_resizable_bar(),
            "directstorage": self._read_directstorage_readiness(),
            "display_topology": self._read_display_topology(),
        }

    def audit(self) -> list[Issue]:
        issues: list[Issue] = []
        data = self.detect()

        self._check_gpu_preferences(data.get("gpu_preferences"), issues)
        self._check_background_capture(data.get("background_capture_enabled"), issues)
        self._check_active_downloads(data.get("active_downloads"), issues)
        self._check_running_overlays(data.get("running_overlays"), issues)
        self._check_nvidia_driver(data.get("nvidia_driver"), issues)
        self._check_memory_profile(data.get("memory_profile"), issues)
        self._check_resizable_bar(data.get("resizable_bar"), issues)
        self._check_directstorage(data.get("directstorage"), issues)
        self._check_display_topology(data.get("display_topology"), issues)

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:  # noqa: ARG002
        # Diagnostics handler is audit-only by design.
        return {
            "success": True,
            "error": None,
            "requires_reboot": False,
            "applied": [],
        }

    def backup(self) -> dict[str, Any]:
        return {}

    def restore(self, data: dict[str, Any]) -> bool:  # noqa: ARG002
        return True

    @property
    def restore_guarantee(self) -> str:
        return "ephemeral"

    # ------------------------------------------------------------------
    # Detection helpers
    # ------------------------------------------------------------------

    def _read_gpu_preferences(self) -> dict[str, str] | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _GPU_PREF_KEY, 0, winreg.KEY_READ
            ) as key:
                result: dict[str, str] = {}
                i = 0
                while True:
                    try:
                        name, value, _ = winreg.EnumValue(key, i)
                    except OSError:
                        break
                    if isinstance(value, str):
                        result[name] = value
                    i += 1
                return result
        except FileNotFoundError:
            return {}
        except OSError as e:
            logger.debug("GPU prefs read failed: %s", e)
            return None

    def _read_background_capture(self) -> bool | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, _GAME_CONFIG_STORE_KEY, 0, winreg.KEY_READ
            ) as key:
                try:
                    value, _ = winreg.QueryValueEx(key, "GameDVR_Enabled")
                    return bool(value)
                except FileNotFoundError:
                    return None
        except FileNotFoundError:
            return None
        except OSError as e:
            logger.debug("background capture read failed: %s", e)
            return None

    def _detect_active_downloads(self) -> dict[str, str]:
        status: dict[str, str] = {}
        for svc in _DOWNLOAD_RELATED_SERVICES:
            state = self._query_service_state(svc)
            if state is not None:
                status[svc] = state
        return status

    def _query_service_state(self, name: str) -> str | None:
        try:
            proc = subprocess.run(
                ["sc.exe", "query", name],
                capture_output=True,
                text=True,
                timeout=5,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        for line in proc.stdout.splitlines():
            stripped = line.strip().upper()
            if stripped.startswith("STATE"):
                if "RUNNING" in stripped:
                    return "running"
                if "STOPPED" in stripped:
                    return "stopped"
                return stripped.split(":")[-1].strip().lower()
        return None

    def _detect_running_overlays(self) -> list[str]:
        try:
            proc = subprocess.run(
                ["tasklist.exe", "/fo", "csv", "/nh"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return []
        running: set[str] = set()
        for line in proc.stdout.splitlines():
            if not line:
                continue
            # CSV first column is quoted image name.
            first = line.split('","')[0].strip('"').strip()
            lowered = first.lower()
            for hint in _OVERLAY_PROCESS_HINTS:
                if lowered == hint.lower():
                    running.add(hint)
        return sorted(running)

    def _read_nvidia_driver_info(self) -> dict[str, Any] | None:
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=driver_version",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        version = proc.stdout.strip().splitlines()[0] if proc.stdout.strip() else ""
        if not version:
            return None
        return {"driver_version": version}

    def _read_memory_profile(self) -> dict[str, Any] | None:
        try:
            proc = subprocess.run(
                [
                    "wmic",
                    "memorychip",
                    "get",
                    "ConfiguredClockSpeed,Speed",
                    "/format:list",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        speeds: list[int] = []
        configured: list[int] = []
        for line in proc.stdout.splitlines():
            if "=" not in line:
                continue
            key, _, value = line.partition("=")
            value = value.strip()
            if not value.isdigit():
                continue
            if key.strip() == "Speed":
                speeds.append(int(value))
            elif key.strip() == "ConfiguredClockSpeed":
                configured.append(int(value))
        if not speeds or not configured:
            return None
        return {
            "rated_speeds_mhz": speeds,
            "configured_speeds_mhz": configured,
        }

    def _read_resizable_bar(self) -> bool | None:
        try:
            proc = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=resizable_bar",
                    "--format=csv,noheader",
                ],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        text = proc.stdout.strip().splitlines()[0].lower() if proc.stdout.strip() else ""
        if not text:
            return None
        if "enabled" in text:
            return True
        if "disabled" in text:
            return False
        return None

    def _read_directstorage_readiness(self) -> dict[str, Any] | None:
        # DirectStorage 1.1 requires Windows 11 + NVMe + DirectX 12 Ultimate.
        # Full readiness needs the DirectStorage runtime DLLs (dstorage.dll and
        # dstoragecore.dll) and an NVMe drive. We check:
        #   - dstorage.dll presence
        #   - whether the system has an NVMe disk per WMI
        runtime_present = self._directstorage_runtime_present()
        has_nvme = self._has_nvme_disk()
        if runtime_present is None and has_nvme is None:
            return None
        return {
            "runtime_present": runtime_present,
            "nvme_present": has_nvme,
        }

    def _directstorage_runtime_present(self) -> bool | None:
        system32 = os.environ.get("SystemRoot")
        if not system32:
            return None
        candidate = os.path.join(system32, "System32", "dstorage.dll")
        try:
            return os.path.isfile(candidate)
        except OSError:
            return None

    def _has_nvme_disk(self) -> bool | None:
        try:
            proc = subprocess.run(
                ["wmic", "diskdrive", "get", "Model,InterfaceType", "/format:list"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError):
            return None
        text = proc.stdout.lower()
        if not text.strip():
            return None
        return "nvme" in text

    def _read_display_topology(self) -> dict[str, Any] | None:
        try:
            from abso.core.multimon_detector import detect_displays
        except ImportError:
            return None
        try:
            displays = detect_displays()
        except Exception as e:  # detector has a lot of edge cases
            logger.debug("display topology detect failed: %s", e)
            return None
        refresh_rates: list[float] = []
        for disp in displays or []:
            hz = getattr(disp, "refresh_rate_hz", None) or getattr(
                disp, "refresh_hz", None
            )
            if isinstance(hz, (int, float)) and hz > 0:
                refresh_rates.append(float(hz))
        return {
            "count": len(displays) if displays else 0,
            "refresh_rates": refresh_rates,
        }

    # ------------------------------------------------------------------
    # Audit helpers
    # ------------------------------------------------------------------

    def _check_gpu_preferences(
        self, prefs: dict[str, str] | None, issues: list[Issue]
    ) -> None:
        if prefs is None or not prefs:
            return
        default_paths: list[str] = []
        for path, value in prefs.items():
            # Value format is a semicolon-delimited list of "Key=Value" tokens.
            tokens = {
                token.split("=", 1)[0]: token.split("=", 1)[1]
                for token in value.split(";")
                if "=" in token
            }
            pref = tokens.get("GpuPreference", "0")
            if pref == "0":
                default_paths.append(path)
        if default_paths:
            issues.append(
                Issue(
                    title=(
                        f"{len(default_paths)} apps using system-default GPU preference"
                    ),
                    severity="info",
                    current_value="GpuPreference=0",
                    optimal_value="GpuPreference=2 (High performance)",
                    explanation=(
                        "On laptops and some desktops, Windows routes apps using "
                        "the system default GPU preference through the iGPU unless "
                        "explicitly set to High Performance. Per-app GPU preference "
                        "is in Settings > Display > Graphics."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                )
            )

    def _check_background_capture(
        self, enabled: bool | None, issues: list[Issue]
    ) -> None:
        if enabled is True:
            issues.append(
                Issue(
                    title="Background game recording is enabled",
                    severity="warning",
                    current_value="GameDVR_Enabled=1",
                    optimal_value="Disabled",
                    explanation=(
                        "Xbox Game Bar background recording impacts frametime "
                        "consistency even when you are not actively recording. "
                        "Disable via Settings > Gaming > Captures or via the "
                        "per-profile Game DVR toggle in ABSO."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                )
            )

    def _check_active_downloads(
        self, status: dict[str, str] | None, issues: list[Issue]
    ) -> None:
        if not status:
            return
        running = [name for name, state in status.items() if state == "running"]
        if not running:
            return
        # DoSvc (Delivery Optimization) is the main peer-to-peer download service.
        # BITS runs for many benign reasons; only flag when DoSvc or wuauserv
        # are actively running alongside a BITS job.
        notable = [r for r in running if r in ("DoSvc", "wuauserv")]
        if not notable:
            return
        issues.append(
            Issue(
                title="Windows Update / Delivery Optimization services are running",
                severity="info",
                current_value=", ".join(sorted(running)),
                optimal_value="Paused during gaming",
                explanation=(
                    "Active Windows Update or Delivery Optimization transfers "
                    "compete for disk, CPU, and network bandwidth. Pause updates "
                    "or set the current connection to metered before a session."
                ),
                category="diagnostics",
                evidence_tier=EvidenceTier.EMPIRICAL,
            )
        )

    def _check_running_overlays(
        self, overlays: list[str] | None, issues: list[Issue]
    ) -> None:
        if not overlays:
            return
        issues.append(
            Issue(
                title="Capture / overlay processes detected",
                severity="info",
                current_value=", ".join(overlays),
                optimal_value="Disabled during competitive play",
                explanation=(
                    "Overlay apps (Game Bar, Discord overlay, Overwolf, Nahimic, "
                    "etc.) hook the game's present path and can cost frametime "
                    "stability or compatibility. ABSO does not kill user apps; "
                    "this is informational so you can disable their overlays."
                ),
                category="diagnostics",
                evidence_tier=EvidenceTier.EMPIRICAL,
            )
        )

    def _check_nvidia_driver(
        self, info: dict[str, Any] | None, issues: list[Issue]
    ) -> None:
        if not info:
            return
        version = info.get("driver_version") or ""
        if not version:
            return
        # Treat the driver as fresh if the branch number is >= 550 (covers
        # DX12 LLM support added in 551.23). This is a heuristic; the main
        # point is to flag users stuck on very old drivers.
        match = re.match(r"(\d+)\.(\d+)", version)
        if match:
            branch = int(match.group(1))
            if branch < 520:
                issues.append(
                    Issue(
                        title=f"NVIDIA driver branch {branch} is older than recommended",
                        severity="info",
                        current_value=version,
                        optimal_value="Driver branch 550+ (for DX12 Ultra Low Latency Mode)",
                        explanation=(
                            "Older branches lack DX12 Ultra Low Latency Mode (added in "
                            "551.23) and may ship with Reflex/HAGS issues that newer "
                            "drivers have fixed."
                        ),
                        category="diagnostics",
                        evidence_tier=EvidenceTier.VERIFIED,
                    )
                )

    def _check_memory_profile(
        self, profile: dict[str, Any] | None, issues: list[Issue]
    ) -> None:
        if not profile:
            return
        rated = profile.get("rated_speeds_mhz") or []
        configured = profile.get("configured_speeds_mhz") or []
        if not rated or not configured:
            return
        rated_max = max(rated)
        configured_max = max(configured)
        # If configured is significantly below rated, XMP/EXPO is likely off.
        if configured_max and rated_max and configured_max < rated_max * 0.8:
            issues.append(
                Issue(
                    title="RAM appears to be running below its rated speed",
                    severity="info",
                    current_value=f"{configured_max} MT/s (configured)",
                    optimal_value=f"{rated_max} MT/s (rated — enable XMP / EXPO in BIOS)",
                    explanation=(
                        "DDR4 XMP or DDR5 EXPO/DOCP profiles must be enabled in BIOS "
                        "for RAM to run at its advertised speed. ABSO cannot toggle "
                        "BIOS settings; this is a nudge."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                )
            )

    def _check_resizable_bar(
        self, state: bool | None, issues: list[Issue]
    ) -> None:
        if state is False:
            issues.append(
                Issue(
                    title="Resizable BAR is disabled on this GPU",
                    severity="info",
                    current_value="Disabled",
                    optimal_value="Enabled (BIOS + GPU support required)",
                    explanation=(
                        "Resizable BAR (Smart Access Memory) lets the CPU access "
                        "the full VRAM aperture. Modern drivers have per-game "
                        "allowlists; if supported by your motherboard and GPU, "
                        "enable in BIOS (Above 4G Decoding + Re-Size BAR Support)."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.VERIFIED,
                )
            )

    def _check_directstorage(
        self, info: dict[str, Any] | None, issues: list[Issue]
    ) -> None:
        if not info:
            return
        if info.get("nvme_present") is False:
            issues.append(
                Issue(
                    title="No NVMe SSD detected for DirectStorage",
                    severity="info",
                    current_value="No NVMe",
                    optimal_value="NVMe SSD recommended for DirectStorage 1.1 games",
                    explanation=(
                        "DirectStorage 1.1 accelerates GPU-decompressed asset "
                        "streaming but is only effective on NVMe storage. "
                        "SATA SSDs still work but lose the DirectStorage fast path."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.VERIFIED,
                )
            )
        if info.get("runtime_present") is False:
            issues.append(
                Issue(
                    title="DirectStorage runtime DLL not found",
                    severity="info",
                    current_value="dstorage.dll missing in System32",
                    optimal_value="Runtime present (ships with Windows 11 and games)",
                    explanation=(
                        "DirectStorage 1.1 needs dstorage.dll / dstoragecore.dll. "
                        "Most DirectStorage-enabled games ship the runtime; if a "
                        "game reports missing DirectStorage, verify the game's "
                        "redistributable install."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                )
            )

    def _check_display_topology(
        self, topology: dict[str, Any] | None, issues: list[Issue]
    ) -> None:
        if not topology:
            return
        refresh_rates = topology.get("refresh_rates") or []
        if len(refresh_rates) < 2:
            return
        # Round to integer Hz before comparing so 59.94/60 etc. don't trip.
        rounded = sorted({int(round(hz)) for hz in refresh_rates})
        if len(rounded) > 1:
            issues.append(
                Issue(
                    title="Mixed refresh rates across active displays",
                    severity="info",
                    current_value=", ".join(f"{hz}Hz" for hz in rounded),
                    optimal_value="Match the gaming display's refresh rate, or disable secondary displays",
                    explanation=(
                        "Mixed-refresh multi-monitor setups can cost frametime "
                        "stability and VRR reliability on the primary gaming "
                        "display. If you play on one monitor, consider switching "
                        "non-gaming monitors off or matching refresh rates."
                    ),
                    category="diagnostics",
                    evidence_tier=EvidenceTier.EMPIRICAL,
                )
            )


def estimate_driver_age_days(version: str, reference: datetime | None = None) -> int | None:
    """Heuristic driver-age estimator.

    NVIDIA driver versions do not carry a date. This helper exists so tests
    can hook in a reference point if they ever need to; right now it simply
    reports how far in the past a branch number sits based on the crude
    "one branch per ~3 months" rhythm NVIDIA has used for several years.
    """
    if not version:
        return None
    match = re.match(r"(\d+)\.(\d+)", version)
    if not match:
        return None
    ref = reference or datetime.now(timezone.utc)
    branch = int(match.group(1))
    # Base: branch 550 ~ early 2024. This is deliberately imprecise; the
    # audit check above only fires when branch < 520, so this helper is a
    # placeholder for future refinement.
    base_branch = 550
    base_date = datetime(2024, 1, 15, tzinfo=timezone.utc)
    delta_branches = base_branch - branch
    approx = base_date.timestamp() - delta_branches * 90 * 24 * 3600
    approx_dt = datetime.fromtimestamp(approx, tz=timezone.utc)
    return max((ref - approx_dt).days, 0)
