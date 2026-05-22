"""Tests for constants module."""


from abso.core.constants import (
    AppCompatFlags,
    Defaults,
    ErrorMessages,
    RegistryPaths,
    RegistryValues,
)


class TestRegistryPaths:
    """Tests for RegistryPaths constants."""

    def test_multimedia_paths_are_strings(self):
        """Test multimedia registry paths are strings."""
        assert isinstance(RegistryPaths.MULTIMEDIA_SYSTEM_PROFILE, str)
        assert isinstance(RegistryPaths.MULTIMEDIA_TASKS, str)
        assert isinstance(RegistryPaths.MULTIMEDIA_GAMES_TASK, str)
        assert isinstance(RegistryPaths.MULTIMEDIA_AUDIO_TASK, str)

    def test_graphics_paths_are_strings(self):
        """Test graphics registry paths are strings."""
        assert isinstance(RegistryPaths.GAME_BAR, str)
        assert isinstance(RegistryPaths.GAME_DVR, str)
        assert isinstance(RegistryPaths.GAME_CONFIG_STORE, str)
        assert isinstance(RegistryPaths.GRAPHICS_DRIVERS, str)
        assert isinstance(RegistryPaths.DWM, str)
        assert isinstance(RegistryPaths.DWM_USER, str)

    def test_security_paths_are_strings(self):
        """Test security registry paths are strings."""
        assert isinstance(RegistryPaths.VBS, str)

    def test_process_paths_are_strings(self):
        """Test process registry paths are strings."""
        assert isinstance(RegistryPaths.IFEO, str)
        assert isinstance(RegistryPaths.PRIORITY_CONTROL, str)
        assert isinstance(RegistryPaths.APPCOMPAT_LAYERS, str)

    def test_network_paths_are_strings(self):
        """Test network registry paths are strings."""
        assert isinstance(RegistryPaths.TCPIP_PARAMETERS, str)
        assert isinstance(RegistryPaths.TCPIP_INTERFACES, str)

    def test_memory_paths_are_strings(self):
        """Test memory registry paths are strings."""
        assert isinstance(RegistryPaths.MEMORY_MANAGEMENT, str)

    def test_visual_paths_are_strings(self):
        """Test visual effect registry paths are strings."""
        assert isinstance(RegistryPaths.VISUAL_EFFECTS, str)
        assert isinstance(RegistryPaths.EXPLORER_ADVANCED, str)
        assert isinstance(RegistryPaths.DESKTOP, str)
        assert isinstance(RegistryPaths.WINDOW_METRICS, str)
        assert isinstance(RegistryPaths.PERSONALIZE, str)

    def test_input_paths_are_strings(self):
        """Test input registry paths are strings."""
        assert isinstance(RegistryPaths.MOUSE, str)

    def test_audio_paths_are_strings(self):
        """Test audio registry paths are strings."""
        assert isinstance(RegistryPaths.AUDIO, str)
        assert isinstance(RegistryPaths.MMDEVICES_RENDER, str)

    def test_update_paths_are_strings(self):
        """Test Windows Update registry paths are strings."""
        assert isinstance(RegistryPaths.DELIVERY_OPTIMIZATION, str)
        assert isinstance(RegistryPaths.WINDOWS_UPDATE_UX, str)
        assert isinstance(RegistryPaths.WINDOWS_UPDATE_AU, str)


class TestRegistryValues:
    """Tests for RegistryValues constants."""

    def test_game_mode_values_are_strings(self):
        """Test game mode value names are strings."""
        assert isinstance(RegistryValues.GAME_MODE_ENABLED, str)
        assert isinstance(RegistryValues.GAME_BAR_ENABLED, str)
        assert isinstance(RegistryValues.GAME_DVR_ENABLED, str)

    def test_hags_value_is_string(self):
        """Test HAGS value name is string."""
        assert isinstance(RegistryValues.HAGS_ENABLED, str)

    def test_vbs_value_is_string(self):
        """Test VBS value name is string."""
        assert isinstance(RegistryValues.VBS_ENABLED, str)

    def test_memory_values_are_strings(self):
        """Test memory value names are strings."""
        assert isinstance(RegistryValues.LARGE_SYSTEM_CACHE, str)
        assert isinstance(RegistryValues.DISABLE_PAGING_EXECUTIVE, str)

    def test_multimedia_values_are_strings(self):
        """Test multimedia value names are strings."""
        assert isinstance(RegistryValues.SYSTEM_RESPONSIVENESS, str)
        assert isinstance(RegistryValues.NETWORK_THROTTLING_INDEX, str)

    def test_games_task_values_are_strings(self):
        """Test games task value names are strings."""
        assert isinstance(RegistryValues.GPU_PRIORITY, str)
        assert isinstance(RegistryValues.PRIORITY, str)
        assert isinstance(RegistryValues.SCHEDULING_CATEGORY, str)
        assert isinstance(RegistryValues.SFIO_PRIORITY, str)

    def test_network_values_are_strings(self):
        """Test network value names are strings."""
        assert isinstance(RegistryValues.TCP_ACK_FREQUENCY, str)
        assert isinstance(RegistryValues.TCP_NO_DELAY, str)
        assert isinstance(RegistryValues.NAGLING_DISABLED, str)

    def test_mouse_values_are_strings(self):
        """Test mouse value names are strings."""
        assert isinstance(RegistryValues.MOUSE_SPEED, str)
        assert isinstance(RegistryValues.MOUSE_THRESHOLD1, str)
        assert isinstance(RegistryValues.MOUSE_THRESHOLD2, str)


