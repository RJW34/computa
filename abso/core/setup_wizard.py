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

from abso.core.app_paths import app_data_dir
from abso.core.auditor import ConfigurationAuditor
from abso.core.detector import HardwareDetector
from abso.core.kb_checker import check_problematic_kbs, get_installed_kbs, uninstall_kb
from abso.core.transaction import ProfileTransactionManager

console = Console()


def _get_data_dir() -> Path:
    """Get the data directory (mirrors main.py logic)."""
    import sys

    if getattr(sys, "frozen", False):
        return app_data_dir(create=True)
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
        self.baseline_backup_id: str | None = None
        self.config_created: Path | None = None
        self.tray_autostart_installed = False

    def run(self) -> None:
        """Run the full setup wizard."""
        self._print_welcome()

        # Step 1: Hardware detection — the result feeds capability-aware
        # profile filtering later; other steps still query what they need.
        hardware = self._step_hardware_detection()

        # Step 2: KB check
        self._step_kb_check()

        # Step 3: System audit
        self._step_system_audit()

        # Step 4: Machine-local configuration file
        self._step_config_bootstrap()

        # Step 5: Baseline backup — the "get me back to before ABSO" anchor
        self._step_baseline_backup()

        # Step 6: Game detection
        suggestions = self._step_game_detection()

        # Step 7: Profile selection (filtered/annotated by capability)
        profile_id = self._step_profile_selection(suggestions, hardware)

        # Step 8: Apply
        if profile_id:
            self._step_apply_profile(profile_id)

        # Step 9: Tray autostart
        self._step_tray_autostart()

        # Even without a profile apply, record that setup ran (and where the
        # baseline lives) so first-run flows and uninstall can rely on it.
        if not self.profile_applied and (self.baseline_backup_id or self.tray_autostart_installed):
            try:
                self._write_setup_state({
                    "current_profile": None,
                    "applied_at": None,
                    "reboot_pending": False,
                    "reboot_reasons": [],
                    "setup_completed": True,
                    "baseline_backup_id": self.baseline_backup_id,
                })
            except Exception as e:
                logging.getLogger(__name__).error(f"Failed to save setup state: {e}")

        # Summary
        self._print_summary()

    def _print_welcome(self) -> None:
        from abso.__version__ import __version__

        header = Text()
        header.append("computa", style="bold cyan")
        header.append(f" v{__version__}\n", style="dim")
        header.append("Per-game Windows optimization, with backups for everything it touches\n", style="italic")
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

        # GPU vendor note — what optimization depth this machine gets
        if hardware.get("gpu"):
            from abso.core.gpu_vendor import GpuVendor, classify_gpu_name

            vendor = classify_gpu_name(hardware["gpu"].get("name", ""))
            if vendor is GpuVendor.NVIDIA:
                console.print(
                    "  [green]NVIDIA GPU detected — full driver optimization available[/green]"
                )
            elif vendor is GpuVendor.AMD:
                console.print(
                    "  [green]AMD Radeon detected — Radeon driver tuning available "
                    "(Anti-Lag, ULPS, Enhanced Sync)[/green]"
                )
            else:
                console.print(
                    "  [yellow]No vendor-specific GPU driver tuning for this GPU; all "
                    "OS/power/input/display optimizations still apply.[/yellow]"
                )

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
                console.print("  [dim]Skipped. You can run 'computa audit' later.[/dim]")

        console.print()

    def _step_config_bootstrap(self) -> None:
        """Create a machine-local abso.yaml when none exists yet."""
        console.print("[bold cyan]Step 4: CONFIGURATION[/bold cyan]")
        console.print()

        try:
            from abso.core.config import ConfigManager

            config_manager = ConfigManager()
            if config_manager.config_path.exists():
                console.print(
                    f"  [dim]Using existing configuration: {config_manager.config_path}[/dim]"
                )
                console.print()
                return

            if Confirm.ask(
                "  Create a machine-local abso.yaml with safe defaults?", default=True
            ):
                config_manager.create_default()
                self.config_created = config_manager.config_path
                console.print(f"  [green]Created {config_manager.config_path}[/green]")
                console.print(
                    "  [dim]Edit it later for per-machine tweaks (protected "
                    "peripheral processes, profile overrides).[/dim]"
                )
            else:
                console.print("  [dim]Skipped. ABSO runs on built-in defaults without one.[/dim]")
        except Exception as e:
            console.print(f"  [yellow]Config bootstrap unavailable: {e}[/yellow]")

        console.print()

    def _step_baseline_backup(self) -> None:
        """Capture a pre-ABSO baseline of every backed-up settings domain."""
        console.print("[bold cyan]Step 5: BASELINE BACKUP[/bold cyan]")
        console.print()
        console.print(
            "  A baseline records your system as it is [bold]right now[/bold], before ABSO"
        )
        console.print(
            "  changes anything. 'computa uninstall' restores it to remove ABSO cleanly."
        )

        if not Confirm.ask("  Capture the baseline backup?", default=True):
            console.print("  [dim]Skipped. 'computa backup-create' can capture one later.[/dim]")
            console.print()
            return

        try:
            from abso.core.backup import BackupManager

            self.backups_dir.mkdir(parents=True, exist_ok=True)
            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=console,
            ) as progress:
                task = progress.add_task("Backing up current settings...", total=None)
                backup_manager = BackupManager(self.backups_dir)
                self.baseline_backup_id = backup_manager.create_backup(
                    profile_id=None,
                    backup_type="baseline",
                )
                progress.update(task, description="Baseline captured!")
                time.sleep(0.2)

            console.print(f"  [green]Baseline saved: {self.baseline_backup_id}[/green]")
        except Exception as e:
            console.print(f"  [red]Baseline backup failed: {e}[/red]")

        console.print()

    def _display_supports_hdr(self) -> bool | None:
        """Best-effort HDR capability probe. None means unknown."""
        try:
            from abso.settings.windows import WindowsSettingsHandler

            summary = WindowsSettingsHandler()._get_hdr_state_summary()
            if not summary.get("available"):
                return None
            return summary.get("hdr_capable_count", 0) > 0
        except Exception:
            return None

    @staticmethod
    def _any_vrr_capable_monitor(hardware: dict) -> bool | None:
        """Whether any detected monitor looks VRR-capable. None means unknown."""
        monitors = hardware.get("monitors") or []
        if not monitors:
            return None
        capable_states = (True, "hardware", "likely")
        return any(mon.get("vrr_supported") in capable_states for mon in monitors)

    def _step_game_detection(self) -> dict[str, str]:
        """Detect installed games and return profile suggestions.

        Returns:
            Dict mapping display string to profile ID.
        """
        console.print("[bold cyan]Step 6: GAME DETECTION[/bold cyan]")
        console.print()

        try:
            from abso.core.game_detector import get_profile_suggestions

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
                console.print("  [dim]You can manually apply a profile with 'computa apply <profile>'.[/dim]")
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

    def _step_profile_selection(
        self,
        suggestions: dict[str, str],
        hardware: dict | None = None,
    ) -> str | None:
        console.print("[bold cyan]Step 7: PROFILE SELECTION[/bold cyan]")
        console.print()

        hardware = hardware or {}
        hdr_support = self._display_supports_hdr()
        vrr_capable = self._any_vrr_capable_monitor(hardware)

        # Build list of choices: detected games + capability-filtered catalog
        from abso.profiles.catalog import get_profile_manifest

        manifest = get_profile_manifest()

        # Suggested profiles first
        choices: list[tuple[str, str]] = []
        suggested_ids = set()

        for display, profile_id in suggestions.items():
            choices.append((profile_id, display))
            suggested_ids.add(profile_id)

        hidden_hdr_lanes = 0
        for p in manifest:
            if p["id"] in suggested_ids:
                continue
            # HDR composition lanes are meaningless without an HDR-capable
            # display; drop them instead of offering settings that can't apply.
            if hdr_support is False and p.get("requires_hdr_display"):
                hidden_hdr_lanes += 1
                continue
            label = f"{p['display_name']} ({p['id']})"
            if vrr_capable is False and p.get("sync_mode") == "on":
                label += " [yellow](needs a VRR display)[/yellow]"
            choices.append((p["id"], label))

        if hidden_hdr_lanes:
            console.print(
                f"  [dim]{hidden_hdr_lanes} HDR profile variants hidden — no HDR-capable "
                "display detected.[/dim]"
            )
            console.print()

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
            console.print("  [dim]Skipped. Run 'computa apply <profile>' later.[/dim]")
            console.print()
            return None

        selected = choices[idx - 1][0]
        console.print()
        return selected

    def _step_apply_profile(self, profile_id: str) -> None:
        console.print("[bold cyan]Step 8: APPLY[/bold cyan]")
        console.print()

        self.backups_dir.mkdir(parents=True, exist_ok=True)

        with Progress(
            SpinnerColumn(),
            TextColumn("[progress.description]{task.description}"),
            console=console,
        ) as progress:
            apply_task = progress.add_task(f"Running transactional apply for {profile_id}...", total=None)
            tx_manager = ProfileTransactionManager(self.backups_dir)
            try:
                tx = tx_manager.execute(profile_id=profile_id, create_backup=True)
                result = tx.apply_result
                actual_profile_id = tx.profile_id or profile_id
                if tx.success and result and result.success:
                    progress.update(
                        apply_task,
                        description=f"[green]Profile applied: {actual_profile_id}[/green]",
                    )
                    self.profile_applied = actual_profile_id

                    # Save state
                    state = {
                        "current_profile": actual_profile_id,
                        "applied_at": datetime.now().isoformat(),
                        "reboot_pending": result.requires_reboot,
                        "reboot_reasons": result.reboot_reasons,
                        "setup_completed": True,
                        "baseline_backup_id": self.baseline_backup_id,
                    }
                    try:
                        self._write_setup_state(state)
                    except Exception as e:
                        logging.getLogger(__name__).error(f"Failed to save state: {e}")

                    if result.requires_reboot:
                        self.needs_reboot = True
                        self.reboot_reasons.append("Profile settings (HAGS, etc.)")
                else:
                    error = tx.error or (result.error if result else "Unknown transaction error")
                    progress.update(apply_task, description=f"[red]Failed: {error}[/red]")
            except Exception as e:
                progress.update(apply_task, description=f"[red]Error: {e}[/red]")

            progress.stop_task(apply_task)

        console.print()

    def _step_tray_autostart(self) -> None:
        """Offer to register the tray app to start with Windows."""
        console.print("[bold cyan]Step 9: TRAY AUTOSTART[/bold cyan]")
        console.print()

        if not Confirm.ask(
            "  Start the ABSO tray (one-click profile switching) with Windows?",
            default=True,
        ):
            console.print(
                "  [dim]Skipped. 'computa tray --install-startup' sets it up later.[/dim]"
            )
            console.print()
            return

        try:
            from abso.tray import install_startup

            with Progress(
                SpinnerColumn(),
                TextColumn("[progress.description]{task.description}"),
                transient=True,
                console=console,
            ) as progress:
                task = progress.add_task("Registering tray autostart...", total=None)
                install_startup()
                progress.update(task, description="Done!")
                time.sleep(0.2)

            self.tray_autostart_installed = True
            console.print("  [green]Tray registered to start with Windows.[/green]")
        except Exception as e:
            console.print(f"  [red]Tray autostart registration failed: {e}[/red]")
            console.print("  [dim]You can retry with 'computa tray --install-startup'.[/dim]")

        console.print()

    def _write_setup_state(self, state: dict) -> None:
        """Write setup state through the shared active-profile state mirror."""
        try:
            from abso.main import STATE_FILE, _write_state_snapshot

            if self.state_file.resolve() == STATE_FILE.resolve():
                _write_state_snapshot(state)
                return
        except Exception:
            pass

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_file.with_suffix(".tmp")
        tmp.write_text(json.dumps(state, indent=2), encoding="utf-8")
        os.replace(tmp, self.state_file)

    def _print_summary(self) -> None:
        lines = []

        if self.fixes_applied > 0:
            lines.append(f"[green]{self.fixes_applied} system issues will be fixed by profile[/green]")
        if self.kbs_uninstalled > 0:
            lines.append(f"[green]{self.kbs_uninstalled} problematic KB(s) uninstalled[/green]")
        if self.config_created:
            lines.append(f"[green]Machine config created: {self.config_created}[/green]")
        if self.baseline_backup_id:
            lines.append(
                f"[green]Baseline backup captured: {self.baseline_backup_id}[/green] "
                "[dim]('computa uninstall' restores it)[/dim]"
            )
        if self.tray_autostart_installed:
            lines.append("[green]Tray registered to start with Windows[/green]")
        if self.profile_applied:
            lines.append(f"[green]Profile applied: {self.profile_applied}[/green]")
        if self.needs_reboot:
            reasons = ", ".join(self.reboot_reasons)
            lines.append(f"[yellow]Reboot required for: {reasons}[/yellow]")

        if not lines:
            lines.append("[dim]Setup complete. No changes made.[/dim]")

        lines.append("")
        lines.append("[dim]Run 'computa setup' anytime to reconfigure.[/dim]")
        lines.append("[dim]Run 'computa apply <profile>' to switch profiles.[/dim]")

        console.print(Panel(
            "\n".join(lines),
            title="[bold]Summary[/bold]",
            border_style="green",
            padding=(1, 2),
        ))
        console.print()
