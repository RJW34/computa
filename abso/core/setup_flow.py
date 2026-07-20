"""Non-interactive setup engine behind the GUI installer.

Two entry points:

- ``build_setup_plan()``: read-only preflight — hardware summary, GPU vendor
  note, problematic Windows updates, detected games. The installer window
  shows this before the user commits to anything. Nothing is mutated.
- ``run_unattended_setup()``: executes exactly the actions the user toggled
  on, emitting one JSON object per line so the installer can narrate
  progress. Never applies a profile — installing changes no game or Windows
  settings; that happens later, from the tray, when the user chooses.
"""

from __future__ import annotations

import json
import logging
import os
import sys
from collections.abc import Callable
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any

from abso.core.app_paths import app_data_dir

logger = logging.getLogger(__name__)

Emit = Callable[[dict[str, Any]], None]

_VENDOR_NOTES = {
    "nvidia": "NVIDIA GPU — full driver tuning available.",
    "amd": "AMD Radeon — Radeon driver tuning available (Anti-Lag, ULPS, Enhanced Sync).",
}
_VENDOR_NOTE_FALLBACK = (
    "No vendor-specific GPU driver tuning for this GPU; Windows, power, and "
    "input optimizations still apply."
)


def _hardware_summary(hardware: dict[str, Any]) -> dict[str, Any]:
    summary: dict[str, Any] = {}
    gpu = hardware.get("gpu") or {}
    cpu = hardware.get("cpu") or {}
    ram = hardware.get("ram") or {}
    monitors = hardware.get("monitors") or []
    if gpu.get("name"):
        summary["gpu"] = gpu["name"]
    if cpu.get("name"):
        summary["cpu"] = cpu["name"]
    if ram.get("total_gb"):
        summary["ram_gb"] = ram["total_gb"]
    if monitors:
        # Lead with the fastest display — for a gaming tool that's the one
        # the user cares about, regardless of enumeration order.
        def _refresh(mon: dict[str, Any]) -> float:
            try:
                return float(mon.get("refresh_rate") or 0)
            except (TypeError, ValueError):
                return 0.0

        mon = max(monitors, key=_refresh)
        refresh = mon.get("refresh_rate")
        name = mon.get("name") or "Monitor"
        summary["monitor"] = f"{name} @ {refresh}Hz" if refresh else name
        summary["monitor_count"] = len(monitors)
    return summary


def _display_hdr_capable() -> bool | None:
    """Best-effort HDR capability probe. None means unknown."""
    try:
        from abso.settings.windows import WindowsSettingsHandler

        summary = WindowsSettingsHandler()._get_hdr_state_summary()
        if not summary.get("available"):
            return None
        return summary.get("hdr_capable_count", 0) > 0
    except Exception:
        return None


def _any_vrr_capable_monitor(hardware: dict[str, Any]) -> bool | None:
    """Whether any detected monitor looks VRR-capable. None means unknown."""
    monitors = hardware.get("monitors") or []
    if not monitors:
        return None
    capable_states = (True, "hardware", "likely")
    return any(mon.get("vrr_supported") in capable_states for mon in monitors)


def _build_game_catalog(detected_profile_ids: set[str]) -> list[dict[str, Any]]:
    """Group the profile manifest into survey-ready game entries.

    Desktop/Productivity is excluded: those profiles are always available
    and never survey-filtered.
    """
    from abso.profiles.catalog import get_profile_manifest

    groups: dict[str, dict[str, Any]] = {}
    for p in get_profile_manifest():
        if not p.get("tray_visible", True):
            continue
        group = p.get("tray_group") or p["id"]
        if group == "productivity":
            continue
        if group not in groups:
            groups[group] = {
                "key": group,
                "name": p.get("tray_group_name") or p.get("display_name") or group,
                "category": p.get("tray_category") or "Other",
                "detected": False,
            }
        if p["id"] in detected_profile_ids:
            groups[group]["detected"] = True
    return list(groups.values())


