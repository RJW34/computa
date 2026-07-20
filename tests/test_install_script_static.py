"""Static contract checks for the GUI installer (scripts/install.ps1).

The installer ships as a bare release asset next to computa.exe, so it must
stay self-contained, ASCII-safe for ANSI-assuming PowerShell 5.1 hosts, and
on the phosphor design system without dot-sourcing repo theme modules.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
INSTALL_PS1 = REPO_ROOT / "scripts" / "install.ps1"
INSTALL_CMD = REPO_ROOT / "scripts" / "Install computa.cmd"


def _text() -> str:
    return INSTALL_PS1.read_text(encoding="utf-8")


def test_installer_exists_with_cmd_shim() -> None:
    assert INSTALL_PS1.exists()
    assert INSTALL_CMD.exists()


def test_installer_is_pure_ascii() -> None:
    """PS 5.1 reads BOM-less scripts as ANSI; non-ASCII literals corrupt.

    Glyphs must be built from [char] codes, never pasted literally.
    """
    text = _text()
    non_ascii = sorted({c for c in text if ord(c) > 127})
    assert not non_ascii, f"Non-ASCII characters found: {non_ascii!r}"


def test_installer_is_self_contained() -> None:
    """No dot-sourcing of tray/theme modules: friends only get this file."""
    text = _text()
    assert "ABSO-Theme.ps1" not in text
    assert "ABSO-ThemePack.ps1" not in text
    assert ". (Join-Path" not in text


def test_installer_avoids_cmdlets_that_break_in_hidden_hosts() -> None:
    """Hidden PS hosts here cannot autoload Get-FileHash (project memory)."""
    assert "Get-FileHash" not in _text()


def test_installer_backend_contract() -> None:
    """The window drives computa.exe via the hidden setup modes."""
    text = _text()
    assert '"setup", "--plan"' in text
    assert '@("setup", "--unattended")' in text
    for flag in (
        "--baseline",
        "--no-baseline",
        "--tray-autostart",
        "--no-tray-autostart",
        "--remove-kb",
    ):
        assert flag in text, f"missing backend flag wiring: {flag}"


def test_installer_never_applies_a_profile() -> None:
    """Installing must not change game/Windows settings; applies come later."""
    text = _text()
    assert '"apply"' not in text
    assert "--profile" not in text


def test_installer_uses_phosphor_palette_and_font_stacks() -> None:
    text = _text()
    assert "255, 4, 15, 18" in text  # Ink0 window surface
    assert "255, 0, 245, 212" in text  # Signal primary action
    assert "255, 225, 244, 240" in text  # Paper text
    assert '"Bahnschrift"' in text
    assert '"Cascadia Mono"' in text
    # Fonts resolve through the stack helper, not ad-hoc constructions.
    assert "function New-InstallerFont" in text


def test_installer_keeps_console_fallback_and_test_switches() -> None:
    text = _text()
    assert "[switch]$Console" in text
    assert "[switch]$SafeDefaults" in text
    assert '[string]$PreviewUi' in text
    assert "Invoke-ConsoleInstall" in text


def test_installer_elevates_hidden() -> None:
    """The end user must never see a console window in GUI mode."""
    text = _text()
    assert "-Verb RunAs" in text
    assert '"-WindowStyle", "Hidden"' in text


def test_cmd_shim_launches_installer_hidden() -> None:
    content = INSTALL_CMD.read_text(encoding="utf-8")
    assert "install.ps1" in content
    assert "-WindowStyle Hidden" in content
    assert "-ExecutionPolicy Bypass" in content
