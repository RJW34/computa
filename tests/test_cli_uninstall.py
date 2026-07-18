"""Tests for the abso uninstall command."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from click.testing import CliRunner

from abso.main import cli


def _write_baseline_backup(backups_dir: Path, backup_id: str, backup_type: str = "baseline") -> None:
    backup_dir = backups_dir / backup_id
    backup_dir.mkdir(parents=True)
    (backup_dir / "manifest.json").write_text(
        json.dumps(
            {
                "timestamp": backup_id,
                "created_at": "2026-07-17T12:00:00",
                "profile_id": None,
                "backup_type": backup_type,
                "components": {},
            }
        ),
        encoding="utf-8",
    )


def test_uninstall_requires_admin(tmp_path: Path) -> None:
    runner = CliRunner()
    with patch("abso.main.is_admin", return_value=False):
        result = runner.invoke(cli, ["uninstall", "--yes"])
    assert result.exit_code == 1


def test_uninstall_restores_state_baseline_and_removes_autostart(tmp_path: Path) -> None:
    backups_dir = tmp_path / "backups"
    _write_baseline_backup(backups_dir, "2026-07-17_090000")

    restore_summary = MagicMock()
    restore_summary.to_dict.return_value = {"has_blocking_issues": False}
    manager = MagicMock()
    manager.restore_backup.return_value = restore_summary

    runner = CliRunner()
    with (
        patch("abso.main.is_admin", return_value=True),
        patch("abso.main.BACKUPS_DIR", backups_dir),
        patch("abso.main.STATE_FILE", tmp_path / ".abso_state.json"),
        patch(
            "abso.main._read_state_snapshot",
            return_value={"baseline_backup_id": "2026-07-17_090000"},
        ),
        patch("abso.main.BackupManager", return_value=manager),
        patch("abso.main.clear_current_profile") as clear_profile,
        patch("abso.tray.install_startup") as tray_uninstall,
    ):
        result = runner.invoke(cli, ["uninstall", "--yes", "--json"])

    assert result.exit_code == 0
    manager.restore_backup.assert_called_once_with("2026-07-17_090000")
    tray_uninstall.assert_called_once_with(uninstall=True)
    clear_profile.assert_called_once()

    assert '"restore_performed": true' in result.output
    assert '"tray_autostart_removed": true' in result.output
    assert '"state_cleared": true' in result.output


def test_uninstall_falls_back_to_oldest_baseline_backup(tmp_path: Path) -> None:
    backups_dir = tmp_path / "backups"
    _write_baseline_backup(backups_dir, "2026-07-17_090000")
    _write_baseline_backup(backups_dir, "2026-07-16_080000")
    _write_baseline_backup(backups_dir, "2026-07-17_100000", backup_type="pre_apply")

    restore_summary = MagicMock()
    restore_summary.to_dict.return_value = {"has_blocking_issues": False}
    manager = MagicMock()
    manager.restore_backup.return_value = restore_summary

    runner = CliRunner()
    with (
        patch("abso.main.is_admin", return_value=True),
        patch("abso.main.BACKUPS_DIR", backups_dir),
        patch("abso.main._read_state_snapshot", return_value={}),
        patch("abso.main.BackupManager", return_value=manager),
        patch("abso.main.clear_current_profile"),
        patch("abso.tray.install_startup"),
    ):
        result = runner.invoke(cli, ["uninstall", "--yes", "--json"])

    assert result.exit_code == 0
    # The oldest baseline-type backup is closest to the pre-ABSO system.
    manager.restore_backup.assert_called_once_with("2026-07-16_080000")


def test_uninstall_skip_restore_leaves_settings(tmp_path: Path) -> None:
    backups_dir = tmp_path / "backups"
    _write_baseline_backup(backups_dir, "2026-07-17_090000")

    runner = CliRunner()
    with (
        patch("abso.main.is_admin", return_value=True),
        patch("abso.main.BACKUPS_DIR", backups_dir),
        patch("abso.main._read_state_snapshot", return_value={}),
        patch("abso.main.BackupManager") as manager_cls,
        patch("abso.main.clear_current_profile"),
        patch("abso.tray.install_startup"),
    ):
        result = runner.invoke(cli, ["uninstall", "--yes", "--skip-restore", "--json"])

    assert result.exit_code == 0
    manager_cls.assert_not_called()
    assert '"restore_performed": false' in result.output


def test_uninstall_help_mentions_baseline() -> None:
    runner = CliRunner()
    result = runner.invoke(cli, ["uninstall", "--help"])
    assert result.exit_code == 0
    assert "baseline" in result.output.lower()
