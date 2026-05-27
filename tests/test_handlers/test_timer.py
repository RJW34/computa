"""Tests for TimerSettingsHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.settings.timer import TimerResolutionGuard, TimerSettingsHandler


class TestTimerConversions:
    """Tests for timer resolution conversion methods."""

    def test_resolution_to_ms(self):
        """Test converting 100ns units to milliseconds."""
        handler = TimerSettingsHandler()

        assert handler._resolution_to_ms(10000) == 1.0
        assert handler._resolution_to_ms(5000) == 0.5
        assert handler._resolution_to_ms(156250) == 15.625

    def test_ms_to_resolution(self):
        """Test converting milliseconds to 100ns units."""
        handler = TimerSettingsHandler()

        assert handler._ms_to_resolution(1.0) == 10000
        assert handler._ms_to_resolution(0.5) == 5000
        assert handler._ms_to_resolution(15.625) == 156250


class TestTimerDetect:
    """Tests for detect() method."""

    def test_detect_returns_expected_keys(self):
        """Test detect returns dict with expected keys."""
        handler = TimerSettingsHandler()
        result = handler.detect()

        assert "available" in result
        assert "current_resolution_100ns" in result
        assert "current_resolution_ms" in result
        assert "minimum_resolution_100ns" in result
        assert "maximum_resolution_100ns" in result
        assert "is_optimized" in result

    def test_detect_available_when_ntdll_loaded(self):
        """Test detect reports available when ntdll is loaded."""
        handler = TimerSettingsHandler()
        result = handler.detect()

        # On Windows, ntdll should be available
        assert result["available"] is True

    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_detect_is_optimized_when_low(self, mock_query):
        """Test is_optimized is True when resolution <= 1ms."""
        mock_query.return_value = (5000, 156250, 10000)  # min, max, current

        handler = TimerSettingsHandler()
        result = handler.detect()

        assert result["is_optimized"] is True
        assert result["current_resolution_ms"] == 1.0

    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_detect_not_optimized_when_high(self, mock_query):
        """Test is_optimized is False when resolution > 1ms."""
        mock_query.return_value = (5000, 156250, 156250)  # default ~15.6ms

        handler = TimerSettingsHandler()
        result = handler.detect()

        assert result["is_optimized"] is False
        assert result["current_resolution_ms"] == 15.625


class TestTimerAudit:
    """Tests for audit() method."""

    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_audit_no_issues_when_optimized(self, mock_query):
        """Test audit returns no issues when timer is optimized."""
        mock_query.return_value = (5000, 156250, 5000)  # 0.5ms

        handler = TimerSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0

    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_audit_issue_when_not_optimized(self, mock_query):
        """Test audit returns issue when timer is at default."""
        mock_query.return_value = (5000, 156250, 156250)  # 15.6ms default

        handler = TimerSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 1
        assert "Timer resolution" in issues[0].title
        assert issues[0].severity == "info"


class TestTimerApply:
    """Tests for apply() method."""

    @patch.object(TimerSettingsHandler, "_set_timer_resolution")
    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_apply_with_resolution_ms(self, mock_query, mock_set):
        """Test apply with resolution_ms setting."""
        mock_query.return_value = (5000, 156250, 156250)
        mock_set.return_value = 5000

        handler = TimerSettingsHandler()
        result = handler.apply({"resolution_ms": 0.5})

        assert result["success"] is True
        mock_set.assert_called_once_with(5000, enable=True)

    @patch.object(TimerSettingsHandler, "_set_timer_resolution")
    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_apply_with_resolution_100ns(self, mock_query, mock_set):
        """Test apply with resolution_100ns setting."""
        mock_query.return_value = (5000, 156250, 156250)
        mock_set.return_value = 10000

        handler = TimerSettingsHandler()
        result = handler.apply({"resolution_100ns": 10000})

        assert result["success"] is True
        mock_set.assert_called_once_with(10000, enable=True)

    @patch.object(TimerSettingsHandler, "_set_timer_resolution")
    @patch.object(TimerSettingsHandler, "_query_timer_resolution")
    def test_apply_defaults_to_0_5ms(self, mock_query, mock_set):
        """Test apply defaults to 0.5ms when no setting provided."""
        mock_query.return_value = (5000, 156250, 156250)
        mock_set.return_value = 5000

        handler = TimerSettingsHandler()
        result = handler.apply({})

        assert result["success"] is True
        mock_set.assert_called_once_with(5000, enable=True)

    @patch.object(TimerSettingsHandler, "_set_timer_resolution")
    def test_apply_failure(self, mock_set):
        """Test apply handles failure gracefully."""
        mock_set.return_value = None  # Indicates failure

        handler = TimerSettingsHandler()
        result = handler.apply({"resolution_ms": 0.5})

        assert result["success"] is False
        assert result["error"] is not None

    def test_set_timer_resolution_gates_on_privilege_not_held(self):
        """STATUS_PRIVILEGE_NOT_HELD must be downgraded from warning to a one-shot
        info, and subsequent calls must short-circuit so the per-apply log
        doesn't fill with the same kernel-policy message."""
        from unittest.mock import MagicMock

        handler = TimerSettingsHandler()
        # Bypass real ntdll load by injecting a mock that returns the
        # 25H2 privilege-not-held NTSTATUS.
        mock_ntdll = MagicMock()
        mock_ntdll.NtSetTimerResolution.return_value = (
            TimerSettingsHandler._STATUS_PRIVILEGE_NOT_HELD
        )
        handler._ntdll = mock_ntdll

        first = handler._set_timer_resolution(5000, enable=True)
        second = handler._set_timer_resolution(5000, enable=True)

        assert first is None and second is None
        assert handler._privilege_blocked is True
        # Only the first call reaches ntdll; subsequent ones short-circuit.
        assert mock_ntdll.NtSetTimerResolution.call_count == 1

    def test_apply_returns_skipped_under_privilege_gate(self):
        """Apply must report skipped (not failed) when the kernel refuses the
        timer call, so profile applies are not rolled back over a capability
        the user cannot grant from inside Python."""
        from unittest.mock import MagicMock

        handler = TimerSettingsHandler()
        mock_ntdll = MagicMock()
        mock_ntdll.NtSetTimerResolution.return_value = (
            TimerSettingsHandler._STATUS_PRIVILEGE_NOT_HELD
        )
        # NtQueryTimerResolution returns 0 (success) with arbitrary current
        # values so _query_timer_resolution does not crash the apply path.
        mock_ntdll.NtQueryTimerResolution.return_value = 0
        handler._ntdll = mock_ntdll

        result = handler.apply({"resolution_ms": 0.5})

        assert result["success"] is True
        assert "skipped" in result
        assert "PRIVILEGE_NOT_HELD" in result["skipped"]


