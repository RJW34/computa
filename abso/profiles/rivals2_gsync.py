"""Rivals of Aether 2 G-SYNC / VRR profiles (merged offline/online lanes).

Four variants:
- Rivals2GSyncProfile: SDR G-SYNC
- Rivals2GSyncCaptureProfile: + borderless SDR streaming path (OBS/Medal)
- Rivals2GSyncHDRProfile: + Windows HDR composition
- Rivals2GSyncHDRCaptureProfile: + borderless HDR streaming path (OBS/Medal)

The render cap is independent of the fixed simulation rate: SnapNet can
interpolate between simulation ticks. Native refresh-minus-three (297 at
300 Hz) is a VRR starting point, not a measured optimum or rollback guarantee.
Reflex support has not been established for this game; driver LLM stays On.
"""

from __future__ import annotations

from typing import Any

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
        "vsync": True,  # Native VSync supplies the windowed presentation path.
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
        elif row.get("setting") == "Set up G-SYNC":
            row = {**row, "reason": "Enable G-SYNC for windowed and fullscreen mode for this borderless lane."}
        elif row.get("setting") == "V-SYNC":
            row = {
                **row,
                "value": "On",
                "reason": "Use native VSync for the windowed path; the native FPS cap provides headroom below refresh.",
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
    """VRR lane for Rivals 2 online play and training, with one native cap."""

    @property
    def allow_dual_limiter(self) -> bool:
        return False

    @property
    def profile_id(self) -> str:
        return "rivals2-gsync"

    @property
    def display_name(self) -> str:
        return "Rivals 2 - G-SYNC"

    @property
    def description(self) -> str:
        return "G-SYNC lane with VSync and a native FPS cap below refresh"

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
                # Keep the complete lane explicit: no shared preset may
                # reintroduce a second limiter or forced OpenGL threading.
                "low_latency_mode": "on",
                "power_management": "prefer_max_performance",
                "vsync": "on",
                "vsync_tear_control": "disable",
                "shader_cache": "on",
                "triple_buffering": "off",
                "max_frame_rate": "off",
                # Enable G-SYNC: global fullscreen-only mode PLUS an explicit
                # per-app allow so switching from the no-sync lane (which sets
                # vrr_app_override=force_off) actually re-enables VRR for this
                # profile instead of relying on the global flip alone.
                "global_vrr_mode": "fullscreen_only",
                "vrr_app_override": "allow",
                "threaded_optimization": "auto",  # OGL control; no proven DX11 gain.
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,  # Requested fullscreen mode; runtime path unverified.
                "vsync": False,  # In-game VSync OFF (NVCP handles sync)
                "auto_vrr_fps_cap": True,
                "vrr_cap_policy": "refresh_minus_3",
                "hdr_output": False,
            },
            "NvidiaNotificationHandler": {
                "disable_notifications": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "G-SYNC profile",
                "setting": "Overview",
                "value": "G-SYNC On, VSync On, native FPS cap below refresh",
                "reason": (
                    "Uses one native render cap with headroom below display refresh. "
                    "SnapNet interpolates between simulation ticks; a 60 Hz simulation "
                    "does not require a render cap in multiples of 60. This is a "
                    "starting policy, not a measured latency or rollback guarantee."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Set up G-SYNC",
                "value": "Enable G-SYNC / G-SYNC Compatible",
                "reason": "Enable fullscreen G-SYNC for this lane; verify engagement during gameplay.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical sync",
                "value": "On",
                "reason": "Provides tear prevention with G-SYNC; the cap reduces refresh-ceiling backpressure.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded Optimization",
                "value": "Auto",
                "reason": "Restores automatic policy for this OpenGL control; no DX11 performance gain is claimed.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Driver queue-control starting point for the published DX11 path. "
                    "Compare frame times and latency before choosing another mode; "
                    "neither On nor Ultra is proven best on this PC."
                ),
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "Off",
                "reason": "The native limiter owns the cap; adding another limiter has no measured benefit here.",
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": (
                    "This lane requests fullscreen and disables FSO. The actual presentation "
                    "path and latency still require observation; use a capture lane for borderless."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "This fullscreen lane uses driver VSync; capture lanes use native VSync for windowed presentation.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "Refresh minus 3 (297 at 300 Hz)",
                "reason": (
                    "ABSO writes the native cap below the detected primary refresh. "
                    "Confirm the game retained it after launch; saved-file verification "
                    "does not prove runtime limiter behavior."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "NVIDIA Reflex",
                "value": "Support not established",
                "reason": "Rivals of Aether 2 is not listed in NVIDIA's checked Reflex game list. ABSO does not enable Reflex through driver settings.",
            },
            *self._rivals2_overlay_guidance(),
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Check frame pacing, tearing, and online responsiveness",
                "reason": "Saved settings cannot establish active VRR, input latency, or absence of rollback corrections.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Rivals 2 manual: use fullscreen, in-game VSync Off, and the native "
            "refresh-minus-three cap (297 at 300 Hz). Driver Max Frame Rate is Off; "
            "avoid adding an external cap unless comparing limiter behavior."
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
            "G-SYNC Rivals 2 lane with Windows HDR composition. "
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
            "SDR G-SYNC lane on the borderless windowed VRR "
            "path; preserves OBS, Medal, RTSS, and overlay processes and keeps "
            "game CPU/I/O priority at Normal; capture performance still needs measurement."
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
            "keep in-game V-Sync On, and use the native refresh-minus-three cap. OBS and "
            "overlay processes remain available on this lane."
        ]


class Rivals2GSyncHDRCaptureProfile(Rivals2GSyncHDRProfile):
    """Streaming-safe borderless sibling of the G-SYNC HDR lane.

    Same VRR + Windows HDR composition policy as
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
            "G-SYNC Rivals 2 lane with Windows HDR composition "
            "on the borderless windowed VRR path; preserves OBS, Medal, RTSS, "
            "and overlay processes and keeps game CPU/I/O priority at Normal. "
            "Native HDR support is not established; native game HDR remains off."
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
            "keep in-game V-Sync On, and use the native refresh-minus-three cap. OBS and "
            "overlay processes remain available on this lane.",
            "Streaming color: default to SDR Streaming for an SDR destination. "
            "Use HDR Streaming only when OBS/output color space or tone mapping "
            "is already intentionally configured; ABSO does not change OBS settings.",
        ]
