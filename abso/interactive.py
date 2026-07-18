"""Interactive CLI interface for computa."""

from __future__ import annotations

import sys
import time
from pathlib import Path

from rich import box
from rich.console import Console
from rich.panel import Panel
from rich.progress import Progress, SpinnerColumn, TextColumn
from rich.prompt import Confirm, Prompt
from rich.table import Table
from rich.text import Text

from abso.core.applier import ProfileApplier
from abso.core.auditor import ConfigurationAuditor
from abso.core.backup import BackupManager
from abso.core.detector import HardwareDetector
from abso.core.transaction import ProfileTransactionManager
from abso.utils.admin import ensure_admin, is_admin

console = Console()

# Paths
ROOT_DIR = Path(__file__).parent.parent
BACKUPS_DIR = ROOT_DIR / "backups"
REPORTS_DIR = ROOT_DIR / "reports"


def clear_screen() -> None:
    """Clear the console screen."""
    console.clear()


def print_header() -> None:
    """Print the application header."""
    header = Text()
    header.append("computa", style="bold cyan")
    header.append(" v0.1.0\n", style="dim")
    header.append("Windows Gaming Optimization Tool", style="italic")

    console.print(Panel(
        header,
        box=box.DOUBLE,
        padding=(1, 2),
        title="[bold white]Welcome[/bold white]",
        subtitle="[dim]github.com/your-repo/abso[/dim]"
    ))
    console.print()


def print_admin_warning() -> None:
    """Print warning if not running as admin."""
    if not is_admin():
        console.print(Panel(
            "[yellow]Warning:[/yellow] Not running as Administrator.\n"
            "Some features require admin privileges to work correctly.\n\n"
            "[dim]Right-click and 'Run as Administrator' for full functionality.[/dim]",
            title="[yellow]Limited Mode[/yellow]",
            border_style="yellow"
        ))
        console.print()


def show_main_menu() -> str:
    """Display the main menu and get user choice."""
    table = Table(show_header=False, box=None, padding=(0, 2))
    table.add_column("Option", style="bold cyan", width=6)
    table.add_column("Description")

    table.add_row("[1]", "Audit System - Scan for optimization opportunities")
    table.add_row("[2]", "Apply Game Profile - Optimize for a specific game")
    table.add_row("[3]", "Detect Hardware - View your gaming hardware")
    table.add_row("[4]", "Restore Backup - Undo previous changes")
    table.add_row("[5]", "View Profiles - See available game profiles")
    table.add_row("")
    table.add_row("[Q]", "Quit")

    console.print(Panel(table, title="[bold]Main Menu[/bold]", border_style="blue"))
    console.print()

    choice = Prompt.ask(
        "[bold]Select an option[/bold]",
        choices=["1", "2", "3", "4", "5", "q", "Q"],
        default="1"
    )

    return choice.lower()


def show_profile_menu() -> str | None:
    """Display profile selection menu and get user choice."""
    applier = ProfileApplier()
    profiles = applier.list_profiles()

    table = Table(show_header=True, box=box.ROUNDED, border_style="cyan")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Profile ID", style="bold")
    table.add_column("Game")
    table.add_column("Focus", style="dim")

    for i, profile in enumerate(profiles, 1):
        table.add_row(
            f"[{i}]",
            profile["id"],
            profile["display_name"],
            profile["optimization_target"].replace("_", " ").title()
        )

    table.add_row("", "", "", "")
    table.add_row("[0]", "Back", "Return to main menu", "")

    console.print(Panel(table, title="[bold]Select Game Profile[/bold]", border_style="cyan"))
    console.print()

    choices = [str(i) for i in range(len(profiles) + 1)]
    choice = Prompt.ask(
        "[bold]Select a profile[/bold]",
        choices=choices,
        default="0"
    )

    if choice == "0":
        return None

    return profiles[int(choice) - 1]["id"]