def build_setup_plan() -> dict[str, Any]:
    """Assemble the read-only preflight the installer shows before install."""
    from abso.__version__ import __version__
    from abso.utils.admin import is_admin

    plan: dict[str, Any] = {
        "app_version": __version__,
        "is_admin": bool(is_admin()),
        "hardware": {},
        "gpu_vendor": "unknown",
        "gpu_vendor_note": _VENDOR_NOTE_FALLBACK,
        "problematic_kbs": [],
        "detected_games": [],
        "game_catalog": [],
        "hdr_capable": None,
        "vrr_capable": None,
    }

    try:
        from abso.core.detector import HardwareDetector

        hardware = HardwareDetector().detect_all()
        plan["hardware"] = _hardware_summary(hardware)
        plan["vrr_capable"] = _any_vrr_capable_monitor(hardware)
        gpu_name = (hardware.get("gpu") or {}).get("name", "")
        if gpu_name:
            from abso.core.gpu_vendor import classify_gpu_name

            vendor = classify_gpu_name(gpu_name)
            vendor_key = getattr(vendor, "value", "unknown") or "unknown"
            plan["gpu_vendor"] = vendor_key
            plan["gpu_vendor_note"] = _VENDOR_NOTES.get(vendor_key, _VENDOR_NOTE_FALLBACK)
    except Exception as e:
        logger.warning(f"Setup plan hardware detection failed: {e}")

    plan["hdr_capable"] = _display_hdr_capable()

    try:
        from abso.core.kb_checker import check_problematic_kbs, get_installed_kbs

        plan["problematic_kbs"] = [
            {"kb_id": kb.kb_id, "title": kb.title, "affected": kb.affected}
            for kb in check_problematic_kbs(get_installed_kbs())
        ]
    except Exception as e:
        logger.warning(f"Setup plan KB check failed: {e}")

    detected_profile_ids: set[str] = set()
    try:
        from abso.core.game_detector import get_profile_suggestions

        suggestions = get_profile_suggestions()
        detected_profile_ids = set(suggestions.keys())
        plan["detected_games"] = [
            {
                "profile": profile_name,
                "games": list(dict.fromkeys(g.name for g in matched)),
            }
            for profile_name, matched in suggestions.items()
        ]
    except Exception as e:
        logger.warning(f"Setup plan game detection failed: {e}")

    try:
        plan["game_catalog"] = _build_game_catalog(detected_profile_ids)
    except Exception as e:
        logger.warning(f"Setup plan game catalog failed: {e}")

    return plan


@dataclass
class UnattendedOptions:
    """Which setup actions the user toggled on in the installer."""

    baseline: bool = True
    create_config: bool = True
    tray_autostart: bool = False
    remove_kbs: tuple[str, ...] = ()
    # Survey answers. ``games`` holds tray_group keys the user plays; an
    # empty tuple means the survey was skipped and nothing is filtered.
    games: tuple[str, ...] = field(default=())
    hdr: bool | None = None
    vrr: bool | None = None
    capture: bool | None = None


_STEP_LABELS = {
    "tray_assets": "Putting the tray helper's files in place",
    "config": "Creating your settings file",
    "baseline": "Saving a snapshot of your current settings",
    "windows_updates": "Removing a problematic Windows update",
    "preferences": "Tuning the tray to your games",
    "tray_autostart": "Setting the tray to start with Windows",
    "state": "Finishing up",
}


def _planned_steps(options: UnattendedOptions) -> list[str]:
    steps = ["tray_assets"]
    if options.create_config:
        steps.append("config")
    if options.baseline:
        steps.append("baseline")
    if options.remove_kbs:
        steps.append("windows_updates")
    if options.games:
        steps.append("preferences")
    if options.tray_autostart:
        steps.append("tray_autostart")
    steps.append("state")
    return steps


