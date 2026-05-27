"""BIOS/firmware detection module.

Detects gaming-relevant BIOS and firmware settings via WMI and registry
queries. All operations are READ-ONLY -- no system modifications are made.

Detects:
- Resizable BAR (ReBAR) status
- XMP/EXPO memory profile status
- Virtualization-Based Security (VBS) and Memory Integrity
- Secure Boot state
- TPM presence and version
"""

from __future__ import annotations

import contextlib
import logging
import winreg
from dataclasses import dataclass, field
from datetime import date
from typing import Literal

from abso.core.exceptions import RegistryReadError
from abso.core.models import EvidenceTier
from abso.utils.registry import read_registry_dword, read_registry_value

logger = logging.getLogger(__name__)

# GPU class GUID for display adapters
_GPU_CLASS_GUID = r"SYSTEM\CurrentControlSet\Control\Class\{4d36e968-e325-11ce-bfc1-08002be10318}"

# DeviceGuard registry paths
_DEVICE_GUARD_KEY = r"SYSTEM\CurrentControlSet\Control\DeviceGuard"
_HVCI_KEY = r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity"

# Secure Boot registry paths.
# State: whether Secure Boot is on at all.
# Servicing: post-KB5089549 (May 2026) rollout of the PCA2023 / UEFI CA 2023
#            certificates that supersede the 2011 certs expiring June 2026.
_SECURE_BOOT_KEY = r"SYSTEM\CurrentControlSet\Control\SecureBoot\State"
_SECURE_BOOT_SERVICING_KEY = r"SYSTEM\CurrentControlSet\Control\SecureBoot\Servicing"

# The original 2011 Secure Boot certs expire starting June 2026. ABSO escalates
# the cert warning from informational to critical once we are inside the
# rollout window.
SECURE_BOOT_CERT_EXPIRY_DATE = date(2026, 6, 1)

# JEDEC base speeds (MHz) for DDR generations.
# If the current speed matches one of these, XMP/EXPO is likely not active.
_DDR4_JEDEC_SPEEDS: set[int] = {2133, 2400, 2666, 2933, 3200}
_DDR5_JEDEC_SPEEDS: set[int] = {4800, 5600}


@dataclass(frozen=True)
class BiosRecommendation:
    """A single BIOS/firmware recommendation for gaming optimization."""

    title: str
    explanation: str
    impact: Literal["high", "medium", "low"]
    evidence_tier: EvidenceTier
    current_value: str
    recommended_value: str


CertRolloutStatus = Literal[
    "updated",
    "updated_reboot_pending",
    "pending",
    "not_applicable",
    "unknown",
]


@dataclass(frozen=True)
class SecureBootCertState:
    """Snapshot of the June 2026 Secure Boot certificate rollout.

    Microsoft is replacing the 2011 PCA / UEFI CA certificates with
    PCA2023 / UEFI CA 2023 ahead of the original certs' expiry in June 2026.
    Devices that fail to receive the new certs may lose the ability to boot
    signed components after expiry.

    The progress is exposed via ``SecureBoot\\Servicing`` registry values
    populated by KB5089549 (May 2026) and later cumulatives. Field names
    mirror the raw registry values so future debugging is grep-able.
    """

    enabled: Literal["enabled", "disabled", "unknown"]
    capable: int | None  # WindowsUEFICA2023Capable (0/1/2)
    status_raw: str | None  # UEFICA2023Status: "Updated" | "Pending" | ...
    reboot_pending: bool  # RebootRequested3POROMDB == 1
    confidence: str | None  # "High Confidence" etc. — Microsoft's targeting signal
    rollout_status: CertRolloutStatus

    @property
    def needs_action(self) -> bool:
        """Whether the user should take action before the cert expiry window."""
        return self.rollout_status in {"pending", "updated_reboot_pending", "unknown"}


