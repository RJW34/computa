"""Audio latency settings handler."""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class AudioSettingsHandler(SettingsHandler):
    """Handles audio latency optimization settings.

    Manages:
    - Exclusive mode priority for audio devices
    - Audio service priority

    Technical notes:
    - Exclusive mode allows applications to bypass Windows audio mixing,
      reducing latency but preventing other apps from using audio.
    - Some competitive players prefer exclusive mode to reduce audio path latency.
    - Changes to audio settings typically require application restart.

    Note: Per-device settings are managed through the Windows Sound control panel.
    This handler focuses on system-wide audio optimizations.
    """

    # Registry paths
    AUDIO_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\Audio"
    MMCSS_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"

    # MMCSS Audio-task values the high-priority apply path writes. Restore must
    # put each one back exactly as captured (or delete it when it was absent at
    # backup time) so a rollback never leaves ABSO-injected audio scheduling
    # values behind on a system whose profile never even touched audio.
    _MANAGED_AUDIO_VALUES: tuple[tuple[str, int], ...] = (
        ("Scheduling Category", winreg.REG_SZ),
        ("SFIO Priority", winreg.REG_SZ),
        ("Priority", winreg.REG_DWORD),
        ("Background Only", winreg.REG_SZ),
    )

    def detect(self) -> dict[str, Any]:
        """Detect current audio settings."""
        return {
            "disable_audio_enhancements": self._get_audio_enhancements_disabled(),
            "audio_service_priority": self._get_audio_priority(),
            "audio_task_state": self._get_audio_task_snapshot(),
        }

    def audit(self) -> list[Issue]:
        """Audit audio settings for ABSO profile conflicts."""
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
        """Apply audio settings.

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
        """Restore audio settings from backup.

        Faithfully reverts only the MMCSS Audio-task values ABSO manages,
        writing each captured value back (or deleting it when it was absent at
        backup time). This must NOT re-run the high-priority apply path, which
        would otherwise re-inject optimization values (``Priority``,
        ``SFIO Priority``, ``Background Only``) that the backup never captured
        and the active profile never changed.

        Legacy backups that only captured the scheduling category restore just
        that value and never create the Audio task key.
        """
        try:
            state = data.get("audio_task_state")
            if isinstance(state, dict) and "values" in state:
                return self._restore_audio_task_state(state)
            # Legacy backup shape: only the Scheduling Category was captured.
            legacy = data.get("audio_service_priority")
            if legacy:
                self._write_scheduling_category_only(str(legacy))
            return True
        except Exception as e:
            logger.error(f"Failed to restore audio settings: {e}")
            return False

    # Private helper methods

    def _get_audio_enhancements_disabled(self) -> bool | None:
        """Check if audio enhancements are disabled on the default audio device.

        Checks the default render (playback) device's FxProperties for the
        DisableAllEnhancements flag.

        Registry path:
        HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render\\{GUID}\\FxProperties
        - DisableAllEnhancements (DWORD): 1 = disabled, 0 or missing = enabled

        Returns:
            True if enhancements are disabled on default device.
            False if enhancements are enabled.
            None if unable to determine (device not found, access denied, etc.).
        """
        mmdevices_key = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"

        try:
            render_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                mmdevices_key,
                0,
                winreg.KEY_READ
            )
        except (FileNotFoundError, PermissionError, OSError) as e:
            logger.debug(f"Cannot access audio devices registry: {e}")
            return None

        try:
            # Find the default device by looking for DeviceState = 1 (active)
            i = 0
            while True:
                try:
                    device_guid = winreg.EnumKey(render_key, i)
                    device_path = f"{mmdevices_key}\\{device_guid}"

                    try:
                        device_key = winreg.OpenKey(
                            winreg.HKEY_LOCAL_MACHINE,
                            device_path,
                            0,
                            winreg.KEY_READ
                        )
                        try:
                            # Check if device is active (DeviceState = 1)
                            state = winreg.QueryValueEx(device_key, "DeviceState")[0]
                            if state == 1:  # Active device
                                # Check FxProperties for DisableAllEnhancements
                                try:
                                    fx_key = winreg.OpenKey(
                                        winreg.HKEY_LOCAL_MACHINE,
                                        f"{device_path}\\FxProperties",
                                        0,
                                        winreg.KEY_READ
                                    )
                                    try:
                                        disabled = winreg.QueryValueEx(
                                            fx_key, "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"
                                        )[0]
                                        # Value of 1 means enhancements are disabled
                                        return disabled == 1
                                    except FileNotFoundError:
                                        # Key exists but value doesn't - enhancements are enabled
                                        return False
                                    finally:
                                        winreg.CloseKey(fx_key)
                                except FileNotFoundError:
                                    # No FxProperties key - enhancements are enabled (default)
                                    return False
                        finally:
                            winreg.CloseKey(device_key)
                    except (FileNotFoundError, PermissionError, OSError):
                        pass  # Skip inaccessible devices

                    i += 1
                except OSError:
                    # No more subkeys
                    break
        finally:
            winreg.CloseKey(render_key)

        # Could not find an active device
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
        key = None
        try:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    f"{self.MMCSS_KEY}\\Tasks\\Audio",
                    0,
                    winreg.KEY_ALL_ACCESS
                )
            except FileNotFoundError:
                # Create the Audio task key if it doesn't exist
                tasks_key = None
                try:
                    tasks_key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        f"{self.MMCSS_KEY}\\Tasks",
                        0,
                        winreg.KEY_ALL_ACCESS
                    )
                    key = winreg.CreateKey(tasks_key, "Audio")
                finally:
                    if tasks_key is not None:
                        winreg.CloseKey(tasks_key)

            if key is not None:
                winreg.SetValueEx(key, "Scheduling Category", 0, winreg.REG_SZ, priority)
                # Also set other audio optimization values. Within the MMCSS
                # scheduling category, "Priority" runs 1-8 (8 highest); the
                # Windows default for the Audio task is 8, so a "High" apply
                # pins 8 rather than the previous (mislabeled) value of 2.
                winreg.SetValueEx(key, "SFIO Priority", 0, winreg.REG_SZ, priority)
                winreg.SetValueEx(key, "Priority", 0, winreg.REG_DWORD, 8)
                winreg.SetValueEx(key, "Background Only", 0, winreg.REG_SZ, "False")
        finally:
            if key is not None:
                winreg.CloseKey(key)

    def _get_audio_task_snapshot(self) -> dict[str, Any]:
        """Capture the MMCSS Audio-task values the apply path manages.

        Returns a structure recording whether the Audio task key exists and the
        current value (or ``None`` when absent) for every managed value, so
        :meth:`restore` can put each one back exactly or remove it.
        """
        values: dict[str, Any] = {name: None for name, _ in self._MANAGED_AUDIO_VALUES}
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{self.MMCSS_KEY}\\Tasks\\Audio",
                0,
                winreg.KEY_READ,
            )
        except FileNotFoundError:
            return {"key_exists": False, "values": values}
        except OSError as e:
            logger.debug(f"Cannot read audio task key: {e}")
            return {"key_exists": False, "values": values}

        try:
            for name, _ in self._MANAGED_AUDIO_VALUES:
                try:
                    values[name] = winreg.QueryValueEx(key, name)[0]
                except FileNotFoundError:
                    values[name] = None
            return {"key_exists": True, "values": values}
        finally:
            winreg.CloseKey(key)

    def _restore_audio_task_state(self, state: dict[str, Any]) -> bool:
        """Revert managed Audio-task values to their captured originals.

        Each managed value present at backup time is written back; any value
        that was absent is deleted so ABSO-injected values do not survive a
        rollback. If the Audio task key does not exist there is nothing ABSO
        could have changed, so the restore is a no-op.
        """
        captured: dict[str, Any] = state.get("values") or {}
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{self.MMCSS_KEY}\\Tasks\\Audio",
                0,
                winreg.KEY_SET_VALUE,
            )
        except FileNotFoundError:
            return True

        try:
            for name, regtype in self._MANAGED_AUDIO_VALUES:
                original = captured.get(name)
                if original is None:
                    with contextlib.suppress(FileNotFoundError):
                        winreg.DeleteValue(key, name)
                else:
                    winreg.SetValueEx(key, name, 0, regtype, original)
        finally:
            winreg.CloseKey(key)
        return True

    def _write_scheduling_category_only(self, value: str) -> None:
        """Write back only the Scheduling Category; never create the key.

        Used for legacy backups that captured only the scheduling category.
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{self.MMCSS_KEY}\\Tasks\\Audio",
                0,
                winreg.KEY_SET_VALUE,
            )
        except FileNotFoundError:
            return

        try:
            winreg.SetValueEx(key, "Scheduling Category", 0, winreg.REG_SZ, value)
        finally:
            winreg.CloseKey(key)
