"""AMD GPU detection and settings handler.

Manages AMD Radeon driver-level and Radeon Software settings for gaming
optimization. Reads/writes registry keys under the AMD display driver class
and HKCU AMD Software paths.
"""

from __future__ import annotations

import logging
import winreg
from typing import Any

from abso.core.models import EvidenceTier, Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# AMD display driver registry path (device instance 0000)
_AMD_DRIVER_KEY = (
    r"SYSTEM\CurrentControlSet\Control\Class"
    r"\{4d36e968-e325-11ce-bfc1-08002be10318}\0000"
)

# Radeon Software user-level registry paths
_AMD_DVR_KEY = r"Software\AMD\DVR"
_AMD_CN_KEY = r"Software\AMD\CN"


def _read_reg_dword(
    hive: int,
    subkey: str,
    value_name: str,
) -> int | None:
    """Read a REG_DWORD from the registry.

    Returns:
        The integer value, or None if the key/value does not exist or
        cannot be read.
    """
    try:
        key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
        try:
            val, regtype = winreg.QueryValueEx(key, value_name)
            if regtype == winreg.REG_DWORD:
                return val
            return val
        except FileNotFoundError:
            return None
        finally:
            winreg.CloseKey(key)
    except (PermissionError, FileNotFoundError, OSError) as exc:
        logger.debug("Failed to read %s\\%s: %s", subkey, value_name, exc)
        return None


def _write_reg_dword(
    hive: int,
    subkey: str,
    value_name: str,
    value: int,
) -> None:
    """Write a REG_DWORD to the registry.

    Raises:
        PermissionError: If the caller lacks write access.
        OSError: If the key cannot be opened/created or the write fails.
    """
    # CreateKeyEx opens the key or creates it when missing. Radeon Software
    # keys (HKCU\Software\AMD\CN, DVR) frequently do not exist until Radeon
    # Software writes them, so a plain OpenKey would raise FileNotFoundError
    # and the tweak could never be applied on a fresh install.
    key = winreg.CreateKeyEx(hive, subkey, 0, winreg.KEY_ALL_ACCESS)
    try:
        winreg.SetValueEx(key, value_name, 0, winreg.REG_DWORD, value)
    finally:
        winreg.CloseKey(key)


