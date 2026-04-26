"""Tests for backup and restore module."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from abso.core.backup import BackupManager
from abso.core.exceptions import BackupCorruptedError, BackupNotFoundError


class TestBackupManagerInit:
    """Tests for BackupManager initialization."""

    def test_init_creates_instance(self, tmp_path):
        """Test BackupManager can be instantiated."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            assert manager is not None
            assert manager.backup_dir == tmp_path

    def test_init_loads_handlers(self, tmp_path):
        """Test BackupManager loads handlers on init."""
        mock_handler = MagicMock()

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            assert len(manager._handlers) == 1


class TestCreateBackup:
    """Tests for create_backup method."""

    def test_create_backup_creates_directory(self, tmp_path):
        """Test create_backup creates a timestamped directory."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {"setting": "value"}

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        backup_path = tmp_path / backup_id
        assert backup_path.exists()
        assert backup_path.is_dir()

    def test_create_backup_creates_manifest(self, tmp_path):
        """Test create_backup creates manifest.json."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {"setting": "value"}

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        manifest_path = tmp_path / backup_id / "manifest.json"
        assert manifest_path.exists()

        manifest = json.loads(manifest_path.read_text())
        assert "timestamp" in manifest
        assert "created_at" in manifest
        assert "components" in manifest

    def test_create_backup_saves_handler_data(self, tmp_path):
        """Test create_backup saves handler backup data."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {"setting": "value", "nested": {"key": 123}}

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        component_path = tmp_path / backup_id / "TestHandler.json"
        assert component_path.exists()

        data = json.loads(component_path.read_text())
        assert data["setting"] == "value"
        assert data["nested"]["key"] == 123

    def test_create_backup_handles_handler_failure(self, tmp_path):
        """Test create_backup handles handler backup failure."""
        handler1 = MagicMock()
        handler1.__class__.__name__ = "Handler1"
        handler1.backup.return_value = {"data": "ok"}

        handler2 = MagicMock()
        handler2.__class__.__name__ = "Handler2"
        handler2.backup.side_effect = PermissionError("Access denied")

        with patch("abso.core.backup._get_backup_handlers", return_value=[handler1, handler2]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        manifest_path = tmp_path / backup_id / "manifest.json"
        manifest = json.loads(manifest_path.read_text())

        assert manifest["components"]["Handler1"]["success"] is True
        assert manifest["components"]["Handler2"]["success"] is False
        assert "Permission denied" in manifest["components"]["Handler2"]["error"]

    def test_create_backup_marks_unrestorable_component(self, tmp_path):
        """Test create_backup respects a handler-reported success flag."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "NvidiaSettingsHandler"
        mock_handler.backup.return_value = {
            "success": False,
            "note": "Safe restore unavailable",
            "profile_path": None,
        }

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        manifest = json.loads((tmp_path / backup_id / "manifest.json").read_text())
        assert manifest["components"]["NvidiaSettingsHandler"]["success"] is False
        assert manifest["components"]["NvidiaSettingsHandler"]["note"] == "Safe restore unavailable"

    def test_create_backup_returns_timestamp_id(self, tmp_path):
        """Test create_backup returns timestamp-based ID."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        # Should be in format YYYY-MM-DD_HHMMSS
        assert len(backup_id) == 17
        assert backup_id[4] == "-"
        assert backup_id[7] == "-"
        assert backup_id[10] == "_"


class TestRestoreBackup:
    """Tests for restore_backup method."""

    def test_restore_backup_not_found(self, tmp_path):
        """Test restore_backup raises for non-existent backup."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            with pytest.raises(BackupNotFoundError) as exc_info:
                manager.restore_backup("nonexistent")

            assert "not found" in str(exc_info.value).lower()

    def test_restore_backup_corrupted_manifest(self, tmp_path):
        """Test restore_backup raises for corrupted manifest."""
        # Create backup directory without valid manifest
        backup_dir = tmp_path / "2024-01-01_120000"
        backup_dir.mkdir()
        (backup_dir / "manifest.json").write_text("invalid json{{{")

        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            with pytest.raises(BackupCorruptedError) as exc_info:
                manager.restore_backup("2024-01-01_120000")

            assert "corrupted" in str(exc_info.value).lower()

    def test_restore_backup_missing_manifest(self, tmp_path):
        """Test restore_backup raises for missing manifest."""
        backup_dir = tmp_path / "2024-01-01_120000"
        backup_dir.mkdir()

        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            with pytest.raises(BackupCorruptedError) as exc_info:
                manager.restore_backup("2024-01-01_120000")

            assert "manifest" in str(exc_info.value).lower()

    def test_restore_backup_calls_handlers(self, tmp_path):
        """Test restore_backup calls handler restore methods."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {"setting": "original"}
        mock_handler.restore.return_value = True

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)

            # Create backup
            backup_id = manager.create_backup()

            # Restore backup
            manager.restore_backup(backup_id)

        mock_handler.restore.assert_called_once()
        call_args = mock_handler.restore.call_args[0][0]
        assert call_args["setting"] == "original"

    def test_restore_backup_latest(self, tmp_path):
        """Test restore_backup with 'latest' argument."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {"version": 1}
        mock_handler.restore.return_value = True

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)

            # Create two backups
            manager.create_backup()
            import time
            time.sleep(0.1)  # Ensure different timestamp
            manager.create_backup()  # Second backup

            # Update handler backup data
            mock_handler.backup.return_value = {"version": 2}

            # Restore latest
            manager.restore_backup("latest")

        # Should have restored from the second backup
        mock_handler.restore.assert_called()

    def test_restore_backup_skips_failed_components(self, tmp_path):
        """Test restore_backup skips components that failed during backup."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.side_effect = PermissionError("Failed")

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        # Reset mock for restore
        mock_handler.restore.reset_mock()

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            manager.restore_backup(backup_id)

        # Restore should not be called for failed component
        mock_handler.restore.assert_not_called()

    def test_restore_backup_returns_incomplete_summary_when_handler_restore_fails(self, tmp_path):
        """Test restore summary is incomplete when a handler reports restore failure."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {"setting": "value"}
        mock_handler.restore.return_value = False

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            summary = manager.restore_backup(backup_id)

        assert summary.complete is False
        assert summary.failed_components[0]["handler"] == "TestHandler"

    def test_restore_backup_legacy_manifest_uses_handler_restore_guarantee(self, tmp_path):
        """Legacy manifests without restore_guarantee must inherit it from the live handler."""
        backup_dir = tmp_path / "2026-04-01_031936"
        backup_dir.mkdir()
        (backup_dir / "manifest.json").write_text(
            json.dumps(
                {
                    "timestamp": "2026-04-01_031936",
                    "created_at": "2026-04-01T03:19:36.377134",
                    "profile_id": "overwatch2-gsync",
                    "backup_type": "pre_apply",
                    "components": {
                        "NvidiaSettingsHandler": {
                            "file": "NvidiaSettingsHandler.json",
                            "success": False,
                            "note": (
                                "NVIDIA backup cannot be restored safely because Profile Inspector "
                                "import is disabled to avoid wiping the user's driver profile database."
                            ),
                        }
                    },
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        (backup_dir / "NvidiaSettingsHandler.json").write_text(
            json.dumps({"success": False}),
            encoding="utf-8",
        )

        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "NvidiaSettingsHandler"
        type(mock_handler).restore_guarantee = property(lambda self: "none")

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            summary = manager.restore_backup("2026-04-01_031936")

        assert summary.complete is False
        assert summary.has_blocking_issues is False
        assert summary.skipped_components == [
            {
                "handler": "NvidiaSettingsHandler",
                "reason": "backup_unavailable",
                "detail": (
                    "NVIDIA backup cannot be restored safely because Profile Inspector import "
                    "is disabled to avoid wiping the user's driver profile database."
                ),
                "blocking": False,
            }
        ]


class TestListBackups:
    """Tests for list_backups method."""

    def test_list_backups_empty(self, tmp_path):
        """Test list_backups with no backups."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            backups = manager.list_backups()

        assert backups == []

    def test_list_backups_returns_all(self, tmp_path):
        """Test list_backups returns all backups."""
        import time
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            manager.create_backup()
            time.sleep(1.1)  # 1-second timestamp resolution needs >1s gap
            manager.create_backup()

            backups = manager.list_backups()

        assert len(backups) == 2

    def test_list_backups_sorted_newest_first(self, tmp_path):
        """Test list_backups returns newest first."""
        import time
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            id1 = manager.create_backup()
            time.sleep(1.1)  # 1-second timestamp resolution needs >1s gap
            id2 = manager.create_backup()

            backups = manager.list_backups()

        assert backups[0]["id"] == id2  # Newest first
        assert backups[1]["id"] == id1

    def test_list_backups_structure(self, tmp_path):
        """Test list_backups returns correct structure."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.backup.return_value = {}

        with patch("abso.core.backup._get_backup_handlers", return_value=[mock_handler]):
            manager = BackupManager(tmp_path)
            manager.create_backup()
            backups = manager.list_backups()

        assert len(backups) == 1
        backup = backups[0]
        assert "id" in backup
        assert "created_at" in backup
        assert "components" in backup
        assert "TestHandler" in backup["components"]

    def test_list_backups_skips_invalid(self, tmp_path):
        """Test list_backups skips directories without valid manifest."""
        # Create valid backup
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            valid_id = manager.create_backup()

        # Create invalid directory
        invalid_dir = tmp_path / "invalid-backup"
        invalid_dir.mkdir()
        (invalid_dir / "manifest.json").write_text("not json")

        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            backups = manager.list_backups()

        # Should only include valid backup
        assert len(backups) == 1
        assert backups[0]["id"] == valid_id


class TestDeleteBackup:
    """Tests for delete_backup method."""

    def test_delete_backup_removes_directory(self, tmp_path):
        """Test delete_backup removes backup directory."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            backup_id = manager.create_backup()

            backup_path = tmp_path / backup_id
            assert backup_path.exists()

            manager.delete_backup(backup_id)

            assert not backup_path.exists()

    def test_delete_backup_not_found(self, tmp_path):
        """Test delete_backup raises for non-existent backup."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            with pytest.raises(BackupNotFoundError):
                manager.delete_backup("nonexistent")

    def test_delete_backup_removes_from_list(self, tmp_path):
        """Test deleted backup is removed from list."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            backup_id = manager.create_backup()
            assert len(manager.list_backups()) == 1

            manager.delete_backup(backup_id)
            assert len(manager.list_backups()) == 0


class TestGetLatestBackup:
    """Tests for _get_latest_backup method."""

    def test_get_latest_backup_none(self, tmp_path):
        """Test _get_latest_backup returns None when no backups."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)
            result = manager._get_latest_backup()

        assert result is None

    def test_get_latest_backup_returns_newest(self, tmp_path):
        """Test _get_latest_backup returns newest backup."""
        with patch("abso.core.backup._get_backup_handlers", return_value=[]):
            manager = BackupManager(tmp_path)

            manager.create_backup()
            import time
            time.sleep(0.1)
            id2 = manager.create_backup()

            result = manager._get_latest_backup()

        assert result.name == id2
