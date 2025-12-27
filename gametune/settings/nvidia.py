"""Nvidia settings handler."""

from __future__ import annotations

import logging
import os
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from gametune.settings.base import SettingsHandler
from gametune.core.models import Issue

logger = logging.getLogger(__name__)


# Nvidia Profile Inspector setting IDs and human-readable names
# These are the internal IDs used by NPI for common gaming settings
class NvidiaSettingIDs:
    """Known Nvidia Profile Inspector setting IDs."""

    # Low Latency Mode (0x0x10834BB = Enable, 0x10834BC = Ultra)
    LOW_LATENCY_MODE = "0x10834BB"

    # Power Management Mode
    POWER_MANAGEMENT = "0x10834E4"

    # VSync
    VSYNC = "0x10834F8"

    # Max Frame Rate
    MAX_FRAME_RATE = "0x10835F7"

    # Shader Cache Size
    SHADER_CACHE_SIZE = "0x10835FE"

    # Threaded Optimization
    THREADED_OPTIMIZATION = "0x10835E8"

    # Triple Buffering
    TRIPLE_BUFFERING = "0x10834FC"

    # Texture Filtering Quality
    TEXTURE_FILTERING_QUALITY = "0x1085B0E"

    # Anisotropic Filtering
    ANISOTROPIC_FILTERING = "0x1085BA9"


class NvidiaSettingValues:
    """Known values for Nvidia settings."""

    # Low Latency Mode
    LOW_LATENCY_OFF = 0x00000000
    LOW_LATENCY_ON = 0x00000001
    LOW_LATENCY_ULTRA = 0x00000002

    # Power Management Mode
    POWER_ADAPTIVE = 0x00000000
    POWER_PREFER_MAX_PERFORMANCE = 0x00000001
    POWER_OPTIMAL = 0x00000002

    # VSync
    VSYNC_OFF = 0x00000000
    VSYNC_ON = 0x00000001
    VSYNC_ADAPTIVE = 0x00000002
    VSYNC_ADAPTIVE_HALF = 0x00000003

    # Max Frame Rate
    FRAME_RATE_OFF = 0x00000000

    # Shader Cache Size
    SHADER_CACHE_DEFAULT = 0x00000000
    SHADER_CACHE_UNLIMITED = 0xFFFFFFFF

    # Threaded Optimization
    THREADED_OPT_AUTO = 0x00000000
    THREADED_OPT_ON = 0x00000001
    THREADED_OPT_OFF = 0x00000002


# Preset profiles for different optimization targets
NVIDIA_PRESETS: dict[str, dict[str, Any]] = {
    "minimum_latency": {
        "description": "Ultra-low latency for competitive gaming",
        "settings": {
            "low_latency_mode": "ultra",
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
        },
    },
    "low_latency_high_fps": {
        "description": "Low latency with stable high FPS",
        "settings": {
            "low_latency_mode": "on",
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
        },
    },
    "balanced": {
        "description": "Balanced performance and quality",
        "settings": {
            "low_latency_mode": "on",
            "power_management": "prefer_max_performance",
            "vsync": "adaptive",
            "max_frame_rate": "off",
            "shader_cache": "unlimited",
            "threaded_optimization": "auto",
        },
    },
}


