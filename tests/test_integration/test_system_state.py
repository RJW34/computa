"""Integration tests that verify settings handlers read/write REAL system state.

WARNING: These tests touch the live Windows registry, WMI, and system
configuration.  They must ONLY be run:
  - On Windows
  - With explicit user consent
  - In an admin-elevated terminal (for write tests)
  - Via: pytest -m integration

Every write test saves the original value before modification and restores it
in a finally block, even if an assertion fails.

Run with:
    pytest tests/test_integration/ -m integration -v
"""

from __future__ import annotations

import sys
import winreg

import pytest

from tests.test_integration.conftest import requires_admin

pytestmark = [
    pytest.mark.integration,
    pytest.mark.skipif(sys.platform != "win32", reason="Windows-only"),
]


# ============================================================================
# Registry round-trip tests (require admin)
# ============================================================================


@requires_admin
class TestRegistryRoundTrip:
    """Verify that RegistrySettingsHandler can read, write, and restore
    real registry values on the live system."""

    # --- SystemResponsiveness ------------------------------------------------

    def test_system_responsiveness_roundtrip(self, registry_backup):
        """Read -> write test value -> read back -> verify -> restore."""
        from abso.settings.registry import RegistrySettingsHandler

        handler = RegistrySettingsHandler()
        hive = winreg.HKEY_LOCAL_MACHINE
        subkey = RegistrySettingsHandler.MULTIMEDIA_KEY
        value_name = "SystemResponsiveness"

        with registry_backup(hive, subkey, value_name) as original:
            # Sanity: the original value should be readable (int or None).
            assert original is None or isinstance(original, int)

            # Pick a test value that differs from the current one.
            test_value = 10 if original != 10 else 20

            # Write via the handler.
            handler._set_system_responsiveness(test_value)

            # Verify via direct winreg read.
            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
            try:
                actual, _ = winreg.QueryValueEx(key, value_name)
            finally:
                winreg.CloseKey(key)

            assert actual == test_value, (
                f"Expected {test_value} after write, got {actual}"
            )

            # Also verify the handler's own detect path agrees.
            detected = handler._get_system_responsiveness()
            assert detected == test_value

        # After the context manager exits, original is restored.
        # Verify restoration.
        restored = handler._get_system_responsiveness()
        assert restored == original, (
            f"Restore failed: expected {original}, got {restored}"
        )

    # --- Win32PrioritySeparation ---------------------------------------------

    def test_win32_priority_separation_roundtrip(self, registry_backup):
        """Read -> write test value -> read back -> verify -> restore."""
        from abso.settings.registry import RegistrySettingsHandler

        handler = RegistrySettingsHandler()
        hive = winreg.HKEY_LOCAL_MACHINE
        subkey = RegistrySettingsHandler.PRIORITY_CONTROL_KEY
        value_name = "Win32PrioritySeparation"

        with registry_backup(hive, subkey, value_name) as original:
            assert original is None or isinstance(original, int)

            # Toggle between the two well-known values.
            if original == RegistrySettingsHandler.WIN32_PRIORITY_GAMING:
                test_value = RegistrySettingsHandler.WIN32_PRIORITY_DEFAULT
            else:
                test_value = RegistrySettingsHandler.WIN32_PRIORITY_GAMING

            handler._set_win32_priority_separation(test_value)

            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
            try:
                actual, _ = winreg.QueryValueEx(key, value_name)
            finally:
                winreg.CloseKey(key)

            assert actual == test_value

            detected = handler._get_win32_priority_separation()
            assert detected == test_value

        restored = handler._get_win32_priority_separation()
        assert restored == original

    # --- Game Priority (MMCSS Tasks\Games) -----------------------------------

    def test_game_priority_roundtrip(self, registry_backup):
        """Read -> write test value -> read back -> verify -> restore."""
        from abso.settings.registry import RegistrySettingsHandler

        handler = RegistrySettingsHandler()
        hive = winreg.HKEY_LOCAL_MACHINE
        subkey = RegistrySettingsHandler.GAMES_TASK_KEY
        value_name = "Priority"

        with registry_backup(hive, subkey, value_name) as original:
            assert original is None or isinstance(original, int)

            test_value = 6 if original != 6 else 2

            handler._set_game_priority({"priority": test_value})

            key = winreg.OpenKey(hive, subkey, 0, winreg.KEY_READ)
            try:
                actual, _ = winreg.QueryValueEx(key, value_name)
            finally:
                winreg.CloseKey(key)

            assert actual == test_value

            detected = handler._get_game_priority()
            assert detected.get("priority") == test_value

        # Verify the fixture restored the original.
        after = handler._get_game_priority()
        assert after.get("priority") == original


