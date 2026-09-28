"""Profile switching preserves other games; explicit restore and rollback do not.

All native file writes are under tmp_path. The shared-system handler is a
memory-only fake, so this exercises real backup/transaction logic without
changing this machine's registry, display, or installed game configuration.
"""

from __future__ import annotations

import json
from types import SimpleNamespace
from unittest.mock import MagicMock

import pytest

from abso.core.applier import ApplyResult
from abso.core.backup import BackupManager
from abso.core.transaction import ProfileTransactionManager
from abso.settings.ow2_config import OW2ConfigHandler


class WindowsSettingsHandler:
    """Memory-only shared setting with the same registry identity as production."""

    restore_guarantee = "full"
    backup_requires_main_thread = False

    def __init__(self):
        self.value = "baseline"

    def backup(self):
        return {"value": self.value}

    def restore(self, data):
        self.value = data["value"]
        return True


@pytest.fixture
def native_switch(tmp_path, monkeypatch):
    prefs = tmp_path / "Settings_v0.ini"

    def write_native(vsync, reflex=2):
        prefs.write_text(
            '[Render.13]\n'
            f'VerticalSyncEnabled = "{vsync}"\n'
            f'ReflexMode = "{reflex}"\n'
            'LocalReflections = "0"\n',
            encoding="utf-8",
        )

    monkeypatch.setattr("abso.settings.ow2_config._get_ow2_settings_path", lambda: prefs)
    monkeypatch.setenv("ABSO_BACKUP_SCAN_WORKERS", "1")
    system = WindowsSettingsHandler()
    native = OW2ConfigHandler()
    monkeypatch.setattr("abso.core.backup._get_backup_handlers", lambda: [system, native])
    monkeypatch.setattr("abso.core.transaction.get_config", lambda: SimpleNamespace(max_backups=20))

    backups = tmp_path / "backups"
    write_native(0, reflex=0)
    baseline_id = BackupManager(backups).create_backup(
        profile_id="overwatch2-gsync-hdr-capture", backup_type="pre_apply",
    )
    write_native(1)
    system.value = "live-before-switch"
    return SimpleNamespace(
        prefs=prefs, write_native=write_native, system=system, native=native,
        backups=backups, baseline_id=baseline_id,
    )


def _transaction(env, profile_id, native_handlers, apply):
    applier = MagicMock()
    applier.PROFILES = {profile_id: object()}
    applier.validate_profile_prerequisites.return_value = None
    applier._get_profile.return_value = SimpleNamespace(
        get_handlers=lambda: [env.system, *native_handlers],
    )
    applier.apply_profile.side_effect = apply
    applier.verify_profile.return_value = {"all_active": True, "handlers": {}}
    compliance = MagicMock()
    compliance.evaluate.return_value = SimpleNamespace(has_critical=False, warnings=[])
    return ProfileTransactionManager(
        env.backups, applier=applier, compliance_engine=compliance,
    ).execute(profile_id)


@pytest.mark.parametrize("profile_id", ["counter-strike-2-gsync-capture", "productivity"])
def test_switch_to_other_game_or_desktop_preserves_ow2_native_settings(native_switch, profile_id):
    env = native_switch
    before = env.prefs.read_bytes()

    def apply(_profile_id):
        assert env.prefs.read_bytes() == before
        assert env.system.value == "baseline"  # Shared state still resets.
        env.system.value = "new-profile"
        return ApplyResult(success=True, changed_settings=["WindowsSettingsHandler.value"])

    tx = _transaction(env, profile_id, [], apply)
    assert tx.success is True
    assert env.prefs.read_bytes() == before
    assert env.system.value == "new-profile"
    assert any(cp.phase == "baseline_restore" and cp.status == "ok" for cp in tx.checkpoints)
    # Preservation scopes restoration only: both snapshots remain complete.
    for backup_id in (tx.rollback_backup_id, tx.backup_id):
        data = json.loads((env.backups / backup_id / "OW2ConfigHandler.json").read_text())
        assert 'VerticalSyncEnabled = "1"' in data["file_content"]


def test_switch_within_ow2_restores_owned_baseline_then_applies_target(native_switch):
    env = native_switch

    def apply(_profile_id):
        assert 'VerticalSyncEnabled = "0"' in env.prefs.read_text()
        # Manual Reflex remains live even when owned fields reset for this game.
        assert 'ReflexMode = "2"' in env.prefs.read_text()
        result = env.native.apply({"vsync": True})
        assert result["success"] is True
        return ApplyResult(success=True, changed_settings=["OW2ConfigHandler.vsync"])

    tx = _transaction(env, "overwatch2-gsync-hdr-capture", [env.native], apply)
    assert tx.success is True
    assert 'VerticalSyncEnabled = "1"' in env.prefs.read_text()


def test_failed_cross_game_switch_rolls_back_full_pre_switch_native_snapshot(native_switch):
    env = native_switch
    before = env.prefs.read_bytes()

    def fail(_profile_id):
        # Simulate a partial mutation before a late failure. Rollback must not
        # inherit the Phase0 filter, even for files unrelated to the target.
        env.write_native(0)
        env.system.value = "partial-apply"
        return ApplyResult(success=False, error="late failure", changed_settings=["shared"])

    tx = _transaction(env, "counter-strike-2-gsync-capture", [], fail)
    assert tx.success is False
    assert tx.rollback_performed is True
    assert tx.state == "rolled_back"
    assert env.prefs.read_bytes() == before
    assert env.system.value == "live-before-switch"
    assert tx.rollback_summary["preserved_components"] == []
    assert "OW2ConfigHandler" in tx.rollback_summary["restored_components"]


def test_explicit_backup_restore_still_restores_native_owned_values(native_switch):
    env = native_switch
    summary = BackupManager(env.backups).restore_backup(env.baseline_id)
    assert summary.complete is True
    assert summary.preserved_components == []
    assert "OW2ConfigHandler" in summary.restored_components
    assert 'VerticalSyncEnabled = "0"' in env.prefs.read_text()
    assert 'ReflexMode = "2"' in env.prefs.read_text()


def test_intentional_native_preservation_is_complete_even_with_unavailable_old_file(native_switch):
    env = native_switch
    (env.backups / env.baseline_id / "OW2ConfigHandler.json").unlink()
    before = env.prefs.read_bytes()
    summary = BackupManager(env.backups).restore_backup(
        env.baseline_id, native_config_handlers=set(),
    )
    assert summary.complete is True
    assert summary.has_blocking_issues is False
    assert summary.skipped_components == []
    assert summary.to_dict()["preserved_components"] == ["OW2ConfigHandler"]
    assert env.prefs.read_bytes() == before

    # The same missing data remains a real error for explicit full restoration.
    full_summary = BackupManager(env.backups).restore_backup(env.baseline_id)
    assert full_summary.complete is False
    assert full_summary.has_blocking_issues is True
