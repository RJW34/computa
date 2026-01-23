"""Rivals of Aether 2 profile - OLED with VRR/G-Sync for multi-monitor setups.

This variant uses borderless windowed (fullscreen windowed) mode for compatibility
with multi-monitor setups where exclusive fullscreen causes issues with other displays.

CRITICAL: This profile REQUIRES SpecialK injection via SKIF for optimal latency.
G-Sync must be enabled for "windowed and full screen mode" in NVCP.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.rivals2_oled_vrr import Rivals2OLEDVRRProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Rivals2OLEDVRRMultiMonProfile(Rivals2OLEDVRRProfile):
    """Optimization profile for Rivals of Aether 2 on OLED with G-Sync (Multi-Monitor).

    REQUIRES: SpecialK injection via SKIF for optimal latency.

    This variant uses BORDERLESS WINDOWED mode instead of exclusive fullscreen,
    making it compatible with multi-monitor setups where you want to:
    - Keep other monitors active during gameplay
    - Avoid display flickering when alt-tabbing
    - Use overlays or secondary applications on other screens

    GOLDEN CONFIG (Multi-Monitor G-Sync):
    - SpecialK: Reflex On+Boost, TearingMode=0, AllowTearingInDWM=false, FlipDiscard=true
    - NVCP: G-Sync enabled for "windowed and full screen mode"
    - NVCP: Vertical sync=Fast, Threaded Optimization=ON, Low Latency Mode=Ultra
    - Windows: HAGS ON, VBS OFF, Windows VRR OFF, MPO ENABLED (required for windowed VRR)
    - Game: Borderless Windowed (FullscreenMode=1), in-game VSync OFF

    Trade-offs vs Exclusive Fullscreen:
    - Slightly higher latency (~1-2ms) due to DWM compositor
    - Better multi-monitor experience
    - No display mode switching when alt-tabbing

    Still keeps HDR DISABLED since Rivals 2 is an SDR game.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-oled-vrr-multimon"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2 (OLED + G-Sync + Multi-Monitor)"

    @property
    def description(self) -> str:
        return "G-Sync with borderless windowed for multi-monitor setups (HDR disabled - game is SDR)"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get settings with borderless windowed mode for multi-monitor compatibility."""
        settings = super().get_settings(handler_name)

        if handler_name == "GraphicsSettingsHandler":
            settings = settings.copy()
            # FSO doesn't matter for borderless, but keep it disabled
            settings["disable_global_fso"] = True
            # MPO MUST be ENABLED - required for VRR in windowed modes
            settings["disable_mpo"] = False

        elif handler_name == "Rivals2ConfigHandler":
            settings = settings.copy()
            # Use borderless windowed for multi-monitor compatibility
            settings["fullscreen_mode"] = 1  # Borderless Windowed
            settings["vsync"] = False  # Let NVCP handle sync
            settings["raw_input"] = True

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for multi-monitor G-Sync setup."""
        return [
            # =========================================================================
            # SPECIALK REQUIREMENT (CRITICAL)
            # =========================================================================
            {
                "category": "=== SPECIALK REQUIRED ===",
                "setting": "Install SpecialK",
                "value": "Download from special-k.info, launch via SKIF",
                "reason": (
                    "CRITICAL: SpecialK is REQUIRED for optimal latency even in borderless. "
                    "Provides Reflex On+Boost for frame queue management."
                ),
            },
            {
                "category": "SpecialK Settings",
                "setting": "Reflex",
                "value": "On + Boost",
                "reason": "SpecialK's Reflex implementation handles frame queue for lower latency.",
            },
            {
                "category": "SpecialK Settings",
                "setting": "Frame Limiter",
                "value": "Disabled",
                "reason": "Let LLM Ultra or in-game cap handle limiting.",
            },
            {
                "category": "SpecialK Settings",
                "setting": "Key settings in SpecialK.ini",
                "value": "TearingMode=0, FlipDiscard=true, AllowTearingInDWM=false",
                "reason": "G-Sync mode: no tearing, optimal flip presentation for windowed.",
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
                "setting": "HAGS (Hardware Accelerated GPU Scheduling)",
                "value": "ON",
                "reason": "Enable in Windows Graphics Settings. Helps latency when GFE removed.",
            },
            {
                "category": "System Setup",
                "setting": "Windows VRR (Variable refresh rate)",
                "value": "OFF",
                "reason": "DISABLE in Windows Graphics Settings. It adds latency.",
            },
            {
                "category": "System Setup",
                "setting": "Multi-Plane Overlay (MPO)",
                "value": "ENABLED (default)",
                "reason": "CRITICAL: MPO must be ENABLED for G-Sync to work in windowed modes.",
            },

            # =========================================================================
            # NVIDIA CONTROL PANEL
            # =========================================================================
            {
                "category": "=== NVIDIA CONTROL PANEL ===",
                "setting": "Set up G-SYNC",
                "value": "Enable for windowed and full screen mode",
                "reason": (
                    "CRITICAL: Must enable for BOTH windowed and fullscreen. "
                    "Display > Set up G-SYNC. This is required for borderless windowed G-Sync."
                ),
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Vertical sync",
                "value": "Fast",
                "reason": "Fast VSync renders uncapped and discards incomplete frames as fallback.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Threaded Optimization",
                "value": "On",
                "reason": "ON for this G-Sync + SpecialK setup.",
            },
            {
                "category": "NVCP (Auto)",
                "setting": "Low Latency Mode",
                "value": "Ultra",
                "reason": "Ultra for aggressive frame pacing with G-Sync.",
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
                "value": "Borderless Windowed (Fullscreen Windowed)",
                "reason": (
                    "Use Borderless/Windowed Fullscreen for multi-monitor compatibility. "
                    "G-Sync works in windowed mode when enabled in NVCP."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "NVCP Fast VSync handles sync. In-game VSync OFF.",
            },
            {
                "category": "In-Game Video",
                "setting": "Resolution",
                "value": "Match your monitor's native resolution",
                "reason": "Borderless windowed uses desktop resolution. Ensure it matches.",
            },

            # =========================================================================
            # MULTI-MONITOR NOTES
            # =========================================================================
            {
                "category": "=== MULTI-MONITOR NOTES ===",
                "setting": "Other monitors",
                "value": "Will remain active during gameplay",
                "reason": (
                    "Unlike exclusive fullscreen, borderless windowed keeps other monitors "
                    "active. You can use overlays, Discord, etc. on secondary displays."
                ),
            },
            {
                "category": "Multi-Monitor",
                "setting": "Expected latency",
                "value": "~1-2ms higher than exclusive fullscreen",
                "reason": (
                    "DWM compositor adds slight latency in windowed modes. "
                    "This is the trade-off for multi-monitor convenience."
                ),
            },
            {
                "category": "Multi-Monitor",
                "setting": "If G-Sync isn't working",
                "value": "Check NVCP G-Sync settings",
                "reason": (
                    "Ensure 'Enable for windowed and full screen mode' is selected in "
                    "Display > Set up G-SYNC. Also verify MPO is not disabled."
                ),
            },
        ]
