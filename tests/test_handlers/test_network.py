"""Tests for NetworkSettingsHandler."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from abso.settings.network import NetworkSettingsHandler


class TestNetworkRestore:
    """Tests for restore() method."""

    def test_restore_empty_data(self):
        """Test restore with empty data returns True."""
        handler = NetworkSettingsHandler()

        result = handler.restore({})
        assert result is True

    def test_restore_no_interfaces(self):
        """Test restore with no interfaces key returns True."""
        handler = NetworkSettingsHandler()

        result = handler.restore({"other_key": "value"})
        assert result is True

    @patch("abso.settings.network.winreg.OpenKey")
    @patch("abso.settings.network.winreg.SetValueEx")
    @patch("abso.settings.network.winreg.CloseKey")
    @patch.object(NetworkSettingsHandler, "_set_tcp_global_setting")
    def test_restore_sets_values(self, mock_set_tcp_global, mock_close, mock_set, mock_open):
        """Test restore sets registry values correctly."""
        mock_key = MagicMock()
        mock_open.return_value = mock_key
        mock_set_tcp_global.return_value = {"success": True}

        handler = NetworkSettingsHandler()
        data = {
            "interfaces": {
                "{GUID-1234}": {
                    "tcp_ack_frequency": 1,
                    "tcp_no_delay": 1,
                }
            },
            "tcp_global": {
                "autotuninglevel": "normal",
            },
        }

        result = handler.restore(data)

        assert result is True
        mock_open.assert_called_once()
        assert mock_set.call_count == 2
        mock_close.assert_called_once_with(mock_key)
        mock_set_tcp_global.assert_called_once_with("autotuninglevel", "normal")

    @patch.object(NetworkSettingsHandler, "_set_tcp_global_setting")
    def test_restore_skips_nondefault_tcp_global(self, mock_set_tcp_global, monkeypatch):
        """Restore refuses to move a TCP global away from the Windows default."""
        monkeypatch.delenv("ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL", raising=False)
        mock_set_tcp_global.return_value = {"success": True}

        handler = NetworkSettingsHandler()
        data = {
            "tcp_global": {
                "autotuninglevel": "disabled",
                "rss": "enabled",
            }
        }

        result = handler.restore(data)

        # Skipping the poisoned value is not a failure; the default-valued
        # setting is still restored.
        assert result is True
        mock_set_tcp_global.assert_called_once_with("rss", "enabled")

    @patch.object(NetworkSettingsHandler, "_set_tcp_global_setting")
    def test_restore_nondefault_tcp_global_with_opt_in(self, mock_set_tcp_global, monkeypatch):
        """The env opt-in restores non-default TCP globals for intentional setups."""
        monkeypatch.setenv("ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL", "1")
        mock_set_tcp_global.return_value = {"success": True}

        handler = NetworkSettingsHandler()
        result = handler.restore({"tcp_global": {"autotuninglevel": "disabled"}})

        assert result is True
        mock_set_tcp_global.assert_called_once_with("autotuninglevel", "disabled")

    @patch.object(NetworkSettingsHandler, "_set_tcp_global_setting")
    def test_restore_ungated_tcp_global_still_writes(self, mock_set_tcp_global, monkeypatch):
        """Settings without a windows_default (ECN) restore without the opt-in."""
        monkeypatch.delenv("ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL", raising=False)
        mock_set_tcp_global.return_value = {"success": True}

        handler = NetworkSettingsHandler()
        result = handler.restore({"tcp_global": {"ecncapability": "disabled"}})

        assert result is True
        mock_set_tcp_global.assert_called_once_with("ecncapability", "disabled")

    @patch("abso.settings.network.winreg.OpenKey")
    @patch("abso.settings.network.winreg.SetValueEx")
    @patch("abso.settings.network.winreg.DeleteValue")
    @patch("abso.settings.network.winreg.CloseKey")
    def test_restore_deletes_none_values(self, mock_close, mock_delete, mock_set, mock_open):
        """Test restore deletes values that were None in backup."""
        mock_key = MagicMock()
        mock_open.return_value = mock_key

        handler = NetworkSettingsHandler()
        data = {
            "interfaces": {
                "{GUID-1234}": {
                    "tcp_ack_frequency": None,
                    "tcp_no_delay": None,
                }
            }
        }

        result = handler.restore(data)

        assert result is True
        assert mock_delete.call_count == 2

    @patch("abso.settings.network.winreg.OpenKey")
    def test_restore_handles_permission_error(self, mock_open):
        """Test restore handles PermissionError gracefully."""
        mock_open.side_effect = PermissionError("Access denied")

        handler = NetworkSettingsHandler()
        data = {
            "interfaces": {
                "{GUID-1234}": {"tcp_no_delay": 1}
            }
        }

        result = handler.restore(data)

        assert result is False

    @patch("abso.settings.network.winreg.OpenKey")
    def test_restore_handles_missing_interface(self, mock_open):
        """Test restore handles FileNotFoundError for missing interface."""
        mock_open.side_effect = FileNotFoundError("Interface not found")

        handler = NetworkSettingsHandler()
        data = {
            "interfaces": {
                "{GUID-1234}": {"tcp_no_delay": 1}
            }
        }

        result = handler.restore(data)

        # Missing interface is not a failure - just skipped
        assert result is True


class TestNetworkDetect:
    """Tests for detect() method."""

    @patch.object(NetworkSettingsHandler, "_get_interfaces_settings")
    def test_detect_returns_interfaces(self, mock_get):
        """Test detect returns interface settings."""
        mock_get.return_value = {
            "{GUID-1}": {"tcp_no_delay": 1, "tcp_ack_frequency": 1}
        }

        handler = NetworkSettingsHandler()
        result = handler.detect()

        assert "interfaces" in result
        assert "{GUID-1}" in result["interfaces"]


class TestNetworkAudit:
    """Tests for audit() method."""

    @patch.object(NetworkSettingsHandler, "detect")
    def test_audit_nagle_enabled(self, mock_detect):
        """Test audit detects Nagle enabled."""
        mock_detect.return_value = {
            "interfaces": {
                "{GUID-1}": {"tcp_no_delay": None}
            }
        }

        handler = NetworkSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 1
        assert "Nagle" in issues[0].title

    @patch.object(NetworkSettingsHandler, "detect")
    def test_audit_nagle_disabled(self, mock_detect):
        """Test audit passes when Nagle is disabled."""
        mock_detect.return_value = {
            "interfaces": {
                "{GUID-1}": {"tcp_no_delay": 1}
            }
        }

        handler = NetworkSettingsHandler()
        issues = handler.audit()

        assert len(issues) == 0


class TestNetworkVerify:
    """Tests for verify_active()."""

    @patch.object(NetworkSettingsHandler, "detect")
    @patch.object(NetworkSettingsHandler, "_get_active_interface_guids")
    def test_verify_active_for_gaming_preset(self, mock_active_ifaces, mock_detect):
        mock_active_ifaces.return_value = ["{GUID-1}"]
        mock_detect.return_value = {
            "interfaces": {
                "{GUID-1}": {"tcp_no_delay": 1, "tcp_ack_frequency": 1},
            },
            "tcp_global": {
                "autotuninglevel": "disabled",
                "ecncapability": "disabled",
                "rss": "enabled",
                "timestamps": "disabled",
            },
        }

        handler = NetworkSettingsHandler()
        result = handler.verify_active({"preset": "gaming"})

        assert result["all_active"] is True
        assert result["settings"]["interface:{GUID-1}"]["active"] is True
        assert result["settings"]["tcp_global:autotuninglevel"]["active"] is True

    @patch.object(NetworkSettingsHandler, "detect")
    @patch.object(NetworkSettingsHandler, "_get_active_interface_guids")
    def test_verify_active_reports_mismatch(self, mock_active_ifaces, mock_detect):
        mock_active_ifaces.return_value = ["{GUID-1}"]
        mock_detect.return_value = {
            "interfaces": {
                "{GUID-1}": {"tcp_no_delay": None, "tcp_ack_frequency": 1},
            },
            "tcp_global": {
                "autotuninglevel": "normal",
            },
        }

        handler = NetworkSettingsHandler()
        result = handler.verify_active(
            {
                "disable_nagle": True,
                "tcp_global": {"autotuninglevel": "disabled"},
            }
        )

        assert result["all_active"] is False
        assert result["settings"]["interface:{GUID-1}"]["active"] is False
        assert result["settings"]["tcp_global:autotuninglevel"]["active"] is False
