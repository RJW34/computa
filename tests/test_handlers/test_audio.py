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

    @patch.object(AudioSettingsHandler, "_set_audio_priority", side_effect=Exception("Error"))
    def test_restore_handles_exception(self, mock_set):
        """Test restore handles exceptions gracefully."""
        handler = AudioSettingsHandler()
        result = handler.restore({"audio_service_priority": "High"})

        assert result is False


class TestAudioPrivateMethods:
    """Tests for private helper methods."""

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.QueryValueEx")
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_get_audio_priority_returns_value(self, mock_open, mock_query, mock_close):
        """Test _get_audio_priority returns scheduling category."""
        mock_query.return_value = ("High", 1)

        handler = AudioSettingsHandler()
        result = handler._get_audio_priority()

        assert result == "High"

    @patch("abso.settings.audio.winreg.OpenKey", side_effect=FileNotFoundError)
    def test_get_audio_priority_handles_missing_key(self, mock_open):
        """Test _get_audio_priority handles missing key."""
        handler = AudioSettingsHandler()
        result = handler._get_audio_priority()

        assert result is None

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.QueryValueEx", side_effect=FileNotFoundError)
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_get_audio_priority_handles_missing_value(self, mock_open, mock_query, mock_close):
        """Test _get_audio_priority handles missing value."""
        handler = AudioSettingsHandler()
        result = handler._get_audio_priority()

        assert result is None

    @patch("abso.settings.audio.winreg.OpenKey", side_effect=Exception("Error"))
    def test_get_audio_priority_handles_exception(self, mock_open):
        """Test _get_audio_priority handles exception."""
        handler = AudioSettingsHandler()
        result = handler._get_audio_priority()

        assert result is None

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.SetValueEx")
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_set_audio_priority_writes_value(self, mock_open, mock_set, mock_close):
        """Test _set_audio_priority writes to registry."""
        handler = AudioSettingsHandler()
        handler._set_audio_priority("High")

        # Should set multiple values
        assert mock_set.call_count >= 1

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.SetValueEx")
    @patch("abso.settings.audio.winreg.CreateKey")
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_set_audio_priority_creates_key_if_missing(self, mock_open, mock_create, mock_set, mock_close):
        """Test _set_audio_priority creates key if missing."""
        from unittest.mock import MagicMock
        # First OpenKey fails (Audio task key missing), second succeeds (Tasks key)
        mock_open.side_effect = [FileNotFoundError, MagicMock()]
        mock_create.return_value = MagicMock()

        handler = AudioSettingsHandler()
        handler._set_audio_priority("High")

        mock_create.assert_called_once()

    @patch("abso.settings.audio.winreg.OpenKey", side_effect=FileNotFoundError)
    def test_get_audio_enhancements_handles_missing_mmdevices(self, mock_open):
        """Test _get_audio_enhancements_disabled handles missing MMDevices."""
        handler = AudioSettingsHandler()
        result = handler._get_audio_enhancements_disabled()

        assert result is None

    @patch("abso.settings.audio.winreg.OpenKey", side_effect=PermissionError)
    def test_get_audio_enhancements_handles_permission_error(self, mock_open):
        """Test _get_audio_enhancements_disabled handles permission error."""
        handler = AudioSettingsHandler()
        result = handler._get_audio_enhancements_disabled()

        assert result is None

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.EnumKey")
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_get_audio_enhancements_enumerates_devices(self, mock_open, mock_enum, mock_close):
        """Test _get_audio_enhancements_disabled enumerates audio devices."""
        from unittest.mock import MagicMock
        # Make EnumKey raise OSError after first call to simulate end of enumeration
        mock_enum.side_effect = ["{device-guid}", OSError("No more data")]
        mock_open.return_value = MagicMock()

        # Mock the device state check
        with patch("abso.settings.audio.winreg.QueryValueEx") as mock_query:
            mock_query.return_value = (0, 1)  # Not active device

            handler = AudioSettingsHandler()
            handler._get_audio_enhancements_disabled()

            # Should try to enumerate devices
            mock_enum.assert_called()

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.EnumKey")
    @patch("abso.settings.audio.winreg.QueryValueEx")
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_get_audio_enhancements_finds_active_device(self, mock_open, mock_query, mock_enum, mock_close):
        """Test _get_audio_enhancements_disabled finds active device."""
        from unittest.mock import MagicMock
        mock_enum.side_effect = ["{device-guid}", OSError("No more data")]
        mock_open.return_value = MagicMock()
        # First query is DeviceState=1 (active), second is DisableAllEnhancements
        mock_query.side_effect = [(1, 1), (1, 1)]

        handler = AudioSettingsHandler()
        result = handler._get_audio_enhancements_disabled()

        assert result is True

    @patch("abso.settings.audio.winreg.CloseKey")
    @patch("abso.settings.audio.winreg.EnumKey")
    @patch("abso.settings.audio.winreg.QueryValueEx")
    @patch("abso.settings.audio.winreg.OpenKey")
    def test_get_audio_enhancements_returns_false_no_fx_key(self, mock_open, mock_query, mock_enum, mock_close):
        """Test _get_audio_enhancements_disabled returns False when no FxProperties key."""
        from unittest.mock import MagicMock
        mock_enum.side_effect = ["{device-guid}", OSError("No more data")]
        # Device state query succeeds, then FxProperties open fails
        mock_open.side_effect = [MagicMock(), MagicMock(), FileNotFoundError]
        mock_query.return_value = (1, 1)  # Active device

        handler = AudioSettingsHandler()
        result = handler._get_audio_enhancements_disabled()

        assert result is False
