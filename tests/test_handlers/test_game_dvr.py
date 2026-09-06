"""Hermetic tests for GameDvrHandler (registry calls are mocked)."""

from __future__ import annotations

from unittest.mock import patch

from abso.settings.game_dvr import GameDvrHandler


class TestGameDvrDetectAudit:
    @patch.object(GameDvrHandler, "_read_dword", side_effect=[1, None])
    def test_detect_returns_both_values(self, _mock_read):
        result = GameDvrHandler().detect()
        assert result == {"game_dvr_enabled": 1, "allow_game_dvr_policy": None}

    @patch.object(GameDvrHandler, "detect", return_value={
        "game_dvr_enabled": 1,
        "allow_game_dvr_policy": None,
    })
    def test_audit_flags_armed(self, _mock_detect):
        issues = GameDvrHandler().audit()
        assert any("Game DVR" in i.title for i in issues)

    @patch.object(GameDvrHandler, "detect", return_value={
        "game_dvr_enabled": 0,
        "allow_game_dvr_policy": 0,
    })
    def test_audit_clean_when_hard_off(self, _mock_detect):
        assert GameDvrHandler().audit() == []


class TestGameDvrApply:
    @patch.object(GameDvrHandler, "_write_dword", return_value=True)
    def test_apply_hard_disable_writes_both_zero(self, mock_write):
        result = GameDvrHandler().apply({"hard_disable": True})
        assert result["success"] is True
        assert set(result["changed_keys"]) == {"game_dvr_enabled", "allow_game_dvr_policy"}
        # Both writes target value 0.
        for call in mock_write.call_args_list:
            assert call.args[-1] == 0

    @patch.object(GameDvrHandler, "_write_dword")
    def test_apply_noop_without_hard_disable(self, mock_write):
        result = GameDvrHandler().apply({})
        assert result["success"] is True
        assert result["changed"] is False
        mock_write.assert_not_called()

    @patch.object(GameDvrHandler, "_write_dword", side_effect=OSError("denied"))
    def test_apply_write_failure_is_best_effort_warning(self, _mock_write):
        # Opt-in add-on: a write failure must NOT fail the apply (which would
        # roll back the whole profile); it surfaces as a warning instead.
        result = GameDvrHandler().apply({"hard_disable": True})
        assert result["success"] is True
        assert result["changed"] is False
        assert result["warnings"]


class TestGameDvrVerify:
    @patch.object(GameDvrHandler, "detect", return_value={
        "game_dvr_enabled": 0,
        "allow_game_dvr_policy": 0,
    })
    def test_verify_active_true(self, _mock_detect):
        result = GameDvrHandler().verify_active({"hard_disable": True})
        assert result["all_active"] is True

    @patch.object(GameDvrHandler, "detect", return_value={
        "game_dvr_enabled": 1,
        "allow_game_dvr_policy": None,
    })
    def test_verify_active_false_when_still_armed(self, _mock_detect):
        result = GameDvrHandler().verify_active({"hard_disable": True})
        assert result["all_active"] is False

    def test_verify_noop_without_hard_disable(self):
        assert GameDvrHandler().verify_active({})["all_active"] is True


class TestGameDvrRestore:
    @patch.object(GameDvrHandler, "_restore_value")
    def test_restore_calls_restore_for_both_keys(self, mock_restore):
        ok = GameDvrHandler().restore({"game_dvr_enabled": 1, "allow_game_dvr_policy": None})
        assert ok is True
        assert mock_restore.call_count == 2

    @patch.object(GameDvrHandler, "_restore_value", side_effect=Exception("boom"))
    def test_restore_exception_reports_failure(self, _mock_restore):
        # A failed rollback must remain visible to the transaction.
        assert GameDvrHandler().restore({"game_dvr_enabled": 0}) is False

    def test_restore_guarantee_partial(self):
        assert GameDvrHandler().restore_guarantee == "partial"

    def test_is_critical_verify_false(self):
        assert GameDvrHandler().is_critical_verify is False