# ============================================================================
# Power settings detection (no admin needed)
# ============================================================================


class TestPowerSettingsDetection:
    """Verify that PowerSettingsHandler.detect() reads valid data from the
    live system without requiring admin privileges."""

    def test_detect_active_power_plan(self):
        """detect() should return a dict with a valid active_plan entry."""
        from abso.settings.power import PowerSettingsHandler

        handler = PowerSettingsHandler()
        result = handler.detect()

        assert "active_plan" in result
        active_plan = result["active_plan"]
        assert isinstance(active_plan, dict)
        assert "guid" in active_plan
        assert "name" in active_plan

    def test_detect_returns_known_plan_name(self):
        """The active plan name should be a non-empty string."""
        from abso.settings.power import PowerSettingsHandler

        handler = PowerSettingsHandler()
        result = handler.detect()

        name = result["active_plan"].get("name", "")
        assert isinstance(name, str)
        assert len(name) > 0, "Power plan name should not be empty"


# ============================================================================
# Mouse settings detection (no admin needed)
# ============================================================================


class TestMouseSettingsDetection:
    """Verify that MouseSettingsHandler.detect() reads valid mouse state
    from the live system."""

    def test_detect_mouse_acceleration_state(self):
        """detect() should include an is_acceleration_disabled boolean."""
        from abso.settings.mouse import MouseSettingsHandler

        handler = MouseSettingsHandler()
        result = handler.detect()

        assert "is_acceleration_disabled" in result
        assert isinstance(result["is_acceleration_disabled"], bool)

    def test_detect_returns_valid_values(self):
        """detect() values should have the expected types."""
        from abso.settings.mouse import MouseSettingsHandler

        handler = MouseSettingsHandler()
        result = handler.detect()

        # mouse_speed is int or None
        mouse_speed = result.get("mouse_speed")
        assert mouse_speed is None or isinstance(mouse_speed, int)

        # mouse_threshold1 and mouse_threshold2 are int or None
        for key in ("mouse_threshold1", "mouse_threshold2"):
            val = result.get(key)
            assert val is None or isinstance(val, int), (
                f"{key} should be int or None, got {type(val)}"
            )

        # enhanced_pointer_precision is bool
        epp = result.get("enhanced_pointer_precision")
        assert isinstance(epp, bool)

        # smooth curves are list or None
        for key in ("smooth_mouse_x_curve", "smooth_mouse_y_curve"):
            val = result.get(key)
            assert val is None or isinstance(val, list), (
                f"{key} should be list or None, got {type(val)}"
            )


# ============================================================================
# Network detection (no admin needed for reads)
# ============================================================================


class TestNetworkDetection:
    """Verify that NetworkSettingsHandler.detect() reads valid network
    state from the live system."""

    def test_detect_returns_interface_info(self):
        """detect() should find at least one network interface."""
        from abso.settings.network import NetworkSettingsHandler

        handler = NetworkSettingsHandler()
        result = handler.detect()

        assert "interfaces" in result
        interfaces = result["interfaces"]
        assert isinstance(interfaces, dict)
        assert len(interfaces) > 0, (
            "Expected at least one network interface"
        )

        # Each interface should have the expected keys.
        for guid, settings in interfaces.items():
            assert isinstance(guid, str)
            assert isinstance(settings, dict)
            assert "tcp_ack_frequency" in settings
            assert "tcp_no_delay" in settings

    def test_detect_tcp_settings(self):
        """detect() should include tcp_global settings."""
        from abso.settings.network import NetworkSettingsHandler

        handler = NetworkSettingsHandler()
        result = handler.detect()

        assert "tcp_global" in result
        tcp_global = result["tcp_global"]
        assert isinstance(tcp_global, dict)
        # netsh should return at least the auto-tuning level on any
        # functioning Windows system.
        assert len(tcp_global) > 0, (
            "Expected at least one TCP global setting from netsh"
        )


