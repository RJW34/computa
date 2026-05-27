"""Regression tests for tray startup profile resolution."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
STARTUP_STATE_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-StartupState.ps1"


def _resolve_startup_profile(
    tmp_path: Path,
    *,
    config: dict[str, object],
    project_state: dict[str, object] | None = None,
    local_state: dict[str, object] | None = None,
) -> dict[str, object]:
    project_root = tmp_path / "project"
    project_root.mkdir()

    state_candidates: list[str] = []

    if project_state is not None:
        project_state_path = project_root / ".abso_state.json"
        project_state_path.write_text(json.dumps(project_state), encoding="utf-8")
        state_candidates.append(str(project_state_path))

    if local_state is not None:
        local_root = tmp_path / "localapp"
        local_root.mkdir()
        local_state_path = local_root / ".abso_state.json"
        local_state_path.write_text(json.dumps(local_state), encoding="utf-8")
        state_candidates.append(str(local_state_path))

    candidate_literal = ", ".join(
        "'" + path.replace("'", "''") + "'" for path in state_candidates
    )
    config_json = json.dumps(config)
    ps_script = tmp_path / "resolve-startup-state.ps1"
    ps_script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f". '{STARTUP_STATE_SCRIPT}'",
                "$profiles = [ordered]@{",
                "  'slippi-melee' = @{ Name = 'Slippi Melee (Competitive)' }",
                "  'overwatch2-gsync' = @{ Name = 'Overwatch 2 - GSYNC' }",
                "  'overwatch2-gsync-hdr' = @{ Name = 'Overwatch 2 - GSYNC HDR' }",
                "  'overwatch2-gsync-hdr-capture' = @{ Name = 'Overwatch 2 - GSYNC HDR Capture' }",
                "  'deadlock-hdr' = @{ Name = 'Deadlock - No Sync HDR' }",
                "}",
                "$config = @'",
                config_json,
                "'@ | ConvertFrom-Json",
                f"$stateCandidates = @({candidate_literal})",
                "$result = Resolve-StartupActiveProfile -Config $config -StateCandidates $stateCandidates -ProfileMap $profiles",
                "$result | ConvertTo-Json -Depth 6 -Compress",
            ]
        ),
        encoding="utf-8",
    )

    completed = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_script),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(completed.stdout)


def _repair_startup_profile_state(tmp_path: Path) -> bytes:
    state_path = tmp_path / ".abso_state.json"
    ps_script = tmp_path / "repair-startup-state.ps1"
    escaped_state_path = str(state_path).replace("'", "''")
    ps_script.write_text(
        "\n".join(
            [
                "$ErrorActionPreference = 'Stop'",
                f". '{STARTUP_STATE_SCRIPT}'",
                "$record = [ordered]@{",
                "  status = 'active'",
                "  id = 'overwatch2-gsync-hdr'",
                "  timestamp = '2026-05-26T23:08:44.711941'",
                f"  sync_state_path = '{escaped_state_path}'",
                "}",
                "[void](Repair-StartupActiveProfileState -Record $record)",
            ]
        ),
        encoding="utf-8",
    )

    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(ps_script),
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return state_path.read_bytes()


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_resolution_prefers_newer_recent_history_over_stale_state_file(tmp_path: Path) -> None:
    """Startup restore should not trust an older state file over newer tray history."""
    result = _resolve_startup_profile(
        tmp_path,
        config={
            "recentProfiles": [
                {
                    "id": "overwatch2-gsync",
                    "name": "Overwatch 2 - GSYNC",
                    "timestamp": "2026-03-10 12:49:26",
                    "recorded_at": "2026-03-10T12:49:26",
                }
            ]
        },
        project_state={
            "current_profile": "slippi-melee",
            "applied_at": "2026-02-26T20:58:53",
        },
    )

    assert result["status"] == "active"
    assert result["id"] == "overwatch2-gsync"
    assert result["source"] == "recent_history"
    assert result["decision"] == "resolved_conflict_by_timestamp"


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_resolution_honors_newer_restored_state_over_older_active_candidates(tmp_path: Path) -> None:
    """A newer explicit restore record should suppress stale active profile candidates."""
    result = _resolve_startup_profile(
        tmp_path,
        config={
            "lastProfileState": {
                "status": "restored",
                "timestamp": "2026-03-10T13:00:00",
                "source": "tray_restore",
            },
            "recentProfiles": [
                {
                    "id": "overwatch2-gsync",
                    "name": "Overwatch 2 - GSYNC",
                    "timestamp": "2026-03-10 12:49:26",
                    "recorded_at": "2026-03-10T12:49:26",
                }
            ],
        },
        project_state={
            "current_profile": "slippi-melee",
            "applied_at": "2026-03-10T12:00:00",
        },
    )

    assert result["status"] == "restored"
    assert result["id"] is None
    assert result["source"] == "last_profile_state:tray_restore"
    assert result["decision"] == "resolved_conflict_by_timestamp"


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_resolution_prefers_corroborated_tray_state_over_conflicting_older_state_file(tmp_path: Path) -> None:
    """Tray startup should not be clobbered by an older lone state-file write."""
    result = _resolve_startup_profile(
        tmp_path,
        config={
            "lastProfileState": {
                "status": "active",
                "id": "overwatch2-gsync",
                "name": "Overwatch 2 - GSYNC",
                "timestamp": "2026-04-08T00:20:17.5404388-04:00",
                "source": "tray_apply",
            },
            "recentProfiles": [
                {
                    "id": "overwatch2-gsync",
                    "name": "Overwatch 2 - GSYNC",
                    "timestamp": "2026-04-08 00:20:17",
                    "recorded_at": "2026-04-08T00:20:17.5404388-04:00",
                }
            ],
        },
        project_state={
            "current_profile": "slippi-melee",
            "applied_at": "2026-04-07T12:42:38.770201",
        },
    )

    assert result["status"] == "active"
    assert result["id"] == "overwatch2-gsync"
    assert result["source"] == "last_profile_state:tray_apply"
    assert result["decision"] == "corroborated_tray_state"


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_resolution_honors_newer_cli_state_file_over_stale_corroborated_tray_state(
    tmp_path: Path,
) -> None:
    """A CLI apply state file should beat stale tray cache even if tray cache corroborates itself."""
    result = _resolve_startup_profile(
        tmp_path,
        config={
            "lastProfileState": {
                "status": "active",
                "id": "overwatch2-gsync-hdr-capture",
                "name": "Overwatch 2 - GSYNC HDR Capture",
                "timestamp": "2026-05-26T22:27:32.9327018-04:00",
                "source": "tray_apply",
            },
            "recentProfiles": [
                {
                    "id": "overwatch2-gsync-hdr-capture",
                    "name": "Overwatch 2 - GSYNC HDR Capture",
                    "timestamp": "2026-05-26 22:27:32",
                    "recorded_at": "2026-05-26T22:27:32.9327018-04:00",
                }
            ],
        },
        local_state={
            "current_profile": "overwatch2-gsync-hdr",
            "applied_at": "2026-05-26T23:08:44.711941",
        },
    )

    assert result["status"] == "active"
    assert result["id"] == "overwatch2-gsync-hdr"
    assert result["source"] == "state_file"
    assert result["decision"] == "newer_state_file"


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_resolution_honors_corroborated_newer_cli_state_files(tmp_path: Path) -> None:
    """Mirrored CLI state files should beat older tray history after an external apply."""
    result = _resolve_startup_profile(
        tmp_path,
        config={
            "lastProfileState": {
                "status": "active",
                "id": "deadlock-hdr",
                "name": "Deadlock - No Sync HDR",
                "timestamp": "2026-05-26T00:54:37.1862377-04:00",
                "source": "tray_apply",
            },
            "recentProfiles": [
                {
                    "id": "deadlock-hdr",
                    "name": "Deadlock - No Sync HDR",
                    "recorded_at": "2026-05-26T00:54:37.1862377-04:00",
                }
            ],
        },
        project_state={
            "current_profile": "overwatch2-gsync-hdr-capture",
            "applied_at": "2026-05-26T01:50:15.343758",
        },
        local_state={
            "current_profile": "overwatch2-gsync-hdr-capture",
            "applied_at": "2026-05-26T01:50:15.343758",
        },
    )

    assert result["status"] == "active"
    assert result["id"] == "overwatch2-gsync-hdr-capture"
    assert result["source"] == "state_file"
    assert result["decision"] == "corroborated_state_files_newer"


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_resolution_collapses_recursive_startup_restore_source(
    tmp_path: Path,
) -> None:
    """Repeated tray launches should not grow startup_restore source chains."""
    result = _resolve_startup_profile(
        tmp_path,
        config={
            "lastProfileState": {
                "status": "active",
                "id": "overwatch2-gsync-hdr-capture",
                "name": "Overwatch 2 - GSYNC HDR Capture",
                "timestamp": "2026-05-26T04:40:55.653093",
                "source": (
                    "startup_restore:last_profile_state:"
                    "startup_restore:last_profile_state:state_file"
                ),
            },
        },
    )

    assert result["status"] == "active"
    assert result["id"] == "overwatch2-gsync-hdr-capture"
    assert result["source"] == "last_profile_state:state_file"


@pytest.mark.skipif(sys.platform != "win32", reason="Tray startup resolution tests are Windows-specific")
def test_startup_state_repair_writes_utf8_without_bom(tmp_path: Path) -> None:
    """State repair must stay parseable by Python's strict UTF-8 JSON reader."""
    data = _repair_startup_profile_state(tmp_path)

    assert not data.startswith(b"\xef\xbb\xbf")
    state = json.loads(data.decode("utf-8"))
    assert state["current_profile"] == "overwatch2-gsync-hdr"
