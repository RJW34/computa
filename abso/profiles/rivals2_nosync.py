"""Rivals of Aether 2 - No Sync profile (merged offline/online lane).

Target: Everything — ranked matchmaking, unranked, training, local versus,
replays. The 2026-07 consolidation collapsed the old offline/online split;
this lane carries the online-safe tuning everywhere because SnapNet's sim is
server-authoritative and the aggressive offline-only tuning bought nothing
measurable.

Per rollback.md canonical spec:
- Optimization Class: Rollback-Safe Low Latency
- Priority: Frame pacing stability > raw latency

NVCP Settings (per-game for Rivals2-Win64-Shipping.exe):
- V-Sync: OFF (rollback is timing-sensitive, not tear-sensitive)
- G-SYNC / VRR: OFF (use the G-SYNC lanes for tear-free)
- Low Latency Mode: ON (NOT Ultra!)
- Max Frame Rate: OFF (no driver cap; the in-game limiter owns pacing)
- Threaded Optimization: AUTO (the NVAPI control is OpenGL-specific; Rivals 2
  uses D3D12, so ABSO does not present it as a DX renderer optimization)
- Power Management: Prefer Maximum Performance

In-game frame cap: largest multiple of 60 at/below refresh (300 @ 300 Hz).
Rivals 2 ticks at a fixed 60 Hz; 60-multiples hold an even frames-per-tick
cadence, and the bounded render load preserves CPU headroom for rollback
resimulation bursts.

External Tools: RTSS, frame pacing hooks DISABLED (matchmaking-safe lane).

Canonical one-line definition:
> Exclusive fullscreen + no sync + in-game 60-multiple cap + NV LLM ON (not
> Ultra) + HAGS ON + Ultimate Performance plan + no overlays
"""

from __future__ import annotations

from typing import Any, Literal

from abso.core.vrr import FIGHTING_60HZ_NOSYNC_CAP_POLICY
from abso.profiles.profile_bases import Rivals2BaseProfile, merge_settings_map


class Rivals2NoSyncProfile(Rivals2BaseProfile):
    """Rollback-safe no-sync lane for Rivals 2 (online and training).

    Single lane for ranked, unranked, and offline training — the online-safe
    tuning is carried everywhere. Prioritizes stable rollback pacing while
    keeping the leanest presentation path (no VRR, no VSync, tearing
    accepted).
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-nosync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - No Sync"

    @property
    def description(self) -> str:
        return "Rollback-safe no-sync lane for online play and training"

    @property
    def optimization_target(self) -> str:
        return "stable_online"

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Current Windows builds select D3D12RHI by default."""
        return "dx12"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Matchmaking-safe lane: no aggressive settings."""
        return False

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        """Stable, rollback-safe no-sync settings."""
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,  # Set display to max refresh rate for current resolution
            },
            "NvidiaSettingsHandler": {
                "low_latency_mode": "on",  # ON, NOT Ultra! (Ultra can cause frame pacing issues, overrides FPS caps)
                "power_management": "prefer_max_performance",
                "vsync": "off",  # OFF - rollback netcode is timing-sensitive, not tear-sensitive
                "vsync_tear_control": "disable",  # Explicit tear control off with VSync OFF
                "vrr_app_override": "force_off",  # OFF for the no-sync path
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "max_frame_rate": "off",  # No driver cap - the in-game limiter owns pacing
                "shader_cache": "unlimited",
                # NVIDIA exposes this as OGL_THREAD_CONTROL. Rivals 2's D3D12
                # renderer does not benefit from forcing the OpenGL knob.
                "threaded_optimization": "auto",
                "triple_buffering": "off",  # OFF - irrelevant without VSync
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Exclusive fullscreen no-sync path
                "vsync": False,  # In-game VSync OFF — driver handles sync
                "raw_input": True,  # Best input latency
                # In-game cap on the 60 Hz sim grid: largest multiple of 60
                # at/below refresh (300 @ 300 Hz). Even frames-per-tick
                # cadence, and the bounded render load preserves CPU headroom
                # for rollback resimulation bursts ("stability > raw latency"
                # made concrete). The driver cap stays off.
                "auto_vrr_fps_cap": True,
                "vrr_cap_policy": FIGHTING_60HZ_NOSYNC_CAP_POLICY,
                "hdr_output": False,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for the no-sync lane."""
        return [
            {
                "category": "=== NO SYNC PROFILE ===",
                "setting": "Use Case",
                "value": "Ranked, Unranked, Training, Local VS, Replays",
                "reason": (
                    "One rollback-safe lane for everything. Offline training "
                    "runs identically on the online-safe tuning."
                ),
            },
            {
                "category": "=== EXPLICIT PROHIBITIONS ===",
                "setting": "DO NOT USE",
                "value": "LLM Ultra, Fast VSync, External FPS Caps, Refresh-3 Logic",
                "reason": (
                    "These can cause rollback timing failures on high-refresh "
                    "setups, and off-grid caps micro-stutter the 60 Hz sim."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "G-SYNC / VRR",
                "value": "OFF",
                "reason": (
                    "VRR OFF keeps the no-sync scanout path simple and "
                    "deterministic. Use the G-SYNC HDR lane if you want "
                    "tear-free VRR."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "OFF",
                "reason": "OFF - rollback netcode is timing-sensitive, high-refresh tearing is negligible.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "Auto",
                "reason": (
                    "NVIDIA exposes this as an OpenGL driver control. Rivals 2 uses "
                    "D3D12, so forcing it On is not a D3D12 optimization."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": "ON (not Ultra) - Ultra can cause frame pacing issues and overrides FPS caps.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "DISABLED",
                "reason": "No driver-level cap — the in-game limiter owns pacing.",
            },
            {
                "category": "In-Game Settings",
                "setting": "V-Sync",
                "value": "OFF",
                "reason": "Native engine timing must remain authoritative.",
            },
            {
                "category": "In-Game Settings",
                "setting": "Frame Rate Cap",
                "value": "Multiple of 60 at/below refresh (auto-set: 300 @ 300Hz)",
                "reason": (
                    "Rivals 2 ticks at a fixed 60 Hz; 60-multiple caps hold an "
                    "even frames-per-tick cadence, and the bounded render load "
                    "keeps CPU headroom free for rollback resimulation bursts."
                ),
            },
            {
                "category": "External Tools",
                "setting": "RTSS / Frame Limiters",
                "value": "DISABLED",
                "reason": "External limiters cause limiter contention with rollback. Disable all.",
            },
            {
                "category": "Monitoring",
                "setting": "Overlays",
                "value": "ALLOWED (read-only)",
                "reason": "Monitoring overlays are fine, but no frame pacing intervention.",
            },
            *self._rivals2_overlay_guidance(),
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Minor frametime variance OK, no persistent VRR dropouts",
                "reason": "Rollback resync frames must not cause cascading frame loss.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: disable RTSS/external FPS caps; keep in-game "
            "V-Sync Off. ABSO sets the in-game cap to the largest multiple of "
            "60 at your refresh (e.g. 300 @ 300 Hz)."
        ]


class Rivals2NoSyncHDRProfile(Rivals2NoSyncProfile):
    """No-sync Rivals 2 lane with Windows HDR composition enabled."""

    @property
    def profile_id(self) -> str:
        return "rivals2-nosync-hdr"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe no-sync Rivals 2 lane with Windows HDR composition. "
            "Keeps no-sync rollback stability; Rivals 2 native HDR output stays off."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            self.HDR_WINDOWS_COMPOSITION_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*self._rivals2_hdr_guidance(), *super().get_in_game_settings()]
