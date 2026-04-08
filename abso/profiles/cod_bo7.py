"""Call of Duty: Black Ops 7 profiles."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile, merge_settings_map


class _CodBo7BaseProfile(ReflexShooterBaseProfile):
    """Shared Black Ops 7 profile defaults."""

    @property
    def executable_hints(self) -> list[str]:
        return ["cod.exe", "BlackOps7.exe"]

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Call of Duty: Black Ops 7"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return ["Call of Duty: Black Ops 7 - SDR", "Call of Duty: Black Ops 7 - HDR"]

    def _shared_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(self._shared_overrides(), self._variant_overrides())

    def _common_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen Exclusive",
                "reason": "Matches the competitive no-sync Reflex path this profile applies.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "Reflex owns latency control in this lane; do not reintroduce sync latency in-game.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost",
                "reason": "Application-level Reflex should own queue control for Call of Duty.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Unlimited",
                "reason": "This shipped profile is the competitive no-sync path, not a VRR cap variant.",
            },
            {
                "category": "Graphics",
                "setting": "Render Resolution",
                "value": "100% (or DLSS Performance if GPU-limited)",
                "reason": "Native looks best; DLSS is the fallback when you need more GPU headroom.",
            },
            {
                "category": "Graphics",
                "setting": "On-Demand Texture Streaming",
                "value": "Off",
                "reason": "Reduces unexpected texture IO churn during play.",
            },
            {
                "category": "Graphics",
                "setting": "Shaders",
                "value": "Restart after first launch",
                "reason": "Let shaders fully compile before judging frame-time quality.",
            },
        ]


class CodBo7Profile(_CodBo7BaseProfile):
    """Call of Duty HDR profile."""

    @property
    def profile_id(self) -> str:
        return "cod-bo7"

    @property
    def display_name(self) -> str:
        return "Call of Duty: Black Ops 7 - HDR"

    @property
    def description(self) -> str:
        return "Competitive Call of Duty HDR system path with manual in-game tuning still required"

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
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "On",
                "reason": "Use the game's native HDR path when you want wide-gamut/high-contrast presentation.",
            },
            *self._common_in_game_settings(),
            {
                "category": "Audio",
                "setting": "Audio Mix",
                "value": "Headphones",
                "reason": "Use the preset that matches your setup for positional clarity.",
            },
        ]


class CodBo7SDRProfile(_CodBo7BaseProfile):
    """Call of Duty SDR profile."""

    @property
    def profile_id(self) -> str:
        return "cod-bo7-sdr"

    @property
    def display_name(self) -> str:
        return "Call of Duty: Black Ops 7 - SDR"

    @property
    def description(self) -> str:
        return "Competitive Call of Duty SDR system path with manual in-game tuning still required"

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
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Off",
                "reason": "Use the SDR variant when you want the simpler SDR presentation path.",
            },
            *self._common_in_game_settings(),
            {
                "category": "Audio",
                "setting": "Audio Mix",
                "value": "Headphones",
                "reason": "Use the preset that matches your setup for positional clarity.",
            },
        ]
