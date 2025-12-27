"""CLI entry point for GameTune."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from gametune.utils.admin import ensure_admin, is_admin
from gametune.core.detector import HardwareDetector
from gametune.core.auditor import ConfigurationAuditor
from gametune.core.applier import ProfileApplier
from gametune.core.backup import BackupManager

console = Console()

# Paths
ROOT_DIR = Path(__file__).parent.parent
BACKUPS_DIR = ROOT_DIR / "backups"
REPORTS_DIR = ROOT_DIR / "reports"


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="GameTune")
@click.pass_context
def cli(ctx) -> None:
    """GameTune - Windows Gaming Optimization Tool.

    Detect hardware, audit configuration, and apply game-specific
    optimization profiles for competitive gaming.

    Run without arguments to launch interactive mode.
    """
    # If no command is given, run interactive mode
    if ctx.invoked_subcommand is None:
        from gametune.interactive import run_interactive
        run_interactive()


@cli.command()
def interactive() -> None:
    """Launch interactive menu mode (default when run without arguments)."""
    from gametune.interactive import run_interactive
    run_interactive()


@cli.command()
def detect() -> None:
    """Detect and report gaming hardware."""
    if not is_admin():
        console.print("[yellow]Warning: Running without admin privileges. Some detection may be limited.[/yellow]")

    console.print(Panel("Hardware Detection", style="bold blue"))

    detector = HardwareDetector()
    hardware = detector.detect_all()

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
            console.print(f"      Refresh Rate: {monitor.get('refresh_rate', 'Unknown')} Hz")
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


@cli.command()
@click.option("--verbose", "-v", is_flag=True, help="Show detailed explanations")
def audit(verbose: bool) -> None:
    """Audit current system configuration for gaming optimization."""
    if not is_admin():
        console.print("[red]Error: Admin privileges required for full audit.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    console.print(Panel("Configuration Audit", style="bold blue"))

    auditor = ConfigurationAuditor()
    issues = auditor.audit_all()

    if not issues:
        console.print("[green]No issues found! Your system appears optimally configured.[/green]")
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
def profiles() -> None:
    """List available game optimization profiles."""
    console.print(Panel("Available Profiles", style="bold blue"))

    available_profiles = [
        ("slippi-melee", "Super Smash Bros. Melee (Slippi)", "Ultra-low latency"),
        ("rivals2", "Rivals of Aether 2", "Ultra-low latency"),
        ("cod-bo7", "Call of Duty: Black Ops 7", "Low latency, stable FPS"),
        ("diablo4", "Diablo 4", "Balanced performance"),
    ]

    for profile_id, name, focus in available_profiles:
        console.print(f"\n[bold cyan]{profile_id}[/bold cyan]")
        console.print(f"  {name}")
        console.print(f"  [dim]Focus: {focus}[/dim]")


@cli.command()
@click.argument("profile_name")
@click.option("--no-backup", is_flag=True, help="Skip automatic backup (not recommended)")
def apply(profile_name: str, no_backup: bool) -> None:
    """Apply a game optimization profile.

    PROFILE_NAME is the profile to apply (e.g., slippi-melee, cod-bo7, diablo4).
    """
    if not is_admin():
        console.print("[red]Error: Admin privileges required to apply profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    console.print(Panel(f"Applying Profile: {profile_name}", style="bold blue"))

    # Create backup first (unless explicitly skipped)
    if not no_backup:
        console.print("[yellow]Creating backup before applying changes...[/yellow]")
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        backup_manager = BackupManager(BACKUPS_DIR)
        backup_id = backup_manager.create_backup()
        console.print(f"[green]Backup created: {backup_id}[/green]\n")
    else:
        console.print("[yellow]Warning: Skipping backup as requested.[/yellow]\n")

    applier = ProfileApplier()

    try:
        result = applier.apply_profile(profile_name)

        if result.success:
            console.print(f"\n[green]Profile '{profile_name}' applied successfully![/green]")

            if result.requires_reboot:
                console.print("[yellow]Note: Some changes require a reboot to take effect.[/yellow]")

            if result.in_game_settings:
                console.print(f"\n[cyan]In-game settings saved to: {REPORTS_DIR / f'{profile_name}_settings.md'}[/cyan]")
        else:
            console.print(f"\n[red]Failed to apply profile: {result.error}[/red]")
            sys.exit(1)

    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("backup_id", default="latest")
def restore(backup_id: str) -> None:
    """Restore system settings from a backup.

    BACKUP_ID is the backup timestamp or 'latest' for most recent.
    """
    if not is_admin():
        console.print("[red]Error: Admin privileges required to restore settings.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    console.print(Panel(f"Restoring Backup: {backup_id}", style="bold blue"))

    backup_manager = BackupManager(BACKUPS_DIR)

    try:
        backup_manager.restore_backup(backup_id)
        console.print(f"\n[green]Backup '{backup_id}' restored successfully![/green]")
        console.print("[yellow]Note: Some changes may require a reboot to take effect.[/yellow]")
    except FileNotFoundError:
        console.print(f"[red]Error: Backup '{backup_id}' not found.[/red]")
        sys.exit(1)
    except Exception as e:
        console.print(f"[red]Error restoring backup: {e}[/red]")
        sys.exit(1)


@cli.command()
@click.argument("profile_name")
def report(profile_name: str) -> None:
    """Generate in-game settings report for a profile.

    PROFILE_NAME is the profile to generate report for.
    """
    REPORTS_DIR.mkdir(parents=True, exist_ok=True)

    applier = ProfileApplier()

    try:
        report_path = applier.generate_report(profile_name, REPORTS_DIR)
        console.print(f"[green]Report generated: {report_path}[/green]")
    except ValueError as e:
        console.print(f"[red]Error: {e}[/red]")
        sys.exit(1)


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