class AmdSettingsHandler(SettingsHandler):
    """Handles AMD Radeon GPU driver and software settings.

    Manages:
    - ULPS (Ultra Low Power State) — causes micro-stutters on multi-monitor
    - Large page support (KMD_EnableInternalLargePage)
    - Thermal auto-throttling
    - Anti-Lag (Radeon Software)
    - Radeon Chill min/max FPS
    - Radeon Boost
    - Enhanced Sync
    """

    # --- AMD GPU presence detection -------------------------------------------

    _amd_present_cached: bool | None = None

    @classmethod
    def is_amd_gpu_present(cls) -> bool:
        """Detect whether an AMD/Radeon GPU is installed.

        The result is cached after the first call so subsequent checks are
        free.

        Returns:
            True if at least one AMD GPU was found via WMI.
        """
        if cls._amd_present_cached is not None:
            return cls._amd_present_cached

        cls._amd_present_cached = cls._detect_amd_gpu()
        return cls._amd_present_cached

    @staticmethod
    def _detect_amd_gpu() -> bool:
        """Query WMI Win32_VideoController for AMD/Radeon GPUs."""
        try:
            import wmi  # type: ignore[import-untyped]

            conn = wmi.WMI()
            for gpu in conn.Win32_VideoController():
                name: str = gpu.Name or ""
                if "AMD" in name or "Radeon" in name:
                    logger.info("AMD GPU detected: %s", name)
                    return True
        except ImportError:
            logger.debug("wmi package not available; falling back to registry check")
            # Fallback: probe the AMD driver registry key directly
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE, _AMD_DRIVER_KEY, 0, winreg.KEY_READ
                )
                try:
                    provider, _ = winreg.QueryValueEx(key, "ProviderName")
                    if provider and "AMD" in str(provider).upper():
                        return True
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(key)
            except (PermissionError, FileNotFoundError, OSError):
                pass
        except Exception as exc:
            logger.debug("WMI GPU detection failed: %s", exc)

        return False

    # --- SettingsHandler interface --------------------------------------------

    def detect(self) -> dict[str, Any]:
        """Detect AMD GPU presence and current driver/software settings.

        Returns:
            Dictionary containing ``is_amd_present`` and, when True, all
            readable driver-level and Radeon Software settings.
        """
        if not self.is_amd_gpu_present():
            return {"is_amd_present": False}

        driver_settings = self._detect_driver_settings()
        software_settings = self._detect_software_settings()

        return {
            "is_amd_present": True,
            **driver_settings,
            **software_settings,
        }

    def audit(self) -> list[Issue]:
        """Audit AMD settings for gaming optimization issues.

        Returns:
            List of issues found. Empty list if no AMD GPU is present.
        """
        if not self.is_amd_gpu_present():
            return []

        issues: list[Issue] = []
        current = self.detect()

        # ULPS enabled — known to cause micro-stutters on multi-monitor setups
        ulps = current.get("enable_ulps")
        if ulps is not None and ulps != 0:
            issues.append(Issue(
                title="AMD ULPS (Ultra Low Power State) is enabled",
                severity="warning",
                current_value=str(ulps),
                optimal_value="0 (disabled)",
                explanation=(
                    "ULPS aggressively power-gates idle GPUs and is a documented "
                    "source of micro-stutters, black screens, and clock recovery "
                    "delays on multi-monitor AMD setups. Disabling it keeps the "
                    "GPU in a ready state at the cost of slightly higher idle power."
                ),
                category="amd",
                evidence_tier=EvidenceTier.VERIFIED,
            ))

        # Enhanced Sync enabled — adds latency compared to no sync
        enhanced_sync = current.get("enhanced_sync")
        if enhanced_sync is not None and enhanced_sync != 0:
            issues.append(Issue(
                title="AMD Enhanced Sync is enabled",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation=(
                    "Enhanced Sync adds a frame queue that reduces tearing but "
                    "increases input latency compared to running uncapped with "
                    "no sync. Disable for competitive/latency-sensitive games."
                ),
                category="amd",
                evidence_tier=EvidenceTier.VERIFIED,
            ))

        # Anti-Lag not enabled — inform the user it exists
        anti_lag = current.get("anti_lag")
        if anti_lag is not None and anti_lag == 0:
            issues.append(Issue(
                title="AMD Anti-Lag is not enabled",
                severity="info",
                current_value="Disabled",
                optimal_value="Enabled (per-game)",
                explanation=(
                    "AMD Anti-Lag reduces input-to-display latency by aligning "
                    "CPU work closer to GPU consumption. Enable per-game in "
                    "Radeon Software for supported titles."
                ),
                category="amd",
                evidence_tier=EvidenceTier.VERIFIED,
            ))

        # Radeon Chill enabled — harmful for competitive profiles
        chill_enabled = current.get("radeon_chill_enabled")
        if chill_enabled is not None and chill_enabled != 0:
            issues.append(Issue(
                title="Radeon Chill is enabled",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation=(
                    "Radeon Chill dynamically caps frame rate based on user "
                    "activity, which adds variable latency. Disable for "
                    "competitive or latency-sensitive games."
                ),
                category="amd",
                evidence_tier=EvidenceTier.VERIFIED,
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply AMD-specific settings.

        Supported keys:
        - ``disable_ulps`` (bool): Disable Ultra Low Power State.
        - ``anti_lag`` (bool): Enable/disable Anti-Lag.
        - ``enhanced_sync`` (bool): Enable/disable Enhanced Sync.
        - ``radeon_chill`` (bool): Enable/disable Radeon Chill.
        - ``large_page`` (bool): Enable/disable large page support.
        - ``thermal_throttling`` (bool): Enable/disable thermal auto-throttle.
        - ``radeon_boost`` (bool): Enable/disable Radeon Boost.

        Args:
            settings: Dictionary of AMD settings to apply.

        Returns:
            Result dict with ``success``, optional ``error``, ``applied``,
            and ``requires_reboot`` keys.
        """
        if not self.is_amd_gpu_present():
            logger.info("No AMD GPU detected — skipping AMD settings apply")
            return {
                "success": True,
                "error": None,
                "applied": [],
                "note": "No AMD GPU detected; no settings applied.",
                "requires_reboot": False,
            }

        errors: list[str] = []
        applied: list[str] = []

        # Driver-level settings (HKLM)
        if "disable_ulps" in settings:
            self._apply_driver_setting(
                "EnableUlps",
                0 if settings["disable_ulps"] else 1,
                "ULPS",
                applied,
                errors,
            )

        if "large_page" in settings:
            self._apply_driver_setting(
                "KMD_EnableInternalLargePage",
                1 if settings["large_page"] else 0,
                "LargePage",
                applied,
                errors,
            )

        if "thermal_throttling" in settings:
            self._apply_driver_setting(
                "PP_ThermalAutoThrottlingEnable",
                1 if settings["thermal_throttling"] else 0,
                "ThermalThrottling",
                applied,
                errors,
            )

        # Radeon Software settings (HKCU)
        if "anti_lag" in settings:
            self._apply_software_setting(
                _AMD_CN_KEY,
                "AntiLag",
                1 if settings["anti_lag"] else 0,
                "AntiLag",
                applied,
                errors,
            )

        if "enhanced_sync" in settings:
            self._apply_software_setting(
                _AMD_CN_KEY,
                "EnhancedSync",
                1 if settings["enhanced_sync"] else 0,
                "EnhancedSync",
                applied,
                errors,
            )

        if "radeon_chill" in settings:
            self._apply_software_setting(
                _AMD_CN_KEY,
                "ChillEnabled",
                1 if settings["radeon_chill"] else 0,
                "RadeonChill",
                applied,
                errors,
            )

        if "radeon_boost" in settings:
            self._apply_software_setting(
                _AMD_CN_KEY,
                "BoostEnabled",
                1 if settings["radeon_boost"] else 0,
                "RadeonBoost",
                applied,
                errors,
            )

        # Log summary
        if applied:
            logger.info(
                "AMD: Applied %d settings: %s", len(applied), ", ".join(applied)
            )
        if errors:
            logger.warning("AMD: %d errors: %s", len(errors), "; ".join(errors))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "applied": applied,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Export current AMD settings for backup.

        Returns:
            Dictionary of all detectable AMD settings, suitable for passing
            back to :meth:`restore`.
        """
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore AMD settings from backup data.

        Args:
            data: Previously backed-up settings from :meth:`backup`.

        Returns:
            True if all restorable settings were written successfully.
        """
        if not self.is_amd_gpu_present():
            logger.info("No AMD GPU detected — skipping AMD settings restore")
            return True

        success = True

        # Driver-level settings (HKLM)
        driver_restore_map: dict[str, str] = {
            "enable_ulps": "EnableUlps",
            "large_page": "KMD_EnableInternalLargePage",
            "thermal_throttling": "PP_ThermalAutoThrottlingEnable",
        }
        for data_key, reg_name in driver_restore_map.items():
            if data_key in data:
                try:
                    _write_reg_dword(
                        winreg.HKEY_LOCAL_MACHINE,
                        _AMD_DRIVER_KEY,
                        reg_name,
                        data[data_key],
                    )
                except (PermissionError, OSError) as exc:
                    logger.error("Failed to restore AMD driver %s: %s", reg_name, exc)
                    success = False

        # Software settings (HKCU)
        software_restore_map: dict[str, tuple[str, str]] = {
            "anti_lag": (_AMD_CN_KEY, "AntiLag"),
            "enhanced_sync": (_AMD_CN_KEY, "EnhancedSync"),
            "radeon_chill_enabled": (_AMD_CN_KEY, "ChillEnabled"),
            "radeon_chill_min_fps": (_AMD_CN_KEY, "ChillMinFPS"),
            "radeon_chill_max_fps": (_AMD_CN_KEY, "ChillMaxFPS"),
            "radeon_boost": (_AMD_CN_KEY, "BoostEnabled"),
        }
        for data_key, (subkey, reg_name) in software_restore_map.items():
            if data_key in data and data[data_key] is not None:
                try:
                    _write_reg_dword(
                        winreg.HKEY_CURRENT_USER,
                        subkey,
                        reg_name,
                        data[data_key],
                    )
                except (PermissionError, OSError) as exc:
                    logger.error(
                        "Failed to restore AMD software %s: %s", reg_name, exc
                    )
                    success = False

        return success

    # --- Private helpers ------------------------------------------------------

    def _detect_driver_settings(self) -> dict[str, Any]:
        """Read AMD driver-level registry values from HKLM."""
        return {
            "large_page": _read_reg_dword(
                winreg.HKEY_LOCAL_MACHINE,
                _AMD_DRIVER_KEY,
                "KMD_EnableInternalLargePage",
            ),
            "enable_ulps": _read_reg_dword(
                winreg.HKEY_LOCAL_MACHINE,
                _AMD_DRIVER_KEY,
                "EnableUlps",
            ),
            "thermal_throttling": _read_reg_dword(
                winreg.HKEY_LOCAL_MACHINE,
                _AMD_DRIVER_KEY,
                "PP_ThermalAutoThrottlingEnable",
            ),
        }

    def _detect_software_settings(self) -> dict[str, Any]:
        """Read Radeon Software settings from HKCU."""
        return {
            "anti_lag": _read_reg_dword(
                winreg.HKEY_CURRENT_USER,
                _AMD_CN_KEY,
                "AntiLag",
            ),
            "radeon_chill_enabled": _read_reg_dword(
                winreg.HKEY_CURRENT_USER,
                _AMD_CN_KEY,
                "ChillEnabled",
            ),
            "radeon_chill_min_fps": _read_reg_dword(
                winreg.HKEY_CURRENT_USER,
                _AMD_CN_KEY,
                "ChillMinFPS",
            ),
            "radeon_chill_max_fps": _read_reg_dword(
                winreg.HKEY_CURRENT_USER,
                _AMD_CN_KEY,
                "ChillMaxFPS",
            ),
            "radeon_boost": _read_reg_dword(
                winreg.HKEY_CURRENT_USER,
                _AMD_CN_KEY,
                "BoostEnabled",
            ),
            "enhanced_sync": _read_reg_dword(
                winreg.HKEY_CURRENT_USER,
                _AMD_CN_KEY,
                "EnhancedSync",
            ),
        }

    def _apply_driver_setting(
        self,
        reg_name: str,
        value: int,
        label: str,
        applied: list[str],
        errors: list[str],
    ) -> None:
        """Write a single AMD driver registry DWORD."""
        try:
            _write_reg_dword(
                winreg.HKEY_LOCAL_MACHINE, _AMD_DRIVER_KEY, reg_name, value
            )
            applied.append(label)
            logger.info("Set AMD driver %s = %d", reg_name, value)
        except PermissionError as exc:
            msg = f"{label}: Permission denied; run as administrator ({exc})"
            errors.append(msg)
            logger.error("Failed to set AMD driver %s: %s", reg_name, exc)
        except OSError as exc:
            msg = f"{label}: {exc}"
            errors.append(msg)
            logger.error("Failed to set AMD driver %s: %s", reg_name, exc)

    def _apply_software_setting(
        self,
        subkey: str,
        reg_name: str,
        value: int,
        label: str,
        applied: list[str],
        errors: list[str],
    ) -> None:
        """Write a single Radeon Software registry DWORD."""
        try:
            _write_reg_dword(
                winreg.HKEY_CURRENT_USER, subkey, reg_name, value
            )
            applied.append(label)
            logger.info("Set AMD software %s = %d", reg_name, value)
        except PermissionError as exc:
            msg = f"{label}: Permission denied ({exc})"
            errors.append(msg)
            logger.error("Failed to set AMD software %s: %s", reg_name, exc)
        except OSError as exc:
            msg = f"{label}: {exc}"
            errors.append(msg)
            logger.error("Failed to set AMD software %s: %s", reg_name, exc)
