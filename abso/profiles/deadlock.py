"""Deadlock profiles (Valve, Source 2).

Deadlock is a Reflex-capable Source 2 hero shooter. ABSO does not yet
write Deadlock's native config (Source 2 user config is volatile across
playtest patches), so these variants are ``system_only`` — they tune
OS/driver/display state and surface manual in-game guidance for the
Reflex/VRR settings themselves.

The variant matrix mirrors Overwatch 2's core four:
  - ``deadlock``            -> No-sync SDR (minimum-latency lane)
  - ``deadlock-hdr``        -> No-sync HDR (OLED / Mini-LED)
  - ``deadlock-gsync``      -> Strict fullscreen-only G-SYNC SDR
  - ``deadlock-gsync-hdr``  -> Strict fullscreen-only G-SYNC HDR
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import DisplayPathRequirements
from abso.profiles.profile_bases import ReflexShooterBaseProfile, merge_settings_map

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


# Deadlock's playtest binary is ``project8.exe`` (internal codename).
# The post-launch binary is expected to be ``deadlock.exe``. Listing both
# keeps process detection, NVIDIA binding, and FSO overrides correct across
# the rename without forcing a profile bump on launch day.
_DEADLOCK_EXECUTABLES: list[str] = ["project8.exe", "deadlock.exe"]


class _DeadlockBaseProfile(ReflexShooterBaseProfile):
    """Shared Deadlock profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return list(_DEADLOCK_EXECUTABLES)

    @property
    def nvidia_binding_executables(self) -> list[str]:
        return list(_DEADLOCK_EXECUTABLES)

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
        # Source 2 ships DX11 as default. Vulkan is optional and not the
        # path most playtesters land on; align HAGS / LLM expectations with
        # the DX11 path the game uses out of the box.
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
                "reason": "No-sync mode removes sync queueing latency.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost (must be enabled manually in-game)",
                "reason": "Deadlock supports Reflex in its video settings. ABSO does not write the Source 2 video config; the in-game toggle has to be flipped manually. ABSO keeps driver LLM off so Reflex owns render-queue control.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Uncapped (or your monitor's refresh rate)",
                "reason": "No-sync lane: maximum FPS minimizes click-to-pixel latency. Cap only if your GPU runs hot or coil whine becomes an issue.",
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
                "value": "Fullscreen (Exclusive)",
                "reason": (
                    "This profile is tuned for fullscreen-only G-SYNC. "
                    "Do not switch to borderless/windowed mode after launch."
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
                "value": "On + Boost (must be enabled manually in-game)",
                "reason": "Deadlock supports Reflex in its video settings. ABSO does not write the Source 2 video config; the in-game toggle has to be flipped manually. ABSO keeps driver LLM off so Reflex owns render-queue control.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Auto (refresh rate - 3)",
                "reason": "Set by ABSO via NVCP to keep VSync from engaging while preserving VRR.",
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
                "category": "Display",
                "setting": "HDR",
                "value": "On (if Deadlock exposes the toggle in this build)",
                "reason": "Use Deadlock's HDR output when the active display path supports native HDR. If Deadlock has not yet shipped an HDR toggle, leave it off and rely on the Windows HDR path.",
            },
            {
                "category": "Display",
                "setting": "HDR Calibration",
                "value": "Calibrate paper white / peak brightness in-game or via Windows HDR Calibration",
                "reason": "Tune once for your display; do not crank brightness past your panel's real peak or you trade visibility for raw nits.",
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


class DeadlockProfile(_DeadlockBaseProfile):
    """Deadlock no-sync SDR profile (minimum latency lane)."""

    @property
    def profile_id(self) -> str:
        return "deadlock"

    @property
    def display_name(self) -> str:
        return "Deadlock - No Sync SDR"

    @property
    def description(self) -> str:
        return (
            "Minimum latency no-sync SDR Deadlock profile (VSync OFF, VRR OFF). "
            "Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # No-sync lane runs exclusive fullscreen. Disable FSO per-exe so
        # Windows cannot silently shunt Deadlock into the composited
        # borderless FSO shim and pay the compositor tax on top of the
        # native present path.
        return {exe: True for exe in _DEADLOCK_EXECUTABLES}

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
                "digital_vibrance": 50,
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
    """Deadlock no-sync HDR profile (OLED / Mini-LED)."""

    @property
    def profile_id(self) -> str:
        return "deadlock-hdr"

    @property
    def display_name(self) -> str:
        return "Deadlock - No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "Minimum latency no-sync HDR Deadlock profile (VSync OFF, VRR OFF). "
            "Native HDR for OLED / Mini-LED; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Same exclusive-fullscreen contract as the SDR no-sync lane.
        return {exe: True for exe in _DEADLOCK_EXECUTABLES}

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
    """Deadlock G-SYNC SDR profile (strict fullscreen-only VRR)."""

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
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Strict fullscreen VRR lane: disable FSO per-exe so Windows holds
        # the true exclusive path and the refresh-3 cap stays cap-bound
        # instead of paying the compositor tax if Deadlock drifts to
        # borderless.
        return {exe: True for exe in _DEADLOCK_EXECUTABLES}

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=True)

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Deadlock",
                # Enforce VRR-safe cap automatically (refresh-3) so NVCP
                # VSync stays a safety net and never engages.
                "auto_vrr_fps_cap": True,
                # Fullscreen-only VRR matches the strict exclusive lane.
                "global_vrr_mode": "fullscreen_only",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                # Slightly below neutral to compensate for DCI-P3
                # oversaturation in SDR.
                "digital_vibrance": 45,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            *self._sdr_in_game_settings(),
            *self._gsync_in_game_settings(),
        ]


class DeadlockGSyncHDRProfile(_DeadlockBaseProfile):
    """Deadlock G-SYNC HDR profile (strict fullscreen-only VRR, OLED / Mini-LED)."""

    @property
    def profile_id(self) -> str:
        return "deadlock-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Deadlock - GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low latency VRR HDR Deadlock profile (VSync safety net, "
            "G-SYNC ON). Native HDR for OLED / Mini-LED; enable Reflex On + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Native HDR strict lane: FSO must stay disabled per-exe. Otherwise
        # Windows composites Deadlock's HDR path through DWM and the GPU
        # pays the compositor cost on top of the real HDR pipeline.
        return {exe: True for exe in _DEADLOCK_EXECUTABLES}

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=True)

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
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
                "global_vrr_mode": "fullscreen_only",
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
            *self._gsync_in_game_settings(),
        ]
