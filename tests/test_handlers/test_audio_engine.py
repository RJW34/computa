"""Tests for AudioEngineHandler.

All winreg access is mocked; these tests never read or write the real registry.
"""

from unittest.mock import MagicMock, patch

from abso.settings.audio_engine import (
    _FX_VALUE_NAME,
    _RENDER_ROOT,
    AudioEngineHandler,
)


class TestAudioEngineDetect:
    """Tests for AudioEngineHandler.detect()."""

    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value=None)
    def test_detect_no_active_device(self, mock_find):
        """Detect returns None values when no active device is found."""
        result = AudioEngineHandler().detect()

        assert result == {"enhancements_disabled": None, "device_guid": None}

    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=1)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_detect_disabled(self, mock_find, mock_read):
        """Flag of 1 reports enhancements as disabled."""
        result = AudioEngineHandler().detect()

        assert result == {"enhancements_disabled": True, "device_guid": "{g}"}

    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=0)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_detect_enabled(self, mock_find, mock_read):
        """Flag of 0 reports enhancements as enabled."""
        result = AudioEngineHandler().detect()

        assert result["enhancements_disabled"] is False

    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=None)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_detect_absent_flag_is_none(self, mock_find, mock_read):
        """Absent flag (None) yields None enhancements state, not False."""
        result = AudioEngineHandler().detect()

        assert result["enhancements_disabled"] is None


class TestAudioEngineAudit:
    """Tests for AudioEngineHandler.audit()."""

    @patch.object(AudioEngineHandler, "detect")
    def test_audit_flags_enabled_chain(self, mock_detect):
        """An enabled chain on the active device produces one info issue."""
        mock_detect.return_value = {"enhancements_disabled": False, "device_guid": "{g}"}
        issues = AudioEngineHandler().audit()

        assert len(issues) == 1
        assert issues[0].severity == "info"
        assert issues[0].category == "audio"

    @patch.object(AudioEngineHandler, "detect")
    def test_audit_no_issue_when_disabled(self, mock_detect):
        """A disabled chain produces no issue."""
        mock_detect.return_value = {"enhancements_disabled": True, "device_guid": "{g}"}

        assert AudioEngineHandler().audit() == []

    @patch.object(AudioEngineHandler, "detect")
    def test_audit_no_issue_when_unknown(self, mock_detect):
        """An undeterminable state (None) produces no issue."""
        mock_detect.return_value = {"enhancements_disabled": None, "device_guid": None}

        assert AudioEngineHandler().audit() == []


