"""Static + functional checks for the tray icon/sound theme-pack system."""

from __future__ import annotations

import json
from pathlib import Path

import build
from abso.core.health import TRAY_RUNTIME_MODULES

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAY_DIR = REPO_ROOT / "abso" / "tray"
TRAY_SCRIPT = TRAY_DIR / "ABSO-Tray.ps1"
ICONS_SCRIPT = TRAY_DIR / "ABSO-Icons.ps1"
SETTINGS_SCRIPT = TRAY_DIR / "ABSO-Settings.ps1"
THEME_PACK_SCRIPT = TRAY_DIR / "ABSO-ThemePack.ps1"
DEFAULT_THEME_MANIFEST = TRAY_DIR / "themes" / "default" / "theme.json"

# The pre-theme-pack personal media that used to sit in the tray root. None of
# these may ever reappear in the repo root or be referenced by the scripts:
# they are not redistributable.
LEGACY_PERSONAL_MEDIA = (
    "260 Swampert.ico",
    "pokemon_pc_idle.ico",
    "favicon.ico",
    "icon0260_f00_s0.ico",
    "icon0260_f01_s0.ico",
    "pokemon-red_blue_yellow-save-game-sound-effect.mp3",
    "hit-weak-not-very-effective.mp3",
    "oot_navi_hey1.mp3",
    "pokemon-redblueyellow-item-found-sound-effect.mp3",
)


def test_theme_pack_module_is_loaded_before_icons() -> None:
    """Icon generation consults the theme pack, so it must load first."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    theme_pack_load = tray.index('. (Join-Path $script:ScriptDir "ABSO-ThemePack.ps1")')
    icons_load = tray.index('. (Join-Path $script:ScriptDir "ABSO-Icons.ps1")')
    assert theme_pack_load < icons_load


def test_theme_pack_module_is_hash_tracked() -> None:
    """Runtime-marker and health hash manifests must cover the theme module."""
    assert "ABSO-ThemePack.ps1" in TRAY_RUNTIME_MODULES
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '"ABSO-ThemePack.ps1",' in tray


def test_sound_events_route_through_theme_cues() -> None:
    """Every sound event resolves via Get-ThemeSoundCue, not a fixed file."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    for sound_event in ("success", "fail", "vrrWarning", "restart"):
        assert f'Get-ThemeSoundCue -SoundEvent "{sound_event}"' in tray


def test_state_icons_route_through_theme_pack() -> None:
    """State icons and the apply animation resolve through the theme pack."""
    icons = ICONS_SCRIPT.read_text(encoding="utf-8")
    assert "Get-ThemeIconPath -State $State" in icons
    assert "Get-ThemeApplySequencePaths" in icons


def test_no_personal_media_in_tray_root_or_scripts() -> None:
    """Non-redistributable media stays out of the tray root and all scripts."""
    for name in LEGACY_PERSONAL_MEDIA:
        assert not (TRAY_DIR / name).exists(), name

    for script in sorted(TRAY_DIR.glob("*.ps1")):
        text = script.read_text(encoding="utf-8")
        for name in LEGACY_PERSONAL_MEDIA:
            assert name not in text, f"{script.name} references {name}"


def test_default_theme_is_self_contained() -> None:
    """The shipped default theme needs no media files at all."""
    manifest = json.loads(DEFAULT_THEME_MANIFEST.read_text(encoding="utf-8"))

    icons = manifest["icons"]
    for key in ("idle", "active", "gaming", "applying", "warning", "error"):
        assert icons[key] is None, f"default theme must not require an icon file for {key}"
    assert icons["applySequence"] == []

    sounds = manifest["sounds"]
    for key in ("success", "fail", "vrrWarning", "restart"):
        value = sounds[key]
        assert value == "none" or value.startswith("system:"), (
            f"default theme sound '{key}' must be a system cue or none, got {value!r}"
        )


def test_theme_pack_defaults_cover_all_sound_events() -> None:
    """Built-in cue fallbacks exist for every sound event the tray plays."""
    theme_pack = THEME_PACK_SCRIPT.read_text(encoding="utf-8")
    for sound_event in ("success", "fail", "vrrWarning", "restart"):
        assert sound_event in theme_pack
    assert "system:Asterisk" in theme_pack


def test_tray_config_defaults_include_theme_selection() -> None:
    """Get-DefaultConfig carries the theme key so config merge preserves it."""
    settings = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    assert 'theme           = "default"' in settings


def test_build_ships_theme_packs_and_purges_legacy_root_media(tmp_path, monkeypatch) -> None:
    """Deploy copies themes/<name>/ trees and removes stale root media."""
    root = tmp_path / "repo"
    dist = root / "dist"
    tray = root / "abso" / "tray"
    theme_dir = tray / "themes" / "custom"
    install = tmp_path / "install"
    installed_tray = install / "abso" / "tray"

    dist.mkdir(parents=True)
    theme_dir.mkdir(parents=True)
    installed_tray.mkdir(parents=True)

    (dist / "computa.exe").write_bytes(b"backend")
    (tray / "ABSO-Tray.ps1").write_text("# tray", encoding="utf-8")
    (theme_dir / "theme.json").write_text('{"name": "Custom"}', encoding="utf-8")
    (theme_dir / "active.ico").write_bytes(b"icon")
    (theme_dir / "success.wav").write_bytes(b"wav")
    (theme_dir / "notes.txt").write_text("not deployable", encoding="utf-8")
    # Stale pre-theme-pack media in the installed tray root must be purged.
    (installed_tray / "260 Swampert.ico").write_bytes(b"old icon")
    (installed_tray / "oot_navi_hey1.mp3").write_bytes(b"old sound")

    monkeypatch.setattr(build, "ROOT_DIR", root)
    monkeypatch.setattr(build, "DIST_DIR", dist)
    monkeypatch.setattr(build, "GUI_DIR", root / "gui")
    monkeypatch.setattr(build, "GUI_BINARIES_DIR", root / "gui" / "src-tauri" / "binaries")

    result = build.deploy_local_runtime(install_dir=install)

    deployed_theme = installed_tray / "themes" / "custom"
    assert (deployed_theme / "theme.json").read_text(encoding="utf-8") == '{"name": "Custom"}'
    assert (deployed_theme / "active.ico").read_bytes() == b"icon"
    assert (deployed_theme / "success.wav").read_bytes() == b"wav"
    assert not (deployed_theme / "notes.txt").exists()
    assert not (installed_tray / "260 Swampert.ico").exists()
    assert not (installed_tray / "oot_navi_hey1.mp3").exists()
    assert result["tray_file_count"] == 4
    assert result["tray_removed_count"] == 2


def test_gitignore_keeps_personal_themes_local() -> None:
    """Only the default theme (and docs) are tracked; other themes stay local."""
    gitignore = (REPO_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert "abso/tray/themes/*" in gitignore
    assert "!abso/tray/themes/default/" in gitignore
    assert "!abso/tray/themes/README.md" in gitignore