class TestTimerBackupRestore:
    """Tests for backup() and restore() methods."""

    @patch.object(TimerSettingsHandler, "detect")
    def test_backup_returns_current_settings(self, mock_detect):
        """Test backup returns current resolution."""
        mock_detect.return_value = {
            "current_resolution_100ns": 10000,
            "current_resolution_ms": 1.0,
        }

        handler = TimerSettingsHandler()
        backup = handler.backup()

        assert backup["resolution_100ns"] == 10000
        assert backup["resolution_ms"] == 1.0

    @patch.object(TimerSettingsHandler, "_set_timer_resolution")
    def test_restore_releases_resolution(self, mock_set):
        """Test restore releases the timer resolution request."""
        handler = TimerSettingsHandler()
        result = handler.restore({"resolution_100ns": 156250})

        assert result is True
        mock_set.assert_called_once_with(156250, enable=False)


class TestTimerConvenienceMethods:
    """Tests for convenience methods."""

    @patch.object(TimerSettingsHandler, "apply")
    def test_set_gaming_resolution(self, mock_apply):
        """Test set_gaming_resolution convenience method."""
        mock_apply.return_value = {"success": True}

        handler = TimerSettingsHandler()
        result = handler.set_gaming_resolution(0.5)

        assert result is True
        mock_apply.assert_called_once_with({"resolution_ms": 0.5})

    @patch.object(TimerSettingsHandler, "restore")
    def test_release_resolution(self, mock_restore):
        """Test release_resolution convenience method."""
        mock_restore.return_value = True

        handler = TimerSettingsHandler()
        result = handler.release_resolution()

        assert result is True
        mock_restore.assert_called_once_with({})


@patch("abso.settings.timer.subprocess.run")
def test_timer_process_check_uses_exact_tasklist_image_name(mock_subprocess_run):
    """Timer hold should not keep running because of substring tasklist matches."""
    mock_subprocess_run.return_value = MagicMock(
        stdout='"notgame.exe","1111","Console","1","10000 K"\n',
    )

    assert TimerResolutionGuard._is_process_running("game.exe") is False
