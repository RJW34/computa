"""Tests for local build/deploy helper script."""

from __future__ import annotations

import os
import subprocess
from pathlib import Path

import build


def test_build_help_points_at_pyinstaller_ready_venv() -> None:
    """Build help should steer local deploys to the PyInstaller-ready venv."""
    assert ".\\.venv\\Scripts\\python.exe build.py deploy" in build.__doc__
    assert "Use a Python interpreter with PyInstaller installed." in build.__doc__


def test_pyinstaller_spec_bundles_cache_first_tray_assets() -> None:
    """The one-file fallback bundle should carry every deployable tray asset."""
    spec_path = build.ROOT_DIR / "abso.spec"
    prefix = spec_path.read_text(encoding="utf-8").split("\na = Analysis(", 1)[0]
    namespace: dict[str, object] = {"__file__": str(spec_path)}
    exec(compile(prefix, str(spec_path), "exec"), namespace)

    bundled = {
        Path(source).name
        for source, destination in namespace["TRAY_DATA_FILES"]
        if destination == "abso\\tray"
    }
    source_dir = build.ROOT_DIR / "abso" / "tray"
    source_files = {
        path.name
        for path in source_dir.iterdir()
        if (
            path.is_file()
            and path.suffix.lower() in namespace["TRAY_BUNDLE_EXTENSIONS"]
            and path.name not in namespace["TRAY_BUNDLE_EXCLUDE_FILENAMES"]
        )
    }

    assert source_files
    assert source_files <= bundled
    assert "profile-catalog-cache.json" in bundled
    assert "tray-config.json" not in bundled
    assert "_diag-and-restart.ps1" not in bundled
    assert "_restart-tray.ps1" not in bundled


def test_deploy_local_runtime_copies_runtime_assets(tmp_path, monkeypatch):
    """Local deploy should keep backend, sidecars, tray, config, and backups aligned."""
    root = tmp_path / "repo"
    dist = root / "dist"
    tray = root / "abso" / "tray"
    backups = root / "backups" / "2026-05-26_010101"
    gui = root / "gui"
    gui_bins = root / "gui" / "src-tauri" / "binaries"
    gui_release = root / "gui" / "src-tauri" / "target" / "release"
    install = tmp_path / "install"

    dist.mkdir(parents=True)
    tray.mkdir(parents=True)
    backups.mkdir(parents=True)
    gui_bins.mkdir(parents=True)
    gui_release.mkdir(parents=True)

    (dist / "computa.exe").write_bytes(b"new backend")
    (gui_release / "abso-gui.exe").write_bytes(b"new gui")
    (tray / "ABSO-Tray.ps1").write_text("# tray", encoding="utf-8")
    (tray / "Install-Startup.ps1").write_text("# installer", encoding="utf-8")
    (root / "abso.yaml").write_text("backup_dir: backups\n", encoding="utf-8")
    (backups / "metadata.json").write_text("{}", encoding="utf-8")
    (install / "computa.exe").parent.mkdir(parents=True)
    (install / "computa.exe").write_bytes(b"old backend")
    (install / "abso-gui.exe").write_bytes(b"old gui")

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", gui)
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", gui_bins)

    result = build.deploy_local_runtime(install_dir=install)

    assert (install / "computa.exe").read_bytes() == b"new backend"
    assert (install / "abso-gui.exe").read_bytes() == b"new gui"
    assert (install / "abso.yaml").read_text(encoding="utf-8") == "backup_dir: backups\n"
    assert (install / "abso" / "tray" / "ABSO-Tray.ps1").exists()
    assert (install / "backups" / "2026-05-26_010101" / "metadata.json").exists()
    assert (gui_bins / "abso.exe").read_bytes() == b"new backend"
    assert (gui_bins / "abso-x86_64-pc-windows-msvc.exe").read_bytes() == b"new backend"
    assert (gui_bins / "abso-x86_64-pc-windows-gnu.exe").read_bytes() == b"new backend"
    assert result["installed_length"] == len(b"new backend")
    assert result["backend"]["copied"] is True
    assert result["backend"]["backup"] is not None
    assert result["backend"]["length"] == len(b"new backend")
    assert result["gui"]["copied"] is True
    assert result["gui"]["backup"] is not None
    assert result["gui"]["length"] == len(b"new gui")
    assert result["tray_file_count"] == 2
    assert result["tray_updated_count"] == 2
    assert result["config_copied"] is True
    assert result["migrated_backups"] == 1
    assert result["backup"] is not None


