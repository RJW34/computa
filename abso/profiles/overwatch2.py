"""Overwatch 2 profile."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile


class Overwatch2Profile(ReflexShooterBaseProfile):
    """Optimization profile for Overwatch 2.

    Focus: Low latency, high FPS competitive play with NVIDIA Reflex.
    Overwatch 2 uses DirectX 11 by default. Reflex On + Boost is recommended.
    """

    @property
    def profile_id(self) -> str:
        return "overwatch2"

    @property
    def display_name(self) -> str:
        return "Overwatch 2"

    @property
    def description(self) -> str:
        return "Low latency, high FPS competitive settings with Reflex"

    @property
    def executable_hints(self) -> list[str]:
        return ["Overwatch.exe"]

    # === Validation Metadata Overrides ===

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Overwatch 2 uses DirectX 11 by default."""
        return "dx11"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # OW2 has native HDR support
                "hdr": True,
            },
            "GraphicsSettingsHandler": {
                "disable_mpo": False,
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Lowest input latency path.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "Adds a frame of latency. Use Reflex instead.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex",
                "value": "Enabled + Boost",
                "reason": "Hardware-level latency reduction. Takes priority over driver LLM.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Cap",
                "value": "Match monitor Hz or Uncapped",
                "reason": "Cap at refresh rate - 3 if using G-Sync; otherwise uncapped.",
            },
            {
                "category": "Display",
                "setting": "Triple Buffering",
                "value": "Off",
                "reason": "Adds render queue depth. Not needed with Reflex.",
            },
            {
                "category": "Display",
                "setting": "Reduce Buffering",
                "value": "On",
                "reason": "Reduces render pipeline depth for lower latency.",
            },
            {
                "category": "Graphics",
                "setting": "Render Scale",
                "value": "100% (or 75% if GPU-bound)",
                "reason": "Native for clarity; lower if FPS-limited.",
            },
            {
                "category": "Graphics",
                "setting": "Dynamic Render Scale",
                "value": "Off",
                "reason": "Inconsistent frame times. Prefer fixed render scale.",
            },
            {
                "category": "Graphics",
                "setting": "DLSS / FSR",
                "value": "Off or Quality (if GPU-bound)",
                "reason": "Upscaling adds latency. Only use if needed to hit target FPS.",
            },
            {
                "category": "Graphics",
                "setting": "Texture Quality",
                "value": "High (if VRAM allows)",
                "reason": "Minimal FPS impact, better visual clarity for target identification.",
            },
            {
                "category": "Graphics",
                "setting": "Shadow Detail",
                "value": "Low or Medium",
                "reason": "Shadows are GPU-heavy with minimal competitive value.",
            },
            {
                "category": "Graphics",
                "setting": "Effects Detail",
                "value": "Low",
                "reason": "Reduces visual clutter and frame time spikes during team fights.",
            },
        ]