def _compute_hidden_profiles(
    games: tuple[str, ...],
    hdr: bool | None,
    vrr: bool | None,
    capture: bool | None,
) -> list[str]:
    """Derive the tray hiddenProfiles list from survey answers.

    Desktop/Productivity profiles are never hidden by game selection, but
    do respect the display-variant answers (an SDR-only user has no use
    for the Desktop HDR lane). ``None`` answers hide nothing.
    """
    from abso.profiles.catalog import get_profile_manifest

    selected = set(games)
    hidden: list[str] = []
    for p in get_profile_manifest():
        if not p.get("tray_visible", True):
            continue
        group = p.get("tray_group") or p["id"]
        if group != "productivity" and group not in selected:
            hidden.append(p["id"])
            continue
        if hdr is False and p.get("requires_hdr_display"):
            hidden.append(p["id"])
            continue
        if vrr is False and p.get("sync_mode") == "on":
            hidden.append(p["id"])
            continue
        if capture is False and "capture" in p["id"]:
            hidden.append(p["id"])
    return sorted(hidden)


def _tray_config_path() -> Path:
    """Path of the tray's per-machine config (honors redirected APPDATA)."""
    appdata = os.environ.get("APPDATA")
    root = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
    return root / "ABSO" / "tray-config.json"


def run_unattended_setup(
    options: UnattendedOptions,
    emit: Emit,
    *,
    data_dir: Path | None = None,
) -> dict[str, Any]:
    """Execute the toggled setup actions, streaming progress via ``emit``.

    Args:
        options: The user's installer toggles.
        emit: Called with one JSON-serializable dict per progress event.
        data_dir: Override for the app data directory (tests).

    Returns:
        The final ``done`` event payload.
    """
    if data_dir is None:
        from abso.core.setup_wizard import _get_data_dir

        data_dir = _get_data_dir()
    state_file = data_dir / ".abso_state.json"
    backups_dir = data_dir / "backups"

    steps = _planned_steps(options)
    emit({
        "event": "start",
        "steps": [{"id": s, "label": _STEP_LABELS[s]} for s in steps],
    })

    def step(step_id: str, status: str, detail: str | None = None) -> None:
        payload: dict[str, Any] = {"event": "step", "id": step_id, "status": status}
        if detail:
            payload["detail"] = detail
        emit(payload)

    success = True
    needs_reboot = False
    reboot_reasons: list[str] = []
    baseline_id: str | None = None
    summary: list[str] = []
    frozen = bool(getattr(sys, "frozen", False))
    tray_assets_ok = True

    # 1) Tray assets: a bare-exe install has no tray files on disk; deploy the
    # bundled copies beside the exe so startup registration survives reboots.
    step("tray_assets", "running")
    try:
        from abso.tray import deploy_tray_assets

        deployed = deploy_tray_assets()
        if deployed is None:
            step("tray_assets", "skipped", "Running from source; tray files already in place.")
        else:
            step("tray_assets", "ok", str(deployed))
    except Exception as e:
        tray_assets_ok = False
        success = False
        step("tray_assets", "error", str(e))

    # 2) Machine-local config in the install directory (never the cwd — a
    # friend runs the installer from Downloads).
    if options.create_config:
        step("config", "running")
        try:
            from abso.core.config import DEFAULT_CONFIG_NAME, ConfigManager

            config_path = app_data_dir(create=True) / DEFAULT_CONFIG_NAME
            manager = ConfigManager(config_path)
            if config_path.exists():
                step("config", "skipped", f"Already exists: {config_path}")
            else:
                manager.create_default()
                summary.append("Settings file created")
                step("config", "ok", str(config_path))
        except Exception as e:
            success = False
            step("config", "error", str(e))

    # 3) Baseline backup: the "get me back to before computa" anchor.
    if options.baseline:
        step("baseline", "running")
        try:
            from abso.core.backup import BackupManager

            backups_dir.mkdir(parents=True, exist_ok=True)
            baseline_id = BackupManager(backups_dir).create_backup(
                profile_id=None,
                backup_type="baseline",
            )
            summary.append(f"Safety snapshot saved ({baseline_id})")
            step("baseline", "ok", str(baseline_id))
        except Exception as e:
            success = False
            step("baseline", "error", str(e))

    # 4) Optional removal of known-problematic Windows updates.
    if options.remove_kbs:
        step("windows_updates", "running")
        try:
            from abso.core.kb_checker import uninstall_kb

            removed: list[str] = []
            failed: list[str] = []
            for kb_id in options.remove_kbs:
                if uninstall_kb(kb_id):
                    removed.append(kb_id)
                    needs_reboot = True
                    reboot_reasons.append(f"{kb_id} removal")
                else:
                    failed.append(kb_id)
            if removed:
                summary.append(f"Windows update removed: {', '.join(removed)}")
            if failed:
                success = False
                step("windows_updates", "error", f"Could not remove: {', '.join(failed)}")
            else:
                step("windows_updates", "ok", ", ".join(removed))
        except Exception as e:
            success = False
            step("windows_updates", "error", str(e))

    # 5) Survey preferences: tune the tray to the games/display the user
    # actually has, via the tray's per-machine hiddenProfiles curation.
    if options.games:
        step("preferences", "running")
        try:
            hidden = _compute_hidden_profiles(
                options.games, options.hdr, options.vrr, options.capture
            )
            config_path = _tray_config_path()
            config_path.parent.mkdir(parents=True, exist_ok=True)
            tray_config: dict[str, Any] = {}
            if config_path.exists():
                try:
                    loaded = json.loads(config_path.read_text(encoding="utf-8"))
                    if isinstance(loaded, dict):
                        tray_config = loaded
                except Exception:
                    tray_config = {}
            tray_config["hiddenProfiles"] = hidden
            tray_config["setupSurvey"] = {
                "games": list(options.games),
                "hdr": options.hdr,
                "vrr": options.vrr,
                "capture": options.capture,
                "collectedAt": datetime.now().isoformat(),
            }
            tmp = config_path.with_suffix(".tmp")
            tmp.write_text(json.dumps(tray_config, indent=2), encoding="utf-8")
            os.replace(tmp, config_path)
            summary.append(f"Tray tuned to your games ({len(options.games)} selected)")
            step("preferences", "ok", f"{len(hidden)} profile variants hidden")
        except Exception as e:
            success = False
            step("preferences", "error", str(e))

    # 6) Tray autostart — only with durable tray files in place.
    if options.tray_autostart:
        step("tray_autostart", "running")
        if frozen and not tray_assets_ok:
            success = False
            step(
                "tray_autostart",
                "error",
                "Tray files could not be set up; startup registration skipped.",
            )
        else:
            try:
                from abso.tray import install_startup

                install_startup()
                summary.append("Tray will start with Windows")
                step("tray_autostart", "ok")
            except Exception as e:
                success = False
                step("tray_autostart", "error", str(e))

    # 7) Record that setup ran without clobbering an existing profile state.
    step("state", "running")
    try:
        existing: dict[str, Any] = {}
        if state_file.exists():
            try:
                loaded = json.loads(state_file.read_text(encoding="utf-8"))
                if isinstance(loaded, dict):
                    existing = loaded
            except Exception:
                existing = {}

        state = {
            "current_profile": existing.get("current_profile"),
            "applied_at": existing.get("applied_at"),
            "reboot_pending": bool(existing.get("reboot_pending")) or needs_reboot,
            "reboot_reasons": list(existing.get("reboot_reasons") or []) + reboot_reasons,
            "setup_completed": True,
            "baseline_backup_id": baseline_id or existing.get("baseline_backup_id"),
        }
        from abso.core.setup_wizard import write_setup_state

        write_setup_state(state_file, state)
        step("state", "ok")
    except Exception as e:
        success = False
        step("state", "error", str(e))

    done = {
        "event": "done",
        "success": success,
        "needs_reboot": needs_reboot,
        "reboot_reasons": reboot_reasons,
        "baseline_backup_id": baseline_id,
        "summary": summary,
    }
    emit(done)
    return done
