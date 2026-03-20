"""Nvidia setting IDs, values, and preset configurations."""

from __future__ import annotations

from typing import Any


class NvidiaSettingIDs:
    """Known Nvidia setting IDs (hex string format for NPI profile parsing).

    Verified against NVIDIA nvapi/NvApiDriverSettings.h.
    Canonical source: DRSProfileManager.SETTING_IDS in nvapi_drs.py.
    """

    LOW_LATENCY_MODE = "0x007BA09E"       # PRERENDERLIMIT_ID
    POWER_MANAGEMENT = "0x1057EB71"       # PREFERRED_PSTATE_ID
    VSYNC = "0x00A879CF"                  # VSYNCMODE_ID
    MAX_FRAME_RATE = "0x10835002"         # FRL_FPS_ID
    SHADER_CACHE_SIZE = "0x00198FFF"      # PS_SHADERDISKCACHE_ID
    THREADED_OPTIMIZATION = "0x20C1221E"  # OGL_THREAD_CONTROL_ID
    TRIPLE_BUFFERING = "0x20FDD1F9"       # OGL_TRIPLE_BUFFER_ID
    TEXTURE_FILTERING_QUALITY = "0x1085B0E"  # Unchanged (not in DRS path)
    ANISOTROPIC_FILTERING = "0x1085BA9"      # Unchanged (not in DRS path)
    # VRR / G-Sync settings
    VRR_APP_OVERRIDE = "0x10A879CF"       # VRR_APP_OVERRIDE_ID
    VRR_APP_OVERRIDE_REQUEST_STATE = "0x10A879AC"
    VSYNC_VRR_CONTROL = "0x10A879CE"      # VSYNCVRRCONTROL_ID
    VSYNC_TEAR_CONTROL = "0x005A375C"     # VSYNCTEARCONTROL_ID


class NvidiaSettingDecimalIDs:
    """Nvidia setting IDs in decimal format (for NIP file generation).

    Verified against NVIDIA nvapi/NvApiDriverSettings.h.
    """

    LOW_LATENCY_MODE = 0x007BA09E         # PRERENDERLIMIT_ID
    POWER_MANAGEMENT = 0x1057EB71         # PREFERRED_PSTATE_ID
    VSYNC = 0x00A879CF                    # VSYNCMODE_ID
    MAX_FRAME_RATE = 0x10835002           # FRL_FPS_ID
    SHADER_CACHE_SIZE = 0x00198FFF        # PS_SHADERDISKCACHE_ID
    THREADED_OPTIMIZATION = 0x20C1221E    # OGL_THREAD_CONTROL_ID
    TRIPLE_BUFFERING = 0x20FDD1F9         # OGL_TRIPLE_BUFFER_ID
    # VRR / G-Sync settings
    VRR_APP_OVERRIDE = 0x10A879CF         # VRR_APP_OVERRIDE_ID
    VRR_APP_OVERRIDE_REQUEST_STATE = 0x10A879AC
    VSYNC_VRR_CONTROL = 0x10A879CE        # VSYNCVRRCONTROL_ID
    VSYNC_TEAR_CONTROL = 0x005A375C       # VSYNCTEARCONTROL_ID


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

    # Triple Buffering
    TRIPLE_BUFFERING_OFF = 0x00000000
    TRIPLE_BUFFERING_ON = 0x00000001

    # VRR / G-Sync App Override
    # Controls per-application G-Sync behavior
    VRR_APP_OVERRIDE_ALLOW = 0x00000000  # Enable G-Sync (default)
    VRR_APP_OVERRIDE_FORCE_OFF = 0x00000001  # Force G-Sync OFF
    VRR_APP_OVERRIDE_DISALLOW = 0x00000002  # Disallow VRR
    VRR_APP_OVERRIDE_ULMB = 0x00000003  # Use ULMB instead
    VRR_APP_OVERRIDE_FIXED_REFRESH = 0x00000004  # Fixed refresh rate

    # VSync Tear Control
    VSYNC_TEAR_CONTROL_DISABLE = 0x00000000
    VSYNC_TEAR_CONTROL_ENABLE = 0x00000001


