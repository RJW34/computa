"""CLI entry point for ABSO."""

import json
import logging
import os
import re
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel

from abso.core.applier import ProfileApplier
from abso.core.auditor import ConfigurationAuditor
from abso.core.backup import BackupManager
from abso.core.detector import HardwareDetector
from abso.core.exceptions import BackupNotFoundError, ProfileLaunchError
from abso.core.launcher import launch_profile
from abso.core.transaction import ProfileTransactionManager
from abso.profiles.catalog import (
    get_profile_aliases,
    get_profile_manifest,
    resolve_profile_id,
)
from abso.utils.admin import is_admin
from abso.utils.atomic_io import atomic_write_json

console = Console()
logger = logging.getLogger(__name__)

# Paths - handle both development and PyInstaller bundled modes
def get_data_dir() -> Path:
    """Get the data directory for backups and reports.

    In development: uses project root
    When bundled: uses user's AppData/Local/AdaptiveBattleStationOptimizer
    """
    import sys

    # Check if running as PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running as bundled exe - use AppData
        app_data = Path.home() / "AppData" / "Local" / "AdaptiveBattleStationOptimizer"
        app_data.mkdir(parents=True, exist_ok=True)
        return app_data
    else:
        # Development mode - use project root
        return Path(__file__).parent.parent

ROOT_DIR = get_data_dir()
BACKUPS_DIR = ROOT_DIR / "backups"
REPORTS_DIR = ROOT_DIR / "reports"
STATE_FILE = ROOT_DIR / ".abso_state.json"


def _local_appdata_state_file() -> Path:
    """Return the packaged-app state-file location used by tray/GUI clients."""
    local_appdata = os.environ.get("LOCALAPPDATA")
    if local_appdata:
        app_data = Path(local_appdata)
    else:
        app_data = Path.home() / "AppData" / "Local"
    return app_data / "AdaptiveBattleStationOptimizer" / ".abso_state.json"


def _state_file_targets() -> list[Path]:
    """Return state file paths that should stay in sync.

    In packaged mode ROOT_DIR already points at LocalAppData, so there is only
    one target. In development mode, mirror the repo state into LocalAppData so
    the PowerShell tray and backend CLI see the same active profile.
    """
    targets = [STATE_FILE]

    try:
        default_dev_state = Path(__file__).resolve().parent.parent / ".abso_state.json"
        is_default_dev_state = (
            not getattr(sys, "frozen", False)
            and STATE_FILE.resolve() == default_dev_state.resolve()
        )
        if is_default_dev_state:
            local_state = _local_appdata_state_file()
            if local_state.resolve() != STATE_FILE.resolve():
                targets.append(local_state)
    except OSError:
        pass

    return targets


def _sanitize_state_snapshot(state: dict[str, Any]) -> dict[str, Any]:
    """Return the public active-profile state shape with canonical profile id."""
    return {
        "current_profile": resolve_profile_id(state.get("current_profile")),
        "applied_at": state.get("applied_at"),
        "reboot_pending": bool(state.get("reboot_pending", False)),
        "reboot_reasons": list(state.get("reboot_reasons") or []),
    }


def _read_state_file(path: Path) -> dict[str, Any] | None:
    """Read and sanitize one state-file candidate."""
    if not path.exists():
        return None
    try:
        state = json.loads(path.read_text(encoding="utf-8"))
    except (json.JSONDecodeError, OSError):
        return None
    if not isinstance(state, dict):
        return None
    return _sanitize_state_snapshot(state)


def _state_sort_value(path: Path, state: dict[str, Any]) -> float:
    """Return a comparable freshness value for a state candidate."""
    applied_at = state.get("applied_at")
    if applied_at:
        try:
            return datetime.fromisoformat(str(applied_at).replace("Z", "+00:00")).timestamp()
        except (TypeError, ValueError, OSError):
            pass
    try:
        return path.stat().st_mtime
    except OSError:
        return 0.0


def _write_state_snapshot(state: dict[str, Any]) -> None:
    """Write active-profile state to primary and mirrored targets."""
    targets = _state_file_targets()
    atomic_write_json(targets[0], state, indent=2)

    for target in targets[1:]:
        try:
            atomic_write_json(target, state, indent=2)
        except OSError as exc:
            logger.warning("Failed to mirror state file to %s: %s", target, exc)


def get_current_profile() -> str | None:
    """Get the currently active profile from state file."""
    return _read_state_snapshot().get("current_profile")


def set_current_profile(
    profile_name: str,
    requires_reboot: bool = False,
    reboot_reasons: list[str] | None = None,
) -> None:
    """Save the current profile to state file (atomic write)."""
    canonical_profile_name = resolve_profile_id(profile_name) or profile_name
    state: dict[str, Any] = {
        "current_profile": canonical_profile_name,
        "applied_at": datetime.now().isoformat(),
        "reboot_pending": requires_reboot,
        "reboot_reasons": reboot_reasons or [],
    }
    _write_state_snapshot(state)


def clear_reboot_pending() -> None:
    """Clear the reboot-pending flag from state file."""
    if not any(path.exists() for path in _state_file_targets()):
        return
    try:
        state = _read_state_snapshot()
        state["reboot_pending"] = False
        state["reboot_reasons"] = []
        _write_state_snapshot(state)
    except (json.JSONDecodeError, OSError):
        pass


def clear_current_profile() -> None:
    """Clear the active profile state file after a restore/reset."""
    for index, path in enumerate(_state_file_targets()):
        try:
            if path.exists():
                path.unlink()
        except OSError as exc:
            if index == 0:
                raise
            logger.warning("Failed to remove mirrored state file %s: %s", path, exc)


def json_serial(obj: Any) -> Any:
    """JSON serializer for objects not serializable by default."""
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, Path):
        return str(obj)
    if hasattr(obj, "__dict__"):
        return obj.__dict__
    raise TypeError(f"Type {type(obj)} not serializable")


def output_json(data: Any, success: bool = True, error: str | None = None) -> None:
    """Output data as JSON to stdout."""
    if error:
        result = {"success": False, "error": error, "data": None}
    else:
        result = {"success": success, "data": data}
    click.echo(json.dumps(result, default=json_serial, indent=2))


def json_error(message: str, exit_code: int = 1) -> None:
    """Output an error as JSON and exit."""
    output_json(None, success=False, error=message)
    sys.exit(exit_code)


def _describe_restore_summary(
    summary: dict[str, Any], *, blocking_only: bool = False
) -> str | None:
    """Build a concise message for an incomplete restore summary.

    When ``blocking_only`` is True, non-blocking entries (handlers whose
    ``restore_guarantee`` is ``"none"`` or ``"ephemeral"``) are ignored —
    they do not represent broken promises and so should not be reported
    as failures to the user.
    """
    incomplete = summary.get("failed_components", []) + summary.get("skipped_components", [])
    if blocking_only:
        incomplete = [item for item in incomplete if bool(item.get("blocking", True))]
    if not incomplete:
        return None

    handlers = ", ".join(item.get("handler", "unknown") for item in incomplete)
    return f"Restore incomplete for: {handlers}"


def _read_state_snapshot() -> dict[str, Any]:
    """Read the persisted active-profile state file."""
    default_state = {
        "current_profile": None,
        "applied_at": None,
        "reboot_pending": False,
        "reboot_reasons": [],
    }
    candidates: list[tuple[float, dict[str, Any]]] = []
    for path in _state_file_targets():
        state = _read_state_file(path)
        if state is None:
            continue
        candidates.append((_state_sort_value(path, state), state))

    if not candidates:
        return default_state

    candidates.sort(key=lambda item: item[0], reverse=True)
    return candidates[0][1]


def _append_unique_message(messages: list[str], message: str | None) -> None:
    """Append a non-empty message if it has not already been recorded."""
    if not message:
        return

    normalized = message.strip()
    if not normalized or normalized in messages:
        return

    messages.append(normalized)


def _collect_apply_warnings(
    tx: ProfileTransactionManager | Any,
    result: Any | None,
) -> list[str]:
    """Collect user-facing warnings from apply result + transaction state."""
    warnings: list[str] = []

    if result:
        for warning in result.warnings or []:
            _append_unique_message(warnings, warning)

    transaction = getattr(tx, "checkpoints", None) or []
    for checkpoint in transaction:
        if getattr(checkpoint, "status", "") == "warn":
            _append_unique_message(warnings, getattr(checkpoint, "message", None))

    compliance_report = getattr(tx, "compliance_report", None)
    if compliance_report:
        for issue in compliance_report.warnings:
            detail = f"{issue.message}: {issue.details}" if issue.details else issue.message
            _append_unique_message(warnings, detail)

    return warnings


def _collect_apply_notices(result: Any | None) -> list[str]:
    """Collect non-warning informational notices from an apply result."""
    notices: list[str] = []
    if not result:
        return notices

    for notice in getattr(result, "notices", []) or []:
        _append_unique_message(notices, notice)

    return notices


_SOFT_APPLY_WARNING_PATTERNS = (
    re.compile(r"mixed refresh rates detected", re.IGNORECASE),
    re.compile(r"\b\d+\s+monitors detected\b", re.IGNORECASE),
    re.compile(r"mpo glitch risk", re.IGNORECASE),
    re.compile(
        r"baseline restore incomplete for known non-restorable handlers",
        re.IGNORECASE,
    ),
)


def _is_soft_apply_warning(message: str | None) -> bool:
    """Return True when a warning is an environmental caution, not an action blocker."""
    if not message:
        return False

    normalized = message.strip()
    if not normalized:
        return False

    return any(pattern.search(normalized) for pattern in _SOFT_APPLY_WARNING_PATTERNS)


