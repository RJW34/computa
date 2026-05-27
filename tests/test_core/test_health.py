"""Tests for diagnostics health module."""

from __future__ import annotations

import json
from collections.abc import Callable
from contextlib import ExitStack
from datetime import datetime
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock, patch

from abso.core.display_diagnostics import (
    ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
    ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
    ACTION_REVIEW_SECONDARY_REFRESH_RATE,
)
from abso.core.health import build_health_report, write_health_bundle
from abso.utils.atomic_io import atomic_write_json as real_atomic_write_json


def _build_health_report_with_mocks(
    tmp_path: Path,
    state_file: Path,
    *,
    backups_dir: Path | None = None,
    verify_result: dict[str, Any] | None = None,
    startup_status: dict[str, Any] | None = None,
    tray_runtime: dict[str, Any] | None = None,
    backup_list: list[dict[str, Any]] | None = None,
    backup_manager_side_effect: list[Any] | None = None,
    candidate_backup_dirs: list[Path] | None = None,
    boot_time: datetime | None = None,
    state_file_targets: list[Path] | None = None,
    atomic_write_side_effect: Callable[..., None] | None = None,
    marker_pid_running: bool = True,
    include_verify_details: bool = False,
    include_backup_details: bool = False,
    display_stability_snapshot: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Build a health report with stable, non-live dependencies."""
    with ExitStack() as stack:
        stack.enter_context(
            patch(
                "abso.core.health.get_startup_status",
                return_value=startup_status or {"installed": True},
            )
        )
        stack.enter_context(
            patch(
                "abso.core.health.ensure_tray_running",
                return_value=tray_runtime or {"running_after": True},
            )
        )

        if candidate_backup_dirs is not None:
            stack.enter_context(
                patch(
                    "abso.core.health._candidate_backup_dirs",
                    return_value=candidate_backup_dirs,
                )
            )
        mock_backup_cls = stack.enter_context(patch("abso.core.health.BackupManager"))
        if backup_manager_side_effect is not None:
            mock_backup_cls.side_effect = backup_manager_side_effect
        else:
            mock_backup_cls.return_value.list_backups.return_value = (
                backup_list if backup_list is not None else [{"id": "2026-05-26_010101"}]
            )

        mock_config_cls = stack.enter_context(patch("abso.core.health.ConfigManager"))
        mock_config_cls.return_value.validate.return_value = []
        mock_fallback_cls = stack.enter_context(patch("abso.core.health.FallbackController"))
        mock_fallback_cls.return_value.list_all.return_value = []
        mock_applier_cls = stack.enter_context(patch("abso.core.applier.ProfileApplier"))
        mock_applier_cls.return_value.verify_profile.return_value = verify_result or {
            "profile": "overwatch2",
            "all_active": True,
        }
        stack.enter_context(
            patch(
                "abso.core.health.collect_recent_display_events",
                return_value={
                    "supported": True,
                    "lookback_minutes": 360,
                    "max_events": 20,
                    "providers": [],
                    "events": [],
                    "count": 0,
                },
            )
        )
        stack.enter_context(
            patch(
                "abso.core.health.collect_display_stability_snapshot",
                return_value=display_stability_snapshot
                or {
                    "supported": True,
                    "query_scope": "multimon_detector_read_only",
                    "monitor_count": 1,
                    "risk_factors": [],
                    "risk_level": "low",
                },
            )
        )

        if boot_time is not None:
            stack.enter_context(
                patch("abso.core.health.get_system_boot_time", return_value=boot_time)
            )
        if state_file_targets is not None:
            stack.enter_context(
                patch(
                    "abso.core.health.state_file_write_targets",
                    return_value=state_file_targets,
                )
            )
        if atomic_write_side_effect is not None:
            stack.enter_context(
                patch(
                    "abso.core.health.atomic_write_json",
                    side_effect=atomic_write_side_effect,
                )
            )
        stack.enter_context(
            patch("abso.core.health._is_process_running", return_value=marker_pid_running)
        )

        return build_health_report(
            tmp_path,
            backups_dir or tmp_path / "backups",
            state_file,
            include_verify_details=include_verify_details,
            include_backup_details=include_backup_details,
        )


def _write_tray_runtime_marker(
    root_dir: Path,
    *,
    script_body: str = "# tray\n",
    marker_hash: str | None = None,
    marker_pid: int = 1234,
    marker_script_path: str | None = None,
) -> None:
    """Write an installed tray script plus matching or explicit runtime marker."""
    script_path = root_dir / "abso" / "tray" / "ABSO-Tray.ps1"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text(script_body, encoding="utf-8")

    if marker_hash is None:
        import hashlib

        marker_hash = hashlib.sha256(script_path.read_bytes()).hexdigest()

    marker_path = root_dir / "tray-runtime.json"
    marker_path.write_text(
        json.dumps({
            "version": "2.5.0",
            "pid": marker_pid,
            "script_path": marker_script_path or str(script_path),
            "script_hash_sha256": marker_hash,
        }),
        encoding="utf-8",
    )


def test_build_health_report_collects_checks(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    _write_tray_runtime_marker(tmp_path)

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        startup_status={"installed": True, "mode": "scheduled_task"},
        tray_runtime={"running_before": True, "running_after": True, "started": False},
        backup_list=[],
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    assert report["current_profile"] == "overwatch2"
    assert "checks" in report
    assert "summary" in report
    assert "tray_startup" in report["checks"]
    assert report["checks"]["tray_runtime_marker"]["status"] == "ok"
    assert report["checks"]["tray_runtime_marker"]["data"]["marker_pid_running"] is True
    assert report["checks"]["display_events"]["status"] == "ok"
    assert report["checks"]["display_stability"]["status"] == "ok"
    assert report["checks"]["profile_verify"]["status"] == "ok"
    assert report["checks"]["profile_verify"]["data"]["verification_status"] == "active"
    assert report["checks"]["profile_verify"]["data"]["verify_detail_included"] is False
    assert "verify" not in report["checks"]["profile_verify"]["data"]


def test_build_health_report_warns_when_running_tray_has_no_runtime_marker(
    tmp_path: Path,
) -> None:
    """A running tray without marker may still be old in-memory script code."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    script_path = tmp_path / "abso" / "tray" / "ABSO-Tray.ps1"
    script_path.parent.mkdir(parents=True, exist_ok=True)
    script_path.write_text("# tray\n", encoding="utf-8")

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        tray_runtime={"running_after": True},
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    marker_check = report["checks"]["tray_runtime_marker"]
    assert marker_check["status"] == "warning"
    assert marker_check["warnings"] == ["running tray has not written a runtime marker"]


def test_build_health_report_warns_when_running_tray_hash_is_stale(
    tmp_path: Path,
) -> None:
    """A stale marker means the tray should be restarted to load deployed fixes."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    _write_tray_runtime_marker(tmp_path, script_body="# new tray\n", marker_hash="0" * 64)

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        tray_runtime={"running_after": True},
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    marker_check = report["checks"]["tray_runtime_marker"]
    assert marker_check["status"] == "warning"
    assert marker_check["warnings"] == [
        "running tray script hash differs from installed tray script"
    ]


def test_build_health_report_warns_when_tray_marker_pid_is_stale(
    tmp_path: Path,
) -> None:
    """A stale marker file must not certify a crashed tray as current."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    _write_tray_runtime_marker(tmp_path)

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        tray_runtime={"running_after": True},
        verify_result={"profile": "overwatch2", "all_active": True},
        marker_pid_running=False,
    )

    marker_check = report["checks"]["tray_runtime_marker"]
    assert marker_check["status"] == "warning"
    assert marker_check["data"]["marker_pid_running"] is False
    assert marker_check["warnings"] == ["tray runtime marker pid is not running"]


