"""Tests for DisplayColorRangeHandler.

All NVAPI interaction is mocked — these tests never load nvapi64.dll and
never call the NVIDIA driver, so they're safe to run on any system.
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from abso.settings.display_range import DisplayColorRangeHandler
from abso.settings.nvidia.nvapi_display import (
    NvColorSelectionPolicy,
    NvDynamicRange,
    parse_dynamic_range,
)

# ---------------------------------------------------------------------------
# parse_dynamic_range
# ---------------------------------------------------------------------------


def test_parse_dynamic_range_full_aliases():
    for label in ("full", "Full", "FULL", "vesa", "pc"):
        assert parse_dynamic_range(label) == NvDynamicRange.VESA


def test_parse_dynamic_range_limited_aliases():
    for label in ("limited", "Limited", "cea", "tv"):
        assert parse_dynamic_range(label) == NvDynamicRange.CEA


def test_parse_dynamic_range_auto_and_unknown():
    assert parse_dynamic_range("auto") == NvDynamicRange.AUTO
    assert parse_dynamic_range(None) == NvDynamicRange.AUTO
    assert parse_dynamic_range("gibberish") == NvDynamicRange.AUTO


def test_parse_dynamic_range_int_passthrough():
    assert parse_dynamic_range(0) == NvDynamicRange.VESA
    assert parse_dynamic_range(1) == NvDynamicRange.CEA
    assert parse_dynamic_range(0xFF) == NvDynamicRange.AUTO


# ---------------------------------------------------------------------------
# Handler behavior without NVAPI
# ---------------------------------------------------------------------------


def _make_handler_with_mock(nvapi_available: bool, **nvapi_attrs):
    """Return a DisplayColorRangeHandler wired to a MagicMock NVAPIDisplay."""
    handler = DisplayColorRangeHandler()

    mock_nvapi = MagicMock()
    mock_nvapi._initialized = nvapi_available
    mock_nvapi.initialize.return_value = nvapi_available
    for attr, value in nvapi_attrs.items():
        setattr(mock_nvapi, attr, value)

    # Bypass real NVAPI init by injecting the mock directly.
    handler._nvdisp = mock_nvapi if nvapi_available else None

    # Patch NVAPIDisplay() so _ensure_nvapi() never constructs a real one.
    patcher = patch(
        "abso.settings.display_range.NVAPIDisplay",
        return_value=mock_nvapi,
    )
    patcher.start()
    return handler, mock_nvapi, patcher


def test_detect_returns_empty_when_nvapi_unavailable():
    handler = DisplayColorRangeHandler()
    with patch("abso.settings.display_range.NVAPIDisplay") as nvapi_cls:
        mock_nvapi = MagicMock()
        mock_nvapi._initialized = False
        mock_nvapi.initialize.return_value = False
        nvapi_cls.return_value = mock_nvapi

        result = handler.detect()

    assert result["displays"] == []
    assert result["display_count"] == 0
    assert result["any_limited"] is False


def test_audit_returns_empty_when_no_displays():
    handler = DisplayColorRangeHandler()
    with patch("abso.settings.display_range.NVAPIDisplay") as nvapi_cls:
        mock = MagicMock()
        mock._initialized = False
        mock.initialize.return_value = False
        nvapi_cls.return_value = mock

        assert handler.audit() == []


def test_audit_flags_limited_displays():
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [111, 222]
        mock_nvapi.get_color.side_effect = [
            {
                "display_id": 111,
                "dynamic_range": NvDynamicRange.CEA,
                "dynamic_range_label": "limited",
                "color_selection_policy": NvColorSelectionPolicy.USER,
            },
            {
                "display_id": 222,
                "dynamic_range": NvDynamicRange.VESA,
                "dynamic_range_label": "full",
                "color_selection_policy": NvColorSelectionPolicy.USER,
            },
        ]

        issues = handler.audit()

        assert any(i.title.startswith("NVIDIA Output Dynamic Range set to Limited") for i in issues)
        assert issues[0].severity == "warning"
        assert "111" in issues[0].current_value
        assert "222" not in issues[0].current_value
    finally:
        patcher.stop()


def test_audit_flags_non_user_policy_when_no_limited():
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [42]
        mock_nvapi.get_color.return_value = {
            "display_id": 42,
            "dynamic_range": NvDynamicRange.VESA,
            "dynamic_range_label": "full",
            "color_selection_policy": NvColorSelectionPolicy.BEST_QUALITY,
        }

        issues = handler.audit()
        titles = [i.title for i in issues]
        assert any("non-USER" in t for t in titles)
        # Severity is info, not warning, when the range itself is fine.
        non_user = next(i for i in issues if "non-USER" in i.title)
        assert non_user.severity == "info"
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# apply
# ---------------------------------------------------------------------------


def test_apply_is_noop_without_dynamic_range_key():
    handler = DisplayColorRangeHandler()
    with patch("abso.settings.display_range.NVAPIDisplay") as nvapi_cls:
        # No call should be made on the mock NVAPI when settings is empty.
        mock_nvapi = MagicMock()
        nvapi_cls.return_value = mock_nvapi

        result = handler.apply({})

        assert result["success"] is True
        assert result["requires_reboot"] is False
        mock_nvapi.initialize.assert_not_called()


def test_apply_skips_when_nvapi_unavailable():
    handler = DisplayColorRangeHandler()
    with patch("abso.settings.display_range.NVAPIDisplay") as nvapi_cls:
        mock_nvapi = MagicMock()
        mock_nvapi._initialized = False
        mock_nvapi.initialize.return_value = False
        nvapi_cls.return_value = mock_nvapi

        result = handler.apply({"dynamic_range": "full"})

        assert result["success"] is True  # graceful skip
        assert result["applied"] == []
        assert any("NVAPI" in msg for msg in result["skipped"])


def test_apply_full_range_on_two_displays():
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [101, 202]
        mock_nvapi.set_dynamic_range.side_effect = [
            {"display_id": 101, "success": True, "before": 1, "after": 0, "changed": True},
            {"display_id": 202, "success": True, "before": 0, "after": 0, "changed": False},
        ]

        result = handler.apply({"dynamic_range": "full"})

        assert result["success"] is True
        assert len(result["applied"]) == 2
        assert result["changed"] is True
        assert result["changed_keys"] == ["dynamic_range"]
        assert any("101" in entry and "Full" in entry for entry in result["applied"])
        assert any("202" in entry and "already" in entry for entry in result["applied"])
        # Must call with VESA for "full"
        args_list = mock_nvapi.set_dynamic_range.call_args_list
        assert args_list[0].args[1] == NvDynamicRange.VESA
        assert args_list[1].args[1] == NvDynamicRange.VESA
    finally:
        patcher.stop()


def test_apply_is_idempotent_second_call():
    """Two consecutive apply(full) calls should both succeed without error."""
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [1]
        # First call actually changes; second call is already-full.
        mock_nvapi.set_dynamic_range.side_effect = [
            {"display_id": 1, "success": True, "before": 1, "after": 0, "changed": True},
            {"display_id": 1, "success": True, "before": 0, "after": 0, "changed": False},
        ]

        first = handler.apply({"dynamic_range": "full"})
        second = handler.apply({"dynamic_range": "full"})

        assert first["success"] is True
        assert first["changed"] is True
        assert second["success"] is True
        assert second["changed"] is False
    finally:
        patcher.stop()


def test_apply_collects_errors_from_per_display_failures():
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [1, 2]
        mock_nvapi.set_dynamic_range.side_effect = [
            {
                "display_id": 1,
                "success": False,
                "before": 1,
                "after": None,
                "changed": False,
                "error": "SET failed: NVAPI status -9 (struct v5)",
            },
            {"display_id": 2, "success": True, "before": 0, "after": 0, "changed": False},
        ]

        result = handler.apply({"dynamic_range": "full"})

        assert result["success"] is False
        assert result["error"] is not None
        assert "Display 1" in result["error"]
        # Successful display should still appear under applied.
        assert any("2" in entry for entry in result["applied"])
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# backup/restore
# ---------------------------------------------------------------------------


def test_backup_returns_empty_when_nvapi_missing():
    handler = DisplayColorRangeHandler()
    with patch("abso.settings.display_range.NVAPIDisplay") as nvapi_cls:
        mock = MagicMock()
        mock._initialized = False
        mock.initialize.return_value = False
        nvapi_cls.return_value = mock

        assert handler.backup() == {"displays": []}


def test_restore_is_noop_without_data():
    handler = DisplayColorRangeHandler()
    assert handler.restore({}) is True
    assert handler.restore({"displays": []}) is True


def test_restore_round_trips_per_display_state():
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [7, 8]
        mock_nvapi.set_dynamic_range.side_effect = [
            {"display_id": 7, "success": True, "before": 0, "after": 1, "changed": True},
            {"display_id": 8, "success": True, "before": 1, "after": 0, "changed": True},
        ]

        ok = handler.restore(
            {
                "displays": [
                    {"display_id": 7, "dynamic_range": NvDynamicRange.CEA},
                    {"display_id": 8, "dynamic_range": NvDynamicRange.VESA},
                ]
            }
        )

        assert ok is True
        calls = mock_nvapi.set_dynamic_range.call_args_list
        assert calls[0].args == (7, NvDynamicRange.CEA)
        assert calls[1].args == (8, NvDynamicRange.VESA)
    finally:
        patcher.stop()


def test_restore_skips_disconnected_displays():
    handler, mock_nvapi, patcher = _make_handler_with_mock(nvapi_available=True)
    try:
        mock_nvapi.enumerate_display_ids.return_value = [5]  # backed-up 9 is gone
        mock_nvapi.set_dynamic_range.return_value = {
            "display_id": 5,
            "success": True,
            "before": 0,
            "after": 0,
            "changed": False,
        }

        ok = handler.restore(
            {
                "displays": [
                    {"display_id": 5, "dynamic_range": NvDynamicRange.VESA},
                    {"display_id": 9, "dynamic_range": NvDynamicRange.CEA},
                ]
            }
        )

        assert ok is True
        # 9 is disconnected — must not call set_dynamic_range for it.
        calls = [c.args[0] for c in mock_nvapi.set_dynamic_range.call_args_list]
        assert 5 in calls
        assert 9 not in calls
    finally:
        patcher.stop()


# ---------------------------------------------------------------------------
# Integration-lite: profile wiring surfaces the handler
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "profile_import_path,profile_cls_name",
    [
        ("abso.profiles.overwatch2", "Overwatch2GSyncHDRProfile"),
        ("abso.profiles.overwatch2", "Overwatch2NoSyncHDRProfile"),
        ("abso.profiles.marvel_rivals", "MarvelRivalsHDRProfile"),
        ("abso.profiles.fortnite", "FortniteHDRProfile"),
        ("abso.profiles.diablo4", "Diablo4Profile"),
    ],
)
def test_profile_includes_display_color_range_handler(profile_import_path, profile_cls_name):
    import importlib

    module = importlib.import_module(profile_import_path)
    profile_cls = getattr(module, profile_cls_name)
    profile = profile_cls()
    handler_names = [h.__class__.__name__ for h in profile.get_handlers()]
    assert "DisplayColorRangeHandler" in handler_names


@pytest.mark.parametrize(
    "profile_import_path,profile_cls_name",
    [
        ("abso.profiles.overwatch2", "Overwatch2GSyncHDRProfile"),
        ("abso.profiles.marvel_rivals", "MarvelRivalsHDRProfile"),
        ("abso.profiles.diablo4", "Diablo4Profile"),
    ],
)
def test_hdr_profiles_default_to_full_dynamic_range(profile_import_path, profile_cls_name):
    import importlib

    module = importlib.import_module(profile_import_path)
    profile = getattr(module, profile_cls_name)()
    assert profile.get_settings("DisplayColorRangeHandler").get("dynamic_range") == "full"
