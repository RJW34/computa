"""Tests for NicDriverHandler.

All tests are hermetic: the single PowerShell entry point (``_run_ps``) is
mocked so no real Get/Set-NetAdapterAdvancedProperty cmdlet ever runs.
"""

from __future__ import annotations

import base64
import json
import re
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


def _batch_results(
    *results: tuple[str, bool, str | None],
) -> str:
    """Build the JSON emitted by the batched property writer."""
    rows = [
        {"Keyword": keyword, "Success": success, "Error": error}
        for keyword, success, error in results
    ]
    payload = rows[0] if len(rows) == 1 else rows
    return json.dumps(payload)


def _batch_payload(script: str) -> dict:
    """Decode the safely embedded JSON payload from a batch script."""
    match = re.search(r"FromBase64String\('([^']+)'\)", script)
    assert match is not None
    return json.loads(base64.b64decode(match.group(1)).decode("utf-8"))


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
    def test_apply_batches_all_mismatched_keywords(self, mock_run):
        # Detect uses two queries; every write is then made by one batch process.
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json(_FULL_PROPS)),
            _completed(
                _batch_results(
                    ("*InterruptModeration", True, None),
                    ("*RSS", True, None),
                    ("*FlowControl", True, None),
                    ("*EEE", True, None),
                )
            ),
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
        assert mock_run.call_count == 3
        batch_script = mock_run.call_args_list[-1].args[0]
        assert batch_script.count("Set-NetAdapterAdvancedProperty") == 1
        payload = _batch_payload(batch_script)
        assert payload == {
            "Adapter": "Ethernet",
            "Properties": [
                {"Keyword": "*InterruptModeration", "Value": "0"},
                {"Keyword": "*RSS", "Value": "1"},
                {"Keyword": "*FlowControl", "Value": "0"},
                {"Keyword": "*EEE", "Value": "0"},
            ],
        }

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_all_matching_is_noop(self, mock_run):
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json(_OPTIMAL_PROPS)),
        ]

        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert result["changed_keys"] == []
        assert result["warnings"] == []
        assert mock_run.call_count == 2
        assert not any(
            "Set-NetAdapterAdvancedProperty" in call.args[0] for call in mock_run.call_args_list
        )

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_mixed_values_batches_only_mismatches(self, mock_run):
        mixed = [
            _FULL_PROPS[0],  # Interrupt Moderation needs 0.
            _OPTIMAL_PROPS[1],  # RSS already 1.
            _FULL_PROPS[2],  # Flow Control needs 0.
            _OPTIMAL_PROPS[3],  # EEE already 0.
        ]
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json(mixed)),
            _completed(
                _batch_results(
                    ("*InterruptModeration", True, None),
                    ("*FlowControl", True, None),
                )
            ),
        ]

        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["changed_keys"] == ["*InterruptModeration", "*FlowControl"]
        payload = _batch_payload(mock_run.call_args_list[-1].args[0])
        assert payload["Properties"] == [
            {"Keyword": "*InterruptModeration", "Value": "0"},
            {"Keyword": "*FlowControl", "Value": "0"},
        ]

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
        assert "unverifiable" in result["note"].lower()
        assert result["warnings"]

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_empty_property_detection_warns_and_writes_nothing(self, mock_run):
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(""),
        ]

        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert result["warnings"]
        assert "unverifiable" in result["note"].lower()
        assert mock_run.call_count == 2

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_skips_absent_keywords(self, mock_run):
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json([_FULL_PROPS[1]])),  # only *RSS exposed
            _completed(_batch_results(("*RSS", True, None))),
        ]
        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["changed_keys"] == ["*RSS"]

    @patch.object(NicDriverHandler, "_run_ps")
    def test_apply_reports_each_property_failure_from_batch(self, mock_run):
        # A rejected property warns without hiding a successful sibling.
        mock_run.side_effect = [
            _completed(_adapter_json("Ethernet")),
            _completed(_props_json([_FULL_PROPS[0], _FULL_PROPS[2]])),
            _completed(
                _batch_results(
                    ("*InterruptModeration", True, None),
                    ("*FlowControl", False, "Access denied"),
                )
            ),
        ]
        result = NicDriverHandler().apply({"nic_tuning": True})

        assert result["success"] is True
        assert result["changed"] is True
        assert result["changed_keys"] == ["*InterruptModeration"]
        assert len(result["warnings"]) == 1
        assert "*FlowControl" in result["warnings"][0]
        assert "Access denied" in result["warnings"][0]


