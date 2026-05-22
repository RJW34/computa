"""Pokemon Auto Chess (Browser-based WebGL game) profile."""

from __future__ import annotations

from typing import Any

from abso.profiles.profile_bases import WebGLBaseProfile


class PokemonAutoChessProfile(WebGLBaseProfile):
    """Profile for Pokemon Auto Chess (browser-based WebGL).

    Focus: Stable WebGL performance in Chrome/browser with smooth frame pacing.

    Pokemon Auto Chess is an auto-battler that runs in the browser using WebGL.
    Unlike competitive games, it does not need a strict no-sync latency path but benefits
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
        return "WebGL browser game profile for stable performance"

    @property
    def optimization_target(self) -> str:
        return "balanced"

    @property
    def executable_hints(self) -> list[str]:
        return ["chrome.exe", "msedge.exe", "firefox.exe", "brave.exe"]

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # Explicit low-latency WebGL settings (avoid preset overrides)
                "low_latency_mode": "on",
                "power_management": "prefer_max_performance",
                "vsync": "off",
                "max_frame_rate": "off",
                "shader_cache": "unlimited",
                "threaded_optimization": "on",
                "triple_buffering": "off",
            },
        }

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


