"""Rivals of Aether 2 G-SYNC / VRR profiles.

Two variants:
- Rivals2GSyncProfile: General-purpose G-SYNC (tear-free low latency)
- Rivals2OnlineGSyncProfile: Rollback-safe G-SYNC (online play with VRR)

Key difference from OW2 G-SYNC: Rivals 2 does NOT have NVIDIA Reflex,
so we use the ``vrr_fighting_game`` preset (LLM "on") instead of
``reflex_gsync`` (LLM "off").
"""

from __future__ import annotations

from typing import Any

from abso.profiles.profile_bases import Rivals2BaseProfile, merge_settings_map
from abso.settings.registry import WIN32_PRIORITY_GAMING_ONLINE

# Shared payload delta for the capture-safe siblings: swap the strict
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
    """Low latency VRR profile for Rivals of Aether 2.

    Tear-free output via G-SYNC with VSync as safety net.
    Uses ``vrr_fighting_game`` preset (LLM on, VSync on, VRR allow).
    """

    @property
    def allow_dual_limiter(self) -> bool:
        # Rivals 2 GameUserSettings.ini is known to be rewritten by the game
        # on exit, so ABSO keeps the NVIDIA driver cap as a safety net in
        # addition to the in-game cap. Both resolve to the same
        # refresh - 3 VRR cap.
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Offline GSYNC"

    @property
    def description(self) -> str:
        return "Low latency VRR profile (G-SYNC ON, VSync safety net)"

    @property
    def optimization_target(self) -> str:
        return "low_latency_vrr"

    @property
    def is_online_profile(self) -> bool:
        return False

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def include_nvidia_notifications(self) -> bool:
        return True

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "rivals2-offline"

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
                # Auto-detect refresh rate and cap below refresh for G-SYNC headroom
                "auto_vrr_fps_cap": True,
                # Enable G-SYNC: global fullscreen-only mode PLUS an explicit
                # per-app allow so switching from a no-sync Rivals lane (which
                # sets vrr_app_override=force_off) actually re-enables VRR for
                # this profile instead of relying on the global flip alone.
                "global_vrr_mode": "fullscreen_only",
                "vrr_app_override": "allow",
                # Keep driver threading consistent with the no-sync Rivals
                # lanes; the generic fighting-game preset defaults this on.
                "threaded_optimization": "off",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Exclusive fullscreen for best VRR
                "vsync": False,  # In-game VSync OFF (NVCP handles sync)
                "raw_input": True,
                "auto_vrr_fps_cap": True,
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
                "value": "G-SYNC ON, VSync ON (NVCP), refresh - 3 FPS cap",
                "reason": (
                    "Tear-free low-latency VRR profile. VSync acts as safety net only - "
                    "never activates with FPS capped below refresh rate. "
                    "For 300Hz: cap at 297. For 240Hz: cap at 237. For 144Hz: cap at 141. "
                    "(Blur Busters G-SYNC 101 convention.)"
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
                "value": "refresh - 3 cap (auto-set by ABSO)",
                "reason": (
                    "ABSO auto-detects your refresh rate and applies the Blur "
                    "Busters G-SYNC 101 convention (refresh - 3: e.g. 297 @ "
                    "300Hz, 237 @ 240Hz, 141 @ 144Hz). Keeps G-SYNC active "
                    "and V-SYNC from engaging."
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
                "value": "refresh - 3 cap (e.g., 297 for 300Hz)",
                "reason": (
                    "Must cap below refresh for G-SYNC to work properly. "
                    "In-game limiter has lower latency than NVCP/RTSS limiters."
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
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: use exclusive fullscreen, in-game V-Sync Off, and the refresh-minus-3 FPS cap for G-SYNC."
        ]


class Rivals2GSyncHDRProfile(Rivals2GSyncProfile):
    """Offline G-SYNC Rivals 2 profile with Windows HDR composition enabled."""

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Offline GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Offline G-SYNC Rivals 2 profile with Windows HDR composition. "
            "Keeps the strict VRR path; Rivals 2 native HDR output stays off."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "rivals2-offline-hdr"

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
    """Capture-safe borderless sibling of the offline G-SYNC HDR lane.

    Same VRR + Windows HDR composition contract as
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
        return "Rivals 2 - Offline GSYNC HDR Capture-Safe"

    @property
    def description(self) -> str:
        return (
            "Offline G-SYNC Rivals 2 lane with Windows HDR composition on the "
            "borderless windowed VRR path; keeps OBS/Medal/RTSS and overlays "
            "alive. Rivals 2 currently advertises no native HDR support, so "
            "native game HDR remains off."
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
            "V-Sync Off, and the refresh-minus-3 cap. OBS/overlays may stay "
            "running on this lane."
        ]


class Rivals2OnlineGSyncProfile(Rivals2BaseProfile):
    """Rollback-safe G-SYNC profile for Rivals 2 online play.

    Same G-SYNC setup as the general profile but with stability constraints
    for SnapNet rollback netcode. Threaded optimization is forced off to avoid
    extra driver-side timing variability.
    """

    @property
    def allow_dual_limiter(self) -> bool:
        # Same rationale as Rivals2GSyncProfile: the game rewrites
        # GameUserSettings.ini on exit, so ABSO keeps the driver cap as a
        # safety net alongside the in-game cap. Both resolve to the same
        # refresh - 3 VRR cap.
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-online-gsync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Online GSYNC"

    @property
    def description(self) -> str:
        return "Rollback-safe VRR profile (G-SYNC ON, stability-focused)"

    @property
    def optimization_target(self) -> str:
        return "stable_online_vrr"

    @property
    def is_online_profile(self) -> bool:
        return True

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
        return "rivals2-online"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "max_refresh_rate": True,
            },
            "RegistrySettingsHandler": {
                # Match the no-sync online lane (Rivals2OnlineProfile): rollback
                # netcode wants deterministic scheduler timing over maximum
                # foreground favoritism, so downgrade Win32PrioritySeparation to
                # the ONLINE value. The base inherits the OFFLINE value, so the
                # two online lanes would otherwise ship different scheduler
                # tuning.
                "win32_priority_separation": WIN32_PRIORITY_GAMING_ONLINE,
            },
            "NvidiaSettingsHandler": {
                "preset": "vrr_fighting_game",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_only",
                # Explicit per-app VRR allow, symmetric with the no-sync lanes'
                # explicit force_off (vrr_fighting_game sets neither).
                "vrr_app_override": "allow",
                # Override preset default - driver timing variability risk with rollback
                "threaded_optimization": "off",
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                "raw_input": True,
                "auto_vrr_fps_cap": True,
                "hdr_output": False,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,  # Conservative (not aggressive) for online stability
                "io_priority": 2,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "=== ONLINE G-SYNC PROFILE ===",
                "setting": "Overview",
                "value": "G-SYNC ON, Rollback-Safe, Stability-Focused",
                "reason": (
                    "Tear-free VRR for online play. Stability constraints applied for "
                    "SnapNet rollback netcode. Threaded optimization OFF to prevent "
                    "driver-side timing variability during rollback recovery."
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
                "value": "On (safety net)",
                "reason": "NVCP VSync as safety net only. Never engages with FPS capped below refresh.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "Off",
                "reason": "OFF - avoids extra driver-side timing variability during rollback.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On (NOT Ultra)",
                "reason": (
                    "Ultra can cause frame pacing issues and overrides FPS caps. "
                    "'On' reduces queue depth safely for online play."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Required for proper G-SYNC behavior.",
            },
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "NVCP VSync handles sync. In-game VSync must be off with G-SYNC.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "Refresh-scaled VRR cap",
                "reason": (
                    "Keeps G-SYNC active and below the VSync ceiling. Use the "
                    "in-game cap for lowest limiter latency."
                ),
            },
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Tear-free, stable frametimes, no rollback dropouts",
                "reason": "G-SYNC smooths frame delivery. Conservative priority prevents timing contention.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: keep in-game V-Sync Off and use the refresh-minus-3 cap; disable external caps for online rollback."
        ]


class Rivals2OnlineGSyncHDRProfile(Rivals2OnlineGSyncProfile):
    """Rollback-safe online G-SYNC Rivals 2 profile with Windows HDR composition."""

    @property
    def profile_id(self) -> str:
        return "rivals2-online-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Online GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe online G-SYNC Rivals 2 profile with Windows HDR composition. "
            "Keeps the strict VRR stability path; Rivals 2 native HDR output stays off."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "rivals2-online-hdr"

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        # Overlay-blocked applies (OBS/Medal running) reroute to the
        # borderless capture-safe sibling instead of hard-failing.
        return "rivals2-online-gsync-hdr-capture"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._settings_overrides(),
            self.HDR_WINDOWS_COMPOSITION_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*self._rivals2_hdr_guidance(), *super().get_in_game_settings()]


class Rivals2OnlineGSyncHDRCaptureProfile(Rivals2OnlineGSyncHDRProfile):
    """Capture-safe borderless sibling of the online G-SYNC HDR lane.

    Same rollback-safe VRR + Windows HDR composition contract as
    :class:`Rivals2OnlineGSyncHDRProfile`, but on the borderless windowed
    G-SYNC flip path with the capture / overlay / peripheral stack (OBS,
    Medal, RTSS, overlays) kept alive at apply and game launch.
    """

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def profile_id(self) -> str:
        return "rivals2-online-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - Online GSYNC HDR Capture-Safe"

    @property
    def description(self) -> str:
        return (
            "Rollback-safe online G-SYNC Rivals 2 lane with Windows HDR "
            "composition on the borderless windowed VRR path; keeps "
            "OBS/Medal/RTSS and overlays alive. Rivals 2 currently advertises "
            "no native HDR support, so native game HDR remains off."
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
            "V-Sync Off, and the refresh-minus-3 cap. OBS/overlays may stay "
            "running on this lane."
        ]


