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

        Note: NPI may not support headless export. This attempts the export
        but may fail if NPI requires GUI interaction for exports.

        Args:
            output_path: Path to save the exported .nip file.

        Raises:
            RuntimeError: If NPI is not configured or export fails.
        """
        if not self.npi_path:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Exporting Nvidia profile to: {output_path}")

        result = subprocess.run(
            [str(self.npi_path), "-export", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        # NPI may return 0 even if it opened GUI instead of exporting
        if not output_path.exists():
            raise RuntimeError(
                "NPI export did not create file. Export may require GUI interaction. "
                "Run NPI manually and use File > Export to create a backup."
            )

        if result.returncode != 0:
            raise RuntimeError(f"NPI export failed: {result.stderr or result.stdout}")

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
