"""Call of Duty: Black Ops 7 profile."""

from __future__ import annotations

from typing import Any, TYPE_CHECKING

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class CodBo7Profile(BaseProfile):
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
    def optimization_target(self) -> str:
        return "low_latency_high_fps"

    @property
    def executable_hints(self) -> list[str]:
        return ["cod.exe", "BlackOps7.exe"]

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.windows import WindowsSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.timer import TimerSettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.services import ServicesSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler

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
            ProcessPriorityHandler(["cod.exe", "BlackOps7.exe"]),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,  # Generally beneficial for modern games
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
                # Low latency with stable FPS preset
                "preset": "low_latency_high_fps",
                # Individual overrides (applied via preset):
                # - Low Latency Mode: On (not Ultra - may cause issues with Reflex)
                # - VSync: Off
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited
                # - Threaded Optimization: On
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",
            },
            "TimerSettingsHandler": {
                # Precise scheduling for consistent frame pacing
                # Note: Not input latency - CoD likely sets this automatically
                "resolution_ms": 0.5,
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": True,
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
                "cpu_priority": 3,
                "io_priority": 3,
            },
        }

        return settings_map.get(handler_name, {})

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
