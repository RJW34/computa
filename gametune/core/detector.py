"""Hardware detection module."""

from __future__ import annotations

import logging
import subprocess
import winreg
from dataclasses import dataclass
from typing import Any

from gametune.core.exceptions import (
    GPUDetectionError,
    CPUDetectionError,
    MonitorDetectionError,
    WMIError,
    NvidiaSmiError,
    CommandTimeoutError,
)

logger = logging.getLogger(__name__)


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
    result = {
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
            revision = edid[offset + 1]
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
                    ext_code = edid[db_offset + 1]
                    # Various VRR-related extended tags could be here

                db_offset += length + 1

        # DisplayID extension (0x70) - newer displays may use this
        elif ext_tag == 0x70:
            # DisplayID 2.0+ can contain Adaptive-Sync data
            # Simplified detection - presence suggests modern VRR support
            pass

        offset += 128

    return result


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

        try:
            import win32api

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
                    except Exception:
                        pass

                    # Get current settings
                    settings = win32api.EnumDisplaySettings(
                        adapter.DeviceName, -1  # ENUM_CURRENT_SETTINGS
                    )

                    refresh_rate = settings.DisplayFrequency

                    # Detect VRR/G-Sync capability
                    vrr_info = {"vrr_supported": None, "vrr_type": None}
                    if monitor_id:
                        vrr_info = _detect_vrr_from_edid(monitor_id)

                    # If EDID detection failed, use heuristics
                    if vrr_info.get("vrr_supported") is None:
                        # High refresh rate monitors are typically VRR-capable
                        if refresh_rate > 60:
                            vrr_info["vrr_supported"] = "likely"  # Probable but not confirmed
                        else:
                            vrr_info["vrr_supported"] = "unknown"

                    monitors.append({
                        "name": monitor_name,
                        "adapter": adapter.DeviceString or "Unknown",
                        "resolution": f"{settings.PelsWidth}x{settings.PelsHeight}",
                        "refresh_rate": refresh_rate,
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
                except Exception:
                    break

        except ImportError:
            logger.warning("win32api not available for monitor detection")
        except AttributeError as e:
            logger.error(f"Monitor detection failed (attribute error): {e}")
        except OSError as e:
            logger.error(f"Monitor detection failed (OS error): {e}")

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
