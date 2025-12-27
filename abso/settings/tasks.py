"""Scheduled tasks settings handler."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from abso.settings.base import SettingsHandler
from abso.core.models import Issue

logger = logging.getLogger(__name__)


class TasksSettingsHandler(SettingsHandler):
    """Handles Windows scheduled task optimization settings.

    Manages telemetry and background tasks that can impact gaming:
    - CompatTelRunner - Application telemetry collection
    - Consolidator - Customer Experience data aggregation
    - UsbCeip - USB telemetry
    - Various maintenance tasks

    Uses schtasks.exe for task management.
    """

    # Tasks to manage for gaming optimization
    GAMING_TASKS = {
        r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser": {
            "display_name": "Compatibility Appraiser",
            "description": "Collects program telemetry. Can use significant CPU/disk.",
            "optimal_state": "Disabled",
            "severity": "warning",
        },
        r"\Microsoft\Windows\Application Experience\ProgramDataUpdater": {
            "display_name": "Program Data Updater",
            "description": "Collects program telemetry data.",
            "optimal_state": "Disabled",
            "severity": "info",
        },
        r"\Microsoft\Windows\Customer Experience Improvement Program\Consolidator": {
            "display_name": "CEIP Consolidator",
            "description": "Aggregates and uploads Customer Experience data.",
            "optimal_state": "Disabled",
            "severity": "info",
        },
        r"\Microsoft\Windows\Customer Experience Improvement Program\UsbCeip": {
            "display_name": "USB CEIP",
            "description": "Collects USB usage data.",
            "optimal_state": "Disabled",
            "severity": "info",
        },
        r"\Microsoft\Windows\DiskDiagnostic\Microsoft-Windows-DiskDiagnosticDataCollector": {
            "display_name": "Disk Diagnostic Data Collector",
            "description": "Collects disk diagnostic data for Microsoft.",
            "optimal_state": "Disabled",
            "severity": "info",
        },
        r"\Microsoft\Windows\Maintenance\WinSAT": {
            "display_name": "Windows System Assessment Tool",
            "description": "Measures system performance. Can cause CPU spikes.",
            "optimal_state": "Disabled",
            "severity": "info",
        },
        r"\Microsoft\Windows\Power Efficiency Diagnostics\AnalyzeSystem": {
            "display_name": "Power Efficiency Diagnostics",
            "description": "Analyzes system for power efficiency.",
            "optimal_state": "Disabled",
            "severity": "info",
        },
    }

    def detect(self) -> dict[str, Any]:
        """Detect current scheduled task states."""
        result = {
            "tasks": {},
        }

        for task_path in self.GAMING_TASKS:
            task_info = self._get_task_info(task_path)
            result["tasks"][task_path] = task_info

        return result

    def audit(self) -> list[Issue]:
        """Audit scheduled tasks for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        for task_path, config in self.GAMING_TASKS.items():
            task_info = current["tasks"].get(task_path, {})

            if not task_info.get("exists"):
                continue  # Task doesn't exist on this system

            state = task_info.get("state", "Unknown")
            optimal_state = config["optimal_state"]

            # Check if task is enabled when it should be disabled
            if state == "Ready" and optimal_state == "Disabled":
                issues.append(Issue(
                    title=f"{config['display_name']} is enabled",
                    severity=config["severity"],
                    current_value="Enabled",
                    optimal_value="Disabled",
                    explanation=config["description"],
                    category="tasks",
                ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply scheduled task settings.

        Settings format:
        {
            "tasks": {
                r"\\Microsoft\\Windows\\...\\TaskName": {"enabled": False},
            }
        }

        Or use preset:
        {
            "preset": "gaming"  # Disables all telemetry/background tasks
        }
        """
        errors: list[str] = []

        try:
            if settings.get("preset") == "gaming":
                # Disable all gaming-related tasks
                for task_path, config in self.GAMING_TASKS.items():
                    if config["optimal_state"] == "Disabled":
                        result = self._set_task_enabled(task_path, False)
                        if not result["success"]:
                            # Don't treat missing tasks as errors
                            if "does not exist" not in result.get("error", "").lower():
                                errors.append(result.get("error", f"Failed to disable {task_path}"))

            elif "tasks" in settings:
                for task_path, task_settings in settings["tasks"].items():
                    if "enabled" in task_settings:
                        result = self._set_task_enabled(task_path, task_settings["enabled"])
                        if not result["success"]:
                            if "does not exist" not in result.get("error", "").lower():
                                errors.append(result.get("error", f"Failed to configure {task_path}"))

        except PermissionError as e:
            errors.append(f"Permission denied (requires admin): {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current scheduled task settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore scheduled task settings from backup."""
        try:
            tasks = data.get("tasks", {})
            for task_path, task_info in tasks.items():
                if task_info.get("exists"):
                    # Re-enable tasks that were enabled before
                    was_enabled = task_info.get("state") == "Ready"
                    self._set_task_enabled(task_path, was_enabled)
            return True
        except Exception as e:
            logger.error(f"Failed to restore scheduled task settings: {e}")
            return False

    # Private helper methods

    def _get_task_info(self, task_path: str) -> dict[str, Any]:
        """Get information about a scheduled task."""
        result = {
            "exists": False,
            "state": None,
            "last_run": None,
        }

        try:
            # Use schtasks to query task
            query_result = subprocess.run(
                ["schtasks", "/Query", "/TN", task_path, "/FO", "LIST", "/V"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if query_result.returncode == 0:
                result["exists"] = True
                # Parse output
                for line in query_result.stdout.splitlines():
                    if line.startswith("Status:"):
                        result["state"] = line.split(":", 1)[1].strip()
                    elif line.startswith("Last Run Time:"):
                        result["last_run"] = line.split(":", 1)[1].strip()

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout querying task {task_path}")
        except Exception as e:
            logger.debug(f"Failed to get task info for {task_path}: {e}")

        return result

    def _set_task_enabled(self, task_path: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a scheduled task."""
        try:
            action = "/Enable" if enabled else "/Disable"
            result = subprocess.run(
                ["schtasks", "/Change", "/TN", task_path, action],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return {"success": True}
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return {"success": False, "error": error_msg}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout configuring task"}
        except Exception as e:
            return {"success": False, "error": str(e)}
