"""Launch orchestration for profile-driven game sessions."""

from __future__ import annotations

import subprocess
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from abso.core.backup import BackupManager
from abso.core.exceptions import LaunchTargetNotFoundError, ProfileLaunchError
from abso.core.game_detector import (
    InstalledGame,
    detect_installed_games,
    match_games_to_profiles,
)
from abso.core.transaction import ProfileTransactionManager, TransactionResult
from abso.profiles.catalog import get_profile_instances, resolve_profile_id


@dataclass
class LaunchTarget:
    """Resolved executable target for a profile launch."""

    profile_id: str
    game_name: str | None
    platform: str | None
    executable_name: str
    executable_path: Path
    source: str
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile_id": self.profile_id,
            "game_name": self.game_name,
            "platform": self.platform,
            "executable_name": self.executable_name,
            "executable_path": str(self.executable_path),
            "source": self.source,
            "warnings": list(self.warnings),
        }


@dataclass
class LaunchResult:
    """Lifecycle result for apply -> launch -> optional restore."""

    success: bool
    profile_id: str
    transaction: TransactionResult
    requested_profile_id: str | None = None
    fallback_chain: list[dict[str, str]] = field(default_factory=list)
    target: LaunchTarget | None = None
    launched: bool = False
    process_id: int | None = None
    wait_requested: bool = True
    exit_code: int | None = None
    restore_attempted: bool = False
    restored: bool = False
    restore_backup_id: str | None = None
    restore_error: str | None = None
    error: str | None = None
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "profile_id": self.profile_id,
            "requested_profile_id": self.requested_profile_id,
            "fallback_applied": bool(self.fallback_chain),
            "fallback_chain": list(self.fallback_chain),
            "launched": self.launched,
            "process_id": self.process_id,
            "wait_requested": self.wait_requested,
            "exit_code": self.exit_code,
            "restore_attempted": self.restore_attempted,
            "restored": self.restored,
            "restore_backup_id": self.restore_backup_id,
            "restore_error": self.restore_error,
            "error": self.error,
            "warnings": list(self.warnings),
            "target": self.target.to_dict() if self.target else None,
            "transaction": self.transaction.to_dict(),
        }


def _find_executable_path(install_path: Path, executable_name: str) -> Path | None:
    """Resolve an executable within an install root."""
    direct = install_path / executable_name
    if direct.exists():
        return direct

    try:
        matches = sorted(
            (path for path in install_path.rglob(executable_name) if path.is_file()),
            key=lambda p: (len(p.parts), str(p).lower()),
        )
    except OSError:
        return None

    return matches[0] if matches else None


def ensure_direct_launch_supported(profile_id: str) -> None:
    """Reject unsupported launcher/lifetime routing before any profile write."""
    canonical = resolve_profile_id(profile_id) or profile_id
    profile = get_profile_instances().get(canonical)
    reason = getattr(profile, "external_launch_required_reason", None)
    if isinstance(reason, str) and reason.strip():
        raise ProfileLaunchError(
            "This profile requires an external game launcher",
            details=(
                f"{reason.strip()} Apply settings separately with 'computa apply {canonical}', "
                "then start the game through its platform client."
            ),
        )


def resolve_launch_target(
    profile_id: str,
    launch_path: Path | None = None,
    detected_games: list[InstalledGame] | None = None,
) -> LaunchTarget:
    """Resolve the launchable executable for a profile."""
    canonical_profile_id = resolve_profile_id(profile_id) or profile_id
    ensure_direct_launch_supported(canonical_profile_id)
    if launch_path:
        candidate = launch_path.expanduser()
        if not candidate.exists() or not candidate.is_file():
            raise LaunchTargetNotFoundError(
                "Launch path does not exist",
                details=str(candidate),
            )
        return LaunchTarget(
            profile_id=canonical_profile_id,
            game_name=None,
            platform="manual",
            executable_name=candidate.name,
            executable_path=candidate,
            source="manual_path",
        )

    profiles = get_profile_instances()
    profile = profiles.get(canonical_profile_id)
    if profile is None:
        raise LaunchTargetNotFoundError(
            "Profile has no launch metadata",
            details=canonical_profile_id,
        )

    games = detected_games if detected_games is not None else detect_installed_games()
    matched_games = match_games_to_profiles(games, profiles)
    candidates = [game for game in matched_games if game.profile_match == canonical_profile_id]

    if not candidates:
        hints = ", ".join(profile.executable_hints) or "(none)"
        raise LaunchTargetNotFoundError(
            "No installed game matched this profile",
            details=f"profile={canonical_profile_id}, executable_hints={hints}",
        )

    warnings: list[str] = []
    if len(candidates) > 1:
        warnings.append(
            f"Multiple installs matched '{canonical_profile_id}'. Using the first resolvable executable."
        )

    preferred_order = {
        exe.lower(): index
        for index, exe in enumerate(profile.executable_hints)
    }
    platform_priority = {
        "standalone": 0,
        "battle_net": 1,
        "steam": 2,
        "epic": 3,
    }
    ordered_candidates = sorted(
        candidates,
        key=lambda game: (
            preferred_order.get(game.executable.lower(), len(preferred_order)),
            platform_priority.get(game.platform, 99),
            str(game.install_path).lower(),
        ),
    )

    for game in ordered_candidates:
        executable_path = _find_executable_path(game.install_path, game.executable)
        if executable_path is None:
            continue

        return LaunchTarget(
            profile_id=canonical_profile_id,
            game_name=game.name,
            platform=game.platform,
            executable_name=game.executable,
            executable_path=executable_path,
            source="game_detector",
            warnings=warnings,
        )

    install_roots = ", ".join(str(game.install_path) for game in ordered_candidates)
    raise LaunchTargetNotFoundError(
        "Game install detected but executable path could not be resolved",
        details=install_roots,
    )