class TestAudioEngineApply:
    """Tests for AudioEngineHandler.apply()."""

    @patch.object(AudioEngineHandler, "_write_fx_flag", return_value=True)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_apply_writes_flag(self, mock_find, mock_write):
        """Apply writes flag=1 and reports the change."""
        result = AudioEngineHandler().apply({"disable_enhancements": True})

        assert result["success"] is True
        assert result["requires_reboot"] is False
        assert result["changed"] is True
        assert "enhancements_disabled" in result["changed_keys"]
        mock_write.assert_called_once_with("{g}", 1)

    @patch.object(AudioEngineHandler, "_write_fx_flag")
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_apply_noop_when_not_requested(self, mock_find, mock_write):
        """Apply does nothing when disable_enhancements is absent/false."""
        result = AudioEngineHandler().apply({})

        assert result["success"] is True
        assert result["changed"] is False
        mock_write.assert_not_called()

    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value=None)
    def test_apply_no_active_device_is_best_effort_warning(self, mock_find):
        """No active device: opt-in add-on warns, never fails the profile apply."""
        result = AudioEngineHandler().apply({"disable_enhancements": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert result["warnings"]

    @patch.object(
        AudioEngineHandler, "_write_fx_flag", side_effect=OSError("Access denied")
    )
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_apply_write_error_is_best_effort_warning(self, mock_find, mock_write):
        """A write OSError surfaces as a warning, not an apply failure."""
        result = AudioEngineHandler().apply({"disable_enhancements": True})

        assert result["success"] is True
        assert result["changed"] is False
        assert result["warnings"]


class TestAudioEngineBackupRestore:
    """Tests for AudioEngineHandler backup/restore."""

    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=0)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_backup_captures_guid_and_flag(self, mock_find, mock_read):
        """Backup records the active guid and the original flag value."""
        result = AudioEngineHandler().backup()

        assert result == {"device_guid": "{g}", "original_flag": 0}

    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value=None)
    def test_backup_no_device(self, mock_find):
        """Backup records None values when there is no active device."""
        result = AudioEngineHandler().backup()

        assert result == {"device_guid": None, "original_flag": None}

    @patch.object(AudioEngineHandler, "_restore_fx_flag")
    def test_restore_writes_captured_flag(self, mock_restore):
        """Restore forwards the captured guid and original flag."""
        result = AudioEngineHandler().restore(
            {"device_guid": "{g}", "original_flag": 0}
        )

        assert result is True
        mock_restore.assert_called_once_with("{g}", 0)

    @patch.object(AudioEngineHandler, "_restore_fx_flag")
    def test_restore_noop_without_guid(self, mock_restore):
        """Restore is a safe no-op when no guid was captured."""
        result = AudioEngineHandler().restore({"device_guid": None})

        assert result is True
        mock_restore.assert_not_called()

    @patch.object(
        AudioEngineHandler, "_restore_fx_flag", side_effect=Exception("boom")
    )
    def test_restore_exception_is_non_blocking(self, mock_restore):
        """Best-effort: restore logs but returns True so a profile switch is
        never blocked by a failed audio-flag revert."""
        result = AudioEngineHandler().restore(
            {"device_guid": "{g}", "original_flag": 1}
        )

        assert result is True


class TestAudioEngineVerify:
    """Tests for AudioEngineHandler.verify_active()."""

    def test_verify_skipped_when_not_requested(self):
        """Verify is a pass-through when disable_enhancements is not requested."""
        result = AudioEngineHandler().verify_active({})

        assert result["all_active"] is True
        assert result["settings"] == {}

    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=1)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_verify_active_when_flag_set(self, mock_find, mock_read):
        """Verify passes when the flag reads 1 on the active device."""
        result = AudioEngineHandler().verify_active({"disable_enhancements": True})

        assert result["all_active"] is True
        assert result["settings"]["enhancements_disabled"]["active"] is True

    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=0)
    @patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}")
    def test_verify_fails_when_flag_unset(self, mock_find, mock_read):
        """Verify fails when the flag does not read 1."""
        result = AudioEngineHandler().verify_active({"disable_enhancements": True})

        assert result["all_active"] is False
        assert result["settings"]["enhancements_disabled"]["active"] is False


class TestAudioEngineProperties:
    """Tests for handler capability flags."""

    def test_is_critical_verify_false(self):
        """Opt-in best-effort add-on: verify miss is a warning, not critical."""
        assert AudioEngineHandler().is_critical_verify is False

    def test_restore_guarantee_partial(self):
        """Best-effort revert -> partial guarantee (non-blocking)."""
        assert AudioEngineHandler().restore_guarantee == "partial"


