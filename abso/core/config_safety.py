"""Safety helpers for deterministic config patching."""

from __future__ import annotations

import re
from dataclasses import dataclass

INI_ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)\s*$")


def validate_allowed_keys(requested_keys: set[str], allowed_keys: set[str]) -> list[str]:
    """Return unsupported keys from a requested setting set."""
    return sorted(k for k in requested_keys if k not in allowed_keys)


def parse_ini_assignments(lines: list[str]) -> dict[str, str]:
    """Parse simple key=value INI assignments into a dictionary."""
    assignments: dict[str, str] = {}
    for line in lines:
        match = INI_ASSIGNMENT_RE.match(line)
        if not match:
            continue
        key, value = match.group(1), match.group(2)
        assignments[key] = value
    return assignments


@dataclass
class IniPatchResult:
    """Result of applying key-value patch operations to INI content."""

    lines: list[str]
    changed_keys: set[str]
    appended_keys: set[str]
    unchanged_keys: set[str]

    @property
    def changed(self) -> bool:
        return bool(self.changed_keys or self.appended_keys)


def apply_ini_key_patch(
    lines: list[str],
    replacements: dict[str, str],
    append_missing: bool = False,
) -> IniPatchResult:
    """Apply deterministic key=value replacements while preserving other lines."""
    output: list[str] = []
    seen: set[str] = set()
    changed: set[str] = set()
    appended: set[str] = set()

    for line in lines:
        match = INI_ASSIGNMENT_RE.match(line)
        if not match:
            output.append(line)
            continue

        key = match.group(1)
        current_value = match.group(2)
        if key not in replacements:
            output.append(line)
            continue

        target_value = replacements[key]
        seen.add(key)
        output.append(f"{key}={target_value}")
        if current_value != target_value:
            changed.add(key)

    if append_missing:
        for key, value in replacements.items():
            if key in seen:
                continue
            output.append(f"{key}={value}")
            appended.add(key)

    unchanged = set(replacements) - changed - appended
    return IniPatchResult(
        lines=output,
        changed_keys=changed,
        appended_keys=appended,
        unchanged_keys=unchanged,
    )
