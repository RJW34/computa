"""Slippi Melee (Super Smash Bros. Melee via Dolphin) profile."""

from __future__ import annotations

import os
import re
from pathlib import Path
from typing import TYPE_CHECKING, Any, Literal

from abso.profiles.profile_bases import (
    EmulatorLatencyBaseProfile,
    fso_overrides,
    merge_settings_map,
)

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


# Dolphin/Slippi renders SDR; the HDR variants run the game as SDR-in-HDR via
# Windows HDR composition for users who get eye-strain relief from HDR
# desktop tone-mapping. The latency cost vs the pure-SDR exclusive lane is
# small but nonzero, so the HDR siblings inherit every other latency choice
# from their SDR parents unchanged.
_HDR_OVERRIDES: dict[str, dict[str, Any]] = {
    "WindowsSettingsHandler": {
        "hdr": True,
        "advanced_color": True,  # Win11 24H2+ WCG pairing
        "auto_hdr": False,  # Dolphin renders true SDR; Auto HDR would inject fake HDR
        # 200 nits paper-white is the standard OLED / Mini-LED starting point
        # for SDR-in-HDR. Driver installs reset this slider; asserting it
        # restores correct tone-mapping so Dolphin doesn't render blown-out.
        "sdr_white_level_nits": 200,
    },
    "GraphicsSettingsHandler": {
        # Keep ACM off so the HDR path tone-maps from the source gamut rather
        # than being clamped to sRGB system-wide by Win11 24H2+ Auto Color
        # Management.
        "disable_auto_color_management": True,
    },
    "ColorProfileSettingsHandler": {
        # Match the OW2-HDR convention: native (no explicit sRGB
        # association). On this hardware (LG OLED primary + Alienware
        # QD-OLED secondary + Windows HDR on) the sRGB ICC clamp was
        # empirically verified to LOOK MORE washed-out than native, not
        # less — the LG's internal color processing reacts to the sRGB
        # ICC metadata by switching to an sRGB-simulation picture mode
        # that reads as muted. The COLOR_HDR_SRGB_CLAMP lint rule has
        # the right default for this hardware class.
        "icc_profile": "native",
        # Restore neutral vibrance on the HDR path — the SDR base
        # applies a -5 compensation for wide-gamut SDR-on-OLED, but
        # Windows HDR composition owns gamut mapping and an extra
        # NVCP pull-down would fight it.
        "digital_vibrance": 50,
    },
}


def _hdr_in_game_guidance() -> list[dict[str, str]]:
    """Manual setup notes specific to running Dolphin/Slippi as SDR-in-HDR."""
    return [
        {
            "category": "Windows HDR",
            "setting": "Use HDR (Settings > System > Display)",
            "value": "On",
            "reason": (
                "Dolphin/Slippi renders SDR. With Windows HDR on, the OS tone-maps "
                "Dolphin's SDR output through the HDR pipeline, which is what gives "
                "the lower-strain look. Leave HDR enabled at the OS level before launching Slippi."
            ),
        },
        {
            "category": "Windows HDR",
            "setting": "SDR content brightness",
            "value": "Tune until Dolphin matches your preferred SDR brightness",
            "reason": (
                "ABSO sets the SDR-in-HDR paper-white slider to 200 nits as a starting "
                "point. Move it up or down until the Dolphin window looks right for your "
                "panel and ambient light. This is the slider that controls how bright "
                "Dolphin appears inside the HDR desktop."
            ),
        },
        {
            "category": "Windows HDR",
            "setting": "Auto HDR",
            "value": "Off",
            "reason": (
                "Auto HDR forces a fake HDR expansion on SDR content. Dolphin already runs "
                "fine through native SDR-in-HDR tone-mapping; leaving Auto HDR off keeps "
                "color accurate."
            ),
        },
        {
            "category": "Display",
            "setting": "Exclusive Fullscreen vs SDR-in-HDR latency",
            "value": "Accept a small HDR composition cost",
            "reason": (
                "When Windows is in HDR mode, even 'exclusive fullscreen' SDR apps go through "
                "the HDR composition path. The added latency is small (sub-frame on a high-refresh "
                "display) but it's not zero. The HDR variant is for sessions where eye-strain relief "
                "matters more than the leanest no-sync path; switch back to the SDR sibling "
                "for tournament/practice where latency is the priority."
            ),
        },
    ]


