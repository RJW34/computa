"""Tests for the non-interactive setup engine behind the GUI installer."""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import MagicMock, patch

from abso.core.setup_flow import (
    UnattendedOptions,
    _planned_steps,
    build_setup_plan,
    run_unattended_setup,
)


class _Collector:
    """Collects emitted events, proving each is JSON-serializable."""

    def __init__(self) -> None:
        self.events: list[dict] = []

    def __call__(self, obj: dict) -> None:
        json.dumps(obj)
        self.events.append(obj)

    def step_events(self, step_id: str) -> list[dict]:
        return [
            e for e in self.events if e.get("event") == "step" and e.get("id") == step_id
        ]

    def start_step_ids(self) -> list[str]:
        start = next(e for e in self.events if e.get("event") == "start")
        return [s["id"] for s in start["steps"]]


def test_build_setup_plan_shape() -> None:
    hardware = {
        "gpu": {"name": "AMD Radeon RX 7800 XT"},
        "cpu": {"name": "AMD Ryzen 7 7800X3D"},
        "ram": {"total_gb": 32},
        "monitors": [
            {"name": "Slow Office Panel", "refresh_rate": 60},
            {"name": "Fast Panel", "refresh_rate": 240},
        ],
    }
    kb = SimpleNamespace(kb_id="KB123", title="Bad update", affected="NVIDIA GPUs")
    game = SimpleNamespace(name="Fortnite")

    detector = MagicMock()
    detector.detect_all.return_value = hardware
    with (
        patch("abso.core.detector.HardwareDetector", return_value=detector),
        patch("abso.core.kb_checker.get_installed_kbs", return_value=["KB123"]),
        patch("abso.core.kb_checker.check_problematic_kbs", return_value=[kb]),
        patch(
            "abso.core.game_detector.get_profile_suggestions",
            return_value={"fortnite": [game, game]},
        ),
    ):
        plan = build_setup_plan()

    assert plan["gpu_vendor"] == "amd"
    assert "Radeon" in plan["gpu_vendor_note"]
    # The summary leads with the fastest display, not enumeration order.
    assert "240" in plan["hardware"]["monitor"]
    assert plan["hardware"]["monitor_count"] == 2
    assert plan["problematic_kbs"] == [
        {"kb_id": "KB123", "title": "Bad update", "affected": "NVIDIA GPUs"}
    ]
    # Duplicate game names collapse for display.
    assert plan["detected_games"] == [{"profile": "fortnite", "games": ["Fortnite"]}]
    json.dumps(plan)


def test_build_setup_plan_survives_detection_failure() -> None:
    with (
        patch("abso.core.detector.HardwareDetector", side_effect=RuntimeError("wmi down")),
        patch("abso.core.kb_checker.get_installed_kbs", side_effect=RuntimeError("no")),
        patch(
            "abso.core.game_detector.get_profile_suggestions",
            side_effect=RuntimeError("no"),
        ),
    ):
        plan = build_setup_plan()

    assert plan["hardware"] == {}
    assert plan["problematic_kbs"] == []
    assert plan["detected_games"] == []


def test_planned_steps_reflect_options() -> None:
    assert _planned_steps(UnattendedOptions()) == [
        "tray_assets",
        "config",
        "baseline",
        "state",
    ]
    assert _planned_steps(
        UnattendedOptions(
            baseline=False,
            create_config=False,
            tray_autostart=True,
            remove_kbs=("KB1",),
        )
    ) == ["tray_assets", "windows_updates", "tray_autostart", "state"]


