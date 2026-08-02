"""Tests for the bulk SCM service query utility."""

from __future__ import annotations

import sys
import types
from unittest.mock import patch

from abso.utils import win_services


class _FakePywintypesError(Exception):
    def __init__(self, winerror: int, message: str = "fake") -> None:
        super().__init__(message)
        self.winerror = winerror


def _install_fake_scm(monkeypatch, services: dict[str, dict], open_errors: dict[str, int]):
    """Install fake win32service/pywintypes modules into sys.modules.

    Args:
        services: name -> {"state": int, "start_type": int}
        open_errors: name -> winerror raised by OpenService
    """
    fake_pywintypes = types.ModuleType("pywintypes")
    fake_pywintypes.error = _FakePywintypesError

    fake = types.ModuleType("win32service")
    fake.SC_MANAGER_CONNECT = 0x0001
    fake.SERVICE_QUERY_STATUS = 0x0004
    fake.SERVICE_QUERY_CONFIG = 0x0001

    def OpenSCManager(machine, database, access):
        return "scm-handle"

    def OpenService(scm, name, access):
        if name in open_errors:
            raise _FakePywintypesError(open_errors[name])
        if name not in services:
            raise _FakePywintypesError(1060)
        return f"svc-{name}"

    def QueryServiceStatus(handle):
        name = handle.removeprefix("svc-")
        return (16, services[name]["state"], 0, 0, 0, 0, 0)

    def QueryServiceConfig(handle):
        name = handle.removeprefix("svc-")
        return (16, services[name]["start_type"], 0, "", "", 0, "", "", "")

    def CloseServiceHandle(handle):
        return None

    fake.OpenSCManager = OpenSCManager
    fake.OpenService = OpenService
    fake.QueryServiceStatus = QueryServiceStatus
    fake.QueryServiceConfig = QueryServiceConfig
    fake.CloseServiceHandle = CloseServiceHandle

    monkeypatch.setitem(sys.modules, "win32service", fake)
    monkeypatch.setitem(sys.modules, "pywintypes", fake_pywintypes)


class TestQueryServices:
    def test_maps_states_and_start_types(self, monkeypatch):
        _install_fake_scm(
            monkeypatch,
            services={
                "SysMain": {"state": 4, "start_type": 2},  # running, auto
                "DiagTrack": {"state": 1, "start_type": 4},  # stopped, disabled
            },
            open_errors={},
        )

        result = win_services.query_services(["SysMain", "DiagTrack"])

        assert result == {
            "SysMain": {"exists": True, "start_type": 2, "state": "running"},
            "DiagTrack": {"exists": True, "start_type": 4, "state": "stopped"},
        }

    def test_missing_service_is_definitive(self, monkeypatch):
        """Error 1060 (does not exist) is a definitive answer, not a fallback."""
        _install_fake_scm(monkeypatch, services={}, open_errors={})

        result = win_services.query_services(["NoSuchService"])

        assert result == {
            "NoSuchService": {"exists": False, "start_type": None, "state": None}
        }

    def test_access_denied_defers_to_fallback(self, monkeypatch):
        """Non-1060 open errors return None for that name (caller falls back)."""
        _install_fake_scm(
            monkeypatch,
            services={"SysMain": {"state": 4, "start_type": 2}},
            open_errors={"Locked": 5},  # ERROR_ACCESS_DENIED
        )

        result = win_services.query_services(["SysMain", "Locked"])

        assert result["SysMain"]["exists"] is True
        assert result["Locked"] is None

    def test_boot_start_type_reads_as_none(self, monkeypatch):
        """Boot/system driver start types map to None, matching the sc parser."""
        _install_fake_scm(
            monkeypatch,
            services={"BootDriver": {"state": 4, "start_type": 0}},
            open_errors={},
        )

        result = win_services.query_services(["BootDriver"])

        assert result["BootDriver"] == {
            "exists": True,
            "start_type": None,
            "state": "running",
        }

    def test_transitional_state_reads_as_none(self, monkeypatch):
        """States other than running/stopped (e.g. start-pending) map to None."""
        _install_fake_scm(
            monkeypatch,
            services={"Pending": {"state": 2, "start_type": 3}},  # START_PENDING
            open_errors={},
        )

        result = win_services.query_services(["Pending"])

        assert result["Pending"]["state"] is None
        assert result["Pending"]["start_type"] == 3

    def test_scm_unavailable_returns_none(self, monkeypatch):
        """A dead SCM connection returns None so callers fall back entirely."""
        fake_pywintypes = types.ModuleType("pywintypes")
        fake_pywintypes.error = _FakePywintypesError
        fake = types.ModuleType("win32service")
        fake.SC_MANAGER_CONNECT = 0x0001
        fake.SERVICE_QUERY_STATUS = 0x0004
        fake.SERVICE_QUERY_CONFIG = 0x0001

        def OpenSCManager(machine, database, access):
            raise _FakePywintypesError(5)

        fake.OpenSCManager = OpenSCManager
        monkeypatch.setitem(sys.modules, "win32service", fake)
        monkeypatch.setitem(sys.modules, "pywintypes", fake_pywintypes)

        assert win_services.query_services(["SysMain"]) is None

    def test_import_error_returns_none(self):
        """Missing pywin32 returns None (sc fallback), never raises."""
        with patch.dict(sys.modules, {"win32service": None, "pywintypes": None}):
            assert win_services.query_services(["SysMain"]) is None
