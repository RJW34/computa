"""Windows gaming settings handler."""

from __future__ import annotations

import ctypes
import logging
import winreg
from ctypes import wintypes
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)

# Windows display mode constants
DM_PELSWIDTH = 0x00080000
DM_PELSHEIGHT = 0x00100000
DM_DISPLAYFREQUENCY = 0x00400000
ENUM_CURRENT_SETTINGS = -1
DISP_CHANGE_SUCCESSFUL = 0
CDS_UPDATEREGISTRY = 0x00000001
CDS_TEST = 0x00000002

# CCD API constants for HDR control
QDC_ONLY_ACTIVE_PATHS = 0x00000002
DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO = 9
DISPLAYCONFIG_DEVICE_INFO_SET_ADVANCED_COLOR_STATE = 10


class _LUID(ctypes.Structure):
    _fields_ = [("LowPart", wintypes.DWORD), ("HighPart", wintypes.LONG)]


class DISPLAYCONFIG_DEVICE_INFO_HEADER(ctypes.Structure):
    _fields_ = [
        ("type", wintypes.UINT),
        ("size", wintypes.UINT),
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
    ]


class DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO(ctypes.Structure):
    """Query structure for advanced color (HDR) info per display target.

    The 'value' field is a bitfield:
      bit 0: advancedColorSupported
      bit 1: advancedColorEnabled
      bit 2: wideColorEnforced
      bit 3: advancedColorForceDisabled
    """
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", wintypes.UINT),
        ("colorEncoding", wintypes.UINT),
        ("bitsPerColorChannel", wintypes.UINT),
    ]


class DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE(ctypes.Structure):
    """Set structure for toggling advanced color (HDR) per display target.

    The 'value' field is a bitfield:
      bit 0: enableAdvancedColor (1=on, 0=off)
    """
    _fields_ = [
        ("header", DISPLAYCONFIG_DEVICE_INFO_HEADER),
        ("value", wintypes.UINT),
    ]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    _fields_ = [("Numerator", wintypes.UINT), ("Denominator", wintypes.UINT)]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    _fields_ = [
        ("adapterId", _LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("outputTechnology", wintypes.UINT),
        ("rotation", wintypes.UINT),
        ("scaling", wintypes.UINT),
        ("refreshRate", DISPLAYCONFIG_RATIONAL),
        ("scanLineOrdering", wintypes.UINT),
        ("targetAvailable", wintypes.BOOL),
        ("statusFlags", wintypes.UINT),
    ]


class DISPLAYCONFIG_PATH_INFO(ctypes.Structure):
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", wintypes.UINT),
    ]


class DEVMODE(ctypes.Structure):
    """Windows DEVMODE structure for display settings."""
    _fields_ = [
        ("dmDeviceName", ctypes.c_wchar * 32),
        ("dmSpecVersion", ctypes.c_ushort),
        ("dmDriverVersion", ctypes.c_ushort),
        ("dmSize", ctypes.c_ushort),
        ("dmDriverExtra", ctypes.c_ushort),
        ("dmFields", ctypes.c_ulong),
        ("dmPositionX", ctypes.c_long),
        ("dmPositionY", ctypes.c_long),
        ("dmDisplayOrientation", ctypes.c_ulong),
        ("dmDisplayFixedOutput", ctypes.c_ulong),
        ("dmColor", ctypes.c_short),
        ("dmDuplex", ctypes.c_short),
        ("dmYResolution", ctypes.c_short),
        ("dmTTOption", ctypes.c_short),
        ("dmCollate", ctypes.c_short),
        ("dmFormName", ctypes.c_wchar * 32),
        ("dmLogPixels", ctypes.c_ushort),
        ("dmBitsPerPel", ctypes.c_ulong),
        ("dmPelsWidth", ctypes.c_ulong),
        ("dmPelsHeight", ctypes.c_ulong),
        ("dmDisplayFlags", ctypes.c_ulong),
        ("dmDisplayFrequency", ctypes.c_ulong),
        ("dmICMMethod", ctypes.c_ulong),
        ("dmICMIntent", ctypes.c_ulong),
        ("dmMediaType", ctypes.c_ulong),
        ("dmDitherType", ctypes.c_ulong),
        ("dmReserved1", ctypes.c_ulong),
        ("dmReserved2", ctypes.c_ulong),
        ("dmPanningWidth", ctypes.c_ulong),
        ("dmPanningHeight", ctypes.c_ulong),
    ]


