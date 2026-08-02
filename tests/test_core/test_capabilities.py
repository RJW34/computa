"""Tests for capability graph evaluation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.core import capabilities as cap_mod
from abso.core.capabilities import CapabilityEngine
from abso.core.multimon_detector import DisplayEnvironment, MultiMonitorResult
from abso.profiles.base import DisplayPathRequirements
from abso.utils.os_release import OsRelease


def _make_profile(
    profile_id: str,
    requires_confirmed_vrr_support: bool = False,
    settings_map: dict[str, dict[str, object]] | None = None,
    min_os_build: tuple[int, int] | None = None,
    validated_os_build: tuple[int, int] | None = None,
) -> MagicMock:
    profile = MagicMock()
    profile.profile_id = profile_id
    profile.requires_confirmed_vrr_support = requires_confirmed_vrr_support
    profile.display_path_requirements = DisplayPathRequirements()
    profile.min_os_build = min_os_build
    profile.validated_os_build = validated_os_build
    settings_map = settings_map or {}
    profile.get_settings.side_effect = lambda handler_name: settings_map.get(handler_name, {})
    return profile


def _release(build: int, ubr: int) -> OsRelease:
    return OsRelease(
        product_name="Windows 10 Home",
        display_version="25H2",
        edition_id="Core",
        installation_type="Client",
        build=build,
        ubr=ubr,
    )


def test_min_os_build_blocks_on_older_build() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = []
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("future-profile", min_os_build=(26200, 8457))

    with patch.object(cap_mod, "detect_os_release", return_value=_release(26200, 1234)):
        report = CapabilityEngine(detector).evaluate(profile)

    assert any(f.code == "OS_BUILD_BELOW_FLOOR" for f in report.findings)
    assert report.has_blockers is True


def test_min_os_build_passes_when_at_floor() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "Primary", "vrr_supported": True, "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("future-profile", min_os_build=(26200, 8457))

    with patch.object(cap_mod, "detect_os_release", return_value=_release(26200, 8457)):
        report = CapabilityEngine(detector).evaluate(profile)

    assert not any(f.code == "OS_BUILD_BELOW_FLOOR" for f in report.findings)


def test_validated_os_build_surfaces_info_on_newer_os() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = []
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("legacy-profile", validated_os_build=(26200, 8246))

    with patch.object(cap_mod, "detect_os_release", return_value=_release(26200, 8457)):
        report = CapabilityEngine(detector).evaluate(profile)

    assert any(f.code == "OS_BUILD_UNTESTED_ON_PROFILE" for f in report.findings)
    assert not any(f.severity == "blocker" and f.code == "OS_BUILD_UNTESTED_ON_PROFILE" for f in report.findings)


def _experimental_release(build: int = 29591, ubr: int = 1000) -> OsRelease:
    """OsRelease snapshot above the 29000 experimental-platforms floor."""
    return OsRelease(
        product_name="Windows 10 Home",
        display_version="Dev",
        edition_id="Core",
        installation_type="Client",
        build=build,
        ubr=ubr,
    )


def test_experimental_branch_emits_info_finding_on_29xxx() -> None:
    """Canary 29xxx hosts get an info caveat in profile preflight."""
    detector = MagicMock()
    detector.detect_monitors.return_value = []
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("future-profile")

    with patch.object(cap_mod, "detect_os_release", return_value=_experimental_release()):
        report = CapabilityEngine(detector).evaluate(profile)

    experimental = [f for f in report.findings if f.code == "OS_EXPERIMENTAL_FUTURE_PLATFORMS"]
    assert len(experimental) == 1
    assert experimental[0].severity == "info"
    assert "29591.1000" in experimental[0].message
    assert report.has_blockers is False


def test_experimental_branch_silent_on_25h2_host() -> None:
    """Stable 25H2 hosts do not get the experimental caveat."""
    detector = MagicMock()
    detector.detect_monitors.return_value = []
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("future-profile")

    with patch.object(cap_mod, "detect_os_release", return_value=_release(26200, 8457)):
        report = CapabilityEngine(detector).evaluate(profile)

    assert not any(f.code == "OS_EXPERIMENTAL_FUTURE_PLATFORMS" for f in report.findings)


def test_unreadable_os_release_logs_warning_finding() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = []
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("future-profile", min_os_build=(26200, 8457))

    with patch.object(cap_mod, "detect_os_release", return_value=_release(0, 0)):
        report = CapabilityEngine(detector).evaluate(profile)

    assert any(f.code == "OS_RELEASE_UNAVAILABLE" for f in report.findings)


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


def test_capability_targets_highest_refresh_vrr_display_even_if_not_primary() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {
            "name": "Secondary Office Display",
            "vrr_supported": "possible",
            "is_primary": True,
            "refresh_rate": 60,
        },
        {
            "name": "LG UltraGear",
            "vrr_supported": True,
            "is_primary": False,
            "refresh_rate": 300,
        },
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is False


def test_capability_blocks_vrr_profile_when_target_gaming_display_lacks_confirmed_vrr() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {
            "name": "Office Display",
            "vrr_supported": True,
            "is_primary": True,
            "refresh_rate": 60,
        },
        {
            "name": "LG UltraGear",
            "vrr_supported": "possible",
            "is_primary": False,
            "refresh_rate": 300,
        },
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)

    report = CapabilityEngine(detector).evaluate(profile)

    assert report.has_blockers is True
    assert any(f.code == "VRR_REQUIRED_NOT_CONFIRMED" for f in report.findings)
    assert any("LG UltraGear" in f.message for f in report.findings if f.code == "VRR_REQUIRED_NOT_CONFIRMED")


def test_capability_reports_amd_gpu_path_as_info() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [{"name": "Primary", "vrr_supported": True}]
    detector.detect_gpu.return_value = {"name": "AMD Radeon RX 7900 XTX"}
    profile = _make_profile("rivals2-nosync")

    report = CapabilityEngine(detector).evaluate(profile)

    amd_findings = [f for f in report.findings if f.code == "GPU_AMD_PATH"]
    assert amd_findings
    assert amd_findings[0].severity == "info"
    assert "Radeon tuning" in amd_findings[0].message
    assert not any(f.code == "GPU_NOT_NVIDIA" for f in report.findings)


def test_capability_warns_on_gpu_without_vendor_tuning_path() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [{"name": "Primary", "vrr_supported": True}]
    detector.detect_gpu.return_value = {"name": "Intel Arc(TM) B580 Graphics"}
    profile = _make_profile("rivals2-nosync")

    report = CapabilityEngine(detector).evaluate(profile)

    assert any(f.code == "GPU_NOT_NVIDIA" for f in report.findings)
    assert report.to_dict()["warnings"] >= 1


def test_capability_blocks_overlay_sensitive_profile_when_overlays_are_detected() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {"name": "LG UltraGear", "vrr_supported": True, "is_primary": True}
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("overwatch2-gsync", requires_confirmed_vrr_support=True)
    profile.display_path_requirements = DisplayPathRequirements(require_overlay_free_path=True)
    profile.overlay_compatible_fallback_profile_id = "overwatch2-gsync-capture"
    multimon_result = MultiMonitorResult(
        environment=DisplayEnvironment(
            monitors=[],
            monitor_count=1,
            detected_overlays=["Discord Overlay", "Xbox Game Bar"],
        )
    )

    report = CapabilityEngine(detector).evaluate(profile, multimon_result=multimon_result)

    assert report.has_blockers is True
    finding = next(f for f in report.findings if f.code == "DISPLAY_OVERLAYS_BLOCK_EXCLUSIVE_PROFILE")
    assert "overwatch2-gsync-capture" in finding.message
    assert finding.fallback_profile_id == "overwatch2-gsync-capture"
    assert (
        next(
            item for item in report.to_dict()["findings"]
            if item["code"] == "DISPLAY_OVERLAYS_BLOCK_EXCLUSIVE_PROFILE"
        )["fallback_profile_id"]
        == "overwatch2-gsync-capture"
    )


def test_capability_warns_strict_vrr_on_mixed_refresh_multimon_path() -> None:
    detector = MagicMock()
    detector.detect_monitors.return_value = [
        {
            "name": "LG UltraGear",
            "vrr_supported": True,
            "is_primary": True,
            "refresh_rate": 300,
        }
    ]
    detector.detect_gpu.return_value = {"name": "NVIDIA GeForce RTX 4090"}
    profile = _make_profile("deadlock-gsync-hdr", requires_confirmed_vrr_support=True)
    profile.display_path_requirements = DisplayPathRequirements(require_overlay_free_path=True)
    profile.uses_fullscreen_only_vrr_path = True
    profile.mixed_refresh_safe_fallback_profile_id = "deadlock-hdr"
    multimon_result = MultiMonitorResult(
        environment=DisplayEnvironment(
            monitors=[],
            monitor_count=2,
            has_mixed_refresh=True,
            min_refresh=59.95,
            max_refresh=300.0,
        )
    )

    report = CapabilityEngine(detector).evaluate(profile, multimon_result=multimon_result)

    assert report.has_blockers is False
    finding = next(
        f for f in report.findings
        if f.code == "DISPLAY_PATH_MIXED_REFRESH_BLOCKS_STRICT_VRR"
    )
    assert finding.severity == "warning"
    assert "deadlock-hdr" not in finding.message
    assert finding.fallback_profile_id is None
    assert (
        next(
            item for item in report.to_dict()["findings"]
            if item["code"] == "DISPLAY_PATH_MIXED_REFRESH_BLOCKS_STRICT_VRR"
        )["fallback_profile_id"]
        is None
    )


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

    profile = _make_profile("rivals2-nosync")
    profile.get_settings.side_effect = lambda handler_name: (
        {"refresh_rate": 360} if handler_name == "WindowsSettingsHandler" else {}
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

    profile = _make_profile("rivals2-nosync")
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
