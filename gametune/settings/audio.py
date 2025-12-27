"""Audio latency settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from gametune.settings.base import SettingsHandler
from gametune.core.models import Issue

logger = logging.getLogger(__name__)


class AudioSettingsHandler(SettingsHandler):
    """Handles audio latency optimization settings.

    Manages:
    - Exclusive mode priority for audio devices
    - Audio service priority

    Technical notes:
    - Exclusive mode allows applications to bypass Windows audio mixing,
      reducing latency but preventing other apps from using audio.
    - Most competitive gamers prefer exclusive mode for lowest latency.
    - Changes to audio settings typically require application restart.

    Note: Per-device settings are managed through the Windows Sound control panel.
    This handler focuses on system-wide audio optimizations.
    """

    # Registry paths
    AUDIO_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio"
    MMCSS_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"

    def detect(self) -> dict[str, Any]:
        """Detect current audio settings."""
        return {
            "disable_audio_enhancements": self._get_audio_enhancements_disabled(),
            "audio_service_priority": self._get_audio_priority(),
        }

    def audit(self) -> list[Issue]:
        """Audit audio settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check audio priority
        priority = current.get("audio_service_priority")
        if priority is not None and priority != "High":
            issues.append(Issue(
                title="Audio service not set to high priority",
                severity="info",
                current_value=str(priority) if priority else "Unknown",
                optimal_value="High",
                explanation=(
                    "Setting audio service to high priority reduces the chance of "
                    "audio crackling or dropouts during intensive gaming."
                ),
                category="audio",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply audio optimization settings.

        Settings format:
        {
            "high_priority": True,
        }
        """
        errors: list[str] = []

        try:
            if settings.get("high_priority"):
                self._set_audio_priority("High")

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
        """Backup current audio settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore audio settings from backup."""
        try:
            if "audio_service_priority" in data and data["audio_service_priority"]:
                self._set_audio_priority(data["audio_service_priority"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore audio settings: {e}")
            return False

    # Private helper methods

    def _get_audio_enhancements_disabled(self) -> bool | None:
        """Check if audio enhancements are disabled globally.

        Note: This is a simplified check. Per-device settings are in:
        HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render\\{GUID}\\FxProperties
        """
        # Global disable is not straightforward in registry
        # This is primarily managed per-device through Sound control panel
        return None

    def _get_audio_priority(self) -> str | None:
        """Get audio service scheduling priority."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{self.MMCSS_KEY}\\Tasks\\Audio",
                0,
                winreg.KEY_READ
            )
            try:
                category = winreg.QueryValueEx(key, "Scheduling Category")[0]
                return category
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            return None
        except Exception as e:
            logger.debug(f"Failed to get audio priority: {e}")
            return None

    def _set_audio_priority(self, priority: str) -> None:
        """Set audio service scheduling priority."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{self.MMCSS_KEY}\\Tasks\\Audio",
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            # Create the Audio task key if it doesn't exist
            tasks_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{self.MMCSS_KEY}\\Tasks",
                0,
                winreg.KEY_ALL_ACCESS
            )
            key = winreg.CreateKey(tasks_key, "Audio")
            winreg.CloseKey(tasks_key)

        try:
            winreg.SetValueEx(key, "Scheduling Category", 0, winreg.REG_SZ, priority)
            # Also set other audio optimization values
            winreg.SetValueEx(key, "SFIO Priority", 0, winreg.REG_SZ, priority)
            winreg.SetValueEx(key, "Priority", 0, winreg.REG_DWORD, 2)  # High priority
            winreg.SetValueEx(key, "Background Only", 0, winreg.REG_SZ, "False")
        finally:
            winreg.CloseKey(key)