def _determine_apply_summary_level(
    warnings: list[str],
    notices: list[str],
) -> str:
    """Classify apply UX severity for tray/gui surfaces."""
    if warnings:
        if all(_is_soft_apply_warning(warning) for warning in warnings):
            return "caution"
        return "warning"

    if notices:
        return "notice"

    return "success"


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="ABSO")
@click.pass_context
def cli(ctx) -> None:
    """ABSO - Windows Gaming Optimization Tool.

    Detect hardware, audit configuration, and apply game-specific
    optimization profiles for competitive gaming.

    Run without arguments to launch interactive mode.
    """
    # If no command is given, check for first run or launch interactive
    if ctx.invoked_subcommand is None:
        from abso.core.setup_wizard import is_first_run

        if is_first_run():
            from abso.core.setup_wizard import SetupWizard
            SetupWizard().run()
        else:
            from abso.interactive import run_interactive
            run_interactive()


@cli.command()
def interactive() -> None:
    """Launch interactive menu mode (default when run without arguments)."""
    from abso.interactive import run_interactive
    run_interactive()


@cli.command()
def setup() -> None:
    """Run the first-time setup wizard.

    Walks through hardware detection, Windows update checks, system audit,
    game detection, and profile selection.
    """
    if not is_admin():
        console.print("[red]Setup wizard requires admin privileges.[/red]")
        console.print("Please run from an elevated (admin) terminal.")
        raise SystemExit(1)
    from abso.core.setup_wizard import SetupWizard
    SetupWizard().run()


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def detect(json_output: bool) -> None:
    """Detect and report gaming hardware."""
    if not json_output and not is_admin():
        console.print("[yellow]Warning: Running without admin privileges. Some detection may be limited.[/yellow]")

    detector = HardwareDetector()
    hardware = detector.detect_all()

    # Gather BIOS info for both JSON and Rich output
    bios_info = None
    try:
        from abso.core.bios_detector import BiosDetector
        bios_det = BiosDetector()
        bios_info = bios_det.detect_all()
    except Exception:
        pass  # BIOS detection is best-effort

    # CPU topology info
    cpu_topology = None
    cpu_data = hardware.get("cpu")
    if cpu_data:
        cpu_name = cpu_data.get("name", "").lower()
        core_count = cpu_data.get("cores", 0)
        thread_count = cpu_data.get("threads", 0)
        is_hybrid = False
        if "12th gen" in cpu_name or "13th gen" in cpu_name or "14th gen" in cpu_name:
            is_hybrid = True
        elif any(tag in cpu_name for tag in ["core ultra", "-12", "-13", "-14"]):
            if "intel" in cpu_name or "core" in cpu_name:
                is_hybrid = True
        if is_hybrid and core_count > 0 and thread_count > 0:
            e_cores = thread_count - core_count
            p_cores = core_count - e_cores
            if p_cores > 0 and e_cores >= 0:
                cpu_topology = {"type": "hybrid", "p_cores": p_cores, "e_cores": e_cores}
            else:
                cpu_topology = {"type": "hybrid"}
        elif core_count > 0:
            cpu_topology = {"type": "homogeneous"}

    # JSON output mode
    if json_output:
        # Flatten for GUI consumption
        output_data = {
            "system": hardware.get("system"),
            "gpu": hardware.get("gpu"),
            "cpu": hardware.get("cpu"),
            "cpu_topology": cpu_topology,
            "ram_gb": (hardware.get("ram") or {}).get("total_gb"),
            "monitors": hardware.get("monitors") or [],
            "is_admin": is_admin(),
            "bios": None,
        }
        if bios_info:
            output_data["bios"] = {
                "rebar_status": bios_info.rebar_status,
                "xmp_status": bios_info.memory_profile,
                "xmp_rated_mhz": bios_info.rated_speed_mhz,
                "xmp_current_mhz": bios_info.current_speed_mhz,
                "vbs_status": bios_info.vbs_status,
                "memory_integrity": bios_info.memory_integrity,
                "secure_boot": bios_info.secure_boot,
                "tpm_present": bios_info.tpm_present,
                "tpm_version": bios_info.tpm_version,
            }
        output_json(output_data)
        return

    # Rich console output
    console.print(Panel("Hardware Detection", style="bold blue"))

    # System info (manufacturer/model)
    console.print("\n[bold]System:[/bold]")
    if hardware.get("system"):
        sys_info = hardware["system"]
        manufacturer = sys_info.get("manufacturer") or "Unknown"
        model = sys_info.get("model") or "Unknown"

        if sys_info.get("is_prebuilt"):
            # Pre-built PC - show identified name or OEM branding
            prebuilt_name = sys_info.get("prebuilt_name")
            if prebuilt_name:
                console.print(f"  [green bold]{prebuilt_name}[/green bold]")
            else:
                # Fall back to SMBIOS data
                system_family = sys_info.get("system_family")
                if system_family and system_family.lower() not in ["default string", "to be filled"]:
                    console.print(f"  [green]{manufacturer} {system_family}[/green]")
                else:
                    console.print(f"  [green]{manufacturer} {model}[/green]")
            console.print("  Type: [cyan]Pre-built[/cyan]")
            # Show motherboard for reference
            mobo_model = sys_info.get("motherboard_model")
            if mobo_model:
                console.print(f"  Motherboard: [dim]{mobo_model}[/dim]")
        else:
            # Custom build - show motherboard info
            mobo_mfr = sys_info.get("motherboard_manufacturer") or manufacturer
            mobo_model = sys_info.get("motherboard_model") or model
            console.print(f"  Motherboard: {mobo_mfr}")
            console.print(f"  Model: {mobo_model}")
            console.print("  Type: [yellow]Custom Build[/yellow]")

        if sys_info.get("chassis_type"):
            console.print(f"  Chassis: {sys_info.get('chassis_type')}")
    else:
        console.print("  [red]Not detected[/red]")

    console.print("\n[bold]GPU:[/bold]")
    if hardware.get("gpu"):
        gpu = hardware["gpu"]
        console.print(f"  Name: {gpu.get('name', 'Unknown')}")
        console.print(f"  Driver: {gpu.get('driver_version', 'Unknown')}")
        console.print(f"  VRAM: {gpu.get('vram_mb', 'Unknown')} MB")
    else:
        console.print("  [red]Not detected[/red]")

    console.print("\n[bold]CPU:[/bold]")
    if hardware.get("cpu"):
        cpu = hardware["cpu"]
        console.print(f"  Name: {cpu.get('name', 'Unknown')}")
        console.print(f"  Cores: {cpu.get('cores', 'Unknown')}")
        console.print(f"  Threads: {cpu.get('threads', 'Unknown')}")
        # CPU topology: P-cores/E-cores for hybrid architectures
        cpu_name = cpu.get("name", "").lower()
        core_count = cpu.get("cores", 0)
        thread_count = cpu.get("threads", 0)
        is_hybrid = False
        if "12th gen" in cpu_name or "13th gen" in cpu_name or "14th gen" in cpu_name:
            is_hybrid = True
        elif any(tag in cpu_name for tag in ["core ultra", "-12", "-13", "-14"]):
            # Match i5-12600K, i7-13700K, i9-14900K style naming
            if "intel" in cpu_name or "core" in cpu_name:
                is_hybrid = True
        if is_hybrid and core_count > 0 and thread_count > 0:
            # Estimate P-cores and E-cores from thread/core ratio
            # P-cores are hyperthreaded (2 threads each), E-cores are not (1 thread each)
            # threads = p_cores * 2 + e_cores, cores = p_cores + e_cores
            e_cores = thread_count - core_count
            p_cores = core_count - e_cores
            if p_cores > 0 and e_cores >= 0:
                console.print(f"  Topology: [cyan]Hybrid[/cyan] ({p_cores}P + {e_cores}E)")
            else:
                console.print(f"  Topology: [cyan]Hybrid[/cyan]")
        elif core_count > 0:
            console.print(f"  Topology: [dim]Homogeneous[/dim]")
    else:
        console.print("  [red]Not detected[/red]")

    console.print("\n[bold]RAM:[/bold]")
    if hardware.get("ram"):
        ram = hardware["ram"]
        console.print(f"  Total: {ram.get('total_gb', 'Unknown')} GB")
    else:
        console.print("  [red]Not detected[/red]")

    console.print("\n[bold]Monitor(s):[/bold]")
    if hardware.get("monitors"):
        for i, monitor in enumerate(hardware["monitors"], 1):
            name = monitor.get('name', 'Unknown')
            primary = " [green](Primary)[/green]" if monitor.get('is_primary') else ""
            console.print(f"  [{i}] {name}{primary}")
            console.print(f"      Resolution: {monitor.get('resolution', 'Unknown')}")
            refresh_str = f"{monitor.get('refresh_rate', 'Unknown')} Hz"
            max_refresh = monitor.get('max_refresh_rate')
            max_capability = monitor.get('max_refresh_capability')
            if max_refresh:
                refresh_str += f" [yellow](Max @ res: {max_refresh} Hz)[/yellow]"
            elif max_capability:
                refresh_str += f" [yellow](Supports up to {max_capability} Hz)[/yellow]"
            console.print(f"      Refresh Rate: {refresh_str}")
            if monitor.get('adapter'):
                console.print(f"      Adapter: {monitor.get('adapter')}")

            # VRR/G-Sync status
            vrr = monitor.get('vrr_supported')
            vrr_type = monitor.get('vrr_type')
            vrr_range = monitor.get('vrr_range')

            if vrr is True:
                vrr_label = vrr_type.upper() if vrr_type else "VRR"
                vrr_str = f"[green]{vrr_label}[/green]"
                if vrr_range:
                    vrr_str += f" ({vrr_range})"
            elif vrr == "likely":
                vrr_str = "[yellow]Likely (high refresh)[/yellow]"
            else:
                vrr_str = "[dim]Unknown[/dim]"

            console.print(f"      G-Sync/VRR: {vrr_str}")
    else:
        console.print("  [red]Not detected[/red]")

    # BIOS/Firmware summary
    console.print("\n[bold]BIOS/Firmware:[/bold]")
    if bios_info:
        # ReBAR
        rebar_color = {"enabled": "green", "disabled": "yellow", "unknown": "dim"}.get(
            bios_info.rebar_status, "dim"
        )
        console.print(f"  ReBAR: [{rebar_color}]{bios_info.rebar_status}[/{rebar_color}]")

        # XMP/EXPO
        if bios_info.memory_profile == "xmp_enabled":
            xmp_str = "[green]Enabled[/green]"
            if bios_info.current_speed_mhz:
                xmp_str += f" ({bios_info.current_speed_mhz} MHz)"
        elif bios_info.memory_profile == "xmp_disabled_likely":
            xmp_str = f"[yellow]Likely disabled[/yellow]"
            if bios_info.current_speed_mhz and bios_info.rated_speed_mhz:
                xmp_str += (
                    f" ({bios_info.current_speed_mhz} MHz, "
                    f"rated {bios_info.rated_speed_mhz} MHz)"
                )
        else:
            xmp_str = "[dim]Unknown[/dim]"
        console.print(f"  XMP/EXPO: {xmp_str}")

        # VBS/Memory Integrity
        vbs_color = "yellow" if bios_info.vbs_status == "enabled" else "green"
        console.print(f"  VBS: [{vbs_color}]{bios_info.vbs_status}[/{vbs_color}]")
        mi_color = "yellow" if bios_info.memory_integrity == "enabled" else "green"
        console.print(f"  Memory Integrity: [{mi_color}]{bios_info.memory_integrity}[/{mi_color}]")
    else:
        console.print("  [dim]Detection unavailable[/dim]")


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed explanations")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def audit(verbose: bool, json_output: bool) -> None:
    """Audit current system configuration for gaming optimization."""
    if not is_admin():
        if json_output:
            json_error("Admin privileges required for full audit")
        console.print("[red]Error: Admin privileges required for full audit.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    auditor = ConfigurationAuditor()
    issues = auditor.audit_all()

    # JSON output mode
    if json_output:
        issues_data = [
            {
                "title": issue.title,
                "severity": issue.severity,
                "current_value": issue.current_value,
                "optimal_value": issue.optimal_value,
                "explanation": issue.explanation,
                "category": getattr(issue, "category", "general"),
            }
            for issue in issues
        ]
        output_json(issues_data)
        return

    # Rich console output
    console.print(Panel("Configuration Audit", style="bold blue"))

    if not issues:
        console.print("[green]No issues were detected by the current audit scope.[/green]")
        return

    console.print(f"\n[yellow]Found {len(issues)} issue(s):[/yellow]\n")

    for issue in issues:
        severity_color = {
            "critical": "red",
            "warning": "yellow",
            "info": "blue"
        }.get(issue.severity, "white")

        console.print(f"[{severity_color}][{issue.severity.upper()}][/{severity_color}] {issue.title}")
        console.print(f"  Current: {issue.current_value}")
        console.print(f"  Optimal: {issue.optimal_value}")

        if verbose and issue.explanation:
            console.print(f"  [dim]{issue.explanation}[/dim]")

        console.print()


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def profiles(json_output: bool) -> None:
    """List available game optimization profiles."""
    available_profiles = get_profile_manifest()

    if json_output:
        output_json(available_profiles)
        return

    console.print(Panel("Available Profiles", style="bold blue"))

    for profile in available_profiles:
        console.print(f"\n[bold cyan]{profile['id']}[/bold cyan]")
        console.print(f"  {profile['display_name']}")
        console.print(f"  [dim]Focus: {profile['description']}[/dim]")


@cli.command("profile-aliases")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def profile_aliases(json_output: bool) -> None:
    """List retired -> canonical profile id aliases (for tray/GUI normalization)."""
    aliases = get_profile_aliases()

    if json_output:
        output_json(aliases)
        return

    console.print(Panel("Profile Aliases", style="bold blue"))
    if not aliases:
        console.print("[dim]No aliases registered.[/dim]")
        return
    for legacy, canonical in sorted(aliases.items()):
        console.print(f"  [cyan]{legacy}[/cyan] -> [green]{canonical}[/green]")


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def state(json_output: bool) -> None:
    """Show the persisted active-profile state."""
    snapshot = _read_state_snapshot()

    if json_output:
        output_json(snapshot)
        return

    console.print(Panel("Current State", style="bold blue"))
    current_profile = snapshot["current_profile"] or "(none)"
    console.print(f"Current profile: {current_profile}")
    if snapshot["applied_at"]:
        console.print(f"Applied at: {snapshot['applied_at']}")
    console.print(f"Reboot pending: {'yes' if snapshot['reboot_pending'] else 'no'}")
    if snapshot["reboot_reasons"]:
        console.print("Reboot reasons:")
        for reason in snapshot["reboot_reasons"]:
            console.print(f"  - {reason}")


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def games(json_output: bool) -> None:
    """Detect installed games and suggest matching profiles."""
    from abso.core.game_detector import detect_installed_games, get_profile_suggestions

    detected_games = detect_installed_games()

    if json_output:
        games_data = [
            {
                "name": game.name,
                "platform": game.platform,
                "executable": game.executable,
                "install_path": str(game.install_path),
            }
            for game in detected_games
        ]
        suggestions = get_profile_suggestions()
        suggestions_data = {
            profile: [g.name for g in matched]
            for profile, matched in suggestions.items()
        }
        output_json({"games": games_data, "suggestions": suggestions_data})
        return

    console.print(Panel("Game Detection", style="bold blue"))
    console.print("[dim]Scanning for installed games...[/dim]\n")

    if not detected_games:
        console.print("[yellow]No supported games detected.[/yellow]")
        console.print("\nSupported games:")
        console.print("  - Super Smash Bros. Melee (Slippi)")
        console.print("  - Rivals of Aether 2")
        console.print("  - Diablo IV")
        console.print("  - Fortnite")
        console.print("  - Marvel Rivals")
        return

    console.print(f"[green]Found {len(detected_games)} game(s):[/green]\n")

    for game in detected_games:
        platform_icon = {
            "steam": "[blue]Steam[/blue]",
            "epic": "[dim]Epic[/dim]",
            "battle_net": "[cyan]Battle.net[/cyan]",
            "standalone": "[yellow]Standalone[/yellow]",
        }.get(game.platform, game.platform)

        console.print(f"[bold]{game.name}[/bold]")
        console.print(f"  Platform: {platform_icon}")
        console.print(f"  Executable: {game.executable}")
        console.print(f"  Path: [dim]{game.install_path}[/dim]")
        console.print()

    # Show profile suggestions
    suggestions = get_profile_suggestions()
    if suggestions:
        console.print("[bold cyan]Suggested profiles:[/bold cyan]")
        for profile_name, matched_games in suggestions.items():
            game_names = ", ".join(g.name for g in matched_games)
            console.print(f"  [green]{profile_name}[/green] -> {game_names}")
        console.print("\nRun [bold]abso apply <profile>[/bold] to optimize.")


@cli.command()
@click.argument("profile_name")
@click.option("--no-backup", is_flag=True, help="Skip automatic backup (not recommended)")
@click.option("--benchmark", is_flag=True, help="Capture before/after frame times (requires PresentMon)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def apply(profile_name: str, no_backup: bool, benchmark: bool, json_output: bool) -> None:
    """Apply a game optimization profile.

    PROFILE_NAME is the profile to apply (e.g., slippi-melee, rivals2-online, diablo4).
    """
    profile_name = resolve_profile_id(profile_name) or profile_name
    if not is_admin():
        if json_output:
            json_error("Admin privileges required to apply profiles")
        console.print("[red]Error: Admin privileges required to apply profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    if not json_output:
        console.print(Panel(f"Applying Profile: {profile_name}", style="bold blue"))
        if no_backup:
            console.print("[yellow]Warning: Skipping backup as requested.[/yellow]\n")
        else:
            console.print("[yellow]Creating backup before applying changes...[/yellow]")

    # --- Benchmark: capture baseline before apply ---
    benchmark_baseline = None
    benchmark_exe = None
    if benchmark:
        try:
            from abso.core.benchmark import FrameTimeBenchmark, PresentMonNotFoundError

            bench = FrameTimeBenchmark()
            profile_class = ProfileApplier.PROFILES.get(profile_name)
            if profile_class:
                for exe in profile_class().executable_hints:
                    # Check if game is running
                    check = subprocess.run(
                        ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/NH"],
                        capture_output=True, text=True, timeout=5,
                    )
                    if exe.lower() in check.stdout.lower():
                        benchmark_exe = exe
                        break

            if benchmark_exe:
                if not json_output:
                    console.print(f"[cyan]Capturing 30s baseline for {benchmark_exe}...[/cyan]")
                baseline_capture = bench.capture(benchmark_exe, duration=30)
                benchmark_baseline = bench.analyze(baseline_capture)
            elif not json_output:
                console.print("[dim]Game not running — skipping benchmark baseline[/dim]")
        except PresentMonNotFoundError:
            if not json_output:
                console.print("[dim]PresentMon not found — skipping benchmark[/dim]")
            benchmark = False
        except Exception as e:
            if not json_output:
                console.print(f"[dim]Benchmark baseline failed: {e}[/dim]")
            benchmark_baseline = None

    try:
        tx_manager = ProfileTransactionManager(BACKUPS_DIR)
        tx = tx_manager.execute(profile_id=profile_name, create_backup=not no_backup)
        result = tx.apply_result
        apply_warnings = _collect_apply_warnings(tx, result)
        apply_notices = _collect_apply_notices(result)
        apply_summary_level = _determine_apply_summary_level(apply_warnings, apply_notices)

        if json_output:
            if tx.success and result and result.success:
                set_current_profile(
                    profile_name,
                    requires_reboot=result.requires_reboot,
                    reboot_reasons=result.reboot_reasons,
                )
            applied_settings = result.applied_settings if result else []
            failed_settings = result.failed_settings if result else []
            output_json({
                "success": tx.success,
                "profile": profile_name,
                "backup_id": tx.backup_id,
                "requires_reboot": result.requires_reboot if result else False,
                "in_game_settings": result.in_game_settings if result else False,
                "error": tx.error if not tx.success else None,
                "applied_settings": applied_settings,
                "failed_settings": failed_settings,
                "warnings": apply_warnings,
                "notices": apply_notices,
                "summary_level": apply_summary_level,
                "capabilities": (
                    result.capability_report.to_dict()
                    if result and result.capability_report
                    else None
                ),
                "results": [
                    {"handler": h, "status": "success"} for h in applied_settings
                ] + [
                    {"handler": f.split(":")[0].strip(), "status": "failed", "error": f}
                    for f in failed_settings
                ],
                "transaction": tx.to_dict(),
                "compliance": tx.compliance_report.to_dict() if tx.compliance_report else None,
            }, success=tx.success)
            return

        if tx.backup_id and not no_backup:
            console.print(f"[green]Backup created: {tx.backup_id}[/green]\n")

        if tx.success and result and result.success:
            set_current_profile(
                profile_name,
                requires_reboot=result.requires_reboot,
                reboot_reasons=result.reboot_reasons,
            )
            if apply_summary_level == "warning":
                console.print(f"\n[yellow]Profile '{profile_name}' committed with warnings.[/yellow]")
            elif apply_summary_level == "caution":
                console.print(f"\n[green]Profile '{profile_name}' applied with cautions.[/green]")
            elif apply_summary_level == "notice":
                console.print(f"\n[green]Profile '{profile_name}' applied with notices.[/green]")
            else:
                console.print(
                    f"\n[green]Profile '{profile_name}' apply completed.[/green] "
                    f"[dim]Run 'abso verify {profile_name}' to confirm handler state.[/dim]"
                )

            if result.requires_reboot and result.reboot_reasons:
                console.print("[yellow]Note: The following changes require a reboot to take effect:[/yellow]")
                for reason in result.reboot_reasons:
                    console.print(f"  [yellow]- {reason}[/yellow]")
                console.print(f"[dim]Run 'abso verify {profile_name}' to check if reboot is still needed.[/dim]")
            elif result.requires_reboot:
                console.print("[yellow]Note: Some changes may require a reboot to take effect.[/yellow]")
                console.print(f"[dim]Run 'abso verify {profile_name}' to check if reboot is still needed.[/dim]")

            warning_prefix = "Caution" if apply_summary_level == "caution" else "Warning"
            for warning in apply_warnings:
                console.print(f"[yellow]{warning_prefix}: {warning}[/yellow]")
            for notice in apply_notices:
                console.print(f"[cyan]Note: {notice}[/cyan]")

            if result.in_game_settings:
                # Actually generate the report file
                REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                applier = tx_manager.applier
                report_path = applier.generate_report(profile_name, REPORTS_DIR)
                console.print(f"\n[cyan]In-game settings saved to: {report_path}[/cyan]")

            # --- Benchmark: capture after apply and compare ---
            if benchmark and benchmark_baseline and benchmark_exe:
                try:
                    console.print(f"\n[cyan]Capturing 30s post-apply for {benchmark_exe}...[/cyan]")
                    after_capture = bench.capture(benchmark_exe, duration=30)
                    after_analysis = bench.analyze(after_capture)
                    comparison = bench.compare(benchmark_baseline, after_analysis)

                    from rich.table import Table

                    table = Table(title="Benchmark Comparison (Before → After)")
                    table.add_column("Metric", style="bold")
                    table.add_column("Before", justify="right")
                    table.add_column("After", justify="right")
                    table.add_column("Delta", justify="right")

                    def _fmt_delta(val: float, higher_is_better: bool = True) -> str:
                        if val > 0:
                            color = "green" if higher_is_better else "red"
                            return f"[{color}]+{val:.1f}[/{color}]"
                        elif val < 0:
                            color = "red" if higher_is_better else "green"
                            return f"[{color}]{val:.1f}[/{color}]"
                        return "0"

                    b, a = comparison.before, comparison.after
                    table.add_row("Avg FPS", f"{b.avg_fps:.1f}", f"{a.avg_fps:.1f}",
                                  _fmt_delta(a.avg_fps - b.avg_fps, True))
                    table.add_row("1% Low", f"{b.fps_1_low:.1f}", f"{a.fps_1_low:.1f}",
                                  _fmt_delta(a.fps_1_low - b.fps_1_low, True))
                    table.add_row("0.1% Low", f"{b.fps_01_low:.1f}", f"{a.fps_01_low:.1f}",
                                  _fmt_delta(a.fps_01_low - b.fps_01_low, True))
                    table.add_row("Avg Frame Time", f"{b.avg_frametime_ms:.2f}ms", f"{a.avg_frametime_ms:.2f}ms",
                                  _fmt_delta(a.avg_frametime_ms - b.avg_frametime_ms, False))
                    table.add_row("P99 Frame Time", f"{b.p99_frametime_ms:.2f}ms", f"{a.p99_frametime_ms:.2f}ms",
                                  _fmt_delta(a.p99_frametime_ms - b.p99_frametime_ms, False))
                    table.add_row("Stdev", f"{b.stdev_frametime_ms:.2f}ms", f"{a.stdev_frametime_ms:.2f}ms",
                                  _fmt_delta(a.stdev_frametime_ms - b.stdev_frametime_ms, False))

                    console.print(table)
                except Exception as e:
                    console.print(f"[dim]Post-apply benchmark failed: {e}[/dim]")
        else:
            err = tx.error or (result.error if result else "Unknown transaction error")
            console.print(f"\n[red]Failed to apply profile: {err}[/red]")
            if tx.rollback_performed and tx.backup_id:
                console.print(
                    f"[yellow]Automatic rollback completed from backup {tx.backup_id}.[/yellow]"
                )
            sys.exit(1)

    except ValueError as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        if json_output:
            json_error(f"Unexpected apply failure: {e}")
        console.print(f"[red]Unexpected apply failure: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("profile_name")
@click.argument("launch_args", nargs=-1)
@click.option(
    "--launch-path",
    type=click.Path(path_type=Path, dir_okay=False, file_okay=True),
    default=None,
    help="Explicit executable path override instead of auto-detecting an installed game",
)
@click.option("--no-backup", is_flag=True, help="Skip automatic backup before apply")
@click.option("--no-wait", is_flag=True, help="Return immediately after launching instead of waiting for exit")
@click.option(
    "--restore-on-exit",
    is_flag=True,
    help="Restore the pre-launch backup after the launched process exits (requires backup + waiting)",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def launch(
    profile_name: str,
    launch_args: tuple[str, ...],
    launch_path: Path | None,
    no_backup: bool,
    no_wait: bool,
    restore_on_exit: bool,
    json_output: bool,
) -> None:
    """Apply a profile, launch its game, and optionally restore on exit."""
    profile_name = resolve_profile_id(profile_name) or profile_name
    if not is_admin():
        if json_output:
            json_error("Admin privileges required to launch profiles")
        console.print("[red]Error: Admin privileges required to launch profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    if not json_output:
        console.print(Panel(f"Launching With Profile: {profile_name}", style="bold blue"))

    try:
        launch_result = launch_profile(
            profile_id=profile_name,
            backup_dir=BACKUPS_DIR,
            create_backup=not no_backup,
            wait=not no_wait,
            restore_on_exit=restore_on_exit,
            launch_path=launch_path,
            launch_args=list(launch_args),
        )
    except ProfileLaunchError as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)
    except Exception as e:
        if json_output:
            json_error(f"Unexpected launch failure: {e}")
        console.print(f"[red]Unexpected launch failure: {e}[/red]")
        sys.exit(1)

    tx = launch_result.transaction
    apply_result = tx.apply_result
    if tx.success and apply_result and apply_result.success:
        set_current_profile(
            profile_name,
            requires_reboot=apply_result.requires_reboot,
            reboot_reasons=apply_result.reboot_reasons,
        )
        if launch_result.restored:
            clear_current_profile()

    if json_output:
        output_json(launch_result.to_dict(), success=launch_result.success, error=launch_result.error)
        return

    if tx.backup_id and not no_backup:
        console.print(f"[green]Backup created: {tx.backup_id}[/green]")

    if launch_result.target:
        console.print(f"[cyan]Target:[/cyan] {launch_result.target.executable_path}")
    if launch_args:
        console.print(f"[dim]Args:[/dim] {' '.join(launch_args)}")

    if launch_result.launched:
        console.print(f"[green]Process launched[/green] (PID {launch_result.process_id})")
        if no_wait:
            console.print("[dim]Not waiting for process exit.[/dim]")
        elif launch_result.exit_code is not None:
            console.print(f"[dim]Process exit code:[/dim] {launch_result.exit_code}")
    else:
        console.print(f"[yellow]Launch did not start a process.[/yellow]")

    for warning in launch_result.warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")

    if launch_result.restored:
        console.print(f"[green]Restored pre-launch backup: {launch_result.restore_backup_id}[/green]")
    elif launch_result.restore_attempted and launch_result.restore_error:
        console.print(f"[red]Restore failed: {launch_result.restore_error}[/red]")

    if launch_result.success:
        console.print("[green]Launch flow completed.[/green]")
        return

    if launch_result.error:
        console.print(f"[red]Launch flow failed: {launch_result.error}[/red]")
    else:
        console.print("[red]Launch flow failed.[/red]")

    if tx.success and apply_result and apply_result.success and not launch_result.restored:
        console.print("[yellow]Profile settings may still be active because apply succeeded before launch failed.[/yellow]")

    sys.exit(1)


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def reapply(json_output: bool) -> None:
    """Re-apply the current profile without creating a backup.

    Use this when Windows reverts settings (e.g., after display mode change).
    Faster than 'apply' since it skips backup creation.
    """
    if not is_admin():
        if json_output:
            json_error("Admin privileges required to apply profiles")
        console.print("[red]Error: Admin privileges required to apply profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    current_profile = get_current_profile()
    if not current_profile:
        if json_output:
            json_error("No profile has been applied yet. Use 'abso apply <profile>' first.")
        console.print("[red]Error: No profile has been applied yet.[/red]")
        console.print("Use [bold]abso apply <profile>[/bold] first.")
        sys.exit(1)

    if not json_output:
        console.print(Panel(f"Re-applying Profile: {current_profile}", style="bold blue"))
        console.print("[dim]Skipping backup (use 'apply' for full backup)[/dim]\n")

    applier = ProfileApplier()

    try:
        result = applier.apply_profile(current_profile)
        summary_level = _determine_apply_summary_level(result.warnings, result.notices)

        if json_output:
            output_json({
                "success": result.success,
                "profile": current_profile,
                "warnings": result.warnings,
                "notices": result.notices,
                "summary_level": summary_level,
                "error": result.error if not result.success else None,
            })
            return

        if result.success:
            if summary_level == "warning":
                console.print(f"\n[yellow]Profile '{current_profile}' re-applied with warnings.[/yellow]")
            elif summary_level == "caution":
                console.print(f"\n[green]Profile '{current_profile}' re-applied with cautions.[/green]")
            elif summary_level == "notice":
                console.print(f"\n[green]Profile '{current_profile}' re-applied with notices.[/green]")
            else:
                console.print(
                    f"\n[green]Profile '{current_profile}' re-apply completed.[/green] "
                    f"[dim]Run 'abso verify {current_profile}' to confirm handler state.[/dim]"
                )
            warning_prefix = "Caution" if summary_level == "caution" else "Warning"
            for warning in result.warnings:
                console.print(f"[yellow]{warning_prefix}: {warning}[/yellow]")
            for notice in result.notices:
                console.print(f"[cyan]Note: {notice}[/cyan]")
        else:
            console.print(f"\n[red]Failed to re-apply profile: {result.error}[/red]")
            sys.exit(1)

    except ValueError as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("profile_name")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def verify(profile_name: str, json_output: bool) -> None:
    """Verify that a profile's verifiable settings are active.

    PROFILE_NAME is the profile to verify (e.g., slippi-melee, rivals2-online, diablo4).

    This checks every handler that implements verify_active and helps confirm
    the machine is actually in the intended end state after apply.
    """
    profile_name = resolve_profile_id(profile_name) or profile_name
    applier = ProfileApplier()

    try:
        result = applier.verify_profile(profile_name)

        if json_output:
            output_json(result)
            return

        console.print(Panel(f"Verifying Profile: {profile_name}", style="bold blue"))

        all_active = result.get("all_active", False)
        handlers = result.get("handlers", {})

        if all_active:
            console.print("\n[green]All verifiable settings are active.[/green]")
            console.print("[dim]No outstanding verification mismatches were detected.[/dim]")
        else:
            console.print("\n[yellow]Some settings are not yet in the intended state:[/yellow]")

        for handler_name, handler_result in handlers.items():
            if not handler_result.get("settings"):
                continue

            console.print(f"\n[bold]{handler_name}:[/bold]")
            for setting_name, setting_info in handler_result.get("settings", {}).items():
                status = "[green]Active[/green]" if setting_info.get("active") else "[yellow]Mismatch[/yellow]"
                console.print(f"  {setting_name}: {status}")
                console.print(f"    Target: {setting_info.get('target')}, Current: {setting_info.get('current')}")

    except ValueError as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("backup_id", default="latest")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def restore(backup_id: str, json_output: bool) -> None:
    """Restore system settings from a backup.

    BACKUP_ID is the backup timestamp or 'latest' for most recent.
    """
    if not is_admin():
        if json_output:
            json_error("Admin privileges required to restore settings")
        console.print("[red]Error: Admin privileges required to restore settings.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    if not json_output:
        console.print(Panel(f"Restoring Backup: {backup_id}", style="bold blue"))

    backup_manager = BackupManager(BACKUPS_DIR)

    try:
        restore_summary = backup_manager.restore_backup(backup_id).to_dict()
        # Only surface an error when a handler ABSO actually promises to
        # restore failed. Skips from ``restore_guarantee="none"`` /
        # ``"ephemeral"`` handlers (e.g. timer resolution, which reverts on
        # process exit) are non-blocking and must not fail the restore.
        if restore_summary.get("has_blocking_issues"):
            restore_error = _describe_restore_summary(
                restore_summary, blocking_only=True
            )
            if json_output:
                output_json({
                    "success": False,
                    "backup_id": backup_id,
                    "message": restore_error,
                    "restore_summary": restore_summary,
                }, success=False)
                return
            console.print(f"[red]{restore_error}[/red]")
            for item in restore_summary["failed_components"] + restore_summary["skipped_components"]:
                if not bool(item.get("blocking", True)):
                    continue
                console.print(f"  [red]- {item['handler']}: {item.get('detail', item['reason'])}[/red]")
            sys.exit(1)
        clear_current_profile()
        if json_output:
            output_json({
                "success": True,
                "backup_id": backup_id,
                "message": "Restore completed for fully restorable handlers",
                "restore_summary": restore_summary,
            })
            return
        console.print(
            f"\n[green]Backup '{backup_id}' restore completed for fully restorable handlers.[/green]"
        )
        console.print("[yellow]Note: Some changes may require a reboot to take effect.[/yellow]")
        console.print("[dim]If restoring to previously-active settings, no reboot is needed.[/dim]")
    except FileNotFoundError:
        if json_output:
            json_error(f"Backup '{backup_id}' not found")
        console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
        sys.exit(1)
    except Exception as e:
        if json_output:
            json_error(f"Error restoring backup: {e}")
        console.print(f"[red]Error restoring backup: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def backups(json_output: bool) -> None:
    """List available backups."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_manager = BackupManager(BACKUPS_DIR)

    backup_list = backup_manager.list_backups()

    if json_output:
        # list_backups() returns dicts with id, created_at, components
        output_json(backup_list)
        return

    console.print(Panel("Available Backups", style="bold blue"))

    if not backup_list:
        console.print("[yellow]No backups found.[/yellow]")
        console.print("\nBackups are created automatically when you apply a profile.")
        return

    for backup in backup_list:
        console.print(f"\n[bold cyan]{backup['id']}[/bold cyan]")
        console.print(f"  Created: {backup['created_at']}")
        if backup.get("components"):
            components = ", ".join(backup["components"])
            console.print(f"  [dim]Components: {components}[/dim]")


@cli.command("backup-create")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def backup_create(json_output: bool) -> None:
    """Create a manual backup."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_manager = BackupManager(BACKUPS_DIR)

    backup_id = backup_manager.create_backup(
        profile_id=get_current_profile(),
        backup_type="manual",
    )
    backup = next(
        (item for item in backup_manager.list_backups() if item["id"] == backup_id),
        {"id": backup_id, "created_at": datetime.now().isoformat(), "components": []},
    )

    if json_output:
        output_json(backup)
        return

    console.print(f"[green]Created manual backup: {backup_id}[/green]")


@cli.command("backup-delete")
@click.argument("backup_id")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def backup_delete(backup_id: str, json_output: bool) -> None:
    """Delete a backup by ID."""
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_manager = BackupManager(BACKUPS_DIR)

    try:
        backup_manager.delete_backup(backup_id)
    except BackupNotFoundError:
        if json_output:
            json_error(f"Backup '{backup_id}' not found")
        console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
        sys.exit(1)

    if json_output:
        output_json({"success": True, "backup_id": backup_id})
        return

    console.print(f"[green]Deleted backup: {backup_id}[/green]")


@cli.command()
@click.option("--keep", "-k", type=int, default=20, help="Number of backups to keep (default: 20)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def prune(keep: int, json_output: bool) -> None:
    """Remove old backups, keeping the most recent N.

    By default keeps the 20 most recent backups and deletes the rest.
    """
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
    backup_manager = BackupManager(BACKUPS_DIR)

    existing = backup_manager.list_backups()

    if json_output:
        deleted = backup_manager.prune(max_backups=keep)
        output_json({
            "kept": keep,
            "deleted_count": len(deleted),
            "deleted": deleted,
            "remaining": len(existing) - len(deleted),
        })
        return

    if len(existing) <= keep:
        console.print(f"[green]Nothing to prune. {len(existing)} backup(s) exist, limit is {keep}.[/green]")
        return

    console.print(f"[yellow]Found {len(existing)} backups, pruning to keep {keep}...[/yellow]")
    deleted = backup_manager.prune(max_backups=keep)

    if deleted:
        console.print(f"[green]Deleted {len(deleted)} old backup(s).[/green]")
        for bid in deleted:
            console.print(f"  [dim]- {bid}[/dim]")
    else:
        console.print("[green]No backups needed pruning.[/green]")

    remaining = len(existing) - len(deleted)
    console.print(f"\n[bold]{remaining}[/bold] backup(s) remaining.")


@cli.command()
@click.option("--resolution", "-r", type=float, default=0.5,
              help="Timer resolution in milliseconds (default: 0.5)")
@click.option("--keep-alive", "-k", is_flag=True,
              help="Keep running to maintain timer resolution")
@click.option("--status", is_flag=True, help="Show current timer status only")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def timer(resolution: float, keep_alive: bool, status: bool, json_output: bool) -> None:
    """Set system timer resolution for gaming.

    Timer resolution affects frame pacing and scheduling precision.
    Lower values (0.5ms) improve consistency. This is NOT input latency.

    Note: Timer resolution only persists while this process runs.
    Use --keep-alive to maintain the resolution continuously.
    """
    from abso.settings.timer import TimerSettingsHandler

    handler = TimerSettingsHandler()
    current = handler.detect()

    if not current.get("available"):
        if json_output:
            json_error("Timer resolution API not available")
        console.print("[red]Error: Timer resolution API not available.[/red]")
        sys.exit(1)

    # Status-only mode
    if status or (json_output and not keep_alive):
        if json_output:
            output_json({
                "current": current.get("current_resolution_ms"),
                "minimum": current.get("maximum_resolution_ms"),  # "maximum" is actually minimum possible
                "maximum": current.get("minimum_resolution_ms", 15.625),  # Default is actually max
            })
            return
        console.print(Panel("Timer Resolution", style="bold blue"))
        console.print(f"Current: {current.get('current_resolution_ms', 'Unknown'):.3f}ms")
        console.print(f"Minimum: {current.get('maximum_resolution_ms', 'Unknown'):.3f}ms")
        return

    if not json_output:
        console.print(Panel("Timer Resolution", style="bold blue"))
        console.print(f"Current: {current.get('current_resolution_ms', 'Unknown'):.3f}ms")
        console.print(f"Minimum: {current.get('maximum_resolution_ms', 'Unknown'):.3f}ms")
        console.print()

    # Set the resolution
    result = handler.apply({"resolution_ms": resolution})

    if result.get("success"):
        if json_output:
            output_json({"success": True, "resolution_ms": resolution})
            return

        console.print(f"[green]Timer resolution set to {resolution}ms[/green]")

        if keep_alive:
            console.print("\n[yellow]Keep-alive mode active. Press Ctrl+C to exit.[/yellow]")
            console.print("[dim]Timer resolution will revert when this process exits.[/dim]")
            try:
                import time
                while True:
                    time.sleep(60)  # Sleep and check periodically
            except KeyboardInterrupt:
                console.print("\n[yellow]Releasing timer resolution...[/yellow]")
                handler.release_resolution()
                console.print("[green]Timer resolution released.[/green]")
        else:
            console.print("[dim]Note: Resolution will revert when this process exits.[/dim]")
            console.print("[dim]Use --keep-alive to maintain continuously.[/dim]")
    else:
        if json_output:
            json_error(f"Failed to set timer resolution: {result.get('error')}")
        console.print(f"[red]Failed to set timer resolution: {result.get('error')}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("profile_name")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def report(profile_name: str, json_output: bool) -> None:
    """Generate in-game settings report for a profile.

    PROFILE_NAME is the profile to generate report for.
    """
    profile_name = resolve_profile_id(profile_name) or profile_name
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    applier = ProfileApplier()

    try:
        report_path = applier.generate_report(profile_name, REPORTS_DIR)

        if json_output:
            # Read the report content
            content = ""
            if report_path.exists():
                content = report_path.read_text(encoding="utf-8")
            output_json({"path": str(report_path), "content": content})
            return

        console.print(f"[green]Report generated: {report_path}[/green]")
    except ValueError as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--install-startup", is_flag=True, help="Add tray to Windows startup")
@click.option("--uninstall-startup", is_flag=True, help="Remove tray from Windows startup")
@click.option("--startup-status", is_flag=True, help="Show tray startup registration status")
def tray(install_startup: bool, uninstall_startup: bool, startup_status: bool) -> None:
    """Launch the A.B.S.O. system tray application.

    The tray provides quick access to profile switching via left-click menu.
    It automatically pauses during gaming and restarts when the game exits.
    """
    import abso.tray as tray_module

    if install_startup:
        tray_module.install_startup(uninstall=False)
    elif uninstall_startup:
        tray_module.install_startup(uninstall=True)
    elif startup_status:
        status = tray_module.get_startup_status()
        mode = status.get("mode", "none")
        installed = status.get("installed", False)
        console.print(f"[bold]Startup Installed:[/bold] {'Yes' if installed else 'No'}")
        console.print(f"[bold]Mode:[/bold] {mode}")
        if status.get("task_installed"):
            console.print(f"[bold]Task:[/bold] {status.get('task_name')}")
            console.print(
                f"[bold]Highest Privileges:[/bold] {'Yes' if status.get('task_highest', False) else 'No'}"
            )
        if status.get("shortcut_installed"):
            console.print(f"[bold]Shortcut:[/bold] {status.get('shortcut_path')}")
    else:
        tray_module.start_tray()


@cli.command()
@click.option("--bundle", is_flag=True, help="Write diagnostics bundle ZIP")
@click.option(
    "--output-dir",
    type=click.Path(path_type=Path, file_okay=False, dir_okay=True),
    default=None,
    help="Output directory for diagnostics bundle",
)
@click.option(
    "--start-tray-if-missing",
    is_flag=True,
    help="Attempt to start tray if runtime check shows it is missing",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def health(
    bundle: bool,
    output_dir: Path | None,
    start_tray_if_missing: bool,
    json_output: bool,
) -> None:
    """Generate diagnostics and optional support bundle."""
    from abso.core.health import build_health_report, write_health_bundle
    import abso.tray as tray_module

    report = build_health_report(
        root_dir=ROOT_DIR,
        backups_dir=BACKUPS_DIR,
        state_file=STATE_FILE,
    )

    if start_tray_if_missing:
        report["tray_start_attempt"] = tray_module.ensure_tray_running(start_if_missing=True)

    if bundle:
        target_dir = output_dir or (REPORTS_DIR / "diagnostics")
        bundle_path = write_health_bundle(report, target_dir)
        report["bundle_path"] = str(bundle_path)

    if json_output:
        output_json(report)
        return

    console.print(Panel("ABSO Health Report", style="bold blue"))
    summary = report.get("summary", {})
    console.print(
        f"Checks: [green]{summary.get('ok', 0)} ok[/green], "
        f"[yellow]{summary.get('warning', 0)} warning[/yellow], "
        f"[red]{summary.get('error', 0)} error[/red]"
    )
    current_profile = report.get("current_profile") or "(none)"
    console.print(f"Current profile: {current_profile}")

    if report.get("bundle_path"):
        console.print(f"[green]Bundle:[/green] {report['bundle_path']}")

    checks = report.get("checks", {})
    for check_name in ["tray_startup", "tray_runtime", "state_file", "backups", "config", "fallback"]:
        check = checks.get(check_name, {})
        status = check.get("status", "error")
        color = {"ok": "green", "warning": "yellow", "error": "red"}.get(status, "white")
        console.print(f"  [{color}]{check_name}: {status}[/{color}]")


@cli.command()
@click.option("--init", is_flag=True, help="Create default configuration file")
@click.option("--show", is_flag=True, help="Show current configuration")
def config(init: bool, show: bool) -> None:
    """Manage ABSO configuration file.

    Configuration is stored in abso.yaml in the current directory.
    Use profile_overrides to customize settings per game profile.
    """
    from abso.core.config import ConfigManager

    config_manager = ConfigManager()

    if init:
        if config_manager.config_path.exists():
            console.print(f"[yellow]Configuration already exists: {config_manager.config_path}[/yellow]")
            console.print("Delete it first to create a new one.")
            return

        config_manager.create_default()
        console.print(f"[green]Created default config: {config_manager.config_path}[/green]")
        console.print("\nEdit this file to:")
        console.print("  - Override profile settings (profile_overrides)")
        console.print("  - Disable specific handlers (disabled_handlers)")
        console.print("  - Set logging verbosity (log_level)")
        return

    if show:
        if not config_manager.config_path.exists():
            console.print("[yellow]No configuration file found.[/yellow]")
            console.print("Run [bold]abso config --init[/bold] to create one.")
            return

        console.print(Panel("Current Configuration", style="bold blue"))
        cfg = config_manager.config
        console.print(f"  backup_dir: {cfg.backup_dir}")
        console.print(f"  auto_backup: {cfg.auto_backup}")
        console.print(f"  log_level: {cfg.log_level}")
        console.print(f"  default_profile: {cfg.default_profile or '(none)'}")
        console.print(f"  confirm_destructive: {cfg.confirm_destructive}")

        if cfg.disabled_handlers:
            console.print(f"  disabled_handlers: {', '.join(cfg.disabled_handlers)}")
        else:
            console.print("  disabled_handlers: (none)")

        if cfg.profile_overrides:
            console.print("\n[bold]Profile Overrides:[/bold]")
            for profile_id, overrides in cfg.profile_overrides.items():
                console.print(f"  [cyan]{profile_id}[/cyan]:")
                for attr in ["nvidia", "windows", "network", "power", "timer", "mouse"]:
                    override_val = getattr(overrides, attr, {})
                    if override_val:
                        console.print(f"    {attr}: {override_val}")
        return

    # Default: show help
    console.print("Use [bold]abso config --init[/bold] to create a configuration file.")
    console.print("Use [bold]abso config --show[/bold] to view current settings.")


@cli.command()
@click.argument("process_name")
@click.option("--duration", default=30, help="Capture duration in seconds")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def benchmark(process_name: str, duration: int, json_output: bool):
    """Capture frame times using PresentMon for a running game."""
    from dataclasses import asdict

    from rich.table import Table

    from abso.core.benchmark import (
        FrameTimeBenchmark,
        PresentMonNotFoundError,
    )

    bench = FrameTimeBenchmark()

    try:
        if not json_output:
            console.print(Panel(f"Benchmarking: {process_name}", style="bold blue"))
            console.print(f"[dim]Capturing frame times for {duration}s...[/dim]\n")

        capture = bench.capture(process_name, duration_seconds=duration)
        analysis = bench.analyze(capture)

        if json_output:
            output_json(asdict(analysis))
            return

        table = Table(title="Frame Time Analysis", show_header=True, border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Value", justify="right")

        table.add_row("Avg FPS", f"{analysis.avg_fps:.2f}")
        table.add_row("1% Low FPS", f"{analysis.p1_low_fps:.2f}")
        table.add_row("0.1% Low FPS", f"{analysis.p01_low_fps:.2f}")
        table.add_row("Avg Frame Time", f"{analysis.avg_frame_time_ms:.3f} ms")
        table.add_row("P95 Frame Time", f"{analysis.p95_frame_time_ms:.3f} ms")
        table.add_row("P99 Frame Time", f"{analysis.p99_frame_time_ms:.3f} ms")
        table.add_row("Stdev", f"{analysis.frame_time_stdev:.3f} ms")
        table.add_row("Dropped Frames", str(analysis.dropped_frame_count))
        table.add_row("Total Frames", str(analysis.total_frames))

        console.print(table)
        console.print(f"\n[dim]CSV saved: {capture.csv_path}[/dim]")

    except PresentMonNotFoundError:
        if json_output:
            json_error(
                "PresentMon is not installed. "
                "Download from https://github.com/GameTechDev/PresentMon/releases "
                "and add to PATH or install to C:\\Program Files\\PresentMon\\."
            )
        console.print("[red]Error: PresentMon is not installed.[/red]")
        console.print("\nInstall PresentMon to use frame-time benchmarking:")
        console.print("  1. Download from [cyan]https://github.com/GameTechDev/PresentMon/releases[/cyan]")
        console.print("  2. Install to [bold]C:\\Program Files\\PresentMon\\[/bold] or add to PATH")
        console.print("  3. Run this command again with the game running")
        sys.exit(1)
    except Exception as e:
        if json_output:
            json_error(f"Benchmark failed: {e}")
        console.print(f"[red]Benchmark failed: {e}[/red]")
        sys.exit(1)


@cli.command("benchmark-compare")
@click.argument("before_csv")
@click.argument("after_csv")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def benchmark_compare(before_csv: str, after_csv: str, json_output: bool):
    """Compare two benchmark captures (before/after profile)."""
    from dataclasses import asdict

    from rich.table import Table

    from abso.core.benchmark import CaptureResult, FrameTimeBenchmark

    bench = FrameTimeBenchmark()

    # Load and parse both CSV files
    before_path = Path(before_csv)
    after_path = Path(after_csv)

    for label, path in [("Before", before_path), ("After", after_path)]:
        if not path.is_file():
            if json_output:
                json_error(f"{label} CSV not found: {path}")
            console.print(f"[red]Error: {label} CSV not found: {path}[/red]")
            sys.exit(1)

    try:
        before_capture = CaptureResult(
            raw_data=bench._parse_csv(before_path, "before"),
            process_name="before",
            duration_seconds=0,
            csv_path=before_path,
            timestamp=datetime.now(),
        )
        after_capture = CaptureResult(
            raw_data=bench._parse_csv(after_path, "after"),
            process_name="after",
            duration_seconds=0,
            csv_path=after_path,
            timestamp=datetime.now(),
        )

        before_analysis = bench.analyze(before_capture)
        after_analysis = bench.analyze(after_capture)
        comparison = bench.compare(before_analysis, after_analysis)

        if json_output:
            deltas_data = {
                name: asdict(delta) for name, delta in comparison.deltas.items()
            }
            output_json({
                "before": asdict(comparison.before),
                "after": asdict(comparison.after),
                "deltas": deltas_data,
            })
            return

        console.print(Panel("Benchmark Comparison", style="bold blue"))

        table = Table(title="Before vs After", show_header=True, border_style="cyan")
        table.add_column("Metric", style="bold")
        table.add_column("Before", justify="right")
        table.add_column("After", justify="right")
        table.add_column("Delta", justify="right")
        table.add_column("", justify="center")  # Improvement indicator

        display_metrics = [
            ("Avg FPS", "avg_fps", ".2f"),
            ("1% Low FPS", "p1_low_fps", ".2f"),
            ("0.1% Low FPS", "p01_low_fps", ".2f"),
            ("Avg Frame Time (ms)", "avg_frame_time_ms", ".3f"),
            ("P95 Frame Time (ms)", "p95_frame_time_ms", ".3f"),
            ("P99 Frame Time (ms)", "p99_frame_time_ms", ".3f"),
            ("Stdev (ms)", "frame_time_stdev", ".3f"),
            ("Dropped Frames", "dropped_frame_count", ".0f"),
            ("Total Frames", "total_frames", ".0f"),
        ]

        for label, key, fmt in display_metrics:
            delta = comparison.deltas.get(key)
            if delta is None:
                continue

            before_str = f"{delta.before:{fmt}}"
            after_str = f"{delta.after:{fmt}}"

            # Format delta with sign and percentage
            sign = "+" if delta.absolute > 0 else ""
            delta_str = f"{sign}{delta.absolute:{fmt}}"
            if delta.percentage != float("inf"):
                delta_str += f" ({sign}{delta.percentage:.1f}%)"

            if delta.improved:
                indicator = "[green]+++[/green]"
                delta_str = f"[green]{delta_str}[/green]"
            elif delta.absolute == 0:
                indicator = "[dim]---[/dim]"
                delta_str = f"[dim]{delta_str}[/dim]"
            else:
                indicator = "[red]---[/red]"
                delta_str = f"[red]{delta_str}[/red]"

            table.add_row(label, before_str, after_str, delta_str, indicator)

        console.print(table)

    except Exception as e:
        if json_output:
            json_error(f"Comparison failed: {e}")
        console.print(f"[red]Comparison failed: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def bios(json_output: bool):
    """Detect BIOS/firmware settings relevant to gaming."""
    from abso.core.bios_detector import BiosDetector

    detector = BiosDetector()

    try:
        info = detector.detect_all()
        has_nvidia = False
        try:
            hw_detector = HardwareDetector()
            gpu = hw_detector.detect_gpu()
            if gpu and "nvidia" in (gpu.get("name", "") or "").lower():
                has_nvidia = True
        except Exception:
            pass  # GPU detection is best-effort for recommendation context

        recommendations = detector.get_recommendations(info, has_nvidia_gpu=has_nvidia)

        if json_output:
            output_json({
                "rebar_status": info.rebar_status,
                "memory_profile": info.memory_profile,
                "rated_speed_mhz": info.rated_speed_mhz,
                "current_speed_mhz": info.current_speed_mhz,
                "vbs_status": info.vbs_status,
                "memory_integrity": info.memory_integrity,
                "secure_boot": info.secure_boot,
                "tpm_present": info.tpm_present,
                "tpm_version": info.tpm_version,
                "recommendations": [
                    {
                        "title": rec.title,
                        "explanation": rec.explanation,
                        "impact": rec.impact,
                        "current_value": rec.current_value,
                        "recommended_value": rec.recommended_value,
                    }
                    for rec in recommendations
                ],
            })
            return

        console.print(Panel("BIOS/Firmware Detection", style="bold blue"))

        # Detection results
        rebar_color = {"enabled": "green", "disabled": "yellow", "unknown": "dim"}.get(
            info.rebar_status, "dim"
        )
        console.print(f"  Resizable BAR: [{rebar_color}]{info.rebar_status}[/{rebar_color}]")

        if info.memory_profile == "xmp_enabled":
            xmp_str = "[green]Enabled[/green]"
            if info.current_speed_mhz:
                xmp_str += f" ({info.current_speed_mhz} MHz)"
        elif info.memory_profile == "xmp_disabled_likely":
            xmp_str = "[yellow]Likely disabled[/yellow]"
            if info.current_speed_mhz and info.rated_speed_mhz:
                xmp_str += (
                    f" ({info.current_speed_mhz} MHz, "
                    f"rated {info.rated_speed_mhz} MHz)"
                )
        else:
            xmp_str = "[dim]Unknown[/dim]"
        console.print(f"  XMP/EXPO: {xmp_str}")

        vbs_color = "yellow" if info.vbs_status == "enabled" else "green"
        console.print(f"  VBS: [{vbs_color}]{info.vbs_status}[/{vbs_color}]")

        mi_color = "yellow" if info.memory_integrity == "enabled" else "green"
        console.print(f"  Memory Integrity: [{mi_color}]{info.memory_integrity}[/{mi_color}]")

        sb_color = {"enabled": "green", "disabled": "yellow", "unknown": "dim"}.get(
            info.secure_boot, "dim"
        )
        console.print(f"  Secure Boot: [{sb_color}]{info.secure_boot}[/{sb_color}]")

        if info.tpm_present:
            tpm_ver = info.tpm_version or "Unknown version"
            console.print(f"  TPM: [green]Present[/green] (v{tpm_ver})")
        else:
            console.print(f"  TPM: [dim]Not detected[/dim]")

        # Recommendations
        if recommendations:
            console.print(f"\n[bold]Recommendations ({len(recommendations)}):[/bold]\n")
            for rec in recommendations:
                impact_color = {
                    "high": "red",
                    "medium": "yellow",
                    "low": "blue",
                }.get(rec.impact, "white")

                console.print(
                    f"  [{impact_color}][{rec.impact.upper()}][/{impact_color}] {rec.title}"
                )
                console.print(f"    Current: {rec.current_value}")
                console.print(f"    Recommended: {rec.recommended_value}")
                console.print(f"    [dim]{rec.explanation}[/dim]")
                console.print()
        else:
            console.print(
                "\n[green]No BIOS/firmware recommendations -- your settings look good![/green]"
            )

    except Exception as e:
        if json_output:
            json_error(f"BIOS detection failed: {e}")
        console.print(f"[red]BIOS detection failed: {e}[/red]")
        sys.exit(1)
    finally:
        detector.cleanup()


@cli.command("profile-create")
@click.argument("profile_id")
@click.option("--game", required=True, help="Display name for the game")
@click.option("--exe", required=True, multiple=True, help="Game executable name(s)")
@click.option(
    "--base",
    type=click.Choice(["competitive_fps", "reflex_shooter", "emulator", "browser", "balanced"]),
    default="balanced",
    help="Base template to inherit from",
)
@click.option("--category", default="Other", help="Tray category (Fighting, Shooter, ARPG, etc.)")
def profile_create(
    profile_id: str,
    game: str,
    exe: tuple[str, ...],
    base: str,
    category: str,
) -> None:
    """Create a new user profile YAML template.

    Generates a starter YAML in ~/.abso/profiles/ that you can customize.

    Example: abso profile-create my-game --game "My Game" --exe MyGame.exe --base reflex_shooter
    """
    profiles_dir = Path.home() / ".abso" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    output_path = profiles_dir / f"{profile_id}.yaml"

    if output_path.exists():
        console.print(f"[red]Profile already exists: {output_path}[/red]")
        sys.exit(1)

    # Build YAML content
    exe_list = "\n".join(f"  - {e}" for e in exe)
    yaml_content = f"""# ABSO User Profile: {game}
# Created by: abso profile-create
# Documentation: https://github.com/your-repo/abso/docs/profiles.md

profile_id: {profile_id}
display_name: "{game}"
description: "Custom optimization profile for {game}"
optimization_target: minimum_latency
executable_hints:
{exe_list}

# Base template — inherits sensible defaults
# Options: competitive_fps, reflex_shooter, emulator, browser, balanced
base: {base}

# Profile metadata (optional)
# metadata:
#   is_online_profile: false
#   graphics_api: dx12
#   is_sdr_only: true

# Settings overrides — only include handlers you want to customize
# Full list: WindowsSettingsHandler, NvidiaSettingsHandler, PowerSettingsHandler,
#            RegistrySettingsHandler, NetworkSettingsHandler, MouseSettingsHandler,
#            GraphicsSettingsHandler, ServicesSettingsHandler, ProcessPriorityHandler,
#            ColorProfileSettingsHandler
settings:
  NvidiaSettingsHandler:
    preset: {_base_to_preset(base)}
  WindowsSettingsHandler:
    max_refresh_rate: true

# Tray app appearance
tray_category: {category}
tray_subtitle: "Custom | {game}"
sync_mode: off

# In-game settings recommendations (shown after profile apply)
# in_game_settings:
#   - category: Video
#     setting: V-Sync
#     value: "Off"
#     reason: "Driver handles sync"
"""
    output_path.write_text(yaml_content, encoding="utf-8")
    console.print(f"[green]Profile created: {output_path}[/green]")
    console.print(f"Edit the YAML to customize settings, then restart the tray or run [bold]abso profiles[/bold] to verify.")


def _base_to_preset(base: str) -> str:
    """Map base template name to a sensible default NVIDIA preset."""
    return {
        "competitive_fps": "no_sync_fighting_game",
        "reflex_shooter": "reflex_game",
        "emulator": "no_sync_fighting_game",
        "browser": "vrr_optimal",
        "balanced": "vrr_optimal",
    }.get(base, "vrr_optimal")


@cli.command("memory-clear")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def memory_clear(json_output: bool) -> None:
    """Purge the Windows standby list (ISLC equivalent).

    Clears cached memory pages that can cause stutters during long gaming sessions.
    Requires admin elevation.
    """
    if not is_admin():
        if json_output:
            json_error("Admin privileges required")
        console.print("[red]Error: Admin privileges required.[/red]")
        sys.exit(1)

    try:
        from abso.settings.standby_list import StandbyListHandler

        handler = StandbyListHandler()
        before = handler.detect()

        if not json_output:
            console.print(
                f"[dim]Memory before: {before['available_mb']}MB available "
                f"({before['memory_load_percent']}% load)[/dim]"
            )
            console.print("[cyan]Purging standby list...[/cyan]")

        success = handler.clear_standby_list()
        after = handler.detect()

        if json_output:
            output_json({
                "success": success,
                "before_available_mb": before["available_mb"],
                "after_available_mb": after["available_mb"],
                "freed_mb": after["available_mb"] - before["available_mb"],
            })
        elif success:
            freed = after["available_mb"] - before["available_mb"]
            console.print(
                f"[green]Standby list purged. Freed ~{freed}MB "
                f"({after['available_mb']}MB now available)[/green]"
            )
        else:
            console.print("[red]Failed to purge standby list (privilege escalation may have failed)[/red]")
    except Exception as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option("--tier", type=click.IntRange(1, 3), required=True, help="Debloat tier (1=safe, 2=moderate, 3=aggressive)")
@click.option("--dry-run", is_flag=True, help="Show what would be changed without applying")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def debloat(tier: int, dry_run: bool, json_output: bool) -> None:
    """Apply Windows debloat and privacy tweaks.

    Tier 1: Safe telemetry/privacy tweaks (always reversible).
    Tier 2: Moderate tweaks including background app control.
    Tier 3: Aggressive — removes bloatware appx packages (partially irreversible).
    """
    if not is_admin():
        if json_output:
            json_error("Admin privileges required")
        console.print("[red]Error: Admin privileges required.[/red]")
        sys.exit(1)

    try:
        from abso.settings.debloat import DebloatHandler

        handler = DebloatHandler(tier=tier)

        if dry_run:
            issues = handler.audit()
            if json_output:
                output_json({"tier": tier, "issues": [
                    {"title": i.title, "severity": i.severity, "current": i.current_value,
                     "optimal": i.optimal_value} for i in issues
                ]})
            else:
                console.print(Panel(f"Debloat Tier {tier} — Dry Run ({len(issues)} items)", style="bold yellow"))
                for issue in issues:
                    console.print(f"  [yellow]{issue.title}[/yellow]: {issue.current_value} → {issue.optimal_value}")
            return

        if not json_output:
            console.print(Panel(f"Applying Debloat Tier {tier}", style="bold blue"))
            if tier == 3:
                console.print("[red]WARNING: Tier 3 removes appx packages. This is partially irreversible.[/red]")

        result = handler.apply({"debloat_tier": tier})

        if json_output:
            output_json(result)
        elif result.get("success"):
            console.print(f"[green]Debloat tier {tier} apply completed.[/green]")
            if result.get("applied"):
                for item in result["applied"]:
                    console.print(f"  [green]✓[/green] {item}")
        else:
            console.print(f"[red]Debloat failed: {result.get('error')}[/red]")
            sys.exit(1)

    except Exception as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command("cpu-balance")
@click.option("--pid", type=int, required=True, help="Game process ID to protect")
@click.option("--system-threshold", type=int, default=85, help="System CPU % to trigger intervention")
@click.option("--process-threshold", type=int, default=20, help="Per-process CPU % threshold")
@click.option("--poll-interval", type=int, default=1000, help="Poll interval in ms")
def cpu_balance(pid: int, system_threshold: int, process_threshold: int, poll_interval: int) -> None:
    """Run real-time CPU priority balancer for a game session.

    Monitors CPU usage and temporarily lowers background process priority
    when the game is being starved. Exits when the game process exits.

    Typically launched by the tray app, not run manually.
    """
    from abso.core.cpu_balancer import CpuBalancer, CpuBalancerConfig

    config = CpuBalancerConfig(
        system_cpu_threshold=system_threshold,
        process_cpu_threshold=process_threshold,
        poll_interval_ms=poll_interval,
    )
    balancer = CpuBalancer(pid, config)

    import signal

    def _shutdown(signum, frame):
        balancer.stop()

    signal.signal(signal.SIGTERM, _shutdown)
    signal.signal(signal.SIGINT, _shutdown)

    balancer.run()


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
