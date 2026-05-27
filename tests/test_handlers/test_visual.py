"""Tests for VisualSettingsHandler."""

from unittest.mock import patch

from abso.settings.visual import VisualSettingsHandler


class TestVisualDetect:
    """Tests for VisualSettingsHandler.detect()."""

    @patch.object(VisualSettingsHandler, "_get_visual_fx_setting")
    @patch.object(VisualSettingsHandler, "_get_transparency_enabled")
    @patch.object(VisualSettingsHandler, "_get_animations_enabled")
    @patch.object(VisualSettingsHandler, "_get_menu_animation")
    def test_detect_returns_visual_settings(self, mock_menu, mock_anim, mock_trans, mock_fx):
        """Test detect returns dictionary with visual settings."""
        mock_fx.return_value = "Custom"
        mock_trans.return_value = True
        mock_anim.return_value = True
        mock_menu.return_value = True

        handler = VisualSettingsHandler()
        result = handler.detect()

        assert "visual_fx_setting" in result
        assert "transparency" in result
        assert "animations" in result
        assert "menu_animation" in result

    @patch.object(VisualSettingsHandler, "_get_visual_fx_setting")
    @patch.object(VisualSettingsHandler, "_get_transparency_enabled")
    @patch.object(VisualSettingsHandler, "_get_animations_enabled")
    @patch.object(VisualSettingsHandler, "_get_menu_animation")
    def test_detect_handles_none_values(self, mock_menu, mock_anim, mock_trans, mock_fx):
        """Test detect handles None values gracefully."""
        mock_fx.return_value = None
        mock_trans.return_value = None
        mock_anim.return_value = None
        mock_menu.return_value = None

        handler = VisualSettingsHandler()
        result = handler.detect()

        assert result is not None


class TestVisualAudit:
    """Tests for VisualSettingsHandler.audit()."""

    @patch.object(VisualSettingsHandler, "detect")
    def test_audit_transparency_enabled_creates_issue(self, mock_detect):
        """Test audit creates issue when transparency is enabled."""
        mock_detect.return_value = {
            "visual_fx_setting": "Custom",
            "transparency": True,
            "animations": False,
            "menu_animation": False,
        }

        handler = VisualSettingsHandler()
        issues = handler.audit()

        transparency_issues = [i for i in issues if "transparency" in i.title.lower()]
        assert len(transparency_issues) >= 1

    @patch.object(VisualSettingsHandler, "detect")
    def test_audit_animations_enabled_creates_issue(self, mock_detect):
        """Test audit creates issue when animations are enabled."""
        mock_detect.return_value = {
            "visual_fx_setting": "Custom",
            "transparency": False,
            "animations": True,
            "menu_animation": False,
        }

        handler = VisualSettingsHandler()
        issues = handler.audit()

        animation_issues = [i for i in issues if "animation" in i.title.lower()]
        assert len(animation_issues) >= 1

    @patch.object(VisualSettingsHandler, "detect")
    def test_audit_all_disabled_no_issues(self, mock_detect):
        """Test audit returns no issues when all effects are disabled."""
        mock_detect.return_value = {
            "visual_fx_setting": "Performance",
            "transparency": False,
            "animations": False,
            "menu_animation": False,
        }

        handler = VisualSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0


class TestVisualApply:
    """Tests for VisualSettingsHandler.apply()."""

    @patch.object(VisualSettingsHandler, "_set_transparency_enabled")
    @patch.object(VisualSettingsHandler, "_set_animations_enabled")
    def test_apply_disables_effects(self, mock_anim, mock_trans):
        """Test apply disables visual effects."""
        handler = VisualSettingsHandler()
        result = handler.apply({
            "disable_transparency": True,
            "disable_animations": True,
        })

        assert result["success"] is True
        mock_trans.assert_called_with(False)
        mock_anim.assert_called_with(False)

    @patch.object(VisualSettingsHandler, "_set_transparency_enabled")
    def test_apply_handles_error(self, mock_trans):
        """Test apply handles errors gracefully."""
        mock_trans.side_effect = PermissionError("Access denied")

        handler = VisualSettingsHandler()
        result = handler.apply({"disable_transparency": True})

        assert result["success"] is False
        assert result["error"] is not None


