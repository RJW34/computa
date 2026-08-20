"""Safety helpers for deterministic config patching."""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

INI_ASSIGNMENT_RE = re.compile(r"^\s*([A-Za-z0-9_.-]+)\s*=\s*(.*)\s*$")
INI_SECTION_RE = re.compile(r"^\s*\[([^\]]+)\]\s*$")


def _line_without_ending(line: str) -> str:
    """Return *line* without changing anything except its line ending."""
    return line.rstrip("\r\n")


def _line_ending(line: str) -> str:
    """Return the exact line ending used by *line*."""
    return line[len(_line_without_ending(line)):]


def _preferred_line_ending(content: str) -> str:
    """Choose the first line ending already used by *content*."""
    match = re.search(r"\r\n|\n|\r", content)
    return match.group(0) if match else "\n"


def read_config_text(path: Path) -> str:
    """Read UTF-8 config text without universal-newline normalization."""
    with path.open("r", encoding="utf-8", errors="replace", newline="") as stream:
        return stream.read()


def write_config_text(path: Path, content: str) -> None:
    """Write UTF-8 config text without newline translation."""
    with path.open("w", encoding="utf-8", newline="") as stream:
        stream.write(content)


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


def _matching_section_bounds(
    lines: list[str],
    *,
    section_name: str | None,
    section_pattern: re.Pattern[str] | None,
) -> tuple[int, int] | None:
    """Return strict body bounds for an exact or pattern-matched section.

    Headerless files are treated as one implicit section for compatibility
    with Unreal configs written without a section header.  Once a file has any
    section header, however, a missing target never falls back to the whole
    file.  That distinction prevents a restore intended for one game-settings
    section from modifying a same-named key in another section.
    """
    if section_name is None and section_pattern is None:
        return 0, len(lines)

    target_name = (
        _normalize_section_name(section_name).casefold()
        if section_name is not None
        else None
    )
    section_start: int | None = None
    saw_section = False

    for index, line in enumerate(lines):
        stripped = _line_without_ending(line).strip()
        match = INI_SECTION_RE.match(stripped)
        if not match:
            continue

        saw_section = True
        if section_start is not None:
            return section_start, index

        header_matches = False
        if target_name is not None:
            header_matches = match.group(1).strip().casefold() == target_name
        elif section_pattern is not None:
            header_matches = bool(section_pattern.fullmatch(stripped))

        if header_matches:
            section_start = index + 1

    if section_start is not None:
        return section_start, len(lines)
    if not saw_section:
        return 0, len(lines)
    return None


def restore_managed_key_lines(
    current_content: str,
    backup_content: str,
    managed_keys: set[str],
    *,
    assignment_pattern: re.Pattern[str] = INI_ASSIGNMENT_RE,
    section_name: str | None = None,
    section_pattern: re.Pattern[str] | None = None,
) -> str:
    """Restore only handler-owned assignment lines into current content.

    The current file is authoritative for every unmanaged line.  For the
    selected section, managed assignments found in the backup replace or are
    inserted into the current content, while managed assignments absent from
    the backup are removed.  Keys and section names are matched
    case-insensitively.  A selected section is strict: when the current file
    contains section headers but not the requested section, this is a no-op.

    Assignment patterns must expose the key as capture group 1.  The complete
    backed-up assignment line is reused, which supports ordinary ``key=value``
    INI files, Dolphin's spaced form, OW2's quoted form, and Diablo IV's
    ``Key \"value\"`` form without teaching this helper their value grammars.
    """
    if not managed_keys or not current_content:
        return current_content
    if section_name is not None and section_pattern is not None:
        raise ValueError("section_name and section_pattern are mutually exclusive")

    current_lines = current_content.splitlines(keepends=True)
    backup_lines = backup_content.splitlines(keepends=True)
    current_bounds = _matching_section_bounds(
        current_lines,
        section_name=section_name,
        section_pattern=section_pattern,
    )
    if current_bounds is None:
        return current_content

    backup_bounds = _matching_section_bounds(
        backup_lines,
        section_name=section_name,
        section_pattern=section_pattern,
    )
    backup_start, backup_end = backup_bounds or (0, 0)

    normalized_managed = {key.casefold(): key for key in managed_keys}
    backup_assignments: dict[str, str] = {}
    backup_order: list[str] = []
    for line in backup_lines[backup_start:backup_end]:
        raw_line = _line_without_ending(line)
        match = assignment_pattern.match(raw_line)
        if not match:
            continue
        normalized_key = match.group(1).casefold()
        if normalized_key not in normalized_managed:
            continue
        if normalized_key not in backup_assignments:
            backup_order.append(normalized_key)
        # Last occurrence wins, matching parse_ini_assignments().
        backup_assignments[normalized_key] = raw_line

    current_start, current_end = current_bounds
    restored_keys: set[str] = set()
    restored_body: list[str] = []
    for line in current_lines[current_start:current_end]:
        raw_line = _line_without_ending(line)
        match = assignment_pattern.match(raw_line)
        if not match:
            restored_body.append(line)
            continue

        normalized_key = match.group(1).casefold()
        if normalized_key not in normalized_managed:
            restored_body.append(line)
            continue

        backup_line = backup_assignments.get(normalized_key)
        if backup_line is None:
            # The handler owned this current key but it did not exist at the
            # time of backup, so restoring the old state means removing it.
            continue

        restored_body.append(backup_line + _line_ending(line))
        restored_keys.add(normalized_key)

    missing_keys = [key for key in backup_order if key not in restored_keys]
    if missing_keys:
        preferred_ending = _preferred_line_ending(current_content)
        has_suffix = current_end < len(current_lines)
        had_trailing_ending = bool(current_lines and _line_ending(current_lines[-1]))

        if restored_body and not _line_ending(restored_body[-1]):
            restored_body[-1] += preferred_ending

        for index, normalized_key in enumerate(missing_keys):
            is_last_file_line = (
                not has_suffix
                and index == len(missing_keys) - 1
                and not had_trailing_ending
            )
            ending = "" if is_last_file_line else preferred_ending
            restored_body.append(backup_assignments[normalized_key] + ending)

    restored_lines = (
        current_lines[:current_start]
        + restored_body
        + current_lines[current_end:]
    )
    return "".join(restored_lines)


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
