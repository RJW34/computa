"""NIP profile generation utilities."""

from __future__ import annotations

import logging
import tempfile
from pathlib import Path
from typing import Any

from .presets import NVIDIA_PRESETS, NvidiaSettingDecimalIDs

logger = logging.getLogger(__name__)


def generate_preset_profile(preset_name: str, preset: dict[str, Any] | None = None) -> Path:
    """Generate a .nip profile file from a preset configuration.

    Args:
        preset_name: Name of the preset.
        preset: Preset configuration dict. If None, looks up from NVIDIA_PRESETS.

    Returns:
        Path to the generated .nip file.
    """
    if preset is None:
        preset = NVIDIA_PRESETS.get(preset_name, {})
    settings = preset.get("settings", {})
    return generate_custom_profile(settings, f"abso_{preset_name}")


def generate_custom_profile(settings: dict[str, Any], profile_name: str = "abso_custom") -> Path:
    """Generate a minimal .nip profile with specified settings.

    NPI .nip files use UTF-16 XML with decimal setting IDs and values.

    Args:
        settings: Dictionary of setting names to values.
        profile_name: Name for the profile.

    Returns:
        Path to the generated .nip file.
    """
    xml_settings = []

    if "low_latency_mode" in settings:
        value = get_setting_value(settings["low_latency_mode"], "low_latency")
        xml_settings.append(_make_setting_xml(NvidiaSettingDecimalIDs.LOW_LATENCY_MODE, value))

    if "power_management" in settings:
        value = get_setting_value(settings["power_management"], "power")
        xml_settings.append(_make_setting_xml(NvidiaSettingDecimalIDs.POWER_MANAGEMENT, value))

    if "vsync" in settings:
        value = get_setting_value(settings["vsync"], "vsync")
        xml_settings.append(_make_setting_xml(NvidiaSettingDecimalIDs.VSYNC, value))

    if "max_frame_rate" in settings:
        value = get_setting_value(settings["max_frame_rate"], "framerate")
        xml_settings.append(_make_setting_xml(NvidiaSettingDecimalIDs.MAX_FRAME_RATE, value))

    if "shader_cache" in settings:
        value = get_setting_value(settings["shader_cache"], "shader_cache")
        xml_settings.append(_make_setting_xml(NvidiaSettingDecimalIDs.SHADER_CACHE_SIZE, value))

    if "threaded_optimization" in settings:
        value = get_setting_value(settings["threaded_optimization"], "threaded")
        xml_settings.append(_make_setting_xml(NvidiaSettingDecimalIDs.THREADED_OPTIMIZATION, value))

    # Construct NIP XML matching real NPI format
    settings_xml = "\n      ".join(xml_settings)

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

    # Write to temp file with UTF-16 encoding (with BOM)
    temp_dir = Path(tempfile.gettempdir()) / "abso_nvidia"
    temp_dir.mkdir(parents=True, exist_ok=True)

    profile_path = temp_dir / f"{profile_name}.nip"
    profile_path.write_text(nip_content, encoding="utf-16")

    logger.debug(f"Generated NIP profile at: {profile_path}")
    return profile_path


def _make_setting_xml(setting_id: int, value: int) -> str:
    """Create XML for a single setting using decimal format."""
    return f'''<ProfileSetting>
        <SettingID>{setting_id}</SettingID>
        <SettingValue>{value}</SettingValue>
      </ProfileSetting>'''


def get_setting_value(value: str, setting_type: str) -> int:
    """Convert setting string to decimal value.

    Args:
        value: Human-readable setting value.
        setting_type: Type of setting for value mapping.

    Returns:
        Decimal value for the setting.
    """
    if setting_type == "low_latency":
        mapping = {"off": 0, "on": 1, "ultra": 2}
        return mapping.get(value.lower(), 0)

    elif setting_type == "power":
        mapping = {"adaptive": 0, "prefer_max_performance": 1, "optimal": 2}
        return mapping.get(value.lower(), 1)

    elif setting_type == "vsync":
        mapping = {"off": 0, "on": 1, "adaptive": 2, "adaptive_half": 3}
        return mapping.get(value.lower(), 0)

    elif setting_type == "framerate":
        if value.lower() == "off":
            return 0
        try:
            return int(value)
        except ValueError:
            return 0

    elif setting_type == "shader_cache":
        if value.lower() == "off":
            return 0
        elif value.lower() in ("unlimited", "max"):
            return 4294967295  # 0xFFFFFFFF
        elif value.lower() == "default":
            return 0
        try:
            return int(value)
        except ValueError:
            return 0

    elif setting_type == "threaded":
        mapping = {"auto": 0, "on": 1, "off": 2}
        return mapping.get(value.lower(), 0)

    return 0
