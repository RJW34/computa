"""Diablo 4 profiles."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class _Diablo4BaseProfile(BaseProfile):
    """Shared Diablo 4 profile defaults."""

    @property
    def optimization_target(self) -> str:
        return "balanced"

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def executable_hints(self) -> list[str]:
        return ["Diablo IV.exe"]

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Diablo IV"

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
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(["Diablo IV.exe"]),
            CNMSettingsHandler(),
            ColorProfileSettingsHandler(),
        ]

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "windowed_optimizations": False,
                "max_refresh_rate": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 10,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                },
            },
            "NvidiaSettingsHandler": {
                "preset": "vrr_diablo4",
                "vsync": "on",
                "auto_vrr_fps_cap": True,
                "global_vrr_mode": "fullscreen_only",
            },
            "NetworkSettingsHandler": {
                "disable_nagle": False,
                "preset": "default",
            },
            "MouseSettingsHandler": {
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
            },
            "MemorySettingsHandler": {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
            "ServicesSettingsHandler": {
                "services": {
                    "SysMain": {"start_type": 4, "stop": True},
                    "DiagTrack": {"start_type": 4, "stop": True},
                },
            },
            "ProcessPriorityHandler": {
                "gpu_priority": 8,
                "cpu_priority": 2,
                "io_priority": 2,
            },
        }

        settings_map.update(self._variant_overrides())
        return settings_map.get(handler_name, {})

    def _common_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "Matches the fullscreen VRR path this profile applies.",
            },
            {
                "category": "Display",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost",
                "reason": "Diablo 4 has native Reflex, so ABSO keeps driver LLM off.",
            },
            {
                "category": "Display",
                "setting": "VSync (in-game)",
                "value": "Off",
                "reason": "Keep synchronization in the driver VRR safety-net path, not in the game.",
            },
            {
                "category": "Display",
                "setting": "Foreground FPS Limit",
                "value": "Unlimited",
                "reason": "ABSO now makes the driver cap authoritative for this VRR lane.",
            },
            {
                "category": "Graphics",
                "setting": "DLSS/FSR",
                "value": "Quality or Balanced",
                "reason": "Good visual quality with performance headroom during heavy fights.",
            },
            {
                "category": "Graphics",
                "setting": "Overall Quality",
                "value": "Adjust based on GPU",
                "reason": "Stable frame times matter more than maxing every setting.",
            },
            {
                "category": "Graphics",
                "setting": "Effects",
                "value": "Medium-High",
                "reason": "High effects can cause frame drops in dense combat.",
            },
        ]


class Diablo4Profile(_Diablo4BaseProfile):
    """Diablo 4 HDR profile."""

    @property
    def profile_id(self) -> str:
        return "diablo4"

    @property
    def display_name(self) -> str:
        return "Diablo 4 - HDR"

    @property
    def description(self) -> str:
        return "Balanced Diablo 4 HDR profile with Reflex and VRR"

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": True,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "cinematic",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "On",
                "reason": "Diablo 4 exposes native HDR controls in LocalPrefs.txt on this machine.",
            },
            {
                "category": "Display",
                "setting": "HDR Paper White / Max Nits",
                "value": "Tune to your panel",
                "reason": "Use the game's native HDR calibration rather than Auto HDR.",
            },
            *self._common_in_game_settings(),
        ]


class Diablo4SDRProfile(_Diablo4BaseProfile):
    """Diablo 4 SDR profile."""

    @property
    def profile_id(self) -> str:
        return "diablo4-sdr"

    @property
    def display_name(self) -> str:
        return "Diablo 4 - SDR"

    @property
    def description(self) -> str:
        return "Balanced Diablo 4 SDR profile with Reflex and VRR"

    @property
    def is_sdr_only(self) -> bool:
        return True

    def _variant_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "hdr": False,
                "auto_hdr": False,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 45,
                "show_osd_guidance": True,
                "game_type": "cinematic",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Display",
                "setting": "HDR",
                "value": "Off",
                "reason": "Use this variant when you want the SDR path or do not have an HDR display active.",
            },
            *self._common_in_game_settings(),
        ]
