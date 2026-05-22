"""Shared profile bases and mixins to reduce drift across variants."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile
from abso.settings.registry import (
    WIN32_PRIORITY_GAMING_OFFLINE,
    WIN32_PRIORITY_GAMING_ONLINE,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


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


def inject_nvidia_profile_identity(
    profile: BaseProfile,
    handler_name: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Attach stable NVIDIA profile metadata when a profile declares it."""
    if handler_name != "NvidiaSettingsHandler" or not settings:
        return settings

    profile_name = profile.nvidia_profile_name
    profile_aliases = profile.nvidia_profile_aliases
    if not profile_name and not profile_aliases:
        return settings

    merged = settings.copy()
    if profile_name:
        merged.setdefault("profile_name", profile_name)
    if profile_aliases:
        merged.setdefault("profile_aliases", list(profile_aliases))
    return merged


def inject_fullscreen_optimizations(
    profile: BaseProfile,
    handler_name: str,
    settings: dict[str, Any],
) -> dict[str, Any]:
    """Merge per-exe FSO overrides into RegistrySettingsHandler settings.

    The profile declares ``fullscreen_optimizations_per_exe`` to force
    exclusive-fullscreen (or clear a prior exclusive lock) for specific
    executables; this helper keeps the routing in one place so every
    profile base inherits the behavior consistently.
    """
    import logging

    if handler_name != "RegistrySettingsHandler":
        return settings

    overrides = profile.fullscreen_optimizations_per_exe
    if not overrides:
        return settings

    merged = {k: v for k, v in settings.items()} if settings else {}
    raw_existing = merged.get("fullscreen_optimizations")

    if raw_existing is None:
        existing: dict[str, bool] = {}
    elif isinstance(raw_existing, dict):
        existing = {
            str(exe): bool(flag)
            for exe, flag in raw_existing.items()
            if isinstance(exe, str) and exe.strip()
        }
    else:
        # Do not silently drop the malformed value - log it so the profile
        # author can fix the declaration, then fall back to an empty dict
        # so the profile-declared overrides still take effect.
        logging.getLogger(__name__).warning(
            "RegistrySettingsHandler.fullscreen_optimizations had unexpected type %s for profile %s; ignoring existing value",
            type(raw_existing).__name__,
            getattr(profile, "profile_id", "<unknown>"),
        )
        existing = {}

    # Profile-declared overrides win over any base defaults.
    for exe, disabled in overrides.items():
        if not isinstance(exe, str) or not exe.strip():
            continue
        existing[str(exe)] = bool(disabled)

    merged["fullscreen_optimizations"] = existing
    return merged


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
    def xbox_mode(self) -> Literal["off", "on", "leave"]:
        # Rivals 2 family ships fullscreen_mode=0; the Xbox Mode shell layer
        # actively conflicts with the exclusive-fullscreen FSO override.
        return "off"

    @property
    def ai_agents(self) -> Literal["off", "on", "leave"]:
        return "off"

    @property
    def nvidia_binding_executables(self) -> list[str]:
        """Bind the stable NVIDIA family to the real shipping binary only."""
        return ["Rivals2-Win64-Shipping.exe"]

    @property
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Every Rivals 2 variant ships fullscreen_mode=0 in its GameUserSettings,
        # so the whole family wants Windows to keep the real shipping binary on
        # the true exclusive path. Disable FSO per-exe for the shipping binary
        # and the legacy detection aliases.
        exe_names = {
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        }
        return {exe: True for exe in exe_names}

    @property
    def allow_unverified_nvidia_profile_reuse(self) -> bool:
        """Permit safe reuse of ABSO-managed Rivals driver profiles.

        NVIDIA does not always enumerate custom-profile ownership cleanly for
        every driver branch, even when the stable family profile already exists.
        ABSO still fails closed on conflicts; this only relaxes the "existing
        bound profile, no conflicting owner" case.
        """
        return True

    @property
    def is_sdr_only(self) -> bool:
        # Rivals 2 variants choose SDR/HDR explicitly instead of relying on a
        # family-level SDR-only default.
        return False

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        return "dx12"

    @property
    def include_nvidia_notifications(self) -> bool:
        return False

    @property
    def include_rivals2_config(self) -> bool:
        return True

    @property
    def nvidia_profile_name(self) -> str:
        """Stable NVIDIA DRS profile identity for Rivals 2 variants.

        Rivals 2 does not have a reliable predefined NVIDIA profile like
        Overwatch 2. We intentionally collapse multiple ABSO variants onto a
        stable custom profile family so switching between Rivals profiles
        updates one bound driver profile instead of creating unbound leftovers.
        """
        return "Rivals 2 Online" if self.is_online_profile else "Rivals 2"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        """Legacy/custom NVIDIA profile names worth reusing when already bound."""
        if self.is_online_profile:
            candidates = [
                "Rivals 2 - Online No Sync",
                "Rivals 2 - Online GSYNC",
                "Rivals 2: Online / Matchmaking",
                "Rivals 2: Online G-SYNC",
                "Rivals 2 (Streaming)",
            ]
        else:
            candidates = [
                "Rivals2-Win64-Shipping.exe",
                "Rivals of Aether 2",
                "Rivals 2 - Offline No Sync",
                "Rivals 2 - Offline GSYNC",
                "Rivals 2: Offline / Training",
                "Rivals 2: G-SYNC",
                "Rivals 2: 300Hz Maximum",
                "Rivals 2: Tournament Sim (144Hz)",
            ]

        deduped: list[str] = []
        for name in candidates:
            if name != self.nvidia_profile_name and name not in deduped:
                deduped.append(name)
        return deduped

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.cpu_affinity import CpuAffinityHandler
        from abso.settings.display_range import DisplayColorRangeHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
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
        ]

        if self.include_legacy_tweaks:
            handlers.append(MemorySettingsHandler())

        handlers.append(ProcessPriorityHandler(self.executable_hints))
        handlers.append(CpuAffinityHandler(self.executable_hints))

        if self.include_rivals2_config:
            from abso.settings.rivals2_config import Rivals2ConfigHandler

            handlers.append(Rivals2ConfigHandler())

        handlers.append(ColorProfileSettingsHandler())
        handlers.append(DisplayColorRangeHandler())
        return handlers

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Verified settings — documented, measurable effect
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                # Win11 borderless-compositor settings. Kept True universally
                # (was False prior to 2026-05-21) so the profile honors its
                # ordering contract: strict / no-sync variants are at-least-
                # as-fast as capture variants regardless of in-game display
                # mode. True is a true no-op in real exclusive fullscreen
                # (DX11 swap chain doesn't go through Windows' upgrade path)
                # and a multi-ms win in borderless (flip-model upgrade + VRR-
                # aware compositing). The <1ms compositor-stays-warm cost in
                # exclusive (see windows.py::_get_vrr_optimize comment) is
                # accepted in exchange for not silently falling off a latency
                # cliff when the user is in borderless. Users committed to
                # pure-exclusive can override to False via abso.yaml
                # profile_overrides.windows.{windowed_optimizations,vrr_optimize}.
                "windowed_optimizations": True,
                "vrr_optimize": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "win32_priority_separation": WIN32_PRIORITY_GAMING_OFFLINE,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    # sfio_priority omitted — has no effect per Microsoft docs
                },
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
                "disable_global_fso": True,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 3,
                "io_priority": 3,
            },
            "CpuAffinityHandler": {
                # No affinity pinning by default. Intel officially discourages
                # hard affinity on hybrid CPUs (prevents Thread Director from
                # optimizing). Users can opt in via abso.yaml profile_overrides.
                "strategy": None,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            settings["RegistrySettingsHandler"]["system_responsiveness"] = 10
            settings["RegistrySettingsHandler"]["network_throttling"] = 0xFFFFFFFF
            settings["MemorySettingsHandler"] = {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            }

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        settings = settings_map.get(handler_name, {})
        settings = inject_nvidia_profile_identity(self, handler_name, settings)
        settings = inject_fullscreen_optimizations(self, handler_name, settings)
        return settings


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

    @property
    def xbox_mode(self) -> Literal["off", "on", "leave"]:
        # Slippi/Ryujinx run on tight fixed-rate budgets; shell-side mode
        # transitions break frame pacing.
        return "off"

    @property
    def ai_agents(self) -> Literal["off", "on", "leave"]:
        return "off"

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.cpu_affinity import CpuAffinityHandler
        from abso.settings.display_range import DisplayColorRangeHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        handlers: list[SettingsHandler] = [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
        ]

        if self.include_legacy_tweaks:
            handlers.append(MemorySettingsHandler())

        handlers += [
            ProcessPriorityHandler(self.executable_hints),
            CpuAffinityHandler(self.executable_hints),
            ColorProfileSettingsHandler(),
            DisplayColorRangeHandler(),
        ]

        handlers.extend(self._additional_handlers())
        return handlers

    def _additional_handlers(self) -> list[SettingsHandler]:
        return []

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Verified settings — documented, measurable effect
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                # Win11 borderless-compositor settings. Kept True universally
                # (was False prior to 2026-05-21) so the profile honors its
                # ordering contract: strict / no-sync variants are at-least-
                # as-fast as capture variants regardless of in-game display
                # mode. True is a true no-op in real exclusive fullscreen
                # (DX11 swap chain doesn't go through Windows' upgrade path)
                # and a multi-ms win in borderless (flip-model upgrade + VRR-
                # aware compositing). The <1ms compositor-stays-warm cost in
                # exclusive (see windows.py::_get_vrr_optimize comment) is
                # accepted in exchange for not silently falling off a latency
                # cliff when the user is in borderless. Users committed to
                # pure-exclusive can override to False via abso.yaml
                # profile_overrides.windows.{windowed_optimizations,vrr_optimize}.
                "windowed_optimizations": True,
                "vrr_optimize": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "win32_priority_separation": WIN32_PRIORITY_GAMING_OFFLINE,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    # sfio_priority omitted — has no effect per Microsoft docs
                },
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
                "disable_global_fso": True,
                # MPO is NOT disabled by default — it's required for G-SYNC/VRR
                # and toggling it requires a reboot. Only disable MPO in profiles
                # that explicitly need it (e.g., no-sync exclusive fullscreen profiles
                # where MPO compositor interference is measured and confirmed).
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 3,
                "io_priority": 3,
            },
            "CpuAffinityHandler": {
                # No affinity pinning by default. Intel officially discourages
                # hard affinity on hybrid CPUs (prevents Thread Director from
                # optimizing). Users can opt in via abso.yaml profile_overrides.
                "strategy": None,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "emulator",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            settings["RegistrySettingsHandler"]["system_responsiveness"] = 10
            settings["RegistrySettingsHandler"]["network_throttling"] = 0xFFFFFFFF
            settings["MemorySettingsHandler"] = {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            }

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        settings = settings_map.get(handler_name, {})
        settings = inject_nvidia_profile_identity(self, handler_name, settings)
        settings = inject_fullscreen_optimizations(self, handler_name, settings)
        return settings


class WebGLBaseProfile(BaseProfile):
    """Shared base for WebGL/WebView2 performance profiles."""

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.display_range import DisplayColorRangeHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        handlers = [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            GraphicsSettingsHandler(),
        ]

        if self.include_legacy_tweaks:
            handlers.append(MemorySettingsHandler())

        handlers += [
            ProcessPriorityHandler(self.executable_hints),
            ColorProfileSettingsHandler(),
            DisplayColorRangeHandler(),
        ]
        return handlers

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Verified settings — documented, measurable effect
        settings: dict[str, dict[str, Any]] = {
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
                "win32_priority_separation": WIN32_PRIORITY_GAMING_ONLINE,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 4,
                    "scheduling_category": "Medium",
                    # sfio_priority omitted — has no effect per Microsoft docs
                },
            },
            "NetworkSettingsHandler": {
                "disable_nagle": False,
                "preset": "default",
            },
            "GraphicsSettingsHandler": {
                "disable_global_fso": False,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 2,
                "io_priority": 2,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "casual",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            settings["RegistrySettingsHandler"]["system_responsiveness"] = 10
            settings["RegistrySettingsHandler"]["network_throttling"] = 0xFFFFFFFF
            settings["MemorySettingsHandler"] = {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            }

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        settings = settings_map.get(handler_name, {})
        settings = inject_nvidia_profile_identity(self, handler_name, settings)
        settings = inject_fullscreen_optimizations(self, handler_name, settings)
        return settings


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

    @property
    def xbox_mode(self) -> Literal["off", "on", "leave"]:
        # Reflex / FSE path: Xbox Mode's shell-side compositor swap is the
        # opposite of what we want. Keep it off across SDR/HDR/capture lanes.
        return "off"

    @property
    def ai_agents(self) -> Literal["off", "on", "leave"]:
        # Background agents (notably Researcher) wake schedulers mid-frame.
        # Reflex profiles cannot tolerate that jitter budget.
        return "off"

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.cpu_affinity import CpuAffinityHandler
        from abso.settings.display_range import DisplayColorRangeHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        handlers = [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
        ]

        if self.include_legacy_tweaks:
            handlers.append(MemorySettingsHandler())

        handlers += [
            ProcessPriorityHandler(self.executable_hints),
            CpuAffinityHandler(self.executable_hints),
            ColorProfileSettingsHandler(),
            DisplayColorRangeHandler(),
        ]
        return handlers

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Verified settings — documented, measurable effect
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                # Win11 borderless-compositor settings. Kept True universally
                # (was False prior to 2026-05-21) so the profile honors its
                # ordering contract: strict / no-sync variants are at-least-
                # as-fast as capture variants regardless of in-game display
                # mode. True is a true no-op in real exclusive fullscreen
                # (DX11 swap chain doesn't go through Windows' upgrade path)
                # and a multi-ms win in borderless (flip-model upgrade + VRR-
                # aware compositing). The <1ms compositor-stays-warm cost in
                # exclusive (see windows.py::_get_vrr_optimize comment) is
                # accepted in exchange for not silently falling off a latency
                # cliff when the user is in borderless. Users committed to
                # pure-exclusive can override to False via abso.yaml
                # profile_overrides.windows.{windowed_optimizations,vrr_optimize}.
                "windowed_optimizations": True,
                "vrr_optimize": True,
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
                "win32_priority_separation": WIN32_PRIORITY_GAMING_OFFLINE,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    # sfio_priority omitted — has no effect per Microsoft docs
                },
            },
            "NvidiaSettingsHandler": {
                "preset": "reflex_game",
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
                "disable_global_fso": True,
            },
            "ProcessPriorityHandler": {
                "cpu_priority": 3,
                "io_priority": 3,
            },
            "CpuAffinityHandler": {
                # No affinity pinning by default. Intel officially discourages
                # hard affinity on hybrid CPUs (prevents Thread Director from
                # optimizing). Users can opt in via abso.yaml profile_overrides.
                "strategy": None,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "srgb",
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            settings["RegistrySettingsHandler"]["system_responsiveness"] = 10
            settings["RegistrySettingsHandler"]["network_throttling"] = 0xFFFFFFFF
            settings["MemorySettingsHandler"] = {
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            }

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map = merge_settings_map(self._base_settings(), self._settings_overrides())
        settings = settings_map.get(handler_name, {})
        settings = inject_nvidia_profile_identity(self, handler_name, settings)
        settings = inject_fullscreen_optimizations(self, handler_name, settings)
        return settings
