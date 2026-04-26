"""Tests for admin utilities module."""

import ctypes
import sys
from unittest.mock import MagicMock, patch

import pytest

from abso.utils.admin import ensure_admin, is_admin


class TestIsAdmin:
    """Tests for is_admin function."""

    @patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=1)
    def test_returns_true_when_admin(self, mock_is_admin):
        """Test returns True when running as admin."""
        result = is_admin()
        assert result is True

    @patch("ctypes.windll.shell32.IsUserAnAdmin", return_value=0)
    def test_returns_false_when_not_admin(self, mock_is_admin):
        """Test returns False when not running as admin."""
        result = is_admin()
        assert result is False

    @patch("ctypes.windll.shell32.IsUserAnAdmin", side_effect=AttributeError("No windll"))
    def test_returns_false_on_attribute_error(self, mock_is_admin):
        """Test returns False on AttributeError (non-Windows)."""
        result = is_admin()
        assert result is False

    @patch("ctypes.windll.shell32.IsUserAnAdmin", side_effect=OSError("OS error"))
    def test_returns_false_on_os_error(self, mock_is_admin):
        """Test returns False on OSError."""
        result = is_admin()
        assert result is False


class TestEnsureAdmin:
    """Tests for ensure_admin function."""

    @patch("abso.utils.admin.is_admin", return_value=True)
    def test_does_nothing_when_already_admin(self, mock_is_admin):
        """Test does nothing when already running as admin."""
        # Should not raise
        ensure_admin()

    @patch("sys.exit")
    @patch("ctypes.windll.shell32.ShellExecuteW", return_value=42)
    @patch("abso.utils.admin.is_admin", return_value=False)
    def test_attempts_elevation_when_not_admin(self, mock_is_admin, mock_execute, mock_exit):
        """Test attempts to elevate when not running as admin."""
        ensure_admin()

        mock_execute.assert_called_once()
        # Should call with "runas" for elevation
        call_args = mock_execute.call_args[0]
        assert call_args[1] == "runas"
        mock_exit.assert_called_once_with(0)

    @patch("ctypes.windll.shell32.ShellExecuteW", side_effect=Exception("Elevation failed"))
    @patch("abso.utils.admin.is_admin", return_value=False)
    def test_raises_on_elevation_failure(self, mock_is_admin, mock_execute):
        """Test raises RuntimeError when elevation fails."""
        with pytest.raises(RuntimeError, match="Admin privileges required"):
            ensure_admin()

    @patch("sys.exit")
    @patch("ctypes.windll.shell32.ShellExecuteW", return_value=42)
    @patch("abso.utils.admin.is_admin", return_value=False)
    def test_quotes_argv_with_spaces(self, mock_is_admin, mock_execute, mock_exit):
        """Args with spaces survive the re-launch via list2cmdline quoting."""
        with patch.object(sys, "argv", ["abso", "apply", r"C:\Path With Space\profile.yaml"]):
            ensure_admin()
        params = mock_execute.call_args[0][3]
        assert '"C:\\Path With Space\\profile.yaml"' in params
