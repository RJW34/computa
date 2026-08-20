#!/usr/bin/env python
r"""Build script for computa (CLI + GUI).

Commands:
    .\.venv\Scripts\python.exe build.py           # Build CLI only (default)
    .\.venv\Scripts\python.exe build.py cli       # Build CLI only (dist/computa/)
    .\.venv\Scripts\python.exe build.py gui       # Build GUI with Tauri (requires CLI)
    .\.venv\Scripts\python.exe build.py all       # Build both CLI and GUI installer
    .\.venv\Scripts\python.exe build.py deploy    # Build CLI and deploy local runtime assets
    .\.venv\Scripts\python.exe build.py deploy-existing  # Deploy existing dist/computa/
    .\.venv\Scripts\python.exe build.py installer # Build dist/computa-setup.exe (Inno Setup)
    .\.venv\Scripts\python.exe build.py dev       # Set up for GUI development

Use a Python interpreter with PyInstaller installed. On this PC that is the
repo-local .venv interpreter above; other launchers may not have PyInstaller.

Output:
    dist/computa/computa.exe                        - CLI (one-dir; needs _internal)
    dist/computa-portable.exe                       - One-file portable build / Tauri sidecar
    gui/src-tauri/target/release/bundle/msi/*.msi   - Windows installer
    gui/src-tauri/target/release/bundle/nsis/*.exe  - NSIS installer

The CLI is a one-dir build on purpose: the tray runs it as a short-lived
subprocess repeatedly during a gaming session, and a one-file build would
re-extract its whole archive to %TEMP% on every single call.
"""

from __future__ import annotations

import contextlib
import os
import shutil
import subprocess
import sys
from datetime import datetime
from pathlib import Path

# Build directories
ROOT_DIR = Path(__file__).parent
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
SPEC_FILE = ROOT_DIR / "abso.spec"
GUI_DIR = ROOT_DIR / "gui"
GUI_BINARIES_DIR = GUI_DIR / "src-tauri" / "binaries"
APP_DIR_NAME = "AdaptiveBattleStationOptimizer"
GUI_EXE_NAME = "abso-gui.exe"
# PyInstaller one-dir payload: dist/computa/computa.exe + dist/computa/_internal.
# The tray runs this backend as a short-lived subprocess many times per session,
# and one-dir avoids re-extracting the whole archive to %TEMP% on every call.
CLI_DIR_NAME = "computa"
CLI_EXE_NAME = "computa.exe"
# One-file build: the Tauri sidecar (which must be a single file) and the
# portable download the release docs point users at.
PORTABLE_EXE_NAME = "computa-portable.exe"
TRAY_RUNTIME_EXTENSIONS = frozenset({".ico", ".json", ".mp3", ".ps1", ".vbs", ".wav"})
TRAY_DEPLOY_EXCLUDE_FILENAMES = frozenset({
    # Deprecated ad-hoc diagnostics used broad process killing and should not
    # ship into the installed tray runtime.
    "_diag-and-restart.ps1",
    "_restart-tray.ps1",
    # User tray settings are stored in %APPDATA%\ABSO\tray-config.json.
    "tray-config.json",
})
# Nvidia Profile Inspector is a third-party binary the user supplies under
# tools/npi. It is mirrored into the install root (not the public installer,
# which must not redistribute it) so the installed backend can find it: NPI
# discovery is anchored to the program's own directory, and without this the
# tray -- whose working directory is the install root -- silently skips every
# NVIDIA setting. The archive and the disabled build are local clutter.
NPI_RUNTIME_EXCLUDE_SUFFIXES = frozenset({".zip", ".disabled"})
TRAY_OBSOLETE_SIDECAR_FILENAMES = frozenset({
    "__init__.py",
    *TRAY_DEPLOY_EXCLUDE_FILENAMES,
    # Pre-theme-pack media that used to sit in the tray root; these assets now
    # live under themes/<name>/ and stale root copies should not linger in the
    # installed runtime.
    "260 Swampert.ico",
    "pokemon_pc_idle.ico",
    "favicon.ico",
    "icon0260_f00_s0.ico",
    "icon0260_f01_s0.ico",
    "pokemon-red_blue_yellow-save-game-sound-effect.mp3",
    "hit-weak-not-very-effective.mp3",
    "oot_navi_hey1.mp3",
    "pokemon-redblueyellow-item-found-sound-effect.mp3",
})


