"""Tests for active-profile state-file helpers."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from abso.core.state_store import read_state_snapshot, write_state_snapshot
from abso.utils.atomic_io import atomic_write_json


def test_read_state_snapshot_prefers_newest_valid_applied_at(tmp_path: Path) -> None:
    """Mirrored state readers should choose the freshest valid state file."""
    primary = tmp_path / "repo" / ".abso_state.json"
    mirror = tmp_path / "local" / ".abso_state.json"
    primary.parent.mkdir(parents=True)
    mirror.parent.mkdir(parents=True)
    primary.write_text(
        json.dumps(
            {
                "current_profile": "deadlock-hdr",
                "applied_at": "2026-05-26T01:00:00",
                "reboot_pending": False,
            }
        ),
        encoding="utf-8",
    )
    mirror.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T02:00:00",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )

    state = read_state_snapshot([primary, mirror])

    assert state["current_profile"] == "overwatch2-gsync-hdr-capture"
    assert state["reboot_pending"] is True
    assert state["reboot_reasons"] == ["GraphicsSettingsHandler"]


def test_read_state_snapshot_ignores_invalid_json(tmp_path: Path) -> None:
    """A corrupt mirror should not hide a valid primary state file."""
    primary = tmp_path / "repo" / ".abso_state.json"
    mirror = tmp_path / "local" / ".abso_state.json"
    primary.parent.mkdir(parents=True)
    mirror.parent.mkdir(parents=True)
    primary.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T02:00:00",
            }
        ),
        encoding="utf-8",
    )
    mirror.write_text("{not-json", encoding="utf-8")

    state = read_state_snapshot([primary, mirror])

    assert state["current_profile"] == "overwatch2-gsync-hdr-capture"
    assert state["reboot_pending"] is False
    assert state["reboot_reasons"] == []


def test_write_state_snapshot_returns_mirror_warnings(tmp_path: Path) -> None:
    """Primary writes are authoritative while mirror write failures are reported."""
    primary = tmp_path / "repo" / ".abso_state.json"
    mirror = tmp_path / "local" / ".abso_state.json"
    state = {
        "current_profile": "overwatch2-gsync-hdr-capture",
        "applied_at": "2026-05-26T02:00:00",
        "reboot_pending": False,
        "reboot_reasons": [],
    }

    def write_or_fail(path: Path, data: dict[str, Any], *, indent: int | None = None) -> None:
        if path == mirror:
            raise OSError("mirror denied")
        atomic_write_json(path, data, indent=indent)

    warnings = write_state_snapshot([primary, mirror], state, writer=write_or_fail)

    assert warnings == [{"path": str(mirror), "error": "mirror denied"}]
    assert json.loads(primary.read_text(encoding="utf-8")) == state
    assert not mirror.exists()