class TestBackupRestore:
    @patch.object(NicDriverHandler, "detect")
    def test_backup_mirrors_detect(self, mock_detect):
        expected = {"adapter": "Ethernet", "properties": {"*RSS": "0"}}
        mock_detect.return_value = expected
        assert NicDriverHandler().backup() == expected

    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_batches_only_values_not_already_restored(self, mock_run):
        mock_run.side_effect = [
            _completed(
                _props_json(
                    [
                        {
                            "RegistryKeyword": "*InterruptModeration",
                            "RegistryValue": "0",
                        },
                        {"RegistryKeyword": "*FlowControl", "RegistryValue": "3"},
                    ]
                )
            ),
            _completed(_batch_results(("*InterruptModeration", True, None))),
        ]
        data = {
            "adapter": "Ethernet",
            "properties": {"*InterruptModeration": "1", "*FlowControl": "3"},
        }
        assert NicDriverHandler().restore(data) is True

        assert mock_run.call_count == 2
        payload = _batch_payload(mock_run.call_args_list[-1].args[0])
        assert payload["Properties"] == [{"Keyword": "*InterruptModeration", "Value": "1"}]

    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_all_matching_is_idempotent(self, mock_run):
        mock_run.return_value = _completed(
            _props_json(
                [
                    {"RegistryKeyword": "*InterruptModeration", "RegistryValue": "1"},
                    {"RegistryKeyword": "*FlowControl", "RegistryValue": "3"},
                ]
            )
        )
        data = {
            "adapter": "Ethernet",
            "properties": {"*InterruptModeration": "1", "*FlowControl": "3"},
        }

        assert NicDriverHandler().restore(data) is True

        mock_run.assert_called_once()
        assert "Set-NetAdapterAdvancedProperty" not in mock_run.call_args.args[0]

    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_empty_detection_attempts_batch_and_warns(self, mock_run, caplog):
        mock_run.side_effect = [
            _completed(""),
            _completed(_batch_results(("*FlowControl", True, None))),
        ]
        data = {"adapter": "Ethernet", "properties": {"*FlowControl": "3"}}

        assert NicDriverHandler().restore(data) is True

        assert mock_run.call_count == 2
        assert "Could not verify current NIC properties" in caplog.text
        payload = _batch_payload(mock_run.call_args_list[-1].args[0])
        assert payload["Properties"] == [{"Keyword": "*FlowControl", "Value": "3"}]

    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_logs_only_failed_property_from_batch(self, mock_run, caplog):
        mock_run.side_effect = [
            _completed(
                _props_json(
                    [
                        {"RegistryKeyword": "*InterruptModeration", "RegistryValue": "0"},
                        {"RegistryKeyword": "*FlowControl", "RegistryValue": "0"},
                    ]
                )
            ),
            _completed(
                _batch_results(
                    ("*InterruptModeration", True, None),
                    ("*FlowControl", False, "Driver rejected value"),
                )
            ),
        ]
        data = {
            "adapter": "Ethernet",
            "properties": {"*InterruptModeration": "1", "*FlowControl": "3"},
        }

        assert NicDriverHandler().restore(data) is False

        assert "Failed to restore NIC driver property *FlowControl" in caplog.text
        assert "Driver rejected value" in caplog.text
        assert "Failed to restore NIC driver property *InterruptModeration" not in caplog.text

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

    @patch.object(NicDriverHandler, "_targeted_properties", return_value={})
    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_continues_after_one_property_fails(self, mock_run, _detect):
        mock_run.return_value = _completed(_batch_results(
            ("*RSS", False, "first failed"), ("*EEE", True, None),
        ))
        data = {"adapter": "Ethernet", "properties": {"*RSS": "0", "*EEE": "1"}}
        assert NicDriverHandler().restore(data) is False
        mock_run.assert_called_once()
        assert _batch_payload(mock_run.call_args.args[0])["Properties"] == [
            {"Keyword": "*RSS", "Value": "0"}, {"Keyword": "*EEE", "Value": "1"},
        ]

    @patch.object(NicDriverHandler, "_targeted_properties", return_value={})
    @patch.object(NicDriverHandler, "_run_ps")
    def test_restore_reports_native_setter_failure(self, mock_run, _detect):
        mock_run.return_value = _completed(returncode=1, stderr="Access denied")
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

    @patch.object(NicDriverHandler, "detect")
    def test_verify_empty_detection_fails_closed(self, mock_detect):
        mock_detect.return_value = {"adapter": "Ethernet", "properties": {}}

        result = NicDriverHandler().verify_active({"nic_tuning": True})

        assert result["all_active"] is False
        assert result["settings"]["detection"]["active"] is False

    @patch.object(NicDriverHandler, "detect")
    def test_verify_missing_adapter_fails_closed(self, mock_detect):
        mock_detect.return_value = {"adapter": None, "properties": {}}

        result = NicDriverHandler().verify_active({"nic_tuning": True})

        assert result["all_active"] is False
        assert result["settings"]["detection"]["current"] == "unavailable"


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

    @patch.object(NicDriverHandler, "_run_ps")
    def test_batch_inputs_are_encoded_not_executable(self, mock_run):
        adapter = "Ether'net; Write-Host adapter-injection"
        keyword = "*RSS'; Write-Host keyword-injection; #"
        value = "1'; Write-Host value-injection; #"
        mock_run.return_value = _completed(_batch_results((keyword, True, None)))

        result = NicDriverHandler()._set_properties(adapter, {keyword: value})

        assert result[keyword]["success"] is True
        script = mock_run.call_args.args[0]
        assert adapter not in script
        assert keyword not in script
        assert value not in script
        assert _batch_payload(script) == {
            "Adapter": adapter,
            "Properties": [{"Keyword": keyword, "Value": value}],
        }