def run_audit(verbose: bool = True) -> None:
    """Run system audit with visual feedback."""
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as progress:
        task = progress.add_task("Scanning system configuration...", total=None)

        auditor = ConfigurationAuditor()
        issues = auditor.audit_all()

        progress.update(task, description="Analysis complete!")
        time.sleep(0.3)

    if not issues:
        console.print(Panel(
            "[green]No issues were detected by the current audit scope.[/green]\n\n"
            "This audit did not find any configuration gaps to call out.",
            title="[green]Audit Results[/green]",
            border_style="green"
        ))
    else:
        # Count by severity
        warnings = sum(1 for i in issues if i.severity == "warning")
        critical = sum(1 for i in issues if i.severity == "critical")
        info = sum(1 for i in issues if i.severity == "info")

        summary = Text()
        if critical > 0:
            summary.append(f"{critical} critical  ", style="bold red")
        if warnings > 0:
            summary.append(f"{warnings} warnings  ", style="bold yellow")
        if info > 0:
            summary.append(f"{info} suggestions", style="bold blue")

        console.print(Panel(
            summary,
            title=f"[bold]Found {len(issues)} Issue(s)[/bold]",
            border_style="yellow"
        ))
        console.print()

        # Group issues by severity
        for severity, color, icon in [
            ("critical", "red", "[!]"),
            ("warning", "yellow", "[!]"),
            ("info", "blue", "[i]")
        ]:
            severity_issues = [i for i in issues if i.severity == severity]
            if not severity_issues:
                continue

            for issue in severity_issues:
                console.print(f"[{color}]{icon}[/{color}] [bold]{issue.title}[/bold]")
                console.print(f"    Current: [red]{issue.current_value}[/red]")
                console.print(f"    Target: [green]{issue.optimal_value}[/green]")
                if verbose and issue.explanation:
                    console.print(f"    [dim]{issue.explanation}[/dim]")
                console.print()

    console.print()
    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


