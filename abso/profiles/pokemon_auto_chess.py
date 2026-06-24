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
                # Casual windowed WebGL auto-battler: smoothness over latency.
                # Use the balanced preset for its LLM-on / max-perf / shader-cache
                # baseline, but pair windowed G-SYNC (vrr_app_override allow +
                # the WebGL base's windowed-VRR optimize) with VSync ON rather
                # than the preset's "adaptive" default. Adaptive VSync is the
                # *alternative* to G-SYNC (it disables VSync below refresh), so
                # combining it with G-SYNC is contradictory; G-SYNC + VSync On is
                # the canonical tear-free pairing. Kept identical to PACDeluxe so
                # the two Pokemon Auto Chess siblings stay consistent.
                "preset": "balanced",
                "vrr_app_override": "allow",
                "vsync": "on",
                # Borderless/windowed G-SYNC needs THREE enablers: the two Windows
                # windowed-VRR flags (set by WebGLBaseProfile) AND the NVIDIA
                # global VRR mode. Without this the driver global VRR mode is
                # never reconciled, so windowed G-SYNC can silently fail to engage
                # when switching in from a no-sync profile.
                "global_vrr_mode": "fullscreen_and_windowed",
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


