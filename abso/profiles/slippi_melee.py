"""Slippi Melee (Super Smash Bros. Melee via Dolphin) profile."""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import EmulatorLatencyBaseProfile


class SlippiMeleeProfile(EmulatorLatencyBaseProfile):
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

    # === Validation Metadata Overrides ===

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Backend is user's choice - Vulkan or DX12 both work well."""
        return "unknown"

    def _additional_handlers(self) -> list[SettingsHandler]:
        from abso.settings.dolphin import DolphinConfigHandler

        return [DolphinConfigHandler()]

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # Use max refresh rate for minimum scanout latency
                "max_refresh_rate": True,
            },
            "NvidiaSettingsHandler": {
                # Absolute minimum latency - no sync overhead
                # Per rollback.md canonical spec for Slippi/SSBM
                "low_latency_mode": "on",  # ON recommended; Ultra optional (test both)
                "vsync": "off",  # OFF - removes sync latency entirely
                "vsync_tear_control": "disable",  # Explicit tear control off with VSync OFF
                "vrr_app_override": "force_off",  # OFF - fixed 60fps, no VRR benefit
                "power_management": "prefer_max_performance",
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF - emulator stability (per canonical spec)
                "max_frame_rate": "off",  # OFF - no artificial limiting
                "triple_buffering": "off",  # OFF - only works with VSync
                # Backend: Experiment with Vulkan and DX12 - both work well.
                # Vulkan often best on NVIDIA/AMD. DX12 + HAGS can also achieve low latency.
                # High refresh still helps via reduced scanout latency even without VRR.
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

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended Dolphin and NVCP settings.

        Optimized for absolute minimum latency in competitive Melee.
        Key notes:
        - Backend: Experiment with Vulkan and DX12 (Vulkan often best on NVIDIA/AMD)
        - HAGS: Generally helps with DX12; results vary by system
        - LLM: On recommended; Ultra may work but test for your setup
        - Lower internal resolution = measurably lower render latency
        - G-Sync/VSync disabled - fixed 60fps games don't benefit from VRR
        - Results vary by system - always test configurations
        """
        return [
            # === WINDOWS SETTINGS ===
            {
                "category": "Windows Settings",
                "setting": "Hardware Accelerated GPU Scheduling (HAGS)",
                "value": "On (test both settings)",
                "reason": (
                    "HAGS generally helps with DX12 backend; results vary by system. "
                    "Test both ON and OFF for your specific setup. Avoid with DX11 backend."
                ),
            },
            {
                "category": "Windows Settings",
                "setting": "VRR Optimize",
                "value": "Off (critical!)",
                "reason": (
                    "VRROptimizeEnable=1 keeps Windows compositor logic in the path. "
                    "Disabling may reduce latency for fixed-framerate emulators."
                ),
            },

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
                "value": "On (test Ultra)",
                "reason": (
                    "On reduces render queue safely. Ultra may provide additional latency "
                    "reduction but can cause micro-stutters on some systems. Test both "
                    "settings to find what works best for your hardware."
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
                "value": "Experiment (Vulkan often best)",
                "reason": (
                    "Test both Vulkan and DX12 for your system. Vulkan is often best on "
                    "modern NVIDIA/AMD GPUs. DX12 + HAGS can also achieve low latency. "
                    "The difference is typically 0-2ms between the two."
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
                "setting": "ImmediateXFBEnable",
                "value": "True (default for Melee)",
                "reason": "Immediately Present XFB - skips frame buffer queue for lower latency.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "RushPresentation",
                "value": "Optional (test for 8-14ms reduction)",
                "reason": (
                    "Rush Frame Presentation (December 2025 feature). Can reduce latency by "
                    "8-14ms but may cause frame pacing variance on slower GPUs. Test both settings."
                ),
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

            # === IMPORTANT DISCLAIMER ===
            {
                "category": "Important",
                "setting": "System Variance Disclaimer",
                "value": "Results vary by system",
                "reason": (
                    "Latency improvements depend on your specific GPU, CPU, drivers, and settings. "
                    "Always test configurations rather than assuming one setting is universally best. "
                    "The settings above are starting points - experiment to find what works for you."
                ),
            },
        ]


