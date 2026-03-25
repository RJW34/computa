"""Diablo 4 profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Diablo4Profile(BaseProfile):
    """Optimization profile for Diablo 4.

    Focus: Stable FPS with good visual quality. Less latency-critical than shooters.
    """

    @property
    def profile_id(self) -> str:
        return "diablo4"

    @property
    def display_name(self) -> str:
        return "Diablo 4"

    @property
    def description(self) -> str:
        return "Balanced performance with visual quality"

    @property
    def optimization_target(self) -> str:
        return "balanced"

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Diablo 4 uses DirectX 12."""
        return "dx12"

    @property
    def executable_hints(self) -> list[str]:
        return ["Diablo IV.exe"]

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.color import ColorProfileSettingsHandler
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
            NetworkSettingsHandler(),  # Online ARPG benefits from network optimization
            MouseSettingsHandler(),     # Mouse settings benefit all games
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(["Diablo IV.exe"]),
            CNMSettingsHandler(),
            ColorProfileSettingsHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": True,  # Diablo 4 has native HDR support
                "auto_hdr": False,  # Native HDR, no Auto HDR needed
                "max_refresh_rate": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",  # Standardize on Ultimate
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 10,  # Some background task allowance
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                },
            },
            "NvidiaSettingsHandler": {
                # Diablo 4 has native NVIDIA Reflex — LLM must be OFF to avoid conflict.
                # Using vrr_diablo4 preset: LLM=off, threaded_opt=off for lower render latency.
                # Override VSync to adaptive: acts as safety net for non-G-Sync users
                # (VSync only engages when FPS exceeds refresh rate, otherwise stays off).
                "preset": "vrr_diablo4",
                "vsync": "adaptive",
            },
            "NetworkSettingsHandler": {
                # Online ARPG - keep OS defaults (avoid aggressive TCP tuning)
                "disable_nagle": False,
                "preset": "default",
            },
            "MouseSettingsHandler": {
                # Consistent mouse behavior helps with targeting
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                # Balanced: Keep FSO enabled (works well with modern games)
                # MPO can stay enabled for balanced profile
                "disable_global_fso": False,
            },
            "MemorySettingsHandler": {
                # Optimize for application performance
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "CNMSettingsHandler": {
                # Stop CNM during gaming to allow power optimizations
                "action": "stop",
            },
            "ServicesSettingsHandler": {
                # Less aggressive - only disable high-impact services
                "services": {
                    "SysMain": {"start_type": 4, "stop": True},  # Superfetch
                    "DiagTrack": {"start_type": 4, "stop": True},  # Telemetry
                },
            },
            "ProcessPriorityHandler": {
                "gpu_priority": 8,
                "cpu_priority": 2,  # Normal - Diablo 4 is less latency-critical
                "io_priority": 2,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",      # HDR game, let wide gamut work
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "cinematic",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Better performance than windowed modes.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost",
                "reason": (
                    "Diablo 4 has native Reflex. Driver LLM is OFF to avoid conflict. "
                    "Reflex handles latency more effectively at the application level."
                ),
            },
            {
                "category": "Display",
                "setting": "VSync (in-game)",
                "value": "Off",
                "reason": (
                    "Keep in-game VSync OFF. ABSO sets NVCP VSync to Adaptive as a "
                    "safety net — it only engages if FPS exceeds refresh rate, adding "
                    "zero latency when FPS is capped below refresh."
                ),
            },
            {
                "category": "Display",
                "setting": "Limit FPS",
                "value": "2-3 below monitor refresh rate",
                "reason": "G-Sync sweet spot to prevent VSync activation.",
            },
            {
                "category": "Display",
                "setting": "DLSS/FSR",
                "value": "Quality or Balanced",
                "reason": "Good visual quality with performance headroom.",
            },
            {
                "category": "Graphics",
                "setting": "Overall Quality",
                "value": "Adjust based on GPU",
                "reason": "Prioritize stable frame times over max settings.",
            },
            {
                "category": "Graphics",
                "setting": "Effects",
                "value": "Medium-High",
                "reason": "High effects can cause frame drops in dense combat.",
            },
        ]