def run_apply_profile(profile_id: str) -> None:
    """Apply a game profile with progress display and confirmation."""
    applier = ProfileApplier()

    # Get profile info
    try:
        profile = applier._get_profile(profile_id)
    except Exception as e:
        console.print(f"[red]Error:[/red] {e}")
        return

    # Show what will be changed
    console.print()
    console.print(Panel(
        f"[bold]{profile.display_name}[/bold]\n\n"
        f"[dim]{profile.description}[/dim]\n\n"
        f"Target: [cyan]{profile.optimization_target.replace('_', ' ').title()}[/cyan]",
        title="[bold]Profile Details[/bold]",
        border_style="cyan"
    ))
    console.print()

    # List handlers that will be applied
    handlers = profile.get_handlers()
    console.print("[bold]The following optimizations will be applied:[/bold]\n")

    for handler in handlers:
        handler_name = handler.__class__.__name__.replace("SettingsHandler", "").replace("Handler", "")
        settings = profile.get_settings(handler.__class__.__name__)
        if settings:
            console.print(f"  [cyan]\u2022[/cyan] {handler_name} settings")

    console.print()

    if not is_admin():
        console.print(Panel(
            "[red]Administrator privileges are required to apply a profile.[/red]\n\n"
            "Run computa as Administrator so backup, preflight, apply, verify, and rollback "
            "all operate through the same protected transaction path.",
            title="[red]Apply Blocked[/red]",
            border_style="red",
        ))
        Prompt.ask("[dim]Press Enter to continue[/dim]", default="")
        return

    if not Confirm.ask("[bold]Proceed with applying this profile?[/bold]", default=True):
        console.print("[dim]Cancelled.[/dim]")
        return

    console.print()
    BACKUPS_DIR.mkdir(parents=True, exist_ok=True)

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Running transactional apply...", total=None)
        tx_manager = ProfileTransactionManager(BACKUPS_DIR, applier=applier)
        tx = tx_manager.execute(profile_id=profile_id, create_backup=True)
        if tx.success:
            progress.update(task, description="[green][OK][/green] Transaction committed")
        else:
            progress.update(task, description="[red][X][/red] Transaction failed")
        progress.stop_task(task)

    console.print()

    result = tx.apply_result
    tx_profile_id = getattr(tx, "profile_id", None)
    actual_profile_id = (
        tx_profile_id
        if isinstance(tx_profile_id, str) and tx_profile_id.strip()
        else profile_id
    )
    fallback_chain = getattr(tx, "fallback_chain", None)
    fallback_applied = isinstance(fallback_chain, list) and bool(fallback_chain)
    fallback_note = ""
    if fallback_applied and actual_profile_id != profile_id:
        fallback_note = (
            f"\n[yellow]Requested '{profile_id}' was blocked; "
            f"applied safe fallback '{actual_profile_id}' instead.[/yellow]\n"
        )

    if tx.success and result and result.success:
        try:
            from abso.main import set_current_profile

            set_current_profile(
                actual_profile_id,
                requires_reboot=result.requires_reboot,
                reboot_reasons=result.reboot_reasons,
            )
        except Exception as e:
            console.print(f"[yellow]Warning:[/yellow] Could not persist active profile state: {e}")

        console.print(Panel(
            f"[green]Profile '{actual_profile_id}' apply completed.[/green]\n"
            f"{fallback_note}\n"
            f"[dim]Backup ID: {tx.backup_id or 'not created'}[/dim]\n"
            f"[dim]Run 'computa verify {actual_profile_id}' to confirm handler state.[/dim]\n"
            f"[dim]Use 'Restore Backup' to undo changes if needed.[/dim]",
            title="[green]Apply Completed[/green]",
            border_style="green"
        ))

        for warning in result.warnings:
            console.print(f"[yellow]Warning:[/yellow] {warning}")
        for notice in result.notices:
            console.print(f"[cyan]Note:[/cyan] {notice}")
    else:
        failed_settings = result.failed_settings if result else []
        console.print(Panel(
            f"[red]Profile apply did not commit.[/red]\n\n"
            f"[dim]{tx.error or (result.error if result else 'Unknown error')}[/dim]",
            title="[red]Apply Failed[/red]",
            border_style="red"
        ))
        for failed in failed_settings:
            console.print(f"[red]Failed:[/red] {failed}")
        if tx.rollback_performed:
            console.print("[yellow]Rollback:[/yellow] Pre-apply snapshot restored automatically.")
        elif tx.rollback_error:
            console.print(f"[red]Rollback failed:[/red] {tx.rollback_error}")

    for checkpoint in tx.checkpoints:
        console.print(f"[dim]{checkpoint.phase}: {checkpoint.status} - {checkpoint.message}[/dim]")

    if result and result.requires_reboot:
        console.print()
        if result.reboot_reasons:
            console.print("[yellow]Reboot required for:[/yellow] " + ", ".join(result.reboot_reasons))
        else:
            console.print("[yellow]Some changes may require a reboot.[/yellow]")

    # Generate in-game settings report
    if tx.success and result and result.success and profile.has_in_game_settings():
        console.print()
        if Confirm.ask("Generate in-game settings recommendations?", default=True):
            REPORTS_DIR.mkdir(parents=True, exist_ok=True)
            report_path = applier.generate_report(actual_profile_id, REPORTS_DIR)
            console.print(f"[green]\u2713[/green] Report saved to: [cyan]{report_path}[/cyan]")

    console.print()
    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


