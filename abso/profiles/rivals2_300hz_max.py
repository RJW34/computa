"""Rivals of Aether 2 - 300Hz Maximum Performance Profile.

Target: Absolute minimum latency on 300Hz display.
When the game is being annoying and you need every advantage.

Settings:
- 300Hz fixed refresh
- LLM ON (Ultra has no effect in DX12/UE5)
- Ultimate Performance power plan
- No sync, no caps, no compromises
- All aggressive optimizations enabled

Use this when you're done messing around.
"""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import Rivals2BaseProfile



class Rivals2_300HzMaxProfile(Rivals2BaseProfile):
    """Maximum performance profile for Rivals 2 at 300Hz.

    No compromises. Everything maxed.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-300hz-max"

    @property
    def display_name(self) -> str:
        return "Rivals 2: 300Hz Maximum"

    @property
    def description(self) -> str:
        return "Absolute minimum latency - 300Hz, no sync, Ultimate Performance"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return super().executable_hints

    @property
    def is_online_profile(self) -> bool:
        return False

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def allows_aggressive_settings(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "refresh_rate": 300,  # Lock to 300Hz
            },
            "PowerSettingsHandler": {
                "processor_min_state": 100,
            },
            "NvidiaSettingsHandler": {
                # Rivals 2 is DX12/UE5 — LLM Ultra has no effect (DX9/DX11 only).
                "low_latency_mode": "on",
                "power_management": "prefer_max_performance",
                "vsync": "off",
                "vsync_tear_control": "disable",
                "vrr_app_override": "force_off",
                "max_frame_rate": "off",  # Uncapped
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF — UE5 driver contention
                "triple_buffering": "off",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Profile",
                "setting": "Mode",
                "value": "300Hz MAXIMUM PERFORMANCE",
                "reason": "No compromises. Everything maxed.",
            },
            {
                "category": "Display",
                "setting": "Refresh Rate",
                "value": "300Hz (locked)",
                "reason": "Maximum refresh for minimum scanout latency.",
            },
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "True exclusive for lowest latency.",
            },
            {
                "category": "NVIDIA",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Reduces pre-render queue. Ultra has no effect in DX12/UE5 "
                    "(only works in DX9/DX11)."
                ),
            },
            {
                "category": "NVIDIA",
                "setting": "VSync / G-SYNC",
                "value": "OFF",
                "reason": "No sync overhead.",
            },
            {
                "category": "Power",
                "setting": "Power Plan",
                "value": "Ultimate Performance",
                "reason": "Maximum CPU/GPU clocks.",
            },
            {
                "category": "In-Game",
                "setting": "FPS Limit",
                "value": "Uncapped or 297",
                "reason": "Let it rip or cap at refresh-3 for headroom.",
            },
        ]



