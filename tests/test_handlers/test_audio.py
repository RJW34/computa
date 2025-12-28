"""Tests for AudioSettingsHandler."""

from unittest.mock import patch

from abso.settings.audio import AudioSettingsHandler


class TestAudioDetect:
    """Tests for AudioSettingsHandler.detect()."""

    @patch.object(AudioSettingsHandler, "_get_audio_enhancements_disabled")
    @patch.object(AudioSettingsHandler, "_get_audio_priority")
    def test_detect_returns_audio_settings(self, mock_priority, mock_enhancements):
        """Test detect returns dictionary with audio settings."""
        mock_enhancements.return_value = False
        mock_priority.return_value = "Normal"

        handler = AudioSettingsHandler()
        result = handler.detect()

        assert "disable_audio_enhancements" in result
        assert "audio_service_priority" in result

    @patch.object(AudioSettingsHandler, "_get_audio_enhancements_disabled")
    @patch.object(AudioSettingsHandler, "_get_audio_priority")
    def test_detect_handles_none_values(self, mock_priority, mock_enhancements):
        """Test detect handles None values gracefully."""
        mock_enhancements.return_value = None
        mock_priority.return_value = None

        handler = AudioSettingsHandler()
        result = handler.detect()

        assert result is not None


class TestAudioAudit:
    """Tests for AudioSettingsHandler.audit()."""

    @patch.object(AudioSettingsHandler, "detect")
    def test_audit_low_priority_creates_issue(self, mock_detect):
        """Test audit creates issue when audio priority is not high."""
        mock_detect.return_value = {
            "audio_service_priority": "Normal",
            "disable_audio_enhancements": False,
        }

        handler = AudioSettingsHandler()
        issues = handler.audit()

        priority_issues = [i for i in issues if "priority" in i.title.lower()]
        assert len(priority_issues) >= 1

    @patch.object(AudioSettingsHandler, "detect")
    def test_audit_high_priority_no_issues(self, mock_detect):
        """Test audit returns no issues when priority is high."""
        mock_detect.return_value = {
            "audio_service_priority": "High",
            "disable_audio_enhancements": True,
        }

        handler = AudioSettingsHandler()
        issues = handler.audit()

        priority_issues = [i for i in issues if "priority" in i.title.lower()]
        assert len(priority_issues) == 0


class TestAudioApply:
    """Tests for AudioSettingsHandler.apply()."""

    @patch.object(AudioSettingsHandler, "_set_audio_priority")
    def test_apply_sets_high_priority(self, mock_set_priority):
        """Test apply sets high audio priority."""
        handler = AudioSettingsHandler()
        result = handler.apply({"high_priority": True})

        assert result["success"] is True
        mock_set_priority.assert_called_with("High")

    @patch.object(AudioSettingsHandler, "_set_audio_priority")
    def test_apply_handles_error(self, mock_set_priority):
        """Test apply handles errors gracefully."""
        mock_set_priority.side_effect = PermissionError("Access denied")

        handler = AudioSettingsHandler()
        result = handler.apply({"high_priority": True})

        assert result["success"] is False
        assert result["error"] is not None


class TestAudioBackupRestore:
    """Tests for AudioSettingsHandler backup/restore."""

    @patch.object(AudioSettingsHandler, "detect")
    def test_backup_returns_current_state(self, mock_detect):
        """Test backup returns current audio settings."""
        expected = {"audio_service_priority": "High"}
        mock_detect.return_value = expected

        handler = AudioSettingsHandler()
        result = handler.backup()

        assert "audio_service_priority" in result

    @patch.object(AudioSettingsHandler, "_set_audio_priority")
    def test_restore_applies_backed_up_state(self, mock_set_priority):
        """Test restore applies backed up settings."""
        handler = AudioSettingsHandler()
        result = handler.restore({"audio_service_priority": "High"})

        assert result is True
        mock_set_priority.assert_called_with("High")

    def test_restore_handles_missing_data(self):
        """Test restore handles missing data gracefully."""
        handler = AudioSettingsHandler()
        result = handler.restore({})

        assert result is True
