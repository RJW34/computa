"""Nvidia setting IDs, values, and preset configurations."""

from __future__ import annotations

from typing import Any


class NvidiaSettingIDs:
    """Known Nvidia setting IDs (hex string format for NPI profile parsing).

    Verified against NVIDIA nvapi/NvApiDriverSettings.h.
    Canonical source: DRSProfileManager.SETTING_IDS in nvapi_drs.py.
    """

    LOW_LATENCY_MODE = "0x0005F543"       # Inspector ULL CPL state, not queue depth
    PRERENDERED_FRAMES = "0x007BA09E"     # PRERENDERLIMIT_ID
    ULTRA_LOW_LATENCY = "0x10835000"      # Inspector ULL enable
    POWER_MANAGEMENT = "0x1057EB71"       # PREFERRED_PSTATE_ID
    VSYNC = "0x00A879CF"                  # VSYNCMODE_ID
    MAX_FRAME_RATE = "0x10835002"         # FRL_FPS_ID
    SHADER_CACHE = "0x00198FFF"           # PS_SHADERDISKCACHE_ID (off/on)
    SHADER_CACHE_SIZE = "0x00AC8497"      # PS_SHADERDISKCACHE_MAX_SIZE_ID (MiB)
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

    LOW_LATENCY_MODE = 0x0005F543         # Inspector ULL CPL state
    PRERENDERED_FRAMES = 0x007BA09E       # PRERENDERLIMIT_ID
    ULTRA_LOW_LATENCY = 0x10835000        # Inspector ULL enable
    POWER_MANAGEMENT = 0x1057EB71         # PREFERRED_PSTATE_ID
    VSYNC = 0x00A879CF                    # VSYNCMODE_ID
    MAX_FRAME_RATE = 0x10835002           # FRL_FPS_ID
    SHADER_CACHE = 0x00198FFF             # PS_SHADERDISKCACHE_ID (off/on)
    SHADER_CACHE_SIZE = 0x00AC8497        # PS_SHADERDISKCACHE_MAX_SIZE_ID (MiB)
    THREADED_OPTIMIZATION = 0x20C1221E    # OGL_THREAD_CONTROL_ID
    TRIPLE_BUFFERING = 0x20FDD1F9         # OGL_TRIPLE_BUFFER_ID
    # VRR / G-Sync settings
    VRR_APP_OVERRIDE = 0x10A879CF         # VRR_APP_OVERRIDE_ID
    VRR_APP_OVERRIDE_REQUEST_STATE = 0x10A879AC
    VSYNC_VRR_CONTROL = 0x10A879CE        # VSYNCVRRCONTROL_ID
    VSYNC_TEAR_CONTROL = 0x005A375C       # VSYNCTEARCONTROL_ID


class NvidiaSettingValues:
    """Known values for Nvidia settings as used by NPI (Nvidia Profile Inspector).

    NIP files store raw driver DWORD values, just like NVAPI DRS. Private
    Ultra Low Latency IDs come from Inspector's CustomSettingNames.xml.
    """

    # Low Latency Mode
    LOW_LATENCY_OFF = 0x00000000
    LOW_LATENCY_ON = 0x00000001
    LOW_LATENCY_ULTRA = 0x00000002

    # Power Management Mode
    POWER_ADAPTIVE = 0x00000000
    POWER_PREFER_MAX_PERFORMANCE = 0x00000001
    POWER_OPTIMAL = 0x00000002

    # VSync
    VSYNC_OFF = 0x08416747
    VSYNC_ON = 0x47814940
    VSYNC_ADAPTIVE = 0x47814940  # Plus adaptive tear control
    VSYNC_ADAPTIVE_HALF = 0x32610244
    VSYNC_FAST = 0x18888888

    # Max Frame Rate
    FRAME_RATE_OFF = 0x00000000

    # Separate SDK enums: enabled defaults to ON; size is measured in MiB.
    SHADER_CACHE_ENABLED_DEFAULT = 0x00000001
    SHADER_CACHE_DEFAULT = 0x00004000
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

    # VSync Tear Control (native DWORDs)
    VSYNC_TEAR_CONTROL_DISABLE = 0x96861077
    VSYNC_TEAR_CONTROL_ENABLE = 0x99941284


