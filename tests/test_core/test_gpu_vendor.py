"""Tests for GPU vendor classification and detection routing."""

from __future__ import annotations

import pytest

from abso.core import gpu_vendor
from abso.core.gpu_vendor import GpuVendor, classify_gpu_name, detect_gpu_vendor


@pytest.fixture(autouse=True)
def _reset_vendor_cache(monkeypatch):
    monkeypatch.setattr(gpu_vendor, "_cached_vendor", None)
    monkeypatch.delenv("ABSO_GPU_VENDOR", raising=False)


@pytest.mark.parametrize(
    ("name", "expected"),
    [
        ("NVIDIA GeForce RTX 4070", GpuVendor.NVIDIA),
        ("NVIDIA GeForce GTX 1080 Ti", GpuVendor.NVIDIA),
        ("Quadro P2000", GpuVendor.NVIDIA),
        ("AMD Radeon RX 7900 XTX", GpuVendor.AMD),
        ("Radeon RX 6700 XT", GpuVendor.AMD),
        ("Intel(R) UHD Graphics 770", GpuVendor.INTEL),
        ("Intel(R) Iris(R) Xe Graphics", GpuVendor.INTEL),
        ("Intel(R) Arc(TM) B580 Graphics", GpuVendor.INTEL),
        ("Microsoft Basic Display Adapter", GpuVendor.UNKNOWN),
        ("", GpuVendor.UNKNOWN),
        (None, GpuVendor.UNKNOWN),
    ],
)
def test_classify_gpu_name(name, expected) -> None:
    assert classify_gpu_name(name) is expected


def test_detect_gpu_vendor_env_override_wins(monkeypatch) -> None:
    monkeypatch.setenv("ABSO_GPU_VENDOR", "amd")
    assert detect_gpu_vendor() is GpuVendor.AMD


def test_detect_gpu_vendor_invalid_override_falls_through(monkeypatch) -> None:
    monkeypatch.setenv("ABSO_GPU_VENDOR", "voodoo3")
    monkeypatch.setattr(gpu_vendor, "_cached_vendor", GpuVendor.NVIDIA)
    assert detect_gpu_vendor() is GpuVendor.NVIDIA


def test_detect_gpu_vendor_prefers_discrete_over_integrated(monkeypatch) -> None:
    """A dGPU + iGPU laptop should route by the discrete gaming vendor."""

    class _Gpu:
        def __init__(self, name: str) -> None:
            self.Name = name

    class _Conn:
        def Win32_VideoController(self):
            return [_Gpu("Intel(R) UHD Graphics 770"), _Gpu("AMD Radeon RX 7800 XT")]

    class _WmiModule:
        @staticmethod
        def WMI():
            return _Conn()

    monkeypatch.setitem(__import__("sys").modules, "wmi", _WmiModule())
    assert detect_gpu_vendor(refresh=True) is GpuVendor.AMD


def test_detect_gpu_vendor_unknown_when_probe_fails(monkeypatch) -> None:
    class _BrokenWmiModule:
        @staticmethod
        def WMI():
            raise RuntimeError("no WMI service")

    monkeypatch.setitem(__import__("sys").modules, "wmi", _BrokenWmiModule())
    assert detect_gpu_vendor(refresh=True) is GpuVendor.UNKNOWN
