"""VRR (Variable Refresh Rate) tuning knowledge base.

Contains data and logic for G-SYNC, FreeSync, and frame rate caps
based on Blur Busters G-SYNC 101 research.

Source: https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Any


class SyncMethod(Enum):
    """Display synchronization methods."""

    NONE = "none"  # No sync, tearing accepted
    VSYNC_ONLY = "vsync_only"  # V-SYNC without VRR, high latency
    VRR = "vrr"  # G-SYNC/FreeSync, low latency tear-free
    VRR_VSYNC = "vrr_vsync"  # VRR + NVCP V-SYNC as safety net (recommended)
    FAST_SYNC = "fast_sync"  # For high FPS multiples of refresh


class FrameLimiterType(Enum):
    """Frame limiter types ranked by latency (best to worst)."""

    IN_GAME = "in_game"  # Usually preferred when stable
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


# APIs where NVIDIA's driver Low Latency Mode is most predictable.
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


# FPS cap presets for VRR.
#
# Updated 2026-05 to scale the margin with refresh rate, matching Blur
# Busters' current G-SYNC 101 guidance. The legacy "refresh - 3" rule was
# correct for 60-200Hz displays but too tight for high-refresh: frame-time
# variance at 240Hz+ can exceed a 3-fps headroom, briefly hitting the
# refresh ceiling and letting V-SYNC engage. NVIDIA Reflex's own empirical
# safety margins (224 at 240Hz, 276 at 300Hz, 327 at 360Hz) demonstrate
# the same scaling.
#
# Formula:
#   refresh < 200    -> refresh - 3              (~1.5-5% margin)
#   200 <= refresh < 300 -> round(refresh * 0.97)  (~3% margin)
#   refresh >= 300   -> round(refresh * 0.95)    (~5% margin)
#
# Note: for Reflex-enabled games on G-SYNC, Reflex's own auto-cap is
# always more aggressive than this formula and will preempt it - so this
# value matters primarily for non-Reflex titles (Rivals 2, emulators,
# older games). See vrr.py:get_vrr_fps_cap docstring.
VRR_FPS_CAPS: dict[int, int] = {
    60: 57,
    75: 72,
    100: 97,
    120: 117,
    144: 141,
    165: 162,
    180: 177,
    200: 194,    # was 197; refresh - 3 still close, but 0.97 scaling is cleaner
    240: 233,    # was 237; 0.97 scaling, matches Reflex's 224 cap behavior
    280: 272,    # was 277
    300: 285,    # was 297; 0.95 scaling, Reflex caps at 276 anyway
    360: 342,    # was 357; 0.95 scaling, Reflex caps at 327
    390: 371,    # was 387
    480: 456,    # was 477
    500: 475,    # was 497
}

# Common in-game FPS cap presets (for games without custom values)
COMMON_FPS_PRESETS = [30, 60, 120, 144, 165, 240, 300, 360]


def get_vrr_fps_cap(refresh_rate: int | float) -> int:
    """Calculate ABSO's recommended FPS cap for VRR displays.

    Uses a refresh-scaled margin matching current Blur Busters G-SYNC 101
    guidance (updated 2026-05). The legacy "refresh - 3" rule was correct
    for 60-200Hz but too tight for high-refresh - frame-time variance at
    240Hz+ can exceed a 3-fps headroom, letting V-SYNC engage briefly.

    Scaling:
        refresh < 200       -> refresh - 3       (~1.5-5% margin)
        200 <= refresh < 300 -> refresh * 0.97   (~3% margin)
        refresh >= 300      -> refresh * 0.95    (~5% margin)

    NVIDIA Reflex (when enabled on a G-SYNC game) applies its own
    auto-cap that is always more aggressive than this (e.g. 276 at 300Hz
    vs this function's 285), so for Reflex-enabled titles the in-game /
    NVCP cap this function returns is informational - Reflex preempts it.

    Accepts float inputs (e.g. 299.99) and rounds to the nearest integer
    before lookup so fractional Hz values from CCD/pixel-clock detection
    hit the correct preset.

    Args:
        refresh_rate: Monitor's maximum refresh rate in Hz.

    Returns:
        Recommended FPS cap value.
    """
    refresh_rate = round(float(refresh_rate))
    # Use preset table when available so common refresh rates return
    # consistent, hand-reviewed values.
    if refresh_rate in VRR_FPS_CAPS:
        return VRR_FPS_CAPS[refresh_rate]
    # Otherwise compute from the scaled formula.
    if refresh_rate < 200:
        return refresh_rate - 3
    if refresh_rate < 300:
        return round(refresh_rate * 0.97)
    return round(refresh_rate * 0.95)


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
    recommended = get_vrr_fps_cap(refresh_rate)

    # Find highest preset at or below the recommended cap.
    valid = [p for p in presets if p <= recommended]
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
    recommended_cap = get_vrr_fps_cap(refresh_rate)

    if has_ingame_limiter:
        if ingame_allows_custom:
            return {
                "limiter": FrameLimiterType.IN_GAME,
                "fps_cap": recommended_cap,
                "reason": "Use the in-game limiter when it supports stable custom values.",
            }
        else:
            # Preset-only limiter
            best_preset = get_best_ingame_preset(refresh_rate, available_presets)
            if best_preset and (recommended_cap - best_preset) <= 10:
                return {
                    "limiter": FrameLimiterType.IN_GAME,
                    "fps_cap": best_preset,
                    "reason": f"In-game preset {best_preset} is within acceptable range of recommended cap {recommended_cap}",
                }
            else:
                return {
                    "limiter": FrameLimiterType.RTSS,
                    "fps_cap": recommended_cap,
                    "reason": f"In-game presets too far from recommended cap; use RTSS at {recommended_cap}",
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
            "fps_cap": recommended_cap,
            "reason": f"No in-game limiter; use RTSS at {recommended_cap}",
        }


def get_llm_recommendation(api: GraphicsAPI, has_reflex: bool) -> dict[str, Any]:
    """Get Low Latency Mode recommendation based on graphics API.

    Driver LLM is most predictable on DX9/DX11. When a game has Reflex,
    prefer Reflex instead of layering driver LLM.

    Args:
        api: Graphics API the game uses.
        has_reflex: Whether game supports NVIDIA Reflex.

    Returns:
        Dictionary with LLM setting and explanation.
    """
    if has_reflex and api in REFLEX_PREFERRED_APIS:
        return {
            "low_latency_mode": "off",
            "use_reflex": True,
            "reason": f"Use NVIDIA Reflex instead of driver LLM for {api.value}.",
        }
    elif api in LLM_SUPPORTED_APIS:
        return {
            "low_latency_mode": "on",  # Not "ultra" - it overrides manual FPS caps
            "reason": f"LLM 'On' is the conservative driver setting for {api.value}. Avoid 'Ultra' as it can override manual FPS caps.",
        }
    else:
        return {
            "low_latency_mode": "off",
            "reason": f"Driver LLM does not provide the same benefit in {api.value}. No alternative available.",
        }


def get_fighting_game_config(
    refresh_rate: int,
    accept_tearing: bool = False,
) -> dict[str, Any]:
    """Get ABSO's VRR/no-sync config for fighting games (60Hz logic).

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
            "reason": "No-sync path, tearing acceptable",
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
