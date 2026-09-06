"""Missing evidence must not certify UE settings or prescribe a different lane."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import patch

import pytest

from abso.settings.fortnite_config import FortniteConfigHandler


@pytest.fixture
def config(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("LOCALAPPDATA", str(tmp_path))
    monkeypatch.setenv("ABSO_CONFIG", str(tmp_path / "abso.yaml"))
    monkeypatch.setattr("abso.settings.ue_game_user_settings.__file__", str(tmp_path / "source/abso/settings/ue_game_user_settings.py"))
    path = tmp_path / "FortniteGame/Saved/Config/WindowsClient/GameUserSettings.ini"
    path.parent.mkdir(parents=True)
    path.write_text(
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "PreferredFullscreenMode=1\nbUseVSync=True\nFrameRateLimit=60\n",
        encoding="utf-8",
    )
    return path


def test_missing_config_cannot_verify_requested_settings(config: Path) -> None:
    config.unlink()
    result = FortniteConfigHandler().verify_active({"vsync": True, "frame_rate_limit": 297})
    assert result["all_active"] is False
    assert set(result["settings"]) == {"vsync", "frame_rate_limit"}
    assert all(row["status"] == "unverifiable" for row in result["settings"].values())


@pytest.mark.parametrize("refresh", [None, 0])
def test_unknown_refresh_does_not_hide_a_60_fps_cap(config: Path, refresh: int | None) -> None:
    with patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=refresh):
        result = FortniteConfigHandler().verify_active({"auto_vrr_fps_cap": True, "vsync": True})
    assert result["all_active"] is False
    assert result["settings"]["auto_vrr_fps_cap"]["status"] == "unverifiable"
    assert result["settings"]["vsync"]["active"] is True


def test_refresh_failure_cannot_certify_even_matching_explicit_fallback(config: Path) -> None:
    with patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", side_effect=OSError("unavailable")):
        result = FortniteConfigHandler().verify_active({"auto_vrr_fps_cap": True, "frame_rate_limit": 60})
    assert result["all_active"] is False
    assert result["settings"]["frame_rate_limit"]["active"] is True
    assert result["settings"]["auto_vrr_fps_cap"]["active"] is False


def test_known_refresh_reports_actual_cap_drift(config: Path) -> None:
    with patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300):
        result = FortniteConfigHandler().verify_active({"auto_vrr_fps_cap": True})
    assert result["all_active"] is False
    assert result["settings"]["frame_rate_limit"] == {"target": 297, "current": 60, "active": False}


def test_unreadable_requested_value_is_unverifiable(config: Path) -> None:
    result = FortniteConfigHandler().verify_active({"hdr_output": True})
    assert result["all_active"] is False
    assert result["settings"]["hdr_output"]["status"] == "unverifiable"


def test_synthetic_only_settings_do_not_require_a_config(config: Path) -> None:
    config.unlink()
    assert FortniteConfigHandler().verify_active({"_reboot_pending": False}) == {"all_active": True, "settings": {}}


@pytest.mark.parametrize(
    ("profile_id", "expected_count"),
    [(None, 0), ("cs2-gsync-hdr-capture", 0), ("fortnite-gsync-hdr-capture", 0), ("fortnite", 2)],
)
def test_audit_uses_selected_profiles_presentation_policy(
    config: Path, tmp_path: Path, profile_id: str | None, expected_count: int,
) -> None:
    state_path = tmp_path / "AdaptiveBattleStationOptimizer/.abso_state.json"
    state_path.parent.mkdir()
    state_path.write_text(json.dumps({"current_profile": profile_id}), encoding="utf-8")
    issues = FortniteConfigHandler().audit()
    assert len(issues) == expected_count
    assert all("differs from active profile" in issue.title for issue in issues)


def test_audit_honors_overrides_and_disabled_handlers(config: Path, tmp_path: Path) -> None:
    state_path = tmp_path / "AdaptiveBattleStationOptimizer/.abso_state.json"
    state_path.parent.mkdir()
    state_path.write_text(json.dumps({"current_profile": "fortnite"}), encoding="utf-8")
    config_path = tmp_path / "abso.yaml"
    config_path.write_text(
        "profile_overrides:\n  fortnite:\n    fortnite_config:\n      fullscreen_mode: 1\n      vsync: true\n",
        encoding="utf-8",
    )
    assert FortniteConfigHandler().audit() == []
    config_path.write_text("disabled_handlers: [FortniteConfigHandler]\n", encoding="utf-8")
    assert FortniteConfigHandler().audit() == []


def test_audit_uses_newest_source_or_installed_state(config: Path, tmp_path: Path) -> None:
    source_state = tmp_path / "source/.abso_state.json"
    source_state.parent.mkdir()
    source_state.write_text(json.dumps({
        "current_profile": "fortnite-gsync-hdr-capture", "applied_at": "2026-09-06T12:00:00",
    }), encoding="utf-8")
    installed_state = tmp_path / "AdaptiveBattleStationOptimizer/.abso_state.json"
    installed_state.parent.mkdir()
    installed_state.write_text(json.dumps({
        "current_profile": "fortnite", "applied_at": "2026-09-05T12:00:00",
    }), encoding="utf-8")
    assert FortniteConfigHandler().audit() == []
    installed_state.write_text(json.dumps({
        "current_profile": "fortnite", "applied_at": "2026-09-07T12:00:00",
    }), encoding="utf-8")
    assert len(FortniteConfigHandler().audit()) == 2
