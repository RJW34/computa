"""Tests for narrow pending-apply remediation."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from abso.core.pending_apply import (
    apply_pending_profile_settings,
    build_pending_apply_actions,
)
from abso.settings.graphics import GraphicsSettingsHandler


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
    """A pending MPO action must not also change FSO or other graphics keys."""
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


def _pending_fso_verify(target: bool = False, *, include_mpo: bool = False) -> dict:
    verify = _pending_mpo_verify()
    settings = verify["handlers"]["GraphicsSettingsHandler"]["settings"]
    if not include_mpo:
        verify["pending_apply_settings"].clear()
        settings.clear()
    verify["pending_apply_settings"].append("GraphicsSettingsHandler.disable_global_fso")
    settings["global_fso_disabled"] = {"target": target, "current": not target}
    return verify


@pytest.mark.parametrize("target", [False, True])
def test_pending_fso_uses_actual_graphics_verifier_readback_key(target: bool) -> None:
    handler = GraphicsSettingsHandler()
    with patch.object(handler, "detect", return_value={"global_fso_disabled": not target}):
        verified = handler.verify_active({"disable_global_fso": target})
    actions, unsupported, error = build_pending_apply_actions(
        "overwatch2-gsync-hdr-capture",
        {
            "pending_apply_settings": [
                f"GraphicsSettingsHandler.{key}" for key in verified["pending_apply_settings"]
            ],
            "handlers": {"GraphicsSettingsHandler": verified},
        },
    )
    assert error is None
    assert unsupported == []
    assert len(actions) == 1
    assert actions[0]["apply_setting"] == "disable_global_fso"
    assert actions[0]["target"] is target
    assert actions[0]["reboot_gated"] is False


@pytest.mark.parametrize("target", [False, True])
@pytest.mark.parametrize("include_mpo", [False, True])
def test_pending_fso_and_mpo_apply_only_requested_keys(target: bool, include_mpo: bool) -> None:
    applier = MagicMock()
    applier.verify_profile.side_effect = [
        _pending_fso_verify(target, include_mpo=include_mpo),
        {"all_active": not include_mpo, "pending_apply_settings": []},
    ]
    settings = {"disable_global_fso": target}
    if include_mpo:
        settings["disable_mpo"] = True
    handler = MagicMock()
    handler.apply.return_value = {
        "success": True,
        "changed_keys": list(settings),
        "requires_reboot": include_mpo,
    }
    persist = MagicMock()
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
        graphics_handler_factory=lambda: handler, set_current_profile_func=persist,
    )
    handler.apply.assert_called_once_with(settings)
    assert result["success"] is True
    assert result["changed"] is True
    assert result["changed_settings"] == [f"GraphicsSettingsHandler.{key}" for key in settings]
    assert result["requires_reboot"] is include_mpo
    assert result["pending_apply_settings_after"] == []
    if include_mpo:
        persist.assert_called_once_with(
            "overwatch2-gsync-hdr-capture", requires_reboot=True,
            reboot_reasons=["GraphicsSettingsHandler"],
        )
    else:
        persist.assert_not_called()


@pytest.mark.parametrize("target", [None, "false", 0, 1])
def test_invalid_fso_target_fails_closed_before_any_mpo_write(target: object) -> None:
    verify = _pending_fso_verify(include_mpo=True)
    verify["handlers"]["GraphicsSettingsHandler"]["settings"]["global_fso_disabled"]["target"] = target
    applier = MagicMock()
    applier.verify_profile.return_value = verify
    factory = MagicMock()
    persist = MagicMock()
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
        graphics_handler_factory=factory, set_current_profile_func=persist,
    )
    assert result["success"] is False
    assert "boolean global FSO target" in result["error"]
    assert result["actions"] == []
    factory.assert_not_called()
    persist.assert_not_called()


@pytest.mark.parametrize("dry_run", [False, True])
def test_pending_fso_obeys_privilege_and_dry_run_without_writes(dry_run: bool) -> None:
    applier = MagicMock()
    applier.verify_profile.return_value = _pending_fso_verify(include_mpo=True)
    factory = MagicMock()
    persist = MagicMock()
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", dry_run=dry_run, applier=applier,
        is_admin_func=lambda: False, graphics_handler_factory=factory,
        set_current_profile_func=persist,
    )
    assert result["success"] is dry_run
    assert len(result["actions"]) == 2
    assert result["changed"] is False
    assert result["requires_reboot"] is False
    if not dry_run:
        assert "Admin privileges required" in result["error"]
    factory.assert_not_called()
    persist.assert_not_called()
    applier.verify_profile.assert_called_once()


def test_unsupported_pending_key_blocks_supported_graphics_writes() -> None:
    verify = _pending_fso_verify(include_mpo=True)
    verify["pending_apply_settings"].append("GraphicsSettingsHandler.game_dvr_behavior")
    applier = MagicMock()
    applier.verify_profile.return_value = verify
    factory = MagicMock()
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
        graphics_handler_factory=factory,
    )
    assert result["success"] is False
    assert result["unsupported_pending_settings"] == ["GraphicsSettingsHandler.game_dvr_behavior"]
    assert "Unsupported pending apply" in result["error"]
    factory.assert_not_called()


def test_partial_graphics_failure_preserves_mpo_change_and_reboot_state() -> None:
    """Real handler can commit MPO before a later FSO setter is denied."""
    applier = MagicMock()
    applier.verify_profile.return_value = _pending_fso_verify(False, include_mpo=True)
    persist = MagicMock()
    handler = GraphicsSettingsHandler()
    with (
        patch.object(handler, "detect", return_value={
            "mpo_disabled": False, "global_fso_disabled": True,
        }),
        patch.object(handler, "_set_mpo_disabled") as set_mpo,
        patch.object(handler, "_set_global_fso_disabled", side_effect=PermissionError("FSO denied")) as set_fso,
    ):
        result = apply_pending_profile_settings(
            "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
            graphics_handler_factory=lambda: handler, set_current_profile_func=persist,
        )
    assert result["success"] is False
    assert "FSO denied" in result["error"]
    assert result["changed"] is True
    assert result["changed_settings"] == ["GraphicsSettingsHandler.disable_mpo"]
    assert result["requires_reboot"] is True
    assert result["reboot_reasons"] == ["GraphicsSettingsHandler"]
    assert any("MPO registry state changed" in notice for notice in result["notices"])
    persist.assert_called_once_with(
        "overwatch2-gsync-hdr-capture", requires_reboot=True,
        reboot_reasons=["GraphicsSettingsHandler"],
    )
    set_mpo.assert_called_once_with(True)
    set_fso.assert_called_once_with(False)
    applier.verify_profile.assert_called_once()


def test_pending_fso_fails_when_setter_claims_success_but_readback_still_pending() -> None:
    applier = MagicMock()
    applier.verify_profile.return_value = _pending_fso_verify(False)
    handler = MagicMock()
    handler.apply.return_value = {"success": True, "changed_keys": ["disable_global_fso"]}
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
        graphics_handler_factory=lambda: handler,
    )
    assert result["success"] is False
    assert result["changed"] is True  # Reported writes remain visible despite failed readback.
    assert result["pending_apply_settings_after"] == ["GraphicsSettingsHandler.disable_global_fso"]
    assert "remain after remediation" in result["error"]
    assert "GraphicsSettingsHandler.disable_global_fso" in result["error"]
    handler.apply.assert_called_once_with({"disable_global_fso": False})


@pytest.mark.parametrize("readback", [
    {"error": "Readback unavailable"},
    {"all_active": False, "handlers": {"GraphicsSettingsHandler": {"error": "Readback unavailable"}}},
    RuntimeError("Readback unavailable"),
    None,
])
def test_pending_apply_readback_errors_fail_without_discarding_mpo_reboot(readback: object) -> None:
    applier = MagicMock()
    applier.verify_profile.side_effect = [_pending_fso_verify(include_mpo=True), readback]
    handler = MagicMock()
    handler.apply.return_value = {
        "success": True, "changed_keys": ["disable_mpo", "disable_global_fso"],
        "requires_reboot": True,
    }
    persist = MagicMock()
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
        graphics_handler_factory=lambda: handler, set_current_profile_func=persist,
    )
    assert result["success"] is False
    assert "verification" in result["error"]
    assert result["changed_settings"] == [
        "GraphicsSettingsHandler.disable_mpo", "GraphicsSettingsHandler.disable_global_fso",
    ]
    assert result["requires_reboot"] is True
    persist.assert_called_once()


def test_pending_apply_success_allows_unrelated_mismatches_manual_steps_and_reboot() -> None:
    applier = MagicMock()
    applier.verify_profile.side_effect = [
        _pending_fso_verify(include_mpo=True),
        {
            "all_active": False,
            "pending_apply_settings": ["GraphicsSettingsHandler.disable_auto_color_management"],
            "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
            "manual_steps": [{"handler": "Ow2ConfigHandler", "message": "Check native Reflex"}],
            "handlers": {
                "GraphicsSettingsHandler": {"all_active": False},
                "OtherHandler": {"all_active": False, "error": "Unrelated readback unavailable"},
            },
        },
    ]
    handler = MagicMock()
    handler.apply.return_value = {"success": True, "changed_keys": ["disable_global_fso"]}
    result = apply_pending_profile_settings(
        "overwatch2-gsync-hdr-capture", applier=applier, is_admin_func=lambda: True,
        graphics_handler_factory=lambda: handler,
    )
    assert result["success"] is True
    assert result["error"] is None
    assert result["verify_after"]["all_active"] is False
    assert result["pending_apply_settings_after"] == ["GraphicsSettingsHandler.disable_auto_color_management"]
    assert result["pending_reboot_gated_settings_after"] == ["GraphicsSettingsHandler.mpo_disabled"]
