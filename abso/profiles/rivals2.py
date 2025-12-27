"""Rivals of Aether 2 profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Rivals2Profile(BaseProfile):
    """Optimization profile for Rivals of Aether 2.

    Focus: Ultra-low input latency for competitive platform fighting.
    Similar to Melee optimization but for a native UE5 game.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2"

    @property
    def description(self) -> str:
        return "Ultra-low latency optimization for competitive play"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return ["RivalsofAether2.exe", "Rivals2.exe", "RivalsOfAether2-Win64-Shipping.exe"]

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.services import ServicesSettingsHandler
        from abso.settings.timer import TimerSettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

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
            ProcessPriorityHandler([
                "RivalsofAether2.exe",
                "Rivals2.exe",
                "RivalsOfAether2-Win64-Shipping.exe",
            ]),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,  # UE5 generally benefits from HAGS
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
                "win32_priority_separation": 0x2A,  # Short fixed quantum, max foreground boost
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
            },
            "NvidiaSettingsHandler": {
                # Ultra-low latency for competitive fighting game
                "preset": "minimum_latency",
                # - Low Latency Mode: Ultra
                # - VSync: Off
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited
                # - Threaded Optimization: On
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",  # TCP global optimizations
            },
            "TimerSettingsHandler": {
                # Precise scheduling for consistent frame pacing
                "resolution_ms": 0.5,
            },
            "MouseSettingsHandler": {
                # Disable acceleration for consistent muscle memory
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                # Disable FSO for true exclusive fullscreen
                "disable_global_fso": True,
                # UE5 can have MPO issues
                "disable_mpo": True,
            },
            "ServicesSettingsHandler": {
                # Disable background services for minimum hitches
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                # Keep kernel in RAM, optimize for applications
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                # High priority for the game executable
                "gpu_priority": 8,
                "cpu_priority": 3,  # High
                "io_priority": 3,   # High
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Video",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Exclusive fullscreen has lowest input latency.",
            },
            {
                "category": "Video",
                "setting": "VSync",
                "value": "Off",
                "reason": "Eliminates VSync input delay. Use Nvidia Reflex if available.",
            },
            {
                "category": "Video",
                "setting": "Frame Rate Limit",
                "value": "Unlimited or match monitor Hz",
                "reason": "Higher FPS = lower input latency in fighting games.",
            },
            {
                "category": "Video",
                "setting": "Nvidia Reflex",
                "value": "On + Boost (if available)",
                "reason": "Hardware-level latency reduction. Best option when supported.",
            },
            {
                "category": "Video",
                "setting": "Resolution Scale",
                "value": "100% (Native)",
                "reason": "Native resolution for sharpest visuals. Lower if GPU-limited.",
            },
            {
                "category": "Video",
                "setting": "Graphics Quality",
                "value": "Medium-High",
                "reason": "Prioritize stable FPS over visual fidelity for competitive play.",
            },
            {
                "category": "Video",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Obscures visual clarity in fast-paced combat.",
            },
            {
                "category": "Video",
                "setting": "Anti-Aliasing",
                "value": "TAA or DLAA",
                "reason": "UE5 uses TAA-based AA. Disable if it causes ghosting.",
            },
            {
                "category": "Audio",
                "setting": "Audio Latency",
                "value": "Lowest stable setting",
                "reason": "Audio cues are important for reactions.",
            },
            {
                "category": "Controller",
                "setting": "Input Method",
                "value": "Direct connection (not Bluetooth)",
                "reason": "Wired/USB dongle has lower latency than Bluetooth.",
            },
        ]
