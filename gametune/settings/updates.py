"""Windows Update settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from gametune.settings.base import SettingsHandler
from gametune.core.models import Issue

logger = logging.getLogger(__name__)


class UpdatesSettingsHandler(SettingsHandler):
    """Handles Windows Update optimization settings.

    Manages:
    - Delivery Optimization (P2P updates)
    - Active Hours (prevent updates during gaming)
    - Update pause status

    Technical notes:
    - Delivery Optimization can use bandwidth for P2P sharing of updates
    - Disabling P2P can reduce network usage during gaming
    - Active Hours setting prevents restarts during specified times

    Note: This handler does NOT disable Windows Update entirely (which would
    be a security risk). It only optimizes update behavior for gaming.
    """

    # Registry paths
    DELIVERY_OPT_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\DeliveryOptimization\Config"
    WINDOWS_UPDATE_KEY = r"SOFTWARE\Microsoft\WindowsUpdate\UX\Settings"
    AU_KEY = r"SOFTWARE\Policies\Microsoft\Windows\WindowsUpdate\AU"

    def detect(self) -> dict[str, Any]:
        """Detect current Windows Update settings."""
        return {
            "delivery_optimization": self._get_delivery_optimization(),
            "active_hours": self._get_active_hours(),
            "updates_paused": self._get_updates_paused(),
        }

    def audit(self) -> list[Issue]:
        """Audit Windows Update settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check Delivery Optimization
        do_mode = current.get("delivery_optimization", {}).get("download_mode")
        if do_mode is not None and do_mode > 0:
            mode_names = {
                0: "HTTP only (disabled)",
                1: "LAN only",
                2: "LAN + Internet",
                3: "LAN + Internet + Group",
                99: "Simple (no peering)",
                100: "Bypass",
            }
            issues.append(Issue(
                title="Delivery Optimization P2P is enabled",
                severity="info",
                current_value=mode_names.get(do_mode, f"Mode {do_mode}"),
                optimal_value="HTTP only (disabled)",
                explanation=(
                    "Delivery Optimization shares updates with other PCs, using bandwidth. "
                    "Disabling P2P ensures all bandwidth is available for gaming."
                ),
                category="updates",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Windows Update optimization settings.

        Settings format:
        {
            "disable_p2p": True,
            "active_hours": {"start": 8, "end": 2},  # 8 AM to 2 AM
        }
        """
        errors: list[str] = []

        try:
            if settings.get("disable_p2p"):
                self._set_delivery_optimization_mode(0)  # HTTP only

            if "active_hours" in settings:
                hours = settings["active_hours"]
                self._set_active_hours(hours.get("start", 8), hours.get("end", 2))

        except PermissionError as e:
            errors.append(f"Permission denied: {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current Windows Update settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Windows Update settings from backup."""
        try:
            do_settings = data.get("delivery_optimization", {})
            if "download_mode" in do_settings:
                self._set_delivery_optimization_mode(do_settings["download_mode"])

            active_hours = data.get("active_hours", {})
            if "start" in active_hours and "end" in active_hours:
                self._set_active_hours(active_hours["start"], active_hours["end"])

            return True
        except Exception as e:
            logger.error(f"Failed to restore Windows Update settings: {e}")
            return False

    # Private helper methods

    def _get_delivery_optimization(self) -> dict[str, Any]:
        """Get Delivery Optimization settings."""
        result = {
            "download_mode": None,
        }

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.DELIVERY_OPT_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                result["download_mode"] = winreg.QueryValueEx(key, "DODownloadMode")[0]
            except FileNotFoundError:
                pass
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"Failed to get Delivery Optimization settings: {e}")

        return result

    def _set_delivery_optimization_mode(self, mode: int) -> None:
        """Set Delivery Optimization download mode.

        Modes:
        0 = HTTP only (no P2P)
        1 = LAN only
        2 = LAN + Internet
        3 = LAN + Internet + Group
        99 = Simple (download only)
        100 = Bypass (use BITS)
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.DELIVERY_OPT_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, self.DELIVERY_OPT_KEY)

        try:
            winreg.SetValueEx(key, "DODownloadMode", 0, winreg.REG_DWORD, mode)
        finally:
            winreg.CloseKey(key)

    def _get_active_hours(self) -> dict[str, Any]:
        """Get Active Hours settings."""
        result = {
            "start": None,
            "end": None,
        }

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.WINDOWS_UPDATE_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                result["start"] = winreg.QueryValueEx(key, "ActiveHoursStart")[0]
            except FileNotFoundError:
                pass
            try:
                result["end"] = winreg.QueryValueEx(key, "ActiveHoursEnd")[0]
            except FileNotFoundError:
                pass
            winreg.CloseKey(key)
        except FileNotFoundError:
            pass
        except Exception as e:
            logger.debug(f"Failed to get Active Hours: {e}")

        return result

    def _set_active_hours(self, start: int, end: int) -> None:
        """Set Active Hours (when Windows won't restart for updates).

        Args:
            start: Start hour (0-23)
            end: End hour (0-23)

        Note: Active hours can span up to 18 hours.
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.WINDOWS_UPDATE_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, self.WINDOWS_UPDATE_KEY)

        try:
            winreg.SetValueEx(key, "ActiveHoursStart", 0, winreg.REG_DWORD, start)
            winreg.SetValueEx(key, "ActiveHoursEnd", 0, winreg.REG_DWORD, end)
        finally:
            winreg.CloseKey(key)

    def _get_updates_paused(self) -> bool | None:
        """Check if updates are currently paused."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.WINDOWS_UPDATE_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "PauseUpdatesExpiryTime")[0]
                # If there's a pause expiry time in the future, updates are paused
                return value is not None and len(value) > 0
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get pause status: {e}")
            return None