# Preset profiles for different optimization targets
#
# IMPORTANT: Driver Low Latency Mode (LLM) is most predictable on DX9/DX11.
# NVIDIA documents DX12/Vulkan as game-controlled queueing paths for the
# original driver feature, while Reflex is the preferred path when a game
# implements it. LLM "Ultra" can interfere with manual caps - use "On" with
# a manual cap unless a profile explicitly accepts that tradeoff.
#
# NOTE ON STUTTERING: LLM reduces the render queue (pre-rendered frames).
# This CAN cause micro-stuttering on some systems, especially if CPU-bound or
# with variable frame times. If stuttering occurs:
# - Try LLM "Off" in NVCP
# - Or use NPI to set Max Pre-Rendered Frames to 2-3 (more granular control)
# These settings are hardware-dependent - test and adjust for your system.
#
# V-SYNC with G-SYNC provides tear protection. A below-refresh ceiling reduces
# ceiling backpressure; limiter precision and the presentation path still matter.
# See: https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/

NVIDIA_PRESETS: dict[str, dict[str, Any]] = {
    # === VRR PRESETS ===
    "vrr_optimal": {
        "description": "VRR (G-SYNC/FreeSync) setup - tear-free, latency-aware",
        "settings": {
            "low_latency_mode": "on",  # Not Ultra - it overrides manual FPS caps
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Tear protection; latency depends on actual presentation
            "max_frame_rate": "off",  # Use in-game or RTSS limiter instead
            "shader_cache": "on",
            "threaded_optimization": "on",
        },
        "notes": {
            "fps_cap": "Set in-game or RTSS to refresh_rate - 3 (e.g., 141 for 144Hz)",
            "api_support": "Driver LLM is most predictable on DX9/DX11. Use Reflex when available; DX12/Vulkan results depend more on the game path.",
        },
    },
    "vrr_fighting_game": {
        "description": "VRR fighting-game setup - tear-free, capped latency path",
        "settings": {
            "low_latency_mode": "on",  # NOT Ultra - Ultra overrides manual FPS caps
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Tear protection; keep a below-refresh ceiling
            "max_frame_rate": "off",  # Limiter choice belongs to the game profile
            "shader_cache": "on",
            "threaded_optimization": "on",
            "triple_buffering": "off",  # Reduces latency - not needed with G-SYNC
        },
        "notes": {
            "fps_cap": (
                "Use the limiter and below-refresh target chosen by the game profile. "
                "A 60 Hz simulation does not establish the optimal render cap: "
                "interpolation and actual frame pacing must be measured. Legacy "
                "60 Hz-multiple policies remain available for explicit comparisons."
            ),
            "fighting_games": (
                "High refresh can reduce scanout time. Render interpolation and "
                "simulation rate are separate; no cadence improvement is guaranteed."
            ),
            "api_support": "Most modern fighting games use DX12/UE5. Driver LLM is less deterministic there than classic DX11 paths; measure per game.",
            "stuttering": (
                "If experiencing micro-stutter, try low_latency_mode='off' or use NPI "
                "to set Max Pre-Rendered Frames to 2-3. Hardware-dependent - test both."
            ),
        },
    },
    "vrr_diablo4": {
        "description": "VRR for Diablo 4 with native Reflex",
        "settings": {
            "low_latency_mode": "off",  # OFF - Diablo 4 has native Reflex, don't conflict
            "power_management": "prefer_max_performance",
            # Preset default. The Diablo 4 profile overrides this to "on" so NVCP
            # VSync acts as the G-SYNC backstop (never engages below the
            # refresh-3 cap, per Blur Busters G-SYNC 101).
            "vsync": "off",
            # Max Frame Rate is set by the Diablo 4 profile via auto_vrr_fps_cap.
            # That path calls NvidiaSettingsHandler to compute refresh - 3 at apply time.
            "max_frame_rate": "off",
            "shader_cache": "on",
            "threaded_optimization": "off",  # OFF - reduces render latency
            "triple_buffering": "off",  # OFF - reduces latency
        },
        "notes": {
            "reflex": (
                "ABSO writes NVIDIA Reflex 'On' into LocalPrefs.txt via the "
                "Diablo4ConfigHandler so the in-game toggle is pre-set without "
                "launching the game. If your GPU has headroom you can upgrade "
                "to 'On + Boost' manually in Diablo 4's in-game graphics "
                "settings; ABSO keeps driver LLM off either way."
            ),
            "fps_cap": (
                "Single-limiter policy per Blur Busters G-SYNC 101: the Diablo 4 "
                "profile uses Diablo 4's in-game Foreground FPS limiter "
                "(LimitForegroundFPS=1, MaxForegroundFPS=refresh-3) as the only "
                "cap. The NVIDIA driver Max Frame Rate is intentionally off. "
                "If LocalPrefs.txt is not present at apply time the in-game cap "
                "cannot be written; the applier surfaces a notice so the user "
                "can enable NvidiaSettingsHandler.auto_vrr_fps_cap as a fallback."
            ),
            "system_requirements": (
                "HAGS=ON (per-profile default; reboot-relevant), "
                "VBS/HVCI tradeoff is opt-in, "
                "MPO enabled by default because disabling it can alter the "
                "Windows 11 VRR/compositor path on some systems."
            ),
            "hdr": (
                "Diablo 4 has excellent native HDR. The Diablo 4 HDR profile keeps "
                "HDR enabled and writes sane native HDR baselines into "
                "LocalPrefs.txt. Fine-tune HDR Paper White / Max Nits for your panel."
            ),
        },
    },
    "no_sync_fighting_game": {
        "description": "No-sync fighting-game setup - accepts tearing for a shorter presentation path",
        "settings": {
            "low_latency_mode": "on",  # 'On' by default - see stuttering note below
            "power_management": "prefer_max_performance",
            "vsync": "off",  # No sync = no sync latency
            "max_frame_rate": "off",  # Uncapped FPS
            "shader_cache": "on",
            "threaded_optimization": "on",  # On for no-sync; VRR profiles override to Off
            "triple_buffering": "off",
            "vrr_app_override": "force_off",  # Disable G-Sync for this profile
        },
        "notes": {
            "warning": (
                "Accepts screen tearing, including at high refresh rates. Compare "
                "motion clarity and latency with the game's G-SYNC lane."
            ),
            "fighting_games": (
                "Avoids sync/VRR queueing and accepts tearing. The exact latency "
                "difference versus a VRR setup depends on the game, display, and "
                "frame pacing, so ABSO does not claim a fixed millisecond gain."
            ),
            "stuttering": (
                "If experiencing micro-stutter, try low_latency_mode='off' or use NPI "
                "to set Max Pre-Rendered Frames to 2. LLM reduces queue depth which "
                "can starve the GPU on some systems. Hardware-dependent - test both."
            ),
            "threaded_opt": (
                "This driver's Threaded Optimization control is an OpenGL setting. "
                "It does not configure DirectX engine worker threads, so it must not "
                "be described as a DirectX latency or rollback optimization."
            ),
        },
    },

    # === REFLEX-ENABLED GAMES ===
    "reflex_no_sync": {
        "description": "Reflex game no-sync profile - latency-focused, tearing acceptable",
        "settings": {
            "low_latency_mode": "off",  # Reflex replaces driver LLM
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",  # Use in-game limiter only if needed
            "shader_cache": "on",
            "threaded_optimization": "on",
            "triple_buffering": "off",
            "vrr_app_override": "force_off",  # Enforce no VRR/G-SYNC for deterministic no-sync
            "vsync_tear_control": "disable",
        },
        "notes": {
            "usage": "For competitive no-sync play where lower queueing is prioritized over tear-free output.",
            "reflex": "Enable in-game NVIDIA Reflex. Boost is optional; compare latency, FPS and power use.",
            "warning": "Will tear on high-motion scenes; this is expected for no-sync mode.",
        },
    },
    "reflex_gsync": {
        "description": "Reflex + G-SYNC profile - tear-free low latency",
        "settings": {
            "low_latency_mode": "off",  # Reflex replaces driver LLM
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Driver tear-protection policy for VRR
            "max_frame_rate": "off",  # Set in-game cap to refresh - 3
            "shader_cache": "on",
            "threaded_optimization": "on",
            "triple_buffering": "off",
            "vrr_app_override": "allow",  # Enforce VRR/G-SYNC for this game
            "vsync_tear_control": "disable",
            "vsync_vrr_control": "enable",  # Coordinate VSync with VRR — safety net only below max refresh
        },
        "notes": {
            "usage": "For VRR users who want tear-free output without giving up Reflex.",
            "fps_cap": "Follow the game profile's single-limiter policy and below-refresh target. Reflex may pace FPS below that ceiling.",
            "reflex": "Enable in-game NVIDIA Reflex. Boost is optional; compare latency, FPS and power use.",
        },
    },
    "ull_gsync": {
        "description": "Driver ULL + G-SYNC profile - tear-free, driver-paced caps, in-game Reflex OFF",
        "settings": {
            "low_latency_mode": "ultra",  # Driver owns the queue; in-game Reflex stays OFF
            "power_management": "prefer_max_performance",
            "vsync": "on",  # Driver tear-protection policy for VRR
            "max_frame_rate": "off",  # Profiles layer the driver v3 cap via auto_vrr_fps_cap
            "shader_cache": "on",
            "threaded_optimization": "on",
            "triple_buffering": "off",
            "vrr_app_override": "allow",
            "vsync_tear_control": "disable",
            "vsync_vrr_control": "enable",
        },
        "notes": {
            "usage": (
                "Experimental alternative for a controlled comparison against native "
                "Reflex. No reproducible benchmark artifact establishes this preset "
                "as better for OW2 or for this machine; built-in Reflex profiles "
                "continue to prefer native Reflex."
            ),
            "reflex": "Set in-game NVIDIA Reflex to Off; driver ULL Ultra owns pacing.",
            "fps_cap": (
                "Follow the explicit profile cap policy. Driver automatic pacing "
                "can vary; a fixed percentage below refresh is not a universal rule."
            ),
        },
    },
    "reflex_game": {
        "description": "For games with NVIDIA Reflex - let Reflex handle latency",
        "settings": {
            "low_latency_mode": "off",  # CRITICAL: Reflex replaces driver LLM
            "power_management": "prefer_max_performance",
            "vsync": "off",  # Game/Reflex handles sync
            "max_frame_rate": "off",  # Use in-game limiter
            "shader_cache": "on",
            "threaded_optimization": "on",
        },
        "notes": {
            "reflex": (
                "NVIDIA Reflex is more effective than driver Low Latency Mode. "
                "Enable Reflex in-game; Boost is optional. This preset leaves driver "
                "Low Latency Mode off because Reflex controls the render queue."
            ),
            "games": (
                "CoD, Apex Legends, Valorant, Fortnite, Overwatch 2, and many others. "
                "Check in-game settings for 'NVIDIA Reflex Low Latency' option."
            ),
            "conflict_warning": (
                "NVIDIA Reflex overrides driver Ultra Low Latency functionality "
                "when both are enabled; their latency reductions are not additive."
            ),
        },
    },

    # === LEGACY PRESETS (for non-VRR or specific scenarios) ===
    "minimum_latency": {
        "description": "Legacy no-sync latency profile - accepts tearing",
        "settings": {
            "low_latency_mode": "ultra",  # Ultra is fine here since we're uncapped
            "power_management": "prefer_max_performance",
            "vsync": "off",
            "max_frame_rate": "off",
            "shader_cache": "on",
            "threaded_optimization": "on",
            "vrr_app_override": "force_off",  # Disable G-Sync per-app
        },
        "notes": {
            "warning": "Causes screen tearing. Only use if tearing is acceptable.",
            "api_support": "LLM Ultra is most predictable on DX9/DX11. DX12/Vulkan queueing is more game-controlled; measure before relying on it.",
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
            "shader_cache": "on",
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
            "shader_cache": "on",
            "threaded_optimization": "auto",
        },
    },
}
