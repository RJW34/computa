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


# =============================================================================
# FPS cap presets for VRR
# =============================================================================
#
# Two cap tables, both targeting "stay inside the VRR window so NVCP V-SYNC
# never has to engage". They differ in how much headroom they leave below
# refresh:
#
#   * VRR_FPS_CAPS_REFLEX (Reflex-active path) uses `refresh - 3`.
#     When NVIDIA Reflex is in the render loop, the engine's own dynamic
#     cap is the real latency control — it pins frame rate to whatever
#     keeps the render queue at the configured depth (empirically ~276 fps
#     on a 300 Hz panel). The static cap below is a *safety boundary*
#     only — its job is to be the absolute ceiling that prevents frame
#     time from crossing the refresh interval and triggering V-SYNC. A
#     3 fps headroom is sufficient because Reflex constrains frame-time
#     variance from inside the engine; widening it just throws away
#     fps the user could otherwise see in Reflex's loose moments.
#
#   * VRR_FPS_CAPS (non-Reflex path) uses a refresh-scaled margin matching
#     Blur Busters' 2026 G-SYNC 101 update — 3% under 300 Hz, 5% at 300 Hz+.
#     For games without Reflex (Rivals 2, emulators, older titles), nothing
#     constrains frame-time variance internally, so a wider headroom is
#     needed to keep VRR engaged through micro-bursts at high refresh.
#
# Formula (non-Reflex):
#   refresh < 200        -> refresh - 3              (~1.5–5% margin)
#   200 <= refresh < 300 -> round(refresh * 0.97)    (~3% margin)
#   refresh >= 300       -> round(refresh * 0.95)    (~5% margin)
#
# Formula (Reflex-active): refresh - 3 across the board.
#
# Routing: the `reflex_active` parameter on get_vrr_fps_cap controls which
# table/formula is used. The applier propagates this from the active
# profile's `requires_reflex` property (see abso/profiles/base.py).
VRR_FPS_CAPS: dict[int, int] = {
    60: 57,
    75: 72,
    100: 97,
    120: 117,
    144: 141,
    165: 162,
    180: 177,
    200: 194,    # 0.97 scaling, near refresh - 3
    240: 233,    # 0.97 scaling — conservative buffer for non-Reflex high-refresh
    280: 272,
    300: 285,    # 0.95 scaling — non-Reflex needs the headroom
    360: 342,
    390: 371,
    480: 456,
    500: 475,
}

VRR_FPS_CAPS_REFLEX: dict[int, int] = {
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
    300: 297,    # refresh - 3 — Reflex's dynamic cap is the real latency control
    360: 357,
    390: 387,
    480: 477,
    500: 497,
}

# Common in-game FPS cap presets (for games without custom values)
COMMON_FPS_PRESETS = [30, 60, 120, 144, 165, 240, 300, 360]


def get_vrr_fps_cap(
    refresh_rate: int | float,
    reflex_active: bool = False,
) -> int:
    """Calculate ABSO's recommended FPS cap for VRR displays.

    Picks one of two policies depending on whether NVIDIA Reflex is in the
    render loop for the active profile.

    **Reflex-active (refresh - 3):**
        When Reflex is engaged (typically via in-game "NVIDIA Reflex Low
        Latency: On + Boost"), the engine's dynamic cap is the real latency
        control. The static cap below is only the V-SYNC safety boundary,
        and a 3 fps headroom is enough because Reflex constrains frame-time
        variance from inside the pipeline. Widening the static cap further
        just leaves fps on the table — Reflex's dynamic cap is the lower
        bound that actually runs in practice.

    **Non-Reflex (scaled margin):**
        Without Reflex, frame-time variance can briefly poke above a tight
        headroom and engage V-SYNC, defeating the VRR-only path. A
        refresh-scaled margin (3% under 300 Hz, 5% at 300 Hz+) holds VRR
        through those micro-bursts.

    Accepts float inputs (e.g. 299.99) and rounds to the nearest integer
    before lookup so fractional Hz values from CCD / pixel-clock detection
    hit the correct preset.

    Args:
        refresh_rate: Monitor's maximum refresh rate in Hz.
        reflex_active: True when the active profile expects NVIDIA Reflex
            to be engaged (game supports it and the profile keeps driver
            LLM off so the engine owns the queue). The applier sources
            this from ``profile.requires_reflex`` so callers usually do
            not pass it directly — it is threaded through the apply /
            verify path via a private settings key.

    Returns:
        Recommended FPS cap value.
    """
    refresh_rate = round(float(refresh_rate))

    if reflex_active:
        # Reflex-active table prioritizes headroom over conservatism.
        if refresh_rate in VRR_FPS_CAPS_REFLEX:
            return VRR_FPS_CAPS_REFLEX[refresh_rate]
        # Refresh - 3 is the canonical Blur Busters rule and works across
        # the whole range when Reflex provides the dynamic ceiling.
        return max(1, refresh_rate - 3)

    # Non-Reflex path: hand-reviewed preset table first, scaled formula otherwise.
    if refresh_rate in VRR_FPS_CAPS:
        return VRR_FPS_CAPS[refresh_rate]
    if refresh_rate < 200:
        return refresh_rate - 3
    if refresh_rate < 300:
        return round(refresh_rate * 0.97)
    return round(refresh_rate * 0.95)


def get_best_ingame_preset(
    refresh_rate: int,
    available_presets: list[int] | None = None,
    reflex_active: bool = False,
) -> int | None:
    """Find best in-game FPS preset for VRR.

    For games with preset-only FPS caps (no custom values), find the
    highest preset that's still safely below the refresh rate.

    Args:
        refresh_rate: Monitor's refresh rate.
        available_presets: Game's available FPS presets. Uses common presets if None.
        reflex_active: Forwarded to ``get_vrr_fps_cap`` so the chosen preset
            tracks the Reflex-aware ceiling.

    Returns:
        Best preset value, or None if no suitable preset exists.
    """
    presets = available_presets or COMMON_FPS_PRESETS
    recommended = get_vrr_fps_cap(refresh_rate, reflex_active=reflex_active)

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
    # When the game supports Reflex, use the Reflex-aware (looser) static
    # cap as the safety boundary — Reflex's dynamic cap handles latency.
    recommended_cap = get_vrr_fps_cap(refresh_rate, reflex_active=has_reflex)

    if has_ingame_limiter:
        if ingame_allows_custom:
            return {
                "limiter": FrameLimiterType.IN_GAME,
                "fps_cap": recommended_cap,
                "reason": "Use the in-game limiter when it supports stable custom values.",
            }
        else:
            # Preset-only limiter
            best_preset = get_best_ingame_preset(
                refresh_rate, available_presets, reflex_active=has_reflex,
            )
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