def test_build_health_report_warns_when_tray_marker_path_is_stale(
    tmp_path: Path,
) -> None:
    """A source-script marker should not prove the installed tray is current."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    _write_tray_runtime_marker(
        tmp_path,
        marker_script_path=str(tmp_path / "source" / "ABSO-Tray.ps1"),
    )

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        tray_runtime={"running_after": True},
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    marker_check = report["checks"]["tray_runtime_marker"]
    assert marker_check["status"] == "warning"
    assert marker_check["warnings"] == [
        "running tray script path differs from installed tray script"
    ]


def test_build_health_report_can_include_full_verify_details(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    verify_result = {
        "profile": "overwatch2",
        "all_active": True,
        "handlers": {"WindowsSettingsHandler": {"all_active": True}},
    }

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result=verify_result,
        include_verify_details=True,
    )

    profile_data = report["checks"]["profile_verify"]["data"]
    assert profile_data["verify_detail_included"] is True
    assert profile_data["verify"] == verify_result


def test_build_health_report_warns_on_stale_startup_task_action(tmp_path: Path) -> None:
    """Health should surface startup drift without hiding it in raw JSON."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        startup_status={
            "installed": True,
            "mode": "scheduled_task",
            "task_highest": True,
            "task_action_path_current": False,
            "task_action_arguments": '"C:\\repo\\abso\\tray\\ABSO-Tray.vbs"',
            "task_action_expected_vbs_path": (
                "C:\\Users\\mtoli\\AppData\\Local\\AdaptiveBattleStationOptimizer"
                "\\abso\\tray\\ABSO-Tray.vbs"
            ),
        },
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    startup_check = report["checks"]["tray_startup"]
    assert startup_check["status"] == "warning"
    assert startup_check["warnings"] == [
        "scheduled task action points at a different tray path"
    ]
    assert report["summary"]["warning"] >= 1


