"""Productivity profile - OLED with HDR for browsing and coding.

Optimized for multi-monitor productivity work with HDR enabled.
Unlike gaming profiles, this prioritizes system responsiveness,
smooth scrolling, and keeps background services running.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class ProductivityOLEDProfile(BaseProfile):
    """Optimization profile for productivity work on OLED with HDR.

    Designed for general browsing and multi-monitor coding projects.
    Key differences from gaming profiles:
    - HDR and OLED pixel-shift friendly settings
    - Balanced power for lower heat/noise
    - Background services remain enabled for snappy app launching
    - VRR enabled for smooth scrolling
    - No aggressive latency optimizations
    """

    @property
    def profile_id(self) -> str:
        return "productivity"

    @property
    def display_name(self) -> str:
        return "Desktop / Productivity"

    @property
    def description(self) -> str:
        return "Multi-monitor browsing and coding with HDR enabled"

    @property
    def optimization_target(self) -> str:
        return "productivity"

    @property
    def executable_hints(self) -> list[str]:
        # Common productivity apps - used for detection, not required
        return [
            "Code.exe",           # VS Code
            "devenv.exe",         # Visual Studio
            "chrome.exe",         # Chrome
            "firefox.exe",        # Firefox
            "msedge.exe",         # Edge
            "WindowsTerminal.exe", # Windows Terminal
            "idea64.exe",         # IntelliJ IDEA
        ]

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.color import ColorProfileSettingsHandler
        from abso.settings.display_range import DisplayColorRangeHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        # Minimal handlers - no power handler (would switch power plans) and
        # no mouse handler (changing desktop mouse feel outside a game is out
        # of scope for a productivity profile).
        return [
            WindowsSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            GraphicsSettingsHandler(),
            ColorProfileSettingsHandler(),
            DisplayColorRangeHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                # Game features - keep enabled for compatibility
                "game_mode": True,
                "game_bar": False,  # Not needed for productivity
                "game_dvr": False,  # Not recording
                # HAGS ON - helps with smooth desktop compositing
                "hags": True,
                # HDR enabled for OLED
                "hdr": True,
                # Wide Color Gamut ON — required on Win11 24H2+ to pair with
                # HDR so SDR desktop content renders in OLED's wide gamut
                # rather than sRGB (otherwise the desktop looks washed out).
                "advanced_color": True,
                "auto_hdr": False,  # Not gaming, no need for Auto HDR
                "windowed_optimizations": True,  # Beneficial for desktop apps
                # VRR ON - smooth scrolling benefit
                "vrr_optimize": True,
                # Paper-white ≈ 200 nits under HDR on OLED.
                # Driver installs reset this slider; asserting it here
                # keeps the SDR desktop looking right on every profile apply.
                "sdr_white_level_nits": 200,
            },
            # PowerSettingsHandler intentionally excluded - keep current power plan
            "RegistrySettingsHandler": {
                # Allow more background tasks - we want indexing, search, etc.
                "system_responsiveness": 20,  # Default Windows value
                # Normal priority - not gaming
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 2,  # Normal
                    "scheduling_category": "Medium",
                },
            },
            "NvidiaSettingsHandler": {
                # Balanced explicit settings - smooth visuals with adaptive vsync.
                # No Low Latency Mode and no Prefer Max Performance: productivity
                # wants lower heat/noise and default driver pacing, not
                # latency-favoring clocks.
                "low_latency_mode": "off",
                "power_management": "adaptive",
                "vsync": "adaptive",
                "max_frame_rate": "off",
                "shader_cache": "unlimited",
                "threaded_optimization": "auto",
                "vrr_app_override": "allow",
            },
            "GraphicsSettingsHandler": {
                # Keep FSO enabled - works well with modern apps
                "disable_global_fso": False,
                # Windows 11 24H2+ Auto Color Management can silently turn on
                # after display re-enumeration (common after NVIDIA driver
                # installs) and clamp the wide-gamut OLED desktop to sRGB.
                # Assert it off so a calibrated OLED keeps its native look.
                "disable_auto_color_management": True,
            },
            "ColorProfileSettingsHandler": {
                "icc_profile": "native",      # Keep calibrated profile
                "digital_vibrance": 50,
                "show_osd_guidance": True,
                "game_type": "productivity",
            },
            "DisplayColorRangeHandler": {
                "dynamic_range": "full",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Productivity settings recommendations."""
        return [
            # =========================================================================
            # DISPLAY SETTINGS
            # =========================================================================
            {
                "category": "=== DISPLAY SETTINGS ===",
                "setting": "HDR",
                "value": "ON",
                "reason": "OLED panels excel at HDR. Enable in Windows Display Settings.",
            },
            {
                "category": "Display Settings",
                "setting": "SDR content brightness",
                "value": "40-50%",
                "reason": "Comfortable for extended coding sessions. Adjust in HDR settings.",
            },
            {
                "category": "Display Settings",
                "setting": "Night Light",
                "value": "Scheduled (evening hours)",
                "reason": "Reduces blue light for late-night coding. Settings > Display > Night light.",
            },
            {
                "category": "Display Settings",
                "setting": "Refresh Rate",
                "value": "Maximum available",
                "reason": "Higher refresh = smoother scrolling and cursor movement.",
            },

            # =========================================================================
            # MULTI-MONITOR
            # =========================================================================
            {
                "category": "=== MULTI-MONITOR ===",
                "setting": "Mixed refresh rate monitors",
                "value": "Hardware-accelerated GPU scheduling ON",
                "reason": "HAGS helps with mixed refresh multi-monitor setups.",
            },
            {
                "category": "Multi-Monitor",
                "setting": "VRR/G-Sync",
                "value": "Enable for windowed and full screen mode",
                "reason": "Smooth scrolling in browsers and editors.",
            },
            {
                "category": "Multi-Monitor",
                "setting": "Primary monitor",
                "value": "Set to your main OLED display",
                "reason": "Taskbar and new windows appear on primary monitor.",
            },

            # =========================================================================
            # OLED CARE
            # =========================================================================
            {
                "category": "=== OLED CARE ===",
                "setting": "Screen timeout",
                "value": "5-10 minutes",
                "reason": "Prevent burn-in from static UI elements. Windows Settings > Power.",
            },
            {
                "category": "OLED Care",
                "setting": "Dark mode",
                "value": "Enable in Windows and apps",
                "reason": "Reduces OLED power draw and potential burn-in from bright backgrounds.",
            },
            {
                "category": "OLED Care",
                "setting": "Taskbar auto-hide",
                "value": "Consider enabling",
                "reason": "Reduces static elements. Right-click taskbar > Taskbar settings.",
            },
            {
                "category": "OLED Care",
                "setting": "Pixel refresh",
                "value": "Run periodically per monitor manufacturer",
                "reason": "Most OLED monitors have built-in pixel refresh cycles.",
            },

            # =========================================================================
            # PRODUCTIVITY APPS
            # =========================================================================
            {
                "category": "=== APP SETTINGS ===",
                "setting": "VS Code theme",
                "value": "Dark theme (e.g., Dark+, One Dark Pro)",
                "reason": "Easier on eyes and OLED-friendly.",
            },
            {
                "category": "App Settings",
                "setting": "Browser dark mode",
                "value": "Enable via extension or settings",
                "reason": "Chrome: Settings > Appearance. Firefox: about:config darkmode.",
            },
            {
                "category": "App Settings",
                "setting": "Hardware acceleration",
                "value": "ON in browsers and editors",
                "reason": "Enables GPU rendering for smoother scrolling.",
            },
        ]
