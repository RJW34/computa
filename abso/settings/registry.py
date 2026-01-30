"""Registry settings handler."""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.exceptions import RegistryWriteError
from abso.core.models import Issue
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
    #   Bits 3-2 (BB): Quantum type (0/1=default, 2=variable, 3=fixed)
    #   Bits 1-0 (CC): Foreground boost (0=none, 1=minimum, 2=maximum)
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
        return {
            "system_responsiveness": self._get_system_responsiveness(),
            "network_throttling": self._get_network_throttling(),
            "game_priority": self._get_game_priority(),
            "win32_priority_separation": self._get_win32_priority_separation(),
        }

    def audit(self) -> list[Issue]:
        """Audit registry settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # System Responsiveness (10 = games get near-max CPU priority while keeping audio stable)
        responsiveness = current.get("system_responsiveness")
        if responsiveness is not None and responsiveness != 10:
            issues.append(Issue(
                title="System Responsiveness not optimized for gaming",
                severity="warning",
                current_value=str(responsiveness),
                optimal_value="10",
                explanation=(
                    "Controls CPU % reserved for background tasks. Setting to 10 gives games near-maximum "
                    "priority while reserving minimal CPU for audio/USB, preventing crackling and dropouts."
                ),
                category="registry",
            ))

        # Network Throttling
        throttling = current.get("network_throttling")
        if throttling is not None and throttling != 0xFFFFFFFF:
            issues.append(Issue(
                title="Network throttling is enabled",
                severity="warning",
                current_value=f"0x{throttling:08X}" if throttling else "Unknown",
                optimal_value="0xFFFFFFFF (disabled)",
                explanation=(
                    "Controls multimedia streaming throttling. Disabling removes any network-related throttling. "
                    "Primary benefit is for streaming/recording while gaming."
                ),
                category="registry",
            ))

        # Game priority settings
        game_priority = current.get("game_priority", {})
        if game_priority.get("priority") != 6:
            issues.append(Issue(
                title="Game process priority not optimized",
                severity="info",
                current_value=str(game_priority.get("priority", "Unknown")),
                optimal_value="6",
                explanation="Higher priority value gives games more CPU scheduling preference.",
                category="registry",
            ))

        # Win32PrioritySeparation (scheduler quantum)
        priority_sep = current.get("win32_priority_separation")
        if priority_sep is not None and priority_sep != self.WIN32_PRIORITY_GAMING:
            issues.append(Issue(
                title="Windows scheduler not optimized for gaming",
                severity="info",
                current_value=f"0x{priority_sep:02X}" if priority_sep else "Unknown",
                optimal_value=f"0x{self.WIN32_PRIORITY_GAMING:02X}",
                explanation=(
                    "Win32PrioritySeparation controls CPU time slice allocation. "
                    "0x28 uses short variable quantum with max foreground boost, "
                    "giving the active game more responsive CPU scheduling."
                ),
                category="registry",
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
        }
        for key, setter in restore_map.items():
            if key in data:
                try:
                    setter(data[key])
                except Exception as e:
                    logger.error(f"Failed to restore registry setting '{key}': {e}")
                    success = False
        return success

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
                if "sfio_priority" in settings:
                    winreg.SetValueEx(key, "SFIO Priority", 0, winreg.REG_SZ, settings["sfio_priority"])
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

        Args:
            exe_path: Full path to the executable (e.g., "C:\\Games\\game.exe").
            disabled: True to disable fullscreen optimizations.

        Raises:
            ValidationError: If exe_path is invalid or contains dangerous characters.
            RegistryWriteError: If registry write fails.
        """
        # Validate the executable path to prevent registry injection
        validate_executable_path(exe_path)

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.APPCOMPAT_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                if disabled:
                    winreg.SetValueEx(
                        key,
                        exe_path,
                        0,
                        winreg.REG_SZ,
                        "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"
                    )
                else:
                    with contextlib.suppress(FileNotFoundError):
                        winreg.DeleteValue(key, exe_path)
            finally:
                winreg.CloseKey(key)
        except PermissionError as e:
            raise RegistryWriteError(
                f"Failed to set fullscreen optimization for {exe_path}",
                details=f"Permission denied. ({e})"
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                f"Failed to set fullscreen optimization for {exe_path}",
                details=str(e)
            ) from e

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
            value: Scheduler quantum value (typically 0x26 or 0x28 for gaming).

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
