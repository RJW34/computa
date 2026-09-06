"""Rivals of Aether 2 G-SYNC / VRR profiles (merged offline/online lanes).

Three variants:
- Rivals2GSyncProfile: SDR G-SYNC (tear-free, rollback-safe)
- Rivals2GSyncHDRProfile: + Windows HDR composition
- Rivals2GSyncHDRCaptureProfile: + borderless capture-safe path (OBS/Medal)

The 2026-07 consolidation collapsed the old offline/online split; every lane
carries the online-safe tuning (SnapNet's sim is server-authoritative, so the
aggressive offline-only tuning bought nothing measurable).

Key difference from OW2 G-SYNC: Rivals 2 does NOT have NVIDIA Reflex,
so we use the ``vrr_fighting_game`` preset (LLM "on") instead of
``reflex_gsync`` (LLM "off"). Caps snap to the 60 Hz sim grid via the
``fighting_60hz_vrr`` policy (240 @ 300 Hz).
"""

from __future__ import annotations

from typing import Any

from abso.core.vrr import FIGHTING_60HZ_VRR_CAP_POLICY
from abso.profiles.profile_bases import Rivals2BaseProfile, merge_settings_map

# Shared payload delta for the capture-safe sibling: swap the strict
# exclusive-fullscreen + fullscreen-only VRR contract for the borderless
# windowed G-SYNC flip path (same mechanism the OW2 capture lanes use).
# Switching global_vrr_mode off "fullscreen_only" also drops the
# overlay-free display-path gate that blocks apply while OBS runs.
_CAPTURE_WINDOWED_VRR_OVERRIDES: dict[str, dict[str, Any]] = {
    "WindowsSettingsHandler": {
        "windowed_optimizations": True,
        "vrr_optimize": True,
    },
    "NvidiaSettingsHandler": {
        "global_vrr_mode": "fullscreen_and_windowed",
    },
    "Rivals2ConfigHandler": {
        "fullscreen_mode": 1,  # UE windowed-fullscreen (borderless)
    },
}


def _capture_display_mode_rows(rows: list[dict[str, str]]) -> list[dict[str, str]]:
    """Rewrite the strict lanes' exclusive-fullscreen guidance for capture lanes."""
    patched: list[dict[str, str]] = []
    for row in rows:
        if row.get("setting") == "Display Mode":
            row = {
                **row,
                "value": "Borderless / Windowed Fullscreen",
                "reason": (
                    "Capture-safe lane: runs the Win11 borderless windowed G-SYNC "
                    "path so OBS/Medal/overlays coexist with VRR. ABSO enables "
                    "windowed VRR and windowed optimizations to keep the flip "
                    "path fast."
                ),
            }
        patched.append(row)
    return patched


