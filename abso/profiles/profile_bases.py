"""Shared profile bases and mixins to reduce drift across variants."""

from __future__ import annotations

from collections.abc import Iterable
from copy import deepcopy
from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.base import BaseProfile
from abso.settings.registry import (
    WIN32_PRIORITY_GAMING_OFFLINE,
    WIN32_PRIORITY_GAMING_ONLINE,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


# SDR-on-wide-gamut compensation. Modern OLED / QD-OLED / mini-LED panels
# render wider than sRGB natively; without compensation, sRGB content gets
# stretched into the panel's wider primaries and reads as oversaturated /
# "off-color." A small DVC pull-down (-5 from neutral 50) restores the
# author-intended sRGB perception across the SDR profile lineup.
#
# HDR profiles override this back to NEUTRAL_VIBRANCE because Windows HDR
# composition owns the gamut mapping and DVC compensation would fight it.
SDR_WIDE_GAMUT_VIBRANCE = 45
NEUTRAL_VIBRANCE = 50


def fso_overrides(
    executables: Iterable[str],
    *,
    disabled: bool = True,
) -> dict[str, bool]:
    """Build a per-executable Fullscreen Optimizations override map."""
    return dict.fromkeys(executables, disabled)


def merge_settings(
    base: dict[str, Any] | None,
    overrides: dict[str, Any] | None,
) -> dict[str, Any]:
    merged: dict[str, Any] = {}
    if base:
        merged.update(deepcopy(base))
    if overrides:
        merged.update(deepcopy(overrides))
    return merged


def merge_settings_map(
    base_map: dict[str, dict[str, Any]],
    overrides_map: dict[str, dict[str, Any]],
) -> dict[str, dict[str, Any]]:
    merged: dict[str, dict[str, Any]] = {}
    for key, value in base_map.items():
        merged[key] = deepcopy(value)
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

    merged = dict(settings) if settings else {}
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


def add_legacy_system_tweaks(settings: dict[str, dict[str, Any]]) -> None:
    """Add opt-in legacy registry/memory targets to a profile settings map."""
    settings["RegistrySettingsHandler"]["system_responsiveness"] = 10
    settings["RegistrySettingsHandler"]["network_throttling"] = 0xFFFFFFFF
    settings["MemorySettingsHandler"] = {
        "large_system_cache": 0,
        "disable_paging_executive": 1,
    }


def merged_handler_settings(profile: Any, handler_name: str) -> dict[str, Any]:
    """Resolve one handler's settings through the shared base merge pipeline."""
    settings_map = merge_settings_map(
        profile._base_settings(),
        profile._settings_overrides(),
    )
    settings = settings_map.get(handler_name, {})
    settings = inject_nvidia_profile_identity(profile, handler_name, settings)
    settings = inject_fullscreen_optimizations(profile, handler_name, settings)
    return settings


def build_standard_handlers(
    profile: BaseProfile,
    *,
    include_mouse: bool,
    include_cpu_affinity: bool,
    include_nvidia_notifications: bool = False,
    include_rivals2_config: bool = False,
    additional_handlers: list[SettingsHandler] | None = None,
) -> list[SettingsHandler]:
    """Build the common gaming handler chain in one drift-resistant place."""
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

    if include_nvidia_notifications:
        from abso.settings.nvidia_notifications import NvidiaNotificationHandler

        handlers.append(NvidiaNotificationHandler())

    handlers.append(NetworkSettingsHandler())

    if include_mouse:
        handlers.append(MouseSettingsHandler())

    handlers.append(GraphicsSettingsHandler())

    if profile.include_legacy_tweaks:
        handlers.append(MemorySettingsHandler())

    handlers.append(ProcessPriorityHandler(profile.executable_hints))

    if include_cpu_affinity:
        handlers.append(CpuAffinityHandler(profile.executable_hints))

    if include_rivals2_config:
        from abso.settings.rivals2_config import Rivals2ConfigHandler

        handlers.append(Rivals2ConfigHandler())

    handlers.append(ColorProfileSettingsHandler())
    handlers.append(DisplayColorRangeHandler())

    if additional_handlers:
        handlers.extend(additional_handlers)

    return handlers


class Rivals2BaseProfile(BaseProfile):
    """Shared base for Rivals 2 profiles."""

    HDR_WINDOWS_COMPOSITION_OVERRIDES: dict[str, dict[str, Any]] = {
        "WindowsSettingsHandler": {
            "hdr": True,
            "advanced_color": True,
            "auto_hdr": False,
            # Rivals 2 currently advertises no native HDR support in Steam's
            # metadata, so HDR variants run the game as SDR composited into
            # Windows HDR. 200 nits is the OLED / Mini-LED starting point for
            # the SDR-in-HDR paper-white slider.
            "sdr_white_level_nits": 200,
        },
        "GraphicsSettingsHandler": {
            "disable_auto_color_management": True,
        },
        "ColorProfileSettingsHandler": {
            "icc_profile": "native",
            "digital_vibrance": NEUTRAL_VIBRANCE,
            "show_osd_guidance": True,
            "game_type": "competitive_fps",
        },
    }

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
        exe_names = (
            "Rivals2-Win64-Shipping.exe",
            "RivalsofAether2.exe",
            "Rivals2.exe",
        )
        return fso_overrides(exe_names)

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
                "Rivals 2 - Online No Sync HDR",
                "Rivals 2 - Online GSYNC",
                "Rivals 2 - Online GSYNC HDR",
                "Rivals 2: Online / Matchmaking",
                "Rivals 2: Online G-SYNC",
                "Rivals 2: Online HDR",
                "Rivals 2: Online G-SYNC HDR",
                "Rivals 2 (Streaming)",
            ]
        else:
            candidates = [
                "Rivals2-Win64-Shipping.exe",
                "Rivals of Aether 2",
                "Rivals 2 - Offline No Sync",
                "Rivals 2 - Offline No Sync HDR",
                "Rivals 2 - Offline GSYNC",
                "Rivals 2 - Offline GSYNC HDR",
                "Rivals 2: Offline / Training",
                "Rivals 2: G-SYNC",
                "Rivals 2: Offline HDR",
                "Rivals 2: G-SYNC HDR",
                "Rivals 2: 300Hz Maximum",
                "Rivals 2: Tournament Sim (144Hz)",
            ]

        deduped: list[str] = []
        for name in candidates:
            if name != self.nvidia_profile_name and name not in deduped:
                deduped.append(name)
        return deduped

    def get_handlers(self) -> list[SettingsHandler]:
        return build_standard_handlers(
            self,
            include_mouse=True,
            include_cpu_affinity=True,
            include_nvidia_notifications=self.include_nvidia_notifications,
            include_rivals2_config=self.include_rivals2_config,
        )

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Profile defaults. Evidence and tradeoffs vary by setting; legacy
        # tweaks remain opt-in.
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                # Strict fullscreen/no-sync Rivals profiles do not force the
                # Win11 windowed compositor path. Capture/borderless variants
                # opt into these flags explicitly.
                "windowed_optimizations": False,
                "vrr_optimize": False,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
                # Bitsum "Highest Performance" equivalent: hold the CPU floor at
                # base clock and keep every core unparked during play, removing
                # the DVFS ramp + core-unpark wake latency that degrades 1% lows
                # under a frame cap. The desktop/productivity profile relaxes the
                # floor back to 5 so the 14900F still idles cool. EXPERIMENTAL:
                # a frame-time consistency win, not an average-FPS gain.
                "processor_min_state": 100,
                "disable_core_parking": True,
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
                "digital_vibrance": SDR_WIDE_GAMUT_VIBRANCE,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            add_legacy_system_tweaks(settings)

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)

    def _rivals2_hdr_guidance(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Windows HDR",
                "setting": "Use HDR (Settings > System > Display)",
                "value": "On",
                "reason": (
                    "This profile enables Windows HDR + WCG for OLED / Mini-LED "
                    "comfort. Rivals 2 currently advertises no native HDR support, "
                    "so the game remains SDR and Windows composites it into the HDR surface."
                ),
            },
            {
                "category": "Windows HDR",
                "setting": "SDR content brightness",
                "value": "200 nits starting point; tune to taste",
                "reason": (
                    "ABSO sets the Windows SDR-in-HDR paper-white slider to 200 nits. "
                    "Move it up or down until Rivals 2 matches your preferred desktop brightness."
                ),
            },
            {
                "category": "Rivals 2 Video",
                "setting": "HDR Output",
                "value": "Off in GameUserSettings.ini",
                "reason": (
                    "Steam metadata reports hdr_support=0 for Rivals 2, so ABSO does not "
                    "force Unreal's bUseHDRDisplayOutput flag. These HDR lanes are OS-level "
                    "SDR-in-HDR composition variants, not native game HDR."
                ),
            },
            {
                "category": "Windows HDR",
                "setting": "Auto HDR",
                "value": "Off",
                "reason": (
                    "Auto HDR applies synthetic expansion to SDR games. Rivals 2's competitive "
                    "color path is kept as SDR inside Windows HDR composition instead."
                ),
            },
            {
                "category": "Display",
                "setting": "Exclusive Fullscreen vs SDR-in-HDR latency",
                "value": "Accept a small HDR composition cost",
                "reason": (
                    "Windows HDR composition can add a small nonzero presentation cost. "
                    "Use the SDR sibling when the leanest latency path matters more than HDR desktop comfort."
                ),
            },
        ]


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

    @property
    def keep_awake_while_gaming(self) -> bool:
        # Slippi Melee / Ryujinx SSBU are gamepad-driven: controller input does
        # not reset the OS idle timer, and netplay has long matchmaking / lobby
        # / spectate / shader / download waits where Windows would blank or
        # sleep mid-session. Emulator lane defaults this ON; other lanes leave
        # it off (their fullscreen path self-asserts display-required).
        return True

    def get_handlers(self) -> list[SettingsHandler]:
        return build_standard_handlers(
            self,
            include_mouse=True,
            include_cpu_affinity=True,
            additional_handlers=self._additional_handlers(),
        )

    def _additional_handlers(self) -> list[SettingsHandler]:
        return []

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Profile defaults. Evidence and tradeoffs vary by setting; legacy
        # tweaks remain opt-in.
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                # Emulator/no-sync profiles keep the Win11 windowed compositor
                # path off by default. Console-parity/capture variants can
                # enable it explicitly when their presentation path requires it.
                "windowed_optimizations": False,
                "vrr_optimize": False,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
                # Bitsum "Highest Performance" equivalent: hold the CPU floor at
                # base clock and keep every core unparked during play, removing
                # the DVFS ramp + core-unpark wake latency that degrades 1% lows
                # under a frame cap. The desktop/productivity profile relaxes the
                # floor back to 5 so the 14900F still idles cool. EXPERIMENTAL:
                # a frame-time consistency win, not an average-FPS gain.
                "processor_min_state": 100,
                "disable_core_parking": True,
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
                # MPO is not disabled by default. Toggling it requires a reboot
                # and can alter the VRR/compositor path on some systems, so only
                # disable it for a measured profile-specific issue.
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
                "digital_vibrance": SDR_WIDE_GAMUT_VIBRANCE,
                "show_osd_guidance": True,
                "game_type": "emulator",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            add_legacy_system_tweaks(settings)

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)


