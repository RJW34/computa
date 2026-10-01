"""Conservative Rocket League DX11 lanes with manual native settings.

These profiles manage supported Windows/NVIDIA presentation policy, not the
game's config. There is no native Reflex or PC HDR integration assumed here.
Defaults are starting points, not measured frame-time or latency optima.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile, DisplayPathRequirements
from abso.profiles.profile_bases import (
    build_standard_handlers,
    fso_overrides,
    merged_handler_settings,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class _RocketLeagueBaseProfile(BaseProfile):
    """Explicit policy avoids inheriting unrelated shooter or Reflex tweaks."""

    _gsync = False
    _hdr = False
    _capture = False

    @property
    def profile_id(self) -> str:
        return (
            "rocket-league"
            + ("-gsync" if self._gsync else "")
            + ("-hdr" if self._hdr else "")
            + ("-capture" if self._capture else "")
        )

    @property
    def display_name(self) -> str:
        sync = "GSYNC" if self._gsync else "No Sync"
        color = "HDR" if self._hdr else "SDR"
        capture = " Streaming" if self._capture else ""
        return f"Rocket League - {sync} {color}{capture}"

    @property
    def description(self) -> str:
        if self._capture:
            lane = (
                "Borderless G-SYNC lane that keeps capture and overlay processes "
                "available. Set native VSync On and FPS Unlimited manually."
            )
        elif self._gsync:
            lane = (
                "Fullscreen-only G-SYNC lane. Set native VSync Off and FPS "
                "Unlimited manually; ABSO requests driver VSync On."
            )
        else:
            lane = (
                "Fullscreen no-sync lane (VSync and VRR Off; tearing expected). "
                "Choose a sustainable native FPS limit manually."
            )
        color = (
            " Windows HDR On displays SDR content; native HDR/RTX HDR is not configured."
            if self._hdr else " Windows HDR Off."
        )
        return lane + color + " Driver LLM On is a heuristic; performance is unmeasured."

    @property
    def optimization_target(self) -> str:
        # Online metadata must be honest, even in the tearing-allowed lane.
        return "stable_online"

    @property
    def is_online_profile(self) -> bool:
        return True

    @property
    def requires_reflex(self) -> bool:
        return False

    @property
    def executable_hints(self) -> list[str]:
        return ["RocketLeague.exe"]

    @property
    def nvidia_binding_executables(self) -> list[str]:
        return ["RocketLeague.exe"]

    @property
    def external_launch_required_reason(self) -> str:
        return (
            "Launch Rocket League through Epic Games Launcher or Steam for "
            "launcher authentication and Easy Anti-Cheat startup. Direct process "
            "launch and game lifetime tracking are unsupported; apply the profile "
            "separately before launching from your platform client."
        )

    @property
    def nvidia_profile_name(self) -> str:
        return "Rocket League"

    @property
    def graphics_api(self) -> Literal["dx11"]:
        return "dx11"

    @property
    def is_sdr_only(self) -> bool:
        # This property describes the Windows display lane, not native support.
        return not self._hdr

    @property
    def is_capture_safe(self) -> bool:
        return self._capture

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return self._gsync

    @property
    def requires_exact_nvidia_binding(self) -> bool:
        return self._gsync

    @property
    def display_path_requirements(self) -> DisplayPathRequirements:
        return DisplayPathRequirements(require_overlay_free_path=self._gsync and not self._capture)

    @property
    def overlay_compatible_fallback_profile_id(self) -> str | None:
        return f"{self.profile_id}-capture" if self._gsync and not self._capture else None

    @property
    def mixed_refresh_safe_fallback_profile_id(self) -> str | None:
        if self._gsync and not self._capture:
            return "rocket-league-hdr" if self._hdr else "rocket-league"
        return None

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        return fso_overrides(self.executable_hints, disabled=False)

    def get_handlers(self) -> list[SettingsHandler]:
        # Standard handlers retain backup/restore coverage; empty policies
        # below request no additional power, input, color, or network tuning.
        return build_standard_handlers(self, include_mouse=False, include_cpu_affinity=True)

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        windows: dict[str, Any] = {
            "game_mode": True, "max_refresh_rate": True, "hdr": self._hdr, "auto_hdr": False,
        }
        if self._hdr:
            # Pair Windows advanced color with HDR, without inventing an SDR
            # white calibration. None is the handler's explicit leave-as-is.
            windows.update(advanced_color=True, sdr_white_level_nits=None)
        if self._capture:
            windows.update(windowed_optimizations=True, vrr_optimize=True)
        return {
            "WindowsSettingsHandler": windows,
            "GraphicsSettingsHandler": {"disable_global_fso": False},
            "RegistrySettingsHandler": {},
            "NvidiaSettingsHandler": {
                # LLM On agrees with both online safety gates. Ultra is a
                # vendor alternative for comparison, not our shipped target.
                "low_latency_mode": "on",
                "vsync": "on" if self._gsync else "off",
                "vsync_tear_control": "disable",
                "vsync_vrr_control": "enable" if self._gsync else "disable",
                "vrr_app_override": "allow" if self._gsync else "force_off",
                "global_vrr_mode": (
                    "fullscreen_and_windowed" if self._capture
                    else "fullscreen_only" if self._gsync else "off"
                ),
                # Off explicitly clears stale caps in no-sync. The NVIDIA
                # handler resolves the auto cap from the display for VRR lanes.
                "max_frame_rate": "off",
                "auto_vrr_fps_cap": self._gsync,
            },
            "ProcessPriorityHandler": {"cpu_priority": 2, "io_priority": 2},
            "CpuAffinityHandler": {"strategy": None},
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        if handler_name == "AmdSettingsHandler":
            # The shared helper derives AMD ULPS/Anti-Lag tweaks from LLM.
            # This NVIDIA-specific review does not justify those writes.
            return {}
        return merged_handler_settings(self, handler_name)

    def get_in_game_settings(self) -> list[dict[str, str]]:
        display_mode = "Borderless" if self._capture else "Fullscreen"
        native_vsync = "On" if self._capture else "Off"
        return [
            {
                "category": "Video",
                "setting": "Display Mode",
                "value": display_mode,
                "reason": (
                    "Set manually. The capture lane requests windowed G-SYNC and Windows "
                    "windowed optimizations so capture processes can remain available."
                    if self._capture else
                    "Set manually. Fullscreen Optimizations remain available; a menu label "
                    "does not prove exclusive presentation or live VRR engagement."
                ),
            },
            {
                "category": "Video",
                "setting": "Vertical Sync",
                "value": native_vsync,
                "reason": (
                    "Set On manually for the borderless G-SYNC path, following NVIDIA's "
                    "windowed VSync guidance. Driver VSync On alone does not prove engagement."
                    if self._capture else
                    "Set Off manually. The fullscreen G-SYNC lane uses driver VSync On; "
                    "the no-sync lane disables driver sync as well and accepts tearing."
                ),
            },
            {
                "category": "Video",
                "setting": "Frames Per Second",
                "value": "Unlimited (set manually)" if self._gsync else "Sustainable limit (set manually)",
                "reason": (
                    "ABSO requests a driver refresh - 3 ceiling (297 at 300 Hz). Set native "
                    "FPS to Unlimited to avoid a second configured limiter. This ceiling "
                    "does not promise 297 FPS, smooth frame times, or live VRR engagement."
                    if self._gsync else
                    "The driver limiter is Off. Choose a sustainable native limit using "
                    "representative frame-time measurements; Unlimited is optional, not "
                    "a guarantee of better responsiveness or smoothness."
                ),
            },
            {
                "category": "Driver (NVIDIA)",
                "setting": "Low Latency Mode",
                "value": "On (requested by ABSO)",
                "reason": (
                    "A conservative DX11 queueing heuristic, not a Rocket League benchmark. "
                    "No native Reflex is assumed. NVIDIA recommends Ultra as an alternative "
                    "when Reflex is unavailable; a controlled comparison would need a "
                    "separate reviewed policy because ABSO's online gates retain On. "
                    "If driver readback is unavailable, confirm this setting manually."
                ),
            },
            {
                "category": "Display (Windows)",
                "setting": "HDR",
                "value": "On (SDR game content in Windows HDR)" if self._hdr else "Off",
                "reason": (
                    "This lane enables Windows HDR and disables Auto HDR. It does not "
                    "configure native game HDR or RTX HDR. Existing SDR brightness, color "
                    "calibration, ICC association, and digital vibrance are preserved."
                    if self._hdr else
                    "This lane requests Windows HDR Off and Auto HDR Off. Color calibration "
                    "and digital vibrance remain user-owned; SDR is not a measured speed advantage."
                ),
            },
            {
                "category": "Preferences",
                "setting": "Graphics, controls, and Input Buffer",
                "value": "Preserve your settings",
                "reason": (
                    "ABSO does not write or verify Rocket League's native config. Graphics "
                    "quality trades rendering cost for image quality; controls and network "
                    "Input Buffer choices need individual evaluation, not a universal preset."
                ),
            },
        ]

    def get_post_apply_notes(self) -> list[str]:
        display_mode = "Borderless" if self._capture else "Fullscreen"
        native_vsync = "On" if self._capture else "Off"
        fps = "Unlimited" if self._gsync else "a sustainable manual limit"
        notes = [
            f"Rocket League manual: set Display Mode {display_mode}, Vertical Sync "
            f"{native_vsync}, and Frames Per Second to {fps}. ABSO does not write "
            "or verify native settings. Launch through Epic Games Launcher or Steam.",
            "Driver Low Latency Mode On is the conservative requested policy. No native "
            "Reflex is assumed; these settings have not been benchmarked on this machine.",
        ]
        if self._gsync:
            notes.append(
                "The managed driver refresh - 3 ceiling is 297 at 300 Hz; it does not "
                "guarantee that FPS or prove G-SYNC engagement. Confirm the live display path."
            )
        if self._hdr:
            notes.append(
                "Windows HDR is On with Auto HDR Off. Rocket League remains SDR content "
                "under this policy; native HDR/RTX HDR is not configured and calibration is preserved."
            )
        if self._capture:
            notes.append(
                "OBS and overlay processes remain available; encoder/output settings are "
                "unchanged. Prefer SDR Streaming for an SDR destination, or deliberately "
                "configure HDR capture and tone mapping for your chosen output."
            )
        return notes


class RocketLeagueProfile(_RocketLeagueBaseProfile):
    """No-sync SDR lane."""


class RocketLeagueHDRProfile(_RocketLeagueBaseProfile):
    """No-sync lane with Windows HDR."""

    _hdr = True


class RocketLeagueGSyncProfile(_RocketLeagueBaseProfile):
    """Fullscreen-only G-SYNC SDR lane."""

    _gsync = True


class RocketLeagueGSyncHDRProfile(RocketLeagueGSyncProfile):
    """Fullscreen-only G-SYNC lane with Windows HDR."""

    _hdr = True


class RocketLeagueGSyncCaptureProfile(RocketLeagueGSyncProfile):
    """Borderless G-SYNC SDR lane preserving capture processes."""

    _capture = True


class RocketLeagueGSyncHDRCaptureProfile(RocketLeagueGSyncHDRProfile):
    """Borderless G-SYNC lane with Windows HDR preserving capture processes."""

    _capture = True