class TestVisualBackupRestore:
    """Tests for VisualSettingsHandler backup/restore."""

    @patch.object(VisualSettingsHandler, "detect")
    def test_backup_returns_current_state(self, mock_detect):
        """Test backup returns current visual settings."""
        expected = {"transparency": True, "animations": True}
        mock_detect.return_value = expected

        handler = VisualSettingsHandler()
        result = handler.backup()

        assert "transparency" in result
        assert "animations" in result

    @patch.object(VisualSettingsHandler, "_set_transparency_enabled")
    @patch.object(VisualSettingsHandler, "_set_animations_enabled")
    def test_restore_applies_backed_up_state(self, mock_anim, mock_trans):
        """Test restore applies backed up settings."""
        handler = VisualSettingsHandler()
        result = handler.restore({
            "transparency": True,
            "animations": True,
        })

        assert result is True
        mock_trans.assert_called()
        mock_anim.assert_called()

    def test_restore_handles_empty_data(self):
        """Test restore handles empty backup data."""
        handler = VisualSettingsHandler()
        result = handler.restore({})

        assert result is True

    @patch.object(VisualSettingsHandler, "_set_transparency_enabled")
    def test_restore_handles_exception(self, mock_set):
        """Test restore handles exceptions gracefully."""
        mock_set.side_effect = Exception("Failed")

        handler = VisualSettingsHandler()
        result = handler.restore({"transparency": True})

        assert result is False


class TestVisualApplyPreset:
    """Tests for preset application."""

    @patch.object(VisualSettingsHandler, "_set_transparency_enabled")
    @patch.object(VisualSettingsHandler, "_set_animations_enabled")
    @patch.object(VisualSettingsHandler, "_set_menu_animation")
    def test_apply_gaming_preset(self, mock_menu, mock_anim, mock_trans):
        """Test apply gaming preset optimizes all settings."""
        handler = VisualSettingsHandler()
        result = handler.apply({"preset": "gaming"})

        assert result["success"] is True

    @patch.object(VisualSettingsHandler, "_set_transparency_enabled")
    @patch.object(VisualSettingsHandler, "_set_animations_enabled")
    def test_apply_multiple_settings(self, mock_anim, mock_trans):
        """Test apply can set multiple visual settings."""
        handler = VisualSettingsHandler()
        result = handler.apply({
            "disable_transparency": True,
            "disable_animations": True,
        })

        assert result["success"] is True


class TestVisualConstants:
    """Tests for visual constants and configuration."""

    def test_registry_paths_defined(self):
        """Test registry paths are defined."""
        handler = VisualSettingsHandler()
        assert hasattr(handler, "DESKTOP_KEY") or hasattr(handler, "VISUAL_EFFECTS_KEY")


class TestVisualPrivateMethods:
    """Tests for private methods."""

    @patch("abso.settings.visual.winreg.CloseKey")
    @patch("abso.settings.visual.winreg.QueryValueEx")
    @patch("abso.settings.visual.winreg.OpenKey")
    def test_get_transparency_enabled(self, mock_open, mock_query, mock_close):
        """Test _get_transparency_enabled returns boolean."""
        mock_query.return_value = (1, 1)

        handler = VisualSettingsHandler()
        result = handler._get_transparency_enabled()

        assert isinstance(result, bool)

    @patch("abso.settings.visual.winreg.OpenKey", side_effect=FileNotFoundError)
    def test_get_transparency_handles_missing_key(self, mock_open):
        """Test _get_transparency_enabled handles missing key."""
        handler = VisualSettingsHandler()
        result = handler._get_transparency_enabled()

        assert result is None

    @patch("abso.settings.visual.winreg.CloseKey")
    @patch("abso.settings.visual.winreg.QueryValueEx")
    @patch("abso.settings.visual.winreg.OpenKey")
    def test_get_animations_enabled(self, mock_open, mock_query, mock_close):
        """Test _get_animations_enabled returns boolean."""
        mock_query.return_value = ("1", 1)

        handler = VisualSettingsHandler()
        result = handler._get_animations_enabled()

        assert isinstance(result, bool | None)

    @patch("abso.settings.visual.winreg.OpenKey", side_effect=FileNotFoundError)
    def test_get_animations_handles_missing_key(self, mock_open):
        """Test _get_animations_enabled handles missing key."""
        handler = VisualSettingsHandler()
        result = handler._get_animations_enabled()

        assert result is None

    @patch("abso.settings.visual.winreg.CloseKey")
    @patch("abso.settings.visual.winreg.SetValueEx")
    @patch("abso.settings.visual.winreg.OpenKey")
    def test_set_transparency_enabled(self, mock_open, mock_set, mock_close):
        """Test _set_transparency_enabled writes to registry."""
        handler = VisualSettingsHandler()
        handler._set_transparency_enabled(False)

        mock_set.assert_called()

    @patch("abso.settings.visual.winreg.OpenKey", side_effect=PermissionError)
    def test_set_transparency_raises_on_permission_error(self, mock_open):
        """Test _set_transparency_enabled raises on permission error."""
        import pytest
        handler = VisualSettingsHandler()

        with pytest.raises(PermissionError):
            handler._set_transparency_enabled(False)
