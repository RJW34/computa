"""GPU vendor classification and cached machine-level vendor detection.

Profiles express GPU driver intent through the NVIDIA settings map (the
historically first-supported vendor); the AMD handler derives its Radeon
equivalents from that intent, and both handlers self-guard on hardware
presence. This module is the shared vocabulary for the places that need to
*name* the vendor: capability preflight, the setup wizard, and diagnostics.
"""

from __future__ import annotations

import logging
import os
from enum import StrEnum

logger = logging.getLogger(__name__)


class GpuVendor(StrEnum):
    """Primary GPU vendor for optimization routing."""

    NVIDIA = "nvidia"
    AMD = "amd"
    INTEL = "intel"
    UNKNOWN = "unknown"


_NVIDIA_MARKERS = ("nvidia", "geforce", "quadro", "rtx", "gtx")
_AMD_MARKERS = ("amd", "radeon", "firepro")
_INTEL_MARKERS = ("intel", "iris", "uhd graphics", "hd graphics", "arc(tm)")

# Multi-GPU machines (dGPU + iGPU laptops) report several controllers; the
# discrete gaming vendor outranks the integrated one for routing purposes.
_VENDOR_PRIORITY = (GpuVendor.NVIDIA, GpuVendor.AMD, GpuVendor.INTEL)

_cached_vendor: GpuVendor | None = None


def classify_gpu_name(name: str | None) -> GpuVendor:
    """Classify a GPU display name into a vendor bucket."""
    lowered = (name or "").lower()
    if not lowered:
        return GpuVendor.UNKNOWN
    if any(marker in lowered for marker in _NVIDIA_MARKERS):
        return GpuVendor.NVIDIA
    if any(marker in lowered for marker in _AMD_MARKERS):
        return GpuVendor.AMD
    if any(marker in lowered for marker in _INTEL_MARKERS):
        return GpuVendor.INTEL
    return GpuVendor.UNKNOWN


def detect_gpu_vendor(*, refresh: bool = False) -> GpuVendor:
    """Detect this machine's primary GPU vendor (cached after first probe).

    The ``ABSO_GPU_VENDOR`` environment variable overrides detection
    (``nvidia`` / ``amd`` / ``intel`` / ``unknown``) for testing and for
    machines where WMI misreports the topology.
    """
    global _cached_vendor

    override = os.environ.get("ABSO_GPU_VENDOR", "").strip().lower()
    if override:
        try:
            return GpuVendor(override)
        except ValueError:
            logger.warning("Ignoring invalid ABSO_GPU_VENDOR=%r", override)

    if _cached_vendor is not None and not refresh:
        return _cached_vendor

    vendors: set[GpuVendor] = set()
    try:
        import wmi  # type: ignore[import-untyped]

        conn = wmi.WMI()
        for gpu in conn.Win32_VideoController():
            vendor = classify_gpu_name(getattr(gpu, "Name", None))
            if vendor is not GpuVendor.UNKNOWN:
                vendors.add(vendor)
    except Exception as exc:
        logger.debug("WMI GPU vendor probe failed: %s", exc)

    for vendor in _VENDOR_PRIORITY:
        if vendor in vendors:
            _cached_vendor = vendor
            return vendor

    _cached_vendor = GpuVendor.UNKNOWN
    return _cached_vendor
