"""Tests for manifest loading and linter integration."""

from __future__ import annotations

import json
from unittest.mock import patch

from abso.core.linter import ProfileLinter
from abso.core.manifests import load_game_detection_manifest, load_linter_rules


def test_load_linter_rules_uses_fallback_when_manifest_missing(tmp_path) -> None:
    fallback = {"reflex_presets": ["reflex_game"]}

    with patch("abso.core.manifests.MANIFESTS_DIR", tmp_path):
        load_linter_rules.cache_clear()
        data = load_linter_rules(json.dumps(fallback, sort_keys=True))

    assert data == fallback


def test_load_game_detection_manifest_uses_fallback_when_manifest_missing(tmp_path) -> None:
    fallback = {"steam_game_patterns": {"Game": ["game.exe"]}}

    with patch("abso.core.manifests.MANIFESTS_DIR", tmp_path):
        load_game_detection_manifest.cache_clear()
        data = load_game_detection_manifest(json.dumps(fallback, sort_keys=True))

    assert data == fallback


def test_profile_linter_loads_manifest_rules() -> None:
    manifest_rules = {
        "reflex_presets": ["custom_reflex"],
        "llm_ultra_presets": ["custom_ultra"],
        "fast_sync_presets": [],
        "emulator_targets": ["custom_target"],
        "rollback_targets": ["custom_rollback"],
        "dx12_vulkan_indicators": ["custom_api"],
    }
    with patch("abso.core.linter.load_linter_rules", return_value=manifest_rules):
        linter = ProfileLinter()

    assert linter.reflex_presets == {"custom_reflex"}
    assert linter.llm_ultra_presets == {"custom_ultra"}
    assert linter.rollback_targets == {"custom_rollback"}
