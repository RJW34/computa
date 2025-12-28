#!/usr/bin/env python
"""Build script for A.B.S.O. standalone executable.

This script:
1. Cleans previous build artifacts
2. Runs PyInstaller with the spec file
3. Verifies the output executable

Usage:
    python build.py

Output:
    dist/abso.exe - Standalone Windows executable
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

# Build directories
ROOT_DIR = Path(__file__).parent
BUILD_DIR = ROOT_DIR / "build"
DIST_DIR = ROOT_DIR / "dist"
SPEC_FILE = ROOT_DIR / "abso.spec"


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


def main() -> int:
    """Main build process."""
    print("=" * 60)
    print("A.B.S.O. Build Script")
    print("=" * 60)

    # Step 1: Clean
    clean_build()

    # Step 2: Build
    if not run_pyinstaller():
        return 1

    # Step 3: Verify
    if not verify_output():
        return 1

    print("\n" + "=" * 60)
    print("Build complete! You can now distribute dist/abso.exe")
    print("=" * 60)

    return 0


if __name__ == "__main__":
    sys.exit(main())
