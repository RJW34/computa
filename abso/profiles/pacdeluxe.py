"""PACDeluxe (Tauri-wrapped Pokemon Auto Chess) profile."""

from __future__ import annotations

from typing import Any

from abso.profiles.profile_bases import WebGLBaseProfile


class PACDeluxeProfile(WebGLBaseProfile):
    """Profile for PACDeluxe native desktop client.

    Focus: Smooth WebGL performance with stable frame pacing for the
    Tauri-wrapped Pokemon Auto Chess auto-battler.

    PACDeluxe is a native Windows 11 desktop client that wraps the
    Pokemon Auto Chess browser game (Phaser 3 / WebGL) in a Tauri v2 shell
    using WebView2. The app already applies some optimizations internally:
    - ABOVE_NORMAL_PRIORITY_CLASS for the process
    - 1ms timer resolution via timeBeginPeriod
    - DWM transition animations disabled
    - Priority boost disabled for consistent timing

    This profile complements those internal choices with system-level
    settings for stable WebGL rendering and default network behavior.

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
        return "Native Tauri client profile for smooth WebGL auto-battler gameplay"

    @property
    def optimization_target(self) -> str:
        return "smooth_framerate"

    @property
    def executable_hints(self) -> list[str]:
        # pac-deluxe.exe is the main Tauri app (installed to C:\Program Files\PACDeluxe\)
        # WebView2 spawns msedgewebview2.exe processes for rendering
        return ["pac-deluxe.exe", "msedgewebview2.exe"]

    @property
    def nvidia_profile_name(self) -> str | None:
        return "PACDeluxe (Pokemon Auto Chess)"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "PACDeluxe (Streaming)",
        ]

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "PowerSettingsHandler": {
                "disable_pcie_power_saving": True,
            },
            "NvidiaSettingsHandler": {
                # Smooth windowed WebGL frame pacing (Tauri/WebView2). Use the
                # balanced preset's LLM-on / max-perf / unlimited-shader-cache
                # baseline, but pair windowed G-SYNC (vrr_app_override allow +
                # the WebGL base's windowed-VRR optimize) with VSync ON instead
                # of the preset's "adaptive". Adaptive VSync is the alternative
                # to G-SYNC, so pairing it with G-SYNC is contradictory; G-SYNC
                # + VSync On is the canonical tear-free combo and is kept
                # identical to the Pokemon Auto Chess (browser) sibling.
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
                "setting": "Shader Cache",
                "value": "On",
                "reason": "Allows compiled shaders to be reused; preserves the global cache-size limit.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Vertical Sync",
                "value": "On (paired with windowed G-SYNC)",
                "reason": (
                    "G-SYNC + VSync On is the canonical tear-free pairing. Latency "
                    "is irrelevant for an auto-battler, so prefer guaranteed smoothness. "
                    "Do not use Adaptive here - it is the alternative to G-SYNC, not a "
                    "companion."
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