def test_build_health_report_accepts_installed_startup_task_action(tmp_path: Path) -> None:
    """Source-mode health should accept a task pointing at installed tray assets."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        startup_status={
            "installed": True,
            "mode": "scheduled_task",
            "task_highest": True,
            "task_action_path_current": False,
            "task_action_path_installed": True,
            "task_action_arguments": (
                '"C:\\Users\\mtoli\\AppData\\Local\\AdaptiveBattleStationOptimizer'
                '\\abso\\tray\\ABSO-StartupLaunch.ps1"'
            ),
        },
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    startup_check = report["checks"]["tray_startup"]
    assert startup_check["status"] == "ok"
    assert "warnings" not in startup_check


def test_build_health_report_warns_on_pending_apply_verify(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "reboot_pending": False,
                "reboot_reasons": [],
            }
        ),
        encoding="utf-8",
    )

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result={
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": False,
            "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
        },
    )

    profile_check = report["checks"]["profile_verify"]
    assert profile_check["status"] == "warning"
    assert profile_check["data"]["verification_status"] == "pending_apply"
    assert profile_check["data"]["verification_summary"]["status"] == "pending_apply"
    assert profile_check["data"]["pending_apply_settings"] == [
        "GraphicsSettingsHandler.mpo_disabled"
    ]
    assert profile_check["data"]["pending_reboot_gated_settings"] == []
    assert profile_check["warnings"] == [
        "active profile has pending apply settings: GraphicsSettingsHandler.mpo_disabled"
    ]


def test_build_health_report_warns_on_display_stability_risk(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result={"profile": "overwatch2-gsync-hdr-capture", "all_active": True},
        boot_time=datetime(2026, 5, 26, 4, 30),
        display_stability_snapshot={
            "supported": True,
            "query_scope": "multimon_detector_read_only",
            "monitor_count": 2,
            "risk_factors": ["multi_monitor", "mixed_refresh", "vrr_capable_display"],
            "risk_level": "high",
            "likely_black_flash_path": "windows_compositor_mpo_vrr_mixed_refresh",
            "warnings": [
                {
                    "code": "MULTIMON_REFRESH_BELOW_CAPABILITY",
                    "message": (
                        "Dell S2719DGF(Displayport) is running at 59.95Hz "
                        "below detected capability 144Hz"
                    ),
                }
            ],
        },
    )

    stability_check = report["checks"]["display_stability"]
    assert stability_check["status"] == "warning"
    assert stability_check["warnings"] == [
        "display topology has compositor black-flash risk factors"
    ]
    assert stability_check["data"]["graphics_reboot_pending"] is True
    assert stability_check["data"]["next_action"] == (
        "Normal reboot required before judging MPO/compositor flicker fix."
    )
    assert [
        action["code"]
        for action in stability_check["data"]["recommended_actions"]
    ] == [
        ACTION_REBOOT_TO_COMMIT_GRAPHICS_SETTINGS,
        ACTION_REVIEW_SECONDARY_REFRESH_RATE,
        ACTION_AVOID_REDUNDANT_PROFILE_APPLY,
    ]
    profile_check = report["checks"]["profile_verify"]
    assert profile_check["warnings"] == [
        "active profile is reboot pending: GraphicsSettingsHandler"
    ]


def test_build_health_report_clears_stale_reboot_pending_after_later_clean_boot(
    tmp_path: Path,
) -> None:
    """Health should not keep stale reboot warnings after boot and clean verify."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T04:40:55",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result={
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": True,
        },
        boot_time=datetime(2026, 5, 26, 4, 50),
    )

    profile_check = report["checks"]["profile_verify"]
    assert profile_check["status"] == "ok"
    assert profile_check["data"]["reboot_pending"] is False
    assert profile_check["data"]["reboot_reasons"] == []
    assert report["checks"]["state_file"]["data"]["reboot_pending"] is False
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["reboot_pending"] is False
    assert saved["reboot_reasons"] == []


