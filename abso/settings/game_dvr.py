"""Game DVR hard-off handler.

The launch-time process janitor stops the Game Bar / Game DVR *processes*, but
Windows respawns them next session unless the underlying *settings* are
disarmed. This handler turns Game DVR fully off at the source:

- ``HKCU\\System\\GameConfigStore\\GameDVR_Enabled = 0`` - the master per-user
  Game DVR toggle (the key the WindowsSettingsHandler ``AppCaptureEnabled``
  write does NOT cover).
- ``HKLM\\SOFTWARE\\Policies\\Microsoft\\Windows\\GameDVR\\AllowGameDVR = 0`` -
  the machine policy that hard-disables background recording regardless of the
  per-user toggle.

Both are plain registry values, fully restorable, and take effect for new game
sessions without a reboot.
"""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# (hive, subkey, value_name)
_GAMEDVR_ENABLED = (winreg.HKEY_CURRENT_USER, r"System\GameConfigStore", "GameDVR_Enabled")
_ALLOW_GAMEDVR = (
    winreg.HKEY_LOCAL_MACHINE,
    r"SOFTWARE\Policies\Microsoft\Windows\GameDVR",
    "AllowGameDVR",
)


class GameDvrHandler(SettingsHandler):
    """Hard-disable Game DVR background recording at the registry source."""

    # Opt-in best-effort latency add-on: a verify miss is a WARNING, not a
    # CRITICAL apply failure (apply is best-effort too).
    is_critical_verify = False

    @property
    def restore_guarantee(self) -> str:
        # Permissions/policy can prevent reverting captured values. A failed
        # revert is returned to the transaction instead of claiming success.
        return "partial"

    def detect(self) -> dict[str, Any]:
        """Detect the master Game DVR toggle and the machine policy value."""
        return {
            "game_dvr_enabled": self._read_dword(*_GAMEDVR_ENABLED),
            "allow_game_dvr_policy": self._read_dword(*_ALLOW_GAMEDVR),
        }

    def audit(self) -> list[Issue]:
        """Flag Game DVR that is still armed at the source."""
        issues: list[Issue] = []
        current = self.detect()

        enabled = current.get("game_dvr_enabled")
        policy = current.get("allow_game_dvr_policy")
        # GameDVR_Enabled defaults to 1 (on) when absent.
        armed = enabled in (None, 1) or (policy not in (0,) and policy is not None) or policy is None
        if armed:
            issues.append(
                Issue(
                    title="Game DVR is not hard-disabled",
                    severity="info",
                    current_value=(
                        f"GameDVR_Enabled={enabled}, AllowGameDVR policy={policy}"
                    ),
                    optimal_value="GameDVR_Enabled=0 + AllowGameDVR policy=0",
                    explanation=(
                        "Game DVR background recording adds capture overhead and can "
                        "respawn the Game Bar processes the janitor stops. Hard-disabling "
                        "it at the registry source keeps it off across sessions."
                    ),
                    category="windows",
                )
            )
        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Game DVR settings.

        Settings:
            hard_disable: bool - when True, set GameDVR_Enabled=0 and the
                AllowGameDVR machine policy to 0.
        """
        # Best-effort: this is an opt-in latency add-on, so an individual write
        # failure surfaces as a warning rather than failing (and rolling back)
        # the whole profile apply. verify_active still reports unapplied state.
        warnings: list[str] = []
        changed_keys: list[str] = []

        if settings.get("hard_disable"):
            try:
                if self._write_dword(*_GAMEDVR_ENABLED, 0):
                    changed_keys.append("game_dvr_enabled")
            except OSError as exc:
                warnings.append(f"Game DVR: could not write GameDVR_Enabled ({exc})")
            try:
                if self._write_dword(*_ALLOW_GAMEDVR, 0):
                    changed_keys.append("allow_game_dvr_policy")
            except OSError as exc:
                warnings.append(f"Game DVR: could not write AllowGameDVR policy ({exc})")

        return {
            "success": True,
            "error": None,
            "requires_reboot": False,
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
            "warnings": warnings,
        }

    def backup(self) -> dict[str, Any]:
        """Capture both raw values (None = value absent) for faithful restore."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Write back the captured values, deleting any that were absent."""
        try:
            self._restore_value(*_GAMEDVR_ENABLED, data.get("game_dvr_enabled"))
            self._restore_value(*_ALLOW_GAMEDVR, data.get("allow_game_dvr_policy"))
        except Exception as exc:  # noqa: BLE001 - surface failed rollback to the transaction
            logger.error("Failed to restore Game DVR settings: %s", exc)
            return False
        return True

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify the hard-off values are present after apply."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        if not settings.get("hard_disable"):
            return results

        current = self.detect()
        for key, target in (
            ("game_dvr_enabled", 0),
            ("allow_game_dvr_policy", 0),
        ):
            value = current.get(key)
            active = value == target
            results["settings"][key] = {"target": target, "current": value, "active": active}
            if not active:
                results["all_active"] = False
        return results

    # -- registry helpers --------------------------------------------------

    @staticmethod
    def _read_dword(hive: int, subkey: str, name: str) -> int | None:
        try:
            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
        except FileNotFoundError:
            return None
        except OSError as exc:
            logger.debug("Cannot read %s\\%s: %s", subkey, name, exc)
            return None
        try:
            try:
                value, _ = winreg.QueryValueEx(key, name)
                return int(value)
            except FileNotFoundError:
                return None
        finally:
            winreg.CloseKey(key)

    @staticmethod
    def _write_dword(hive: int, subkey: str, name: str, value: int) -> bool:
        key = winreg.CreateKeyEx(hive, subkey, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
            return True
        finally:
            winreg.CloseKey(key)

    @staticmethod
    def _restore_value(hive: int, subkey: str, name: str, original: int | None) -> None:
        if original is None:
            # Value was absent at backup; remove ABSO's write (best-effort).
            try:
                key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_SET_VALUE)
            except FileNotFoundError:
                return
            try:
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, name)
            finally:
                winreg.CloseKey(key)
            return

        key = winreg.CreateKeyEx(hive, subkey, 0, winreg.KEY_SET_VALUE)
        try:
            winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, int(original))
        finally:
            winreg.CloseKey(key)
