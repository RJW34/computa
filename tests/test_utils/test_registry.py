"""Tests for registry utility functions."""

import pytest
from unittest.mock import patch, MagicMock
import winreg

from gametune.utils.registry import (
    read_registry_value,
    write_registry_value,
    delete_registry_value,
    key_exists,
    value_exists,
    read_registry_dword,
    read_registry_string,
)
from gametune.core.exceptions import RegistryReadError, RegistryWriteError


class TestReadRegistryValue:
    """Tests for read_registry_value function."""

    @patch("gametune.utils.registry.winreg")
    def test_read_existing_value(self, mock_winreg):
        """Test reading an existing registry value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (42, winreg.REG_DWORD)
        mock_winreg.KEY_READ = winreg.KEY_READ

        result = read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result == 42
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch("gametune.utils.registry.winreg")
    def test_read_missing_value_returns_default(self, mock_winreg):
        """Test reading a missing value returns the default."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        mock_winreg.KEY_READ = winreg.KEY_READ

        result = read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "MissingValue",
            default=99
        )

        assert result == 99

    @patch("gametune.utils.registry.winreg")
    def test_read_missing_key_returns_default(self, mock_winreg):
        """Test reading from a missing key returns the default."""
        mock_winreg.OpenKey.side_effect = FileNotFoundError()
        mock_winreg.KEY_READ = winreg.KEY_READ

        result = read_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NonExistent",
            "TestValue",
            default="fallback"
        )

        assert result == "fallback"

    @patch("gametune.utils.registry.winreg")
    def test_read_permission_denied_raises(self, mock_winreg):
        """Test reading with permission denied raises RegistryReadError."""
        mock_winreg.OpenKey.side_effect = PermissionError("Access denied")
        mock_winreg.KEY_READ = winreg.KEY_READ

        with pytest.raises(RegistryReadError, match="Permission denied"):
            read_registry_value(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Protected",
                "SecretValue"
            )


class TestWriteRegistryValue:
    """Tests for write_registry_value function."""

    @patch("gametune.utils.registry.winreg")
    def test_write_value_to_existing_key(self, mock_winreg):
        """Test writing a value to an existing key."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        write_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue",
            123
        )

        mock_winreg.SetValueEx.assert_called_once()
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch("gametune.utils.registry.winreg")
    def test_write_value_creates_key(self, mock_winreg):
        """Test writing a value with create_key=True creates the key."""
        mock_key = MagicMock()
        mock_winreg.CreateKey.return_value = mock_key
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        write_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\NewKey",
            "TestValue",
            456,
            create_key=True
        )

        mock_winreg.CreateKey.assert_called_once()
        mock_winreg.SetValueEx.assert_called_once()

    @patch("gametune.utils.registry.winreg")
    def test_write_permission_denied_raises(self, mock_winreg):
        """Test writing with permission denied raises RegistryWriteError."""
        mock_winreg.OpenKey.side_effect = PermissionError("Access denied")
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        with pytest.raises(RegistryWriteError, match="Permission denied"):
            write_registry_value(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Protected",
                "TestValue",
                789
            )

    @patch("gametune.utils.registry.winreg")
    def test_write_key_not_found_raises(self, mock_winreg):
        """Test writing to non-existent key raises RegistryWriteError."""
        mock_winreg.OpenKey.side_effect = FileNotFoundError()
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS
        mock_winreg.REG_DWORD = winreg.REG_DWORD

        with pytest.raises(RegistryWriteError, match="not found"):
            write_registry_value(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\NonExistent",
                "TestValue",
                123
            )


class TestDeleteRegistryValue:
    """Tests for delete_registry_value function."""

    @patch("gametune.utils.registry.winreg")
    def test_delete_existing_value(self, mock_winreg):
        """Test deleting an existing value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS

        result = delete_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result is True
        mock_winreg.DeleteValue.assert_called_once()

    @patch("gametune.utils.registry.winreg")
    def test_delete_missing_value_returns_false(self, mock_winreg):
        """Test deleting a missing value returns False with ignore_missing."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.DeleteValue.side_effect = FileNotFoundError()
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS

        result = delete_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "MissingValue",
            ignore_missing=True
        )

        assert result is False

    @patch("gametune.utils.registry.winreg")
    def test_delete_missing_value_raises_when_not_ignored(self, mock_winreg):
        """Test deleting a missing value raises when ignore_missing=False."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.DeleteValue.side_effect = FileNotFoundError()
        mock_winreg.KEY_ALL_ACCESS = winreg.KEY_ALL_ACCESS

        with pytest.raises(RegistryWriteError, match="not found"):
            delete_registry_value(
                winreg.HKEY_LOCAL_MACHINE,
                r"SOFTWARE\Test",
                "MissingValue",
                ignore_missing=False
            )


