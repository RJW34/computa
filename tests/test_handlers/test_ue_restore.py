"""Rollback owns game settings keys, not later user edits to the whole INI."""

from pathlib import Path
from unittest.mock import patch

import pytest

from abso.settings.fortnite_config import FortniteConfigHandler
from abso.settings.marvel_rivals_config import MarvelRivalsConfigHandler


def _backup(path: Path, content: str) -> dict:
    return {"config_found": True, "config_path": str(path), "file_content": content}


def test_restore_keeps_graphics_renderer_and_controls_changed_after_backup(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    old = (
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "PreferredFullscreenMode=0\nLastConfirmedFullscreenMode=0\n"
        "bUseVSync=False\nFrameRateLimit=60.000000\n"
        "bUseNanite=True\nDLSSQuality=0\nLatencyTweak2=1\nMouseSensitivity=0.5\n"
        "[ScalabilityGroups]\nsg.TextureQuality=3\n"
        "[D3DRHIPreference]\nPreferredRHI=dx11\n"
        "[/Script/Unrelated.Settings]\nbUseVSync=False\n"
    )
    latest = (
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "PreferredFullscreenMode=1\nLastConfirmedFullscreenMode=1\n"
        "bUseVSync=True\nFrameRateLimit=0\n"
        "bUseNanite=False\nDLSSQuality=2\nLatencyTweak2=2\nMouseSensitivity=0.7\n"
        "; latest user comment\n  ExtraOption = keep spacing  \n\n"
        "NewUserOption=keep-me\n"
        "[ScalabilityGroups]\nsg.TextureQuality=1\n"
        "[D3DRHIPreference]\nPreferredRHI=dx12\n"
        "[/Script/Unrelated.Settings]\nbUseVSync=True\n"
    )
    path.write_text(latest, encoding="utf-8")
    handler = FortniteConfigHandler()
    assert handler.restore(_backup(path, old)) is True
    expected = latest.replace("PreferredFullscreenMode=1", "PreferredFullscreenMode=0")
    expected = expected.replace("LastConfirmedFullscreenMode=1", "LastConfirmedFullscreenMode=0")
    expected = expected.replace("bUseVSync=True", "bUseVSync=False", 1)
    expected = expected.replace("FrameRateLimit=0", "FrameRateLimit=60.000000")
    assert path.read_text(encoding="utf-8") == expected
    # Repeating a baseline restore cannot resurrect old graphics settings.
    assert handler.restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == expected


def test_restore_removes_owned_keys_absent_from_backup_only_in_target_section(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    old = "[/Script/FortniteGame.FortGameUserSettings]\nbUseNanite=True\n"
    latest = (
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "bUseVSync=True\nFrameRateLimit=0\nLastConfirmedFullscreenMode=1\nbUseNanite=False\n"
        "[Other]\nbUseVSync=True\nFrameRateLimit=120\n"
    )
    path.write_text(latest, encoding="utf-8")
    assert FortniteConfigHandler().restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == (
        "[/Script/FortniteGame.FortGameUserSettings]\nbUseNanite=False\n"
        "[Other]\nbUseVSync=True\nFrameRateLimit=120\n"
    )


def test_restore_missing_target_section_preserves_other_sections(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    old = "[/Script/FortniteGame.FortGameUserSettings]\nbUseVSync=False\nbUseNanite=True\n"
    current = "[Other]\nbUseVSync=True\nUserOption=latest\n"
    path.write_text(current, encoding="utf-8")
    assert FortniteConfigHandler().restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == (
        current + "[/Script/FortniteGame.FortGameUserSettings]\nbUseVSync=False\n"
    )


def test_restore_missing_backup_section_does_not_copy_other_sections_values(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    old = "[Other]\nbUseVSync=False\n"
    current = "[Other]\nbUseVSync=True\n[/Script/FortniteGame.FortGameUserSettings]\nbUseVSync=True\nUserOption=latest\n"
    path.write_text(current, encoding="utf-8")
    assert FortniteConfigHandler().restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == current.replace("bUseVSync=True\nUserOption", "UserOption")


def test_restore_recovers_missing_file_from_full_backup(tmp_path: Path) -> None:
    path = tmp_path / "removed" / "GameUserSettings.ini"
    original = "bUseVSync=False\nUserOption=original\n[Other]\nKeep=original\n"
    assert FortniteConfigHandler().restore(_backup(path, original)) is True
    assert path.read_text(encoding="utf-8") == original


def test_restore_owned_values_into_empty_section_without_final_newline(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    section = "[/Script/FortniteGame.FortGameUserSettings]"
    old = section + "\nbUseVSync=False\nUserOption=removed-later\n"
    path.write_text("; latest comment\n" + section, encoding="utf-8")
    assert FortniteConfigHandler().restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == "; latest comment\n" + section + "\nbUseVSync=False\n"


@pytest.mark.parametrize("handler_type", [FortniteConfigHandler, MarvelRivalsConfigHandler])
def test_unchanged_unowned_content_restores_exact_backup_layout(tmp_path: Path, handler_type) -> None:
    path = tmp_path / "GameUserSettings.ini"
    original = f"[{handler_type.TARGET_SECTION_NAME}]\n; keep comment\nbUseVSync = False\nUserOption=stay\nFrameRateLimit=60.000000"
    path.write_text(original, encoding="utf-8")
    with patch.object(handler_type, "_get_config_dir", return_value=tmp_path):
        handler = handler_type()
        backup = handler.backup()
        assert handler.apply({"vsync": True, "frame_rate_limit": 0})["success"] is True
        assert handler.restore(backup) is True
    assert path.read_text(encoding="utf-8") == original


def test_flat_legacy_restore_preserves_newer_user_values_and_removes_extra_duplicates(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    old = "FrameRateLimit=60\nFrameRateLimit=120\nUserOption=old\n"
    path.write_text("FrameRateLimit=0\nUserOption=new\nFrameRateLimit=0\nFrameRateLimit=0\n", encoding="utf-8")
    assert FortniteConfigHandler().restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == "FrameRateLimit=60\nUserOption=new\nFrameRateLimit=120\n"


def test_marvel_restore_uses_its_own_reflex_framegen_and_fullscreen_ownership(tmp_path: Path) -> None:
    path = tmp_path / "GameUserSettings.ini"
    old = "bNvidiaReflex=False\nbDlssFrameGeneration=True\nFullscreenMode=0\nPreferredFullscreenMode=0\nLastConfirmedFullscreenMode=0\nUserOption=old\n"
    current = "bNvidiaReflex=True\nbDlssFrameGeneration=False\nFullscreenMode=1\nPreferredFullscreenMode=1\nLastConfirmedFullscreenMode=1\nUserOption=new\n"
    path.write_text(current, encoding="utf-8")
    assert MarvelRivalsConfigHandler().restore(_backup(path, old)) is True
    assert path.read_text(encoding="utf-8") == old.replace("UserOption=old", "UserOption=new")
