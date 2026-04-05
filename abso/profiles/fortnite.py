"""Fortnite profile."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import ReflexShooterBaseProfile


class FortniteProfile(ReflexShooterBaseProfile):
    """Optimization profile for Fortnite.

    Focus: Low latency, high FPS competitive settings with NVIDIA Reflex.
    """

    @property
    def profile_id(self) -> str:
        return "fortnite"

    @property
    def display_name(self) -> str:
        return "Fortnite"

    @property
    def description(self) -> str:
        return "Low latency, high FPS competitive settings with Reflex"

    @property
    def executable_hints(self) -> list[str]:
        return [
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        ]

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Fortnite"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "Fortnite (Streaming)",
        ]

    # === Validation Metadata Overrides ===

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Fortnite primarily uses DirectX 12 for competitive play."""
        return "dx12"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen (Exclusive)",
                "reason": "Lowest latency path vs windowed or borderless.",
            },
            {
                "category": "Display",
                "setting": "VSync",
                "value": "Off",
                "reason": "Disable sync latency. Use VRR + FPS cap if you prefer tear-free.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost",
                "reason": "Reflex controls the render queue more effectively than driver LLM.",
            },
            {
                "category": "Display",
                "setting": "Frame Rate Limit",
                "value": "Refresh rate - 3 (VRR) or Unlimited (no sync)",
                "reason": "Cap below refresh for G-Sync safety net; otherwise uncapped for minimum latency.",
            },
            {
                "category": "Graphics",
                "setting": "Rendering Mode",
                "value": "DirectX 12 (recommended) or Performance Mode",
                "reason": "DX12 offers stable frame pacing; Performance Mode maximizes FPS on weaker GPUs.",
            },
            {
                "category": "Graphics",
                "setting": "Multithreaded Rendering",
                "value": "On",
                "reason": "Better CPU utilization and frame time consistency.",
            },
            {
                "category": "Graphics",
                "setting": "3D Resolution / DLSS",
                "value": "100% or DLSS Performance if GPU-bound",
                "reason": "Maintain high FPS while keeping input latency low.",
            },
            {
                "category": "Graphics",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Reduces visual latency and improves clarity during fast flicks.",
            },
            {
                "category": "Graphics",
                "setting": "Shadows / Effects",
                "value": "Low",
                "reason": "Minimize frame time spikes in busy endgames.",
            },
            {
                "category": "Content",
                "setting": "High Resolution Textures",
                "value": "Off",
                "reason": "Avoids texture streaming hitches and VRAM spikes.",
            },
        ]


