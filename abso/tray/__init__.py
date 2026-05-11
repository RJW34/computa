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
import json
import time
from pathlib import Path

TRAY_MUTEX_NAME = "Global\\ABSO_Tray_SingleInstance_v2"


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


def get_startup_status() -> dict[str, object]:
    """Get startup registration status from the installer script."""
    tray_dir = get_tray_dir()
    installer = tray_dir / "Install-Startup.ps1"

    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(installer),
            "-Status",
            "-Json",
        ],
        capture_output=True,
        text=True,
        check=True,
    )

    return json.loads(result.stdout.strip() or "{}")


def _tray_mutex_exists() -> bool:
    """Return True when the tray's single-instance mutex is currently owned."""
    if sys.platform != "win32":
        return False

    try:
        import ctypes
        from ctypes import wintypes

        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel32.OpenMutexW.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.LPCWSTR]
        kernel32.OpenMutexW.restype = wintypes.HANDLE
        kernel32.CloseHandle.argtypes = [wintypes.HANDLE]
        kernel32.CloseHandle.restype = wintypes.BOOL
        synchronize = 0x00100000
        handle = kernel32.OpenMutexW(synchronize, False, TRAY_MUTEX_NAME)
        if not handle:
            return False
        kernel32.CloseHandle(handle)
        return True
    except Exception:
        return False


def get_tray_processes() -> list[dict[str, object]]:
    """Return running PowerShell processes that host ABSO tray."""
    ps_command = (
        "Get-CimInstance Win32_Process "
        "| Where-Object { "
        "$_.ProcessId -ne $PID -and "
        "($_.Name -eq 'powershell.exe' -or $_.Name -eq 'pwsh.exe') -and "
        "$_.CommandLine -and "
        "$_.CommandLine -like '*ABSO-Tray.ps1*' -and "
        "$_.CommandLine -notlike '*Get-CimInstance Win32_Process*' "
        "} "
        "| Select-Object ProcessId, Name, CommandLine "
        "| ConvertTo-Json -Compress"
    )
    result = subprocess.run(
        [
            "powershell.exe",
            "-NoProfile",
            "-ExecutionPolicy",
            "Bypass",
            "-Command",
            ps_command,
        ],
        capture_output=True,
        text=True,
        check=False,
    )

    if result.returncode != 0 or not result.stdout.strip():
        return []

    payload = json.loads(result.stdout)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict):
        return [payload]
    return []


def _tray_runtime_snapshot() -> dict[str, object]:
    processes = get_tray_processes()
    mutex_exists = _tray_mutex_exists()
    return {
        "running": mutex_exists or bool(processes),
        "mutex_exists": mutex_exists,
        "processes": processes,
    }


def is_tray_running() -> bool:
    """Return True when at least one tray host process is detected."""
    return bool(_tray_runtime_snapshot()["running"])


def ensure_tray_running(start_if_missing: bool = False) -> dict[str, object]:
    """Check tray process and optionally start it when missing."""
    before = _tray_runtime_snapshot()
    running_before = bool(before["running"])
    started = False
    error: str | None = None

    if (not running_before) and start_if_missing:
        try:
            start_tray()
            started = True
            time.sleep(1.0)
        except Exception as e:
            error = str(e)

    after = _tray_runtime_snapshot()
    running_after = bool(after["running"])
    return {
        "running_before": running_before,
        "started": started,
        "running_after": running_after,
        "mutex_exists": after["mutex_exists"],
        "error": error,
        "processes": after["processes"] if running_after else [],
    }


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
    parser.add_argument(
        "--startup-status",
        action="store_true",
        help="Show current startup registration status",
    )

    args = parser.parse_args()

    if args.install_startup:
        install_startup(uninstall=False)
    elif args.uninstall_startup:
        install_startup(uninstall=True)
    elif args.startup_status:
        print(json.dumps(get_startup_status(), indent=2))
    else:
        start_tray()
