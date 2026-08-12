"""Deadlock profiles (Valve, Source 2).

Deadlock is a Reflex-capable Source 2 hero shooter. ABSO does not yet
write Deadlock's native config (Source 2 user config is volatile across
playtest patches), so these variants are ``system_only`` — they tune
OS/driver/display state and surface manual in-game guidance for the
Reflex/VRR settings themselves.

The variant matrix mirrors Overwatch 2's core four:
  - ``deadlock``            -> No-sync SDR (latency-focused lane)
  - ``deadlock-hdr``        -> No-sync HDR (OLED / Mini-LED)
  - ``deadlock-gsync``      -> G-SYNC SDR (overlay-strict, flip path)
  - ``deadlock-gsync-hdr``  -> G-SYNC HDR (overlay-strict, flip path)

The G-SYNC lanes are strict on overlays, not on display path: like the CS2
family they run the borderless/windowed G-SYNC contract, because Source 2 has
no exclusive-fullscreen mode. See ``_DEADLOCK_WINDOWED_VRR_OVERRIDES``.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import DisplayPathRequirements
from abso.profiles.profile_bases import (
    ReflexShooterBaseProfile,
    fso_overrides,
    merge_settings_map,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


# Deadlock's playtest binary is ``project8.exe`` (internal codename).
# The post-launch binary is expected to be ``deadlock.exe``. Listing both
# keeps process detection, NVIDIA binding, and FSO overrides correct across
# the rename without forcing a profile bump on launch day.
_DEADLOCK_EXECUTABLES: list[str] = ["project8.exe", "deadlock.exe"]


# Deadlock is Source 2, so it inherits the same presentation reality as CS2:
# no true exclusive fullscreen, everything presents through DXGI flip. The
# strict exclusive-fullscreen VRR contract is therefore unsatisfiable and
# fails silently — ``fullscreen_only`` restricts driver VRR to a mode the game
# never enters, while the same lane turns off the enablers the flip path needs.
# See ``_CS2_WINDOWED_VRR_OVERRIDES`` in counter_strike_2.py for the full
# write-up; this is the identical contract.
_DEADLOCK_WINDOWED_VRR_OVERRIDES: dict[str, dict[str, Any]] = {
    "WindowsSettingsHandler": {
        "windowed_optimizations": True,
        "vrr_optimize": True,
    },
    "GraphicsSettingsHandler": {
        "disable_global_fso": False,
    },
    "NvidiaSettingsHandler": {
        "global_vrr_mode": "fullscreen_and_windowed",
        # Assert the per-app allow so switching in from a Deadlock no-sync
        # lane (vrr_app_override=force_off) re-enables VRR deterministically.
        "vrr_app_override": "allow",
    },
}


class _DeadlockBaseProfile(ReflexShooterBaseProfile):
    """Shared Deadlock profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return list(_DEADLOCK_EXECUTABLES)

    @property
    def nvidia_binding_executables(self) -> list[str]:
        # Current playtest shipping binary. Keep executable_hints broader for
        # process detection, but strict NVIDIA binding should target one real
        # game binary instead of every future/legacy alias.
        return ["project8.exe"]

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Every Deadlock lane runs exclusive fullscreen. Disable FSO per-exe
        # for both playtest/final binary names so Windows cannot silently shunt
        # the game into the composited borderless shim.
        return fso_overrides(_DEADLOCK_EXECUTABLES)

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Deadlock"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "project8.exe",
            "deadlock.exe",
            "Deadlock (Playtest)",
        ]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        # Deadlock (Source 2) exposes BOTH DX11 (-dx11) and Vulkan (-vulkan).
        # ABSO targets the DX11 path: it delivers more consistent frame-time
        # stability on most NVIDIA hardware (Vulkan can edge out peak FPS but is
        # less stable), which matches this profile's latency-consistency goal.
        # Players on AMD or chasing peak average FPS may prefer -vulkan; HAGS /
        # LLM expectations here are aligned to DX11.
        return "dx11"

    def get_handlers(self) -> list[SettingsHandler]:
        # No native config handler yet: ABSO stays system_only for Deadlock
        # until the Source 2 video config schema stabilizes.
        return super().get_handlers()

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
        }

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(self._base_overrides(), self._variant_overrides())

    def _no_sync_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "No-sync lane: exclusive fullscreen avoids the DWM compositor tax and keeps the Source 2 present path deterministic.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "No-sync mode avoids the VSync/VRR queueing path and accepts tearing.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost — ABSO already set driver LLM off; flip the in-game toggle to finish",
                "reason": "ABSO has already configured the driver side: NVIDIA LLM is OFF so the engine owns the render queue (Reflex's correct path). The Source 2 video config is owned by the game and cannot be written from outside; manually toggle 'NVIDIA Reflex Low Latency' to 'On + Boost' in Deadlock's Video settings once to finish setup.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Uncapped (or your monitor's refresh rate)",
                "reason": "No-sync lane: higher uncapped FPS can reduce frame time when the game can sustain it. Cap if heat, noise, or pacing gets worse.",
            },
            {
                "category": "Graphics",
                "setting": "Upscaling",
                "value": "DLSS Quality / FSR Quality if GPU-bound, otherwise Native",
                "reason": "Use upscaling only when the GPU cannot hold the target FPS native; otherwise keep the native render path for the cleanest pixel pipeline.",
            },
            {
                "category": "Graphics",
                "setting": "Shadow / Effects / Post Processing",
                "value": "Low",
                "reason": "Team-fight effects are the most common source of frame-time spikes in Source 2 hero shooters; competitive-low keeps the frame queue clean.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur / Film Grain / Chromatic Aberration",
                "value": "Off",
                "reason": "Reduces visual noise and preserves target clarity during fast camera movement.",
            },
        ]

    def _gsync_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen Windowed (borderless)",
                "reason": (
                    "Source 2 has no true exclusive fullscreen — every display "
                    "mode presents through DXGI hardware independent flip. ABSO "
                    "therefore runs the borderless G-SYNC path (windowed "
                    "optimizations + VRR optimize + driver VRR in fullscreen AND "
                    "windowed). Plain Fullscreen also keeps VRR on this path."
                ),
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Use NVCP VSync as the VRR safety net; keep the in-game toggle off.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost — ABSO already set driver LLM off; flip the in-game toggle to finish",
                "reason": "ABSO has already configured the driver side: NVIDIA LLM is OFF so the engine owns the render queue (Reflex's correct path). The Source 2 video config is owned by the game and cannot be written from outside; manually toggle 'NVIDIA Reflex Low Latency' to 'On + Boost' in Deadlock's Video settings once to finish setup.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Auto (refresh - 3: e.g. 297 @ 300Hz, 237 @ 240Hz, 141 @ 144Hz)",
                "reason": "Set by ABSO via NVCP to refresh - 3 (Blur Busters G-SYNC 101 convention). Keeps NVCP V-SYNC from engaging while preserving VRR.",
            },
            {
                "category": "Graphics",
                "setting": "Upscaling",
                "value": "DLSS Quality / FSR Quality if GPU-bound, otherwise Native",
                "reason": "Use upscaling only when the GPU cannot hold the VRR cap native; otherwise keep the native render path.",
            },
            {
                "category": "Graphics",
                "setting": "Shadow / Effects / Post Processing",
                "value": "Low",
                "reason": "Heavy team fights are where Source 2 hero shooters spike frame times; competitive-low keeps the VRR window clean.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur / Film Grain / Chromatic Aberration",
                "value": "Off",
                "reason": "Reduces visual noise and preserves target clarity during fast tracking.",
            },
        ]

    @staticmethod
    def _hdr_in_game_settings() -> list[dict[str, str]]:
        return [
            {
                "category": "Display (Windows)",
                "setting": "HDR",
                "value": "On (set by this profile for desktop comfort)",
                "reason": (
                    "Deadlock has not shipped a native HDR toggle in the playtest "
                    "builds this profile was authored against. Windows HDR is on "
                    "to keep the OS composition path consistent for OLED owners; "
                    "the game itself renders SDR and is composited into the HDR "
                    "surface. If Deadlock ships an in-game HDR toggle later, "
                    "enable it then - until then this is SDR-in-HDR composition."
                ),
            },
            {
                "category": "Display (Windows)",
                "setting": "SDR content brightness",
                "value": "200 nits starting point; tune to taste",
                "reason": (
                    "Settings > System > Display > HDR > SDR content brightness. "
                    "This profile sets 200 nits as the OLED baseline. If the "
                    "desktop reads dim, push it up to 240-280."
                ),
            },
        ]

    @staticmethod
    def _sdr_in_game_settings() -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Off",
                "reason": "Use this variant when you want the cleaner SDR path or do not have HDR active.",
            },
            {
                "category": "Display",
                "setting": "Color Space",
                "value": "SDR / default gamut",
                "reason": "Matches the profile's sRGB clamp and avoids wide-gamut oversaturation in SDR.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        return [
            (
                "Deadlock manual: set NVIDIA Reflex to On + Boost; keep in-game "
                "VSync Off and fullscreen exclusive."
            )
        ]


