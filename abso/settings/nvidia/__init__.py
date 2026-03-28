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

from .npi import NPIManager, NPI_IMPORTS_DISABLED
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


class NvidiaSettingsHandler(SettingsHandler):
    """Handles Nvidia GPU settings via Profile Inspector.

    Manages:
    - 3D settings (Low Latency Mode, Power Management, etc.)
    - Per-application profiles
    - Global profile settings

    Note: Full functionality requires Nvidia Profile Inspector (NPI).
    Download from: https://github.com/Orbmu2k/nvidiaProfileInspector
    """

    # Backup directory for exported profiles
    BACKUP_DIR: Path = Path(tempfile.gettempdir()) / "abso_nvidia_backups"

    def __init__(self, npi_path: Path | str | None = None) -> None:
        """Initialize Nvidia settings handler.

        Args:
            npi_path: Path to nvidiaProfileInspector.exe.
        """
        self._npi = NPIManager(npi_path)

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
                optimal_value="Installed and configured",
                explanation=(
                    "NPI is required for full Nvidia 3D settings management. "
                    "Download from: https://github.com/Orbmu2k/nvidiaProfileInspector"
                ),
                category="nvidia",
            ))
            return issues

        # Note: We cannot read current Nvidia 3D settings without triggering NPI GUI
        # (NPI doesn't support headless export). Skip detailed settings audit.
        # Users should apply a profile to ensure optimal settings.
        return issues

        # DISABLED: The code below requires NPI export which opens GUI
        # Check current settings against optimal for gaming
        current_settings = {}

        # Check Power Management Mode
        power_mode = current_settings.get("power_management")
        if power_mode and power_mode != "prefer_max_performance":
            issues.append(Issue(
                title="Power Management not set to maximum performance",
                severity="warning",
                current_value=power_mode,
                optimal_value="Prefer Maximum Performance",
                explanation=(
                    "Setting power management to 'Prefer Maximum Performance' ensures "
                    "the GPU runs at full speed during gaming, reducing frame time variance."
                ),
                category="nvidia",
            ))

        # Check Low Latency Mode
        low_latency = current_settings.get("low_latency_mode")
        if low_latency == "off":
            issues.append(Issue(
                title="Low Latency Mode is disabled",
                severity="warning",
                current_value="Off",
                optimal_value="On or Ultra",
                explanation=(
                    "Low Latency Mode reduces render queue depth, decreasing input lag. "
                    "'On' is safer; 'Ultra' provides minimum latency but may reduce FPS on CPU-limited scenarios."
                ),
                category="nvidia",
            ))

        # Check VSync setting
        # NOTE: With G-SYNC enabled, NVCP V-SYNC "On" acts as a SAFETY NET only.
        # It doesn't add latency when FPS is properly capped below refresh rate.
        # See: Blur Busters G-SYNC 101 - https://blurbusters.com/gsync/gsync101-input-lag-tests-and-settings/
        vsync = current_settings.get("vsync")
        if vsync == "off":
            issues.append(Issue(
                title="VSync is disabled (potential tearing with VRR)",
                severity="info",
                current_value="Off",
                optimal_value="On (as VRR safety net)",
                explanation=(
                    "With G-SYNC/FreeSync enabled, NVCP V-SYNC 'On' acts as a safety net - "
                    "it only activates if FPS exceeds refresh rate, preventing tearing. "
                    "With a proper FPS cap (refresh - 3), V-SYNC never engages and adds zero latency. "
                    "Keep V-SYNC Off only if you accept occasional tearing or don't use VRR."
                ),
                category="nvidia",
            ))
        elif vsync == "on":
            # V-SYNC On is correct for VRR - just inform about FPS cap requirement
            issues.append(Issue(
                title="VSync enabled - ensure FPS is capped for VRR",
                severity="info",
                current_value="On",
                optimal_value="On (with FPS cap at refresh - 3)",
                explanation=(
                    "V-SYNC 'On' with G-SYNC is correct. To avoid latency, cap FPS at "
                    "your refresh rate minus 3 (e.g., 141 for 144Hz). This keeps V-SYNC "
                    "as a safety net that never activates. Use in-game limiter or RTSS."
                ),
                category="nvidia",
            ))

        # Check Shader Cache
        shader_cache = current_settings.get("shader_cache")
        if shader_cache and shader_cache != "unlimited":
            issues.append(Issue(
                title="Shader Cache not set to Unlimited",
                severity="info",
                current_value=shader_cache,
                optimal_value="Unlimited",
                explanation=(
                    "Unlimited shader cache prevents stutter from shader recompilation. "
                    "Requires adequate disk space."
                ),
                category="nvidia",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply NVIDIA settings using direct NVAPI DRS integration.

        This uses NVAPI's DRS (Driver Settings) API directly, allowing safe
        per-game profile modification without wiping the entire profile database.

        Args:
            settings: Dictionary of settings to apply.
        """
        settings = settings.copy()
        applied: list[str] = []
        errors: list[str] = []

        # Extract game info
        executables = settings.pop("executables", [])
        game_name = settings.pop("game_name", "Game")
        driver_profile_name = settings.pop("profile_name", None)
        global_settings: dict[str, Any] = {}

        # Optional explicit global/base-profile settings
        raw_global_settings = settings.pop("global_settings", None)
        if isinstance(raw_global_settings, dict):
            global_settings.update(raw_global_settings)

        # Convenience aliases for global G-SYNC mode control
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

        # Optional auto-cap for VRR profiles (refresh - 3)
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

                auto_cap = get_vrr_fps_cap(refresh_hz)
                settings["max_frame_rate"] = auto_cap
                applied.append(f"Auto VRR FPS cap: {auto_cap} (from {refresh_hz} Hz)")
                logger.info(
                    f"Auto VRR FPS cap enabled for {game_name}: refresh={refresh_hz}Hz cap={auto_cap}"
                )
            else:
                applied.append(
                    "NOTE: Auto VRR FPS cap requested but refresh rate could not be detected"
                )
                logger.warning(
                    f"Auto VRR FPS cap requested for {game_name}, but refresh detection failed"
                )

        # Determine what settings to apply
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
            # Allow per-profile overrides on top of presets (e.g., auto frame cap).
            for key in allowed_keys:
                if key in settings:
                    nvidia_settings[key] = settings[key]
        else:
            nvidia_settings = {
                k: v for k, v in settings.items()
                if k in allowed_keys
            }

        if not nvidia_settings and not global_settings:
            return {
                "success": True,
                "error": None,
                "requires_reboot": False,
                "applied": ["No NVIDIA settings to apply"],
            }

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

            # Safety net: always clear global FRL to prevent it from capping games
            if "max_frame_rate" not in global_settings:
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
                profile_name = str(driver_profile_name or game_name)
                primary_exe = executables[0]

                if len(executables) == 1:
                    result = manager.apply_settings_to_app(
                        primary_exe,
                        nvidia_settings,
                        profile_name=profile_name,
                    )
                else:
                    result = manager.apply_settings_to_profile(
                        executables,
                        nvidia_settings,
                        profile_name=profile_name,
                    )

                # Report results
                if result.get("settings_applied"):
                    for setting, value in result["settings_applied"].items():
                        applied.append(f"{setting}: {value}")
                    applied.insert(0, f"NVIDIA profile '{profile_name}' configured:")

                if len(executables) > 1:
                    applied.append(f"Bound executables: {', '.join(executables)}")

                if result.get("errors"):
                    for err in result["errors"]:
                        errors.append(f"{err['setting']}: {err['error']}")

                # Note about app binding
                if not result.get("app_bound", True):
                    app_bound = False
                    note = result.get("app_binding_note", "")
                    if note:
                        applied.append(f"NOTE: {note}")
                        errors.append(f"App binding failed: {note}")

                    # If NPI was launched, add a clear message
                    if result.get("npi_launched"):
                        npi_launched = True
                        applied.append("ACTION REQUIRED: NPI opened - add the app(s) to the profile and click Apply")
                else:
                    app_bound = True
                    npi_launched = bool(result.get("npi_launched", False))

                logger.info(f"NVIDIA settings applied for {game_name}: {nvidia_settings}")

                # Post-apply verification: read back settings to confirm they took effect
                try:
                    verify_result = manager.get_app_settings(
                        primary_exe,
                        profile_name=profile_name,
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
                "app_bound": app_bound,
                "npi_launched": npi_launched,
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
        for candidate_name, candidate_id in getattr(manager, "SETTING_IDS", {}).items():
            if candidate_id == setting_id and candidate_name in verify_result:
                return verify_result[candidate_name]
        return None

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
        """Detect current/maximum refresh rate for the primary display.

        Returns:
            Refresh rate in Hz, or None when unavailable.
        """
        try:
            from abso.core.detector import HardwareDetector

            monitors = HardwareDetector().detect_monitors()
            if not monitors:
                raise RuntimeError("No monitors returned from HardwareDetector")

            primary = next((m for m in monitors if m.get("is_primary")), monitors[0])
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
                                f"Primary refresh detected via HardwareDetector ({label}): {detected} Hz"
                            )
                            return detected
        except Exception as e:
            logger.warning(f"Primary refresh rate detection failed: {e}")

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
                    f"Primary refresh detected via WindowsSettingsHandler fallback: {detected} Hz"
                )
                return detected
        except Exception as e:
            logger.warning(f"Primary refresh rate fallback detection failed: {e}")
            return None

        return None

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