def test_deploy_local_runtime_copies_profile_cache_and_removes_legacy_sidecar_config(
    tmp_path,
    monkeypatch,
):
    """Deploy should ship the tray catalog cache and purge obsolete sidecar settings."""
    root = tmp_path / "repo"
    dist = root / "dist"
    tray = root / "abso" / "tray"
    install = tmp_path / "install"
    installed_tray = install / "abso" / "tray"

    dist.mkdir(parents=True)
    tray.mkdir(parents=True)
    installed_tray.mkdir(parents=True)

    (dist / "computa.exe").write_bytes(b"backend")
    (tray / "profile-catalog-cache.json").write_text('{"profiles":[]}', encoding="utf-8")
    (tray / "_restart-tray.ps1").write_text("# deprecated", encoding="utf-8")
    (tray / "tray-config.json").write_text('{"stale":true}', encoding="utf-8")
    (installed_tray / "_diag-and-restart.ps1").write_text("# stale diagnostic", encoding="utf-8")
    (installed_tray / "_restart-tray.ps1").write_text("# stale restart helper", encoding="utf-8")
    (installed_tray / "__init__.py").write_text("# stale python sidecar", encoding="utf-8")
    (installed_tray / "tray-config.json").write_text('{"local":true}', encoding="utf-8")

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", root / "gui")
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", root / "gui" / "src-tauri" / "binaries")

    result = build.deploy_local_runtime(install_dir=install)

    assert (installed_tray / "profile-catalog-cache.json").read_text(encoding="utf-8") == (
        '{"profiles":[]}'
    )
    assert not (installed_tray / "_diag-and-restart.ps1").exists()
    assert not (installed_tray / "_restart-tray.ps1").exists()
    assert not (installed_tray / "__init__.py").exists()
    assert not (installed_tray / "tray-config.json").exists()
    assert result["tray_file_count"] == 1
    assert result["tray_updated_count"] == 1
    assert result["tray_removed_count"] == 4


def test_deploy_local_runtime_skips_identical_backend_executable(tmp_path, monkeypatch):
    """Deploy should not create backend backups when the installed backend is current."""
    root = tmp_path / "repo"
    dist = root / "dist"
    install = tmp_path / "install"

    dist.mkdir(parents=True)
    install.mkdir(parents=True)
    (dist / "computa.exe").write_bytes(b"same backend")
    (install / "computa.exe").write_bytes(b"same backend")

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", root / "gui")
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", root / "gui" / "src-tauri" / "binaries")

    result = build.deploy_local_runtime(install_dir=install)

    assert (install / "computa.exe").read_bytes() == b"same backend"
    assert result["installed_length"] == len(b"same backend")
    assert result["backend"]["available"] is True
    assert result["backend"]["copied"] is False
    assert result["backend"]["backup"] is None
    assert result["backup"] is None
    assert not list((install / "deploy-backups").glob("computa.exe.bak-*"))


def test_sync_file_with_backup_does_not_overwrite_same_second_backup(tmp_path):
    """Deploy backups should remain unique even with the same timestamp string."""
    source = tmp_path / "source.exe"
    target = tmp_path / "target.exe"
    backup_dir = tmp_path / "deploy-backups"
    backup_dir.mkdir()
    existing_backup = backup_dir / "computa.exe.bak-20260526-093000"

    source.write_bytes(b"new backend")
    target.write_bytes(b"old backend")
    existing_backup.write_bytes(b"previous backup")

    result = build._sync_file_with_backup(
        source=source,
        target=target,
        backup_dir=backup_dir,
        backup_name="computa.exe",
        stamp="20260526-093000",
    )

    assert target.read_bytes() == b"new backend"
    assert existing_backup.read_bytes() == b"previous backup"
    assert (backup_dir / "computa.exe.bak-20260526-093000-2").read_bytes() == b"old backend"
    assert result["backup"] == str(backup_dir / "computa.exe.bak-20260526-093000-2")


