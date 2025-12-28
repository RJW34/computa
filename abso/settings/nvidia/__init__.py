"""Nvidia settings handler.

This package manages Nvidia GPU settings via Nvidia Profile Inspector (NPI).

Example usage:
    from abso.settings.nvidia import NvidiaSettingsHandler

    handler = NvidiaSettingsHandler()
    current = handler.detect()
    issues = handler.audit()
    handler.apply({"preset": "minimum_latency"})
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

from .npi import NPIManager
from .presets import NVIDIA_PRESETS, NvidiaSettingIDs, NvidiaSettingValues
from .profiles import generate_custom_profile, generate_preset_profile

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = [
    "NvidiaSettingsHandler",
    "NvidiaSettingIDs",
    "NvidiaSettingValues",
    "NVIDIA_PRESETS",
]


class NvidiaSettingsHandler(SettingsHandler):
    """Handles Nvidia GPU settings via Profile Inspector.

    Manages:
    - 3D settings (Low Latency Mode, Power Management, etc.)
    - Per-application profiles
    - Global profile settings

    Note: Full functionality requires Nvidia Profile Inspector (NPI).
    Download from: https://github.com/Orbmu2k/nvidiaProfileInspector
    """

    # Backup directory for exported profiles
    BACKUP_DIR: Path = Path(tempfile.gettempdir()) / "abso_nvidia_backups"

    def __init__(self, npi_path: Path | str | None = None) -> None:
        """Initialize Nvidia settings handler.

        Args:
            npi_path: Path to nvidiaProfileInspector.exe.
        """
        self._npi = NPIManager(npi_path)

    @property
    def NPI_PATH(self) -> Path | None:
        """Get NPI path for backwards compatibility."""
        return self._npi.get_path()

    def detect(self) -> dict[str, Any]:
        """Detect current Nvidia settings.

        Returns GPU info via nvidia-smi and current 3D settings via NPI export.
        """
        result: dict[str, Any] = {
            "driver_version": None,
            "gpu_name": None,
            "vram_total_mb": None,
            "npi_available": self._npi.is_available(),
            "npi_path": str(self._npi.get_path()) if self._npi.get_path() else None,
            "current_settings": {},
        }

        # Get basic info from nvidia-smi
        gpu_info = self._detect_gpu_info()
        result.update(gpu_info)

        # Get current 3D settings if NPI is available
        if result["npi_available"]:
            try:
                settings = self._npi.read_current_settings()
                result["current_settings"] = settings
            except Exception as e:
                logger.debug(f"Failed to read current Nvidia settings: {e}")

        return result

    def audit(self) -> list[Issue]:
        """Audit Nvidia settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check NPI availability
        if not current.get("npi_available"):
            issues.append(Issue(
                title="Nvidia Profile Inspector not found",
                severity="info",
                current_value="Not installed",
                optimal_value="Installed and configured",
                explanation=(
                    "NPI is required for full Nvidia 3D settings management. "
                    "Download from: https://github.com/Orbmu2k/nvidiaProfileInspector"
                ),
                category="nvidia",
            ))
            return issues

        # Check current settings against optimal for gaming
        current_settings = current.get("current_settings", {})

        # Check Power Management Mode
        power_mode = current_settings.get("power_management")
        if power_mode and power_mode != "prefer_max_performance":
            issues.append(Issue(
                title="Power Management not set to maximum performance",
                severity="warning",
                current_value=power_mode,
                optimal_value="Prefer Maximum Performance",
                explanation=(
                    "Setting power management to 'Prefer Maximum Performance' ensures "
                    "the GPU runs at full speed during gaming, reducing frame time variance."
                ),
                category="nvidia",
            ))

        # Check Low Latency Mode
        low_latency = current_settings.get("low_latency_mode")
        if low_latency == "off":
            issues.append(Issue(
                title="Low Latency Mode is disabled",
                severity="warning",
                current_value="Off",
                optimal_value="On or Ultra",
                explanation=(
                    "Low Latency Mode reduces render queue depth, decreasing input lag. "
                    "'On' is safer; 'Ultra' provides minimum latency but may reduce FPS on CPU-limited scenarios."
                ),
                category="nvidia",
            ))

        # Check VSync if present
        vsync = current_settings.get("vsync")
        if vsync == "on":
            issues.append(Issue(
                title="VSync is enabled globally",
                severity="info",
                current_value="On",
                optimal_value="Off (use in-game or G-Sync)",
                explanation=(
                    "Global VSync adds input latency. Prefer per-game VSync settings or "
                    "use G-Sync/FreeSync for tear-free gaming without the latency penalty."
                ),
                category="nvidia",
            ))

        # Check Shader Cache
        shader_cache = current_settings.get("shader_cache")
        if shader_cache and shader_cache != "unlimited":
            issues.append(Issue(
                title="Shader Cache not set to Unlimited",
                severity="info",
                current_value=shader_cache,
                optimal_value="Unlimited",
                explanation=(
                    "Unlimited shader cache prevents stutter from shader recompilation. "
                    "Requires adequate disk space."
                ),
                category="nvidia",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Nvidia settings.

        Supports:
        - 'profile_path': Import a .nip profile file
        - 'preset': Apply a named preset (minimum_latency, low_latency_high_fps, balanced)
        - Individual settings: low_latency_mode, power_management, vsync, etc.

        Args:
            settings: Dictionary of settings to apply.
        """
        errors: list[str] = []
        applied: list[str] = []

        if not self._npi.is_available():
            return {
                "success": False,
                "error": "Nvidia Profile Inspector not configured or not found",
                "requires_reboot": False,
                "applied": [],
            }

        try:
            # Option 1: Apply from .nip profile file
            if "profile_path" in settings:
                profile_path = Path(settings["profile_path"])
                if profile_path.exists():
                    self._npi.import_profile(profile_path)
                    applied.append(f"Imported profile: {profile_path.name}")
                else:
                    errors.append(f"Profile file not found: {profile_path}")

            # Option 2: Apply a preset
            elif "preset" in settings:
                preset_name = settings["preset"]
                if preset_name in NVIDIA_PRESETS:
                    preset = NVIDIA_PRESETS[preset_name]
                    profile_path = generate_preset_profile(preset_name, preset)
                    self._npi.import_profile(profile_path)
                    applied.append(f"Applied preset: {preset_name}")
                else:
                    errors.append(f"Unknown preset: {preset_name}. Available: {list(NVIDIA_PRESETS.keys())}")

            # Option 3: Apply individual settings
            else:
                individual_settings = {
                    k: v for k, v in settings.items()
                    if k in ("low_latency_mode", "power_management", "vsync",
                             "max_frame_rate", "shader_cache", "threaded_optimization")
                }

                if individual_settings:
                    profile_path = generate_custom_profile(individual_settings)
                    self._npi.import_profile(profile_path)
                    applied.append(f"Applied settings: {list(individual_settings.keys())}")

        except Exception as e:
            errors.append(str(e))
            logger.error(f"Failed to apply Nvidia settings: {e}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
            "applied": applied,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current Nvidia profile settings.

        Exports current profile to a timestamped .nip file in the backup directory.

        Returns:
            Dictionary containing backup path and metadata.
        """
        if not self._npi.is_available():
            return {
                "success": False,
                "error": "NPI not available",
                "profile_path": None,
            }

        try:
            # Ensure backup directory exists
            self.BACKUP_DIR.mkdir(parents=True, exist_ok=True)

            # Create timestamped backup filename
            timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
            backup_filename = f"nvidia_backup_{timestamp}.nip"
            backup_path = self.BACKUP_DIR / backup_filename

            # Export current profile
            self._npi.export_profile(backup_path)

            # Get current settings for metadata
            current_settings = {}
            with contextlib.suppress(Exception):
                current_settings = self._npi.read_current_settings()

            logger.info(f"Nvidia profile backed up to: {backup_path}")

            return {
                "success": True,
                "profile_path": str(backup_path),
                "timestamp": timestamp,
                "settings_snapshot": current_settings,
            }

        except Exception as e:
            logger.error(f"Failed to backup Nvidia profile: {e}")
            return {
                "success": False,
                "error": str(e),
                "profile_path": None,
            }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Nvidia profile from backup.

        Args:
            data: Backup data containing 'profile_path' to a .nip file.

        Returns:
            True if restore succeeded, False otherwise.
        """
        profile_path = data.get("profile_path")

        if not profile_path:
            logger.warning("No profile_path in backup data, nothing to restore")
            return True  # Not an error, just nothing to do

        if not Path(profile_path).exists():
            logger.error(f"Backup profile not found: {profile_path}")
            return False

        result = self.apply({"profile_path": profile_path})
        return result.get("success", False)

    def _check_npi_available(self) -> bool:
        """Check if NPI is available (backwards compatibility)."""
        return self._npi.is_available()

    def _detect_gpu_info(self) -> dict[str, Any]:
        """Detect GPU information via nvidia-smi."""
        result: dict[str, Any] = {
            "driver_version": None,
            "gpu_name": None,
            "vram_total_mb": None,
        }

        try:
            smi_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if smi_result.returncode == 0 and smi_result.stdout.strip():
                parts = [p.strip() for p in smi_result.stdout.strip().split(",")]
                result["gpu_name"] = parts[0] if len(parts) > 0 else None
                result["driver_version"] = parts[1] if len(parts) > 1 else None
                if len(parts) > 2:
                    with contextlib.suppress(ValueError):
                        result["vram_total_mb"] = int(float(parts[2]))
        except FileNotFoundError:
            logger.debug("nvidia-smi not found - Nvidia GPU may not be present")
        except subprocess.TimeoutExpired:
            logger.debug("nvidia-smi timed out")
        except Exception as e:
            logger.debug(f"nvidia-smi detection failed: {e}")

        return result

    # Keep these methods for backwards compatibility with tests
    def _get_setting_value(self, value: str, setting_type: str) -> int:
        """Convert setting string to decimal value (backwards compatibility)."""
        from .profiles import get_setting_value
        return get_setting_value(value, setting_type)

    def _import_profile(self, profile_path: Path) -> None:
        """Import profile (backwards compatibility)."""
        self._npi.import_profile(profile_path)

    def _export_profile(self, output_path: Path) -> None:
        """Export profile (backwards compatibility)."""
        self._npi.export_profile(output_path)
