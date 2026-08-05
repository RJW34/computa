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

import contextlib
import logging
import os
import subprocess
import sys
from pathlib import Path
from typing import Any

logger = logging.getLogger(__name__)


def _app_roots() -> list[Path]:
    """Return directories that may hold a bundled ``tools/npi`` alongside ABSO.

    NPI discovery used to be purely CWD-relative. The tray launches the backend
    with its working directory set to the install root, which has no ``tools``
    tree, so every tray-driven apply silently skipped NVIDIA settings while a
    developer running the same command from the repo saw it work. Anchor the
    search to the running program instead of the caller's CWD.
    """
    roots: list[Path] = []

    # Frozen build: <install root>\computa.exe -> <install root>.
    if getattr(sys, "frozen", False):
        with contextlib.suppress(Exception):
            roots.append(Path(sys.executable).resolve().parent)

    # Source checkout: .../abso/settings/nvidia/npi.py -> repo root.
    with contextlib.suppress(Exception):
        roots.append(Path(__file__).resolve().parents[3])

    unique: list[Path] = []
    for root in roots:
        if root not in unique:
            unique.append(root)
    return unique

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
        """Export the customized Nvidia driver profiles to a .nip file.

        Uses NPI's ``-exportCustomized`` flag, which writes a timestamped .nip
        next to the executable and exits without opening a window. NPI 3.x
        restored this CLI path; on 2.4.x the flag does not exist and the process
        falls through to the GUI, which is detected and reported.

        NEVER pass a bare path as an argument. NPI's CLI grammar is
        ``nvidiaProfileInspector.exe [options] [profile1.nip ...]`` - bare
        arguments are files to IMPORT. The historical call here was
        ``-export <path>``, which in 3.x parses as an unknown option plus an
        import target, i.e. exactly the operation NPI_IMPORTS_DISABLED exists
        to prevent. It was inert only because the path never existed.

        Args:
            output_path: Path to save the exported .nip file.

        Raises:
            RuntimeError: If NPI is not configured or export fails.
        """
        if not self.npi_path:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Exporting Nvidia profile to: {output_path}")

        # -exportCustomized drops the file beside the executable, so diff the
        # directory to find what this run produced rather than guessing at the
        # timestamp format.
        npi_dir = self.npi_path.parent
        before = {p.resolve() for p in npi_dir.glob("*.nip")}

        process = None
        try:
            startupinfo = subprocess.STARTUPINFO()
            startupinfo.dwFlags |= subprocess.STARTF_USESHOWWINDOW
            startupinfo.wShowWindow = 0  # SW_HIDE

            process = subprocess.Popen(
                [str(self.npi_path), "-exportCustomized"],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
                startupinfo=startupinfo,
                creationflags=subprocess.CREATE_NO_WINDOW,
                cwd=str(npi_dir),
            )

            try:
                stdout, stderr = process.communicate(timeout=60)
            except subprocess.TimeoutExpired:
                # Unsupported flag on older NPI: the UI opened and is waiting.
                logger.warning("NPI export spawned GUI window, terminating process")
                self._kill_npi_process(process)
                raise RuntimeError(
                    "NPI export spawned a GUI instead of exiting. This build does not "
                    "support -exportCustomized (requires NPI 3.x). Nvidia profile "
                    "backup skipped."
                ) from None

            produced = sorted(
                ({p.resolve() for p in npi_dir.glob("*.nip")} - before),
                key=lambda p: p.stat().st_mtime,
            )
            if not produced:
                raise RuntimeError(
                    f"NPI export produced no .nip file (exit {process.returncode}): "
                    f"{stderr or stdout or 'no output'}"
                )

            output_path.parent.mkdir(parents=True, exist_ok=True)
            if output_path.exists():
                output_path.unlink()
            produced[-1].replace(output_path)

            # A single run can only legitimately produce one file; clean up any
            # extras so they are not mistaken for a later backup.
            for stale in produced[:-1]:
                with contextlib.suppress(OSError):
                    stale.unlink()

            if process.returncode != 0:
                logger.warning(
                    f"NPI exited {process.returncode} but produced {output_path.name}"
                )

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

        Note: headless export now works via ``export_profile`` on NPI 3.x, but
        parsing the resulting .nip into a settings dict is not implemented -
        the NVAPI DRS path in ``nvapi_drs.py`` is the authoritative reader.
        This method remains a stub.

        Returns:
            Empty dictionary (.nip parsing not implemented).
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
        common_paths: list[Path] = []

        # Anchored to the running program, so the installed tray (whose CWD is
        # the install root) resolves the same bundled copy a repo run does.
        for root in _app_roots():
            common_paths.extend([
                root / "tools" / "npi" / "nvidiaProfileInspector.exe",
                root / "tools" / "nvidiaProfileInspector.exe",
                root / "nvidiaProfileInspector.exe",
            ])

        common_paths += [
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
