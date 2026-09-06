"""Audio engine (APO) enhancement-chain handler.

Windows runs every render stream through the device's Audio Processing Object
(APO) enhancement chain unless that chain is explicitly disabled. The chain adds
DPC-latency overhead on the audio path, so turning it off on the active default
render device is a documented latency reducer for gaming.

The "disable all enhancements" flag lives under each render device's
``FxProperties`` subkey:

``HKLM\\SOFTWARE\\Microsoft\\Windows\\CurrentVersion\\MMDevices\\Audio\\Render\\{deviceGuid}\\FxProperties``

with value name ``{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5`` (REG_DWORD):

- ``1`` -> enhancements disabled
- ``0`` or absent -> enhancements enabled (Windows default)

This is the same registry shape ``AudioSettingsHandler`` reads; this handler owns
*writing* it. The active device is found exactly as ``audio.py`` enumerates it
(the render subkey whose ``DeviceState`` is ``1``).
"""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# Render device enumeration root and the "disable all enhancements" flag.
_RENDER_ROOT = r"SOFTWARE\Microsoft\Windows\CurrentVersion\MMDevices\Audio\Render"
_FX_VALUE_NAME = "{1da5d803-d492-4edd-8c23-e0c0ffee7f0e},5"


class AudioEngineHandler(SettingsHandler):
    """Disable the Windows audio enhancement (APO) chain on the default device."""

    # Opt-in best-effort latency add-on: a verify miss is a WARNING, not a
    # CRITICAL apply failure (apply is best-effort too).
    is_critical_verify = False

    @property
    def restore_guarantee(self) -> str:
        # Device availability/permissions can prevent a complete revert.
        return "partial"

    def detect(self) -> dict[str, Any]:
        """Detect the enhancement-chain state of the active render device.

        Returns:
            Dictionary with ``enhancements_disabled`` (True when the chain is
            off, False when it is on, None when undeterminable) and
            ``device_guid`` (the active device's GUID, or None).
        """
        guid = self._find_active_device_guid()
        if guid is None:
            return {"enhancements_disabled": None, "device_guid": None}
        flag = self._read_fx_flag(guid)
        disabled = None if flag is None else flag == 1
        return {"enhancements_disabled": disabled, "device_guid": guid}

    def audit(self) -> list[Issue]:
        """Flag an active device whose enhancement chain is still enabled."""
        issues: list[Issue] = []
        current = self.detect()

        # Only emit when we positively determined the chain is NOT disabled.
        if current.get("enhancements_disabled") is False:
            issues.append(
                Issue(
                    title="Audio enhancement (APO) chain is not disabled",
                    severity="info",
                    current_value="Enhancements enabled",
                    optimal_value="Enhancements disabled",
                    explanation=(
                        "Windows routes the default render device through its audio "
                        "enhancement (APO) chain, which adds DPC-latency overhead on the "
                        "audio path. Disabling all enhancements on the active device "
                        "trims that overhead for gaming."
                    ),
                    category="audio",
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply the enhancement-chain setting.

        Settings:
            disable_enhancements: bool - when True, set the
                ``DisableAllEnhancements`` flag to 1 on the active render device.
        """
        # Best-effort: this is an opt-in latency add-on, so a missing device or
        # a write failure surfaces as a warning rather than failing (and rolling
        # back) the whole profile apply. verify_active still reports the state.
        warnings: list[str] = []
        changed_keys: list[str] = []

        if settings.get("disable_enhancements"):
            guid = self._find_active_device_guid()
            if guid is None:
                warnings.append("Audio enhancements: no active render device found")
            else:
                try:
                    if self._write_fx_flag(guid, 1):
                        changed_keys.append("enhancements_disabled")
                except OSError as exc:
                    warnings.append(f"Audio enhancements: could not write flag ({exc})")

        # Audio changes typically take effect on the next audio-stream start,
        # so no reboot is required.
        return {
            "success": True,
            "error": None,
            "requires_reboot": False,
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
            "warnings": warnings,
        }

    def backup(self) -> dict[str, Any]:
        """Capture the active device GUID and its original flag value.

        Returns:
            Dictionary with ``device_guid`` and ``original_flag`` (the raw flag
            value, or None when the value/key was absent at backup time).
        """
        guid = self._find_active_device_guid()
        original = self._read_fx_flag(guid) if guid is not None else None
        return {"device_guid": guid, "original_flag": original}

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore the captured flag, deleting it if it was absent at backup."""
        guid = data.get("device_guid")
        if not guid:
            # Nothing was captured (no active device at backup); nothing to do.
            return True
        try:
            self._restore_fx_flag(str(guid), data.get("original_flag"))
        except Exception as exc:  # noqa: BLE001 - surface failed rollback to the transaction
            logger.error("Failed to restore audio enhancement flag: %s", exc)
            return False
        return True

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify the enhancement chain is disabled on the active device."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        if not settings.get("disable_enhancements"):
            return results

        guid = self._find_active_device_guid()
        flag = self._read_fx_flag(guid) if guid is not None else None
        active = flag == 1
        results["settings"]["enhancements_disabled"] = {
            "target": 1,
            "current": flag,
            "active": active,
        }
        results["all_active"] = active
        return results

    # -- registry helpers --------------------------------------------------

    @staticmethod
    def _find_active_device_guid() -> str | None:
        """Return the GUID of the active default render device (DeviceState==1)."""
        try:
            render_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, _RENDER_ROOT, 0, winreg.KEY_READ
            )
        except (FileNotFoundError, PermissionError, OSError) as exc:
            logger.debug("Cannot access render devices registry: %s", exc)
            return None

        try:
            i = 0
            while True:
                try:
                    guid = winreg.EnumKey(render_key, i)
                except OSError:
                    break  # No more subkeys.
                i += 1
                try:
                    device_key = winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        f"{_RENDER_ROOT}\\{guid}",
                        0,
                        winreg.KEY_READ,
                    )
                except (FileNotFoundError, PermissionError, OSError):
                    continue  # Skip inaccessible devices.
                try:
                    try:
                        state = winreg.QueryValueEx(device_key, "DeviceState")[0]
                    except FileNotFoundError:
                        continue
                    if state == 1:
                        return guid
                finally:
                    winreg.CloseKey(device_key)
        finally:
            winreg.CloseKey(render_key)
        return None

    @staticmethod
    def _read_fx_flag(guid: str | None) -> int | None:
        """Read the DisableAllEnhancements flag for a device GUID (None if absent)."""
        if not guid:
            return None
        try:
            fx_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                f"{_RENDER_ROOT}\\{guid}\\FxProperties",
                0,
                winreg.KEY_READ,
            )
        except (FileNotFoundError, PermissionError, OSError):
            return None
        try:
            try:
                return int(winreg.QueryValueEx(fx_key, _FX_VALUE_NAME)[0])
            except FileNotFoundError:
                return None
        finally:
            winreg.CloseKey(fx_key)

    @staticmethod
    def _write_fx_flag(guid: str, value: int) -> bool:
        """Write the DisableAllEnhancements flag, creating FxProperties if absent."""
        # CreateKeyEx opens the subkey when present and creates it (and any
        # missing FxProperties parent) when it is not.
        key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            f"{_RENDER_ROOT}\\{guid}\\FxProperties",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            winreg.SetValueEx(key, _FX_VALUE_NAME, 0, winreg.REG_DWORD, value)
            return True
        finally:
            winreg.CloseKey(key)

    @staticmethod
    def _restore_fx_flag(guid: str, original: int | None) -> None:
        """Write back the captured flag, or delete it if it was absent at backup."""
        if original is None:
            # Flag was absent at backup; remove ABSO's write (best-effort).
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    f"{_RENDER_ROOT}\\{guid}\\FxProperties",
                    0,
                    winreg.KEY_SET_VALUE,
                )
            except FileNotFoundError:
                return
            try:
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, _FX_VALUE_NAME)
            finally:
                winreg.CloseKey(key)
            return

        key = winreg.CreateKeyEx(
            winreg.HKEY_LOCAL_MACHINE,
            f"{_RENDER_ROOT}\\{guid}\\FxProperties",
            0,
            winreg.KEY_SET_VALUE,
        )
        try:
            winreg.SetValueEx(key, _FX_VALUE_NAME, 0, winreg.REG_DWORD, int(original))
        finally:
            winreg.CloseKey(key)
