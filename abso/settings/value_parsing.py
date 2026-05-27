"""Small value coercion helpers shared by settings handlers."""

from __future__ import annotations

from typing import Any

TRUE_STRINGS = frozenset({"1", "true", "yes", "on"})
FALSE_STRINGS = frozenset({"0", "false", "no", "off"})


def parse_bool_like(value: Any) -> bool | None:
    """Return a bool for common bool-like values, or ``None`` when unsupported."""
    if isinstance(value, bool):
        return value
    if isinstance(value, int | float):
        return bool(value)
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in TRUE_STRINGS:
            return True
        if lowered in FALSE_STRINGS:
            return False
    return None
