"""Tests for capability graph evaluation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core.capabilities import CapabilityEngine


def _make_profile(
    profile_id: str,
    requires_confirmed_vrr_support: bool = False,
    settings_map: dict[str, dict[str, object]] | None = None,
) -> MagicMock:
    profile = MagicMock()
    profile.profile_id = profile_id
    profile.requires_confirmed_vrr_support = requires_confirmed_vrr_support
    settings_map = settings_map or {}
    profile.get_settings.side_effect = lambda handler_name: settings_map.get(handler_name, {})
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


def test_capability_accepts_vrr_hardware_status() -> None:
    """EDID reports hardware VRR — accepted as 'likely' since commit 611a5bd."""
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "DELL S2722DGM", "vrr_supported": "hardware", "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is False
    assert any(f.code == "VRR_LIKELY_ACCEPTED" for f in report.findings)


def test_capability_blocks_vrr_profile_when_vrr_only_possible() -> None:
    """VRR 'possible' (not confirmed or likely) should still block."""
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "Generic Monitor", "vrr_supported": "possible", "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is True
    assert any(f.code == "VRR_REQUIRED_NOT_CONFIRMED" for f in report.findings)


def test_capability_warns_on_non_nvidia_gpu() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [{"name": "Primary", "vrr_supported": True}]
    detector.detect_gpu.return_value = {"name": "AMD Radeon RX 7900 XTX"}
    profile = _make_profile("rivals2")

    report = CapabilityEngine(detector).evaluate(profile)

    assert any(f.code == "GPU_NOT_NVIDIA" for f in report.findings)
    assert report.to_dict()["warnings"] >= 1


def test_capability_blocks_fixed_refresh_when_monitor_cannot_support_it() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {
            "name": "Primary",
            "is_primary": True,
            "refresh_rate": 240,
            "max_refresh_rate": 240,
            "max_refresh_capability": 240,
        }
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}

    profile = _make_profile("rivals2-300hz-max")
    profile.get_settings.side_effect = lambda handler_name: (
        {"refresh_rate": 300} if handler_name == "WindowsSettingsHandler" else {}
    )

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is True
    assert any(f.code == "REFRESH_TARGET_UNSUPPORTED" for f in report.findings)


def test_capability_allows_fixed_refresh_when_supported() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {
            "name": "Primary",
            "is_primary": True,
            "refresh_rate": 240,
            "max_refresh_rate": 240,
            "max_refresh_capability": 360,
        }
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}

    profile = _make_profile("rivals2-tournament-sim")
    profile.get_settings.side_effect = lambda handler_name: (
        {"refresh_rate": 144} if handler_name == "WindowsSettingsHandler" else {}
    )

    report = CapabilityEngine(detector).evaluate(profile)

    assert not any(f.code == "REFRESH_TARGET_UNSUPPORTED" for f in report.findings)


@patch("abso.core.capabilities.WindowsSettingsHandler.detect")
def test_capability_blocks_hdr_profile_when_no_hdr_capable_display(mock_detect) -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "Primary", "vrr_supported": True, "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    mock_detect.return_value = {
        "hdr_capable_count": 0,
        "hdr_enabled_count": 0,
    }
    profile = _make_profile(
        "overwatch2-gsync-hdr",
        requires_confirmed_vrr_support=True,
        settings_map={"WindowsSettingsHandler": {"hdr": True, "auto_hdr": False}},
    )

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is True
    assert any(f.code == "HDR_REQUIRED_NO_CAPABLE_DISPLAY" for f in report.findings)


@patch("abso.core.capabilities.WindowsSettingsHandler.detect")
def test_capability_blocks_hdr_profile_when_hdr_capability_cannot_be_verified(mock_detect) -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "Primary", "vrr_supported": True, "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    mock_detect.return_value = {
        "hdr_capable_count": None,
        "hdr_enabled_count": None,
    }
    profile = _make_profile(
        "overwatch2-gsync-hdr",
        requires_confirmed_vrr_support=True,
        settings_map={"WindowsSettingsHandler": {"hdr": True, "auto_hdr": False}},
    )

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is True
    assert any(f.code == "HDR_REQUIRED_UNVERIFIED" for f in report.findings)


@patch("abso.core.capabilities.WindowsSettingsHandler.detect")
def test_capability_allows_hdr_profile_with_confirmed_hdr_capable_display(mock_detect) -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "Primary", "vrr_supported": True, "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    mock_detect.return_value = {
        "hdr_capable_count": 1,
        "hdr_enabled_count": 0,
    }
    profile = _make_profile(
        "overwatch2-gsync-hdr",
        requires_confirmed_vrr_support=True,
        settings_map={"WindowsSettingsHandler": {"hdr": True, "auto_hdr": False}},
    )

    report = CapabilityEngine(detector).evaluate(profile)

    assert not any(
        f.code in {"HDR_REQUIRED_NO_CAPABLE_DISPLAY", "HDR_REQUIRED_UNVERIFIED"}
        for f in report.findings
    )
