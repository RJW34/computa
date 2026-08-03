"""Tests for DolphinConfigHandler."""

from __future__ import annotations

from pathlib import Path

from abso.settings.dolphin import DolphinConfigHandler


def _write_file(path: Path, content: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")


def _prepare_slippi_config(tmp_path: Path) -> tuple[Path, Path]:
    config_dir = tmp_path / "Slippi Launcher" / "netplay" / "User" / "Config"
    gfx_ini = config_dir / "GFX.ini"
    dolphin_ini = config_dir / "Dolphin.ini"

    _write_file(
        gfx_ini,
        "\n".join(
            [
                "[Settings]",
                "EFBScale = 2",
                "BackendMultithreading = True",
                "",
                "[Enhancements]",
                "TextureScalingFactor = 2",
                "UseScalingFilter = True",
                "UseDePosterize = True",
                "",
                "[Hardware]",
                "VSync = False",
                "",
            ]
        ),
    )
    _write_file(
        dolphin_ini,
        "\n".join(
            [
                "[Core]",
                "ReduceTimingDispersion = False",
                "ImmediateXFBEnable = True",
                "RushPresentation = True",
                "SmoothPresentation = False",
                "SyncGPU = False",
                "",
            ]
        ),
    )
    return gfx_ini, dolphin_ini


def test_apply_only_updates_explicit_dolphin_keys(tmp_path: Path, monkeypatch) -> None:
    _prepare_slippi_config(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    handler = DolphinConfigHandler()
    result = handler.apply({"reduce_timing_dispersion": "True"})

    assert result["success"] is True
    content = handler.dolphin_ini.read_text(encoding="utf-8")
    assert "ReduceTimingDispersion = True" in content
    # Not explicitly requested: should remain unchanged.
    assert "RushPresentation = True" in content


def test_apply_can_set_dolphin_vsync(tmp_path: Path, monkeypatch) -> None:
    _prepare_slippi_config(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path))

    handler = DolphinConfigHandler()
    result = handler.apply({"vsync": "True"})

    assert result["success"] is True
    content = handler.gfx_ini.read_text(encoding="utf-8")
    assert "VSync = True" in content


def test_every_managed_key_is_audited_or_explicitly_waived() -> None:
    """No managed key may silently skip audit.

    SmoothPresentation drifted to True in a live config while `abso audit`
    reported clean, because the old hand-written audit() simply did not look at
    it. Adding a key map entry must now force an audit decision.
    """
    managed = set(DolphinConfigHandler.GFX_KEY_MAP) | set(
        DolphinConfigHandler.DOLPHIN_KEY_MAP
    )
    covered = set(DolphinConfigHandler.AUDIT_RULES) | set(
        DolphinConfigHandler.UNAUDITED_KEYS
    )

    assert managed - covered == set(), (
        "Managed Dolphin keys with no audit decision. Add an AUDIT_RULES entry, "
        "or add to UNAUDITED_KEYS with a reason."
    )
    assert covered - managed == set(), "Audit decision for a key that is not managed"
    assert not (
        set(DolphinConfigHandler.AUDIT_RULES)
        & set(DolphinConfigHandler.UNAUDITED_KEYS)
    ), "A key cannot be both audited and waived"


def test_audit_flags_smooth_presentation_enabled(tmp_path: Path, monkeypatch) -> None:
    """The exact live drift that motivated the table-driven audit."""
    _prepare_slippi_config(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    dolphin_ini = tmp_path / "Slippi Launcher" / "netplay" / "User" / "Config" / "Dolphin.ini"
    dolphin_ini.write_text(
        dolphin_ini.read_text(encoding="utf-8").replace(
            "SmoothPresentation = False", "SmoothPresentation = True"
        ),
        encoding="utf-8",
    )

    issues = DolphinConfigHandler().audit()

    flagged = {i["setting"]: i for i in issues}
    assert "SmoothPresentation" in flagged
    assert flagged["SmoothPresentation"]["current"] == "True"
    assert flagged["SmoothPresentation"]["recommended"] == "False"


def test_audit_ignores_profile_dependent_and_absent_keys(
    tmp_path: Path, monkeypatch
) -> None:
    """VSync differs per profile and absent keys are not misconfiguration."""
    _prepare_slippi_config(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    gfx_ini = tmp_path / "Slippi Launcher" / "netplay" / "User" / "Config" / "GFX.ini"
    gfx_ini.write_text(
        gfx_ini.read_text(encoding="utf-8").replace("VSync = False", "VSync = True"),
        encoding="utf-8",
    )

    flagged = {i["setting"] for i in DolphinConfigHandler().audit()}

    # console-parity legitimately wants VSync on.
    assert "VSync" not in flagged
    # Absent from the fixture entirely - apply() inserts it, not an issue.
    assert "BorderlessFullscreen" not in flagged


def test_detect_reports_ishiiruka_lineage(tmp_path: Path, monkeypatch) -> None:
    """Ishiiruka-exclusive GFX keys gate the mainline-only Rush guidance."""
    _prepare_slippi_config(tmp_path)
    monkeypatch.setenv("APPDATA", str(tmp_path))
    gfx_ini = tmp_path / "Slippi Launcher" / "netplay" / "User" / "Config" / "GFX.ini"

    assert DolphinConfigHandler().detect()["build_lineage"] == "mainline"

    gfx_ini.write_text(
        gfx_ini.read_text(encoding="utf-8") + "\nPredictiveFifo = False\n",
        encoding="utf-8",
    )
    assert DolphinConfigHandler().detect()["build_lineage"] == "ishiiruka"


def test_apply_inserts_missing_key_when_absent(tmp_path: Path, monkeypatch) -> None:
    config_dir = tmp_path / "Slippi Launcher" / "netplay" / "User" / "Config"
    gfx_ini = config_dir / "GFX.ini"
    dolphin_ini = config_dir / "Dolphin.ini"
    _write_file(gfx_ini, "[Settings]\nEFBScale = 1\n")
    _write_file(dolphin_ini, "[Core]\nReduceTimingDispersion = True\n")

    monkeypatch.setenv("APPDATA", str(tmp_path))
    handler = DolphinConfigHandler()
    result = handler.apply({"vsync": "True"})

    assert result["success"] is True
    content = handler.gfx_ini.read_text(encoding="utf-8")
    assert "[Hardware]" in content
    assert "VSync = True" in content
