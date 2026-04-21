"""Tests for registry settings handler."""

from unittest.mock import patch

import pytest

from abso.core.exceptions import RegistryWriteError
from abso.settings.registry import RegistrySettingsHandler


class TestRegistrySettingsHandlerConstants:
    """Tests for RegistrySettingsHandler constants."""

    def test_win32_priority_constants(self):
        """Test Win32PrioritySeparation constants are defined."""
        assert RegistrySettingsHandler.WIN32_PRIORITY_DEFAULT == 0x26
        assert RegistrySettingsHandler.WIN32_PRIORITY_GAMING == 0x2A

    def test_registry_paths_are_strings(self):
        """Test registry paths are defined."""
        assert isinstance(RegistrySettingsHandler.MULTIMEDIA_KEY, str)
        assert isinstance(RegistrySettingsHandler.GAMES_TASK_KEY, str)
        assert isinstance(RegistrySettingsHandler.APPCOMPAT_KEY, str)
        assert isinstance(RegistrySettingsHandler.PRIORITY_CONTROL_KEY, str)


class TestRegistrySettingsHandlerDetect:
    """Tests for detect method."""

    @patch.object(RegistrySettingsHandler, "_get_win32_priority_separation", return_value=0x26)
    @patch.object(RegistrySettingsHandler, "_get_game_priority", return_value={"priority": 6})
    @patch.object(RegistrySettingsHandler, "_get_network_throttling", return_value=0xFFFFFFFF)
    @patch.object(RegistrySettingsHandler, "_get_system_responsiveness", return_value=0)
    def test_detect_returns_expected_keys(self, *mocks):
        """Test detect returns dictionary with expected keys."""
        handler = RegistrySettingsHandler()
        result = handler.detect()

        assert "system_responsiveness" in result
        assert "network_throttling" in result
        assert "game_priority" in result
        assert "win32_priority_separation" in result

    @patch.object(RegistrySettingsHandler, "_get_win32_priority_separation", return_value=0x2A)
    @patch.object(RegistrySettingsHandler, "_get_game_priority", return_value={"priority": 6, "gpu_priority": 8})
    @patch.object(RegistrySettingsHandler, "_get_network_throttling", return_value=0xFFFFFFFF)
    @patch.object(RegistrySettingsHandler, "_get_system_responsiveness", return_value=0)
    def test_detect_optimal_settings(self, *mocks):
        """Test detect with optimal settings."""
        handler = RegistrySettingsHandler()
        result = handler.detect()

        assert result["system_responsiveness"] == 0
        assert result["network_throttling"] == 0xFFFFFFFF
        assert result["game_priority"]["priority"] == 6
        assert result["win32_priority_separation"] == 0x2A