class Rivals2GSyncProfile(Rivals2BaseProfile):
    """Rollback-safe tear-free VRR lane for Rivals 2 (online and training).

    G-SYNC with NVCP VSync as safety net, capped on the 60 Hz sim grid.
    Uses the ``vrr_fighting_game`` preset (LLM on, VSync on, VRR allow).
    """

    @property
    def allow_dual_limiter(self) -> bool:
        # Rivals 2 GameUserSettings.ini is known to be rewritten by the game
        # on exit, so ABSO keeps the NVIDIA driver cap as a safety net in
        # addition to the in-game cap. Both resolve to the same
        # 60-multiple VRR cap (fighting_60hz_vrr policy).
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - G-SYNC"

    @property
    def description(self) -> str:
        return "Rollback-safe tear-free VRR lane (G-SYNC ON, VSync safety net)"

    @property
    def optimization_target(self) -> str:
        return "stable_online_vrr"

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def allows_aggressive_settings(self) -> bool:
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "rivals2-nosync"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,
            },
            "NvidiaSettingsHandler": {
                # vrr_fighting_game: LLM on, VSync on (safety net), threaded
                # opt on, max perf power, shader cache unlimited. NOTE: this
                # preset sets no vrr_app_override, so assert it explicitly below.
                "preset": "vrr_fighting_game",
                # Auto-cap on the 60 Hz sim grid: largest multiple of 60 below
                # refresh - 3 (240 @ 300 Hz). Rivals 2 ticks at a fixed 60 Hz
                # and community testing shows only 60-multiples render with an
                # even cadence — the generic refresh - 3 cap (297) alternates
                # 4/5 rendered frames per tick and reads as micro-stutter.
                "auto_vrr_fps_cap": True,
                "vrr_cap_policy": FIGHTING_60HZ_VRR_CAP_POLICY,
                # Enable G-SYNC: global fullscreen-only mode PLUS an explicit
                # per-app allow so switching from the no-sync lane (which sets
                # vrr_app_override=force_off) actually re-enables VRR for this
                # profile instead of relying on the global flip alone.
                "global_vrr_mode": "fullscreen_only",
                "vrr_app_override": "allow",
                # Keep the preset default explicitly: Rivals 2 is CPU-bound
                # UE5/DX11 and driver worker threads improve frame times; the
                # server-authoritative SnapNet sim cannot be desynced by them.
                "threaded_optimization": "on",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Exclusive fullscreen for best VRR
                "vsync": False,  # In-game VSync OFF (NVCP handles sync)
                "raw_input": True,
                "auto_vrr_fps_cap": True,
                "vrr_cap_policy": FIGHTING_60HZ_VRR_CAP_POLICY,
                "hdr_output": False,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "=== G-SYNC PROFILE ===",
                "setting": "Overview",
                "value": "G-SYNC ON, VSync ON (NVCP), 60-multiple FPS cap below refresh",
                "reason": (
                    "Tear-free rollback-safe VRR lane for online and training. "
                    "VSync acts as safety net only - never activates with FPS "
                    "capped below refresh rate. Rivals 2 ticks at a fixed 60 Hz, "
                    "so the cap snaps to the largest multiple of 60 under "
                    "refresh - 3 for an even frames-per-tick cadence: 240 @ "
                    "300Hz, 180 @ 240Hz, 120 @ 144Hz. (Blur Busters G-SYNC 101 "
                    "margin + 60 Hz sim grid.)"
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Set up G-SYNC",
                "value": "Enable G-SYNC, G-SYNC Compatible: ON",
                "reason": "Display > Set up G-SYNC. Check 'Enable G-SYNC' and 'Enable for full screen mode'.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical sync",
                "value": "On",
                "reason": (
                    "Manage 3D Settings. Acts as SAFETY NET only with G-SYNC. "
                    "With FPS capped below refresh, VSync never engages."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "On",
                "reason": (
                    "This NVIDIA setting is exposed as OGL_THREAD_CONTROL. "
                    "A frame-time benefit on Rivals 2's DX11 path has not been established."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Reduces render queue depth on the published DX11 path. 'On' is correct "
                    "(not 'Off' - Rivals 2 has no Reflex). If stuttering occurs, try 'Off' or "
                    "set Pre-Rendered Frames to 2 via Nvidia Profile Inspector."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "60-multiple cap below refresh (auto-set by ABSO)",
                "reason": (
                    "ABSO auto-detects your refresh rate and caps at the largest "
                    "multiple of 60 under refresh - 3 (240 @ 300Hz, 180 @ 240Hz, "
                    "120 @ 144Hz). Keeps G-SYNC active, V-SYNC from engaging, and "
                    "the 60 Hz sim cadence even — generic 297-style caps land off "
                    "the sim grid; whether snapping improves motion requires measurement."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Required for proper G-SYNC behavior. Borderless adds compositor latency.",
            },
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "ALWAYS disable in-game VSync with G-SYNC. NVCP VSync handles sync.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "60-multiple cap below refresh (e.g., 240 for 300Hz)",
                "reason": (
                    "Must cap below refresh for G-SYNC to work properly, and on a "
                    "multiple of 60 so the fixed 60 Hz sim renders an even number "
                    "of frames per tick. In-game limiter has lower latency than "
                    "NVCP/RTSS limiters."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "NVIDIA Reflex",
                "value": "Not available",
                "reason": (
                    "Rivals 2 does not implement NVIDIA Reflex. LLM 'On' is set via NVCP instead. "
                    "This is different from OW2/Fortnite where Reflex handles queue control."
                ),
            },
            *self._rivals2_overlay_guidance(),
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Tear-free, stable frametimes, no rollback dropouts",
                "reason": "G-SYNC smooths frame delivery. Conservative priority prevents timing contention.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: use exclusive fullscreen, in-game V-Sync Off, and "
            "the 60-multiple VRR cap (e.g. 240 @ 300 Hz) for G-SYNC. Disable "
            "external caps."
        ]


class Rivals2GSyncHDRProfile(Rivals2GSyncProfile):
    """G-SYNC Rivals 2 lane with Windows HDR composition enabled."""

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - G-SYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe G-SYNC Rivals 2 lane with Windows HDR composition. "
            "Keeps the strict VRR path; Rivals 2 native HDR output stays off."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "rivals2-nosync-hdr"

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        # Overlay-blocked applies (OBS/Medal running) reroute to the
        # borderless capture-safe sibling instead of hard-failing.
        return "rivals2-gsync-hdr-capture"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            self.HDR_WINDOWS_COMPOSITION_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*self._rivals2_hdr_guidance(), *super().get_in_game_settings()]


class Rivals2GSyncHDRCaptureProfile(Rivals2GSyncHDRProfile):
    """Capture-safe borderless sibling of the G-SYNC HDR lane.

    Same rollback-safe VRR + Windows HDR composition contract as
    :class:`Rivals2GSyncHDRProfile`, but on the borderless windowed G-SYNC
    flip path with the capture / overlay / peripheral stack (OBS, Medal,
    RTSS, overlays) kept alive at apply and game launch.
    """

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - G-SYNC HDR Capture-Safe"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe G-SYNC Rivals 2 lane with Windows HDR composition "
            "on the borderless windowed VRR path; keeps OBS/Medal/RTSS and "
            "overlays alive. Rivals 2 currently advertises no native HDR "
            "support, so native game HDR remains off."
        )

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        # Windowed VRR drops the exclusive-fullscreen contract, but the
        # NVIDIA app-binding proof stays mandatory like the strict lane.
        return True

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        # This lane IS the overlay-compatible path; terminate the chain so
        # the inherited strict-lane fallback cannot self-reference.
        return None

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            _CAPTURE_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return _capture_display_mode_rows(super().get_in_game_settings())

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: use Borderless / Windowed Fullscreen, in-game "
            "V-Sync Off, and the 60-multiple VRR cap (e.g. 240 @ 300 Hz). "
            "OBS/overlays may stay running on this lane."
        ]
