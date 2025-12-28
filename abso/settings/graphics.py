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
    """

    # Registry paths
    DWM_KEY = r"SOFTWARE\Microsoft\Windows\Dwm"
    GAME_CONFIG_KEY = r"System\GameConfigStore"
    EXPLORER_ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"

    def detect(self) -> dict[str, Any]:
        """Detect current graphics settings."""
        return {
            "mpo_disabled": self._get_mpo_disabled(),
            "global_fso_disabled": self._get_global_fso_disabled(),
            "game_dvr_behavior": self._get_game_dvr_behavior(),
            "hardware_cursor": self._get_hardware_cursor(),
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

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply graphics optimization settings."""
        errors: list[str] = []
        requires_reboot = False

        try:
            if "disable_mpo" in settings:
                self._set_mpo_disabled(settings["disable_mpo"])
                requires_reboot = True  # MPO changes require reboot

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
