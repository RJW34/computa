"""OBS Studio settings handler.

Manages OBS encoder settings, video configuration, and profile optimization
for streaming and recording. Detects OBS installation, reads/writes profile
settings, and audits for common streaming issues.
"""

from __future__ import annotations

import configparser
import contextlib
import json
import logging
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


# Twitch streaming target settings
OPTIMAL_STREAM_SETTINGS = {
    "rate_control": "CBR",
    "bitrate": 6000,
    "preset": "p5",
    "multipass": "disabled",
    "profile": "high",
    "look-ahead": False,
    "psycho_aq": True,
    "keyint_sec": 2,
}

# Maximum bitrate for various platforms
PLATFORM_BITRATE_LIMITS = {
    "twitch": 8500,
    "youtube": 51000,
    "facebook": 8000,
    "kick": 8000,
}


class OBSSettingsHandler(SettingsHandler):
    """Handler for OBS Studio encoder and video settings.

    Manages:
    - Stream encoder settings (NVENC, x264, etc.)
    - Recording encoder settings
    - Video output resolution and scaling
    - Profile-specific configurations

    Supports both standard OBS installation (%APPDATA%/obs-studio)
    and portable installations.
    """

    def __init__(self, obs_path: Path | None = None) -> None:
        """Initialize OBS settings handler.

        Args:
            obs_path: Optional custom OBS config path. If None, uses
                      standard %APPDATA%/obs-studio location.
        """
        self._obs_path = obs_path or self._find_obs_path()
        self._profiles_path = self._obs_path / "basic" / "profiles" if self._obs_path else None

    def _find_obs_path(self) -> Path | None:
        """Find OBS configuration directory.

        Returns:
            Path to OBS config directory, or None if not found.
        """
        import os

        # Standard installation
        appdata = os.environ.get("APPDATA")
        if appdata:
            standard_path = Path(appdata) / "obs-studio"
            if standard_path.exists():
                return standard_path

        # Check for portable installation in common locations
        portable_paths = [
            Path("C:/OBS-Studio-Portable"),
            Path.home() / "OBS-Portable",
        ]
        for path in portable_paths:
            if path.exists() and (path / "config" / "obs-studio").exists():
                return path / "config" / "obs-studio"

        return None

    def _get_profile_path(self, profile_name: str) -> Path | None:
        """Get path to a specific OBS profile.

        Args:
            profile_name: Name of the OBS profile.

        Returns:
            Path to profile directory, or None if not found.
        """
        if not self._profiles_path:
            return None

        profile_path = self._profiles_path / profile_name
        if profile_path.exists():
            return profile_path
        return None

    def _list_profiles(self) -> list[str]:
        """List all OBS profiles.

        Returns:
            List of profile names.
        """
        if not self._profiles_path or not self._profiles_path.exists():
            return []

        return [
            d.name for d in self._profiles_path.iterdir()
            if d.is_dir() and (d / "basic.ini").exists()
        ]

    def _read_encoder_json(self, profile_path: Path, encoder_type: str = "stream") -> dict[str, Any]:
        """Read encoder JSON file.

        Args:
            profile_path: Path to OBS profile directory.
            encoder_type: "stream" or "record"

        Returns:
            Encoder settings dict, empty if not found.
        """
        filename = f"{encoder_type}Encoder.json"
        encoder_file = profile_path / filename

        if not encoder_file.exists():
            return {}

        try:
            with open(encoder_file, encoding="utf-8") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as e:
            logger.warning(f"Failed to read {filename}: {e}")
            return {}

    def _write_encoder_json(
        self, profile_path: Path, settings: dict[str, Any], encoder_type: str = "stream"
    ) -> bool:
        """Write encoder JSON file.

        Args:
            profile_path: Path to OBS profile directory.
            settings: Encoder settings to write.
            encoder_type: "stream" or "record"

        Returns:
            True if successful, False otherwise.
        """
        filename = f"{encoder_type}Encoder.json"
        encoder_file = profile_path / filename

        try:
            with open(encoder_file, "w", encoding="utf-8") as f:
                json.dump(settings, f, indent=None)
            return True
        except OSError as e:
            logger.error(f"Failed to write {filename}: {e}")
            return False

    def _read_basic_ini(self, profile_path: Path) -> configparser.ConfigParser:
        """Read basic.ini configuration file.

        Args:
            profile_path: Path to OBS profile directory.

        Returns:
            ConfigParser object with settings.
        """
        config = configparser.ConfigParser()
        basic_ini = profile_path / "basic.ini"

        if basic_ini.exists():
            try:
                # Handle BOM and encoding issues
                content = basic_ini.read_text(encoding="utf-8-sig")
                config.read_string(content)
            except (configparser.Error, OSError) as e:
                logger.warning(f"Failed to read basic.ini: {e}")

        return config

    def _write_basic_ini(self, profile_path: Path, config: configparser.ConfigParser) -> bool:
        """Write basic.ini configuration file.

        Args:
            profile_path: Path to OBS profile directory.
            config: ConfigParser object to write.

        Returns:
            True if successful, False otherwise.
        """
        basic_ini = profile_path / "basic.ini"

        try:
            with open(basic_ini, "w", encoding="utf-8") as f:
                config.write(f)
            return True
        except OSError as e:
            logger.error(f"Failed to write basic.ini: {e}")
            return False

    def detect(self) -> dict[str, Any]:
        """Detect current OBS settings.

        Returns:
            Dictionary containing:
            - obs_installed: Whether OBS is installed
            - obs_path: Path to OBS config
            - profiles: List of profile configs
        """
        result: dict[str, Any] = {
            "obs_installed": self._obs_path is not None and self._obs_path.exists(),
            "obs_path": str(self._obs_path) if self._obs_path else None,
            "profiles": [],
        }

        if not result["obs_installed"]:
            return result

        for profile_name in self._list_profiles():
            profile_path = self._get_profile_path(profile_name)
            if not profile_path:
                continue

            # Read encoder settings
            stream_encoder = self._read_encoder_json(profile_path, "stream")
            record_encoder = self._read_encoder_json(profile_path, "record")

            # Read basic.ini for video settings
            basic_ini = self._read_basic_ini(profile_path)

            # Extract video settings
            video_settings = {}
            if basic_ini.has_section("Video"):
                video_settings = {
                    "base_cx": basic_ini.getint("Video", "BaseCX", fallback=1920),
                    "base_cy": basic_ini.getint("Video", "BaseCY", fallback=1080),
                    "output_cx": basic_ini.getint("Video", "OutputCX", fallback=1920),
                    "output_cy": basic_ini.getint("Video", "OutputCY", fallback=1080),
                    "fps_common": basic_ini.get("Video", "FPSCommon", fallback="60"),
                    "scale_type": basic_ini.get("Video", "ScaleType", fallback="lanczos"),
                    "color_format": basic_ini.get("Video", "ColorFormat", fallback="NV12"),
                }

            # Extract output mode
            output_mode = "Simple"
            if basic_ini.has_section("Output"):
                output_mode = basic_ini.get("Output", "Mode", fallback="Simple")

            # Extract low latency setting
            low_latency = False
            if basic_ini.has_section("Output"):
                low_latency = basic_ini.getboolean("Output", "LowLatencyEnable", fallback=False)

            result["profiles"].append({
                "name": profile_name,
                "output_mode": output_mode,
                "stream_encoder": stream_encoder,
                "record_encoder": record_encoder,
                "video": video_settings,
                "low_latency": low_latency,
            })

        return result

    def audit(self) -> list[Issue]:
        """Audit OBS settings for streaming optimization issues.

        Checks for:
        - Lossless rate control (wrong for streaming)
        - Bitrate too high for platform
        - Wrong encoder preset
        - Output resolution issues
        - Missing low latency mode

        Returns:
            List of issues found.
        """
        issues: list[Issue] = []
        detected = self.detect()

        if not detected["obs_installed"]:
            issues.append(Issue(
                title="OBS Studio not detected",
                severity="info",
                current_value="Not installed",
                optimal_value="Installed",
                explanation="OBS Studio configuration not found. Install OBS or check paths.",
                category="obs",
            ))
            return issues

        for profile in detected["profiles"]:
            profile_name = profile["name"]
            encoder = profile.get("stream_encoder", {})
            video = profile.get("video", {})

            # Check rate control
            rate_control = encoder.get("rate_control", "").lower()
            if rate_control == "lossless":
                issues.append(Issue(
                    title=f"[{profile_name}] Lossless encoding for streaming",
                    severity="critical",
                    current_value="lossless",
                    optimal_value="CBR",
                    explanation=(
                        "Lossless mode generates unlimited bitrate that streaming platforms "
                        "cannot accept. This causes massive GPU load and will be rejected by Twitch. "
                        "Use CBR (Constant Bit Rate) for streaming."
                    ),
                    category="obs",
                ))

            # Check bitrate for streaming
            bitrate = encoder.get("bitrate", 0)
            if bitrate > PLATFORM_BITRATE_LIMITS["twitch"]:
                issues.append(Issue(
                    title=f"[{profile_name}] Bitrate too high for Twitch",
                    severity="critical",
                    current_value=f"{bitrate} kbps",
                    optimal_value="6000-8500 kbps",
                    explanation=(
                        f"Twitch caps bitrate at {PLATFORM_BITRATE_LIMITS['twitch']} kbps. "
                        f"Your {bitrate} kbps setting will be rejected or cause buffering."
                    ),
                    category="obs",
                ))

            # Check encoder preset
            preset = encoder.get("preset", "")
            if preset == "p7":
                issues.append(Issue(
                    title=f"[{profile_name}] Encoder preset too slow",
                    severity="warning",
                    current_value="p7 (Max Quality)",
                    optimal_value="p5 (Balanced)",
                    explanation=(
                        "p7 preset uses maximum GPU resources for quality overkill. "
                        "For streaming, p5 provides excellent quality with much lower GPU load."
                    ),
                    category="obs",
                ))

            # Check output resolution
            output_cx = video.get("output_cx", 1920)
            output_cy = video.get("output_cy", 1080)
            if output_cx > 1920 or output_cy > 1080:
                # Calculate approximate required bitrate for resolution
                pixels = output_cx * output_cy
                fps = int(video.get("fps_common", 60))
                # Rough estimate: 0.1 bits per pixel per second is minimum
                min_bitrate = (pixels * fps * 0.1) / 1000

                issues.append(Issue(
                    title=f"[{profile_name}] Output resolution too high for streaming",
                    severity="warning",
                    current_value=f"{output_cx}x{output_cy}",
                    optimal_value="1920x1080",
                    explanation=(
                        f"Streaming at {output_cx}x{output_cy} requires ~{int(min_bitrate)}+ kbps for clarity. "
                        "Twitch recommends 1080p at 6000 kbps. Higher resolutions = worse quality per pixel."
                    ),
                    category="obs",
                ))

            # Check low latency mode
            if not profile.get("low_latency", False):
                issues.append(Issue(
                    title=f"[{profile_name}] Low Latency mode disabled",
                    severity="info",
                    current_value="Disabled",
                    optimal_value="Enabled",
                    explanation=(
                        "Low Latency mode reduces stream delay. Enable in Output > Advanced > Low Latency Mode."
                    ),
                    category="obs",
                ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply OBS profile settings.

        Args:
            settings: Dictionary with:
                - profile_name: OBS profile to modify (default: first found)
                - stream_encoder: Stream encoder settings
                - video: Video output settings
                - low_latency: Enable low latency mode

        Returns:
            Result dict with 'success', 'error', 'requires_restart' keys.
        """
        result: dict[str, Any] = {
            "success": False,
            "requires_reboot": False,
            "requires_restart": True,  # OBS must be restarted for changes
            "changes": [],
        }

        if not self._obs_path or not self._profiles_path:
            result["error"] = "OBS installation not found"
            return result

        # Determine which profile to modify
        profile_name = settings.get("profile_name")
        if not profile_name:
            profiles = self._list_profiles()
            if not profiles:
                result["error"] = "No OBS profiles found"
                return result
            profile_name = profiles[0]

        profile_path = self._get_profile_path(profile_name)
        if not profile_path:
            result["error"] = f"Profile '{profile_name}' not found"
            return result

        changes: list[str] = []

        # Apply stream encoder settings
        if "stream_encoder" in settings:
            encoder_settings = settings["stream_encoder"]
            if self._write_encoder_json(profile_path, encoder_settings, "stream"):
                changes.append(f"Updated stream encoder: {encoder_settings}")
            else:
                result["error"] = "Failed to write stream encoder settings"
                return result

        # Apply video settings and low latency mode
        if "video" in settings or "low_latency" in settings:
            config = self._read_basic_ini(profile_path)

            if "video" in settings:
                video = settings["video"]
                if not config.has_section("Video"):
                    config.add_section("Video")

                if "output_cx" in video:
                    config.set("Video", "OutputCX", str(video["output_cx"]))
                if "output_cy" in video:
                    config.set("Video", "OutputCY", str(video["output_cy"]))
                if "scale_type" in video:
                    config.set("Video", "ScaleType", video["scale_type"])
                changes.append(f"Updated video settings: {video}")

            if "low_latency" in settings:
                if not config.has_section("Output"):
                    config.add_section("Output")
                config.set("Output", "LowLatencyEnable", "true" if settings["low_latency"] else "false")
                changes.append(f"Low latency: {settings['low_latency']}")

            if not self._write_basic_ini(profile_path, config):
                result["error"] = "Failed to write basic.ini"
                return result

        result["success"] = True
        result["changes"] = changes
        result["message"] = f"OBS profile '{profile_name}' updated. Restart OBS to apply changes."

        return result

    def backup(self) -> dict[str, Any]:
        """Backup all OBS profile configurations.

        Returns:
            Dictionary containing all profile settings that can be restored.
        """
        backup_data: dict[str, Any] = {
            "obs_path": str(self._obs_path) if self._obs_path else None,
            "profiles": {},
        }

        if not self._profiles_path or not self._profiles_path.exists():
            return backup_data

        for profile_name in self._list_profiles():
            profile_path = self._get_profile_path(profile_name)
            if not profile_path:
                continue

            profile_backup: dict[str, Any] = {}

            # Backup encoder JSONs
            for encoder_type in ["stream", "record"]:
                encoder_file = profile_path / f"{encoder_type}Encoder.json"
                if encoder_file.exists():
                    with contextlib.suppress(OSError):
                        profile_backup[f"{encoder_type}_encoder"] = encoder_file.read_text(encoding="utf-8")

            # Backup basic.ini
            basic_ini = profile_path / "basic.ini"
            if basic_ini.exists():
                with contextlib.suppress(OSError):
                    profile_backup["basic_ini"] = basic_ini.read_text(encoding="utf-8-sig")

            backup_data["profiles"][profile_name] = profile_backup

        return backup_data

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore OBS profiles from backup data.

        Args:
            data: Previously backed up settings data.

        Returns:
            True if restore succeeded, False otherwise.
        """
        if not self._profiles_path:
            logger.error("OBS profiles path not found")
            return False

        profiles_data = data.get("profiles", {})
        if not profiles_data:
            logger.warning("No profile data in backup")
            return True  # Nothing to restore is not a failure

        success = True
        for profile_name, profile_data in profiles_data.items():
            profile_path = self._get_profile_path(profile_name)
            if not profile_path:
                # Try to create the profile directory if it doesn't exist
                profile_path = self._profiles_path / profile_name
                try:
                    profile_path.mkdir(parents=True, exist_ok=True)
                except OSError as e:
                    logger.error(f"Failed to create profile directory {profile_name}: {e}")
                    success = False
                    continue

            # Restore encoder JSONs
            for encoder_type in ["stream", "record"]:
                key = f"{encoder_type}_encoder"
                if key in profile_data:
                    encoder_file = profile_path / f"{encoder_type}Encoder.json"
                    try:
                        encoder_file.write_text(profile_data[key], encoding="utf-8")
                    except OSError as e:
                        logger.error(f"Failed to restore {encoder_type} encoder for {profile_name}: {e}")
                        success = False

            # Restore basic.ini
            if "basic_ini" in profile_data:
                basic_ini = profile_path / "basic.ini"
                try:
                    basic_ini.write_text(profile_data["basic_ini"], encoding="utf-8")
                except OSError as e:
                    logger.error(f"Failed to restore basic.ini for {profile_name}: {e}")
                    success = False

        return success

    def apply_streaming_preset(
        self,
        profile_name: str | None = None,
        bitrate: int = 6000,
        resolution: tuple[int, int] = (1920, 1080),
        preset: str = "p5",
    ) -> dict[str, Any]:
        """Apply ABSO's streaming preset to an OBS profile.

        Convenience method that applies a conservative Twitch streaming baseline.

        Args:
            profile_name: OBS profile to modify (None = first profile)
            bitrate: Target bitrate in kbps (default: 6000)
            resolution: Output resolution tuple (default: 1920x1080)
            preset: NVENC preset (default: p5)

        Returns:
            Result dict from apply().
        """
        settings = {
            "profile_name": profile_name,
            "stream_encoder": {
                "rate_control": "CBR",
                "bitrate": bitrate,
                "preset": preset,
                "multipass": "disabled",
                "profile": "high",
                "look-ahead": False,
                "psycho_aq": True,
            },
            "video": {
                "output_cx": resolution[0],
                "output_cy": resolution[1],
                "scale_type": "lanczos",
            },
            "low_latency": True,
        }

        return self.apply(settings)
