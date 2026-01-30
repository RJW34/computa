"""Rivals of Aether 2 - OFFLINE / TRAINING profile.

Target: Training mode, local versus, CPU matches, replay review.
NO network rollback timing considerations.

Goals:
- Maximum frame pacing precision
- Minimum end-to-end latency
- Aggressive timing assumptions allowed

NVCP Settings (per-game for Rivals2.exe):
- V-Sync: FAST
- Low Latency Mode: ULTRA
- Max Frame Rate: ENABLED (Refresh - 3, e.g., 297 for 300Hz)
- Power Management: Prefer Maximum Performance
- Threaded Optimization: Auto

External Tools: RTSS, frame pacing hooks ALLOWED.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Rivals2OfflineProfile(BaseProfile):
    """Optimization profile for Rivals 2 OFFLINE / TRAINING play.

    Aggressive low-latency profile for:
    - Training mode
    - Local versus
    - CPU matches
    - Replay review

    NOT suitable for online play - rollback netcode requires different timing.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-offline"

    @property
    def display_name(self) -> str:
        return "Rivals 2: Offline / Training"

    @property
    def description(self) -> str:
        return "Maximum latency reduction for training/local play (NOT for online)"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency_offline"

    @property
    def executable_hints(self) -> list[str]:
        return [
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        ]

    # === Validation Metadata Overrides ===

    @property
    def is_online_profile(self) -> bool:
        """This is explicitly an OFFLINE profile - no rollback protection needed."""
        return False

    @property
    def is_sdr_only(self) -> bool:
        """Rivals 2 is SDR-only."""
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Rivals 2 uses DirectX 12 (UE5)."""
        return "dx12"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Offline profiles allow aggressive latency settings."""
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
        """Get aggressive low-latency settings for offline play."""
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,  # Hardware Accelerated GPU Scheduling
                "hdr": False,  # Rivals 2 is SDR
                "auto_hdr": False,
                "vrr_optimize": False,  # Windows VRR OFF - adds latency
                "max_refresh_rate": True,  # Set display to max refresh rate
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
                # Aggressive timing allowed for offline
                "disable_core_parking": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 10,
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
                # Custom settings for OFFLINE profile
                "low_latency_mode": "ultra",  # ULTRA for offline
                "power_management": "prefer_max_performance",
                "vsync": "fast",  # FAST V-Sync for offline
                "max_frame_rate": "297",  # Refresh - 3 (for 300Hz)
                "shader_cache": "unlimited",
                "threaded_optimization": "auto",  # Auto for Rivals 2
                "triple_buffering": "off",
                "game_name": "Rivals 2 Offline",
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
                "disable_mpo": False,  # MPO enabled for VRR
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
                "cpu_priority": 3,  # High priority
                "io_priority": 3,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for OFFLINE play."""
        return [
            {
                "category": "=== OFFLINE PROFILE ===",
                "setting": "Use Case",
                "value": "Training, Local VS, CPU, Replays",
                "reason": "This profile is for OFFLINE play only. Use ONLINE profile for matchmaking.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Monitor Technology",
                "value": "G-SYNC",
                "reason": "Enable G-Sync for tear-free gameplay.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical Sync",
                "value": "Fast",
                "reason": "Fast V-Sync renders uncapped, discards incomplete frames.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "Ultra",
                "reason": "ULTRA for aggressive frame queue reduction in offline play.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "297 (Refresh - 3)",
                "reason": "Cap at refresh - 3 for G-Sync headroom. Adjust for your refresh rate.",
            },
            {
                "category": "In-Game Settings",
                "setting": "V-Sync",
                "value": "OFF",
                "reason": "Native engine frame pacing, driver handles sync.",
            },
            {
                "category": "External Tools",
                "setting": "RTSS",
                "value": "ALLOWED",
                "reason": "External limiters and frame pacing hooks are permitted for offline.",
            },
            {
                "category": "Validation",
                "setting": "Expected Behavior",
                "value": "Stable 297 FPS, no VRR disengagement",
                "reason": "FPS should hold at cap without oscillation or hitching.",
            },
        ]
