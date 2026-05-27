"""Tests for BIOS/firmware detector (cert rollout coverage focused)."""

from __future__ import annotations

from datetime import date
from unittest.mock import patch

import pytest

from abso.core.bios_detector import (
    SECURE_BOOT_CERT_EXPIRY_DATE,
    BiosDetector,
    SecureBootCertState,
)


def _patch_reads(detector: BiosDetector, dwords: dict[str, int], values: dict[str, object]):
    """Patch _read_reg_dword / _read_reg_value to serve the given fixtures."""

    def _dword(hive, subkey, name):
        return dwords.get(name)

    def _value(hive, subkey, name):
        return values.get(name)

    return (
        patch.object(BiosDetector, "_read_reg_dword", staticmethod(_dword)),
        patch.object(BiosDetector, "_read_reg_value", staticmethod(_value)),
    )


class TestSecureBootCertDetect:
    def test_updated_reboot_pending(self):
        detector = BiosDetector()
        dwords = {
            "UEFISecureBootEnabled": 1,
            "WindowsUEFICA2023Capable": 2,
            "RebootRequested3POROMDB": 1,
        }
        values = {
            "UEFICA2023Status": "Updated",
            "ConfidenceLevel": "High Confidence",
        }
        p1, p2 = _patch_reads(detector, dwords, values)
        with p1, p2:
            cert = detector.detect_secure_boot_cert_state()
        assert cert.rollout_status == "updated_reboot_pending"
        assert cert.reboot_pending is True
        assert cert.capable == 2
        assert cert.needs_action is True

    def test_updated_clean(self):
        detector = BiosDetector()
        dwords = {
            "UEFISecureBootEnabled": 1,
            "WindowsUEFICA2023Capable": 2,
            "RebootRequested3POROMDB": 0,
        }
        values = {"UEFICA2023Status": "Updated"}
        p1, p2 = _patch_reads(detector, dwords, values)
        with p1, p2:
            cert = detector.detect_secure_boot_cert_state()
        assert cert.rollout_status == "updated"
        assert cert.needs_action is False

    def test_pending_when_status_not_updated(self):
        detector = BiosDetector()
        dwords = {"UEFISecureBootEnabled": 1, "WindowsUEFICA2023Capable": 1}
        values = {"UEFICA2023Status": "Pending"}
        p1, p2 = _patch_reads(detector, dwords, values)
        with p1, p2:
            cert = detector.detect_secure_boot_cert_state()
        assert cert.rollout_status == "pending"
        assert cert.needs_action is True

    def test_unknown_when_servicing_key_absent(self):
        detector = BiosDetector()
        dwords = {"UEFISecureBootEnabled": 1}
        values: dict[str, object] = {}
        p1, p2 = _patch_reads(detector, dwords, values)
        with p1, p2:
            cert = detector.detect_secure_boot_cert_state()
        assert cert.rollout_status == "unknown"
        assert cert.needs_action is True

    def test_disabled_secure_boot_marks_not_applicable(self):
        detector = BiosDetector()
        cert = detector.detect_secure_boot_cert_state(secure_boot="disabled")
        assert cert.rollout_status == "not_applicable"
        assert cert.needs_action is False


class TestSecureBootCertRecommendation:
    @pytest.fixture
    def reboot_pending(self) -> SecureBootCertState:
        return SecureBootCertState(
            enabled="enabled",
            capable=2,
            status_raw="Updated",
            reboot_pending=True,
            confidence="High Confidence",
            rollout_status="updated_reboot_pending",
        )

    @pytest.fixture
    def pending(self) -> SecureBootCertState:
        return SecureBootCertState(
            enabled="enabled",
            capable=1,
            status_raw=None,
            reboot_pending=False,
            confidence=None,
            rollout_status="pending",
        )

    def test_none_when_cert_absent(self):
        assert BiosDetector._secure_boot_cert_recommendation(None) is None

    def test_none_when_secure_boot_disabled(self):
        cert = SecureBootCertState(
            enabled="disabled",
            capable=None,
            status_raw=None,
            reboot_pending=False,
            confidence=None,
            rollout_status="not_applicable",
        )
        assert BiosDetector._secure_boot_cert_recommendation(cert) is None

    def test_reboot_pending_fires_with_high_impact_inside_window(self, reboot_pending):
        rec = BiosDetector._secure_boot_cert_recommendation(
            reboot_pending, today=SECURE_BOOT_CERT_EXPIRY_DATE
        )
        assert rec is not None
        assert rec.impact == "high"
        assert "Reboot" in rec.title

    def test_reboot_pending_medium_impact_before_window(self, reboot_pending):
        rec = BiosDetector._secure_boot_cert_recommendation(
            reboot_pending, today=date(2026, 1, 1)
        )
        assert rec is not None
        assert rec.impact == "medium"

    def test_pending_surfaces_rollout_message(self, pending):
        rec = BiosDetector._secure_boot_cert_recommendation(pending, today=date(2026, 5, 13))
        assert rec is not None
        assert "June 2026" in rec.explanation
        assert "rolling out" in rec.explanation.lower()
