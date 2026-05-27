"""Active-profile state-file read/write helpers."""

from __future__ import annotations

import json
from collections.abc import Callable
from pathlib import Path
from typing import Any

from abso.core.state_reconcile import parse_state_timestamp
from abso.profiles.catalog import resolve_profile_id
from abso.utils.atomic_io import atomic_write_json


def default_state_snapshot() -> dict[str, Any]:
    """Return the empty active-profile state shape."""
    return {
        "current_profile": None,
        "applied_at": None,
        "reboot_pending": False,
        "reboot_reasons": [],
    }


def sanitize_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Return the public active-profile state shape with canonical profile id."""
    return {
        "current_profile": resolve_profile_id(state.get("current_profile")),
        "applied_at": state.get("applied_at"),
        "reboot_pending": bool(state.get("reboot_pending", False)),
        "reboot_reasons": list(state.get("reboot_reasons") or []),
    }


def read_state_file(path: Path) -> dict[str, Any] | None:
    """Read and sanitize one state-file candidate."""
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(state, dict):
        return None
    return sanitize_state_snapshot(state)


def state_sort_value(path: Path, state: dict[str, Any]) -> float:
    """Return a comparable freshness value for a state candidate."""
    applied_at_ts = parse_state_timestamp(state.get("applied_at"))
    if applied_at_ts is not None:
        return applied_at_ts
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def read_state_snapshot(targets: list[Path]) -> dict[str, Any]:
    """Read the newest valid state snapshot from the configured targets."""
    candidates: list[tuple[float, dict[str, Any]]] = []
    for path in targets:
        state = read_state_file(path)
        if state is None:
            continue
        candidates.append((state_sort_value(path, state), state))

    if not candidates:
        return default_state_snapshot()

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def write_state_snapshot(
    targets: list[Path],
    state: dict[str, Any],
    *,
    writer: Callable[..., None] = atomic_write_json,
) -> list[dict[str, str]]:
    """Write state to the primary target and best-effort mirrors.

    Primary write failures are authoritative and are allowed to raise. Mirror
    failures are returned as structured warnings so callers can decide whether
    to surface them or only log them.
    """
    if not targets:
        raise ValueError("At least one state-file target is required")

    writer(targets[0], state, indent=2)

    mirror_warnings: list[dict[str, str]] = []
    for target in targets[1:]:
        try:
            writer(target, state, indent=2)
        except OSError as exc:
            mirror_warnings.append({"path": str(target), "error": str(exc)})

    return mirror_warnings


def remove_state_targets(targets: list[Path]) -> list[dict[str, str]]:
    """Remove primary and mirrored state files.

    Primary removal failures are authoritative and are allowed to raise. Mirror
    failures are returned as structured warnings.
    """
    mirror_warnings: list[dict[str, str]] = []
    for index, path in enumerate(targets):
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            if index == 0:
                raise
            mirror_warnings.append({"path": str(path), "error": str(exc)})
    return mirror_warnings
