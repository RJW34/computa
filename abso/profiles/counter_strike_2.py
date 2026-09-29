"""Counter-Strike 2 profiles (Valve, Source 2).

Counter-Strike 2 is a Reflex-capable Source 2 competitive shooter. ABSO does
not write CS2's native config (Source 2 user config lives under Steam
``userdata`` and the game rewrites ``cs2_video.txt`` on exit), so these
variants are ``system_only`` — they tune OS/driver/display state and surface
manual in-game guidance for the Reflex/VRR/fps_max settings themselves. Same
posture as the Deadlock family.

The variant matrix mirrors Deadlock's core four, plus two streaming siblings:
  - ``counter-strike-2``            -> No-sync SDR (latency-focused lane)
  - ``counter-strike-2-hdr``        -> No-sync HDR (OLED / Mini-LED)
  - ``counter-strike-2-gsync``      -> Strict fullscreen-only G-SYNC SDR
  - ``counter-strike-2-gsync-hdr``  -> Strict fullscreen-only G-SYNC HDR
  - ``counter-strike-2-gsync-capture`` -> Borderless G-SYNC SDR streaming lane
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
    preserve_baseline_system_policy,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


# CS2 ships a single stable binary (``game\bin\win64\cs2.exe``). VAC is an
# in-process module, so unlike Fortnite there is no anti-cheat bootstrapper
# alias to track.
_CS2_EXECUTABLES: list[str] = ["cs2.exe"]

_STREAMING_WINDOWED_VRR_OVERRIDES: dict[str, dict[str, Any]] = {
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
    "ProcessPriorityHandler": {
        "cpu_priority": 2,
        "io_priority": 2,
    },
}


def _streaming_display_mode_rows(
    rows: list[dict[str, str]],
) -> list[dict[str, str]]:
    """Keep display mode and native sync guidance coherent for borderless."""
    patched: list[dict[str, str]] = []
    for row in rows:
        if row.get("setting") == "Display Mode":
            row = {
                **row,
                "value": "Fullscreen Windowed (borderless)",
                "reason": (
                    "Streaming lane: uses the borderless windowed G-SYNC path "
                    "so OBS, Medal, RTSS, and overlays can stay running."
                ),
            }
        elif row.get("setting") == "Wait for Vertical Sync":
            row = {
                **row,
                "value": "Enabled (in-game)",
                "reason": (
                    "NVIDIA recommends in-game VSync for windowed G-SYNC + "
                    "Reflex; driver VSync alone does not establish this path. "
                    "Set this manually in CS2's Video settings."
                ),
            }
        patched.append(row)
    return patched


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
        # Allow Windows' optimized presentation path, including Fullscreen.
        # A Fullscreen menu label alone does not prove exclusive presentation;
        # no CS2 measurement here justifies disabling FSO.
        return fso_overrides(_CS2_EXECUTABLES, disabled=False)

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
        # also available on Windows via -vulkan). HAGS / LLM expectations
        # here are aligned to DX11, not runtime API detection.
        return "dx11"

    def get_handlers(self) -> list[SettingsHandler]:
        # No native config handler: ABSO stays system_only for CS2 because the
        # game rewrites its Source 2 video config (cs2_video.txt) on exit and
        # the file lives under a per-account Steam userdata path.
        return super().get_handlers()

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Preserve the captured system policy rather than force unmeasured
        # power, scheduler/MMCSS, NIC or GPU MSI tweaks for this game.
        return preserve_baseline_system_policy(super()._base_settings())

    def _base_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
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
                "reason": "Use Fullscreen for this lane. Windows Fullscreen Optimizations remain available; actual presentation and latency need runtime measurement.",
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
                "value": "Enabled; Enabled + Boost is optional (set manually)",
                "reason": "In Settings > Video > Advanced Video, set NVIDIA Reflex Low Latency to Enabled. ABSO requests driver LLM Off and leaves CS2 settings user-owned. NVIDIA describes Boost as a possible latency reduction with extra power use and potentially lower FPS; compare on your setup before preferring it.",
            },
            {
                "category": "Video",
                "setting": "Maximum FPS in game (fps_max)",
                "value": "0 (uncapped)",
                "reason": "Optional uncapped starting point for the tearing-allowed lane. The driver limiter is Off. A sustainable manual cap may suit heat, noise or frame pacing better; uncapped FPS is not a smoothness guarantee.",
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
                "value": "Enabled (in-game)",
                "reason": "Valve recommends G-SYNC, VSync and NVIDIA Reflex together in CS2. Enable this native toggle manually; ABSO also requests driver VSync On. Check the game's NVIDIA G-Sync status row after launch, rather than assume a driver setting proves engagement.",
            },
            {
                "category": "Video",
                "setting": "NVIDIA Reflex",
                "value": "Enabled; Enabled + Boost is optional (set manually)",
                "reason": "In Settings > Video > Advanced Video, set NVIDIA Reflex Low Latency to Enabled. ABSO requests driver LLM Off and leaves CS2 settings user-owned. Boost may reduce latency at the cost of power and FPS; neither choice is a measured optimum on this machine.",
            },
            {
                "category": "Video",
                "setting": "Maximum FPS in game (fps_max)",
                "value": "0 (manual; driver refresh-minus-three ceiling remains)",
                "reason": "ABSO retains a managed driver refresh - 3 ceiling (297 at 300 Hz) because it does not write or verify CS2's native limiter. With G-SYNC, VSync and Reflex enabled, Reflex may pace FPS lower. This fallback ceiling does not promise 297 FPS, prove VRR engagement, or establish a benefit from redundant limits.",
            },
            {
                "category": "Video",
                "setting": "NVIDIA G-Sync status",
                "value": "Confirm enabled in CS2's Frame Pacing section",
                "reason": "Valve exposes this status for the current display settings. It may be hidden with Vulkan or a non-NVIDIA GPU. ABSO's configured driver values do not verify live engagement; the profile assumes the Windows DX11 path.",
            },
            *self._shared_graphics_in_game_settings(),
        ]

    @staticmethod
    def _shared_graphics_in_game_settings() -> list[dict[str, str]]:
        return [
            {
                "category": "Video",
                "setting": "Multisampling Anti-Aliasing Mode",
                "value": "CMAA2 starting point; compare 2x-4x MSAA for image quality",
                "reason": "Anti-aliasing trades edge quality for rendering cost. Compare GPU frame time and visibility at your chosen resolution; no option is proven fastest and clearest for every scene.",
            },
            {
                "category": "Video",
                "setting": "Shader Detail",
                "value": "Low starting point",
                "reason": "Valve describes higher shader detail as a visual-quality versus graphics-performance tradeoff. Compare representative scenes; Low does not guarantee fewer frame-time spikes.",
            },
            {
                "category": "Video",
                "setting": "Particle Detail",
                "value": "Low starting point",
                "reason": "Valve describes higher particle detail as more complex effects and particle shadows with possible graphics cost. Preserve a higher setting if its visual benefit is worth the measured cost.",
            },
            {
                "category": "Video",
                "setting": "Boost Player Contrast",
                "value": "Enabled starting point for visibility",
                "reason": "Valve says this improves player legibility in low-contrast situations and can degrade graphics performance. It is a visibility preference, not a free FPS improvement.",
            },
        ]

    @staticmethod
    def _hdr_in_game_settings() -> list[dict[str, str]]:
        return [
            {
                "category": "Display (Windows)",
                "setting": "HDR",
                "value": "On (Windows policy; game HDR output unverified)",
                "reason": (
                    "This lane enables Windows HDR and disables Auto HDR. "
                    "CS2's High Dynamic Range Quality/Performance setting is a "
                    "rendering-quality choice; its name does not verify HDR "
                    "display output. ABSO does not detect CS2's live output "
                    "color space or claim this improves FPS or latency."
                ),
            },
            {
                "category": "Display (Windows)",
                "setting": "SDR content brightness",
                "value": "200 nits starting point; tune to taste",
                "reason": (
                    "Settings > System > Display > HDR > SDR content brightness. "
                    "This profile sets a 200-nit preference; it is not panel "
                    "calibration or a universal OLED target. Adjust to your "
                    "display and viewing conditions."
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
                "reason": "This variant requests Windows HDR Off. It is a display preference, not a measured latency advantage over the HDR lane.",
            },
            {
                "category": "Display",
                "setting": "Color Space",
                "value": "SDR / default gamut",
                "reason": "The profile selects its sRGB ICC association and digital vibrance 45 preference. ICC association is not proof that CS2 applies a gamut transform, and vibrance is not an sRGB clamp; use display calibration for color accuracy.",
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        gsync = self.requires_confirmed_vrr_support
        vsync = "Enabled" if gsync else "Disabled"
        return [
            (
                "Counter-Strike 2 manual: set NVIDIA Reflex to Enabled "
                "(Enabled + Boost is optional); keep 'Wait for Vertical Sync' "
                f"{vsync} and Display Mode Fullscreen. ABSO does not write or "
                "verify these native settings."
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
            "VRR OFF; tearing expected). Requests driver LLM Off; set native "
            "Reflex Enabled, with Boost optional. Native settings are manual."
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
    """No-sync profile that enables Windows HDR; game HDR output is unverified."""

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
            "on (VSync OFF, VRR OFF; tearing expected). Game HDR output is "
            "unverified. Set native Reflex Enabled, with Boost optional."
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
                # Existing SDR-white preference, not panel calibration.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                # Retain this lane's existing color-management policy.
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
            "Fullscreen G-SYNC SDR Counter-Strike 2 lane. Set native VSync "
            "On and Reflex Enabled, with Boost optional. Driver refresh-minus-"
            "three cap is a fallback ceiling; confirm G-SYNC in-game."
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

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return "counter-strike-2-gsync-capture"

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Counter-Strike 2",
                # Managed fallback ceiling. Reflex can pace FPS lower; this
                # does not prove runtime presentation or eliminate all stalls.
                "auto_vrr_fps_cap": True,
                # Fullscreen-only VRR matches the native Fullscreen guidance.
                "global_vrr_mode": "fullscreen_only",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                # Existing desaturation preference, not a gamut transform.
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


class CounterStrike2GSyncCaptureProfile(CounterStrike2GSyncProfile):
    """Streaming-safe borderless sibling of the CS2 G-SYNC SDR lane."""

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-gsync-capture"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - GSYNC SDR Streaming"

    @property
    def description(self) -> str:
        return (
            "SDR G-SYNC lane on the borderless windowed path; preserves OBS, "
            "Medal, RTSS, and overlays and keeps game CPU/I/O priority at "
            "Normal. Set native VSync On and Reflex Enabled, with Boost "
            "optional; capture performance still needs measurement."
        )

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements()

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return None

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> None:
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        return fso_overrides(_CS2_EXECUTABLES, disabled=False)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._variant_overrides(),
            _STREAMING_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return _streaming_display_mode_rows(super().get_in_game_settings())

    def get_post_apply_notes(self) -> list[str]:
        return [
            "Counter-Strike 2 streaming manual: use Fullscreen Windowed, set "
            "NVIDIA Reflex to Enabled (Enabled + Boost is optional), and keep "
            "Wait for Vertical Sync Enabled in-game. Confirm G-SYNC in CS2; "
            "ABSO does not write or verify native settings. OBS and overlay "
            "processes remain available."
        ]


class CounterStrike2GSyncHDRProfile(_CounterStrike2BaseProfile):
    """Fullscreen G-SYNC with Windows HDR on; game HDR output is unverified."""

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-gsync-hdr"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - GSYNC HDR"

    @property
    def description(self) -> str:
        return (
            "Fullscreen G-SYNC Counter-Strike 2 lane with Windows HDR on; "
            "game HDR output is unverified. Set native VSync On and Reflex "
            "Enabled, with Boost optional; confirm G-SYNC in-game."
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
    """Streaming-safe borderless sibling of the CS2 G-SYNC HDR lane.

    Same VRR + Windows HDR policy as
    :class:`CounterStrike2GSyncHDRProfile`, with two deliberate differences:

    - The launch-time janitor keeps the capture / overlay / peripheral stack
      alive (Medal, OBS, RTSS, Discord overlay, NVIDIA Share, G HUB, iCUE)
      instead of stopping it for frame-time headroom.
    - VRR runs on the Win11 borderless windowed flip path
      (``fullscreen_and_windowed`` + windowed optimizations) rather than the
      strict fullscreen-only path, because the overlay-free display-path gate
      is what would otherwise block apply while a recorder is running.

    Game CPU and I/O priority stay at Normal. Capture performance is unmeasured.
    """

    @property
    def is_capture_safe(self) -> bool:
        return True

    @property
    def profile_id(self) -> str:
        return "counter-strike-2-gsync-hdr-capture"

    @property
    def display_name(self) -> str:
        return "Counter-Strike 2 - GSYNC HDR Streaming"

    @property
    def description(self) -> str:
        return (
            "Windows HDR G-SYNC lane on the borderless windowed path; "
            "preserves OBS, Medal, RTSS, and overlays and keeps game CPU/I/O "
            "priority at Normal. Set native VSync On and Reflex Enabled, with "
            "Boost optional. Game HDR output and capture performance are unverified."
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
    def mixed_refresh_safe_fallback_profile_id(self) -> None:
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Clear a stale FSO-disable entry left by an earlier CS2 profile.
        return fso_overrides(_CS2_EXECUTABLES, disabled=False)

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(
            super()._variant_overrides(),
            _STREAMING_WINDOWED_VRR_OVERRIDES,
        )

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return _streaming_display_mode_rows(super().get_in_game_settings())

    def get_post_apply_notes(self) -> list[str]:
        return [
            (
                "Counter-Strike 2 streaming manual: use Fullscreen Windowed, "
                "set NVIDIA Reflex to Enabled (Enabled + Boost is optional), "
                "and keep Wait for Vertical Sync Enabled in-game. Confirm "
                "G-SYNC in CS2; ABSO does not write or verify native settings. "
                "OBS and overlay processes remain available."
            ),
            (
                "Streaming color: default to SDR Streaming for an SDR destination. "
                "Use HDR Streaming only when OBS/output color space or tone mapping "
                "is already intentionally configured; ABSO does not change OBS settings."
            ),
        ]
