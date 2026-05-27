from datetime import datetime
from unittest.mock import MagicMock, patch

from abso.core.backup_actions import (
    create_manual_backup_payload,
    delete_backup_payload,
    list_backup_payloads,
    prune_backup_payload,
)


def test_list_backup_payloads_uses_backup_manager(tmp_path):
    manager = MagicMock()
    manager.list_backups.return_value = [{"id": "backup-1"}]

    with patch("abso.core.backup_actions.BackupManager", return_value=manager):
        payload = list_backup_payloads(tmp_path / "backups")

    assert payload == [{"id": "backup-1"}]
    assert (tmp_path / "backups").is_dir()


def test_create_manual_backup_payload_returns_created_manifest(tmp_path):
    manager = MagicMock()
    manager.create_backup.return_value = "2026-05-26_070000"
    manager.list_backups.return_value = [
        {"id": "older", "created_at": "2026-05-26T06:00:00", "components": []},
        {
            "id": "2026-05-26_070000",
            "created_at": "2026-05-26T07:00:00",
            "components": ["WindowsSettingsHandler"],
        },
    ]

    with patch("abso.core.backup_actions.BackupManager", return_value=manager):
        payload = create_manual_backup_payload(
            tmp_path,
            current_profile="overwatch2-gsync-hdr-capture",
        )

    manager.create_backup.assert_called_once_with(
        profile_id="overwatch2-gsync-hdr-capture",
        backup_type="manual",
    )
    assert payload["id"] == "2026-05-26_070000"
    assert payload["components"] == ["WindowsSettingsHandler"]


def test_create_manual_backup_payload_has_stable_fallback(tmp_path):
    manager = MagicMock()
    manager.create_backup.return_value = "manual-id"
    manager.list_backups.return_value = []

    with patch("abso.core.backup_actions.BackupManager", return_value=manager):
        payload = create_manual_backup_payload(
            tmp_path,
            current_profile=None,
            now_factory=lambda: datetime(2026, 5, 26, 7, 0, 0),
        )

    assert payload == {
        "id": "manual-id",
        "created_at": "2026-05-26T07:00:00",
        "components": [],
    }


def test_delete_backup_payload_delegates_and_returns_command_payload(tmp_path):
    manager = MagicMock()

    with patch("abso.core.backup_actions.BackupManager", return_value=manager):
        payload = delete_backup_payload(tmp_path, "backup-id")

    manager.delete_backup.assert_called_once_with("backup-id")
    assert payload == {"success": True, "backup_id": "backup-id"}


def test_prune_backup_payload_reports_counts_from_pre_prune_list(tmp_path):
    manager = MagicMock()
    manager.list_backups.return_value = [{"id": "a"}, {"id": "b"}, {"id": "c"}]
    manager.prune.return_value = ["a"]

    with patch("abso.core.backup_actions.BackupManager", return_value=manager):
        payload = prune_backup_payload(tmp_path, keep=2)

    manager.prune.assert_called_once_with(max_backups=2)
    assert payload == {
        "kept": 2,
        "deleted_count": 1,
        "deleted": ["a"],
        "remaining": 2,
    }
