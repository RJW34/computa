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
    """Frame limiter types; relative latency depends on the implementation."""

    IN_GAME = "in_game"  # Usually preferred when stable
    REFLEX = "reflex"  # Engine-level, auto-adjusts
    RTSS = "rtss"  # Best frametime consistency
    NVCP = "nvcp"  # Driver-level limiter fallback


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
# ABSO's static FPS cap exists to be the V-SYNC safety boundary: when G-SYNC
# is engaged and NVCP V-SYNC is on as a tear-prevention safety net, an
# uncapped frame rate that briefly exceeds the refresh interval will trigger
# V-SYNC and add scanout latency for those frames. The cap prevents that.
#
# The default formula is `refresh - 3`, the long-standing Blur Busters
# G-SYNC 101 convention. ABSO previously experimented with a wider
# refresh-scaled margin (3% under 300 Hz, 5% at 300 Hz+, plus a separate
# Reflex-aware table) but that policy was synthesized from secondhand
# references rather than a fetched primary source. Adversarial deep
# research in 2026-05 could not confirm any specific scaling formula
# from a primary Blur Busters or NVIDIA citation, so ABSO reverts to the
# historical refresh - 3 convention as the single source of truth.
#
# Practical implication: the cap is *not* the latency control. NVIDIA
# Reflex (when engaged in-game) provides dynamic pacing that may bind
# below this static ceiling; that's expected and desirable. The cap just
# provides headroom; limiter precision and the presentation path still matter.
#
# Users observing FPS far below the cap should run the empirical isolation
# test (each Reflex mode in turn, see docs/AGENT_PROTOCOL.md) to identify
# what is actually binding — Reflex, CPU, GPU, or an in-game limit. The
# cap value itself is rarely the answer.
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

OW2_REFLEX_GSYNC_CAP_POLICY = "ow2_reflex_gsync"

# Optional Rivals 2 render-cap heuristic: snap to a 60 Hz simulation grid.
# Simulation rate alone does not prove a render cap is optimal; rendering can
# interpolate between ticks. Retained for compatibility pending controlled
# comparisons against refresh - 3 on the user's actual display/game build.
FIGHTING_SIM_RATE_HZ = 60
FIGHTING_60HZ_VRR_CAP_POLICY = "fighting_60hz_vrr"
FIGHTING_60HZ_NOSYNC_CAP_POLICY = "fighting_60hz_nosync"

REFLEX_GSYNC_FRAME_TIME_MARGIN_MS = 0.29

REFLEX_GSYNC_FPS_CAPS: dict[int, int] = {
    144: 138,
    165: 157,
    240: 224,
    300: 276,
    360: 326,
    480: 421,
}

# Common in-game FPS cap presets (for games without custom values)
COMMON_FPS_PRESETS = [30, 60, 120, 144, 165, 240, 300, 360]


def get_vrr_fps_cap(
    refresh_rate: int | float,
    reflex_active: bool | None = None,  # noqa: ARG001 — kept for callsite stability
) -> int:
    """Calculate ABSO's static V-SYNC-safety-boundary FPS cap for VRR.

    Returns ``refresh - 3`` (the historical Blur Busters G-SYNC 101
    convention), looked up from the ``VRR_FPS_CAPS`` preset table for
    common rates or computed inline otherwise. Float inputs (e.g. 299.99
    from CCD / pixel-clock detection) are rounded before lookup.

    The cap is intentionally the same regardless of whether NVIDIA Reflex
    is in the render loop. Reflex is a latency control (dynamic CPU
    pacing); the static cap is a V-SYNC safety boundary. They operate on
    different mechanisms — there is no documented primary-source basis
    for ABSO to apply a different static cap based on Reflex presence.

    Args:
        refresh_rate: Monitor's maximum refresh rate in Hz.
        reflex_active: Accepted for callsite stability; currently ignored.
            Previously used to select between two cap tables under an
            unverified scaling rationale. Now both Reflex and non-Reflex
            profiles use the same ``refresh - 3`` cap.

    Returns:
        Recommended FPS cap value.
    """
    refresh_rate = round(float(refresh_rate))
    if refresh_rate in VRR_FPS_CAPS:
        return VRR_FPS_CAPS[refresh_rate]
    return max(1, refresh_rate - 3)