# ============================================================================
# BIOS / firmware detection (no admin needed for registry reads)
# ============================================================================


class TestBiosDetection:
    """Verify that BiosDetector reads firmware info from the live system."""

    def test_detect_all_returns_populated_info(self):
        """detect_all() should return a BiosFirmwareInfo with fields set."""
        from abso.core.bios_detector import BiosDetector, BiosFirmwareInfo

        detector = BiosDetector()
        try:
            info = detector.detect_all()

            assert isinstance(info, BiosFirmwareInfo)

            # VBS and Secure Boot always return a definite value on Windows.
            assert info.vbs_status in ("enabled", "disabled")
            assert info.memory_integrity in ("enabled", "disabled")
            assert info.secure_boot in ("enabled", "disabled", "unknown")

            # ReBAR may be unknown on systems without a discrete GPU.
            assert info.rebar_status in ("enabled", "disabled", "unknown")

            # Memory profile detection depends on WMI availability.
            assert info.memory_profile in (
                "xmp_enabled", "xmp_disabled_likely", "unknown",
            )
        finally:
            detector.cleanup()

    def test_recommendations_returns_list(self):
        """get_recommendations() should return a list of BiosRecommendation."""
        from abso.core.bios_detector import BiosDetector, BiosRecommendation

        detector = BiosDetector()
        try:
            recommendations = detector.get_recommendations()

            assert isinstance(recommendations, list)
            for rec in recommendations:
                assert isinstance(rec, BiosRecommendation)
                assert rec.title
                assert rec.impact in ("high", "medium", "low")
        finally:
            detector.cleanup()


# ============================================================================
# CPU topology detection (no admin needed for registry reads)
# ============================================================================


class TestCpuTopologyDetection:
    """Verify that CpuAffinityHandler reads CPU topology from the live
    system."""

    def test_detect_returns_topology(self):
        """detect() should return a dict with a topology sub-dict."""
        from abso.settings.cpu_affinity import CpuAffinityHandler

        handler = CpuAffinityHandler()
        result = handler.detect()

        assert "topology" in result
        topology = result["topology"]
        assert isinstance(topology, dict)

        expected_keys = {
            "total_physical",
            "total_logical",
            "p_cores",
            "e_cores",
            "is_hybrid",
            "vendor",
            "architecture",
        }
        assert expected_keys.issubset(topology.keys()), (
            f"Missing topology keys: {expected_keys - topology.keys()}"
        )

    def test_topology_has_valid_core_counts(self):
        """Physical cores > 0 and logical cores >= physical cores."""
        from abso.settings.cpu_affinity import CpuAffinityHandler

        handler = CpuAffinityHandler()
        result = handler.detect()
        topology = result["topology"]

        total_physical = topology["total_physical"]
        total_logical = topology["total_logical"]

        assert isinstance(total_physical, int)
        assert isinstance(total_logical, int)
        assert total_physical > 0, "Physical core count must be > 0"
        assert total_logical >= total_physical, (
            f"Logical cores ({total_logical}) must be >= physical cores "
            f"({total_physical})"
        )

        # P-cores should be a non-empty list of ints.
        p_cores = topology["p_cores"]
        assert isinstance(p_cores, list)
        assert len(p_cores) > 0, "Expected at least one P-core"
        for core_id in p_cores:
            assert isinstance(core_id, int)

        # Vendor should be a non-empty string.
        assert isinstance(topology["vendor"], str)
        assert len(topology["vendor"]) > 0
