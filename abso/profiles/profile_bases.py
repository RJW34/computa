"""Shared profile bases and mixins to reduce drift across variants."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


OBS_EXECUTABLES = [
    "obs64.exe",
    "obs32.exe",
    "obs-browser.exe",
]

STREAMING_OBS_SETTINGS = {
    "stream_encoder": {
        "rate_control": "CBR",
        "bitrate": 6000,
        "preset": "p5",
        "multipass": "disabled",
        "profile": "high",
        "look-ahead": False,
        "psycho_aq": True,
    },
    "video": {
        "output_cx": 1920,
        "output_cy": 1080,
        "scale_type": "lanczos",
    },
    "low_latency": True,
}

STREAMING_GRAPHICS_OVERRIDES = {
    # Multi-monitor streaming: keep compositor-friendly defaults
    "disable_global_fso": False,
    "disable_mpo": False,
}


def merge_settings(
    base: dict[str, Any] | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if base:
        merged.update(base)
    if overrides:
        merged.update(overrides)
    return merged


def merge_settings_map(
    base_map: dict[str, dict[str, Any]],
    overrides_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for key, value in base_map.items():
        merged[key] = value.copy()
    for handler, overrides in overrides_map.items():
        merged[handler] = merge_settings(merged.get(handler, {}), overrides)
    return merged


def with_obs_executables(executables: list[str]) -> list[str]:
    merged = list(executables)
    for exe in OBS_EXECUTABLES:
        if exe not in merged:
            merged.append(exe)
    return merged


def _inject_obs_handlers(
    handlers: list[SettingsHandler],
    executables: list[str],
) -> list[SettingsHandler]:
    from abso.settings.obs import OBSSettingsHandler
    from abso.settings.process_priority import ProcessPriorityHandler

    merged: list[SettingsHandler] = []
    obs_added = False
    priority_replaced = False
    obs_executables = with_obs_executables(executables)

    for handler in handlers:
        if isinstance(handler, ProcessPriorityHandler):
            merged.append(ProcessPriorityHandler(obs_executables))
            priority_replaced = True
            if not obs_added:
                merged.append(OBSSettingsHandler())
                obs_added = True
            continue
        if isinstance(handler, OBSSettingsHandler):
            if not obs_added:
                merged.append(handler)
                obs_added = True
            continue
        merged.append(handler)

    if not priority_replaced:
        merged.append(ProcessPriorityHandler(obs_executables))
    if not obs_added:
        merged.append(OBSSettingsHandler())

    return merged


class OBSStreamingMixin:
    """Adds OBS settings + multi-monitor graphics overrides to a profile."""

    obs_settings: dict[str, Any] = STREAMING_OBS_SETTINGS
    graphics_overrides: dict[str, Any] = STREAMING_GRAPHICS_OVERRIDES

    def get_handlers(self) -> list[SettingsHandler]:
        base_handlers = super().get_handlers()
        return _inject_obs_handlers(base_handlers, self.executable_hints)

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        if handler_name == "OBSSettingsHandler":
            return self.obs_settings.copy()

        base = super().get_settings(handler_name)
        if handler_name == "GraphicsSettingsHandler":
            return merge_settings(base, self.graphics_overrides)
        return base


class Rivals2BaseProfile(BaseProfile):
    """Shared base for Rivals 2 profiles."""

    @property
    def executable_hints(self) -> list[str]:
        return [
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        ]

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def include_nvidia_notifications(self) -> bool:
        return False

    @property
    def include_rivals2_config(self) -> bool:
        return False

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

        handlers: list[SettingsHandler] = [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
        ]

        if self.include_nvidia_notifications:
            from abso.settings.nvidia_notifications import NvidiaNotificationHandler

            handlers.append(NvidiaNotificationHandler())

        handlers += [
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(self.executable_hints),
        ]

        if self.include_rivals2_config:
            from abso.settings.rivals2_config import Rivals2ConfigHandler

            handlers.append(Rivals2ConfigHandler())

        handlers.append(CNMSettingsHandler())
        handlers.append(ColorProfileSettingsHandler())
        return handlers

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                "vrr_optimize": False,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
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
                "cpu_priority": 3,
                "io_priority": 3,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        return settings_map.get(handler_name, {})


class EmulatorLatencyBaseProfile(BaseProfile):
    """Shared base for fixed-FPS emulator profiles."""

    @property
    def is_emulator_profile(self) -> bool:
        return True

    @property
    def is_sdr_only(self) -> bool:
        return True

    @property
    def allows_aggressive_settings(self) -> bool:
        return True

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

        handlers: list[SettingsHandler] = [
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
            ColorProfileSettingsHandler(),
        ]

        handlers.extend(self._additional_handlers())
        return handlers

    def _additional_handlers(self) -> list[SettingsHandler]:
        return []

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                "vrr_optimize": False,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
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
                "disable_mpo": True,
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
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "emulator",
            },
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        return settings_map.get(handler_name, {})


class WebGLBaseProfile(BaseProfile):
    """Shared base for WebGL/WebView2 performance profiles."""

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
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
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler(self.executable_hints),
            CNMSettingsHandler(),
            ColorProfileSettingsHandler(),
        ]

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 10,
                "network_throttling": 0xFFFFFFFF,
                "win32_priority_separation": 0x26,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 4,
                    "scheduling_category": "Medium",
                    "sfio_priority": "Normal",
                },
            },
            "NetworkSettingsHandler": {
                "disable_nagle": False,
                "preset": "default",
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
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
                "cpu_priority": 2,
                "io_priority": 2,
            },
            "CNMSettingsHandler": {
                "action": "stop",
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "casual",
            },
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        return settings_map.get(handler_name, {})


class ReflexShooterBaseProfile(BaseProfile):
    """Shared base for Reflex-enabled competitive shooters."""

    @property
    def optimization_target(self) -> str:
        return "low_latency_high_fps"

    @property
    def requires_reflex(self) -> bool:
        return True

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

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
            ProcessPriorityHandler(self.executable_hints),
            CNMSettingsHandler(),
            ColorProfileSettingsHandler(),
        ]

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                "vrr_optimize": False,
                "max_refresh_rate": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
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
                "preset": "reflex_game",
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
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
        }

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        return settings_map.get(handler_name, {})
