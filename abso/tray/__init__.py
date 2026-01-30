"""A.B.S.O. System Tray Application.

Ultra-lightweight PowerShell-based tray for quick profile switching.

Features:
- Left-click shows profile menu
- Apply profile via CLI (JSON mode)

Files:
- ABSO-Tray.ps1: Main tray application (~25-30MB RAM)
- ABSO-Tray.vbs: Hidden launcher (no console flash)
- Install-Startup.ps1: Add/remove from Windows startup

Usage:
    # Start tray manually
    wscript.exe "abso/tray/ABSO-Tray.vbs"

    # Or via Python
    python -m abso.tray

    # Add to Windows startup
    powershell -File "abso/tray/Install-Startup.ps1" -Install
"""

import subprocess
import sys
from pathlib import Path


def get_tray_dir() -> Path:
    """Get the tray scripts directory."""
    return Path(__file__).parent


def start_tray() -> None:
    """Start the A.B.S.O. system tray application."""
    tray_dir = get_tray_dir()
    vbs_path = tray_dir / "ABSO-Tray.vbs"

    if not vbs_path.exists():
        print(f"Error: Tray launcher not found: {vbs_path}", file=sys.stderr)
        sys.exit(1)

    # Launch via wscript for truly hidden startup
    subprocess.Popen(
        ["wscript.exe", str(vbs_path)],
        cwd=str(tray_dir),
        creationflags=subprocess.CREATE_NO_WINDOW if sys.platform == "win32" else 0,
    )
    print("A.B.S.O. tray started.")


def install_startup(uninstall: bool = False) -> None:
    """Install or uninstall from Windows startup."""
    tray_dir = get_tray_dir()
    installer = tray_dir / "Install-Startup.ps1"

    flag = "-Uninstall" if uninstall else "-Install"
    subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            flag,
        ],
        check=True,
    )


if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="A.B.S.O. System Tray")
    parser.add_argument(
        "--install-startup",
        action="store_true",
        help="Add to Windows startup",
    )
    parser.add_argument(
        "--uninstall-startup",
        action="store_true",
        help="Remove from Windows startup",
    )

    args = parser.parse_args()

    if args.install_startup:
        install_startup(uninstall=False)
    elif args.uninstall_startup:
        install_startup(uninstall=True)
    else:
        start_tray()
