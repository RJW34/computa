"""Per-process priority settings handler."""

from __future__ import annotations

import contextlib
import logging
import subprocess
import winreg
from typing import Any

from abso.core.exceptions import RegistryWriteError
from abso.core.models import Issue
from abso.settings.base import SettingsHandler
from abso.utils.validation import (
    validate_executable_name,
    validate_priority_value,
)

logger = logging.getLogger(__name__)


class ProcessPriorityHandler(SettingsHandler):
    """Handles per-process GPU, CPU, and I/O priority settings.

    Uses Image File Execution Options (IFEO) to set persistent priority
    for specific executables. These settings apply every time the process starts.

    Registry path:
    HKLM\\SOFTWARE\\Microsoft\\Windows NT\\CurrentVersion\\Image File Execution Options\\{exe}\\PerfOptions

    Available settings:
    - CpuPriorityClass: 1=Idle, 2=Normal, 3=High, 4=Realtime (ABSO uses 3 at most)
    - IoPriority: 0=Very Low, 1=Low, 2=Normal, 3=High
    - PagePriority: 0-5 (memory page priority)

    Mark this handler as critical-verify because IFEO mismatches mean the
    game launched with the wrong priority — a direct latency regression.

    Tradeoffs to be aware of:

    - "Realtime" (4) can starve the OS, audio, and anti-cheat; ABSO never writes it.
    - Even "High" (3) is not a universal win. It can starve audio threads, OBS
      capture, launcher overlays, and some anti-cheat helper processes. Certain
      anti-cheat engines also treat IFEO changes as suspicious. Think of this
      as an experimental tradeoff per-game, not a guaranteed FPS boost.
    - GPU scheduling priority is handled via MMCSS / ``RegistrySettingsHandler``,
      not IFEO. The ``GpuPriority`` value here only affects the PerfOptions
      hint used by the app, not the global scheduler.

    ABSO gaming profiles apply at most CPU priority 3 (High) and IO priority 3
    (High). Users who hit stability, audio, or capture problems can drop to 2
    (Normal) via profile overrides without losing the rest of the profile.
    """

    is_critical_verify = True

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
        result: dict[str, Any] = {
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

            io_priority = exe_settings.get("io_priority")
            if io_priority is None or io_priority < self.IO_PRIORITY_NORMAL:
                issues.append(Issue(
                    title=f"I/O priority not optimized for {exe}",
                    severity="info",
                    current_value=str(io_priority) if io_priority is not None else "Not set",
                    optimal_value=str(self.IO_PRIORITY_NORMAL),
                    explanation=(
                        f"Normal I/O priority helps {exe} avoid background storage contention "
                        "without over-claiming unsupported IFEO GPU tweaks."
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

        This method:
        1. Sets IFEO registry settings for future launches
        2. Also sets priority on any currently running matching processes
           (since IFEO may be overridden by Steam/UE5 launchers)
        """
        errors: list[str] = []
        cpu_priority = settings.get("cpu_priority", self.CPU_PRIORITY_HIGH)

        if "processes" in settings:
            # Apply per-process settings
            for exe, exe_settings in settings["processes"].items():
                try:
                    self._set_process_settings(exe, exe_settings)
                except PermissionError as e:
                    errors.append(f"{exe}: Permission denied (requires admin): {e}")
                except Exception as e:
                    errors.append(f"{exe}: {e}")
        else:
            # Apply same settings to all managed executables
            for exe in self.executables:
                try:
                    self._set_process_settings(exe, settings)
                except PermissionError as e:
                    errors.append(f"{exe}: Permission denied (requires admin): {e}")
                except Exception as e:
                    errors.append(f"{exe}: {e}")

        # Also set priority on running processes (IFEO may not work with Steam/UE5)
        try:
            self._set_running_processes_priority(cpu_priority)
        except Exception as e:
            errors.append(f"Running process priority: {e}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,  # Takes effect on next process start
        }

    def _discover_configured_executables(self) -> list[str]:
        """Scan IFEO registry for executables with PerfOptions subkey.

        Returns:
            List of executable names that have priority settings configured.
        """
        discovered: list[str] = []
        try:
            ifeo_key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.IFEO_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                i = 0
                while True:
                    try:
                        subkey_name = winreg.EnumKey(ifeo_key, i)
                        i += 1
                        # Check if this subkey has a PerfOptions child
                        try:
                            perf_key = winreg.OpenKey(
                                ifeo_key,
                                f"{subkey_name}\\PerfOptions",
                                0,
                                winreg.KEY_READ,
                            )
                            winreg.CloseKey(perf_key)
                            discovered.append(subkey_name)
                        except FileNotFoundError:
                            pass
                    except OSError:
                        break
            finally:
                winreg.CloseKey(ifeo_key)
        except Exception as e:
            logger.debug(f"Failed to discover IFEO executables: {e}")

        return discovered

    def backup(self) -> dict[str, Any]:
        """Backup current per-process priority settings."""
        if not self.executables:
            self.executables = self._discover_configured_executables()
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore per-process priority settings from backup."""
        try:
            processes = data.get("processes", {})
            for exe, exe_settings in processes.items():
                if any(value is not None for value in exe_settings.values()):
                    self._set_process_settings(exe, exe_settings)
                else:
                    # Remove settings if they were not set before
                    self._remove_process_settings(exe)
            return True
        except Exception as e:
            logger.error(f"Failed to restore process priority settings: {e}")
            return False

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested IFEO process priority settings are active."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}

        if "processes" in settings:
            targets = settings["processes"]
        else:
            targets = {exe: settings for exe in self.executables}

        for exe, exe_settings in targets.items():
            current = self._get_process_settings(exe)
            for key in ("cpu_priority", "io_priority", "page_priority"):
                if key not in exe_settings:
                    continue
                target = exe_settings[key]
                current_value = current.get(key)
                is_active = current_value == target
                results["settings"][f"{exe}:{key}"] = {
                    "target": target,
                    "current": current_value,
                    "active": is_active,
                }
                if not is_active:
                    results["all_active"] = False

        return results

    def add_executable(self, exe_name: str) -> None:
        """Add an executable to the managed list.

        Args:
            exe_name: Executable name (e.g., "game.exe").

        Raises:
            ValidationError: If the executable name is invalid.
        """
        validate_executable_name(exe_name)
        if exe_name not in self.executables:
            self.executables.append(exe_name)

    def set_gaming_priorities(self, exe_name: str) -> dict[str, Any]:
        """Set optimal gaming priorities for an executable.

        This is a convenience method that applies recommended settings.

        Args:
            exe_name: Executable name (e.g., "game.exe").

        Returns:
            Result dictionary with success status.

        Raises:
            ValidationError: If the executable name is invalid.
        """
        validate_executable_name(exe_name)
        settings = {
            "cpu_priority": self.CPU_PRIORITY_HIGH,
            "io_priority": self.IO_PRIORITY_HIGH,
        }
        return self._set_process_settings(exe_name, settings)

    # Private helper methods

    def _get_process_settings(self, exe_name: str) -> dict[str, Any]:
        """Get priority settings for a specific executable.

        Args:
            exe_name: Executable name (e.g., "game.exe").

        Returns:
            Dictionary with priority settings.

        Raises:
            ValidationError: If the executable name is invalid.
        """
        # Validate to prevent path traversal in registry queries
        validate_executable_name(exe_name)

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
                with contextlib.suppress(FileNotFoundError):
                    result["gpu_priority"] = winreg.QueryValueEx(key, "GpuPriority")[0]

                with contextlib.suppress(FileNotFoundError):
                    result["cpu_priority"] = winreg.QueryValueEx(key, "CpuPriorityClass")[0]

                with contextlib.suppress(FileNotFoundError):
                    result["io_priority"] = winreg.QueryValueEx(key, "IoPriority")[0]

                with contextlib.suppress(FileNotFoundError):
                    result["page_priority"] = winreg.QueryValueEx(key, "PagePriority")[0]

            finally:
                winreg.CloseKey(key)

        except FileNotFoundError:
            # PerfOptions key doesn't exist - that's fine
            pass
        except Exception as e:
            logger.debug(f"Failed to get process settings for {exe_name}: {e}")

        return result

    def _set_process_settings(self, exe_name: str, settings: dict[str, Any]) -> dict[str, Any]:
        """Set priority settings for a specific executable.

        Args:
            exe_name: Executable name (e.g., "game.exe").
            settings: Dictionary with priority settings.

        Returns:
            Result dictionary with success status.

        Raises:
            ValidationError: If exe_name or settings values are invalid.
            RegistryWriteError: If registry write fails.
        """
        # Validate executable name to prevent registry injection
        validate_executable_name(exe_name)

        # Validate priority values
        if "gpu_priority" in settings and settings["gpu_priority"] is not None:
            validate_priority_value(
                settings["gpu_priority"],
                "GpuPriority",
                valid_values={0, 1, 2, 3, 4, 5, 6, 7, 8}
            )
        if "cpu_priority" in settings and settings["cpu_priority"] is not None:
            validate_priority_value(
                settings["cpu_priority"],
                "CpuPriorityClass",
                valid_values={self.CPU_PRIORITY_IDLE, self.CPU_PRIORITY_NORMAL,
                              self.CPU_PRIORITY_HIGH, self.CPU_PRIORITY_REALTIME}
            )
        if "io_priority" in settings and settings["io_priority"] is not None:
            validate_priority_value(
                settings["io_priority"],
                "IoPriority",
                valid_values={self.IO_PRIORITY_VERY_LOW, self.IO_PRIORITY_LOW,
                              self.IO_PRIORITY_NORMAL, self.IO_PRIORITY_HIGH}
            )
        if "page_priority" in settings and settings["page_priority"] is not None:
            validate_priority_value(
                settings["page_priority"],
                "PagePriority",
                valid_values={0, 1, 2, 3, 4, 5}
            )

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
                    # NOTE: GpuPriority is NOT a documented IFEO PerfOptions value.
                    # Microsoft only documents: CpuPriorityClass, IoPriority,
                    # PagePriority, WorkingSetLimitInKB. GPU priority for games
                    # is set via MMCSS Tasks\Games (RegistrySettingsHandler), not IFEO.
                    # We skip GpuPriority here to avoid writing undocumented values.

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

        except PermissionError as e:
            raise RegistryWriteError(
                f"Failed to set process settings for {exe_name}",
                details=f"Permission denied. Run as administrator. ({e})"
            ) from e
        except OSError as e:
            raise RegistryWriteError(
                f"Failed to set process settings for {exe_name}",
                details=str(e)
            ) from e

        return {
            "success": True,
            "error": None,
        }

    def _remove_process_settings(self, exe_name: str) -> bool:
        """Remove priority settings for a specific executable.

        Args:
            exe_name: Executable name (e.g., "game.exe").

        Returns:
            True if settings were removed or didn't exist.

        Raises:
            ValidationError: If the executable name is invalid.
        """
        # Validate to prevent path traversal in registry operations
        validate_executable_name(exe_name)

        try:
            perf_options_path = f"{self.IFEO_KEY}\\{exe_name}\\PerfOptions"
            winreg.DeleteKey(winreg.HKEY_LOCAL_MACHINE, perf_options_path)
            return True
        except FileNotFoundError:
            return True  # Already doesn't exist
        except Exception as e:
            logger.error(f"Failed to remove process settings for {exe_name}: {e}")
            return False

    def _set_running_processes_priority(self, cpu_priority: int) -> None:
        """Set priority on currently running processes matching managed executables.

        This is needed because IFEO registry settings may be overridden by
        Steam, UE5, or other launchers that set their own process priority.

        Args:
            cpu_priority: CPU priority class (1=Idle, 2=Normal, 3=High, 4=Realtime)
        """
        # Map our priority constants to PowerShell priority class names
        priority_map = {
            self.CPU_PRIORITY_IDLE: "Idle",
            self.CPU_PRIORITY_NORMAL: "Normal",
            self.CPU_PRIORITY_HIGH: "High",
            self.CPU_PRIORITY_REALTIME: "RealTime",
        }
        priority_name = priority_map.get(cpu_priority, "High")

        for exe in self.executables:
            # Remove .exe extension for process name matching
            process_name = exe.replace(".exe", "").replace(".EXE", "")
            # Escape single quotes to prevent PowerShell injection
            process_name = process_name.replace("'", "''")

            # Use PowerShell to find and set priority on matching processes
            # This handles cases where IFEO doesn't work (Steam/UE5 override)
            ps_script = f"""
                $procs = Get-Process -Name '{process_name}' -ErrorAction SilentlyContinue
                foreach ($proc in $procs) {{
                    try {{
                        $proc.PriorityClass = '{priority_name}'
                    }} catch {{
                        # Process may have exited or access denied
                    }}
                }}
            """
            try:
                subprocess.run(
                    ["powershell", "-NoProfile", "-Command", ps_script],
                    capture_output=True,
                    timeout=5,
                )
                logger.debug(f"Set {priority_name} priority on running {exe} processes")
            except subprocess.TimeoutExpired:
                logger.warning(f"Timeout setting priority for {exe}")
            except Exception as e:
                logger.debug(f"Could not set priority for {exe}: {e}")
