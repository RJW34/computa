"""Diablo 4 profile - OLED with VRR/G-Sync ultra low latency variant.

Optimized for minimum latency with G-Sync on high refresh OLED.
Uses native NVIDIA Reflex for frame queue management.
"""

from __future__ import annotations

from typing import Any

from abso.profiles.diablo4_oled import Diablo4OLEDProfile


class Diablo4OLEDVRRProfile(Diablo4OLEDProfile):
    """Optimization profile for Diablo 4 on OLED with G-Sync/VRR.

    GOLDEN CONFIG for ultra low latency ARPG:
    - NVCP: VSync OFF, Threaded Optimization OFF, Low Latency Mode OFF
    - In-Game: Reflex On+Boost, VSync OFF, FPS cap at refresh_rate - 3
    - Windows: HAGS ON, VBS OFF, Windows VRR OFF, MPO ENABLED
    - System: GeForce Experience UNINSTALLED for lowest overhead
    - HDR: ENABLED (Diablo 4 has excellent native HDR)

    Why Low Latency Mode is OFF:
    - Diablo 4 has native NVIDIA Reflex support
    - Native Reflex is more effective than driver LLM
    - Using both can cause conflicts and actually increase latency

    Key differences from Rivals 2 VRR profile:
    - No SpecialK required (Diablo 4 handles fullscreen properly)
    - Uses native Reflex instead of SpecialK Reflex
    - HDR enabled (excellent native HDR support)
    """

    @property
    def profile_id(self) -> str:
        return "diablo4-oled-vrr"

    @property
    def display_name(self) -> str:
        return "Diablo 4 (OLED + G-Sync)"

    @property
    def description(self) -> str:
        return "Ultra low latency VRR gaming with HDR (native Reflex)"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings with VRR/G-Sync optimizations.

        Uses native NVIDIA Reflex instead of SpecialK.
        """
        settings = super().get_settings(handler_name)

        if handler_name == "NvidiaSettingsHandler":
            settings = settings.copy()
            # Use the Diablo 4 VRR preset - Reflex native, LLM OFF
            settings["preset"] = "vrr_diablo4"

        elif handler_name == "GraphicsSettingsHandler":
            settings = settings.copy()
            # Disable FSO for true exclusive fullscreen
            settings["disable_global_fso"] = True
            # MPO must be ENABLED - required for VRR to work
            settings["disable_mpo"] = False

        elif handler_name == "WindowsSettingsHandler":
            settings = settings.copy()
            # Windows VRR MUST be OFF - it adds latency
            settings["vrr_optimize"] = False
            # HAGS ON - helps with latency when GFE is removed
            settings["hags_enabled"] = True
            # Keep HDR enabled - Diablo 4 has excellent native HDR
            settings["hdr"] = True
            settings["auto_hdr"] = False  # Not needed, game has native HDR

        elif handler_name == "ProcessPriorityHandler":
            settings = settings.copy()
            # Higher priority for latency-sensitive play
            settings["cpu_priority"] = 3  # Above Normal (2=Normal, 3=AboveNormal)

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for VRR/G-Sync ultra low latency."""
        return [
            # =========================================================================
            # SYSTEM SETUP (SAME AS RIVALS 2 GOLDEN CONFIG)
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
                "reason": "Display > Set up G-SYNC. Enable for both modes.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Vertical sync",
                "value": "Off",
                "reason": "G-Sync handles sync. VSync OFF for lowest latency.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Threaded Optimization",
                "value": "Off",
                "reason": "Reduces render latency. Test On if you experience issues.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Low Latency Mode",
                "value": "Off",
                "reason": "OFF because Diablo 4 uses native Reflex. Don't combine them.",
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
                "setting": "Display Mode",
                "value": "Fullscreen",
                "reason": "True fullscreen for lowest latency. Not Windowed Fullscreen.",
            },
            {
                "category": "In-Game Graphics",
                "setting": "NVIDIA Reflex Low Latency",
                "value": "On + Boost",
                "reason": (
                    "CRITICAL: Enable Reflex On+Boost. This is the primary latency reducer. "
                    "Native Reflex is more effective than NVCP Low Latency Mode."
                ),
            },
            {
                "category": "In-Game Graphics",
                "setting": "V-Sync",
                "value": "Off",
                "reason": "ALWAYS disable in-game V-SYNC. G-Sync handles sync.",
            },
            {
                "category": "In-Game Graphics",
                "setting": "Max Foreground FPS",
                "value": "297 (refresh rate - 3)",
                "reason": (
                    "Cap 3 below refresh for G-Sync headroom. "
                    "Prevents G-Sync from disengaging at refresh rate ceiling."
                ),
            },
            {
                "category": "In-Game Graphics",
                "setting": "Max Background FPS",
                "value": "30 or lower",
                "reason": "Save power/heat when alt-tabbed. Doesn't affect gameplay.",
            },

            # =========================================================================
            # HDR SETTINGS (OLED SPECIFIC)
            # =========================================================================
            {
                "category": "=== HDR SETTINGS ===",
                "setting": "HDR Mode",
                "value": "On",
                "reason": "Diablo 4 has excellent native HDR. Enable on OLED.",
            },
            {
                "category": "HDR Settings",
                "setting": "HDR Paper White Nits",
                "value": "200-250 (adjust to preference)",
                "reason": "Controls SDR content brightness in HDR mode. Start at 200.",
            },
            {
                "category": "HDR Settings",
                "setting": "HDR Max Nits",
                "value": "Match your display peak (e.g., 1000)",
                "reason": "Set to your OLED's peak HDR brightness for best highlights.",
            },

            # =========================================================================
            # PERFORMANCE SETTINGS
            # =========================================================================
            {
                "category": "=== PERFORMANCE ===",
                "setting": "DLSS/FSR",
                "value": "Quality or Off (if maintaining 297+ FPS)",
                "reason": "Use if needed to maintain FPS cap. Quality mode has minimal latency impact.",
            },
            {
                "category": "Performance",
                "setting": "DLSS Frame Generation",
                "value": "Off",
                "reason": "Frame Gen adds latency. Only use if struggling to hit FPS target.",
            },
            {
                "category": "Performance",
                "setting": "Graphics Quality",
                "value": "Adjust to maintain 297+ FPS",
                "reason": "Prioritize stable frame times at cap over max settings.",
            },

            # =========================================================================
            # EXPECTED RESULTS
            # =========================================================================
            {
                "category": "=== EXPECTED RESULTS ===",
                "setting": "With Reflex On+Boost + all settings correct",
                "value": "~2-4ms render latency, low input latency",
                "reason": (
                    "NVIDIA overlay (Alt+R) should show low render latency. "
                    "Diablo 4 with Reflex won't hit 0ms like Rivals 2 with SpecialK, "
                    "but will be significantly lower than default settings."
                ),
            },
        ]
