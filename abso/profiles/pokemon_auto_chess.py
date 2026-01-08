"""Pokemon Auto Chess (Browser-based WebGL game) profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class PokemonAutoChessProfile(BaseProfile):
    """Optimization profile for Pokemon Auto Chess (browser-based WebGL).

    Focus: Stable WebGL performance in Chrome/browser with smooth frame pacing.

    Pokemon Auto Chess is an auto-battler that runs in the browser using WebGL.
    Unlike competitive games, it doesn't require ultra-low latency but benefits
    from stable GPU performance and reduced background interference.

    Game: https://github.com/keldaanCommunity/pokemonAutoChess
    """

    @property
    def profile_id(self) -> str:
        return "pokemon-auto-chess"

    @property
    def display_name(self) -> str:
        return "Pokemon Auto Chess"

    @property
    def description(self) -> str:
        return "WebGL browser game optimization for stable performance"

    @property
    def optimization_target(self) -> str:
        return "balanced"

    @property
    def executable_hints(self) -> list[str]:
        return ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]

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
            ProcessPriorityHandler(["chrome.exe", "msedge.exe", "firefox.exe"]),
            CNMSettingsHandler(),  # Stop CNM during gaming for power optimization
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,  # Disable Game Bar overlay
                "game_dvr": False,  # Disable background recording
                # HAGS: Generally beneficial for WebGL rendering
                "hags": True,
            },
            "PowerSettingsHandler": {
                # High performance but not ultra - balanced for browser gaming
                "active_plan": "high_performance",
                "disable_usb_suspend": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                # Balanced responsiveness for browser games
                "system_responsiveness": 10,  # Some background tasks OK
                "network_throttling": 0xFFFFFFFF,  # Disable throttling
                "win32_priority_separation": 0x26,  # Short variable quantum, foreground boost
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 4,  # Above normal
                    "scheduling_category": "Medium",
                    "sfio_priority": "Normal",
                },
            },
            "NvidiaSettingsHandler": {
                # Low latency preset - VSync disabled everywhere
                "preset": "low_latency_high_fps",
                # Key settings for WebGL:
                # - Low Latency Mode: On
                # - VSync: Off (disabled for lowest latency)
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited (WebGL uses lots of shaders)
                # - Triple Buffering: Off
                "vsync": "off",
                "triple_buffering": "off",
            },
            "NetworkSettingsHandler": {
                # Network optimization for online gameplay
                "disable_nagle": True,
                "preset": "gaming",
            },
            "GraphicsSettingsHandler": {
                # Keep fullscreen optimizations for browser
                # (borderless window mode is typical for browser games)
                "disable_global_fso": False,
            },
            "ServicesSettingsHandler": {
                # Reduce background interference
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                # Browser games benefit from large RAM cache
                "large_system_cache": 0,  # Optimize for applications
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                # Elevated priority for browser process
                "gpu_priority": 8,
                "cpu_priority": 2,  # Above normal
                "io_priority": 2,
            },
            "CNMSettingsHandler": {
                # Stop CNM during gaming to allow power optimizations
                "action": "stop",
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            # Chrome/Browser Settings
            {
                "category": "Chrome Settings",
                "setting": "Hardware Acceleration",
                "value": "Enabled",
                "reason": "Essential for WebGL performance. Check chrome://gpu for status.",
            },
            {
                "category": "Chrome Settings",
                "setting": "Use Angle Graphics Backend",
                "value": "OpenGL or D3D11",
                "reason": "chrome://flags/#use-angle - D3D11 often fastest on Windows.",
            },
            {
                "category": "Chrome Settings",
                "setting": "WebGL Developer Extensions",
                "value": "Enabled",
                "reason": "chrome://flags/#enable-webgl-developer-extensions",
            },
            {
                "category": "Chrome Settings",
                "setting": "GPU Rasterization",
                "value": "Enabled",
                "reason": "chrome://flags/#enable-gpu-rasterization - Offloads rendering to GPU.",
            },
            # Game-Specific Settings
            {
                "category": "Game Settings",
                "setting": "Graphics Quality",
                "value": "Medium or High",
                "reason": "Balance between visual quality and consistent frame rate.",
            },
            {
                "category": "Game Settings",
                "setting": "Animations",
                "value": "On",
                "reason": "Auto-battlers benefit from visible ability animations.",
            },
            {
                "category": "Game Settings",
                "setting": "Sound Effects",
                "value": "User preference",
                "reason": "Audio cues can help track battle events.",
            },
            # Browser Tab Management
            {
                "category": "Browser Optimization",
                "setting": "Other Tabs",
                "value": "Close or suspend inactive tabs",
                "reason": "Reduces memory and CPU competition for the game tab.",
            },
            {
                "category": "Browser Optimization",
                "setting": "Extensions",
                "value": "Disable unnecessary extensions",
                "reason": "Ad blockers are fine, but disable heavy extensions while playing.",
            },
            {
                "category": "Browser Optimization",
                "setting": "Full Screen Mode",
                "value": "F11 for fullscreen",
                "reason": "Reduces browser UI overhead and improves focus.",
            },
        ]
