"""Hyper-V root-partition (hypervisorlaunchtype) audit handler.

Even with VBS/HVCI off, the Windows hypervisor root partition can remain active
when ``hypervisorlaunchtype`` is ``Auto``, adding scheduling overhead with no
security benefit. This is an AUDIT-ONLY surface: ABSO reports the condition but
never runs ``bcdedit`` itself (a BCD edit is reboot-gated and changes the
security posture, so it stays a user decision).

The finding only fires when the hypervisor is set to launch AND VBS is not
actually running - i.e. the root partition is paying its cost for nothing.
"""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.utils.proc import no_window_creationflags

logger = logging.getLogger(__name__)


class HypervisorAuditHandler(SettingsHandler):
    """Detect-only: flag an idle Hyper-V root partition (no VBS) as overhead."""

    def detect(self) -> dict[str, Any]:
        """Return hypervisorlaunchtype + whether VBS is actually running."""
        return {
            "hypervisor_launch_type": self._get_hypervisor_launch_type(),
            "vbs_running": self._get_vbs_running(),
        }

    def audit(self) -> list[Issue]:
        """Flag a launching hypervisor when VBS is not running."""
        issues: list[Issue] = []
        current = self.detect()
        launch_type = current.get("hypervisor_launch_type")
        vbs_running = current.get("vbs_running")

        launching = isinstance(launch_type, str) and launch_type.lower() in {"auto", "on"}
        # Only flag when we positively know VBS is NOT running (False). Unknown
        # (None) stays silent to avoid nagging when detection was inconclusive.
        if launching and vbs_running is False:
            issues.append(
                Issue(
                    title="Hyper-V root partition is active without VBS",
                    severity="info",
                    current_value=f"hypervisorlaunchtype={launch_type}, VBS running=False",
                    optimal_value="hypervisorlaunchtype off (if no VMs/WSL2/sandbox needed)",
                    explanation=(
                        "The hypervisor root partition is launching but Virtualization "
                        "Based Security is not running, so it adds scheduling overhead with "
                        "no security benefit. If you do not use Hyper-V, WSL2, or Windows "
                        "Sandbox, 'bcdedit /set hypervisorlaunchtype off' (then reboot) "
                        "removes it. ABSO does not change BCD for you."
                    ),
                    category="windows",
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Audit-only: ABSO never edits BCD for the hypervisor."""
        return {
            "success": False,
            "error": (
                "HypervisorAuditHandler is audit-only; ABSO does not run bcdedit. "
                "Change hypervisorlaunchtype manually and reboot if desired."
            ),
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Detect-only handler: capture state for reference, nothing to restore."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """No-op: this handler never mutated anything."""
        return True

    @property
    def restore_guarantee(self) -> str:
        return "none"

    # -- detection helpers -------------------------------------------------

    def _run(self, cmd: list[str]) -> subprocess.CompletedProcess:
        """Single subprocess entry point (mocked in tests)."""
        return subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=15,
            creationflags=no_window_creationflags(),
        )

    def _get_hypervisor_launch_type(self) -> str | None:
        """Parse hypervisorlaunchtype from ``bcdedit /enum {current}``.

        Returns the value (e.g. "Auto"/"Off") or None when unreadable (bcdedit
        needs elevation, and the line is absent on some configs).
        """
        try:
            result = self._run(["bcdedit", "/enum", "{current}"])
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("bcdedit enum failed: %s", exc)
            return None
        if result.returncode != 0 or not result.stdout:
            return None
        match = re.search(r"hypervisorlaunchtype\s+(\w+)", result.stdout, re.IGNORECASE)
        return match.group(1) if match else None

    def _get_vbs_running(self) -> bool | None:
        """Return whether VBS is actually running via Win32_DeviceGuard.

        VirtualizationBasedSecurityStatus: 0 = off, 1 = enabled-not-running,
        2 = running. Returns None when the class/value cannot be read.
        """
        try:
            result = self._run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    "(Get-CimInstance -Namespace root\\Microsoft\\Windows\\DeviceGuard "
                    "-ClassName Win32_DeviceGuard)"
                    ".VirtualizationBasedSecurityStatus",
                ]
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("DeviceGuard query failed: %s", exc)
            return None
        if result.returncode != 0:
            return None
        raw = (result.stdout or "").strip()
        if not raw.isdigit():
            return None
        return int(raw) == 2
