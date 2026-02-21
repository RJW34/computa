"""Tests for hardware detection module."""

from __future__ import annotations

import subprocess
from unittest.mock import MagicMock, patch

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

    @patch("abso.core.detector.win32api", create=True)
    def test_detect_monitors_import_error(self, mock_win32api):
        """Test monitor detection handles ImportError gracefully."""
        detector = HardwareDetector()

        with (patch.dict("sys.modules", {"win32api": None}),
              patch("builtins.__import__", side_effect=ImportError)):
            result = detector.detect_monitors()

        # Should return empty list, not raise
        assert isinstance(result, list)


class TestDetectWindowsVersion:
    """Tests for Windows version detection."""

    @patch("abso.core.detector.winreg.OpenKey")
    @patch("abso.core.detector.winreg.QueryValueEx")
    @patch("abso.core.detector.winreg.CloseKey")
    def test_detect_windows_version_success(
        self, mock_close, mock_query, mock_open
    ):
        """Test Windows version detection success."""
        mock_query.side_effect = [
            ("23H2", 1),  # DisplayVersion
            ("22631", 1),  # CurrentBuildNumber
        ]

        detector = HardwareDetector()
        result = detector.detect_windows_version()

        assert result is not None
        assert result["display_version"] == "23H2"
        assert result["build"] == "22631"

    @patch("abso.core.detector.winreg.OpenKey")
    def test_detect_windows_version_registry_error(self, mock_open):
        """Test Windows version detection handles registry errors."""
        mock_open.side_effect = OSError("Access denied")

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
        edid[130] = 10  # DTD offset

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