def test_build_health_report_mirrors_cleared_reboot_pending_state(tmp_path: Path) -> None:
    """Health reconciliation should update every tray/GUI state target."""
    state_file = tmp_path / "repo" / ".abso_state.json"
    mirror_file = tmp_path / "local" / "AdaptiveBattleStationOptimizer" / ".abso_state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T04:40:55",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )

    _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result={
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": True,
        },
        boot_time=datetime(2026, 5, 26, 4, 50),
        state_file_targets=[state_file, mirror_file],
    )

    primary = json.loads(state_file.read_text(encoding="utf-8"))
    mirror = json.loads(mirror_file.read_text(encoding="utf-8"))
    assert primary == mirror
    assert primary["reboot_pending"] is False
    assert primary["reboot_reasons"] == []


def test_build_health_report_keeps_profile_ok_when_state_mirror_write_fails(
    tmp_path: Path,
) -> None:
    """Mirror failures should warn on state sync without poisoning profile verify."""
    state_file = tmp_path / "repo" / ".abso_state.json"
    mirror_file = tmp_path / "local" / "AdaptiveBattleStationOptimizer" / ".abso_state.json"
    state_file.parent.mkdir(parents=True)
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T04:40:55",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )

    def write_or_fail(path: Path, data: dict, *, indent: int | None = None) -> None:
        if path == mirror_file:
            raise OSError("mirror denied")
        real_atomic_write_json(path, data, indent=indent)

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result={
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": True,
        },
        boot_time=datetime(2026, 5, 26, 4, 50),
        state_file_targets=[state_file, mirror_file],
        atomic_write_side_effect=write_or_fail,
    )

    profile_check = report["checks"]["profile_verify"]
    state_check = report["checks"]["state_file"]
    assert profile_check["status"] == "ok"
    assert profile_check["data"]["reboot_pending"] is False
    assert state_check["status"] == "warning"
    assert state_check["mirror_warnings"] == [
        {"path": str(mirror_file), "error": "mirror denied"}
    ]
    primary = json.loads(state_file.read_text(encoding="utf-8"))
    assert primary["reboot_pending"] is False
    assert not mirror_file.exists()


