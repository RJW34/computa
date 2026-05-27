"""Tests for profile launch orchestration."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.core.applier import ApplyResult
from abso.core.launcher import LaunchTarget, launch_profile, launch_profile_without_apply


def test_launch_profile_uses_transaction_fallback_profile_for_target(tmp_path: Path) -> None:
    """A fallback apply should launch and report the profile that actually committed."""
    fallback_chain = [
        {
            "from": "strict-profile",
            "to": "safe-profile",
            "reason": "strict display path blocked",
        }
    ]
    tx = MagicMock()
    tx.success = True
    tx.profile_id = "safe-profile"
    tx.fallback_chain = fallback_chain
    tx.backup_id = None
    tx.apply_result = ApplyResult(success=True)

    manager = MagicMock()
    manager.execute.return_value = tx

    target = LaunchTarget(
        profile_id="safe-profile",
        game_name="Test Game",
        platform="manual",
        executable_name="game.exe",
        executable_path=tmp_path / "game.exe",
        source="test",
    )
    process = MagicMock()
    process.pid = 1234

    with patch("abso.core.launcher.resolve_launch_target", return_value=target) as mock_resolve:
        result = launch_profile(
            "strict-profile",
            tmp_path,
            create_backup=False,
            wait=False,
            transaction_manager=manager,
            popen_factory=MagicMock(return_value=process),
        )

    manager.execute.assert_called_once_with(
        profile_id="strict-profile",
        create_backup=False,
    )
    mock_resolve.assert_called_once_with(
        profile_id="safe-profile",
        launch_path=None,
    )
    assert result.success is True
    assert result.profile_id == "safe-profile"
    assert result.requested_profile_id == "strict-profile"
    assert result.fallback_chain == fallback_chain
    assert result.to_dict()["fallback_applied"] is True


def test_launch_profile_without_apply_skips_transaction_manager(tmp_path: Path) -> None:
    """Already-active launches should start the game without an apply transaction."""
    target = LaunchTarget(
        profile_id="safe-profile",
        game_name="Test Game",
        platform="manual",
        executable_name="game.exe",
        executable_path=tmp_path / "game.exe",
        source="test",
    )
    process = MagicMock()
    process.pid = 1234

    with patch("abso.core.launcher.resolve_launch_target", return_value=target):
        result = launch_profile_without_apply(
            "safe-profile",
            wait=False,
            popen_factory=MagicMock(return_value=process),
        )

    assert result.success is True
    assert result.profile_id == "safe-profile"
    assert result.transaction.state == "skipped_apply"
    assert result.transaction.apply_result is None
    assert result.to_dict()["transaction"]["state"] == "skipped_apply"
    assert result.process_id == 1234
