"""Input validation utilities for safe registry and system operations.

This module provides validation functions to prevent:
- Path traversal attacks
- Registry key injection
- Invalid executable names
- Out-of-range values
"""

from __future__ import annotations

import re
from pathlib import Path, PureWindowsPath


class ValidationError(ValueError):
    """Raised when input validation fails."""
    pass


# Valid executable name pattern:
# - Must end with .exe (case insensitive)
# - Can only contain alphanumeric, spaces, hyphens, underscores, periods
# - Cannot contain path separators or special characters
# - Cannot start with a period
EXECUTABLE_NAME_PATTERN = re.compile(
    r'^[a-zA-Z0-9][a-zA-Z0-9\s\-_\.]*\.exe$',
    re.IGNORECASE
)

# Characters that are never allowed in registry key names
DANGEROUS_CHARS = {'\\', '/', ':', '*', '?', '"', '<', '>', '|', '\0'}

# Maximum reasonable path length
MAX_PATH_LENGTH = 260


def validate_executable_name(exe_name: str) -> str:
    """Validate an executable name is safe for registry operations.

    Args:
        exe_name: The executable name to validate (e.g., "game.exe")

    Returns:
        The validated executable name.

    Raises:
        ValidationError: If the name is invalid or potentially dangerous.

    Examples:
        >>> validate_executable_name("Dolphin.exe")
        'Dolphin.exe'
        >>> validate_executable_name("..\\..\\system32\\cmd.exe")
        ValidationError: Executable name contains path separators
    """
    if not exe_name:
        raise ValidationError("Executable name cannot be empty")

    if not isinstance(exe_name, str):
        raise ValidationError(f"Executable name must be a string, got {type(exe_name).__name__}")

    # Check length
    if len(exe_name) > 255:
        raise ValidationError(f"Executable name too long: {len(exe_name)} characters (max 255)")

    # Check for path separators (path traversal attempt)
    if '\\' in exe_name or '/' in exe_name:
        raise ValidationError(
            f"Executable name contains path separators: {exe_name!r}. "
            "Only the filename is allowed, not a path."
        )

    # Check for dangerous characters
    found_dangerous = DANGEROUS_CHARS.intersection(exe_name)
    if found_dangerous:
        raise ValidationError(
            f"Executable name contains invalid characters: {found_dangerous}"
        )

    # Check pattern match
    if not EXECUTABLE_NAME_PATTERN.match(exe_name):
        raise ValidationError(
            f"Invalid executable name format: {exe_name!r}. "
            "Must be a valid .exe filename (e.g., 'game.exe')"
        )

    # Prevent reserved Windows names
    reserved_names = {
        'CON', 'PRN', 'AUX', 'NUL',
        'COM1', 'COM2', 'COM3', 'COM4', 'COM5', 'COM6', 'COM7', 'COM8', 'COM9',
        'LPT1', 'LPT2', 'LPT3', 'LPT4', 'LPT5', 'LPT6', 'LPT7', 'LPT8', 'LPT9',
    }
    name_without_ext = exe_name.rsplit('.', 1)[0].upper()
    if name_without_ext in reserved_names:
        raise ValidationError(f"Executable name uses reserved Windows name: {exe_name}")

    return exe_name


def validate_executable_path(exe_path: str) -> str:
    """Validate a full executable path is safe for registry operations.

    Args:
        exe_path: The full path to validate (e.g., "C:\\Games\\game.exe")

    Returns:
        The validated path.

    Raises:
        ValidationError: If the path is invalid or potentially dangerous.
    """
    if not exe_path:
        raise ValidationError("Executable path cannot be empty")

    if not isinstance(exe_path, str):
        raise ValidationError(f"Executable path must be a string, got {type(exe_path).__name__}")

    # Check length
    if len(exe_path) > MAX_PATH_LENGTH:
        raise ValidationError(f"Path too long: {len(exe_path)} characters (max {MAX_PATH_LENGTH})")

    # Check for null bytes
    if '\0' in exe_path:
        raise ValidationError("Path contains null bytes")

    # Parse as Windows path
    try:
        path = PureWindowsPath(exe_path)
    except Exception as e:
        raise ValidationError(f"Invalid path format: {e}")

    # Must be an absolute path or just a filename
    # Relative paths with .. are suspicious
    path_str = str(path)
    if '..' in path_str:
        raise ValidationError(
            f"Path contains parent directory reference (..): {exe_path!r}. "
            "This could be a path traversal attempt."
        )

    # Must end with .exe
    if not path.suffix.lower() == '.exe':
        raise ValidationError(f"Path must end with .exe: {exe_path!r}")

    # Validate the filename part
    validate_executable_name(path.name)

    return exe_path


def validate_dword_value(value: int, name: str, min_val: int = 0, max_val: int = 0xFFFFFFFF) -> int:
    """Validate a DWORD registry value is within acceptable range.

    Args:
        value: The value to validate.
        name: Name of the setting (for error messages).
        min_val: Minimum acceptable value.
        max_val: Maximum acceptable value.

    Returns:
        The validated value.

    Raises:
        ValidationError: If the value is out of range.
    """
    if not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer, got {type(value).__name__}")

    if value < min_val or value > max_val:
        raise ValidationError(
            f"{name} value {value} is out of range. "
            f"Must be between {min_val} and {max_val}."
        )

    return value


def validate_priority_value(value: int, name: str, valid_values: set[int] | None = None) -> int:
    """Validate a priority value.

    Args:
        value: The priority value to validate.
        name: Name of the setting (for error messages).
        valid_values: Optional set of valid values. If None, accepts 0-255.

    Returns:
        The validated value.

    Raises:
        ValidationError: If the value is invalid.
    """
    if not isinstance(value, int):
        raise ValidationError(f"{name} must be an integer, got {type(value).__name__}")

    if valid_values is not None:
        if value not in valid_values:
            raise ValidationError(
                f"{name} value {value} is not valid. "
                f"Must be one of: {sorted(valid_values)}"
            )
    else:
        if value < 0 or value > 255:
            raise ValidationError(
                f"{name} value {value} is out of range. "
                "Must be between 0 and 255."
            )

    return value


def validate_registry_string(value: str, name: str, max_length: int = 16383) -> str:
    """Validate a string value for registry storage.

    Args:
        value: The string to validate.
        name: Name of the setting (for error messages).
        max_length: Maximum allowed length.

    Returns:
        The validated string.

    Raises:
        ValidationError: If the string is invalid.
    """
    if not isinstance(value, str):
        raise ValidationError(f"{name} must be a string, got {type(value).__name__}")

    if len(value) > max_length:
        raise ValidationError(
            f"{name} is too long: {len(value)} characters (max {max_length})"
        )

    # Check for null bytes
    if '\0' in value:
        raise ValidationError(f"{name} contains null bytes")

    return value
