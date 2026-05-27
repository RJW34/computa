"""Profile Linter - Static validation before profile apply.

This module performs pre-apply validation to catch configuration conflicts,
unsafe combinations, and sanity check aggressive settings.
"""

from __future__ import annotations

import json
import logging
from dataclasses import dataclass, field
from enum import Enum
from typing import TYPE_CHECKING, Any

from abso.core.manifests import load_linter_rules

if TYPE_CHECKING:
    from abso.profiles.base import BaseProfile

logger = logging.getLogger(__name__)


class LintSeverity(Enum):
    """Severity levels for lint issues."""
    ERROR = "error"      # Hard error - abort apply
    WARNING = "warning"  # Allow with explicit override
    INFO = "info"        # Informational only


@dataclass
class LintIssue:
    """Represents a lint check result."""

    code: str
    severity: LintSeverity
    message: str
    details: str | None = None
    setting_path: str | None = None  # e.g., "NvidiaSettingsHandler.low_latency_mode"


@dataclass
class LintResult:
    """Result of linting a profile."""

    profile_id: str
    passed: bool
    errors: list[LintIssue] = field(default_factory=list)
    warnings: list[LintIssue] = field(default_factory=list)
    info: list[LintIssue] = field(default_factory=list)

    @property
    def has_errors(self) -> bool:
        return len(self.errors) > 0

    @property
    def has_warnings(self) -> bool:
        return len(self.warnings) > 0

    def add_issue(self, issue: LintIssue) -> None:
        """Add an issue to the appropriate list."""
        if issue.severity == LintSeverity.ERROR:
            self.errors.append(issue)
            self.passed = False
        elif issue.severity == LintSeverity.WARNING:
            self.warnings.append(issue)
        else:
            self.info.append(issue)


