"""Hermetic tests for InterruptModeHandler (WMI + registry mocked)."""

from __future__ import annotations

from unittest.mock import patch

from abso.settings.interrupt_mode import InterruptModeHandler

_GPU = r"PCI\VEN_10DE&DEV_2786&SUBSYS_12345678&REV_A1\4&abcd1234&0&0019"


class TestDetectAudit:
    @patch.object(InterruptModeHandler, "_read_msi", return_value=0)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_detect_reports_per_gpu(self, _ids, _read):
        result = InterruptModeHandler().detect()
        assert result["gpu_msi"][_GPU] == 0

    @patch.object(InterruptModeHandler, "_read_msi", return_value=0)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_audit_flags_non_msi(self, _ids, _read):
        issues = InterruptModeHandler().audit()
        assert any("MSI" in i.title for i in issues)

    @patch.object(InterruptModeHandler, "_read_msi", return_value=1)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_audit_clean_when_msi_on(self, _ids, _read):
        assert InterruptModeHandler().audit() == []

    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[])
    def test_audit_silent_without_gpu(self, _ids):
        assert InterruptModeHandler().audit() == []


class TestApply:
    @patch.object(InterruptModeHandler, "_write_msi")
    @patch.object(InterruptModeHandler, "_read_msi", return_value=0)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_apply_enables_msi_and_requires_reboot(self, _ids, _read, mock_write):
        result = InterruptModeHandler().apply({"enable_msi": True})
        assert result["success"] is True
        assert result["requires_reboot"] is True
        assert result["changed"] is True
        mock_write.assert_called_once_with(_GPU, 1)

    @patch.object(InterruptModeHandler, "_write_msi")
    @patch.object(InterruptModeHandler, "_read_msi", return_value=1)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_apply_skips_when_already_msi(self, _ids, _read, mock_write):
        result = InterruptModeHandler().apply({"enable_msi": True})
        assert result["requires_reboot"] is False
        mock_write.assert_not_called()

    @patch.object(InterruptModeHandler, "_write_msi")
    def test_apply_noop_without_flag(self, mock_write):
        result = InterruptModeHandler().apply({})
        assert result["success"] is True
        assert result["changed"] is False
        mock_write.assert_not_called()

    @patch.object(InterruptModeHandler, "_write_msi", side_effect=OSError("ACL denied"))
    @patch.object(InterruptModeHandler, "_read_msi", return_value=0)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_apply_write_failure_is_best_effort_warning(self, _ids, _read, _write):
        # ACL-restricted Enum key: warn, do not fail (and roll back) the apply.
        result = InterruptModeHandler().apply({"enable_msi": True})
        assert result["success"] is True
        assert result["changed"] is False
        assert result["requires_reboot"] is False
        assert result["warnings"]


class TestVerifyRestore:
    @patch.object(InterruptModeHandler, "_read_msi", return_value=1)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_verify_active_true(self, _ids, _read):
        # Written and no MSI-specific reboot pending -> live/active.
        result = InterruptModeHandler().verify_active(
            {"enable_msi": True, "_reboot_reasons": []}
        )
        assert result["all_active"] is True
        setting = result["settings"][f"msi:{_GPU.split(chr(92))[1]}"]
        assert setting["registry_target_written"] is True
        assert setting["active"] is True

    @patch.object(InterruptModeHandler, "_read_msi", return_value=0)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_verify_active_false(self, _ids, _read):
        result = InterruptModeHandler().verify_active(
            {"enable_msi": True, "_reboot_reasons": []}
        )
        assert result["all_active"] is False
        assert result["pending_apply_settings"]

    @patch.object(InterruptModeHandler, "_read_msi", return_value=1)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_verify_written_but_reboot_pending_is_not_yet_active(self, _ids, _read):
        # Freshly written MSI mode (==1) but the MSI reboot reason is still
        # pending: must report reboot-gated, NOT a false "active".
        result = InterruptModeHandler().verify_active(
            {"enable_msi": True, "_reboot_reasons": ["InterruptModeHandler.msi_mode"]}
        )
        assert result["all_active"] is False
        key = f"msi:{_GPU.split(chr(92))[1]}"
        assert result["pending_reboot_gated_settings"] == [key]
        setting = result["settings"][key]
        assert setting["registry_target_written"] is True
        assert setting["active"] is False
        assert setting["reboot_gated"] is True

    @patch.object(InterruptModeHandler, "_read_msi", return_value=1)
    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[_GPU])
    def test_verify_unrelated_reboot_reason_keeps_live_msi_active(self, _ids, _read):
        # An unrelated reboot reason must NOT mislabel an already-committed MSI.
        result = InterruptModeHandler().verify_active(
            {"enable_msi": True, "_reboot_reasons": ["GraphicsSettingsHandler.mpo_disabled"]}
        )
        assert result["all_active"] is True

    @patch.object(InterruptModeHandler, "_get_gpu_pnp_ids", return_value=[])
    def test_verify_unresolved_gpu_fails_closed(self, _ids):
        # WMI returned no GPU: cannot confirm -> fail closed, not vacuously True.
        result = InterruptModeHandler().verify_active(
            {"enable_msi": True, "_reboot_reasons": []}
        )
        assert result["all_active"] is False
        assert result["pending_apply_settings"] == ["msi_mode"]
        assert "msi:unresolved" in result["settings"]

    def test_verify_noop_without_flag(self):
        assert InterruptModeHandler().verify_active({})["all_active"] is True

    @patch.object(InterruptModeHandler, "_restore_msi")
    def test_restore_writes_each_gpu(self, mock_restore):
        ok = InterruptModeHandler().restore({"gpu_msi": {_GPU: 0, "PCI\\OTHER": None}})
        assert ok is True
        assert mock_restore.call_count == 2

    @patch.object(InterruptModeHandler, "_restore_msi")
    def test_restore_reports_partial_failure_and_attempts_other_gpu(self, mock_restore):
        mock_restore.side_effect = [OSError("access denied"), None]
        ok = InterruptModeHandler().restore({"gpu_msi": {_GPU: 0, "PCI\\OTHER": None}})
        assert ok is False
        assert mock_restore.call_count == 2