class DeadlockProfile(_DeadlockBaseProfile):
    """Deadlock no-sync SDR profile (latency-focused lane)."""

    @property
    def profile_id(self) -> str:
        return "deadlock"

    @property
    def display_name(self) -> str:
        return "Deadlock - No Sync SDR"

    @property
    def description(self) -> str:
        return (
            "Latency-focused no-sync SDR Deadlock profile (VSync OFF, VRR OFF). "
            "Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_no_sync",
                "profile_name": "Deadlock",
                # Explicit no-sync: kill global VRR so behavior is deterministic
                # even when the user has VRR globally enabled.
                "global_vrr_mode": "off",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 45,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            *self._sdr_in_game_settings(),
            *self._no_sync_in_game_settings(),
        ]


class DeadlockHDRProfile(_DeadlockBaseProfile):
    """Deadlock no-sync HDR profile (OS-level HDR for OLED / Mini-LED).

    NOTE: As of the playtest builds available at profile-author time, Deadlock
    has not shipped a native HDR toggle (Valve has not announced HDR support
    for the Source 2 engine on Deadlock). This profile turns Windows HDR ON
    for desktop comfort while the game itself renders SDR composited inside
    the HDR surface - same posture as the Slippi HDR siblings. If Deadlock
    ships native HDR later, the in-game guidance points users at the toggle;
    until then this is functionally SDR-in-HDR composition.
    """

    @property
    def profile_id(self) -> str:
        return "deadlock-hdr"

    @property
    def display_name(self) -> str:
        return "Deadlock - No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "Latency-focused no-sync Deadlock profile with Windows HDR on for "
            "OLED desktop comfort (VSync OFF, VRR OFF). Deadlock currently "
            "renders SDR; HDR is for the OS composition path, not the game. "
            "Enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "advanced_color": True,  # Win11 24H2+ WCG pairing
                "auto_hdr": False,
                # Paper-white at 200 nits is the OLED / Mini-LED starting
                # point. Driver installs reset this slider; asserting it
                # here restores correct SDR-in-HDR tone-mapping.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                # Keep ACM off so wide-gamut colors are not clamped to sRGB
                # system-wide by Windows 11 24H2+ Auto Color Management.
                "disable_auto_color_management": True,
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_no_sync",
                "profile_name": "Deadlock",
                "global_vrr_mode": "off",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            *self._hdr_in_game_settings(),
            *self._no_sync_in_game_settings(),
        ]


