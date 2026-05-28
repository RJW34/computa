"""CLI entry point for ABSO."""

import json
import logging
import subprocess
import sys
from datetime import datetime
from pathlib import Path
from typing import Any

import click
from rich.console import Console
from rich.panel import Panel

from abso.core import state_reconcile, state_store
from abso.core.app_paths import app_data_dir
from abso.core.applier import ProfileApplier
from abso.core.apply_feedback import (
    append_unique_message,
    collect_apply_notices,
    collect_apply_warnings,
    describe_restore_summary,
    determine_apply_summary_level,
)
from abso.core.apply_hooks import (
    run_post_apply_display_reset,
    run_post_apply_sweep,
)
from abso.core.auditor import ConfigurationAuditor
from abso.core.backup import BackupManager
from abso.core.backup_actions import (
    create_manual_backup_payload,
    delete_backup_payload,
    list_backup_payloads,
    prune_backup_payload,
)
from abso.core.detector import HardwareDetector
from abso.core.exceptions import BackupNotFoundError, ProfileLaunchError
from abso.core.hardware_summary import (
    build_detect_payload,
    detect_bios_info,
    infer_cpu_topology,
)
from abso.core.health_console import (
    build_display_context_lines,
    build_display_diagnostic_report_lines,
    build_health_check_lines,
)
from abso.core.launch_sweep import (
    LaunchProfileError,
    build_launch_killset_payload,
    run_launch_sweep,
)
from abso.core.launcher import launch_profile, launch_profile_without_apply
from abso.core.pending_apply import apply_pending_profile_settings
from abso.core.profile_status import build_profile_verification_summary
from abso.core.transaction import ProfileTransactionManager
from abso.profiles.catalog import (
    get_profile_aliases,
    get_profile_manifest,
    is_valid_profile_id,
    is_valid_tray_category,
    profile_id_conflict_kind,
    resolve_profile_id,
    tray_category_choices,
)
from abso.profiles.user_profile_template import build_user_profile_yaml_template
from abso.utils.admin import is_admin

console = Console()
logger = logging.getLogger(__name__)


# Paths - handle both development and PyInstaller bundled modes
def get_data_dir() -> Path:
    """Get the data directory for backups and reports.

    In development: uses project root.
    When bundled: uses %LOCALAPPDATA%/AdaptiveBattleStationOptimizer.
    """
    import sys

    if getattr(sys, "frozen", False):
        return app_data_dir(create=True)
    return Path(__file__).parent.parent


ROOT_DIR = get_data_dir()
BACKUPS_DIR = ROOT_DIR / "backups"
REPORTS_DIR = ROOT_DIR / "reports"
STATE_FILE = ROOT_DIR / ".abso_state.json"


def _state_file_targets() -> list[Path]:
    """Return state file paths that should stay in sync.

    In packaged mode ROOT_DIR already points at LocalAppData, so there is only
    one target. In development mode, mirror the repo state into LocalAppData so
    the PowerShell tray and backend CLI see the same active profile.
    """
    return state_reconcile.state_file_write_targets(STATE_FILE)


def _write_state_snapshot(state: dict[str, Any]) -> None:
    """Write active-profile state to primary and mirrored targets."""
    mirror_warnings = state_store.write_state_snapshot(_state_file_targets(), state)
    for warning in mirror_warnings:
        logger.warning(
            "Failed to mirror state file to %s: %s",
            warning["path"],
            warning["error"],
        )


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


def _get_system_boot_time() -> datetime | None:
    """Return the local system boot time when it can be determined cheaply."""
    return state_reconcile.get_system_boot_time()


def _reconcile_reboot_pending_after_verified_boot(
    snapshot: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any]:
    """Clear stale reboot-pending state after a later boot and clean verify.

    Some settings, notably MPO, can only be committed by the Windows compositor
    at boot. Once the machine has booted after the write and live verification is
    clean, keeping ``reboot_pending`` set only creates stale tray/GUI warnings.
    """
    updated, changed = state_reconcile.reconcile_reboot_pending_after_verified_boot(
        snapshot,
        verification,
        boot_time=_get_system_boot_time(),
    )
    if not changed:
        return snapshot
    try:
        _write_state_snapshot(updated)
    except OSError as exc:
        logger.warning("Failed to clear stale reboot-pending state: %s", exc)
        return snapshot
    return updated


def clear_current_profile() -> None:
    """Clear the active profile state file after a restore/reset."""
    mirror_warnings = state_store.remove_state_targets(_state_file_targets())
    for warning in mirror_warnings:
        logger.warning(
            "Failed to remove mirrored state file %s: %s",
            warning["path"],
            warning["error"],
        )


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


def _read_state_snapshot() -> dict[str, Any]:
    """Read the persisted active-profile state file."""
    return state_store.read_state_snapshot(_state_file_targets())


def _build_state_verification_summary(profile_name: str) -> dict[str, Any]:
    """Return a compact live verification summary for active-profile state."""
    return build_profile_verification_summary(
        profile_name,
        ProfileApplier().verify_profile,
    )


def _apply_pending_profile_settings(profile_name: str, *, dry_run: bool = False) -> dict[str, Any]:
    """Apply narrowly-supported pending verifier fixes without a full profile transaction."""
    return apply_pending_profile_settings(
        profile_name,
        dry_run=dry_run,
        applier=ProfileApplier(),
        is_admin_func=is_admin,
        set_current_profile_func=set_current_profile,
    )


def _handler_names_from_settings(settings: list[Any]) -> set[str]:
    """Extract handler names from compact verifier setting identifiers."""
    names: set[str] = set()
    for setting in settings:
        name = str(setting).split(".", 1)[0].strip()
        if name:
            names.add(name)
    return names


def _verification_needs_no_apply(verification: dict[str, Any]) -> bool:
    """Return whether verification proves another full apply is not useful."""
    if verification.get("error") or verification.get("pending_apply_settings"):
        return False
    if verification.get("all_active") is True:
        return True

    pending_reboot_gated = list(verification.get("pending_reboot_gated_settings") or [])
    if not pending_reboot_gated:
        return False

    mismatched_handlers = {
        str(handler)
        for handler in (verification.get("mismatched_handlers") or [])
        if str(handler).strip()
    }
    if not mismatched_handlers:
        return True

    reboot_gated_handlers = _handler_names_from_settings(pending_reboot_gated)
    return mismatched_handlers.issubset(reboot_gated_handlers)


def _reboot_reasons_from_state_or_verification(
    state_snapshot: dict[str, Any],
    verification: dict[str, Any],
) -> list[str]:
    """Return stable reboot reasons using state first, verifier settings second."""
    state_reasons = [str(reason) for reason in (state_snapshot.get("reboot_reasons") or [])]
    if state_reasons:
        return state_reasons
    return sorted(
        _handler_names_from_settings(
            list(verification.get("pending_reboot_gated_settings") or [])
        )
    )


def _build_same_profile_apply_noop_payload(
    profile_name: str,
    *,
    state_snapshot: dict[str, Any],
    verification: dict[str, Any],
) -> dict[str, Any] | None:
    """Return a no-op apply payload when full apply would be redundant."""
    if not _verification_needs_no_apply(verification):
        return None

    pending_reboot_gated = list(verification.get("pending_reboot_gated_settings") or [])
    reboot_reasons = _reboot_reasons_from_state_or_verification(
        state_snapshot,
        verification,
    )
    reboot_pending = bool(state_snapshot.get("reboot_pending") or pending_reboot_gated)
    if pending_reboot_gated and verification.get("all_active") is not True:
        notice = (
            "Profile has reboot-gated settings already written; skipped apply "
            "because only a reboot can commit them."
        )
    else:
        notice = (
            "Profile already verified active; skipped apply to avoid redundant "
            "display/color resets."
        )
    return {
        "success": True,
        "profile": profile_name,
        "requested_profile": profile_name,
        "fallback_applied": False,
        "fallback_chain": [],
        "backup_id": None,
        "requires_reboot": reboot_pending,
        "reboot_pending": reboot_pending,
        "reboot_reasons": reboot_reasons,
        "in_game_settings": False,
        "error": None,
        "applied_settings": [],
        "handler_applied_details": {},
        "monitor_adaptive_sync_state": None,
        "failed_settings": [],
        "warnings": [],
        "notices": [notice],
        "summary_level": "notice",
        "changed": False,
        "changed_settings": [],
        "capabilities": None,
        "results": [],
        "transaction": None,
        "compliance": None,
        "launch_sweep": None,
        "display_reset": None,
        "verification": verification,
    }