def test_run_unattended_setup_executes_toggled_actions(tmp_path: Path, monkeypatch) -> None:
    local_root = tmp_path / "localappdata"
    monkeypatch.setenv("LOCALAPPDATA", str(local_root))
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    backup_manager = MagicMock()
    backup_manager.create_backup.return_value = "2026-07-20_010101"

    events = _Collector()
    with (
        patch("abso.core.backup.BackupManager", return_value=backup_manager),
        patch("abso.tray.install_startup") as mock_startup,
        patch("abso.tray.deploy_tray_assets", return_value=None),
    ):
        result = run_unattended_setup(
            UnattendedOptions(baseline=True, create_config=True, tray_autostart=True),
            emit=events,
            data_dir=data_dir,
        )

    assert result["success"] is True
    assert result["baseline_backup_id"] == "2026-07-20_010101"
    backup_manager.create_backup.assert_called_once_with(
        profile_id=None,
        backup_type="baseline",
    )
    mock_startup.assert_called_once()

    # Config lands in the (redirected) install dir, never the cwd.
    assert (local_root / "AdaptiveBattleStationOptimizer" / "abso.yaml").exists()

    state = json.loads((data_dir / ".abso_state.json").read_text(encoding="utf-8"))
    assert state["setup_completed"] is True
    assert state["baseline_backup_id"] == "2026-07-20_010101"
    assert state["current_profile"] is None

    assert events.start_step_ids() == [
        "tray_assets",
        "config",
        "baseline",
        "tray_autostart",
        "state",
    ]
    assert events.step_events("baseline")[-1]["status"] == "ok"


def test_run_unattended_setup_preserves_existing_profile_state(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()
    state_file = data_dir / ".abso_state.json"
    state_file.write_text(
        json.dumps({
            "current_profile": "overwatch2-hdr",
            "applied_at": "2026-07-19T20:00:00",
            "reboot_pending": True,
            "reboot_reasons": ["HAGS"],
            "baseline_backup_id": "2026-07-01_090000",
        }),
        encoding="utf-8",
    )

    events = _Collector()
    result = run_unattended_setup(
        UnattendedOptions(baseline=False, create_config=False, tray_autostart=False),
        emit=events,
        data_dir=data_dir,
    )

    assert result["success"] is True
    state = json.loads(state_file.read_text(encoding="utf-8"))
    assert state["current_profile"] == "overwatch2-hdr"
    assert state["reboot_pending"] is True
    assert state["reboot_reasons"] == ["HAGS"]
    assert state["setup_completed"] is True
    # No new baseline requested: the original anchor is kept.
    assert state["baseline_backup_id"] == "2026-07-01_090000"


def test_run_unattended_setup_reports_baseline_failure(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    backup_manager = MagicMock()
    backup_manager.create_backup.side_effect = RuntimeError("access denied")

    events = _Collector()
    with patch("abso.core.backup.BackupManager", return_value=backup_manager):
        result = run_unattended_setup(
            UnattendedOptions(baseline=True, create_config=False, tray_autostart=False),
            emit=events,
            data_dir=data_dir,
        )

    assert result["success"] is False
    assert events.step_events("baseline")[-1]["status"] == "error"
    # Later steps still ran: setup completion is still recorded.
    state = json.loads((data_dir / ".abso_state.json").read_text(encoding="utf-8"))
    assert state["setup_completed"] is True


def test_run_unattended_setup_removes_requested_kbs(tmp_path: Path) -> None:
    data_dir = tmp_path / "data"
    data_dir.mkdir()

    events = _Collector()
    with patch("abso.core.kb_checker.uninstall_kb", return_value=True) as mock_uninstall:
        result = run_unattended_setup(
            UnattendedOptions(
                baseline=False,
                create_config=False,
                remove_kbs=("KB5074109",),
            ),
            emit=events,
            data_dir=data_dir,
        )

    mock_uninstall.assert_called_once_with("KB5074109")
    assert result["success"] is True
    assert result["needs_reboot"] is True
    assert result["reboot_reasons"] == ["KB5074109 removal"]


def test_deploy_tray_assets_copies_bundle(tmp_path: Path) -> None:
    from abso.tray import deploy_tray_assets

    dest = deploy_tray_assets(dest_root=tmp_path)

    assert dest == tmp_path / "abso" / "tray"
    assert (dest / "ABSO-Tray.ps1").exists()
    assert (dest / "ABSO-Tray.vbs").exists()
    assert (dest / "Install-Startup.ps1").exists()


def test_deploy_tray_assets_noop_from_source() -> None:
    from abso.tray import deploy_tray_assets

    assert deploy_tray_assets() is None
