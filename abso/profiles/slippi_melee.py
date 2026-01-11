"""Slippi Melee (Super Smash Bros. Melee via Dolphin) profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class SlippiMeleeProfile(BaseProfile):
    """Optimization profile for Super Smash Bros. Melee via Slippi Dolphin.

    Focus: Ultra-low input latency for competitive play.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi)"

    @property
    def description(self) -> str:
        return "Ultra-low latency optimization for competitive Melee"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

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
            CNMSettingsHandler(),  # Stop CNM during gaming for power optimization
            DolphinConfigHandler(),  # Fix Slippi Dolphin configs (Slippi Launcher overwrites these)
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                # HAGS: Disabled for emulators.
                # Research shows HAGS causes micro-stutters with DX9-11 applications
                # and emulators (MAME, Dolphin). Keep OFF for consistent frame timing.
                "hags": False,
                # HDR disabled for competitive - adds processing overhead
                "hdr": False,
                "auto_hdr": False,
                # VRR Optimize: DISABLED - critical for minimum latency!
                # Even in exclusive fullscreen, VRROptimizeEnable=1 keeps Windows compositor
                # logic active, adding ~0.1ms latency. Disabling achieves true 0.0ms render.
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
                "system_responsiveness": 0,
                "network_throttling": 0xFFFFFFFF,
                "win32_priority_separation": 0x2A,  # Short fixed quantum, max foreground boost
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
                "fullscreen_optimizations": {
                    # Will be populated with detected Dolphin path
                },
            },
            "NvidiaSettingsHandler": {
                # Absolute minimum latency - no sync overhead
                # Use D3D11 backend in Dolphin for best compatibility
                "preset": "minimum_latency",
                # Settings applied:
                # - Low Latency Mode: On (safer than Ultra - Ultra can add CPU sync overhead)
                #   Ultra reduces pre-render queue to near-zero but adds CPU synchronization.
                #   For locked 60fps, "On" (1 frame queue) is more stable.
                #   Test Ultra if chasing 0.0ms - it may work on powerful GPUs (RTX 4070+)
                # - VSync: OFF (critical - removes sync latency entirely)
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited
                # - Threaded Optimization: OFF (reduces threading overhead for emulation)
                # - Triple Buffering: OFF
                # - Max Frame Rate: OFF
                # - G-Sync: OFF (Melee is fixed 60fps - VRR adds overhead for constant rate)
                #
                # High refresh still helps via reduced scanout latency even without VRR.
                # May cause tearing, but competitive players prioritize latency.
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",  # Also optimizes TCP global settings
            },
            "MouseSettingsHandler": {
                # Disable acceleration for consistent muscle memory
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                # Disable FSO globally for true exclusive fullscreen
                "disable_global_fso": True,
                # MPO (Multi-Plane Overlay) can cause stutter with emulators.
                # Disabled by default for minimum latency profile.
                "disable_mpo": True,
            },
            "ServicesSettingsHandler": {
                # Disable background services that can cause hitches
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                # Keep kernel in RAM, optimize for applications
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                # High priority for Dolphin executables
                "gpu_priority": 8,
                "cpu_priority": 3,  # High
                "io_priority": 3,   # High
            },
            "CNMSettingsHandler": {
                # Stop CNM during gaming to allow power optimizations
                # CNM's SetThreadExecutionState interferes with power management
                "action": "stop",
            },
            "DolphinConfigHandler": {
                # Fix Slippi Dolphin configs that get overwritten by Slippi Launcher
                # These are applied every time the profile is activated
                "efb_scale": "1",  # Native resolution for lowest latency
                "texture_scaling_factor": "1",  # No texture upscaling
                "use_scaling_filter": "False",  # No scaling filter
                "use_deposterize": "False",  # No post-processing
                "reduce_timing_dispersion": "True",  # Ishiiruka-specific: tighter frame timing
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended Dolphin and NVCP settings.

        Optimized for absolute minimum latency in competitive Melee.
        Key findings from testing:
        - D3D11 > Vulkan (enables LLM Ultra, Vulkan is 'Experimental' in Slippi)
        - Lower internal resolution = measurably lower render latency
        - G-Sync/VSync disabled - fixed 60fps games don't benefit from VRR
        """
        return [
            # === NVIDIA CONTROL PANEL SETTINGS ===
            {
                "category": "Nvidia Control Panel",
                "setting": "G-SYNC",
                "value": "Off",
                "reason": (
                    "Melee runs at fixed 60fps - G-SYNC adds overhead syncing to a constant rate. "
                    "Disabling removes ~1-2ms+ of sync latency. High refresh still helps via "
                    "reduced scanout latency even without VRR."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "Off",
                "reason": (
                    "Disabling V-SYNC eliminates frame queue latency entirely. "
                    "May cause tearing, but competitive players prioritize input latency."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "On (test Ultra if chasing 0.0ms)",
                "reason": (
                    "'On' limits pre-render queue to 1 frame - stable for locked 60fps. "
                    "'Ultra' adds CPU sync overhead that can backfire. Test Ultra on RTX 4070+ "
                    "if trying to achieve consistent 0.0ms render latency."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Threaded Optimization",
                "value": "Off",
                "reason": "Reduces driver threading overhead for emulation workloads.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Triple Buffering",
                "value": "Off",
                "reason": "Only works with VSync and adds latency.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Max Frame Rate",
                "value": "Off",
                "reason": "No artificial frame limiting.",
            },

            # === DOLPHIN GRAPHICS SETTINGS ===
            {
                "category": "Graphics",
                "setting": "Backend",
                "value": "Direct3D 11",
                "reason": (
                    "D3D11 enables Nvidia Low Latency Mode Ultra (Vulkan doesn't support it). "
                    "Tested: D3D11 + LLM Ultra = lower render latency than Vulkan. "
                    "Vulkan is marked 'Experimental' in Slippi for a reason."
                ),
            },
            {
                "category": "Graphics",
                "setting": "VSync",
                "value": "Off",
                "reason": "Disable Dolphin's V-SYNC. No sync anywhere for minimum latency (tearing acceptable).",
            },
            {
                "category": "Graphics",
                "setting": "Fullscreen Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Lower latency than borderless windowed.",
            },
            {
                "category": "Graphics",
                "setting": "Internal Resolution",
                "value": "Native (1x) or 2x max",
                "reason": (
                    "Lower resolution = lower render latency. Tested: dropping resolution "
                    "reduced render latency from 0.3ms to 0.1ms. Melee is a 2001 game - "
                    "it doesn't need 4K. Prioritize latency over visuals."
                ),
            },

            # === DOLPHIN CONFIG FILES (Ishiiruka/Stable) ===
            # These settings are in GFX.ini and Dolphin.ini
            {
                "category": "GFX.ini [Settings]",
                "setting": "EFBScale",
                "value": "1 (Native)",
                "reason": (
                    "Native resolution = lowest render latency. Higher res adds GPU work. "
                    "Tested: EFBScale 2 added measurable latency vs EFBScale 1."
                ),
            },
            {
                "category": "GFX.ini [Settings]",
                "setting": "BackendMultithreading",
                "value": "False",
                "reason": "Reduces driver threading overhead.",
            },
            {
                "category": "GFX.ini [Enhancements]",
                "setting": "UseScalingFilter",
                "value": "False",
                "reason": "Scaling adds GPU overhead.",
            },
            {
                "category": "GFX.ini [Enhancements]",
                "setting": "UseDePosterize",
                "value": "False",
                "reason": "Post-processing adds GPU overhead.",
            },
            {
                "category": "GFX.ini [Enhancements]",
                "setting": "TextureScalingFactor",
                "value": "1",
                "reason": "Texture upscaling adds GPU overhead.",
            },
            {
                "category": "GFX.ini [Hacks]",
                "setting": "EFBAccessEnable",
                "value": "False",
                "reason": "EFB access is slow - disable for performance.",
            },
            {
                "category": "GFX.ini [Hacks]",
                "setting": "EnableGPUTextureDecoding",
                "value": "True",
                "reason": "Offloads texture decoding to GPU.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "TimingVariance",
                "value": "8",
                "reason": "Ishiiruka-specific: reduces frame timing variance.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "ReduceTimingDispersion",
                "value": "True",
                "reason": "Ishiiruka-specific: tighter frame timing.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "SyncGPU",
                "value": "False",
                "reason": "GPU sync adds latency - disable.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "TimeStretching",
                "value": "False",
                "reason": "Audio time stretching adds processing overhead.",
            },
            {
                "category": "Game Settings (GALE01.ini)",
                "setting": "MMU",
                "value": "False",
                "reason": "Memory Management Unit emulation adds overhead - not needed for Melee.",
            },
            {
                "category": "Game Settings (GALE01.ini)",
                "setting": "FPRF",
                "value": "False",
                "reason": "Floating point result flags add CPU overhead - not needed for Melee.",
            },

            # === AUDIO SETTINGS ===
            {
                "category": "Audio",
                "setting": "Backend",
                "value": "Exclusive WASAPI (Ishiiruka) / Cubeb (Mainline)",
                "reason": "Exclusive mode bypasses Windows audio mixer for lowest latency.",
            },
            {
                "category": "Audio",
                "setting": "Latency",
                "value": "Lowest stable setting",
                "reason": "Lower is better, but too low causes crackling.",
            },

            # === CONTROLLER SETTINGS ===
            {
                "category": "Controller",
                "setting": "Adapter Mode",
                "value": "Wii U / Switch mode",
                "reason": "Not PC mode. Native adapter support has lower latency.",
            },
            {
                "category": "Controller",
                "setting": "Background Input",
                "value": "On",
                "reason": "Allows input when alt-tabbed.",
            },

            # === WHY HIGH REFRESH HELPS WITHOUT VRR ===
            {
                "category": "Display Info",
                "setting": "High refresh benefit",
                "value": "Reduced scanout latency (no G-Sync needed)",
                "reason": (
                    "60fps @ 60Hz = ~17ms scanout, 60fps @ 240Hz = ~4ms scanout. "
                    "This benefit is from faster pixel refresh, NOT from VRR. "
                    "Use your monitor's max refresh rate with G-Sync/VSync OFF for minimum latency."
                ),
            },
            {
                "category": "Display Info",
                "setting": "Tearing",
                "value": "May occur but minimal impact",
                "reason": (
                    "With 60fps on a high refresh display, tears are small and fast-moving. "
                    "The latency reduction far outweighs the visual artifact for competitive play."
                ),
            },
        ]