class DeadlockGSyncProfile(_DeadlockBaseProfile):
    """Deadlock G-SYNC SDR profile (overlay-strict, flip-path VRR).

    "Strict" is an overlay policy here, not a display path: VRR runs on the
    borderless contract in :data:`_DEADLOCK_WINDOWED_VRR_OVERRIDES`.
    """

    @property
    def profile_id(self) -> str:
        return "deadlock-gsync"

    @property
    def display_name(self) -> str:
        return "Deadlock - GSYNC SDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low latency VRR SDR Deadlock profile (VSync safety net, "
            "G-SYNC ON). Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=True)

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "deadlock"

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # No exclusive-fullscreen path exists to force on Source 2, and the
        # FSO-disable entry costs the flip path windowed VRR rides on.
        return fso_overrides(_DEADLOCK_EXECUTABLES, disabled=False)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            {
                "NvidiaSettingsHandler": {
                    "preset": "reflex_gsync",
                    "profile_name": "Deadlock",
                    # Enforce VRR-safe cap automatically (refresh-3) so NVCP
                    # VSync stays a safety net and never engages.
                    "auto_vrr_fps_cap": True,
                },
                "ColorProfileSettingsHandler": {
                    "icc_profile": "srgb",
                    # Slightly below neutral to compensate for DCI-P3
                    # oversaturation in SDR.
                    "digital_vibrance": 45,
                    "show_osd_guidance": True,
                    "game_type": "competitive_fps",
                },
            },
            _DEADLOCK_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            *self._sdr_in_game_settings(),
            *self._gsync_in_game_settings(),
        ]


class DeadlockGSyncHDRProfile(_DeadlockBaseProfile):
    """Deadlock G-SYNC profile with Windows HDR on (overlay-strict).

    NOTE: Same caveat as DeadlockHDRProfile - Deadlock has not shipped native
    HDR in the playtest. Windows HDR is on for OLED desktop comfort, the game
    itself renders SDR composited inside HDR. Switch back to deadlock-gsync
    for the pure SDR lane if you don't want OS HDR on.

    Display path is the borderless VRR contract shared by every Source 2 lane
    (see :data:`_DEADLOCK_WINDOWED_VRR_OVERRIDES`).
    """

    @property
    def profile_id(self) -> str:
        return "deadlock-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Deadlock - GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low latency VRR Deadlock profile with Windows HDR on "
            "for OLED desktop comfort (VSync safety net, G-SYNC ON). Deadlock "
            "currently renders SDR; HDR is for the OS composition path. "
            "Enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=True)

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str:
        return "deadlock-hdr"

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # See the SDR G-SYNC sibling.
        return fso_overrides(_DEADLOCK_EXECUTABLES, disabled=False)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            {
                "WindowsSettingsHandler": {
                    "hdr": True,
                    "advanced_color": True,
                    "auto_hdr": False,
                    "sdr_white_level_nits": 200,
                },
                "GraphicsSettingsHandler": {
                    "disable_auto_color_management": True,
                },
                "NvidiaSettingsHandler": {
                    "preset": "reflex_gsync",
                    "profile_name": "Deadlock",
                    "auto_vrr_fps_cap": True,
                },
                "ColorProfileSettingsHandler": {
                    "icc_profile": "native",
                    "digital_vibrance": 50,
                    "show_osd_guidance": True,
                    "game_type": "competitive_fps",
                },
            },
            _DEADLOCK_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            *self._hdr_in_game_settings(),
            *self._gsync_in_game_settings(),
        ]
