"""Nvidia Profile Inspector (NPI) integration."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from pathlib import Path
from typing import Any

from .parsing import parse_nip_file

logger = logging.getLogger(__name__)


class NPIManager:
    """Manages Nvidia Profile Inspector operations.

    Handles:
    - NPI executable discovery
    - Profile import/export
    - Current settings reading
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
        """Import a Nvidia profile file using NPI.

        Uses the -silent flag for headless profile application.

        Args:
            profile_path: Path to the .nip file to import.

        Raises:
            RuntimeError: If NPI is not configured or import fails.
        """
        if not self.npi_path:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Importing Nvidia profile: {profile_path}")

        result = subprocess.run(
            [str(self.npi_path), "-silent", str(profile_path)],
            capture_output=True,
            text=True,
            timeout=30,
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
            # Use Popen for better process control
            process = subprocess.Popen(
                [str(self.npi_path), "-export", str(output_path)],
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True,
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
                )

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
        """Read current Nvidia 3D settings by exporting and parsing a profile.

        Returns:
            Dictionary of current settings.
        """
        if not self.is_available():
            return {}

        temp_path = Path(tempfile.gettempdir()) / "abso_nvidia_current.nip"

        try:
            self.export_profile(temp_path)
            settings = parse_nip_file(temp_path)
            return settings

        except Exception as e:
            logger.debug(f"Failed to read current settings: {e}")
            return {}
        finally:
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

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
