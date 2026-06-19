"""Hermetic tests for HypervisorAuditHandler (audit-only, subprocess mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from abso.settings.hypervisor import HypervisorAuditHandler


def _proc(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestDetect:
    @patch.object(HypervisorAuditHandler, "_run")
    def test_parses_launch_type_and_vbs(self, mock_run):
        def side_effect(cmd):
            if cmd[0] == "bcdedit":
                return _proc(stdout="hypervisorlaunchtype     Auto\n")
            return _proc(stdout="2\n")  # VBS running

        mock_run.side_effect = side_effect
        result = HypervisorAuditHandler().detect()
        assert result["hypervisor_launch_type"] == "Auto"
        assert result["vbs_running"] is True

    @patch.object(HypervisorAuditHandler, "_run", return_value=_proc(returncode=1))
    def test_unreadable_returns_none(self, _mock):
        result = HypervisorAuditHandler().detect()
        assert result["hypervisor_launch_type"] is None
        assert result["vbs_running"] is None


class TestAudit:
    @patch.object(HypervisorAuditHandler, "detect", return_value={
        "hypervisor_launch_type": "Auto",
        "vbs_running": False,
    })
    def test_flags_idle_hypervisor(self, _detect):
        issues = HypervisorAuditHandler().audit()
        assert any("root partition" in i.title.lower() for i in issues)

    @patch.object(HypervisorAuditHandler, "detect", return_value={
        "hypervisor_launch_type": "Auto",
        "vbs_running": True,
    })
    def test_silent_when_vbs_running(self, _detect):
        # VBS is using the hypervisor, so it is not idle overhead.
        assert HypervisorAuditHandler().audit() == []

    @patch.object(HypervisorAuditHandler, "detect", return_value={
        "hypervisor_launch_type": "Off",
        "vbs_running": False,
    })
    def test_silent_when_hypervisor_off(self, _detect):
        assert HypervisorAuditHandler().audit() == []

    @patch.object(HypervisorAuditHandler, "detect", return_value={
        "hypervisor_launch_type": None,
        "vbs_running": None,
    })
    def test_silent_when_unknown(self, _detect):
        assert HypervisorAuditHandler().audit() == []


class TestContract:
    def test_apply_is_audit_only(self):
        result = HypervisorAuditHandler().apply({})
        assert result["success"] is False
        assert "audit-only" in result["error"].lower()

    def test_restore_is_noop_true(self):
        assert HypervisorAuditHandler().restore({}) is True

    def test_restore_guarantee_none(self):
        assert HypervisorAuditHandler().restore_guarantee == "none"