class SlippiMeleeProfile(EmulatorLatencyBaseProfile):
    """Profile for Super Smash Bros. Melee via Slippi Dolphin.

    Focus: latency-focused no-sync settings for competitive play.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi)"

    @property
    def description(self) -> str:
        return "Latency-focused no-sync profile for competitive Melee"

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
    def fullscreen_optimizations_per_exe(self) -> dict[str, bool]:
        # Slippi runs exclusive fullscreen for lowest scanout latency. Disable
        # FSO per-exe so Dolphin is not silently bumped into the composited
        # borderless path for the strict no-sync profile.
        return fso_overrides(self.executable_hints)

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
                # Use max refresh rate for lower scanout time.
                "max_refresh_rate": True,
            },
            "NvidiaSettingsHandler": {
                # No-sync presentation path for fixed-60 emulator play.
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
                "efb_scale": "1",  # Native resolution keeps GPU work low.
                "texture_scaling_factor": "1",  # No texture upscaling
                "use_scaling_filter": "False",  # No scaling filter
                "use_deposterize": "False",  # No post-processing
                "backend_multithreading": "False",
                "vsync": "False",
                "reduce_timing_dispersion": "True",  # Ishiiruka-specific: tighter frame timing
                "timing_variance": "8",
                "immediate_xfb_enable": "True",
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

        Latency-focused no-sync settings for competitive Melee.
        Key notes:
        - Backend: Experiment with Vulkan and DX12 (Vulkan often best on NVIDIA/AMD)
        - HAGS: Generally helps with DX12; results vary by system
        - LLM: On recommended; Ultra may work but test for your setup
        - Lower internal resolution reduces GPU work and can reduce render time
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
                    "Melee runs at fixed 60fps, so this no-sync profile disables VRR. "
                    "High refresh still helps via "
                    "reduced scanout latency even without VRR."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "Off",
                "reason": (
                    "Disabling V-SYNC avoids the VSync queueing path and may cause tearing."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "Low Latency Mode",
                "value": "Backend-aware (DX11/DX12: On, Vulkan/OpenGL: Off)",
                "reason": (
                    "Driver LLM is most predictable on DX11. DX12 behavior is more "
                    "driver/game dependent; Vulkan/OpenGL paths do not expose the same "
                    "queue-control benefit."
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
                "reason": "Disable Dolphin's V-SYNC for the no-sync path (tearing acceptable).",
            },
            {
                "category": "Graphics",
                "setting": "Fullscreen Mode",
                "value": "Exclusive Fullscreen",
                "reason": "Matches the strict fullscreen path this profile configures.",
            },
            {
                "category": "Graphics",
                "setting": "Internal Resolution",
                "value": "Native (1x) or 2x max",
                "reason": (
                    "Lower resolution reduces GPU work and can reduce render time. "
                    "Melee is a 2001 game; native or modest scaling is the safer "
                    "latency-focused default."
                ),
            },

            # === DOLPHIN CONFIG FILES (Ishiiruka/Stable) ===
            # These settings are in GFX.ini and Dolphin.ini
            {
                "category": "GFX.ini [Settings]",
                "setting": "EFBScale",
                "value": "1 (Native)",
                "reason": (
                    "Native resolution keeps GPU work low. Higher EFB scales add render work."
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
                "reason": "Keep smoothing off for the competitive no-sync path.",
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
                "reason": "Exclusive mode bypasses the Windows audio mixer and can reduce audio path latency.",
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
                    "Use your monitor's max refresh rate with G-Sync/VSync OFF for the no-sync path."
                ),
            },
            {
                "category": "Display Info",
                "setting": "Tearing",
                "value": "May occur but minimal impact",
                "reason": (
                    "With 60fps on a high refresh display, tears are small and fast-moving. "
                    "The tradeoff may be acceptable for competitive play if you tolerate tearing."
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
    """No-sync Slippi profile with fixed HAGS (no reboot required).

    Unlike the base slippi-melee profile which toggles HAGS based on
    Dolphin backend (DX11/OpenGL: off, DX12/Vulkan: on), this profile
    keeps HAGS always enabled. Applying this profile never requires a
    system restart, matching how Overwatch 2 and other modern titles
    treat HAGS as a fixed system-level setting.

    Tuned for the competitive no-sync path while keeping HAGS fixed.
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
        return "No-sync competitive path with HAGS fixed on to avoid reapply reboots"

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
                    "not the aggressive no-sync path."
                ),
            },
            {
                "category": "Nvidia Control Panel",
                "setting": "V-SYNC (global/per-game)",
                "value": "On",
                "reason": (
                    "Keeps presentation cadence stable and tear-free for practice sessions where feel "
                    "consistency is preferred over the no-sync latency-focused path."
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


class SlippiMeleeHDRProfile(SlippiMeleeProfile):
    """Competitive Slippi profile with Windows HDR on for eye-strain relief.

    Dolphin/Slippi renders SDR; this variant runs the game as SDR-in-HDR via
    Windows HDR composition. Every latency choice from the base
    SlippiMeleeProfile is preserved (VSync OFF, backend-aware LLM, exclusive
    fullscreen, native EFB). The only difference is that Windows HDR is
    enabled and ACM is disabled, which costs a small amount of composition
    latency in exchange for the lower-strain HDR desktop look.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee-hdr"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi HDR)"

    @property
    def description(self) -> str:
        return (
            "Eye-strain-friendly HDR variant of the competitive Slippi profile. "
            "Same no-sync latency contract; Dolphin renders SDR through Windows HDR."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(super()._settings_overrides(), _HDR_OVERRIDES)

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*_hdr_in_game_guidance(), *super().get_in_game_settings()]


class SlippiMeleeUniversalHDRProfile(SlippiMeleeUniversalProfile):
    """Universal (HAGS-fixed, no-reboot) Slippi profile with Windows HDR on.

    Mirrors SlippiMeleeUniversalProfile - HAGS stays True regardless of
    Dolphin backend so re-applying never triggers a reboot. HDR is added on
    top via the standard Windows HDR composition path so the day-to-day
    "flip in and out" workflow keeps eye-strain relief without losing the
    no-reboot ergonomics.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee-universal-hdr"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi Universal HDR)"

    @property
    def description(self) -> str:
        return (
            "HDR variant of the universal Slippi profile. Fixed HAGS on (no reboot), "
            "no-sync latency contract, Windows HDR for eye-strain relief."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(super()._settings_overrides(), _HDR_OVERRIDES)

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*_hdr_in_game_guidance(), *super().get_in_game_settings()]


class SlippiMeleeConsoleParityHDRProfile(SlippiMeleeConsoleParityProfile):
    """Console-parity Slippi profile with Windows HDR on for eye-strain relief.

    Mirrors SlippiMeleeConsoleParityProfile - 60 Hz refresh, VSync on for
    stable cadence, no aggressive presentation shortcuts. HDR is added on
    top via the standard Windows HDR composition path. Best fit for offline
    practice sessions where you want console-like feel plus the lower-strain
    HDR desktop look.
    """

    @property
    def profile_id(self) -> str:
        return "slippi-melee-console-parity-hdr"

    @property
    def display_name(self) -> str:
        return "Super Smash Bros. Melee (Slippi Console-Parity HDR)"

    @property
    def description(self) -> str:
        return (
            "HDR variant of the console-parity Slippi profile. 60 Hz + VSync on, "
            "Windows HDR for eye-strain relief on offline practice sessions."
        )

    @property
    def is_sdr_only(self) -> bool:
        return False

    def _settings_overrides(self) -> dict[str, dict[str, Any]]:
        return merge_settings_map(super()._settings_overrides(), _HDR_OVERRIDES)

    def get_in_game_settings(self) -> list[dict[str, str]]:
        return [*_hdr_in_game_guidance(), *super().get_in_game_settings()]
