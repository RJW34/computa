"""Tests for abso.utils.os_release."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.utils import os_release
from abso.utils.os_release import (
    OsRelease,
    detect_os_release,
    invalidate_cache,
)


def _mock_values(values: dict[str, object]) -> MagicMock:
    """Build a mocked registry key whose QueryValueEx serves the dict."""
    fake_key = MagicMock()

    def _query(key, name):  # signature mirrors winreg.QueryValueEx
        if name in values:
            return (values[name], 1)
        raise FileNotFoundError(name)

    return fake_key, _query


class TestOsRelease:
    def test_build_revision_tuple(self) -> None:
        rel = OsRelease(
            product_name="Windows 10 Home",
            display_version="25H2",
            edition_id="Core",
            installation_type="Client",
            build=26200,
            ubr=8457,
        )
        assert rel.build_revision == (26200, 8457)

    def test_at_least_compares_build_then_ubr(self) -> None:
        rel = OsRelease("", "25H2", "Core", "Client", 26200, 8457)
        assert rel.at_least(26200, 8457) is True
        assert rel.at_least(26200, 8458) is False
        assert rel.at_least(26100, 9999) is True
        assert rel.at_least(26201, 0) is False

    def test_is_windows_11_flag(self) -> None:
        win10 = OsRelease("Windows 10 Pro", "22H2", "Professional", "Client", 19045, 4046)
        win11 = OsRelease("Windows 10 Home", "25H2", "Core", "Client", 26200, 8457)
        assert win10.is_windows_11 is False
        assert win11.is_windows_11 is True
        assert win11.is_25h2_or_newer is True

    def test_to_dict_includes_build_revision_string(self) -> None:
        rel = OsRelease("Windows 10 Home", "25H2", "Core", "Client", 26200, 8457)
        d = rel.to_dict()
        assert d["build_revision"] == "26200.8457"
        assert d["display_version"] == "25H2"


class TestDetectOsRelease:
    def setup_method(self) -> None:
        invalidate_cache()

    def teardown_method(self) -> None:
        invalidate_cache()

    def test_reads_full_release_from_registry(self) -> None:
        fake_key, query = _mock_values(
            {
                "ProductName": "Windows 10 Home",
                "DisplayVersion": "25H2",
                "EditionID": "Core",
                "InstallationType": "Client",
                "CurrentBuildNumber": "26200",
                "UBR": 8457,
            }
        )
        with (
            patch.object(os_release.winreg, "OpenKey", return_value=fake_key),
            patch.object(os_release.winreg, "QueryValueEx", side_effect=query),
            patch.object(os_release.winreg, "CloseKey"),
        ):
            rel = detect_os_release(cached=False)
        assert rel.build == 26200
        assert rel.ubr == 8457
        assert rel.display_version == "25H2"
        assert rel.edition_id == "Core"
        assert rel.is_25h2_or_newer is True

    def test_missing_ubr_defaults_to_zero(self) -> None:
        fake_key, query = _mock_values(
            {
                "ProductName": "Windows 10 Home",
                "DisplayVersion": "24H2",
                "EditionID": "Core",
                "InstallationType": "Client",
                "CurrentBuildNumber": "26100",
            }
        )
        with (
            patch.object(os_release.winreg, "OpenKey", return_value=fake_key),
            patch.object(os_release.winreg, "QueryValueEx", side_effect=query),
            patch.object(os_release.winreg, "CloseKey"),
        ):
            rel = detect_os_release(cached=False)
        assert rel.build == 26100
        assert rel.ubr == 0
        assert rel.at_least(26200, 0) is False

    def test_unreadable_registry_returns_zeroed_release(self) -> None:
        with patch.object(os_release.winreg, "OpenKey", side_effect=OSError("denied")):
            rel = detect_os_release(cached=False)
        assert rel.build == 0
        assert rel.ubr == 0
        assert rel.is_25h2_or_newer is False

    def test_cache_round_trip(self) -> None:
        fake_key, query = _mock_values(
            {
                "ProductName": "Windows 10 Home",
                "DisplayVersion": "25H2",
                "EditionID": "Core",
                "InstallationType": "Client",
                "CurrentBuildNumber": "26200",
                "UBR": 8457,
            }
        )
        with (
            patch.object(os_release.winreg, "OpenKey", return_value=fake_key) as open_mock,
            patch.object(os_release.winreg, "QueryValueEx", side_effect=query),
            patch.object(os_release.winreg, "CloseKey"),
        ):
            first = detect_os_release(cached=False)
            second = detect_os_release(cached=True)
            assert first is second
            assert open_mock.call_count == 1

            invalidate_cache()
            third = detect_os_release(cached=True)
            assert third == first
            assert open_mock.call_count == 2
