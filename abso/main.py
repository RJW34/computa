"""CLI entry point for ABSO."""

import sys
from pathlib import Path

import click
from rich.console import Console
from rich.panel import Panel

from abso.core.applier import ProfileApplier
from abso.core.auditor import ConfigurationAuditor
from abso.core.backup import BackupManager
from abso.core.detector import HardwareDetector
from abso.utils.admin import is_admin

console = Console()

# Paths
ROOT_DIR = Path(__file__).parent.parent
BACKUPS_DIR = ROOT_DIR / "backups"
REPORTS_DIR = ROOT_DIR / "reports"


@click.group(invoke_without_command=True)
@click.version_option(version="0.1.0", prog_name="ABSO")
@click.pass_context
def cli(ctx) -> None:
    """ABSO - Windows Gaming Optimization Tool.

    Detect hardware, audit configuration, and apply game-specific
    optimization profiles for competitive gaming.

    Run without arguments to launch interactive mode.
    """
    # If no command is given, run interactive mode
    if ctx.invoked_subcommand is None:
        from abso.interactive import run_interactive
        run_interactive()


@cli.command()
def interactive() -> None:
    """Launch interactive menu mode (default when run without arguments)."""
    from abso.interactive import run_interactive
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
def games() -> None:
    """Detect installed games and suggest matching profiles."""
    from abso.core.game_detector import detect_installed_games, get_profile_suggestions

    console.print(Panel("Game Detection", style="bold blue"))
    console.print("[dim]Scanning for installed games...[/dim]\n")

    games = detect_installed_games()

    if not games:
        console.print("[yellow]No supported games detected.[/yellow]")
        console.print("\nSupported games:")
        console.print("  - Super Smash Bros. Melee (Slippi)")
        console.print("  - Rivals of Aether 2")
        console.print("  - Call of Duty: Black Ops 7")
        console.print("  - Diablo IV")
        return

    console.print(f"[green]Found {len(games)} game(s):[/green]\n")

    for game in games:
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
        console.print(f"\nRun [bold]abso apply <profile>[/bold] to optimize.")


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
@click.option("--resolution", "-r", type=float, default=0.5,
              help="Timer resolution in milliseconds (default: 0.5)")
@click.option("--keep-alive", "-k", is_flag=True,
              help="Keep running to maintain timer resolution")
def timer(resolution: float, keep_alive: bool) -> None:
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
        console.print("[red]Error: Timer resolution API not available.[/red]")
        sys.exit(1)

    console.print(Panel("Timer Resolution", style="bold blue"))
    console.print(f"Current: {current.get('current_resolution_ms', 'Unknown'):.3f}ms")
    console.print(f"Minimum: {current.get('maximum_resolution_ms', 'Unknown'):.3f}ms")
    console.print()

    # Set the resolution
    result = handler.apply({"resolution_ms": resolution})

    if result.get("success"):
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
        console.print(f"[red]Failed to set timer resolution: {result.get('error')}[/red]")
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
            console.print(f"Run [bold]abso config --init[/bold] to create one.")
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


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
