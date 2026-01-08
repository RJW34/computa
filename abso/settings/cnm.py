"""CNM (Celio's Network Machine) settings handler.

Manages the CNM relay server and tray application for gaming optimization.
When gaming, CNM should be stopped to:
- Free resources (Node.js process, port 3001)
- Allow power optimizations (CNM keeps system awake via SetThreadExecutionState)
- Reduce background processes
"""

from __future__ import annotations

import logging
import subprocess
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class CNMSettingsHandler(SettingsHandler):
    """Handles CNM (Celio's Network Machine) optimization settings.

    CNM is a WebSocket relay server for remote terminal access.
    For gaming, it should be stopped to free resources and allow
    power optimizations to take effect.

    CNM components:
    - Node.js server (port 3001)
    - PowerShell tray application (CNM-Tray.ps1)
    - Windows scheduled task (CNM-Server-Tray)
    """

    # Path to CNM control script (adjust if CNM is installed elsewhere)
    CNM_CONTROL_SCRIPT = Path(
        r"C:\Users\mtoli\Documents\Code\iphone bridge\startup\CNM-Control.ps1"
    )

    def __init__(self) -> None:
        self._control_script_exists = self.CNM_CONTROL_SCRIPT.exists()

    def detect(self) -> dict[str, Any]:
        """Detect current CNM state."""
        result: dict[str, Any] = {
            "installed": self._control_script_exists,
            "server_running": False,
            "server_pid": None,
            "tray_running": False,
            "tray_pid": None,
            "task_enabled": False,
        }

        if not self._control_script_exists:
            return result

        try:
            # Run CNM-Control.ps1 -Status to get current state
            proc = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.CNM_CONTROL_SCRIPT),
                    "-Status",
                ],
                capture_output=True,
                text=True,
                timeout=10,
            )

            output = proc.stdout

            # Parse output
            result["server_running"] = "Server: Running" in output
            result["tray_running"] = "Tray:   Running" in output
            result["task_enabled"] = "Task:   Enabled" in output

            # Extract PIDs if running
            for line in output.splitlines():
                if "Server: Running (PID" in line:
                    try:
                        pid_str = line.split("PID ")[1].rstrip(")")
                        result["server_pid"] = int(pid_str)
                    except (IndexError, ValueError):
                        pass
                elif "Tray:   Running (PID" in line:
                    try:
                        pid_str = line.split("PID ")[1].rstrip(")")
                        result["tray_pid"] = int(pid_str)
                    except (IndexError, ValueError):
                        pass

            # Check exit code (0 = running, 1 = stopped)
            result["is_active"] = proc.returncode == 0

        except subprocess.TimeoutExpired:
            logger.warning("Timeout detecting CNM status")
        except Exception as e:
            logger.debug(f"Failed to detect CNM status: {e}")

        return result

    def audit(self) -> list[Issue]:
        """Audit CNM state for gaming optimization."""
        issues: list[Issue] = []

        if not self._control_script_exists:
            # CNM not installed, nothing to audit
            return issues

        current = self.detect()

        if current.get("server_running") or current.get("tray_running"):
            issues.append(
                Issue(
                    title="CNM relay server is running",
                    severity="info",
                    current_value="Running",
                    optimal_value="Stopped (for gaming)",
                    explanation=(
                        "CNM (Celio's Network Machine) is running in the background. "
                        "It uses port 3001, keeps the system awake via SetThreadExecutionState, "
                        "and consumes resources. Stopping it during gaming can improve latency "
                        "consistency and allow power optimizations to work properly."
                    ),
                    category="cnm",
                )
            )

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply CNM settings.

        Settings format:
        {
            "action": "stop" | "start" | "disable" | "enable"
        }

        Actions:
        - stop: Stop CNM server and tray (but keep scheduled task enabled)
        - start: Start CNM tray app (which auto-starts server)
        - disable: Stop CNM AND disable the scheduled task
        - enable: Enable scheduled task AND start CNM
        """
        errors: list[str] = []

        if not self._control_script_exists:
            return {
                "success": True,  # Not an error - CNM just isn't installed
                "skipped": True,
                "message": "CNM not installed, skipping",
                "requires_reboot": False,
            }

        action = settings.get("action", "stop")

        try:
            # Map action to CNM-Control.ps1 flags
            flag_map = {
                "stop": "-Stop",
                "start": "-Start",
                "disable": "-Disable",
                "enable": "-Enable",
            }

            flag = flag_map.get(action)
            if not flag:
                return {
                    "success": False,
                    "error": f"Unknown action: {action}",
                    "requires_reboot": False,
                }

            result = subprocess.run(
                [
                    "powershell.exe",
                    "-NoProfile",
                    "-ExecutionPolicy",
                    "Bypass",
                    "-File",
                    str(self.CNM_CONTROL_SCRIPT),
                    flag,
                    "-Quiet",
                ],
                capture_output=True,
                text=True,
                timeout=30,
            )

            if result.returncode != 0:
                error_msg = (
                    result.stderr.strip() or result.stdout.strip() or "Unknown error"
                )
                errors.append(f"CNM control failed: {error_msg}")

        except subprocess.TimeoutExpired:
            errors.append("Timeout running CNM control script")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current CNM state."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore CNM to previous state."""
        if not self._control_script_exists:
            return True  # Nothing to restore

        try:
            was_running = data.get("server_running") or data.get("tray_running")
            was_task_enabled = data.get("task_enabled", True)

            if was_running:
                # Restore to running state
                action = "enable" if was_task_enabled else "start"
            else:
                # Keep stopped
                action = "disable" if not was_task_enabled else "stop"

            result = self.apply({"action": action})
            return result.get("success", False)

        except Exception as e:
            logger.error(f"Failed to restore CNM state: {e}")
            return False
