"""Storage and filesystem settings handler."""

from __future__ import annotations

import logging
import subprocess
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class StorageSettingsHandler(SettingsHandler):
    """Handles storage and filesystem optimization settings.

    Manages:
    - Last Access Time updates (disablelastaccess)
    - 8.3 Short Filename creation (disable8dot3)
    - TRIM notification (disabledeletenotify)

    Uses fsutil for configuration.

    Technical notes:
    - DisableLastAccess: Prevents updating file access timestamps on every read.
      Reduces disk writes, especially beneficial for HDDs.
    - Disable8dot3: Stops creating legacy short filenames (FILENA~1.TXT).
      Minor performance improvement, may break very old software.
    - TRIM: Should be enabled (disabledeletenotify=0) for SSDs to maintain
      performance over time.
    """

    def detect(self) -> dict[str, Any]:
        """Detect current storage settings."""
        return {
            "last_access_disabled": self._get_last_access_disabled(),
            "short_names_disabled": self._get_8dot3_disabled(),
            "trim_enabled": self._get_trim_enabled(),
        }

    def audit(self) -> list[Issue]:
        """Audit storage settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check Last Access Time
        if not current.get("last_access_disabled"):
            issues.append(Issue(
                title="Last Access Time updates are enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation=(
                    "Windows updates file access timestamps on every read. "
                    "Disabling reduces disk writes and improves I/O performance."
                ),
                category="storage",
            ))

        # Check TRIM (should be enabled for SSDs)
        trim_enabled = current.get("trim_enabled")
        if trim_enabled is False:
            issues.append(Issue(
                title="TRIM is disabled",
                severity="warning",
                current_value="Disabled",
                optimal_value="Enabled",
                explanation=(
                    "TRIM helps SSDs maintain performance by notifying about deleted blocks. "
                    "Should be enabled for any SSD."
                ),
                category="storage",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply storage optimization settings.

        Settings format:
        {
            "disable_last_access": True,
            "disable_8dot3": True,
            "enable_trim": True,
        }

        Or use preset:
        {
            "preset": "gaming"  # Applies all optimizations
        }
        """
        errors: list[str] = []
        requires_reboot = False

        try:
            if settings.get("preset") == "gaming":
                # Apply all optimizations
                result = self._set_last_access_disabled(True)
                if not result["success"]:
                    errors.append(result.get("error", "Failed to disable last access"))
                else:
                    requires_reboot = True

                result = self._set_8dot3_disabled(True)
                if not result["success"]:
                    errors.append(result.get("error", "Failed to disable 8.3 names"))

                result = self._set_trim_enabled(True)
                if not result["success"]:
                    errors.append(result.get("error", "Failed to enable TRIM"))

            else:
                if "disable_last_access" in settings:
                    result = self._set_last_access_disabled(settings["disable_last_access"])
                    if not result["success"]:
                        errors.append(result.get("error", "Failed to set last access"))
                    else:
                        requires_reboot = True

                if "disable_8dot3" in settings:
                    result = self._set_8dot3_disabled(settings["disable_8dot3"])
                    if not result["success"]:
                        errors.append(result.get("error", "Failed to set 8.3 names"))

                if "enable_trim" in settings:
                    result = self._set_trim_enabled(settings["enable_trim"])
                    if not result["success"]:
                        errors.append(result.get("error", "Failed to set TRIM"))

        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current storage settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore storage settings from backup."""
        try:
            if "last_access_disabled" in data:
                self._set_last_access_disabled(data["last_access_disabled"])
            if "short_names_disabled" in data:
                self._set_8dot3_disabled(data["short_names_disabled"])
            if "trim_enabled" in data:
                self._set_trim_enabled(data["trim_enabled"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore storage settings: {e}")
            return False

    # Private helper methods

    def _get_last_access_disabled(self) -> bool | None:
        """Check if Last Access Time updates are disabled."""
        try:
            result = subprocess.run(
                ["fsutil", "behavior", "query", "disablelastaccess"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                # Output like: "DisableLastAccess = 1" or "DisableLastAccess is set to 1"
                output = result.stdout.lower()
                if "= 1" in output or "= 3" in output or "set to 1" in output or "set to 3" in output:
                    return True
                elif "= 0" in output or "= 2" in output or "set to 0" in output or "set to 2" in output:
                    return False

        except subprocess.TimeoutExpired:
            logger.warning("Timeout querying disablelastaccess")
        except Exception as e:
            logger.debug(f"Failed to get disablelastaccess: {e}")

        return None

    def _set_last_access_disabled(self, disabled: bool) -> dict[str, Any]:
        """Enable or disable Last Access Time updates."""
        try:
            # Value 1 = disabled for user mode only
            # Value 3 = disabled for both user and system
            value = "3" if disabled else "0"
            result = subprocess.run(
                ["fsutil", "behavior", "set", "disablelastaccess", value],
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
            return {"success": False, "error": "Timeout setting disablelastaccess"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_8dot3_disabled(self) -> bool | None:
        """Check if 8.3 short filename creation is disabled."""
        try:
            result = subprocess.run(
                ["fsutil", "behavior", "query", "disable8dot3"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                output = result.stdout.lower()
                # Value 1 = disabled on all volumes
                if "= 1" in output or "set to 1" in output:
                    return True
                elif "= 0" in output or "set to 0" in output:
                    return False

        except subprocess.TimeoutExpired:
            logger.warning("Timeout querying disable8dot3")
        except Exception as e:
            logger.debug(f"Failed to get disable8dot3: {e}")

        return None

    def _set_8dot3_disabled(self, disabled: bool) -> dict[str, Any]:
        """Enable or disable 8.3 short filename creation."""
        try:
            value = "1" if disabled else "0"
            result = subprocess.run(
                ["fsutil", "behavior", "set", "disable8dot3", value],
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
            return {"success": False, "error": "Timeout setting disable8dot3"}
        except Exception as e:
            return {"success": False, "error": str(e)}

    def _get_trim_enabled(self) -> bool | None:
        """Check if TRIM is enabled (disabledeletenotify = 0)."""
        try:
            result = subprocess.run(
                ["fsutil", "behavior", "query", "disabledeletenotify"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                output = result.stdout.lower()
                # disabledeletenotify = 0 means TRIM is ENABLED
                if "= 0" in output or "set to 0" in output:
                    return True
                elif "= 1" in output or "set to 1" in output:
                    return False

        except subprocess.TimeoutExpired:
            logger.warning("Timeout querying disabledeletenotify")
        except Exception as e:
            logger.debug(f"Failed to get disabledeletenotify: {e}")

        return None

    def _set_trim_enabled(self, enabled: bool) -> dict[str, Any]:
        """Enable or disable TRIM."""
        try:
            # disabledeletenotify = 0 means TRIM is enabled
            value = "0" if enabled else "1"
            result = subprocess.run(
                ["fsutil", "behavior", "set", "disabledeletenotify", value],
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
            return {"success": False, "error": "Timeout setting TRIM"}
        except Exception as e:
            return {"success": False, "error": str(e)}
