"""First-run interactive setup wizard."""

from __future__ import annotations

import json
import logging
import os
import time
from datetime import datetime
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
from abso.core.kb_checker import check_problematic_kbs, get_installed_kbs, uninstall_kb
from abso.utils.admin import is_admin

console = Console()


def _get_data_dir() -> Path:
    """Get the data directory (mirrors main.py logic)."""
    import sys

    if getattr(sys, "frozen", False):
        app_data = Path.home() / "AppData" / "Local" / "AdaptiveBattleStationOptimizer"
        app_data.mkdir(parents=True, exist_ok=True)
        return app_data
    else:
        return Path(__file__).parent.parent.parent


def _get_state_file() -> Path:
    return _get_data_dir() / ".abso_state.json"


def is_first_run() -> bool:
    """Check if this is the first time ABSO is being run."""
    return not _get_state_file().exists()


class SetupWizard:
    """Interactive first-run setup wizard."""

    def __init__(self) -> None:
        self.data_dir = _get_data_dir()
        self.backups_dir = self.data_dir / "backups"
        self.reports_dir = self.data_dir / "reports"
        self.state_file = self.data_dir / ".abso_state.json"
        self.needs_reboot = False
        self.reboot_reasons: list[str] = []
        self.fixes_applied = 0
        self.kbs_uninstalled = 0
        self.profile_applied: str | None = None

    def run(self) -> None:
        """Run the full setup wizard."""
        self._print_welcome()

        # Step 1: Hardware detection
        hardware = self._step_hardware_detection()

        # Step 2: KB check
        self._step_kb_check()

        # Step 3: System audit
        self._step_system_audit()

        # Step 4: Game detection
        suggestions = self._step_game_detection()

        # Step 5: Profile selection
        profile_id = self._step_profile_selection(suggestions)

        # Step 6: Apply
        if profile_id:
            self._step_apply_profile(profile_id)

        # Summary
        self._print_summary()

    def _print_welcome(self) -> None:
        header = Text()
        header.append("A.B.S.O.", style="bold cyan")
        header.append(" v2.0.0\n", style="dim")
        header.append("Adaptive Battle Station Optimizer\n", style="italic")
        header.append("First-time setup wizard", style="dim")

        console.print()
        console.print(Panel(
            header,
            box=box.DOUBLE,
            padding=(1, 2),
            border_style="cyan",
        ))
        console.print()

    def _step_hardware_detection(self) -> dict:
        console.print("[bold cyan]Step 1: HARDWARE DETECTION[/bold cyan]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Detecting hardware...", total=None)
            detector = HardwareDetector()
            hardware = detector.detect_all()
            progress.update(task, description="Detection complete!")
            time.sleep(0.3)

        # Display summary line
        parts = []
        if hardware.get("gpu"):
            parts.append(f"GPU: {hardware['gpu'].get('name', 'Unknown')}")
        if hardware.get("cpu"):
            parts.append(f"CPU: {hardware['cpu'].get('name', 'Unknown')}")
        if hardware.get("ram"):
            parts.append(f"RAM: {hardware['ram'].get('total_gb', '?')}GB")
        if hardware.get("monitors"):
            mon = hardware["monitors"][0]
            refresh = mon.get("refresh_rate", "?")
            parts.append(f"Monitor: {mon.get('name', 'Unknown')} @ {refresh}Hz")

        for part in parts:
            console.print(f"  {part}")

        # GPU type note
        if hardware.get("gpu"):
            gpu_name = hardware["gpu"].get("name", "").upper()
            if "NVIDIA" in gpu_name or "GEFORCE" in gpu_name or "RTX" in gpu_name or "GTX" in gpu_name:
                console.print("  [green]NVIDIA GPU detected — full optimization available[/green]")

        console.print()
        return hardware

    def _step_kb_check(self) -> None:
        console.print("[bold cyan]Step 2: WINDOWS UPDATE CHECK[/bold cyan]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Checking for problematic updates...", total=None)
            installed_kbs = get_installed_kbs()
            bad_kbs = check_problematic_kbs(installed_kbs)
            progress.update(task, description="Check complete!")
            time.sleep(0.2)

        if not bad_kbs:
            console.print("  [green]No problematic Windows updates found.[/green]")
            console.print()
            return

        for kb in bad_kbs:
            console.print(f"  [yellow]Found {kb.kb_id}[/yellow] — {kb.title} ({kb.affected})")

            if Confirm.ask(f"  Uninstall {kb.kb_id}?", default=True):
                with Progress(
                    SpinnerColumn(),
                    TextColumn("[progress.description]{task.description}"),
                    transient=True,
                    console=console,
                ) as progress:
                    t = progress.add_task(f"Uninstalling {kb.kb_id}...", total=None)
                    success = uninstall_kb(kb.kb_id)
                    progress.update(t, description="Done!")

                if success:
                    console.print(f"  [green]Uninstalled {kb.kb_id}.[/green] Reboot needed after setup.")
                    self.needs_reboot = True
                    self.reboot_reasons.append(f"{kb.kb_id} removal")
                    self.kbs_uninstalled += 1
                else:
                    console.print(f"  [red]Failed to uninstall {kb.kb_id}.[/red]")
            else:
                console.print(f"  [dim]Skipped {kb.kb_id}.[/dim]")

        console.print()

    def _step_system_audit(self) -> None:
        console.print("[bold cyan]Step 3: SYSTEM AUDIT[/bold cyan]")
        console.print()

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            transient=True,
            console=console,
        ) as progress:
            task = progress.add_task("Auditing system configuration...", total=None)
            auditor = ConfigurationAuditor()
            issues = auditor.audit_all()
            progress.update(task, description="Audit complete!")
            time.sleep(0.2)

        if not issues:
            console.print("  [green]No issues were detected by the current audit scope.[/green]")
            console.print()
            return

        # Show issues in a table
        table = Table(box=box.SIMPLE, padding=(0, 1))
        table.add_column("Issue", style="bold")
        table.add_column("Severity")
        table.add_column("Current -> Fix", style="dim")

        for issue in issues:
            severity_color = {"critical": "red", "warning": "yellow", "info": "blue"}.get(
                issue.severity, "white"
            )
            table.add_row(
                issue.title,
                f"[{severity_color}]{issue.severity}[/{severity_color}]",
                f"{issue.current_value} -> {issue.optimal_value}",
            )

        console.print(table)
        console.print()
        console.print(f"  Found [bold]{len(issues)}[/bold] issue(s).")

        # Ask to fix each issue individually would be too verbose for 15+ issues.
        # Instead, ask once to fix all, matching the plan's y/n approach.
        fixable_count = sum(1 for i in issues if i.severity in ("critical", "warning"))
        if fixable_count > 0:
            if Confirm.ask(f"  Fix these {fixable_count} issues?", default=True):
                console.print("  [dim]Issues will be fixed when a profile is applied.[/dim]")
                self.fixes_applied = fixable_count
            else:
                console.print("  [dim]Skipped. You can run 'abso audit' later.[/dim]")

        console.print()

    def _step_game_detection(self) -> dict[str, str]:
        """Detect installed games and return profile suggestions.

        Returns:
            Dict mapping display string to profile ID.
        """
        console.print("[bold cyan]Step 4: GAME DETECTION[/bold cyan]")
        console.print()

        try:
            from abso.core.game_detector import detect_installed_games, get_profile_suggestions

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=console,
            ) as progress:
                task = progress.add_task("Scanning for installed games...", total=None)
                suggestions = get_profile_suggestions()
                progress.update(task, description="Scan complete!")
                time.sleep(0.2)

            if not suggestions:
                console.print("  [dim]No supported games detected.[/dim]")
                console.print("  [dim]You can manually apply a profile with 'abso apply <profile>'.[/dim]")
                console.print()
                return {}

            result: dict[str, str] = {}
            idx = 1
            for profile_name, matched_games in suggestions.items():
                game_names = ", ".join(g.name for g in matched_games)
                display = f"{game_names} -> {profile_name}"
                console.print(f"  {idx}. {display}")
                result[display] = profile_name
                idx += 1

            console.print()
            return result

        except Exception as e:
            console.print(f"  [dim]Game detection unavailable: {e}[/dim]")
            console.print()
            return {}

    def _step_profile_selection(self, suggestions: dict[str, str]) -> str | None:
        console.print("[bold cyan]Step 5: PROFILE SELECTION[/bold cyan]")
        console.print()

        # Build list of choices: detected games + full profile list
        applier = ProfileApplier()
        all_profiles = applier.list_profiles()

        # Suggested profiles first
        choices: list[tuple[str, str]] = []
        suggested_ids = set()

        for display, profile_id in suggestions.items():
            choices.append((profile_id, display))
            suggested_ids.add(profile_id)

        # Add remaining profiles
        for p in all_profiles:
            if p["id"] not in suggested_ids:
                choices.append((p["id"], f"{p['display_name']} ({p['id']})"))

        if not choices:
            console.print("  [dim]No profiles available.[/dim]")
            console.print()
            return None

        for i, (pid, display) in enumerate(choices, 1):
            rec = " [green](detected)[/green]" if pid in suggested_ids else ""
            console.print(f"  [{i}] {display}{rec}")

        skip_idx = len(choices) + 1
        console.print(f"  [{skip_idx}] Skip — I'll apply later")
        console.print()

        valid = [str(i) for i in range(1, skip_idx + 1)]
        choice = Prompt.ask("  Which profile to apply now?", choices=valid, default=str(skip_idx))

        idx = int(choice)
        if idx == skip_idx:
            console.print("  [dim]Skipped. Run 'abso apply <profile>' later.[/dim]")
            console.print()
            return None

        selected = choices[idx - 1][0]
        console.print()
        return selected

    def _step_apply_profile(self, profile_id: str) -> None:
        console.print("[bold cyan]Step 6: APPLY[/bold cyan]")
        console.print()

        self.backups_dir.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            # Backup
            backup_task = progress.add_task("Creating backup...", total=None)
            backup_manager = BackupManager(self.backups_dir)
            backup_id = backup_manager.create_backup()
            progress.update(backup_task, description=f"[green]Backup created: {backup_id}[/green]")
            progress.stop_task(backup_task)

            # Apply
            apply_task = progress.add_task(f"Applying {profile_id}...", total=None)
            applier = ProfileApplier()
            try:
                result = applier.apply_profile(profile_id)
                if result.success:
                    progress.update(apply_task, description=f"[green]Profile applied: {profile_id}[/green]")
                    self.profile_applied = profile_id

                    # Save state
                    state = {
                        "current_profile": profile_id,
                        "applied_at": datetime.now().isoformat(),
                        "setup_completed": True,
                    }
                    try:
                        self.state_file.parent.mkdir(parents=True, exist_ok=True)
                        tmp = self.state_file.with_suffix(".tmp")
                        tmp.write_text(json.dumps(state, indent=2))
                        os.replace(tmp, self.state_file)
                    except Exception as e:
                        logging.getLogger(__name__).error(f"Failed to save state: {e}")

                    if result.requires_reboot:
                        self.needs_reboot = True
                        self.reboot_reasons.append("Profile settings (HAGS, etc.)")
                else:
                    progress.update(apply_task, description=f"[red]Failed: {result.error}[/red]")
            except Exception as e:
                progress.update(apply_task, description=f"[red]Error: {e}[/red]")

            progress.stop_task(apply_task)

        console.print()

    def _print_summary(self) -> None:
        lines = []

        if self.fixes_applied > 0:
            lines.append(f"[green]{self.fixes_applied} system issues will be fixed by profile[/green]")
        if self.kbs_uninstalled > 0:
            lines.append(f"[green]{self.kbs_uninstalled} problematic KB(s) uninstalled[/green]")
        if self.profile_applied:
            lines.append(f"[green]Profile applied: {self.profile_applied}[/green]")
        if self.needs_reboot:
            reasons = ", ".join(self.reboot_reasons)
            lines.append(f"[yellow]Reboot required for: {reasons}[/yellow]")

        if not lines:
            lines.append("[dim]Setup complete. No changes made.[/dim]")

        lines.append("")
        lines.append("[dim]Run 'abso setup' anytime to reconfigure.[/dim]")
        lines.append("[dim]Run 'abso apply <profile>' to switch profiles.[/dim]")

        console.print(Panel(
            "\n".join(lines),
            title="[bold]Summary[/bold]",
            border_style="green",
            padding=(1, 2),
        ))
        console.print()
