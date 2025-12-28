"""Tests for ProcessPriorityHandler."""

from unittest.mock import patch, MagicMock

import pytest

from abso.settings.process_priority import ProcessPriorityHandler


class TestProcessPriorityInit:
    """Tests for ProcessPriorityHandler initialization."""

    def test_init_with_no_executables(self):
        """Test handler initializes with empty executable list."""
        handler = ProcessPriorityHandler()
        assert handler.executables == []

    def test_init_with_executables(self):
        """Test handler initializes with provided executables."""
        exes = ["game.exe", "Dolphin.exe"]
        handler = ProcessPriorityHandler(executables=exes)
        assert handler.executables == exes


class TestProcessPriorityDetect:
    """Tests for ProcessPriorityHandler.detect()."""

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_detect_returns_processes_dict(self, mock_get_settings):
        """Test detect returns dictionary with processes key."""
        mock_get_settings.return_value = {"gpu_priority": 8}

        handler = ProcessPriorityHandler(executables=["game.exe"])
        result = handler.detect()

        assert "processes" in result
        assert "configured_count" in result

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_detect_queries_all_executables(self, mock_get_settings):
        """Test detect queries all configured executables."""
        mock_get_settings.return_value = {"gpu_priority": 8}

        exes = ["game1.exe", "game2.exe", "game3.exe"]
        handler = ProcessPriorityHandler(executables=exes)
        handler.detect()

        assert mock_get_settings.call_count == len(exes)

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_detect_counts_configured_processes(self, mock_get_settings):
        """Test detect counts processes with settings."""
        mock_get_settings.side_effect = [
            {"gpu_priority": 8},
            {"gpu_priority": None},
        ]

        handler = ProcessPriorityHandler(executables=["a.exe", "b.exe"])
        result = handler.detect()

        assert result["configured_count"] == 1


class TestProcessPriorityAudit:
    """Tests for ProcessPriorityHandler.audit()."""

    @patch.object(ProcessPriorityHandler, "detect")
    def test_audit_no_gpu_priority_creates_issue(self, mock_detect):
        """Test audit creates issue when GPU priority not set."""
        mock_detect.return_value = {
            "processes": {
                "game.exe": {"gpu_priority": None}
            },
            "configured_count": 0,
        }

        handler = ProcessPriorityHandler(executables=["game.exe"])
        issues = handler.audit()

        gpu_issues = [i for i in issues if "GPU priority" in i.title]
        assert len(gpu_issues) >= 1

    @patch.object(ProcessPriorityHandler, "detect")
    def test_audit_optimal_settings_fewer_issues(self, mock_detect):
        """Test audit returns fewer issues when settings are optimal."""
        mock_detect.return_value = {
            "processes": {
                "game.exe": {
                    "gpu_priority": 8,
                    "cpu_priority": 3,
                    "io_priority": 3,
                }
            },
            "configured_count": 1,
        }

        handler = ProcessPriorityHandler(executables=["game.exe"])
        issues = handler.audit()

        # Should not have GPU priority issue since it's set to max
        gpu_issues = [i for i in issues if "GPU priority" in i.title]
        assert len(gpu_issues) == 0


class TestProcessPriorityApply:
    """Tests for ProcessPriorityHandler.apply()."""

    @patch.object(ProcessPriorityHandler, "_set_process_settings")
    def test_apply_sets_process_settings(self, mock_set_settings):
        """Test apply sets process settings."""
        mock_set_settings.return_value = {"success": True}

        handler = ProcessPriorityHandler()
        result = handler.apply({
            "processes": {
                "game.exe": {"gpu_priority": 8}
            }
        })

        assert result["success"] is True
        mock_set_settings.assert_called()

    @patch.object(ProcessPriorityHandler, "_set_process_settings")
    def test_apply_handles_error(self, mock_set_settings):
        """Test apply handles errors gracefully."""
        mock_set_settings.side_effect = PermissionError("Access denied")

        handler = ProcessPriorityHandler()
        result = handler.apply({
            "processes": {
                "game.exe": {"gpu_priority": 8}
            }
        })

        assert result["success"] is False
        assert result["error"] is not None


class TestProcessPriorityBackupRestore:
    """Tests for ProcessPriorityHandler backup/restore."""

    @patch.object(ProcessPriorityHandler, "detect")
    def test_backup_returns_current_state(self, mock_detect):
        """Test backup returns current settings."""
        expected = {"processes": {"game.exe": {"gpu_priority": 8}}}
        mock_detect.return_value = expected

        handler = ProcessPriorityHandler(executables=["game.exe"])
        result = handler.backup()

        assert "processes" in result

    @patch.object(ProcessPriorityHandler, "_set_process_settings")
    def test_restore_applies_backed_up_state(self, mock_set_settings):
        """Test restore applies backed up settings."""
        mock_set_settings.return_value = {"success": True}

        handler = ProcessPriorityHandler()
        result = handler.restore({
            "processes": {
                "game.exe": {"gpu_priority": 8}
            }
        })

        assert result is True
        mock_set_settings.assert_called()
