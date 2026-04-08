"""Rivals of Aether 2 - Tournament Simulation Profile (144Hz).

Target: Offline tournament conditions simulation on standard gaming PCs.
Design Goal: Maximize practice transfer to tournament environment.

This profile simulates the look, feel, and timing consistency of Rivals 2
played offline at tournaments on standardized gaming PCs (144 Hz fixed refresh).

Priorities (in order):
1. Deterministic frame pacing
2. Stable worst-case latency
3. Visual consistency under rollback
4. High practice transfer fidelity

NOT a latency-minimum lab profile.

Core Assumptions:
- Tournaments run 144 Hz monitors
- VRR / G-SYNC is disabled at events
- VSync is disabled
- FPS variance fits inside larger frame budget
- LAN or near-LAN conditions reduce rollback resimulation cost

EXPLICIT PROHIBITIONS (any deviation is a bug):
- LLM = Ultra (FORBIDDEN - tournaments don't use it)
- Fast Sync / Adaptive Sync (FORBIDDEN)
- VRR / G-SYNC (FORBIDDEN)
- High / Realtime CPU priority (FORBIDDEN)
- Any overlay or injector (Steam, Discord, NVIDIA, RTSS)
- Secondary FPS caps (RTSS or driver caps - use in-game only)

NVIDIA Driver Settings (per-app):
- Low Latency Mode: ON (not Ultra)
- Max Frame Rate: OFF (use in-game 144 cap)
- VSync: OFF
- Power Management: Prefer Maximum Performance
- Threaded Optimization: OFF
- Triple Buffering: OFF
- G-SYNC (per-app): OFF

Canonical one-line definition:
> Exclusive fullscreen + 144Hz + no VRR + NV LLM ON + in-game cap 144 + HAGS ON + Ultimate Performance plan + no overlays
"""

from __future__ import annotations

from typing import Any, Literal

from abso.profiles.profile_bases import Rivals2BaseProfile



