"""PACDeluxe (Tauri-wrapped Pokemon Auto Chess) profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class PACDeluxeProfile(BaseProfile):
    """Optimization profile for PACDeluxe native desktop client.

    Focus: Smooth WebGL performance with stable frame pacing for the
    Tauri-wrapped Pokemon Auto Chess auto-battler.

    PACDeluxe is a native Windows 11 desktop client that wraps the
    Pokemon Auto Chess browser game (Phaser 3 / WebGL) in a Tauri v2 shell
    using WebView2. The app already applies some optimizations internally:
    - ABOVE_NORMAL_PRIORITY_CLASS for the process
    - 1ms timer resolution via timeBeginPeriod
    - DWM transition animations disabled
    - Priority boost disabled for consistent timing

    This profile complements those internal optimizations with system-level
    settings for optimal WebGL rendering and network performance.

    Game: https://github.com/keldaanCommunity/pokemonAutoChess
    Client: https://github.com/RJW34/PACDeluxe
    """

    @property
    def profile_id(self) -> str:
        return "pacdeluxe"

    @property
    def display_name(self) -> str:
        return "PACDeluxe (Pokemon Auto Chess)"

    @property
    def description(self) -> str:
        return "Native Tauri client optimization for smooth WebGL auto-battler gameplay"

    @property
    def optimization_target(self) -> str:
        return "smooth_framerate"

    @property
    def executable_hints(self) -> list[str]:
        # PACDeluxe.exe is the main Tauri app
        # WebView2 spawns msedge.exe processes for rendering
        return ["PACDeluxe.exe", "msedge.exe"]

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
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
            # Target both the Tauri app and WebView2 renderer processes
            ProcessPriorityHandler(["PACDeluxe.exe", "msedge.exe"]),
            CNMSettingsHandler(),
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,  # Disable Game Bar overlay
                "game_dvr": False,  # Disable background recording
                # HAGS: Generally beneficial for WebGL/GPU compositing
                # Works well with WebView2's GPU acceleration
                "hags": True,
            },
            "PowerSettingsHandler": {
                # High performance for consistent frame pacing
                # Not ultimate - auto-battler doesn't need ultra-low latency
                "active_plan": "high_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                # Moderate responsiveness - some background tasks OK
                # Auto-battler is less latency-sensitive than competitive games
                "system_responsiveness": 10,
                "network_throttling": 0xFFFFFFFF,  # Disable throttling for multiplayer
                "win32_priority_separation": 0x26,  # Short variable quantum, foreground boost
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 4,  # Above normal (matches app's internal setting)
                    "scheduling_category": "Medium",
                    "sfio_priority": "Normal",
                },
            },
            "NvidiaSettingsHandler": {
                # Smooth preset for consistent frame pacing
                # WebGL benefits from shader caching and stable GPU clocks
                "preset": "balanced",
                # Key settings applied:
                # - Low Latency Mode: On (not Ultra - WebView handles timing)
                # - VSync: Adaptive (prevents tearing without full VSync lag)
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited (WebGL generates many shaders)
                # - Threaded Optimization: On
                #
                # G-Sync can help smooth variable frame delivery from WebGL
            },
            "NetworkSettingsHandler": {
                # Critical for multiplayer - Pokemon Auto Chess uses:
                # - Firebase for authentication
                # - Colyseus (WebSocket) for game state sync
                "disable_nagle": True,
                "preset": "gaming",
            },
            "GraphicsSettingsHandler": {
                # Keep FSO enabled - PACDeluxe runs windowed/borderless
                # which works well with Windows compositor
                "disable_global_fso": False,
            },
            "ServicesSettingsHandler": {
                # Reduce background interference for smooth gameplay
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                # WebView2 can use significant memory for caching
                # Optimize for applications, not file caching
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                # Match the app's internal ABOVE_NORMAL priority
                # Elevating further could cause system instability
                "gpu_priority": 8,
                "cpu_priority": 2,  # Above normal
                "io_priority": 2,   # Above normal
            },
            "CNMSettingsHandler": {
                # Stop CNM during gaming to allow power optimizations
                "action": "stop",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended settings for PACDeluxe and the system.

        Since PACDeluxe is a Tauri/WebView2 app, some browser-level
        optimizations can still help via Edge WebView2 flags.
        """
        return [
            # === PACDELUXE APP SETTINGS ===
            {
                "category": "PACDeluxe",
                "setting": "Performance Overlay",
                "value": "Ctrl+Shift+P to toggle",
                "reason": "Monitor FPS, CPU, and memory usage in real-time.",
            },
            {
                "category": "PACDeluxe",
                "setting": "Fullscreen Mode",
                "value": "Alt+Enter or F11",
                "reason": "Reduces compositor overhead for smoother rendering.",
            },

            # === WEBVIEW2 / EDGE FLAGS ===
            # These can be set via Windows environment variables
            {
                "category": "WebView2 Optimization",
                "setting": "GPU Acceleration",
                "value": "Enabled (default)",
                "reason": "WebView2 uses GPU acceleration by default. Verify in edge://gpu.",
            },
            {
                "category": "WebView2 Optimization",
                "setting": "Disable Background Throttling",
                "value": "PACDeluxe handles this internally",
                "reason": "The app disables WebView2 background throttling automatically.",
            },

            # === NVIDIA CONTROL PANEL (for WebView2) ===
            {
                "category": "Nvidia Control Panel",
                "setting": "Preferred GPU",
                "value": "High-performance NVIDIA processor",
                "reason": "Ensure WebView2 uses discrete GPU, not integrated graphics.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Power Management Mode",
                "value": "Prefer Maximum Performance",
                "reason": "Prevents GPU clock throttling during gameplay.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Shader Cache Size",
                "value": "Unlimited",
                "reason": "WebGL generates many shaders - larger cache prevents stutter.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Vertical Sync",
                "value": "Adaptive (or Off for lowest latency)",
                "reason": (
                    "Adaptive VSync prevents tearing without constant latency penalty. "
                    "Use 'Off' if you prefer lowest latency and can tolerate minor tearing."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "On",
                "reason": (
                    "Pre-render limit of 1. 'Ultra' is overkill for auto-battlers "
                    "and may cause inconsistent frame pacing."
                ),
            },

            # === NETWORK OPTIMIZATION ===
            {
                "category": "Network",
                "setting": "Connection Type",
                "value": "Wired Ethernet preferred",
                "reason": (
                    "Pokemon Auto Chess is multiplayer - stable connection reduces "
                    "desync. WiFi works but wired is more consistent."
                ),
            },
            {
                "category": "Network",
                "setting": "Background Downloads",
                "value": "Pause during gameplay",
                "reason": "Large downloads can cause network latency spikes.",
            },

            # === GAME SETTINGS (in Pokemon Auto Chess) ===
            {
                "category": "Game Settings",
                "setting": "Graphics Quality",
                "value": "High (or Medium if stuttering)",
                "reason": "Start with High, reduce if frame drops occur during battles.",
            },
            {
                "category": "Game Settings",
                "setting": "Animations",
                "value": "On",
                "reason": "Ability animations help track what's happening in battles.",
            },
            {
                "category": "Game Settings",
                "setting": "Sound",
                "value": "Enabled",
                "reason": "Audio cues provide useful feedback during auto-battles.",
            },

            # === SYSTEM OPTIMIZATION ===
            {
                "category": "System",
                "setting": "Close Background Apps",
                "value": "Recommended",
                "reason": (
                    "Close browsers, Discord (or use PTT), and heavy apps. "
                    "PACDeluxe benefits from reduced CPU/GPU competition."
                ),
            },
            {
                "category": "System",
                "setting": "Display Scaling",
                "value": "100% (native) preferred",
                "reason": "DPI scaling above 100% can affect WebGL rendering performance.",
            },
        ]
