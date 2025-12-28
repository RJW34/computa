"""Power plan settings handler."""

from __future__ import annotations

import logging
import re
import subprocess
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class PowerSettingsHandler(SettingsHandler):
    """Handles Windows power plan settings.

    Manages:
    - Active power plan selection
    - Ultimate Performance plan creation
    - Power-related subgroup settings
    """

    # Known power plan GUIDs
    BALANCED_GUID = "381b4222-f694-41f0-9685-ff5bb260df2e"
    HIGH_PERFORMANCE_GUID = "8c5e7fda-e8bf-4a96-9a85-a6e23a8c635c"
    # This is the hidden template GUID used to create Ultimate Performance
    ULTIMATE_PERFORMANCE_TEMPLATE_GUID = "e9a42b02-d5df-448d-aa00-03f14749eb61"

    # Power subgroup GUIDs
    USB_SUBGROUP = "2a737441-1930-4402-8d77-b2bebba308a3"
    USB_SELECTIVE_SUSPEND = "48e6b7a6-50f5-4782-a5d4-53bb8f07e226"
    PCIE_SUBGROUP = "501a4d13-42af-4429-9fd1-a8218c268e20"
    PCIE_LINK_STATE = "ee12f906-d277-404b-b6da-e5fa1a576df5"
    PROCESSOR_SUBGROUP = "54533251-82be-4824-96c1-47b60b740d00"
    PROCESSOR_MIN_STATE = "893dee8e-2bef-41e0-89c6-b55d0929964c"
    PROCESSOR_MAX_STATE = "bc5038f7-23e0-4960-96da-33abaf5935ec"

    def detect(self) -> dict[str, Any]:
        """Detect current power settings."""
        return {
            "active_plan": self._get_active_plan(),
            "available_plans": self._list_plans(),
            "has_ultimate_performance": self._has_ultimate_performance(),
        }

    def audit(self) -> list[Issue]:
        """Audit power settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        active_plan = current.get("active_plan", {})

        # Check if using a performance plan (by name or known GUID)
        if not self._is_performance_plan(active_plan):
            issues.append(Issue(
                title="Not using a performance power plan",
                severity="warning",
                current_value=active_plan.get("name", "Unknown"),
                optimal_value="Ultimate Performance or High Performance",
                explanation="Performance power plans prevent CPU throttling and power-saving delays.",
                category="power",
            ))

        # Check if Ultimate Performance is available
        if not current.get("has_ultimate_performance"):
            issues.append(Issue(
                title="Ultimate Performance plan not available",
                severity="info",
                current_value="Not installed",
                optimal_value="Available",
                explanation="Ultimate Performance provides maximum performance for gaming. Can be enabled via powercfg.",
                category="power",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply power settings."""
        errors: list[str] = []

        try:
            # Create Ultimate Performance if requested and not present
            if settings.get("ensure_ultimate_performance") and not self._has_ultimate_performance():
                self._create_ultimate_performance()

            # Set active plan
            if "active_plan" in settings:
                plan_id = settings["active_plan"]

                # Handle special names
                if plan_id == "ultimate_performance":
                    # Find the actual GUID on this system
                    found_guid = self._find_ultimate_performance_guid()
                    if found_guid:
                        plan_id = found_guid
                    else:
                        # Create it if not found
                        plan_id = self._create_ultimate_performance()
                elif plan_id == "high_performance":
                    plan_id = self.HIGH_PERFORMANCE_GUID

                self._set_active_plan(plan_id)

            # Apply sub-settings for gaming
            if settings.get("disable_usb_suspend"):
                self._set_power_setting(
                    self.USB_SUBGROUP,
                    self.USB_SELECTIVE_SUSPEND,
                    0
                )

            if settings.get("disable_pcie_power_saving"):
                self._set_power_setting(
                    self.PCIE_SUBGROUP,
                    self.PCIE_LINK_STATE,
                    0
                )

            if settings.get("processor_max_performance"):
                self._set_power_setting(
                    self.PROCESSOR_SUBGROUP,
                    self.PROCESSOR_MIN_STATE,
                    100
                )
                self._set_power_setting(
                    self.PROCESSOR_SUBGROUP,
                    self.PROCESSOR_MAX_STATE,
                    100
                )

        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current power settings."""
        current = self.detect()

        # Export active plan to file would be done here
        # For now, just save the active plan GUID
        return {
            "active_plan": current.get("active_plan", {}).get("guid"),
        }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore power settings from backup."""
        if "active_plan" in data and data["active_plan"]:
            try:
                self._set_active_plan(data["active_plan"])
                return True
            except Exception as e:
                logger.error(f"Failed to restore power plan: {e}")
                return False
        return True

    # Private helper methods

    def _run_powercfg(self, *args: str) -> subprocess.CompletedProcess:
        """Run powercfg command."""
        return subprocess.run(
            ["powercfg"] + list(args),
            capture_output=True,
            text=True,
            timeout=10,
        )

    def _get_active_plan(self) -> dict[str, str]:
        """Get the currently active power plan."""
        try:
            result = self._run_powercfg("/getactivescheme")
            if result.returncode == 0:
                # Parse output like: "Power Scheme GUID: xxx  (Name)"
                match = re.search(
                    r"GUID:\s*([a-f0-9-]+)\s*\(([^)]+)\)",
                    result.stdout,
                    re.IGNORECASE
                )
                if match:
                    return {
                        "guid": match.group(1),
                        "name": match.group(2).strip(),
                    }
        except Exception as e:
            logger.error(f"Failed to get active plan: {e}")

        return {}

    def _list_plans(self) -> list[dict[str, str]]:
        """List all available power plans."""
        plans = []

        try:
            result = self._run_powercfg("/list")
            if result.returncode == 0:
                for match in re.finditer(
                    r"GUID:\s*([a-f0-9-]+)\s*\(([^)]+)\)",
                    result.stdout,
                    re.IGNORECASE
                ):
                    plans.append({
                        "guid": match.group(1),
                        "name": match.group(2).strip(),
                    })
        except Exception as e:
            logger.error(f"Failed to list plans: {e}")

        return plans

    def _has_ultimate_performance(self) -> bool:
        """Check if Ultimate Performance plan is available."""
        return self._find_ultimate_performance_guid() is not None

    def _find_ultimate_performance_guid(self) -> str | None:
        """Find the GUID of Ultimate Performance plan by name.

        The template GUID is hidden and when duplicated creates a new GUID,
        so we must search by name instead of relying on a fixed GUID.
        """
        plans = self._list_plans()
        for p in plans:
            if "ultimate performance" in p["name"].lower():
                return p["guid"]
        return None

    def _is_performance_plan(self, plan: dict[str, str]) -> bool:
        """Check if a plan is a performance-oriented plan."""
        name = plan.get("name", "").lower()
        guid = plan.get("guid", "").lower()

        # Check by name
        if "performance" in name:
            return True

        # Check by known GUIDs
        known_perf_guids = [
            self.HIGH_PERFORMANCE_GUID.lower(),
            self.ULTIMATE_PERFORMANCE_TEMPLATE_GUID.lower(),
        ]
        return guid in known_perf_guids

    def _create_ultimate_performance(self) -> str:
        """Create Ultimate Performance power plan.

        Returns:
            The GUID of the newly created plan.
        """
        result = self._run_powercfg(
            "/duplicatescheme",
            self.ULTIMATE_PERFORMANCE_TEMPLATE_GUID
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to create Ultimate Performance: {result.stderr}")

        # Parse the new GUID from output like "Power Scheme GUID: xxx"
        match = re.search(r"GUID:\s*([a-f0-9-]+)", result.stdout, re.IGNORECASE)
        if match:
            return match.group(1)

        # Fallback: find it by name
        guid = self._find_ultimate_performance_guid()
        if guid:
            return guid

        raise RuntimeError("Created Ultimate Performance but could not find its GUID")

    def _set_active_plan(self, guid: str) -> None:
        """Set the active power plan."""
        result = self._run_powercfg("/setactive", guid)
        if result.returncode != 0:
            raise RuntimeError(f"Failed to set active plan: {result.stderr}")

    def _set_power_setting(self, subgroup: str, setting: str, value: int) -> None:
        """Set a power setting value for the current scheme."""
        result = self._run_powercfg(
            "/setacvalueindex",
            "SCHEME_CURRENT",
            subgroup,
            setting,
            str(value)
        )
        if result.returncode != 0:
            raise RuntimeError(f"Failed to set power setting: {result.stderr}")

        # Apply changes
        self._run_powercfg("/setactive", "SCHEME_CURRENT")
