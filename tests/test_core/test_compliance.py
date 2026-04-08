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
