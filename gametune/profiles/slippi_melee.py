"""Slippi Melee (Super Smash Bros. Melee via Dolphin) profile."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from gametune.profiles.base import BaseProfile

if TYPE_CHECKING:
    from gametune.settings.base import SettingsHandler


class SlippiMeleeProfile(BaseProfile):
    """Optimization profile for Super Smash Bros. Melee via Slippi Dolphin.

    Focus: Ultra-low input latency for competitive play.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi)"

    @property
    def description(self) -> str:
        return "Ultra-low latency optimization for competitive Melee"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return ["Slippi Dolphin.exe", "Dolphin.exe"]

    def get_handlers(self) -> list[SettingsHandler]:
        from gametune.settings.windows import WindowsSettingsHandler
        from gametune.settings.power import PowerSettingsHandler
        from gametune.settings.registry import RegistrySettingsHandler
        from gametune.settings.nvidia import NvidiaSettingsHandler
        from gametune.settings.network import NetworkSettingsHandler
        from gametune.settings.timer import TimerSettingsHandler
        from gametune.settings.mouse import MouseSettingsHandler
        from gametune.settings.graphics import GraphicsSettingsHandler
        from gametune.settings.services import ServicesSettingsHandler
        from gametune.settings.memory import MemorySettingsHandler
        from gametune.settings.process_priority import ProcessPriorityHandler

        return [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            TimerSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(["Slippi Dolphin.exe", "Dolphin.exe"]),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                # HAGS: Mixed reports for Dolphin, leave as user preference
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 0,
                "network_throttling": 0xFFFFFFFF,
                "win32_priority_separation": 0x28,  # Short quantum, max foreground boost
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
                "fullscreen_optimizations": {
                    # Will be populated with detected Dolphin path
                },
            },
            "NvidiaSettingsHandler": {
                # Ultra-low latency preset for competitive gaming
                "preset": "minimum_latency",
                # Individual overrides (applied via preset):
                # - Low Latency Mode: Ultra
                # - VSync: Off
                # - Power Management: Prefer Maximum Performance
                # - Max Frame Rate: Off
                # - Shader Cache: Unlimited
                # - Threaded Optimization: On
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",  # Also optimizes TCP global settings
            },
            "TimerSettingsHandler": {
                # Precise scheduling for consistent frame pacing
                # Note: Not input latency - most games set this automatically
                "resolution_ms": 0.5,
            },
            "MouseSettingsHandler": {
                # Disable acceleration for consistent muscle memory
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                # Disable FSO globally for true exclusive fullscreen
                "disable_global_fso": True,
                # MPO can cause issues with emulators, disable if stutter occurs
                # "disable_mpo": True,  # Uncomment if experiencing stutter
            },
            "ServicesSettingsHandler": {
                # Disable background services that can cause hitches
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                # Keep kernel in RAM, optimize for applications
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                # High priority for Dolphin executables
                "gpu_priority": 8,
                "cpu_priority": 3,  # High
                "io_priority": 3,   # High
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Graphics",
                "setting": "Backend",
                "value": "Vulkan",
                "reason": "Lowest latency on most systems. Test vs D3D12 on your hardware.",
            },
            {
                "category": "Graphics",
                "setting": "VSync",
                "value": "Off",
                "reason": "Eliminates VSync input delay.",
            },
            {
                "category": "Graphics",
                "setting": "Fullscreen Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Lower latency than borderless windowed.",
            },
            {
                "category": "Graphics",
                "setting": "Internal Resolution",
                "value": "Native (1x) or 2x",
                "reason": "Higher resolutions don't add latency but use more GPU.",
            },
            {
                "category": "Audio",
                "setting": "Backend",
                "value": "Cubeb or XAudio2",
                "reason": "Both are low-latency options.",
            },
            {
                "category": "Audio",
                "setting": "Latency",
                "value": "Lowest stable setting",
                "reason": "Lower is better, but too low causes crackling.",
            },
            {
                "category": "Controller",
                "setting": "Adapter Mode",
                "value": "Wii U / Switch mode",
                "reason": "Not PC mode. Native adapter support has lower latency.",
            },
            {
                "category": "Controller",
                "setting": "Background Input",
                "value": "On",
                "reason": "Allows input when alt-tabbed.",
            },
        ]
