"""Registry settings handler."""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.exceptions import RegistryWriteError
from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler
from abso.utils.validation import (
    validate_dword_value,
    validate_executable_path,
    validate_priority_value,
)

logger = logging.getLogger(__name__)


class RegistrySettingsHandler(SettingsHandler):
    """Handles registry-based gaming optimizations.

    Manages:
    - Multimedia scheduling / Game priority
    - Fullscreen optimizations
    - System responsiveness
    - Windows scheduler (Win32PrioritySeparation)
    """

    # Registry paths
    MULTIMEDIA_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile"
    GAMES_TASK_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
    APPCOMPAT_KEY = r"Software\Microsoft\Windows NT\CurrentVersion\AppCompatFlags\Layers"
    PRIORITY_CONTROL_KEY = r"SYSTEM\CurrentControlSet\Control\PriorityControl"

    # Win32PrioritySeparation values
    # Format: 0xAABBCC where (6-bit value):
    #   Bits 5-4 (AA): Quantum length (0/1=default, 2=short, 3=long)
    #   Bits 3-2 (BB): Quantum type (0/1=default, 2=fixed, 3=variable)
    #   Bits 1-0 (CC): Foreground boost (0=none, 1=minimum, 2=maximum)
    # Ref: Windows Internals (Russinovich), "Master Your Quantum" (MSDN archive)
    #
    # Common values:
    # 0x26 (38) = Short, variable, max boost (Windows desktop default)
    # 0x28 (40) = Short, variable, no boost
    # 0x2A (42) = Short, fixed, max boost (recommended for gaming)
    #
    # Short fixed quantum with max foreground boost gives games more responsive
    # CPU scheduling while prioritizing the active window.
    WIN32_PRIORITY_DEFAULT = 0x26  # Windows default for desktop
    WIN32_PRIORITY_GAMING = 0x2A   # Short fixed quantum, max foreground boost

    def detect(self) -> dict[str, Any]:
        """Detect current registry gaming settings."""
        result: dict[str, Any] = {
            "system_responsiveness": self._get_system_responsiveness(),
            "network_throttling": self._get_network_throttling(),
            "game_priority": self._get_game_priority(),
            "win32_priority_separation": self._get_win32_priority_separation(),
        }
        # Omit fullscreen_optimizations from the snapshot entirely if
        # enumeration can't be proven complete. restore() skips missing
        # keys, so this protects current state from being overwritten by
        # a truncated snapshot later.
        try:
            result["fullscreen_optimizations"] = self._enumerate_fullscreen_optimizations()
        except OSError as e:
            logger.warning(
                "Skipping fullscreen_optimizations in backup snapshot; "
                "AppCompatFlags\\Layers enumeration failed: %s",
                e,
            )
        return result

    def audit(self) -> list[Issue]:
        """Audit registry settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # System Responsiveness — legacy MMCSS setting, undocumented behavior on Win11
        responsiveness = current.get("system_responsiveness")
        if responsiveness is not None and responsiveness != 10:
            issues.append(Issue(
                title="System Responsiveness not optimized for gaming",
                severity="info",
                current_value=str(responsiveness),
                optimal_value="10",
                explanation=(
                    "MMCSS scheduling hint for background CPU reservation. "
                    "Effect on modern Windows 11 is undocumented — MMCSS was redesigned "
                    "in Win10+. May have no measurable impact on current systems. "
                    "Opt-in via include_legacy_tweaks."
                ),
                category="registry",
                evidence_tier=EvidenceTier.LEGACY_UNVERIFIED,
            ))

        # Network Throttling — legacy multimedia setting, unclear modern effect
        throttling = current.get("network_throttling")
        if throttling is not None and throttling != 0xFFFFFFFF:
            issues.append(Issue(
                title="Network throttling is enabled",
                severity="info",
                current_value=f"0x{throttling:08X}" if throttling else "Unknown",
                optimal_value="0xFFFFFFFF (disabled)",
                explanation=(
                    "Multimedia network throttling index — originally designed for "
                    "Vista-era media streaming. Microsoft has not documented its effect "
                    "on Windows 10/11 network stacks. Likely no measurable impact. "
                    "Opt-in via include_legacy_tweaks."
                ),
                category="registry",
                evidence_tier=EvidenceTier.LEGACY_UNVERIFIED,
            ))

        # Game priority settings — documented MMCSS task priority
        game_priority = current.get("game_priority", {})
        if game_priority.get("priority") != 6:
            issues.append(Issue(
                title="Game process priority not optimized",
                severity="info",
                current_value=str(game_priority.get("priority", "Unknown")),
                optimal_value="6",
                explanation=(
                    "MMCSS Games task priority. Higher values give game threads "
                    "more CPU scheduling preference via the multimedia class scheduler."
                ),
                category="registry",
                evidence_tier=EvidenceTier.VERIFIED,
            ))

        # Win32PrioritySeparation (scheduler quantum) — documented kernel behavior
        priority_sep = current.get("win32_priority_separation")
        if priority_sep is not None and priority_sep != self.WIN32_PRIORITY_GAMING:
            issues.append(Issue(
                title="Windows scheduler not optimized for gaming",
                severity="info",
                current_value=f"0x{priority_sep:02X}" if priority_sep else "Unknown",
                optimal_value=f"0x{self.WIN32_PRIORITY_GAMING:02X}",
                explanation=(
                    "Win32PrioritySeparation controls CPU time slice allocation. "
                    "0x2A uses short fixed quantum with max foreground boost, "
                    "giving the active game more responsive CPU scheduling. "
                    "Documented in Windows Internals (Russinovich)."
                ),
                category="registry",
                evidence_tier=EvidenceTier.VERIFIED,
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply registry gaming settings.

        Each setting is applied independently so partial failures don't
        prevent other settings from being applied. All errors are collected
        and reported.
        """
        errors: list[str] = []
        applied: list[str] = []

        # System Responsiveness
        if "system_responsiveness" in settings:
            try:
                self._set_system_responsiveness(settings["system_responsiveness"])
                applied.append("SystemResponsiveness")
                logger.info(f"Set SystemResponsiveness = {settings['system_responsiveness']}")
            except Exception as e:
                errors.append(f"SystemResponsiveness: {e}")
                logger.error(f"Failed to set SystemResponsiveness: {e}")

        # Network Throttling
        if "network_throttling" in settings:
            try:
                self._set_network_throttling(settings["network_throttling"])
                applied.append("NetworkThrottling")
                logger.info(f"Set NetworkThrottlingIndex = 0x{settings['network_throttling']:08X}")
            except Exception as e:
                errors.append(f"NetworkThrottling: {e}")
                logger.error(f"Failed to set NetworkThrottling: {e}")

        # Game Priority
        if "game_priority" in settings:
            try:
                self._set_game_priority(settings["game_priority"])
                applied.append("GamePriority")
                logger.info(f"Set GamePriority = {settings['game_priority']}")
            except Exception as e:
                errors.append(f"GamePriority: {e}")
                logger.error(f"Failed to set GamePriority: {e}")

        # Fullscreen Optimizations (per-exe)
        if "fullscreen_optimizations" in settings:
            for exe_path, disabled in settings["fullscreen_optimizations"].items():
                try:
                    self._set_fullscreen_optimization(exe_path, disabled)
                    applied.append(f"FSO:{exe_path}")
                    logger.info(f"Set FullscreenOptimization for {exe_path} = {'disabled' if disabled else 'enabled'}")
                except Exception as e:
                    errors.append(f"FSO({exe_path}): {e}")
                    logger.error(f"Failed to set FSO for {exe_path}: {e}")

        # Win32PrioritySeparation (scheduler quantum)
        if "win32_priority_separation" in settings:
            try:
                self._set_win32_priority_separation(settings["win32_priority_separation"])
                applied.append("Win32PrioritySeparation")
                logger.info(f"Set Win32PrioritySeparation = 0x{settings['win32_priority_separation']:02X}")
            except Exception as e:
                errors.append(f"Win32PrioritySeparation: {e}")
                logger.error(f"Failed to set Win32PrioritySeparation: {e}")

        # Log summary
        if applied:
            logger.info(f"Registry: Applied {len(applied)} settings: {', '.join(applied)}")
        if errors:
            logger.warning(f"Registry: {len(errors)} errors: {'; '.join(errors)}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "applied": applied,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current registry gaming settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore registry gaming settings from backup."""
        success = True
        restore_map = {
            "system_responsiveness": self._set_system_responsiveness,
            "network_throttling": self._set_network_throttling,
            "game_priority": self._set_game_priority,
            "win32_priority_separation": self._set_win32_priority_separation,
            "fullscreen_optimizations": self._restore_fullscreen_optimizations,
        }
        for key, setter in restore_map.items():
            if key in data:
                try:
                    setter(data[key])
                except Exception as e:
                    logger.error(f"Failed to restore registry setting '{key}': {e}")
                    success = False
        return success

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested registry settings are active."""
        current = self.detect()
        results: dict[str, Any] = {"all_active": True, "settings": {}}

        if "system_responsiveness" in settings:
            current_value = current.get("system_responsiveness")
            target = settings["system_responsiveness"]
            is_active = current_value == target
            results["settings"]["system_responsiveness"] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "network_throttling" in settings:
            current_value = current.get("network_throttling")
            target = settings["network_throttling"]
            is_active = current_value == target
            results["settings"]["network_throttling"] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "game_priority" in settings:
            current_value = current.get("game_priority", {})
            target_settings = settings["game_priority"]
            for key, target in target_settings.items():
                setting_name = f"game_priority.{key}"
                current_setting = current_value.get(key)
                is_active = current_setting == target
                results["settings"][setting_name] = {
                    "target": target,
                    "current": current_setting,
                    "active": is_active,
                }
                if not is_active:
                    results["all_active"] = False

        if "win32_priority_separation" in settings:
            current_value = current.get("win32_priority_separation")
            target = settings["win32_priority_separation"]
            is_active = current_value == target
            results["settings"]["win32_priority_separation"] = {
                "target": target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "fullscreen_optimizations" in settings:
            for exe_path, disabled in settings["fullscreen_optimizations"].items():
                current_disabled = self._get_fullscreen_optimization(exe_path)
                is_active = current_disabled == disabled
                results["settings"][f"fullscreen_optimizations:{exe_path}"] = {
                    "target": disabled,
                    "current": current_disabled,
                    "active": is_active,
                }
                if not is_active:
                    results["all_active"] = False

        return results

    # Private helper methods

    def _get_system_responsiveness(self) -> int | None:
        """Get SystemResponsiveness value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MULTIMEDIA_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "SystemResponsiveness")[0]
                return value
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get SystemResponsiveness: {e}")
            return None

    def _set_system_responsiveness(self, value: int) -> None:
        """Set SystemResponsiveness value.

        Args:
            value: SystemResponsiveness value (0-100). 0 = games get max priority.

        Raises:
            ValidationError: If value is out of range.
            RegistryWriteError: If registry write fails.
        """
        validate_dword_value(value, "SystemResponsiveness", min_val=0, max_val=100)

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MULTIMEDIA_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                winreg.SetValueEx(key, "SystemResponsiveness", 0, winreg.REG_DWORD, value)
            finally:
                winreg.CloseKey(key)
        except PermissionError as e:
            raise RegistryWriteError(
                "Failed to set SystemResponsiveness",
                details=f"Permission denied. Run as administrator. ({e})"
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                "Failed to set SystemResponsiveness",
                details=str(e)
            ) from e

    def _get_network_throttling(self) -> int | None:
        """Get NetworkThrottlingIndex value."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MULTIMEDIA_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "NetworkThrottlingIndex")[0]
                return value
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get NetworkThrottlingIndex: {e}")
            return None

    def _set_network_throttling(self, value: int) -> None:
        """Set NetworkThrottlingIndex value.

        Args:
            value: Network throttling index. 0xFFFFFFFF disables throttling.

        Raises:
            ValidationError: If value is out of DWORD range.
            RegistryWriteError: If registry write fails.
        """
        validate_dword_value(value, "NetworkThrottlingIndex")

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MULTIMEDIA_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                winreg.SetValueEx(key, "NetworkThrottlingIndex", 0, winreg.REG_DWORD, value)
            finally:
                winreg.CloseKey(key)
        except PermissionError as e:
            raise RegistryWriteError(
                "Failed to set NetworkThrottlingIndex",
                details=f"Permission denied. Run as administrator. ({e})"
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                "Failed to set NetworkThrottlingIndex",
                details=str(e)
            ) from e

    def _get_game_priority(self) -> dict[str, Any]:
        """Get game task priority settings."""
        result = {}

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.GAMES_TASK_KEY,
                0,
                winreg.KEY_READ
            )
            with contextlib.suppress(FileNotFoundError):
                result["gpu_priority"] = winreg.QueryValueEx(key, "GPU Priority")[0]

            with contextlib.suppress(FileNotFoundError):
                result["priority"] = winreg.QueryValueEx(key, "Priority")[0]

            with contextlib.suppress(FileNotFoundError):
                result["scheduling_category"] = winreg.QueryValueEx(key, "Scheduling Category")[0]

            winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get game priority: {e}")

        return result

    def _set_game_priority(self, settings: dict[str, Any]) -> None:
        """Set game task priority settings.

        Args:
            settings: Dictionary with gpu_priority, priority, scheduling_category, sfio_priority.

        Raises:
            ValidationError: If values are invalid.
            RegistryWriteError: If registry write fails.
        """
        # Validate priority values before writing
        if "gpu_priority" in settings:
            validate_priority_value(settings["gpu_priority"], "GPU Priority", valid_values={0, 1, 2, 3, 4, 5, 6, 7, 8})
        if "priority" in settings:
            validate_priority_value(settings["priority"], "Priority", valid_values={1, 2, 3, 4, 5, 6, 7, 8})

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.GAMES_TASK_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                if "gpu_priority" in settings:
                    winreg.SetValueEx(key, "GPU Priority", 0, winreg.REG_DWORD, settings["gpu_priority"])
                if "priority" in settings:
                    winreg.SetValueEx(key, "Priority", 0, winreg.REG_DWORD, settings["priority"])
                if "scheduling_category" in settings:
                    winreg.SetValueEx(key, "Scheduling Category", 0, winreg.REG_SZ, settings["scheduling_category"])
                # NOTE: SFIO Priority is intentionally NOT written.
                # Microsoft documentation confirms it has no effect — the IO
                # priority of MMCSS-registered threads is not influenced by this
                # value. We still read it in detect()/backup() for completeness.
            finally:
                winreg.CloseKey(key)
        except PermissionError as e:
            raise RegistryWriteError(
                "Failed to set game priority",
                details=f"Permission denied. Run as administrator. ({e})"
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                "Failed to set game priority",
                details=str(e)
            ) from e

    def _set_fullscreen_optimization(self, exe_path: str, disabled: bool) -> None:
        """Set fullscreen optimization for an executable.

        Preserves any existing AppCompat layers (HIGHDPIAWARE, RUNASINVOKER,
        PROCESSORAFFINITYMASK, etc.) for the same exe - only the
        DISABLEDXMAXIMIZEDWINDOWEDMODE token is toggled based on *disabled*.
        If no other tokens remain after clearing, the value is deleted so
        the key stays tidy.

        Args:
            exe_path: Full path to the executable (e.g., "C:\\Games\\game.exe").
            disabled: True to disable fullscreen optimizations.

        Raises:
            ValidationError: If exe_path is invalid or contains dangerous characters.
            RegistryWriteError: If registry write fails.
        """
        # Validate the executable path to prevent registry injection
        validate_executable_path(exe_path)

        fso_token = "DISABLEDXMAXIMIZEDWINDOWEDMODE"
        # Windows error code for "file/value not found" from the registry API.
        _WIN_ERR_FILE_NOT_FOUND = 2

        try:
            # CreateKey tolerates the parent key not existing on fresh installs.
            # The returned handle already has KEY_ALL_ACCESS, which covers both
            # the Query/Enum and Set/Delete calls below.
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.APPCOMPAT_KEY)
        except OSError as e:
            raise RegistryWriteError(
                f"Failed to open AppCompatFlags\\Layers for {exe_path}",
                details=str(e),
            ) from e

        try:
            existing: str | None
            try:
                existing = str(winreg.QueryValueEx(key, exe_path)[0])
            except FileNotFoundError:
                existing = None
            except OSError as e:
                # Any other registry read failure is unsafe to treat as
                # "no existing tokens" — that would silently drop HIGHDPIAWARE,
                # PROCESSORAFFINITYMASK, etc. from an existing AppCompat entry.
                if getattr(e, "winerror", None) == _WIN_ERR_FILE_NOT_FOUND:
                    existing = None
                else:
                    raise RegistryWriteError(
                        f"Failed to read AppCompatFlags\\Layers[{exe_path}]",
                        details=str(e),
                    ) from e

            # Tokens are whitespace-separated; the leading "~" is the
            # AppCompat layer marker (kept if any tokens remain).
            source = existing or ""
            tokens = [t for t in source.split() if t and t != "~"]
            tokens = [t for t in tokens if t.upper() != fso_token]
            if disabled:
                tokens.append(fso_token)

            if tokens:
                new_value = "~ " + " ".join(tokens)
                winreg.SetValueEx(key, exe_path, 0, winreg.REG_SZ, new_value)
            elif existing is not None:
                # Only attempt deletion when an entry actually exists; skip
                # when there was nothing to clear so we do not race a peer
                # writer into an unnecessary DeleteValue call.
                with contextlib.suppress(FileNotFoundError):
                    winreg.DeleteValue(key, exe_path)
        except PermissionError as e:
            raise RegistryWriteError(
                f"Failed to set fullscreen optimization for {exe_path}",
                details=f"Permission denied. ({e})",
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                f"Failed to set fullscreen optimization for {exe_path}",
                details=str(e),
            ) from e
        finally:
            winreg.CloseKey(key)

    def _enumerate_fullscreen_optimizations(self) -> dict[str, bool]:
        """Enumerate HKCU AppCompatFlags\\Layers for all FSO-disabled entries.

        Returns a dict keyed by the registry value name (exe name or full path)
        with ``True`` when the entry contains the ``DISABLEDXMAXIMIZEDWINDOWEDMODE``
        token. Entries are captured verbatim so a full backup/restore round-trip
        can reverse any ABSO-written per-exe FSO flags without disturbing
        unrelated AppCompat layers the user or other tools may have set.

        Raises:
            OSError: If the Layers key exists but cannot be opened or enumerated.
                The caller is expected to omit this section from the backup
                snapshot so a partial read does not destroy live state on a
                later restore.
        """
        _WIN_ERR_FILE_NOT_FOUND = 2
        _WIN_ERR_NO_MORE_ITEMS = 259
        result: dict[str, bool] = {}

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.APPCOMPAT_KEY,
                0,
                winreg.KEY_READ,
            )
        except FileNotFoundError:
            return result
        except OSError as e:
            if getattr(e, "winerror", None) == _WIN_ERR_FILE_NOT_FOUND:
                return result
            # Any other failure (permission denied, transient OS error) is
            # unsafe to treat as "empty" because the result feeds backup +
            # restore. Bubble up so detect() can drop the section.
            raise

        try:
            index = 0
            while True:
                try:
                    name, value, _ = winreg.EnumValue(key, index)
                except OSError as e:
                    if getattr(e, "winerror", None) == _WIN_ERR_NO_MORE_ITEMS:
                        break
                    raise
                if "DISABLEDXMAXIMIZEDWINDOWEDMODE" in str(value).upper():
                    result[name] = True
                index += 1
        finally:
            winreg.CloseKey(key)
        return result

    def _restore_fullscreen_optimizations(self, backed_up: dict[str, bool]) -> None:
        """Reverse ABSO per-exe FSO writes from a backup snapshot.

        - Entries present in *backed_up*: re-assert their backed-up state
          (usually ``True``, meaning disabled at backup time) via
          ``_set_fullscreen_optimization`` so other AppCompat tokens stay
          intact.
        - Entries absent from *backed_up* but present in the current
          registry with the FSO token: clear the FSO token, which removes
          ABSO-applied shims without touching unrelated layers.

        Rollback semantics are exact: user-set FSO entries created AFTER
        the backup will be cleared on restore, matching the snapshot-at-a-
        point-in-time contract the rest of ``RegistrySettingsHandler`` uses.

        Raises:
            RegistryWriteError: If any per-exe write/clear fails. Aggregates
                across all failures so one flaky entry doesn't mask the
                others, and the enclosing ``restore()`` can mark the step as
                failed instead of reporting a false success.
        """
        if not isinstance(backed_up, dict):
            raise RegistryWriteError(
                "fullscreen_optimizations backup payload is corrupted",
                details=(
                    f"Expected dict, got {type(backed_up).__name__}. "
                    "Refusing to restore from an unreadable snapshot."
                ),
            )

        try:
            current = self._enumerate_fullscreen_optimizations()
        except OSError as e:
            # If we cannot read the current state, we cannot safely restore
            # without risking destruction of live tokens we don't know about.
            raise RegistryWriteError(
                "Cannot restore fullscreen_optimizations: current Layers state unreadable",
                details=str(e),
            ) from e

        failures: list[str] = []

        for exe, disabled in backed_up.items():
            if not isinstance(exe, str) or not exe.strip():
                continue
            desired = bool(disabled)
            if current.get(exe, False) != desired:
                try:
                    self._set_fullscreen_optimization(exe, desired)
                except Exception as e:
                    logger.error(
                        f"Failed to restore fullscreen_optimizations[{exe}]: {e}"
                    )
                    failures.append(f"{exe}: {e}")

        for exe in current:
            if exe in backed_up:
                continue
            try:
                self._set_fullscreen_optimization(exe, False)
            except Exception as e:
                logger.error(
                    f"Failed to clear fullscreen_optimizations[{exe}] during restore: {e}"
                )
                failures.append(f"{exe}: {e}")

        if failures:
            raise RegistryWriteError(
                "One or more fullscreen_optimizations entries could not be restored",
                details="; ".join(failures),
            )

    def _get_fullscreen_optimization(self, exe_path: str) -> bool | None:
        """Return True when fullscreen optimizations are disabled for an executable."""
        validate_executable_path(exe_path)

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.APPCOMPAT_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, exe_path)[0]
                return "DISABLEDXMAXIMIZEDWINDOWEDMODE" in str(value).upper()
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get fullscreen optimization for {exe_path}: {e}")
            return None

    def _get_win32_priority_separation(self) -> int | None:
        """Get Win32PrioritySeparation value (scheduler quantum settings)."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.PRIORITY_CONTROL_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "Win32PrioritySeparation")[0]
                return value
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Win32PrioritySeparation: {e}")
            return None

    def _set_win32_priority_separation(self, value: int) -> None:
        """Set Win32PrioritySeparation value.

        Args:
            value: Scheduler quantum value (typically 0x26 or 0x2A for gaming).

        Raises:
            ValidationError: If value is out of DWORD range.
            RegistryWriteError: If registry write fails.
        """
        # Valid values are 0x00-0x3F, but we allow full DWORD range for flexibility
        validate_dword_value(value, "Win32PrioritySeparation", min_val=0, max_val=0x3F)

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.PRIORITY_CONTROL_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                winreg.SetValueEx(key, "Win32PrioritySeparation", 0, winreg.REG_DWORD, value)
            finally:
                winreg.CloseKey(key)
        except PermissionError as e:
            raise RegistryWriteError(
                "Failed to set Win32PrioritySeparation",
                details=f"Permission denied. Run as administrator. ({e})"
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                "Failed to set Win32PrioritySeparation",
                details=str(e)
            ) from e
