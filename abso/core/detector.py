"""Hardware detection module."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

from abso.data.hardware_db import (
    GENERIC_SMBIOS_PLACEHOLDERS,
    GSYNC_NATIVE_PATTERNS,
    GSYNC_ULTIMATE_PATTERNS,
    MOTHERBOARD_MODEL_PATTERNS,
    OEM_MANUFACTURERS,
    OEM_MOTHERBOARD_LOOKUP,
    SMBIOS_CHASSIS_TYPES,
)
from abso.utils.os_release import detect_os_release

logger = logging.getLogger(__name__)


# CCD API structures for accurate refresh rate detection
# See: https://docs.microsoft.com/en-us/windows/win32/api/wingdi/

class LUID(ctypes.Structure):
    """Locally Unique Identifier for display adapter."""
    _fields_ = [
        ("LowPart", wintypes.DWORD),
        ("HighPart", wintypes.LONG),
    ]


class DISPLAYCONFIG_RATIONAL(ctypes.Structure):
    """Rational number for refresh rate (numerator/denominator)."""
    _fields_ = [
        ("Numerator", wintypes.UINT),
        ("Denominator", wintypes.UINT),
    ]


class DISPLAYCONFIG_PATH_SOURCE_INFO(ctypes.Structure):
    """Source info for a display path."""
    _fields_ = [
        ("adapterId", LUID),
        ("id", wintypes.UINT),
        ("modeInfoIdx", wintypes.UINT),
        ("statusFlags", wintypes.UINT),
    ]


class DISPLAYCONFIG_PATH_TARGET_INFO(ctypes.Structure):
    """Target info for a display path including refresh rate."""
    _fields_ = [
        ("adapterId", LUID),
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
    """Display path info containing source and target."""
    _fields_ = [
        ("sourceInfo", DISPLAYCONFIG_PATH_SOURCE_INFO),
        ("targetInfo", DISPLAYCONFIG_PATH_TARGET_INFO),
        ("flags", wintypes.UINT),
    ]


class DISPLAYCONFIG_2DREGION(ctypes.Structure):
    """2D region for display mode."""
    _fields_ = [
        ("cx", wintypes.UINT),
        ("cy", wintypes.UINT),
    ]


class DISPLAYCONFIG_VIDEO_SIGNAL_INFO(ctypes.Structure):
    """Video signal info including pixel rate and resolution."""
    _fields_ = [
        ("pixelRate", ctypes.c_uint64),
        ("hSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("vSyncFreq", DISPLAYCONFIG_RATIONAL),
        ("activeSize", DISPLAYCONFIG_2DREGION),
        ("totalSize", DISPLAYCONFIG_2DREGION),
        ("videoStandard", wintypes.UINT),
        ("scanLineOrdering", wintypes.UINT),
    ]


class DISPLAYCONFIG_TARGET_MODE(ctypes.Structure):
    """Target mode with video signal info."""
    _fields_ = [
        ("targetVideoSignalInfo", DISPLAYCONFIG_VIDEO_SIGNAL_INFO),
    ]


class POINTL(ctypes.Structure):
    """Point structure for position."""
    _fields_ = [
        ("x", wintypes.LONG),
        ("y", wintypes.LONG),
    ]


class DISPLAYCONFIG_SOURCE_MODE(ctypes.Structure):
    """Source mode with resolution and position."""
    _fields_ = [
        ("width", wintypes.UINT),
        ("height", wintypes.UINT),
        ("pixelFormat", wintypes.UINT),
        ("position", POINTL),
    ]


class DISPLAYCONFIG_DESKTOP_IMAGE_INFO(ctypes.Structure):
    """Desktop image info (for completeness of union)."""
    _fields_ = [
        ("PathSourceSize", POINTL),
        ("DesktopImageRegion", ctypes.c_byte * 16),
        ("DesktopImageClip", ctypes.c_byte * 16),
    ]


class DISPLAYCONFIG_MODE_INFO_UNION(ctypes.Union):
    """Union for target or source mode."""
    _fields_ = [
        ("targetMode", DISPLAYCONFIG_TARGET_MODE),
        ("sourceMode", DISPLAYCONFIG_SOURCE_MODE),
        ("desktopImageInfo", DISPLAYCONFIG_DESKTOP_IMAGE_INFO),
    ]


class DISPLAYCONFIG_MODE_INFO(ctypes.Structure):
    """Mode info structure."""
    _fields_ = [
        ("infoType", wintypes.UINT),
        ("id", wintypes.UINT),
        ("adapterId", LUID),
        ("info", DISPLAYCONFIG_MODE_INFO_UNION),
    ]


# CCD API constants
QDC_ONLY_ACTIVE_PATHS = 0x00000002
DISPLAYCONFIG_MODE_INFO_TYPE_SOURCE = 1
DISPLAYCONFIG_MODE_INFO_TYPE_TARGET = 2

# Win32 display constants (legacy APIs)
DISPLAY_DEVICE_ATTACHED_TO_DESKTOP = 0x00000001
DISPLAY_DEVICE_PRIMARY_DEVICE = 0x00000004
ENUM_CURRENT_SETTINGS = -1

# Win32 structure constants
CCHDEVICENAME = 32
CCHDEVICESTRING = 128
CCHFORMNAME = 32


class DISPLAY_DEVICEW(ctypes.Structure):
    """Win32 DISPLAY_DEVICEW structure."""

    _fields_ = [
        ("cb", wintypes.DWORD),
        ("DeviceName", wintypes.WCHAR * CCHDEVICENAME),
        ("DeviceString", wintypes.WCHAR * CCHDEVICESTRING),
        ("StateFlags", wintypes.DWORD),
        ("DeviceID", wintypes.WCHAR * CCHDEVICESTRING),
        ("DeviceKey", wintypes.WCHAR * CCHDEVICESTRING),
    ]


class DEVMODEW(ctypes.Structure):
    """Win32 DEVMODEW structure (display-relevant fields)."""

    _fields_ = [
        ("dmDeviceName", wintypes.WCHAR * CCHDEVICENAME),
        ("dmSpecVersion", wintypes.WORD),
        ("dmDriverVersion", wintypes.WORD),
        ("dmSize", wintypes.WORD),
        ("dmDriverExtra", wintypes.WORD),
        ("dmFields", wintypes.DWORD),
        ("dmPosition", POINTL),
        ("dmDisplayOrientation", wintypes.DWORD),
        ("dmDisplayFixedOutput", wintypes.DWORD),
        ("dmColor", wintypes.SHORT),
        ("dmDuplex", wintypes.SHORT),
        ("dmYResolution", wintypes.SHORT),
        ("dmTTOption", wintypes.SHORT),
        ("dmCollate", wintypes.SHORT),
        ("dmFormName", wintypes.WCHAR * CCHFORMNAME),
        ("dmLogPixels", wintypes.WORD),
        ("dmBitsPerPel", wintypes.DWORD),
        ("dmPelsWidth", wintypes.DWORD),
        ("dmPelsHeight", wintypes.DWORD),
        ("dmDisplayFlags", wintypes.DWORD),
        ("dmDisplayFrequency", wintypes.DWORD),
        ("dmICMMethod", wintypes.DWORD),
        ("dmICMIntent", wintypes.DWORD),
        ("dmMediaType", wintypes.DWORD),
        ("dmDitherType", wintypes.DWORD),
        ("dmReserved1", wintypes.DWORD),
        ("dmReserved2", wintypes.DWORD),
        ("dmPanningWidth", wintypes.DWORD),
        ("dmPanningHeight", wintypes.DWORD),
    ]


def _get_refresh_rates_ccd() -> dict[int, float]:
    """Get refresh rates for all active displays using CCD API.

    The CCD (Connecting and Configuring Displays) API provides accurate
    refresh rate information including for custom resolutions and DSC modes
    that the legacy EnumDisplaySettings API doesn't report correctly.

    For VRR/G-Sync displays, the vSyncFreq reports the base rate (e.g., 60 Hz).
    To get the actual target refresh rate, we calculate it from:
        pixelRate / (totalSize.cx * totalSize.cy)

    Returns:
        Dictionary mapping source ID to refresh rate in Hz.
    """
    refresh_rates: dict[int, float] = {}

    try:
        user32 = ctypes.windll.user32

        # Get buffer sizes
        num_paths = wintypes.UINT()
        num_modes = wintypes.UINT()

        result = user32.GetDisplayConfigBufferSizes(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths),
            ctypes.byref(num_modes)
        )

        if result != 0:
            logger.debug(f"GetDisplayConfigBufferSizes failed with error {result}")
            return refresh_rates

        if num_paths.value == 0:
            return refresh_rates

        # Allocate arrays
        paths = (DISPLAYCONFIG_PATH_INFO * num_paths.value)()
        modes = (DISPLAYCONFIG_MODE_INFO * num_modes.value)()

        # Query display config
        result = user32.QueryDisplayConfig(
            QDC_ONLY_ACTIVE_PATHS,
            ctypes.byref(num_paths),
            paths,
            ctypes.byref(num_modes),
            modes,
            None  # currentTopologyId
        )

        if result != 0:
            logger.debug(f"QueryDisplayConfig failed with error {result}")
            return refresh_rates

        # Build a map of target ID to mode info for pixel rate calculation
        target_modes = {}
        for i in range(num_modes.value):
            mode = modes[i]
            if mode.infoType == DISPLAYCONFIG_MODE_INFO_TYPE_TARGET:
                target_modes[mode.id] = mode.info.targetMode.targetVideoSignalInfo

        # Extract refresh rates from active paths
        for i in range(num_paths.value):
            path = paths[i]
            target = path.targetInfo
            source = path.sourceInfo

            # Try to get accurate refresh rate from pixel clock calculation
            # This works correctly even when VRR reports a base rate
            vsig = target_modes.get(target.id)
            if vsig and vsig.totalSize.cx > 0 and vsig.totalSize.cy > 0:
                total_pixels = vsig.totalSize.cx * vsig.totalSize.cy
                if vsig.pixelRate > 0 and total_pixels > 0:
                    hz = vsig.pixelRate / total_pixels
                    refresh_rates[source.id] = round(hz, 2)
                    logger.debug(
                        f"CCD: Source {source.id} -> {hz:.2f} Hz "
                        f"(from pixel clock: {vsig.pixelRate} / {total_pixels})"
                    )
                    continue

            # Fallback to vSyncFreq if pixel calculation not available
            if target.refreshRate.Denominator > 0:
                hz = target.refreshRate.Numerator / target.refreshRate.Denominator
                refresh_rates[source.id] = round(hz, 2)
                logger.debug(
                    f"CCD: Source {source.id} -> {hz:.2f} Hz "
                    f"(from vSync: {target.refreshRate.Numerator}/{target.refreshRate.Denominator})"
                )

    except OSError as e:
        logger.debug(f"CCD API failed: {e}")
    except Exception as e:
        logger.debug(f"CCD API unexpected error: {e}")

    return refresh_rates


def _detect_vrr_from_edid(monitor_id: str) -> dict[str, Any]:
    """Detect VRR/G-Sync/FreeSync capability from monitor EDID.

    Args:
        monitor_id: The monitor ID (e.g., 'DELD0E6', 'GSM784C')

    Returns:
        Dictionary with VRR detection results.
    """
    result = {
        "vrr_supported": None,  # None = unknown, True/False = detected
        "vrr_type": None,  # 'gsync', 'gsync_compatible', 'freesync', 'adaptive_sync'
        "vrr_min_hz": None,
        "vrr_max_hz": None,
    }

    MAX_ENUM = 1000  # Guard against malformed registry

    try:
        # Find EDID in registry
        edid_path = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
        display_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, edid_path)
        try:
            i = 0
            while i < MAX_ENUM:
                try:
                    reg_monitor_id = winreg.EnumKey(display_key, i)

                    # Check if this matches our monitor
                    if monitor_id.upper() not in reg_monitor_id.upper():
                        i += 1
                        continue

                    monitor_key = winreg.OpenKey(display_key, reg_monitor_id)
                    try:
                        j = 0
                        while j < MAX_ENUM:
                            try:
                                instance = winreg.EnumKey(monitor_key, j)
                                device_params = winreg.OpenKey(
                                    monitor_key, f"{instance}\\Device Parameters"
                                )
                                try:
                                    edid, _ = winreg.QueryValueEx(device_params, "EDID")
                                    vrr_info = _parse_edid_for_vrr(bytes(edid))
                                    if vrr_info.get("vrr_supported"):
                                        result.update(vrr_info)
                                        return result
                                except FileNotFoundError:
                                    pass
                                finally:
                                    winreg.CloseKey(device_params)
                                j += 1
                            except OSError:
                                break
                    finally:
                        winreg.CloseKey(monitor_key)
                    i += 1
                except OSError:
                    break
        finally:
            winreg.CloseKey(display_key)
    except OSError as e:
        logger.debug(f"EDID VRR detection failed (registry access): {e}")
    except ValueError as e:
        logger.debug(f"EDID VRR detection failed (parsing): {e}")

    return result


def _parse_edid_for_vrr(edid: bytes) -> dict[str, Any]:
    """Parse EDID bytes to detect VRR capability.

    Looks for:
    - AMD FreeSync data block (OUI 00-1A-00)
    - VESA Adaptive-Sync in DisplayID extension
    - VRR capability flags in CTA-861 extension

    Args:
        edid: Raw EDID bytes

    Returns:
        Dictionary with VRR info if detected.
    """
    result: dict[str, Any] = {
        "vrr_supported": False,
        "vrr_type": None,
        "vrr_min_hz": None,
        "vrr_max_hz": None,
    }

    if len(edid) < 128:
        return result

    num_extensions = edid[126]
    if num_extensions == 0:
        return result

    # Parse extension blocks
    offset = 128
    for _ in range(num_extensions):
        if offset + 128 > len(edid):
            break

        ext_tag = edid[offset]

        # CTA-861 extension (0x02) - contains VRR/FreeSync data blocks
        if ext_tag == 0x02:
            _revision = edid[offset + 1]  # noqa: F841 - reserved for future use
            dtd_offset = edid[offset + 2]

            if dtd_offset < 4:
                offset += 128
                continue

            # Parse data blocks
            db_offset = offset + 4
            while db_offset < offset + dtd_offset and db_offset < offset + 127:
                if db_offset >= len(edid):
                    break

                header = edid[db_offset]
                tag = (header >> 5) & 0x07
                length = header & 0x1F

                if length == 0:
                    db_offset += 1
                    continue

                # Vendor-Specific Data Block (tag 3)
                if tag == 3 and length >= 3 and db_offset + length + 1 <= len(edid):
                    # Check OUI (IEEE Registration Authority)
                    oui = edid[db_offset + 1 : db_offset + 4]

                    # AMD FreeSync OUI: 00-1A-00 (stored little-endian: 00 1A 00)
                    # EDID reports hardware capability, NOT whether VRR is
                    # currently enabled in the monitor's OSD.  Mark as
                    # "hardware" so callers can distinguish panel capability
                    # from confirmed-active VRR.
                    if list(oui) == [0x00, 0x1A, 0x00] or list(oui) == [0x1A, 0x00, 0x00]:
                        result["vrr_supported"] = "hardware"
                        result["vrr_type"] = "freesync"
                        # FreeSync range is typically in bytes 5-6 of the data block
                        if length >= 6 and db_offset + 6 < len(edid):
                            result["vrr_min_hz"] = edid[db_offset + 5]
                            result["vrr_max_hz"] = edid[db_offset + 6]
                        return result

                # Extended tag block (tag 7)
                if tag == 7 and length >= 1 and db_offset + 1 < len(edid):
                    _ext_code = edid[db_offset + 1]  # noqa: F841 - reserved for future use
                    # Various VRR-related extended tags could be here

                db_offset += length + 1

        # DisplayID extension (0x70) - newer displays may use this
        elif ext_tag == 0x70:
            # DisplayID 2.0+ can contain Adaptive-Sync data
            # Simplified detection - presence suggests modern VRR support
            pass

        offset += 128

    return result


def _detect_gsync_from_nvidia_registry() -> dict[str, Any]:
    """Detect G-Sync settings from NVIDIA driver registry.

    The NVIDIA driver stores G-Sync/VRR settings in the registry.
    This function queries those settings to determine G-Sync status.

    Returns:
        Dictionary with G-Sync detection results per monitor.
    """
    result: dict[str, Any] = {
        "gsync_enabled_globally": False,
        "gsync_monitors": [],
    }

    try:
        # NVIDIA stores display settings in the driver registry
        # Path: HKLM\SYSTEM\CurrentControlSet\Services\nvlddmkm\...
        nvidia_path = r"SYSTEM\CurrentControlSet\Services\nvlddmkm"

        try:
            nvidia_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, nvidia_path)
            winreg.CloseKey(nvidia_key)
        except FileNotFoundError:
            logger.debug("NVIDIA driver registry not found")
            return result

        # Check for G-Sync compatible mode in NVIDIA profile settings
        # NVIDIA Control Panel stores VRR settings in the user's profile
        nv_profile_paths = [
            r"SOFTWARE\NVIDIA Corporation\Global\FTS",
            r"SOFTWARE\NVIDIA Corporation\Global\GSync",
        ]

        for path in nv_profile_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, path)
            except FileNotFoundError:
                continue
            # CloseKey must run regardless of what QueryValueEx raises.
            # The previous shape only closed on the FileNotFoundError path
            # and leaked the handle for any other registry error.
            try:
                try:
                    value, _ = winreg.QueryValueEx(key, "EnableGSync")
                    if value == 1:
                        result["gsync_enabled_globally"] = True
                except FileNotFoundError:
                    pass
            finally:
                winreg.CloseKey(key)

        # Also check user-specific NVIDIA settings
        user_nv_paths = [
            r"SOFTWARE\NVIDIA Corporation\Global\FTS",
        ]

        for path in user_nv_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
            except FileNotFoundError:
                continue
            try:
                try:
                    value, _ = winreg.QueryValueEx(key, "EnableGSync")
                    if value == 1:
                        result["gsync_enabled_globally"] = True
                except FileNotFoundError:
                    pass
            finally:
                winreg.CloseKey(key)

    except OSError as e:
        logger.debug(f"G-Sync registry detection failed: {e}")

    # Fallback: Modern drivers (591+) store G-SYNC in the DRS global profile
    # rather than the legacy registry paths above.  Query NVAPI directly.
    if not result["gsync_enabled_globally"]:
        try:
            from abso.settings.nvidia.nvapi_drs import DRSProfileManager

            mgr = DRSProfileManager()
            global_settings = mgr.get_app_settings()
            # vrr_mode: 0=disabled, 1=fullscreen_only, 2=fullscreen_and_windowed
            vrr_mode = global_settings.get("vrr_mode")
            if vrr_mode is not None and vrr_mode >= 1:
                result["gsync_enabled_globally"] = True
                logger.debug(f"G-Sync detected via DRS global vrr_mode={vrr_mode}")
        except Exception as e:
            logger.debug(f"DRS G-Sync detection fallback failed: {e}")

    return result


# DEPRECATED: v2.0 — prefer EDID/registry detection
def _is_known_gsync_monitor(monitor_name: str) -> tuple[bool, str | None]:
    """Check if monitor name matches known G-Sync monitor patterns.

    DEPRECATED: This hardcoded list is a last-resort fallback. Prefer EDID
    parsing and NVIDIA registry/DRS detection for VRR discovery. The
    pattern tables live in :mod:`abso.data.hardware_db`.

    Args:
        monitor_name: The monitor name/model string.

    Returns:
        Tuple of (is_gsync, gsync_type) where gsync_type is
        'gsync_native', 'gsync_ultimate', or None.
    """
    name_upper = monitor_name.upper()

    for pattern in GSYNC_ULTIMATE_PATTERNS:
        if pattern in name_upper:
            return True, "gsync_ultimate"

    for pattern in GSYNC_NATIVE_PATTERNS:
        if pattern in name_upper:
            return True, "gsync_native"

    return False, None


@dataclass
class SystemInfo:
    """System/PC information (OEM or motherboard-based)."""

    manufacturer: str
    model: str
    system_family: str | None
    system_sku: str | None
    motherboard_manufacturer: str | None
    motherboard_model: str | None
    bios_vendor: str | None
    bios_version: str | None
    chassis_type: str | None
    is_prebuilt: bool  # True if likely OEM pre-built, False if custom build


@dataclass
class GPUInfo:
    """GPU hardware information."""

    name: str
    driver_version: str
    vram_mb: int


@dataclass
class CPUInfo:
    """CPU hardware information."""

    name: str
    cores: int
    threads: int
    max_clock_mhz: int


@dataclass
class RAMInfo:
    """RAM hardware information."""

    total_gb: float


@dataclass
class MonitorInfo:
    """Monitor hardware information."""

    name: str
    resolution: str
    refresh_rate: int
    is_primary: bool


class HardwareDetector:
    """Detects gaming hardware components."""

    def __init__(self) -> None:
        self._wmi = None

    def __del__(self) -> None:
        """Clean up WMI connection on garbage collection."""
        self.cleanup()

    def cleanup(self) -> None:
        """Explicitly release WMI connection resources."""
        if self._wmi is not None:
            try:
                # WMI connections don't have explicit close, but setting to None
                # allows garbage collection of COM objects
                self._wmi = None
            except Exception:
                pass

    def _get_wmi(self):
        """Lazy-load WMI connection."""
        if self._wmi is None:
            try:
                import wmi
                self._wmi = wmi.WMI()
            except ImportError:
                logger.warning("WMI module not available")
            except AttributeError as e:
                logger.error(f"WMI initialization error: {e}")
            except RuntimeError as e:
                logger.error(f"WMI connection failed: {e}")
        return self._wmi

    def detect_all(self) -> dict[str, Any]:
        """Detect all hardware components.

        Returns:
            Dictionary containing detected hardware information.
        """
        return {
            "system": self.detect_system(),
            "gpu": self.detect_gpu(),
            "cpu": self.detect_cpu(),
            "ram": self.detect_ram(),
            "monitors": self.detect_monitors(),
            "windows_version": self.detect_windows_version(),
        }

    def detect_system(self) -> dict[str, Any] | None:
        """Detect system/PC information (OEM pre-built or custom build).

        Uses WMI to query:
        - Win32_ComputerSystem: Manufacturer, Model, SystemFamily, SystemSKUNumber
        - Win32_BaseBoard: Motherboard manufacturer and model
        - Win32_BIOS: BIOS vendor and version
        - Win32_SystemEnclosure: Chassis type

        For pre-built systems (Dell, HP, Lenovo, etc.), this returns the OEM
        branding. For custom builds, it returns motherboard information.

        Returns:
            System information dict or None if detection fails.
        """
        wmi_conn = self._get_wmi()
        if not wmi_conn:
            return None

        result: dict[str, Any] = {
            "manufacturer": None,
            "model": None,
            "system_family": None,
            "system_sku": None,
            "motherboard_manufacturer": None,
            "motherboard_model": None,
            "bios_vendor": None,
            "bios_version": None,
            "chassis_type": None,
            "is_prebuilt": False,
            "prebuilt_name": None,  # Friendly name if identified
        }

        # OEM / chassis / motherboard reference tables live in
        # abso.data.hardware_db so this method stays focused on flow.
        try:
            # Query Win32_ComputerSystem for main system info
            for system in wmi_conn.Win32_ComputerSystem():
                result["manufacturer"] = (system.Manufacturer or "").strip()
                result["model"] = (system.Model or "").strip()

                # SystemFamily and SystemSKUNumber may not exist on all systems
                try:
                    result["system_family"] = (system.SystemFamily or "").strip() or None
                except AttributeError:
                    pass
                try:
                    result["system_sku"] = (system.SystemSKUNumber or "").strip() or None
                except AttributeError:
                    pass
                break

        except AttributeError as e:
            logger.debug(f"Win32_ComputerSystem query failed: {e}")
        except RuntimeError as e:
            logger.error(f"Win32_ComputerSystem query failed: {e}")

        try:
            # Query Win32_BaseBoard for motherboard info
            for board in wmi_conn.Win32_BaseBoard():
                result["motherboard_manufacturer"] = (board.Manufacturer or "").strip() or None
                result["motherboard_model"] = (board.Product or "").strip() or None
                break

        except AttributeError as e:
            logger.debug(f"Win32_BaseBoard query failed: {e}")
        except RuntimeError as e:
            logger.error(f"Win32_BaseBoard query failed: {e}")

        try:
            # Query Win32_BIOS for BIOS info
            for bios in wmi_conn.Win32_BIOS():
                result["bios_vendor"] = (bios.Manufacturer or "").strip() or None
                result["bios_version"] = (bios.SMBIOSBIOSVersion or "").strip() or None
                break

        except AttributeError as e:
            logger.debug(f"Win32_BIOS query failed: {e}")
        except RuntimeError as e:
            logger.error(f"Win32_BIOS query failed: {e}")

        try:
            # Query Win32_SystemEnclosure for chassis type
            for enclosure in wmi_conn.Win32_SystemEnclosure():
                if enclosure.ChassisTypes:
                    # ChassisTypes is an array, take the first value
                    chassis_code = enclosure.ChassisTypes[0]
                    result["chassis_type"] = SMBIOS_CHASSIS_TYPES.get(
                        chassis_code, f"Unknown ({chassis_code})"
                    )
                break

        except AttributeError as e:
            logger.debug(f"Win32_SystemEnclosure query failed: {e}")
        except RuntimeError as e:
            logger.error(f"Win32_SystemEnclosure query failed: {e}")

        # Check motherboard against known OEM lookup table
        mobo_model_lower = (result["motherboard_model"] or "").lower()
        prebuilt_from_mobo = None
        prebuilt_name_from_mobo = None

        for pattern, mfr, name in OEM_MOTHERBOARD_LOOKUP:
            if pattern in mobo_model_lower:
                prebuilt_from_mobo = mfr or result["manufacturer"]
                prebuilt_name_from_mobo = name
                break

        # If we found a match in the OEM motherboard lookup, it's a pre-built
        if prebuilt_from_mobo:
            result["is_prebuilt"] = True
            result["prebuilt_name"] = prebuilt_name_from_mobo
            # Clean up empty strings to None
            for key in ["manufacturer", "model"]:
                if result[key] == "":
                    result[key] = None
            return result

        # Otherwise, fall back to heuristic detection
        manufacturer_lower = (result["manufacturer"] or "").lower()
        model_lower = (result["model"] or "").lower()
        system_family_lower = (result["system_family"] or "").lower()
        system_sku_lower = (result["system_sku"] or "").lower()

        # Check against known OEM list
        is_known_oem = any(oem in manufacturer_lower for oem in OEM_MANUFACTURERS)

        has_generic_model = any(ind in model_lower for ind in GENERIC_SMBIOS_PLACEHOLDERS)
        has_generic_family = any(ind in system_family_lower for ind in GENERIC_SMBIOS_PLACEHOLDERS)
        has_generic_sku = any(ind in system_sku_lower for ind in GENERIC_SMBIOS_PLACEHOLDERS)

        # Check if the system model looks like a motherboard model
        model_is_motherboard = (
            # Model matches or contains the motherboard model
            (mobo_model_lower and model_lower and
             (model_lower in mobo_model_lower or mobo_model_lower in model_lower)) or
            # Model matches motherboard patterns
            any(pattern in model_lower for pattern in MOTHERBOARD_MODEL_PATTERNS)
        )

        # It's a pre-built if:
        # 1. Manufacturer is a known OEM AND
        # 2. Model is not a generic placeholder AND
        # 3. Model doesn't look like a motherboard model AND
        # 4. System family/SKU are not generic (pre-builts usually have real values)
        result["is_prebuilt"] = (
            is_known_oem and
            not has_generic_model and
            not model_is_motherboard and
            not (has_generic_family and has_generic_sku)
        )

        # Clean up empty strings to None
        for key in ["manufacturer", "model"]:
            if result[key] == "":
                result[key] = None

        return result

    def detect_gpu(self) -> dict[str, Any] | None:
        """Detect GPU information.

        Tries nvidia-smi first, falls back to WMI.

        Returns:
            GPU information dict or None if detection fails.
        """
        # Try nvidia-smi first
        gpu = self._detect_gpu_nvidia_smi()
        if gpu:
            return gpu

        # Fallback to WMI
        return self._detect_gpu_wmi()

    def _detect_gpu_nvidia_smi(self) -> dict[str, Any] | None:
        """Detect GPU using nvidia-smi."""
        try:
            result = subprocess.run(
                [
                    "nvidia-smi",
                    "--query-gpu=name,driver_version,memory.total",
                    "--format=csv,noheader,nounits",
                ],
                capture_output=True,
                text=True,
                timeout=5,
            )

            if result.returncode == 0 and result.stdout.strip():
                parts = result.stdout.strip().split(", ")
                if len(parts) >= 3:
                    return {
                        "name": parts[0].strip(),
                        "driver_version": parts[1].strip(),
                        "vram_mb": int(float(parts[2].strip())),
                    }
        except FileNotFoundError:
            logger.debug("nvidia-smi not found")
        except subprocess.TimeoutExpired:
            logger.warning("nvidia-smi timed out")
        except subprocess.SubprocessError as e:
            logger.error(f"nvidia-smi subprocess error: {e}")
        except (ValueError, IndexError) as e:
            logger.error(f"nvidia-smi output parsing failed: {e}")

        return None

    def _detect_gpu_wmi(self) -> dict[str, Any] | None:
        """Detect GPU using WMI."""
        wmi_conn = self._get_wmi()
        if not wmi_conn:
            return None

        try:
            for gpu in wmi_conn.Win32_VideoController():
                # Skip Microsoft Basic Display Adapter
                if "Microsoft" in (gpu.Name or ""):
                    continue

                return {
                    "name": gpu.Name or "Unknown",
                    "driver_version": gpu.DriverVersion or "Unknown",
                    "vram_mb": int(gpu.AdapterRAM or 0) // (1024 * 1024),
                }
        except AttributeError as e:
            logger.error(f"WMI GPU detection failed (attribute error): {e}")
        except RuntimeError as e:
            logger.error(f"WMI GPU detection failed (runtime error): {e}")

        return None

    def detect_cpu(self) -> dict[str, Any] | None:
        """Detect CPU information using WMI.

        Returns:
            CPU information dict or None if detection fails.
        """
        wmi_conn = self._get_wmi()
        if not wmi_conn:
            return None

        try:
            for cpu in wmi_conn.Win32_Processor():
                return {
                    "name": cpu.Name.strip() if cpu.Name else "Unknown",
                    "cores": cpu.NumberOfCores or 0,
                    "threads": cpu.NumberOfLogicalProcessors or 0,
                    "max_clock_mhz": cpu.MaxClockSpeed or 0,
                }
        except AttributeError as e:
            logger.error(f"CPU detection failed (attribute error): {e}")
        except RuntimeError as e:
            logger.error(f"CPU detection failed (runtime error): {e}")

        return None

    def detect_ram(self) -> dict[str, Any] | None:
        """Detect RAM information using WMI.

        Returns:
            RAM information dict or None if detection fails.
        """
        wmi_conn = self._get_wmi()
        if not wmi_conn:
            return None

        try:
            total_bytes = sum(
                int(mem.Capacity or 0)
                for mem in wmi_conn.Win32_PhysicalMemory()
            )
            return {
                "total_gb": round(total_bytes / (1024**3), 1),
            }
        except AttributeError as e:
            logger.error(f"RAM detection failed (attribute error): {e}")
        except RuntimeError as e:
            logger.error(f"RAM detection failed (runtime error): {e}")
        except (ValueError, TypeError) as e:
            logger.error(f"RAM detection failed (calculation error): {e}")

        return None

    def detect_monitors(self) -> list[dict[str, Any]]:
        """Detect connected monitors.

        Returns:
            List of monitor information dicts.
        """
        monitors = []

        # Get accurate refresh rates from CCD API first
        # This properly reports custom resolutions and DSC modes
        ccd_refresh_rates = _get_refresh_rates_ccd()

        try:
            import pywintypes
            import win32api

            # Track which CCD source ID we're on (for active displays only)
            active_display_index = 0

            device_index = 0
            while True:
                try:
                    # Get display adapter (GPU)
                    adapter = win32api.EnumDisplayDevices(None, device_index)
                    if not adapter.DeviceName:
                        break

                    # Skip inactive adapters
                    if not (adapter.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP):
                        device_index += 1
                        continue

                    # Get the actual monitor connected to this adapter
                    monitor_name = f"Monitor {device_index + 1}"
                    monitor_id = None
                    try:
                        monitor = win32api.EnumDisplayDevices(adapter.DeviceName, 0)
                        monitor_name = monitor.DeviceString or monitor_name
                        # Extract monitor ID from DeviceID (e.g., "MONITOR\DELD0E6\...")
                        if monitor.DeviceID:
                            parts = monitor.DeviceID.split("\\")
                            if len(parts) >= 2:
                                monitor_id = parts[1]
                    except (AttributeError, OSError, pywintypes.error) as e:
                        logger.debug(f"Failed to get monitor details for device {device_index}: {e}")

                    # Get current settings from legacy API
                    settings = win32api.EnumDisplaySettings(adapter.DeviceName, ENUM_CURRENT_SETTINGS)

                    legacy_refresh_rate = settings.DisplayFrequency
                    current_width = settings.PelsWidth
                    current_height = settings.PelsHeight

                    # Use legacy API as primary source - it reports actual current refresh rate
                    # CCD API can report incorrect vSyncFreq (base rate ~60Hz) for VRR monitors
                    refresh_rate = legacy_refresh_rate

                    # Only use CCD if it reports a HIGHER value (catches DSC modes)
                    if active_display_index in ccd_refresh_rates:
                        ccd_rate = ccd_refresh_rates[active_display_index]
                        if ccd_rate > legacy_refresh_rate:
                            refresh_rate = ccd_rate
                            logger.debug(
                                f"Using CCD refresh rate {ccd_rate} Hz for display {active_display_index} "
                                f"(legacy reported lower: {legacy_refresh_rate} Hz)"
                            )
                        else:
                            logger.debug(
                                f"Using legacy refresh rate {legacy_refresh_rate} Hz for display {active_display_index} "
                                f"(CCD reported {ccd_rate} Hz - likely VRR base rate)"
                            )

                    # Find maximum supported refresh rate from legacy API
                    max_refresh_rate = refresh_rate
                    max_refresh_any_res = refresh_rate
                    try:
                        mode_index = 0
                        while mode_index < 500:  # Safety limit
                            try:
                                mode = win32api.EnumDisplaySettings(adapter.DeviceName, mode_index)
                                if mode is None:
                                    break
                                # Track max at any resolution (monitor capability)
                                if mode.DisplayFrequency > max_refresh_any_res:
                                    max_refresh_any_res = mode.DisplayFrequency
                                # Check if this mode matches current resolution
                                if (mode.PelsWidth == current_width
                                    and mode.PelsHeight == current_height
                                    and mode.DisplayFrequency > max_refresh_rate):
                                    max_refresh_rate = mode.DisplayFrequency
                                mode_index += 1
                            except pywintypes.error:
                                break
                    except Exception as e:
                        logger.debug(f"Failed to enumerate display modes: {e}")

                    active_display_index += 1

                    # Detect VRR/G-Sync capability using multiple methods
                    vrr_info: dict[str, Any] = {"vrr_supported": None, "vrr_type": None}

                    # Method 1: Try EDID parsing for FreeSync/Adaptive-Sync
                    # EDID reports hardware capability (panel supports VRR),
                    # not whether VRR is currently enabled in the monitor OSD.
                    # Returns "hardware" instead of True to indicate unconfirmed.
                    if monitor_id:
                        edid_vrr = _detect_vrr_from_edid(monitor_id)
                        if edid_vrr.get("vrr_supported"):
                            vrr_info.update(edid_vrr)

                    # Method 2: Check NVIDIA registry for G-Sync enabled status
                    # Always run this (not just as fallback) to cross-reference
                    # EDID hardware capability with actual driver configuration.
                    if vrr_info.get("vrr_supported") is not True:
                        gsync_registry = _detect_gsync_from_nvidia_registry()
                        if gsync_registry.get("gsync_enabled_globally"):
                            if vrr_info.get("vrr_supported") == "hardware":
                                # EDID confirmed hardware capability + NVIDIA
                                # driver has G-SYNC enabled -> promote to confirmed
                                vrr_info["vrr_supported"] = True
                                if vrr_info.get("vrr_type") not in ("gsync_native", "gsync_ultimate"):
                                    vrr_info["vrr_type"] = "gsync_compatible"
                            elif max_refresh_rate > 60:
                                # No EDID data but NVIDIA says G-SYNC is on
                                vrr_info["vrr_supported"] = True
                                vrr_info["vrr_type"] = "gsync_compatible"

                    # Method 3: Fall back to heuristics
                    if vrr_info.get("vrr_supported") is None:
                        # High refresh rate monitors are typically VRR-capable
                        if max_refresh_rate >= 120:
                            vrr_info["vrr_supported"] = "likely"
                            vrr_info["vrr_type"] = "adaptive_sync"
                        elif max_refresh_rate > 60:
                            vrr_info["vrr_supported"] = "possible"
                        else:
                            vrr_info["vrr_supported"] = "unknown"

                    # Method 4 (DEPRECATED): Hardcoded G-Sync model list — last resort
                    if vrr_info.get("vrr_supported") is None or vrr_info.get("vrr_supported") == "unknown":
                        is_known_gsync, gsync_type = _is_known_gsync_monitor(monitor_name)
                        if is_known_gsync:
                            logger.debug("G-SYNC detected via legacy model list (deprecated) for: %s", monitor_name)
                            vrr_info["vrr_supported"] = True
                            vrr_info["vrr_type"] = gsync_type

                    monitors.append({
                        "name": monitor_name,
                        "adapter": adapter.DeviceString or "Unknown",
                        "resolution": f"{settings.PelsWidth}x{settings.PelsHeight}",
                        "refresh_rate": refresh_rate,
                        "max_refresh_rate": max_refresh_rate if max_refresh_rate > refresh_rate else None,
                        "max_refresh_capability": max_refresh_any_res if max_refresh_any_res > refresh_rate else None,
                        "is_primary": bool(adapter.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE),
                        "vrr_supported": vrr_info.get("vrr_supported"),
                        "vrr_type": vrr_info.get("vrr_type"),
                        "vrr_range": (
                            f"{vrr_info.get('vrr_min_hz')}-{vrr_info.get('vrr_max_hz')}Hz"
                            if vrr_info.get("vrr_min_hz") and vrr_info.get("vrr_max_hz")
                            else None
                        ),
                    })

                    device_index += 1
                except (AttributeError, OSError, pywintypes.error) as e:
                    # No more display devices to enumerate
                    logger.debug(f"Finished enumerating displays at index {device_index}: {e}")
                    break

        except ImportError:
            logger.warning("win32api not available for monitor detection")
        except Exception as e:
            # Catch any remaining pywin32 or OS errors
            logger.error(f"Monitor detection failed: {e}")

        if not monitors:
            logger.info("Falling back to ctypes monitor detection (pywin32 unavailable or empty)")
            monitors = self._detect_monitors_without_pywin32(ccd_refresh_rates)

        return monitors

    def _detect_monitors_without_pywin32(
        self,
        ccd_refresh_rates: dict[int, float],
    ) -> list[dict[str, Any]]:
        """Detect monitors using ctypes Win32 API when pywin32 is unavailable."""
        monitors: list[dict[str, Any]] = []
        gsync_registry = _detect_gsync_from_nvidia_registry()
        gsync_enabled_globally = bool(gsync_registry.get("gsync_enabled_globally"))

        try:
            user32 = ctypes.windll.user32
            device_index = 0
            active_display_index = 0

            while True:
                adapter = DISPLAY_DEVICEW()
                adapter.cb = ctypes.sizeof(DISPLAY_DEVICEW)
                if not user32.EnumDisplayDevicesW(None, device_index, ctypes.byref(adapter), 0):
                    break

                if not (adapter.StateFlags & DISPLAY_DEVICE_ATTACHED_TO_DESKTOP):
                    device_index += 1
                    continue

                monitor = DISPLAY_DEVICEW()
                monitor.cb = ctypes.sizeof(DISPLAY_DEVICEW)
                monitor_name = f"Monitor {device_index + 1}"
                monitor_id = None
                if user32.EnumDisplayDevicesW(adapter.DeviceName, 0, ctypes.byref(monitor), 0):
                    if monitor.DeviceString:
                        monitor_name = str(monitor.DeviceString)
                    if monitor.DeviceID:
                        parts = str(monitor.DeviceID).split("\\")
                        if len(parts) >= 2:
                            monitor_id = parts[1]

                settings = DEVMODEW()
                settings.dmSize = ctypes.sizeof(DEVMODEW)
                if not user32.EnumDisplaySettingsW(
                    adapter.DeviceName,
                    ENUM_CURRENT_SETTINGS,
                    ctypes.byref(settings),
                ):
                    device_index += 1
                    continue

                current_width = int(settings.dmPelsWidth or 0)
                current_height = int(settings.dmPelsHeight or 0)
                legacy_refresh_rate = int(settings.dmDisplayFrequency or 0)
                if legacy_refresh_rate <= 0:
                    legacy_refresh_rate = 60

                refresh_rate = float(legacy_refresh_rate)
                if active_display_index in ccd_refresh_rates:
                    ccd_rate = ccd_refresh_rates[active_display_index]
                    if ccd_rate > refresh_rate:
                        refresh_rate = ccd_rate

                max_refresh_rate = float(refresh_rate)
                max_refresh_any_res = float(refresh_rate)

                mode_index = 0
                while mode_index < 500:
                    mode = DEVMODEW()
                    mode.dmSize = ctypes.sizeof(DEVMODEW)
                    if not user32.EnumDisplaySettingsW(adapter.DeviceName, mode_index, ctypes.byref(mode)):
                        break
                    mode_refresh = int(mode.dmDisplayFrequency or 0)
                    if mode_refresh > max_refresh_any_res:
                        max_refresh_any_res = float(mode_refresh)
                    if (
                        int(mode.dmPelsWidth or 0) == current_width
                        and int(mode.dmPelsHeight or 0) == current_height
                        and mode_refresh > max_refresh_rate
                    ):
                        max_refresh_rate = float(mode_refresh)
                    mode_index += 1

                vrr_info = self._derive_vrr_info(
                    monitor_name=monitor_name,
                    monitor_id=monitor_id,
                    max_refresh_rate=max_refresh_rate,
                    gsync_enabled_globally=gsync_enabled_globally,
                )

                monitors.append({
                    "name": monitor_name,
                    "adapter": str(adapter.DeviceString) or "Unknown",
                    "resolution": f"{current_width}x{current_height}",
                    "refresh_rate": refresh_rate,
                    "max_refresh_rate": max_refresh_rate if max_refresh_rate > refresh_rate else None,
                    "max_refresh_capability": (
                        max_refresh_any_res if max_refresh_any_res > refresh_rate else None
                    ),
                    "is_primary": bool(adapter.StateFlags & DISPLAY_DEVICE_PRIMARY_DEVICE),
                    "vrr_supported": vrr_info.get("vrr_supported"),
                    "vrr_type": vrr_info.get("vrr_type"),
                    "vrr_range": (
                        f"{vrr_info.get('vrr_min_hz')}-{vrr_info.get('vrr_max_hz')}Hz"
                        if vrr_info.get("vrr_min_hz") and vrr_info.get("vrr_max_hz")
                        else None
                    ),
                })

                active_display_index += 1
                device_index += 1
        except Exception as e:
            logger.error(f"Monitor detection (ctypes fallback) failed: {e}")

        if monitors:
            return monitors

        return self._detect_monitors_powershell(ccd_refresh_rates, gsync_enabled_globally)

    def _detect_monitors_powershell(
        self,
        ccd_refresh_rates: dict[int, float],
        gsync_enabled_globally: bool,
    ) -> list[dict[str, Any]]:
        """Best-effort monitor detection fallback via PowerShell."""
        monitors: list[dict[str, Any]] = []

        script = (
            "Add-Type -AssemblyName System.Windows.Forms; "
            "[System.Windows.Forms.Screen]::AllScreens | ForEach-Object { "
            "$name = $_.DeviceName; $bounds = $_.Bounds; $primary = $_.Primary; "
            "Write-Output ('{0}|{1}|{2}|{3}' -f $name, $bounds.Width, $bounds.Height, $primary) }"
        )

        try:
            result = subprocess.run(
                ["powershell", "-NoProfile", "-Command", script],
                capture_output=True,
                text=True,
                timeout=10,
            )
            if result.returncode != 0:
                return monitors

            for index, raw_line in enumerate(result.stdout.splitlines()):
                line = raw_line.strip()
                if "|" not in line:
                    continue
                parts = line.split("|")
                if len(parts) < 4:
                    continue

                try:
                    width = int(parts[1].strip())
                    height = int(parts[2].strip())
                except ValueError:
                    width, height = 1920, 1080

                refresh_rate = float(ccd_refresh_rates.get(index, 60.0))
                if gsync_enabled_globally and refresh_rate > 60:
                    vrr_supported: Any = True
                    vrr_type: str | None = "gsync_compatible"
                elif refresh_rate >= 120:
                    vrr_supported = "likely"
                    vrr_type = "adaptive_sync"
                elif refresh_rate > 60:
                    vrr_supported = "possible"
                    vrr_type = None
                else:
                    vrr_supported = "unknown"
                    vrr_type = None

                monitors.append({
                    "name": parts[0].strip() or f"Monitor {index + 1}",
                    "adapter": "Unknown",
                    "resolution": f"{width}x{height}",
                    "refresh_rate": refresh_rate,
                    "max_refresh_rate": None,
                    "max_refresh_capability": None,
                    "is_primary": parts[3].strip().lower() == "true",
                    "vrr_supported": vrr_supported,
                    "vrr_type": vrr_type,
                    "vrr_range": None,
                })
        except Exception as e:
            logger.error(f"Monitor detection (PowerShell fallback) failed: {e}")

        return monitors

    def _derive_vrr_info(
        self,
        monitor_name: str,
        monitor_id: str | None,
        max_refresh_rate: float,
        gsync_enabled_globally: bool,
    ) -> dict[str, Any]:
        """Derive VRR status using EDID, NVIDIA state, heuristics, and legacy model list."""
        vrr_info: dict[str, Any] = {"vrr_supported": None, "vrr_type": None}

        # Step 1: EDID parsing (most reliable hardware-level detection)
        if monitor_id:
            edid_vrr = _detect_vrr_from_edid(monitor_id)
            if edid_vrr.get("vrr_supported"):
                vrr_info.update(edid_vrr)

        # Step 2: NVIDIA registry / DRS cross-reference
        if vrr_info.get("vrr_supported") is not True and gsync_enabled_globally:
            if vrr_info.get("vrr_supported") == "hardware":
                vrr_info["vrr_supported"] = True
                if vrr_info.get("vrr_type") not in ("gsync_native", "gsync_ultimate"):
                    vrr_info["vrr_type"] = "gsync_compatible"
            elif max_refresh_rate > 60:
                vrr_info["vrr_supported"] = True
                vrr_info["vrr_type"] = "gsync_compatible"

        # Step 3: Heuristics based on refresh rate
        if vrr_info.get("vrr_supported") is None:
            if max_refresh_rate >= 120:
                vrr_info["vrr_supported"] = "likely"
                vrr_info["vrr_type"] = "adaptive_sync"
            elif max_refresh_rate > 60:
                vrr_info["vrr_supported"] = "possible"
            else:
                vrr_info["vrr_supported"] = "unknown"

        # Step 4 (DEPRECATED): Hardcoded G-Sync model list — last resort
        if vrr_info.get("vrr_supported") is None or vrr_info.get("vrr_supported") == "unknown":
            is_known_gsync, gsync_type = _is_known_gsync_monitor(monitor_name)
            if is_known_gsync:
                logger.debug("G-SYNC detected via legacy model list (deprecated) for: %s", monitor_name)
                vrr_info["vrr_supported"] = True
                vrr_info["vrr_type"] = gsync_type

        return vrr_info

    def detect_windows_version(self) -> dict[str, Any] | None:
        """Detect Windows version information.

        Returns:
            Windows version dict or None if detection fails.
        """
        try:
            release = detect_os_release(cached=False)
            if release.build == 0:
                return None
            return {
                "display_version": release.display_version or "Unknown",
                "build": str(release.build) if release.build else "Unknown",
                "ubr": release.ubr,
                "build_revision": f"{release.build}.{release.ubr}",
                "edition_id": release.edition_id or None,
                "installation_type": release.installation_type or None,
            }
        except OSError as e:
            logger.error(f"Windows version detection failed (registry error): {e}")
        except (ValueError, TypeError) as e:
            logger.error(f"Windows version detection failed (parsing error): {e}")

        return None
