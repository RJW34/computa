"""Tests for VBSOptInHandler safety contract."""

from __future__ import annotations

from unittest.mock import patch

from abso.profiles import get_all_profiles
from abso.settings.vbs_optin import VBSOptInHandler


def test_apply_refuses_without_acknowledgement() -> None:
    """Missing acknowledgement must not mutate anything."""
    handler = VBSOptInHandler()

    with (
        patch.object(VBSOptInHandler, "_write_hvci_enabled") as write_hvci,
        patch.object(VBSOptInHandler, "_set_hypervisor_launch_type") as set_launch,
        patch.object(VBSOptInHandler, "_disable_vmp_optional_feature") as disable_vmp,
    ):
        result = handler.apply({"disable_hvci": True, "disable_vmp": True})

    assert result["success"] is True
    assert result["applied"] == []
    assert result["requires_reboot"] is False
    assert any("refused" in note.lower() for note in result.get("notices", []))
    write_hvci.assert_not_called()
    set_launch.assert_not_called()
    disable_vmp.assert_not_called()


def test_apply_with_acknowledgement_writes_requested_state() -> None:
    """Explicit opt-in writes the requested state and flags reboot."""
    handler = VBSOptInHandler()

    with (
        patch.object(VBSOptInHandler, "_write_hvci_enabled") as write_hvci,
        patch.object(VBSOptInHandler, "_set_hypervisor_launch_type") as set_launch,
        patch.object(VBSOptInHandler, "_disable_vmp_optional_feature") as disable_vmp,
    ):
        result = handler.apply(
            {
                "acknowledge_security_tradeoff": True,
                "disable_hvci": True,
                "disable_hypervisor_launch": True,
                "disable_vmp": True,
            }
        )

    assert result["success"] is True
    assert result["requires_reboot"] is True
    assert "HVCI.Enabled=0" in result["applied"]
    assert "hypervisorlaunchtype=off" in result["applied"]
    assert "VirtualMachinePlatform=disabled" in result["applied"]
    assert any("reboot" in note.lower() for note in result.get("notices", []))
    write_hvci.assert_called_once_with(False)
    set_launch.assert_called_once_with("off")
    disable_vmp.assert_called_once()


def test_no_built_in_profile_uses_vbs_opt_in_handler() -> None:
    """No built-in profile may wire the VBSOptInHandler by name.

    This is the main safety invariant: the opt-in flow is a separate
    user-driven path, not something a gaming profile can layer into its
    default behavior.
    """
    offenders: list[str] = []
    for profile in get_all_profiles().values():
        handler_names = [type(h).__name__ for h in profile.get_handlers()]
        if "VBSOptInHandler" in handler_names:
            offenders.append(profile.profile_id)

    assert not offenders, (
        "VBSOptInHandler must not be used by default profiles; offenders: "
        + ", ".join(offenders)
    )


def test_restore_writes_back_full_state() -> None:
    """Restore re-applies every captured flag verbatim."""
    handler = VBSOptInHandler()

    with (
        patch.object(VBSOptInHandler, "_write_hvci_enabled") as write_hvci,
        patch.object(VBSOptInHandler, "_set_hypervisor_launch_type") as set_launch,
        patch.object(VBSOptInHandler, "_enable_vmp_optional_feature") as enable_vmp,
    ):
        ok = handler.restore(
            {
                "hvci_enabled": True,
                "hypervisor_launch_type": "auto",
                "vmp_feature_enabled": True,
            }
        )

    assert ok is True
    write_hvci.assert_called_once_with(True)
    set_launch.assert_called_once_with("auto")
    enable_vmp.assert_called_once()