class TestRegistrySettingsHandlerAudit:
    """Tests for audit method."""

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_no_issues_when_optimal(self, mock_detect):
        """Test audit returns no issues when all settings are optimal."""
        mock_detect.return_value = {
            "system_responsiveness": 10,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_non_zero_responsiveness(self, mock_detect):
        """Test audit detects non-zero system responsiveness."""
        mock_detect.return_value = {
            "system_responsiveness": 20,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        responsiveness_issues = [i for i in issues if "Responsiveness" in i.title]
        assert len(responsiveness_issues) == 1
        assert responsiveness_issues[0].severity == "info"
        assert responsiveness_issues[0].evidence_tier.value == "legacy_unverified"

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_network_throttling(self, mock_detect):
        """Test audit detects enabled network throttling."""
        mock_detect.return_value = {
            "system_responsiveness": 0,
            "network_throttling": 10,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        throttling_issues = [i for i in issues if "throttling" in i.title.lower()]
        assert len(throttling_issues) == 1

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_low_game_priority(self, mock_detect):
        """Test audit detects sub-optimal game priority."""
        mock_detect.return_value = {
            "system_responsiveness": 0,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 2},
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        priority_issues = [i for i in issues if "priority" in i.title.lower()]
        assert len(priority_issues) == 1

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_detects_non_gaming_scheduler(self, mock_detect):
        """Test audit detects non-gaming scheduler setting."""
        mock_detect.return_value = {
            "system_responsiveness": 0,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x26,  # Default, not gaming
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()

        scheduler_issues = [i for i in issues if "scheduler" in i.title.lower()]
        assert len(scheduler_issues) == 1

    @patch.object(RegistrySettingsHandler, "detect")
    def test_audit_handles_none_values(self, mock_detect):
        """Test audit handles None values gracefully."""
        mock_detect.return_value = {
            "system_responsiveness": None,
            "network_throttling": None,
            "game_priority": {},
            "win32_priority_separation": None,
        }

        handler = RegistrySettingsHandler()
        issues = handler.audit()
        # Should not raise, may return issues for missing priority
        assert isinstance(issues, list)


class TestRegistrySettingsHandlerApply:
    """Tests for apply method."""

    @patch.object(RegistrySettingsHandler, "_set_win32_priority_separation")
    @patch.object(RegistrySettingsHandler, "_set_fullscreen_optimization")
    @patch.object(RegistrySettingsHandler, "_set_game_priority")
    @patch.object(RegistrySettingsHandler, "_set_network_throttling")
    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_apply_all_settings(self, mock_resp, mock_throttle, mock_priority, mock_fs, mock_sched):
        """Test apply calls all setters."""
        handler = RegistrySettingsHandler()
        result = handler.apply({
            "system_responsiveness": 0,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {"priority": 6},
            "win32_priority_separation": 0x2A,
        })

        assert result["success"] is True
        mock_resp.assert_called_once_with(0)
        mock_throttle.assert_called_once_with(0xFFFFFFFF)
        mock_priority.assert_called_once()
        mock_sched.assert_called_once_with(0x2A)

    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_apply_handles_exception(self, mock_set):
        """Test apply handles exceptions gracefully."""
        mock_set.side_effect = Exception("Registry error")

        handler = RegistrySettingsHandler()
        result = handler.apply({"system_responsiveness": 0})

        assert result["success"] is False
        assert "Registry error" in result["error"]

    @patch.object(RegistrySettingsHandler, "_set_fullscreen_optimization")
    def test_apply_fullscreen_optimizations(self, mock_set):
        """Test apply handles fullscreen optimization settings."""
        handler = RegistrySettingsHandler()
        result = handler.apply({
            "fullscreen_optimizations": {
                "C:\\Games\\game.exe": True,
            }
        })

        mock_set.assert_called_once_with("C:\\Games\\game.exe", True)
        assert result["success"] is True


class TestRegistrySettingsHandlerBackupRestore:
    """Tests for backup and restore methods."""

    @patch.object(RegistrySettingsHandler, "detect")
    def test_backup_returns_current_settings(self, mock_detect):
        """Test backup returns current settings."""
        mock_detect.return_value = {
            "system_responsiveness": 20,
            "network_throttling": 10,
            "game_priority": {"priority": 2},
            "win32_priority_separation": 0x26,
        }

        handler = RegistrySettingsHandler()
        backup = handler.backup()

        assert backup == mock_detect.return_value

    @patch.object(RegistrySettingsHandler, "_set_win32_priority_separation")
    @patch.object(RegistrySettingsHandler, "_set_game_priority")
    @patch.object(RegistrySettingsHandler, "_set_network_throttling")
    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_restore_applies_backup_data(self, mock_resp, mock_throttle, mock_priority, mock_sched):
        """Test restore applies backup data."""
        handler = RegistrySettingsHandler()
        result = handler.restore({
            "system_responsiveness": 20,
            "network_throttling": 10,
            "game_priority": {"priority": 2},
            "win32_priority_separation": 0x26,
        })

        assert result is True
        mock_resp.assert_called_once_with(20)
        mock_throttle.assert_called_once_with(10)
        mock_priority.assert_called_once()
        mock_sched.assert_called_once_with(0x26)

    @patch.object(RegistrySettingsHandler, "_set_system_responsiveness")
    def test_restore_handles_exception(self, mock_set):
        """Test restore handles exceptions gracefully."""
        mock_set.side_effect = Exception("Registry error")

        handler = RegistrySettingsHandler()
        result = handler.restore({"system_responsiveness": 20})

        assert result is False


class TestRegistrySettingsHandlerPrivateMethods:
    """Tests for private helper methods."""

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_system_responsiveness_handles_missing_key(self, mock_open):
        """Test _get_system_responsiveness handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_system_responsiveness()

        assert result is None

    @patch("abso.settings.registry.winreg.CloseKey")
    @patch("abso.settings.registry.winreg.QueryValueEx")
    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_system_responsiveness_returns_value(self, mock_open, mock_query, mock_close):
        """Test _get_system_responsiveness returns registry value."""
        mock_query.return_value = (20, 1)

        handler = RegistrySettingsHandler()
        result = handler._get_system_responsiveness()

        assert result == 20

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_network_throttling_handles_missing_key(self, mock_open):
        """Test _get_network_throttling handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_network_throttling()

        assert result is None

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_game_priority_handles_missing_key(self, mock_open):
        """Test _get_game_priority handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_game_priority()

        assert result == {}

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_get_win32_priority_separation_handles_missing_key(self, mock_open):
        """Test _get_win32_priority_separation handles missing registry key."""
        mock_open.side_effect = Exception("Key not found")

        handler = RegistrySettingsHandler()
        result = handler._get_win32_priority_separation()

        assert result is None

    @patch("abso.settings.registry.winreg.SetValueEx")
    @patch("abso.settings.registry.winreg.CloseKey")
    @patch("abso.settings.registry.winreg.OpenKey")
    def test_set_system_responsiveness_writes_value(self, mock_open, mock_close, mock_set):
        """Test _set_system_responsiveness writes to registry."""
        handler = RegistrySettingsHandler()
        handler._set_system_responsiveness(0)

        mock_set.assert_called_once()

    @patch("abso.settings.registry.winreg.OpenKey")
    def test_set_system_responsiveness_handles_permission_error(self, mock_open):
        """Test _set_system_responsiveness raises on permission error."""
        mock_open.side_effect = PermissionError("Access denied")

        handler = RegistrySettingsHandler()

        with pytest.raises(RegistryWriteError):
            handler._set_system_responsiveness(0)

    @patch("abso.settings.registry.validate_dword_value")
    @patch("abso.settings.registry.winreg.SetValueEx")
    @patch("abso.settings.registry.winreg.CloseKey")
    @patch("abso.settings.registry.winreg.OpenKey")
    def test_set_win32_priority_separation_validates_value(self, mock_open, mock_close, mock_set, mock_validate):
        """Test _set_win32_priority_separation validates the value."""
        handler = RegistrySettingsHandler()
        handler._set_win32_priority_separation(0x2A)

        mock_validate.assert_called_once()


class TestRegistrySettingsHandlerFullscreenOptimization:
    """Tests for _set_fullscreen_optimization preservation behavior."""

    def _patched_writer(self):
        """Capture SetValueEx/DeleteValue writes against a stub registry."""
        state: dict[str, object] = {}

        def open_or_create_key(hive, path, *_args, **_kwargs):
            # Accepts the 4-arg winreg.OpenKey signature (hive, path, reserved,
            # access_mask) used by _enumerate_fullscreen_optimizations as well
            # as the 2-arg winreg.CreateKey signature used by _set_fullscreen_optimization.
            return ("FAKE_KEY", path)

        def query_value(_key, name):
            if name not in state:
                raise FileNotFoundError(name)
            return state[name], 1  # REG_SZ = 1

        def set_value(_key, name, _reserved, _type, value):
            state[name] = value

        def delete_value(_key, name):
            if name not in state:
                raise FileNotFoundError(name)
            del state[name]

        return state, open_or_create_key, query_value, set_value, delete_value

    def test_disable_fso_adds_token_preserving_other_layers(self):
        state, open_key, query, setval, delval = self._patched_writer()
        state["C:\\Games\\Overwatch.exe"] = "~ HIGHDPIAWARE RUNASINVOKER"

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            handler._set_fullscreen_optimization("C:\\Games\\Overwatch.exe", True)

        value = state["C:\\Games\\Overwatch.exe"]
        assert value.startswith("~ ")
        tokens = value.split()[1:]
        assert set(tokens) == {"HIGHDPIAWARE", "RUNASINVOKER", "DISABLEDXMAXIMIZEDWINDOWEDMODE"}

    def test_enable_fso_removes_token_preserving_other_layers(self):
        state, open_key, query, setval, delval = self._patched_writer()
        state["C:\\Games\\Overwatch.exe"] = "~ HIGHDPIAWARE DISABLEDXMAXIMIZEDWINDOWEDMODE"

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            handler._set_fullscreen_optimization("C:\\Games\\Overwatch.exe", False)

        value = state["C:\\Games\\Overwatch.exe"]
        assert "DISABLEDXMAXIMIZEDWINDOWEDMODE" not in value
        assert "HIGHDPIAWARE" in value

    def test_enable_fso_with_only_fso_token_deletes_value(self):
        state, open_key, query, setval, delval = self._patched_writer()
        state["Overwatch.exe"] = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            handler._set_fullscreen_optimization("Overwatch.exe", False)

        assert "Overwatch.exe" not in state

    def test_disable_fso_without_existing_entry_writes_clean_value(self):
        state, open_key, query, setval, delval = self._patched_writer()

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            handler._set_fullscreen_optimization("Overwatch.exe", True)

        assert state["Overwatch.exe"] == "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"

    def test_non_file_not_found_read_error_aborts_write(self):
        """Any read failure other than FileNotFoundError must raise RegistryWriteError.

        The handler previously suppressed all OSErrors on QueryValueEx and then
        proceeded with ``existing=""``, silently dropping other AppCompat tokens
        (HIGHDPIAWARE, PROCESSORAFFINITYMASK, etc.) on any transient read error.
        """
        state, open_key, _, setval, delval = self._patched_writer()

        def flaky_query(_key, name):  # noqa: ARG001 - signature required by patch
            err = OSError("access denied")
            err.winerror = 5  # ERROR_ACCESS_DENIED, not FILE_NOT_FOUND
            raise err

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", flaky_query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            with pytest.raises(RegistryWriteError):
                handler._set_fullscreen_optimization(
                    "C:\\Games\\Overwatch.exe", True
                )

        # And ABSO must not have written a truncated value.
        assert "C:\\Games\\Overwatch.exe" not in state

    def test_restore_fullscreen_optimizations_reverses_abso_write(self):
        """Restore must re-assert backed-up state and clear any entry not in the backup."""
        state, open_key, query, setval, delval = self._patched_writer()
        # Simulate current: ABSO wrote FSO for OW2 during apply; backup was
        # taken BEFORE apply and captured empty Layers, so restore must
        # remove the Overwatch.exe entry.
        state["Overwatch.exe"] = "~ DISABLEDXMAXIMIZEDWINDOWEDMODE"

        def enum_value(_key, i):
            keys = list(state.keys())
            if i >= len(keys):
                # _enumerate_fullscreen_optimizations only treats
                # ERROR_NO_MORE_ITEMS (259) as loop termination; any other
                # OSError must propagate. Match that contract here so the
                # test exercises the real termination path.
                err = OSError("no more values")
                err.winerror = 259
                raise err
            name = keys[i]
            return name, state[name], 1

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.OpenKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.EnumValue", enum_value),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            # Backup captured empty dict (no FSO entries at backup time).
            handler._restore_fullscreen_optimizations({})

        assert "Overwatch.exe" not in state

    def test_restore_fullscreen_optimizations_reapplies_user_flag(self):
        """If a user's FSO entry existed at backup but was cleared, restore re-adds it."""
        state, open_key, query, setval, delval = self._patched_writer()
        # Current registry has no FSO entries (e.g., ABSO cleared them).
        # Backup recorded one the user had set manually before ABSO ran.

        def enum_value(_key, i):
            keys = list(state.keys())
            if i >= len(keys):
                # _enumerate_fullscreen_optimizations only treats
                # ERROR_NO_MORE_ITEMS (259) as loop termination; any other
                # OSError must propagate. Match that contract here so the
                # test exercises the real termination path.
                err = OSError("no more values")
                err.winerror = 259
                raise err
            name = keys[i]
            return name, state[name], 1

        with (
            patch("abso.settings.registry.winreg.CreateKey", open_key),
            patch("abso.settings.registry.winreg.OpenKey", open_key),
            patch("abso.settings.registry.winreg.QueryValueEx", query),
            patch("abso.settings.registry.winreg.SetValueEx", setval),
            patch("abso.settings.registry.winreg.DeleteValue", delval),
            patch("abso.settings.registry.winreg.EnumValue", enum_value),
            patch("abso.settings.registry.winreg.CloseKey"),
        ):
            handler = RegistrySettingsHandler()
            handler._restore_fullscreen_optimizations(
                {"C:\\Games\\UserGame.exe": True}
            )

        assert (
            "DISABLEDXMAXIMIZEDWINDOWEDMODE" in state["C:\\Games\\UserGame.exe"]
        )

    def test_restore_fullscreen_optimizations_rejects_non_dict(self):
        """A corrupted backup value must raise so restore() reports failure."""
        handler = RegistrySettingsHandler()
        with pytest.raises(RegistryWriteError):
            handler._restore_fullscreen_optimizations("not a dict")  # type: ignore[arg-type]

    def test_restore_returns_false_when_fso_backup_is_corrupted(self):
        """Top-level restore() must surface a non-dict FSO payload as False."""
        handler = RegistrySettingsHandler()
        ok = handler.restore({"fullscreen_optimizations": "garbage"})
        assert ok is False

    def test_enumerate_propagates_non_not_found_osError(self):
        """Broad OSError during enumeration must propagate, not return {}.

        Suppressing permission errors here and returning {} would make the
        backup snapshot falsely report "no FSO entries", and a later restore
        would clear live state. Bubble up so detect() can drop the section.
        """
        def fail_open(*_a, **_kw):
            err = OSError("access denied")
            err.winerror = 5  # ERROR_ACCESS_DENIED
            raise err

        with patch("abso.settings.registry.winreg.OpenKey", fail_open):
            handler = RegistrySettingsHandler()
            with pytest.raises(OSError):
                handler._enumerate_fullscreen_optimizations()

    def test_enumerate_returns_empty_when_layers_key_missing(self):
        """A real not-found should still produce an empty dict (new install)."""

        def fail_open(*_a, **_kw):
            raise FileNotFoundError("Layers key missing")

        with patch("abso.settings.registry.winreg.OpenKey", fail_open):
            handler = RegistrySettingsHandler()
            assert handler._enumerate_fullscreen_optimizations() == {}

    def test_detect_omits_fullscreen_optimizations_on_enumeration_failure(self):
        """detect() must drop fullscreen_optimizations when enumeration can't be proven."""

        def fail_open(*_a, **_kw):
            err = OSError("transient failure")
            err.winerror = 5
            raise err

        with (
            patch("abso.settings.registry.winreg.OpenKey", fail_open),
            patch.object(
                RegistrySettingsHandler, "_get_system_responsiveness", return_value=0
            ),
            patch.object(
                RegistrySettingsHandler, "_get_network_throttling", return_value=0
            ),
            patch.object(
                RegistrySettingsHandler, "_get_game_priority", return_value={}
            ),
            patch.object(
                RegistrySettingsHandler,
                "_get_win32_priority_separation",
                return_value=0x2A,
            ),
        ):
            handler = RegistrySettingsHandler()
            detected = handler.detect()

        assert "fullscreen_optimizations" not in detected

    def test_restore_aggregates_per_exe_failures(self):
        """Per-exe write failures must propagate as RegistryWriteError."""

        def fail_set(*_a, **_kw):
            raise Exception("registry write failed")

        with (
            patch.object(
                RegistrySettingsHandler,
                "_enumerate_fullscreen_optimizations",
                return_value={},
            ),
            patch.object(
                RegistrySettingsHandler,
                "_set_fullscreen_optimization",
                side_effect=fail_set,
            ),
        ):
            handler = RegistrySettingsHandler()
            with pytest.raises(RegistryWriteError):
                handler._restore_fullscreen_optimizations(
                    {"A.exe": True, "B.exe": True}
                )

    def test_restore_returns_false_when_fso_restore_raises(self):
        """Top-level restore() must surface fullscreen_optimizations failure as False."""

        def fail_set(*_a, **_kw):
            raise Exception("write failed")

        with (
            patch.object(
                RegistrySettingsHandler,
                "_enumerate_fullscreen_optimizations",
                return_value={},
            ),
            patch.object(
                RegistrySettingsHandler,
                "_set_fullscreen_optimization",
                side_effect=fail_set,
            ),
        ):
            handler = RegistrySettingsHandler()
            ok = handler.restore({"fullscreen_optimizations": {"X.exe": True}})
        assert ok is False


class TestRegistrySettingsHandlerVerify:
    """Tests for verify_active()."""

    @patch.object(RegistrySettingsHandler, "_get_fullscreen_optimization", return_value=True)
    @patch.object(RegistrySettingsHandler, "detect")
    def test_verify_active_reports_success(self, mock_detect, mock_get_fso):
        mock_detect.return_value = {
            "system_responsiveness": 10,
            "network_throttling": 0xFFFFFFFF,
            "game_priority": {
                "gpu_priority": 8,
                "priority": 6,
                "scheduling_category": "High",
            },
            "win32_priority_separation": 0x2A,
        }

        handler = RegistrySettingsHandler()
        result = handler.verify_active(
            {
                "system_responsiveness": 10,
                "network_throttling": 0xFFFFFFFF,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                    "scheduling_category": "High",
                },
                "win32_priority_separation": 0x2A,
                "fullscreen_optimizations": {"C:\\Games\\test.exe": True},
            }
        )

        assert result["all_active"] is True
        assert result["settings"]["game_priority.priority"]["active"] is True
        assert result["settings"]["fullscreen_optimizations:C:\\Games\\test.exe"]["active"] is True

    @patch.object(RegistrySettingsHandler, "_get_fullscreen_optimization", return_value=False)
    @patch.object(RegistrySettingsHandler, "detect")
    def test_verify_active_reports_mismatch(self, mock_detect, mock_get_fso):
        mock_detect.return_value = {
            "system_responsiveness": 20,
            "network_throttling": 1,
            "game_priority": {
                "gpu_priority": 4,
                "priority": 2,
                "scheduling_category": "Medium",
            },
            "win32_priority_separation": 0x26,
        }

        handler = RegistrySettingsHandler()
        result = handler.verify_active(
            {
                "system_responsiveness": 10,
                "network_throttling": 0xFFFFFFFF,
                "game_priority": {
                    "gpu_priority": 8,
                    "priority": 6,
                },
                "win32_priority_separation": 0x2A,
                "fullscreen_optimizations": {"C:\\Games\\test.exe": True},
            }
        )

        assert result["all_active"] is False
        assert result["settings"]["system_responsiveness"]["active"] is False
        assert result["settings"]["game_priority.priority"]["active"] is False
        assert result["settings"]["fullscreen_optimizations:C:\\Games\\test.exe"]["active"] is False
