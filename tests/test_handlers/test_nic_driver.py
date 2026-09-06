"""Tests for NicDriverHandler.

All tests are hermetic: the single PowerShell entry point (``_run_ps``) is
mocked so no real Get/Set-NetAdapterAdvancedProperty cmdlet ever runs.
"""

from __future__ import annotations

import json
import subprocess
from unittest.mock import MagicMock, patch

from abso.settings.nic_driver import NicDriverHandler


def _completed(stdout: str = "", returncode: int = 0, stderr: str = "") -> MagicMock:
    """Build a fake CompletedProcess for _run_ps to return."""
    return MagicMock(returncode=returncode, stdout=stdout, stderr=stderr)


def _adapter_json(name: str = "Ethernet") -> str:
    """Single-object ConvertTo-Json output for the adapter query."""
    return json.dumps({"Name": name})


def _props_json(props: list[dict]) -> str:
    """ConvertTo-Json output for the advanced-property query.

    A single row serializes to an object; multiple rows to a list. This helper
    reproduces both shapes so the defensive parsing path is exercised.
    """
    payload = props[0] if len(props) == 1 else props
    return json.dumps(payload)


_FULL_PROPS = [
    {"RegistryKeyword": "*InterruptModeration", "DisplayValue": "Enabled", "RegistryValue": "1"},
    {"RegistryKeyword": "*RSS", "DisplayValue": "Disabled", "RegistryValue": "0"},
    {"RegistryKeyword": "*FlowControl", "DisplayValue": "Rx & Tx Enabled", "RegistryValue": "3"},
    {"RegistryKeyword": "*EEE", "DisplayValue": "Enabled", "RegistryValue": "1"},
    # An unrelated property that must be ignored entirely.
    {"RegistryKeyword": "*JumboPacket", "DisplayValue": "Disabled", "RegistryValue": "1514"},
]

_OPTIMAL_PROPS = [
    {"RegistryKeyword": "*InterruptModeration", "DisplayValue": "Disabled", "RegistryValue": "0"},
    {"RegistryKeyword": "*RSS", "DisplayValue": "Enabled", "RegistryValue": "1"},
    {"RegistryKeyword": "*FlowControl", "DisplayValue": "Disabled", "RegistryValue": "0"},
    {"RegistryKeyword": "*EEE", "DisplayValue": "Disabled", "RegistryValue": "0"},
]


class TestDetect:
    @patch.object(NicDriverHandler, "_run_ps")
    def test_detect_returns_adapter_and_targeted_properties(self, mock_run):
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json(_FULL_PROPS)),
        ]
        result = NicDriverHandler().detect()

        assert result["adapter"] == "Ethernet"
        # Only the four targeted keywords are kept; JumboPacket is dropped.
        assert set(result["properties"]) == {
            "*InterruptModeration",
            "*RSS",
            "*FlowControl",
            "*EEE",
        }
        assert result["properties"]["*InterruptModeration"] == "1"

    @patch.object(NicDriverHandler, "_run_ps")
    def test_detect_no_active_adapter(self, mock_run):
        # ConvertTo-Json emits nothing when the pipeline is empty.
        mock_run.return_value = _completed("")
        result = NicDriverHandler().detect()

        assert result["adapter"] is None
        assert result["properties"] == {}

    @patch.object(NicDriverHandler, "_run_ps")
    def test_detect_single_property_object_shape(self, mock_run):
        # One advanced property serializes as an object, not a list.
        mock_run.side_effect = [
            _completed(_adapter_json("Wi-Fi")),
            _completed(_props_json([_FULL_PROPS[1]])),  # just *RSS
        ]
        result = NicDriverHandler().detect()

        assert result["properties"] == {"*RSS": "0"}

    @patch.object(NicDriverHandler, "_run_ps")
    def test_detect_handles_adapter_query_as_list(self, mock_run):
        # Defensive: if the adapter query returns a list, take the first.
        mock_run.side_effect = [
            _completed(json.dumps([{"Name": "Ethernet"}])),
            _completed(_props_json(_OPTIMAL_PROPS)),
        ]
        result = NicDriverHandler().detect()

        assert result["adapter"] == "Ethernet"

    @patch.object(NicDriverHandler, "_run_ps")
    def test_detect_survives_bad_json(self, mock_run):
        mock_run.return_value = _completed("not json at all")
        result = NicDriverHandler().detect()

        assert result["adapter"] is None

    @patch.object(NicDriverHandler, "_run_ps")
    def test_detect_survives_timeout(self, mock_run):
        mock_run.side_effect = subprocess.TimeoutExpired("powershell", 20)
        result = NicDriverHandler().detect()

        assert result == {"adapter": None, "properties": {}}


class TestAudit:
    @patch.object(NicDriverHandler, "detect")
    def test_audit_flags_suboptimal(self, mock_detect):
        mock_detect.return_value = {
            "adapter": "Ethernet",
            "properties": {"*InterruptModeration": "1", "*RSS": "1"},
        }
        issues = NicDriverHandler().audit()

        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].category == "network"
        assert "Interrupt Moderation" in issues[0].current_value
        # RSS already optimal so it should not appear as a problem.
        assert "Receive Side Scaling" not in issues[0].current_value

    @patch.object(NicDriverHandler, "detect")
    def test_audit_no_issue_when_optimal(self, mock_detect):
        mock_detect.return_value = {
            "adapter": "Ethernet",
            "properties": {
                "*InterruptModeration": "0",
                "*RSS": "1",
                "*FlowControl": "0",
                "*EEE": "0",
            },
        }
        assert NicDriverHandler().audit() == []

    @patch.object(NicDriverHandler, "detect")
    def test_audit_no_adapter(self, mock_detect):
        mock_detect.return_value = {"adapter": None, "properties": {}}
        assert NicDriverHandler().audit() == []


