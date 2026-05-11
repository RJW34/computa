"""Tests for config safety helper utilities."""

from __future__ import annotations

from abso.core.config_safety import (
    apply_ini_key_patch,
    find_ini_section_bounds,
    parse_ini_assignments,
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
