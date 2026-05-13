"""Utility modules."""

from abso.utils.admin import ensure_admin, is_admin
from abso.utils.os_release import OsRelease, detect_os_release, invalidate_cache
from abso.utils.registry import (
    delete_registry_value,
    key_exists,
    read_registry_dword,
    read_registry_string,
    read_registry_value,
    value_exists,
    write_registry_value,
)
from abso.utils.validation import (
    ValidationError,
    validate_dword_value,
    validate_executable_name,
    validate_executable_path,
    validate_priority_value,
    validate_registry_string,
)

__all__ = [
    # Admin utilities
    "is_admin",
    "ensure_admin",
    # OS release introspection
    "OsRelease",
    "detect_os_release",
    "invalidate_cache",
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