class TestApply:
    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_sets_present_keywords(self, mock_run):
        # detect: adapter + props, then four Set calls succeed.
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json(_FULL_PROPS)),
            _completed(),
            _completed(),
            _completed(),
            _completed(),
        ]
        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["success"] is True
        assert result["requires_reboot"] is False
        assert result["changed"] is True
        assert set(result["changed_keys"]) == {
            "*InterruptModeration",
            "*RSS",
            "*FlowControl",
            "*EEE",
        }
        # Verify the optimal RegistryValues were passed to Set-...
        set_scripts = [c.args[0] for c in mock_run.call_args_list if "Set-Net" in c.args[0]]
        assert any("*RSS" in s and "-RegistryValue '1'" in s for s in set_scripts)
        assert any(
            "*InterruptModeration" in s and "-RegistryValue '0'" in s for s in set_scripts
        )

    def test_apply_noop_when_not_requested(self):
        # Should not even touch PowerShell.
        with patch.object(NicDriverHandler, "_run_ps") as mock_run:
            result = NicDriverHandler().apply({})
            mock_run.assert_not_called()
        assert result["success"] is True
        assert result["changed"] is False

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_graceful_noop_without_adapter(self, mock_run):
        mock_run.return_value = _completed("")  # no Up adapter
        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert "skipped" in result["note"].lower()

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_skips_absent_keywords(self, mock_run):
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json([_FULL_PROPS[1]])),  # only *RSS exposed
            _completed(),
        ]
        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["changed_keys"] == ["*RSS"]

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_set_failure_is_best_effort_warning(self, mock_run):
        # Opt-in per-NIC add-on: a driver rejecting a keyword warns, it does not
        # fail (and roll back) the whole profile apply.
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json([_FULL_PROPS[0]])),  # only *InterruptModeration
            _completed(returncode=1, stderr="Access denied"),
        ]
        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert result["warnings"]


class TestBackupRestore:
    @patch.object(NicDriverHandler, "detect")
    def test_backup_mirrors_detect(self, mock_detect):
        expected = {"adapter": "Ethernet", "properties": {"*RSS": "0"}}
        mock_detect.return_value = expected
        assert NicDriverHandler().backup() == expected

    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_writes_originals(self, mock_run):
        mock_run.return_value = _completed()
        data = {
            "adapter": "Ethernet",
            "properties": {"*InterruptModeration": "1", "*FlowControl": "3"},
        }
        assert NicDriverHandler().restore(data) is True

        set_scripts = [c.args[0] for c in mock_run.call_args_list]
        assert any("-RegistryValue '1'" in s for s in set_scripts)
        assert any("-RegistryValue '3'" in s for s in set_scripts)

    def test_restore_empty_backup_is_noop_success(self):
        with patch.object(NicDriverHandler, "_run_ps") as mock_run:
            assert NicDriverHandler().restore({"adapter": None, "properties": {}}) is True
            mock_run.assert_not_called()

    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_exception_reports_failure(self, mock_run):
        # A failed revert must remain visible to transaction rollback.
        mock_run.side_effect = Exception("boom")
        data = {"adapter": "Ethernet", "properties": {"*RSS": "0"}}
        assert NicDriverHandler().restore(data) is False

    @patch.object(NicDriverHandler, "_set_property")
    def test_restore_continues_after_one_property_fails(self, setter):
        setter.side_effect = [OSError("first failed"), True]
        data = {"adapter": "Ethernet", "properties": {"*RSS": "0", "*EEE": "1"}}
        assert NicDriverHandler().restore(data) is False
        assert setter.call_count == 2

    @patch.object(NicDriverHandler, "_set_property", return_value=False)
    def test_restore_reports_native_setter_failure(self, setter):
        data = {"adapter": "Ethernet", "properties": {"*RSS": "0"}}
        assert NicDriverHandler().restore(data) is False


class TestVerifyActive:
    def test_verify_skipped_when_not_requested(self):
        result = NicDriverHandler().verify_active({})
        assert result["all_active"] is True
        assert result["settings"] == {}

    @patch.object(NicDriverHandler, "detect")
    def test_verify_active_all_optimal(self, mock_detect):
        mock_detect.return_value = {
            "adapter": "Ethernet",
            "properties": {
                "*InterruptModeration": "0",
                "*RSS": "1",
                "*FlowControl": "0",
                "*EEE": "0",
            },
        }
        result = NicDriverHandler().verify_active({"nic_tuning": True})

        assert result["all_active"] is True
        assert result["settings"]["*RSS"]["active"] is True

    @patch.object(NicDriverHandler, "detect")
    def test_verify_active_detects_mismatch(self, mock_detect):
        mock_detect.return_value = {
            "adapter": "Ethernet",
            "properties": {"*InterruptModeration": "1"},
        }
        result = NicDriverHandler().verify_active({"nic_tuning": True})

        assert result["all_active"] is False
        assert result["settings"]["*InterruptModeration"]["active"] is False


class TestContract:
    def test_critical_verify_and_restore_guarantee(self):
        handler = NicDriverHandler()
        # Opt-in best-effort latency add-on: warning-level verify, non-blocking
        # partial restore.
        assert handler.is_critical_verify is False
        assert handler.restore_guarantee == "partial"

    def test_keyword_matching_is_case_insensitive_and_suffix_based(self):
        # Vendor spellings vary: confirm the suffix matcher catches a prefixed,
        # mixed-case keyword.
        target = NicDriverHandler._target_for("EnableInterruptModeration")
        assert target is not None
        assert target[1] == "0"
        assert NicDriverHandler._target_for("*JumboPacket") is None