class WebGLBaseProfile(BaseProfile):
    """Shared base for WebGL/WebView2 performance profiles."""

    def get_handlers(self) -> list[SettingsHandler]:
        return build_standard_handlers(
            self,
            include_mouse=False,
            include_cpu_affinity=False,
        )

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Profile defaults. Evidence and tradeoffs vary by setting; legacy
        # tweaks remain opt-in.
        settings: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                # Casual WebGL lanes run windowed/borderless in a browser or
                # WebView2 shell, not exclusive fullscreen. Enable the Win11
                # windowed-games optimization + VRR-optimize path so VRR/G-SYNC
                # can actually smooth variable WebGL frame delivery (the
                # profiles' guidance promises this); without it VRR never
                # engages for windowed content.
                "windowed_optimizations": True,
                "vrr_optimize": True,
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
                "digital_vibrance": SDR_WIDE_GAMUT_VIBRANCE,
                "show_osd_guidance": True,
                "game_type": "casual",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            add_legacy_system_tweaks(settings)

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)


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
        from abso.settings.audio_engine import AudioEngineHandler
        from abso.settings.game_dvr import GameDvrHandler
        from abso.settings.interrupt_mode import InterruptModeHandler
        from abso.settings.nic_driver import NicDriverHandler

        # Strict online Reflex shooters opt into the latency-stack handlers:
        # Game DVR hard-off, GPU MSI mode, audio-APO disable, and NIC driver
        # tuning. Each is gated by its settings in _base_settings below.
        return build_standard_handlers(
            self,
            include_mouse=True,
            include_cpu_affinity=True,
            additional_handlers=[
                GameDvrHandler(),
                InterruptModeHandler(),
                AudioEngineHandler(),
                NicDriverHandler(),
            ],
        )

    def _base_settings(self) -> dict[str, dict[str, Any]]:
        # Profile defaults. Evidence and tradeoffs vary by setting; legacy
        # tweaks remain opt-in.
        settings: dict[str, dict[str, Any]] = {
            # --- Latency-stack handlers (strict online Reflex shooters) ---
            # Game DVR hard-off at the registry source (the janitor only stops
            # the processes; this disarms the setting so they stay down).
            "GameDvrHandler": {"hard_disable": True},
            # GPU MSI interrupt mode (reboot-gated; one-time per machine).
            "InterruptModeHandler": {"enable_msi": True},
            # Disable the Windows audio enhancement (APO) DPC chain.
            "AudioEngineHandler": {"disable_enhancements": True},
            # NIC driver tuning for competitive online play (per-NIC; restorable).
            "NicDriverHandler": {"nic_tuning": True},
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,
                "hdr": False,
                "auto_hdr": False,
                # Strict Reflex shooter profiles keep the Win11 windowed
                # compositor path off. Capture/borderless variants opt in.
                "windowed_optimizations": False,
                "vrr_optimize": False,
                "max_refresh_rate": True,
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
                # Bitsum "Highest Performance" equivalent: hold the CPU floor at
                # base clock and keep every core unparked during play, removing
                # the DVFS ramp + core-unpark wake latency that degrades 1% lows
                # under a frame cap. The desktop/productivity profile relaxes the
                # floor back to 5 so the 14900F still idles cool. EXPERIMENTAL:
                # a frame-time consistency win, not an average-FPS gain.
                "processor_min_state": 100,
                "disable_core_parking": True,
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
                "digital_vibrance": SDR_WIDE_GAMUT_VIBRANCE,
                "show_osd_guidance": True,
                "game_type": "competitive_fps",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        # Legacy/unverified settings — opt-in only
        if self.include_legacy_tweaks:
            add_legacy_system_tweaks(settings)

        return settings

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {}

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        return merged_handler_settings(self, handler_name)
