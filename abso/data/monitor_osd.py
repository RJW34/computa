"""Monitor OSD recommendation database.

Pure data module — no system calls. Contains per-monitor-model OSD
recommendations keyed by game type.

Monitors are identified by their manufacturer+model prefix extracted
from the Windows device ID string (e.g. "GSM7847" for LG 27GS95QE).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class OSDRecommendation:
    """A single monitor OSD setting recommendation."""

    setting: str   # OSD menu item name
    value: str     # Recommended value
    reason: str    # Why this matters


@dataclass(frozen=True)
class MonitorOSDProfile:
    """OSD recommendations for a specific monitor model."""

    model_pattern: str                                    # e.g. "GSM784" matches GSM7847
    display_name: str                                     # Human-readable model name
    recommendations: dict[str, list[OSDRecommendation]]   # keyed by game_type


# =============================================================================
# Monitor Database
# =============================================================================

_MONITOR_DB: list[MonitorOSDProfile] = [
    # -------------------------------------------------------------------------
    # LG 27GS95QE UltraGear OLED (240Hz, WQHD, HDR)
    # -------------------------------------------------------------------------
    MonitorOSDProfile(
        model_pattern="GSM784",
        display_name="LG 27GS95QE UltraGear OLED",
        recommendations={
            "competitive_fps": [
                OSDRecommendation(
                    setting="Picture Mode",
                    value="Game Optimizer → FPS",
                    reason="Lowest input lag processing pipeline.",
                ),
                OSDRecommendation(
                    setting="Black Stabilizer",
                    value="60-70",
                    reason="Improves shadow visibility without washing out colors.",
                ),
                OSDRecommendation(
                    setting="Response Time",
                    value="Fast",
                    reason="Fastest pixel response. 'Faster' can introduce overshoot artifacts on OLED.",
                ),
                OSDRecommendation(
                    setting="Adaptive-Sync",
                    value="On",
                    reason="Enable G-Sync Compatible for tear-free gaming.",
                ),
                OSDRecommendation(
                    setting="OLED Pixel Care → Screen Move",
                    value="Off (during sessions)",
                    reason="Pixel shift can cause micro-stutters. Re-enable after sessions.",
                ),
            ],
            "cinematic": [
                OSDRecommendation(
                    setting="Picture Mode",
                    value="Game Optimizer → Standard / Vivid",
                    reason="Better color processing for cinematic games with HDR.",
                ),
                OSDRecommendation(
                    setting="HDR Tone Mapping",
                    value="On (HGiG if available)",
                    reason="Game handles tone mapping; monitor pass-through is most accurate.",
                ),
                OSDRecommendation(
                    setting="OLED Light",
                    value="80-100",
                    reason="Higher brightness for HDR highlight impact.",
                ),
                OSDRecommendation(
                    setting="Black Stabilizer",
                    value="50 (default)",
                    reason="Preserve dark detail and atmosphere in cinematic games.",
                ),
            ],
            "emulator": [
                OSDRecommendation(
                    setting="Picture Mode",
                    value="Game Optimizer → FPS",
                    reason="Lowest input lag for frame-perfect inputs.",
                ),
                OSDRecommendation(
                    setting="Aspect Ratio",
                    value="Original (4:3 for retro)",
                    reason="Preserve original aspect ratio; avoid stretching.",
                ),
                OSDRecommendation(
                    setting="Response Time",
                    value="Fast",
                    reason="Fastest response for fixed-FPS emulation.",
                ),
            ],
            "productivity": [
                OSDRecommendation(
                    setting="Picture Mode",
                    value="sRGB or Custom (calibrated)",
                    reason="Color accuracy for development and content creation.",
                ),
                OSDRecommendation(
                    setting="OLED Light",
                    value="40-60",
                    reason="Comfortable brightness for extended coding sessions.",
                ),
                OSDRecommendation(
                    setting="OLED Pixel Care → Screen Move",
                    value="On",
                    reason="Prevent burn-in from static UI elements (taskbar, IDE chrome).",
                ),
                OSDRecommendation(
                    setting="Screen Saver",
                    value="5-10 minutes",
                    reason="Activate OLED screen saver for static content protection.",
                ),
            ],
        },
    ),

    # -------------------------------------------------------------------------
    # Dell S2719DGF (27", 1440p, 155Hz, TN/IPS)
    # -------------------------------------------------------------------------
    MonitorOSDProfile(
        model_pattern="DELD0E6",
        display_name="Dell S2719DGF",
        recommendations={
            "competitive_fps": [
                OSDRecommendation(
                    setting="Preset Modes",
                    value="FPS",
                    reason="Optimized color and response for competitive FPS.",
                ),
                OSDRecommendation(
                    setting="Response Time",
                    value="Fast",
                    reason="Good pixel response without excessive overshoot.",
                ),
                OSDRecommendation(
                    setting="FreeSync",
                    value="On",
                    reason="Enable G-Sync Compatible mode for tear-free gaming.",
                ),
            ],
        },
    ),
]


# =============================================================================
# Lookup
# =============================================================================

def get_osd_recommendations(
    monitor_id: str,
    game_type: str,
) -> tuple[str, list[OSDRecommendation]] | None:
    """Look up OSD recommendations for a monitor + game type.

    Args:
        monitor_id: Monitor device ID string from Windows (e.g. "MONITOR\\GSM7847\\...")
        game_type: One of "competitive_fps", "cinematic", "emulator", "productivity"

    Returns:
        Tuple of (display_name, recommendations) or None if no match found.
    """
    if not monitor_id:
        return None

    # Normalize for matching
    normalized = monitor_id.upper().replace("/", "\\")

    for profile in _MONITOR_DB:
        if profile.model_pattern.upper() in normalized:
            recs = profile.recommendations.get(game_type, [])
            if recs:
                return (profile.display_name, recs)
            return None

    return None
