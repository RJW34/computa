"""Tests for config safety helper utilities."""

from __future__ import annotations

from abso.core.config_safety import (
    apply_ini_key_patch,
    find_ini_section_bounds,
    parse_ini_assignments,
    restore_managed_key_lines,
    validate_allowed_keys,
)


def test_validate_allowed_keys_returns_only_invalid_keys() -> None:
    invalid = validate_allowed_keys(
        requested_keys={"fullscreen_mode", "raw_input", "player_tag"},
        allowed_keys={"fullscreen_mode", "raw_input"},
    )
    assert invalid == ["player_tag"]


def test_parse_ini_assignments_parses_key_values() -> None:
    lines = [
        "FullscreenMode=1",
        "bUseVSync=True",
        "; comment",
        "NoEqualsHere",
    ]
    parsed = parse_ini_assignments(lines)
    assert parsed["FullscreenMode"] == "1"
    assert parsed["bUseVSync"] == "True"
    assert "NoEqualsHere" not in parsed


def test_apply_ini_key_patch_updates_and_appends() -> None:
    lines = [
        "FullscreenMode=1",
        "PlayerTag=goofy",
    ]
    replacements = {
        "FullscreenMode": "0",
        "bUseRawInput": "True",
    }

    result = apply_ini_key_patch(lines, replacements, append_missing=True)

    assert result.changed is True
    assert result.changed_keys == {"FullscreenMode"}
    assert result.appended_keys == {"bUseRawInput"}
    assert "PlayerTag=goofy" in result.lines
    assert "FullscreenMode=0" in result.lines
    assert "bUseRawInput=True" in result.lines


def test_apply_ini_key_patch_scopes_to_named_section() -> None:
    lines = [
        "[/Script/Other.Settings]",
        "FullscreenMode=2",
        "PlayerTag=goofy",
        "[/Script/Engine.GameUserSettings]",
        "FullscreenMode=1",
        "bUseVSync=True",
        "[/Script/Another.Section]",
        "FullscreenMode=2",
    ]

    assert find_ini_section_bounds(lines, "/Script/Engine.GameUserSettings") == (4, 6)

    result = apply_ini_key_patch(
        lines,
        {
            "FullscreenMode": "0",
            "bUseVSync": "False",
            "FrameRateLimit": "297",
        },
        append_missing=True,
        section_name="/Script/Engine.GameUserSettings",
    )

    assert result.changed_keys == {"FullscreenMode", "bUseVSync"}
    assert result.appended_keys == {"FrameRateLimit"}
    assert result.lines == [
        "[/Script/Other.Settings]",
        "FullscreenMode=2",
        "PlayerTag=goofy",
        "[/Script/Engine.GameUserSettings]",
        "FullscreenMode=0",
        "bUseVSync=False",
        "FrameRateLimit=297",
        "[/Script/Another.Section]",
        "FullscreenMode=2",
    ]

    parsed = parse_ini_assignments(
        result.lines,
        section_name="/Script/Engine.GameUserSettings",
    )
    assert parsed == {
        "FullscreenMode": "0",
        "bUseVSync": "False",
        "FrameRateLimit": "297",
    }


def test_bom_header_scopes_parsing_and_patching_without_rewriting_header() -> None:
    lines = [
        "\ufeff[/Script/Engine.GameUserSettings]",
        "bUseVSync=False",
        "[Other]",
        "bUseVSync=True",
    ]
    section = "/Script/Engine.GameUserSettings"
    assert find_ini_section_bounds(lines, section) == (1, 2)
    assert parse_ini_assignments(lines, section_name=section) == {"bUseVSync": "False"}

    result = apply_ini_key_patch(
        lines, {"bUseVSync": "False", "FrameRateLimit": "0"},
        append_missing=True, section_name=section,
    )
    assert result.changed_keys == set()
    assert result.appended_keys == {"FrameRateLimit"}
    assert result.lines == [
        "\ufeff[/Script/Engine.GameUserSettings]",
        "bUseVSync=False",
        "FrameRateLimit=0",
        "[Other]",
        "bUseVSync=True",
    ]
    assert lines[0] == "\ufeff[/Script/Engine.GameUserSettings]"


def test_bom_normalization_does_not_create_missing_section_bounds() -> None:
    lines = ["\ufeff[Other]", "bUseVSync=True"]
    assert find_ini_section_bounds(lines, "/Script/Engine.GameUserSettings") is None
    assert find_ini_section_bounds(lines, None) is None
def test_restore_managed_key_lines_preserves_unmanaged_current_state() -> None:
    backup = (
        "[/Script/Game.Settings]\r\n"
        "FullscreenMode=0\r\n"
        "bUseVSync=False\r\n"
        "BackupOnlyUserValue=old\r\n"
        "[/Script/Other.Settings]\r\n"
        "FullscreenMode=7\r\n"
    )
    current = (
        "[/Script/Game.Settings]\r\n"
        "FullscreenMode=1\r\n"
        "FrameRateLimit=297\r\n"
        "CurrentUserValue=new\r\n"
        "[/Script/Other.Settings]\r\n"
        "FullscreenMode=9\r\n"
    )

    restored = restore_managed_key_lines(
        current_content=current,
        backup_content=backup,
        managed_keys={"FullscreenMode", "bUseVSync", "FrameRateLimit"},
        section_name="/Script/Game.Settings",
    )

    assert restored == (
        "[/Script/Game.Settings]\r\n"
        "FullscreenMode=0\r\n"
        "CurrentUserValue=new\r\n"
        "bUseVSync=False\r\n"
        "[/Script/Other.Settings]\r\n"
        "FullscreenMode=9\r\n"
    )


def test_restore_managed_key_lines_is_strict_when_section_is_missing() -> None:
    current = "[Other]\nFullscreenMode=2\n"
    backup = "[Target]\nFullscreenMode=0\n"

    restored = restore_managed_key_lines(
        current_content=current,
        backup_content=backup,
        managed_keys={"FullscreenMode"},
        section_name="Target",
    )

    assert restored == current


def test_restore_managed_key_lines_supports_headerless_legacy_ini() -> None:
    restored = restore_managed_key_lines(
        current_content="FullscreenMode=1\nUserChoice=current\n",
        backup_content="FullscreenMode=0\nUserChoice=old\n",
        managed_keys={"FullscreenMode"},
        section_name="/Script/Game.Settings",
    )

    assert restored == "FullscreenMode=0\nUserChoice=current\n"
