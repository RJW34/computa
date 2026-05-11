"""Safety helpers for deterministic config patching."""

from __future__ import annotations

import re
from dataclasses import dataclass

INI_ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)\s*$")
INI_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def validate_allowed_keys(requested_keys: set[str], allowed_keys: set[str]) -> list[str]:
    """Return unsupported keys from a requested setting set."""
    return sorted(k for k in requested_keys if k not in allowed_keys)


def _normalize_section_name(section_name: str) -> str:
    """Normalize a caller-supplied INI section name."""
    section_name = section_name.strip()
    if section_name.startswith("[") and section_name.endswith("]"):
        section_name = section_name[1:-1]
    return section_name.strip()


def find_ini_section_bounds(
    lines: list[str],
    section_name: str | None,
) -> tuple[int, int] | None:
    """Return the body bounds for an INI section, or None when absent."""
    if not section_name:
        return None

    target = _normalize_section_name(section_name).lower()
    section_start: int | None = None

    for index, line in enumerate(lines):
        match = INI_SECTION_RE.match(line)
        if not match:
            continue

        if section_start is not None:
            return section_start, index

        if match.group(1).strip().lower() == target:
            section_start = index + 1

    if section_start is None:
        return None
    return section_start, len(lines)


def parse_ini_assignments(
    lines: list[str],
    section_name: str | None = None,
) -> dict[str, str]:
    """Parse simple key=value INI assignments into a dictionary."""
    assignments: dict[str, str] = {}
    bounds = find_ini_section_bounds(lines, section_name)
    parse_lines = lines
    if bounds is not None:
        start, end = bounds
        parse_lines = lines[start:end]

    for line in parse_lines:
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
    section_name: str | None = None,
) -> IniPatchResult:
    """Apply deterministic key=value replacements while preserving other lines."""
    output = list(lines)
    seen: set[str] = set()
    changed: set[str] = set()
    appended: set[str] = set()

    bounds = find_ini_section_bounds(lines, section_name)
    patch_start, patch_end = bounds if bounds is not None else (0, len(lines))

    for index in range(patch_start, patch_end):
        line = output[index]
        match = INI_ASSIGNMENT_RE.match(line)
        if not match:
            continue

        key = match.group(1)
        current_value = match.group(2)
        if key not in replacements:
            continue

        target_value = replacements[key]
        seen.add(key)
        output[index] = f"{key}={target_value}"
        if current_value != target_value:
            changed.add(key)

    if append_missing:
        missing_lines: list[str] = []
        for key, value in replacements.items():
            if key in seen:
                continue
            missing_lines.append(f"{key}={value}")
            appended.add(key)
        if missing_lines:
            if bounds is not None:
                output[patch_end:patch_end] = missing_lines
            else:
                output.extend(missing_lines)

    unchanged = set(replacements) - changed - appended
    return IniPatchResult(
        lines=output,
        changed_keys=changed,
        appended_keys=appended,
        unchanged_keys=unchanged,
    )
