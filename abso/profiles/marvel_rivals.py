"""Marvel Rivals profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile, merge_settings_map


class _MarvelRivalsBaseProfile(ReflexShooterBaseProfile):
    """Shared Marvel Rivals profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return [
            "Marvel.exe",
            "Marvel-Win64-Shipping.exe",
        ]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    def get_handlers(self):
        from abso.settings.marvel_rivals_config import MarvelRivalsConfigHandler

        return [*super().get_handlers(), MarvelRivalsConfigHandler()]

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                "preset": "reflex_gsync",
                "profile_name": "Marvel Rivals",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_only",
            },
            "MarvelRivalsConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                "nvidia_reflex": True,
                "auto_vrr_fps_cap": True,
            },
        }

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(self._shared_overrides(), self._variant_overrides())

    def _common_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Best match for the profile's G-SYNC fullscreen path and lowest presentation overhead.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off (in-game)",
                "reason": "Leave VSync to NVIDIA Control Panel as the VRR safety net; keep the in-game toggle off.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost",
                "reason": "Reflex should own queue control in Marvel Rivals; the profile disables driver LLM to avoid overlap.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Auto (refresh rate - 3, so 297 on this 300 Hz monitor)",
                "reason": "Keeps G-SYNC active and prevents NVCP VSync from engaging while preserving tear-free latency.",
            },
            {
                "category": "Display",
                "setting": "Frame Generation",
                "value": "Off for ranked / competitive",
                "reason": "Frame generation lifts reported FPS, but it is not the cleanest low-latency path for a competitive shooter.",
            },
            {
                "category": "Graphics",
                "setting": "Upscaling",
                "value": "DLSS Quality or Balanced",
                "reason": "This build ships DLSS, XeSS, and AMD upscaling support; on an RTX 4070, DLSS is the best performance lever if native render cannot hold target cap.",
            },
            {
                "category": "Graphics",
                "setting": "Performance Optimization (Beta)",
                "value": "A/B test On vs Off on your hardware",
                "reason": (
                    "Marvel Rivals added an experimental PC optimization toggle in March 2026. "
                    "Keep the setting that improves 1% lows and frametime consistency on your system."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Shadow / Effects / Post Processing",
                "value": "Low",
                "reason": "Heavy fights and destruction are where frame-time spikes happen; low competitive settings keep the frame queue cleaner.",
            },
            {
                "category": "Graphics",
                "setting": "Textures",
                "value": "Medium",
                "reason": "A 12 GB RTX 4070 can handle more, but medium is the safer performance-first choice during long sessions and new patches.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur / Film Grain / Chromatic Aberration",
                "value": "Off",
                "reason": "Reduces visual noise and preserves target clarity during fast tracking.",
            },
        ]


class MarvelRivalsSDRProfile(_MarvelRivalsBaseProfile):
    """Marvel Rivals SDR competitive profile."""

    @property
    def profile_id(self) -> str:
        return "marvel-rivals-sdr"

    @property
    def display_name(self) -> str:
        return "Marvel Rivals - SDR"

    @property
    def description(self) -> str:
        return "Best-performance SDR profile for 1440p high-refresh competitive play"

    @property
    def is_sdr_only(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 45,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "MarvelRivalsConfigHandler": {
                "hdr_output": False,
                "hdr_nits": 1000,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Off",
                "reason": "This variant keeps the cleaner SDR path that is already active on this PC.",
            },
            {
                "category": "Display",
                "setting": "Color Space",
                "value": "SDR / default gamut",
                "reason": "Matches the profile's sRGB clamp and avoids wide-gamut oversaturation in SDR.",
            },
            *self._common_in_game_settings(),
        ]


class MarvelRivalsHDRProfile(_MarvelRivalsBaseProfile):
    """Marvel Rivals HDR competitive profile."""

    @property
    def profile_id(self) -> str:
        return "marvel-rivals-hdr"

    @property
    def display_name(self) -> str:
        return "Marvel Rivals - HDR"

    @property
    def description(self) -> str:
        return "Best-performance HDR profile for OLED / high-refresh competitive play"

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "MarvelRivalsConfigHandler": {
                "hdr_output": True,
                "hdr_nits": 1000,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "On",
                "reason": "This PC's primary display reports HDR capability, so the HDR path can stay active without using Auto HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Calibration",
                "value": "Calibrate paper white / peak brightness to the monitor",
                "reason": "Keep HDR enabled, but tune it once in-game so you do not give away visibility for the sake of raw brightness.",
            },
            *self._common_in_game_settings(),
        ]
