"""Tests for tray startup registration helpers."""

from __future__ import annotations

import json
from unittest.mock import patch

import pytest

import abso.main as main
import abso.tray as tray
from abso.tray import (
    ensure_tray_running,
    get_startup_status,
    get_tray_dir,
    get_tray_processes,
    install_startup,
    is_tray_running,
    start_tray,
)


def _write_tray_markers(path):
    path.mkdir(parents=True, exist_ok=True)
    (path / "ABSO-Tray.ps1").write_text("# tray\n", encoding="utf-8")
    (path / "ABSO-Tray.vbs").write_text("' tray\n", encoding="utf-8")
    (path / "Install-Startup.ps1").write_text("# installer\n", encoding="utf-8")


def test_get_tray_dir_prefers_durable_tree_for_frozen_onefile(tmp_path):
    """Frozen one-file builds must not register startup against _MEI temp paths."""
    exe_dir = tmp_path / "dist"
    exe_dir.mkdir()
    durable_tray_dir = tmp_path / "abso" / "tray"
    bundled_tray_dir = tmp_path / "_MEI12345" / "abso" / "tray"
    _write_tray_markers(durable_tray_dir)
    _write_tray_markers(bundled_tray_dir)

    with (
        patch.object(tray.sys, "frozen", True, create=True),
        patch.object(tray.sys, "executable", str(exe_dir / "abso.exe")),
        patch.object(tray, "__file__", str(bundled_tray_dir / "__init__.py")),
    ):
        assert get_tray_dir() == durable_tray_dir


def test_get_tray_dir_falls_back_to_bundled_tree_for_frozen_onefile(tmp_path, monkeypatch):
    """Bundled tray files remain usable when no durable sidecar tree exists."""
    exe_dir = tmp_path / "dist"
    exe_dir.mkdir()
    work_dir = tmp_path / "work"
    work_dir.mkdir()
    monkeypatch.chdir(work_dir)
    bundled_tray_dir = tmp_path / "_MEI12345" / "abso" / "tray"
    _write_tray_markers(bundled_tray_dir)

    with (
        patch.object(tray.sys, "frozen", True, create=True),
        patch.object(tray.sys, "executable", str(exe_dir / "abso.exe")),
        patch.object(tray, "__file__", str(bundled_tray_dir / "__init__.py")),
    ):
        assert get_tray_dir() == bundled_tray_dir


def test_start_tray_launches_vbs(tmp_path):
    """start_tray should launch the VBS loader through wscript."""
    vbs = tmp_path / "ABSO-Tray.vbs"
    vbs.write_text("' test\n", encoding="utf-8")

    with (
        patch("abso.tray.get_tray_dir", return_value=tmp_path),
        patch("abso.tray.subprocess.Popen") as mock_popen,
    ):
        start_tray()

    mock_popen.assert_called_once()
    args, kwargs = mock_popen.call_args
    assert args[0][0].lower() == "wscript.exe"
    assert str(vbs) in args[0]
    assert kwargs["cwd"] == str(tmp_path)


def test_start_tray_missing_vbs_exits(tmp_path):
    """start_tray exits with code 1 when launcher script is missing."""
    with (
        patch("abso.tray.get_tray_dir", return_value=tmp_path),
        pytest.raises(SystemExit) as exc,
    ):
        start_tray()
    assert exc.value.code == 1


def test_install_startup_calls_install_flag(tmp_path):
    """install_startup should invoke installer with -Install by default."""
    with (
        patch("abso.tray.get_tray_dir", return_value=tmp_path),
        patch("abso.tray.subprocess.run") as mock_run,
    ):
        install_startup(uninstall=False)

    call_args = mock_run.call_args[0][0]
    assert "-Install" in call_args
    assert "-Uninstall" not in call_args


def test_install_startup_calls_uninstall_flag(tmp_path):
    """install_startup should invoke installer with -Uninstall when requested."""
    with (
        patch("abso.tray.get_tray_dir", return_value=tmp_path),
        patch("abso.tray.subprocess.run") as mock_run,
    ):
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

    with (
        patch("abso.tray.get_tray_dir", return_value=tmp_path),
        patch("abso.tray.subprocess.run") as mock_run,
    ):
        mock_run.return_value.stdout = output
        status = get_startup_status()

    assert status["installed"] is True
    assert status["mode"] == "scheduled_task"


def test_get_startup_status_marks_installed_task_path_usable(tmp_path, monkeypatch):
    """Source-mode status should accept an installed LocalAppData startup path."""
    installed_tray = tmp_path / "Local" / "AdaptiveBattleStationOptimizer" / "abso" / "tray"
    installed_tray.mkdir(parents=True)
    launcher = installed_tray / "ABSO-StartupLaunch.ps1"
    launcher.write_text("# launcher\n", encoding="utf-8")
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path / "Local"))
    output = json.dumps(
        {
            "installed": True,
            "mode": "scheduled_task",
            "task_installed": True,
            "shortcut_installed": False,
            "task_action_arguments": (
                '-NoProfile -ExecutionPolicy Bypass -File "'
                + str(launcher)
                + '"'
            ),
            "task_action_path_current": False,
        }
    )

    with (
        patch("abso.tray.get_tray_dir", return_value=tmp_path),
        patch("abso.tray.subprocess.run") as mock_run,
    ):
        mock_run.return_value.stdout = output
        status = get_startup_status()

    assert status["task_action_path_current"] is False
    assert status["task_action_path_installed"] is True
    assert status["task_action_uses_installed_launcher"] is True