def get_reflex_gsync_fps_cap(refresh_rate: int | float) -> int:
    """Return the historical heuristic cap, retained for explicit custom policies.

    This is not a documented NVIDIA formula or the built-in OW2 policy.
    The historical Reflex/ULLM G-SYNC approximation used a wider margin than the
    static ``refresh - 3`` safety cap. Known public examples include roughly
    157 FPS at 165 Hz and 224 FPS at 240 Hz; the historical 300 Hz estimate was
    276 FPS. The fallback keeps the same ~0.29 ms frame-time margin for less
    common refresh rates.
    """
    rounded_refresh = round(float(refresh_rate))
    if rounded_refresh in REFLEX_GSYNC_FPS_CAPS:
        return REFLEX_GSYNC_FPS_CAPS[rounded_refresh]

    frame_time_ms = (1000.0 / rounded_refresh) + REFLEX_GSYNC_FRAME_TIME_MARGIN_MS
    return max(1, min(rounded_refresh - 1, round(1000.0 / frame_time_ms)))


def get_fighting_60hz_vrr_cap(refresh_rate: int | float) -> int:
    """VRR cap for fixed-60Hz-sim games: largest multiple of 60 <= refresh - 3.

    Keeps the cap below refresh so G-SYNC stays engaged and the NVCP V-SYNC
    safety net never trips, while landing on the 60 Hz sim grid for an even
    frames-per-tick cadence (240 @ 300 Hz, 180 @ 240 Hz, 120 @ 144 Hz).
    Falls back to the generic ``refresh - 3`` cap when no multiple of 60
    fits under the margin (i.e. 60 Hz panels).
    """
    rounded = round(float(refresh_rate))
    snapped = ((rounded - 3) // FIGHTING_SIM_RATE_HZ) * FIGHTING_SIM_RATE_HZ
    if snapped >= FIGHTING_SIM_RATE_HZ:
        return snapped
    return get_vrr_fps_cap(rounded)


def get_fighting_60hz_nosync_cap(refresh_rate: int | float) -> int:
    """No-sync cap for fixed-60Hz-sim games: largest multiple of 60 <= refresh.

    Without G-SYNC/V-SYNC in the path there is no below-refresh margin to
    protect; the cap exists to hold the 60 Hz sim-grid cadence and keep
    render load bounded (preserving CPU headroom for rollback
    resimulation bursts) instead of rendering unbounded duplicate frames.
    """
    rounded = round(float(refresh_rate))
    snapped = (rounded // FIGHTING_SIM_RATE_HZ) * FIGHTING_SIM_RATE_HZ
    return max(FIGHTING_SIM_RATE_HZ, snapped)


def get_vrr_fps_cap_for_policy(
    refresh_rate: int | float,
    policy: str | None = None,
) -> int:
    """Resolve a profile-requested VRR cap policy to a concrete FPS cap."""
    normalized = str(policy or "").strip().lower().replace("-", "_")
    if not normalized or normalized in {"static", "refresh_minus_3", "vrr"}:
        return get_vrr_fps_cap(refresh_rate)
    if normalized in {OW2_REFLEX_GSYNC_CAP_POLICY, "reflex_gsync"}:
        return get_reflex_gsync_fps_cap(refresh_rate)
    if normalized in {FIGHTING_60HZ_VRR_CAP_POLICY, "fighting_60hz"}:
        return get_fighting_60hz_vrr_cap(refresh_rate)
    if normalized == FIGHTING_60HZ_NOSYNC_CAP_POLICY:
        return get_fighting_60hz_nosync_cap(refresh_rate)
    raise ValueError(f"Unknown VRR FPS cap policy: {policy!r}")


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
            stays callsite-compatible with older profile logic.

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
    # Reflex is a dynamic latency control, not a separate static cap policy.
    # The argument is still threaded for compatibility, but get_vrr_fps_cap
    # intentionally uses the same V-SYNC safety boundary either way.
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

def get_high_refresh_benefit(base_hz: int, target_hz: int) -> dict[str, Any]:
    """Calculate the ideal scanout-interval difference of two refresh rates.

    This arithmetic is not an end-to-end latency measurement. Actual timing
    depends on presentation, blanking, panel scanout, and pixel response.

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
