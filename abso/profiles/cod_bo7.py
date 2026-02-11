"""Call of Duty: Black Ops 7 profile."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile


class CodBo7Profile(ReflexShooterBaseProfile):
    """Optimization profile for Call of Duty: Black Ops 7.

    Focus: Low latency with stable high FPS.
    """

    @property
    def profile_id(self) -> str:
        return "cod-bo7"

    @property
    def display_name(self) -> str:
        return "Call of Duty: Black Ops 7"

    @property
    def description(self) -> str:
        return "Low latency, stable high FPS for competitive play"

    @property
    def executable_hints(self) -> list[str]:
        return ["cod.exe", "BlackOps7.exe"]

    # === Validation Metadata Overrides ===

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """CoD uses DirectX 12."""
        return "dx12"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # HDR enabled - OLED has negligible overhead, CoD has native HDR
                "hdr": True,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen Exclusive",
                "reason": "Lower input latency than borderless.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "Use Reflex instead for latency control.",
            },
            {
                "category": "Display",
                "setting": "Nvidia Reflex Low Latency",
                "value": "On + Boost",
                "reason": "Hardware-level latency reduction. Takes priority over driver settings.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Match monitor Hz or Unlimited",
                "reason": "Cap slightly below max if using G-Sync for tear-free.",
            },
            {
                "category": "Graphics",
                "setting": "Render Resolution",
                "value": "100% (or DLSS Performance if GPU-limited)",
                "reason": "Native looks best; DLSS adds minimal latency.",
            },
            {
                "category": "Graphics",
                "setting": "On-Demand Texture Streaming",
                "value": "Off",
                "reason": "Eliminates texture pop-in if you have VRAM headroom.",
            },
            {
                "category": "Graphics",
                "setting": "Shaders",
                "value": "Restart after first launch",
                "reason": "Let shaders fully compile to reduce stutter.",
            },
            {
                "category": "Audio",
                "setting": "Audio Mix",
                "value": "Headphones",
                "reason": "Use appropriate preset for your setup.",
            },
        ]