def _build_pending_apply_as_apply_payload(
    profile_name: str,
    pending_result: dict[str, Any],
) -> dict[str, Any]:
    """Wrap apply-pending output in the apply command's JSON response shape."""
    handler_results = pending_result.get("handler_results") or {}
    results = []
    for handler_name, handler_result in handler_results.items():
        status = "success" if handler_result.get("success") else "failed"
        row: dict[str, Any] = {"handler": handler_name, "status": status}
        if handler_result.get("error"):
            row["error"] = handler_result["error"]
        results.append(row)

    warnings = list(pending_result.get("warnings") or [])
    notices = list(pending_result.get("notices") or [])
    if pending_result.get("success"):
        append_unique_message(
            notices,
            "Used targeted pending apply; skipped full profile transaction.",
        )

    summary_level = "error"
    if pending_result.get("success"):
        summary_level = "caution" if warnings else "notice"

    return {
        "success": bool(pending_result.get("success")),
        "profile": profile_name,
        "requested_profile": profile_name,
        "fallback_applied": False,
        "fallback_chain": [],
        "backup_id": None,
        "requires_reboot": bool(pending_result.get("requires_reboot")),
        "reboot_pending": bool(pending_result.get("requires_reboot")),
        "reboot_reasons": list(pending_result.get("reboot_reasons") or []),
        "in_game_settings": False,
        "error": pending_result.get("error"),
        "applied_settings": [],
        "handler_applied_details": {},
        "monitor_adaptive_sync_state": None,
        "failed_settings": [],
        "warnings": warnings,
        "notices": notices,
        "summary_level": summary_level,
        "changed": bool(pending_result.get("changed")),
        "changed_settings": list(pending_result.get("changed_settings") or []),
        "capabilities": None,
        "results": results,
        "transaction": None,
        "compliance": None,
        "launch_sweep": None,
        "display_reset": None,
        "pending_apply": pending_result,
    }


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
        console.print("Please run from an elevated terminal.")
        raise SystemExit(1)
    from abso.core.setup_wizard import SetupWizard

    SetupWizard().run()


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def detect(json_output: bool) -> None:
    """Detect and report gaming hardware."""
    if not json_output and not is_admin():
        console.print(
            "[yellow]Warning: Running without admin privileges. Some detection may be limited.[/yellow]"
        )

    detector = HardwareDetector()
    hardware = detector.detect_all()

    bios_info = detect_bios_info()
    cpu_topology = infer_cpu_topology(hardware.get("cpu"))

    # JSON output mode
    if json_output:
        output_json(build_detect_payload(hardware, bios_info=bios_info, is_admin=is_admin()))
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
                if system_family and system_family.lower() not in [
                    "default string",
                    "to be filled",
                ]:
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
        if cpu_topology and cpu_topology.get("type") == "hybrid":
            p_cores = cpu_topology.get("p_cores")
            e_cores = cpu_topology.get("e_cores")
            if isinstance(p_cores, int) and isinstance(e_cores, int):
                console.print(f"  Topology: [cyan]Hybrid[/cyan] ({p_cores}P + {e_cores}E)")
            else:
                console.print("  Topology: [cyan]Hybrid[/cyan]")
        elif cpu_topology and cpu_topology.get("type") == "homogeneous":
            console.print("  Topology: [dim]Homogeneous[/dim]")
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
            name = monitor.get("name", "Unknown")
            primary = " [green](Primary)[/green]" if monitor.get("is_primary") else ""
            console.print(f"  [{i}] {name}{primary}")
            console.print(f"      Resolution: {monitor.get('resolution', 'Unknown')}")
            refresh_str = f"{monitor.get('refresh_rate', 'Unknown')} Hz"
            max_refresh = monitor.get("max_refresh_rate")
            max_capability = monitor.get("max_refresh_capability")
            if max_refresh:
                refresh_str += f" [yellow](Max @ res: {max_refresh} Hz)[/yellow]"
            elif max_capability:
                refresh_str += f" [yellow](Supports up to {max_capability} Hz)[/yellow]"
            console.print(f"      Refresh Rate: {refresh_str}")
            if monitor.get("adapter"):
                console.print(f"      Adapter: {monitor.get('adapter')}")

            # VRR/G-Sync status
            vrr = monitor.get("vrr_supported")
            vrr_type = monitor.get("vrr_type")
            vrr_range = monitor.get("vrr_range")

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
            xmp_str = "[yellow]Likely disabled[/yellow]"
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
                "target_value": issue.optimal_value,
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
        severity_color = {"critical": "red", "warning": "yellow", "info": "blue"}.get(
            issue.severity, "white"
        )

        console.print(
            f"[{severity_color}][{issue.severity.upper()}][/{severity_color}] {issue.title}"
        )
        console.print(f"  Current: {issue.current_value}")
        console.print(f"  Target: {issue.optimal_value}")

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
@click.option(
    "--verify/--no-verify",
    "verify_state",
    default=False,
    help="Include a compact live verification summary for the current profile.",
)
def state(json_output: bool, verify_state: bool) -> None:
    """Show the persisted active-profile state."""
    snapshot = _read_state_snapshot()
    if verify_state and snapshot.get("current_profile"):
        snapshot = dict(snapshot)
        verification = _build_state_verification_summary(
            str(snapshot["current_profile"])
        )
        snapshot = _reconcile_reboot_pending_after_verified_boot(snapshot, verification)
        snapshot["verification"] = verification

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
    verification = snapshot.get("verification")
    if isinstance(verification, dict):
        status = verification.get("status", "unknown")
        console.print(f"Verified state: {status}")
        pending_apply = verification.get("pending_apply_settings") or []
        if pending_apply:
            console.print("Pending apply settings:")
            for setting in pending_apply:
                console.print(f"  - {setting}")
        pending_reboot_gated = verification.get("pending_reboot_gated_settings") or []
        if pending_reboot_gated:
            console.print("Pending reboot-gated settings:")
            for setting in pending_reboot_gated:
                console.print(f"  - {setting}")
        if verification.get("error"):
            console.print(f"[yellow]Verification error: {verification['error']}[/yellow]")


