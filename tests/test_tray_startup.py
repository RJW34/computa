"""Tests for tray startup registration helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import abso.main as main
from abso.tray import (
    get_startup_status,
    install_startup,
    start_tray,
)


def test_start_tray_launches_vbs(tmp_path):
    """start_tray should launch the VBS loader through wscript."""
    vbs = tmp_path / "ABSO-Tray.vbs"
    vbs.write_text("' test\n", encoding="utf-8")

    with patch("abso.tray.get_tray_dir", return_value=tmp_path):
        with patch("abso.tray.subprocess.Popen") as mock_popen:
            start_tray()

    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert args[0][0].lower() == "wscript.exe"
    assert str(vbs) in args[0]
    assert kwargs["cwd"] == str(tmp_path)


def test_start_tray_missing_vbs_exits(tmp_path):
    """start_tray exits with code 1 when launcher script is missing."""
    with patch("abso.tray.get_tray_dir", return_value=tmp_path):
        with pytest.raises(SystemExit) as exc:
            start_tray()
    assert exc.value.code == 1


def test_install_startup_calls_install_flag(tmp_path):
    """install_startup should invoke installer with -Install by default."""
    with patch("abso.tray.get_tray_dir", return_value=tmp_path):
        with patch("abso.tray.subprocess.run") as mock_run:
            install_startup(uninstall=False)

    call_args = mock_run.call_args[0][0]
    assert "-Install" in call_args
    assert "-Uninstall" not in call_args


def test_install_startup_calls_uninstall_flag(tmp_path):
    """install_startup should invoke installer with -Uninstall when requested."""
    with patch("abso.tray.get_tray_dir", return_value=tmp_path):
        with patch("abso.tray.subprocess.run") as mock_run:
            install_startup(uninstall=True)

    call_args = mock_run.call_args[0][0]
    assert "-Uninstall" in call_args
    assert "-Install" not in call_args


def test_get_startup_status_parses_json(tmp_path):
    """get_startup_status should parse JSON status output."""
    output = json.dumps({
        "installed": True,
        "mode": "scheduled_task",
        "task_installed": True,
        "shortcut_installed": False,
    })

    with patch("abso.tray.get_tray_dir", return_value=tmp_path):
        with patch("abso.tray.subprocess.run") as mock_run:
            mock_run.return_value.stdout = output
            status = get_startup_status()

    assert status["installed"] is True
    assert status["mode"] == "scheduled_task"


def test_cli_tray_startup_status_option():
    """CLI tray --startup-status should run without crashing."""
    from click.testing import CliRunner

    runner = CliRunner()
    with patch("abso.tray.get_startup_status", return_value={"installed": False, "mode": "none"}):
        result = runner.invoke(main.cli, ["tray", "--startup-status"])

    assert result.exit_code == 0
    assert "Startup Installed" in result.output
