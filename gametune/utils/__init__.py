"""Utility modules."""

from gametune.utils.admin import is_admin, ensure_admin
from gametune.utils.registry import (
    read_registry_value,
    write_registry_value,
    delete_registry_value,
    key_exists,
    value_exists,
    read_registry_dword,
    read_registry_string,
)
from gametune.utils.validation import (
    ValidationError,
    validate_executable_name,
    validate_executable_path,
    validate_dword_value,
    validate_priority_value,
    validate_registry_string,
)

__all__ = [
    # Admin utilities
    "is_admin",
    "ensure_admin",
    # Registry utilities
    "read_registry_value",
    "write_registry_value",
    "delete_registry_value",
    "key_exists",
    "value_exists",
    "read_registry_dword",
    "read_registry_string",
    # Validation utilities
    "ValidationError",
    "validate_executable_name",
    "validate_executable_path",
    "validate_dword_value",
    "validate_priority_value",
    "validate_registry_string",
]
