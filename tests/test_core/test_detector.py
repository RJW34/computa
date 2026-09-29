"""Tests for hardware detection module."""

from __future__ import annotations

import subprocess
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

import pytest

from abso.core.detector import HardwareDetector, _parse_edid_for_vrr


class TestHardwareDetectorInit:
    """Tests for HardwareDetector initialization."""

    def test_init_creates_instance(self):
        """Test HardwareDetector can be instantiated."""
        detector = HardwareDetector()
        assert detector is not None
        assert detector._wmi is None  # Lazy-loaded

    def test_wmi_lazy_loaded(self):
        """Test WMI connection is lazy-loaded on first use."""
        detector = HardwareDetector()
        assert detector._wmi is None


class TestDetectAll:
    """Tests for detect_all method."""

    @patch.object(HardwareDetector, "detect_gpu")
    @patch.object(HardwareDetector, "detect_cpu")
    @patch.object(HardwareDetector, "detect_ram")
    @patch.object(HardwareDetector, "detect_monitors")
    @patch.object(HardwareDetector, "detect_windows_version")
    def test_detect_all_returns_dict(
        self, mock_win, mock_mon, mock_ram, mock_cpu, mock_gpu
    ):
        """Test detect_all returns a dictionary with all components."""
        mock_gpu.return_value = {"name": "RTX 4090"}
        mock_cpu.return_value = {"name": "Intel i9"}
        mock_ram.return_value = {"total_gb": 32}
        mock_mon.return_value = [{"name": "Monitor 1"}]
        mock_win.return_value = {"build": "22631"}

        detector = HardwareDetector()
        result = detector.detect_all()

        assert "gpu" in result
        assert "cpu" in result
        assert "ram" in result
        assert "monitors" in result
        assert "windows_version" in result

    @patch.object(HardwareDetector, "detect_gpu")
    @patch.object(HardwareDetector, "detect_cpu")
    @patch.object(HardwareDetector, "detect_ram")
    @patch.object(HardwareDetector, "detect_monitors")
    @patch.object(HardwareDetector, "detect_windows_version")
    def test_detect_all_handles_none_values(
        self, mock_win, mock_mon, mock_ram, mock_cpu, mock_gpu
    ):
        """Test detect_all handles None return values gracefully."""
        mock_gpu.return_value = None
        mock_cpu.return_value = None
        mock_ram.return_value = None
        mock_mon.return_value = []
        mock_win.return_value = None

        detector = HardwareDetector()
        result = detector.detect_all()

        assert result["gpu"] is None
        assert result["cpu"] is None
        assert result["ram"] is None
        assert result["monitors"] == []


