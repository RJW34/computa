"""Tests for input validation utilities."""

import pytest

from abso.utils.validation import (
    ValidationError,
    validate_dword_value,
    validate_executable_name,
    validate_executable_path,
    validate_priority_value,
    validate_registry_string,
)


class TestValidateExecutableName:
    """Tests for validate_executable_name function."""

    def test_valid_simple_name(self):
        """Test valid simple executable name."""
        assert validate_executable_name("game.exe") == "game.exe"

    def test_valid_name_with_spaces(self):
        """Test valid name with spaces."""
        assert validate_executable_name("My Game.exe") == "My Game.exe"

    def test_valid_name_with_hyphens(self):
        """Test valid name with hyphens."""
        assert validate_executable_name("my-game-2.exe") == "my-game-2.exe"

    def test_valid_name_with_underscores(self):
        """Test valid name with underscores."""
        assert validate_executable_name("my_game_v2.exe") == "my_game_v2.exe"

    def test_valid_dolphin(self):
        """Test Dolphin emulator executable."""
        assert validate_executable_name("Dolphin.exe") == "Dolphin.exe"

    def test_empty_name_raises(self):
        """Test that empty name raises ValidationError."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_executable_name("")

    def test_none_name_raises(self):
        """Test that None raises ValidationError."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_executable_name(None)

    def test_non_string_raises(self):
        """Test that non-string raises ValidationError."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_executable_name(123)

    def test_path_separator_backslash_raises(self):
        """Test that backslash in name raises ValidationError."""
        with pytest.raises(ValidationError, match="path separators"):
            validate_executable_name("..\\..\\system32\\cmd.exe")

    def test_path_separator_forward_slash_raises(self):
        """Test that forward slash in name raises ValidationError."""
        with pytest.raises(ValidationError, match="path separators"):
            validate_executable_name("../system32/cmd.exe")

    def test_dangerous_chars_colon_raises(self):
        """Test that colon raises ValidationError."""
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_executable_name("C:game.exe")

    def test_dangerous_chars_asterisk_raises(self):
        """Test that asterisk raises ValidationError."""
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_executable_name("game*.exe")

    def test_dangerous_chars_null_raises(self):
        """Test that null byte raises ValidationError."""
        with pytest.raises(ValidationError, match="invalid characters"):
            validate_executable_name("game\x00.exe")

    def test_wrong_extension_raises(self):
        """Test that non-.exe extension raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid executable name format"):
            validate_executable_name("game.txt")

    def test_no_extension_raises(self):
        """Test that no extension raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid executable name format"):
            validate_executable_name("game")

    def test_starts_with_period_raises(self):
        """Test that name starting with period raises ValidationError."""
        with pytest.raises(ValidationError, match="Invalid executable name format"):
            validate_executable_name(".hidden.exe")

    def test_reserved_name_con_raises(self):
        """Test that reserved name CON raises ValidationError."""
        with pytest.raises(ValidationError, match="reserved Windows name"):
            validate_executable_name("CON.exe")

    def test_reserved_name_prn_raises(self):
        """Test that reserved name PRN raises ValidationError."""
        with pytest.raises(ValidationError, match="reserved Windows name"):
            validate_executable_name("PRN.exe")

    def test_reserved_name_com1_raises(self):
        """Test that reserved name COM1 raises ValidationError."""
        with pytest.raises(ValidationError, match="reserved Windows name"):
            validate_executable_name("COM1.exe")

    def test_reserved_name_lpt1_raises(self):
        """Test that reserved name LPT1 raises ValidationError."""
        with pytest.raises(ValidationError, match="reserved Windows name"):
            validate_executable_name("LPT1.exe")

    def test_too_long_name_raises(self):
        """Test that name exceeding 255 characters raises ValidationError."""
        long_name = "a" * 252 + ".exe"  # 256 chars total
        with pytest.raises(ValidationError, match="too long"):
            validate_executable_name(long_name)

    def test_case_insensitive_extension(self):
        """Test that .EXE extension is accepted."""
        assert validate_executable_name("game.EXE") == "game.EXE"


class TestValidateExecutablePath:
    """Tests for validate_executable_path function."""

    def test_valid_absolute_path(self):
        """Test valid absolute Windows path."""
        path = "C:\\Games\\game.exe"
        assert validate_executable_path(path) == path

    def test_valid_path_with_spaces(self):
        """Test valid path with spaces."""
        path = "C:\\Program Files\\My Game\\game.exe"
        assert validate_executable_path(path) == path

    def test_empty_path_raises(self):
        """Test that empty path raises ValidationError."""
        with pytest.raises(ValidationError, match="cannot be empty"):
            validate_executable_path("")

    def test_path_traversal_raises(self):
        """Test that path traversal attempt raises ValidationError."""
        with pytest.raises(ValidationError, match="parent directory reference"):
            validate_executable_path("C:\\Games\\..\\system32\\cmd.exe")

    def test_null_byte_raises(self):
        """Test that null byte in path raises ValidationError."""
        with pytest.raises(ValidationError, match="null bytes"):
            validate_executable_path("C:\\Games\\game\x00.exe")

    def test_wrong_extension_raises(self):
        """Test that non-.exe path raises ValidationError."""
        with pytest.raises(ValidationError, match="must end with .exe"):
            validate_executable_path("C:\\Games\\game.txt")

    def test_invalid_filename_in_path_raises(self):
        """Test that invalid filename in path raises ValidationError."""
        with pytest.raises(ValidationError, match="reserved Windows name"):
            validate_executable_path("C:\\Games\\CON.exe")

    def test_too_long_path_raises(self):
        """Test that path exceeding MAX_PATH raises ValidationError."""
        long_path = "C:\\" + "a" * 300 + ".exe"
        with pytest.raises(ValidationError, match="too long"):
            validate_executable_path(long_path)


class TestValidateDwordValue:
    """Tests for validate_dword_value function."""

    def test_valid_zero(self):
        """Test valid zero value."""
        assert validate_dword_value(0, "test") == 0

    def test_valid_max_dword(self):
        """Test valid maximum DWORD value."""
        assert validate_dword_value(0xFFFFFFFF, "test") == 0xFFFFFFFF

    def test_valid_mid_range(self):
        """Test valid mid-range value."""
        assert validate_dword_value(12345, "test") == 12345

    def test_negative_raises(self):
        """Test that negative value raises ValidationError."""
        with pytest.raises(ValidationError, match="out of range"):
            validate_dword_value(-1, "test")

    def test_exceeds_max_raises(self):
        """Test that value exceeding max raises ValidationError."""
        with pytest.raises(ValidationError, match="out of range"):
            validate_dword_value(0x100000000, "test")

    def test_non_integer_raises(self):
        """Test that non-integer raises ValidationError."""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_dword_value("123", "test")

    def test_custom_range(self):
        """Test custom min/max range."""
        assert validate_dword_value(50, "test", min_val=0, max_val=100) == 50

    def test_custom_range_out_of_bounds_raises(self):
        """Test that value outside custom range raises ValidationError."""
        with pytest.raises(ValidationError, match="out of range"):
            validate_dword_value(150, "test", min_val=0, max_val=100)


class TestValidatePriorityValue:
    """Tests for validate_priority_value function."""

    def test_valid_priority_default_range(self):
        """Test valid priority in default range."""
        assert validate_priority_value(128, "test") == 128

    def test_valid_priority_zero(self):
        """Test valid priority zero."""
        assert validate_priority_value(0, "test") == 0

    def test_valid_priority_max(self):
        """Test valid priority max (255)."""
        assert validate_priority_value(255, "test") == 255

    def test_negative_raises(self):
        """Test that negative priority raises ValidationError."""
        with pytest.raises(ValidationError, match="out of range"):
            validate_priority_value(-1, "test")

    def test_exceeds_max_raises(self):
        """Test that priority exceeding 255 raises ValidationError."""
        with pytest.raises(ValidationError, match="out of range"):
            validate_priority_value(256, "test")

    def test_valid_values_set(self):
        """Test valid value from allowed set."""
        valid_set = {1, 2, 3, 4}
        assert validate_priority_value(3, "test", valid_values=valid_set) == 3

    def test_invalid_value_from_set_raises(self):
        """Test that value not in set raises ValidationError."""
        valid_set = {1, 2, 3, 4}
        with pytest.raises(ValidationError, match="not valid"):
            validate_priority_value(5, "test", valid_values=valid_set)

    def test_non_integer_raises(self):
        """Test that non-integer raises ValidationError."""
        with pytest.raises(ValidationError, match="must be an integer"):
            validate_priority_value("high", "test")


class TestValidateRegistryString:
    """Tests for validate_registry_string function."""

    def test_valid_string(self):
        """Test valid string."""
        assert validate_registry_string("Hello World", "test") == "Hello World"

    def test_empty_string(self):
        """Test empty string is valid."""
        assert validate_registry_string("", "test") == ""

    def test_non_string_raises(self):
        """Test that non-string raises ValidationError."""
        with pytest.raises(ValidationError, match="must be a string"):
            validate_registry_string(123, "test")

    def test_null_byte_raises(self):
        """Test that null byte raises ValidationError."""
        with pytest.raises(ValidationError, match="null bytes"):
            validate_registry_string("hello\x00world", "test")

    def test_too_long_raises(self):
        """Test that string exceeding max length raises ValidationError."""
        long_string = "a" * 20000
        with pytest.raises(ValidationError, match="too long"):
            validate_registry_string(long_string, "test")

    def test_custom_max_length(self):
        """Test custom max length."""
        with pytest.raises(ValidationError, match="too long"):
            validate_registry_string("hello world", "test", max_length=5)
