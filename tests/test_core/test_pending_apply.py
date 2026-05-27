"""Tests for narrow pending-apply remediation."""

from __future__ import annotations

from unittest.mock import MagicMock

from abso.core.pending_apply import (
    apply_pending_profile_settings,
    build_pending_apply_actions,
)


def _pending_mpo_verify(target: bool = True) -> dict:
    return {
        "profile": "overwatch2-gsync-hdr-capture",
        "all_active": False,
        "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
        "handlers": {
            "GraphicsSettingsHandler": {
                "all_active": False,
                "settings": {"mpo_disabled": {"target": target, "current": not target}},
            }
        },
    }


def test_build_pending_apply_actions_accepts_mpo_only() -> None:
    """MPO registry writes are the only supported targeted apply action."""
    actions, unsupported, error = build_pending_apply_actions(
        "overwatch2-gsync-hdr-capture",
        _pending_mpo_verify(target=True),
    )

    assert unsupported == []
    assert error is None
    assert actions == [
        {
            "profile": "overwatch2-gsync-hdr-capture",
            "pending_setting": "GraphicsSettingsHandler.mpo_disabled",
            "handler": "GraphicsSettingsHandler",
            "apply_setting": "disable_mpo",
            "target": True,
            "reboot_gated": True,
            "description": "Write the Windows MPO registry target only",
        }
    ]


def test_apply_pending_profile_settings_marks_reboot_with_injected_dependencies() -> None:
    """The core path writes only MPO and delegates reboot state persistence."""
    applier = MagicMock()
    applier.verify_profile.side_effect = [
        _pending_mpo_verify(target=True),
        {
            "profile": "overwatch2-gsync-hdr-capture",
            "all_active": True,
            "handlers": {},
        },
    ]
    graphics_handler = MagicMock()
    graphics_handler.apply.return_value = {
        "success": True,
        "changed_keys": ["disable_mpo"],
        "requires_reboot": True,
        "notices": ["MPO registry state changed; reboot before judging display flicker."],
    }
    set_current_profile = MagicMock()

    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture",
        applier=applier,
        is_admin_func=lambda: True,
        set_current_profile_func=set_current_profile,
        graphics_handler_factory=lambda: graphics_handler,
    )

    assert result["success"] is True
    assert result["changed_settings"] == ["GraphicsSettingsHandler.disable_mpo"]
    assert result["requires_reboot"] is True
    graphics_handler.apply.assert_called_once_with({"disable_mpo": True})
    set_current_profile.assert_called_once_with(
        "overwatch2-gsync-hdr-capture",
        requires_reboot=True,
        reboot_reasons=["GraphicsSettingsHandler"],
    )


def test_apply_pending_profile_settings_rejects_admin_write_without_side_effects() -> None:
    """Non-admin writes should fail before touching the handler or state file."""
    applier = MagicMock()
    applier.verify_profile.return_value = _pending_mpo_verify(target=True)
    graphics_handler_factory = MagicMock()
    set_current_profile = MagicMock()

    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture",
        applier=applier,
        is_admin_func=lambda: False,
        set_current_profile_func=set_current_profile,
        graphics_handler_factory=graphics_handler_factory,
    )

    assert result["success"] is False
    assert "Admin privileges required" in result["error"]
    graphics_handler_factory.assert_not_called()
    set_current_profile.assert_not_called()