class TestDetectGpu:
    """Tests for GPU detection."""

    @patch("abso.core.detector.subprocess.run")
    def test_detect_gpu_nvidia_smi_success(self, mock_run):
        """Test GPU detection with nvidia-smi success."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="NVIDIA GeForce RTX 4090, 546.33, 24564\n"
        )

        detector = HardwareDetector()
        result = detector.detect_gpu()

        assert result is not None
        assert result["name"] == "NVIDIA GeForce RTX 4090"
        assert result["driver_version"] == "546.33"
        assert result["vram_mb"] == 24564

    @patch("abso.core.detector.subprocess.run")
    def test_detect_gpu_nvidia_smi_not_found(self, mock_run):
        """Test GPU detection falls back when nvidia-smi not found."""
        mock_run.side_effect = FileNotFoundError("nvidia-smi not found")

        detector = HardwareDetector()
        # Without WMI mock, this will return None
        with patch.object(detector, "_detect_gpu_wmi", return_value=None):
            result = detector.detect_gpu()

        assert result is None

    @patch("abso.core.detector.subprocess.run")
    def test_detect_gpu_nvidia_smi_timeout(self, mock_run):
        """Test GPU detection handles timeout."""
        mock_run.side_effect = subprocess.TimeoutExpired("nvidia-smi", 5)

        detector = HardwareDetector()
        with patch.object(detector, "_detect_gpu_wmi", return_value=None):
            result = detector.detect_gpu()

        assert result is None

    @patch("abso.core.detector.subprocess.run")
    def test_detect_gpu_nvidia_smi_parse_error(self, mock_run):
        """Test GPU detection handles malformed output."""
        mock_run.return_value = MagicMock(
            returncode=0,
            stdout="malformed output"
        )

        detector = HardwareDetector()
        with patch.object(detector, "_detect_gpu_wmi", return_value=None):
            result = detector.detect_gpu()

        assert result is None

    @patch("abso.core.detector.subprocess.run")
    def test_detect_gpu_fallback_to_wmi(self, mock_run):
        """Test GPU detection falls back to WMI."""
        mock_run.side_effect = FileNotFoundError()

        mock_wmi_gpu = MagicMock()
        mock_wmi_gpu.Name = "AMD Radeon RX 7900"
        mock_wmi_gpu.DriverVersion = "23.12.1"
        mock_wmi_gpu.AdapterRAM = 16 * 1024 * 1024 * 1024  # 16GB

        detector = HardwareDetector()
        detector._wmi = MagicMock()
        detector._wmi.Win32_VideoController.return_value = [mock_wmi_gpu]

        result = detector.detect_gpu()

        assert result is not None
        assert result["name"] == "AMD Radeon RX 7900"


class TestDetectCpu:
    """Tests for CPU detection."""

    def test_detect_cpu_with_mock_wmi(self):
        """Test CPU detection with mocked WMI."""
        mock_cpu = MagicMock()
        mock_cpu.Name = "Intel Core i9-14900K  "  # Note extra spaces
        mock_cpu.NumberOfCores = 24
        mock_cpu.NumberOfLogicalProcessors = 32
        mock_cpu.MaxClockSpeed = 6000

        detector = HardwareDetector()
        detector._wmi = MagicMock()
        detector._wmi.Win32_Processor.return_value = [mock_cpu]

        result = detector.detect_cpu()

        assert result is not None
        assert result["name"] == "Intel Core i9-14900K"  # Stripped
        assert result["cores"] == 24
        assert result["threads"] == 32
        assert result["max_clock_mhz"] == 6000

    def test_detect_cpu_no_wmi(self):
        """Test CPU detection when WMI is unavailable."""
        detector = HardwareDetector()
        detector._wmi = None

        with patch.object(detector, "_get_wmi", return_value=None):
            result = detector.detect_cpu()

        assert result is None


class TestDetectRam:
    """Tests for RAM detection."""

    def test_detect_ram_with_mock_wmi(self):
        """Test RAM detection with mocked WMI."""
        mock_mem1 = MagicMock()
        mock_mem1.Capacity = 17179869184  # 16GB
        mock_mem2 = MagicMock()
        mock_mem2.Capacity = 17179869184  # 16GB

        detector = HardwareDetector()
        detector._wmi = MagicMock()
        detector._wmi.Win32_PhysicalMemory.return_value = [mock_mem1, mock_mem2]

        result = detector.detect_ram()

        assert result is not None
        assert result["total_gb"] == 32.0

    def test_detect_ram_no_wmi(self):
        """Test RAM detection when WMI is unavailable."""
        detector = HardwareDetector()

        with patch.object(detector, "_get_wmi", return_value=None):
            result = detector.detect_ram()

        assert result is None


class TestDetectMonitors:
    """Tests for monitor detection."""

    @pytest.mark.parametrize("backend", ["pywin32", "ctypes"])
    @pytest.mark.parametrize("endless_modes", [False, True])
    def test_late_native_modes_set_maximum_and_enumeration_remains_bounded(
        self, backend, endless_modes
    ):
        enumerated = []

        def mode_values(index):
            if index == -1:
                return 2560, 1440, 60
            enumerated.append(index)
            if index >= 617 and not endless_modes:
                return None
            if index in (615, 616):
                return 2560, 1440, 60 if index == 615 else 300
            return 640, 480, 480

        def device_values(device, index):
            if device is not None:
                return {"DeviceName": "TestMonitor", "DeviceString": "Test Monitor", "DeviceID": ""}
            if index == 0:
                return {"DeviceName": r"\\.\DISPLAY1", "DeviceString": "Test GPU", "StateFlags": 5}
            return None

        fake_win32 = MagicMock()

        def enum_device(device, index):
            values = device_values(device, index)
            if values is None:
                raise OSError("No more devices")
            return SimpleNamespace(**values)

        def enum_mode(device, index):
            values = mode_values(index)
            if values is None:
                raise OSError("No more modes")
            width, height, refresh = values
            return SimpleNamespace(PelsWidth=width, PelsHeight=height, DisplayFrequency=refresh)

        fake_win32.EnumDisplayDevices.side_effect = enum_device
        fake_win32.EnumDisplaySettings.side_effect = enum_mode
        fake_user32 = MagicMock()

        def enum_device_w(device, index, pointer, flags):
            values = device_values(device, index)
            if values is None:
                return False
            for key, value in values.items():
                setattr(pointer._obj, key, value)
            return True

        def enum_mode_w(device, index, pointer):
            values = mode_values(index)
            if values is None:
                return False
            mode = pointer._obj
            mode.dmPelsWidth, mode.dmPelsHeight, mode.dmDisplayFrequency = values
            return True

        fake_user32.EnumDisplayDevicesW.side_effect = enum_device_w
        fake_user32.EnumDisplaySettingsW.side_effect = enum_mode_w
        detector = HardwareDetector()
        with (
            patch.dict("sys.modules", {
                "win32api": fake_win32,
                "pywintypes": SimpleNamespace(error=OSError),
            }),
            patch("abso.core.detector.ctypes.windll.user32", fake_user32),
            patch("abso.core.detector._get_refresh_rates_ccd", return_value={}),
            patch("abso.core.detector._detect_gsync_from_nvidia_registry", return_value={}),
            patch("abso.core.detector._promote_vrr_via_amd_driver"),
            patch.object(detector, "_derive_vrr_info", return_value={}),
        ):
            monitors = (
                detector.detect_monitors()
                if backend == "pywin32"
                else detector._detect_monitors_without_pywin32({})
            )

        assert len(monitors) == 1
        assert monitors[0]["device_name"] == r"\\.\DISPLAY1"
        assert monitors[0]["refresh_rate"] == 60
        assert monitors[0]["max_refresh_rate"] == 300
        assert monitors[0]["max_refresh_capability"] == 480
        assert enumerated == list(range(4096 if endless_modes else 618))
        fake_user32.ChangeDisplaySettingsW.assert_not_called()
        fake_win32.ChangeDisplaySettings.assert_not_called()

    @patch.object(HardwareDetector, "_detect_monitors_without_pywin32")
    def test_detect_monitors_import_error_uses_fallback(self, mock_fallback):
        """Test monitor detection uses fallback when pywin32 is unavailable."""
        mock_fallback.return_value = [{"name": "Fallback Monitor", "vrr_supported": "unknown"}]
        detector = HardwareDetector()

        with patch.dict("sys.modules", {"win32api": None, "pywintypes": None}):
            result = detector.detect_monitors()

        assert result == mock_fallback.return_value
        mock_fallback.assert_called_once()


class TestDetectWindowsVersion:
    """Tests for Windows version detection."""

    def test_detect_windows_version_success(self):
        """Test Windows version detection delegates to OsRelease cleanly."""
        from abso.utils.os_release import OsRelease

        with patch(
            "abso.core.detector.detect_os_release",
            return_value=OsRelease(
                product_name="Windows 10 Pro",
                display_version="23H2",
                edition_id="Professional",
                installation_type="Client",
                build=22631,
                ubr=4317,
            ),
        ):
            detector = HardwareDetector()
            result = detector.detect_windows_version()

        assert result is not None
        assert result["display_version"] == "23H2"
        assert result["build"] == "22631"
        assert result["ubr"] == 4317
        assert result["build_revision"] == "22631.4317"
        assert result["edition_id"] == "Professional"

    def test_detect_windows_version_returns_none_when_unreadable(self):
        """Zeroed OsRelease means registry was unreachable; surface None."""
        from abso.utils.os_release import OsRelease

        with patch(
            "abso.core.detector.detect_os_release",
            return_value=OsRelease("", "", "", "", 0, 0),
        ):
            detector = HardwareDetector()
            result = detector.detect_windows_version()

        assert result is None


class TestParseEdidForVrr:
    """Tests for EDID VRR parsing."""

    def test_parse_edid_too_short(self):
        """Test EDID parsing with data too short."""
        result = _parse_edid_for_vrr(b"\x00" * 64)

        assert result["vrr_supported"] is False
        assert result["vrr_type"] is None

    def test_parse_edid_no_extensions(self):
        """Test EDID parsing with no extensions."""
        edid = b"\x00" * 126 + b"\x00" + b"\x00"  # 128 bytes, 0 extensions

        result = _parse_edid_for_vrr(edid)

        assert result["vrr_supported"] is False

    def test_parse_edid_valid_freesync(self):
        """Test EDID parsing with FreeSync data block."""
        # Create a minimal EDID with CTA-861 extension containing FreeSync OUI
        edid = bytearray(256)
        edid[126] = 1  # 1 extension block

        # CTA-861 extension at offset 128
        edid[128] = 0x02  # Extension tag
        edid[129] = 0x03  # Revision
        edid[130] = 11  # Header + six payload bytes end immediately before DTDs.

        # Vendor-specific data block at offset 132
        # Header: tag=3 (VSDB), length=6
        edid[132] = (3 << 5) | 6  # 0x66

        # AMD FreeSync OUI (00-1A-00)
        edid[133] = 0x00
        edid[134] = 0x1A
        edid[135] = 0x00

        # Padding
        edid[136] = 0x00
        edid[137] = 48  # min Hz
        edid[138] = 144  # max Hz

        result = _parse_edid_for_vrr(bytes(edid))

        assert result["vrr_supported"] == "hardware"
        assert result["vrr_type"] == "freesync"
        assert result["vrr_min_hz"] == 48
        assert result["vrr_max_hz"] == 144

    def test_parse_edid_freesync_v3_uses_extended_300_hz_maximum(self):
        """The active LG block has a legacy 240Hz field but advertises 300Hz.

        Retain the actual captured block; the previous test incorrectly
        asserted 240 and assigned an unverified retail model to this EDID.
        """
        edid = bytearray(256)
        edid[126] = 1  # 1 extension block

        # CTA-861 extension at offset 128
        edid[128] = 0x02
        edid[129] = 0x03
        block = bytes.fromhex("1a0000030130f00000000000002c010000000000")
        edid[130] = 4 + 1 + len(block)  # DTDs start after the data block

        # Vendor-specific data block: tag=3, length=20
        edid[132] = (3 << 5) | len(block)
        edid[133 : 133 + len(block)] = block

        result = _parse_edid_for_vrr(bytes(edid))

        assert result["vrr_supported"] == "hardware"
        assert result["vrr_type"] == "freesync"
        assert result["vrr_min_hz"] == 48
        assert result["vrr_max_hz"] == 300

    @staticmethod
    def _edid_with_block(block, *, dtd_offset=None, block_offset=4):
        edid = bytearray(256)
        edid[126] = 1
        edid[128:132] = bytes([2, 3, dtd_offset or block_offset + 1 + len(block), 0])
        edid[128 + block_offset] = (3 << 5) | len(block)
        edid[129 + block_offset:129 + block_offset + len(block)] = block
        return bytes(edid)

    @pytest.mark.parametrize("oui", [b"\x00\x1a\x00", b"\x1a\x00\x00"])
    def test_legacy_v2_range_unchanged(self, oui):
        block = oui + bytes([2, 1, 48, 240, 0, 0, 0])
        result = _parse_edid_for_vrr(self._edid_with_block(block))
        assert (result["vrr_min_hz"], result["vrr_max_hz"]) == (48, 240)

    @pytest.mark.parametrize("maximum, upper_flags", [(255, 0), (256, 0), (1023, 0xFC), (300, 0xFC)])
    def test_v3_extended_maximum_uses_only_ten_bits(self, maximum, upper_flags):
        block = bytearray.fromhex("1a0000030130f00000000000002c0100")
        block[13], block[14] = maximum & 0xFF, (maximum >> 8) | upper_flags
        result = _parse_edid_for_vrr(self._edid_with_block(block))
        assert (result["vrr_min_hz"], result["vrr_max_hz"]) == (48, maximum)

    @pytest.mark.parametrize("length", [15, 20, 21])
    @pytest.mark.parametrize("maximum", [1024, 4095])
    def test_v3_optional_twelve_bit_maximum_obeys_payload_length(self, length, maximum):
        block = bytearray.fromhex("1a0000030130f00000000000002c01000000000000")
        block[13], block[14] = maximum & 0xFF, ((maximum >> 8) & 3) | 0xFC
        block[20] = (maximum >> 10) | 0xFC
        edid = bytearray(self._edid_with_block(block[:length]))
        # A following DTD/checksum byte must not count as the optional field.
        edid[153] = block[20]
        result = _parse_edid_for_vrr(bytes(edid))
        expected = maximum if length == 21 else maximum & 0x3FF
        assert result["vrr_max_hz"] == (expected if expected > 48 else None)

    @pytest.mark.parametrize("length", [3, 4, 6, 7, 13, 14])
    def test_truncated_v3_does_not_read_following_bytes_or_report_legacy_max(self, length):
        block = bytes.fromhex("1a0000030130f00000000000002c0100")[:length]
        edid = bytearray(self._edid_with_block(block))
        # Bytes outside the declared payload must not complete the v3 maximum.
        edid[133 + length:149] = b"\xff" * (16 - length)
        result = _parse_edid_for_vrr(bytes(edid))
        assert result["vrr_supported"] == "hardware"
        assert result["vrr_min_hz"] is None
        assert result["vrr_max_hz"] is None

    @pytest.mark.parametrize("minimum, maximum", [(0, 300), (48, 0), (48, 48), (48, 30)])
    def test_invalid_v3_range_stays_unknown(self, minimum, maximum):
        block = bytearray.fromhex("1a0000030130f00000000000002c0100")
        block[5], block[13], block[14] = minimum, maximum & 0xFF, maximum >> 8
        result = _parse_edid_for_vrr(self._edid_with_block(block))
        assert result["vrr_supported"] == "hardware"
        assert result["vrr_min_hz"] is None
        assert result["vrr_max_hz"] is None

    @pytest.mark.parametrize("dtd_offset, block_offset", [(10, 4), (127, 114), (128, 4), (255, 4)])
    def test_malformed_cta_boundaries_do_not_supply_a_vrr_block(self, dtd_offset, block_offset):
        block = bytes.fromhex("1a0000030130f00000000000002c0100")
        result = _parse_edid_for_vrr(self._edid_with_block(
            block, dtd_offset=dtd_offset, block_offset=block_offset,
        ))
        assert result["vrr_supported"] is False
        assert result["vrr_max_hz"] is None

    def test_truncated_extension_is_not_read(self):
        block = bytes.fromhex("1a0000030130f00000000000002c0100")
        assert _parse_edid_for_vrr(self._edid_with_block(block)[:-1])["vrr_supported"] is False


class TestExceptionHandling:
    """Tests for exception handling in detection methods."""

    def test_detector_doesnt_crash_on_wmi_error(self):
        """Test detector gracefully handles WMI errors."""
        detector = HardwareDetector()
        detector._wmi = MagicMock()
        detector._wmi.Win32_Processor.side_effect = RuntimeError("WMI error")

        result = detector.detect_cpu()

        assert result is None

    @patch("abso.core.detector.subprocess.run")
    def test_detector_handles_subprocess_error(self, mock_run):
        """Test detector handles subprocess errors gracefully."""
        mock_run.side_effect = subprocess.SubprocessError("Failed to execute")

        detector = HardwareDetector()
        with patch.object(detector, "_detect_gpu_wmi", return_value=None):
            result = detector.detect_gpu()

        assert result is None
