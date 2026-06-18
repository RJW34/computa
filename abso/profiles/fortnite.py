"""Fortnite profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import (
    ReflexShooterBaseProfile,
    fso_overrides,
    merge_settings_map,
)


class _FortniteBaseProfile(ReflexShooterBaseProfile):
    """Shared Fortnite profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return [
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        ]

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Competitive Fortnite runs exclusive-fullscreen (fullscreen_mode=0 in
        # GameUserSettings.ini). Disable FSO per-exe so Windows doesn't shunt
        # the shipping binary into the composited borderless path and steal
        # FPS from the Reflex/DX12 presentation path.
        return fso_overrides(self.executable_hints)

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Fortnite"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "Fortnite - HDR",
            "Fortnite (Streaming)",
            "Fortnite (Streaming HDR)",
        ]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    def get_handlers(self):
        from abso.settings.fortnite_config import FortniteConfigHandler

        return [*super().get_handlers(), FortniteConfigHandler()]

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # Honor the "No Sync" label at the driver level. The inherited
                # ReflexShooter base preset is reflex_game, which sets no
                # vrr_app_override and therefore leaves G-SYNC/VRR to the user's
                # global NVCP toggle. reflex_no_sync explicitly forces VRR off
                # (vrr_app_override=force_off + vsync_tear_control=disable) like
                # the OW2/Deadlock no-sync siblings, while still keeping driver
                # LLM off so in-game Reflex owns the render queue.
                "preset": "reflex_no_sync",
            },
            "FortniteConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                "frame_rate_limit": 0,
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
                "value": "Fullscreen (Exclusive)",
                "reason": "Matches the competitive no-sync path this profile actually applies.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "Keep sync latency out of the path for this Reflex-first profile.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost — ABSO already set driver LLM off; flip the in-game toggle to finish",
                "reason": "ABSO has already configured the driver side: NVIDIA LLM is OFF so the engine owns the render queue (Reflex's correct path). Fortnite's Reflex toggle lives in Fortnite's settings and there is no stable config key to write it from outside; manually flip 'NVIDIA Reflex Low Latency' to 'On + Boost' in the game once.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Unlimited",
                "reason": "This is the explicit no-sync Fortnite lane, not a VRR cap profile.",
            },
            {
                "category": "Graphics",
                "setting": "Rendering Mode",
                "value": "DirectX 12",
                "reason": "This profile is built around Fortnite's DX12 path for Reflex and modern presentation behavior.",
            },
            {
                "category": "Graphics",
                "setting": "Multithreaded Rendering",
                "value": "On",
                "reason": "Better CPU utilization and more stable frame delivery in stacked endgames.",
            },
            {
                "category": "Graphics",
                "setting": "3D Resolution / DLSS",
                "value": "100% or DLSS Performance if GPU-bound",
                "reason": "Keep frame times stable first; use DLSS only when needed to hold target FPS.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Reduces visual noise and preserves snap-tracking clarity.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Endgame effects spikes matter more than visual richness in the competitive lane.",
            },
            {
                "category": "Content",
                "setting": "High Resolution Textures",
                "value": "Off",
                "reason": "Avoids streaming hitches and unnecessary VRAM churn.",
            },
        ]


class FortniteProfile(_FortniteBaseProfile):
    """Fortnite SDR competitive profile."""

    @property
    def profile_id(self) -> str:
        return "fortnite"

    @property
    def display_name(self) -> str:
        return "Fortnite - SDR"

    @property
    def description(self) -> str:
        return (
            "Competitive SDR Fortnite profile with a no-sync latency path. "
            "Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
        )

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
            "FortniteConfigHandler": {
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
                "reason": "This variant intentionally stays on the SDR path.",
            },
            *self._common_in_game_settings(),
        ]


class FortniteHDRProfile(_FortniteBaseProfile):
    """Fortnite HDR competitive profile."""

    @property
    def profile_id(self) -> str:
        return "fortnite-hdr"

    @property
    def display_name(self) -> str:
        return "Fortnite - HDR"

    @property
    def description(self) -> str:
        return (
            "Competitive Fortnite HDR profile with a no-sync latency path. "
            "Keeps driver LLM off for Reflex; enable Reflex On + Boost in-game."
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
                # Paper-white ≈ 200 nits under HDR on OLED / Mini-LED.
                # Driver installs reset this slider; asserting it here
                # restores the correct SDR-in-HDR tone-mapping.
                "sdr_white_level_nits": 200,
            },
            "GraphicsSettingsHandler": {
                # Assert ACM off so Windows can't silently clamp wide-gamut
                # to sRGB after a driver re-enumeration.
                "disable_auto_color_management": True,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "FortniteConfigHandler": {
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
                "reason": "Use Fortnite's native HDR output path in GameUserSettings.ini when the installed build and display path support HDR.",
            },
            {
                "category": "Display",
                "setting": "HDR Peak Brightness / Nits",
                "value": "Start at 1000 nits or match your display peak",
                "reason": "Keep Windows HDR and Fortnite's native HDR output aligned.",
            },
            *self._common_in_game_settings(),
        ]
