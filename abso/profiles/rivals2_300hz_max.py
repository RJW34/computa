"""Rivals of Aether 2 - 300Hz Maximum Performance Profile.

Target: Absolute minimum latency on 300Hz display.
When the game is being annoying and you need every advantage.

Settings:
- 300Hz fixed refresh
- LLM Ultra
- Ultimate Performance power plan
- No sync, no caps, no compromises
- All aggressive optimizations enabled

Use this when you're done messing around.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Rivals2_300HzMaxProfile(BaseProfile):
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
        return "Absolute minimum latency - 300Hz, LLM Ultra, Ultimate Performance"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return [
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        ]

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

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.services import ServicesSettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        return [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(self.executable_hints),
            CNMSettingsHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                "vrr_optimize": False,
                "refresh_rate": 300,  # Lock to 300Hz
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
                "disable_core_parking": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 0,
                "network_throttling": 0xFFFFFFFF,
                "win32_priority_separation": 0x2A,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
            },
            "NvidiaSettingsHandler": {
                "low_latency_mode": "ultra",  # ULTRA - maximum aggression
                "power_management": "prefer_max_performance",
                "vsync": "off",
                "gsync": "off",
                "max_frame_rate": "off",  # Uncapped - use in-game if needed
                "shader_cache": "unlimited",
                "threaded_optimization": "auto",
                "triple_buffering": "off",
                "game_name": "Rivals 2 300Hz Max",
                "vrr_override": "off",
                "vrr_requested_state": "off",
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": True,
                "disable_mpo": False,
            },
            "ServicesSettingsHandler": {
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                "gpu_priority": 8,
                "cpu_priority": 3,  # High
                "io_priority": 3,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
        }

        return settings_map.get(handler_name, {})

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
                "value": "Ultra",
                "reason": "Maximum frame queue reduction.",
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
