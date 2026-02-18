"""Tests for capability graph evaluation."""

from __future__ import annotations

from unittest.mock import MagicMock

from abso.core.capabilities import CapabilityEngine


def _make_profile(profile_id: str, requires_confirmed_vrr_support: bool = False) -> MagicMock:
    profile = MagicMock()
    profile.profile_id = profile_id
    profile.requires_confirmed_vrr_support = requires_confirmed_vrr_support
    return profile


def test_capability_blocks_vrr_profile_when_no_monitor_data() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = []
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is True
    assert any(f.code == "VRR_REQUIRED_NO_MONITOR_DATA" for f in report.findings)


def test_capability_allows_vrr_profile_with_confirmed_monitor() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "Primary", "vrr_supported": True, "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is False


def test_capability_warns_on_non_nvidia_gpu() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [{"name": "Primary", "vrr_supported": True}]
    detector.detect_gpu.return_value = {"name": "AMD Radeon RX 7900 XTX"}
    profile = _make_profile("rivals2")

    report = CapabilityEngine(detector).evaluate(profile)

    assert any(f.code == "GPU_NOT_NVIDIA" for f in report.findings)
    assert report.to_dict()["warnings"] >= 1