def run_detect_hardware() -> None:
    """Detect and display hardware information."""
    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        transient=True,
        console=console
    ) as progress:
        task = progress.add_task("Detecting hardware...", total=None)

        detector = HardwareDetector()
        hardware = detector.detect_all()

        progress.update(task, description="Detection complete!")
        time.sleep(0.3)

    # GPU
    console.print(Panel.fit("[bold cyan]GPU[/bold cyan]", border_style="cyan"))
    if hardware.get("gpu"):
        gpu = hardware["gpu"]
        console.print(f"  Name:   [bold]{gpu.get('name', 'Unknown')}[/bold]")
        console.print(f"  Driver: {gpu.get('driver_version', 'Unknown')}")
        console.print(f"  VRAM:   {gpu.get('vram_mb', 'Unknown')} MB")
    else:
        console.print("  [red]Not detected[/red]")
    console.print()

    # CPU
    console.print(Panel.fit("[bold cyan]CPU[/bold cyan]", border_style="cyan"))
    if hardware.get("cpu"):
        cpu = hardware["cpu"]
        console.print(f"  Name:    [bold]{cpu.get('name', 'Unknown')}[/bold]")
        console.print(f"  Cores:   {cpu.get('cores', 'Unknown')}")
        console.print(f"  Threads: {cpu.get('threads', 'Unknown')}")
    else:
        console.print("  [red]Not detected[/red]")
    console.print()

    # RAM
    console.print(Panel.fit("[bold cyan]RAM[/bold cyan]", border_style="cyan"))
    if hardware.get("ram"):
        console.print(f"  Total: [bold]{hardware['ram'].get('total_gb', 'Unknown')} GB[/bold]")
    else:
        console.print("  [red]Not detected[/red]")
    console.print()

    # Monitors
    console.print(Panel.fit("[bold cyan]Monitors[/bold cyan]", border_style="cyan"))
    if hardware.get("monitors"):
        for i, monitor in enumerate(hardware["monitors"], 1):
            primary = " [green](Primary)[/green]" if monitor.get('is_primary') else ""
            console.print(f"  [{i}] [bold]{monitor.get('name', 'Unknown')}[/bold]{primary}")
            console.print(f"      Resolution:   {monitor.get('resolution', 'Unknown')}")
            refresh_str = f"{monitor.get('refresh_rate', 'Unknown')} Hz"
            max_refresh = monitor.get('max_refresh_rate')
            max_capability = monitor.get('max_refresh_capability')
            if max_refresh:
                refresh_str += f" [yellow](Max @ res: {max_refresh} Hz)[/yellow]"
            elif max_capability:
                refresh_str += f" [yellow](Supports up to {max_capability} Hz)[/yellow]"
            console.print(f"      Refresh Rate: {refresh_str}")

            vrr = monitor.get('vrr_supported')
            vrr_type = monitor.get('vrr_type')
            if vrr is True:
                vrr_label = vrr_type.upper() if vrr_type else "VRR"
                console.print(f"      G-Sync/VRR:   [green]{vrr_label}[/green]")
            elif vrr == "likely":
                console.print("      G-Sync/VRR:   [yellow]Likely (high refresh)[/yellow]")
            else:
                console.print("      G-Sync/VRR:   [dim]Unknown[/dim]")
            console.print()
    else:
        console.print("  [red]Not detected[/red]")

    console.print()
    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


def run_restore_backup() -> None:
    """Restore from a backup."""
    console.print()

    if not BACKUPS_DIR.exists():
        console.print(Panel(
            "[yellow]No backups found.[/yellow]\n\n"
            "Backups are created automatically when applying profiles.",
            title="[yellow]No Backups[/yellow]",
            border_style="yellow"
        ))
        console.print()
        Prompt.ask("[dim]Press Enter to continue[/dim]", default="")
        return

    backup_manager = BackupManager(BACKUPS_DIR)

    # List available backups
    backups = sorted(BACKUPS_DIR.glob("backup_*"), reverse=True)

    if not backups:
        console.print(Panel(
            "[yellow]No backups found.[/yellow]",
            border_style="yellow"
        ))
        console.print()
        Prompt.ask("[dim]Press Enter to continue[/dim]", default="")
        return

    table = Table(show_header=True, box=box.ROUNDED, border_style="cyan")
    table.add_column("#", style="bold cyan", width=4)
    table.add_column("Backup ID")
    table.add_column("Date/Time", style="dim")

    backup_ids = []
    for i, backup_path in enumerate(backups[:10], 1):  # Show last 10
        backup_id = backup_path.name.replace("backup_", "")
        backup_ids.append(backup_id)

        # Parse timestamp from backup ID format: YYYYMMDD_HHMMSS
        try:
            date_str = f"{backup_id[:4]}-{backup_id[4:6]}-{backup_id[6:8]}"
            time_str = f"{backup_id[9:11]}:{backup_id[11:13]}:{backup_id[13:15]}"
            display_time = f"{date_str} {time_str}"
        except (IndexError, ValueError):
            display_time = backup_id

        table.add_row(f"[{i}]", backup_id, display_time)

    table.add_row("", "", "")
    table.add_row("[0]", "Cancel", "Return to main menu")

    console.print(Panel(table, title="[bold]Available Backups[/bold]", border_style="cyan"))
    console.print()

    choices = [str(i) for i in range(len(backup_ids) + 1)]
    choice = Prompt.ask(
        "[bold]Select backup to restore[/bold]",
        choices=choices,
        default="0"
    )

    if choice == "0":
        return

    selected_backup = backup_ids[int(choice) - 1]

    console.print()
    console.print(f"[yellow]Warning:[/yellow] This will restore settings from backup [cyan]{selected_backup}[/cyan]")
    console.print()

    if not Confirm.ask("[bold]Proceed with restore?[/bold]", default=False):
        console.print("[dim]Cancelled.[/dim]")
        return

    console.print()

    with Progress(
        SpinnerColumn(),
        TextColumn("[progress.description]{task.description}"),
        console=console
    ) as progress:
        task = progress.add_task("Restoring backup...", total=None)

        try:
            restore_summary = backup_manager.restore_backup(selected_backup)
            if restore_summary.complete:
                progress.update(task, description="[green]\u2713[/green] Restore completed for fully restorable handlers")
            else:
                incomplete = restore_summary.failed_components + restore_summary.skipped_components
                handlers = ", ".join(item["handler"] for item in incomplete)
                progress.update(
                    task,
                    description=f"[yellow]![/yellow] Restore incomplete: {handlers}",
                )
        except Exception as e:
            progress.update(task, description=f"[red]\u2717[/red] Restore failed: {e}")

    console.print()
    console.print("[yellow]Note:[/yellow] Some changes may require a reboot to take effect.")
    console.print()
    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


