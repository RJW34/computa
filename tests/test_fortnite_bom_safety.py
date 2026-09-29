"""Fortnite's guard, readback and writer must agree on BOM-prefixed sections."""

from unittest.mock import patch

from abso.settings.fortnite_config import FortniteConfigHandler


def test_bom_fortnite_readback_does_not_borrow_another_sections_vsync(tmp_path):
    ini_path = tmp_path / "GameUserSettings.ini"
    content = (
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "bUseVSync=False\nLatencyTweak2=1\n"
        "[Other]\nbUseVSync=True\nLatencyTweak2=2\n"
    )
    ini_path.write_text(content, encoding="utf-8-sig")
    original = ini_path.read_bytes()
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=tmp_path):
        handler = FortniteConfigHandler()
        detected = handler.detect()
        verification = handler.verify_active({"vsync": True, "require_reflex": True})

    assert detected["vsync"] is False
    assert detected["reflex_mode"] == 1
    assert verification["all_active"] is False
    assert verification["settings"]["vsync"]["current"] is False
    assert verification["manual_steps"][0]["current"] == 1
    assert ini_path.read_bytes() == original


def test_bom_fortnite_patch_preserves_other_section_and_bom(tmp_path):
    ini_path = tmp_path / "GameUserSettings.ini"
    content = (
        "[/Script/FortniteGame.FortGameUserSettings]\n"
        "bUseVSync=False\nLatencyTweak2=1\n"
        "[Other]\nbUseVSync=True\nFrameRateLimit=123\nLatencyTweak2=2\n"
    )
    ini_path.write_text(content, encoding="utf-8-sig")
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=tmp_path):
        handler = FortniteConfigHandler()
        result = handler.apply({"vsync": False, "frame_rate_limit": 0, "require_reflex": True})
        verification = handler.verify_active({"vsync": False, "frame_rate_limit": 0})

    assert result["success"] is True
    assert result["applied"] == ["FrameRateLimit"]
    assert verification["all_active"] is True
    assert ini_path.read_bytes().startswith(b"\xef\xbb\xbf")
    assert ini_path.read_text(encoding="utf-8-sig") == content.replace(
        "[Other]", "FrameRateLimit=0\n[Other]"
    )


def test_bom_other_section_does_not_satisfy_fortnite_missing_section_guard(tmp_path):
    ini_path = tmp_path / "GameUserSettings.ini"
    ini_path.write_text("[Other]\nbUseVSync=True\nLatencyTweak2=2\n", encoding="utf-8-sig")
    original = ini_path.read_bytes()
    with patch.object(FortniteConfigHandler, "_get_config_dir", return_value=tmp_path):
        handler = FortniteConfigHandler()
        result = handler.apply({"vsync": False, "require_reflex": True})
        verification = handler.verify_active({"vsync": True, "require_reflex": True})

    assert result["success"] is False
    assert "section is missing" in result["error"]
    assert verification["all_active"] is False
    assert verification["manual_steps"][0]["satisfied"] is None
    assert ini_path.read_bytes() == original