def test_copy_file_if_changed_renames_aside_when_overwrite_is_blocked(
    tmp_path,
    monkeypatch,
):
    """Deploy should recover when Windows allows rename but blocks overwrite."""
    source = tmp_path / "source.exe"
    target = tmp_path / "target.exe"
    source.write_bytes(b"new backend")
    target.write_bytes(b"old backend")
    real_copy2 = build.shutil.copy2
    failed_once = False

    def flaky_copy2(src, dst, *args, **kwargs):
        nonlocal failed_once
        if Path(dst) == target and not failed_once:
            failed_once = True
            raise PermissionError("target is temporarily locked")
        return real_copy2(src, dst, *args, **kwargs)

    monkeypatch.setattr(build.shutil, "copy2", flaky_copy2)

    assert build._copy_file_if_changed(source, target) is True

    assert target.read_bytes() == b"new backend"
    assert failed_once is True
    assert not list(tmp_path.glob("target.exe.replaced-*"))


def test_copy_cli_to_gui_skips_identical_sidecar_writes(tmp_path, monkeypatch):
    """Sidecar sync should preserve already-current files during repeated deploys."""
    root = tmp_path / "repo"
    dist = root / "dist"
    gui_bins = root / "gui" / "src-tauri" / "binaries"
    sidecar_names = [
        "abso-x86_64-pc-windows-msvc.exe",
        "abso-x86_64-pc-windows-gnu.exe",
        "abso.exe",
    ]

    dist.mkdir(parents=True)
    gui_bins.mkdir(parents=True)
    (dist / "computa.exe").write_bytes(b"same backend")
    for name in sidecar_names:
        sidecar = gui_bins / name
        sidecar.write_bytes(b"same backend")
        os.utime(sidecar, (1_700_000_000, 1_700_000_000))

    before_mtimes = {name: (gui_bins / name).stat().st_mtime_ns for name in sidecar_names}

    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", gui_bins)

    assert build.copy_cli_to_gui() is True

    after_mtimes = {name: (gui_bins / name).stat().st_mtime_ns for name in sidecar_names}
    assert after_mtimes == before_mtimes


def test_deploy_local_runtime_skips_identical_tray_assets_and_config(tmp_path, monkeypatch):
    """Repeated deploys should not rewrite already-current tray assets or config."""
    root = tmp_path / "repo"
    dist = root / "dist"
    tray = root / "abso" / "tray"
    install = tmp_path / "install"
    installed_tray = install / "abso" / "tray"

    dist.mkdir(parents=True)
    tray.mkdir(parents=True)
    installed_tray.mkdir(parents=True)
    install.mkdir(parents=True, exist_ok=True)

    (dist / "computa.exe").write_bytes(b"same backend")
    (install / "computa.exe").write_bytes(b"same backend")
    (tray / "ABSO-Tray.ps1").write_text("# tray", encoding="utf-8")
    (tray / "Install-Startup.ps1").write_text("# installer", encoding="utf-8")
    (installed_tray / "ABSO-Tray.ps1").write_text("# tray", encoding="utf-8")
    (installed_tray / "Install-Startup.ps1").write_text("# installer", encoding="utf-8")
    (root / "abso.yaml").write_text("backup_dir: backups\n", encoding="utf-8")
    (install / "abso.yaml").write_text("backup_dir: backups\n", encoding="utf-8")

    tracked_paths = [
        installed_tray / "ABSO-Tray.ps1",
        installed_tray / "Install-Startup.ps1",
        install / "abso.yaml",
    ]
    for path in tracked_paths:
        os.utime(path, (1_700_000_000, 1_700_000_000))

    before_mtimes = {path: path.stat().st_mtime_ns for path in tracked_paths}

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", root / "gui")
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", root / "gui" / "src-tauri" / "binaries")

    result = build.deploy_local_runtime(install_dir=install)

    after_mtimes = {path: path.stat().st_mtime_ns for path in tracked_paths}
    assert result["tray_file_count"] == 2
    assert result["tray_updated_count"] == 0
    assert result["config_copied"] is False
    assert after_mtimes == before_mtimes