def cli_dist_dir() -> Path:
    """Return the built one-dir backend payload directory."""
    return DIST_DIR / CLI_DIR_NAME


def cli_exe_path() -> Path:
    """Return the built backend launcher inside the one-dir payload."""
    return cli_dist_dir() / CLI_EXE_NAME


def portable_exe_path() -> Path:
    """Return the one-file build used as the portable download and GUI sidecar."""
    return DIST_DIR / PORTABLE_EXE_NAME


def _rmtree_tolerant(path: Path) -> list[str]:
    """Remove a tree, returning anything that couldn't be deleted (in use)."""
    failures: list[str] = []

    def _on_error(_func, target, _exc) -> None:
        failures.append(str(target))

    shutil.rmtree(path, onerror=_on_error)
    return failures


def clean_build() -> None:
    """Remove previous build artifacts.

    Tolerates in-use files: a computa-setup.exe with its wizard open (or a
    running computa.exe) must not block rebuilding the CLI — the later build
    steps overwrite their own outputs anyway.
    """
    print("Cleaning previous build...")

    for target in (BUILD_DIR, DIST_DIR):
        if not target.exists():
            continue
        failures = _rmtree_tolerant(target)
        if failures:
            kept = ", ".join(sorted({Path(item).name for item in failures})[:4])
            print(f"  Removed {target} (kept in-use: {kept})")
        else:
            print(f"  Removed {target}")

    print("  Done.")


