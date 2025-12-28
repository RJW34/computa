"""Hardware detection module."""

from __future__ import annotations

import ctypes
import logging
import subprocess
import winreg
from ctypes import wintypes
from dataclasses import dataclass
from typing import Any

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

    try:
        # Find EDID in registry
        edid_path = r"SYSTEM\CurrentControlSet\Enum\DISPLAY"
        display_key = winreg.OpenKey(winreg.HKEY_LOCAL_MACHINE, edid_path)

        i = 0
        while True:
            try:
                reg_monitor_id = winreg.EnumKey(display_key, i)

                # Check if this matches our monitor
                if monitor_id.upper() not in reg_monitor_id.upper():
                    i += 1
                    continue

                monitor_key = winreg.OpenKey(display_key, reg_monitor_id)

                j = 0
                while True:
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
                                winreg.CloseKey(device_params)
                                winreg.CloseKey(monitor_key)
                                winreg.CloseKey(display_key)
                                return result
                        except FileNotFoundError:
                            pass
                        winreg.CloseKey(device_params)
                        j += 1
                    except OSError:
                        break

                winreg.CloseKey(monitor_key)
                i += 1
            except OSError:
                break

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
                    if list(oui) == [0x00, 0x1A, 0x00] or list(oui) == [0x1A, 0x00, 0x00]:
                        result["vrr_supported"] = True
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
                try:
                    # Check for G-Sync enable flag
                    value, _ = winreg.QueryValueEx(key, "EnableGSync")
                    if value == 1:
                        result["gsync_enabled_globally"] = True
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except FileNotFoundError:
                continue

        # Also check user-specific NVIDIA settings
        user_nv_paths = [
            r"SOFTWARE\NVIDIA Corporation\Global\FTS",
        ]

        for path in user_nv_paths:
            try:
                key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, path)
                try:
                    value, _ = winreg.QueryValueEx(key, "EnableGSync")
                    if value == 1:
                        result["gsync_enabled_globally"] = True
                except FileNotFoundError:
                    pass
                winreg.CloseKey(key)
            except FileNotFoundError:
                continue

    except OSError as e:
        logger.debug(f"G-Sync registry detection failed: {e}")

    return result


def _is_known_gsync_monitor(monitor_name: str) -> tuple[bool, str | None]:
    """Check if monitor name matches known G-Sync monitor patterns.

    Args:
        monitor_name: The monitor name/model string.

    Returns:
        Tuple of (is_gsync, gsync_type) where gsync_type is
        'gsync_native', 'gsync_ultimate', or None.
    """
    name_upper = monitor_name.upper()

    # Known G-Sync Ultimate monitors (native module)
    gsync_ultimate_patterns = [
        "PG27UQ", "PG65UQ", "X27", "X35",  # ASUS ROG Swift
        "27GN950", "38GN950",  # LG UltraGear
        "AW5520QF", "AW2721D",  # Alienware
    ]

    # Known G-Sync (native module) monitors
    gsync_native_patterns = [
        "PG279Q", "PG278Q", "PG248Q", "PG258Q",  # ASUS ROG Swift
        "XB271HU", "XB270HU", "XB280HK",  # Acer Predator
        "27GK750F",  # LG
    ]

    for pattern in gsync_ultimate_patterns:
        if pattern in name_upper:
            return True, "gsync_ultimate"

    for pattern in gsync_native_patterns:
        if pattern in name_upper:
            return True, "gsync_native"

    return False, None


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
            "gpu": self.detect_gpu(),
            "cpu": self.detect_cpu(),
            "ram": self.detect_ram(),
            "monitors": self.detect_monitors(),
            "windows_version": self.detect_windows_version(),
        }

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
                    if not (adapter.StateFlags & 0x1):  # DISPLAY_DEVICE_ATTACHED_TO_DESKTOP
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
                    settings = win32api.EnumDisplaySettings(
                        adapter.DeviceName, -1  # ENUM_CURRENT_SETTINGS
                    )

                    legacy_refresh_rate = settings.DisplayFrequency
                    current_width = settings.PelsWidth
                    current_height = settings.PelsHeight

                    # Use CCD API refresh rate if available (more accurate)
                    # CCD source IDs correspond to active display order
                    if active_display_index in ccd_refresh_rates:
                        refresh_rate = ccd_refresh_rates[active_display_index]
                        logger.debug(
                            f"Using CCD refresh rate {refresh_rate} Hz for display {active_display_index} "
                            f"(legacy reported {legacy_refresh_rate} Hz)"
                        )
                    else:
                        refresh_rate = legacy_refresh_rate

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

                    # Method 1: Check if this is a known G-Sync monitor by name
                    is_known_gsync, gsync_type = _is_known_gsync_monitor(monitor_name)
                    if is_known_gsync:
                        vrr_info["vrr_supported"] = True
                        vrr_info["vrr_type"] = gsync_type

                    # Method 2: Try EDID parsing for FreeSync/Adaptive-Sync
                    if not vrr_info.get("vrr_supported") and monitor_id:
                        edid_vrr = _detect_vrr_from_edid(monitor_id)
                        if edid_vrr.get("vrr_supported"):
                            vrr_info.update(edid_vrr)

                    # Method 3: Check NVIDIA registry for G-Sync compatible status
                    if not vrr_info.get("vrr_supported"):
                        gsync_registry = _detect_gsync_from_nvidia_registry()
                        # G-Sync compatible mode enabled system-wide suggests VRR support
                        if gsync_registry.get("gsync_enabled_globally") and max_refresh_rate > 60:
                            vrr_info["vrr_supported"] = True
                            vrr_info["vrr_type"] = "gsync_compatible"

                    # Method 4: Fall back to heuristics
                    if vrr_info.get("vrr_supported") is None:
                        # High refresh rate monitors are typically VRR-capable
                        if max_refresh_rate >= 120:
                            vrr_info["vrr_supported"] = "likely"
                            vrr_info["vrr_type"] = "adaptive_sync"
                        elif max_refresh_rate > 60:
                            vrr_info["vrr_supported"] = "possible"
                        else:
                            vrr_info["vrr_supported"] = "unknown"

                    monitors.append({
                        "name": monitor_name,
                        "adapter": adapter.DeviceString or "Unknown",
                        "resolution": f"{settings.PelsWidth}x{settings.PelsHeight}",
                        "refresh_rate": refresh_rate,
                        "max_refresh_rate": max_refresh_rate if max_refresh_rate > refresh_rate else None,
                        "max_refresh_capability": max_refresh_any_res if max_refresh_any_res > refresh_rate else None,
                        "is_primary": bool(adapter.StateFlags & 0x4),  # DISPLAY_DEVICE_PRIMARY_DEVICE
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

        return monitors

    def detect_windows_version(self) -> dict[str, Any] | None:
        """Detect Windows version information.

        Returns:
            Windows version dict or None if detection fails.
        """
        try:
            import winreg

            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Microsoft\Windows NT\CurrentVersion",
            )

            try:
                display_version = winreg.QueryValueEx(key, "DisplayVersion")[0]
            except FileNotFoundError:
                display_version = "Unknown"

            try:
                build = winreg.QueryValueEx(key, "CurrentBuildNumber")[0]
            except FileNotFoundError:
                build = "Unknown"

            winreg.CloseKey(key)

            return {
                "display_version": display_version,
                "build": build,
            }
        except OSError as e:
            logger.error(f"Windows version detection failed (registry error): {e}")
        except (ValueError, TypeError) as e:
            logger.error(f"Windows version detection failed (parsing error): {e}")

        return None
