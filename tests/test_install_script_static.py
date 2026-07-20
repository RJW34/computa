"""Static contract checks for the install/onboarding surfaces.

Three files make up the friend-facing install story:

- ``scripts/installer.iss`` — Inno Setup definition for computa-setup.exe,
  the standard double-click Windows installer (files, uninstall entry,
  optional PATH, first-run launch).
- ``abso/tray/ABSO-FirstRun.ps1`` — the phosphor first-run setup window
  (preflight, games/display survey, safety snapshot, streamed progress).
  Ships as a tray asset; must stay ASCII-safe for ANSI-assuming PS 5.1.
- ``scripts/install.ps1`` — portable/power-user console path only; the GUI
  lives in the first-run window, never here.
"""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).parent.parent
FIRSTRUN_PS1 = REPO_ROOT / "abso" / "tray" / "ABSO-FirstRun.ps1"
FIRSTRUN_VBS = REPO_ROOT / "abso" / "tray" / "ABSO-FirstRun.vbs"
INSTALL_PS1 = REPO_ROOT / "scripts" / "install.ps1"
INSTALLER_ISS = REPO_ROOT / "scripts" / "installer.iss"


def _firstrun() -> str:
    return FIRSTRUN_PS1.read_text(encoding="utf-8")


def test_surfaces_exist() -> None:
    assert FIRSTRUN_PS1.exists()
    assert FIRSTRUN_VBS.exists()
    assert INSTALL_PS1.exists()
    assert INSTALLER_ISS.exists()
    # The pre-setup.exe cmd shim is gone; the installer is the entry point.
    assert not (REPO_ROOT / "scripts" / "Install computa.cmd").exists()


# --- first-run window ------------------------------------------------------


def test_firstrun_is_pure_ascii() -> None:
    """PS 5.1 reads BOM-less scripts as ANSI; non-ASCII literals corrupt.

    Glyphs must be built from [char] codes, never pasted literally.
    """
    text = _firstrun()
    non_ascii = sorted({c for c in text if ord(c) > 127})
    assert not non_ascii, f"Non-ASCII characters found: {non_ascii!r}"


def test_firstrun_avoids_cmdlets_that_break_in_hidden_hosts() -> None:
    """Hidden PS hosts here cannot autoload Get-FileHash (project memory)."""
    assert "Get-FileHash" not in _firstrun()


def test_firstrun_backend_contract() -> None:
    """The window drives computa.exe via the hidden setup modes."""
    text = _firstrun()
    assert '"setup", "--plan"' in text
    assert '@("setup", "--unattended")' in text
    for flag in (
        "--baseline",
        "--no-baseline",
        "--tray-autostart",
        "--no-tray-autostart",
        "--remove-kb",
        "--game",
        "--hdr",
        "--no-hdr",
        "--vrr",
        "--no-vrr",
        "--capture",
        "--no-capture",
    ):
        assert flag in text, f"missing backend flag wiring: {flag}"


def test_firstrun_has_survey_page() -> None:
    """Games + display survey: the tray gets tuned to what the user plays."""
    text = _firstrun()
    assert '"survey"' in text  # PreviewUi state
    assert "CheckedListBox" in text
    assert "Your games" in text
    assert "Your display" in text
    assert "game_catalog" in text


def test_firstrun_never_applies_a_profile() -> None:
    """First-run must not change game/Windows settings; applies come later."""
    text = _firstrun()
    assert '"apply"' not in text
    assert "--profile" not in text


def test_firstrun_uses_phosphor_palette_and_font_stacks() -> None:
    text = _firstrun()
    assert "255, 4, 15, 18" in text  # Ink0 window surface
    assert "255, 0, 245, 212" in text  # Signal primary action
    assert "255, 225, 244, 240" in text  # Paper text
    assert '"Bahnschrift"' in text
    assert '"Cascadia Mono"' in text
    assert "function New-InstallerFont" in text


def test_firstrun_elevates_hidden() -> None:
    """The end user must never see a console window."""
    text = _firstrun()
    assert "-Verb RunAs" in text
    assert '"-WindowStyle", "Hidden"' in text


def test_firstrun_vbs_launches_hidden() -> None:
    content = FIRSTRUN_VBS.read_text(encoding="utf-8")
    assert "ABSO-FirstRun.ps1" in content
    assert "-WindowStyle Hidden" in content


# --- portable console installer --------------------------------------------


def test_portable_installer_is_console_only() -> None:
    """The GUI lives in ABSO-FirstRun.ps1; install.ps1 stays a console tool."""
    text = INSTALL_PS1.read_text(encoding="utf-8")
    assert "System.Windows.Forms" not in text
    assert "computa-setup.exe" in text  # points users at the real installer
    assert "Copy-Item" in text


# --- Inno Setup definition --------------------------------------------------


def test_installer_iss_contract() -> None:
    text = INSTALLER_ISS.read_text(encoding="utf-8")
    assert "AppName=computa" in text
    # Per-user install: no UAC for the install itself; the first-run window
    # elevates on its own when it actually needs admin.
    assert "PrivilegesRequired=lowest" in text
    assert r"DefaultDirName={localappdata}\AdaptiveBattleStationOptimizer" in text
    assert "computa.exe" in text
    assert "ABSO-FirstRun.vbs" in text
    assert "postinstall" in text  # finish page offers first-run setup
    assert "NeedsAddPath" in text  # PATH task adds without duplicating
    assert "'uninstall','--yes'" in text  # uninstall restores the baseline
    assert "MinVersion=10.0.22000" in text  # Windows 11 only, refused clearly
