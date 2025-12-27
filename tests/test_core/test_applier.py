"""Tests for profile application module."""

from __future__ import annotations

from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from gametune.core.applier import ProfileApplier, ApplyResult
from gametune.core.exceptions import ProfileNotFoundError


class TestApplyResultDataclass:
    """Tests for ApplyResult dataclass."""

    def test_apply_result_success(self):
        """Test ApplyResult with success."""
        result = ApplyResult(
            success=True,
            applied_settings=["WindowsSettingsHandler", "NvidiaSettingsHandler"],
        )

        assert result.success is True
        assert result.error is None
        assert result.requires_reboot is False
        assert len(result.applied_settings) == 2

    def test_apply_result_failure(self):
        """Test ApplyResult with failure."""
        result = ApplyResult(
            success=False,
            error="Failed to apply settings",
            failed_settings=["WindowsSettingsHandler"],
        )

        assert result.success is False
        assert result.error == "Failed to apply settings"
        assert len(result.failed_settings) == 1

    def test_apply_result_requires_reboot(self):
        """Test ApplyResult with reboot required."""
        result = ApplyResult(
            success=True,
            requires_reboot=True,
        )

        assert result.requires_reboot is True


class TestProfileApplierInit:
    """Tests for ProfileApplier initialization."""

    def test_init_creates_instance(self):
        """Test ProfileApplier can be instantiated."""
        applier = ProfileApplier()
        assert applier is not None
        assert applier._profiles == {}

    def test_profiles_registry_exists(self):
        """Test PROFILES registry contains expected profiles."""
        assert "slippi-melee" in ProfileApplier.PROFILES
        assert "cod-bo7" in ProfileApplier.PROFILES
        assert "diablo4" in ProfileApplier.PROFILES
        assert "rivals2" in ProfileApplier.PROFILES


class TestGetProfile:
    """Tests for _get_profile method."""

    def test_get_profile_valid(self):
        """Test getting a valid profile."""
        applier = ProfileApplier()
        profile = applier._get_profile("slippi-melee")

        assert profile is not None
        assert profile.profile_id == "slippi-melee"

    def test_get_profile_caches(self):
        """Test profile instances are cached."""
        applier = ProfileApplier()
        profile1 = applier._get_profile("slippi-melee")
        profile2 = applier._get_profile("slippi-melee")

        assert profile1 is profile2

    def test_get_profile_unknown_raises(self):
        """Test getting unknown profile raises ProfileNotFoundError."""
        applier = ProfileApplier()

        with pytest.raises(ProfileNotFoundError) as exc_info:
            applier._get_profile("nonexistent-profile")

        assert "Unknown profile" in str(exc_info.value)
        assert "slippi-melee" in str(exc_info.value)  # Lists available profiles


class TestApplyProfile:
    """Tests for apply_profile method."""

    def test_apply_profile_unknown(self):
        """Test applying unknown profile returns error."""
        applier = ProfileApplier()
        result = applier.apply_profile("nonexistent")

        assert result.success is False
        assert "Unknown profile" in result.error

    def test_apply_profile_success(self):
        """Test successful profile application."""
        mock_handler = MagicMock()
        mock_handler.__class__.__name__ = "TestHandler"
        mock_handler.apply.return_value = {"success": True}

        mock_profile = MagicMock()
        mock_profile.get_handlers.return_value = [mock_handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is True
            assert "TestHandler" in result.applied_settings
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_partial_failure(self):
        """Test profile application with some handlers failing."""
        handler1 = MagicMock()
        handler1.__class__.__name__ = "Handler1"
        handler1.apply.return_value = {"success": True}

        handler2 = MagicMock()
        handler2.__class__.__name__ = "Handler2"
        handler2.apply.return_value = {"success": False, "error": "Failed"}

        mock_profile = MagicMock()
        mock_profile.get_handlers.return_value = [handler1, handler2]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is False
            assert "Handler1" in result.applied_settings
            assert any("Handler2" in f for f in result.failed_settings)
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_handles_permission_error(self):
        """Test profile application handles PermissionError."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.side_effect = PermissionError("Access denied")

        mock_profile = MagicMock()
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is False
            assert "Permission denied" in str(result.failed_settings)
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_apply_profile_reboot_required(self):
        """Test profile application with reboot required."""
        handler = MagicMock()
        handler.__class__.__name__ = "TestHandler"
        handler.apply.return_value = {"success": True, "requires_reboot": True}

        mock_profile = MagicMock()
        mock_profile.get_handlers.return_value = [handler]
        mock_profile.get_settings.return_value = {}
        mock_profile.has_in_game_settings.return_value = False

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            result = applier.apply_profile("test-profile")

            assert result.success is True
            assert result.requires_reboot is True
        finally:
            del ProfileApplier.PROFILES["test-profile"]


class TestGenerateReport:
    """Tests for generate_report method."""

    def test_generate_report_creates_file(self, tmp_path):
        """Test generate_report creates markdown file."""
        mock_profile = MagicMock()
        mock_profile.generate_in_game_report.return_value = "# Report\nContent"

        applier = ProfileApplier()
        applier._profiles["test-profile"] = mock_profile
        ProfileApplier.PROFILES["test-profile"] = type(mock_profile)

        try:
            report_path = applier.generate_report("test-profile", tmp_path)

            assert report_path.exists()
            assert report_path.suffix == ".md"
            assert "Report" in report_path.read_text()
        finally:
            del ProfileApplier.PROFILES["test-profile"]

    def test_generate_report_unknown_profile(self, tmp_path):
        """Test generate_report raises for unknown profile."""
        applier = ProfileApplier()

        with pytest.raises(ProfileNotFoundError):
            applier.generate_report("nonexistent", tmp_path)


class TestListProfiles:
    """Tests for list_profiles method."""

    def test_list_profiles_returns_all(self):
        """Test list_profiles returns all registered profiles."""
        applier = ProfileApplier()
        profiles = applier.list_profiles()

        assert len(profiles) >= 4  # At least the 4 default profiles
        profile_ids = [p["id"] for p in profiles]
        assert "slippi-melee" in profile_ids
        assert "cod-bo7" in profile_ids

    def test_list_profiles_structure(self):
        """Test list_profiles returns correct structure."""
        applier = ProfileApplier()
        profiles = applier.list_profiles()

        for profile in profiles:
            assert "id" in profile
            assert "display_name" in profile
            assert "description" in profile
            assert "optimization_target" in profile


class TestRealProfiles:
    """Integration tests with real profile classes."""

    def test_slippi_melee_profile_loads(self):
        """Test Slippi Melee profile can be loaded."""
        applier = ProfileApplier()
        profile = applier._get_profile("slippi-melee")

        assert profile.profile_id == "slippi-melee"
        assert "Melee" in profile.display_name

    def test_cod_bo7_profile_loads(self):
        """Test CoD BO7 profile can be loaded."""
        applier = ProfileApplier()
        profile = applier._get_profile("cod-bo7")

        assert profile.profile_id == "cod-bo7"
        assert "Black Ops" in profile.display_name

    def test_diablo4_profile_loads(self):
        """Test Diablo 4 profile can be loaded."""
        applier = ProfileApplier()
        profile = applier._get_profile("diablo4")

        assert profile.profile_id == "diablo4"
        assert "Diablo" in profile.display_name

    def test_rivals2_profile_loads(self):
        """Test Rivals 2 profile can be loaded."""
        applier = ProfileApplier()
        profile = applier._get_profile("rivals2")

        assert profile.profile_id == "rivals2"
