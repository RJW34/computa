"""One-shot helpers for finishing the Slippi NVIDIA binding on this machine.

Usage:
  python -m scripts.bind_slippi_nvidia             # verify current state
  python -m scripts.bind_slippi_nvidia bind        # try NVAPI bind + fallback user profile
  python -m scripts.bind_slippi_nvidia cleanup     # delete the ABSO fallback user profile
  python -m scripts.bind_slippi_nvidia open_nvcp   # launch NVCP 3D settings page
  python -m scripts.bind_slippi_nvidia open_npi    # launch Nvidia Profile Inspector GUI

All output is one JSON line per invocation.
"""

from __future__ import annotations

import json
import sys
from typing import Any

PREDEFINED_PROFILE = "Super Smash Bros. Melee (Slippi)"
FALLBACK_PROFILE = "ABSO - Slippi Dolphin"
TARGET_EXE = "Slippi Dolphin.exe"


def _owner(drs, exe: str) -> str | None:
    try:
        info = drs.find_application_owner(exe)
    except Exception:
        return None
    if isinstance(info, dict):
        name = info.get("profile_name")
        return str(name) if name else None
    return None


def verify() -> dict[str, Any]:
    from abso.settings.nvidia.nvapi_drs import DRSProfileManager

    manager = DRSProfileManager()
    report: dict[str, Any] = {"exe": TARGET_EXE}
    try:
        with manager._drs as drs:
            report["owner"] = _owner(drs, TARGET_EXE)
            for name in (PREDEFINED_PROFILE, FALLBACK_PROFILE):
                profile = drs.find_profile_by_name(name)
                report[f"{name}_exists"] = profile is not None
    except Exception as e:
        report["error"] = str(e)
    return report


def cleanup_fallback() -> dict[str, Any]:
    from abso.settings.nvidia.nvapi_drs import DRSProfileManager

    manager = DRSProfileManager()
    report: dict[str, Any] = {"profile": FALLBACK_PROFILE}
    try:
        with manager._drs as drs:
            profile = drs.find_profile_by_name(FALLBACK_PROFILE)
            if not profile:
                report["result"] = "missing"
                return report
            deleted = drs.delete_profile(profile)
            report["result"] = "deleted" if deleted else "delete_failed"
            drs.save_settings()
    except Exception as e:
        report["error"] = str(e)
    return report


def open_nvcp() -> dict[str, Any]:
    from abso.settings.nvidia.nvapi_drs import DRSProfileManager

    launched = DRSProfileManager.open_nvidia_control_panel()
    return {"launched": bool(launched)}


def open_npi() -> dict[str, Any]:
    from abso.settings.nvidia.npi import NPIManager

    npi = NPIManager()
    if not npi.is_available():
        return {"launched": False, "reason": "npi_not_found"}
    ok = npi.launch_for_app_binding(PREDEFINED_PROFILE, TARGET_EXE)
    return {"launched": bool(ok), "path": str(npi.get_path()) if ok else None}


def main(argv: list[str]) -> int:
    action = argv[1] if len(argv) > 1 else "verify"

    handlers = {
        "verify": verify,
        "cleanup": cleanup_fallback,
        "open_nvcp": open_nvcp,
        "open_npi": open_npi,
    }

    fn = handlers.get(action)
    if not fn:
        print(json.dumps({"ok": False, "error": f"unknown action: {action}"}))
        return 2

    try:
        result = fn()
    except Exception as e:
        print(json.dumps({"ok": False, "action": action, "error": str(e)}))
        return 3

    result.setdefault("action", action)
    print(json.dumps(result))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