@cli.command("apply-pending")
@click.argument("profile_name", required=False)
@click.option("--dry-run", is_flag=True, help="Show pending writes without applying them")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def apply_pending(profile_name: str | None, dry_run: bool, json_output: bool) -> None:
    """Apply narrow verifier-reported fixes without a full profile transaction.

    When PROFILE_NAME is omitted, the persisted current profile is used.
    This command intentionally supports only settings that are safe to write
    outside the full backup/baseline/apply pipeline.
    """
    if not profile_name:
        profile_name = _read_state_snapshot().get("current_profile")
    if not profile_name:
        message = "No current profile recorded; pass PROFILE_NAME explicitly"
        if json_output:
            json_error(message)
        console.print(f"[red]Error: {message}[/red]")
        sys.exit(1)

    profile_name = resolve_profile_id(profile_name) or profile_name

    try:
        result = _apply_pending_profile_settings(profile_name, dry_run=dry_run)
    except ValueError as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)

    if json_output:
        output_json(result, success=bool(result.get("success")))
        if not result.get("success"):
            sys.exit(1)
        return

    if not result.get("success"):
        console.print(f"[red]Failed to apply pending settings: {result.get('error')}[/red]")
        sys.exit(1)

    actions = result.get("actions") or []
    if result.get("dry_run"):
        if not actions:
            console.print("[green]No pending apply settings found.[/green]")
            return
        console.print("[yellow]Pending supported apply action(s):[/yellow]")
        for action in actions:
            console.print(
                f"  [yellow]- {action['pending_setting']} -> "
                f"{action['apply_setting']}={action['target']}[/yellow]"
            )
        return

    changed_settings = result.get("changed_settings") or []
    if changed_settings:
        console.print(
            "[green]Applied pending setting(s): "
            + ", ".join(str(item) for item in changed_settings)
            + "[/green]"
        )
    else:
        console.print("[green]No pending setting write was needed.[/green]")

    if result.get("requires_reboot"):
        console.print(
            "[yellow]Reboot required before judging the live display compositor path.[/yellow]"
        )


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
            profile: [g.name for g in matched] for profile, matched in suggestions.items()
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
@click.option(
    "--benchmark", is_flag=True, help="Capture before/after frame times (requires PresentMon)"
)
@click.option(
    "--no-fallback",
    is_flag=True,
    help="Fail instead of applying a capability fallback profile.",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def apply(
    profile_name: str,
    no_backup: bool,
    benchmark: bool,
    no_fallback: bool,
    json_output: bool,
) -> None:
    """Apply a game optimization profile.

    PROFILE_NAME is the profile to apply (e.g., slippi-melee, rivals2-online, diablo4).
    """
    profile_name = resolve_profile_id(profile_name) or profile_name
    current_profile = get_current_profile()
    same_current_profile = (
        current_profile is not None and resolve_profile_id(current_profile) == profile_name
    )

    if same_current_profile:
        try:
            verification = _build_state_verification_summary(profile_name)
            state_snapshot = _reconcile_reboot_pending_after_verified_boot(
                _read_state_snapshot(),
                verification,
            )
            noop_payload = _build_same_profile_apply_noop_payload(
                profile_name,
                state_snapshot=state_snapshot,
                verification=verification,
            )
            pending_apply_settings = list(verification.get("pending_apply_settings") or [])
        except Exception as exc:  # noqa: BLE001 - fall through to normal apply path
            logger.warning("Pre-apply verification failed for %s: %s", profile_name, exc)
            noop_payload = None
            pending_apply_settings = []

        if noop_payload is not None:
            if json_output:
                output_json(noop_payload)
                return

            console.print(Panel(f"Applying Profile: {profile_name}", style="bold blue"))
            console.print(f"[cyan]Note: {noop_payload['notices'][0]}[/cyan]")
            if noop_payload.get("reboot_pending"):
                console.print("[yellow]Reboot is still required for:[/yellow]")
                for reason in noop_payload.get("reboot_reasons") or []:
                    console.print(f"  [yellow]- {reason}[/yellow]")
            return

        if pending_apply_settings:
            pending_result = _apply_pending_profile_settings(profile_name)
            pending_payload = _build_pending_apply_as_apply_payload(
                profile_name,
                pending_result,
            )
            if json_output:
                output_json(pending_payload, success=bool(pending_payload["success"]))
                if not pending_payload["success"]:
                    sys.exit(1)
                return

            console.print(Panel(f"Applying Pending Fix: {profile_name}", style="bold blue"))
            if not pending_payload["success"]:
                console.print(
                    f"[red]Failed to apply pending settings: {pending_payload.get('error')}[/red]"
                )
                sys.exit(1)

            changed_settings = pending_payload.get("changed_settings") or []
            if changed_settings:
                console.print(
                    "[green]Applied pending setting(s): "
                    + ", ".join(str(item) for item in changed_settings)
                    + "[/green]"
                )
            else:
                console.print("[green]No pending setting write was needed.[/green]")
            if pending_payload.get("requires_reboot"):
                console.print(
                    "[yellow]Reboot required before judging the live display compositor path.[/yellow]"
                )
            return

    if not is_admin():
        if json_output:
            json_error("Admin privileges required to apply profiles")
        console.print("[red]Error: Admin privileges required to apply profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    create_backup = not no_backup and not same_current_profile

    if not json_output:
        console.print(Panel(f"Applying Profile: {profile_name}", style="bold blue"))
        if no_backup:
            console.print("[yellow]Warning: Skipping backup as requested.[/yellow]\n")
        elif same_current_profile:
            console.print(
                "[dim]Profile is already current; skipping backup/baseline restore.[/dim]\n"
            )
        else:
            console.print("[yellow]Creating backup...[/yellow]")

    # --- Benchmark: capture baseline before apply ---
    benchmark_baseline = None
    benchmark_exe = None
    if benchmark:
        try:
            from abso.core.benchmark import FrameTimeBenchmark, PresentMonNotFoundError
            from abso.core.process_list import parse_tasklist_csv_images

            bench = FrameTimeBenchmark()
            profile_class = ProfileApplier.PROFILES.get(profile_name)
            if profile_class:
                for exe in profile_class().executable_hints:
                    # Check if game is running
                    check = subprocess.run(
                        ["tasklist", "/FI", f"IMAGENAME eq {exe}", "/FO", "CSV", "/NH"],
                        capture_output=True,
                        text=True,
                        timeout=5,
                    )
                    if exe.lower() in parse_tasklist_csv_images(check.stdout or ""):
                        benchmark_exe = exe
                        break

            if benchmark_exe:
                if not json_output:
                    console.print(f"[cyan]Capturing 30s baseline for {benchmark_exe}...[/cyan]")
                baseline_capture = bench.capture(benchmark_exe, duration_seconds=30)
                benchmark_baseline = bench.analyze(baseline_capture)
            elif not json_output:
                console.print("[dim]Game not running - skipping benchmark baseline[/dim]")
        except PresentMonNotFoundError:
            if not json_output:
                console.print("[dim]PresentMon not found - skipping benchmark[/dim]")
            benchmark = False
        except Exception as e:
            if not json_output:
                console.print(f"[dim]Benchmark baseline failed: {e}[/dim]")
            benchmark_baseline = None

    try:
        tx_manager = ProfileTransactionManager(BACKUPS_DIR)
        tx = tx_manager.execute(
            profile_id=profile_name,
            create_backup=create_backup,
            allow_capability_fallback=not no_fallback,
        )
        result = tx.apply_result
        requested_profile_name = profile_name
        tx_profile_id = getattr(tx, "profile_id", None)
        actual_profile_name = (
            tx_profile_id
            if isinstance(tx_profile_id, str) and tx_profile_id.strip()
            else requested_profile_name
        )
        raw_fallback_chain = getattr(tx, "fallback_chain", None)
        fallback_chain = raw_fallback_chain if isinstance(raw_fallback_chain, list) else []
        fallback_applied = bool(fallback_chain)
        apply_warnings = collect_apply_warnings(tx, result)
        apply_notices = collect_apply_notices(result)
        if same_current_profile and not no_backup:
            append_unique_message(
                apply_notices,
                (
                    "Profile was already current; skipped backup and baseline "
                    "restore to avoid redundant display/color resets."
                ),
            )
        if fallback_applied:
            fallback_reason = ""
            last_fallback = fallback_chain[-1] if isinstance(fallback_chain[-1], dict) else {}
            if isinstance(last_fallback.get("reason"), str):
                fallback_reason = f": {last_fallback['reason']}"
            append_unique_message(
                apply_notices,
                (
                    f"Requested profile '{requested_profile_name}' was blocked; "
                    f"applied safe fallback '{actual_profile_name}' instead{fallback_reason}"
                ),
            )
        apply_succeeded = bool(tx.success and result and result.success)
        apply_summary_level = (
            determine_apply_summary_level(apply_warnings, apply_notices)
            if apply_succeeded
            else "error"
        )

        # Run the launch-time process janitor right now so the user does not
        # have to wait for the LaunchSanitizer tray timer (which only fires
        # when the game binary itself is detected running).
        launch_sweep = run_post_apply_sweep(actual_profile_name, tx, result)

        # Display recovery is manual by default because even documented
        # recovery paths can briefly blank secondary outputs. Advanced users
        # may opt into the non-disruptive automatic path with
        # ABSO_ENABLE_AUTO_DISPLAY_RECOVERY=1.
        display_reset = run_post_apply_display_reset(actual_profile_name, tx, result)

        if json_output:
            if apply_succeeded:
                set_current_profile(
                    actual_profile_name,
                    requires_reboot=result.requires_reboot,
                    reboot_reasons=result.reboot_reasons,
                )
            applied_settings = result.applied_settings if result else []
            failed_settings = result.failed_settings if result else []
            output_json(
                {
                    "success": tx.success,
                    "profile": actual_profile_name,
                    "requested_profile": requested_profile_name,
                    "fallback_applied": fallback_applied,
                    "fallback_chain": fallback_chain,
                    "backup_id": tx.backup_id,
                    "requires_reboot": result.requires_reboot if result else False,
                    "in_game_settings": result.in_game_settings if result else False,
                    "error": tx.error if not tx.success else None,
                    "applied_settings": applied_settings,
                    "handler_applied_details": (
                        result.handler_applied_details if result else {}
                    ),
                    "monitor_adaptive_sync_state": (
                        result.monitor_adaptive_sync_state if result else None
                    ),
                    "failed_settings": failed_settings,
                    "warnings": apply_warnings,
                    "notices": apply_notices,
                    "summary_level": apply_summary_level,
                    "changed_settings": result.changed_settings if result else [],
                    "capabilities": (
                        result.capability_report.to_dict()
                        if result and result.capability_report
                        else None
                    ),
                    "results": [{"handler": h, "status": "success"} for h in applied_settings]
                    + [
                        {"handler": f.split(":")[0].strip(), "status": "failed", "error": f}
                        for f in failed_settings
                    ],
                    "transaction": tx.to_dict(),
                    "compliance": tx.compliance_report.to_dict() if tx.compliance_report else None,
                    "launch_sweep": launch_sweep,
                    "display_reset": display_reset,
                },
                success=tx.success,
            )
            return

        if tx.backup_id and not no_backup:
            console.print(f"[green]Backup created: {tx.backup_id}[/green]\n")

        if apply_succeeded:
            set_current_profile(
                actual_profile_name,
                requires_reboot=result.requires_reboot,
                reboot_reasons=result.reboot_reasons,
            )
            if apply_summary_level == "warning":
                console.print(
                    f"\n[yellow]Profile '{actual_profile_name}' committed with warnings.[/yellow]"
                )
            elif apply_summary_level == "caution":
                console.print(
                    f"\n[green]Profile '{actual_profile_name}' applied with cautions.[/green]"
                )
            elif apply_summary_level == "notice":
                console.print(
                    f"\n[green]Profile '{actual_profile_name}' applied with notices.[/green]"
                )
            else:
                console.print(
                    f"\n[green]Profile '{actual_profile_name}' apply completed.[/green] "
                    f"[dim]Run 'abso verify {actual_profile_name}' to confirm handler state.[/dim]"
                )

            if result.requires_reboot and result.reboot_reasons:
                console.print("[yellow]Reboot required for:[/yellow]")
                for reason in result.reboot_reasons:
                    console.print(f"  [yellow]- {reason}[/yellow]")
                console.print(
                    f"[dim]Run 'abso verify {actual_profile_name}' to re-check after reboot.[/dim]"
                )
            elif result.requires_reboot:
                console.print("[yellow]Some changes may require a reboot.[/yellow]")
                console.print(
                    f"[dim]Run 'abso verify {actual_profile_name}' to re-check after reboot.[/dim]"
                )

            warning_prefix = "Caution" if apply_summary_level == "caution" else "Warning"
            for warning in apply_warnings:
                console.print(f"[yellow]{warning_prefix}: {warning}[/yellow]")
            for notice in apply_notices:
                console.print(f"[cyan]Note: {notice}[/cyan]")

            # Surface the post-apply launch sweep so users see what got
            # stopped without having to look at tray logs.
            if launch_sweep:
                stopped = launch_sweep.get("stopped") or []
                sweep_warnings = launch_sweep.get("warnings") or []
                if stopped:
                    console.print(
                        f"\n[green]Stopped {len(stopped)} background process(es):[/green]"
                    )
                    for image in stopped:
                        console.print(f"  [green]-[/green] {image}")
                if sweep_warnings:
                    for warning in sweep_warnings:
                        console.print(f"[yellow]Sweep warning: {warning}[/yellow]")

            # Surface the auto DWM refresh so users understand what the
            # post-apply pause was for. Silent when not fired.
            if display_reset and display_reset.get("fired"):
                reasons = display_reset.get("triggered_by") or []
                elapsed = display_reset.get("elapsed_seconds") or 0.0
                method = display_reset.get("method") or "unknown"
                sent_count = display_reset.get("sent_count")
                if method == "driver-hotkey":
                    detail = f"Ctrl+Win+Shift+B x{sent_count}" if sent_count else "Ctrl+Win+Shift+B"
                    console.print(
                        f"\n[green]Reset graphics driver "
                        f"({detail}, {elapsed:.1f}s) to commit HDR.[/green]"
                    )
                elif method == "mode-reset":
                    console.print(
                        f"\n[green]Forced display mode reset "
                        f"(ChangeDisplaySettingsEx, {elapsed:.1f}s) to commit HDR.[/green]"
                    )
                else:
                    console.print(
                        f"\n[green]Refreshed DWM display database "
                        f"(SetDisplayConfig, {elapsed:.1f}s) to commit HDR.[/green]"
                    )
                if reasons:
                    for reason in reasons:
                        console.print(f"  [dim]triggered by: {reason}[/dim]")
            elif display_reset and display_reset.get("error"):
                console.print(
                    f"\n[yellow]DWM refresh attempt failed: " f"{display_reset['error']}[/yellow]"
                )

            if result.in_game_settings:
                # Actually generate the report file
                REPORTS_DIR.mkdir(parents=True, exist_ok=True)
                applier = tx_manager.applier
                report_path = applier.generate_report(actual_profile_name, REPORTS_DIR)
                console.print(f"\n[cyan]In-game settings saved to: {report_path}[/cyan]")

            # --- Benchmark: capture after apply and compare ---
            if benchmark and benchmark_baseline and benchmark_exe:
                try:
                    console.print(f"\n[cyan]Capturing 30s post-apply for {benchmark_exe}...[/cyan]")
                    after_capture = bench.capture(benchmark_exe, duration_seconds=30)
                    after_analysis = bench.analyze(after_capture)
                    comparison = bench.compare(benchmark_baseline, after_analysis)

                    from rich.table import Table

                    table = Table(title="Benchmark Comparison (Before > After)")
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
                    table.add_row(
                        "Avg FPS",
                        f"{b.avg_fps:.1f}",
                        f"{a.avg_fps:.1f}",
                        _fmt_delta(a.avg_fps - b.avg_fps, True),
                    )
                    table.add_row(
                        "1% Low FPS",
                        f"{b.p1_low_fps:.1f}",
                        f"{a.p1_low_fps:.1f}",
                        _fmt_delta(a.p1_low_fps - b.p1_low_fps, True),
                    )
                    table.add_row(
                        "0.1% Low FPS",
                        f"{b.p01_low_fps:.1f}",
                        f"{a.p01_low_fps:.1f}",
                        _fmt_delta(a.p01_low_fps - b.p01_low_fps, True),
                    )
                    table.add_row(
                        "Avg Frame Time",
                        f"{b.avg_frame_time_ms:.2f}ms",
                        f"{a.avg_frame_time_ms:.2f}ms",
                        _fmt_delta(a.avg_frame_time_ms - b.avg_frame_time_ms, False),
                    )
                    table.add_row(
                        "P95 Frame Time",
                        f"{b.p95_frame_time_ms:.2f}ms",
                        f"{a.p95_frame_time_ms:.2f}ms",
                        _fmt_delta(a.p95_frame_time_ms - b.p95_frame_time_ms, False),
                    )
                    table.add_row(
                        "P99 Frame Time",
                        f"{b.p99_frame_time_ms:.2f}ms",
                        f"{a.p99_frame_time_ms:.2f}ms",
                        _fmt_delta(a.p99_frame_time_ms - b.p99_frame_time_ms, False),
                    )
                    table.add_row(
                        "Frame Time Stdev",
                        f"{b.frame_time_stdev:.2f}ms",
                        f"{a.frame_time_stdev:.2f}ms",
                        _fmt_delta(a.frame_time_stdev - b.frame_time_stdev, False),
                    )

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
@click.option(
    "--no-wait", is_flag=True, help="Return immediately after launching instead of waiting for exit"
)
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
    current_profile = get_current_profile()
    same_current_profile = (
        current_profile is not None and resolve_profile_id(current_profile) == profile_name
    )

    if same_current_profile and not restore_on_exit:
        try:
            verification = _build_state_verification_summary(profile_name)
            state_snapshot = _reconcile_reboot_pending_after_verified_boot(
                _read_state_snapshot(),
                verification,
            )
            noop_payload = _build_same_profile_apply_noop_payload(
                profile_name,
                state_snapshot=state_snapshot,
                verification=verification,
            )
            pending_apply_settings = list(verification.get("pending_apply_settings") or [])
        except Exception as exc:  # noqa: BLE001 - fall through to normal launch path
            logger.warning("Pre-launch verification failed for %s: %s", profile_name, exc)
            noop_payload = None
            pending_apply_settings = []

        if noop_payload is not None:
            try:
                launch_result = launch_profile_without_apply(
                    profile_id=profile_name,
                    wait=not no_wait,
                    launch_path=launch_path,
                    launch_args=list(launch_args),
                )
            except Exception as exc:  # noqa: BLE001 - normalize unexpected launch errors
                if json_output:
                    json_error(f"Unexpected launch failure: {exc}")
                console.print(f"[red]Unexpected launch failure: {exc}[/red]")
                sys.exit(1)

            payload = launch_result.to_dict()
            payload["apply"] = noop_payload
            if json_output:
                output_json(payload, success=launch_result.success, error=launch_result.error)
                return

            console.print(Panel(f"Launching With Profile: {profile_name}", style="bold blue"))
            console.print(f"[cyan]Note: {noop_payload['notices'][0]}[/cyan]")
            if launch_result.target:
                console.print(f"[cyan]Target:[/cyan] {launch_result.target.executable_path}")
            if launch_result.launched:
                console.print(f"[green]Process launched[/green] (PID {launch_result.process_id})")
                return
            if launch_result.error:
                console.print(f"[red]Launch flow failed: {launch_result.error}[/red]")
            sys.exit(1)

        if pending_apply_settings:
            pending_result = _apply_pending_profile_settings(profile_name)
            pending_payload = _build_pending_apply_as_apply_payload(
                profile_name,
                pending_result,
            )
            if not pending_payload["success"]:
                if json_output:
                    output_json(
                        {
                            "error": pending_payload.get("error"),
                            "apply": pending_payload,
                        },
                        success=False,
                    )
                    sys.exit(1)
                console.print(
                    f"[red]Failed to apply pending settings: {pending_payload.get('error')}[/red]"
                )
                sys.exit(1)

            try:
                launch_result = launch_profile_without_apply(
                    profile_id=profile_name,
                    wait=not no_wait,
                    launch_path=launch_path,
                    launch_args=list(launch_args),
                )
            except Exception as exc:  # noqa: BLE001 - normalize unexpected launch errors
                if json_output:
                    json_error(f"Unexpected launch failure: {exc}")
                console.print(f"[red]Unexpected launch failure: {exc}[/red]")
                sys.exit(1)

            payload = launch_result.to_dict()
            payload["apply"] = pending_payload
            if json_output:
                output_json(payload, success=launch_result.success, error=launch_result.error)
                return

            console.print(Panel(f"Launching With Profile: {profile_name}", style="bold blue"))
            console.print("[green]Applied targeted pending profile fix before launch.[/green]")
            if launch_result.target:
                console.print(f"[cyan]Target:[/cyan] {launch_result.target.executable_path}")
            if launch_result.launched:
                console.print(f"[green]Process launched[/green] (PID {launch_result.process_id})")
                return
            if launch_result.error:
                console.print(f"[red]Launch flow failed: {launch_result.error}[/red]")
            sys.exit(1)

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
    launch_profile_id = getattr(launch_result, "profile_id", None)
    if not isinstance(launch_profile_id, str) or not launch_profile_id.strip():
        tx_profile_id = getattr(tx, "profile_id", None)
        launch_profile_id = (
            tx_profile_id
            if isinstance(tx_profile_id, str) and tx_profile_id.strip()
            else profile_name
        )
    if tx.success and apply_result and apply_result.success:
        set_current_profile(
            launch_profile_id,
            requires_reboot=apply_result.requires_reboot,
            reboot_reasons=apply_result.reboot_reasons,
        )
        if launch_result.restored:
            clear_current_profile()

    if json_output:
        output_json(
            launch_result.to_dict(), success=launch_result.success, error=launch_result.error
        )
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
        console.print("[yellow]Launch did not start a process.[/yellow]")

    for warning in launch_result.warnings:
        console.print(f"[yellow]Warning: {warning}[/yellow]")

    if launch_result.restored:
        console.print(
            f"[green]Restored pre-launch backup: {launch_result.restore_backup_id}[/green]"
        )
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
        console.print(
            "[yellow]Profile settings remain applied; the apply step finished before launch failed.[/yellow]"
        )

    sys.exit(1)


@cli.command()
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def reapply(json_output: bool) -> None:
    """Re-apply the current profile without creating a backup.

    Use this when Windows reverts settings (e.g., after display mode change).
    Faster than 'apply' since it skips backup creation.
    """
    current_profile = get_current_profile()
    if not current_profile:
        if json_output:
            json_error("No profile has been applied yet. Use 'abso apply <profile>' first.")
        console.print("[red]Error: No profile has been applied yet.[/red]")
        console.print("Use [bold]abso apply <profile>[/bold] first.")
        sys.exit(1)

    try:
        verification = _build_state_verification_summary(current_profile)
    except Exception as exc:  # noqa: BLE001 - inability to verify should fall through to reapply
        logger.warning("Pre-reapply verification failed for %s: %s", current_profile, exc)
        verification = None

    if isinstance(verification, dict):
        state_snapshot = _read_state_snapshot()
        state_snapshot = _reconcile_reboot_pending_after_verified_boot(
            state_snapshot,
            verification,
        )
        if _verification_needs_no_apply(verification):
            pending_reboot_gated = list(verification.get("pending_reboot_gated_settings") or [])
            reboot_reasons = _reboot_reasons_from_state_or_verification(
                state_snapshot,
                verification,
            )
            reboot_pending = bool(state_snapshot.get("reboot_pending") or pending_reboot_gated)
            if pending_reboot_gated and verification.get("all_active") is not True:
                notice = (
                    "Current profile has reboot-gated settings already written; skipped "
                    "reapply because only a reboot can commit them."
                )
            else:
                notice = (
                    "Current profile already verified active; skipped reapply to avoid "
                    "redundant display/color resets."
                )
            if json_output:
                output_json(
                    {
                        "success": True,
                        "profile": current_profile,
                        "requested_profile": current_profile,
                        "fallback_applied": False,
                        "fallback_chain": [],
                        "changed": False,
                        "changed_settings": [],
                        "warnings": [],
                        "notices": [notice],
                        "summary_level": "notice",
                        "reboot_pending": reboot_pending,
                        "reboot_reasons": reboot_reasons,
                        "verification": verification,
                        "transaction": None,
                    }
                )
                return

            console.print(Panel(f"Re-applying Profile: {current_profile}", style="bold blue"))
            console.print(f"[cyan]Note: {notice}[/cyan]")
            if reboot_pending:
                console.print("[yellow]Reboot is still required for:[/yellow]")
                for reason in reboot_reasons:
                    console.print(f"  [yellow]- {reason}[/yellow]")
            return

        pending_apply_settings = list(verification.get("pending_apply_settings") or [])
        if pending_apply_settings:
            pending_result = _apply_pending_profile_settings(current_profile)
            pending_payload = _build_pending_apply_as_apply_payload(
                current_profile,
                pending_result,
            )
            if json_output:
                output_json(pending_payload, success=bool(pending_payload["success"]))
                if not pending_payload["success"]:
                    sys.exit(1)
                return

            console.print(Panel(f"Re-applying Pending Fix: {current_profile}", style="bold blue"))
            if not pending_payload["success"]:
                console.print(
                    f"[red]Failed to apply pending settings: {pending_payload.get('error')}[/red]"
                )
                sys.exit(1)

            changed_settings = pending_payload.get("changed_settings") or []
            if changed_settings:
                console.print(
                    "[green]Applied pending setting(s): "
                    + ", ".join(str(item) for item in changed_settings)
                    + "[/green]"
                )
            else:
                console.print("[green]No pending setting write was needed.[/green]")
            if pending_payload.get("requires_reboot"):
                console.print(
                    "[yellow]Reboot required before judging the live display compositor path.[/yellow]"
                )
            return

    if not is_admin():
        if json_output:
            json_error("Admin privileges required to apply profiles")
        console.print("[red]Error: Admin privileges required to apply profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    if not json_output:
        console.print(Panel(f"Re-applying Profile: {current_profile}", style="bold blue"))
        console.print("[dim]Skipping backup (use 'apply' for full backup)[/dim]\n")

    try:
        tx_manager = ProfileTransactionManager(BACKUPS_DIR)
        tx = tx_manager.execute(profile_id=current_profile, create_backup=False)
        result = tx.apply_result
        tx_profile_id = getattr(tx, "profile_id", None)
        actual_profile = (
            tx_profile_id
            if isinstance(tx_profile_id, str) and tx_profile_id.strip()
            else current_profile
        )
        raw_fallback_chain = getattr(tx, "fallback_chain", None)
        fallback_chain = raw_fallback_chain if isinstance(raw_fallback_chain, list) else []
        fallback_applied = bool(fallback_chain)
        warnings = collect_apply_warnings(tx, result)
        notices = collect_apply_notices(result)
        if fallback_applied and actual_profile != current_profile:
            fallback_reason = ""
            last_fallback = fallback_chain[-1] if isinstance(fallback_chain[-1], dict) else {}
            if isinstance(last_fallback.get("reason"), str):
                fallback_reason = f": {last_fallback['reason']}"
            append_unique_message(
                notices,
                (
                    f"Current profile '{current_profile}' was blocked; "
                    f"re-applied safe fallback '{actual_profile}' instead{fallback_reason}"
                ),
            )
        reapply_succeeded = bool(tx.success and result and result.success)
        summary_level = (
            determine_apply_summary_level(warnings, notices) if reapply_succeeded else "error"
        )

        if json_output:
            if reapply_succeeded:
                set_current_profile(
                    actual_profile,
                    requires_reboot=result.requires_reboot,
                    reboot_reasons=result.reboot_reasons,
                )
            output_json(
                {
                    "success": reapply_succeeded,
                    "profile": actual_profile,
                    "requested_profile": current_profile,
                    "fallback_applied": fallback_applied,
                    "fallback_chain": fallback_chain,
                    "warnings": warnings,
                    "notices": notices,
                    "summary_level": summary_level,
                    "error": tx.error if not reapply_succeeded else None,
                    "transaction": tx.to_dict(),
                },
                success=tx.success,
            )
            return

        if reapply_succeeded:
            set_current_profile(
                actual_profile,
                requires_reboot=result.requires_reboot,
                reboot_reasons=result.reboot_reasons,
            )
            if fallback_applied and actual_profile != current_profile:
                console.print(
                    f"[yellow]Current profile was blocked; "
                    f"using safe fallback '{actual_profile}'.[/yellow]"
                )
            if summary_level == "warning":
                console.print(
                    f"\n[yellow]Profile '{actual_profile}' re-applied with warnings.[/yellow]"
                )
            elif summary_level == "caution":
                console.print(
                    f"\n[green]Profile '{actual_profile}' re-applied with cautions.[/green]"
                )
            elif summary_level == "notice":
                console.print(
                    f"\n[green]Profile '{actual_profile}' re-applied with notices.[/green]"
                )
            else:
                console.print(
                    f"\n[green]Profile '{actual_profile}' re-apply completed.[/green] "
                    f"[dim]Run 'abso verify {actual_profile}' to confirm handler state.[/dim]"
                )
            warning_prefix = "Caution" if summary_level == "caution" else "Warning"
            for warning in warnings:
                console.print(f"[yellow]{warning_prefix}: {warning}[/yellow]")
            for notice in notices:
                console.print(f"[cyan]Note: {notice}[/cyan]")
        else:
            error = tx.error or (result.error if result else "Unknown transaction error")
            console.print(f"\n[red]Failed to re-apply profile: {error}[/red]")
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
        else:
            console.print("\n[yellow]Some settings are not yet in the intended state:[/yellow]")
            pending_apply = result.get("pending_apply_settings") or []
            if pending_apply:
                console.print(
                    "[yellow]Pending setting(s) that still need elevated apply: "
                    + ", ".join(str(item) for item in pending_apply)
                    + "[/yellow]"
                )
                console.print(
                    "[dim]Run the apply from the elevated tray or an Administrator shell. "
                    "A reboot may still be needed after the registry target is written.[/dim]"
                )
            pending_reboot_gated = result.get("pending_reboot_gated_settings") or []
            if pending_reboot_gated:
                console.print(
                    "[yellow]Pending reboot-gated setting(s): "
                    + ", ".join(str(item) for item in pending_reboot_gated)
                    + "[/yellow]"
                )
                console.print(
                    "[dim]Apply from an elevated shell/tray if not written yet, "
                    "then reboot before judging the live compositor path.[/dim]"
                )

        for handler_name, handler_result in handlers.items():
            if not handler_result.get("settings"):
                continue

            console.print(f"\n[bold]{handler_name}:[/bold]")
            for setting_name, setting_info in handler_result.get("settings", {}).items():
                status = (
                    "[green]Active[/green]"
                    if setting_info.get("active")
                    else "[yellow]Mismatch[/yellow]"
                )
                console.print(f"  {setting_name}: {status}")
                console.print(
                    f"    Target: {setting_info.get('target')}, Current: {setting_info.get('current')}"
                )
                if setting_info.get("reboot_gated"):
                    console.print(
                        f"    [dim]Reboot-gated: {setting_info.get('note', 'takes effect after reboot')}[/dim]"
                    )

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
            restore_error = describe_restore_summary(restore_summary, blocking_only=True)
            if json_output:
                output_json(
                    {
                        "success": False,
                        "backup_id": backup_id,
                        "message": restore_error,
                        "restore_summary": restore_summary,
                    },
                    success=False,
                )
                return
            console.print(f"[red]{restore_error}[/red]")
            for item in (
                restore_summary["failed_components"] + restore_summary["skipped_components"]
            ):
                if not bool(item.get("blocking", True)):
                    continue
                console.print(
                    f"  [red]- {item['handler']}: {item.get('detail', item['reason'])}[/red]"
                )
            sys.exit(1)
        clear_current_profile()
        if json_output:
            output_json(
                {
                    "success": True,
                    "backup_id": backup_id,
                    "message": "Restore completed for fully restorable handlers",
                    "restore_summary": restore_summary,
                }
            )
            return
        console.print(
            f"\n[green]Backup '{backup_id}' restore completed for fully restorable handlers.[/green]"
        )
        console.print("[yellow]Some changes may require a reboot.[/yellow]")
        console.print("[dim]Restoring to previously-active settings does not need a reboot.[/dim]")
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
    backup_list = list_backup_payloads(BACKUPS_DIR)

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
    backup = create_manual_backup_payload(BACKUPS_DIR, current_profile=get_current_profile())
    backup_id = backup["id"]

    if json_output:
        output_json(backup)
        return

    console.print(f"[green]Created manual backup: {backup_id}[/green]")


@cli.command("backup-delete")
@click.argument("backup_id")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def backup_delete(backup_id: str, json_output: bool) -> None:
    """Delete a backup by ID."""
    try:
        payload = delete_backup_payload(BACKUPS_DIR, backup_id)
    except BackupNotFoundError:
        if json_output:
            json_error(f"Backup '{backup_id}' not found")
        console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
        sys.exit(1)

    if json_output:
        output_json(payload)
        return

    console.print(f"[green]Deleted backup: {backup_id}[/green]")


@cli.command()
@click.option("--keep", "-k", type=int, default=20, help="Number of backups to keep (default: 20)")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def prune(keep: int, json_output: bool) -> None:
    """Remove old backups, keeping the most recent N.

    By default keeps the 20 most recent backups and deletes the rest.
    """
    existing = list_backup_payloads(BACKUPS_DIR)

    if json_output:
        output_json(prune_backup_payload(BACKUPS_DIR, keep=keep))
        return

    if len(existing) <= keep:
        console.print(
            f"[green]Nothing to prune. {len(existing)} backup(s) exist, limit is {keep}.[/green]"
        )
        return

    console.print(f"[yellow]Found {len(existing)} backups, pruning to keep {keep}...[/yellow]")
    payload = prune_backup_payload(BACKUPS_DIR, keep=keep)
    deleted = payload["deleted"]

    if deleted:
        console.print(f"[green]Deleted {len(deleted)} old backup(s).[/green]")
        for bid in deleted:
            console.print(f"  [dim]- {bid}[/dim]")
    else:
        console.print("[green]No backups needed pruning.[/green]")

    remaining = len(existing) - len(deleted)
    console.print(f"\n[bold]{remaining}[/bold] backup(s) remaining.")


@cli.command()
@click.option(
    "--resolution",
    "-r",
    type=float,
    default=0.5,
    help="Timer resolution in milliseconds (default: 0.5)",
)
@click.option("--keep-alive", "-k", is_flag=True, help="Keep running to maintain timer resolution")
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
            output_json(
                {
                    "current": current.get("current_resolution_ms"),
                    "minimum": current.get(
                        "maximum_resolution_ms"
                    ),  # "maximum" is actually minimum possible
                    "maximum": current.get(
                        "minimum_resolution_ms", 15.625
                    ),  # Default is actually max
                }
            )
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
            console.print("[dim]Use --keep-alive to hold the resolution.[/dim]")
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
            if status.get("task_action_execute") or status.get("task_action_arguments"):
                action_text = (
                    f"{status.get('task_action_execute', '')} "
                    f"{status.get('task_action_arguments', '')}"
                ).strip()
                console.print(f"[bold]Task Action:[/bold] {action_text}")
            if (
                status.get("task_action_path_current") is False
                and not status.get("task_action_path_installed")
            ):
                console.print(
                    "[yellow]Warning: startup task action points at a different tray path.[/yellow]"
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
@click.option(
    "--full-verify",
    is_flag=True,
    help="Include full per-handler profile verification details",
)
@click.option(
    "--full-backups",
    is_flag=True,
    help="Include recent backup rows in the health payload",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def health(
    bundle: bool,
    output_dir: Path | None,
    start_tray_if_missing: bool,
    full_verify: bool,
    full_backups: bool,
    json_output: bool,
) -> None:
    """Generate diagnostics and optional support bundle."""
    import abso.tray as tray_module
    from abso.core.health import build_health_report, write_health_bundle

    report = build_health_report(
        root_dir=ROOT_DIR,
        backups_dir=BACKUPS_DIR,
        state_file=STATE_FILE,
        include_verify_details=bool(full_verify or bundle),
        include_backup_details=bool(full_backups or bundle),
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
    for line in build_health_check_lines(checks):
        console.print(line)

    for line in build_display_context_lines(checks):
        console.print(line)


@cli.command("display-diagnostics")
@click.option(
    "--lookback-minutes",
    default=30,
    show_default=True,
    type=click.IntRange(min=1),
    help="Event-log lookback window for display/driver/power events",
)
@click.option(
    "--max-events",
    default=10,
    show_default=True,
    type=click.IntRange(min=1),
    help="Maximum recent display events to include per sample",
)
@click.option(
    "--event-timeout",
    default=5,
    show_default=True,
    type=click.IntRange(min=1),
    help="Seconds before a display event-log query times out",
)
@click.option(
    "--samples",
    default=1,
    show_default=True,
    type=click.IntRange(min=1),
    help="Number of read-only samples to collect",
)
@click.option(
    "--interval",
    "interval_seconds",
    default=10,
    show_default=True,
    type=click.IntRange(min=0),
    help="Seconds to wait between samples",
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
@click.option(
    "--jsonl",
    is_flag=True,
    help="Stream one JSON object per sample for observation logs",
)
def display_diagnostics(
    lookback_minutes: int,
    max_events: int,
    event_timeout: int,
    samples: int,
    interval_seconds: int,
    json_output: bool,
    jsonl: bool,
) -> None:
    """Sample read-only display diagnostics without touching profile state."""
    if json_output and jsonl:
        raise click.UsageError("--json and --jsonl are mutually exclusive")

    from abso.core.display_diagnostics import iter_display_diagnostic_samples

    payloads: list[dict[str, Any]] = []
    for index, payload in enumerate(
        iter_display_diagnostic_samples(
            samples=samples,
            interval_seconds=interval_seconds,
            lookback_minutes=lookback_minutes,
            max_events=max_events,
            event_timeout_seconds=event_timeout,
            state_targets=_state_file_targets(),
        )
    ):
        if jsonl:
            click.echo(json.dumps({"success": True, "data": payload}, default=json_serial))
            continue

        payloads.append(payload)
        if not json_output:
            if index == 0:
                console.print(Panel("ABSO Display Diagnostics", style="bold blue"))
            if samples > 1:
                console.print(f"[bold]Sample {index + 1}/{samples}[/bold]")
            for line in build_display_diagnostic_report_lines(payload):
                console.print(line)

    if jsonl:
        return

    if json_output:
        data: dict[str, Any]
        if samples == 1:
            data = payloads[0]
        else:
            data = {"read_only": True, "samples": payloads}
        output_json(data)


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
            console.print(
                f"[yellow]Configuration already exists: {config_manager.config_path}[/yellow]"
            )
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
                for attr in [
                    "nvidia",
                    "windows",
                    "graphics",
                    "network",
                    "power",
                    "timer",
                    "mouse",
                    "color",
                    "display_color_range",
                ]:
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
        console.print(
            "  1. Download from [cyan]https://github.com/GameTechDev/PresentMon/releases[/cyan]"
        )
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
            deltas_data = {name: asdict(delta) for name, delta in comparison.deltas.items()}
            output_json(
                {
                    "before": asdict(comparison.before),
                    "after": asdict(comparison.after),
                    "deltas": deltas_data,
                }
            )
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
            output_json(
                {
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
                }
            )
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
                xmp_str += f" ({info.current_speed_mhz} MHz, " f"rated {info.rated_speed_mhz} MHz)"
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
            console.print("  TPM: [dim]Not detected[/dim]")

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
@click.option("--category", default="Other", help="Tray category (Fighting, Shooters, RPGs, etc.)")
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
    if not is_valid_profile_id(profile_id):
        console.print(
            "[red]Profile ID must be a lowercase slug using letters, numbers, "
            "and single hyphens.[/red]"
        )
        sys.exit(1)

    conflict_kind = profile_id_conflict_kind(profile_id)
    if conflict_kind is not None:
        console.print(
            f"[red]Profile ID '{profile_id}' conflicts with an existing "
            f"{conflict_kind}.[/red]"
        )
        sys.exit(1)

    if not is_valid_tray_category(category):
        choices = ", ".join(tray_category_choices())
        console.print(
            f"[red]Tray category '{category}' is not recognized. "
            f"Valid categories: {choices}.[/red]"
        )
        sys.exit(1)

    profiles_dir = Path.home() / ".abso" / "profiles"
    profiles_dir.mkdir(parents=True, exist_ok=True)
    output_path = profiles_dir / f"{profile_id}.yaml"

    if output_path.exists():
        console.print(f"[red]Profile already exists: {output_path}[/red]")
        sys.exit(1)

    yaml_content = build_user_profile_yaml_template(
        profile_id=profile_id,
        game=game,
        exe=exe,
        base=base,
        category=category,
    )
    output_path.write_text(yaml_content, encoding="utf-8")
    console.print(f"[green]Profile created: {output_path}[/green]")
    console.print(
        "Edit the YAML to customize, then run [bold]abso profiles[/bold] to confirm it loads."
    )


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
            output_json(
                {
                    "success": success,
                    "before_available_mb": before["available_mb"],
                    "after_available_mb": after["available_mb"],
                    "freed_mb": after["available_mb"] - before["available_mb"],
                }
            )
        elif success:
            freed = after["available_mb"] - before["available_mb"]
            console.print(
                f"[green]Standby list purged. Freed ~{freed}MB "
                f"({after['available_mb']}MB now available)[/green]"
            )
        else:
            console.print(
                "[red]Failed to purge standby list (privilege escalation may have failed)[/red]"
            )
    except Exception as e:
        if json_output:
            json_error(str(e))
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.option(
    "--tier",
    type=click.IntRange(1, 3),
    required=True,
    help="Debloat tier (1=safe, 2=moderate, 3=aggressive)",
)
@click.option("--dry-run", is_flag=True, help="Show what would be changed without applying")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON")
def debloat(tier: int, dry_run: bool, json_output: bool) -> None:
    """Apply Windows debloat and privacy tweaks.

    Tier 1: Safe telemetry/privacy tweaks (always reversible).
    Tier 2: Moderate tweaks including background app control.
    Tier 3: Aggressive - removes bloatware appx packages (partially irreversible).
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
                output_json(
                    {
                        "tier": tier,
                        "issues": [
                            {
                                "title": i.title,
                                "severity": i.severity,
                                "current": i.current_value,
                                "target": i.optimal_value,
                                "optimal": i.optimal_value,
                            }
                            for i in issues
                        ],
                    }
                )
            else:
                console.print(
                    Panel(
                        f"Debloat Tier {tier} - Dry Run ({len(issues)} items)", style="bold yellow"
                    )
                )
                for issue in issues:
                    console.print(
                        f"  [yellow]{issue.title}[/yellow]: {issue.current_value} -> {issue.optimal_value}"
                    )
            return

        if not json_output:
            console.print(Panel(f"Applying Debloat Tier {tier}", style="bold blue"))
            if tier == 3:
                console.print(
                    "[red]WARNING: Tier 3 removes appx packages. This is partially irreversible.[/red]"
                )

        result = handler.apply({"debloat_tier": tier})

        if json_output:
            output_json(result)
        elif result.get("success"):
            console.print(f"[green]Debloat tier {tier} apply completed.[/green]")
            if result.get("applied"):
                for item in result["applied"]:
                    console.print(f"  [green]+[/green] {item}")
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
@click.option(
    "--system-threshold", type=int, default=85, help="System CPU % to trigger intervention"
)
@click.option("--process-threshold", type=int, default=20, help="Per-process CPU % threshold")
@click.option("--poll-interval", type=int, default=1000, help="Poll interval in ms")
def cpu_balance(
    pid: int, system_threshold: int, process_threshold: int, poll_interval: int
) -> None:
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


@cli.command("launch-killset")
@click.argument("profile_name")
@click.option(
    "--include-opt-in", is_flag=True, help="Include the opt-in tier (cloud sync, OEM RGB, etc.)"
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def launch_killset(profile_name: str, include_opt_in: bool, json_output: bool) -> None:
    """Print the launch-time process killset for a profile (read-only).

    Used by the tray watcher to discover which background processes the
    launch-time janitor would stop while this profile's game is alive. No
    system state is changed by this command.
    """
    try:
        payload = build_launch_killset_payload(profile_name, include_opt_in=include_opt_in)
    except LaunchProfileError as exc:
        if json_output:
            json_error(str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    if json_output:
        output_json(payload)
        return

    canonical = payload["profile"]
    killset = payload["killset"]
    console.print(Panel(f"Launch killset: {canonical}", style="bold blue"))
    console.print(f"Game executables: {', '.join(payload['executables']) or '(none)'}")
    console.print(f"\nAlways-safe images ({len(killset['always_safe'])}):")
    for image in killset["always_safe"]:
        console.print(f"  - {image}")
    if killset["opt_in"]:
        marker = "kill" if include_opt_in else "hold"
        console.print(f"\nOpt-in images ({len(killset['opt_in'])}) [{marker}]:")
        for image in killset["opt_in"]:
            console.print(f"  - {image}")


@cli.command("launch-sweep")
@click.argument("profile_name")
@click.option(
    "--include-opt-in", is_flag=True, help="Also stop opt-in tier (cloud sync, OEM RGB, etc.)"
)
@click.option(
    "--dry-run", is_flag=True, help="Report what would be stopped without invoking taskkill"
)
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def launch_sweep(profile_name: str, include_opt_in: bool, dry_run: bool, json_output: bool) -> None:
    """Sweep launch-time killset processes for an active profile.

    Intended to be called by the tray watcher when the profile's game binary
    is first detected running, and periodically while alive. Stops latency-
    impacting overlay / capture / vendor processes from the always-safe tier
    by default; pass ``--include-opt-in`` to also stop cloud-sync and OEM RGB
    daemons.
    """
    try:
        payload = run_launch_sweep(
            profile_name,
            include_opt_in=include_opt_in,
            dry_run=dry_run,
        )
    except LaunchProfileError as exc:
        if json_output:
            json_error(str(exc))
        else:
            console.print(f"[red]{exc}[/red]")
        sys.exit(1)

    if json_output:
        output_json(payload)
        return

    canonical = payload["profile"]
    result = payload["result"]
    priority_enforcement = payload.get("priority_enforcement")
    if result["notices"] and not result["attempted"]:
        console.print(f"[yellow]{result['notices'][0]}[/yellow]")
        return

    title = f"Launch sweep: {canonical} ({'dry-run' if dry_run else 'live'})"
    console.print(Panel(title, style="bold blue"))
    if result["stopped"]:
        console.print(f"[green]Stopped ({len(result['stopped'])}):[/green]")
        for image in result["stopped"]:
            console.print(f"  - {image}")
    if result["not_running"]:
        console.print(
            f"[dim]Not running ({len(result['not_running'])}): {', '.join(result['not_running'])}[/dim]"
        )
    if result["failed"]:
        console.print(f"[red]Failed ({len(result['failed'])}):[/red]")
        for image in result["failed"]:
            console.print(f"  - {image}")
    if result["warnings"]:
        for warning in result["warnings"]:
            console.print(f"[yellow]Warning:[/yellow] {warning}")
    if priority_enforcement and priority_enforcement.get("targeted"):
        targeted = priority_enforcement["targeted"]
        console.print(
            f"[dim]Re-asserted '{priority_enforcement.get('priority_name', 'High')}' priority on {len(targeted)} live process target(s): {', '.join(targeted)}[/dim]"
        )


@cli.command("reset-display")
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
@click.option(
    "--method",
    type=click.Choice(["auto", "database", "mode-reset", "driver-hotkey"]),
    default="auto",
    show_default=True,
    help="Display recovery method to run.",
)
@click.option(
    "--hotkey-repeat",
    type=click.IntRange(1, 4),
    default=2,
    show_default=True,
    help="Number of Ctrl+Win+Shift+B chords for driver-hotkey.",
)
def reset_display(json_output: bool, method: str, hotkey_repeat: int) -> None:
    """Recover stale DWM / graphics-driver display state.

    ``auto`` uses the least disruptive SetDisplayConfig database reapply.
    Use ``--method driver-hotkey`` explicitly when the heavier documented
    Ctrl+Win+Shift+B graphics-driver reset is needed.
    """
    from abso.utils.display_reset import is_available, refresh_display_pipeline

    if not is_available():
        msg = "Display recovery is not available on this host."
        if json_output:
            json_error(msg)
        else:
            console.print(f"[red]{msg}[/red]")
        sys.exit(1)

    if not json_output:
        console.print(f"[yellow]Running display recovery ({method})...[/yellow]")

    outcome = refresh_display_pipeline(method=method, hotkey_repeat=hotkey_repeat)

    if json_output:
        output_json({"success": outcome.get("success"), "result": outcome})
        return

    if outcome.get("success"):
        selected = outcome.get("method") or method
        sent_count = outcome.get("sent_count")
        suffix = f", sent {sent_count} hotkey combo(s)" if sent_count else ""
        console.print(
            f"[green]Done.[/green] Display recovery used {selected} in "
            f"{outcome.get('elapsed_seconds', 0):.1f}s{suffix}."
        )
    else:
        console.print(f"[red]Refresh failed: {outcome.get('error')}[/red]")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
