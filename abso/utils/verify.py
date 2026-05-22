"""
System verification utility for ABSO.
Outputs clean JSON that can be parsed by external tools.
"""

import json
import sys
import winreg
import subprocess
from typing import Any


def get_registry_value(hive: int, path: str, name: str) -> Any:
    """Get a registry value, returns None if not found."""
    try:
        with winreg.OpenKey(hive, path) as key:
            value, _ = winreg.QueryValueEx(key, name)
            return value
    except (FileNotFoundError, OSError):
        return None


def check_windows_settings() -> dict:
    """Check Windows gaming-related settings."""
    results = {}

    # Game Mode
    results["game_mode"] = {
        "value": get_registry_value(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\GameBar",
            "AutoGameModeEnabled"
        ),
        "expected": 1,
        "description": "Game Mode"
    }

    # Game DVR
    results["game_dvr"] = {
        "value": get_registry_value(
            winreg.HKEY_CURRENT_USER,
            r"Software\Microsoft\Windows\CurrentVersion\GameDVR",
            "AppCaptureEnabled"
        ),
        "expected": 0,
        "description": "Game DVR (should be OFF)"
    }

    # HAGS
    results["hags"] = {
        "value": get_registry_value(
            winreg.HKEY_LOCAL_MACHINE,
            r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers",
            "HwSchMode"
        ),
        "expected": "profile_dependent",
        "description": "Hardware Accelerated GPU Scheduling"
    }

    # Fullscreen Optimizations
    results["fso"] = {
        "value": get_registry_value(
            winreg.HKEY_CURRENT_USER,
            r"System\GameConfigStore",
            "GameDVR_FSEBehavior"
        ),
        "expected": 2,
        "description": "Fullscreen Optimizations disabled"
    }

    # Game Priority settings
    games_path = r"SOFTWARE\Microsoft\Windows NT\CurrentVersion\Multimedia\SystemProfile\Tasks\Games"
    results["game_priority"] = {
        "value": get_registry_value(winreg.HKEY_LOCAL_MACHINE, games_path, "Priority"),
        "expected": 6,
        "description": "Game thread priority"
    }
    results["scheduling_category"] = {
        "value": get_registry_value(winreg.HKEY_LOCAL_MACHINE, games_path, "Scheduling Category"),
        "expected": "High",
        "description": "Scheduling category"
    }
    results["sfio_priority"] = {
        "value": get_registry_value(winreg.HKEY_LOCAL_MACHINE, games_path, "SFIO Priority"),
        "expected": "High",
        "description": "SFIO Priority"
    }

    return results


def check_power_plan() -> dict:
    """Check active power plan (Ultimate Performance is the standard)."""
    try:
        result = subprocess.run(
            ["powercfg", "/getactivescheme"],
            capture_output=True,
            text=True
        )
        output = result.stdout.strip()

        is_high_perf = "high performance" in output.lower()
        is_ultimate = "ultimate" in output.lower()

        return {
            "active_scheme": output,
            "is_high_performance": is_high_perf,
            "is_ultimate": is_ultimate,
            "ok": is_ultimate
        }
    except Exception as e:
        return {"error": str(e)}


def check_nvidia_profile(profile_name: str) -> dict:
    """Check NVIDIA profile settings."""
    try:
        from abso.settings.nvidia.nvapi_drs import NVAPIDRS, DRSProfileManager

        # First check if profile exists and has apps
        mgr = DRSProfileManager()
        profiles = mgr.list_profiles()
        target = None
        for p in profiles:
            if p.get("name") == profile_name:
                target = p
                break

        if not target:
            return {"error": f"Profile '{profile_name}' not found"}

        result = {
            "profile_name": profile_name,
            "num_apps": target.get("num_apps", 0),
            "apps_bound": target.get("num_apps", 0) > 0,
            "settings": {}
        }

        # Try to get settings using context manager
        try:
            drs = NVAPIDRS()
            with drs:
                handle = drs.find_profile_by_name(profile_name)

                if not handle:
                    result["settings_error"] = "Could not find profile handle"
                    return result

                # Map known setting IDs to names (from DRSProfileManager.SETTING_IDS)
                setting_checks = {
                    0x00A879CF: ("vsync", 0, "OFF"),
                    0x00A879CE: ("low_latency_mode", 1, "ON"),
                    0x00A879E2: ("threaded_optimization", 2, "OFF"),
                }

                for setting_id, (name, expected, expected_meaning) in setting_checks.items():
                    try:
                        actual = drs.get_setting(handle, setting_id)
                        entry = {
                            "value": actual,
                            "expected": expected,
                            "expected_meaning": expected_meaning,
                            "ok": actual == expected
                        }
                        result["settings"][name] = entry
                    except Exception as e:
                        result["settings"][name] = {"error": str(e)}

        except Exception as e:
            result["settings_error"] = str(e)

        return result

    except ImportError as e:
        return {"error": f"Import error: {e}"}
    except Exception as e:
        return {"error": str(e)}


def verify_profile(profile_name: str = None) -> dict:
    """Run full verification and return results."""
    results = {
        "windows": check_windows_settings(),
        "power_plan": check_power_plan(),
    }

    if profile_name:
        results["nvidia_profile"] = check_nvidia_profile(profile_name)

    # Compute summary
    issues = []

    for key, check in results["windows"].items():
        if isinstance(check, dict) and "expected" in check:
            if check["expected"] != "profile_dependent":
                if check["value"] != check["expected"]:
                    issues.append(f"{check['description']}: got {check['value']}, expected {check['expected']}")

    if not results["power_plan"].get("ok"):
        issues.append("Power plan is not Ultimate Performance (current standard)")

    if profile_name and "nvidia_profile" in results:
        np = results["nvidia_profile"]
        if "error" in np:
            issues.append(f"NVIDIA: {np['error']}")
        elif not np.get("apps_bound"):
            issues.append(f"NVIDIA profile has no apps bound")
        elif "settings" in np:
            for name, data in np["settings"].items():
                if "ok" in data and not data["ok"]:
                    issues.append(f"NVIDIA {name}: got {data['value']}, expected {data['expected']}")

    results["summary"] = {
        "issues": issues,
        "all_ok": len(issues) == 0
    }

    return results


def main():
    """CLI entry point."""
    profile_name = None
    if len(sys.argv) > 1:
        profile_name = sys.argv[1]

    results = verify_profile(profile_name)
    print(json.dumps(results, indent=2))


if __name__ == "__main__":
    main()
