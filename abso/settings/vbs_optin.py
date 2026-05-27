"""Opt-in max-performance flow for VBS / HVCI / Virtual Machine Platform.

Disabling Virtualization-Based Security (VBS), Hypervisor-Enforced Code
Integrity (HVCI / Memory Integrity), and Virtual Machine Platform (VMP) can
recover measurable gaming performance on some hardware/workload combinations,
but it reduces the system's security posture: Credential Guard, Memory
Integrity, and several hypervisor-protected code paths depend on these
features.

Design rules for this module (enforced by tests):

1. **Never silent.** No built-in gaming profile is allowed to use this handler.
   The handler refuses to apply a disable unless the caller passes the
   explicit ``acknowledge_security_tradeoff=True`` flag.
2. **Reboot required.** Toggling HVCI's ``Enabled`` flag, flipping VMP, or
   changing ``hypervisorlaunchtype`` always requires a reboot to take effect.
3. **Reversible.** Backup captures every touched registry value and optional
   feature state; restore writes them back verbatim.
4. **Audit-only by default.** Callers who don't opt in get the current state
   surfaced as an informational Issue and nothing else.

The target user is a single enthusiast gamer who has read the security
tradeoff and explicitly wants to disable these features on a dedicated
gaming machine.
"""

from __future__ import annotations