def run_pyinstaller() -> bool:
    """Run PyInstaller to build the executable."""
    print("\nBuilding executable with PyInstaller...")

    if not SPEC_FILE.exists():
        print(f"ERROR: Spec file not found: {SPEC_FILE}")
        return False

    result = subprocess.run(
        [
            sys.executable,
            "-m",
            "PyInstaller",
            "--clean",
            "--noconfirm",
            str(SPEC_FILE),
        ],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0:
        print("ERROR: PyInstaller failed!")
        if result.stdout:
            print("\nPyInstaller stdout:")
            print(result.stdout.rstrip())
        if result.stderr:
            print("\nPyInstaller stderr:")
            print(result.stderr.rstrip())
        return False

    print("  Build completed.")
    return True


# Modules whose imports are all lazy/exception-isolated in the codebase: a
# build environment missing them still freezes successfully, and the installed
# runtime silently degrades instead of crashing (the 2026-08-12 deploy shipped
# without ``wmi``, so every WMI-backed handler quietly detected nothing).
CRITICAL_FROZEN_MODULES = frozenset({"wmi", "pynvml"})


def check_frozen_module_warnings() -> bool:
    """Fail the build when PyInstaller reports a critical module as missing."""
    warn_file = BUILD_DIR / SPEC_FILE.stem / f"warn-{SPEC_FILE.stem}.txt"
    if not warn_file.exists():
        print(f"ERROR: PyInstaller warn file not found: {warn_file}")
        print("  Cannot prove the critical runtime modules were bundled.")
        return False

    missing: list[str] = []
    for line in warn_file.read_text(encoding="utf-8", errors="replace").splitlines():
        stripped = line.strip()
        if not stripped.startswith("missing module named "):
            continue
        module = stripped.removeprefix("missing module named ").split(" ", 1)[0]
        if module in CRITICAL_FROZEN_MODULES:
            missing.append(module)

    if missing:
        print("ERROR: Build is missing critical runtime module(s): " + ", ".join(sorted(missing)))
        print("  These imports are lazy/optional in the code, so the frozen exe")
        print("  would run but silently lose the features that need them.")
        print(f"  Install them into this interpreter: {sys.executable}")
        print("  (pip install -r requirements-dev.txt)")
        return False

    return True


def check_build_prerequisites() -> bool:
    """Validate build inputs before removing existing artifacts."""
    if not SPEC_FILE.exists():
        print(f"ERROR: Spec file not found: {SPEC_FILE}")
        return False

    result = subprocess.run(
        [sys.executable, "-m", "PyInstaller", "--version"],
        cwd=ROOT_DIR,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode == 0:
        return True

    print("ERROR: PyInstaller is not available for this Python interpreter.")
    print(f"  Interpreter: {sys.executable}")
    if result.stderr:
        print(f"  Error: {result.stderr.strip()}")
    print("  Use .\\.venv\\Scripts\\python.exe build.py deploy or install PyInstaller here.")
    return False


def verify_output() -> bool:
    """Verify the output executable was created."""
    exe_path = cli_exe_path()

    if not exe_path.exists():
        print(f"ERROR: Executable not found: {exe_path}")
        return False

    payload_bytes = sum(
        path.stat().st_size for path in cli_dist_dir().rglob("*") if path.is_file()
    )
    print("\nBuild successful!")
    print(f"  Executable: {exe_path}")
    print(f"  Payload: {cli_dist_dir()} ({payload_bytes / (1024 * 1024):.1f} MB total)")

    portable = portable_exe_path()
    if portable.exists():
        print(
            f"  Portable/sidecar one-file: {portable} "
            f"({portable.stat().st_size / (1024 * 1024):.1f} MB)"
        )

    return True


def copy_cli_to_gui() -> bool:
    """Copy the one-file CLI build to the GUI binaries directory."""
    print("\nCopying CLI to GUI binaries...")

    # Tauri sidecars must be a single self-contained file, so the GUI gets the
    # one-file build rather than the one-dir payload the tray runs.
    cli_exe = portable_exe_path()
    if not cli_exe.exists():
        print(f"ERROR: CLI sidecar not found at {cli_exe}")
        return False

    # Create binaries directory
    GUI_BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    # Tauri expects: abso-{target_triple}.exe — the sidecar names are an
    # internal GUI contract and keep the legacy abso prefix even though the
    # public CLI is computa.exe.
    targets = [
        "abso-x86_64-pc-windows-msvc.exe",
        "abso-x86_64-pc-windows-gnu.exe",
        "abso.exe",  # Development fallback
    ]

    for target_name in targets:
        target_path = GUI_BINARIES_DIR / target_name
        if _copy_file_if_changed(cli_exe, target_path):
            print(f"  Copied to: {target_path}")
        else:
            print(f"  Already current: {target_path}")

    return True


def local_appdata_root() -> Path:
    """Return the local AppData root for deploys on this machine."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        return Path(local_appdata)
    return Path.home() / "AppData" / "Local"


def _copy_missing_backup_dirs(source: Path, target: Path) -> int:
    """Copy backup snapshot directories that are not already in the target."""
    if not source.exists():
        return 0

    target.mkdir(parents=True, exist_ok=True)
    copied = 0
    for backup_dir in source.iterdir():
        if not backup_dir.is_dir():
            continue
        destination = target / backup_dir.name
        if destination.exists():
            continue
        shutil.copytree(backup_dir, destination)
        copied += 1
    return copied


def _files_equal(left: Path, right: Path) -> bool:
    """Return True when both files exist and have identical bytes."""
    if not left.exists() or not right.exists():
        return False
    if left.stat().st_size != right.stat().st_size:
        return False
    return left.read_bytes() == right.read_bytes()


def _copy_file_if_changed(source: Path, target: Path) -> bool:
    """Copy source to target only when the target bytes differ."""
    if _files_equal(source, target):
        return False

    target.parent.mkdir(parents=True, exist_ok=True)
    try:
        shutil.copy2(source, target)
    except PermissionError:
        _copy_file_via_rename_fallback(source, target)
    return True


def _copy_file_via_rename_fallback(source: Path, target: Path) -> None:
    """Replace a file that allows rename but rejects direct overwrite."""
    if not target.exists():
        raise FileNotFoundError(f"target file disappeared during replace: {target}")

    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    displaced = _unique_displaced_path(target, stamp)
    target.rename(displaced)
    try:
        shutil.copy2(source, target)
    except Exception:
        if not target.exists() and displaced.exists():
            displaced.rename(target)
        raise

    # The original file may still be held by a short-lived scanner. It has
    # already been renamed out of the runtime path, and deploy backups keep the
    # rollback copy.
    with contextlib.suppress(OSError):
        displaced.unlink()


def _unique_displaced_path(target: Path, stamp: str) -> Path:
    """Return a side-by-side path for a temporarily displaced target file."""
    candidate = target.with_name(f"{target.name}.replaced-{stamp}")
    if not candidate.exists():
        return candidate

    counter = 2
    while True:
        candidate = target.with_name(f"{target.name}.replaced-{stamp}-{counter}")
        if not candidate.exists():
            return candidate
        counter += 1


def _iter_tray_runtime_files(tray_source: Path):
    """Yield deployable tray runtime assets in stable order."""
    if not tray_source.exists():
        return
    for path in sorted(tray_source.iterdir(), key=lambda item: item.name.lower()):
        if (
            path.is_file()
            and path.suffix.lower() in TRAY_RUNTIME_EXTENSIONS
            and path.name not in TRAY_DEPLOY_EXCLUDE_FILENAMES
        ):
            yield path


def _iter_tray_theme_files(tray_source: Path):
    """Yield (source, relative) pairs for theme-pack files under themes/."""
    themes_source = tray_source / "themes"
    if not themes_source.exists():
        return
    for path in sorted(themes_source.rglob("*"), key=lambda item: str(item).lower()):
        if path.is_file() and path.suffix.lower() in TRAY_RUNTIME_EXTENSIONS:
            yield path, path.relative_to(tray_source)


def _remove_obsolete_tray_sidecars(tray_target: Path) -> list[str]:
    """Remove known stale sidecar files that no current tray runtime reads."""
    removed: list[str] = []
    for name in sorted(TRAY_OBSOLETE_SIDECAR_FILENAMES):
        path = tray_target / name
        if path.exists() and path.is_file():
            path.unlink()
            removed.append(str(path))
    return removed


def _unique_backup_path(backup_dir: Path, backup_name: str, stamp: str) -> Path:
    """Return a backup path that will not overwrite an existing deploy backup."""
    base_path = backup_dir / f"{backup_name}.bak-{stamp}"
    if not base_path.exists():
        return base_path

    counter = 2
    while True:
        candidate = backup_dir / f"{backup_name}.bak-{stamp}-{counter}"
        if not candidate.exists():
            return candidate
        counter += 1


def _sync_file_with_backup(
    *,
    source: Path,
    target: Path,
    backup_dir: Path,
    backup_name: str,
    stamp: str,
    required: bool = True,
) -> dict[str, object]:
    """Copy a deploy artifact, backing up only when bytes actually differ."""
    result: dict[str, object] = {
        "source": str(source),
        "target": str(target),
        "available": source.exists(),
        "copied": False,
        "backup": None,
        "length": target.stat().st_size if target.exists() else None,
    }

    if not source.exists():
        if required:
            raise FileNotFoundError(f"required deploy source not found: {source}")
        return result

    if _files_equal(source, target):
        result["length"] = target.stat().st_size
        return result

    backup_path: Path | None = None
    if target.exists():
        backup_path = _unique_backup_path(backup_dir, backup_name, stamp)
        shutil.copy2(target, backup_path)

    _copy_file_if_changed(source, target)
    result.update({
        "copied": True,
        "backup": str(backup_path) if backup_path else None,
        "length": target.stat().st_size,
    })
    return result


def _sync_backend_payload(
    *,
    source_dir: Path,
    install_root: Path,
    backup_dir: Path,
    stamp: str,
) -> dict[str, object]:
    """Mirror the one-dir backend payload into the install root.

    Ordering is deliberate: every support file lands (and every stale one is
    pruned) *before* the launcher is replaced, so an interrupted deploy never
    leaves a new ``computa.exe`` pointing at a half-written ``_internal``.

    Pruning is scoped to the top-level directories the payload owns — the
    install root also holds tray assets, backups, config, and the GUI, none of
    which this function may touch.
    """
    launcher_relative = Path(CLI_EXE_NAME)
    payload_files = [path for path in source_dir.rglob("*") if path.is_file()]
    support_files = [
        path for path in payload_files if path.relative_to(source_dir) != launcher_relative
    ]

    copied = 0
    for path in sorted(support_files, key=lambda item: str(item).lower()):
        relative = path.relative_to(source_dir)
        if _copy_file_if_changed(path, install_root / relative):
            copied += 1

    expected = {path.relative_to(source_dir) for path in support_files}
    managed_dirs = {
        relative.parts[0] for relative in expected if len(relative.parts) > 1
    }
    removed = 0
    for dir_name in sorted(managed_dirs):
        target_dir = install_root / dir_name
        if not target_dir.exists():
            continue
        # Deepest-first so directories are empty by the time they are visited.
        for path in sorted(target_dir.rglob("*"), key=lambda item: str(item).lower(), reverse=True):
            if path.is_file():
                if path.relative_to(install_root) not in expected:
                    path.unlink()
                    removed += 1
            elif path.is_dir() and not any(path.iterdir()):
                path.rmdir()

    launcher_result = _sync_file_with_backup(
        source=source_dir / CLI_EXE_NAME,
        target=install_root / CLI_EXE_NAME,
        backup_dir=backup_dir,
        backup_name=CLI_EXE_NAME,
        stamp=stamp,
    )
    launcher_result["support_copied"] = copied
    launcher_result["support_removed"] = removed
    launcher_result["payload_length"] = sum(path.stat().st_size for path in payload_files)
    return launcher_result


def _sync_gui_executable(
    *,
    install_root: Path,
    backup_dir: Path,
    stamp: str,
) -> dict[str, object]:
    """Copy the Tauri GUI exe into LocalAppData when a release build exists."""
    source = GUI_DIR / "src-tauri" / "target" / "release" / GUI_EXE_NAME
    return _sync_file_with_backup(
        source=source,
        target=install_root / GUI_EXE_NAME,
        backup_dir=backup_dir,
        backup_name=GUI_EXE_NAME,
        stamp=stamp,
        required=False,
    )


def deploy_local_runtime(install_dir: Path | None = None) -> dict[str, object]:
    """Deploy the built backend and runtime assets to LocalAppData."""
    cli_exe = cli_exe_path()
    if not cli_exe.exists():
        raise FileNotFoundError(f"CLI not found at {cli_exe}")

    install_root = install_dir or (local_appdata_root() / APP_DIR_NAME)
    install_root.mkdir(parents=True, exist_ok=True)

    backup_dir = install_root / "deploy-backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")

    installed_exe = install_root / CLI_EXE_NAME
    backend_result = _sync_backend_payload(
        source_dir=cli_dist_dir(),
        install_root=install_root,
        backup_dir=backup_dir,
        stamp=stamp,
    )

    # Pre-rebrand installs shipped the backend as abso.exe; move any stale
    # copy into deploy-backups so nothing on the machine keeps running (or
    # resolving) the old binary.
    legacy_exe = install_root / "abso.exe"
    legacy_backend_migrated = False
    if legacy_exe.exists():
        legacy_backup = _unique_backup_path(backup_dir, "abso.exe", stamp)
        try:
            legacy_exe.rename(legacy_backup)
            legacy_backend_migrated = True
        except OSError:
            # A running process may hold the old exe; the next deploy retries.
            pass

    # Keep GUI sidecars aligned with the backend used by the installed GUI.
    copy_cli_to_gui()
    gui_result = _sync_gui_executable(
        install_root=install_root,
        backup_dir=backup_dir,
        stamp=stamp,
    )

    tray_source = ROOT_DIR / "abso" / "tray"
    tray_target = install_root / "abso" / "tray"
    tray_target.mkdir(parents=True, exist_ok=True)
    tray_files = 0
    tray_updated_files = 0
    if tray_source.exists():
        for path in _iter_tray_runtime_files(tray_source):
            tray_files += 1
            if _copy_file_if_changed(path, tray_target / path.name):
                tray_updated_files += 1
        for path, relative in _iter_tray_theme_files(tray_source):
            theme_target = tray_target / relative
            theme_target.parent.mkdir(parents=True, exist_ok=True)
            tray_files += 1
            if _copy_file_if_changed(path, theme_target):
                tray_updated_files += 1
    tray_removed_files = _remove_obsolete_tray_sidecars(tray_target)

    npi_source = ROOT_DIR / "tools" / "npi"
    npi_files = 0
    npi_updated = 0
    if npi_source.exists():
        for path in sorted(npi_source.rglob("*"), key=lambda item: str(item).lower()):
            if not path.is_file():
                continue
            if path.suffix.lower() in NPI_RUNTIME_EXCLUDE_SUFFIXES:
                continue
            npi_files += 1
            target = install_root / "tools" / "npi" / path.relative_to(npi_source)
            if _copy_file_if_changed(path, target):
                npi_updated += 1

    config_source = ROOT_DIR / "abso.yaml"
    config_target: Path | None = None
    config_copied = False
    if config_source.exists():
        config_target = install_root / "abso.yaml"
        config_copied = _copy_file_if_changed(config_source, config_target)

    migrated_backups = _copy_missing_backup_dirs(ROOT_DIR / "backups", install_root / "backups")

    return {
        "installed_exe": str(installed_exe),
        "installed_length": installed_exe.stat().st_size,
        "installed_payload_length": backend_result.get("payload_length"),
        "backend": backend_result,
        "backup": backend_result.get("backup"),
        "gui": gui_result,
        "tray_target": str(tray_target),
        "tray_file_count": tray_files,
        "tray_updated_count": tray_updated_files,
        "tray_removed_count": len(tray_removed_files),
        "tray_removed_files": tray_removed_files,
        "npi_file_count": npi_files,
        "npi_updated_count": npi_updated,
        "config": str(config_target) if config_target else None,
        "config_copied": config_copied,
        "migrated_backups": migrated_backups,
        "legacy_backend_migrated": legacy_backend_migrated,
    }


def print_deploy_result(result: dict[str, object]) -> None:
    """Print a concise deploy summary."""
    print("\nLocal runtime deployed.")
    backend_result = result.get("backend")
    backend_status = ""
    if isinstance(backend_result, dict):
        backend_status = ", copied" if backend_result.get("copied") else ", already current"
    print(
        f"  Backend: {result['installed_exe']} "
        f"({result['installed_length']} bytes{backend_status})"
    )
    if isinstance(backend_result, dict) and "support_copied" in backend_result:
        payload_mb = (backend_result.get("payload_length") or 0) / (1024 * 1024)
        support_summary = f"{backend_result['support_copied']} updated"
        if backend_result.get("support_removed"):
            support_summary += f", {backend_result['support_removed']} stale removed"
        print(f"  Backend payload: {payload_mb:.1f} MB ({support_summary})")
    if result.get("backup"):
        print(f"  Previous backend backup: {result['backup']}")
    gui_result = result.get("gui")
    if isinstance(gui_result, dict) and gui_result.get("available"):
        status = "copied" if gui_result.get("copied") else "already current"
        print(f"  GUI: {gui_result['target']} ({gui_result['length']} bytes, {status})")
        if gui_result.get("backup"):
            print(f"  Previous GUI backup: {gui_result['backup']}")
    tray_summary = f"{result['tray_file_count']} files"
    if "tray_updated_count" in result:
        tray_summary += f", {result['tray_updated_count']} updated"
    if result.get("tray_removed_count"):
        tray_summary += f", {result['tray_removed_count']} stale removed"
    print(f"  Tray assets: {result['tray_target']} ({tray_summary})")
    if result.get("npi_file_count"):
        print(
            f"  Nvidia Profile Inspector: {result['npi_file_count']} files, "
            f"{result['npi_updated_count']} updated"
        )
    if result.get("config"):
        config_status = "copied" if result.get("config_copied") else "already current"
        print(f"  Config: {result['config']} ({config_status})")
    print(f"  Migrated backup snapshots: {result['migrated_backups']}")


def get_gui_build_env() -> dict:
    """Get environment with Node.js, Cargo, and MinGW in PATH."""
    env = os.environ.copy()
    extra_paths = [
        r"C:\Program Files\nodejs",
        os.path.expanduser(r"~\.cargo\bin"),
        r"C:\msys64\mingw64\bin",
    ]
    env["PATH"] = os.pathsep.join(extra_paths + [env.get("PATH", "")])
    return env


def resolve_npm_command(env: dict[str, str] | None = None) -> str:
    """Resolve npm without relying on shell=True command dispatch."""
    search_path = None if env is None else env.get("PATH")
    candidates = ["npm.cmd", "npm"] if os.name == "nt" else ["npm", "npm.cmd"]
    for candidate in candidates:
        resolved = shutil.which(candidate, path=search_path)
        if resolved:
            return resolved
    return candidates[0]


def build_gui() -> bool:
    """Build the GUI using Tauri."""
    print("\n" + "=" * 60)
    print("Building ABSO GUI with Tauri...")
    print("=" * 60)

    # Check CLI is available
    sidecar = GUI_BINARIES_DIR / "abso-x86_64-pc-windows-msvc.exe"
    if not sidecar.exists():
        print("CLI not found in GUI binaries. Building CLI first...")
        if not build_cli():
            return False
        if not copy_cli_to_gui():
            return False

    # Get environment with proper PATH
    env = get_gui_build_env()
    npm_cmd = resolve_npm_command(env)

    # Check for node_modules
    if not (GUI_DIR / "node_modules").exists():
        print("Installing npm dependencies...")
        result = subprocess.run([npm_cmd, "install"], cwd=GUI_DIR, env=env, check=False)
        if result.returncode != 0:
            print("ERROR: npm install failed!")
            return False

    # Build with Tauri
    print("\nRunning Tauri build...")
    result = subprocess.run([npm_cmd, "run", "tauri", "build"], cwd=GUI_DIR, env=env, check=False)

    if result.returncode != 0:
        print("ERROR: Tauri build failed!")
        return False

    # Report output
    bundle_dir = GUI_DIR / "src-tauri" / "target" / "release" / "bundle"
    print("\n" + "=" * 60)
    print("GUI Build Complete!")
    print("=" * 60)

    if bundle_dir.exists():
        for msi in bundle_dir.glob("msi/*.msi"):
            size_mb = msi.stat().st_size / (1024 * 1024)
            print(f"  MSI: {msi.name} ({size_mb:.1f} MB)")
        for nsis in bundle_dir.glob("nsis/*.exe"):
            size_mb = nsis.stat().st_size / (1024 * 1024)
            print(f"  NSIS: {nsis.name} ({size_mb:.1f} MB)")

    return True


def build_cli() -> bool:
    """Build the CLI with PyInstaller."""
    print("=" * 60)
    print("computa CLI Build")
    print("=" * 60)

    if not check_build_prerequisites():
        return False

    clean_build()

    if not run_pyinstaller():
        return False

    if not check_frozen_module_warnings():
        return False

    return verify_output()


def deploy_existing_cli() -> bool:
    """Deploy an already-built CLI to the local runtime."""
    try:
        result = deploy_local_runtime()
    except Exception as e:
        print(f"ERROR: deploy failed: {e}")
        return False

    print_deploy_result(result)
    return True


def build_and_deploy() -> bool:
    """Build the CLI and deploy the full local runtime payload."""
    if not build_cli():
        return False
    return deploy_existing_cli()


def dev_setup() -> None:
    """Set up for GUI development."""
    print("=" * 60)
    print("Development Setup")
    print("=" * 60)

    if not build_cli():
        sys.exit(1)

    if not copy_cli_to_gui():
        sys.exit(1)

    print("\n" + "=" * 60)
    print("Development setup complete!")
    print("=" * 60)
    print("\nTo run the GUI in development mode:")
    print("  cd gui")
    print("  npm install")
    print("  npm run tauri:dev")


def _find_iscc() -> Path | None:
    """Locate the Inno Setup 6 compiler."""
    candidates = []
    env_override = os.environ.get("ISCC")
    if env_override:
        candidates.append(Path(env_override))
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        candidates.append(Path(local_appdata) / "Programs" / "Inno Setup 6" / "ISCC.exe")
    candidates.append(Path(r"C:\Program Files (x86)\Inno Setup 6\ISCC.exe"))
    candidates.append(Path(r"C:\Program Files\Inno Setup 6\ISCC.exe"))
    for candidate in candidates:
        if candidate.is_file():
            return candidate
    return None


def _installer_payload_tray_files(tray_source: Path):
    """Yield (source, dest-relative) pairs for redistributable tray assets.

    Only the default theme ships in the installer; personal theme packs
    (non-redistributable media) never leave this machine.
    """
    for path in sorted(tray_source.iterdir(), key=lambda item: item.name.lower()):
        if (
            path.is_file()
            and path.suffix.lower() in TRAY_RUNTIME_EXTENSIONS
            and path.name not in TRAY_DEPLOY_EXCLUDE_FILENAMES
        ):
            yield path, Path("abso/tray") / path.name
    default_theme = tray_source / "themes" / "default"
    if default_theme.exists():
        for path in sorted(default_theme.rglob("*"), key=lambda item: str(item).lower()):
            if path.is_file():
                yield path, Path("abso/tray/themes/default") / path.relative_to(default_theme)


def build_installer() -> bool:
    """Build dist/computa-setup.exe with Inno Setup."""
    print("\nBuilding computa-setup.exe (Inno Setup)...")

    exe = cli_exe_path()
    if not exe.exists():
        print(f"  dist\\{CLI_DIR_NAME}\\{CLI_EXE_NAME} not found ({exe}).")
        print("  Build it first:  build.py cli")
        return False

    iscc = _find_iscc()
    if iscc is None:
        print("  Inno Setup 6 (ISCC.exe) not found.")
        print("  Install it:  winget install -e --id JRSoftware.InnoSetup --scope user")
        print("  Or set the ISCC env var to the full ISCC.exe path.")
        return False

    payload = BUILD_DIR / "installer-payload"
    if payload.exists():
        shutil.rmtree(payload)
    (payload / "abso" / "tray").mkdir(parents=True)

    # Ship the whole one-dir payload: computa.exe plus its _internal tree.
    backend_files = 0
    for source in sorted(cli_dist_dir().rglob("*"), key=lambda item: str(item).lower()):
        if not source.is_file():
            continue
        dest = payload / source.relative_to(cli_dist_dir())
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        backend_files += 1

    tray_source = ROOT_DIR / "abso" / "tray"
    count = 0
    for source, relative in _installer_payload_tray_files(tray_source):
        dest = payload / relative
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(source, dest)
        count += 1
    print(
        f"  Payload: {backend_files} backend files + {count} tray files "
        f"(themes: default only)"
    )

    version_ns: dict = {}
    exec((ROOT_DIR / "abso" / "__version__.py").read_text(encoding="utf-8"), version_ns)
    version = version_ns["__version__"]

    result = subprocess.run(
        [
            str(iscc),
            f"/DAppVer={version}",
            f"/DPayloadDir={payload}",
            f"/O{DIST_DIR}",
            str(ROOT_DIR / "scripts" / "installer.iss"),
        ],
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        print("  ISCC failed:")
        print(result.stdout[-2000:] if result.stdout else "")
        print(result.stderr[-2000:] if result.stderr else "")
        return False

    setup_exe = DIST_DIR / "computa-setup.exe"
    size_mb = setup_exe.stat().st_size / (1024 * 1024) if setup_exe.exists() else 0
    print(f"  Built {setup_exe} ({size_mb:.1f} MB)")
    return True


def show_help() -> None:
    """Show usage help."""
    print(__doc__)


def main() -> int:
    """Main build process."""
    command = sys.argv[1].lower() if len(sys.argv) > 1 else "cli"

    if command in ["cli", ""]:
        return 0 if build_cli() else 1
    elif command == "gui":
        return 0 if build_gui() else 1
    elif command == "all":
        if not build_cli():
            return 1
        if not copy_cli_to_gui():
            return 1
        if not build_gui():
            return 1
        return 0
    elif command == "deploy":
        return 0 if build_and_deploy() else 1
    elif command in ["deploy-existing", "deploy_existing"]:
        return 0 if deploy_existing_cli() else 1
    elif command == "installer":
        return 0 if build_installer() else 1
    elif command == "dev":
        dev_setup()
        return 0
    elif command in ["help", "-h", "--help"]:
        show_help()
        return 0
    else:
        print(f"Unknown command: {command}")
        show_help()
        return 1


if __name__ == "__main__":
    sys.exit(main())
