"""Windows gaming settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from gametune.settings.base import SettingsHandler
from gametune.core.models import Issue

logger = logging.getLogger(__name__)


class WindowsSettingsHandler(SettingsHandler):
    """Handles Windows gaming-related settings.

    Manages:
    - Game Mode
    - Game Bar / Game DVR
    - Hardware-Accelerated GPU Scheduling (HAGS)
    - VBS / Memory Integrity
    """

    # Registry paths
    GAME_BAR_KEY = r"Software\Microsoft\GameBar"
    GAME_DVR_KEY = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
    GRAPHICS_DRIVERS_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
    VBS_KEY = r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity"

    def detect(self) -> dict[str, Any]:
        """Detect current Windows gaming settings."""
        return {
            "game_mode": self._get_game_mode(),
            "game_bar": self._get_game_bar(),
            "game_dvr": self._get_game_dvr(),
            "hags": self._get_hags(),
            "vbs": self._get_vbs(),
        }

    def audit(self) -> list[Issue]:
        """Audit Windows settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check Game Mode
        if not current.get("game_mode"):
            issues.append(Issue(
                title="Game Mode is disabled",
                severity="warning",
                current_value="Disabled",
                optimal_value="Enabled",
                explanation="Game Mode prioritizes gaming processes and reduces background activity.",
                category="windows",
            ))

        # Check Game Bar/DVR (should be disabled for performance)
        if current.get("game_bar"):
            issues.append(Issue(
                title="Game Bar is enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation="Game Bar can add slight overhead. Disable unless you use its features.",
                category="windows",
            ))

        if current.get("game_dvr"):
            issues.append(Issue(
                title="Background recording is enabled",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation="Background recording impacts performance even when not actively recording.",
                category="windows",
            ))

        # VBS check
        if current.get("vbs"):
            issues.append(Issue(
                title="VBS / Memory Integrity is enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled (for max performance)",
                explanation=(
                    "VBS provides security but may reduce performance 0-5% depending on workload. "
                    "Impact is often overstated. Test before disabling - security tradeoff may not be worth it."
                ),
                category="windows",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Windows gaming settings."""
        requires_reboot = False
        errors: list[str] = []

        try:
            if "game_mode" in settings:
                self._set_game_mode(settings["game_mode"])

            if "game_bar" in settings:
                self._set_game_bar(settings["game_bar"])

            if "game_dvr" in settings:
                self._set_game_dvr(settings["game_dvr"])

            if "hags" in settings:
                self._set_hags(settings["hags"])
                requires_reboot = True

            if "vbs" in settings:
                self._set_vbs(settings["vbs"])
                requires_reboot = True

        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current Windows gaming settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Windows gaming settings from backup."""
        result = self.apply(data)
        return result.get("success", False)

    # Private helper methods

    def _get_game_mode(self) -> bool | None:
        """Get Game Mode status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_BAR_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "AutoGameModeEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game Mode: {e}")
            return None

    def _set_game_mode(self, enabled: bool) -> None:
        """Set Game Mode status."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.GAME_BAR_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "AllowAutoGameMode", 0, winreg.REG_DWORD, 1 if enabled else 0)
            winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_game_bar(self) -> bool | None:
        """Get Game Bar status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_BAR_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "UseNexusForGameBarEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game Bar: {e}")
            return None

    def _set_game_bar(self, enabled: bool) -> None:
        """Set Game Bar status."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.GAME_BAR_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "UseNexusForGameBarEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_game_dvr(self) -> bool | None:
        """Get Game DVR (background recording) status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_DVR_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "AppCaptureEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game DVR: {e}")
            return None

    def _set_game_dvr(self, enabled: bool) -> None:
        """Set Game DVR status."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.GAME_DVR_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_hags(self) -> bool | None:
        """Get Hardware-Accelerated GPU Scheduling status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.GRAPHICS_DRIVERS_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "HwSchMode")[0]
                return value == 2  # 1 = Off, 2 = On
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get HAGS: {e}")
            return None

    def _set_hags(self, enabled: bool) -> None:
        """Set Hardware-Accelerated GPU Scheduling status."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.GRAPHICS_DRIVERS_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "HwSchMode", 0, winreg.REG_DWORD, 2 if enabled else 1)
        finally:
            winreg.CloseKey(key)

    def _get_vbs(self) -> bool | None:
        """Get VBS / Memory Integrity status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.VBS_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "Enabled")[0]
                return bool(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get VBS: {e}")
            return None

    def _set_vbs(self, enabled: bool) -> None:
        """Set VBS / Memory Integrity status."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.VBS_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)
