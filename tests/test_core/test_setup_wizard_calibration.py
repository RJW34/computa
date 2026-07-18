"""Tests for the setup wizard's machine-calibration steps."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

from abso.core.setup_wizard import SetupWizard


def _make_wizard(tmp_path: Path) -> SetupWizard:
    wizard = SetupWizard()
    wizard.backups_dir = tmp_path / "backups"
    wizard.state_file = tmp_path / ".abso_state.json"
    return wizard


# --- capability helpers ------------------------------------------------------


def test_vrr_capability_from_detected_monitors(tmp_path: Path) -> None:
    wizard = _make_wizard(tmp_path)

    assert wizard._any_vrr_capable_monitor({}) is None
    assert wizard._any_vrr_capable_monitor({"monitors": []}) is None
    assert wizard._any_vrr_capable_monitor(
        {"monitors": [{"vrr_supported": "possible"}, {"vrr_supported": None}]}
    ) is False
    for capable_state in (True, "hardware", "likely"):
        assert wizard._any_vrr_capable_monitor(
            {"monitors": [{"vrr_supported": capable_state}]}
        ) is True


def test_display_supports_hdr_maps_summary(tmp_path: Path) -> None:
    wizard = _make_wizard(tmp_path)

    with patch("abso.settings.windows.WindowsSettingsHandler") as handler_cls:
        handler_cls.return_value._get_hdr_state_summary.return_value = {
            "available": True,
            "hdr_capable_count": 1,
        }
        assert wizard._display_supports_hdr() is True

        handler_cls.return_value._get_hdr_state_summary.return_value = {
            "available": True,
            "hdr_capable_count": 0,
        }
        assert wizard._display_supports_hdr() is False

        handler_cls.return_value._get_hdr_state_summary.return_value = {
            "available": False,
        }
        assert wizard._display_supports_hdr() is None


# --- capability-filtered profile selection -----------------------------------


def _selection_manifest() -> list[dict]:
    return [
        {
            "id": "game-sdr",
            "display_name": "Game",
            "requires_hdr_display": False,
            "sync_mode": "off",
        },
        {
            "id": "game-hdr",
            "display_name": "Game",
            "requires_hdr_display": True,
            "sync_mode": "off",
        },
        {
            "id": "game-gsync",
            "display_name": "Game",
            "requires_hdr_display": False,
            "sync_mode": "on",
        },
    ]


def test_profile_selection_hides_hdr_lanes_without_hdr_display(tmp_path: Path) -> None:
    wizard = _make_wizard(tmp_path)

    with (
        patch("abso.profiles.catalog.get_profile_manifest", return_value=_selection_manifest()),
        patch.object(wizard, "_display_supports_hdr", return_value=False),
        patch("abso.core.setup_wizard.Prompt") as prompt,
    ):
        prompt.ask.return_value = "1"
        selected = wizard._step_profile_selection({}, {"monitors": [{"vrr_supported": True}]})

    assert selected == "game-sdr"
    # The prompt's valid choices cover the two visible lanes plus Skip.
    valid_choices = prompt.ask.call_args.kwargs["choices"]
    assert valid_choices == ["1", "2", "3"]


def test_profile_selection_keeps_hdr_lanes_when_capability_unknown(tmp_path: Path) -> None:
    wizard = _make_wizard(tmp_path)

    with (
        patch("abso.profiles.catalog.get_profile_manifest", return_value=_selection_manifest()),
        patch.object(wizard, "_display_supports_hdr", return_value=None),
        patch("abso.core.setup_wizard.Prompt") as prompt,
    ):
        prompt.ask.return_value = "4"  # Skip
        selected = wizard._step_profile_selection({}, {})

    assert selected is None
    valid_choices = prompt.ask.call_args.kwargs["choices"]
    assert valid_choices == ["1", "2", "3", "4"]


# --- baseline backup step ----------------------------------------------------


def test_baseline_backup_records_id_for_state(tmp_path: Path) -> None:
    wizard = _make_wizard(tmp_path)

    manager = MagicMock()
    manager.create_backup.return_value = "2026-07-17_120000"

    with (
        patch("abso.core.backup.BackupManager", return_value=manager),
        patch("abso.core.setup_wizard.Confirm") as confirm,
    ):
        confirm.ask.return_value = True
        wizard._step_baseline_backup()

    manager.create_backup.assert_called_once_with(profile_id=None, backup_type="baseline")
    assert wizard.baseline_backup_id == "2026-07-17_120000"


def test_baseline_backup_can_be_skipped(tmp_path: Path) -> None:
    wizard = _make_wizard(tmp_path)

    with (
        patch("abso.core.backup.BackupManager") as manager_cls,
        patch("abso.core.setup_wizard.Confirm") as confirm,
    ):
        confirm.ask.return_value = False
        wizard._step_baseline_backup()

    manager_cls.assert_not_called()
    assert wizard.baseline_backup_id is None


# --- apply step carries the baseline into state ------------------------------


def test_apply_state_includes_baseline_backup_id(tmp_path: Path) -> None:
    from abso.core.applier import ApplyResult

    tx = MagicMock()
    tx.success = True
    tx.profile_id = "some-profile"
    tx.apply_result = ApplyResult(success=True, requires_reboot=False)

    manager = MagicMock()
    manager.execute.return_value = tx

    wizard = _make_wizard(tmp_path)
    wizard.baseline_backup_id = "2026-07-17_120000"

    with patch("abso.core.setup_wizard.ProfileTransactionManager", return_value=manager):
        wizard._step_apply_profile("some-profile")

    import json

    state = json.loads(wizard.state_file.read_text(encoding="utf-8"))
    assert state["baseline_backup_id"] == "2026-07-17_120000"
