"""Native config verification must require evidence for every requested target."""

from unittest.mock import patch

import pytest

from abso.settings.diablo4_config import Diablo4ConfigHandler
from abso.settings.rivals2_config import Rivals2ConfigHandler


@pytest.fixture(params=[Diablo4ConfigHandler, Rivals2ConfigHandler])
def handler(request):
    return request.param()


@pytest.mark.parametrize("detected", [{"config_found": False}, {"config_found": True}])
def test_missing_config_or_requested_key_is_unverifiable(handler, detected):
    with patch.object(handler, "detect", return_value=detected):
        result = handler.verify_active({"vsync": False})
    assert result["all_active"] is False
    assert result["settings"]["vsync"]["active"] is False
    assert result["settings"]["vsync"]["status"] == "unverifiable"


@pytest.mark.parametrize("reboot_pending", [False, True])
def test_internal_metadata_is_not_a_native_game_setting(handler, reboot_pending):
    with patch.object(handler, "detect", return_value={"config_found": True, "vsync": False}):
        result = handler.verify_active({"vsync": False, "_reboot_pending": reboot_pending})
    assert result["all_active"] is True
    assert set(result["settings"]) == {"vsync"}


@pytest.mark.parametrize("refresh", [None, 0, -1, RuntimeError("display unavailable")])
def test_unresolved_automatic_cap_cannot_pass_with_matching_explicit_fallback(handler, refresh):
    cap_key = "foreground_fps_limit" if isinstance(handler, Diablo4ConfigHandler) else "frame_rate_limit"
    refresh_result = {"side_effect": refresh} if isinstance(refresh, Exception) else {"return_value": refresh}
    with (
        patch.object(handler, "detect", return_value={"config_found": True, cap_key: 297}),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", **refresh_result),
    ):
        result = handler.verify_active({"auto_vrr_fps_cap": True, cap_key: 297})
    assert result["all_active"] is False
    assert result["settings"][cap_key]["active"] is True
    assert result["settings"]["auto_vrr_fps_cap"]["status"] == "unverifiable"


def test_diablo_unresolved_auto_refresh_is_not_silently_omitted():
    handler = Diablo4ConfigHandler()
    with (
        patch.object(handler, "detect", return_value={"config_found": True, "refresh_rate": 300}),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=None),
    ):
        result = handler.verify_active({"auto_refresh_rate": True, "refresh_rate": 300})
    assert result["all_active"] is False
    assert result["settings"]["refresh_rate"]["active"] is True
    assert result["settings"]["auto_refresh_rate"]["status"] == "unverifiable"


@pytest.mark.parametrize("config_found", [False, True])
def test_resolved_cap_requires_actual_native_values(handler, config_found):
    if isinstance(handler, Diablo4ConfigHandler):
        native_values = {"foreground_fps_limit": 297, "limit_foreground_fps": True}
    else:
        native_values = {"frame_rate_limit": 297}
    detected = {"config_found": config_found, **(native_values if config_found else {})}
    with (
        patch.object(handler, "detect", return_value=detected),
        patch("abso.settings.nvidia.NvidiaSettingsHandler._detect_primary_refresh_rate", return_value=300),
    ):
        result = handler.verify_active({"auto_vrr_fps_cap": True})
    assert result["all_active"] is config_found
    assert set(result["settings"]) == set(native_values)
    if not config_found:
        assert all(item["status"] == "unverifiable" for item in result["settings"].values())


def test_diablo_audit_does_not_reject_borderless_vsync_path():
    handler = Diablo4ConfigHandler()
    with patch.object(handler, "detect", return_value={
        "config_found": True, "window_mode": 1, "vsync": True, "reflex": True,
    }):
        assert handler.audit() == []
    with patch.object(handler, "detect", return_value={
        "config_found": True, "window_mode": 0, "vsync": True, "reflex": True,
    }):
        issues = handler.audit()
    assert len(issues) == 1
    assert "Windowed Fullscreen" in issues[0].optimal_value
