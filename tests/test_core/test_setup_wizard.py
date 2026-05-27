"""Tests for first-run setup wizard apply behavior."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.core.applier import ApplyResult
from abso.core.setup_wizard import SetupWizard, _get_data_dir


def test_setup_wizard_frozen_data_dir_honors_localappdata(tmp_path: Path) -> None:
    """Packaged setup state should land beside the packaged CLI/tray state."""
    local_root = tmp_path / "local"

    with (
        patch.dict("os.environ", {"LOCALAPPDATA": str(local_root)}),
        patch("sys.frozen", True, create=True),
    ):
        data_dir = _get_data_dir()

    assert data_dir == local_root / "AdaptiveBattleStationOptimizer"
    assert data_dir.is_dir()


def test_setup_apply_uses_transaction_actual_profile(tmp_path: Path) -> None:
    """Setup wizard should persist the profile that transaction actually committed."""
    tx = MagicMock()
    tx.success = True
    tx.profile_id = "safe-profile"
    tx.apply_result = ApplyResult(
        success=True,
        requires_reboot=True,
        reboot_reasons=["WindowsSettingsHandler"],
    )

    manager = MagicMock()
    manager.execute.return_value = tx

    wizard = SetupWizard()
    wizard.backups_dir = tmp_path / "backups"
    wizard.state_file = tmp_path / ".abso_state.json"

    with patch("abso.core.setup_wizard.ProfileTransactionManager", return_value=manager):
        wizard._step_apply_profile("strict-profile")

    manager.execute.assert_called_once_with(
        profile_id="strict-profile",
        create_backup=True,
    )
    assert wizard.profile_applied == "safe-profile"
    state = json.loads(wizard.state_file.read_text(encoding="utf-8"))
    assert state["current_profile"] == "safe-profile"
    assert state["reboot_pending"] is True
    assert state["reboot_reasons"] == ["WindowsSettingsHandler"]
    assert state["setup_completed"] is True


def test_setup_apply_uses_shared_state_writer_for_default_state(tmp_path: Path) -> None:
    """Default setup state writes through the shared mirror used by CLI/tray."""
    tx = MagicMock()
    tx.success = True
    tx.profile_id = "safe-profile"
    tx.apply_result = ApplyResult(success=True, requires_reboot=False)

    manager = MagicMock()
    manager.execute.return_value = tx

    state_file = tmp_path / ".abso_state.json"
    wizard = SetupWizard()
    wizard.backups_dir = tmp_path / "backups"
    wizard.state_file = state_file

    with (
        patch("abso.core.setup_wizard.ProfileTransactionManager", return_value=manager),
        patch("abso.main.STATE_FILE", state_file),
        patch("abso.main._write_state_snapshot") as mock_write_state,
    ):
        wizard._step_apply_profile("strict-profile")

    mock_write_state.assert_called_once()
    state = mock_write_state.call_args.args[0]
    assert state["current_profile"] == "safe-profile"
    assert state["setup_completed"] is True
