"""Ryujinx SSBU (Super Smash Bros. Ultimate / HewDraw Remix) profile."""

from __future__ import annotations

from typing import Any

from abso.profiles.profile_bases import EmulatorLatencyBaseProfile


class RyujinxSSBUProfile(EmulatorLatencyBaseProfile):
    """Optimization profile for SSBU/HewDraw Remix via Ryujinx or forks.

    Focus: Ultra-low input latency for competitive platform fighting.
    SSBU runs at 60fps, similar to Melee optimization goals.

    HewDraw Remix (HDR) is a comprehensive gameplay mod that makes
    SSBU play more like traditional platform fighters with enhanced
    mechanics and balance changes.

    Note: The original Ryujinx project was shut down in October 2024
    due to Nintendo legal action. Community forks like Ryubing continue
    development. Executable hints cover both original and common forks.
    """

    @property
    def profile_id(self) -> str:
        return "ryujinx-ssbu"

    @property
    def display_name(self) -> str:
        return "SSBU / HewDraw Remix (Ryujinx)"

    @property
    def description(self) -> str:
        return "Ultra-low latency system path for competitive SSBU/HDR with manual emulator tuning"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return ["Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe", "Ryubing.exe"]

    @property
    def nvidia_profile_name(self) -> str | None:
        return "SSBU / HewDraw Remix (Ryujinx)"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "SSBU / HewDraw Remix (Streaming)",
        ]

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "NvidiaSettingsHandler": {
                # Absolute minimum latency - no sync overhead
                # SSBU is 60fps like Melee, same optimization approach
                # Ryujinx uses Vulkan — LLM has no effect (DX9/DX11 only).
                "low_latency_mode": "off",  # OFF — no benefit on Vulkan render queues
                "power_management": "prefer_max_performance",
                "vsync": "off",  # No sync latency
                "vsync_tear_control": "disable",
                "vrr_app_override": "force_off",  # Fixed 60fps, no VRR benefit
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "shader_cache": "unlimited",  # Critical for emulators
                "threaded_optimization": "on",  # Ryujinx benefits from driver threading
                "triple_buffering": "off",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended Ryujinx and system settings.

        Optimized for minimum latency in competitive SSBU/HewDraw Remix.
        SSBU runs at 60fps - similar optimization approach to Melee.
        """
        return [
            # === WINDOWS SETTINGS ===
            {
                "category": "=== WINDOWS SETTINGS ===",
                "setting": "Hardware Accelerated GPU Scheduling (HAGS)",
                "value": "On",
                "reason": (
                    "HAGS works well with Vulkan (Ryujinx's primary backend). "
                    "Similar to DX12, Vulkan's scheduling model benefits from HAGS."
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
            {
                "category": "Windows Settings",
                "setting": "Game Mode",
                "value": "On",
                "reason": "Prioritizes game processes and reduces background activity.",
            },

            # === NVIDIA CONTROL PANEL ===
            {
                "category": "=== NVIDIA CONTROL PANEL ===",
                "setting": "G-SYNC",
                "value": "Off",
                "reason": (
                    "SSBU runs at fixed 60fps - G-SYNC adds overhead syncing to a constant rate. "
                    "Disabling removes sync latency. High refresh still helps via reduced scanout."
                ),
            },
            {
                "category": "NVCP",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "Disabling V-SYNC eliminates frame queue latency. May cause minor tearing.",
            },
            {
                "category": "NVCP",
                "setting": "Low Latency Mode",
                "value": "Off",
                "reason": (
                    "LLM has no effect on Vulkan render queues (only works in DX9/DX11). "
                    "Setting to Off for accuracy. Ryujinx manages its own frame pacing."
                ),
            },
            {
                "category": "NVCP",
                "setting": "Shader Cache Size",
                "value": "Unlimited",
                "reason": (
                    "Critical for emulators! Ryujinx compiles shaders on-the-fly. "
                    "Unlimited cache prevents stutter from shader recompilation."
                ),
            },
            {
                "category": "NVCP",
                "setting": "Power Management Mode",
                "value": "Prefer Maximum Performance",
                "reason": "Prevents GPU downclocking during gameplay.",
            },
            {
                "category": "NVCP",
                "setting": "Threaded Optimization",
                "value": "On",
                "reason": "Ryujinx benefits from driver threading for shader compilation.",
            },

            # === RYUJINX SETTINGS ===
            {
                "category": "=== RYUJINX SETTINGS ===",
                "setting": "Graphics Backend",
                "value": "Vulkan",
                "reason": (
                    "Vulkan has better performance than OpenGL in Ryujinx. "
                    "Works well with HAGS enabled."
                ),
            },
            {
                "category": "Ryujinx Graphics",
                "setting": "Enable VSync",
                "value": "Off",
                "reason": "Disable VSync in Ryujinx for minimum latency. Let NVCP handle sync (which we also disable).",
            },
            {
                "category": "Ryujinx Graphics",
                "setting": "Resolution Scale",
                "value": "Native (1x) or 2x max",
                "reason": (
                    "Lower resolution = lower render latency. For competitive play, "
                    "prioritize latency over visuals. Native or 2x is recommended."
                ),
            },
            {
                "category": "Ryujinx Graphics",
                "setting": "Aspect Ratio",
                "value": "16:9 (default)",
                "reason": "Native aspect ratio for proper gameplay.",
            },
            {
                "category": "Ryujinx Graphics",
                "setting": "Anti-Aliasing",
                "value": "None",
                "reason": "AA adds GPU overhead. Disable for minimum latency.",
            },
            {
                "category": "Ryujinx Graphics",
                "setting": "Scaling Filter",
                "value": "Bilinear or Nearest",
                "reason": "Simple filters have lowest overhead. Avoid FSR/SMAA for latency.",
            },
            {
                "category": "Ryujinx System",
                "setting": "Enable PPTC (Profiled Persistent Translation Cache)",
                "value": "On",
                "reason": (
                    "PPTC caches compiled code between sessions, dramatically reducing "
                    "stutter after the first run. Essential for smooth gameplay."
                ),
            },
            {
                "category": "Ryujinx System",
                "setting": "Enable FS Integrity Checks",
                "value": "Off",
                "reason": "Disabling speeds up game loading.",
            },
            {
                "category": "Ryujinx System",
                "setting": "Memory Manager Mode",
                "value": "Host Unchecked",
                "reason": (
                    "Fastest memory mode. 'Host Unchecked' skips memory access validation "
                    "for better performance. Use 'Host' if you experience crashes."
                ),
            },
            # Hypervisor is macOS-only — omitted since this tool is Windows-only.
            {
                "category": "Ryujinx CPU",
                "setting": "CPU Backend",
                "value": "JIT (default)",
                "reason": "JIT compilation provides best performance on Windows.",
            },

            # === RYUJINX AUDIO ===
            {
                "category": "=== RYUJINX AUDIO ===",
                "setting": "Audio Backend",
                "value": "SDL2",
                "reason": "SDL2 provides good latency. OpenAL is an alternative if issues occur.",
            },
            {
                "category": "Ryujinx Audio",
                "setting": "Volume",
                "value": "100%",
                "reason": "Full volume - adjust in Windows mixer if needed.",
            },

            # === CONTROLLER SETUP ===
            {
                "category": "=== CONTROLLER ===",
                "setting": "Controller Type",
                "value": "Pro Controller (recommended)",
                "reason": (
                    "Pro Controller mapping works best for SSBU. "
                    "Configure your GameCube adapter or fight stick as Pro Controller."
                ),
            },
            {
                "category": "Controller",
                "setting": "Input Device",
                "value": "Wired or 2.4GHz wireless",
                "reason": (
                    "Wired/USB dongle: 1-4ms latency. Bluetooth: 10-20ms+ latency. "
                    "Never use Bluetooth for competitive play."
                ),
            },
            {
                "category": "Controller",
                "setting": "Deadzones",
                "value": "Configure per controller",
                "reason": "Set appropriate deadzones for your controller to prevent drift.",
            },

            # === HEWDRAW REMIX SPECIFIC ===
            {
                "category": "=== HEWDRAW REMIX ===",
                "setting": "HDR Installation",
                "value": "Use Skyline or ARCropolis",
                "reason": (
                    "HewDraw Remix is loaded via mod frameworks. "
                    "Ensure mods are properly installed in Ryujinx's mod directory."
                ),
            },
            {
                "category": "HewDraw Remix",
                "setting": "Mod Location",
                "value": "mods/contents/[TitleID]/",
                "reason": (
                    "Place HDR files in Ryujinx's mod folder. "
                    "SSBU Title ID: 01006A800016E000"
                ),
            },
            {
                "category": "HewDraw Remix",
                "setting": "Training Mode Features",
                "value": "Frame data display, input display",
                "reason": "HDR adds training mode features useful for competitive practice.",
            },

            # === DISPLAY INFO ===
            {
                "category": "=== DISPLAY INFO ===",
                "setting": "High refresh benefit",
                "value": "Reduced scanout latency (no G-Sync needed)",
                "reason": (
                    "60fps @ 60Hz = ~17ms scanout, 60fps @ 240Hz = ~4ms scanout. "
                    "This benefit is from faster pixel refresh, NOT from VRR. "
                    "Use your monitor's max refresh rate with G-Sync/VSync OFF."
                ),
            },
            {
                "category": "Display Info",
                "setting": "Tearing",
                "value": "May occur but minimal at high refresh",
                "reason": (
                    "With 60fps on a high refresh display, tears are small and fast-moving. "
                    "The latency reduction outweighs the visual artifact for competitive play."
                ),
            },

            # === EXPECTED RESULTS ===
            {
                "category": "=== EXPECTED RESULTS ===",
                "setting": "Target Performance",
                "value": "Locked 60fps with low render latency",
                "reason": (
                    "SSBU should run at locked 60fps on modern hardware. "
                    "If dropping frames, lower resolution scale or check PPTC cache status."
                ),
            },
            {
                "category": "Expected Results",
                "setting": "First Run Stutter",
                "value": "Normal - PPTC needs to build",
                "reason": (
                    "First playthrough will have shader compilation stutter. "
                    "This is cached by PPTC and subsequent runs will be smooth."
                ),
            },
        ]


