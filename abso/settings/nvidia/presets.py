"""Nvidia setting IDs, values, and preset configurations."""

from __future__ import annotations

from typing import Any


class NvidiaSettingIDs:
    """Known Nvidia Profile Inspector setting IDs (hex format)."""

    LOW_LATENCY_MODE = "0x10834BB"
    POWER_MANAGEMENT = "0x10834E4"
    VSYNC = "0x10834F8"
    MAX_FRAME_RATE = "0x10835F7"
    SHADER_CACHE_SIZE = "0x10835FE"
    THREADED_OPTIMIZATION = "0x10835E8"
    TRIPLE_BUFFERING = "0x10834FC"
    TEXTURE_FILTERING_QUALITY = "0x1085B0E"
    ANISOTROPIC_FILTERING = "0x1085BA9"


class NvidiaSettingDecimalIDs:
    """Nvidia setting IDs in decimal format (for NIP file generation)."""

    LOW_LATENCY_MODE = 17322171  # 0x10834BB
    POWER_MANAGEMENT = 17322212  # 0x10834E4
    VSYNC = 17322232  # 0x10834F8
    MAX_FRAME_RATE = 17322487  # 0x10835F7
    SHADER_CACHE_SIZE = 17322494  # 0x10835FE
    THREADED_OPTIMIZATION = 17322472  # 0x10835E8


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
