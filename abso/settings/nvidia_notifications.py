"""NVIDIA notification settings handler.

Manages NVIDIA notification popups that can interfere with exclusive fullscreen
gaming. Uses registry keys to suppress GeForce Experience / NVIDIA App notifications.
"""

from __future__ import annotations

import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# Registry path for NVIDIA notification settings
NVIDIA_NOTIFICATION_KEY = r"SOFTWARE\NVIDIA Corporation\NvTray"
NVIDIA_GFE_KEY = r"SOFTWARE\NVIDIA Corporation\Global\GFExperience"


class NvidiaNotificationHandler(SettingsHandler):
    """Disables NVIDIA notifications that can break exclusive fullscreen.

    NVIDIA GeForce Experience and the NVIDIA App can show overlay notifications
    (driver updates, game optimization suggestions, etc.) that force games out
    of exclusive fullscreen mode, causing stuttering and latency spikes.

    The performance overlay (Alt+R) is NOT affected by these settings.
    """

    def detect(self) -> dict[str, Any]:
        """Detect current NVIDIA notification settings."""
        return {
            "notifications_disabled": self._get_notifications_disabled(),
        }

    def audit(self) -> list[Issue]:
        """Audit NVIDIA notification settings."""
        issues: list[Issue] = []
        current = self.detect()

        if not current.get("notifications_disabled"):
            issues.append(Issue(
                title="NVIDIA notifications enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation=(
                    "NVIDIA overlay notifications can break exclusive fullscreen mode, "
                    "causing frame drops and latency spikes. Disabling notifications "
                    "prevents these interruptions. The performance overlay (Alt+R) "
                    "still works."
                ),
                category="nvidia",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply NVIDIA notification settings."""
        errors: list[str] = []

        try:
            if settings.get("disable_notifications"):
                self._set_notifications_disabled(True)
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
        """Backup current NVIDIA notification settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore NVIDIA notification settings from backup."""
        try:
            was_disabled = data.get("notifications_disabled", False)
            self._set_notifications_disabled(was_disabled)
            return True
        except Exception as e:
            logger.error(f"Failed to restore NVIDIA notification settings: {e}")
            return False

    def _get_notifications_disabled(self) -> bool:
        """Check if NVIDIA notifications are disabled."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                NVIDIA_NOTIFICATION_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                value = winreg.QueryValueEx(key, "ShowNotifications")[0]
                return value == 0
            except FileNotFoundError:
                return False  # Not set = notifications enabled (default)
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get NVIDIA notification status: {e}")
            return False

    def _set_notifications_disabled(self, disabled: bool) -> None:
        """Enable or disable NVIDIA notifications."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                NVIDIA_NOTIFICATION_KEY,
                0,
                winreg.KEY_ALL_ACCESS,
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, NVIDIA_NOTIFICATION_KEY)

        try:
            winreg.SetValueEx(
                key, "ShowNotifications", 0, winreg.REG_DWORD, 0 if disabled else 1
            )
        finally:
            winreg.CloseKey(key)
