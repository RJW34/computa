"""Atomic file and directory write helpers.

A single, sharp tool against the half-written-JSON class of bug: backup
manifests, state files, config files, and anything else where a crash or
abrupt process exit between open() and flush() would corrupt the target.

All helpers write to a sibling temp path on the same filesystem and swap
with os.replace, which is the documented atomic move on Windows and POSIX.
"""

from __future__ import annotations

import json
import os
import secrets
import shutil
from pathlib import Path
from typing import Any


def _staging_path(path: Path) -> Path:
    """Return a unique sibling path for staged writes."""
    suffix = secrets.token_hex(4)
    return path.with_name(f"{path.name}.tmp-{suffix}")


def atomic_write_text(
    path: Path | str,
    text: str,
    *,
    encoding: str = "utf-8",
    newline: str | None = None,
) -> None:
    """Write text to *path* atomically.

    Writes to ``path.tmp-<random>``, flushes + fsyncs, then os.replaces the
    destination. If any step fails, the destination is left untouched.
    """
    target = Path(path)
    target.parent.mkdir(parents=True, exist_ok=True)

    staging = _staging_path(target)
    try:
        with open(staging, "w", encoding=encoding, newline=newline) as fh:
            fh.write(text)
            fh.flush()
            try:
                os.fsync(fh.fileno())
            except (OSError, AttributeError):
                pass
        os.replace(staging, target)
    except Exception:
        try:
            staging.unlink(missing_ok=True)
        except OSError:
            pass
        raise


def atomic_write_json(
    path: Path | str,
    obj: Any,
    *,
    indent: int | None = 2,
    sort_keys: bool = False,
    default: Any = None,
) -> None:
    """Serialize *obj* as JSON and atomically write to *path*."""
    text = json.dumps(obj, indent=indent, sort_keys=sort_keys, default=default)
    atomic_write_text(path, text + ("\n" if indent is not None else ""))


def atomic_rename_dir(src: Path | str, dst: Path | str) -> None:
    """Atomically move *src* to *dst*.

    Both paths must be on the same filesystem. Windows os.replace rejects
    directory targets that exist; callers are expected to ensure dst does
    not already exist.
    """
    src_path = Path(src)
    dst_path = Path(dst)
    os.replace(src_path, dst_path)


def cleanup_partial(root: Path | str, *, suffix: str = ".partial") -> list[str]:
    """Remove any ``*<suffix>`` children under *root*.

    Returns the list of removed names. Errors are swallowed per-entry so a
    locked partial dir does not break startup cleanup.
    """
    root_path = Path(root)
    if not root_path.is_dir():
        return []

    removed: list[str] = []
    for child in root_path.iterdir():
        if not child.name.endswith(suffix):
            continue
        try:
            if child.is_dir():
                shutil.rmtree(child, ignore_errors=True)
            else:
                child.unlink(missing_ok=True)
            removed.append(child.name)
        except OSError:
            continue
    return removed
