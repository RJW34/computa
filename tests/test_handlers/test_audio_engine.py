"""Tests for AudioEngineHandler.

All winreg access is mocked; these tests never read or write the real registry.
"""

from unittest.mock import MagicMock, patch

import pytest

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
    def test_restore_exception_reports_failure(self, mock_restore):
        """An unsuccessful revert must remain visible to transaction rollback."""
        result = AudioEngineHandler().restore(
            {"device_guid": "{g}", "original_flag": 1}
        )

        assert result is False


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
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=None)
    def test_write_fx_flag_creates_subkey(
        self, mock_read, mock_open, mock_create, mock_set, mock_close
    ):
        """Write uses CreateKeyEx so a missing FxProperties subkey is created."""
        mock_create.return_value = MagicMock()
        device_key = MagicMock()
        mock_open.side_effect = [device_key, FileNotFoundError()]

        assert AudioEngineHandler._write_fx_flag("{g}", 1) is True
        # Only FxProperties may be created, beneath an existing endpoint.
        assert mock_create.call_args[0][:2] == (device_key, "FxProperties")
        mock_set.assert_called_once()
        # REG_DWORD value 1 written under the documented value name.
        args = mock_set.call_args[0]
        assert args[1] == _FX_VALUE_NAME
        assert args[4] == 1

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.SetValueEx")
    @patch("abso.settings.audio_engine.winreg.CreateKeyEx")
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=1)
    def test_restore_fx_flag_writes_original(
        self, mock_read, mock_open, mock_create, mock_set, mock_close
    ):
        """An existing FxProperties key needs set-value access, not creation."""

        AudioEngineHandler._restore_fx_flag("{g}", 0)

        mock_set.assert_called_once()
        assert mock_set.call_args[0][4] == 0
        mock_create.assert_not_called()
        assert mock_open.call_args[0][:2] == (mock_open.return_value, "FxProperties")

    @patch("abso.settings.audio_engine.winreg.CloseKey")
    @patch("abso.settings.audio_engine.winreg.DeleteValue")
    @patch("abso.settings.audio_engine.winreg.OpenKey")
    @patch.object(AudioEngineHandler, "_read_fx_flag", return_value=1)
    def test_restore_fx_flag_deletes_when_absent(
        self, mock_read, mock_open, mock_delete, mock_close
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


class TestAudioEngineRestoreEndpointChanges:
    """Restore must tolerate endpoint removal without hiding real failures."""

    @pytest.mark.parametrize("original", [None, 0, 1])
    def test_removed_endpoint_is_not_recreated(self, original, caplog):
        # The failed 2026-09-20 switch referenced a removed baseline endpoint.
        with patch("abso.settings.audio_engine.winreg") as registry:
            registry.OpenKey.side_effect = FileNotFoundError("Endpoint removed")

            assert AudioEngineHandler().restore(
                {"device_guid": "{old-device}", "original_flag": original}
            ) is True

            registry.CreateKeyEx.assert_not_called()
            registry.SetValueEx.assert_not_called()
            registry.DeleteValue.assert_not_called()
            assert "no longer exists" in caplog.text

    @pytest.mark.parametrize("original", [None, 0, 1])
    def test_matching_flag_needs_only_read_access(self, original):
        with patch("abso.settings.audio_engine.winreg") as registry:
            if original is None:
                registry.QueryValueEx.side_effect = FileNotFoundError("Value absent")
            else:
                registry.QueryValueEx.return_value = (original, registry.REG_DWORD)
            registry.CreateKeyEx.side_effect = PermissionError("Writes forbidden")

            assert AudioEngineHandler().restore(
                {"device_guid": "{g}", "original_flag": original}
            ) is True

            assert all(call.args[3] == registry.KEY_READ for call in registry.OpenKey.call_args_list)
            registry.CreateKeyEx.assert_not_called()
            registry.SetValueEx.assert_not_called()
            registry.DeleteValue.assert_not_called()

    @pytest.mark.parametrize("failure_point", ["endpoint", "fx_key", "value"])
    def test_unreadable_state_does_not_become_absence(self, failure_point):
        with patch("abso.settings.audio_engine.winreg") as registry:
            denied = PermissionError("Read access denied")
            if failure_point == "endpoint":
                registry.OpenKey.side_effect = denied
            elif failure_point == "fx_key":
                registry.OpenKey.side_effect = [MagicMock(), denied]
            else:
                registry.QueryValueEx.side_effect = denied

            assert AudioEngineHandler().restore(
                {"device_guid": "{g}", "original_flag": None}
            ) is False

            registry.CreateKeyEx.assert_not_called()
            registry.SetValueEx.assert_not_called()
            registry.DeleteValue.assert_not_called()

    def test_changed_flag_write_denial_remains_failure(self):
        with patch("abso.settings.audio_engine.winreg") as registry:
            registry.QueryValueEx.return_value = (1, registry.REG_DWORD)
            registry.SetValueEx.side_effect = PermissionError("Write access denied")

            assert AudioEngineHandler().restore(
                {"device_guid": "{g}", "original_flag": 0}
            ) is False

    def test_delete_denial_remains_failure(self):
        with patch("abso.settings.audio_engine.winreg") as registry:
            registry.QueryValueEx.return_value = (1, registry.REG_DWORD)
            registry.DeleteValue.side_effect = PermissionError("Delete access denied")

            assert AudioEngineHandler().restore(
                {"device_guid": "{g}", "original_flag": None}
            ) is False

    def test_missing_fx_subkey_is_restored_only_beneath_existing_endpoint(self):
        with patch("abso.settings.audio_engine.winreg") as registry:
            device_key = MagicMock(name="existing_endpoint")
            registry.OpenKey.side_effect = [
                device_key, FileNotFoundError("Fx key absent"), FileNotFoundError("Fx key absent")
            ]

            assert AudioEngineHandler().restore(
                {"device_guid": "{g}", "original_flag": 1}
            ) is True

            registry.CreateKeyEx.assert_called_once_with(
                device_key, "FxProperties", 0, registry.KEY_SET_VALUE
            )
            registry.SetValueEx.assert_called_once_with(
                registry.CreateKeyEx.return_value, _FX_VALUE_NAME, 0, registry.REG_DWORD, 1
            )

    def test_incomplete_snapshot_does_not_delete_live_value(self):
        with patch("abso.settings.audio_engine.winreg") as registry:
            assert AudioEngineHandler().restore({"device_guid": "{g}"}) is False
            registry.OpenKey.assert_not_called()
            registry.DeleteValue.assert_not_called()

    @pytest.mark.parametrize("failure_point", ["fx_key", "value"])
    def test_backup_propagates_read_failure_instead_of_capturing_absence(self, failure_point):
        with (
            patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}"),
            patch("abso.settings.audio_engine.winreg") as registry,
        ):
            if failure_point == "fx_key":
                registry.OpenKey.side_effect = PermissionError("Cannot capture")
            else:
                registry.QueryValueEx.side_effect = PermissionError("Cannot capture")

            with pytest.raises(PermissionError, match="Cannot capture"):
                AudioEngineHandler().backup()

    def test_apply_matching_flag_avoids_write_and_false_change(self):
        with (
            patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}"),
            patch("abso.settings.audio_engine.winreg") as registry,
        ):
            registry.QueryValueEx.return_value = (1, registry.REG_DWORD)
            registry.CreateKeyEx.side_effect = PermissionError("Writes forbidden")

            result = AudioEngineHandler().apply({"disable_enhancements": True})

            assert result["success"] is True
            assert result["changed"] is False
            assert not result["warnings"]
            registry.CreateKeyEx.assert_not_called()
            registry.SetValueEx.assert_not_called()

    def test_apply_does_not_recreate_removed_endpoint(self):
        with (
            patch.object(AudioEngineHandler, "_find_active_device_guid", return_value="{g}"),
            patch("abso.settings.audio_engine.winreg") as registry,
        ):
            registry.OpenKey.side_effect = FileNotFoundError("Endpoint removed")

            result = AudioEngineHandler().apply({"disable_enhancements": True})

            assert result["success"] is True
            assert result["changed"] is False
            assert result["warnings"]
            registry.CreateKeyEx.assert_not_called()
            registry.SetValueEx.assert_not_called()