def test_deploy_local_runtime_does_not_overwrite_existing_backup_dirs(tmp_path, monkeypatch):
    """Backup migration should be additive and preserve existing installed snapshots."""
    root = tmp_path / "repo"
    dist = root / "dist"
    source_backup = root / "backups" / "2026-05-26_010101"
    install = tmp_path / "install"
    existing_backup = install / "backups" / "2026-05-26_010101"

    dist.mkdir(parents=True)
    source_backup.mkdir(parents=True)
    existing_backup.mkdir(parents=True)
    (dist / "computa.exe").write_bytes(b"backend")
    (source_backup / "metadata.json").write_text('{"source": true}', encoding="utf-8")
    (existing_backup / "metadata.json").write_text('{"installed": true}', encoding="utf-8")

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", root / "gui")
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", root / "gui" / "src-tauri" / "binaries")

    result = build.deploy_local_runtime(install_dir=install)

    assert result["migrated_backups"] == 0
    assert existing_backup.joinpath("metadata.json").read_text(encoding="utf-8") == (
        '{"installed": true}'
    )


def test_deploy_local_runtime_skips_identical_gui_executable(tmp_path, monkeypatch):
    """Deploy should not create GUI backups when the installed GUI is current."""
    root = tmp_path / "repo"
    dist = root / "dist"
    gui = root / "gui"
    gui_release = gui / "src-tauri" / "target" / "release"
    install = tmp_path / "install"

    dist.mkdir(parents=True)
    gui_release.mkdir(parents=True)
    install.mkdir(parents=True)
    (dist / "computa.exe").write_bytes(b"backend")
    (gui_release / "abso-gui.exe").write_bytes(b"same gui")
    (install / "abso-gui.exe").write_bytes(b"same gui")

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", gui)
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", gui / "src-tauri" / "binaries")

    result = build.deploy_local_runtime(install_dir=install)

    assert result["gui"]["available"] is True
    assert result["gui"]["copied"] is False
    assert result["gui"]["backup"] is None
    assert not list((install / "deploy-backups").glob("abso-gui.exe.bak-*"))


