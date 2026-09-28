"""NIP file parsing utilities."""

from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from collections.abc import Callable
from pathlib import Path
from typing import Any

from .presets import NvidiaSettingIDs, NvidiaSettingValues

logger = logging.getLogger(__name__)


def parse_nip_file(nip_path: Path) -> dict[str, Any]:
    """Parse a .nip profile file to extract key settings.

    NIP files are XML format. This extracts gaming-relevant settings.

    Args:
        nip_path: Path to the .nip file.

    Returns:
        Dictionary of setting names to values.
    """
    settings: dict[str, Any] = {}

    if not nip_path.exists():
        return settings

    try:
        tree = ET.parse(nip_path)
        root = tree.getroot()

        # Map of setting IDs to human-readable names and value parsers
        setting_map: dict[str, tuple[str, Callable[[str], str]]] = {
            NvidiaSettingIDs.LOW_LATENCY_MODE: ("low_latency_mode", parse_low_latency_value),
            NvidiaSettingIDs.PRERENDERED_FRAMES: ("prerendered_frames", lambda value: str(int(value, 0))),
            NvidiaSettingIDs.ULTRA_LOW_LATENCY: ("ultra_low_latency", lambda value: str(int(value, 0))),
            NvidiaSettingIDs.POWER_MANAGEMENT: ("power_management", parse_power_management_value),
            NvidiaSettingIDs.VSYNC: ("vsync", parse_vsync_value),
            NvidiaSettingIDs.VSYNC_TEAR_CONTROL: ("vsync_tear_control", lambda value: str(int(value, 0))),
            NvidiaSettingIDs.MAX_FRAME_RATE: ("max_frame_rate", parse_frame_rate_value),
            NvidiaSettingIDs.SHADER_CACHE: ("shader_cache", parse_shader_cache_enabled_value),
            NvidiaSettingIDs.SHADER_CACHE_SIZE: ("shader_cache_size", parse_shader_cache_value),
            NvidiaSettingIDs.THREADED_OPTIMIZATION: ("threaded_optimization", parse_threaded_opt_value),
        }

        # Find the base profile (global settings)
        for profile in root.findall(".//Profile"):
            profile_name = profile.get("name") or profile.findtext("ProfileName", "")
            if profile_name.lower() in ("base profile", "_global_driver_profile"):
                for setting in profile.findall(".//ProfileSetting"):
                    setting_id = setting.get("id") or setting.findtext("SettingID", "")
                    try:
                        setting_id = f"0x{int(setting_id, 0):08X}"
                    except ValueError:
                        continue
                    if setting_id in setting_map:
                        name, parser = setting_map[setting_id]
                        value_elem = setting.find("SettingValue")
                        if value_elem is not None and value_elem.text:
                            try:
                                settings[name] = parser(value_elem.text)
                            except ValueError:
                                logger.debug(f"Failed to parse setting {name}: {value_elem.text}")
                if settings.get("vsync") == "on" and settings.get("vsync_tear_control") == str(NvidiaSettingValues.VSYNC_TEAR_CONTROL_ENABLE):
                    settings["vsync"] = "adaptive"
                break  # Only need the base profile

    except ET.ParseError as e:
        logger.debug(f"Failed to parse NIP file (XML error): {e}")
    except OSError as e:
        logger.debug(f"Failed to read NIP file: {e}")

    return settings


def parse_low_latency_value(value: str) -> str:
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


def parse_power_management_value(value: str) -> str:
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


def parse_vsync_value(value: str) -> str:
    """Convert VSync value to human-readable string."""
    try:
        int_val = int(value, 0)
        if int_val == NvidiaSettingValues.VSYNC_OFF:
            return "off"
        elif int_val == NvidiaSettingValues.VSYNC_ON:
            return "on"
        elif int_val == NvidiaSettingValues.VSYNC_FAST:
            return "fast"
        elif int_val == NvidiaSettingValues.VSYNC_ADAPTIVE_HALF:
            return "adaptive_half"
    except ValueError:
        pass
    return "unknown"


def parse_frame_rate_value(value: str) -> str:
    """Convert frame rate limit value to human-readable string."""
    try:
        int_val = int(value, 0)
        if int_val == 0:
            return "off"
        return str(int_val)
    except ValueError:
        pass
    return "unknown"


def parse_shader_cache_enabled_value(value: str) -> str:
    """Parse PS_SHADERDISKCACHE_ID without interpreting invalid enums as sizes."""
    try:
        return {0: "off", 1: "on"}.get(int(value, 0), "unknown")
    except ValueError:
        return "unknown"


def parse_shader_cache_value(value: str) -> str:
    """Convert PS_SHADERDISKCACHE_MAX_SIZE_ID (MiB) to a readable size."""
    try:
        int_val = int(value, 0)
        if int_val == 0:
            return "off"
        elif int_val == 0xFFFFFFFF:
            return "unlimited"
        return f"{int_val}MB"
    except ValueError:
        pass
    return "unknown"


def parse_threaded_opt_value(value: str) -> str:
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