class Rivals2TournamentSimProfile(Rivals2BaseProfile):
    """Optimization profile for Rivals 2 Tournament Simulation (144Hz).

    Simulates offline tournament conditions for practice transfer.
    Uses fixed 144Hz refresh with in-game 144 FPS cap.

    This is NOT a minimum latency profile - it's a consistency profile
    designed to match tournament PC conditions.
    """

    @property
    def profile_id(self) -> str:
        return "rivals2-tournament-sim-144hz"

    @property
    def display_name(self) -> str:
        return "Rivals 2: Tournament Sim (144Hz)"

    @property
    def description(self) -> str:
        return "Simulates offline tournament conditions (144Hz, no VRR, practice transfer focus)"

    @property
    def optimization_target(self) -> str:
        return "tournament_simulation"

    @property
    def executable_hints(self) -> list[str]:
        return super().executable_hints

    # === Validation Metadata Overrides ===

    @property
    def is_online_profile(self) -> bool:
        """This profile is for offline tournament simulation / practice."""
        return False

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Rivals 2 uses DirectX 12 (UE5)."""
        return "dx12"

    @property
    def allows_aggressive_settings(self) -> bool:
        """Tournament sim uses conservative settings for consistency."""
        return False

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        """Tournament simulation settings overrides."""
        return {
            "WindowsSettingsHandler": {
                # Override refresh rate to 144Hz for tournament simulation
                "refresh_rate": 144,
            },
            "RegistrySettingsHandler": {
                "win32_priority_separation": 0x26,
            },
            "NvidiaSettingsHandler": {
                # Tournament simulation: 144Hz fixed, use in-game cap
                # LLM ON (NOT Ultra - Ultra is FORBIDDEN)
                "low_latency_mode": "on",  # ON only, not Ultra
                "power_management": "prefer_max_performance",
                "vsync": "off",  # VSync OFF
                "vrr_app_override": "force_off",  # G-SYNC OFF (FORBIDDEN for tournament sim)
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "max_frame_rate": "off",  # Uncapped - use in-game 144 cap
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF - prevents UE5 driver contention
                "triple_buffering": "off",  # OFF (irrelevant without VSync)
            },
            "NetworkSettingsHandler": {
                # Tournament sim is offline-first; keep OS defaults for TCP
                "disable_nagle": False,
                "preset": "default",
            },
            "ProcessPriorityHandler": {
                # Normal or Above Normal priority - High/Realtime FORBIDDEN
                "cpu_priority": 2,
                "io_priority": 2,
            },
            "Rivals2ConfigHandler": {
                "fullscreen_mode": 0,
                "vsync": False,
                "raw_input": True,
                "frame_rate_limit": 144,
                "hdr_output": False,
            },
        }

    def get_forbidden_settings(self) -> dict[str, list[str]]:
        """Get list of explicitly forbidden settings for this profile.

        Returns:
            Dictionary mapping handler to list of forbidden setting descriptions.
        """
        return {
            "NvidiaSettingsHandler": [
                "low_latency_mode: ultra (must be 'on' only)",
                "vsync: fast or adaptive (forbidden entirely)",
                "vrr_app_override: allow (must be force_off)",
            ],
            "ProcessPriorityHandler": [
                "cpu_priority: 3 (High) or 4 (Realtime) - must be 2 or lower",
            ],
            "Overlays": [
                "Steam Overlay",
                "Discord Overlay",
                "NVIDIA Overlay / GeForce Experience",
                "RTSS",
            ],
        }

    def validate_settings(self, applied_settings: dict[str, Any]) -> list[str]:
        """Validate that no forbidden settings are active.

        Args:
            applied_settings: Dictionary of applied settings by handler.

        Returns:
            List of violation messages. Empty if all valid.
        """
        violations = []

        # Check NVIDIA settings
        nvidia = applied_settings.get("NvidiaSettingsHandler", {})
        if nvidia.get("low_latency_mode") == "ultra":
            violations.append("VIOLATION: LLM is Ultra (must be ON only)")
        vrr_override = nvidia.get("vrr_app_override")
        if vrr_override not in (None, "force_off", "disallow", "fixed_refresh"):
            violations.append("VIOLATION: VRR/G-SYNC is enabled (must be OFF)")
        if nvidia.get("vsync") in {"fast", "adaptive", "adaptive_half"}:
            violations.append("VIOLATION: Fast/Adaptive Sync is enabled (FORBIDDEN)")

        # Check CPU priority
        priority = applied_settings.get("ProcessPriorityHandler", {})
        if priority.get("cpu_priority", 0) > 2:
            violations.append("VIOLATION: CPU priority too high (must be Normal or Above Normal)")

        return violations

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended in-game settings for tournament simulation."""
        return [
            {
                "category": "=== TOURNAMENT SIMULATION PROFILE ===",
                "setting": "Purpose",
                "value": "Practice transfer to tournament conditions",
                "reason": "This profile simulates 144-144Hz tournament PCs, NOT minimum latency.",
            },
            {
                "category": "=== EXPLICIT PROHIBITIONS ===",
                "setting": "FORBIDDEN",
                "value": "LLM Ultra, Fast Sync, VRR/G-SYNC, Overlays",
                "reason": "These settings are explicitly prohibited for tournament simulation accuracy.",
            },

            # Display Configuration
            {
                "category": "Display Configuration",
                "setting": "Monitor Refresh Rate",
                "value": "144 Hz",
                "reason": "Tournament standard. System will override to 144Hz if different.",
            },
            {
                "category": "Display Configuration",
                "setting": "Display Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Required for consistent frame delivery.",
            },
            {
                "category": "Display Configuration",
                "setting": "VSync",
                "value": "OFF",
                "reason": "Tournaments disable VSync for input responsiveness.",
            },
            {
                "category": "Display Configuration",
                "setting": "VRR / G-SYNC",
                "value": "OFF (FORBIDDEN)",
                "reason": "Tournament PCs do not use VRR. Disabled for practice transfer.",
            },

            # Frame Rate Control
            {
                "category": "Frame Rate Control",
                "setting": "In-game FPS Limit",
                "value": "144 FPS",
                "reason": "In-game cap at refresh rate. One authoritative cap only.",
            },
            {
                "category": "Frame Rate Control",
                "setting": "Driver FPS Cap (NVIDIA)",
                "value": "OFF",
                "reason": "Uncapped in driver - in-game cap is authoritative.",
            },
            {
                "category": "Frame Rate Control",
                "setting": "Secondary Caps",
                "value": "NONE (driver cap OFF, RTSS disabled)",
                "reason": "Only one FPS cap allowed - the in-game cap.",
            },

            # NVIDIA Control Panel
            {
                "category": "NVIDIA Control Panel",
                "setting": "Low Latency Mode",
                "value": "ON (not Ultra)",
                "reason": "ON reduces queue depth. Ultra is FORBIDDEN for tournament sim.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Max Frame Rate",
                "value": "Off",
                "reason": "Driver cap OFF - in-game 144 FPS cap is authoritative.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Vertical sync",
                "value": "Off",
                "reason": "Tournaments disable VSync.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "G-SYNC",
                "value": "Off (FORBIDDEN)",
                "reason": "Tournament PCs do not have G-SYNC enabled.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Power management mode",
                "value": "Prefer maximum performance",
                "reason": "Consistent GPU clocks for stable frame times.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Threaded optimization",
                "value": "Off",
                "reason": "Prevents UE5 driver contention.",
            },
            {
                "category": "NVIDIA Control Panel",
                "setting": "Triple buffering",
                "value": "Off",
                "reason": "Irrelevant without VSync.",
            },

            # Windows Settings
            {
                "category": "Windows Settings",
                "setting": "Game Mode",
                "value": "ON",
                "reason": "Prioritizes game process.",
            },
            {
                "category": "Windows Settings",
                "setting": "HAGS",
                "value": "ON",
                "reason": "Hardware Accelerated GPU Scheduling enabled.",
            },
            {
                "category": "Windows Settings",
                "setting": "Fullscreen Optimizations",
                "value": "OFF (per executable)",
                "reason": "True exclusive fullscreen for lowest latency.",
            },
            {
                "category": "Windows Settings",
                "setting": "Game Bar / DVR",
                "value": "OFF",
                "reason": "Background capture disabled.",
            },
            {
                "category": "Windows Settings",
                "setting": "HDR / Auto HDR",
                "value": "OFF",
                "reason": (
                    "Tournament simulation intentionally stays on the SDR path. "
                    "The goal is parity with common offline event setups, not maximum display capability."
                ),
            },

            # Power / Scheduling
            {
                "category": "Power / Scheduling",
                "setting": "Power Plan",
                "value": "Ultimate Performance",
                "reason": "Standardized on Ultimate Performance for consistent clocks.",
            },
            {
                "category": "Power / Scheduling",
                "setting": "CPU Priority",
                "value": "Normal or Above Normal",
                "reason": "High / Realtime priority is FORBIDDEN.",
            },

            # Overlays / Injection
            {
                "category": "Overlays / Injection",
                "setting": "Steam Overlay",
                "value": "DISABLED",
                "reason": "All overlays must be disabled for tournament sim.",
            },
            {
                "category": "Overlays / Injection",
                "setting": "Discord Overlay",
                "value": "DISABLED",
                "reason": "All overlays must be disabled for tournament sim.",
            },
            {
                "category": "Overlays / Injection",
                "setting": "NVIDIA Overlay / GFE",
                "value": "DISABLED",
                "reason": "All overlays must be disabled for tournament sim.",
            },
            {
                "category": "Overlays / Injection",
                "setting": "RTSS",
                "value": "DISABLED",
                "reason": "All overlays and frame limiters must be disabled.",
            },
            # Enforcement Summary
            {
                "category": "Enforcement Rules",
                "setting": "Distinct from other profiles",
                "value": "Yes",
                "reason": "This is NOT rivals2-online or rivals2-offline-lab.",
            },
            {
                "category": "Enforcement Rules",
                "setting": "VRR enforcement",
                "value": "NEVER enabled",
                "reason": "VRR must never be enabled for this profile.",
            },
            {
                "category": "Enforcement Rules",
                "setting": "FPS ceiling",
                "value": "144 (via in-game cap)",
                "reason": "FPS should match the 144Hz cap for tournament simulation.",
            },
            {
                "category": "Enforcement Rules",
                "setting": "Refresh override",
                "value": "Force 144Hz if different",
                "reason": "System refresh will be overridden to 144Hz.",
            },
            {
                "category": "Enforcement Rules",
                "setting": "Intended use",
                "value": "Online practice, offline friendlies, tournament simulation",
                "reason": "NOT for ranked ladder optimization.",
            },
        ]



