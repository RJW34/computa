"""Windows services settings handler."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from abso.settings.base import SettingsHandler
from abso.core.models import Issue

logger = logging.getLogger(__name__)


class ServicesSettingsHandler(SettingsHandler):
    """Handles Windows service optimization settings.

    Manages services that can impact gaming performance:
    - SysMain (Superfetch) - Memory prefetching, can cause disk I/O spikes
    - DiagTrack - Telemetry collection, uses CPU/disk
    - WSearch - Windows Search indexing
    - Xbox services - Background activity for Xbox features

    Service start types:
    - 2 = Automatic
    - 3 = Manual
    - 4 = Disabled

    Note: Disabling some services may affect Windows features.
    Always backup before making changes.
    """

    # Services to manage for gaming optimization
    GAMING_SERVICES = {
        "SysMain": {
            "display_name": "SysMain (Superfetch)",
            "description": "Prefetches apps into RAM. Can cause disk I/O during gaming.",
            "optimal_start_type": 4,  # Disabled
            "severity": "warning",
        },
        "DiagTrack": {
            "display_name": "Connected User Experiences and Telemetry",
            "description": "Collects and sends diagnostic data. Uses CPU/disk periodically.",
            "optimal_start_type": 4,  # Disabled
            "severity": "info",
        },
        "WSearch": {
            "display_name": "Windows Search",
            "description": "Indexes files for search. Can cause disk I/O spikes.",
            "optimal_start_type": 4,  # Disabled
            "severity": "info",
        },
        "XblAuthManager": {
            "display_name": "Xbox Live Auth Manager",
            "description": "Xbox Live authentication. Disable if not using Xbox features.",
            "optimal_start_type": 4,  # Disabled
            "severity": "info",
        },
        "XblGameSave": {
            "display_name": "Xbox Live Game Save",
            "description": "Xbox Live cloud saves. Disable if not using Xbox features.",
            "optimal_start_type": 4,  # Disabled
            "severity": "info",
        },
        "XboxGipSvc": {
            "display_name": "Xbox Accessory Management",
            "description": "Xbox controller management. Keep if using Xbox controllers.",
            "optimal_start_type": 3,  # Manual (might be needed)
            "severity": "info",
        },
        "XboxNetApiSvc": {
            "display_name": "Xbox Live Networking",
            "description": "Xbox Live networking. Disable if not using Xbox Live.",
            "optimal_start_type": 4,  # Disabled
            "severity": "info",
        },
    }

    # Start type constants
    START_AUTOMATIC = 2
    START_MANUAL = 3
    START_DISABLED = 4

    def detect(self) -> dict[str, Any]:
        """Detect current service states."""
        result = {
            "services": {},
        }

        for service_name in self.GAMING_SERVICES:
            service_info = self._get_service_info(service_name)
            result["services"][service_name] = service_info

        return result

    def audit(self) -> list[Issue]:
        """Audit service settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        for service_name, config in self.GAMING_SERVICES.items():
            service_info = current["services"].get(service_name, {})

            if not service_info.get("exists"):
                continue  # Service doesn't exist on this system

            start_type = service_info.get("start_type")
            optimal_start_type = config["optimal_start_type"]

            # Check if service is running or set to auto-start when it shouldn't be
            if start_type is not None and start_type < optimal_start_type:
                current_state = self._start_type_to_string(start_type)
                optimal_state = self._start_type_to_string(optimal_start_type)

                issues.append(Issue(
                    title=f"{config['display_name']} is {current_state}",
                    severity=config["severity"],
                    current_value=current_state,
                    optimal_value=optimal_state,
                    explanation=config["description"],
                    category="services",
                ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply service settings.

        Settings format:
        {
            "services": {
                "SysMain": {"start_type": 4, "stop": True},
                "DiagTrack": {"start_type": 4, "stop": True},
            }
        }

        Or use preset:
        {
            "preset": "gaming"  # Applies optimal settings for all gaming services
        }
        """
        errors: list[str] = []
        requires_reboot = False

        try:
            if settings.get("preset") == "gaming":
                # Apply optimal settings for all gaming services
                for service_name, config in self.GAMING_SERVICES.items():
                    result = self._set_service_start_type(service_name, config["optimal_start_type"])
                    if not result["success"]:
                        errors.append(result.get("error", f"Failed to configure {service_name}"))
                    else:
                        # Stop the service if we're disabling it
                        if config["optimal_start_type"] == self.START_DISABLED:
                            self._stop_service(service_name)

            elif "services" in settings:
                for service_name, service_settings in settings["services"].items():
                    if "start_type" in service_settings:
                        result = self._set_service_start_type(service_name, service_settings["start_type"])
                        if not result["success"]:
                            errors.append(result.get("error", f"Failed to configure {service_name}"))

                    if service_settings.get("stop"):
                        self._stop_service(service_name)

        except PermissionError as e:
            errors.append(f"Permission denied (requires admin): {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current service settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore service settings from backup."""
        try:
            services = data.get("services", {})
            for service_name, service_info in services.items():
                if service_info.get("exists") and service_info.get("start_type") is not None:
                    self._set_service_start_type(service_name, service_info["start_type"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore service settings: {e}")
            return False

    # Private helper methods

    def _get_service_info(self, service_name: str) -> dict[str, Any]:
        """Get information about a service."""
        result = {
            "exists": False,
            "start_type": None,
            "state": None,
        }

        try:
            # Use sc query to get service state
            query_result = subprocess.run(
                ["sc", "query", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if query_result.returncode == 0:
                result["exists"] = True
                # Parse state from output
                for line in query_result.stdout.splitlines():
                    if "STATE" in line:
                        if "RUNNING" in line:
                            result["state"] = "running"
                        elif "STOPPED" in line:
                            result["state"] = "stopped"
                        break

            # Use sc qc to get start type
            qc_result = subprocess.run(
                ["sc", "qc", service_name],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if qc_result.returncode == 0:
                result["exists"] = True
                for line in qc_result.stdout.splitlines():
                    if "START_TYPE" in line:
                        if "AUTO_START" in line:
                            result["start_type"] = 2
                        elif "DEMAND_START" in line:
                            result["start_type"] = 3
                        elif "DISABLED" in line:
                            result["start_type"] = 4
                        break

        except subprocess.TimeoutExpired:
            logger.warning(f"Timeout querying service {service_name}")
        except Exception as e:
            logger.debug(f"Failed to get service info for {service_name}: {e}")

        return result

    def _set_service_start_type(self, service_name: str, start_type: int) -> dict[str, Any]:
        """Set the start type for a service."""
        start_type_map = {
            2: "auto",
            3: "demand",
            4: "disabled",
        }

        sc_start_type = start_type_map.get(start_type)
        if not sc_start_type:
            return {"success": False, "error": f"Invalid start type: {start_type}"}

        try:
            result = subprocess.run(
                ["sc", "config", service_name, f"start={sc_start_type}"],
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
            return {"success": False, "error": "Timeout configuring service"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _stop_service(self, service_name: str) -> bool:
        """Stop a running service."""
        try:
            result = subprocess.run(
                ["sc", "stop", service_name],
                capture_output=True,
                text=True,
                timeout=30,
            )
            return result.returncode == 0
        except Exception as e:
            logger.debug(f"Failed to stop service {service_name}: {e}")
            return False

    def _start_type_to_string(self, start_type: int) -> str:
        """Convert start type number to human-readable string."""
        return {
            2: "Automatic",
            3: "Manual",
            4: "Disabled",
        }.get(start_type, f"Unknown ({start_type})")
