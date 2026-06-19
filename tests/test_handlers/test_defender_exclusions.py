"""Hermetic tests for DefenderExclusionsHandler (PowerShell mocked)."""

from __future__ import annotations

from types import SimpleNamespace
from unittest.mock import patch

from abso.settings.defender_exclusions import DefenderExclusionsHandler


def _ps(returncode=0, stdout="", stderr=""):
    return SimpleNamespace(returncode=returncode, stdout=stdout, stderr=stderr)


class TestDefenderActive:
    @patch.object(DefenderExclusionsHandler, "_run_ps")
    def test_normal_mode_is_active(self, mock_ps):
        mock_ps.return_value = _ps(stdout='{"AMRunningMode": "Normal"}')
        assert DefenderExclusionsHandler()._defender_active() is True

    @patch.object(DefenderExclusionsHandler, "_run_ps")
    def test_passive_mode_is_not_active(self, mock_ps):
        mock_ps.return_value = _ps(stdout='{"AMRunningMode": "Passive"}')
        assert DefenderExclusionsHandler()._defender_active() is False


class TestCurrentExclusions:
    @patch.object(DefenderExclusionsHandler, "_run_ps")
    def test_single_string_normalized_to_list(self, mock_ps):
        mock_ps.return_value = _ps(stdout='"C:\\\\Games\\\\One"')
        assert DefenderExclusionsHandler()._current_exclusions() == ["C:\\Games\\One"]

    @patch.object(DefenderExclusionsHandler, "_run_ps")
    def test_list_parsed(self, mock_ps):
        mock_ps.return_value = _ps(stdout='["C:\\\\A", "C:\\\\B"]')
        assert DefenderExclusionsHandler()._current_exclusions() == ["C:\\A", "C:\\B"]


class TestApply:
    @patch.object(DefenderExclusionsHandler, "_run_ps")
    @patch.object(DefenderExclusionsHandler, "_current_exclusions", return_value=[])
    @patch.object(DefenderExclusionsHandler, "_defender_active", return_value=True)
    def test_apply_adds_missing_paths(self, _active, _current, mock_ps):
        mock_ps.return_value = _ps(returncode=0)
        result = DefenderExclusionsHandler().apply({"exclusion_paths": [r"C:\Games\OW"]})
        assert result["success"] is True
        assert result["changed"] is True
        assert r"C:\Games\OW" in result["changed_keys"]

    @patch.object(DefenderExclusionsHandler, "_defender_active", return_value=False)
    def test_apply_skips_when_defender_inactive(self, _active):
        result = DefenderExclusionsHandler().apply({"exclusion_paths": [r"C:\Games\OW"]})
        assert result["success"] is True
        assert result["changed"] is False
        assert "not the active AV" in result["skipped"]

    def test_apply_noop_without_paths(self):
        result = DefenderExclusionsHandler().apply({})
        assert result["success"] is True
        assert result["changed"] is False

    @patch.object(DefenderExclusionsHandler, "_run_ps")
    @patch.object(DefenderExclusionsHandler, "_current_exclusions", return_value=[r"C:\Games\OW"])
    @patch.object(DefenderExclusionsHandler, "_defender_active", return_value=True)
    def test_apply_skips_already_present(self, _active, _current, mock_ps):
        result = DefenderExclusionsHandler().apply({"exclusion_paths": [r"C:\Games\OW"]})
        assert result["changed"] is False
        mock_ps.assert_not_called()


class TestRestore:
    @patch.object(DefenderExclusionsHandler, "_run_ps")
    @patch.object(
        DefenderExclusionsHandler,
        "_current_exclusions",
        return_value=[r"C:\Pre", r"C:\AddedByAbso"],
    )
    def test_restore_removes_only_delta(self, _current, mock_ps):
        mock_ps.return_value = _ps(returncode=0)
        ok = DefenderExclusionsHandler().restore({"exclusion_paths": [r"C:\Pre"]})
        assert ok is True
        # Exactly one Remove-MpPreference, for the path added since the backup.
        assert mock_ps.call_count == 1
        assert "C:\\AddedByAbso" in mock_ps.call_args.args[0]
        assert "Remove-MpPreference" in mock_ps.call_args.args[0]

    @patch.object(DefenderExclusionsHandler, "_run_ps")
    @patch.object(DefenderExclusionsHandler, "_current_exclusions", return_value=[r"C:\Pre"])
    def test_restore_noop_when_nothing_added(self, _current, mock_ps):
        ok = DefenderExclusionsHandler().restore({"exclusion_paths": [r"C:\Pre"]})
        assert ok is True
        mock_ps.assert_not_called()


class TestVerify:
    @patch.object(DefenderExclusionsHandler, "_current_exclusions", return_value=[r"C:\Games\OW"])
    @patch.object(DefenderExclusionsHandler, "_defender_active", return_value=True)
    def test_verify_active_true(self, _active, _current):
        result = DefenderExclusionsHandler().verify_active({"exclusion_paths": [r"C:\Games\OW"]})
        assert result["all_active"] is True

    @patch.object(DefenderExclusionsHandler, "_current_exclusions", return_value=[])
    @patch.object(DefenderExclusionsHandler, "_defender_active", return_value=True)
    def test_verify_active_false_when_missing(self, _active, _current):
        result = DefenderExclusionsHandler().verify_active({"exclusion_paths": [r"C:\Games\OW"]})
        assert result["all_active"] is False