def launch_profile(
    profile_id: str,
    backup_dir: Path,
    *,
    create_backup: bool = True,
    wait: bool = True,
    restore_on_exit: bool = False,
    launch_path: Path | None = None,
    launch_args: list[str] | None = None,
    transaction_manager: ProfileTransactionManager | None = None,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> LaunchResult:
    """Apply profile, launch target executable, and optionally restore on exit."""
    requested_profile_id = resolve_profile_id(profile_id) or profile_id
    ensure_direct_launch_supported(requested_profile_id)
    if restore_on_exit and not wait:
        raise ProfileLaunchError(
            "restore_on_exit requires wait=True",
            details="Use the default wait behavior or disable restore_on_exit.",
        )
    if restore_on_exit and not create_backup:
        raise ProfileLaunchError(
            "restore_on_exit requires backups",
            details="Remove --no-backup or disable restore_on_exit.",
        )

    tx_manager = transaction_manager or ProfileTransactionManager(backup_dir)
    tx = tx_manager.execute(profile_id=requested_profile_id, create_backup=create_backup)
    actual_profile_id = tx.profile_id or requested_profile_id
    raw_fallback_chain = getattr(tx, "fallback_chain", None)
    fallback_chain = raw_fallback_chain if isinstance(raw_fallback_chain, list) else []
    result = LaunchResult(
        success=False,
        profile_id=actual_profile_id,
        requested_profile_id=requested_profile_id,
        fallback_chain=fallback_chain,
        transaction=tx,
        wait_requested=wait,
    )

    if not tx.success or tx.apply_result is None or not tx.apply_result.success:
        result.error = tx.error or "Profile apply failed before launch without a detailed error"
        return result

    try:
        target = resolve_launch_target(profile_id=actual_profile_id, launch_path=launch_path)
    except (LaunchTargetNotFoundError, ProfileLaunchError) as e:
        result.error = str(e)
        if restore_on_exit and tx.backup_id:
            _restore_launch_backup(result, backup_dir, tx.backup_id)
        return result

    result.target = target
    result.warnings.extend(target.warnings)

    args = [str(target.executable_path), *(launch_args or [])]
    try:
        process = popen_factory(
            args,
            cwd=str(target.executable_path.parent),
        )
    except OSError as e:
        result.error = f"Launch failed: {e}"
        if restore_on_exit and tx.backup_id:
            _restore_launch_backup(result, backup_dir, tx.backup_id)
        return result

    result.launched = True
    result.process_id = process.pid
    result.success = True

    if not wait:
        return result

    try:
        result.exit_code = process.wait()
    except Exception as e:  # pragma: no cover - defensive wait handling
        result.error = f"Failed while waiting for process exit: {e}"
        result.success = False
        return result

    if restore_on_exit and tx.backup_id:
        _restore_launch_backup(result, backup_dir, tx.backup_id)

    if restore_on_exit and not result.restored:
        result.success = False
    elif result.exit_code not in (None, 0):
        result.warnings.append(f"Process exited with code {result.exit_code}.")

    return result


def launch_profile_without_apply(
    profile_id: str,
    *,
    wait: bool = True,
    launch_path: Path | None = None,
    launch_args: list[str] | None = None,
    popen_factory: Callable[..., subprocess.Popen[Any]] = subprocess.Popen,
) -> LaunchResult:
    """Launch a profile target when live verification already proved it active."""
    profile_id = resolve_profile_id(profile_id) or profile_id
    ensure_direct_launch_supported(profile_id)
    tx = TransactionResult(
        success=True,
        profile_id=profile_id,
        requested_profile_id=profile_id,
        state="skipped_apply",
    )
    tx.add_checkpoint(
        "apply",
        "skipped",
        "Profile already verified active; launch skipped redundant apply.",
    )
    result = LaunchResult(
        success=False,
        profile_id=profile_id,
        requested_profile_id=profile_id,
        transaction=tx,
        wait_requested=wait,
    )

    try:
        target = resolve_launch_target(profile_id=profile_id, launch_path=launch_path)
    except (LaunchTargetNotFoundError, ProfileLaunchError) as e:
        result.error = str(e)
        return result

    result.target = target
    result.warnings.extend(target.warnings)

    args = [str(target.executable_path), *(launch_args or [])]
    try:
        process = popen_factory(
            args,
            cwd=str(target.executable_path.parent),
        )
    except OSError as e:
        result.error = f"Launch failed: {e}"
        return result

    result.launched = True
    result.process_id = process.pid
    result.success = True

    if not wait:
        return result

    try:
        result.exit_code = process.wait()
    except Exception as e:  # pragma: no cover - defensive wait handling
        result.error = f"Failed while waiting for process exit: {e}"
        result.success = False
        return result

    if result.exit_code not in (None, 0):
        result.warnings.append(f"Process exited with code {result.exit_code}.")

    return result


def _restore_launch_backup(result: LaunchResult, backup_dir: Path, backup_id: str) -> None:
    """Restore baseline backup after a launched session exits."""
    result.restore_attempted = True
    result.restore_backup_id = backup_id

    try:
        restore_summary = BackupManager(backup_dir).restore_backup(backup_id)
        if restore_summary.complete:
            result.restored = True
        else:
            incomplete = restore_summary.failed_components + restore_summary.skipped_components
            handlers = ", ".join(item["handler"] for item in incomplete)
            result.restore_error = f"Restore incomplete for handlers: {handlers}"
    except Exception as e:
        result.restore_error = str(e)