class TestAudioEngineRegistryHelpers:
    """Tests for the winreg-backed helpers (all winreg calls mocked)."""

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.QueryValueEx")
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    @patch("abso.settings.audio_engine.winreg.EnumKey")
    def test_find_active_device_returns_active_guid(
        self, mock_enum, mock_open, mock_query, mock_close
    ):
        """The first device with DeviceState==1 is returned."""
        mock_enum.side_effect = ["{inactive}", "{active}", OSError("end")]
        mock_open.return_value = MagicMock()
        # DeviceState for inactive then active device.
        mock_query.side_effect = [(0, 1), (1, 1)]

        guid = AudioEngineHandler._find_active_device_guid()

        assert guid == "{active}"

    @patch(
        "abso.settings.audio_engine.winreg.OpenKey", side_effect=FileNotFoundError
    )
    def test_find_active_device_missing_root(self, mock_open):
        """A missing render root degrades to None, not a crash."""
        assert AudioEngineHandler._find_active_device_guid() is None

    @patch(
        "abso.settings.audio_engine.winreg.OpenKey", side_effect=PermissionError
    )
    def test_find_active_device_access_denied(self, mock_open):
        """Access-denied on the render root degrades to None."""
        assert AudioEngineHandler._find_active_device_guid() is None

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.QueryValueEx")
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    def test_read_fx_flag_returns_value(self, mock_open, mock_query, mock_close):
        """A present flag is returned as an int."""
        mock_open.return_value = MagicMock()
        mock_query.return_value = (1, 4)

        assert AudioEngineHandler._read_fx_flag("{g}") == 1

    def test_read_fx_flag_no_guid(self):
        """A missing guid short-circuits to None."""
        assert AudioEngineHandler._read_fx_flag(None) is None

    @patch(
        "abso.settings.audio_engine.winreg.OpenKey", side_effect=FileNotFoundError
    )
    def test_read_fx_flag_missing_key(self, mock_open):
        """A missing FxProperties key yields None."""
        assert AudioEngineHandler._read_fx_flag("{g}") is None

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.QueryValueEx", side_effect=FileNotFoundError)
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    def test_read_fx_flag_missing_value(self, mock_open, mock_query, mock_close):
        """A present key but absent value yields None."""
        mock_open.return_value = MagicMock()

        assert AudioEngineHandler._read_fx_flag("{g}") is None

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.SetValueEx")
    @patch("abso.settings.audio_engine.winreg.CreateKeyEx")
    def test_write_fx_flag_creates_subkey(self, mock_create, mock_set, mock_close):
        """Write uses CreateKeyEx so a missing FxProperties subkey is created."""
        mock_create.return_value = MagicMock()

        assert AudioEngineHandler._write_fx_flag("{g}", 1) is True
        # FxProperties path passed to CreateKeyEx.
        assert "FxProperties" in mock_create.call_args[0][1]
        mock_set.assert_called_once()
        # REG_DWORD value 1 written under the documented value name.
        args = mock_set.call_args[0]
        assert args[1] == _FX_VALUE_NAME
        assert args[4] == 1

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.SetValueEx")
    @patch("abso.settings.audio_engine.winreg.CreateKeyEx")
    def test_restore_fx_flag_writes_original(self, mock_create, mock_set, mock_close):
        """Restoring a present original re-writes it via CreateKeyEx."""
        mock_create.return_value = MagicMock()

        AudioEngineHandler._restore_fx_flag("{g}", 0)

        mock_set.assert_called_once()
        assert mock_set.call_args[0][4] == 0

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.DeleteValue")
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    def test_restore_fx_flag_deletes_when_absent(
        self, mock_open, mock_delete, mock_close
    ):
        """Restoring a None original deletes ABSO's injected value."""
        mock_open.return_value = MagicMock()

        AudioEngineHandler._restore_fx_flag("{g}", None)

        mock_delete.assert_called_once()
        assert mock_delete.call_args[0][1] == _FX_VALUE_NAME

    @patch(
        "abso.settings.audio_engine.winreg.OpenKey", side_effect=FileNotFoundError
    )
    def test_restore_fx_flag_absent_no_key(self, mock_open):
        """Deleting from a missing key is a safe no-op (no raise)."""
        # Should not raise.
        AudioEngineHandler._restore_fx_flag("{g}", None)

    def test_render_root_constant(self):
        """The render root constant matches the documented MMDevices path."""
        assert _RENDER_ROOT.endswith(r"MMDevices\Audio\Render")
