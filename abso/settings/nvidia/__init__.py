"""Nvidia settings handler.

This package manages Nvidia GPU settings via Nvidia Profile Inspector (NPI).

Example usage:
    from abso.settings.nvidia import NvidiaSettingsHandler

    handler = NvidiaSettingsHandler()
    current = handler.detect()
    issues = handler.audit()
    handler.apply({"preset": "minimum_latency"})
"""

from __future__ import annotations

import contextlib
import logging
import subprocess
import tempfile
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

from .npi import NPI_IMPORTS_DISABLED, NPIManager
from .presets import NVIDIA_PRESETS, NvidiaSettingIDs, NvidiaSettingValues
from .profiles import generate_custom_profile, generate_game_profile, generate_preset_profile

logger = logging.getLogger(__name__)

# Re-export for backwards compatibility
__all__ = [
    "NvidiaSettingsHandler",
    "NvidiaSettingIDs",
    "NvidiaSettingValues",
    "NVIDIA_PRESETS",
    "generate_custom_profile",
    "generate_game_profile",
    "generate_preset_profile",
]

VERIFICATION_SETTING_IDS = {
    "vsync_mode": 0x00A879CF,
    "vsync_tear_control": 0x005A375C,
    "frame_rate_limiter": 0x10835002,
    "frame_rate_limiter_v3": 0x10835002,
    "low_latency_mode": 0x007BA09E,
    "prerendered_frames": 0x007BA09E,
    "vrr_app_override": 0x10A879CF,
    "vrr_app_override_request_state": 0x10A879AC,
    "vrr_mode": 0x1194F158,
    "vrr_request_state": 0x1094F1F7,
    "vrr_requested_state": 0x1094F1F7,
    "vsync_vrr_control": 0x10A879CE,
    "power_management": 0x1057EB71,
    "preferred_pstate": 0x1057EB71,
    "threaded_optimization": 0x20C1221E,
    "shader_cache": 0x00198FFF,
    "triple_buffering": 0x20FDD1F9,
}


