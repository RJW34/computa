"""Graphics and display settings handler."""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class GraphicsSettingsHandler(SettingsHandler):
    """Handles graphics and display optimization settings.

    Manages:
    - Multi-Plane Overlay (MPO) - can cause stutter on some systems
    - Desktop Window Manager (DWM) settings
    - Global Fullscreen Optimizations (FSO)
    - Hardware cursor settings

    Technical notes:
    - MPO allows Windows to composite multiple planes in hardware
      Can cause issues with G-Sync, overlays, and some games
    - FSO (GameDVR_FSEBehavior) controls whether games get true exclusive fullscreen
    - DWM cannot be disabled on Windows 10/11 but some settings can be tuned

    Reboot behavior:
    - MPO changes (OverlayTestMode registry key) require a reboot to take effect
    - HOWEVER, if MPO is already disabled from a previous profile application,
      no reboot is needed when switching to another profile that also disables MPO
    - FSO changes take effect immediately on next game launch (no reboot needed)
    - Switching between profiles that share the same MPO setting won't require a reboot
    """

    # Registry paths
    DWM_KEY = r"SOFTWARE\Microsoft\Windows\Dwm"
    GAME_CONFIG_KEY = r"System\GameConfigStore"
    EXPLORER_ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    COLOR_MANAGEMENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\ColorManagement"
    MONITOR_DATA_STORE_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers\MonitorDataStore"

    def detect(self) -> dict[str, Any]:
        """Detect current graphics settings."""
        return {
            "mpo_disabled": self._get_mpo_disabled(),
            "global_fso_disabled": self._get_global_fso_disabled(),
            "game_dvr_behavior": self._get_game_dvr_behavior(),
            "hardware_cursor": self._get_hardware_cursor(),
            "auto_color_management": self._get_auto_color_management(),
        }

    def audit(self) -> list[Issue]:
        """Audit graphics settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check MPO status
        if not current.get("mpo_disabled"):
            issues.append(Issue(
                title="Multi-Plane Overlay (MPO) is enabled",
                severity="info",
                current_value="Enabled (default)",
                optimal_value="Disabled (if experiencing stutter)",
                explanation=(
                    "MPO allows hardware compositing of overlays but can cause stuttering "
                    "with G-Sync, screen recording, and certain games. Disable if you "
                    "experience micro-stutter, especially with multiple monitors or overlays."
                ),
                category="graphics",
            ))

        # Check global FSO status
        game_dvr_behavior = current.get("game_dvr_behavior")
        if game_dvr_behavior != 2:
            issues.append(Issue(
                title="Global Fullscreen Optimizations enabled",
                severity="info",
                current_value="Enabled" if game_dvr_behavior != 2 else "Disabled",
                optimal_value="Disabled (GameDVR_FSEBehavior=2)",
                explanation=(
                    "Fullscreen Optimizations run games in borderless windowed mode for "
                    "faster alt-tabbing. This adds ~1 frame of latency. Disabling forces "
                    "true exclusive fullscreen for games that support it."
                ),
                category="graphics",
            ))

        # Check Auto Color Management (ACM) status
        acm_status = current.get("auto_color_management", {})
        acm_enabled_monitors = []
        for monitor_id, enabled in acm_status.get("per_monitor", {}).items():
            if enabled:
                acm_enabled_monitors.append(monitor_id)

        if acm_enabled_monitors:
            issues.append(Issue(
                title="Auto Color Management (ACM) is enabled",
                severity="warning",
                current_value=f"Enabled on {len(acm_enabled_monitors)} monitor(s)",
                optimal_value="Disabled",
                explanation=(
                    "Auto Color Management adds color profile processing to the display "
                    "pipeline, which can introduce latency and color inconsistencies in "
                    "games. Disable via Settings > Display > Advanced display for each "
                    "monitor. This is mainly useful for color-accurate creative work."
                ),
                category="graphics",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply graphics optimization settings.

        Only sets requires_reboot=True if we actually change MPO state.
        If MPO is already in the desired state, no reboot is needed.
        """
        errors: list[str] = []
        requires_reboot = False

        # Get current values to check if we're actually changing anything
        current = self.detect()

        try:
            if "disable_mpo" in settings:
                target = settings["disable_mpo"]
                if current.get("mpo_disabled") != target:
                    self._set_mpo_disabled(target)
                    requires_reboot = True  # Actually changed MPO state

            if "disable_global_fso" in settings:
                self._set_global_fso_disabled(settings["disable_global_fso"])

            if "game_dvr_behavior" in settings:
                self._set_game_dvr_behavior(settings["game_dvr_behavior"])

        except PermissionError as e:
            errors.append(f"Permission denied: {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
        }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify that reboot-requiring settings are already active.

        Use this to check if MPO setting is actually in effect.

        Returns:
            Dict with 'all_active' bool and details for each setting.
        """
        current = self.detect()
        results = {"all_active": True, "settings": {}}

        if "disable_mpo" in settings:
            target = settings["disable_mpo"]
            is_active = current.get("mpo_disabled") == target
            results["settings"]["mpo_disabled"] = {
                "target": target,
                "current": current.get("mpo_disabled"),
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Backup current graphics settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore graphics settings from backup."""
        try:
            if "mpo_disabled" in data:
                self._set_mpo_disabled(data["mpo_disabled"])
            if "game_dvr_behavior" in data and data["game_dvr_behavior"] is not None:
                self._set_game_dvr_behavior(data["game_dvr_behavior"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore graphics settings: {e}")
            return False

    # Private helper methods

    def _get_mpo_disabled(self) -> bool:
        """Check if Multi-Plane Overlay is disabled."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.DWM_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "OverlayTestMode")[0]
                # OverlayTestMode = 5 disables MPO
                return value == 5
            except FileNotFoundError:
                return False  # Not set = MPO enabled (default)
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get MPO status: {e}")
            return False

    def _set_mpo_disabled(self, disabled: bool) -> None:
        """Enable or disable Multi-Plane Overlay."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.DWM_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            if disabled:
                # Set OverlayTestMode = 5 to disable MPO
                winreg.SetValueEx(key, "OverlayTestMode", 0, winreg.REG_DWORD, 5)
            else:
                # Remove the key to re-enable MPO
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, "OverlayTestMode")
        finally:
            winreg.CloseKey(key)

    def _get_global_fso_disabled(self) -> bool:
        """Check if global Fullscreen Optimizations are disabled."""
        behavior = self._get_game_dvr_behavior()
        # GameDVR_FSEBehavior = 2 means FSO disabled globally
        return behavior == 2

    def _get_game_dvr_behavior(self) -> int | None:
        """Get GameDVR Fullscreen Exclusive behavior.

        Values:
        0 = Default (FSO enabled)
        1 = FSO enabled
        2 = FSO disabled (true exclusive fullscreen)
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_CONFIG_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "GameDVR_FSEBehavior")[0]
                return value
            except FileNotFoundError:
                return 0  # Default
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get GameDVR_FSEBehavior: {e}")
            return None

    def _set_game_dvr_behavior(self, value: int) -> None:
        """Set GameDVR Fullscreen Exclusive behavior."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_CONFIG_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.GAME_CONFIG_KEY)

        try:
            winreg.SetValueEx(key, "GameDVR_FSEBehavior", 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)

    def _set_global_fso_disabled(self, disabled: bool) -> None:
        """Enable or disable global Fullscreen Optimizations."""
        self._set_game_dvr_behavior(2 if disabled else 0)

    def _get_hardware_cursor(self) -> bool | None:
        """Check if hardware cursor is enabled (vs software cursor)."""
        # Hardware cursor is default and generally preferred
        # This is mostly informational
        try:
            # Check for software cursor override
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.EXPLORER_ADVANCED_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                # If DisableHardwareCursor exists and is 1, hardware cursor is off
                value = winreg.QueryValueEx(key, "DisableHardwareCursor")[0]
                return value != 1
            except FileNotFoundError:
                return True  # Default = hardware cursor enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get hardware cursor status: {e}")
            return None

    def _get_auto_color_management(self) -> dict[str, Any]:
        """Check Auto Color Management (ACM) status.

        ACM is a Windows 11 feature that applies color profiles automatically.
        For gaming, ACM adds processing overhead and should generally be disabled.

        Returns:
            Dict with 'global' (bool or None) and 'per_monitor' (dict of monitor_id: bool)
        """
        result: dict[str, Any] = {
            "global": None,
            "per_monitor": {},
        }

        # Check global ACM setting (HKCU)
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.COLOR_MANAGEMENT_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "AutoColorManagement")[0]
                result["global"] = value != 0
            except FileNotFoundError:
                result["global"] = None  # Not set
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get global ACM status: {e}")

        # Check per-monitor ACM settings
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MONITOR_DATA_STORE_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                # Enumerate all monitor subkeys
                i = 0
                while True:
                    try:
                        monitor_id = winreg.EnumKey(key, i)
                        i += 1
                        # Check this monitor's ACM setting
                        try:
                            monitor_key = winreg.OpenKey(
                                key,
                                monitor_id,
                                0,
                                winreg.KEY_READ
                            )
                            try:
                                value = winreg.QueryValueEx(
                                    monitor_key, "AutoColorManagementEnabled"
                                )[0]
                                result["per_monitor"][monitor_id] = value != 0
                            except FileNotFoundError:
                                # Not set = disabled by default
                                result["per_monitor"][monitor_id] = False
                            finally:
                                winreg.CloseKey(monitor_key)
                        except Exception as e:
                            logger.debug(f"Failed to read ACM for monitor {monitor_id}: {e}")
                    except OSError:
                        break  # No more subkeys
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to enumerate monitors for ACM: {e}")

        return result