def test_run_pyinstaller_suppresses_success_output(tmp_path, monkeypatch, capsys):
    """Successful PyInstaller builds should not replay verbose tool output."""
    spec = tmp_path / "abso.spec"
    spec.write_text("# spec", encoding="utf-8")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(
            args,
            0,
            stdout="PyInstaller verbose stdout\n",
            stderr="PyInstaller verbose stderr\n",
        )

    monkeypatch.setattr(build, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(build, "SPEC_FILE", spec)
    monkeypatch.setattr(build.subprocess, "run", fake_run)

    assert build.run_pyinstaller() is True

    captured = capsys.readouterr()
    assert "Build completed." in captured.out
    assert "PyInstaller verbose stdout" not in captured.out
    assert "PyInstaller verbose stderr" not in captured.out
    assert captured.err == ""
    assert len(calls) == 1
    assert calls[0][1]["cwd"] == tmp_path
    assert calls[0][1]["capture_output"] is True
    assert calls[0][1]["text"] is True
    assert calls[0][1]["check"] is False


def test_run_pyinstaller_replays_failure_output(tmp_path, monkeypatch, capsys):
    """Failed PyInstaller builds should include captured diagnostic output."""
    spec = tmp_path / "abso.spec"
    spec.write_text("# spec", encoding="utf-8")

    def fake_run(args, **kwargs):
        return subprocess.CompletedProcess(
            args,
            1,
            stdout="PyInstaller failure stdout\n",
            stderr="PyInstaller failure stderr\n",
        )

    monkeypatch.setattr(build, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(build, "SPEC_FILE", spec)
    monkeypatch.setattr(build.subprocess, "run", fake_run)

    assert build.run_pyinstaller() is False

    captured = capsys.readouterr()
    assert "ERROR: PyInstaller failed!" in captured.out
    assert "PyInstaller stdout:" in captured.out
    assert "PyInstaller failure stdout" in captured.out
    assert "PyInstaller stderr:" in captured.out
    assert "PyInstaller failure stderr" in captured.out


def test_build_cli_checks_pyinstaller_before_cleaning(tmp_path, monkeypatch, capsys):
    """A missing PyInstaller module must not delete the last good dist build."""
    spec = tmp_path / "abso.spec"
    spec.write_text("# spec", encoding="utf-8")
    calls = []

    def fake_run(args, **kwargs):
        calls.append(("subprocess", args, kwargs))
        return subprocess.CompletedProcess(
            args,
            1,
            stdout="",
            stderr="No module named PyInstaller\n",
        )

    def fake_clean():
        calls.append(("clean", (), {}))

    monkeypatch.setattr(build, "ROOT_DIR", tmp_path)
    monkeypatch.setattr(build, "SPEC_FILE", spec)
    monkeypatch.setattr(build.subprocess, "run", fake_run)
    monkeypatch.setattr(build, "clean_build", fake_clean)

    assert build.build_cli() is False

    captured = capsys.readouterr()
    assert "PyInstaller is not available" in captured.out
    assert "Use .\\.venv\\Scripts\\python.exe build.py deploy" in captured.out
    assert all(call[0] != "clean" for call in calls)


def test_build_gui_runs_npm_without_shell(tmp_path, monkeypatch):
    """GUI builds should invoke npm directly instead of through shell=True."""
    gui = tmp_path / "gui"
    sidecars = gui / "src-tauri" / "binaries"
    node_modules = gui / "node_modules"
    sidecars.mkdir(parents=True)
    node_modules.mkdir()
    (sidecars / "abso-x86_64-pc-windows-msvc.exe").write_bytes(b"backend")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(build, "GUI_DIR", gui)
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", sidecars)
    monkeypatch.setattr(build, "get_gui_build_env", lambda: {"PATH": "test-path"})
    monkeypatch.setattr(build, "resolve_npm_command", lambda env: "npm.cmd")
    monkeypatch.setattr(build.subprocess, "run", fake_run)

    assert build.build_gui() is True

    assert calls == [
        (["npm.cmd", "run", "tauri", "build"], {"cwd": gui, "env": {"PATH": "test-path"}, "check": False})
    ]
    assert "shell" not in calls[0][1]


def test_build_gui_installs_dependencies_without_shell(tmp_path, monkeypatch):
    """Missing node_modules should still avoid shell=True for npm install."""
    gui = tmp_path / "gui"
    sidecars = gui / "src-tauri" / "binaries"
    sidecars.mkdir(parents=True)
    (sidecars / "abso-x86_64-pc-windows-msvc.exe").write_bytes(b"backend")
    calls = []

    def fake_run(args, **kwargs):
        calls.append((args, kwargs))
        return subprocess.CompletedProcess(args, 0)

    monkeypatch.setattr(build, "GUI_DIR", gui)
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", sidecars)
    monkeypatch.setattr(build, "get_gui_build_env", lambda: {"PATH": "test-path"})
    monkeypatch.setattr(build, "resolve_npm_command", lambda env: "npm.cmd")
    monkeypatch.setattr(build.subprocess, "run", fake_run)

    assert build.build_gui() is True

    assert calls == [
        (["npm.cmd", "install"], {"cwd": gui, "env": {"PATH": "test-path"}, "check": False}),
        (["npm.cmd", "run", "tauri", "build"], {"cwd": gui, "env": {"PATH": "test-path"}, "check": False}),
    ]
    assert all("shell" not in kwargs for _args, kwargs in calls)
