"""Tests for ProcessPriorityHandler."""

from unittest.mock import patch

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
        mock_get_settings.return_value = {"cpu_priority": 3}

        handler = ProcessPriorityHandler(executables=["game.exe"])
        result = handler.detect()

        assert "processes" in result
        assert "configured_count" in result

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_detect_queries_all_executables(self, mock_get_settings):
        """Test detect queries all configured executables."""
        mock_get_settings.return_value = {"cpu_priority": 3}

        exes = ["game1.exe", "game2.exe", "game3.exe"]
        handler = ProcessPriorityHandler(executables=exes)
        handler.detect()

        assert mock_get_settings.call_count == len(exes)

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_detect_counts_configured_processes(self, mock_get_settings):
        """Test detect counts processes with settings."""
        mock_get_settings.side_effect = [
            {"cpu_priority": 3},
            {"cpu_priority": None},
        ]

        handler = ProcessPriorityHandler(executables=["a.exe", "b.exe"])
        result = handler.detect()

        assert result["configured_count"] == 1


class TestProcessPriorityAudit:
    """Tests for ProcessPriorityHandler.audit()."""

    @patch.object(ProcessPriorityHandler, "detect")
    def test_audit_missing_cpu_priority_creates_issue(self, mock_detect):
        """Test audit creates issue when CPU priority not set."""
        mock_detect.return_value = {
            "processes": {
                "game.exe": {"cpu_priority": None, "io_priority": None}
            },
            "configured_count": 0,
        }

        handler = ProcessPriorityHandler(executables=["game.exe"])
        issues = handler.audit()

        cpu_issues = [i for i in issues if "CPU priority" in i.title]
        assert len(cpu_issues) >= 1

    @patch.object(ProcessPriorityHandler, "detect")
    def test_audit_optimal_settings_fewer_issues(self, mock_detect):
        """Test audit returns fewer issues when settings are optimal."""
        mock_detect.return_value = {
            "processes": {
                "game.exe": {
                    "cpu_priority": 3,
                    "io_priority": 2,
                }
            },
            "configured_count": 1,
        }

        handler = ProcessPriorityHandler(executables=["game.exe"])
        issues = handler.audit()

        cpu_issues = [i for i in issues if "CPU priority" in i.title]
        io_issues = [i for i in issues if "I/O priority" in i.title]
        assert len(cpu_issues) == 0
        assert len(io_issues) == 0


class TestProcessPriorityApply:
    """Tests for ProcessPriorityHandler.apply()."""

    @patch.object(ProcessPriorityHandler, "_set_process_settings")
    def test_apply_sets_process_settings(self, mock_set_settings):
        """Test apply sets process settings."""
        mock_set_settings.return_value = {"success": True}

        handler = ProcessPriorityHandler()
        result = handler.apply({
            "processes": {
                "game.exe": {"cpu_priority": 3}
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
                "game.exe": {"cpu_priority": 3}
            }
        })

        assert result["success"] is False
        assert result["error"] is not None


class TestProcessPriorityBackupRestore:
    """Tests for ProcessPriorityHandler backup/restore."""

    @patch.object(ProcessPriorityHandler, "detect")
    def test_backup_returns_current_state(self, mock_detect):
        """Test backup returns current settings."""
        expected = {"processes": {"game.exe": {"cpu_priority": 3}}}
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
                "game.exe": {"cpu_priority": 3}
            }
        })

        assert result is True
        mock_set_settings.assert_called()

    @patch.object(ProcessPriorityHandler, "_remove_process_settings")
    @patch.object(ProcessPriorityHandler, "_set_process_settings")
    def test_restore_removes_empty_backed_up_state(self, mock_set_settings, mock_remove):
        handler = ProcessPriorityHandler()
        result = handler.restore({
            "processes": {
                "game.exe": {
                    "gpu_priority": None,
                    "cpu_priority": None,
                    "io_priority": None,
                    "page_priority": None,
                }
            }
        })

        assert result is True
        mock_set_settings.assert_not_called()
        mock_remove.assert_called_once_with("game.exe")


class TestProcessPriorityVerify:
    """Tests for verify_active()."""

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_verify_active_reports_success(self, mock_get_settings):
        mock_get_settings.return_value = {
            "gpu_priority": None,
            "cpu_priority": 3,
            "io_priority": 2,
            "page_priority": None,
        }

        handler = ProcessPriorityHandler(executables=["game.exe"])
        result = handler.verify_active({"cpu_priority": 3, "io_priority": 2})

        assert result["all_active"] is True
        assert result["settings"]["game.exe:cpu_priority"]["active"] is True

    @patch.object(ProcessPriorityHandler, "_get_process_settings")
    def test_verify_active_reports_mismatch(self, mock_get_settings):
        mock_get_settings.return_value = {
            "gpu_priority": None,
            "cpu_priority": 2,
            "io_priority": 1,
            "page_priority": None,
        }

        handler = ProcessPriorityHandler(executables=["game.exe"])
        result = handler.verify_active({"cpu_priority": 3, "io_priority": 2})

        assert result["all_active"] is False
        assert result["settings"]["game.exe:cpu_priority"]["active"] is False
        assert result["settings"]["game.exe:io_priority"]["active"] is False