class TestDefaults:
    """Tests for Defaults constants."""

    def test_system_responsiveness_values(self):
        """Test system responsiveness default values."""
        assert Defaults.SYSTEM_RESPONSIVENESS_GAMING == 10
        assert Defaults.SYSTEM_RESPONSIVENESS_DEFAULT == 20

    def test_network_throttling_values(self):
        """Test network throttling default values."""
        assert Defaults.NETWORK_THROTTLING_DISABLED == 0xFFFFFFFF
        assert Defaults.NETWORK_THROTTLING_DEFAULT == 10

    def test_gpu_priority_values(self):
        """Test GPU priority default values."""
        assert Defaults.GPU_PRIORITY_HIGH == 8
        assert Defaults.GPU_PRIORITY_NORMAL == 1

    def test_scheduling_values(self):
        """Test scheduling category values."""
        assert Defaults.SCHEDULING_HIGH == "High"
        assert Defaults.SCHEDULING_MEDIUM == "Medium"
        assert Defaults.SCHEDULING_LOW == "Low"

    def test_mouse_values(self):
        """Test mouse default values."""
        assert Defaults.MOUSE_SPEED_RAW == "0"
        assert Defaults.MOUSE_THRESHOLD_DISABLED == "0"


class TestAppCompatFlags:
    """Tests for AppCompatFlags constants."""

    def test_flag_values_are_strings(self):
        """Test all flag values are strings."""
        assert isinstance(AppCompatFlags.DISABLE_FULLSCREEN_OPT, str)
        assert isinstance(AppCompatFlags.HIGH_DPI_AWARE, str)
        assert isinstance(AppCompatFlags.GAMING_FLAGS, str)

    def test_disable_fullscreen_opt_format(self):
        """Test disable fullscreen opt flag format."""
        assert "DISABLEDXMAXIMIZEDWINDOWEDMODE" in AppCompatFlags.DISABLE_FULLSCREEN_OPT

    def test_high_dpi_aware_format(self):
        """Test high DPI aware flag format."""
        assert "HIGHDPIAWARE" in AppCompatFlags.HIGH_DPI_AWARE

    def test_gaming_flags_contains_both(self):
        """Test gaming flags contains both individual flags."""
        assert "DISABLEDXMAXIMIZEDWINDOWEDMODE" in AppCompatFlags.GAMING_FLAGS
        assert "HIGHDPIAWARE" in AppCompatFlags.GAMING_FLAGS


class TestErrorMessages:
    """Tests for ErrorMessages constants."""

    def test_permission_error_messages_are_strings(self):
        """Test permission error messages are strings."""
        assert isinstance(ErrorMessages.PERMISSION_DENIED, str)
        assert isinstance(ErrorMessages.PERMISSION_DENIED_ADMIN, str)
        assert isinstance(ErrorMessages.ADMIN_REQUIRED, str)
        assert isinstance(ErrorMessages.SOME_FEATURES_REQUIRE_ADMIN, str)
        assert isinstance(ErrorMessages.ELEVATED_PRIVILEGES_REQUIRED, str)

    def test_registry_error_messages_are_strings(self):
        """Test registry error messages are strings."""
        assert isinstance(ErrorMessages.REGISTRY_KEY_NOT_FOUND, str)
        assert isinstance(ErrorMessages.REGISTRY_VALUE_NOT_FOUND, str)
        assert isinstance(ErrorMessages.REGISTRY_READ_FAILED, str)
        assert isinstance(ErrorMessages.REGISTRY_WRITE_FAILED, str)

    def test_detection_error_messages_are_strings(self):
        """Test detection error messages are strings."""
        assert isinstance(ErrorMessages.DETECTION_FAILED, str)
        assert isinstance(ErrorMessages.WMI_QUERY_FAILED, str)

    def test_apply_error_messages_are_strings(self):
        """Test apply error messages are strings."""
        assert isinstance(ErrorMessages.APPLY_FAILED, str)
        assert isinstance(ErrorMessages.BACKUP_REQUIRED, str)

    def test_restore_error_messages_are_strings(self):
        """Test restore error messages are strings."""
        assert isinstance(ErrorMessages.RESTORE_FAILED, str)
        assert isinstance(ErrorMessages.BACKUP_NOT_FOUND, str)
        assert isinstance(ErrorMessages.BACKUP_CORRUPTED, str)

    def test_general_error_messages_are_strings(self):
        """Test general error messages are strings."""
        assert isinstance(ErrorMessages.OPERATION_FAILED, str)
        assert isinstance(ErrorMessages.REBOOT_REQUIRED, str)

    def test_permission_denied_is_formattable(self):
        """Test permission denied message can be formatted."""
        result = ErrorMessages.PERMISSION_DENIED.format(error="Access denied")
        assert "Access denied" in result

    def test_registry_key_not_found_is_formattable(self):
        """Test registry key not found message can be formatted."""
        result = ErrorMessages.REGISTRY_KEY_NOT_FOUND.format(key_path="HKLM\\Test")
        assert "HKLM\\Test" in result

    def test_backup_not_found_is_formattable(self):
        """Test backup not found message can be formatted."""
        result = ErrorMessages.BACKUP_NOT_FOUND.format(backup_id="12345")
        assert "12345" in result
