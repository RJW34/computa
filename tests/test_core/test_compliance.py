"""Tests for compliance evaluation engine."""

from __future__ import annotations

from abso.core.applier import ApplyResult
from abso.core.compliance import ComplianceEngine, ComplianceSeverity


def test_compliance_marks_apply_error_as_critical() -> None:
    engine = ComplianceEngine()
    apply_result = ApplyResult(success=False, error="Unknown profile")

    report = engine.evaluate("test-profile", apply_result, {"all_active": True, "handlers": {}})

    assert report.has_critical is True
    assert any(issue.code == "APPLY_FAILED" for issue in report.issues)


def test_compliance_marks_failed_handlers_as_critical() -> None:
    engine = ComplianceEngine()
    apply_result = ApplyResult(
        success=False,
        error="handler failed",
        failed_settings=["WindowsSettingsHandler: fail"],
    )

    report = engine.evaluate("test-profile", apply_result, {"all_active": True, "handlers": {}})

    assert report.has_critical is True
    assert any(issue.code == "APPLY_HANDLER_FAILED" for issue in report.issues)


def test_compliance_critical_verify_handler_mismatch_is_critical() -> None:
    engine = ComplianceEngine()
    apply_result = ApplyResult(success=True)
    verify_result = {
        "all_active": False,
        "handlers": {
            "WindowsSettingsHandler": {
                "all_active": False,
                "settings": {"hags": {"active": False}},
            }
        },
    }

    report = engine.evaluate("test-profile", apply_result, verify_result)

    assert report.has_critical is True
    mismatch = [i for i in report.issues if i.code == "VERIFY_MISMATCH"]
    assert mismatch
    assert mismatch[0].severity == ComplianceSeverity.CRITICAL


def test_compliance_noncritical_verify_handler_mismatch_is_warning() -> None:
    engine = ComplianceEngine()
    apply_result = ApplyResult(success=True)
    verify_result = {
        "all_active": False,
        "handlers": {
            "ColorProfileSettingsHandler": {
                "all_active": False,
                "settings": {"icc_profile": {"active": False}},
            }
        },
    }

    report = engine.evaluate("test-profile", apply_result, verify_result)

    assert report.has_critical is False
    mismatch = [i for i in report.issues if i.code == "VERIFY_MISMATCH"]
    assert mismatch
    assert mismatch[0].severity == ComplianceSeverity.WARNING


def test_compliance_power_verify_handler_mismatch_is_critical() -> None:
    engine = ComplianceEngine()
    apply_result = ApplyResult(success=True)
    verify_result = {
        "all_active": False,
        "handlers": {
            "PowerSettingsHandler": {
                "all_active": False,
                "settings": {"active_plan": {"active": False}},
            }
        },
    }

    report = engine.evaluate("test-profile", apply_result, verify_result)

    assert report.has_critical is True
    mismatch = [i for i in report.issues if i.code == "VERIFY_MISMATCH"]
    assert mismatch
    assert mismatch[0].severity == ComplianceSeverity.CRITICAL


def test_compliance_reboot_gated_written_target_is_warning() -> None:
    """Written reboot-gated settings should not trigger rollback-critical compliance."""
    engine = ComplianceEngine()
    apply_result = ApplyResult(success=True)
    verify_result = {
        "all_active": False,
        "pending_reboot_gated_settings": ["GraphicsSettingsHandler.mpo_disabled"],
        "handlers": {
            "GraphicsSettingsHandler": {
                "all_active": False,
                "pending_reboot_gated_settings": ["mpo_disabled"],
                "settings": {
                    "mpo_disabled": {
                        "target": False,
                        "current": False,
                        "active": True,
                        "reboot_gated": True,
                        "registry_target_written": True,
                        "live_commit_pending": True,
                    }
                },
            }
        },
    }

    report = engine.evaluate("test-profile", apply_result, verify_result)

    assert report.has_critical is False
    pending = [i for i in report.issues if i.code == "VERIFY_PENDING_REBOOT"]
    assert pending
    assert pending[0].severity == ComplianceSeverity.WARNING


def test_compliance_reboot_gated_with_pending_apply_stays_critical() -> None:
    """A missing registry target is still a critical apply/verify mismatch."""
    engine = ComplianceEngine()
    apply_result = ApplyResult(success=True)
    verify_result = {
        "all_active": False,
        "pending_apply_settings": ["GraphicsSettingsHandler.mpo_disabled"],
        "handlers": {
            "GraphicsSettingsHandler": {
                "all_active": False,
                "pending_apply_settings": ["mpo_disabled"],
                "pending_reboot_gated_settings": ["mpo_disabled"],
                "settings": {
                    "mpo_disabled": {
                        "target": True,
                        "current": False,
                        "active": False,
                        "reboot_gated": True,
                        "registry_target_written": False,
                    }
                },
            }
        },
    }

    report = engine.evaluate("test-profile", apply_result, verify_result)

    assert report.has_critical is True
    mismatch = [i for i in report.issues if i.code == "VERIFY_MISMATCH"]
    assert mismatch
    assert mismatch[0].severity == ComplianceSeverity.CRITICAL
