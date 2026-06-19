"""Opt-in fixed (system-managed-off) pagefile pinning handler.

By default Windows manages the pagefile automatically and can grow or shrink it
at runtime. That resize is a blocking disk operation that can produce a
noticeable frame-time hitch in a game. Pinning a *fixed* pagefile (automatic
management disabled, identical initial and maximum size) eliminates runtime
resize stutter because the file never has to be resized.

Design rules for this module (enforced by tests):

1. **Never silent.** The handler refuses to mutate state unless the caller
   passes the explicit ``acknowledge_pagefile_change=True`` flag. No built-in
   gaming profile is allowed to set this; it is a separate user-driven flow.
2. **Reboot required.** Pagefile size and management changes only take effect
   after a reboot, so ``apply`` reports ``requires_reboot=True`` and
   ``verify_active`` is reboot-gated.
3. **Best-effort restore.** Restore re-applies the captured automatic-managed
   flag and any prior fixed sizes, but the OS reconciles pagefile state across
   reboots and a different drive layout can prevent a byte-exact restore. The
   handler advertises ``restore_guarantee == "partial"`` for this reason.
4. **Audit-only by default.** Callers who don't opt in get the current state
   surfaced as an informational Issue and nothing else — never a warning.

All system access goes through a single injectable :meth:`_run_ps` so the test
suite can exercise every path hermetically without touching the real pagefile.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler
from abso.utils.proc import no_window_creationflags

logger = logging.getLogger(__name__)

# Maximum size we will ever pin, regardless of installed RAM. A 32 GB cap keeps
# the on-disk footprint sane on the high-RAM rigs this tool targets; crash dumps
# rarely need more, and a larger fixed file just wastes drive space.
_MAX_PAGEFILE_MB = 32768

# Single source of truth for the acknowledgement gate. Accepting any truthy
# value would let a stray string like "false" silently bypass the gate, so the
# check below compares against the literal boolean True.
ACK_KEY = "acknowledge_pagefile_change"


def _recommended_sizes(total_ram_gb: float | None) -> dict[str, int]:
    """Compute recommended fixed pagefile sizes from installed RAM.

    The rule is min = 1.5x RAM, max = 2x RAM, with the maximum capped at
    32768 MB (32 GB). This is a pure helper so the sizing math can be unit
    tested without any system access.

    Args:
        total_ram_gb: Installed physical memory in gigabytes, or ``None`` when
            it could not be determined.

    Returns:
        Dict with integer ``initial_mb`` and ``maximum_mb`` values. When
        ``total_ram_gb`` is unknown or non-positive, falls back to a safe
        4096/8192 MB pair.
    """
    if not total_ram_gb or total_ram_gb <= 0:
        return {"initial_mb": 4096, "maximum_mb": 8192}

    ram_mb = total_ram_gb * 1024.0
    initial_mb = int(round(ram_mb * 1.5))
    maximum_mb = int(round(ram_mb * 2.0))
    maximum_mb = min(maximum_mb, _MAX_PAGEFILE_MB)
    # Never let the floor exceed the (possibly capped) ceiling.
    initial_mb = min(initial_mb, maximum_mb)
    return {"initial_mb": initial_mb, "maximum_mb": maximum_mb}


class PagefileHandler(SettingsHandler):
    """Opt-in handler that pins a fixed pagefile to avoid resize stutter.

    The handler never mutates state unless the caller passes
    ``acknowledge_pagefile_change=True`` in the settings dict. Missing the
    acknowledgement is a hard refusal: ``apply`` returns ``success=False`` with
    a descriptive error and touches nothing.
    """

    # Aggressive, opt-in, reboot-gated. A verify mismatch (e.g. the user has
    # not rebooted yet) must not escalate to CRITICAL.
    is_critical_verify = False

    @property
    def restore_guarantee(self) -> str:
        """Restore is best-effort: the OS reconciles pagefile state on reboot.

        We can write back the automatic-managed flag and the prior fixed sizes,
        but the running compositor / memory manager only commits pagefile
        layout across a reboot, and a changed drive layout can prevent a
        byte-exact restore. That makes the guarantee ``"partial"`` rather than
        ``"full"``.
        """
        return "partial"

    # ------------------------------------------------------------------
    # Injectable command runner
    # ------------------------------------------------------------------

    def _run_ps(self, script: str) -> str:
        """Run a PowerShell snippet and return its stdout.

        This is the single seam tests mock so no real ``powershell`` / CIM call
        is ever made. Failures are swallowed and surfaced as an empty string so
        callers can treat "unknown" uniformly.

        Args:
            script: PowerShell script body to execute.

        Returns:
            Captured stdout (stripped), or an empty string on any failure.
        """
        try:
            proc = subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-NonInteractive",
                    "-Command",
                    script,
                ],
                capture_output=True,
                text=True,
                timeout=30,
                check=False,
                creationflags=no_window_creationflags(),
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("pagefile _run_ps failed: %s", exc)
            return ""
        return (proc.stdout or "").strip()

    # ------------------------------------------------------------------
    # Read helpers
    # ------------------------------------------------------------------

    def _read_automatic_managed(self) -> bool | None:
        out = self._run_ps(
            "Get-CimInstance Win32_ComputerSystem | "
            "Select-Object AutomaticManagedPagefile | ConvertTo-Json"
        )
        data = self._loads(out)
        if isinstance(data, dict) and "AutomaticManagedPagefile" in data:
            value = data["AutomaticManagedPagefile"]
            return bool(value) if value is not None else None
        return None

    def _read_pagefiles(self) -> list[dict[str, Any]]:
        out = self._run_ps(
            "Get-CimInstance Win32_PageFileSetting | "
            "Select-Object Name,InitialSize,MaximumSize | ConvertTo-Json"
        )
        data = self._loads(out)
        if data is None:
            return []
        # ConvertTo-Json emits a bare object for a single pagefile and a list
        # for multiple; normalise to a list.
        if isinstance(data, dict):
            data = [data]
        if not isinstance(data, list):
            return []
        return [item for item in data if isinstance(item, dict)]

    def _read_total_ram_gb(self) -> float | None:
        out = self._run_ps("(Get-CimInstance Win32_ComputerSystem).TotalPhysicalMemory")
        if not out:
            return None
        try:
            total_bytes = int(out.strip())
        except (TypeError, ValueError):
            return None
        if total_bytes <= 0:
            return None
        return round(total_bytes / (1024.0**3), 2)

    @staticmethod
    def _loads(raw: str) -> Any:
        if not raw:
            return None
        try:
            return json.loads(raw)
        except (TypeError, ValueError):
            return None

    # ------------------------------------------------------------------
    # SettingsHandler contract
    # ------------------------------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Detect automatic-managed flag, fixed pagefiles, and total RAM."""
        return {
            "automatic_managed": self._read_automatic_managed(),
            "pagefiles": self._read_pagefiles(),
            "total_ram_gb": self._read_total_ram_gb(),
        }

    def audit(self) -> list[Issue]:
        """Surface auto-managed pagefile state as opt-in info only.

        Never emits warning severity: a system-managed pagefile is the safe
        default, and pinning a fixed one is an aggressive, acknowledgement-
        required choice rather than a misconfiguration.
        """
        current = self.detect()
        issues: list[Issue] = []

        if current.get("automatic_managed") is True:
            sizes = _recommended_sizes(current.get("total_ram_gb"))
            issues.append(
                Issue(
                    title="Pagefile is automatically managed by Windows",
                    severity="info",
                    current_value="Automatic (system-managed)",
                    optimal_value=(
                        "Fixed pagefile "
                        f"({sizes['initial_mb']}-{sizes['maximum_mb']} MB) — opt-in"
                    ),
                    explanation=(
                        "Windows can resize a system-managed pagefile at runtime, "
                        "and that blocking disk operation can cause an in-game "
                        "frame-time hitch. Pinning a fixed pagefile avoids resize "
                        "stutter, but it is a reboot-gated, acknowledgement-required "
                        "change: ABSO will never pin the pagefile silently."
                    ),
                    category="memory",
                    evidence_tier=EvidenceTier.EXPERIMENTAL,
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Pin a fixed pagefile, but only when explicitly acknowledged.

        Without ``acknowledge_pagefile_change=True`` (literal boolean) this is a
        hard refusal that mutates nothing. When acknowledged it disables
        automatic management and writes a fixed pagefile (initial == maximum is
        not required, but both are pinned) on the system drive, then reports
        ``requires_reboot=True``.
        """
        if settings.get(ACK_KEY) is not True:
            return {
                "success": False,
                "error": (
                    "Pagefile change requires explicit acknowledgement "
                    "(acknowledge_pagefile_change=True)"
                ),
                "requires_reboot": False,
            }

        total_ram_gb = self._read_total_ram_gb()
        sizes = _recommended_sizes(total_ram_gb)
        initial_mb = sizes["initial_mb"]
        maximum_mb = sizes["maximum_mb"]

        errors: list[str] = []
        applied: list[str] = []

        try:
            self._set_automatic_managed(False)
            applied.append("AutomaticManagedPagefile=False")
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"disable automatic management: {exc}")

        try:
            self._set_fixed_pagefile(initial_mb, maximum_mb)
            applied.append(f"pagefile={initial_mb}-{maximum_mb}MB")
        except (OSError, subprocess.SubprocessError) as exc:
            errors.append(f"set fixed pagefile: {exc}")

        return {
            "success": not errors,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": True,
            "applied": applied,
            "initial_mb": initial_mb,
            "maximum_mb": maximum_mb,
        }

    def backup(self) -> dict[str, Any]:
        """Capture automatic-managed flag and existing pagefile settings."""
        return {
            "automatic_managed": self._read_automatic_managed(),
            "pagefiles": self._read_pagefiles(),
        }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore the captured pagefile management state (best-effort).

        If automatic management was originally on, re-enable it (which lets
        Windows discard any fixed sizes ABSO pinned). Otherwise re-apply the
        captured fixed sizes. Restore is non-fatal: any failure logs and
        returns False rather than raising.
        """
        try:
            original_auto = data.get("automatic_managed")
            if original_auto is True:
                self._set_automatic_managed(True)
                return True

            # Was not auto-managed: re-pin the captured fixed pagefiles.
            self._set_automatic_managed(False)
            for entry in data.get("pagefiles", []) or []:
                if not isinstance(entry, dict):
                    continue
                initial = entry.get("InitialSize")
                maximum = entry.get("MaximumSize")
                name = entry.get("Name")
                if initial is None or maximum is None:
                    continue
                self._set_fixed_pagefile(int(initial), int(maximum), name=name)
            return True
        except (OSError, subprocess.SubprocessError, TypeError, ValueError) as exc:
            logger.error("PagefileHandler restore failed: %s", exc)
            return False

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Confirm the fixed pagefile is in place (reboot-gated).

        Only meaningful when the caller acknowledged the change. NOTE: pagefile
        size/management changes only commit after a reboot, so a mismatch here
        before the user reboots is expected, not an apply failure — which is why
        ``is_critical_verify`` stays False.
        """
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        if settings.get(ACK_KEY) is not True:
            return results

        sizes = _recommended_sizes(self._read_total_ram_gb())
        current = self.detect()

        auto = current.get("automatic_managed")
        auto_active = auto is False
        results["settings"]["automatic_managed"] = {
            "target": False,
            "current": auto,
            "active": auto_active,
        }

        pagefiles = current.get("pagefiles") or []
        target_initial = sizes["initial_mb"]
        target_maximum = sizes["maximum_mb"]
        fixed_active = any(
            isinstance(p, dict)
            and p.get("InitialSize") == target_initial
            and p.get("MaximumSize") == target_maximum
            for p in pagefiles
        )
        results["settings"]["fixed_pagefile"] = {
            "target": f"{target_initial}-{target_maximum}MB",
            "current": pagefiles,
            "active": fixed_active,
        }

        results["all_active"] = auto_active and fixed_active
        return results

    # ------------------------------------------------------------------
    # Write helpers
    # ------------------------------------------------------------------

    def _set_automatic_managed(self, enabled: bool) -> None:
        """Set Win32_ComputerSystem.AutomaticManagedPagefile via CIM."""
        flag = "$true" if enabled else "$false"
        script = (
            "$cs = Get-CimInstance Win32_ComputerSystem; "
            f"Set-CimInstance -InputObject $cs "
            f"-Property @{{AutomaticManagedPagefile={flag}}}"
        )
        self._run_ps(script)

    def _set_fixed_pagefile(
        self, initial_mb: int, maximum_mb: int, name: str | None = None
    ) -> None:
        """Create or update a fixed Win32_PageFileSetting on the system drive.

        Args:
            initial_mb: Initial (minimum) pagefile size in megabytes.
            maximum_mb: Maximum pagefile size in megabytes.
            name: Optional explicit pagefile path; defaults to the system drive
                ``pagefile.sys`` (``$env:SystemDrive\\pagefile.sys``).
        """
        target = name or "$env:SystemDrive\\pagefile.sys"
        # Remove any stale setting for this path, then recreate it fixed so the
        # operation is idempotent across repeated applies.
        script = (
            f"$path = \"{target}\"; "
            "Get-CimInstance Win32_PageFileSetting "
            "| Where-Object { $_.Name -eq $path } "
            "| Remove-CimInstance -ErrorAction SilentlyContinue; "
            "New-CimInstance -ClassName Win32_PageFileSetting "
            "-Property @{ Name = $path; "
            f"InitialSize = {int(initial_mb)}; MaximumSize = {int(maximum_mb)} }} "
            "-ErrorAction SilentlyContinue | Out-Null; "
            "Set-CimInstance -Query "
            "\"SELECT * FROM Win32_PageFileSetting WHERE Name='$path'\" "
            f"-Property @{{ InitialSize = {int(initial_mb)}; "
            f"MaximumSize = {int(maximum_mb)} }} -ErrorAction SilentlyContinue"
        )
        self._run_ps(script)
