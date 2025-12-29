"""VRR (Variable Refresh Rate) optimization knowledge base.

Contains data and logic for G-SYNC, FreeSync, and frame rate optimization
based on Blur Busters G-SYNC 101 research.

Source: https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SyncMethod(Enum):
    """Display synchronization methods."""

    NONE = "none"  # No sync, tearing, lowest latency
    VSYNC_ONLY = "vsync_only"  # V-SYNC without VRR, high latency
    VRR = "vrr"  # G-SYNC/FreeSync, low latency tear-free
    VRR_VSYNC = "vrr_vsync"  # VRR + NVCP V-SYNC as safety net (recommended)
    FAST_SYNC = "fast_sync"  # For high FPS multiples of refresh


class FrameLimiterType(Enum):
    """Frame limiter types ranked by latency (best to worst)."""

    IN_GAME = "in_game"  # Lowest latency
    REFLEX = "reflex"  # Engine-level, auto-adjusts
    RTSS = "rtss"  # Best frametime consistency
    NVCP = "nvcp"  # Affects power management, avoid


class GraphicsAPI(Enum):
    """Graphics APIs with different latency mode support."""

    DX9 = "dx9"
    DX11 = "dx11"
    DX12 = "dx12"
    VULKAN = "vulkan"
    OPENGL = "opengl"


# APIs that support NVIDIA Low Latency Mode
LLM_SUPPORTED_APIS = {GraphicsAPI.DX9, GraphicsAPI.DX11}

# APIs that should use Reflex instead of LLM
REFLEX_PREFERRED_APIS = {GraphicsAPI.DX11, GraphicsAPI.DX12, GraphicsAPI.VULKAN}


@dataclass
class VRRConfig:
    """VRR optimization configuration."""

    gsync_enabled: bool
    vsync_nvcp: bool  # NVCP V-SYNC (safety net)
    vsync_ingame: bool  # In-game V-SYNC (should be OFF)
    low_latency_mode: str  # "off", "on", "ultra"
    fps_cap: int | None  # None = uncapped
    fps_cap_method: FrameLimiterType


# FPS cap presets for VRR (refresh_rate - 3)
VRR_FPS_CAPS: dict[int, int] = {
    60: 57,
    75: 72,
    100: 97,
    120: 117,
    144: 141,
    165: 162,
    180: 177,
    200: 197,
    240: 237,
    280: 277,
    300: 297,
    360: 357,
    390: 387,
    480: 477,
    500: 497,
}

# Common in-game FPS cap presets (for games without custom values)
COMMON_FPS_PRESETS = [30, 60, 120, 144, 165, 240, 300, 360]


def get_vrr_fps_cap(refresh_rate: int) -> int:
    """Calculate optimal FPS cap for VRR displays.

    The "3 frames below" rule: Cap FPS at minimum 3 below refresh rate
    to ensure VRR stays engaged and V-SYNC never activates.

    Args:
        refresh_rate: Monitor's maximum refresh rate in Hz.

    Returns:
        Optimal FPS cap value.
    """
    # Use preset if available
    if refresh_rate in VRR_FPS_CAPS:
        return VRR_FPS_CAPS[refresh_rate]
    # Otherwise calculate
    return refresh_rate - 3


def get_best_ingame_preset(refresh_rate: int, available_presets: list[int] | None = None) -> int | None:
    """Find best in-game FPS preset for VRR.

    For games with preset-only FPS caps (no custom values), find the
    highest preset that's still safely below the refresh rate.

    Args:
        refresh_rate: Monitor's refresh rate.
        available_presets: Game's available FPS presets. Uses common presets if None.

    Returns:
        Best preset value, or None if no suitable preset exists.
    """
    presets = available_presets or COMMON_FPS_PRESETS
    optimal = get_vrr_fps_cap(refresh_rate)

    # Find highest preset at or below optimal
    valid = [p for p in presets if p <= optimal]
    return max(valid) if valid else None


def get_limiter_recommendation(
    has_ingame_limiter: bool,
    ingame_allows_custom: bool,
    has_reflex: bool,
    refresh_rate: int,
    available_presets: list[int] | None = None,
) -> dict[str, Any]:
    """Get frame limiter recommendation based on game capabilities.

    Implements the decision tree from Blur Busters G-SYNC 101.

    Args:
        has_ingame_limiter: Game has a built-in FPS limiter.
        ingame_allows_custom: In-game limiter accepts custom values.
        has_reflex: Game supports NVIDIA Reflex.
        refresh_rate: Monitor's refresh rate.
        available_presets: Game's FPS presets if limiter is preset-only.

    Returns:
        Dictionary with limiter type and recommended cap value.
    """
    optimal_cap = get_vrr_fps_cap(refresh_rate)

    if has_ingame_limiter:
        if ingame_allows_custom:
            return {
                "limiter": FrameLimiterType.IN_GAME,
                "fps_cap": optimal_cap,
                "reason": "In-game limiter with custom values has lowest latency",
            }
        else:
            # Preset-only limiter
            best_preset = get_best_ingame_preset(refresh_rate, available_presets)
            if best_preset and (optimal_cap - best_preset) <= 10:
                return {
                    "limiter": FrameLimiterType.IN_GAME,
                    "fps_cap": best_preset,
                    "reason": f"In-game preset {best_preset} is within acceptable range of optimal {optimal_cap}",
                }
            else:
                return {
                    "limiter": FrameLimiterType.RTSS,
                    "fps_cap": optimal_cap,
                    "reason": f"In-game presets too far from optimal; use RTSS at {optimal_cap}",
                }
    elif has_reflex:
        return {
            "limiter": FrameLimiterType.REFLEX,
            "fps_cap": None,  # Reflex auto-caps
            "reason": "Reflex auto-caps appropriately with G-SYNC + V-SYNC",
        }
    else:
        return {
            "limiter": FrameLimiterType.RTSS,
            "fps_cap": optimal_cap,
            "reason": f"No in-game limiter; use RTSS at {optimal_cap}",
        }


def get_llm_recommendation(api: GraphicsAPI, has_reflex: bool) -> dict[str, Any]:
    """Get Low Latency Mode recommendation based on graphics API.

    LLM only works in DX9/DX11. DX12/Vulkan should use Reflex.

    Args:
        api: Graphics API the game uses.
        has_reflex: Whether game supports NVIDIA Reflex.

    Returns:
        Dictionary with LLM setting and explanation.
    """
    if api in LLM_SUPPORTED_APIS:
        return {
            "low_latency_mode": "on",  # Not "ultra" - it overrides manual FPS caps
            "reason": f"LLM 'On' recommended for {api.value}. Avoid 'Ultra' as it overrides manual FPS caps.",
        }
    elif api in REFLEX_PREFERRED_APIS and has_reflex:
        return {
            "low_latency_mode": "off",
            "use_reflex": True,
            "reason": f"LLM doesn't work in {api.value}. Use NVIDIA Reflex instead.",
        }
    else:
        return {
            "low_latency_mode": "off",
            "reason": f"LLM doesn't work in {api.value}. No alternative available.",
        }


def get_fighting_game_config(
    refresh_rate: int,
    accept_tearing: bool = False,
) -> dict[str, Any]:
    """Get optimal VRR config for fighting games (60Hz logic).

    Fighting games run game logic at fixed 60Hz but benefit from
    high refresh for reduced scanout/display latency.

    Args:
        refresh_rate: Monitor's refresh rate.
        accept_tearing: If True, returns competitive "no sync" config.

    Returns:
        Complete VRR configuration for fighting games.
    """
    if accept_tearing:
        return {
            "gsync": False,
            "vsync_nvcp": False,
            "vsync_ingame": False,
            "low_latency_mode": "off",
            "fps_cap": None,
            "reason": "Absolute minimum latency, tearing acceptable",
        }
    else:
        return {
            "gsync": True,
            "vsync_nvcp": True,  # Safety net, adds zero latency with proper cap
            "vsync_ingame": False,  # Always off
            "low_latency_mode": "on",
            "fps_cap": get_vrr_fps_cap(refresh_rate),
            "fps_cap_method": "ingame_preset_or_rtss",
            "reason": "Tear-free, low latency. V-SYNC acts as safety net only.",
        }


# Scanout time data for different refresh rates (at 60 FPS)
SCANOUT_TIMES_MS: dict[int, float] = {
    60: 16.6,
    120: 8.3,
    144: 6.9,
    240: 4.2,
    360: 2.8,
}

# Tested display latency for 60 FPS content
DISPLAY_LATENCY_MS: dict[int, float] = {
    60: 40.7,
    120: 16.8,
    170: 15.5,
}


def get_high_refresh_benefit(base_hz: int, target_hz: int) -> dict[str, Any]:
    """Calculate latency benefit of higher refresh rate.

    Even for 60Hz-logic games, higher refresh reduces display latency.

    Args:
        base_hz: Lower refresh rate to compare.
        target_hz: Higher refresh rate to compare.

    Returns:
        Latency reduction information.
    """
    base_scanout = SCANOUT_TIMES_MS.get(base_hz, 1000 / base_hz)
    target_scanout = SCANOUT_TIMES_MS.get(target_hz, 1000 / target_hz)

    return {
        "base_scanout_ms": base_scanout,
        "target_scanout_ms": target_scanout,
        "scanout_reduction_ms": base_scanout - target_scanout,
        "scanout_reduction_percent": ((base_scanout - target_scanout) / base_scanout) * 100,
    }