@dataclass
class BiosFirmwareInfo:
    """Aggregated BIOS/firmware detection results."""

    # Resizable BAR
    rebar_status: Literal["enabled", "disabled", "unknown"] = "unknown"

    # XMP / EXPO memory profile
    memory_profile: Literal["xmp_enabled", "xmp_disabled_likely", "unknown"] = "unknown"
    rated_speed_mhz: int | None = None
    current_speed_mhz: int | None = None

    # Virtualization-Based Security
    vbs_status: Literal["enabled", "disabled"] = "disabled"
    memory_integrity: Literal["enabled", "disabled"] = "disabled"

    # Secure Boot
    secure_boot: Literal["enabled", "disabled", "unknown"] = "unknown"
    secure_boot_cert: SecureBootCertState | None = None

    # TPM
    tpm_present: bool = False
    tpm_version: str | None = None

    # Raw recommendations (populated by BiosDetector.get_recommendations)
    recommendations: list[BiosRecommendation] = field(default_factory=list)


class BiosDetector:
    """Detects gaming-relevant BIOS/firmware settings.

    Uses WMI and Windows registry queries. All operations are read-only.
    """

    def __init__(self) -> None:
        self._wmi = None
        self._info: BiosFirmwareInfo | None = None

    def __del__(self) -> None:
        self.cleanup()

    def cleanup(self) -> None:
        """Release WMI connection resources."""
        if self._wmi is not None:
            self._wmi = None

    # ------------------------------------------------------------------
    # WMI helpers
    # ------------------------------------------------------------------

    def _get_wmi(self):
        """Lazy-load default WMI connection (root\\cimv2)."""
        if self._wmi is None:
            try:
                import wmi
                self._wmi = wmi.WMI()
            except ImportError:
                logger.warning("WMI module not available")
            except AttributeError as e:
                logger.error("WMI initialization error: %s", e)
            except RuntimeError as e:
                logger.error("WMI connection failed: %s", e)
        return self._wmi

    def _get_wmi_tpm(self):
        """Return a WMI connection to the MicrosoftTpm namespace.

        Win32_Tpm lives in root\\cimv2\\Security\\MicrosoftTpm and
        requires a separate WMI connection.
        """
        try:
            import wmi
            return wmi.WMI(namespace=r"root\cimv2\Security\MicrosoftTpm")
        except ImportError:
            logger.warning("WMI module not available for TPM query")
        except AttributeError as e:
            logger.error("WMI TPM initialization error: %s", e)
        except RuntimeError as e:
            logger.error("WMI TPM connection failed: %s", e)
        except Exception as e:
            # TPM namespace may not exist on all systems
            logger.debug("TPM WMI namespace unavailable: %s", e)
        return None

    # ------------------------------------------------------------------
    # Registry helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _read_reg_dword(
        hive: int,
        subkey: str,
        value_name: str,
    ) -> int | None:
        """Read a DWORD value from the registry.

        Thin wrapper over :func:`abso.utils.registry.read_registry_dword`
        that demotes permission/OS errors to ``None`` so best-effort BIOS
        detection never throws upward. Missing keys/values also return
        ``None`` via the default.
        """
        try:
            return read_registry_dword(hive, subkey, value_name, default=None)
        except RegistryReadError as exc:
            logger.debug("Registry DWORD read failed for %s\\%s: %s", subkey, value_name, exc)
            return None

    @staticmethod
    def _read_reg_value(
        hive: int,
        subkey: str,
        value_name: str,
    ) -> object | None:
        """Read any registry value (returns ``None`` on failure or absence)."""
        try:
            return read_registry_value(hive, subkey, value_name, default=None)
        except RegistryReadError as exc:
            logger.debug("Registry read failed for %s\\%s: %s", subkey, value_name, exc)
            return None

    # ------------------------------------------------------------------
    # Detection methods
    # ------------------------------------------------------------------

    def detect_rebar(self) -> Literal["enabled", "disabled", "unknown"]:
        """Detect Resizable BAR (ReBAR) status.

        Checks the GPU class registry key for LargeMemoryRange or ReBarState
        values, then falls back to WMI PnP entity BAR size heuristic.

        Returns:
            "enabled", "disabled", or "unknown".
        """
        # Strategy 1: Registry — GPU adapter subkey 0000
        subkey = f"{_GPU_CLASS_GUID}\\0000"

        rebar_state = self._read_reg_dword(
            winreg.HKEY_LOCAL_MACHINE, subkey, "ReBarState",
        )
        if rebar_state is not None:
            return "enabled" if rebar_state != 0 else "disabled"

        large_mem = self._read_reg_value(
            winreg.HKEY_LOCAL_MACHINE, subkey, "LargeMemoryRange",
        )
        if large_mem is not None:
            # LargeMemoryRange is typically a QWORD; non-zero means enabled
            try:
                return "enabled" if int(large_mem) > 0 else "disabled"
            except (ValueError, TypeError):
                pass

        # Strategy 2: Check additional adapter subkeys (0001, 0002, etc.)
        for idx in range(1, 4):
            idx_subkey = f"{_GPU_CLASS_GUID}\\{idx:04d}"
            rebar_val = self._read_reg_dword(
                winreg.HKEY_LOCAL_MACHINE, idx_subkey, "ReBarState",
            )
            if rebar_val is not None:
                return "enabled" if rebar_val != 0 else "disabled"

        # Strategy 3: WMI — look for GPU PnP entities with large BAR
        wmi_conn = self._get_wmi()
        if wmi_conn:
            try:
                gpus = wmi_conn.Win32_PnPEntity(
                    PNPClass="Display",
                )
                for gpu in gpus:
                    # Check for memory resources that indicate large BAR
                    try:
                        resources = gpu.associators(
                            wmi_result_class="Win32_DeviceMemoryAddress",
                        )
                        for res in resources:
                            start = getattr(res, "StartingAddress", None)
                            end = getattr(res, "EndingAddress", None)
                            if start is not None and end is not None:
                                size_bytes = int(end) - int(start)
                                # BAR > 256MB strongly suggests ReBAR is enabled
                                if size_bytes > 256 * 1024 * 1024:
                                    return "enabled"
                    except Exception as e:
                        logger.debug("WMI GPU BAR size query failed: %s", e)
            except Exception as e:
                logger.debug("WMI PnP GPU query failed: %s", e)

        return "unknown"

    def detect_xmp(
        self,
    ) -> tuple[
        Literal["xmp_enabled", "xmp_disabled_likely", "unknown"],
        int | None,
        int | None,
    ]:
        """Detect XMP/EXPO memory profile status.

        Compares Win32_PhysicalMemory Speed (rated) vs ConfiguredClockSpeed
        (current). If the current speed matches a JEDEC base speed and the
        rated speed is higher, XMP/EXPO is likely not enabled.

        Returns:
            Tuple of (profile_status, rated_speed_mhz, current_speed_mhz).
        """
        wmi_conn = self._get_wmi()
        if not wmi_conn:
            return ("unknown", None, None)

        try:
            sticks = wmi_conn.Win32_PhysicalMemory()
        except Exception as e:
            logger.debug("WMI PhysicalMemory query failed: %s", e)
            return ("unknown", None, None)

        if not sticks:
            return ("unknown", None, None)

        # Use the first stick as representative (kits are normally matched)
        stick = sticks[0]

        rated_speed: int | None = None
        current_speed: int | None = None

        raw_speed = getattr(stick, "Speed", None)
        if raw_speed is not None:
            with contextlib.suppress(ValueError, TypeError):
                rated_speed = int(raw_speed)

        raw_configured = getattr(stick, "ConfiguredClockSpeed", None)
        if raw_configured is not None:
            with contextlib.suppress(ValueError, TypeError):
                current_speed = int(raw_configured)

        if rated_speed is None or current_speed is None:
            return ("unknown", rated_speed, current_speed)

        # Determine DDR generation from speed ranges
        jedec_speeds = _DDR4_JEDEC_SPEEDS | _DDR5_JEDEC_SPEEDS

        # If current speed exceeds rated, it is overclocked (XMP/EXPO active)
        if current_speed > rated_speed:
            return ("xmp_enabled", rated_speed, current_speed)

        # If current matches rated and both exceed JEDEC base → XMP active
        if current_speed == rated_speed and current_speed not in jedec_speeds:
            return ("xmp_enabled", rated_speed, current_speed)

        # Current matches a JEDEC base speed but rated is higher → not enabled
        if current_speed in jedec_speeds and rated_speed > current_speed:
            return ("xmp_disabled_likely", rated_speed, current_speed)

        # Current matches rated and is a JEDEC speed — ambiguous but normal
        if current_speed == rated_speed and current_speed in jedec_speeds:
            # Could be a non-XMP kit running at rated JEDEC speed
            return ("unknown", rated_speed, current_speed)

        return ("unknown", rated_speed, current_speed)

    def detect_vbs(self) -> tuple[Literal["enabled", "disabled"], Literal["enabled", "disabled"]]:
        """Detect Virtualization-Based Security and Memory Integrity (HVCI).

        Returns:
            Tuple of (vbs_status, memory_integrity_status).
        """
        vbs_val = self._read_reg_dword(
            winreg.HKEY_LOCAL_MACHINE,
            _DEVICE_GUARD_KEY,
            "EnableVirtualizationBasedSecurity",
        )
        vbs_status: Literal["enabled", "disabled"] = (
            "enabled" if vbs_val is not None and vbs_val != 0 else "disabled"
        )

        hvci_val = self._read_reg_dword(
            winreg.HKEY_LOCAL_MACHINE,
            _HVCI_KEY,
            "Enabled",
        )
        memory_integrity: Literal["enabled", "disabled"] = (
            "enabled" if hvci_val is not None and hvci_val != 0 else "disabled"
        )

        return (vbs_status, memory_integrity)

    def detect_secure_boot(self) -> Literal["enabled", "disabled", "unknown"]:
        """Detect Secure Boot state from registry.

        Returns:
            "enabled", "disabled", or "unknown".
        """
        val = self._read_reg_dword(
            winreg.HKEY_LOCAL_MACHINE,
            _SECURE_BOOT_KEY,
            "UEFISecureBootEnabled",
        )
        if val is None:
            return "unknown"
        return "enabled" if val == 1 else "disabled"

    def detect_secure_boot_cert_state(
        self,
        secure_boot: Literal["enabled", "disabled", "unknown"] | None = None,
    ) -> SecureBootCertState:
        """Detect the June 2026 Secure Boot cert rollout state.

        Reads ``HKLM\\SYSTEM\\CurrentControlSet\\Control\\SecureBoot\\Servicing``
        for the PCA2023 / UEFI CA 2023 enrollment signals published by
        KB5089549 (May 2026) and later cumulatives.

        Args:
            secure_boot: Pre-detected Secure Boot enable state, to avoid an
                extra registry read when callers already have it.
        """
        sb_state: Literal["enabled", "disabled", "unknown"] = (
            secure_boot if secure_boot is not None else self.detect_secure_boot()
        )

        capable = self._read_reg_dword(
            winreg.HKEY_LOCAL_MACHINE,
            _SECURE_BOOT_SERVICING_KEY,
            "WindowsUEFICA2023Capable",
        )
        status_raw_obj = self._read_reg_value(
            winreg.HKEY_LOCAL_MACHINE,
            _SECURE_BOOT_SERVICING_KEY,
            "UEFICA2023Status",
        )
        status_raw = str(status_raw_obj) if status_raw_obj is not None else None
        confidence_obj = self._read_reg_value(
            winreg.HKEY_LOCAL_MACHINE,
            _SECURE_BOOT_SERVICING_KEY,
            "ConfidenceLevel",
        )
        confidence = str(confidence_obj) if confidence_obj is not None else None
        reboot_dword = self._read_reg_dword(
            winreg.HKEY_LOCAL_MACHINE,
            _SECURE_BOOT_SERVICING_KEY,
            "RebootRequested3POROMDB",
        )
        reboot_pending = bool(reboot_dword) if reboot_dword is not None else False

        rollout_status: CertRolloutStatus
        if sb_state == "disabled":
            rollout_status = "not_applicable"
        elif status_raw is None and capable is None:
            rollout_status = "unknown"
        elif status_raw is not None and status_raw.strip().lower() == "updated":
            rollout_status = (
                "updated_reboot_pending" if reboot_pending else "updated"
            )
        else:
            rollout_status = "pending"

        return SecureBootCertState(
            enabled=sb_state,
            capable=capable,
            status_raw=status_raw,
            reboot_pending=reboot_pending,
            confidence=confidence,
            rollout_status=rollout_status,
        )

    def detect_tpm(self) -> tuple[bool, str | None]:
        """Detect TPM presence and version via WMI.

        Queries Win32_Tpm in the root\\cimv2\\Security\\MicrosoftTpm namespace.

        Returns:
            Tuple of (tpm_present, tpm_version).
        """
        tpm_conn = self._get_wmi_tpm()
        if not tpm_conn:
            return (False, None)

        try:
            tpm_instances = tpm_conn.Win32_Tpm()
        except Exception as e:
            logger.debug("WMI Win32_Tpm query failed: %s", e)
            return (False, None)

        if not tpm_instances:
            return (False, None)

        tpm = tpm_instances[0]
        version: str | None = None

        spec_version = getattr(tpm, "SpecVersion", None)
        if spec_version:
            # SpecVersion is typically "2.0, 0, 1.59" — extract major version
            try:
                version = str(spec_version).split(",")[0].strip()
            except (IndexError, AttributeError):
                version = str(spec_version)

        return (True, version)

    # ------------------------------------------------------------------
    # Aggregate detection
    # ------------------------------------------------------------------

    def detect_all(self) -> BiosFirmwareInfo:
        """Run all BIOS/firmware detection checks.

        Results are cached on the instance. Call again to refresh.

        Returns:
            BiosFirmwareInfo with all detected settings populated.
        """
        rebar_status = self.detect_rebar()

        memory_profile, rated_speed, current_speed = self.detect_xmp()

        vbs_status, memory_integrity = self.detect_vbs()

        secure_boot = self.detect_secure_boot()
        secure_boot_cert = self.detect_secure_boot_cert_state(secure_boot)

        tpm_present, tpm_version = self.detect_tpm()

        self._info = BiosFirmwareInfo(
            rebar_status=rebar_status,
            memory_profile=memory_profile,
            rated_speed_mhz=rated_speed,
            current_speed_mhz=current_speed,
            vbs_status=vbs_status,
            memory_integrity=memory_integrity,
            secure_boot=secure_boot,
            secure_boot_cert=secure_boot_cert,
            tpm_present=tpm_present,
            tpm_version=tpm_version,
        )

        return self._info

    # ------------------------------------------------------------------
    # Recommendations
    # ------------------------------------------------------------------

    def get_recommendations(
        self,
        info: BiosFirmwareInfo | None = None,
        has_nvidia_gpu: bool = False,
    ) -> list[BiosRecommendation]:
        """Generate gaming optimization recommendations from firmware state.

        Args:
            info: Pre-existing detection results. If None, runs detect_all().
            has_nvidia_gpu: Whether an NVIDIA GPU was detected by the hardware
                detector. Enables ReBAR-specific NVIDIA guidance.

        Returns:
            List of BiosRecommendation sorted by impact (high first).
        """
        if info is None:
            info = self._info if self._info is not None else self.detect_all()

        recommendations: list[BiosRecommendation] = []

        # ReBAR recommendation
        if info.rebar_status == "disabled":
            explanation = (
                "Resizable BAR allows the CPU to access the full GPU VRAM in "
                "a single mapping, reducing overhead for texture and buffer "
                "transfers. Most modern GPUs and motherboards support this."
            )
            if has_nvidia_gpu:
                explanation += (
                    " NVIDIA requires both ReBAR enabled in BIOS and the "
                    "'ReBAR' toggle set to ON in the NVIDIA Control Panel."
                )
            recommendations.append(BiosRecommendation(
                title="Enable Resizable BAR (ReBAR) in BIOS",
                explanation=explanation,
                impact="medium",
                evidence_tier=EvidenceTier.VERIFIED,
                current_value="disabled",
                recommended_value="enabled",
            ))

        # XMP / EXPO recommendation
        if info.memory_profile == "xmp_disabled_likely":
            speed_detail = ""
            if info.current_speed_mhz and info.rated_speed_mhz:
                speed_detail = (
                    f" Your RAM is rated for {info.rated_speed_mhz} MHz but "
                    f"currently running at {info.current_speed_mhz} MHz "
                    f"(JEDEC default)."
                )
            recommendations.append(BiosRecommendation(
                title="Enable XMP/EXPO memory profile in BIOS",
                explanation=(
                    "Your memory appears to be running at JEDEC base speed "
                    f"instead of its rated XMP/EXPO speed.{speed_detail} Enabling "
                    "XMP (Intel) or EXPO (AMD) in BIOS is free performance "
                    "-- typically 5-15% improvement in CPU-bound scenarios "
                    "and minimum frame times."
                ),
                impact="high",
                evidence_tier=EvidenceTier.VERIFIED,
                current_value=f"{info.current_speed_mhz} MHz (JEDEC base)",
                recommended_value=f"{info.rated_speed_mhz} MHz (XMP/EXPO rated)",
            ))

        # VBS / Memory Integrity recommendation
        if info.vbs_status == "enabled" or info.memory_integrity == "enabled":
            parts: list[str] = []
            if info.vbs_status == "enabled":
                parts.append("VBS")
            if info.memory_integrity == "enabled":
                parts.append("Memory Integrity (HVCI)")
            feature_str = " and ".join(parts)

            recommendations.append(BiosRecommendation(
                title=f"Disable {feature_str} for gaming",
                explanation=(
                    f"{feature_str} {'is' if len(parts) == 1 else 'are'} "
                    "currently enabled. Microsoft's own documentation "
                    "acknowledges a 5-10% FPS impact from Memory Integrity "
                    "due to hypervisor-enforced code integrity checks on "
                    "every kernel driver load. For a dedicated gaming system, "
                    "disabling these provides measurable frame time "
                    "improvement. Requires reboot after change."
                ),
                impact="high",
                evidence_tier=EvidenceTier.VERIFIED,
                current_value=f"{feature_str} enabled",
                recommended_value=f"{feature_str} disabled",
            ))

        # Secure Boot cert rollout (June 2026 expiry)
        cert_rec = self._secure_boot_cert_recommendation(info.secure_boot_cert)
        if cert_rec is not None:
            recommendations.append(cert_rec)

        # Sort by impact: high > medium > low
        impact_order = {"high": 0, "medium": 1, "low": 2}
        recommendations.sort(key=lambda r: impact_order.get(r.impact, 3))

        # Attach to info for convenience
        info.recommendations = recommendations

        return recommendations

    @staticmethod
    def _secure_boot_cert_recommendation(
        cert: SecureBootCertState | None,
        today: date | None = None,
    ) -> BiosRecommendation | None:
        """Build a recommendation for the 2026 Secure Boot cert rollout.

        Surfaces:
          * ``updated_reboot_pending`` → user must reboot to finalize the
            cert install. High impact within the expiry window.
          * ``pending`` / ``unknown`` → cert has not yet been delivered. The
            user should let Windows Update run before the expiry date.
        """
        if cert is None:
            return None
        if cert.enabled == "disabled":
            return None
        if cert.rollout_status in ("not_applicable", "updated"):
            return None

        current = today or date.today()
        in_expiry_window = current >= SECURE_BOOT_CERT_EXPIRY_DATE
        impact: Literal["high", "medium", "low"] = "high" if in_expiry_window else "medium"

        if cert.rollout_status == "updated_reboot_pending":
            title = "Reboot to finalize new Secure Boot certificates"
            explanation = (
                "Windows has delivered the PCA2023 / UEFI CA 2023 "
                "certificates that replace the 2011 Secure Boot certs "
                "expiring in June 2026, but a reboot is required to commit "
                "the change. Without it, signed boot components may stop "
                "loading once the 2011 certs expire."
            )
            current_value = "Updated - reboot pending"
            recommended = "Reboot to finalize cert installation"
        else:
            title = "Pending Secure Boot certificate rollout"
            explanation = (
                "The 2011 Secure Boot certificates begin expiring in June "
                "2026. Microsoft is rolling out replacement certificates via "
                "Windows Update. This device has not yet been confirmed as "
                "having received them. Keep Windows Update enabled; the "
                "rollout is signal-driven and may take additional update "
                "cycles to reach this device."
            )
            current_value = cert.status_raw or "Not yet delivered"
            recommended = "Updated"

        return BiosRecommendation(
            title=title,
            explanation=explanation,
            impact=impact,
            evidence_tier=EvidenceTier.VERIFIED,
            current_value=current_value,
            recommended_value=recommended,
        )
