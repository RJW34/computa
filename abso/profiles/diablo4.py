"""Diablo 4 profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile
from abso.profiles.profile_bases import (
    build_standard_handlers,
    fso_overrides,
    merged_handler_settings,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class _Diablo4BaseProfile(BaseProfile):
    """Shared Diablo 4 profile defaults."""

    @property
    def optimization_target(self) -> str:
        return "balanced"

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def requires_reflex(self) -> bool:
        return True

    @property
    def enforces_reflex_in_config(self) -> bool:
        # Diablo4ConfigHandler writes the native Reflex key into
        # LocalPrefs.txt so the toggle is set without the user needing to
        # launch the game first.
        return True

    @property
    def executable_hints(self) -> list[str]:
        return ["Diablo IV.exe"]

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # D4's native HDR VRR lane wants the true exclusive path so the HDR
        # tone map runs in the game, not in DWM. Disable FSO per-exe to keep
        # the GPU off the compositor's borderless HDR shim.
        return fso_overrides(self.executable_hints)

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Diablo IV"

    @property
    def ai_agents(self) -> Literal["off", "on", "leave"]:
        # ARPG is latency-tolerant for input but the HDR tone-map pipeline
        # is still sensitive to background jitter — keep agents off during
        # the gaming session.
        return "off"

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.diablo4_config import Diablo4ConfigHandler

        return build_standard_handlers(
            self,
            include_mouse=True,
            include_cpu_affinity=False,
            additional_handlers=[Diablo4ConfigHandler()],
        )

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                # Diablo 4 profile targets fullscreen-only VRR. Do not force
                # the Win11 windowed compositor path unless a future borderless
                # variant opts in explicitly.
                "windowed_optimizations": False,
                "vrr_optimize": False,
                "max_refresh_rate": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
            },
            "RegistrySettingsHandler": {
                # Diablo IV is a cinematic ARPG, not a twitch shooter. Use the
                # Medium MMCSS scheduling category (same as productivity / emulator
                # profiles) instead of the High setting inherited by ReflexShooter
                # profiles — High can starve OBS / Discord encoder threads during
                # streamed sessions without delivering measurable latency benefit
                # on a non-twitch game. ``gpu_priority: 8`` is preserved because
                # GPU work for D4 still benefits from the elevated bucket.
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "Medium",
                },
            },
            "NvidiaSettingsHandler": {
                "preset": "vrr_diablo4",
                "vsync": "on",
                # Driver cap intentionally disabled. Diablo 4's native Foreground FPS
                # limiter (written by Diablo4ConfigHandler.auto_vrr_fps_cap) is the
                # single authoritative limiter per Blur Busters G-SYNC 101.
                "auto_vrr_fps_cap": False,
                "global_vrr_mode": "fullscreen_only",
            },
            "NetworkSettingsHandler": {
                "disable_nagle": False,
                "preset": "default",
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,
                "io_priority": 2,
            },
            "Diablo4ConfigHandler": {
                "window_mode": 1,
                "vsync": False,
                "reflex": True,
                "auto_refresh_rate": True,
                # In-game foreground cap at refresh - 3 via auto_vrr_fps_cap.
                # This is the single VRR limiter; the NVIDIA driver cap is off.
                # Blur Busters G-SYNC 101: in-game limiter has lower latency
                # than driver / NVCP / RTSS caps when the game exposes one.
                "auto_vrr_fps_cap": True,
                "limit_background_fps": True,
                "background_fps_limit": 60,
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return self._variant_overrides()

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)

    def _common_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Matches the fullscreen VRR path this profile applies.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On",
                "reason": "Diablo 4 exposes native Reflex in LocalPrefs.txt, so ABSO keeps driver LLM off.",
            },
            {
                "category": "Display",
                "setting": "VSync (in-game)",
                "value": "Off",
                "reason": "Keep synchronization in the driver VRR safety-net path, not in the game.",
            },
            {
                "category": "Display",
                "setting": "Foreground FPS Limit",
                "value": "refresh - 3 (e.g., 141 @ 144Hz, 237 @ 240Hz, 297 @ 300Hz)",
                "reason": "ABSO writes LimitForegroundFPS=1 and MaxForegroundFPS=<refresh-3> into LocalPrefs.txt (Blur Busters G-SYNC 101 convention). In-game limiter owns the VRR safety boundary; the NVIDIA driver cap is off.",
            },
            {
                "category": "Graphics",
                "setting": "DLSS/FSR",
                "value": "Quality or Balanced",
                "reason": "Good visual quality with performance headroom during heavy fights.",
            },
            {
                "category": "Graphics",
                "setting": "Overall Quality",
                "value": "Adjust based on GPU",
                "reason": "Stable frame times matter more than maxing every setting.",
            },
            {
                "category": "Graphics",
                "setting": "Effects",
                "value": "Medium-High",
                "reason": "High effects can cause frame drops in dense combat.",
            },
        ]


class Diablo4Profile(_Diablo4BaseProfile):
    """Diablo 4 HDR profile."""

    @property
    def profile_id(self) -> str:
        return "diablo4"

    @property
    def display_name(self) -> str:
        return "Diablo 4 - HDR"

    @property
    def description(self) -> str:
        return "Balanced Diablo 4 HDR profile with native LocalPrefs enforcement for Reflex, HDR, and VRR"

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "advanced_color": True,  # Win11 24H2+ WCG pairing
                "auto_hdr": False,
                # Paper-white ≈ 250 nits matches this profile's Diablo 4
                # in-game HDR brightness target for cinematic playback.
                "sdr_white_level_nits": 250,
            },
            "GraphicsSettingsHandler": {
                # Windows 11 24H2+ can silently re-enable ACM on wide-gamut
                # displays (especially after NVIDIA driver installs), which
                # clamps SDR content to sRGB system-wide and washes out the
                # cinematic look this profile targets. Assert ACM off.
                "disable_auto_color_management": True,
            },
            "Diablo4ConfigHandler": {
                "hdr_output": True,
                "hdr_black_point": 0.0001,
                "hdr_white_point": 1000.0,
                "hdr_brightness": 250.0,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "cinematic",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "On",
                "reason": "Use Diablo 4's native HDR controls in LocalPrefs.txt when the installed game and display path support HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Paper White / Max Nits",
                "value": "Start at 250 / 1000 and tune to your panel",
                "reason": "ABSO applies a sane native HDR baseline in LocalPrefs.txt; fine-tune from there if your panel needs it.",
            },
            *self._common_in_game_settings(),
        ]


class Diablo4SDRProfile(_Diablo4BaseProfile):
    """Diablo 4 SDR profile."""

    @property
    def profile_id(self) -> str:
        return "diablo4-sdr"

    @property
    def display_name(self) -> str:
        return "Diablo 4 - SDR"

    @property
    def description(self) -> str:
        return "Balanced Diablo 4 SDR profile with native LocalPrefs enforcement for Reflex and VRR"

    @property
    def is_sdr_only(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
            "Diablo4ConfigHandler": {
                "hdr_output": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 45,
                "show_osd_guidance": True,
                "game_type": "cinematic",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Off",
                "reason": "Use this variant when you want the SDR path or do not have an HDR display active.",
            },
            *self._common_in_game_settings(),
        ]
