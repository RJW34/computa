"""CLI entry point for ABSO."""

import json
import sys
from dataclasses import asdict
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
from abso.utils.admin import is_admin

console = Console()

# Paths - handle both development and PyInstaller bundled modes
def get_data_dir() -> Path:
    """Get the data directory for backups and reports.

    In development: uses project root
    When bundled: uses user's AppData/Local/ABSO
    """
    import sys

    # Check if running as PyInstaller bundle
    if getattr(sys, 'frozen', False):
        # Running as bundled exe - use AppData
        app_data = Path.home() / "AppData" / "Local" / "ABSO"
        app_data.mkdir(parents=True, exist_ok=True)
        return app_data
    else:
        # Development mode - use project root
        return Path(__file__).parent.parent

ROOT_DIR = get_data_dir()
BACKUPS_DIR = ROOT_DIR / "backups"
REPORTS_DIR = ROOT_DIR / "reports"


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
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def detect(json_output: bool) -> None:
    """Detect and report gaming hardware."""
    if not json_output and not is_admin():
        console.print("[yellow]Warning: Running without admin privileges. Some detection may be limited.[/yellow]")

    detector = HardwareDetector()
    hardware = detector.detect_all()

    # JSON output mode
    if json_output:
        # Flatten for GUI consumption
        output_data = {
            "gpu": hardware.get("gpu"),
            "cpu": hardware.get("cpu"),
            "ram_gb": hardware.get("ram", {}).get("total_gb"),
            "monitors": hardware.get("monitors", []),
            "is_admin": is_admin(),
        }
        output_json(output_data)
        return

    # Rich console output
    console.print(Panel("Hardware Detection", style="bold blue"))

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
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def profiles(json_output: bool) -> None:
    """List available game optimization profiles."""
    available_profiles = [
        {
            "id": "slippi-melee",
            "display_name": "Super Smash Bros. Melee (Slippi)",
            "description": "Ultra-low latency for competitive SSBM",
            "optimization_target": "minimum_latency",
            "executables": ["Slippi Dolphin.exe", "Dolphin.exe"],
        },
        {
            "id": "rivals2",
            "display_name": "Rivals of Aether 2",
            "description": "VRR-optimized for UE5 fighting game",
            "optimization_target": "vrr_fighting_game",
            "executables": ["RivalsofAether2.exe", "Rivals2.exe"],
        },
        {
            "id": "cod-bo7",
            "display_name": "Call of Duty: Black Ops 7",
            "description": "Low latency with Nvidia Reflex",
            "optimization_target": "low_latency_high_fps",
            "executables": ["cod.exe", "BlackOps7.exe"],
        },
        {
            "id": "diablo4",
            "display_name": "Diablo 4",
            "description": "Balanced performance for ARPG",
            "optimization_target": "balanced",
            "executables": ["Diablo IV.exe"],
        },
    ]

    if json_output:
        output_json(available_profiles)
        return

    console.print(Panel("Available Profiles", style="bold blue"))

    for profile in available_profiles:
        console.print(f"\n[bold cyan]{profile['id']}[/bold cyan]")
        console.print(f"  {profile['display_name']}")
        console.print(f"  [dim]Focus: {profile['description']}[/dim]")


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
        console.print("  - Call of Duty: Black Ops 7")
        console.print("  - Diablo IV")
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
@click.option("--json", "json_output", is_flag=True, help="Output as JSON for GUI integration")
def apply(profile_name: str, no_backup: bool, json_output: bool) -> None:
    """Apply a game optimization profile.

    PROFILE_NAME is the profile to apply (e.g., slippi-melee, cod-bo7, diablo4).
    """
    if not is_admin():
        if json_output:
            json_error("Admin privileges required to apply profiles")
        console.print("[red]Error: Admin privileges required to apply profiles.[/red]")
        console.print("Please run as administrator.")
        sys.exit(1)

    backup_id = None

    if not json_output:
        console.print(Panel(f"Applying Profile: {profile_name}", style="bold blue"))

    # Create backup first (unless explicitly skipped)
    if not no_backup:
        if not json_output:
            console.print("[yellow]Creating backup before applying changes...[/yellow]")
        BACKUPS_DIR.mkdir(parents=True, exist_ok=True)
        backup_manager = BackupManager(BACKUPS_DIR)
        backup_id = backup_manager.create_backup()
        if not json_output:
            console.print(f"[green]Backup created: {backup_id}[/green]\n")
    else:
        if not json_output:
            console.print("[yellow]Warning: Skipping backup as requested.[/yellow]\n")

    applier = ProfileApplier()

    try:
        result = applier.apply_profile(profile_name)

        if json_output:
            output_json({
                "success": result.success,
                "profile": profile_name,
                "backup_id": backup_id,
                "requires_reboot": result.requires_reboot,
                "in_game_settings": result.in_game_settings if hasattr(result, "in_game_settings") else [],
                "error": result.error if not result.success else None,
            })
            return

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
        backup_manager.restore_backup(backup_id)
        if json_output:
            output_json({"success": True, "backup_id": backup_id, "message": "Backup restored successfully"})
            return
        console.print(f"\n[green]Backup '{backup_id}' restored successfully![/green]")
        console.print("[yellow]Note: Some changes may require a reboot to take effect.[/yellow]")
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


def main() -> None:
    """Main entry point."""
    cli()


if __name__ == "__main__":
    main()