class NvidiaSettingsHandler(SettingsHandler):
    """Handles Nvidia GPU settings via Profile Inspector.

    Manages:
    - 3D settings (Low Latency Mode, Power Management, etc.)
    - Per-application profiles
    - Global profile settings

    Note: Full functionality requires Nvidia Profile Inspector (NPI).
    Download from: https://github.com/Orbmu2k/nvidiaProfileInspector
    """

    is_critical_verify = True

    # Backup directory for exported profiles
    BACKUP_DIR: Path = Path(tempfile.gettempdir()) / "abso_nvidia_backups"

    def __init__(self, npi_path: Path | str | None = None) -> None:
        """Initialize Nvidia settings handler.

        Args:
            npi_path: Path to nvidiaProfileInspector.exe.
        """
        self._npi = NPIManager(npi_path)

    @property
    def restore_guarantee(self) -> str:
        """NVIDIA restore is intentionally not promised as automatic/safe."""
        return "none"

    @property
    def NPI_PATH(self) -> Path | None:
        """Get NPI path for backwards compatibility."""
        return self._npi.get_path()

    def detect(self) -> dict[str, Any]:
        """Detect current Nvidia settings.

        Returns GPU info via nvidia-smi. Does NOT read current 3D settings
        to avoid triggering NPI GUI (which doesn't support headless export).
        """
        result: dict[str, Any] = {
            "driver_version": None,
            "gpu_name": None,
            "vram_total_mb": None,
            "npi_available": self._npi.is_available(),
            "npi_path": str(self._npi.get_path()) if self._npi.get_path() else None,
        }

        # Get basic info from nvidia-smi (headless, no GUI)
        gpu_info = self._detect_gpu_info()
        result.update(gpu_info)

        return result

    def audit(self) -> list[Issue]:
        """Audit Nvidia settings for gaming optimization issues.

        Note: Cannot read current 3D settings without triggering NPI GUI.
        This audit only checks NPI availability and provides general guidance.
        """
        issues: list[Issue] = []
        current = self.detect()

        # Check NPI availability
        if not current.get("npi_available"):
            issues.append(Issue(
                title="Nvidia Profile Inspector not found",
                severity="info",
                current_value="Not installed",
                optimal_value="Installed only if NVIDIA profile management is needed",
                explanation=(
                    "NPI is required for full Nvidia 3D settings management. "
                    "Download from: https://github.com/Orbmu2k/nvidiaProfileInspector"
                ),
                category="nvidia",
            ))
            return issues

        # Note: We cannot read current Nvidia 3D settings without triggering NPI GUI
        # (NPI doesn't support headless export). Skip detailed settings audit —
        # applying a profile is how users get profile-specific driver targets.
        return issues

    @staticmethod
    def _allowed_setting_keys() -> tuple[str, ...]:
        return (
            "low_latency_mode",
            "power_management",
            "vsync",
            "max_frame_rate",
            "shader_cache",
            "threaded_optimization",
            "triple_buffering",
            "vrr_app_override",
            "vsync_tear_control",
            "vsync_vrr_control",
        )

    def _extract_requested_settings(
        self,
        raw_settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Normalize NVIDIA handler settings for preflight/apply paths."""
        settings = raw_settings.copy()

        executables = settings.pop("executables", [])
        game_name = settings.pop("game_name", "Game")
        driver_profile_name = settings.pop("profile_name", None)
        raw_profile_aliases = settings.pop("profile_aliases", [])
        driver_profile_aliases = [
            str(alias) for alias in raw_profile_aliases
            if isinstance(alias, str) and alias.strip()
        ]
        require_exact_binding = bool(settings.pop("require_exact_binding", False))
        allow_unverified_existing_profile_reuse = bool(
            settings.pop("allow_unverified_existing_profile_reuse", False)
        )

        global_settings: dict[str, Any] = {}
        raw_global_settings = settings.pop("global_settings", None)
        if isinstance(raw_global_settings, dict):
            global_settings.update(raw_global_settings)

        for key in ("global_vrr_mode", "global_gsync_mode", "vrr_mode"):
            value = settings.pop(key, None)
            if value is not None:
                global_settings["vrr_mode"] = value

        global_gsync = settings.pop("global_gsync", None)
        if global_gsync is not None:
            if isinstance(global_gsync, bool):
                global_settings["vrr_mode"] = "fullscreen_only" if global_gsync else "off"
            else:
                global_settings["vrr_mode"] = global_gsync

        auto_vrr_fps_cap = bool(settings.pop("auto_vrr_fps_cap", False))
        forced_refresh_hz = settings.pop("vrr_refresh_rate_hz", None)

        return {
            "settings": settings,
            "executables": executables,
            "game_name": game_name,
            "driver_profile_name": driver_profile_name,
            "driver_profile_aliases": driver_profile_aliases,
            "global_settings": global_settings,
            "auto_vrr_fps_cap": auto_vrr_fps_cap,
            "forced_refresh_hz": forced_refresh_hz,
            "require_exact_binding": require_exact_binding,
            "allow_unverified_existing_profile_reuse": allow_unverified_existing_profile_reuse,
        }

    def _resolve_requested_nvidia_settings(
        self,
        settings: dict[str, Any],
    ) -> dict[str, Any]:
        """Resolve preset-backed per-app NVIDIA writes."""
        preset_name = settings.get("preset")
        allowed_keys = self._allowed_setting_keys()
        if preset_name and preset_name in NVIDIA_PRESETS:
            preset = NVIDIA_PRESETS[preset_name]
            nvidia_settings = preset.get("settings", {}).copy()
            for key in allowed_keys:
                if key in settings:
                    nvidia_settings[key] = settings[key]
            return nvidia_settings

        return {
            key: value for key, value in settings.items()
            if key in allowed_keys
        }

    def preflight(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Validate strict NVIDIA profile prerequisites before apply."""
        requested = self._extract_requested_settings(settings)
        require_exact_binding = requested["require_exact_binding"]
        allow_unverified_existing_profile_reuse = bool(
            requested["allow_unverified_existing_profile_reuse"]
        )
        executables = list(requested["executables"] or [])

        if not require_exact_binding or not executables:
            return super().preflight(settings)

        nvidia_settings = self._resolve_requested_nvidia_settings(requested["settings"])
        global_settings = dict(requested["global_settings"])
        if not nvidia_settings and not global_settings:
            return super().preflight(settings)

        try:
            from abso.settings.nvidia.nvapi_drs import DRSProfileManager

            manager = DRSProfileManager()
            probe = manager.probe_profile_binding(
                executables,
                profile_name=(
                    str(requested["driver_profile_name"] or requested["game_name"])
                ),
                profile_aliases=list(requested["driver_profile_aliases"]),
            )
        except Exception as e:
            return {
                "success": False,
                "error": f"Could not verify NVIDIA profile binding safely: {e}",
                "warnings": [],
                "notices": [],
            }

        binding_ok = bool(probe.get("app_binding_safe", probe.get("app_binding_exact", False)))
        if (
            not binding_ok
            and allow_unverified_existing_profile_reuse
            and str(probe.get("app_binding_state") or "").strip().lower()
            in {"reused_family_profile", "existing_profile_unverified"}
        ):
            binding_ok = True
        if not binding_ok:
            return {
                "success": False,
                "error": str(
                    probe.get("app_binding_note")
                    or "Exact NVIDIA executable binding could not be confirmed."
                ),
                "warnings": [],
                "notices": [],
            }

        notices: list[str] = []
        selection_note = probe.get("profile_selection_note")
        if selection_note:
            notices.append(str(selection_note))
        binding_note = probe.get("app_binding_note")
        if binding_note:
            if str(probe.get("app_binding_state") or "").strip().lower() in {
                "reused_family_profile",
                "existing_profile_unverified",
            }:
                notices.append(f"Proceeding with stable NVIDIA profile reuse: {binding_note}")
            else:
                notices.append(str(binding_note))

        return {
            "success": True,
            "error": None,
            "warnings": [],
            "notices": notices,
        }

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply NVIDIA settings using direct NVAPI DRS integration.

        This uses NVAPI's DRS (Driver Settings) API directly, allowing safe
        per-game profile modification without wiping the entire profile database.

        Args:
            settings: Dictionary of settings to apply.
        """
        requested = self._extract_requested_settings(settings)
        settings = requested["settings"]
        applied: list[str] = []
        errors: list[str] = []
        warnings: list[str] = []
        notices: list[str] = []
        # Structured signal so callers (applier / tray) don't have to grep the `applied` lines
        # for the "Monitor Adaptive Sync: ..." string. None means we never touched it.
        monitor_adaptive_sync_state: str | None = None

        executables = list(requested["executables"] or [])
        game_name = str(requested["game_name"] or "Game")
        driver_profile_name = requested["driver_profile_name"]
        driver_profile_aliases = list(requested["driver_profile_aliases"])
        global_settings: dict[str, Any] = dict(requested["global_settings"])
        require_exact_binding = bool(requested["require_exact_binding"])
        allow_unverified_existing_profile_reuse = bool(
            requested["allow_unverified_existing_profile_reuse"]
        )

        # Optional auto-cap for VRR profiles. Uses the Blur Busters G-SYNC 101
        # ``refresh - 3`` convention as the V-SYNC safety boundary.  Reflex
        # presence does not change the static cap (separate mechanism, separate
        # purpose — see abso/core/vrr.py for the rationale).
        auto_vrr_fps_cap = bool(requested["auto_vrr_fps_cap"])
        forced_refresh_hz = requested["forced_refresh_hz"]
        if auto_vrr_fps_cap:
            refresh_hz: int | None = None
            if forced_refresh_hz is not None:
                with contextlib.suppress(ValueError, TypeError):
                    refresh_hz = round(float(forced_refresh_hz))
            if refresh_hz is None:
                refresh_hz = self._detect_primary_refresh_rate()

            if refresh_hz and refresh_hz > 0:
                from abso.core.vrr import get_vrr_fps_cap

                auto_cap = get_vrr_fps_cap(refresh_hz)
                settings["max_frame_rate"] = auto_cap
                applied.append(f"Auto VRR FPS cap: {auto_cap} (from {refresh_hz} Hz)")
                logger.info(
                    f"Auto VRR FPS cap enabled for {game_name}: "
                    f"refresh={refresh_hz}Hz cap={auto_cap}"
                )
            else:
                applied.append(
                    "NOTE: Auto VRR FPS cap requested but refresh rate could not be detected"
                )
                logger.warning(
                    f"Auto VRR FPS cap requested for {game_name}, but refresh detection failed"
                )

        # Determine what settings to apply
        nvidia_settings = self._resolve_requested_nvidia_settings(settings)

        if not nvidia_settings and not global_settings:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": ["No NVIDIA settings to apply"],
            }

        if require_exact_binding:
            preflight_result = self.preflight({
                **settings,
                "executables": executables,
                "game_name": game_name,
                "profile_name": driver_profile_name,
                "profile_aliases": driver_profile_aliases,
                "global_settings": global_settings,
                "require_exact_binding": True,
                "allow_unverified_existing_profile_reuse": allow_unverified_existing_profile_reuse,
            })
            if not preflight_result.get("success", True):
                errors.append(str(preflight_result.get("error") or "NVIDIA preflight failed"))
                return {
                    "success": False,
                    "error": "; ".join(errors),
                    "requires_reboot": False,
                    "applied": applied,
                    "warnings": warnings,
                    "notices": notices,
                    "app_bound": False,
                    "npi_launched": False,
                }
            for notice in preflight_result.get("notices", []) or []:
                notices.append(str(notice))

        # Try to apply using NVAPI DRS
        try:
            from abso.settings.nvidia.nvapi_drs import DRSProfileManager

            manager = DRSProfileManager()
            verification_failures: list[str] = []
            global_verification_failures: list[str] = []
            app_bound = True
            npi_launched = False

            # Clean up stale ABSO profiles (0-app leftovers from previous versions)
            profile_name_for_cleanup = str(driver_profile_name or game_name)
            self._cleanup_stale_profiles(manager, profile_name_for_cleanup, game_name)

            # Safety net: when we are already touching the global/base profile,
            # also clear any lingering global FRL so it cannot unexpectedly cap
            # the active game profile.
            if global_settings and "max_frame_rate" not in global_settings:
                global_settings["max_frame_rate"] = "off"

            if global_settings:
                global_result = manager.apply_settings_to_global(global_settings)

                if global_result.get("settings_applied"):
                    applied.append("NVIDIA global profile configured:")
                    for setting, value in global_result["settings_applied"].items():
                        applied.append(f"{setting}: {value}")

                if global_result.get("errors"):
                    for err in global_result["errors"]:
                        errors.append(f"global.{err['setting']}: {err['error']}")

                logger.info(f"NVIDIA global settings applied for {game_name}: {global_settings}")

                try:
                    global_verify_result = manager.get_app_settings()
                    global_verification_failures = self._collect_verification_failures(
                        manager,
                        global_verify_result,
                        global_result.get("settings_applied", {}),
                    )
                    if global_verification_failures:
                        logger.warning(
                            "NVIDIA global post-apply verification mismatches: %s",
                            global_verification_failures,
                        )
                        for failure in global_verification_failures:
                            errors.append(f"global verification failed: {failure}")
                except Exception as ve:
                    logger.warning(f"NVIDIA global post-apply verification skipped: {ve}")

                # Sync monitor OSD Adaptive Sync to match driver VRR mode.
                # The monitor firmware needs Adaptive Sync enabled for G-SYNC
                # to work, and disabled for strict no-sync.
                #
                # DDC/CI is OFF by default — VCP codes are manufacturer-specific
                # and sending wrong codes can cause display glitches. Users must
                # opt in via ddci.enabled in abso.yaml.
                vrr_mode_value = global_settings.get("vrr_mode")
                if vrr_mode_value is not None:
                    from abso.core.config import get_config

                    ddci_config = get_config().ddci
                    if ddci_config.enabled:
                        enable_adaptive = vrr_mode_value not in ("off", "disabled", 0, "0")

                        # Allow the monitor to settle after any preceding HDR /
                        # refresh-rate change. 4 seconds covers the typical EDID
                        # re-handshake on OLED and Mini-LED panels.
                        import time as _time

                        _time.sleep(4)

                        try:
                            from abso.settings.nvidia.monitor_adaptive_sync import (
                                set_monitor_adaptive_sync,
                            )

                            sync_result = set_monitor_adaptive_sync(
                                enable_adaptive,
                                controller_override=ddci_config.controller_override,
                            )
                            if sync_result["success"]:
                                state = "enabled" if enable_adaptive else "disabled"
                                applied.append(f"Monitor Adaptive Sync: {state}")
                                monitor_adaptive_sync_state = state
                                logger.info(f"Monitor Adaptive Sync {state}")
                            elif sync_result.get("error"):
                                logger.warning(
                                    f"Monitor Adaptive Sync toggle failed: {sync_result['error']}"
                                )
                        except Exception as e:
                            logger.warning(f"Monitor Adaptive Sync toggle skipped: {e}")
                    else:
                        logger.info(
                            "Monitor DDC/CI Adaptive Sync skipped (ddci.enabled=false in config)"
                        )

            # Use provided executables (bind all when multiple are supplied)
            if executables and nvidia_settings:
                requested_profile_name = str(driver_profile_name or game_name)
                primary_exe = executables[0]

                if len(executables) == 1:
                    result = manager.apply_settings_to_app(
                        primary_exe,
                        nvidia_settings,
                        profile_name=requested_profile_name,
                        profile_aliases=driver_profile_aliases,
                    )
                else:
                    result = manager.apply_settings_to_profile(
                        executables,
                        nvidia_settings,
                        profile_name=requested_profile_name,
                        profile_aliases=driver_profile_aliases,
                    )

                effective_profile_name = str(result.get("profile_name") or requested_profile_name)
                if result.get("profile_selection_note"):
                    selection_note = str(result["profile_selection_note"])
                    applied.append(selection_note)
                    notices.append(selection_note)

                # Report results
                if result.get("settings_applied"):
                    for setting, value in result["settings_applied"].items():
                        applied.append(f"{setting}: {value}")
                    applied.insert(0, f"NVIDIA profile '{effective_profile_name}' configured:")

                if len(executables) > 1:
                    applied.append(f"Bound executables: {', '.join(executables)}")

                if result.get("errors"):
                    for err in result["errors"]:
                        errors.append(f"{err['setting']}: {err['error']}")

                # Note about app binding
                if not result.get("app_bound", True):
                    app_bound = False
                    note = result.get("app_binding_note", "")
                    state = str(result.get("app_binding_state") or "").strip().lower()

                    if note:
                        applied.append(f"NOTE: {note}")

                    # `bound_elsewhere` is a hard failure: the driver reports the
                    # executable(s) owned by a conflicting profile, so NVAPI
                    # intentionally skipped the setting writes. Only profile
                    # conflict resolution can recover from this.
                    #
                    # Every other unbound state (notably `manual_required`, the
                    # driver-struct-mismatch path) still wrote the settings to
                    # the target profile — only the per-executable association
                    # is missing, and the note already spells out the one-click
                    # NVCP action that finishes it. Treat those as a warning so
                    # the rest of the handlers aren't rolled back over a known
                    # driver limitation with a clear manual remediation.
                    if state == "bound_elsewhere":
                        if note:
                            errors.append(f"App binding failed: {note}")
                    elif note:
                        warnings.append(f"NVIDIA app binding requires manual action: {note}")

                    # If NPI was launched, surface a message that does NOT overstate
                    # the work remaining. The profile settings ARE written to the
                    # target driver profile; only the per-EXE association is missing.
                    # Saying "ACTION REQUIRED" with no qualifier read as "your apply
                    # failed", which is wrong.
                    if result.get("npi_launched"):
                        npi_launched = True
                        applied.append(
                            "NVIDIA settings applied. Final step: NPI opened — "
                            "add the executable(s) to this profile and click "
                            "Apply to finish the per-EXE binding."
                        )
                else:
                    app_bound = True
                    npi_launched = bool(result.get("npi_launched", False))
                    note = result.get("app_binding_note", "")
                    if note:
                        if result.get("app_binding_exact", True) or result.get("app_binding_safe", False):
                            notices.append(str(note))
                        else:
                            warnings.append(str(note))

                logger.info(f"NVIDIA settings applied for {game_name}: {nvidia_settings}")

                # Post-apply verification: read back settings to confirm they took effect
                try:
                    verify_result = manager.get_app_settings(
                        primary_exe,
                        profile_name=effective_profile_name,
                    )
                    verification_failures = self._collect_verification_failures(
                        manager,
                        verify_result,
                        result.get("settings_applied", {}),
                    )
                    if verification_failures:
                        logger.warning("NVIDIA post-apply verification mismatches: %s", verification_failures)
                        for failure in verification_failures:
                            errors.append(f"verification failed: {failure}")
                except Exception as ve:
                    logger.warning(f"NVIDIA post-apply verification skipped: {ve}")
            elif nvidia_settings and not executables:
                logger.warning(
                    f"No executable specified for {game_name}, per-app NVIDIA settings not applied"
                )
                applied.append("No executable specified - per-application NVIDIA settings not applied")

            return {
                "success": len(errors) == 0,
                "error": "; ".join(errors) if errors else None,
                "requires_reboot": False,
                "applied": applied,
                "warnings": warnings,
                "notices": notices,
                "app_bound": app_bound,
                "npi_launched": npi_launched,
                "monitor_adaptive_sync_state": monitor_adaptive_sync_state,
                "global_verification_failures": global_verification_failures if global_verification_failures else None,
                "verification_failures": verification_failures if verification_failures else None,
            }

        except ImportError as e:
            logger.warning(f"NVAPI DRS module not available: {e}")
            applied.append(f"NVIDIA settings for {game_name} (apply manually in NVCP):")
            for key, value in nvidia_settings.items():
                setting_name = key.replace("_", " ").title()
                applied.append(f"  - {setting_name}: {value}")
            if global_settings:
                applied.append("Global settings requested:")
                for key, value in global_settings.items():
                    setting_name = key.replace("_", " ").title()
                    applied.append(f"  - {setting_name}: {value}")
            return {
                "success": False,
                "error": f"NVAPI module unavailable: {e}",
                "requires_reboot": False,
                "applied": applied,
                "warnings": warnings,
                "notices": notices,
                "note": "NVAPI module unavailable - settings NOT applied, manual application required",
            }
        except Exception as e:
            logger.error(f"NVAPI DRS error: {e}")
            applied.append(f"NVIDIA settings for {game_name} (apply manually in NVCP):")
            for key, value in nvidia_settings.items():
                setting_name = key.replace("_", " ").title()
                applied.append(f"  - {setting_name}: {value}")
            if global_settings:
                applied.append("Global settings requested:")
                for key, value in global_settings.items():
                    setting_name = key.replace("_", " ").title()
                    applied.append(f"  - {setting_name}: {value}")
            return {
                "success": False,
                "error": f"NVAPI error: {e}",
                "requires_reboot": False,
                "applied": applied,
                "warnings": warnings,
                "notices": notices,
                "note": f"NVAPI error ({e}) - settings NOT applied, manual application required",
            }

    def _collect_verification_failures(
        self,
        manager: Any,
        verify_result: dict[str, Any],
        requested_settings: dict[str, Any],
    ) -> list[str]:
        """Compare requested DRS writes against numeric driver readback values."""
        failures: list[str] = []

        for setting_name, expected_value in requested_settings.items():
            if str(setting_name).startswith("_"):
                continue

            resolved = manager._resolve_setting(setting_name, expected_value)
            if resolved is None:
                continue

            setting_id, resolved_value = resolved
            actual = self._find_verified_setting_value(manager, verify_result, setting_id)
            if actual is None:
                continue

            if str(actual) != str(resolved_value):
                failures.append(
                    f"{setting_name}: expected={expected_value} ({resolved_value}), actual={actual}"
                )

        return failures

    def _find_verified_setting_value(
        self,
        manager: Any,
        verify_result: dict[str, Any],
        setting_id: int,
    ) -> Any:
        """Find a readback value by canonical DRS setting id, regardless of alias name."""
        setting_ids = getattr(manager, "SETTING_IDS", None)
        if not isinstance(setting_ids, dict):
            setting_ids = VERIFICATION_SETTING_IDS

        for candidate_name, candidate_id in setting_ids.items():
            if candidate_id == setting_id and candidate_name in verify_result:
                return verify_result[candidate_name]
        return None

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify NVIDIA setting readback for a profile.

        This verifies driver setting values on the target profile/global profile.
        Current NVAPI readback does not prove executable-to-profile membership,
        so the returned metadata explicitly marks the scope as profile readback.
        """
        settings = settings.copy()
        executables = list(settings.pop("executables", []))
        game_name = settings.pop("game_name", "Game")
        driver_profile_name = settings.pop("profile_name", None)
        raw_profile_aliases = settings.pop("profile_aliases", [])
        driver_profile_aliases = [
            str(alias) for alias in raw_profile_aliases
            if isinstance(alias, str) and alias.strip()
        ]
        require_exact_binding = bool(settings.pop("require_exact_binding", False))
        allow_unverified_existing_profile_reuse = bool(
            settings.pop("allow_unverified_existing_profile_reuse", False)
        )

        global_settings: dict[str, Any] = {}
        raw_global_settings = settings.pop("global_settings", None)
        if isinstance(raw_global_settings, dict):
            global_settings.update(raw_global_settings)

        for key in ("global_vrr_mode", "global_gsync_mode", "vrr_mode"):
            value = settings.pop(key, None)
            if value is not None:
                global_settings["vrr_mode"] = value

        global_gsync = settings.pop("global_gsync", None)
        if global_gsync is not None:
            if isinstance(global_gsync, bool):
                global_settings["vrr_mode"] = "fullscreen_only" if global_gsync else "off"
            else:
                global_settings["vrr_mode"] = global_gsync

        auto_vrr_fps_cap = bool(settings.pop("auto_vrr_fps_cap", False))
        forced_refresh_hz = settings.pop("vrr_refresh_rate_hz", None)
        if auto_vrr_fps_cap:
            refresh_hz: int | None = None
            if forced_refresh_hz is not None:
                with contextlib.suppress(ValueError, TypeError):
                    refresh_hz = round(float(forced_refresh_hz))
            if refresh_hz is None:
                refresh_hz = self._detect_primary_refresh_rate()

            if refresh_hz and refresh_hz > 0:
                from abso.core.vrr import get_vrr_fps_cap

                settings["max_frame_rate"] = get_vrr_fps_cap(refresh_hz)

        preset_name = settings.get("preset")
        allowed_keys = (
            "low_latency_mode",
            "power_management",
            "vsync",
            "max_frame_rate",
            "shader_cache",
            "threaded_optimization",
            "triple_buffering",
            "vrr_app_override",
            "vsync_tear_control",
            "vsync_vrr_control",
        )
        if preset_name and preset_name in NVIDIA_PRESETS:
            preset = NVIDIA_PRESETS[preset_name]
            nvidia_settings = preset.get("settings", {}).copy()
            for key in allowed_keys:
                if key in settings:
                    nvidia_settings[key] = settings[key]
        else:
            nvidia_settings = {
                key: value for key, value in settings.items()
                if key in allowed_keys
            }

        result: dict[str, Any] = {
            "all_active": True,
            "scope": "profile_readback_only",
            "profile_name": str(driver_profile_name or game_name),
            "global_failures": [],
            "setting_failures": [],
            "notes": [],
        }

        try:
            from abso.settings.nvidia.nvapi_drs import DRSProfileManager

            manager = DRSProfileManager()

            if global_settings:
                global_verify = manager.get_app_settings()
                if global_verify.get("_error"):
                    result["global_failures"].append(str(global_verify["_error"]))
                else:
                    result["global_failures"] = self._collect_verification_failures(
                        manager,
                        global_verify,
                        global_settings,
                    )

            if nvidia_settings:
                if executables:
                    effective_profile_name = str(driver_profile_name or game_name)
                    binding_owner_profiles: dict[str, str] = {}
                    if driver_profile_aliases:
                        try:
                            with manager._drs as drs:
                                selected_profile_name, _, selection_note = manager._select_profile_target(
                                    drs,
                                    effective_profile_name,
                                    driver_profile_aliases,
                                )
                            effective_profile_name = selected_profile_name
                            if selection_note:
                                result["notes"].append(selection_note)
                        except Exception:
                            pass

                    try:
                        with manager._drs as drs:
                            profile_handle = drs.find_profile_by_name(effective_profile_name)
                            for exe in executables:
                                owner_profile_name = manager._get_application_owner_profile_name(
                                    drs,
                                    exe,
                                )
                                if not owner_profile_name and profile_handle and manager._profile_contains_application(
                                    drs,
                                    profile_handle,
                                    exe,
                                ):
                                    owner_profile_name = effective_profile_name

                                if owner_profile_name:
                                    binding_owner_profiles[exe] = owner_profile_name
                    except Exception as binding_error:
                        result["notes"].append(
                            f"Executable binding ownership could not be queried: {binding_error}"
                        )

                    verify_result = manager.get_app_settings(
                        executables[0],
                        profile_name=effective_profile_name,
                    )
                    if verify_result.get("_error"):
                        result["setting_failures"].append(str(verify_result["_error"]))
                    else:
                        result["profile_name"] = effective_profile_name
                        result["readback_profile"] = verify_result.get("_profile")
                        result["setting_failures"] = self._collect_verification_failures(
                            manager,
                            verify_result,
                            nvidia_settings,
                        )
                        if binding_owner_profiles:
                            result["binding_owner_profiles"] = binding_owner_profiles

                        mismatched_bindings = [
                            f"{exe} -> {owner}"
                            for exe, owner in binding_owner_profiles.items()
                            if owner != effective_profile_name
                        ]
                        unresolved_bindings = [
                            exe for exe in executables
                            if exe not in binding_owner_profiles
                        ]

                        if require_exact_binding and (mismatched_bindings or unresolved_bindings):
                            try:
                                probe = manager.probe_profile_binding(
                                    executables,
                                    profile_name=effective_profile_name,
                                    profile_aliases=driver_profile_aliases,
                                )
                                result["binding_probe_state"] = probe.get("app_binding_state")
                                probe_safe = bool(
                                    probe.get(
                                        "app_binding_safe",
                                        probe.get("app_binding_exact", False),
                                    )
                                )
                                if (
                                    not probe_safe
                                    and allow_unverified_existing_profile_reuse
                                    and str(probe.get("app_binding_state") or "")
                                    .strip()
                                    .lower()
                                    in {
                                        "reused_family_profile",
                                        "existing_profile_unverified",
                                    }
                                ):
                                    probe_safe = True

                                probe_note = probe.get("app_binding_note")
                                if probe_note:
                                    result["notes"].append(str(probe_note))

                                if probe_safe:
                                    mismatched_bindings = []
                                    unresolved_bindings = []
                                    binding_owner_profiles = dict.fromkeys(
                                        executables,
                                        effective_profile_name,
                                    )
                                    result["binding_owner_profiles"] = binding_owner_profiles
                                    result["scope"] = "profile_and_safe_binding_probe"
                                else:
                                    result["setting_failures"].append(
                                        str(
                                            probe_note
                                            or "Exact NVIDIA executable binding could not be confirmed."
                                        )
                                    )
                            except Exception as binding_probe_error:
                                result["setting_failures"].append(
                                    "Executable binding ownership could not be proven: "
                                    + str(binding_probe_error)
                                )

                        if mismatched_bindings:
                            result["setting_failures"].append(
                                "Executable binding mismatch: "
                                + ", ".join(sorted(mismatched_bindings))
                            )
                        elif len(binding_owner_profiles) == len(executables):
                            if result["scope"] != "profile_and_safe_binding_probe":
                                result["scope"] = "profile_and_binding_readback"
                                result["notes"].append(
                                    "Executable membership was confirmed on the effective NVIDIA profile."
                                )
                        elif require_exact_binding:
                            result["setting_failures"].append(
                                "Executable binding could not be proven for: "
                                + ", ".join(sorted(unresolved_bindings))
                            )
                        else:
                            result["notes"].append(
                                "Executable membership could not be proven for: "
                                + ", ".join(sorted(unresolved_bindings))
                                + ". Verification covers driver profile settings only."
                            )
                else:
                    result["setting_failures"].append(
                        "Per-application NVIDIA settings could not be verified because no executable was provided."
                    )

        except Exception as e:
            result["all_active"] = False
            result["error"] = str(e)
            return result

        result["all_active"] = not result["global_failures"] and not result["setting_failures"]
        return result

    def backup(self) -> dict[str, Any]:
        """Backup current Nvidia profile settings.

        Nvidia Profile Inspector exports are not safe to restore automatically
        in the current implementation. We only report backup success when the
        handler is not applicable on this machine (for example no NVIDIA GPU is
        present). Otherwise we mark the component as not safely restorable so
        callers can treat the backup as incomplete instead of pretending a
        rollback exists.

        Returns:
            Dictionary containing backup metadata and whether restore is safe.
        """
        gpu_info = self._detect_gpu_info()
        has_nvidia_gpu = bool(gpu_info.get("gpu_name"))

        if not has_nvidia_gpu:
            return {
                "success": True,
                "nvidia_present": False,
                "note": "No NVIDIA GPU detected - nothing to back up",
                "profile_path": None,
            }

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        if not self._npi.is_available():
            return {
                "success": False,
                "nvidia_present": True,
                "profile_path": None,
                "timestamp": timestamp,
                "note": (
                    "NVIDIA backup unavailable: Nvidia Profile Inspector was not found, "
                    "so current driver settings cannot be captured safely."
                ),
            }

        if NPI_IMPORTS_DISABLED:
            logger.warning(
                "NVIDIA backup marked unrestorable because NPI import is disabled for safety"
            )
            return {
                "success": False,
                "nvidia_present": True,
                "profile_path": None,
                "timestamp": timestamp,
                "note": (
                    "NVIDIA backup cannot be restored safely because Profile Inspector import "
                    "is disabled to avoid wiping the user's driver profile database."
                ),
            }

        return {
            "success": False,
            "nvidia_present": True,
            "profile_path": None,
            "timestamp": timestamp,
            "note": "NVIDIA backup is unavailable in the current configuration",
        }

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Nvidia profile from backup.

        Args:
            data: Backup data containing 'profile_path' to a .nip file.

        Returns:
            True if restore succeeded, False otherwise.
        """
        if data.get("nvidia_present") is False:
            logger.info("Skipping NVIDIA restore: no NVIDIA GPU was present when the backup was created")
            return True

        profile_path = data.get("profile_path")

        if not profile_path:
            logger.error(
                "NVIDIA restore unavailable: the backup did not contain a restorable profile artifact"
            )
            return False

        if not Path(profile_path).exists():
            logger.error(f"Backup profile not found: {profile_path}")
            return False

        if NPI_IMPORTS_DISABLED:
            logger.error(
                "NVIDIA restore unavailable: Profile Inspector import is disabled for safety"
            )
            return False

        try:
            self._import_profile(Path(profile_path))
            return True
        except Exception as e:
            logger.error(f"Failed to restore NVIDIA profile from backup: {e}")
            return False

    def _check_npi_available(self) -> bool:
        """Check if NPI is available (backwards compatibility)."""
        return self._npi.is_available()

    def _cleanup_stale_profiles(
        self,
        manager: Any,
        target_profile_name: str,
        game_name: str,
    ) -> None:
        """Delete stale ABSO-created NVIDIA profiles with 0 bound applications.

        Previous ABSO versions may have created profiles like
        "Overwatch 2 - GSYNC" that are no longer used. These can contain
        stale settings (e.g., FRL=0) that interfere if the driver falls
        back to them.

        Uses ``target_profile_name`` (the DRS profile name being actively
        written, e.g. "Overwatch 2") as the base for pattern matching so
        variant suffixes like "Overwatch 2 - GSYNC" are correctly caught.

        Args:
            manager: DRSProfileManager instance.
            target_profile_name: The DRS profile name we're about to create/update.
            game_name: Display name of the game (may include variant suffix).
        """
        try:
            all_profiles = manager.list_profiles(include_predefined=False)
            stale_names: list[str] = []

            # Use the DRS profile name as base (e.g. "Overwatch 2"), not the
            # display name which may already contain a variant suffix.
            base_lower = target_profile_name.lower()

            for profile in all_profiles:
                name = profile.get("name", "")
                num_apps = profile.get("num_apps", 0)

                # Skip the profile we're about to use
                if name == target_profile_name:
                    continue

                # Skip profiles that have apps bound (actively in use)
                if num_apps > 0:
                    continue

                # Match patterns: "ABSO - <anything>", "<base> - <variant>"
                name_lower = name.lower()
                if (
                    name_lower.startswith("abso -")
                    or name_lower.startswith(f"{base_lower} -")
                    or name_lower.startswith(f"{base_lower} –")  # en-dash variant
                ):
                    stale_names.append(name)

            if stale_names:
                logger.info(f"Cleaning up {len(stale_names)} stale NVIDIA profile(s): {stale_names}")
                cleanup_result = manager.delete_profiles_by_name(stale_names)
                for deleted in cleanup_result.get("deleted", []):
                    logger.info(f"Deleted stale NVIDIA profile: {deleted}")
                for err in cleanup_result.get("errors", []):
                    logger.warning(f"Failed to delete stale profile: {err}")
        except Exception as e:
            logger.debug(f"Stale NVIDIA profile cleanup failed (non-fatal): {e}")

    def _detect_gpu_info(self) -> dict[str, Any]:
        """Detect GPU information via nvidia-smi."""
        result: dict[str, Any] = {
            "driver_version": None,
            "gpu_name": None,
            "vram_total_mb": None,
        }

        try:
            smi_result = subprocess.run(
                ["nvidia-smi", "--query-gpu=name,driver_version,memory.total", "--format=csv,noheader,nounits"],
                capture_output=True,
                text=True,
                timeout=5,
            )
            if smi_result.returncode == 0 and smi_result.stdout.strip():
                parts = [p.strip() for p in smi_result.stdout.strip().split(",")]
                result["gpu_name"] = parts[0] if len(parts) > 0 else None
                result["driver_version"] = parts[1] if len(parts) > 1 else None
                if len(parts) > 2:
                    with contextlib.suppress(ValueError):
                        result["vram_total_mb"] = int(float(parts[2]))
        except FileNotFoundError:
            logger.debug("nvidia-smi not found - Nvidia GPU may not be present")
        except subprocess.TimeoutExpired:
            logger.debug("nvidia-smi timed out")
        except Exception as e:
            logger.debug(f"nvidia-smi detection failed: {e}")

        return result

    def _detect_primary_refresh_rate(self) -> int | None:
        """Detect refresh rate for the target gaming display.

        Returns:
            Refresh rate in Hz, or None when unavailable.
        """
        try:
            from abso.core.detector import HardwareDetector

            monitors = HardwareDetector().detect_monitors()
            if not monitors:
                raise RuntimeError("No monitors returned from HardwareDetector")

            primary = self._select_target_gaming_monitor(monitors)
            # Prefer active mode refresh first. For VRR frame caps, using a
            # higher "max capability" from a different mode/resolution can
            # overcap and push rendering above the real active scan rate.
            prioritized_candidates = [
                ("refresh_rate", primary.get("refresh_rate")),
                ("max_refresh_rate", primary.get("max_refresh_rate")),
                ("max_refresh_capability", primary.get("max_refresh_capability")),
            ]

            for label, value in prioritized_candidates:
                with contextlib.suppress(ValueError, TypeError):
                    if value is not None:
                        detected = round(float(value))
                        if detected > 0:
                            logger.info(
                                f"Target display refresh detected via HardwareDetector ({label}): {detected} Hz"
                            )
                            return detected
        except Exception as e:
            logger.warning(f"Target display refresh detection failed: {e}")

        # Fallback path: Windows handler uses ctypes and does not depend on pywin32.
        try:
            from abso.settings.windows import WindowsSettingsHandler

            refresh_info = WindowsSettingsHandler()._get_refresh_rate_info()
            candidates = [refresh_info.get("max"), refresh_info.get("current")]
            numeric: list[int] = []
            for value in candidates:
                with contextlib.suppress(ValueError, TypeError):
                    if value is not None:
                        numeric.append(round(float(value)))

            if numeric:
                detected = max(numeric)
                logger.info(
                    f"Target display refresh detected via WindowsSettingsHandler fallback: {detected} Hz"
                )
                return detected
        except Exception as e:
            logger.warning(f"Target display refresh fallback detection failed: {e}")
            return None

        return None

    def _select_target_gaming_monitor(self, monitors: list[dict[str, Any]]) -> dict[str, Any]:
        """Pick the display ABSO should treat as the gaming display."""
        if not monitors:
            raise RuntimeError("No monitors available for target selection")

        def vrr_score(monitor: dict[str, Any]) -> int:
            status = monitor.get("vrr_supported")
            if status is True:
                return 4
            if status == "hardware":
                return 3
            if status == "likely":
                return 2
            if status == "possible":
                return 1
            return 0

        def refresh_score(monitor: dict[str, Any]) -> float:
            for key in ("refresh_rate", "max_refresh_rate", "max_refresh_capability"):
                value = monitor.get(key)
                try:
                    if value is not None:
                        parsed = float(value)
                        if parsed > 0:
                            return parsed
                except (TypeError, ValueError):
                    continue
            return 0.0

        return max(
            monitors,
            key=lambda monitor: (
                refresh_score(monitor),
                vrr_score(monitor),
                1 if monitor.get("is_primary") else 0,
            ),
        )

    # Keep these methods for backwards compatibility with tests
    def _get_setting_value(self, value: str, setting_type: str) -> int:
        """Convert setting string to decimal value (backwards compatibility)."""
        from .profiles import get_setting_value
        return get_setting_value(value, setting_type)

    def _import_profile(self, profile_path: Path) -> None:
        """Import profile (backwards compatibility)."""
        self._npi.import_profile(profile_path)

    def _export_profile(self, output_path: Path) -> None:
        """Export profile (backwards compatibility)."""
        self._npi.export_profile(output_path)
