"""Slippi Melee (Super Smash Bros. Melee via Dolphin) profile."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.profile_bases import EmulatorLatencyBaseProfile

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


class SlippiMeleeProfile(EmulatorLatencyBaseProfile):
    """Optimization profile for Super Smash Bros. Melee via Slippi Dolphin.

    Focus: Ultra-low input latency for competitive play.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi)"

    @property
    def description(self) -> str:
        return "Ultra-low latency optimization for competitive Melee"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    @property
    def executable_hints(self) -> list[str]:
        return ["Slippi Dolphin.exe", "Dolphin.exe"]

    @property
    def nvidia_binding_executables(self) -> list[str]:
        """Target the Slippi build directly for NVIDIA profile ownership."""
        return ["Slippi Dolphin.exe"]

    @property
    def allow_unverified_nvidia_profile_reuse(self) -> bool:
        """Allow safe reuse of stable ABSO-managed Slippi driver profiles."""
        return True

    @property
    def nvidia_profile_name(self) -> str | None:
        return "Super Smash Bros. Melee (Slippi)"

    @property
    def nvidia_profile_aliases(self) -> list[str]:
        return [
            "Super Smash Bros. Melee (Slippi Universal)",
            "Super Smash Bros. Melee (Slippi Console-Parity)",
            "Super Smash Bros. Melee (Slippi VRR Lab)",
            "Slippi Melee (Streaming)",
        ]

    # === Validation Metadata Overrides ===

    @property
    def graphics_api(self) -> Literal["dx11", "dx12", "vulkan", "opengl", "unknown"]:
        """Backend is user's choice - Vulkan or DX12 both work well."""
        return "unknown"

    def _additional_handlers(self) -> list[SettingsHandler]:
        from abso.settings.dolphin import DolphinConfigHandler

        return [DolphinConfigHandler()]

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # Use max refresh rate for minimum scanout latency
                "max_refresh_rate": True,
            },
            "NvidiaSettingsHandler": {
                # Absolute minimum latency - no sync overhead
                # Per rollback.md canonical spec for Slippi/SSBM
                "low_latency_mode": "on",  # ON recommended; Ultra optional (test both)
                "vsync": "off",  # OFF - removes sync latency entirely
                "vsync_tear_control": "disable",  # Explicit tear control off with VSync OFF
                "vrr_app_override": "force_off",  # OFF - fixed 60fps, no VRR benefit
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "power_management": "prefer_max_performance",
                "shader_cache": "unlimited",
                "threaded_optimization": "off",  # OFF - emulator stability (per canonical spec)
                "max_frame_rate": "off",  # OFF - no artificial limiting
                "triple_buffering": "off",  # OFF - only works with VSync
                # Backend: Experiment with Vulkan and DX12 - both work well.
                # Vulkan often best on NVIDIA/AMD. DX12 + HAGS can also achieve low latency.
                # High refresh still helps via reduced scanout latency even without VRR.
            },
            "DolphinConfigHandler": {
                # Fix Slippi Dolphin configs that get overwritten by Slippi Launcher
                # These are applied every time the profile is activated
                "efb_scale": "1",  # Native resolution for lowest latency
                "texture_scaling_factor": "1",  # No texture upscaling
                "use_scaling_filter": "False",  # No scaling filter
                "use_deposterize": "False",  # No post-processing
                "backend_multithreading": "False",
                "vsync": "False",
                "reduce_timing_dispersion": "True",  # Ishiiruka-specific: tighter frame timing
                "timing_variance": "8",
                "immediate_xfb_enable": "True",
                # Clear presentation features that can linger after switching
                # away from the VRR lab or parity profiles.
                "rush_presentation": "False",
                "smooth_presentation": "False",
                "sync_gpu": "False",
            },
        }

    def _detect_dolphin_backend(self) -> Literal["dx11", "dx12", "vulkan", "opengl"] | None:
        """Best-effort detection of active Dolphin backend from GFX.ini."""
        appdata = os.environ.get("APPDATA")
        if not appdata:
            return None

        gfx_ini = Path(appdata) / "Slippi Launcher" / "netplay" / "User" / "Config" / "GFX.ini"
        if not gfx_ini.exists():
            return None

        try:
            content = gfx_ini.read_text(encoding="utf-8")
        except OSError:
            return None

        match = re.search(r"^GFXBackend\s*=\s*(.+)$", content, re.MULTILINE)
        if not match:
            return None

        raw = match.group(1).strip().lower()
        if "d3d11" in raw or "dx11" in raw:
            return "dx11"
        if "d3d12" in raw or "dx12" in raw:
            return "dx12"
        if "vulkan" in raw:
            return "vulkan"
        if "opengl" in raw or raw.startswith("ogl"):
            return "opengl"
        return None

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get handler settings with backend-aware adaptive overrides."""
        settings = super().get_settings(handler_name).copy()
        backend = self._detect_dolphin_backend()

        if handler_name == "NvidiaSettingsHandler" and backend in {"vulkan", "opengl"}:
            # NVIDIA added DX12 support for Low Latency Mode in the 551.23
            # driver family, but Vulkan/OpenGL still do not expose the same
            # driver queue control path.
            settings["low_latency_mode"] = "off"

        if handler_name == "WindowsSettingsHandler":
            # HAGS behavior is backend-dependent for emulators.
            if backend in {"dx11", "opengl"}:
                settings["hags"] = False
            elif backend in {"dx12", "vulkan"}:
                settings["hags"] = True

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        """Get recommended Dolphin and NVCP settings.

        Optimized for absolute minimum latency in competitive Melee.
        Key notes:
        - Backend: Experiment with Vulkan and DX12 (Vulkan often best on NVIDIA/AMD)
        - HAGS: Generally helps with DX12; results vary by system
        - LLM: On recommended; Ultra may work but test for your setup
        - Lower internal resolution = measurably lower render latency
        - G-Sync/VSync disabled - fixed 60fps games don't benefit from VRR
        - Results vary by system - always test configurations
        """
        return [
            # === WINDOWS SETTINGS ===
            {
                "category": "Windows Settings",
                "setting": "Hardware Accelerated GPU Scheduling (HAGS)",
                "value": "Backend-aware (DX11/OpenGL: Off, DX12/Vulkan: On)",
                "reason": (
                    "HAGS is adapted to Dolphin backend: disable for DX11/OpenGL paths, "
                    "enable for DX12/Vulkan paths."
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

            # === NVIDIA CONTROL PANEL SETTINGS ===
            {
                "category": "Nvidia Control Panel",
                "setting": "G-SYNC",
                "value": "Off",
                "reason": (
                    "Melee runs at fixed 60fps - G-SYNC adds overhead syncing to a constant rate. "
                    "Disabling removes ~1-2ms+ of sync latency. High refresh still helps via "
                    "reduced scanout latency even without VRR."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "Off",
                "reason": (
                    "Disabling V-SYNC eliminates frame queue latency entirely. "
                    "May cause tearing, but competitive players prioritize input latency."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "Backend-aware (DX11/DX12: On, Vulkan/OpenGL: Off)",
                "reason": (
                    "Driver LLM remains useful on DX11, and newer NVIDIA drivers also support "
                    "DX12. Vulkan/OpenGL paths do not expose the same queue control benefit."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Threaded Optimization",
                "value": "Off",
                "reason": "Reduces driver threading overhead for emulation workloads.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Triple Buffering",
                "value": "Off",
                "reason": "Only works with VSync and adds latency.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Max Frame Rate",
                "value": "Off",
                "reason": "No artificial frame limiting.",
            },

            # === DOLPHIN GRAPHICS SETTINGS ===
            {
                "category": "Graphics",
                "setting": "Backend",
                "value": "Vulkan first, then test DX12",
                "reason": (
                    "Official Dolphin guidance still points most NVIDIA/AMD users to Vulkan first. "
                    "DX12 is still worth A/B testing if Vulkan misbehaves or if HAGS + DX12 performs "
                    "better on your exact system."
                ),
            },
            {
                "category": "Graphics",
                "setting": "VSync",
                "value": "Off",
                "reason": "Disable Dolphin's V-SYNC. No sync anywhere for minimum latency (tearing acceptable).",
            },
            {
                "category": "Graphics",
                "setting": "Fullscreen Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Lower latency than borderless windowed.",
            },
            {
                "category": "Graphics",
                "setting": "Internal Resolution",
                "value": "Native (1x) or 2x max",
                "reason": (
                    "Lower resolution = lower render latency. Tested: dropping resolution "
                    "reduced render latency from 0.3ms to 0.1ms. Melee is a 2001 game - "
                    "it doesn't need 4K. Prioritize latency over visuals."
                ),
            },

            # === DOLPHIN CONFIG FILES (Ishiiruka/Stable) ===
            # These settings are in GFX.ini and Dolphin.ini
            {
                "category": "GFX.ini [Settings]",
                "setting": "EFBScale",
                "value": "1 (Native)",
                "reason": (
                    "Native resolution = lowest render latency. Higher res adds GPU work. "
                    "Tested: EFBScale 2 added measurable latency vs EFBScale 1."
                ),
            },
            {
                "category": "GFX.ini [Settings]",
                "setting": "BackendMultithreading",
                "value": "False",
                "reason": "Reduces driver threading overhead.",
            },
            {
                "category": "GFX.ini [Enhancements]",
                "setting": "UseScalingFilter",
                "value": "False",
                "reason": "Scaling adds GPU overhead.",
            },
            {
                "category": "GFX.ini [Enhancements]",
                "setting": "UseDePosterize",
                "value": "False",
                "reason": "Post-processing adds GPU overhead.",
            },
            {
                "category": "GFX.ini [Enhancements]",
                "setting": "TextureScalingFactor",
                "value": "1",
                "reason": "Texture upscaling adds GPU overhead.",
            },
            {
                "category": "GFX.ini [Hacks]",
                "setting": "EFBAccessEnable",
                "value": "False",
                "reason": "EFB access is slow - disable for performance.",
            },
            {
                "category": "GFX.ini [Hacks]",
                "setting": "EnableGPUTextureDecoding",
                "value": "True",
                "reason": "Offloads texture decoding to GPU.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "TimingVariance",
                "value": "8",
                "reason": "Ishiiruka-specific: reduces frame timing variance.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "ReduceTimingDispersion",
                "value": "True",
                "reason": "Ishiiruka-specific: tighter frame timing.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "SyncGPU",
                "value": "False",
                "reason": "GPU sync adds latency - disable.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "ImmediateXFBEnable",
                "value": "True (default for Melee)",
                "reason": "Immediately Present XFB - skips frame buffer queue for lower latency.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "RushPresentation",
                "value": "Off by default (manual A/B test)",
                "reason": (
                    "Rush Frame Presentation can lower latency on some systems, but the gain varies a lot. "
                    "This profile keeps it off by default so the no-sync path stays deterministic unless you "
                    "explicitly A/B test it."
                ),
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "SmoothPresentation",
                "value": "False",
                "reason": (
                    "Keep smoothing off for the competitive no-sync path. This is only meant for "
                    "the VRR lab profile."
                ),
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "TimeStretching",
                "value": "False",
                "reason": "Audio time stretching adds processing overhead.",
            },
            {
                "category": "Game Settings (GALE01.ini)",
                "setting": "MMU",
                "value": "False",
                "reason": "Memory Management Unit emulation adds overhead - not needed for Melee.",
            },
            {
                "category": "Game Settings (GALE01.ini)",
                "setting": "FPRF",
                "value": "False",
                "reason": "Floating point result flags add CPU overhead - not needed for Melee.",
            },

            # === AUDIO SETTINGS ===
            {
                "category": "Audio",
                "setting": "Backend",
                "value": "Exclusive WASAPI (Ishiiruka) / Cubeb (Mainline)",
                "reason": "Exclusive mode bypasses Windows audio mixer for lowest latency.",
            },
            {
                "category": "Audio",
                "setting": "Latency",
                "value": "Lowest stable setting",
                "reason": "Lower is better, but too low causes crackling.",
            },

            # === CONTROLLER SETTINGS ===
            {
                "category": "Controller",
                "setting": "Adapter Mode",
                "value": "Wii U / Switch mode",
                "reason": "Not PC mode. Native adapter support has lower latency.",
            },
            {
                "category": "Controller",
                "setting": "Background Input",
                "value": "On",
                "reason": "Allows input when alt-tabbed.",
            },

            # === WHY HIGH REFRESH HELPS WITHOUT VRR ===
            {
                "category": "Display Info",
                "setting": "High refresh benefit",
                "value": "Reduced scanout latency (no G-Sync needed)",
                "reason": (
                    "60fps @ 60Hz = ~17ms scanout, 60fps @ 240Hz = ~4ms scanout. "
                    "This benefit is from faster pixel refresh, NOT from VRR. "
                    "Use your monitor's max refresh rate with G-Sync/VSync OFF for minimum latency."
                ),
            },
            {
                "category": "Display Info",
                "setting": "Tearing",
                "value": "May occur but minimal impact",
                "reason": (
                    "With 60fps on a high refresh display, tears are small and fast-moving. "
                    "The latency reduction far outweighs the visual artifact for competitive play."
                ),
            },

            # === IMPORTANT DISCLAIMER ===
            {
                "category": "Important",
                "setting": "System Variance Disclaimer",
                "value": "Results vary by system",
                "reason": (
                    "Latency improvements depend on your specific GPU, CPU, drivers, and settings. "
                    "Always test configurations rather than assuming one setting is universally best. "
                    "The settings above are starting points - experiment to find what works for you."
                ),
            },
        ]


class SlippiMeleeUniversalProfile(SlippiMeleeProfile):
    """Lowest-latency Slippi profile with fixed HAGS (no reboot required).

    Unlike the base slippi-melee profile which toggles HAGS based on
    Dolphin backend (DX11/OpenGL: off, DX12/Vulkan: on), this profile
    keeps HAGS always enabled. Applying this profile never requires a
    system restart, matching how Overwatch 2 and other modern titles
    treat HAGS as a fixed system-level setting.

    Optimized for the competitive no-sync path while keeping HAGS fixed.
    Dolphin's own latency features (Immediately Present XFB, Rush Frame
    Presentation) provide far greater latency reduction than any HAGS
    toggle, so fixing HAGS=True avoids unnecessary reboots with no
    meaningful latency penalty.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee-universal"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi Universal)"

    @property
    def description(self) -> str:
        return "Lowest latency, fixed HAGS on (no reboot), no-sync competitive path"

    @property
    def optimization_target(self) -> str:
        return "minimum_latency"

    def get_settings(self, handler_name: str) -> dict[str, Any]:
        """Get handler settings with fixed HAGS, no MPO toggle, and backend-aware LLM.

        HAGS is always True and MPO is never toggled, so applying this
        profile never triggers a reboot requirement. LLM is still adapted
        per-backend since it is a runtime driver setting.
        """
        settings = super().get_settings(handler_name).copy()

        if handler_name == "WindowsSettingsHandler":
            # Fixed HAGS=True - no backend-dependent toggling.
            # Avoids reboot requirement when switching Dolphin backends.
            # HAGS benefit on DX12/Vulkan outweighs marginal DX11/OpenGL cost.
            settings["hags"] = True

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        base = super().get_in_game_settings()
        # Replace the HAGS entry with fixed-value guidance
        updated = []
        for entry in base:
            if entry.get("setting") == "Hardware Accelerated GPU Scheduling (HAGS)":
                updated.append({
                    "category": "Windows Settings",
                    "setting": "Hardware Accelerated GPU Scheduling (HAGS)",
                    "value": "On (always - no reboot on re-apply)",
                    "reason": (
                        "HAGS is fixed to True regardless of Dolphin backend. This avoids "
                        "reboot requirements when switching backends or re-applying the profile. "
                        "Dolphin's own latency features (ImmediateXFB, RushPresentation) provide "
                        "far more latency reduction than HAGS state changes."
                    ),
                })
            else:
                updated.append(entry)
        return updated


