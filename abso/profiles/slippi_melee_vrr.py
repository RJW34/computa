"""Slippi Melee (Super Smash Bros. Melee) VRR/G-Sync profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class SlippiMeleeVRRProfile(BaseProfile):
    """Optimization profile for Slippi Melee with G-Sync/VRR enabled.

    Focus: Tear-free competitive play with near-minimum latency.
    Uses "Quick Frame Transport" (QFT) benefits of high-refresh displays.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee-vrr"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (G-Sync)"

    @property
    def description(self) -> str:
        return "Tear-free G-Sync optimization (recommended for 240Hz+)"

    @property
    def optimization_target(self) -> str:
        return "vrr_optimal"

    @property
    def executable_hints(self) -> list[str]:
        return ["Slippi Dolphin.exe", "Dolphin.exe"]

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.dolphin import DolphinConfigHandler
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
            ProcessPriorityHandler(["Slippi Dolphin.exe", "Dolphin.exe"]),
            CNMSettingsHandler(),
            DolphinConfigHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,  # DX12 + HAGS is critical for rendering performance
                "hdr": False,  # Melee is SDR
                "auto_hdr": False,
                "vrr_optimize": False, # Keep DISABLED - prevents windowed mode compositor lag
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
                "win32_priority_separation": 0x2A,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
            },
            "NvidiaSettingsHandler": {
                "preset": "vrr_optimal",
                # Applies: G-Sync ON, V-Sync ON, Low Latency ON
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
                "disable_mpo": True, # Safe to disable for Melee/Dolphin
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
            "CNMSettingsHandler": {
                "action": "stop",
            },
            "DolphinConfigHandler": {
                # Inherit standard low-latency configs
                "efb_scale": "1",
                "texture_scaling_factor": "1",
                "use_scaling_filter": "False",
                "use_deposterize": "False",
                "reduce_timing_dispersion": "True",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Nvidia Control Panel",
                "setting": "G-SYNC / V-SYNC",
                "value": "ON / ON",
                "reason": "Allows tear-free gameplay. Low Latency Mode + FPS Cap prevents V-Sync lag.",
            },
            {
                "category": "Dolphin Video",
                "setting": "V-Sync",
                "value": "OFF",
                "reason": "Must be OFF in Dolphin. Nvidia Driver handles the sync.",
            },
            {
                "category": "FPS Limit",
                "setting": "RTSS / Driver Limit",
                "value": "Refresh Rate - 3 (e.g. 297 for 300Hz)",
                "reason": "Keeps G-Sync active. Prevents hitting V-Sync ceiling.",
            }
        ]
