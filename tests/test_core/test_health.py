"""Tests for diagnostics health module."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.core.health import build_health_report, write_health_bundle


def test_build_health_report_collects_checks(tmp_path: Path) -> None:
    state_file = tmp_path / ".abso_state.json"
    state_file.write_text(json.dumps({"current_profile": "overwatch2"}), encoding="utf-8")

    with patch("abso.core.health.get_startup_status", return_value={"installed": True, "mode": "scheduled_task"}):
        with patch(
            "abso.core.health.ensure_tray_running",
            return_value={"running_before": True, "running_after": True, "started": False},
        ):
            with patch("abso.core.health.BackupManager") as mock_backup_cls:
                mock_backup_cls.return_value.list_backups.return_value = []
                with patch("abso.core.health.ConfigManager") as mock_config_cls:
                    mock_config_cls.return_value.validate.return_value = []
                    with patch("abso.core.health.FallbackController") as mock_fallback_cls:
                        mock_fallback_cls.return_value.list_all.return_value = []
                        report = build_health_report(tmp_path, tmp_path / "backups", state_file)

    assert report["current_profile"] == "overwatch2"
    assert "checks" in report
    assert "summary" in report
    assert "tray_startup" in report["checks"]


def test_write_health_bundle_creates_zip(tmp_path: Path) -> None:
    report = {
        "generated_at": "2026-02-18T00:00:00",
        "checks": {},
        "summary": {"ok": 1, "warning": 0, "error": 0},
    }
    archive = write_health_bundle(report, tmp_path)

    assert archive.exists()
    assert archive.suffix == ".zip"
