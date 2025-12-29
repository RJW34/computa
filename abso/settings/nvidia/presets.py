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
    # VRR / G-Sync settings
    VRR_APP_OVERRIDE = "0x10A879CF"  # Per-app G-Sync control
    VRR_APP_OVERRIDE_REQUEST_STATE = "0x10A879AC"
    VSYNC_VRR_CONTROL = "0x10A879CE"  # Variable Refresh Rate control


class NvidiaSettingDecimalIDs:
    """Nvidia setting IDs in decimal format (for NIP file generation)."""

    LOW_LATENCY_MODE = 17322171  # 0x10834BB
    POWER_MANAGEMENT = 17322212  # 0x10834E4
    VSYNC = 17322232  # 0x10834F8
    MAX_FRAME_RATE = 17322487  # 0x10835F7
    SHADER_CACHE_SIZE = 17322494  # 0x10835FE
    THREADED_OPTIMIZATION = 17322472  # 0x10835E8
    # VRR / G-Sync settings
    VRR_APP_OVERRIDE = 279542223  # 0x10A879CF - Per-app G-Sync control
    VRR_APP_OVERRIDE_REQUEST_STATE = 279542188  # 0x10A879AC
    VSYNC_VRR_CONTROL = 279542222  # 0x10A879CE


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

    # VRR / G-Sync App Override
    # Controls per-application G-Sync behavior
    VRR_APP_OVERRIDE_ALLOW = 0x00000000  # Enable G-Sync (default)
    VRR_APP_OVERRIDE_FORCE_OFF = 0x00000001  # Force G-Sync OFF
    VRR_APP_OVERRIDE_DISALLOW = 0x00000002  # Disallow VRR
    VRR_APP_OVERRIDE_ULMB = 0x00000003  # Use ULMB instead
    VRR_APP_OVERRIDE_FIXED_REFRESH = 0x00000004  # Fixed refresh rate


# Preset profiles for different optimization targets
#
# IMPORTANT: Low Latency Mode (LLM) only works in DX9/DX11.
# For DX12/Vulkan games, use NVIDIA Reflex instead.
# LLM "Ultra" auto-caps FPS and overrides manual caps - use "On" with manual cap.
#
# V-SYNC with G-SYNC: NVCP V-SYNC "On" acts as a safety net, not active latency.
# With FPS capped at refresh_rate - 3, V-SYNC never engages.
# See: https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/

NVIDIA_PRESETS: dict[str, dict[str, Any]] = {
    # === VRR-OPTIMIZED PRESETS (RECOMMENDED) ===
    "vrr_optimal": {
        "description": "Optimal VRR (G-SYNC/FreeSync) setup - tear-free, low latency",
        "settings": {
            "low_latency_mode": "on",  # Not Ultra - it overrides manual FPS caps
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Safety net for VRR - adds zero latency with proper FPS cap
            "max_frame_rate": "off",  # Use in-game or RTSS limiter instead
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
        },
        "notes": {
            "fps_cap": "Set in-game or RTSS to refresh_rate - 3 (e.g., 141 for 144Hz)",
            "api_support": "LLM works in DX9/DX11 only. Use Reflex for DX12/Vulkan.",
        },
    },
    "vrr_fighting_game": {
        "description": "Optimized for fighting games with VRR - 60Hz logic benefits from high refresh",
        "settings": {
            "low_latency_mode": "on",
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Safety net
            "max_frame_rate": "off",
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
        },
        "notes": {
            "fps_cap": "Use in-game preset closest to (but below) refresh rate, or RTSS at refresh - 3",
            "fighting_games": "Even 60Hz-logic games benefit from high refresh (reduced scanout latency)",
            "api_support": "Most modern fighting games use DX12/UE5 - prefer Reflex over LLM",
        },
    },

    # === LEGACY PRESETS (for non-VRR or specific scenarios) ===
    "minimum_latency": {
        "description": "Absolute minimum latency - accepts tearing, no sync",
        "settings": {
            "low_latency_mode": "ultra",  # Ultra is fine here since we're uncapped
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
            "vrr_app_override": "force_off",  # Disable G-Sync per-app
        },
        "notes": {
            "warning": "Causes screen tearing. Only use if tearing is acceptable.",
            "api_support": "LLM Ultra only works in DX9/DX11.",
            "gsync": "G-Sync disabled for this profile to eliminate VRR overhead.",
        },
    },
    "low_latency_high_fps": {
        "description": "Low latency with stable high FPS (legacy, prefer vrr_optimal)",
        "settings": {
            "low_latency_mode": "on",
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
        },
        "notes": {
            "warning": "V-SYNC off may cause tearing. Consider vrr_optimal for G-SYNC setups.",
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