def show_profiles_info() -> None:
    """Display detailed information about available profiles."""
    applier = ProfileApplier()
    profiles = applier.list_profiles()

    console.print()

    for profile_info in profiles:
        profile = applier._get_profile(profile_info["id"])

        # Header
        console.print(Panel(
            f"[bold]{profile.display_name}[/bold]\n"
            f"[dim]{profile.description}[/dim]",
            title=f"[cyan]{profile_info['id']}[/cyan]",
            border_style="cyan"
        ))

        # Optimizations applied
        handlers = profile.get_handlers()
        handler_names = []
        for handler in handlers:
            name = handler.__class__.__name__.replace("SettingsHandler", "").replace("Handler", "")
            settings = profile.get_settings(handler.__class__.__name__)
            if settings:
                handler_names.append(name)

        console.print(f"  [bold]Optimizations:[/bold] {', '.join(handler_names)}")
        console.print(f"  [bold]Target:[/bold] {profile.optimization_target.replace('_', ' ').title()}")
        console.print(f"  [bold]Executables:[/bold] {', '.join(profile.executable_hints)}")
        console.print()

    Prompt.ask("[dim]Press Enter to continue[/dim]", default="")


def run_interactive() -> None:
    """Main interactive loop."""
    # Check for admin on startup
    if not is_admin():
        console.print()
        console.print("[yellow]computa works best when run as Administrator.[/yellow]")
        console.print("[dim]Some optimizations require elevated privileges.[/dim]")
        console.print()

        if Confirm.ask("Restart as Administrator?", default=True):
            ensure_admin()
            sys.exit(0)

    while True:
        clear_screen()
        print_header()
        print_admin_warning()

        choice = show_main_menu()

        if choice == "1":
            clear_screen()
            console.print(Panel("[bold]System Audit[/bold]", border_style="blue"))
            run_audit()

        elif choice == "2":
            clear_screen()
            console.print(Panel("[bold]Apply Game Profile[/bold]", border_style="cyan"))
            profile_id = show_profile_menu()
            if profile_id:
                clear_screen()
                console.print(Panel(f"[bold]Applying: {profile_id}[/bold]", border_style="cyan"))
                run_apply_profile(profile_id)

        elif choice == "3":
            clear_screen()
            console.print(Panel("[bold]Hardware Detection[/bold]", border_style="blue"))
            run_detect_hardware()

        elif choice == "4":
            clear_screen()
            console.print(Panel("[bold]Restore Backup[/bold]", border_style="yellow"))
            run_restore_backup()

        elif choice == "5":
            clear_screen()
            console.print(Panel("[bold]Available Profiles[/bold]", border_style="cyan"))
            show_profiles_info()

        elif choice == "q":
            clear_screen()
            console.print("[bold cyan]Thanks for using computa![/bold cyan]")
            console.print("[dim]No further changes were made.[/dim]")
            console.print()
            break


if __name__ == "__main__":
    run_interactive()