def test_cli_tray_startup_status_option():
    """CLI tray --startup-status should run without crashing."""
    from click.testing import CliRunner

    runner = CliRunner()
    with patch("abso.tray.get_startup_status", return_value={"installed": False, "mode": "none"}):
        result = runner.invoke(main.cli, ["tray", "--startup-status"])

    assert result.exit_code == 0
    assert "Startup Installed" in result.output


def test_cli_tray_startup_status_warns_on_action_path_drift():
    """CLI startup status should surface when the task points at stale tray assets."""
    from click.testing import CliRunner

    runner = CliRunner()
    status = {
        "installed": True,
        "mode": "scheduled_task",
        "task_installed": True,
        "task_name": "ABSO-Tray-Startup",
        "task_highest": True,
        "task_action_execute": "wscript.exe",
        "task_action_arguments": '"C:\\repo\\abso\\tray\\ABSO-Tray.vbs"',
        "task_action_path_current": False,
    }
    with patch("abso.tray.get_startup_status", return_value=status):
        result = runner.invoke(main.cli, ["tray", "--startup-status"])

    assert result.exit_code == 0
    assert "Task Action" in result.output
    assert "different tray path" in result.output


def test_cli_tray_startup_status_accepts_installed_action_path():
    """CLI status should not warn when source status sees the installed task path."""
    from click.testing import CliRunner

    runner = CliRunner()
    status = {
        "installed": True,
        "mode": "scheduled_task",
        "task_installed": True,
        "task_name": "ABSO-Tray-Startup",
        "task_highest": True,
        "task_action_execute": "powershell.exe",
        "task_action_arguments": '"C:\\Users\\mtoli\\AppData\\Local\\AdaptiveBattleStationOptimizer\\abso\\tray\\ABSO-StartupLaunch.ps1"',
        "task_action_path_current": False,
        "task_action_path_installed": True,
    }
    with patch("abso.tray.get_startup_status", return_value=status):
        result = runner.invoke(main.cli, ["tray", "--startup-status"])

    assert result.exit_code == 0
    assert "Task Action" in result.output
    assert "different tray path" not in result.output


def test_get_tray_processes_parses_single_object():
    """get_tray_processes should normalize single JSON object into list."""
    payload = '{"ProcessId":1234,"Name":"powershell.exe","CommandLine":"ABSO-Tray.ps1"}'
    with patch("abso.tray.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = payload
        processes = get_tray_processes()

    assert isinstance(processes, list)
    assert len(processes) == 1
    assert processes[0]["ProcessId"] == 1234


def test_get_tray_processes_excludes_own_probe_command():
    """The process query must not count the probing PowerShell host as tray."""
    with patch("abso.tray.subprocess.run") as mock_run:
        mock_run.return_value.returncode = 0
        mock_run.return_value.stdout = ""
        get_tray_processes()

    ps_command = mock_run.call_args[0][0][-1]
    assert "$_.ProcessId -ne $PID" in ps_command
    assert "$_.CommandLine -notlike '*Get-CimInstance Win32_Process*'" in ps_command


def test_is_tray_running_true_when_process_found():
    """is_tray_running should return true when tray process list is non-empty."""
    with (
        patch("abso.tray.get_tray_processes", return_value=[{"ProcessId": 1}]),
        patch("abso.tray._tray_mutex_exists", return_value=False),
    ):
        assert is_tray_running() is True


def test_is_tray_running_true_when_mutex_exists():
    """Elevated tray hosts can hide command lines, so the mutex is authoritative."""
    with (
        patch("abso.tray.get_tray_processes", return_value=[]),
        patch("abso.tray._tray_mutex_exists", return_value=True),
    ):
        assert is_tray_running() is True


def test_is_tray_running_false_when_no_process_or_mutex():
    """Tray runtime should be false only when both probes are empty."""
    with (
        patch("abso.tray.get_tray_processes", return_value=[]),
        patch("abso.tray._tray_mutex_exists", return_value=False),
    ):
        assert is_tray_running() is False


def test_ensure_tray_running_starts_when_missing():
    """ensure_tray_running should attempt startup when requested."""
    with patch(
        "abso.tray._tray_runtime_snapshot",
        side_effect=[
            {"running": False, "mutex_exists": False, "processes": []},
            {"running": True, "mutex_exists": True, "processes": []},
        ],
    ), patch("abso.tray.start_tray") as mock_start:
        result = ensure_tray_running(start_if_missing=True)

    mock_start.assert_called_once()
    assert result["running_before"] is False
    assert result["started"] is True
    assert result["running_after"] is True
    assert result["mutex_exists"] is True
