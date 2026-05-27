"""Marvel Rivals profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import (
    ReflexShooterBaseProfile,
    fso_overrides,
    merge_settings_map,
)


class _MarvelRivalsBaseProfile(ReflexShooterBaseProfile):
    """Shared Marvel Rivals profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return [
            "Marvel.exe",
            "Marvel-Win64-Shipping.exe",
        ]

    @property
    def nvidia_binding_executables(self) -> list[str]:
        """Use the actual game binary for NVIDIA binding verification."""
        return ["Marvel-Win64-Shipping.exe"]

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Marvel Rivals competitive lane uses fullscreen_mode=0 (exclusive).
        # Disable FSO per-exe so the game cannot silently run through the
        # DWM compositor's borderless FSO shim and give up Reflex headroom.
        return fso_overrides(self.executable_hints)

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def enforces_reflex_in_config(self) -> bool:
        # MarvelRivalsConfigHandler writes bNvidiaReflex into
        # GameUserSettings.ini so the in-game Reflex toggle is pre-set.
        return True

    def get_handlers(self):
        from abso.settings.marvel_rivals_config import MarvelRivalsConfigHandler

        return [*super().get_handlers(), MarvelRivalsConfigHandler()]

    @property
    def allow_dual_limiter(self) -> bool:
        # Marvel Rivals lanes deliberately layer the in-game cap (authoritative,
        # Blur Busters-preferred) with the NVIDIA driver cap (safety net).
        # Both resolve to refresh - 3 so the effective cap is deterministic;
        # the driver cap catches any GameUserSettings drift the game writes
        # back on exit.
        return True

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
                "dynamic_resolution": False,
                "dlss_frame_generation": False,
                "fsr_frame_generation": False,
                "xe_frame_generation": False,
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
                "value": "Auto (refresh-scaled: e.g. 285 @ 300Hz, 233 @ 240Hz, 141 @ 144Hz)",
                "reason": "Set by ABSO using Blur Busters' 2026 scaled-margin formula. Keeps G-SYNC active and prevents NVCP VSync from engaging while preserving tear-free latency.",
            },
            {
                "category": "Display",
                "setting": "Frame Generation",
                "value": "Off for ranked / competitive (enforced for DLSS/FSR/Xe FG)",
                "reason": "Frame generation raises displayed FPS, but native rendered frames with Reflex are the cleaner low-latency path for a competitive shooter.",
            },
            {
                "category": "Display",
                "setting": "Dynamic Resolution",
                "value": "Off",
                "reason": "Keeps the render path deterministic so the VRR cap and in-game frame pacing remain predictable.",
            },
            {
                "category": "Graphics",
                "setting": "Upscaling",
                "value": "Use your GPU vendor's quality/balanced upscaler if GPU-bound",
                "reason": "Upscaling is the cleanest performance lever when native rendering cannot hold the VRR cap.",
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
                "reason": "Use a texture setting that fits your VRAM; lower it if you see streaming hitches or memory pressure.",
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
                "reason": "Use this variant when you want the cleaner SDR path or do not have HDR active.",
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
                "advanced_color": True,  # Win11 24H2+ WCG pairing
                "auto_hdr": False,
                # Paper-white ≈ 200 nits under HDR on OLED / Mini-LED.
                # Driver installs reset this slider; asserting it here
                # restores the correct SDR-in-HDR tone-mapping.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                # Keep ACM off so wide-gamut colors aren't clamped to sRGB
                # system-wide by Windows 11 24H2+ Auto Color Management.
                "disable_auto_color_management": True,
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
                "reason": "Use this variant when the active display path supports native HDR without relying on Auto HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Calibration",
                "value": "Calibrate paper white / peak brightness to the monitor",
                "reason": "Keep HDR enabled, but tune it once in-game so you do not give away visibility for the sake of raw brightness.",
            },
            *self._common_in_game_settings(),
        ]
