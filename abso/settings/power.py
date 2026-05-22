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

    is_critical_verify = True

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
                optimal_value="Ultimate Performance (standard) or High Performance (fallback)",
                explanation=(
                    "Performance power plans reduce Windows power-saving behavior "
                    "that can matter under load. Benefit depends on CPU, firmware, "
                    "cooling, and OEM policy, and it can increase power and noise."
                ),
                category="power",
            ))

        # Check if Ultimate Performance is available
        if not current.get("has_ultimate_performance"):
            issues.append(Issue(
                title="Ultimate Performance plan not available",
                severity="info",
                current_value="Not installed",
                optimal_value="Available",
                explanation=(
                    "Ultimate Performance is an optional Windows power scheme that "
                    "biases toward performance over efficiency. It is not a universal "
                    "FPS gain, but it gives ABSO a consistent high-performance target."
                ),
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
                    settings.get("processor_min_state", 5)
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

        backup_data: dict[str, Any] = {
            "active_plan": current.get("active_plan", {}).get("guid"),
        }

        # Backup power sub-settings via powercfg /query
        backup_data["processor_min_state"] = self._get_power_setting(
            self.PROCESSOR_SUBGROUP, self.PROCESSOR_MIN_STATE
        )
        backup_data["processor_max_state"] = self._get_power_setting(
            self.PROCESSOR_SUBGROUP, self.PROCESSOR_MAX_STATE
        )
        backup_data["usb_selective_suspend"] = self._get_power_setting(
            self.USB_SUBGROUP, self.USB_SELECTIVE_SUSPEND
        )
        backup_data["pcie_link_state"] = self._get_power_setting(
            self.PCIE_SUBGROUP, self.PCIE_LINK_STATE
        )

        return backup_data

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore power settings from backup."""
        success = True

        if "active_plan" in data and data["active_plan"]:
            try:
                self._set_active_plan(data["active_plan"])
            except Exception as e:
                logger.error(f"Failed to restore power plan: {e}")
                success = False

        # Restore power sub-settings
        setting_map = {
            "processor_min_state": (self.PROCESSOR_SUBGROUP, self.PROCESSOR_MIN_STATE),
            "processor_max_state": (self.PROCESSOR_SUBGROUP, self.PROCESSOR_MAX_STATE),
            "usb_selective_suspend": (self.USB_SUBGROUP, self.USB_SELECTIVE_SUSPEND),
            "pcie_link_state": (self.PCIE_SUBGROUP, self.PCIE_LINK_STATE),
        }

        for key, (subgroup, setting) in setting_map.items():
            value = data.get(key)
            if value is not None:
                try:
                    self._set_power_setting(subgroup, setting, value)
                except Exception as e:
                    logger.error(f"Failed to restore {key}: {e}")
                    success = False

        return success

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested power settings are active."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        current = self.detect()
        active_plan = current.get("active_plan", {})

        if settings.get("ensure_ultimate_performance"):
            has_ultimate = current.get("has_ultimate_performance")
            is_active = bool(has_ultimate)
            results["settings"]["ensure_ultimate_performance"] = {
                "target": True,
                "current": has_ultimate,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "active_plan" in settings:
            target_plan = settings["active_plan"]
            is_active = self._plan_matches_target(active_plan, target_plan)
            results["settings"]["active_plan"] = {
                "target": target_plan,
                "current": active_plan.get("guid") or active_plan.get("name"),
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if settings.get("disable_usb_suspend"):
            current_value = self._get_power_setting(self.USB_SUBGROUP, self.USB_SELECTIVE_SUSPEND)
            is_active = current_value == 0
            results["settings"]["disable_usb_suspend"] = {
                "target": 0,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if settings.get("disable_pcie_power_saving"):
            current_value = self._get_power_setting(self.PCIE_SUBGROUP, self.PCIE_LINK_STATE)
            is_active = current_value == 0
            results["settings"]["disable_pcie_power_saving"] = {
                "target": 0,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if settings.get("processor_max_performance"):
            target_min = int(settings.get("processor_min_state", 5))
            current_min = self._get_power_setting(self.PROCESSOR_SUBGROUP, self.PROCESSOR_MIN_STATE)
            current_max = self._get_power_setting(self.PROCESSOR_SUBGROUP, self.PROCESSOR_MAX_STATE)

            min_active = current_min == target_min
            max_active = current_max == 100
            results["settings"]["processor_min_state"] = {
                "target": target_min,
                "current": current_min,
                "active": min_active,
            }
            results["settings"]["processor_max_state"] = {
                "target": 100,
                "current": current_max,
                "active": max_active,
            }
            if not min_active or not max_active:
                results["all_active"] = False

        return results

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
        apply_result = self._run_powercfg("/setactive", "SCHEME_CURRENT")
        if apply_result.returncode != 0:
            logger.warning(f"Failed to apply power setting changes: {apply_result.stderr}")

    def _get_power_setting(self, subgroup: str, setting: str) -> int | None:
        """Get a power setting value for the current scheme via powercfg /query."""
        try:
            result = self._run_powercfg(
                "/query", "SCHEME_CURRENT", subgroup, setting
            )
            if result.returncode == 0:
                # Parse "Current AC Power Setting Index: 0x000000nn"
                match = re.search(
                    r"Current AC Power Setting Index:\s*0x([0-9a-fA-F]+)",
                    result.stdout
                )
                if match:
                    return int(match.group(1), 16)
        except Exception as e:
            logger.debug(f"Failed to get power setting {setting}: {e}")
        return None

    def _plan_matches_target(self, active_plan: dict[str, str], target_plan: str) -> bool:
        """Check whether the active plan matches a requested target identifier."""
        target = str(target_plan).strip().lower()
        active_guid = str(active_plan.get("guid", "")).strip().lower()
        active_name = str(active_plan.get("name", "")).strip().lower()

        if not active_guid and not active_name:
            return False

        if target == "ultimate_performance":
            return "ultimate performance" in active_name
        if target == "high_performance":
            return (
                active_guid == self.HIGH_PERFORMANCE_GUID.lower()
                or "high performance" in active_name
            )
        if target == "balanced":
            return (
                active_guid == self.BALANCED_GUID.lower()
                or "balanced" in active_name
            )

        return active_guid == target