class SlippiMeleeConsoleParityProfile(SlippiMeleeProfile):
    """Console-parity style profile for offline Melee practice on modern displays."""

    @property
    def profile_id(self) -> str:
        return "slippi-melee-console-parity"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi Console-Parity)"

    @property
    def description(self) -> str:
        return "Console-like frame pacing and presentation for offline practice"

    @property
    def optimization_target(self) -> str:
        return "balanced"

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return {
            "WindowsSettingsHandler": {
                # Strict console-style pacing is 60 Hz output cadence.
                "refresh_rate": 60,
            },
            "NvidiaSettingsHandler": {
                # Console-parity: prioritize stable cadence/feel over minimum click-to-pixel latency.
                "low_latency_mode": "off",
                "vsync": "on",
                "vsync_tear_control": "disable",
                "vrr_app_override": "force_off",
                "global_vrr_mode": "off",  # Enforce global VRR off for clean no-sync transitions
                "power_management": "prefer_max_performance",
                "shader_cache": "unlimited",
                "threaded_optimization": "off",
                "max_frame_rate": "off",
                "triple_buffering": "off",
            },
            "DolphinConfigHandler": {
                # Keep visual overhead minimal but avoid aggressive presentation shortcuts.
                "efb_scale": "1",
                "texture_scaling_factor": "1",
                "use_scaling_filter": "False",
                "use_deposterize": "False",
                "backend_multithreading": "False",
                "vsync": "True",
                "reduce_timing_dispersion": "True",
                "timing_variance": "8",
                "immediate_xfb_enable": "True",
                "sync_gpu": "False",
                "rush_presentation": "False",
                "smooth_presentation": "False",
            },
        }

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Profile Goal",
                "setting": "Target",
                "value": "Console-like pacing and feel (offline)",
                "reason": (
                    "Use this when you want closer console-like presentation cadence on an LCD/OLED, "
                    "not maximum latency reduction."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "On",
                "reason": (
                    "Keeps presentation cadence stable and tear-free for practice sessions where feel "
                    "consistency is preferred over absolute minimum latency."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "Off",
                "reason": (
                    "Avoids aggressive queue reduction. This profile intentionally favors consistent "
                    "frame pacing over minimum queue depth."
                ),
            },
            {
                "category": "Windows Display",
                "setting": "Desktop Refresh Rate",
                "value": "60 Hz",
                "reason": (
                    "The profile forces 60 Hz output for stricter console-style cadence on flat panels. "
                    "Switch back to high refresh when using the competitive profile."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Dolphin VSync",
                "value": "On",
                "reason": "Keep VSync enabled in Dolphin for stable, console-style frame presentation.",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "RushPresentation",
                "value": "False",
                "reason": (
                    "Disables aggressive latency-cutting presentation path to preserve a more console-like feel."
                ),
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "ImmediateXFBEnable",
                "value": "True (Slippi default)",
                "reason": (
                    "Keep Slippi defaults unless you are running controlled local tests and explicitly "
                    "understand the compatibility/latency tradeoff."
                ),
            },
            {
                "category": "Display",
                "setting": "G-SYNC / VRR",
                "value": "Off",
                "reason": (
                    "Melee is fixed 60fps. VRR is not required for this parity profile and can alter pacing feel."
                ),
            },
        ]


class SlippiMeleeVRRLabProfile(SlippiMeleeProfile):
    """Experimental Slippi profile for controlled VRR/G-SYNC A/B testing."""

    @property
    def profile_id(self) -> str:
        return "slippi-melee-vrr-lab"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi VRR Lab)"

    @property
    def description(self) -> str:
        return "Experimental VRR/G-SYNC test profile for Slippi latency and pacing A/B"

    @property
    def optimization_target(self) -> str:
        return "balanced"

    @property
    def requires_confirmed_vrr_support(self) -> bool:
        return True

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        settings = super()._settings_overrides()

        settings["NvidiaSettingsHandler"].update({
            # VRR path for controlled testing (not treated as universal best).
            "vsync": "on",
            "vrr_app_override": "allow",
            "vsync_tear_control": "disable",
            "global_vrr_mode": "fullscreen_only",
            "max_frame_rate": "off",
            "triple_buffering": "off",
        })

        settings["GraphicsSettingsHandler"] = {
            "disable_global_fso": True,
        }

        settings["DolphinConfigHandler"].update({
            # Keep queue path explicit and avoid double-sync in Dolphin.
            "vsync": "False",
            "rush_presentation": "False",
            "smooth_presentation": "True",
        })

        return settings

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [
            {
                "category": "Profile Goal",
                "setting": "Target",
                "value": "Controlled VRR A/B test (not universal default)",
                "reason": (
                    "Use this profile to compare VRR behavior against the competitive no-sync profile "
                    "on your exact monitor/OSD/backend path."
                ),
            },
            {
                "category": "Display",
                "setting": "Monitor OSD Adaptive Sync",
                "value": "On",
                "reason": "Required so Windows/NVIDIA can confirm VRR capability.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "G-SYNC",
                "value": "On (fullscreen)",
                "reason": "Profile enables fullscreen VRR mode for Slippi Dolphin.",
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "On",
                "reason": (
                    "Used as a VRR safety net. Dolphin VSync stays off to avoid double-sync."
                ),
            },
            {
                "category": "Graphics",
                "setting": "Dolphin VSync",
                "value": "Off",
                "reason": "Keep synchronization in one place (NVCP VRR path).",
            },
            {
                "category": "Dolphin.ini [Core]",
                "setting": "SmoothPresentation",
                "value": "True",
                "reason": "Intended to improve cadence behavior on VRR displays during lab testing.",
            },
            {
                "category": "Measurement",
                "setting": "A/B Method",
                "value": "Compare against slippi-melee over repeat runs",
                "reason": (
                    "Judge by repeated input-to-photon consistency and frame pacing, not single-session readouts."
                ),
            },
        ]