class WindowsSettingsHandler(SettingsHandler):
    """Handles Windows gaming-related settings.

    Manages:
    - Game Mode
    - Game Bar / Game DVR
    - Hardware-Accelerated GPU Scheduling (HAGS)
    - VBS / Memory Integrity
    - HDR / Auto HDR
    - Display refresh rate optimization
    """

    # Registry paths
    GAME_BAR_KEY = r"Software\Microsoft\GameBar"
    GAME_DVR_KEY = r"Software\Microsoft\Windows\CurrentVersion\GameDVR"
    GRAPHICS_DRIVERS_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
    VBS_KEY = r"SYSTEM\CurrentControlSet\Control\DeviceGuard\Scenarios\HypervisorEnforcedCodeIntegrity"
    # HDR registry path (per-monitor, but this is the global toggle)
    DISPLAY_KEY = r"SOFTWARE\Microsoft\Windows\CurrentVersion\VideoSettings"

    def detect(self) -> dict[str, Any]:
        """Detect current Windows gaming settings."""
        refresh_info = self._get_refresh_rate_info()
        return {
            "game_mode": self._get_game_mode(),
            "game_bar": self._get_game_bar(),
            "game_dvr": self._get_game_dvr(),
            "hags": self._get_hags(),
            "vbs": self._get_vbs(),
            "hdr": self._get_hdr(),
            "auto_hdr": self._get_auto_hdr(),
            "vrr_optimize": self._get_vrr_optimize(),
            "refresh_rate": refresh_info.get("current"),
            "max_refresh_rate": refresh_info.get("max"),
            "available_refresh_rates": refresh_info.get("available"),
        }

    def audit(self) -> list[Issue]:
        """Audit Windows settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check Game Mode
        if not current.get("game_mode"):
            issues.append(Issue(
                title="Game Mode is disabled",
                severity="warning",
                current_value="Disabled",
                optimal_value="Enabled",
                explanation="Game Mode prioritizes gaming processes and reduces background activity.",
                category="windows",
            ))

        # Check Game Bar/DVR (should be disabled for performance)
        if current.get("game_bar"):
            issues.append(Issue(
                title="Game Bar is enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation="Game Bar can add slight overhead. Disable unless you use its features.",
                category="windows",
            ))

        if current.get("game_dvr"):
            issues.append(Issue(
                title="Background recording is enabled",
                severity="warning",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation="Background recording impacts performance even when not actively recording.",
                category="windows",
            ))

        # VBS check
        if current.get("vbs"):
            issues.append(Issue(
                title="VBS / Memory Integrity is enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled (for max performance)",
                explanation=(
                    "VBS provides security but may reduce performance 0-5% depending on workload. "
                    "Impact is often overstated. Test before disabling - security tradeoff may not be worth it."
                ),
                category="windows",
            ))

        # Refresh rate check
        current_hz = current.get("refresh_rate")
        max_hz = current.get("max_refresh_rate")
        if current_hz and max_hz and current_hz < max_hz:
            issues.append(Issue(
                title="Display not running at maximum refresh rate",
                severity="warning",
                current_value=f"{current_hz} Hz",
                optimal_value=f"{max_hz} Hz",
                explanation=(
                    f"Your monitor supports up to {max_hz} Hz but is currently set to {current_hz} Hz. "
                    "Higher refresh rates provide smoother gameplay and lower input latency."
                ),
                category="windows",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply Windows gaming settings.

        Only sets requires_reboot=True if we actually change HAGS or VBS.
        If values already match, no reboot is needed.

        Returns detailed per-setting success/failure information.
        """
        requires_reboot = False
        errors: list[str] = []
        applied: list[str] = []

        # Get current values to check if we're actually changing anything
        current = self.detect()

        # Apply each setting individually with error tracking
        if "game_mode" in settings:
            try:
                self._set_game_mode(settings["game_mode"])
                applied.append(f"Game Mode: {'enabled' if settings['game_mode'] else 'disabled'}")
            except Exception as e:
                errors.append(f"Game Mode: {e}")

        if "game_bar" in settings:
            try:
                self._set_game_bar(settings["game_bar"])
                applied.append(f"Game Bar: {'enabled' if settings['game_bar'] else 'disabled'}")
            except Exception as e:
                errors.append(f"Game Bar: {e}")

        if "game_dvr" in settings:
            try:
                self._set_game_dvr(settings["game_dvr"])
                applied.append(f"Game DVR: {'enabled' if settings['game_dvr'] else 'disabled'}")
            except Exception as e:
                errors.append(f"Game DVR: {e}")

        if "hags" in settings:
            try:
                target = settings["hags"]
                current_hags = current.get("hags")
                # Only set requires_reboot if we can detect current value AND it differs
                if current_hags is not None and current_hags != target:
                    requires_reboot = True
                self._set_hags(target)
                applied.append(f"HAGS: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"HAGS: {e}")

        if "vbs" in settings:
            try:
                target = settings["vbs"]
                current_vbs = current.get("vbs_enabled")
                if current_vbs is None:
                    # Detection failed — conservatively assume reboot needed
                    requires_reboot = True
                elif current_vbs != target:
                    requires_reboot = True
                self._set_vbs(target)
                applied.append(f"VBS: {'enabled' if target else 'disabled'}")
            except Exception as e:
                errors.append(f"VBS: {e}")

        if "hdr" in settings:
            hdr_result = self._set_hdr(settings["hdr"])
            if hdr_result["success"]:
                if settings["hdr"]:
                    applied.append(f"HDR: enabled on {hdr_result['hdr_enabled_count']} monitor(s)")
                else:
                    applied.append("HDR: disabled on all monitors")
            else:
                for err in hdr_result.get("errors", []):
                    errors.append(f"HDR: {err}")

        if "auto_hdr" in settings:
            auto_hdr_result = self._set_auto_hdr(settings["auto_hdr"])
            if auto_hdr_result["success"]:
                applied.append(f"Auto HDR: {'enabled' if settings['auto_hdr'] else 'disabled'}")
            else:
                errors.append(f"Auto HDR: {auto_hdr_result.get('error', 'Unknown error')}")

        if "vrr_optimize" in settings:
            vrr_result = self._set_vrr_optimize(settings["vrr_optimize"])
            if vrr_result["success"]:
                applied.append(f"VRR Optimize: {'enabled' if settings['vrr_optimize'] else 'disabled'}")
            else:
                errors.append(f"VRR Optimize: {vrr_result.get('error', 'Unknown error')}")

        if "refresh_rate" in settings:
            try:
                self._set_refresh_rate(settings["refresh_rate"])
                applied.append(f"Refresh Rate: {settings['refresh_rate']} Hz")
            except Exception as e:
                errors.append(f"Refresh Rate: {e}")

        if settings.get("max_refresh_rate") is True:
            try:
                self._set_max_refresh_rate()
                applied.append("Refresh Rate: set to maximum")
            except Exception as e:
                errors.append(f"Max Refresh Rate: {e}")

        # Log summary
        if applied:
            logger.info(f"Windows settings applied: {', '.join(applied)}")
        if errors:
            logger.warning(f"Windows settings errors: {', '.join(errors)}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
            "applied": applied,
            "failed": errors,
        }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify that reboot-requiring settings are already active.

        Checks HAGS and VBS settings.

        Returns:
            Dict with 'all_active' bool and details for each setting.
        """
        current = self.detect()
        results = {"all_active": True, "settings": {}}

        if "hags" in settings:
            target = settings["hags"]
            current_val = current.get("hags")
            # If we can't detect, assume it's active (can't prove otherwise)
            is_active = current_val is None or current_val == target
            results["settings"]["hags"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        if "vbs" in settings:
            target = settings["vbs"]
            current_val = current.get("vbs_enabled")
            # If we can't detect, assume it's active (can't prove otherwise)
            is_active = current_val is None or current_val == target
            results["settings"]["vbs"] = {
                "target": target,
                "current": current_val if current_val is not None else "undetectable",
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Backup current Windows gaming settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore Windows gaming settings from backup."""
        result = self.apply(data)
        return result.get("success", False)

    # Private helper methods

    def _get_game_mode(self) -> bool | None:
        """Get Game Mode status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_BAR_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "AutoGameModeEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game Mode: {e}")
            return None

    def _set_game_mode(self, enabled: bool) -> None:
        """Set Game Mode status."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.GAME_BAR_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "AllowAutoGameMode", 0, winreg.REG_DWORD, 1 if enabled else 0)
            winreg.SetValueEx(key, "AutoGameModeEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_game_bar(self) -> bool | None:
        """Get Game Bar status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_BAR_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "UseNexusForGameBarEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game Bar: {e}")
            return None

    def _set_game_bar(self, enabled: bool) -> None:
        """Set Game Bar status."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.GAME_BAR_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "UseNexusForGameBarEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_game_dvr(self) -> bool | None:
        """Get Game DVR (background recording) status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.GAME_DVR_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "AppCaptureEnabled")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Game DVR: {e}")
            return None

    def _set_game_dvr(self, enabled: bool) -> None:
        """Set Game DVR status."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.GAME_DVR_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "AppCaptureEnabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_hags(self) -> bool | None:
        """Get Hardware-Accelerated GPU Scheduling status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.GRAPHICS_DRIVERS_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "HwSchMode")[0]
                return value == 2  # 1 = Off, 2 = On
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get HAGS: {e}")
            return None

    def _set_hags(self, enabled: bool) -> None:
        """Set Hardware-Accelerated GPU Scheduling status."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.GRAPHICS_DRIVERS_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "HwSchMode", 0, winreg.REG_DWORD, 2 if enabled else 1)
        finally:
            winreg.CloseKey(key)

    def _get_vbs(self) -> bool | None:
        """Get VBS / Memory Integrity status."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.VBS_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "Enabled")[0]
                return bool(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get VBS: {e}")
            return None

    def _set_vbs(self, enabled: bool) -> None:
        """Set VBS / Memory Integrity status."""
        key = winreg.OpenKey(
            winreg.HKEY_LOCAL_MACHINE,
            self.VBS_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "Enabled", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    @staticmethod
    def _get_active_display_targets() -> list[tuple[_LUID, int]]:
        """Enumerate active display targets via QueryDisplayConfig.

        Returns:
            List of (adapterId, targetId) tuples for each active display.
        """
        user32 = ctypes.windll.user32
        num_paths = wintypes.UINT()
        num_modes = wintypes.UINT()

        status = user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths),
            ctypes.byref(num_modes),
        )
        if status != 0 or num_paths.value == 0:
            return []

        paths = (DISPLAYCONFIG_PATH_INFO * num_paths.value)()
        # We only need paths, not modes, but the API requires the modes buffer
        modes_buf = (ctypes.c_byte * (num_modes.value * 64))()

        status = user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths),
            paths,
            ctypes.byref(num_modes),
            modes_buf,
            None,
        )
        if status != 0:
            return []

        targets: list[tuple[_LUID, int]] = []
        for i in range(num_paths.value):
            t = paths[i].targetInfo
            targets.append((t.adapterId, t.id))
        return targets

    def _is_monitor_hdr_capable(self, monitor_id: str) -> bool:
        """Check if a monitor supports HDR based on hardware ID or registry.

        Uses a two-tier approach:
        1. Known OLED PnP ID patterns (e.g. LG UltraGear OLED GSM78xx+)
        2. Registry AdvancedColorSupported fallback for unknown monitors

        Args:
            monitor_id: Monitor hardware identifier (e.g., "GSM784C_12345").

        Returns:
            True if the monitor is known or detected to support HDR.
        """
        # LG OLED UltraGear monitors use PnP IDs in the GSM78xx+ range
        if monitor_id.startswith("GSM"):
            try:
                hex_part = monitor_id[3:7]
                pnp_num = int(hex_part, 16)
                if pnp_num >= 0x7800:
                    return True
            except (ValueError, IndexError):
                pass

        # Fall back to registry AdvancedColorSupported check
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                rf"SYSTEM\CurrentControlSet\Enum\DISPLAY\{monitor_id}\Device Parameters",
                0,
                winreg.KEY_READ,
            )
            try:
                value, _ = winreg.QueryValueEx(key, "AdvancedColorSupported")
                return bool(value)
            finally:
                winreg.CloseKey(key)
        except Exception:
            return False

    def _get_hdr(self) -> bool | None:
        """Get Windows HDR status using the CCD DisplayConfig API.

        Queries each active display target for advanced color (HDR) state.
        Returns True if ANY monitor has HDR enabled, False if all off, None if unavailable.
        """
        try:
            targets = self._get_active_display_targets()
            if not targets:
                return None

            any_enabled = False
            for adapter_id, target_id in targets:
                info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
                info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
                info.header.size = ctypes.sizeof(info)
                info.header.adapterId = adapter_id
                info.header.id = target_id

                status = ctypes.windll.user32.DisplayConfigGetDeviceInfo(
                    ctypes.byref(info)
                )
                if status != 0:
                    continue

                # bit 1 of value = advancedColorEnabled
                if info.value & 0x02:
                    any_enabled = True
                    break

            return any_enabled
        except Exception as e:
            logger.debug(f"CCD HDR detection failed: {e}")
            return None

    def _set_hdr(self, enabled: bool) -> dict[str, Any]:
        """Set Windows HDR status using the CCD DisplayConfig API.

        Uses DisplayConfigSetDeviceInfo with ADVANCED_COLOR_STATE to
        actually toggle HDR on the display pipeline.  Registry-only writes
        do NOT take effect on modern Windows 11.

        For HDR enable requests:
        - Only enables HDR on monitors that report advancedColorSupported
        - Leaves SDR monitors unchanged

        For HDR disable requests:
        - Disables HDR on all monitors

        Requires admin privileges.

        Returns:
            Dict with 'success', 'hdr_capable_count', 'hdr_enabled_count', and 'errors'.
        """
        result: dict[str, Any] = {
            "success": True,
            "hdr_capable_count": 0,
            "hdr_enabled_count": 0,
            "errors": [],
        }

        try:
            targets = self._get_active_display_targets()
            if not targets:
                result["errors"].append("No active display targets found")
                result["success"] = False
                return result

            user32 = ctypes.windll.user32

            for adapter_id, target_id in targets:
                try:
                    # Query current advanced color info for this target
                    info = DISPLAYCONFIG_GET_ADVANCED_COLOR_INFO()
                    info.header.type = DISPLAYCONFIG_DEVICE_INFO_GET_ADVANCED_COLOR_INFO
                    info.header.size = ctypes.sizeof(info)
                    info.header.adapterId = adapter_id
                    info.header.id = target_id

                    status = user32.DisplayConfigGetDeviceInfo(ctypes.byref(info))
                    if status != 0:
                        logger.debug(
                            f"DisplayConfigGetDeviceInfo failed for target {target_id}: {status}"
                        )
                        continue

                    supported = bool(info.value & 0x01)  # bit 0: advancedColorSupported
                    currently_enabled = bool(info.value & 0x02)  # bit 1: advancedColorEnabled

                    if enabled:
                        if not supported:
                            logger.debug(f"Target {target_id}: SDR monitor, skipping HDR enable")
                            continue
                        result["hdr_capable_count"] += 1
                        if currently_enabled:
                            # Already on, count it
                            result["hdr_enabled_count"] += 1
                            logger.debug(f"Target {target_id}: HDR already enabled")
                            continue
                    else:
                        if not currently_enabled:
                            logger.debug(f"Target {target_id}: HDR already disabled")
                            continue

                    # Set advanced color state
                    state = DISPLAYCONFIG_SET_ADVANCED_COLOR_STATE()
                    state.header.type = DISPLAYCONFIG_DEVICE_INFO_SET_ADVANCED_COLOR_STATE
                    state.header.size = ctypes.sizeof(state)
                    state.header.adapterId = adapter_id
                    state.header.id = target_id
                    state.value = 1 if enabled else 0  # bit 0: enableAdvancedColor

                    status = user32.DisplayConfigSetDeviceInfo(ctypes.byref(state))
                    if status != 0:
                        error_msg = (
                            f"DisplayConfigSetDeviceInfo failed for target {target_id}: "
                            f"error {status}"
                        )
                        logger.error(error_msg)
                        result["errors"].append(error_msg)
                        result["success"] = False
                    else:
                        action = "enabled" if enabled else "disabled"
                        logger.info(f"HDR {action} for display target {target_id}")
                        if enabled:
                            result["hdr_enabled_count"] += 1

                except Exception as e:
                    error_msg = f"Failed to set HDR for target {target_id}: {e}"
                    logger.error(error_msg)
                    result["errors"].append(error_msg)
                    result["success"] = False

        except Exception as e:
            error_msg = f"Failed to set HDR: {e}"
            logger.error(error_msg)
            result["errors"].append(error_msg)
            result["success"] = False

        return result

    def _get_auto_hdr(self) -> bool | None:
        """Get Windows Auto HDR status (Windows 11 only)."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\DirectX\UserGpuPreferences",
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                # Auto HDR is enabled if SwapEffectUpgradeEnable=1 in the string
                return "SwapEffectUpgradeEnable=1" in str(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get Auto HDR status: {e}")
            return None

    def _set_auto_hdr(self, enabled: bool) -> dict[str, Any]:
        """Set Windows Auto HDR status (Windows 11 only).

        Auto HDR converts SDR games to HDR automatically.
        For competitive gaming, this should typically be disabled.

        Returns:
            Dict with 'success' and optional 'error'.
        """
        result: dict[str, Any] = {"success": True, "error": None}

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\DirectX\UserGpuPreferences",
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                current = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                # Parse and update the SwapEffectUpgradeEnable setting
                if "SwapEffectUpgradeEnable=" in current:
                    new_value = current.replace(
                        "SwapEffectUpgradeEnable=1" if not enabled else "SwapEffectUpgradeEnable=0",
                        "SwapEffectUpgradeEnable=1" if enabled else "SwapEffectUpgradeEnable=0"
                    )
                else:
                    # Add the setting
                    new_value = current + f";SwapEffectUpgradeEnable={'1' if enabled else '0'}"
                winreg.SetValueEx(key, "DirectXUserGlobalSettings", 0, winreg.REG_SZ, new_value)
                logger.info(f"Auto HDR set to {'enabled' if enabled else 'disabled'}")
            except FileNotFoundError:
                # Create default value
                winreg.SetValueEx(
                    key,
                    "DirectXUserGlobalSettings",
                    0,
                    winreg.REG_SZ,
                    f"SwapEffectUpgradeEnable={'1' if enabled else '0'}"
                )
                logger.info(f"Auto HDR set to {'enabled' if enabled else 'disabled'} (created new key)")
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            # Key doesn't exist, create it
            try:
                key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\DirectX\UserGpuPreferences"
                )
                try:
                    winreg.SetValueEx(
                        key,
                        "DirectXUserGlobalSettings",
                        0,
                        winreg.REG_SZ,
                        f"SwapEffectUpgradeEnable={'1' if enabled else '0'}"
                    )
                    logger.info(f"Auto HDR set to {'enabled' if enabled else 'disabled'} (created registry path)")
                finally:
                    winreg.CloseKey(key)
            except Exception as e:
                error_msg = f"Failed to create Auto HDR registry key: {e}"
                logger.error(error_msg)
                result["success"] = False
                result["error"] = error_msg
        except PermissionError as e:
            error_msg = f"Permission denied setting Auto HDR: {e}"
            logger.error(error_msg)
            result["success"] = False
            result["error"] = error_msg
        except Exception as e:
            error_msg = f"Failed to set Auto HDR: {e}"
            logger.error(error_msg)
            result["success"] = False
            result["error"] = error_msg

        return result

    def _get_vrr_optimize(self) -> bool | None:
        """Get VRR Optimize for windowed games status (Windows 11).

        VRROptimizeEnable controls whether Windows applies VRR compositor
        optimizations. Counterintuitively, this can ADD latency even in
        exclusive fullscreen by keeping compositor logic in the path.
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\DirectX\UserGpuPreferences",
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                return "VRROptimizeEnable=1" in str(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get VRR Optimize status: {e}")
            return None

    def _set_vrr_optimize(self, enabled: bool) -> dict[str, Any]:
        """Set VRR Optimize for windowed games (Windows 11).

        IMPORTANT: For minimum latency, this should be DISABLED.
        VRROptimizeEnable=1 keeps compositor logic in the path even in
        exclusive fullscreen, which may add latency.

        Returns:
            Dict with 'success' and optional 'error'.
        """
        result: dict[str, Any] = {"success": True, "error": None}

        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                r"Software\Microsoft\DirectX\UserGpuPreferences",
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                current = winreg.QueryValueEx(key, "DirectXUserGlobalSettings")[0]
                # Parse and update the VRROptimizeEnable setting
                if "VRROptimizeEnable=" in current:
                    new_value = current.replace(
                        "VRROptimizeEnable=1" if not enabled else "VRROptimizeEnable=0",
                        "VRROptimizeEnable=1" if enabled else "VRROptimizeEnable=0"
                    )
                else:
                    # Add the setting
                    new_value = current.rstrip(";") + f";VRROptimizeEnable={'1' if enabled else '0'};"
                winreg.SetValueEx(key, "DirectXUserGlobalSettings", 0, winreg.REG_SZ, new_value)
                logger.info(f"VRR Optimize set to {'enabled' if enabled else 'disabled'}")
            except FileNotFoundError:
                # Create default value with all relevant settings disabled for latency
                winreg.SetValueEx(
                    key,
                    "DirectXUserGlobalSettings",
                    0,
                    winreg.REG_SZ,
                    f"SwapEffectUpgradeEnable=0;AutoHDREnable=0;VRROptimizeEnable={'1' if enabled else '0'};"
                )
                logger.info(f"VRR Optimize set to {'enabled' if enabled else 'disabled'} (created new key)")
            finally:
                winreg.CloseKey(key)
        except FileNotFoundError:
            # Key doesn't exist, create it
            try:
                key = winreg.CreateKey(
                    winreg.HKEY_CURRENT_USER,
                    r"Software\Microsoft\DirectX\UserGpuPreferences"
                )
                try:
                    winreg.SetValueEx(
                        key,
                        "DirectXUserGlobalSettings",
                        0,
                        winreg.REG_SZ,
                        f"SwapEffectUpgradeEnable=0;AutoHDREnable=0;VRROptimizeEnable={'1' if enabled else '0'};"
                    )
                    logger.info(f"VRR Optimize set to {'enabled' if enabled else 'disabled'} (created registry path)")
                finally:
                    winreg.CloseKey(key)
            except Exception as e:
                error_msg = f"Failed to create VRR Optimize registry key: {e}"
                logger.error(error_msg)
                result["success"] = False
                result["error"] = error_msg
        except PermissionError as e:
            error_msg = f"Permission denied setting VRR Optimize: {e}"
            logger.error(error_msg)
            result["success"] = False
            result["error"] = error_msg
        except Exception as e:
            error_msg = f"Failed to set VRR Optimize: {e}"
            logger.error(error_msg)
            result["success"] = False
            result["error"] = error_msg

        return result

    def _get_refresh_rate_info(self) -> dict[str, Any]:
        """Get current and available refresh rates for the primary display.

        Returns:
            Dictionary with 'current', 'max', and 'available' refresh rates.
        """
        result: dict[str, Any] = {
            "current": None,
            "max": None,
            "available": [],
        }

        try:
            user32 = ctypes.windll.user32

            # Get current display settings
            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)

            if user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
                result["current"] = devmode.dmDisplayFrequency
                current_width = devmode.dmPelsWidth
                current_height = devmode.dmPelsHeight

                # Enumerate all available modes at current resolution
                available_rates: set[int] = set()
                mode_num = 0
                enum_devmode = DEVMODE()
                enum_devmode.dmSize = ctypes.sizeof(DEVMODE)

                while mode_num < 500 and user32.EnumDisplaySettingsW(None, mode_num, ctypes.byref(enum_devmode)):
                    # Only consider modes at current resolution
                    if (enum_devmode.dmPelsWidth == current_width and
                        enum_devmode.dmPelsHeight == current_height and
                        enum_devmode.dmDisplayFrequency > 0):
                        available_rates.add(enum_devmode.dmDisplayFrequency)
                    mode_num += 1

                if available_rates:
                    result["available"] = sorted(available_rates)
                    result["max"] = max(available_rates)

        except Exception as e:
            logger.debug(f"Failed to get refresh rate info: {e}")

        return result

    def _set_refresh_rate(self, target_hz: int) -> None:
        """Set the display refresh rate.

        Args:
            target_hz: Target refresh rate in Hz.
        """
        try:
            user32 = ctypes.windll.user32

            # Get current settings
            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)

            if not user32.EnumDisplaySettingsW(None, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
                raise RuntimeError("Failed to get current display settings")

            # Check if already at target rate
            if devmode.dmDisplayFrequency == target_hz:
                logger.info(f"Display already at {target_hz} Hz")
                return

            # Set new refresh rate
            devmode.dmDisplayFrequency = target_hz
            devmode.dmFields = DM_DISPLAYFREQUENCY

            # Test if the mode is valid
            result = user32.ChangeDisplaySettingsW(ctypes.byref(devmode), CDS_TEST)
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Display mode {target_hz} Hz is not supported (error: {result})")

            # Apply the change
            result = user32.ChangeDisplaySettingsW(ctypes.byref(devmode), CDS_UPDATEREGISTRY)
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Failed to set display to {target_hz} Hz (error: {result})")

            logger.info(f"Display refresh rate set to {target_hz} Hz")

        except Exception as e:
            logger.error(f"Failed to set refresh rate: {e}")
            raise

    def _set_max_refresh_rate(self) -> None:
        """Set the display to its maximum supported refresh rate."""
        info = self._get_refresh_rate_info()
        max_hz = info.get("max")
        current_hz = info.get("current")

        if not max_hz:
            logger.warning("Could not determine maximum refresh rate")
            return

        if current_hz == max_hz:
            logger.info(f"Display already at maximum refresh rate ({max_hz} Hz)")
            return

        logger.info(f"Setting display to maximum refresh rate: {max_hz} Hz (was {current_hz} Hz)")
        self._set_refresh_rate(max_hz)

    def optimize_for_gaming(self, primary_max: bool = True, secondary_low: bool = True) -> dict[str, Any]:
        """Optimize multi-monitor setup for gaming.

        Strategy:
        - Primary monitor: Set to maximum refresh rate for best gaming experience
        - Secondary monitors: Lower to 60Hz to reduce GPU compositor load

        This reduces the GPU work for rendering the Windows desktop on secondary
        monitors, freeing up resources for gaming on the primary display.

        Args:
            primary_max: Set primary monitor to max refresh rate (default True)
            secondary_low: Set secondary monitors to 60Hz (default True)

        Returns:
            Dictionary with results for each display.
        """
        results: dict[str, Any] = {}

        try:
            user32 = ctypes.windll.user32

            # Enumerate all display devices
            display_num = 0
            while True:
                try:
                    # DISPLAY_DEVICE structure
                    class DISPLAY_DEVICE(ctypes.Structure):
                        _fields_ = [
                            ("cb", ctypes.c_ulong),
                            ("DeviceName", ctypes.c_wchar * 32),
                            ("DeviceString", ctypes.c_wchar * 128),
                            ("StateFlags", ctypes.c_ulong),
                            ("DeviceID", ctypes.c_wchar * 128),
                            ("DeviceKey", ctypes.c_wchar * 128),
                        ]

                    dd = DISPLAY_DEVICE()
                    dd.cb = ctypes.sizeof(DISPLAY_DEVICE)

                    if not user32.EnumDisplayDevicesW(None, display_num, ctypes.byref(dd), 0):
                        break

                    # Check if this is an active display
                    DISPLAY_DEVICE_ACTIVE = 0x00000001
                    DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004

                    if dd.StateFlags & DISPLAY_DEVICE_ACTIVE:
                        is_primary = bool(dd.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE)
                        device_name = dd.DeviceName

                        # Get current settings for this display
                        devmode = DEVMODE()
                        devmode.dmSize = ctypes.sizeof(DEVMODE)

                        if user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
                            current_hz = devmode.dmDisplayFrequency
                            current_width = devmode.dmPelsWidth
                            current_height = devmode.dmPelsHeight

                            # Find available refresh rates at current resolution
                            available_rates: set[int] = set()
                            mode_num = 0
                            enum_devmode = DEVMODE()
                            enum_devmode.dmSize = ctypes.sizeof(DEVMODE)

                            while mode_num < 500 and user32.EnumDisplaySettingsW(device_name, mode_num, ctypes.byref(enum_devmode)):
                                if (enum_devmode.dmPelsWidth == current_width and
                                    enum_devmode.dmPelsHeight == current_height and
                                    enum_devmode.dmDisplayFrequency > 0):
                                    available_rates.add(enum_devmode.dmDisplayFrequency)
                                mode_num += 1

                            if available_rates:
                                max_hz = max(available_rates)
                                min_hz = min(available_rates)

                                if is_primary and primary_max:
                                    # Primary: set to max
                                    if current_hz < max_hz:
                                        target_hz = max_hz
                                        self._set_display_refresh_rate(device_name, target_hz)
                                        results[device_name] = {
                                            "is_primary": True,
                                            "previous": current_hz,
                                            "new": target_hz,
                                            "action": "maximized",
                                        }
                                    else:
                                        results[device_name] = {
                                            "is_primary": True,
                                            "current": current_hz,
                                            "action": "already_max",
                                        }

                                elif not is_primary and secondary_low:
                                    # Secondary: set to 60Hz (or closest available)
                                    target_hz = 60 if 60 in available_rates else min_hz
                                    if current_hz != target_hz:
                                        self._set_display_refresh_rate(device_name, target_hz)
                                        results[device_name] = {
                                            "is_primary": False,
                                            "previous": current_hz,
                                            "new": target_hz,
                                            "action": "lowered",
                                        }
                                    else:
                                        results[device_name] = {
                                            "is_primary": False,
                                            "current": current_hz,
                                            "action": "already_low",
                                        }

                    display_num += 1

                except Exception as e:
                    logger.debug(f"Error processing display {display_num}: {e}")
                    display_num += 1

        except Exception as e:
            logger.error(f"Failed to optimize displays: {e}")
            results["error"] = str(e)

        return results

    def _set_display_refresh_rate(self, device_name: str, target_hz: int) -> None:
        """Set refresh rate for a specific display.

        Args:
            device_name: Display device name (e.g., '\\\\.\\DISPLAY1')
            target_hz: Target refresh rate in Hz.
        """
        try:
            user32 = ctypes.windll.user32

            devmode = DEVMODE()
            devmode.dmSize = ctypes.sizeof(DEVMODE)

            if not user32.EnumDisplaySettingsW(device_name, ENUM_CURRENT_SETTINGS, ctypes.byref(devmode)):
                raise RuntimeError(f"Failed to get settings for {device_name}")

            devmode.dmDisplayFrequency = target_hz
            devmode.dmFields = DM_DISPLAYFREQUENCY

            # Test the mode
            result = user32.ChangeDisplaySettingsExW(
                device_name, ctypes.byref(devmode), None, CDS_TEST, None
            )
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Mode {target_hz} Hz not supported for {device_name}")

            # Apply the change
            result = user32.ChangeDisplaySettingsExW(
                device_name, ctypes.byref(devmode), None, CDS_UPDATEREGISTRY, None
            )
            if result != DISP_CHANGE_SUCCESSFUL:
                raise RuntimeError(f"Failed to set {device_name} to {target_hz} Hz")

            logger.info(f"Set {device_name} to {target_hz} Hz")

        except Exception as e:
            logger.error(f"Failed to set refresh rate for {device_name}: {e}")
            raise
