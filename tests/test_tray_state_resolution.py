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
def test_startup_resolution_prefers_corroborated_tray_state_over_conflicting_newer_state_file(tmp_path: Path) -> None:
    """Tray startup should trust its corroborated last successful apply over a lone conflicting state-file write."""
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
            "applied_at": "2026-04-08T12:42:38.770201",
        },
    )

    assert result["status"] == "active"
    assert result["id"] == "overwatch2-gsync"
    assert result["source"] == "last_profile_state:tray_apply"
    assert result["decision"] == "corroborated_tray_state"
