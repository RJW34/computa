"""Counter-Strike 2 profiles (Valve, Source 2).

Counter-Strike 2 is a Reflex-capable Source 2 competitive shooter. ABSO does
not write CS2's native config (Source 2 user config lives under Steam
``userdata`` and the game rewrites ``cs2_video.txt`` on exit), so these
variants are ``system_only`` — they tune OS/driver/display state and surface
manual in-game guidance for the Reflex/VRR/fps_max settings themselves. Same
posture as the Deadlock family.

The variant matrix mirrors Deadlock's core four, plus a capture-safe sibling:
  - ``counter-strike-2``            -> No-sync SDR (latency-focused lane)
  - ``counter-strike-2-hdr``        -> No-sync HDR (OLED / Mini-LED)
  - ``counter-strike-2-gsync``      -> Strict fullscreen-only G-SYNC SDR
  - ``counter-strike-2-gsync-hdr``  -> Strict fullscreen-only G-SYNC HDR
  - ``counter-strike-2-gsync-hdr-capture`` -> Borderless G-SYNC HDR that keeps
    Medal / OBS / RTSS / overlays alive (same contract as the OW2 and Rivals 2
    capture lanes)
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


# CS2 ships a single stable binary (``game\bin\win64\cs2.exe``). VAC is an
# in-process module, so unlike Fortnite there is no anti-cheat bootstrapper
# alias to track.
_CS2_EXECUTABLES: list[str] = ["cs2.exe"]


class _CounterStrike2BaseProfile(ReflexShooterBaseProfile):
    """Shared Counter-Strike 2 profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return list(_CS2_EXECUTABLES)

    @property
    def nvidia_binding_executables(self) -> list[str]:
        return ["cs2.exe"]

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Every CS2 lane runs exclusive-style Fullscreen. Disable FSO per-exe
        # so Windows cannot silently shunt the game into the composited
        # borderless shim.
        return fso_overrides(_CS2_EXECUTABLES)

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Counter-Strike 2"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        # CS2 replaced CS:GO inside Steam app 730, so driver DBs that predate
        # the rename can still own the cs2.exe binding through the CS:GO-era
        # profile. Reuse that binding instead of creating an unbound duplicate.
        return [
            "Counter-strike 2",
            "cs2.exe",
            "Counter-Strike: Global Offensive",
            "Counter-strike: Global Offensive",
        ]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        # CS2 (Source 2) renders through DX11 on Windows (the Vulkan path is
        # the Linux build). HAGS / LLM expectations here are aligned to DX11.
        return "dx11"

    def get_handlers(self) -> list[SettingsHandler]:
        # No native config handler: ABSO stays system_only for CS2 because the
        # game rewrites its Source 2 video config (cs2_video.txt) on exit and
        # the file lives under a per-account Steam userdata path.
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
                "category": "Video",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "No-sync lane: Fullscreen avoids the DWM compositor tax and keeps the Source 2 present path deterministic.",
            },
            {
                "category": "Video",
                "setting": "Wait for Vertical Sync",
                "value": "Disabled",
                "reason": "No-sync mode avoids the VSync/VRR queueing path and accepts tearing.",
            },
            {
                "category": "Video",
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — ABSO already set driver LLM off; flip the in-game toggle to finish",
                "reason": "ABSO has already configured the driver side: NVIDIA LLM is OFF so the engine owns the render queue (Reflex's correct path). The Source 2 video config is owned by the game and cannot be written from outside; toggle 'NVIDIA Reflex' to 'Enabled + Boost' in CS2's Video settings once to finish setup.",
            },
            {
                "category": "Video",
                "setting": "Maximum FPS in game (fps_max)",
                "value": "0 (uncapped)",
                "reason": "No-sync lane: CS2 is CPU-bound at competitive settings and higher uncapped FPS lowers frame time. Cap if heat, noise, or pacing gets worse.",
            },
            *self._shared_graphics_in_game_settings(),
        ]

    def _gsync_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Video",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": (
                    "This profile is tuned for fullscreen-only G-SYNC. "
                    "Do not switch to windowed modes after launch."
                ),
            },
            {
                "category": "Video",
                "setting": "Wait for Vertical Sync",
                "value": "Disabled (in-game)",
                "reason": "Use NVCP VSync as the VRR safety net; keep the in-game toggle off.",
            },
            {
                "category": "Video",
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost — ABSO already set driver LLM off; flip the in-game toggle to finish",
                "reason": "ABSO has already configured the driver side: NVIDIA LLM is OFF so the engine owns the render queue (Reflex's correct path). The Source 2 video config is owned by the game and cannot be written from outside; toggle 'NVIDIA Reflex' to 'Enabled + Boost' in CS2's Video settings once to finish setup.",
            },
            {
                "category": "Video",
                "setting": "Maximum FPS in game (fps_max)",
                "value": "0 (uncapped in-game; ABSO caps at the driver)",
                "reason": "ABSO sets the NVCP limiter to refresh - 3 (Blur Busters G-SYNC 101 convention). Keeping fps_max at 0 leaves one deterministic limiter in the path and stops NVCP V-SYNC from engaging.",
            },
            *self._shared_graphics_in_game_settings(),
        ]

    @staticmethod
    def _shared_graphics_in_game_settings() -> list[dict[str, str]]:
        return [
            {
                "category": "Video",
                "setting": "Multisampling Anti-Aliasing Mode",
                "value": "CMAA2, or 2x-4x MSAA with GPU headroom",
                "reason": "MSAA is CS2's main GPU cost lever; CMAA2 keeps the CPU-bound lane cheap while MSAA is affordable only when the GPU is not the bottleneck.",
            },
            {
                "category": "Video",
                "setting": "Shader / Particle / Effect Detail",
                "value": "Low",
                "reason": "Smokes and utility fights are the most common source of frame-time spikes in CS2; competitive-low keeps the frame queue clean.",
            },
            {
                "category": "Video",
                "setting": "Boost Player Contrast",
                "value": "Enabled",
                "reason": "Improves enemy visibility at negligible GPU cost.",
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
                    "Counter-Strike 2 has not shipped a native HDR toggle in the "
                    "builds this profile was authored against. Windows HDR is on "
                    "to keep the OS composition path consistent for OLED owners; "
                    "the game itself renders SDR and is composited into the HDR "
                    "surface. If CS2 ships an in-game HDR toggle later, enable "
                    "it then - until then this is SDR-in-HDR composition."
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
                "Counter-Strike 2 manual: set NVIDIA Reflex to Enabled + Boost; "
                "keep 'Wait for Vertical Sync' Disabled and Display Mode "
                "Fullscreen."
            )
        ]