class ProfileLinter:
    """Static validation engine for game profiles.

    Performs pre-apply checks to catch:
    - NVIDIA pipeline conflicts (Reflex + LLM, LLM Ultra + FPS cap, etc.)
    - Windows graphics stack conflicts (HDR on SDR, VRR on latency profiles)
    - Power & scheduler sanity (RAM requirements, scheduler sanity)
    """

    # Profiles that use NVIDIA Reflex (LLM must be OFF)
    REFLEX_PRESETS = {"reflex_game", "reflex_no_sync", "reflex_gsync", "vrr_diablo4"}

    # Presets with LLM Ultra (cannot have explicit FPS cap)
    LLM_ULTRA_PRESETS = {"minimum_latency"}

    # Presets with Fast Sync (not safe for rollback)
    FAST_SYNC_PRESETS: set[str] = set()  # Currently none, but reserved

    # Fixed framerate emulator profiles (VRR adds overhead)
    EMULATOR_TARGETS = {"minimum_latency"}  # optimization_target values

    # Rollback-sensitive optimization targets (ONLINE only - need consistent timing)
    # Note: minimum_latency_offline is NOT in this set - offline profiles can use Fast Sync
    ROLLBACK_TARGETS = {"stable_online"}

    # DX12/Vulkan games where LLM Ultra has limited effect
    DX12_VULKAN_INDICATORS = {"ue5", "vulkan", "dx12", "unreal"}

    def __init__(self, system_ram_gb: int = 32) -> None:
        """Initialize linter.

        Args:
            system_ram_gb: System RAM in GB (used for memory setting checks).
        """
        self.system_ram_gb = system_ram_gb
        fallback_rules = {
            "reflex_presets": sorted(self.REFLEX_PRESETS),
            "llm_ultra_presets": sorted(self.LLM_ULTRA_PRESETS),
            "fast_sync_presets": sorted(self.FAST_SYNC_PRESETS),
            "emulator_targets": sorted(self.EMULATOR_TARGETS),
            "rollback_targets": sorted(self.ROLLBACK_TARGETS),
            "dx12_vulkan_indicators": sorted(self.DX12_VULKAN_INDICATORS),
        }
        rules = load_linter_rules(json.dumps(fallback_rules, sort_keys=True))

        self.reflex_presets = set(rules.get("reflex_presets", fallback_rules["reflex_presets"]))
        self.llm_ultra_presets = set(rules.get("llm_ultra_presets", fallback_rules["llm_ultra_presets"]))
        self.fast_sync_presets = set(rules.get("fast_sync_presets", fallback_rules["fast_sync_presets"]))
        self.emulator_targets = set(rules.get("emulator_targets", fallback_rules["emulator_targets"]))
        self.rollback_targets = set(rules.get("rollback_targets", fallback_rules["rollback_targets"]))
        self.dx12_vulkan_indicators = set(
            rules.get("dx12_vulkan_indicators", fallback_rules["dx12_vulkan_indicators"])
        )

    def lint(self, profile: BaseProfile) -> LintResult:
        """Run all lint checks on a profile.

        Args:
            profile: The profile to validate.

        Returns:
            LintResult with all found issues.
        """
        result = LintResult(profile_id=profile.profile_id, passed=True)

        # Collect all settings from the profile
        settings_map = self._collect_settings(profile)

        # Run all checks
        self._check_nvidia_conflicts(profile, settings_map, result)
        self._check_windows_conflicts(profile, settings_map, result)
        self._check_strict_vrr_contract(profile, settings_map, result)
        self._check_presentation_guidance(profile, settings_map, result)
        self._check_power_sanity(profile, settings_map, result)
        self._check_emulator_vrr(profile, settings_map, result)
        self._check_xbox_mode_conflicts(profile, result)

        # Log results
        if result.has_errors:
            logger.error(
                f"Profile '{profile.profile_id}' failed linting with "
                f"{len(result.errors)} error(s)"
            )
        elif result.has_warnings:
            logger.warning(
                f"Profile '{profile.profile_id}' passed with "
                f"{len(result.warnings)} warning(s)"
            )
        else:
            logger.info(f"Profile '{profile.profile_id}' passed all lint checks")

        return result

    def _collect_settings(self, profile: BaseProfile) -> dict[str, dict[str, Any]]:
        """Collect all settings from a profile's handlers.

        Args:
            profile: The profile to collect settings from.

        Returns:
            Dict mapping handler names to their settings.
        """
        settings_map: dict[str, dict[str, Any]] = {}

        for handler in profile.get_handlers():
            handler_name = handler.__class__.__name__
            settings = profile.get_settings(handler_name)
            if settings:
                settings_map[handler_name] = settings

        return settings_map

    def _check_nvidia_conflicts(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        result: LintResult,
    ) -> None:
        """Check for NVIDIA driver setting conflicts.

        Hard errors:
        - NVIDIA Reflex ON + Driver Low Latency Mode != Off
        - LLM Ultra + Explicit FPS cap present
        - Fast Sync + Rollback-enabled online profile
        - VRR + Fixed-framerate emulator profile

        Warnings:
        - LLM Ultra on DX12 titles
        - Threaded Optimization OFF on non-fighting UE5 titles
        """
        nvidia_settings = settings_map.get("NvidiaSettingsHandler", {})
        if not nvidia_settings:
            return

        preset = nvidia_settings.get("preset", "")
        llm = nvidia_settings.get("low_latency_mode", "")
        vsync = nvidia_settings.get("vsync", "")
        max_fps = nvidia_settings.get("max_frame_rate", "")

        # Check 1: Reflex preset + LLM conflict
        if preset in self.reflex_presets and llm and llm != "off":
            result.add_issue(LintIssue(
                code="NVIDIA_REFLEX_LLM_CONFLICT",
                severity=LintSeverity.ERROR,
                message="NVIDIA Reflex preset requires Low Latency Mode = Off",
                details=(
                    f"Preset '{preset}' uses NVIDIA Reflex. Driver LLM conflicts with "
                    "Reflex and can cause stuttering. Set low_latency_mode='off' or "
                    "remove the explicit setting to use preset default."
                ),
                setting_path="NvidiaSettingsHandler.low_latency_mode",
            ))

        # Check 2: LLM Ultra + explicit FPS cap
        # Note: LLM Ultra and FPS cap CAN work together (Ultra handles queue, cap limits rate)
        # But for online profiles, LLM Ultra's timing isn't ideal for rollback netcode
        if (llm == "ultra" or preset in self.llm_ultra_presets) and max_fps and max_fps != "off":
            # Only warn for online profiles - offline can use aggressive settings
            allows_aggressive = getattr(profile, "allows_aggressive_settings", False)
            if not allows_aggressive:
                result.add_issue(LintIssue(
                    code="NVIDIA_LLM_ULTRA_FPS_CAP",
                    severity=LintSeverity.WARNING,
                    message="LLM Ultra with FPS cap may have frame pacing quirks",
                    details=(
                        "Low Latency Mode 'Ultra' uses Just-In-Time frame submission "
                        "which may interact unexpectedly with explicit FPS caps. "
                        "For consistent online timing, use LLM='On' with your FPS cap. "
                        "For offline/training, this combination is acceptable."
                    ),
                    setting_path="NvidiaSettingsHandler.max_frame_rate",
                ))

        # Check 3: Fast Sync + rollback profile
        if vsync == "fast" and profile.optimization_target in self.rollback_targets:
            result.add_issue(LintIssue(
                code="NVIDIA_FAST_SYNC_ROLLBACK",
                severity=LintSeverity.ERROR,
                message="Fast Sync is incompatible with rollback netcode",
                details=(
                    "Fast Sync causes frame timing irregularities that break rollback "
                    "netcode synchronization. Use VSync='On' or 'Off' for online play."
                ),
                setting_path="NvidiaSettingsHandler.vsync",
            ))

        # Check 4: LLM Ultra warning on DX12/UE5 titles
        if llm == "ultra" or preset in self.llm_ultra_presets:
            profile_desc = profile.description.lower()
            profile_name = profile.display_name.lower()
            is_dx12_vulkan = any(
                ind in profile_desc or ind in profile_name
                for ind in self.dx12_vulkan_indicators
            )
            if is_dx12_vulkan:
                result.add_issue(LintIssue(
                    code="NVIDIA_LLM_ULTRA_DX12",
                    severity=LintSeverity.WARNING,
                    message="LLM Ultra is less predictable on DX12/Vulkan titles",
                    details=(
                        "Modern NVIDIA drivers do support Low Latency Mode on DX12, but "
                        "Ultra is still more prone to pacing quirks than LLM='On'. Vulkan "
                        "also tends to see less consistent driver-side benefit. Prefer "
                        "Reflex when available, otherwise use LLM='On' first."
                    ),
                    setting_path="NvidiaSettingsHandler.low_latency_mode",
                ))

    def _check_windows_conflicts(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        result: LintResult,
    ) -> None:
        """Check for Windows graphics stack conflicts.

        Hard errors:
        - HDR enabled for SDR-only profiles
        - VRR Optimize ON for latency-critical gaming profiles

        Warnings:
        - HAGS enabled on DX11-only titles
        - MPO enabled with known overlay injectors
        """
        windows_settings = settings_map.get("WindowsSettingsHandler", {})
        graphics_settings = settings_map.get("GraphicsSettingsHandler", {})
        color_settings = settings_map.get("ColorProfileSettingsHandler", {})
        display_range_settings = settings_map.get("DisplayColorRangeHandler", {})

        if not windows_settings and not graphics_settings:
            return

        hdr = windows_settings.get("hdr", False)
        auto_hdr = windows_settings.get("auto_hdr", False)
        hags = windows_settings.get("hags", False)

        # Check 1: HDR enabled for SDR-only content
        # Most emulator profiles and older games are SDR-only
        is_sdr_profile = self._is_sdr_profile(profile)
        if is_sdr_profile and (hdr or auto_hdr):
            result.add_issue(LintIssue(
                code="WINDOWS_HDR_SDR_MISMATCH",
                severity=LintSeverity.ERROR,
                message="HDR enabled for SDR-only content",
                details=(
                    "This profile is for SDR content. Enabling Windows HDR with SDR "
                    "content causes washed-out colors. Set hdr=False and auto_hdr=False."
                ),
                setting_path="WindowsSettingsHandler.hdr",
            ))

        # Check 1b: Native HDR profiles must not also enable Auto HDR.
        if hdr and auto_hdr:
            result.add_issue(LintIssue(
                code="WINDOWS_NATIVE_HDR_AUTO_HDR_CONFLICT",
                severity=LintSeverity.ERROR,
                message="Native HDR profile must keep Auto HDR disabled",
                details=(
                    "Auto HDR is only for SDR titles. Native HDR profiles should set "
                    "hdr=True and auto_hdr=False to avoid conflicting tone-mapping paths."
                ),
                setting_path="WindowsSettingsHandler.auto_hdr",
            ))

        # Check 1c: HDR profiles should not clamp SDR composition to sRGB.
        #
        # Empirically verified on a multi-display (LG OLED + AW QD-OLED)
        # rig running Windows Insider build 29591 with NVIDIA 5xx drivers:
        # icc='srgb' alongside hdr=True looks visibly MORE washed-out than
        # icc='native' on wide-gamut panels, regardless of whether the
        # game itself renders HDR or SDR. The OW2-HDR convention (icc=
        # native) is the right choice for both true-HDR titles AND for
        # SDR-rendering apps composited inside Windows HDR mode.
        if hdr and color_settings.get("icc_profile") == "srgb":
            result.add_issue(LintIssue(
                code="COLOR_HDR_SRGB_CLAMP",
                severity=LintSeverity.ERROR,
                message="HDR profile cannot use an sRGB clamp color path",
                details=(
                    "HDR output needs the display's native wide-gamut path. "
                    "Using icc_profile='srgb' under HDR was empirically "
                    "verified to look MORE washed-out than native on the "
                    "LG OLED + QD-OLED multi-display reference rig."
                ),
                setting_path="ColorProfileSettingsHandler.icc_profile",
            ))

        # Check 1d: HDR profiles should not force Limited (TV) RGB range.
        if hdr and display_range_settings.get("dynamic_range") == "limited":
            result.add_issue(LintIssue(
                code="DISPLAY_HDR_LIMITED_RANGE",
                severity=LintSeverity.ERROR,
                message="HDR profile cannot use Limited (TV) RGB range",
                details=(
                    "HDR output requires Full RGB to preserve the full dynamic range. "
                    "Set dynamic_range='full' or 'auto' on DisplayColorRangeHandler."
                ),
                setting_path="DisplayColorRangeHandler.dynamic_range",
            ))

        # Strict/no-sync profiles keep vrr_optimize=False by profile contract.
        # Borderless/capture profiles opt into the windowed compositor path
        # explicitly and are checked by _check_presentation_guidance().

        # Check 3: HAGS warning on DX11-only titles (info only)
        # This is hardware/game dependent, so just info
        if hags:
            result.add_issue(LintIssue(
                code="WINDOWS_HAGS_ENABLED",
                severity=LintSeverity.INFO,
                message="HAGS enabled - verify DX12/Vulkan backend is used",
                details=(
                    "Hardware Accelerated GPU Scheduling works best with DX12/Vulkan. "
                    "If using DX11, HAGS may cause micro-stutters. The profile assumes "
                    "DX12/Vulkan backend is configured."
                ),
                setting_path="WindowsSettingsHandler.hags",
            ))

    def _check_power_sanity(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        result: LintResult,
    ) -> None:
        """Check power and scheduler setting sanity.

        Checks:
        - Disable Paging Executive only if RAM >= 32GB
        """
        memory_settings = settings_map.get("MemorySettingsHandler", {})
        registry_settings = settings_map.get("RegistrySettingsHandler", {})

        # Check 1: Disable Paging Executive with insufficient RAM
        disable_paging = memory_settings.get("disable_paging_executive", 0)
        if disable_paging == 1 and self.system_ram_gb < 32:
            result.add_issue(LintIssue(
                code="MEMORY_PAGING_EXECUTIVE_LOW_RAM",
                severity=LintSeverity.WARNING,
                message=f"Disable Paging Executive with only {self.system_ram_gb}GB RAM",
                details=(
                    "DisablePagingExecutive keeps the kernel in RAM but requires "
                    "sufficient memory. With less than 32GB RAM, this may cause "
                    "issues under heavy load. Consider disable_paging_executive=0."
                ),
                setting_path="MemorySettingsHandler.disable_paging_executive",
            ))

        # Check 2: Aggressive quantum settings for online play
        from abso.settings.registry import WIN32_PRIORITY_GAMING_OFFLINE

        win32_priority = registry_settings.get("win32_priority_separation", 0)
        if (
            win32_priority == WIN32_PRIORITY_GAMING_OFFLINE
            and profile.optimization_target == "stable_online"
        ):
            result.add_issue(LintIssue(
                code="REGISTRY_QUANTUM_ONLINE",
                severity=LintSeverity.INFO,
                message=f"Fixed quantum (0x{WIN32_PRIORITY_GAMING_OFFLINE:02X}) used for online profile",
                details=(
                    "Win32PrioritySeparation uses fixed short quantum. "
                    "This is a latency-focused scheduler tradeoff and may reduce timing flexibility "
                    "for rollback netcode. Monitor for issues."
                ),
                setting_path="RegistrySettingsHandler.win32_priority_separation",
            ))

    def _check_presentation_guidance(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        result: LintResult,
    ) -> None:
        """Check that in-game display guidance matches the configured VRR path."""
        if not getattr(profile, "requires_confirmed_vrr_support", False):
            return

        try:
            in_game_settings = profile.get_in_game_settings()
        except Exception:
            return

        display_mode = next(
            (
                entry for entry in in_game_settings
                if str(entry.get("setting", "")).strip().lower() == "display mode"
            ),
            None,
        )
        if not display_mode:
            return

        display_value = str(display_mode.get("value", "")).lower()
        display_reason = str(display_mode.get("reason", "")).lower()

        recommends_windowed = any(term in display_value for term in ("borderless", "windowed"))
        if not recommends_windowed:
            positive_windowed_phrases = (
                "switch to borderless",
                "toggle borderless",
                "use borderless",
                "run borderless",
                "borderless windowed",
                "windowed mode",
            )
            negative_windowed_phrases = (
                "do not switch",
                "do not use",
                "don't switch",
                "don't use",
                "adds compositor latency",
                "disable borderless",
                "avoid borderless",
            )
            recommends_windowed = (
                any(phrase in display_reason for phrase in positive_windowed_phrases)
                and not any(phrase in display_reason for phrase in negative_windowed_phrases)
            )

        if not recommends_windowed:
            return

        nvidia_settings = settings_map.get("NvidiaSettingsHandler", {})
        windows_settings = settings_map.get("WindowsSettingsHandler", {})
        global_vrr_mode = (
            nvidia_settings.get("global_vrr_mode")
            or nvidia_settings.get("global_gsync_mode")
            or nvidia_settings.get("vrr_mode")
        )
        vrr_optimize = bool(windows_settings.get("vrr_optimize", False))

        missing_support: list[str] = []
        if global_vrr_mode != "fullscreen_and_windowed":
            missing_support.append("global_vrr_mode='fullscreen_and_windowed'")
        if not vrr_optimize:
            missing_support.append("WindowsSettingsHandler.vrr_optimize=True")

        if missing_support:
            result.add_issue(LintIssue(
                code="VRR_DISPLAY_MODE_GUIDANCE_MISMATCH",
                severity=LintSeverity.ERROR,
                message="VRR profile display-mode guidance does not match the configured VRR path",
                details=(
                    "This profile recommends borderless/windowed presentation, but its "
                    "configured VRR path does not support that guidance. Borderless VRR "
                    "profiles must explicitly enable windowed G-SYNC support. Missing: "
                    f"{', '.join(missing_support)}."
                ),
                setting_path="NvidiaSettingsHandler.global_vrr_mode",
            ))

    def _check_strict_vrr_contract(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        result: LintResult,
    ) -> None:
        """Ensure fullscreen-only VRR profiles opt into the strict display-path contract."""
        nvidia_settings = settings_map.get("NvidiaSettingsHandler", {})
        if not nvidia_settings:
            return

        global_vrr_mode = (
            nvidia_settings.get("global_vrr_mode")
            or nvidia_settings.get("global_gsync_mode")
            or nvidia_settings.get("vrr_mode")
        )
        if str(global_vrr_mode or "").strip().lower() != "fullscreen_only":
            return

        requirements = getattr(profile, "display_path_requirements", None)
        require_overlay_free_path = getattr(requirements, "require_overlay_free_path", False)
        if not isinstance(require_overlay_free_path, bool) or not require_overlay_free_path:
            result.add_issue(LintIssue(
                code="STRICT_VRR_OVERLAY_PATH_REQUIRED",
                severity=LintSeverity.ERROR,
                message="Fullscreen-only VRR profiles must require an overlay-free display path",
                details=(
                    "Strict fullscreen-only VRR profiles need the hardened display-path "
                    "contract so ABSO can auto-remediate or block overlays before apply."
                ),
                setting_path="BaseProfile.display_path_requirements",
            ))

        requires_exact_binding = getattr(profile, "requires_exact_nvidia_binding", False)
        if not isinstance(requires_exact_binding, bool) or not requires_exact_binding:
            result.add_issue(LintIssue(
                code="STRICT_VRR_EXACT_BINDING_REQUIRED",
                severity=LintSeverity.ERROR,
                message="Fullscreen-only VRR profiles must require exact NVIDIA binding proof",
                details=(
                    "Strict fullscreen-only VRR profiles should fail closed when ABSO "
                    "cannot prove the executable is bound to the intended NVIDIA profile."
                ),
                setting_path="BaseProfile.requires_exact_nvidia_binding",
            ))

        executable_hints = list(getattr(profile, "executable_hints", []) or [])
        binding_executables = list(
            getattr(profile, "nvidia_binding_executables", executable_hints) or []
        )
        if len(executable_hints) > 1 and binding_executables == executable_hints:
            result.add_issue(LintIssue(
                code="STRICT_VRR_BINDING_EXECUTABLES_TOO_BROAD",
                severity=LintSeverity.WARNING,
                message="Strict VRR profile reuses all detection aliases for NVIDIA binding",
                details=(
                    "Profiles with multiple executable hints should usually provide a narrower "
                    "nvidia_binding_executables list so strict NVIDIA binding proof targets the "
                    "real game binary instead of every launcher or alias name."
                ),
                setting_path="BaseProfile.nvidia_binding_executables",
            ))

    def _check_emulator_vrr(
        self,
        profile: BaseProfile,
        settings_map: dict[str, dict[str, Any]],
        result: LintResult,
    ) -> None:
        """Check for VRR on fixed-framerate emulator profiles.

        Fixed framerate emulators (Melee @ 60fps, SSBU @ 60fps) don't benefit
        from VRR and the overhead adds latency.
        """
        nvidia_settings = settings_map.get("NvidiaSettingsHandler", {})

        # Detect emulator profile by executable hints or name
        exe_hints = profile.executable_hints
        is_emulator = any(
            hint.lower() in {"dolphin.exe", "slippi dolphin.exe", "ryujinx.exe",
                           "ryujinx.ava.exe", "ryujinx.headless.sdl2.exe"}
            for hint in exe_hints
        )

        if not is_emulator:
            return

        # Check if VRR is being used (no force_off override)
        vrr_override = nvidia_settings.get("vrr_app_override", "")
        preset = nvidia_settings.get("preset", "")

        # If using VRR preset without force_off, warn
        vrr_presets = {"vrr_optimal", "vrr_fighting_game", "vrr_ue5_fighting_game"}
        if preset in vrr_presets and vrr_override != "force_off":
            result.add_issue(LintIssue(
                code="EMULATOR_VRR_OVERHEAD",
                severity=LintSeverity.WARNING,
                message="VRR adds overhead for fixed-framerate emulator",
                details=(
                    "This emulator runs at a fixed framerate (60fps). G-Sync/VRR "
                    "adds overhead when syncing to a constant rate. Consider using "
                    "preset='minimum_latency' with G-Sync disabled for the no-sync path."
                ),
                setting_path="NvidiaSettingsHandler.preset",
            ))

    def _is_sdr_profile(self, profile: BaseProfile) -> bool:
        """Determine if a profile is for SDR-only content.

        Args:
            profile: The profile to check.

        Returns:
            True if the profile is likely SDR-only.
        """
        explicit_flag = getattr(profile, "is_sdr_only", None)
        if isinstance(explicit_flag, bool):
            return explicit_flag

        # Check executable hints for known SDR games/emulators
        sdr_executables = {
            "dolphin.exe", "slippi dolphin.exe",  # Melee - GameCube era
            "ryujinx.exe", "ryujinx.ava.exe",     # SSBU - SDR game
            "rivals2-win64-shipping.exe",         # Rivals 2 - SDR
        }

        for hint in profile.executable_hints:
            if hint.lower() in sdr_executables:
                return True

        # Check profile description/name for SDR indicators
        name_lower = profile.display_name.lower()
        desc_lower = profile.description.lower()

        sdr_indicators = {"sdr", "melee", "slippi", "rivals 2", "rivals2"}
        hdr_indicators = {"hdr", "diablo 4", "diablo4"}

        has_sdr = any(ind in name_lower or ind in desc_lower for ind in sdr_indicators)
        has_hdr = any(ind in name_lower or ind in desc_lower for ind in hdr_indicators)

        return has_sdr and not has_hdr

    def _check_xbox_mode_conflicts(
        self,
        profile: BaseProfile,
        result: LintResult,
    ) -> None:
        """Catch profile declarations that conflict with the Xbox Mode shell.

        Xbox Mode (Win11 25H2 26200.8457+) is a streamlined fullscreen shell
        that swaps the compositor topology. It is incompatible with the
        strict fullscreen-only VRR path ABSO uses for OW2 G-SYNC and
        Diablo 4 HDR — those profiles disable per-exe Fullscreen
        Optimizations to keep the GPU on the true exclusive path.

        Hard error:
        - ``xbox_mode == "on"`` + ``uses_fullscreen_only_vrr_path == True``.
          The shell-layer path competes with the exclusive contract; one of
          the two must give.
        """
        xbox_mode = getattr(profile, "xbox_mode", "leave")
        if xbox_mode != "on":
            return
        if not getattr(profile, "uses_fullscreen_only_vrr_path", False):
            return

        result.add_issue(LintIssue(
            code="XBOX_MODE_FSE_CONFLICT",
            severity=LintSeverity.ERROR,
            message="Xbox Mode 'on' is incompatible with fullscreen-only VRR profiles",
            details=(
                "This profile relies on the strict fullscreen-only VRR path "
                "(per-exe FSO disabled, exclusive-fullscreen compositor). "
                "Xbox Mode rewrites that compositor topology and breaks the "
                "exclusive contract. Either set xbox_mode='off' or 'leave', "
                "or remove the strict fullscreen-only VRR requirement."
            ),
            setting_path="BaseProfile.xbox_mode",
        ))
