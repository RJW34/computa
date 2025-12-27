"""Per-process priority settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from gametune.settings.base import SettingsHandler
from gametune.core.models import Issue

logger = logging.getLogger(__name__)


class ProcessPriorityHandler(SettingsHandler):
    """Handles per-process GPU, CPU, and I/O priority settings.

    Uses Image File Execution Options (IFEO) to set persistent priority
    for specific executables. These settings apply every time the process starts.

    Registry path:
    HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe}\\PerfOptions

    Available settings:
    - CpuPriorityClass: 1=Idle, 2=Normal, 3=High, 4=Realtime (use 3 for games)
    - IoPriority: 0=Very Low, 1=Low, 2=Normal, 3=High
    - GpuPriority: 0-8 (8=highest priority for GPU scheduling)
    - PagePriority: 0-5 (memory page priority)

    Note: Realtime CPU priority (4) can cause system instability and is not recommended.
    """

    IFEO_KEY = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Image File Execution Options"

    # Priority class constants
    CPU_PRIORITY_IDLE = 1
    CPU_PRIORITY_NORMAL = 2
    CPU_PRIORITY_HIGH = 3
    CPU_PRIORITY_REALTIME = 4  # Not recommended

    IO_PRIORITY_VERY_LOW = 0
    IO_PRIORITY_LOW = 1
    IO_PRIORITY_NORMAL = 2
    IO_PRIORITY_HIGH = 3

    GPU_PRIORITY_MAX = 8

    def __init__(self, executables: list[str] | None = None):
        """Initialize handler with list of executables to manage.

        Args:
            executables: List of executable names (e.g., ["game.exe", "Dolphin.exe"])
        """
        self.executables = executables or []

    def detect(self) -> dict[str, Any]:
        """Detect current per-process priority settings."""
        result = {
            "processes": {},
            "configured_count": 0,
        }

        for exe in self.executables:
            exe_settings = self._get_process_settings(exe)
            if exe_settings:
                result["processes"][exe] = exe_settings
                if any(v is not None for v in exe_settings.values()):
                    result["configured_count"] += 1

        return result

    def audit(self) -> list[Issue]:
        """Audit per-process priority settings."""
        issues: list[Issue] = []
        current = self.detect()

        for exe in self.executables:
            exe_settings = current["processes"].get(exe, {})

            # Check if GPU priority is not set to maximum
            gpu_priority = exe_settings.get("gpu_priority")
            if gpu_priority is None or gpu_priority < self.GPU_PRIORITY_MAX:
                issues.append(Issue(
                    title=f"GPU priority not optimized for {exe}",
                    severity="info",
                    current_value=str(gpu_priority) if gpu_priority is not None else "Not set",
                    optimal_value=str(self.GPU_PRIORITY_MAX),
                    explanation=(
                        f"Setting GPU priority to {self.GPU_PRIORITY_MAX} ensures {exe} gets "
                        "maximum GPU scheduling priority over background processes."
                    ),
                    category="process_priority",
                ))

            # Check if CPU priority is not high
            cpu_priority = exe_settings.get("cpu_priority")
            if cpu_priority is None or cpu_priority < self.CPU_PRIORITY_HIGH:
                issues.append(Issue(
                    title=f"CPU priority not optimized for {exe}",
                    severity="info",
                    current_value=str(cpu_priority) if cpu_priority is not None else "Not set",
                    optimal_value=str(self.CPU_PRIORITY_HIGH),
                    explanation=(
                        f"High CPU priority ensures {exe} gets CPU time before normal "
                        "priority processes. Avoids stuttering from background tasks."
                    ),
                    category="process_priority",
                ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply per-process priority settings.

        Settings format:
        {
            "processes": {
                "game.exe": {
                    "gpu_priority": 8,
                    "cpu_priority": 3,
                    "io_priority": 3,
                }
            }
        }

        Or shorthand for all managed executables:
        {
            "gpu_priority": 8,
            "cpu_priority": 3,
            "io_priority": 3,
        }
        """
        errors: list[str] = []

        try:
            if "processes" in settings:
                # Apply per-process settings
                for exe, exe_settings in settings["processes"].items():
                    self._set_process_settings(exe, exe_settings)
            else:
                # Apply same settings to all managed executables
                for exe in self.executables:
                    self._set_process_settings(exe, settings)

        except PermissionError as e:
            errors.append(f"Permission denied (requires admin): {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,  # Takes effect on next process start
        }

    def backup(self) -> dict[str, Any]:
        """Backup current per-process priority settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore per-process priority settings from backup."""
        try:
            processes = data.get("processes", {})
            for exe, exe_settings in processes.items():
                if exe_settings:
                    self._set_process_settings(exe, exe_settings)
                else:
                    # Remove settings if they were not set before
                    self._remove_process_settings(exe)
            return True
        except Exception as e:
            logger.error(f"Failed to restore process priority settings: {e}")
            return False

    def add_executable(self, exe_name: str) -> None:
        """Add an executable to the managed list."""
        if exe_name not in self.executables:
            self.executables.append(exe_name)

    def set_gaming_priorities(self, exe_name: str) -> dict[str, Any]:
        """Set optimal gaming priorities for an executable.

        This is a convenience method that applies recommended settings.
        """
        settings = {
            "gpu_priority": self.GPU_PRIORITY_MAX,
            "cpu_priority": self.CPU_PRIORITY_HIGH,
            "io_priority": self.IO_PRIORITY_HIGH,
        }
        return self._set_process_settings(exe_name, settings)

    # Private helper methods

    def _get_process_settings(self, exe_name: str) -> dict[str, Any]:
        """Get priority settings for a specific executable."""
        result = {
            "gpu_priority": None,
            "cpu_priority": None,
            "io_priority": None,
            "page_priority": None,
        }

        try:
            perf_options_path = f"{self.IFEO_KEY}\\{exe_name}\\PerfOptions"
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                perf_options_path,
                0,
                winreg.KEY_READ
            )
            try:
                try:
                    result["gpu_priority"] = winreg.QueryValueEx(key, "GpuPriority")[0]
                except FileNotFoundError:
                    pass

                try:
                    result["cpu_priority"] = winreg.QueryValueEx(key, "CpuPriorityClass")[0]
                except FileNotFoundError:
                    pass

                try:
                    result["io_priority"] = winreg.QueryValueEx(key, "IoPriority")[0]
                except FileNotFoundError:
                    pass

                try:
                    result["page_priority"] = winreg.QueryValueEx(key, "PagePriority")[0]
                except FileNotFoundError:
                    pass

            finally:
                winreg.CloseKey(key)

        except FileNotFoundError:
            # PerfOptions key doesn't exist - that's fine
            pass
        except Exception as e:
            logger.debug(f"Failed to get process settings for {exe_name}: {e}")

        return result

    def _set_process_settings(self, exe_name: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Set priority settings for a specific executable."""
        errors = []

        try:
            # Create the executable key if it doesn't exist
            exe_key_path = f"{self.IFEO_KEY}\\{exe_name}"
            try:
                exe_key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    exe_key_path,
                    0,
                    winreg.KEY_ALL_ACCESS
                )
            except FileNotFoundError:
                exe_key = winreg.CreateKey(winreg.HKEY_LOCAL_MACHINE, exe_key_path)

            try:
                # Create PerfOptions subkey
                try:
                    perf_key = winreg.OpenKey(exe_key, "PerfOptions", 0, winreg.KEY_ALL_ACCESS)
                except FileNotFoundError:
                    perf_key = winreg.CreateKey(exe_key, "PerfOptions")

                try:
                    if "gpu_priority" in settings and settings["gpu_priority"] is not None:
                        winreg.SetValueEx(perf_key, "GpuPriority", 0, winreg.REG_DWORD, settings["gpu_priority"])

                    if "cpu_priority" in settings and settings["cpu_priority"] is not None:
                        winreg.SetValueEx(perf_key, "CpuPriorityClass", 0, winreg.REG_DWORD, settings["cpu_priority"])

                    if "io_priority" in settings and settings["io_priority"] is not None:
                        winreg.SetValueEx(perf_key, "IoPriority", 0, winreg.REG_DWORD, settings["io_priority"])

                    if "page_priority" in settings and settings["page_priority"] is not None:
                        winreg.SetValueEx(perf_key, "PagePriority", 0, winreg.REG_DWORD, settings["page_priority"])

                finally:
                    winreg.CloseKey(perf_key)
            finally:
                winreg.CloseKey(exe_key)

        except PermissionError:
            errors.append(f"Permission denied for {exe_name}")
            raise
        except Exception as e:
            errors.append(str(e))
            logger.error(f"Failed to set process settings for {exe_name}: {e}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
        }

    def _remove_process_settings(self, exe_name: str) -> bool:
        """Remove priority settings for a specific executable."""
        try:
            perf_options_path = f"{self.IFEO_KEY}\\{exe_name}\\PerfOptions"
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, perf_options_path)
            return True
        except FileNotFoundError:
            return True  # Already doesn't exist
        except Exception as e:
            logger.error(f"Failed to remove process settings for {exe_name}: {e}")
            return False