import logging
import subprocess
import winreg
from typing import Any

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class VBSOptInHandler(SettingsHandler):
    """Opt-in handler for VBS / HVCI / VMP / hypervisor launch state.

    The handler never mutates state unless the caller passes
    ``acknowledge_security_tradeoff=True`` in the settings dict. Missing
    the acknowledgement is a soft refusal, not an error — the result
    surfaces a notice and returns ``success=True`` without touching
    anything.
    """

    HVCI_KEY = (
        r"SYSTEM\CurrentControlSet\Control\DeviceGuard"
        r"\Scenarios\HypervisorEnforcedCodeIntegrity"
    )
    DEVICE_GUARD_KEY = r"SYSTEM\CurrentControlSet\Control\DeviceGuard"

    ACK_KEY = "acknowledge_security_tradeoff"

    def detect(self) -> dict[str, Any]:
        """Detect current HVCI, VBS platform security flags, and VMP state."""
        result: dict[str, Any] = {
            "hvci_enabled": self._read_hvci_enabled(),
            "platform_security_features": self._read_platform_security_features(),
            "vbs_running": self._read_vbs_running_state(),
            "hypervisor_launch_type": self._read_hypervisor_launch_type(),
            "vmp_feature_enabled": self._read_vmp_feature_enabled(),
        }
        return result

    def audit(self) -> list[Issue]:
        """Surface opt-in status only — never grade VBS enabled as a problem."""
        current = self.detect()
        issues: list[Issue] = []

        hvci = current.get("hvci_enabled")
        if hvci is True:
            issues.append(
                Issue(
                    title="Memory Integrity (HVCI) is enabled",
                    severity="info",
                    current_value="Enabled",
                    optimal_value="Enabled (security tradeoff — opt-in disable available)",
                    explanation=(
                        "HVCI (Hypervisor-Enforced Code Integrity) can cost measurable "
                        "gaming FPS on some CPUs. Disabling it requires an explicit "
                        "opt-in through the VBS max-performance flow and a reboot. "
                        "ABSO will never toggle this silently."
                    ),
                    category="vbs",
                    evidence_tier=EvidenceTier.EXPERIMENTAL,
                )
            )

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply VBS/HVCI/VMP changes only when explicitly acknowledged."""
        # Require the acknowledgement to be the literal boolean True.
        # Accepting any truthy value would let a stray string like "false"
        # silently bypass the gate.
        ack = settings.get(self.ACK_KEY) is True
        disable_hvci = bool(settings.get("disable_hvci"))
        disable_vmp = bool(settings.get("disable_vmp"))
        disable_hypervisor_launch = bool(settings.get("disable_hypervisor_launch"))

        if not any((disable_hvci, disable_vmp, disable_hypervisor_launch)):
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": [],
                "notices": [
                    "VBSOptInHandler received no disable flags; nothing changed."
                ],
            }

        if not ack:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": [],
                "notices": [
                    "VBSOptInHandler refused to apply: "
                    f"{self.ACK_KEY}=True is required so the caller confirms "
                    "the security tradeoff. Built-in profiles never set this; "
                    "only the explicit max-performance flow does."
                ],
            }

        applied: list[str] = []
        errors: list[str] = []
        notices: list[str] = [
            "VBSOptInHandler disabled security features. A REBOOT is required "
            "for changes to take effect. Use the ABSO restore flow to re-enable."
        ]

        if disable_hvci:
            try:
                self._write_hvci_enabled(False)
                applied.append("HVCI.Enabled=0")
            except OSError as e:
                errors.append(f"HVCI disable: {e}")

        if disable_hypervisor_launch:
            try:
                self._set_hypervisor_launch_type("off")
                applied.append("hypervisorlaunchtype=off")
            except (OSError, subprocess.SubprocessError) as e:
                errors.append(f"hypervisorlaunchtype: {e}")

        if disable_vmp:
            try:
                self._disable_vmp_optional_feature()
                applied.append("VirtualMachinePlatform=disabled")
            except (OSError, subprocess.SubprocessError) as e:
                errors.append(f"Virtual Machine Platform: {e}")

        return {
            "success": not errors,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": True,
            "applied": applied,
            "notices": notices,
        }

    def backup(self) -> dict[str, Any]:
        """Capture everything we might touch, verbatim."""
        return {
            "hvci_enabled": self._read_hvci_enabled(),
            "platform_security_features": self._read_platform_security_features(),
            "hypervisor_launch_type": self._read_hypervisor_launch_type(),
            "vmp_feature_enabled": self._read_vmp_feature_enabled(),
        }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore HVCI / hypervisor / VMP state from backup."""
        try:
            hvci = data.get("hvci_enabled")
            if hvci is not None:
                self._write_hvci_enabled(bool(hvci))

            launch = data.get("hypervisor_launch_type")
            if launch is not None:
                self._set_hypervisor_launch_type(str(launch))

            vmp = data.get("vmp_feature_enabled")
            if vmp is True:
                self._enable_vmp_optional_feature()
            elif vmp is False:
                self._disable_vmp_optional_feature()
        except (OSError, subprocess.SubprocessError) as e:
            logger.error("VBSOptInHandler restore failed: %s", e)
            return False
        return True

    # ------------------------------------------------------------------
    # Registry / BCD / OptionalFeatures primitives
    # ------------------------------------------------------------------

    def _read_hvci_enabled(self) -> bool | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, self.HVCI_KEY, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, "Enabled")
                return bool(value)
        except FileNotFoundError:
            return None
        except OSError as e:
            logger.debug("HVCI read failed: %s", e)
            return None

    def _write_hvci_enabled(self, enabled: bool) -> None:
        with winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE, self.HVCI_KEY, 0, winreg.KEY_ALL_ACCESS
        ) as key:
            winreg.SetValueEx(
                key, "Enabled", 0, winreg.REG_DWORD, 1 if enabled else 0
            )

    def _read_platform_security_features(self) -> list[int] | None:
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, self.DEVICE_GUARD_KEY, 0, winreg.KEY_READ
            ) as key:
                value, _ = winreg.QueryValueEx(key, "RequiredSecurityProperties")
                return list(value) if isinstance(value, list | tuple) else [int(value)]
        except FileNotFoundError:
            return None
        except OSError:
            return None

    def _read_vbs_running_state(self) -> bool | None:
        """Best-effort detection of whether VBS is actually running.

        There is no stable registry key for 'VBS is currently running'; it
        depends on DeviceGuard policy, hypervisor launch state, and hardware.
        We return None and let upstream callers fall back to the individual
        flags rather than pretending we know more than we do.
        """
        return None

    def _read_hypervisor_launch_type(self) -> str | None:
        try:
            proc = subprocess.run(
                ["bcdedit", "/enum", "{current}"],
                capture_output=True,
                text=True,
                timeout=10,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("bcdedit read failed: %s", e)
            return None

        for line in proc.stdout.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("hypervisorlaunchtype"):
                parts = stripped.split()
                if len(parts) >= 2:
                    return parts[-1]
        return None

    def _set_hypervisor_launch_type(self, value: str) -> None:
        value = value.strip().lower()
        if value not in {"auto", "off"}:
            raise ValueError(f"hypervisorlaunchtype must be 'auto' or 'off', got {value!r}")
        subprocess.run(
            ["bcdedit", "/set", "hypervisorlaunchtype", value],
            check=True,
            capture_output=True,
            text=True,
            timeout=15,
        )

    def _read_vmp_feature_enabled(self) -> bool | None:
        try:
            proc = subprocess.run(
                [
                    "dism.exe",
                    "/online",
                    "/get-featureinfo",
                    "/featurename:VirtualMachinePlatform",
                ],
                capture_output=True,
                text=True,
                timeout=20,
                check=False,
            )
        except (OSError, subprocess.SubprocessError) as e:
            logger.debug("dism VMP read failed: %s", e)
            return None

        for line in proc.stdout.splitlines():
            stripped = line.strip().lower()
            if stripped.startswith("state"):
                if "enabled" in stripped:
                    return True
                if "disabled" in stripped:
                    return False
        return None

    def _disable_vmp_optional_feature(self) -> None:
        subprocess.run(
            [
                "dism.exe",
                "/online",
                "/disable-feature",
                "/featurename:VirtualMachinePlatform",
                "/norestart",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )

    def _enable_vmp_optional_feature(self) -> None:
        subprocess.run(
            [
                "dism.exe",
                "/online",
                "/enable-feature",
                "/featurename:VirtualMachinePlatform",
                "/norestart",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=60,
        )