def test_build_health_report_keeps_reboot_pending_before_later_boot(tmp_path: Path) -> None:
    """A clean registry verify before reboot must still be reported as pending."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(
        json.dumps(
            {
                "current_profile": "overwatch2-gsync-hdr-capture",
                "applied_at": "2026-05-26T04:40:55",
                "reboot_pending": True,
                "reboot_reasons": ["GraphicsSettingsHandler"],
            }
        ),
        encoding="utf-8",
    )

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        verify_result={
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": True,
        },
        boot_time=datetime(2026, 5, 26, 4, 30),
    )

    profile_check = report["checks"]["profile_verify"]
    assert profile_check["status"] == "warning"
    assert profile_check["data"]["reboot_pending"] is True
    assert profile_check["data"]["reboot_reasons"] == ["GraphicsSettingsHandler"]
    saved = json.loads(state_file.read_text(encoding="utf-8"))
    assert saved["reboot_pending"] is True


def test_build_health_report_counts_workspace_backups(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    primary_backups = tmp_path / "local_backups"
    workspace_backups = tmp_path / "workspace_backups"

    primary_manager = MagicMock()
    primary_manager.list_backups.return_value = []
    workspace_manager = MagicMock()
    workspace_manager.list_backups.return_value = [{"id": "2026-05-26_020202", "created_at": "now"}]

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        backups_dir=primary_backups,
        verify_result={"profile": "overwatch2", "all_active": True},
        backup_manager_side_effect=[primary_manager, workspace_manager],
        candidate_backup_dirs=[primary_backups, workspace_backups],
    )

    backup_check = report["checks"]["backups"]
    assert backup_check["status"] == "ok"
    assert backup_check["data"]["count"] == 1
    assert backup_check["data"]["entry_count"] == 1
    assert backup_check["data"]["mirror_count"] == 0
    assert backup_check["data"]["roots"] == [
        {"role": "primary", "path": str(primary_backups), "count": 0},
        {"role": "workspace", "path": str(workspace_backups), "count": 1},
    ]
    assert backup_check["data"]["latest"]["source"] == "workspace"
    assert "recent" not in backup_check["data"]


def test_build_health_report_deduplicates_mirrored_backup_roots(tmp_path: Path) -> None:
    """Mirrored workspace/AppData backups should not inflate the health count."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    primary_backups = tmp_path / "local_backups"
    workspace_backups = tmp_path / "workspace_backups"
    backup = {
        "id": "2026-05-26_020202",
        "created_at": "now",
        "profile_id": "overwatch2",
        "backup_type": "pre_apply",
    }

    primary_manager = MagicMock()
    primary_manager.list_backups.return_value = [backup]
    workspace_manager = MagicMock()
    workspace_manager.list_backups.return_value = [backup]

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        backups_dir=primary_backups,
        verify_result={"profile": "overwatch2", "all_active": True},
        backup_manager_side_effect=[primary_manager, workspace_manager],
        candidate_backup_dirs=[primary_backups, workspace_backups],
    )

    backups_data = report["checks"]["backups"]["data"]
    assert backups_data["count"] == 1
    assert backups_data["entry_count"] == 2
    assert backups_data["mirror_count"] == 1
    assert backups_data["latest"]["source"] == "primary"
    assert backups_data["latest"]["mirrors"] == [
        {"source": "workspace", "source_path": str(workspace_backups)}
    ]


def test_build_health_report_defaults_to_latest_backup_only(tmp_path: Path) -> None:
    """Frequent health checks should not include repeated recent backup rows."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    components = [f"Handler{i}" for i in range(12)]

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        backup_list=[
            {
                "id": "2026-05-26_030303",
                "created_at": "now",
                "profile_id": "overwatch2",
                "backup_type": "pre_apply",
                "components": components,
            }
        ],
        verify_result={"profile": "overwatch2", "all_active": True},
    )

    backups_data = report["checks"]["backups"]["data"]
    latest = backups_data["latest"]
    assert "recent" not in backups_data
    assert "components" not in latest
    assert "components_preview" not in latest
    assert latest["component_count"] == 12
    assert latest["profile_id"] == "overwatch2"
    assert latest["backup_type"] == "pre_apply"


def test_build_health_report_can_include_recent_backup_details(tmp_path: Path) -> None:
    """Bundles can opt into recent backup rows without full component arrays."""
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")
    components = [f"Handler{i}" for i in range(12)]

    report = _build_health_report_with_mocks(
        tmp_path,
        state_file,
        backup_list=[
            {
                "id": "2026-05-26_030303",
                "created_at": "now",
                "profile_id": "overwatch2",
                "backup_type": "pre_apply",
                "components": components,
            }
        ],
        verify_result={"profile": "overwatch2", "all_active": True},
        include_backup_details=True,
    )

    recent = report["checks"]["backups"]["data"]["recent"][0]
    assert "latest" not in report["checks"]["backups"]["data"]
    assert "components" not in recent
    assert recent["component_count"] == 12
    assert recent["components_preview"] == components[:8]
    assert recent["components_truncated"] is True


def test_write_health_bundle_creates_zip(tmp_path: Path) -> None:
    report = {
        "generated_at": "2026-02-18T00:00:00",
        "checks": {},
        "summary": {"ok": 1, "warning": 0, "error": 0},
    }
    archive = write_health_bundle(report, tmp_path)

    assert archive.exists()
    assert archive.suffix == ".zip"