# Preset profiles for different optimization targets
#
# IMPORTANT: Low Latency Mode (LLM) works in DX9/DX11 and modern NVIDIA
# drivers also support DX12. Vulkan still does not expose the same benefit.
# If a game has NVIDIA Reflex, use Reflex instead of layering driver LLM.
# LLM "Ultra" auto-caps FPS and overrides manual caps - use "On" with manual cap.
#
# NOTE ON STUTTERING: LLM reduces the render queue (pre-rendered frames).
# This CAN cause micro-stuttering on some systems, especially if CPU-bound or
# with variable frame times. If stuttering occurs:
# - Try LLM "Off" in NVCP
# - Or use NPI to set Max Pre-Rendered Frames to 2-3 (more granular control)
# These settings are hardware-dependent - test and adjust for your system.
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
            "api_support": "LLM works in DX9/DX11/DX12. Use Reflex when available; Vulkan still relies on the game/driver path instead.",
        },
    },
    "vrr_fighting_game": {
        "description": "Optimized for fighting games with VRR - tear-free, near-minimum latency",
        "settings": {
            "low_latency_mode": "on",  # NOT Ultra - Ultra overrides manual FPS caps
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Safety net - never activates with proper FPS cap
            "max_frame_rate": "off",  # Use in-game limiter (lower latency than NVCP/RTSS)
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
            "triple_buffering": "off",  # Reduces latency - not needed with G-SYNC
        },
        "notes": {
            "fps_cap": (
                "Use in-game limiter at highest preset below refresh rate. "
                "For 300Hz: use 240 in-game cap. In-game limiters have ~0.5-1 frame "
                "lower latency than RTSS/NVCP, which outweighs scanout benefits."
            ),
            "fighting_games": (
                "60Hz-logic games still benefit from high refresh (reduced scanout latency). "
                "300Hz and 240Hz both divide evenly into 60fps - no cadence judder."
            ),
            "api_support": "Most modern fighting games use DX12/UE5. LLM can still help, but results vary more than classic DX11 paths and Rivals 2 still lacks Reflex.",
            "stuttering": (
                "If experiencing micro-stutter, try low_latency_mode='off' or use NPI "
                "to set Max Pre-Rendered Frames to 2-3. Hardware-dependent - test both."
            ),
        },
    },
    "vrr_diablo4": {
        "description": "VRR for Diablo 4 with native Reflex - ultra low latency ARPG",
        "settings": {
            "low_latency_mode": "off",  # OFF - Diablo 4 has native Reflex, don't conflict
            "power_management": "prefer_max_performance",
            "vsync": "off",  # OFF - G-Sync handles sync
            "max_frame_rate": "off",  # Use in-game limiter (297 for 300Hz)
            "shader_cache": "unlimited",
            "threaded_optimization": "off",  # OFF - reduces render latency
            "triple_buffering": "off",  # OFF - reduces latency
        },
        "notes": {
            "reflex": (
                "Enable NVIDIA Reflex 'On + Boost' in Diablo 4 graphics settings. "
                "Native Reflex is more effective than driver Low Latency Mode."
            ),
            "fps_cap": (
                "Set in-game Max Foreground FPS to refresh_rate - 3 (e.g., 297 for 300Hz). "
                "In-game limiter has lower latency than NVCP/RTSS limiters."
            ),
            "system_requirements": (
                "HAGS=ON, VBS=OFF, Windows VRR=OFF, MPO=ENABLED. "
                "Uninstall GeForce Experience for lowest overhead."
            ),
            "hdr": (
                "Diablo 4 has excellent native HDR. Keep HDR enabled on OLED. "
                "Set HDR Paper White Nits and Max Nits appropriately for your display."
            ),
        },
    },
    "no_sync_fighting_game": {
        "description": "Absolute minimum latency for fighting games - accepts tearing",
        "settings": {
            "low_latency_mode": "on",  # 'On' by default - see stuttering note below
            "power_management": "prefer_max_performance",
            "vsync": "off",  # No sync = no sync latency
            "max_frame_rate": "off",  # Uncapped FPS
            "shader_cache": "unlimited",
            "threaded_optimization": "on",  # On for no-sync; VRR profiles override to Off
            "triple_buffering": "off",
            "vrr_app_override": "force_off",  # Disable G-Sync for this profile
        },
        "notes": {
            "warning": (
                "Causes screen tearing. At 300Hz+, tearing is less perceptible "
                "(tear lines move faster). Use for tournament/LAN settings only."
            ),
            "fighting_games": (
                "Absolute minimum click-to-pixel latency. Saves ~1-3ms over VRR setup. "
                "Worth it only if you can tolerate tearing and need every millisecond."
            ),
            "stuttering": (
                "If experiencing micro-stutter, try low_latency_mode='off' or use NPI "
                "to set Max Pre-Rendered Frames to 2. LLM reduces queue depth which "
                "can starve the GPU on some systems. Hardware-dependent - test both."
            ),
            "threaded_opt": (
                "Threaded Optimization ON is default for this preset. For VRR/G-Sync "
                "setups (vrr_ue5_fighting_game, vrr_diablo4), it's set to OFF for "
                "lower render latency. Test both settings for your hardware."
            ),
        },
    },

    # === REFLEX-ENABLED GAMES ===
    "reflex_no_sync": {
        "description": "Reflex game no-sync profile - minimum latency, tearing acceptable",
        "settings": {
            "low_latency_mode": "off",  # Reflex replaces driver LLM
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",  # Use in-game limiter only if needed
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
            "triple_buffering": "off",
            "vrr_app_override": "force_off",  # Enforce no VRR/G-SYNC for deterministic no-sync
            "vsync_tear_control": "disable",
        },
        "notes": {
            "usage": "For competitive no-sync play where minimum latency is prioritized over tearing.",
            "reflex": "Set in-game NVIDIA Reflex to On + Boost.",
            "warning": "Will tear on high-motion scenes; this is expected for no-sync mode.",
        },
    },
    "reflex_gsync": {
        "description": "Reflex + G-SYNC profile - tear-free low latency",
        "settings": {
            "low_latency_mode": "off",  # Reflex replaces driver LLM
            "power_management": "prefer_max_performance",
            "vsync": "on",  # NVCP safety net for VRR
            "max_frame_rate": "off",  # Set in-game cap to refresh - 3
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
            "triple_buffering": "off",
            "vrr_app_override": "allow",  # Enforce VRR/G-SYNC for this game
            "vsync_tear_control": "disable",
            "vsync_vrr_control": "enable",  # Coordinate VSync with VRR — safety net only below max refresh
        },
        "notes": {
            "usage": "For VRR users who want tear-free output without giving up Reflex.",
            "fps_cap": "Set in-game FPS cap to refresh_rate - 3 to keep VSync as safety net only.",
            "reflex": "Set in-game NVIDIA Reflex to On + Boost.",
        },
    },
    "reflex_game": {
        "description": "For games with NVIDIA Reflex - let Reflex handle latency",
        "settings": {
            "low_latency_mode": "off",  # CRITICAL: Reflex replaces driver LLM
            "power_management": "prefer_max_performance",
            "vsync": "off",  # Game/Reflex handles sync
            "max_frame_rate": "off",  # Use in-game limiter
            "shader_cache": "unlimited",
            "threaded_optimization": "on",
        },
        "notes": {
            "reflex": (
                "NVIDIA Reflex is more effective than driver Low Latency Mode. "
                "Enable Reflex 'On + Boost' in-game. Do NOT combine with driver LLM."
            ),
            "games": (
                "CoD, Apex Legends, Valorant, Fortnite, Overwatch 2, and many others. "
                "Check in-game settings for 'NVIDIA Reflex Low Latency' option."
            ),
            "conflict_warning": (
                "Using LLM with Reflex can cause stuttering and actually increase "
                "latency. Always use Reflex alone when available."
            ),
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