class CounterStrike2Profile(_CounterStrike2BaseProfile):
    """Counter-Strike 2 no-sync SDR profile (latency-focused lane)."""

    @property
    def profile_id(self) -> str:
        return "counter-strike-2"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - No Sync SDR"

    @property
    def description(self) -> str:
        return (
            "Latency-focused no-sync SDR Counter-Strike 2 profile (VSync OFF, "
            "VRR OFF). Keeps driver LLM off for Reflex; enable Reflex "
            "Enabled + Boost in-game."
        )

    @property
    def is_sdr_only(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_no_sync",
                "profile_name": "Counter-Strike 2",
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


class CounterStrike2HDRProfile(_CounterStrike2BaseProfile):
    """Counter-Strike 2 no-sync HDR profile (OS-level HDR for OLED / Mini-LED).

    NOTE: CS2 has no native HDR toggle in the builds this profile was authored
    against. This profile turns Windows HDR ON for desktop comfort while the
    game itself renders SDR composited inside the HDR surface - same posture
    as the Deadlock HDR siblings. If Valve ships native HDR later, the in-game
    guidance points users at the toggle; until then this is functionally
    SDR-in-HDR composition.
    """

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-hdr"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - No Sync HDR"

    @property
    def description(self) -> str:
        return (
            "Latency-focused no-sync Counter-Strike 2 profile with Windows HDR "
            "on for OLED desktop comfort (VSync OFF, VRR OFF). CS2 currently "
            "renders SDR; HDR is for the OS composition path, not the game. "
            "Enable Reflex Enabled + Boost in-game."
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
                "profile_name": "Counter-Strike 2",
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


class CounterStrike2GSyncProfile(_CounterStrike2BaseProfile):
    """Counter-Strike 2 G-SYNC SDR profile (strict fullscreen-only VRR)."""

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-gsync"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - GSYNC SDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low latency VRR SDR Counter-Strike 2 profile (VSync "
            "safety net, G-SYNC ON). Keeps driver LLM off for Reflex; enable "
            "Reflex Enabled + Boost in-game."
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
        return "counter-strike-2"

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Counter-Strike 2",
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


class CounterStrike2GSyncHDRProfile(_CounterStrike2BaseProfile):
    """Counter-Strike 2 G-SYNC profile with Windows HDR on (strict fullscreen-only VRR).

    NOTE: Same caveat as CounterStrike2HDRProfile - CS2 has no native HDR
    toggle. Windows HDR is on for OLED desktop comfort, the game itself
    renders SDR composited inside HDR. Switch back to counter-strike-2-gsync
    for the pure SDR lane if you don't want OS HDR on.
    """

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Tear-free low latency VRR Counter-Strike 2 profile with Windows "
            "HDR on for OLED desktop comfort (VSync safety net, G-SYNC ON). "
            "CS2 currently renders SDR; HDR is for the OS composition path. "
            "Enable Reflex Enabled + Boost in-game."
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
        return "counter-strike-2-hdr"

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        # Overlay-blocked applies (Medal/OBS running) reroute to the borderless
        # capture-safe sibling instead of hard-failing or killing the recorder.
        return "counter-strike-2-gsync-hdr-capture"

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
                "profile_name": "Counter-Strike 2",
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


class CounterStrike2GSyncHDRCaptureProfile(CounterStrike2GSyncHDRProfile):
    """Capture-safe borderless sibling of the CS2 G-SYNC HDR lane.

    Same VRR + Windows HDR composition contract as
    :class:`CounterStrike2GSyncHDRProfile`, with two deliberate differences:

    - The launch-time janitor keeps the capture / overlay / peripheral stack
      alive (Medal, OBS, RTSS, Discord overlay, NVIDIA Share, G HUB, iCUE)
      instead of stopping it for frame-time headroom.
    - VRR runs on the Win11 borderless windowed flip path
      (``fullscreen_and_windowed`` + windowed optimizations) rather than the
      strict fullscreen-only path, because the overlay-free display-path gate
      is what would otherwise block apply while a recorder is running.

    Cost of this lane vs the strict one: the recorder's encode work and the
    composited borderless present path both take a small slice of frame-time
    budget. That is the trade being bought - a clip you actually keep.
    """

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - GSYNC HDR Capture-Safe"

    @property
    def description(self) -> str:
        return (
            "Same VRR + Windows HDR path as GSYNC HDR, on the borderless "
            "windowed G-SYNC path, but keeps Medal/OBS/RTSS and overlays "
            "alive at launch instead of stopping them. Enable Reflex "
            "Enabled + Boost in-game."
        )

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        # This lane IS the overlay-tolerant path: no overlay-free gate, so
        # apply does not fail (or auto-close Medal) when a recorder is up.
        return DisplayPathRequirements()

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        # Terminate the fallback chain so the inherited strict-lane pointer
        # cannot self-reference this profile.
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Borderless capture lane: clear any stale FSO-disable entry left by a
        # prior strict CS2 apply so the composited flip path can engage
        # instead of fighting an OS-level exclusive-fullscreen lock.
        return fso_overrides(_CS2_EXECUTABLES, disabled=False)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._variant_overrides(),
            {
                "WindowsSettingsHandler": {
                    # Win11 borderless flip path: required for VRR to engage
                    # in windowed fullscreen.
                    "windowed_optimizations": True,
                    "vrr_optimize": True,
                },
                "GraphicsSettingsHandler": {
                    # Leave the global FSO policy alone; the borderless lane
                    # depends on the optimized composited path the strict lane
                    # deliberately disables.
                    "disable_global_fso": False,
                },
                "NvidiaSettingsHandler": {
                    "global_vrr_mode": "fullscreen_and_windowed",
                },
            },
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        rows = [
            *self._hdr_in_game_settings(),
            *self._gsync_in_game_settings(),
        ]
        patched: list[dict[str, str]] = []
        for row in rows:
            if row.get("setting") == "Display Mode":
                row = {
                    **row,
                    "value": "Fullscreen Windowed (borderless)",
                    "reason": (
                        "Capture-safe lane: runs the Win11 borderless windowed "
                        "G-SYNC path so Medal/OBS/overlays coexist with VRR. "
                        "ABSO enables windowed VRR and windowed optimizations "
                        "to keep the flip path fast. Use the strict "
                        "counter-strike-2-gsync-hdr lane for exclusive "
                        "Fullscreen when nothing is recording."
                    ),
                }
            patched.append(row)
        return patched

    def get_post_apply_notes(self) -> list[str]:
        return [
            (
                "Counter-Strike 2 manual: set Display Mode to Fullscreen "
                "Windowed, NVIDIA Reflex to Enabled + Boost, and keep 'Wait "
                "for Vertical Sync' Disabled."
            ),
            (
                "Capture-safe lane: Medal, OBS, RTSS, and overlay apps are "
                "left running at apply and at game launch. Expect slightly "
                "more frame-time noise than counter-strike-2-gsync-hdr."
            ),
        ]
