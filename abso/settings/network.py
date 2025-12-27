"""Network settings handler."""

from __future__ import annotations

import logging
import subprocess
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class NetworkSettingsHandler(SettingsHandler):
    """Handles network-related gaming optimizations.

    Manages:
    - Nagle's Algorithm (TCP delay)
    - TCP acknowledgment frequency
    - TCP Auto-Tuning level
    - ECN Capability
    - RSS (Receive Side Scaling)
    - Network adapter settings (via netsh)

    Technical notes:
    - TCP Auto-Tuning dynamically adjusts receive window. Disabling can reduce
      latency but may hurt throughput on high-latency connections.
    - ECN (Explicit Congestion Notification) adds overhead. Disabling is safe.
    - RSS distributes network processing across CPU cores. Generally beneficial.
    """

    TCPIP_PARAMS_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
    INTERFACES_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"

    # TCP global settings managed via netsh
    TCP_GLOBAL_SETTINGS = {
        "autotuninglevel": {
            "gaming_value": "disabled",
            "description": "TCP receive window auto-tuning. Disable for lower latency.",
        },
        "ecncapability": {
            "gaming_value": "disabled",
            "description": "Explicit Congestion Notification. Adds overhead.",
        },
        "rss": {
            "gaming_value": "enabled",
            "description": "Receive Side Scaling. Distributes load across CPU cores.",
        },
        "timestamps": {
            "gaming_value": "disabled",
            "description": "TCP timestamps. Small overhead, rarely needed.",
        },
    }

    def detect(self) -> dict[str, Any]:
        """Detect current network settings."""
        return {
            "interfaces": self._get_interfaces_settings(),
            "tcp_global": self._get_tcp_global_settings(),
        }

    def audit(self) -> list[Issue]:
        """Audit network settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        interfaces = current.get("interfaces", {})

        # Check each interface for Nagle settings
        nagle_enabled = False
        for iface_guid, settings in interfaces.items():
            if settings.get("tcp_no_delay") != 1:
                nagle_enabled = True
                break

        if nagle_enabled:
            issues.append(Issue(
                title="Nagle's Algorithm may be enabled",
                severity="info",
                current_value="Default (enabled)",
                optimal_value="Disabled (TCPNoDelay=1)",
                explanation="Disabling Nagle reduces network latency by sending packets immediately instead of buffering.",
                category="network",
            ))

        # Check TCP global settings
        tcp_global = current.get("tcp_global", {})

        # Check auto-tuning
        auto_tuning = tcp_global.get("autotuninglevel", "").lower()
        if auto_tuning and auto_tuning != "disabled":
            issues.append(Issue(
                title="TCP Auto-Tuning is enabled",
                severity="info",
                current_value=auto_tuning.capitalize(),
                optimal_value="Disabled",
                explanation=(
                    "TCP Auto-Tuning dynamically adjusts receive window size. "
                    "Disabling can reduce latency for gaming but may hurt download speeds."
                ),
                category="network",
            ))

        # Check ECN
        ecn = tcp_global.get("ecncapability", "").lower()
        if ecn and ecn != "disabled":
            issues.append(Issue(
                title="ECN Capability is enabled",
                severity="info",
                current_value=ecn.capitalize(),
                optimal_value="Disabled",
                explanation="ECN adds packet overhead. Disabling is safe and reduces latency.",
                category="network",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply network settings.

        Settings format:
        {
            "disable_nagle": True,
            "tcp_global": {
                "autotuninglevel": "disabled",
                "ecncapability": "disabled",
                "rss": "enabled",
                "timestamps": "disabled",
            }
        }

        Or use preset:
        {
            "preset": "gaming"  # Applies all gaming-optimized settings
        }
        """
        errors: list[str] = []

        try:
            if settings.get("preset") == "gaming":
                # Apply all gaming optimizations
                self._apply_to_all_interfaces({
                    "TcpAckFrequency": 1,
                    "TCPNoDelay": 1,
                })
                for setting_name, config in self.TCP_GLOBAL_SETTINGS.items():
                    result = self._set_tcp_global_setting(setting_name, config["gaming_value"])
                    if not result["success"]:
                        errors.append(result.get("error", f"Failed to set {setting_name}"))

            else:
                if settings.get("disable_nagle"):
                    self._apply_to_all_interfaces({
                        "TcpAckFrequency": 1,
                        "TCPNoDelay": 1,
                    })

                if "tcp_global" in settings:
                    for setting_name, value in settings["tcp_global"].items():
                        result = self._set_tcp_global_setting(setting_name, value)
                        if not result["success"]:
                            errors.append(result.get("error", f"Failed to set {setting_name}"))

        except PermissionError as e:
            errors.append(f"Permission denied: {e}")
        except OSError as e:
            errors.append(f"OS error: {e}")
        except subprocess.SubprocessError as e:
            errors.append(f"Subprocess error: {e}")

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,
        }

    def backup(self) -> dict[str, Any]:
        """Backup current network settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore network settings from backup.

        Args:
            data: Backup data from backup() containing interface settings.

        Returns:
            True if restore succeeded, False otherwise.
        """
        interfaces = data.get("interfaces", {})
        if not interfaces:
            logger.warning("No interface data in backup to restore")
            return True

        success = True
        for guid, settings in interfaces.items():
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    f"{self.INTERFACES_KEY}\\{guid}",
                    0,
                    winreg.KEY_ALL_ACCESS
                )

                try:
                    # Restore TcpAckFrequency
                    tcp_ack = settings.get("tcp_ack_frequency")
                    if tcp_ack is not None:
                        winreg.SetValueEx(key, "TcpAckFrequency", 0, winreg.REG_DWORD, tcp_ack)
                    else:
                        # Value was not set originally, try to delete if it exists
                        try:
                            winreg.DeleteValue(key, "TcpAckFrequency")
                        except FileNotFoundError:
                            pass

                    # Restore TCPNoDelay
                    tcp_no_delay = settings.get("tcp_no_delay")
                    if tcp_no_delay is not None:
                        winreg.SetValueEx(key, "TCPNoDelay", 0, winreg.REG_DWORD, tcp_no_delay)
                    else:
                        # Value was not set originally, try to delete if it exists
                        try:
                            winreg.DeleteValue(key, "TCPNoDelay")
                        except FileNotFoundError:
                            pass

                    logger.debug(f"Restored network settings for interface {guid}")
                finally:
                    winreg.CloseKey(key)

            except PermissionError:
                logger.warning(f"Permission denied restoring interface {guid}")
                success = False
            except FileNotFoundError:
                logger.warning(f"Interface {guid} no longer exists, skipping")
            except (ValueError, TypeError, KeyError) as e:
                logger.error(f"Invalid backup data for interface {guid}: {e}")
                success = False

        return success

    # Private helper methods

    def _get_interface_guids(self) -> list[str]:
        """Get all network interface GUIDs."""
        guids = []

        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.INTERFACES_KEY,
                0,
                winreg.KEY_READ
            )

            try:
                i = 0
                while True:
                    try:
                        guid = winreg.EnumKey(key, i)
                        guids.append(guid)
                        i += 1
                    except OSError:
                        break
            finally:
                winreg.CloseKey(key)

        except OSError as e:
            logger.error(f"Failed to enumerate interfaces (registry error): {e}")

        return guids

    def _get_interfaces_settings(self) -> dict[str, dict[str, Any]]:
        """Get settings for all network interfaces."""
        interfaces = {}

        for guid in self._get_interface_guids():
            settings = {}

            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    f"{self.INTERFACES_KEY}\\{guid}",
                    0,
                    winreg.KEY_READ
                )

                try:
                    settings["tcp_ack_frequency"] = winreg.QueryValueEx(key, "TcpAckFrequency")[0]
                except FileNotFoundError:
                    settings["tcp_ack_frequency"] = None

                try:
                    settings["tcp_no_delay"] = winreg.QueryValueEx(key, "TCPNoDelay")[0]
                except FileNotFoundError:
                    settings["tcp_no_delay"] = None

                winreg.CloseKey(key)

            except OSError as e:
                logger.debug(f"Failed to read interface {guid}: {e}")

            interfaces[guid] = settings

        return interfaces

    def _apply_to_all_interfaces(self, settings: dict[str, int]) -> None:
        """Apply settings to all network interfaces."""
        for guid in self._get_interface_guids():
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    f"{self.INTERFACES_KEY}\\{guid}",
                    0,
                    winreg.KEY_ALL_ACCESS
                )

                try:
                    for name, value in settings.items():
                        winreg.SetValueEx(key, name, 0, winreg.REG_DWORD, value)
                finally:
                    winreg.CloseKey(key)

                logger.debug(f"Applied network settings to {guid}")

            except PermissionError:
                logger.warning(f"Permission denied for interface {guid}")
            except OSError as e:
                logger.error(f"Failed to apply to interface {guid}: {e}")

    def _get_tcp_global_settings(self) -> dict[str, str]:
        """Get TCP global settings via netsh."""
        result = {}

        try:
            # Run netsh to get TCP global settings
            output = subprocess.run(
                ["netsh", "int", "tcp", "show", "global"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if output.returncode == 0:
                for line in output.stdout.splitlines():
                    line = line.strip()
                    if ":" in line:
                        parts = line.split(":", 1)
                        if len(parts) == 2:
                            key = parts[0].strip().lower().replace(" ", "")
                            value = parts[1].strip()

                            # Map to our setting names
                            if "autotuning" in key or "autotuninglevel" in key:
                                result["autotuninglevel"] = value.lower()
                            elif "ecn" in key:
                                result["ecncapability"] = value.lower()
                            elif "rss" in key and "receive" in key:
                                result["rss"] = value.lower()
                            elif "timestamps" in key:
                                result["timestamps"] = value.lower()

        except subprocess.TimeoutExpired:
            logger.warning("Timeout getting TCP global settings")
        except subprocess.SubprocessError as e:
            logger.debug(f"Failed to get TCP global settings (subprocess error): {e}")
        except (ValueError, IndexError) as e:
            logger.debug(f"Failed to parse TCP global settings: {e}")

        return result

    def _set_tcp_global_setting(self, setting: str, value: str) -> dict[str, Any]:
        """Set a TCP global setting via netsh."""
        try:
            result = subprocess.run(
                ["netsh", "int", "tcp", "set", "global", f"{setting}={value}"],
                capture_output=True,
                text=True,
                timeout=10,
            )

            if result.returncode == 0:
                return {"success": True}
            else:
                error_msg = result.stderr.strip() or result.stdout.strip()
                return {"success": False, "error": error_msg}

        except subprocess.TimeoutExpired:
            return {"success": False, "error": "Timeout setting TCP global"}
        except subprocess.SubprocessError as e:
            return {"success": False, "error": f"Subprocess error: {e}"}
        except FileNotFoundError:
            return {"success": False, "error": "netsh command not found"}
