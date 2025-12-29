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
        settings_map: dict[str, dict[str, Any]] = {
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
                # VRR-optimized for fighting games
                # See: abso/core/vrr.py for VRR knowledge base
                "preset": "vrr_fighting_game",
                # Settings applied:
                # - Low Latency Mode: On (limited effect - UE5 uses DX12, LLM only works in DX9/DX11)
                # - VSync: On (safety net for VRR - zero latency with proper FPS cap)
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited
                # - Threaded Optimization: On
                #
                # NOTE: Rivals 2 does NOT support NVIDIA Reflex, and LLM doesn't work in DX12.
                # Primary latency reduction comes from: proper FPS cap + G-SYNC + system optimizations.
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
        """Get recommended in-game and NVCP settings.

        VRR/G-SYNC guidance based on Blur Busters G-SYNC 101 research.
        Fighting games benefit from high refresh even with 60Hz game logic.
        """
        return [
            # === WINDOWS SETTINGS ===
            {
                "category": "Windows Settings",
                "setting": "Variable refresh rate",
                "value": "On",
                "reason": (
                    "Settings > System > Display > Graphics > Change default graphics settings. "
                    "Required for VRR to work in borderless windowed mode. Already enabled on this PC."
                ),
            },

            # === NVIDIA CONTROL PANEL SETTINGS ===
            # VRR-optimized configuration (recommended for most players)
            {
                "category": "Nvidia Control Panel",
                "setting": "G-SYNC",
                "value": "On (recommended)",
                "reason": (
                    "Set in Display > Set up G-SYNC. G-SYNC ON with proper FPS cap provides "
                    "tear-free gameplay with minimal latency. Only disable if you accept tearing "
                    "for absolute minimum latency in tournament settings."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "On",
                "reason": (
                    "Manage 3D settings > V-SYNC On. With G-SYNC, this acts as a SAFETY NET only. "
                    "With FPS capped below refresh rate, V-SYNC never activates and adds zero latency. "
                    "Prevents tearing if FPS momentarily exceeds refresh rate."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "On (limited effect)",
                "reason": (
                    "Manage 3D settings > Low Latency Mode. Note: LLM only works in DX9/DX11. "
                    "Rivals 2 uses UE5/DX12, so LLM has minimal effect. Reflex is not available "
                    "in this game. Primary latency reduction comes from proper FPS cap + G-SYNC."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Preferred refresh rate",
                "value": "Highest available",
                "reason": (
                    "Set in Display > Change resolution. Higher refresh = lower scanout latency, "
                    "even for 60Hz-logic fighting games (60fps @ 240Hz has ~4ms scanout vs ~17ms @ 60Hz)."
                ),
            },

            # === IN-GAME VIDEO SETTINGS ===
            {
                "category": "Video",
                "setting": "Display Mode",
                "value": "Borderless Windowed (recommended for DX12)",
                "reason": (
                    "UE5/DX12 uses flip model in borderless, giving near-identical latency to exclusive. "
                    "With Windows VRR enabled, G-SYNC works in borderless. Faster alt-tab, more stable. "
                    "Exclusive fullscreen is fine too, but offers no real advantage in DX12."
                ),
            },
            {
                "category": "Video",
                "setting": "VSync (in-game)",
                "value": "Off",
                "reason": "Always disable in-game V-SYNC when using G-SYNC. NVCP V-SYNC handles sync as safety net.",
            },
            {
                "category": "Video",
                "setting": "Frame Rate Limit",
                "value": "Highest in-game preset below your refresh rate (e.g., 240 for 300Hz)",
                "reason": (
                    "Rivals 2 only offers preset FPS caps (60, 120, 144, 165, 240). "
                    "For 60Hz-logic fighting games, the in-game limiter's lower latency "
                    "outweighs the marginal scanout benefit of RTSS at refresh-3. "
                    "Example: On a 300Hz monitor, use the 240 preset - the ~0.5-1 frame "
                    "latency saved by in-game limiter matters more than 240→297 scanout difference."
                ),
            },
            {
                "category": "Video",
                "setting": "Nvidia Reflex",
                "value": "Not available",
                "reason": (
                    "Rivals 2 does not implement NVIDIA Reflex. Combined with UE5/DX12 (where LLM "
                    "doesn't work), there's no driver-level latency reduction for this game. "
                    "Focus on: proper FPS cap, G-SYNC enabled, and system-level optimizations."
                ),
            },
            {
                "category": "Video",
                "setting": "Resolution Scale",
                "value": "100% (Native)",
                "reason": "Native resolution for sharpest visuals. Lower only if GPU-limited and can't maintain FPS cap.",
            },
            {
                "category": "Video",
                "setting": "Graphics Quality",
                "value": "Medium-High",
                "reason": "Prioritize stable FPS at your cap over visual fidelity. Reduce if dropping below cap.",
            },
            {
                "category": "Video",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Obscures visual clarity in fast-paced combat. Always disable for competitive play.",
            },
            {
                "category": "Video",
                "setting": "Anti-Aliasing",
                "value": "TAA or DLAA",
                "reason": "UE5 uses TAA-based AA. Disable if it causes ghosting on fast-moving characters.",
            },

            # === AUDIO & INPUT ===
            {
                "category": "Audio",
                "setting": "Audio Latency",
                "value": "Lowest stable setting",
                "reason": "Audio cues are important for reactions. Lower is better but may cause crackling.",
            },
            {
                "category": "Controller",
                "setting": "Input Method",
                "value": "Wired or 2.4GHz dongle",
                "reason": "Wired/USB dongle has 1-4ms latency. Bluetooth adds 10-20ms+ latency.",
            },

            # === ALTERNATIVE: COMPETITIVE (ACCEPT TEARING) ===
            {
                "category": "Alternative Setup",
                "setting": "No-sync competitive mode",
                "value": "G-SYNC Off, V-SYNC Off, Uncapped FPS",
                "reason": (
                    "For tournament/LAN settings where absolute minimum latency is required "
                    "and tearing is acceptable. Most players should use the VRR setup above."
                ),
            },
        ]
