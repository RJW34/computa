#!/usr/bin/env python
"""Build script for A.B.S.O. (CLI + GUI).

Commands:
    python build.py           # Build CLI only (default)
    python build.py cli       # Build CLI only (dist/abso.exe)
    python build.py gui       # Build GUI with Tauri (requires CLI)
    python build.py all       # Build both CLI and GUI installer
    python build.py dev       # Set up for GUI development

Output:
    dist/abso.exe                                    - Standalone CLI
    gui/src-tauri/target/release/bundle/msi/*.msi   - Windows installer
    gui/src-tauri/target/release/bundle/nsis/*.exe  - NSIS installer
"""

from __future__ import annotations

import os
import shutil
import subprocess
import sys
from pathlib import Path

# Build directories
ROOT_DIR = Path(__file__).parent
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
SPEC_FILE = ROOT_DIR / "abso.spec"
GUI_DIR = ROOT_DIR / "gui"
GUI_BINARIES_DIR = GUI_DIR / "src-tauri" / "binaries"


def clean_build() -> None:
    """Remove previous build artifacts."""
    print("Cleaning previous build...")

    if BUILD_DIR.exists():
        shutil.rmtree(BUILD_DIR)
        print(f"  Removed {BUILD_DIR}")

    if DIST_DIR.exists():
        shutil.rmtree(DIST_DIR)
        print(f"  Removed {DIST_DIR}")

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
    )

    if result.returncode != 0:
        print("ERROR: PyInstaller failed!")
        return False

    print("  Build completed.")
    return True


def verify_output() -> bool:
    """Verify the output executable was created."""
    exe_path = DIST_DIR / "abso.exe"

    if not exe_path.exists():
        print(f"ERROR: Executable not found: {exe_path}")
        return False

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print("\nBuild successful!")
    print(f"  Executable: {exe_path}")
    print(f"  Size: {size_mb:.1f} MB")

    return True


def copy_cli_to_gui() -> bool:
    """Copy the built CLI to the GUI binaries directory."""
    print("\nCopying CLI to GUI binaries...")

    cli_exe = DIST_DIR / "abso.exe"
    if not cli_exe.exists():
        print(f"ERROR: CLI not found at {cli_exe}")
        return False

    # Create binaries directory
    GUI_BINARIES_DIR.mkdir(parents=True, exist_ok=True)

    # Tauri expects: abso-{target_triple}.exe
    target_name = "abso-x86_64-pc-windows-msvc.exe"
    target_path = GUI_BINARIES_DIR / target_name

    shutil.copy2(cli_exe, target_path)
    print(f"  Copied to: {target_path}")

    # Also copy as abso.exe for development fallback
    dev_path = GUI_BINARIES_DIR / "abso.exe"
    shutil.copy2(cli_exe, dev_path)
    print(f"  Copied to: {dev_path}")

    return True


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

    # Check for node_modules
    if not (GUI_DIR / "node_modules").exists():
        print("Installing npm dependencies...")
        result = subprocess.run(["npm", "install"], cwd=GUI_DIR, shell=True)
        if result.returncode != 0:
            print("ERROR: npm install failed!")
            return False

    # Build with Tauri
    print("\nRunning Tauri build...")
    result = subprocess.run(["npm", "run", "tauri", "build"], cwd=GUI_DIR, shell=True)

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
    print("A.B.S.O. CLI Build")
    print("=" * 60)

    clean_build()

    if not run_pyinstaller():
        return False

    if not verify_output():
        return False

    return True


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
