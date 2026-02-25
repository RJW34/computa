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
