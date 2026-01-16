"""Rivals of Aether 2 profile - OLED with VRR/G-Sync variant.

CRITICAL: This profile REQUIRES SpecialK injection via SKIF for optimal latency.
Without SpecialK, UE5/Rivals 2 forces borderless windowed mode during gameplay,
which adds 2-7ms latency. SpecialK forces true exclusive fullscreen.
"""

from __future__ import annotations

from typing import Any

from abso.profiles.rivals2_oled import Rivals2OLEDProfile


class Rivals2OLEDVRRProfile(Rivals2OLEDProfile):
    """Optimization profile for Rivals of Aether 2 on OLED with G-Sync/VRR.

    REQUIRES: SpecialK injection via SKIF for 0ms input latency.

    GOLDEN CONFIG (tested ~1.0ms render / 0ms input latency):
    - SpecialK: Reflex On+Boost, Frame Limiter OFF, FlipDiscard=true
    - NVCP: VSync OFF, Threaded Optimization OFF, Low Latency Mode ON
    - Windows: HAGS ON, VBS OFF, Windows VRR OFF, MPO ENABLED
    - System: GeForce Experience UNINSTALLED, NVIDIA Shield DISABLED
    - Game: 297 FPS cap, VSync OFF, Exclusive Fullscreen

    Why SpecialK is required:
    - UE5/Rivals 2 forces borderless windowed (0x14000000) during gameplay
    - SpecialK overrides this to maintain exclusive fullscreen (0x94000000)
    - SpecialK's Reflex On+Boost handles frame queue better than driver LLM
    - SpecialK handles process priority boosting (no external watcher needed)

    Still keeps HDR DISABLED since Rivals 2 is an SDR game.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-oled-vrr"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2 (OLED + G-Sync)"

    @property
    def description(self) -> str:
        return "Tear-free VRR gaming with near-minimum latency (HDR disabled - game is SDR)"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings with VRR/G-Sync optimizations.

        REQUIRES SpecialK injection via SKIF for optimal latency.
        """
        settings = super().get_settings(handler_name)

        if handler_name == "NvidiaSettingsHandler":
            settings = settings.copy()
            # VSync OFF, Threaded Optimization OFF - SpecialK handles latency
            settings["preset"] = "vrr_ue5_fighting_game"

        elif handler_name == "GraphicsSettingsHandler":
            settings = settings.copy()
            # Disable FSO for true exclusive fullscreen
            settings["disable_global_fso"] = True
            # MPO must be ENABLED - required for VRR to work with SpecialK
            settings["disable_mpo"] = False

        elif handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            # Windows VRR MUST be OFF - it adds latency
            settings["vrr_optimize"] = False
            # HAGS MUST be ON - helps with latency when GFE is removed
            settings["hags_enabled"] = True

        elif handler_name == "Rivals2ConfigHandler":
            settings = settings.copy()
            # For VRR/G-Sync: cap at refresh_rate - 3 for G-Sync headroom
            settings["frame_rate_limit"] = 297.0  # 300Hz - 3

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for VRR/G-Sync setup.

        REQUIRES SpecialK injection via SKIF for optimal latency.
        """
        return [
            # =========================================================================
            # SPECIALK REQUIREMENT (CRITICAL)
            # =========================================================================
            {
                "category": "=== SPECIALK REQUIRED ===",
                "setting": "Install SpecialK",
                "value": "Download from special-k.info, launch via SKIF",
                "reason": (
                    "CRITICAL: SpecialK is REQUIRED for 0ms input latency. Without it, "
                    "UE5/Rivals 2 forces borderless windowed during gameplay (adds 2-7ms). "
                    "SpecialK forces true exclusive fullscreen and provides Reflex On+Boost."
                ),
            },
            {
                "category": "SpecialK Settings",
                "setting": "Reflex",
                "value": "On + Boost",
                "reason": "SpecialK's Reflex implementation handles frame queue better than driver LLM.",
            },
            {
                "category": "SpecialK Settings",
                "setting": "Frame Limiter",
                "value": "Disabled",
                "reason": "Let the game's 297 FPS cap handle limiting - lower latency than SK limiter.",
            },
            {
                "category": "SpecialK Settings",
                "setting": "Key settings in SpecialK.ini",
                "value": "FlipDiscard=true, AllowTearingInDWM=true",
                "reason": "Enables optimal flip model presentation and VRR tearing support.",
            },

            # =========================================================================
            # SYSTEM REQUIREMENTS
            # =========================================================================
            {
                "category": "=== SYSTEM SETUP ===",
                "setting": "GeForce Experience",
                "value": "UNINSTALL",
                "reason": "GFE adds latency overhead. Completely uninstall, not just disable.",
            },
            {
                "category": "System Setup",
                "setting": "NVIDIA Shield/Broadcast",
                "value": "DISABLE",
                "reason": "Stop and disable NvBroadcast.ContainerLocalSystem service.",
            },
            {
                "category": "System Setup",
                "setting": "HAGS (Hardware Accelerated GPU Scheduling)",
                "value": "ON",
                "reason": "Enable in Windows Graphics Settings. Helps latency when GFE removed.",
            },
            {
                "category": "System Setup",
                "setting": "VBS / Memory Integrity",
                "value": "OFF",
                "reason": "Disable in Windows Security > Device Security. Reduces kernel overhead.",
            },
            {
                "category": "System Setup",
                "setting": "Windows VRR (Variable refresh rate)",
                "value": "OFF",
                "reason": "DISABLE in Windows Graphics Settings. It adds latency, not reduces it.",
            },

            # =========================================================================
            # NVIDIA CONTROL PANEL
            # =========================================================================
            {
                "category": "=== NVIDIA CONTROL PANEL ===",
                "setting": "Set up G-SYNC",
                "value": "Enable for windowed and full screen mode",
                "reason": "Display > Set up G-SYNC. Enable for both modes in case game falls back.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Vertical sync",
                "value": "Off",
                "reason": "SpecialK + G-Sync handles sync. VSync OFF for lowest latency.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Threaded Optimization",
                "value": "Off",
                "reason": "CRITICAL: Must be OFF. Reduces render latency significantly.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": "On, not Ultra. SpecialK Reflex On+Boost handles aggressive latency.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Triple buffering",
                "value": "Off",
                "reason": "Adds frame queue latency. Not needed with G-Sync.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Power management mode",
                "value": "Prefer maximum performance",
                "reason": "Prevents GPU downclocking during gameplay.",
            },

            # =========================================================================
            # IN-GAME SETTINGS
            # =========================================================================
            {
                "category": "=== IN-GAME SETTINGS ===",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "ALWAYS disable in-game V-SYNC. G-Sync + SpecialK handles sync.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "297 (refresh rate - 3)",
                "reason": (
                    "Cap 3 below refresh for G-Sync headroom. "
                    "In-game limiter has lowest latency (~0.5ms vs 2-4ms for NVCP/RTSS)."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Set to Exclusive. SpecialK ensures it stays exclusive during gameplay.",
            },

            # =========================================================================
            # EXPECTED RESULTS
            # =========================================================================
            {
                "category": "=== EXPECTED RESULTS ===",
                "setting": "With SpecialK + all settings correct",
                "value": "~1.0ms render / 0ms input latency",
                "reason": (
                    "NVIDIA overlay should show ~1.0ms render latency and 0ms input latency. "
                    "Window style will be 0x94000000 (true exclusive). "
                    "Presentation mode: Hardware Independent Flip."
                ),
            },
            {
                "category": "Expected Results",
                "setting": "Without SpecialK",
                "value": "~2-7ms render / elevated input latency",
                "reason": (
                    "UE5 forces borderless windowed (0x14000000) which adds compositor overhead. "
                    "This is unavoidable without SpecialK injection."
                ),
            },
        ]
