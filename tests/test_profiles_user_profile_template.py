from __future__ import annotations

import yaml

from abso.profiles.user_profile_template import (
    base_to_preset,
    build_user_profile_yaml_template,
)


def test_user_profile_template_quotes_yaml_sensitive_values() -> None:
    text = build_user_profile_yaml_template(
        profile_id="custom-game",
        game='My: Game "ON"',
        exe=("on", "Game:Two.exe"),
        base="reflex_shooter",
        category="Shooter",
    )

    data = yaml.safe_load(text)

    assert data["profile_id"] == "custom-game"
    assert data["display_name"] == 'My: Game "ON"'
    assert data["executable_hints"] == ["on", "Game:Two.exe"]
    assert data["settings"]["NvidiaSettingsHandler"]["preset"] == "reflex_game"
    assert data["sync_mode"] == "off"


def test_base_to_preset_uses_balanced_fallback() -> None:
    assert base_to_preset("balanced") == "vrr_optimal"
    assert base_to_preset("unknown") == "vrr_optimal"
