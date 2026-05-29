"""Monitor OSD recommendation database.

Pure data module — no system calls. Contains per-monitor-model OSD
recommendations keyed by game type.

Monitors are identified by their manufacturer+model prefix extracted
from the Windows device ID string (e.g. "GSM7847" for LG 27GS95QE).

Data is loaded from YAML files (bundled + user override at ~/.abso/monitor_osd.yaml),
with a built-in Python fallback if YAML loading fails.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class OSDRecommendation:
    """A single monitor OSD setting recommendation.

    Optional metadata lets the lookup filter out recommendations that the
    user's active context contradicts:

    * ``applies_to_sync_modes`` — restrict to {"on", "off"}; when empty/None
      the recommendation is shown regardless of the profile's sync mode.
    * ``setting_kind`` — coarse tag for the kind of OSD knob this is
      (``"vibrance"``, ``"icc"``, ``"sync"``, ``"other"``). Lets the color
      handler suppress vibrance/ICC hints when the user has opted out of
      ABSO managing those.
    """

    setting: str   # OSD menu item name
    value: str     # Recommended value
    reason: str    # Why this matters
    applies_to_sync_modes: tuple[str, ...] = ()
    setting_kind: str = "other"


@dataclass(frozen=True)
class MonitorOSDProfile:
    """OSD recommendations for a specific monitor model."""

    model_pattern: str                                    # e.g. "GSM784" matches GSM7847
    display_name: str                                     # Human-readable model name
    recommendations: dict[str, list[OSDRecommendation]]   # keyed by game_type


# =============================================================================
# Built-in Monitor Database (fallback if YAML loading fails)
# =============================================================================

_BUILTIN_MONITOR_DB: list[MonitorOSDProfile] = [
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
                    setting="Color Gamut (SDR only)",
                    value="Use 'sRGB' picture mode, or stay on 'Game Optimizer' and lower digital vibrance",
                    reason="OLED native gamut is DCI-P3. SDR games output sRGB; the wider gamut causes oversaturation. Switch to 'sRGB' mode for accurate colors (some settings restricted), or compensate via digital vibrance if you need Game Optimizer's lowest input lag.",
                    setting_kind="vibrance",
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
                    applies_to_sync_modes=("on",),
                    setting_kind="sync",
                ),
                OSDRecommendation(
                    setting="Adaptive-Sync",
                    value="Off",
                    reason="No-sync competitive profiles want strict OFF to avoid VRR scan-out adding input lag.",
                    applies_to_sync_modes=("off",),
                    setting_kind="sync",
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
                    reason="Tuned color and response preset for competitive FPS.",
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
                    applies_to_sync_modes=("on",),
                    setting_kind="sync",
                ),
                OSDRecommendation(
                    setting="FreeSync",
                    value="Off",
                    reason="No-sync competitive profiles want strict OFF to avoid VRR scan-out adding input lag.",
                    applies_to_sync_modes=("off",),
                    setting_kind="sync",
                ),
            ],
        },
    ),
]


# =============================================================================
# YAML Loading
# =============================================================================

_MONITOR_DB: list[MonitorOSDProfile] | None = None


def _parse_monitor_entry(data: dict) -> MonitorOSDProfile:
    """Convert a YAML monitor dict into a MonitorOSDProfile."""
    recommendations: dict[str, list[OSDRecommendation]] = {}
    for game_type, recs in data.get("recommendations", {}).items():
        parsed: list[OSDRecommendation] = []
        for r in recs:
            raw_sync = r.get("applies_to_sync_modes") or ()
            if isinstance(raw_sync, str):
                raw_sync = (raw_sync,)
            sync_modes = tuple(
                str(s).lower() for s in raw_sync
                if str(s).lower() in {"on", "off"}
            )
            parsed.append(
                OSDRecommendation(
                    setting=r["setting"],
                    value=r["value"],
                    reason=r["reason"],
                    applies_to_sync_modes=sync_modes,
                    setting_kind=str(r.get("setting_kind", "other")).lower(),
                )
            )
        recommendations[game_type] = parsed
    return MonitorOSDProfile(
        model_pattern=data["model_pattern"],
        display_name=data["display_name"],
        recommendations=recommendations,
    )


def _load_monitor_db() -> list[MonitorOSDProfile]:
    """Load monitor OSD database from YAML files.

    Loads from bundled YAML first, then merges user YAML (~/.abso/monitor_osd.yaml).
    User entries override bundled entries with matching model_pattern.
    Falls back to built-in Python data if YAML loading fails.
    """
    try:
        import yaml
    except ImportError:
        logger.warning("PyYAML not installed; using built-in monitor OSD data.")
        return list(_BUILTIN_MONITOR_DB)

    bundled_yaml = Path(__file__).parent / "monitor_osd.yaml"
    user_yaml = Path.home() / ".abso" / "monitor_osd.yaml"

    profiles: list[MonitorOSDProfile] = []
    seen_patterns: set[str] = set()

    # Load user YAML first (takes priority)
    for yaml_path in [user_yaml, bundled_yaml]:
        if yaml_path.exists():
            try:
                data = yaml.safe_load(yaml_path.read_text(encoding="utf-8"))
                for monitor in data.get("monitors", []):
                    pattern = monitor["model_pattern"]
                    if pattern not in seen_patterns:
                        profiles.append(_parse_monitor_entry(monitor))
                        seen_patterns.add(pattern)
            except Exception as e:
                logger.warning(f"Failed to load monitor OSD YAML from {yaml_path}: {e}")

    return profiles or list(_BUILTIN_MONITOR_DB)


def _get_monitor_db() -> list[MonitorOSDProfile]:
    """Return the monitor database, lazily loading from YAML on first access."""
    global _MONITOR_DB
    if _MONITOR_DB is None:
        _MONITOR_DB = _load_monitor_db()
    return _MONITOR_DB


# =============================================================================
# Lookup
# =============================================================================

def get_osd_recommendations(
    monitor_id: str,
    game_type: str,
    sync_mode: str | None = None,
    suppressed_kinds: tuple[str, ...] = (),
) -> tuple[str, list[OSDRecommendation]] | None:
    """Look up OSD recommendations for a monitor + game type.

    Args:
        monitor_id: Monitor device ID string from Windows (e.g. "MONITOR\\GSM7847\\...")
        game_type: One of "competitive_fps", "cinematic", "emulator", "productivity"
        sync_mode: Active profile sync mode — "on" / "off" / "agnostic" / None.
            Recommendations tagged with ``applies_to_sync_modes`` are filtered
            to entries that match this value. Untagged entries pass through.
        suppressed_kinds: Iterable of ``setting_kind`` values to drop entirely.
            Used by the color handler to hide "lower digital vibrance" OSD
            hints when the user has set ``color.manage_vibrance: false`` in
            their config (because ABSO will never touch DV in that case, and
            telling them to does not match what ABSO actually does).

    Returns:
        Tuple of (display_name, recommendations) or None if no match found.
        Returns None if filtering removed every recommendation for this
        combination (since showing an empty list to the user is noise).
    """
    if not monitor_id:
        return None

    normalized_sync = (sync_mode or "").lower()
    suppressed = {str(k).lower() for k in suppressed_kinds}

    # Normalize for matching
    normalized = monitor_id.upper().replace("/", "\\")

    for profile in _get_monitor_db():
        if profile.model_pattern.upper() in normalized:
            recs = profile.recommendations.get(game_type, [])
            if not recs:
                return None
            filtered: list[OSDRecommendation] = []
            for rec in recs:
                if rec.setting_kind in suppressed:
                    continue
                # Sync-mode filtering applies only when the caller actually told
                # us the active sync mode. With an empty/None sync_mode, we keep
                # tagged entries (caller may want to display every variant; e.g.
                # docs UIs, legacy callers).
                if (
                    rec.applies_to_sync_modes
                    and normalized_sync in ("on", "off")
                    and normalized_sync not in rec.applies_to_sync_modes
                ):
                    continue
                filtered.append(rec)
            if filtered:
                return (profile.display_name, filtered)
            return None

    return None