class NvidiaSettingsHandler(SettingsHandler):
    """Handles Nvidia GPU settings via Profile Inspector.

    Manages:
    - 3D settings (Low Latency Mode, Power Management, etc.)
    - Per-application profiles
    - Global profile settings

    Note: Full functionality requires Nvidia Profile Inspector (NPI).
    Download from: https://github.com/Orbmu2k/nvidiaProfileInspector
    """

    # Path to Nvidia Profile Inspector (user should configure)
    NPI_PATH: Path | None = None

    # Backup directory for exported profiles
    BACKUP_DIR: Path = Path(tempfile.gettempdir()) / "gametune_nvidia_backups"

    def __init__(self, npi_path: Path | str | None = None) -> None:
        """Initialize Nvidia settings handler.

        Args:
            npi_path: Path to nvidiaProfileInspector.exe.
        """
        if npi_path:
            self.NPI_PATH = Path(npi_path)
        else:
            # Try to find NPI in common locations
            self._find_npi()

    def detect(self) -> dict[str, Any]:
        """Detect current Nvidia settings.

        Returns GPU info via nvidia-smi and current 3D settings via NPI export.
        """
        result: dict[str, Any] = {
            "driver_version": None,
            "gpu_name": None,
            "vram_total_mb": None,
            "npi_available": self._check_npi_available(),
            "npi_path": str(self.NPI_PATH) if self.NPI_PATH else None,
            "current_settings": {},
        }

        # Get basic info from nvidia-smi
        gpu_info = self._detect_gpu_info()
        result.update(gpu_info)

        # Get current 3D settings if NPI is available
        if result["npi_available"]:
            try:
                settings = self._read_current_settings()
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

        if not self._check_npi_available():
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
                    self._import_profile(profile_path)
                    applied.append(f"Imported profile: {profile_path.name}")
                else:
                    errors.append(f"Profile file not found: {profile_path}")

            # Option 2: Apply a preset
            elif "preset" in settings:
                preset_name = settings["preset"]
                if preset_name in NVIDIA_PRESETS:
                    preset = NVIDIA_PRESETS[preset_name]
                    profile_path = self._generate_preset_profile(preset_name, preset)
                    self._import_profile(profile_path)
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
                    profile_path = self._generate_custom_profile(individual_settings)
                    self._import_profile(profile_path)
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
        if not self._check_npi_available():
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
            self._export_profile(backup_path)

            # Get current settings for metadata
            current_settings = {}
            try:
                current_settings = self._read_current_settings()
            except Exception:
                pass

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

    # -------------------------------------------------------------------------
    # Private helper methods
    # -------------------------------------------------------------------------

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
            Path(os.environ.get("ProgramFiles", "C:\\Program Files")) / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
            Path(os.environ.get("ProgramFiles(x86)", "C:\\Program Files (x86)")) / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
            # Local AppData
            Path(os.environ.get("LOCALAPPDATA", "")) / "nvidiaProfileInspector" / "nvidiaProfileInspector.exe",
        ]

        for path in common_paths:
            try:
                if path.exists():
                    self.NPI_PATH = path
                    logger.debug(f"Found NPI at: {path}")
                    return
            except (OSError, PermissionError):
                continue

    def _check_npi_available(self) -> bool:
        """Check if Nvidia Profile Inspector is available."""
        if self.NPI_PATH and self.NPI_PATH.exists():
            return True

        # Try to find it again
        self._find_npi()
        return self.NPI_PATH is not None and self.NPI_PATH.exists()

    def _detect_gpu_info(self) -> dict[str, Any]:
        """Detect GPU information via nvidia-smi."""
        result: dict[str, Any] = {
            "driver_version": None,
            "gpu_name": None,
            "vram_total_mb": None,
        }

        try:
            # Query GPU name and driver version
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
                    try:
                        result["vram_total_mb"] = int(float(parts[2]))
                    except ValueError:
                        pass
        except FileNotFoundError:
            logger.debug("nvidia-smi not found - Nvidia GPU may not be present")
        except subprocess.TimeoutExpired:
            logger.debug("nvidia-smi timed out")
        except Exception as e:
            logger.debug(f"nvidia-smi detection failed: {e}")

        return result

    def _read_current_settings(self) -> dict[str, Any]:
        """Read current Nvidia 3D settings by exporting and parsing a profile.

        Note: This is a simplified implementation. Full parsing of .nip XML
        would require more detailed handling.
        """
        if not self._check_npi_available():
            return {}

        # Export to temp file
        temp_path = Path(tempfile.gettempdir()) / "gametune_nvidia_current.nip"

        try:
            self._export_profile(temp_path)

            # Parse the exported profile (NIP files are XML-like)
            # For now, return a basic structure - full parsing would be more complex
            settings = self._parse_nip_file(temp_path)
            return settings

        except Exception as e:
            logger.debug(f"Failed to read current settings: {e}")
            return {}
        finally:
            # Clean up temp file
            try:
                if temp_path.exists():
                    temp_path.unlink()
            except Exception:
                pass

    def _parse_nip_file(self, nip_path: Path) -> dict[str, Any]:
        """Parse a .nip profile file to extract key settings.

        NIP files are XML format. This extracts gaming-relevant settings.
        """
        settings: dict[str, Any] = {}

        if not nip_path.exists():
            return settings

        try:
            import xml.etree.ElementTree as ET

            tree = ET.parse(nip_path)
            root = tree.getroot()

            # Map of setting IDs to human-readable names and value parsers
            setting_map = {
                "0x10834BB": ("low_latency_mode", self._parse_low_latency_value),
                "0x10834E4": ("power_management", self._parse_power_management_value),
                "0x10834F8": ("vsync", self._parse_vsync_value),
                "0x10835F7": ("max_frame_rate", self._parse_frame_rate_value),
                "0x10835FE": ("shader_cache", self._parse_shader_cache_value),
                "0x10835E8": ("threaded_optimization", self._parse_threaded_opt_value),
            }

            # Find the base profile (global settings)
            for profile in root.findall(".//Profile"):
                profile_name = profile.get("name", "")
                if profile_name.lower() in ("base profile", "_global_driver_profile"):
                    for setting in profile.findall(".//ProfileSetting"):
                        setting_id = setting.get("id", "")
                        if setting_id in setting_map:
                            name, parser = setting_map[setting_id]
                            value_elem = setting.find("SettingValue")
                            if value_elem is not None and value_elem.text:
                                try:
                                    settings[name] = parser(value_elem.text)
                                except ValueError:
                                    logger.debug(f"Failed to parse setting {name}: {value_elem.text}")
                    break  # Only need the base profile

        except ET.ParseError as e:
            logger.debug(f"Failed to parse NIP file (XML error): {e}")
        except (OSError, IOError) as e:
            logger.debug(f"Failed to read NIP file: {e}")

        return settings

    def _parse_low_latency_value(self, value: str) -> str:
        """Convert low latency mode value to human-readable string."""
        try:
            int_val = int(value, 0)  # Handle hex or decimal
            if int_val == NvidiaSettingValues.LOW_LATENCY_OFF:
                return "off"
            elif int_val == NvidiaSettingValues.LOW_LATENCY_ON:
                return "on"
            elif int_val == NvidiaSettingValues.LOW_LATENCY_ULTRA:
                return "ultra"
        except ValueError:
            pass
        return "unknown"

    def _parse_power_management_value(self, value: str) -> str:
        """Convert power management value to human-readable string."""
        try:
            int_val = int(value, 0)
            if int_val == NvidiaSettingValues.POWER_ADAPTIVE:
                return "adaptive"
            elif int_val == NvidiaSettingValues.POWER_PREFER_MAX_PERFORMANCE:
                return "prefer_max_performance"
            elif int_val == NvidiaSettingValues.POWER_OPTIMAL:
                return "optimal"
        except ValueError:
            pass
        return "unknown"

    def _parse_vsync_value(self, value: str) -> str:
        """Convert VSync value to human-readable string."""
        try:
            int_val = int(value, 0)
            if int_val == NvidiaSettingValues.VSYNC_OFF:
                return "off"
            elif int_val == NvidiaSettingValues.VSYNC_ON:
                return "on"
            elif int_val == NvidiaSettingValues.VSYNC_ADAPTIVE:
                return "adaptive"
            elif int_val == NvidiaSettingValues.VSYNC_ADAPTIVE_HALF:
                return "adaptive_half"
        except ValueError:
            pass
        return "unknown"

    def _parse_frame_rate_value(self, value: str) -> str:
        """Convert frame rate limit value to human-readable string."""
        try:
            int_val = int(value, 0)
            if int_val == 0:
                return "off"
            return str(int_val)
        except ValueError:
            pass
        return "unknown"

    def _parse_shader_cache_value(self, value: str) -> str:
        """Convert shader cache value to human-readable string."""
        try:
            int_val = int(value, 0)
            if int_val == 0:
                return "default"
            elif int_val == 0xFFFFFFFF:
                return "unlimited"
            return f"{int_val}MB"
        except ValueError:
            pass
        return "unknown"

    def _parse_threaded_opt_value(self, value: str) -> str:
        """Convert threaded optimization value to human-readable string."""
        try:
            int_val = int(value, 0)
            if int_val == NvidiaSettingValues.THREADED_OPT_AUTO:
                return "auto"
            elif int_val == NvidiaSettingValues.THREADED_OPT_ON:
                return "on"
            elif int_val == NvidiaSettingValues.THREADED_OPT_OFF:
                return "off"
        except ValueError:
            pass
        return "unknown"

    def _import_profile(self, profile_path: Path) -> None:
        """Import a Nvidia profile file using NPI."""
        if not self.NPI_PATH:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Importing Nvidia profile: {profile_path}")

        result = subprocess.run(
            [str(self.NPI_PATH), "-import", str(profile_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"NPI import failed: {result.stderr or result.stdout}")

    def _export_profile(self, output_path: Path) -> None:
        """Export current Nvidia profile using NPI."""
        if not self.NPI_PATH:
            raise RuntimeError("NPI path not configured")

        logger.info(f"Exporting Nvidia profile to: {output_path}")

        result = subprocess.run(
            [str(self.NPI_PATH), "-export", str(output_path)],
            capture_output=True,
            text=True,
            timeout=30,
        )

        if result.returncode != 0:
            raise RuntimeError(f"NPI export failed: {result.stderr or result.stdout}")

    def _generate_preset_profile(self, preset_name: str, preset: dict[str, Any]) -> Path:
        """Generate a .nip profile file from a preset configuration."""
        settings = preset.get("settings", {})
        return self._generate_custom_profile(settings, f"gametune_{preset_name}")

    def _generate_custom_profile(self, settings: dict[str, Any], profile_name: str = "gametune_custom") -> Path:
        """Generate a minimal .nip profile with specified settings.

        Args:
            settings: Dictionary of setting names to values.
            profile_name: Name for the profile.

        Returns:
            Path to the generated .nip file.
        """
        # Build XML for the profile
        xml_settings = []

        # Map human-readable setting names to NPI format
        if "low_latency_mode" in settings:
            value = self._get_low_latency_hex(settings["low_latency_mode"])
            xml_settings.append(self._make_setting_xml("0x10834BB", value))

        if "power_management" in settings:
            value = self._get_power_management_hex(settings["power_management"])
            xml_settings.append(self._make_setting_xml("0x10834E4", value))

        if "vsync" in settings:
            value = self._get_vsync_hex(settings["vsync"])
            xml_settings.append(self._make_setting_xml("0x10834F8", value))

        if "max_frame_rate" in settings:
            value = self._get_frame_rate_hex(settings["max_frame_rate"])
            xml_settings.append(self._make_setting_xml("0x10835F7", value))

        if "shader_cache" in settings:
            value = self._get_shader_cache_hex(settings["shader_cache"])
            xml_settings.append(self._make_setting_xml("0x10835FE", value))

        if "threaded_optimization" in settings:
            value = self._get_threaded_opt_hex(settings["threaded_optimization"])
            xml_settings.append(self._make_setting_xml("0x10835E8", value))

        # Construct minimal NIP XML
        settings_xml = "\n        ".join(xml_settings)

        nip_content = f'''<?xml version="1.0" encoding="utf-16"?>
<ArrayOfProfile>
  <Profile>
    <ProfileName>Base Profile</ProfileName>
    <Executeables />
    <Settings>
        {settings_xml}
    </Settings>
  </Profile>
</ArrayOfProfile>
'''

        # Write to temp file
        temp_dir = Path(tempfile.gettempdir()) / "gametune_nvidia"
        temp_dir.mkdir(parents=True, exist_ok=True)

        profile_path = temp_dir / f"{profile_name}.nip"
        profile_path.write_text(nip_content, encoding="utf-16")

        logger.debug(f"Generated NIP profile at: {profile_path}")
        return profile_path

    def _make_setting_xml(self, setting_id: str, value: str) -> str:
        """Create XML for a single setting."""
        return f'''<ProfileSetting>
            <SettingNameInfo>{setting_id}</SettingNameInfo>
            <SettingID>{setting_id}</SettingID>
            <SettingValue>{value}</SettingValue>
            <ValueType>Dword</ValueType>
        </ProfileSetting>'''

    def _get_low_latency_hex(self, value: str) -> str:
        """Convert low latency mode string to hex value."""
        mapping = {
            "off": "0x00000000",
            "on": "0x00000001",
            "ultra": "0x00000002",
        }
        return mapping.get(value.lower(), "0x00000000")

    def _get_power_management_hex(self, value: str) -> str:
        """Convert power management string to hex value."""
        mapping = {
            "adaptive": "0x00000000",
            "prefer_max_performance": "0x00000001",
            "optimal": "0x00000002",
        }
        return mapping.get(value.lower(), "0x00000001")

    def _get_vsync_hex(self, value: str) -> str:
        """Convert VSync string to hex value."""
        mapping = {
            "off": "0x00000000",
            "on": "0x00000001",
            "adaptive": "0x00000002",
            "adaptive_half": "0x00000003",
        }
        return mapping.get(value.lower(), "0x00000000")

    def _get_frame_rate_hex(self, value: str) -> str:
        """Convert frame rate limit to hex value."""
        if value.lower() == "off":
            return "0x00000000"
        try:
            fps = int(value)
            return f"0x{fps:08X}"
        except ValueError:
            return "0x00000000"

    def _get_shader_cache_hex(self, value: str) -> str:
        """Convert shader cache setting to hex value."""
        if value.lower() == "off":
            return "0x00000000"
        elif value.lower() in ("unlimited", "max"):
            return "0xFFFFFFFF"
        elif value.lower() == "default":
            return "0x00000000"
        try:
            size_mb = int(value)
            return f"0x{size_mb:08X}"
        except ValueError:
            return "0x00000000"

    def _get_threaded_opt_hex(self, value: str) -> str:
        """Convert threaded optimization string to hex value."""
        mapping = {
            "auto": "0x00000000",
            "on": "0x00000001",
            "off": "0x00000002",
        }
        return mapping.get(value.lower(), "0x00000000")
