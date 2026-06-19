"""Windows Defender game-folder exclusion handler.

Real-time AV scanning of shader-cache / pak writes during play causes I/O
spikes and stutter. Adding the game's install directory to Defender's
``ExclusionPath`` stops those scans. This is gated on Microsoft Defender being
the *active* antivirus (a third-party AV owns its own exclusions, and
``Add-MpPreference`` is meaningless or disabled then).

Backup/restore semantics: ``backup`` snapshots the current exclusion list;
``restore`` reverts to that snapshot by removing any exclusion added since
(i.e. ``current - backup``). It never clears the whole list.
"""

from __future__ import annotations

import json
import logging
import subprocess
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.utils.proc import no_window_creationflags

logger = logging.getLogger(__name__)

_PS_TIMEOUT = 20


class DefenderExclusionsHandler(SettingsHandler):
    """Manage Microsoft Defender path exclusions for game install folders."""

    # Opt-in latency feature, not core system state: a verify miss is a WARNING.
    is_critical_verify = False

    def _run_ps(self, script: str) -> subprocess.CompletedProcess:
        """Single PowerShell entry point (injected/mocked in tests)."""
        return subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", script],
            capture_output=True,
            text=True,
            timeout=_PS_TIMEOUT,
            creationflags=no_window_creationflags(),
        )

    def _defender_active(self) -> bool | None:
        """Return whether Microsoft Defender is the active real-time AV."""
        try:
            result = self._run_ps(
                "(Get-MpComputerStatus | "
                "Select-Object AMRunningMode,RealTimeProtectionEnabled | ConvertTo-Json)"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("Get-MpComputerStatus failed: %s", exc)
            return None
        if result.returncode != 0:
            return None
        try:
            data = json.loads(result.stdout or "{}")
        except json.JSONDecodeError:
            return None
        mode = str(data.get("AMRunningMode", "")).strip().lower()
        # "Normal" = Defender is the primary AV. "Passive"/"EDR Block Mode"/"SxS
        # Passive" mean a third-party AV is primary, so our exclusions are inert.
        return mode == "normal"

    def _current_exclusions(self) -> list[str]:
        """Return Defender's current ExclusionPath list."""
        try:
            result = self._run_ps(
                "(Get-MpPreference | Select-Object -ExpandProperty ExclusionPath | ConvertTo-Json)"
            )
        except (OSError, subprocess.SubprocessError) as exc:
            logger.debug("Get-MpPreference failed: %s", exc)
            return []
        if result.returncode != 0 or not (result.stdout or "").strip():
            return []
        try:
            data = json.loads(result.stdout)
        except json.JSONDecodeError:
            return []
        if isinstance(data, str):
            return [data]
        if isinstance(data, list):
            return [str(p) for p in data if p]
        return []

    def detect(self) -> dict[str, Any]:
        """Detect Defender active state + current path exclusions."""
        return {
            "defender_active": self._defender_active(),
            "exclusion_paths": self._current_exclusions(),
        }

    def audit(self) -> list[Issue]:
        """Info-only note that game folders can be excluded (when Defender is active)."""
        issues: list[Issue] = []
        current = self.detect()
        if current.get("defender_active"):
            issues.append(
                Issue(
                    title="Game folders can be excluded from Defender real-time scans",
                    severity="info",
                    current_value=f"{len(current.get('exclusion_paths') or [])} exclusion(s) set",
                    optimal_value="Game install dirs excluded during play",
                    explanation=(
                        "Microsoft Defender is the active AV. Excluding a game's install "
                        "directory stops real-time scans of shader-cache writes mid-match. "
                        "Opt-in: ABSO only adds the paths a profile supplies."
                    ),
                    category="windows",
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Add the supplied exclusion paths (only when Defender is the active AV).

        Settings:
            exclusion_paths: list[str] - directories to exclude.
        """
        paths = [str(p) for p in (settings.get("exclusion_paths") or []) if p]
        if not paths:
            return {"success": True, "error": None, "requires_reboot": False, "changed": False}

        if self._defender_active() is not True:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "changed": False,
                "skipped": "Microsoft Defender is not the active AV; exclusions not applied.",
            }

        existing = {p.lower() for p in self._current_exclusions()}
        errors: list[str] = []
        added: list[str] = []
        for path in paths:
            if path.lower() in existing:
                continue
            try:
                result = self._run_ps(f"Add-MpPreference -ExclusionPath '{self._escape(path)}'")
                if result.returncode == 0:
                    added.append(path)
                else:
                    errors.append(f"{path}: {(result.stderr or '').strip()[:120]}")
            except (OSError, subprocess.SubprocessError) as exc:
                errors.append(f"{path}: {exc}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
            "changed": bool(added),
            "changed_keys": added,
        }

    def backup(self) -> dict[str, Any]:
        """Snapshot the current exclusion list for revert-to-snapshot restore."""
        return {"exclusion_paths": self._current_exclusions()}

    def restore(self, data: dict[str, Any]) -> bool:
        """Revert to the backed-up exclusion set by removing exclusions added since.

        Removes ``current - backup`` only; never clears pre-existing exclusions.
        """
        try:
            backed_up = {str(p).lower() for p in (data.get("exclusion_paths") or [])}
            current = self._current_exclusions()
            to_remove = [p for p in current if p.lower() not in backed_up]
            ok = True
            for path in to_remove:
                try:
                    result = self._run_ps(
                        f"Remove-MpPreference -ExclusionPath '{self._escape(path)}'"
                    )
                    if result.returncode != 0:
                        ok = False
                        logger.warning("Failed to remove Defender exclusion %s", path)
                except (OSError, subprocess.SubprocessError) as exc:
                    ok = False
                    logger.warning("Failed to remove Defender exclusion %s: %s", path, exc)
            return ok
        except Exception as exc:  # noqa: BLE001 - restore must be non-fatal
            logger.error("Failed to restore Defender exclusions: %s", exc)
            return False

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify the requested exclusion paths are present (when Defender active)."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        paths = [str(p) for p in (settings.get("exclusion_paths") or []) if p]
        if not paths or self._defender_active() is not True:
            return results
        current = {p.lower() for p in self._current_exclusions()}
        for path in paths:
            active = path.lower() in current
            results["settings"][path] = {"target": "excluded", "active": active}
            if not active:
                results["all_active"] = False
        return results

    @staticmethod
    def _escape(path: str) -> str:
        """Escape single quotes for a PowerShell single-quoted string literal."""
        return path.replace("'", "''")
