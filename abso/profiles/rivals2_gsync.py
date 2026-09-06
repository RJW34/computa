"""Rivals of Aether 2 G-SYNC / VRR profiles (merged offline/online lanes).

Four variants:
- Rivals2GSyncProfile: SDR G-SYNC (tear-free, rollback-safe)
- Rivals2GSyncCaptureProfile: + borderless SDR streaming path (OBS/Medal)
- Rivals2GSyncHDRProfile: + Windows HDR composition
- Rivals2GSyncHDRCaptureProfile: + borderless HDR streaming path (OBS/Medal)

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
from abso.profiles.profile_bases import (
    Rivals2BaseProfile,
    fso_overrides,
    merge_settings_map,
)

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
    "GraphicsSettingsHandler": {
        "disable_global_fso": False,
    },
    "NvidiaSettingsHandler": {
        "global_vrr_mode": "fullscreen_and_windowed",
    },
    "Rivals2ConfigHandler": {
        "fullscreen_mode": 1,  # UE windowed-fullscreen (borderless)
    },
    "ProcessPriorityHandler": {
        "cpu_priority": 2,
        "io_priority": 2,
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
                    "Streaming lane: uses the borderless windowed G-SYNC path "
                    "so OBS, Medal, RTSS, and overlays can stay running while "
                    "ABSO enables windowed VRR and windowed optimizations."
                ),
            }
        elif row.get("setting") == "Exclusive Fullscreen vs SDR-in-HDR latency":
            row = {
                **row,
                "setting": "Borderless Streaming vs SDR-in-HDR latency",
                "value": "Use Borderless / Windowed Fullscreen",
                "reason": (
                    "Rivals 2 renders SDR through Windows HDR on this streaming "
                    "lane. Presentation cost varies by OS, driver, and display "
                    "and is not measured by ABSO."
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

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return "rivals2-gsync-capture"

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
                # as a heuristic for an integer frames-per-tick cadence.
                # A frame-time advantage over refresh - 3 needs measurement.
                "auto_vrr_fps_cap": True,
                "vrr_cap_policy": FIGHTING_60HZ_VRR_CAP_POLICY,
                # Enable G-SYNC: global fullscreen-only mode PLUS an explicit
                # per-app allow so switching from the no-sync lane (which sets
                # vrr_app_override=force_off) actually re-enables VRR for this
                # profile instead of relying on the global flip alone.
                "global_vrr_mode": "fullscreen_only",
                "vrr_app_override": "allow",
                # Keep the existing preset value. The setting is exposed as
                # OGL_THREAD_CONTROL; a benefit for DX11 is unestablished.
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


class Rivals2GSyncCaptureProfile(Rivals2GSyncProfile):
    """Streaming-safe borderless sibling of the SDR G-SYNC lane."""

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync-capture"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - G-SYNC SDR Streaming"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe SDR G-SYNC lane on the borderless windowed VRR "
            "path; preserves OBS, Medal, RTSS, and overlay processes and keeps "
            "game CPU/I/O priority at Normal so capture is not starved."
        )

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return None

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> None:
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        return fso_overrides(self.executable_hints, disabled=False)

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            _CAPTURE_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return _capture_display_mode_rows(super().get_in_game_settings())

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 streaming manual: use Borderless / Windowed Fullscreen, "
            "keep in-game V-Sync Off, and use the 60-multiple VRR cap. OBS and "
            "overlay processes remain available on this lane."
        ]


class Rivals2GSyncHDRCaptureProfile(Rivals2GSyncHDRProfile):
    """Streaming-safe borderless sibling of the G-SYNC HDR lane.

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
        return "Rivals 2 - G-SYNC HDR Streaming"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe G-SYNC Rivals 2 lane with Windows HDR composition "
            "on the borderless windowed VRR path; preserves OBS, Medal, RTSS, "
            "and overlay processes and keeps game CPU/I/O priority at Normal. "
            "Rivals 2 currently advertises no native HDR "
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

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> None:
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        return fso_overrides(self.executable_hints, disabled=False)

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            _CAPTURE_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return _capture_display_mode_rows(super().get_in_game_settings())

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 streaming manual: use Borderless / Windowed Fullscreen, "
            "keep in-game V-Sync Off, and use the 60-multiple VRR cap. OBS and "
            "overlay processes remain available on this lane.",
            "Streaming color: default to SDR Streaming for an SDR destination. "
            "Use HDR Streaming only when OBS/output color space or tone mapping "
            "is already intentionally configured; ABSO does not change OBS settings.",
        ]