class TestKeyExists:
    """Tests for key_exists function."""

    @patch("gametune.utils.registry.winreg")
    def test_key_exists_returns_true(self, mock_winreg):
        """Test key_exists returns True for existing key."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.KEY_READ = winreg.KEY_READ

        assert key_exists(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\Test") is True
        mock_winreg.CloseKey.assert_called_once_with(mock_key)

    @patch("gametune.utils.registry.winreg")
    def test_key_not_exists_returns_false(self, mock_winreg):
        """Test key_exists returns False for non-existent key."""
        mock_winreg.OpenKey.side_effect = FileNotFoundError()
        mock_winreg.KEY_READ = winreg.KEY_READ

        assert key_exists(winreg.HKEY_LOCAL_MACHINE, r"SOFTWARE\NonExistent") is False


class TestValueExists:
    """Tests for value_exists function."""

    @patch("gametune.utils.registry.winreg")
    def test_value_exists_returns_true(self, mock_winreg):
        """Test value_exists returns True for existing value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.return_value = (1, winreg.REG_DWORD)
        mock_winreg.KEY_READ = winreg.KEY_READ

        result = value_exists(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result is True

    @patch("gametune.utils.registry.winreg")
    def test_value_not_exists_returns_false(self, mock_winreg):
        """Test value_exists returns False for non-existent value."""
        mock_key = MagicMock()
        mock_winreg.OpenKey.return_value = mock_key
        mock_winreg.QueryValueEx.side_effect = FileNotFoundError()
        mock_winreg.KEY_READ = winreg.KEY_READ

        result = value_exists(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "MissingValue"
        )

        assert result is False


class TestReadRegistryDword:
    """Tests for read_registry_dword function."""

    @patch("gametune.utils.registry.read_registry_value")
    def test_read_dword_returns_int(self, mock_read):
        """Test read_registry_dword returns an integer."""
        mock_read.return_value = 42

        result = read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result == 42
        assert isinstance(result, int)

    @patch("gametune.utils.registry.read_registry_value")
    def test_read_dword_returns_default_for_none(self, mock_read):
        """Test read_registry_dword returns default for None value."""
        mock_read.return_value = None

        result = read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue",
            default=99
        )

        assert result == 99

    @patch("gametune.utils.registry.read_registry_value")
    def test_read_dword_converts_string(self, mock_read):
        """Test read_registry_dword converts string to int."""
        mock_read.return_value = "123"

        result = read_registry_dword(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result == 123


class TestReadRegistryString:
    """Tests for read_registry_string function."""

    @patch("gametune.utils.registry.read_registry_value")
    def test_read_string_returns_string(self, mock_read):
        """Test read_registry_string returns a string."""
        mock_read.return_value = "test value"

        result = read_registry_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result == "test value"
        assert isinstance(result, str)

    @patch("gametune.utils.registry.read_registry_value")
    def test_read_string_returns_default_for_none(self, mock_read):
        """Test read_registry_string returns default for None value."""
        mock_read.return_value = None

        result = read_registry_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue",
            default="fallback"
        )

        assert result == "fallback"

    @patch("gametune.utils.registry.read_registry_value")
    def test_read_string_converts_int(self, mock_read):
        """Test read_registry_string converts int to string."""
        mock_read.return_value = 456

        result = read_registry_string(
            winreg.HKEY_LOCAL_MACHINE,
            r"SOFTWARE\Test",
            "TestValue"
        )

        assert result == "456"
