"""External-client launch policy must stop before profile mutation or spawn."""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest
from click.testing import CliRunner

from abso.core.exceptions import ProfileLaunchError
from abso.core.launcher import (
    launch_profile,
    launch_profile_without_apply,
    resolve_launch_target,
)
from abso.main import cli
from abso.profiles.catalog import get_profile_aliases, get_profile_instances


@pytest.fixture
def rocket_ids():
    profiles = get_profile_instances()
    canonical = {key for key in profiles if key.startswith("rocket-league")}
    assert len(canonical) == 6
    aliases = {alias for alias, target in get_profile_aliases().items() if target in canonical}
    assert aliases, "The policy must be tested through legacy/short aliases too"
    return sorted(canonical | aliases)


@pytest.mark.parametrize("entry", ["resolve", "apply_and_launch", "already_active"])
@pytest.mark.parametrize("manual_path", [False, True])
def test_rocket_launch_core_rejects_all_lanes_and_aliases_before_writes_or_spawn(
    tmp_path, rocket_ids, entry, manual_path,
):
    override = tmp_path / "Launcher.exe" if manual_path else None
    if override:
        override.write_bytes(b"test launcher")
    manager = MagicMock()
    popen = MagicMock()
    with (
        patch("abso.core.launcher.ProfileTransactionManager") as manager_factory,
        patch("abso.core.launcher.detect_installed_games") as detect,
        patch("abso.core.launcher._find_executable_path") as find_exe,
        patch("abso.core.launcher.BackupManager") as backup,
    ):
        for profile_id in rocket_ids:
            with pytest.raises(ProfileLaunchError, match="Epic Games Launcher or Steam") as error:
                if entry == "resolve":
                    resolve_launch_target(profile_id, launch_path=override)
                elif entry == "apply_and_launch":
                    launch_profile(profile_id, tmp_path, launch_path=override,
                                   restore_on_exit=True, transaction_manager=manager,
                                   popen_factory=popen)
                else:
                    launch_profile_without_apply(profile_id, launch_path=override, popen_factory=popen)
            assert "computa apply rocket-league" in str(error.value)
        manager_factory.assert_not_called()
        manager.execute.assert_not_called()
        detect.assert_not_called()
        find_exe.assert_not_called()
        backup.assert_not_called()
        popen.assert_not_called()


@pytest.mark.parametrize("state_kind", ["different", "active", "pending"])
@pytest.mark.parametrize("manual_path", [False, True])
def test_cli_launch_rejects_before_state_reconciliation_pending_repair_or_apply(
    tmp_path, rocket_ids, state_kind, manual_path,
):
    override = tmp_path / "Launcher.exe"
    override.write_bytes(b"test launcher")
    state_path = tmp_path / ".abso_state.json"
    before = b'{"current_profile":"rocket-league","reboot_pending":true}'
    state_path.write_bytes(before)
    with (
        patch("abso.main.get_current_profile", return_value="rocket-league" if state_kind != "different" else "other") as current,
        patch("abso.main._build_state_verification_summary", return_value={
            "all_active": state_kind == "active",
            "pending_apply_settings": ["GlobalFSO"] if state_kind == "pending" else [],
        }) as verify,
        patch("abso.main._reconcile_reboot_pending_after_verified_boot") as reconcile,
        patch("abso.main._apply_pending_profile_settings") as pending,
        patch("abso.main.launch_profile") as launch,
        patch("abso.main.launch_profile_without_apply") as direct,
        patch("abso.main.set_current_profile") as save,
        patch("abso.main.is_admin", return_value=True),
        patch("abso.core.launcher.subprocess.Popen") as spawn,
    ):
        for profile_id in rocket_ids:
            args = ["launch", profile_id, "--json", "--no-wait"]
            if manual_path:
                args += ["--launch-path", str(override)]
            result = CliRunner().invoke(cli, args)
            assert result.exit_code == 1, result.output
            payload = json.loads(result.output)
            assert payload["success"] is False
            assert "Epic Games Launcher or Steam" in payload["error"]
            assert "computa apply rocket-league" in payload["error"]
        current.assert_not_called()
        verify.assert_not_called()
        reconcile.assert_not_called()
        pending.assert_not_called()
        launch.assert_not_called()
        direct.assert_not_called()
        save.assert_not_called()
        spawn.assert_not_called()
    assert state_path.read_bytes() == before


def test_external_launch_policy_is_not_a_ban_on_other_profiles_or_manual_paths(tmp_path):
    path = tmp_path / "game.exe"
    path.write_bytes(b"test game")
    target = resolve_launch_target("slippi-melee", launch_path=path)
    assert target.executable_path == path
    assert target.source == "manual_path"


def test_cli_external_launch_text_explains_separate_apply_without_elevation(tmp_path, rocket_ids):
    with patch("abso.main.is_admin", return_value=False) as admin:
        result = CliRunner().invoke(cli, ["launch", rocket_ids[0], "--restore-on-exit"])
    assert result.exit_code == 1
    assert "Epic Games Launcher or Steam" in result.output
    assert "computa apply rocket-league" in result.output
    admin.assert_not_called()
