"""Nvidia Profile Inspector (NPI) integration.

WARNING: NPI IMPORT IS PERMANENTLY DISABLED.

NPI's -silent import command REPLACES the entire NVIDIA profile database,
wiping ALL existing per-game profiles. This caused catastrophic data loss
for users who had carefully configured their NVIDIA settings.

Until proper NVAPI integration is implemented that can safely merge profiles,
all NPI import functionality is disabled. The import_profile method will
raise an error if called.
"""

from __future__ import annotations

import logging
import os
import subprocess
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)

# SAFETY FLAG: Set to True to completely disable NPI imports
NPI_IMPORTS_DISABLED = True


class NPIManager:
    """Manages Nvidia Profile Inspector operations.

    WARNING: IMPORT FUNCTIONALITY IS DISABLED.

    NPI import wipes all existing profiles. Do not re-enable without
    implementing proper NVAPI-based profile merging.
    """

    def __init__(self, npi_path: Path | str | None = None) -> None:
        """Initialize NPI manager.

        Args:
            npi_path: Path to nvidiaProfileInspector.exe.
        """
        self.npi_path: Path | None = Path(npi_path) if npi_path else None
        if not self.npi_path:
            self._find_npi()

    def is_available(self) -> bool:
        """Check if NPI is available."""
        if self.npi_path and self.npi_path.exists():
            return True
        self._find_npi()
        return self.npi_path is not None and self.npi_path.exists()

    def get_path(self) -> Path | None:
        """Get the NPI executable path."""
        return self.npi_path

    def import_profile(self, profile_path: Path) -> None:
        """DISABLED: Import a Nvidia profile file using NPI.

        WARNING: THIS METHOD IS PERMANENTLY DISABLED.

        NPI's -silent import REPLACES the entire NVIDIA profile database,
        wiping all existing per-game profiles. This caused catastrophic
        data loss and is now blocked.

        Args:
            profile_path: Path to the .nip file to import.

        Raises:
            RuntimeError: Always - NPI imports are disabled.
        """
        if NPI_IMPORTS_DISABLED:
            logger.error(
                "NPI import is PERMANENTLY DISABLED. "
                "NPI wipes all existing profiles when importing. "
                "Use NVIDIA Control Panel to configure settings manually."
            )
            raise RuntimeError(
                "NPI import disabled - it wipes all existing NVIDIA profiles. "
                "Configure NVIDIA settings manually in NVCP."
            )

        if not self.npi_path:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Importing Nvidia profile: {profile_path}")

        # Ensure absolute paths
        npi_abs = self.npi_path.resolve()
        profile_abs = Path(profile_path).resolve()

        # NPI ignores all hiding flags - use Windows API to hide window after launch
        # This script: starts NPI, finds its window, hides it, waits for exit
        ps_script = f'''
Add-Type @"
using System;
using System.Runtime.InteropServices;
public class Win32 {{
    [DllImport("user32.dll")]
    public static extern bool ShowWindow(IntPtr hWnd, int nCmdShow);
    public const int SW_HIDE = 0;
}}
"@

$p = Start-Process -FilePath "{npi_abs}" -ArgumentList '-silent', '"{profile_abs}"' -WorkingDirectory "{npi_abs.parent}" -PassThru
Start-Sleep -Milliseconds 100

# Hide the window as soon as it appears
for ($i = 0; $i -lt 20; $i++) {{
    if ($p.MainWindowHandle -ne [IntPtr]::Zero) {{
        [Win32]::ShowWindow($p.MainWindowHandle, 0) | Out-Null
        break
    }}
    Start-Sleep -Milliseconds 50
}}

$p.WaitForExit(25000)
exit $p.ExitCode
'''
        startupinfo = subprocess.STARTUPINFO()
        startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
        startupinfo.wShowWindow = 0

        result = subprocess.run(
            ["powershell", "-NoProfile", "-NonInteractive", "-Command", ps_script],
            capture_output=True,
            text=True,
            timeout=30,
            startupinfo=startupinfo,
            creationflags=subprocess.CREATE_NO_WINDOW,
        )

        if result.returncode != 0:
            raise RuntimeError(f"NPI import failed: {result.stderr or result.stdout}")

    def export_profile(self, output_path: Path) -> None:
        """Export current Nvidia profile using NPI.

        Note: NPI does not support headless export - the -export flag opens the GUI.
        This method attempts export with a short timeout and kills the process if
        it spawns a GUI window.

        Args:
            output_path: Path to save the exported .nip file.

        Raises:
            RuntimeError: If NPI is not configured or export fails.
        """
        if not self.npi_path:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Exporting Nvidia profile to: {output_path}")

        process = None
        try:
            # Hide the window using Windows-specific flags
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

            # Use Popen for better process control
            process = subprocess.Popen(
                [str(self.npi_path), "-export", str(output_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
            )

            # Short timeout - NPI export opens GUI, so it will hang
            # If it completes quickly, great. If not, assume GUI spawned.
            try:
                stdout, stderr = process.communicate(timeout=5)
            except subprocess.TimeoutExpired:
                # NPI opened GUI window - kill it
                logger.warning("NPI export spawned GUI window, terminating process")
                self._kill_npi_process(process)
                raise RuntimeError(
                    "NPI does not support headless export (GUI was spawned). "
                    "Use nvidia-smi or manual backup. Nvidia profile backup skipped."
                ) from None

            # NPI may return 0 even if it opened GUI instead of exporting
            if not output_path.exists():
                raise RuntimeError(
                    "NPI export did not create file. Export may require GUI interaction. "
                    "Run NPI manually and use File > Export to create a backup."
                )

            if process.returncode != 0:
                raise RuntimeError(f"NPI export failed: {stderr or stdout}")

        except subprocess.TimeoutExpired:
            if process:
                self._kill_npi_process(process)
            raise
        except Exception:
            if process and process.poll() is None:
                self._kill_npi_process(process)
            raise

    def _kill_npi_process(self, process: subprocess.Popen) -> None:
        """Kill an NPI process and any spawned GUI windows."""
        try:
            process.kill()
            process.wait(timeout=2)
        except Exception:
            pass

        # Also kill any lingering NPI processes by name
        try:
            subprocess.run(
                ["taskkill", "/F", "/IM", "nvidiaProfileInspector.exe"],
                capture_output=True,
                timeout=5,
            )
        except Exception as e:
            logger.debug(f"Failed to taskkill NPI: {e}")

    def read_current_settings(self) -> dict[str, Any]:
        """Read current Nvidia 3D settings.

        Note: NPI cannot export headlessly (opens GUI), so this method
        returns empty dict. Use nvidia-smi for reading current settings instead.

        Returns:
            Empty dictionary (NPI export not supported headlessly).
        """
        # NPI export opens GUI, so skip entirely to avoid window flash
        logger.debug("Skipping NPI read_current_settings - export opens GUI")
        return {}

    def launch_for_app_binding(
        self,
        profile_name: str,
        app_executable: str,
        auto_close: bool = False,
    ) -> bool:
        """Launch NPI so user can easily add an app to a profile.

        Opens NPI's GUI. The user needs to:
        1. Select the profile from the dropdown
        2. Add the application executable
        3. Click Apply

        Args:
            profile_name: The profile name to bind to (shown to user).
            app_executable: The executable to add (shown to user).
            auto_close: If True, close NPI after launch (not useful here).

        Returns:
            True if NPI was launched successfully.
        """
        if not self.is_available() or self.npi_path is None:
            logger.warning("NPI not available for app binding")
            return False

        try:
            # Launch NPI (it will open to the GUI). is_available() above
            # already proved npi_path is set + the file exists; the narrow
            # None-check here is what keeps mypy honest and protects against
            # races where _find_npi() succeeded but the file was deleted
            # before we got here.
            logger.info(f"Launching NPI for app binding: {app_executable} -> {profile_name}")
            subprocess.Popen(
                [str(self.npi_path.resolve())],
                creationflags=subprocess.DETACHED_PROCESS,
            )
            return True
        except Exception as e:
            logger.error(f"Failed to launch NPI: {e}")
            return False

    def _find_npi(self) -> None:
        """Try to find Nvidia Profile Inspector in common locations."""
        common_paths = [
            # Current directory
            Path("nvidiaProfileInspector.exe"),
            Path("tools/nvidiaProfileInspector.exe"),
            Path("tools/npi/nvidiaProfileInspector.exe"),
            # User's home directory
            Path.home() / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
            Path.home() / "Tools" / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
            # Program Files
            Path(os.environ.get("PROGRAMFILES", "C:\\Program Files")) / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
            Path(os.environ.get("PROGRAMFILES(X86)", "C:\\Program Files (x86)")) / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
            # Local AppData
            Path(os.environ.get("LOCALAPPDATA", "")) / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
        ]

        for path in common_paths:
            try:
                if path.exists():
                    self.npi_path = path
                    logger.debug(f"Found NPI at: {path}")
                    return
            except (OSError, PermissionError):
                continue
