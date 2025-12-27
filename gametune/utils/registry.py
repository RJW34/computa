"""Registry utility functions for safe registry operations.

This module provides helper functions to reduce code duplication
across settings handlers when reading/writing Windows registry values.
"""

from __future__ import annotations

import logging
import winreg
from typing import Any

from gametune.core.exceptions import RegistryReadError, RegistryWriteError

logger = logging.getLogger(__name__)


def read_registry_value(
    hive: int,
    key_path: str,
    value_name: str,
    default: Any = None,
) -> Any:
    """Read a value from the Windows registry.

    Args:
        hive: Registry hive (e.g., winreg.HKEY_LOCAL_MACHINE).
        key_path: Path to the registry key.
        value_name: Name of the value to read.
        default: Default value if the key/value doesn't exist.

    Returns:
        The registry value, or default if not found.

    Raises:
        RegistryReadError: If registry access fails (other than key not found).
    """
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        try:
            value, _ = winreg.QueryValueEx(key, value_name)
            return value
        except FileNotFoundError:
            return default
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        return default
    except PermissionError as e:
        raise RegistryReadError(
            f"Permission denied reading {key_path}\\{value_name}",
            details=str(e)
        )
    except OSError as e:
        raise RegistryReadError(
            f"Failed to read {key_path}\\{value_name}",
            details=str(e)
        )


def write_registry_value(
    hive: int,
    key_path: str,
    value_name: str,
    value: Any,
    value_type: int = winreg.REG_DWORD,
    create_key: bool = False,
) -> None:
    """Write a value to the Windows registry.

    Args:
        hive: Registry hive (e.g., winreg.HKEY_LOCAL_MACHINE).
        key_path: Path to the registry key.
        value_name: Name of the value to write.
        value: The value to write.
        value_type: Registry value type (default: REG_DWORD).
        create_key: If True, create the key if it doesn't exist.

    Raises:
        RegistryWriteError: If registry write fails.
    """
    try:
        if create_key:
            key = winreg.CreateKey(hive, key_path)
        else:
            key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_ALL_ACCESS)

        try:
            winreg.SetValueEx(key, value_name, 0, value_type, value)
        finally:
            winreg.CloseKey(key)

    except FileNotFoundError as e:
        raise RegistryWriteError(
            f"Registry key not found: {key_path}",
            details=str(e)
        )
    except PermissionError as e:
        raise RegistryWriteError(
            f"Permission denied writing to {key_path}\\{value_name}",
            details=f"Run as administrator. ({e})"
        )
    except OSError as e:
        raise RegistryWriteError(
            f"Failed to write {key_path}\\{value_name}",
            details=str(e)
        )


def delete_registry_value(
    hive: int,
    key_path: str,
    value_name: str,
    ignore_missing: bool = True,
) -> bool:
    """Delete a value from the Windows registry.

    Args:
        hive: Registry hive (e.g., winreg.HKEY_LOCAL_MACHINE).
        key_path: Path to the registry key.
        value_name: Name of the value to delete.
        ignore_missing: If True, don't raise error if value doesn't exist.

    Returns:
        True if value was deleted, False if it didn't exist.

    Raises:
        RegistryWriteError: If deletion fails.
    """
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_ALL_ACCESS)
        try:
            winreg.DeleteValue(key, value_name)
            return True
        except FileNotFoundError:
            if ignore_missing:
                return False
            raise RegistryWriteError(
                f"Value not found: {key_path}\\{value_name}"
            )
        finally:
            winreg.CloseKey(key)
    except FileNotFoundError:
        if ignore_missing:
            return False
        raise RegistryWriteError(f"Key not found: {key_path}")
    except PermissionError as e:
        raise RegistryWriteError(
            f"Permission denied deleting {key_path}\\{value_name}",
            details=f"Run as administrator. ({e})"
        )
    except OSError as e:
        raise RegistryWriteError(
            f"Failed to delete {key_path}\\{value_name}",
            details=str(e)
        )


def key_exists(hive: int, key_path: str) -> bool:
    """Check if a registry key exists.

    Args:
        hive: Registry hive.
        key_path: Path to the registry key.

    Returns:
        True if the key exists, False otherwise.
    """
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        winreg.CloseKey(key)
        return True
    except FileNotFoundError:
        return False
    except (PermissionError, OSError):
        # Can't access, but key might exist
        return False


def value_exists(hive: int, key_path: str, value_name: str) -> bool:
    """Check if a registry value exists.

    Args:
        hive: Registry hive.
        key_path: Path to the registry key.
        value_name: Name of the value.

    Returns:
        True if the value exists, False otherwise.
    """
    try:
        key = winreg.OpenKey(hive, key_path, 0, winreg.KEY_READ)
        try:
            winreg.QueryValueEx(key, value_name)
            return True
        except FileNotFoundError:
            return False
        finally:
            winreg.CloseKey(key)
    except (FileNotFoundError, PermissionError, OSError):
        return False


def read_registry_dword(
    hive: int,
    key_path: str,
    value_name: str,
    default: int | None = None,
) -> int | None:
    """Read a DWORD value from the Windows registry.

    Convenience function that validates the return type.

    Args:
        hive: Registry hive.
        key_path: Path to the registry key.
        value_name: Name of the value to read.
        default: Default value if the key/value doesn't exist.

    Returns:
        The registry value as an integer, or default if not found.
    """
    value = read_registry_value(hive, key_path, value_name, default)
    if value is None:
        return default
    if isinstance(value, int):
        return value
    # Try to convert string values
    try:
        return int(value)
    except (ValueError, TypeError):
        logger.warning(f"Expected DWORD for {key_path}\\{value_name}, got {type(value)}")
        return default


def read_registry_string(
    hive: int,
    key_path: str,
    value_name: str,
    default: str | None = None,
) -> str | None:
    """Read a string value from the Windows registry.

    Args:
        hive: Registry hive.
        key_path: Path to the registry key.
        value_name: Name of the value to read.
        default: Default value if the key/value doesn't exist.

    Returns:
        The registry value as a string, or default if not found.
    """
    value = read_registry_value(hive, key_path, value_name, default)
    if value is None:
        return default
    return str(value)
