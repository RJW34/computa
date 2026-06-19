"""Tests for TasksSettingsHandler."""

from unittest.mock import patch

from abso.settings.tasks import TasksSettingsHandler


class TestTasksDetect:
    """Tests for TasksSettingsHandler.detect()."""

    @patch.object(TasksSettingsHandler, "_get_task_info")
    def test_detect_returns_tasks_dict(self, mock_get_info):
        """Test detect returns dictionary with tasks key."""
        mock_get_info.return_value = {"exists": True, "state": "Ready"}

        handler = TasksSettingsHandler()
        result = handler.detect()

        assert "tasks" in result
        assert isinstance(result["tasks"], dict)

    @patch.object(TasksSettingsHandler, "_get_task_info")
    def test_detect_queries_all_gaming_tasks(self, mock_get_info):
        """Test detect queries all configured gaming tasks."""
        mock_get_info.return_value = {"exists": True, "state": "Disabled"}

        handler = TasksSettingsHandler()
        handler.detect()

        assert mock_get_info.call_count == len(handler.GAMING_TASKS)

    @patch.object(TasksSettingsHandler, "_get_task_info")
    def test_detect_handles_missing_task(self, mock_get_info):
        """Test detect handles tasks that don't exist."""
        mock_get_info.return_value = {"exists": False}

        handler = TasksSettingsHandler()
        result = handler.detect()

        assert result is not None


class TestTasksAudit:
    """Tests for TasksSettingsHandler.audit()."""

    @patch.object(TasksSettingsHandler, "detect")
    def test_audit_enabled_task_creates_issue(self, mock_detect):
        """Test audit creates issue when telemetry task is enabled."""
        mock_detect.return_value = {
            "tasks": {
                r"\Microsoft\Windows\Application Experience\Microsoft Compatibility Appraiser": {
                    "exists": True,
                    "state": "Ready",
                },
            }
        }

        handler = TasksSettingsHandler()
        issues = handler.audit()

        assert len(issues) >= 1
        assert any("Compatibility Appraiser" in i.title for i in issues)

    @patch.object(TasksSettingsHandler, "detect")
    def test_audit_disabled_tasks_no_issues(self, mock_detect):
        """Test audit returns no issues when tasks are disabled."""
        # Create mock data with all tasks disabled
        mock_detect.return_value = {
            "tasks": {
                path: {"exists": True, "state": "Disabled"}
                for path in TasksSettingsHandler.GAMING_TASKS
            }
        }

        handler = TasksSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0

    @patch.object(TasksSettingsHandler, "detect")
    def test_audit_skips_nonexistent_tasks(self, mock_detect):
        """Test audit skips tasks that don't exist."""
        mock_detect.return_value = {
            "tasks": {
                path: {"exists": False}
                for path in TasksSettingsHandler.GAMING_TASKS
            }
        }

        handler = TasksSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0


class TestTasksApply:
    """Tests for TasksSettingsHandler.apply()."""

    @patch.object(TasksSettingsHandler, "_set_task_enabled")
    def test_apply_disables_task(self, mock_set_enabled):
        """Test apply can disable a task."""
        mock_set_enabled.return_value = {"success": True}

        handler = TasksSettingsHandler()
        result = handler.apply({
            "tasks": {
                r"\Microsoft\Windows\Test\Task": {"enabled": False}
            }
        })

        assert result["success"] is True
        mock_set_enabled.assert_called()

    @patch.object(TasksSettingsHandler, "_set_task_enabled")
    def test_apply_preset_gaming(self, mock_set_enabled):
        """Test apply with gaming preset disables telemetry tasks."""
        mock_set_enabled.return_value = {"success": True}

        handler = TasksSettingsHandler()
        result = handler.apply({"preset": "gaming"})

        assert result["success"] is True
        # Should have called _set_task_enabled for each task to disable
        assert mock_set_enabled.call_count > 0

    @patch.object(TasksSettingsHandler, "_set_task_enabled")
    def test_apply_handles_error(self, mock_set_enabled):
        """Test apply handles errors gracefully."""
        mock_set_enabled.side_effect = RuntimeError("Failed to change task")

        handler = TasksSettingsHandler()
        result = handler.apply({
            "tasks": {
                r"\Microsoft\Windows\Test\Task": {"enabled": False}
            }
        })

        assert result["success"] is False
        assert result["error"] is not None


class TestTasksBackupRestore:
    """Tests for TasksSettingsHandler backup/restore."""

    @patch.object(TasksSettingsHandler, "detect")
    def test_backup_returns_task_states(self, mock_detect):
        """Test backup returns current task states."""
        expected = {
            "tasks": {
                r"\Microsoft\Windows\Test\Task": {"exists": True, "state": "Ready"}
            }
        }
        mock_detect.return_value = expected

        handler = TasksSettingsHandler()
        result = handler.backup()

        assert "tasks" in result

    @patch.object(TasksSettingsHandler, "_set_task_enabled")
    def test_restore_applies_backed_up_states(self, mock_set_enabled):
        """Test restore applies backed up task states."""
        mock_set_enabled.return_value = {"success": True}

        handler = TasksSettingsHandler()
        result = handler.restore({
            "tasks": {
                r"\Microsoft\Windows\Test\Task": {"exists": True, "state": "Ready"}
            }
        })

        assert result is True
        mock_set_enabled.assert_called()

    @patch.object(TasksSettingsHandler, "_set_task_enabled")
    def test_restore_keeps_disabled_task_disabled(self, mock_set_enabled):
        """A disabled-but-ready task must NOT be re-enabled on restore.

        ``Status: Ready`` is runtime readiness; ``Scheduled Task State`` is the
        authoritative Enabled/Disabled flag. Keying off Status would wrongly
        re-enable a task the user had disabled.
        """
        mock_set_enabled.return_value = {"success": True}
        handler = TasksSettingsHandler()
        task = r"\Microsoft\Windows\Test\DisabledTask"
        handler.restore({
            "tasks": {
                task: {
                    "exists": True,
                    "state": "Ready",
                    "scheduled_task_state": "Disabled",
                }
            }
        })

        mock_set_enabled.assert_called_once_with(task, False)

    def test_was_task_enabled_prefers_scheduled_task_state(self):
        assert TasksSettingsHandler._was_task_enabled(
            {"state": "Ready", "scheduled_task_state": "Enabled"}
        ) is True
        assert TasksSettingsHandler._was_task_enabled(
            {"state": "Ready", "scheduled_task_state": "Disabled"}
        ) is False

    def test_was_task_enabled_legacy_fallback_uses_status(self):
        # Legacy backup without the authoritative field falls back to Status.
        assert TasksSettingsHandler._was_task_enabled({"state": "Ready"}) is True
        assert TasksSettingsHandler._was_task_enabled({"state": "Disabled"}) is False
