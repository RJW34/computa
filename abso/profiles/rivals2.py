"""Rivals of Aether 2 profile."""

from __future__ import annotations

from typing import TYPE_CHECKING, Any

from abso.profiles.base import BaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class Rivals2Profile(BaseProfile):
    """Optimization profile for Rivals of Aether 2.

    Focus: Ultra-low input latency for competitive platform fighting.
    Similar to Melee optimization but for a native UE5 game.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2"

    @property
    def description(self) -> str:
        return "Ultra-low latency optimization for competitive play"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return ["Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe"]

    # === Validation Metadata Overrides ===

    @property
    def is_online_profile(self) -> bool:
        """NOT for online play - uses LLM Ultra which causes rollback contention.

        For online/ranked play, use rivals2-online profile instead.
        """
        return False

    @property
    def is_sdr_only(self) -> bool:
        """Rivals 2 is SDR-only."""
        return True

    def get_handlers(self) -> list[SettingsHandler]:
        from abso.settings.cnm import CNMSettingsHandler
        from abso.settings.graphics import GraphicsSettingsHandler
        from abso.settings.memory import MemorySettingsHandler
        from abso.settings.mouse import MouseSettingsHandler
        from abso.settings.network import NetworkSettingsHandler
        from abso.settings.nvidia import NvidiaSettingsHandler
        from abso.settings.nvidia_notifications import NvidiaNotificationHandler
        from abso.settings.power import PowerSettingsHandler
        from abso.settings.process_priority import ProcessPriorityHandler
        from abso.settings.registry import RegistrySettingsHandler
        from abso.settings.rivals2_config import Rivals2ConfigHandler
        from abso.settings.services import ServicesSettingsHandler
        from abso.settings.windows import WindowsSettingsHandler

        return [
            WindowsSettingsHandler(),
            PowerSettingsHandler(),
            RegistrySettingsHandler(),
            NvidiaSettingsHandler(),
            NvidiaNotificationHandler(),  # Disable NVIDIA notifications that break fullscreen
            NetworkSettingsHandler(),
            MouseSettingsHandler(),
            GraphicsSettingsHandler(),
            ServicesSettingsHandler(),
            MemorySettingsHandler(),
            ProcessPriorityHandler([
                "Rivals2-Win64-Shipping.exe",  # Actual UE5 shipping exe
                "RivalsofAether2.exe",
                "Rivals2.exe",
            ]),
            Rivals2ConfigHandler(),  # Enforce game config (fullscreen mode, etc.)
            CNMSettingsHandler(),  # Stop CNM during gaming for power optimization
        ]

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        settings_map: dict[str, dict[str, Any]] = {
            "WindowsSettingsHandler": {
                "game_mode": True,
                "game_bar": False,
                "game_dvr": False,
                "hags": True,  # UE5 generally benefits from HAGS when GFE removed
                # HDR disabled - Rivals 2 is an SDR game (no native HDR support)
                # Enabling Windows HDR with SDR content causes washed-out colors
                "hdr": False,
                "auto_hdr": False,  # Keep Auto HDR off - game is SDR
                # Windows VRR setting should be OFF - it adds latency even in fullscreen
                "vrr_optimize": False,
                "max_refresh_rate": True,  # Set display to max refresh rate for minimum scanout
            },
            "PowerSettingsHandler": {
                "ensure_ultimate_performance": True,
                "active_plan": "ultimate_performance",
                "disable_usb_suspend": True,
                "disable_pcie_power_saving": True,
                "processor_max_performance": True,
            },
            "RegistrySettingsHandler": {
                "system_responsiveness": 10,
                "network_throttling": 0xFFFFFFFF,
                "win32_priority_separation": 0x2A,  # Short fixed quantum, max foreground boost
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                    "sfio_priority": "High",
                },
            },
            "NvidiaSettingsHandler": {
                # NO-SYNC for absolute minimum latency (Default for Rivals 2)
                # See: rivals2-300hz-lowest-latency-guide.md for detailed rationale
                "preset": "no_sync_fighting_game",
                "threaded_optimization": "auto",  # Auto for Rivals 2
                # Settings applied:
                # - G-SYNC: Force OFF (via vrr_app_override)
                # - VSync: OFF (no sync = no sync latency)
                # - Low Latency Mode: On
                # - Max Frame Rate: OFF (uncapped or use in-game cap)
                # - Power Management: Prefer Maximum Performance
                # - Shader Cache: Unlimited
                # - Triple Buffering: Off
                #
                # WHY NO-SYNC FOR RIVALS 2:
                # - Fighting games prioritize minimum latency over visual polish
                # - At 300Hz, tearing is barely visible (~3.33ms tear lines)
                # - No sync overhead = absolute minimum click-to-pixel latency
                # - Rivals 2 lacks NVIDIA Reflex, and LLM has limited effect in DX12/UE5
                #
                # For 300Hz monitors: Keep at 300Hz for fastest scanout (3.33ms).
                # In-game FPS cap: Use 240 (highest preset) or uncapped if available.
                #
                # ALTERNATIVE for tear-free experience:
                # Change to "preset": "vrr_fighting_game" if tearing bothers you.
            },
            "NetworkSettingsHandler": {
                "disable_nagle": True,
                "preset": "gaming",  # TCP global optimizations
            },
            "MouseSettingsHandler": {
                # Disable acceleration for consistent muscle memory
                "disable_acceleration": True,
                "set_linear_curve": True,
            },
            "GraphicsSettingsHandler": {
                # Disable FSO for true exclusive fullscreen
                "disable_global_fso": True,
                # MPO: Leave enabled (default) - disabling breaks VRR/G-Sync
                # The no-sync profile doesn't use VRR, but we don't force disable
                # to avoid issues if user later switches to VRR profile
                "disable_mpo": False,
            },
            "ServicesSettingsHandler": {
                # Disable background services for minimum hitches
                "preset": "gaming",
            },
            "MemorySettingsHandler": {
                # Keep kernel in RAM, optimize for applications
                "large_system_cache": 0,
                "disable_paging_executive": 1,
            },
            "ProcessPriorityHandler": {
                # High priority for the game executable
                "gpu_priority": 8,
                "cpu_priority": 3,  # High
                "io_priority": 3,   # High
            },
            "CNMSettingsHandler": {
                # Stop CNM during gaming to allow power optimizations
                # CNM's SetThreadExecutionState interferes with power management
                "action": "stop",
            },
            "Rivals2ConfigHandler": {
                # Enforce game config settings that may be reset by the game
                # FullscreenMode: 0=Exclusive, 1=Borderless, 2=Windowed
                "fullscreen_mode": 0,  # CRITICAL: Exclusive fullscreen for lowest latency
                "vsync": False,  # Let NVCP handle sync
                "raw_input": True,  # Best input latency
                # Note: frame_rate_limit is set in VRR profile override
            },
            "NvidiaNotificationHandler": {
                # Disable NVIDIA notifications that can break exclusive fullscreen
                # The performance overlay (Alt+R) will still work
                "disable_notifications": True,
            },
        }

        return settings_map.get(handler_name, {})

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game and NVCP settings.

        Two configurations provided based on rivals2-300hz-lowest-latency-guide.md:
        - DEFAULT: No sync (G-SYNC OFF, V-SYNC OFF) - absolute minimum latency
        - ALTERNATIVE: VRR setup for tear-free experience

        Key insight: Rivals 2 has 60Hz game logic - you receive new gameplay
        information 60 times per second regardless of render FPS. Higher FPS
        provides: faster frame delivery, reduced display latency, smoother motion.

        For fighting games, minimum latency takes priority over visual polish.
        At 300Hz, tearing is barely visible (~3.33ms tear lines).
        """
        return [
            # =========================================================================
            # DEFAULT: NO-SYNC SETUP (Absolute Minimum Latency)
            # =========================================================================
            {
                "category": "=== DEFAULT: NO-SYNC (Minimum Latency) ===",
                "setting": "Overview",
                "value": "G-SYNC OFF, V-SYNC OFF, 300Hz, Uncapped/240 FPS",
                "reason": (
                    "Absolute minimum click-to-pixel latency. No sync = no sync overhead. "
                    "At 300Hz, tearing is barely visible. This is the competitive standard for fighting games."
                ),
            },

            # --- NVIDIA Control Panel (No-Sync) ---
            {
                "category": "Nvidia Control Panel",
                "setting": "Set up G-SYNC",
                "value": "UNCHECKED (Disabled)",
                "reason": (
                    "Display > Set up G-SYNC. Uncheck 'Enable G-SYNC, G-SYNC Compatible'. "
                    "Eliminates all VRR overhead. Frames display immediately when ready."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Vertical sync",
                "value": "Off",
                "reason": (
                    "Manage 3D Settings > Program Settings > Rivals2.exe. "
                    "No sync = frames render and display with zero sync latency."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "On (or Off if stuttering)",
                "reason": (
                    "Manage 3D Settings. Reduces render queue depth from ~3 frames to ~1-2. "
                    "Note: Limited effect in DX12/UE5 games. CAN cause stuttering on some systems - "
                    "if you experience micro-stutter, try 'Off' or use Nvidia Profile Inspector to set "
                    "Max Pre-Rendered Frames to 2 (middle ground between latency and smoothness)."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Max Frame Rate",
                "value": "Off",
                "reason": (
                    "Manage 3D Settings. Let GPU render as fast as possible. "
                    "Use in-game cap if needed, not NVCP (in-game has lower limiter latency)."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Power management mode",
                "value": "Prefer maximum performance",
                "reason": "Manage 3D Settings. Prevents GPU downclocking for consistent frametimes.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Triple buffering",
                "value": "Off",
                "reason": "Manage 3D Settings. Only relevant with V-SYNC on (which we disable).",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Preferred refresh rate",
                "value": "Highest available (300Hz)",
                "reason": (
                    "Display > Change resolution. CRITICAL for no-sync setup: "
                    "300Hz = 3.33ms scanout vs 240Hz = 4.17ms. Monitor refresh rate directly determines scanout speed."
                ),
            },

            # --- Windows Settings (No-Sync) ---
            {
                "category": "Windows Settings",
                "setting": "Refresh Rate",
                "value": "300Hz (MUST be at max)",
                "reason": (
                    "Settings > System > Display > Advanced display. "
                    "WITHOUT G-SYNC, monitor refresh rate DIRECTLY determines scanout time. "
                    "300Hz = 3.33ms scanout. 240Hz = 4.17ms scanout. Always use max refresh."
                ),
            },
            {
                "category": "Windows Settings",
                "setting": "Variable refresh rate",
                "value": "Off",
                "reason": (
                    "Settings > System > Display > Graphics > Change default graphics settings. "
                    "Not needed with G-SYNC disabled. Turn off to be explicit."
                ),
            },

            # --- In-Game Settings (No-Sync) ---
            {
                "category": "In-Game Video",
                "setting": "V-SYNC",
                "value": "Off",
                "reason": "No sync of any kind. Frames display immediately when ready.",
            },
            {
                "category": "In-Game Video",
                "setting": "Frame Rate Cap",
                "value": "999 (uncapped) or highest your GPU sustains",
                "reason": (
                    "Rivals 2 now supports custom FPS caps (1-999). For no-sync, set 999 for "
                    "effectively uncapped. No limiter = no limiter latency. FPS will exceed 300 "
                    "if GPU capable - this is intended for minimum latency with no-sync setup."
                ),
            },
            {
                "category": "In-Game Video",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Required for no-sync. Borderless windowed adds compositor latency.",
            },

            # =========================================================================
            # ALTERNATIVE: VRR SETUP (Tear-Free, Slightly Higher Latency)
            # =========================================================================
            {
                "category": "=== ALTERNATIVE: VRR (Tear-Free) ===",
                "setting": "Overview",
                "value": "G-SYNC ON, V-SYNC ON (NVCP), in-game cap at refresh-3",
                "reason": (
                    "Use this if tearing bothers you. Adds ~2-5ms latency vs no-sync. "
                    "V-SYNC acts as safety net only - never activates with FPS capped below refresh. "
                    "For 300Hz: cap at 297. For 240Hz: cap at 237. For 144Hz: cap at 141."
                ),
            },
            {
                "category": "Nvidia Control Panel (VRR Alternative)",
                "setting": "Set up G-SYNC",
                "value": "Enable G-SYNC, G-SYNC Compatible: ON",
                "reason": "Display > Set up G-SYNC. Check 'Enable G-SYNC' and 'Enable for full screen mode'.",
            },
            {
                "category": "Nvidia Control Panel (VRR Alternative)",
                "setting": "Vertical sync",
                "value": "On",
                "reason": (
                    "Manage 3D Settings. Acts as SAFETY NET only with G-SYNC. "
                    "With FPS capped at 240 on 300Hz monitor, V-SYNC never engages."
                ),
            },
            {
                "category": "Nvidia Control Panel (VRR Alternative)",
                "setting": "Low Latency Mode",
                "value": "On (or Off if stuttering)",
                "reason": (
                    "Reduces render queue. 'Ultra' overrides manual FPS caps - avoid with G-SYNC. "
                    "'On' may cause micro-stutter on some systems. If stuttering occurs, try 'Off' or "
                    "use Nvidia Profile Inspector to manually set Pre-Rendered Frames to 2-3."
                ),
            },
            {
                "category": "In-Game Video (VRR Alternative)",
                "setting": "V-SYNC",
                "value": "Off (CRITICAL)",
                "reason": "ALWAYS disable in-game V-SYNC with G-SYNC. NVCP V-SYNC handles sync.",
            },
            {
                "category": "In-Game Video (VRR Alternative)",
                "setting": "Frame Rate Cap",
                "value": "Refresh rate - 3 (e.g., 297 for 300Hz)",
                "reason": (
                    "Must cap below refresh for G-SYNC to work properly. "
                    "With custom cap support (1-999), set exactly 3 below your refresh rate. "
                    "In-game limiter has lower latency than NVCP/RTSS limiters."
                ),
            },

            # =========================================================================
            # COMMON SETTINGS (Both Configurations)
            # =========================================================================
            {
                "category": "In-Game Video (Both)",
                "setting": "Resolution Scale",
                "value": "100% (Native)",
                "reason": "Native resolution for sharpest visuals. Lower only if GPU-limited and can't maintain FPS cap.",
            },
            {
                "category": "In-Game Video (Both)",
                "setting": "Graphics Quality",
                "value": "Medium-High (prioritize stable FPS)",
                "reason": (
                    "Stable frametimes matter more than visual fidelity. Reduce settings if dropping below "
                    "your FPS cap. Fighting games are about consistent frame delivery."
                ),
            },
            {
                "category": "In-Game Video (Both)",
                "setting": "Motion Blur",
                "value": "Off",
                "reason": "Obscures visual clarity in fast-paced combat. Always disable for competitive play.",
            },
            {
                "category": "In-Game Video (Both)",
                "setting": "Anti-Aliasing",
                "value": "TAA (or disable if ghosting)",
                "reason": "UE5 uses TAA-based AA. Disable if it causes ghosting on fast-moving characters.",
            },
            {
                "category": "In-Game Video (Both)",
                "setting": "NVIDIA Reflex",
                "value": "Not available",
                "reason": (
                    "Rivals 2 does not implement NVIDIA Reflex. Combined with UE5/DX12 (where LLM has limited effect), "
                    "there's no driver-level latency reduction for this game. Focus on proper FPS cap + system optimization."
                ),
            },

            # --- Audio & Input (Both) ---
            {
                "category": "Audio (Both)",
                "setting": "Audio Latency",
                "value": "Lowest stable setting",
                "reason": "Audio cues are important for reactions. Lower is better but may cause crackling if too aggressive.",
            },
            {
                "category": "Controller (Both)",
                "setting": "Input Method",
                "value": "Wired or 2.4GHz wireless dongle",
                "reason": "Wired/USB dongle: 1-4ms latency. Bluetooth: 10-20ms+ latency. Never use Bluetooth for competitive play.",
            },

            # =========================================================================
            # LATENCY COMPARISON SUMMARY
            # =========================================================================
            {
                "category": "Latency Comparison",
                "setting": "Expected results at 300Hz monitor",
                "value": "See table below",
                "reason": (
                    "| Configuration           | Scanout | Limiter | Tearing | Total Relative |\n"
                    "|-------------------------|---------|---------|---------|----------------|\n"
                    "| No sync, 999 cap 300Hz  | ~3.3ms  | ~0ms    | Yes     | LOWEST (DEFAULT)|\n"
                    "| G-SYNC+VSYNC, 297 cap   | ~3.4ms  | ~0.5ms  | No      | +2-3ms (VRR)   |\n\n"
                    "WITHOUT G-SYNC: Monitor refresh rate DIRECTLY affects scanout. 300Hz = 3.33ms. "
                    "WITH G-SYNC: Scanout matches FPS. 297fps = 3.37ms scanout."
                ),
            },
            {
                "category": "Latency Comparison",
                "setting": "Custom FPS cap recommendations",
                "value": "Set based on your monitor and sync mode",
                "reason": (
                    "Rivals 2 now supports custom FPS caps (1-999).\n\n"
                    "| Setup | Recommended Cap | Why |\n"
                    "|-------|-----------------|-----|\n"
                    "| No-sync 300Hz | 999 | Uncapped = no limiter latency |\n"
                    "| G-Sync 300Hz | 297 | Refresh - 3 for G-Sync headroom |\n"
                    "| G-Sync 240Hz | 237 | Refresh - 3 for G-Sync headroom |\n"
                    "| G-Sync 144Hz | 141 | Refresh - 3 for G-Sync headroom |\n\n"
                    "In-game limiter (~0.5ms overhead) is faster than NVCP/RTSS (~2-4ms overhead)."
                ),
            },
            {
                "category": "Latency Comparison",
                "setting": "Why 300Hz matters for no-sync",
                "value": "Scanout time is fixed by refresh rate",
                "reason": (
                    "WITHOUT G-SYNC, scanout time = 1000ms / refresh rate:\n"
                    "- 300Hz: 3.33ms scanout (faster)\n"
                    "- 240Hz: 4.17ms scanout (slower)\n\n"
                    "This is different from G-SYNC where scanout matches FPS. "
                    "For no-sync, monitor MUST be at 300Hz for minimum latency."
                ),
            },

            # =========================================================================
            # TROUBLESHOOTING
            # =========================================================================
            {
                "category": "Troubleshooting",
                "setting": "If experiencing micro-stuttering",
                "value": "Adjust Low Latency Mode / Pre-Rendered Frames",
                "reason": (
                    "Low Latency Mode reduces the render queue, which CAN cause stuttering on some "
                    "hardware/game combinations - especially if CPU-bound or with variable frame times. "
                    "Try these in order:\n"
                    "1. Set Low Latency Mode to 'Off' in NVCP\n"
                    "2. Use Nvidia Profile Inspector to set 'Maximum Pre-Rendered Frames' to 2 "
                    "(provides buffer against frame time variance while keeping latency reasonable)\n"
                    "3. If still stuttering, try Pre-Rendered Frames = 3 (driver default)\n\n"
                    "These settings are hardware-dependent. Test and find what works for YOUR system."
                ),
            },

            # =========================================================================
            # RECOMMENDATION
            # =========================================================================
            {
                "category": "Final Recommendation",
                "setting": "Default configuration",
                "value": "No-Sync (G-SYNC OFF, V-SYNC OFF, 300Hz)",
                "reason": (
                    "Fighting games prioritize minimum latency. At 300Hz, tearing is barely visible "
                    "(~3.33ms tear lines). The no-sync setup provides absolute minimum click-to-pixel latency. "
                    "Use VRR alternative only if tearing genuinely bothers you - it adds ~2-5ms. "
                    "NOTE: These recommendations are based on common setups but may not be optimal for all hardware. "
                    "If you experience stuttering, see the Troubleshooting section above."
                ),
            },
        ]
