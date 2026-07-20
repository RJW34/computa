"""Network settings handler."""

from __future__ import annotations

import contextlib
import logging
import os
import subprocess
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


def restore_nondefault_tcp_global_enabled() -> bool:
    """Whether restore may write TCP globals that differ from the Windows default."""
    value = os.environ.get("ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL", "")
    return value.strip().lower() in {"1", "true", "yes", "on"}


class NetworkSettingsHandler(SettingsHandler):
    """Handles network-related tweaks available as an opt-in preset.

    Manages:
    - Nagle's Algorithm (TCP delay)
    - TCP acknowledgment frequency
    - TCP Auto-Tuning level
    - ECN Capability
    - RSS (Receive Side Scaling)
    - Network adapter settings (via netsh)

    A verify-mismatch here means a netsh / registry write didn't stick;
    that's actionable and must surface as CRITICAL.

    Scope: these are **opt-in** tweaks. Built-in profiles default to
    ``preset: "default"`` and do not mutate global TCP state. Most
    competitive gameplay traffic is UDP, where Nagle and TCP autotuning
    have no effect on in-game latency. Surface-level "disable all TCP
    things for gaming" guides are not aligned with current Microsoft
    documentation.

    Technical notes:
    - **Nagle**: Only affects TCP. Disabling lowers small-packet TCP delay
      for TCP-based traffic (matchmaking, chat, login), not UDP gameplay.
      Some security tools may interact poorly with per-interface
      TCPNoDelay/TcpAckFrequency writes.
    - **TCP Auto-Tuning**: Microsoft documents the default ``normal`` as a
      TCP throughput win on modern Windows. Disabling is not a general
      gaming latency fix and can hurt downloads/streaming.
    - **ECN**: Adds a small handshake cost. Some middleboxes drop ECN-marked
      packets. Not recommended as a universal latency tweak.
    - **RSS**: Distributes network processing across CPU cores. Generally
      beneficial and ABSO leaves it enabled.
    """

    is_critical_verify = True

    TCPIP_PARAMS_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters"
    INTERFACES_KEY = r"SYSTEM\CurrentControlSet\Services\Tcpip\Parameters\Interfaces"

    # TCP global settings managed via netsh.
    #
    # ``gaming_value`` here is the value the opt-in ``preset: "gaming"``
    # applies on request. It is NOT what built-in profiles do by default —
    # those use ``preset: "default"`` and leave these settings alone. These
    # descriptions avoid blanket "safe to disable" claims because modern
    # Windows networking does not behave that way in practice.
    #
    # ``windows_default`` is the Microsoft-documented default. restore() will
    # not move a setting AWAY from it without the
    # ``ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL`` opt-in; settings without a
    # ``windows_default`` key are never gated.
    TCP_GLOBAL_SETTINGS = {
        "autotuninglevel": {
            "gaming_value": "disabled",
            "windows_default": "normal",
            "description": (
                "TCP receive window auto-tuning. Microsoft recommends "
                "'normal' for TCP throughput; only disable if you have a "
                "specific measured reason."
            ),
        },
        "ecncapability": {
            "gaming_value": "disabled",
            # No windows_default: the client default has changed across
            # Windows builds, so restore does not gate this setting.
            "description": (
                "Explicit Congestion Notification. Small handshake overhead; "
                "some middleboxes drop ECN-marked packets."
            ),
        },
        "rss": {
            "gaming_value": "enabled",
            "windows_default": "enabled",
            "description": "Receive Side Scaling. Distributes load across CPU cores.",
        },
        "timestamps": {
            "gaming_value": "disabled",
            "windows_default": "disabled",
            "description": "TCP timestamps. Small overhead, rarely matters for gaming.",
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
        for _iface_guid, settings in interfaces.items():
            if settings.get("tcp_no_delay") != 1:
                nagle_enabled = True
                break

        if nagle_enabled:
            issues.append(Issue(
                title="Nagle TCP delay setting is at Windows default",
                severity="info",
                current_value="Default (enabled)",
                optimal_value="Profile-dependent / opt-in only",
                explanation=(
                    "Nagle affects TCP small-packet behavior; most live game traffic "
                    "for the built-in competitive profiles is UDP, where this registry "
                    "tweak has no effect. ABSO leaves it at default unless a profile "
                    "or user opt-in has measured a TCP-specific reason to change it."
                ),
                category="network",
            ))

        # NOTE: we intentionally no longer flag TCP Auto-Tuning or ECN as
        # suboptimal. Microsoft documents TCP receive-window autotuning
        # default 'normal' as a TCP throughput win. Most gameplay traffic is
        # UDP, and ECN/autotuning are not universally "safe to disable"
        # latency wins. ABSO surfaces these only when the user opts into the
        # TCP 'gaming' preset; they are not a default-profile audit finding.

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
            "preset": "gaming"  # Applies the opt-in TCP tuning set
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

        TCP globals with a known ``windows_default`` are only written when the
        backed-up value matches that default; restoring a non-default value
        requires the ``ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL`` opt-in. Skipped
        settings log a warning and do not fail the restore.

        Args:
            data: Backup data from backup() containing interface settings.

        Returns:
            True if restore succeeded, False otherwise.
        """
        success = True
        interfaces = data.get("interfaces", {})
        tcp_global = data.get("tcp_global", {})

        if not interfaces and not tcp_global:
            logger.warning("No network backup data to restore")
            return True

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
                        with contextlib.suppress(FileNotFoundError):
                            winreg.DeleteValue(key, "TcpAckFrequency")

                    # Restore TCPNoDelay
                    tcp_no_delay = settings.get("tcp_no_delay")
                    if tcp_no_delay is not None:
                        winreg.SetValueEx(key, "TCPNoDelay", 0, winreg.REG_DWORD, tcp_no_delay)
                    else:
                        # Value was not set originally, try to delete if it exists
                        with contextlib.suppress(FileNotFoundError):
                            winreg.DeleteValue(key, "TCPNoDelay")

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

        for setting_name, value in tcp_global.items():
            if value in {None, ""}:
                continue
            # Guard (2026-07-19): backups written while a pre-reform build's
            # gaming preset was live recorded ``autotuninglevel: disabled`` as
            # machine state, so a plain restore silently re-applied an
            # abandoned tweak that caps every TCP connection near 40 Mbps.
            # Moving a TCP global away from the Windows default is opt-in.
            normalized = self._normalize_tcp_global_value(value)
            windows_default = self.TCP_GLOBAL_SETTINGS.get(setting_name, {}).get(
                "windows_default"
            )
            if (
                windows_default is not None
                and normalized != windows_default
                and not restore_nondefault_tcp_global_enabled()
            ):
                logger.warning(
                    "Skipping restore of TCP global %s=%s: it differs from the "
                    "Windows default '%s'. Set ABSO_RESTORE_NONDEFAULT_TCP_GLOBAL=1 "
                    "to restore non-default TCP globals intentionally.",
                    setting_name,
                    value,
                    windows_default,
                )
                continue
            result = self._set_tcp_global_setting(setting_name, str(value))
            if not result["success"]:
                logger.error(
                    "Failed to restore TCP global setting %s: %s",
                    setting_name,
                    result.get("error"),
                )
                success = False

        return success

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify requested network settings are active."""
        results: dict[str, Any] = {"all_active": True, "settings": {}}
        current = self.detect()

        target_tcp_global: dict[str, str] = {}
        verify_nagle = False

        if settings.get("preset") == "gaming":
            verify_nagle = True
            target_tcp_global = {
                name: config["gaming_value"]
                for name, config in self.TCP_GLOBAL_SETTINGS.items()
            }
        else:
            verify_nagle = bool(settings.get("disable_nagle"))
            target_tcp_global = {
                name: str(value).lower()
                for name, value in settings.get("tcp_global", {}).items()
            }

        if verify_nagle:
            interfaces = current.get("interfaces", {})
            for guid in self._get_active_interface_guids():
                interface_settings = interfaces.get(guid, {})
                ack_active = interface_settings.get("tcp_ack_frequency") == 1
                no_delay_active = interface_settings.get("tcp_no_delay") == 1
                key_name = f"interface:{guid}"
                results["settings"][key_name] = {
                    "target": {"tcp_ack_frequency": 1, "tcp_no_delay": 1},
                    "current": {
                        "tcp_ack_frequency": interface_settings.get("tcp_ack_frequency"),
                        "tcp_no_delay": interface_settings.get("tcp_no_delay"),
                    },
                    "active": ack_active and no_delay_active,
                }
                if not ack_active or not no_delay_active:
                    results["all_active"] = False

        current_tcp_global = current.get("tcp_global", {})
        for setting_name, target_value in target_tcp_global.items():
            normalized_target = str(target_value).lower()
            current_value = self._normalize_tcp_global_value(current_tcp_global.get(setting_name))
            is_active = current_value == normalized_target
            results["settings"][f"tcp_global:{setting_name}"] = {
                "target": normalized_target,
                "current": current_value,
                "active": is_active,
            }
            if not is_active:
                results["all_active"] = False

        return results

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

    def _get_active_interface_guids(self) -> list[str]:
        """Get GUIDs of active network interfaces (those with a default gateway)."""
        active_guids = []

        for guid in self._get_interface_guids():
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    f"{self.INTERFACES_KEY}\\{guid}",
                    0,
                    winreg.KEY_READ
                )
                try:
                    gateway = winreg.QueryValueEx(key, "DefaultGateway")[0]
                    # DefaultGateway is REG_MULTI_SZ (list of strings)
                    if gateway and any(g.strip() for g in gateway if g):
                        active_guids.append(guid)
                except FileNotFoundError:
                    pass
                finally:
                    winreg.CloseKey(key)
            except OSError:
                pass

        if not active_guids:
            # Fallback: if no active interfaces found, use all (safety net)
            logger.debug("No active interfaces found via DefaultGateway, falling back to all")
            return self._get_interface_guids()

        logger.debug(f"Found {len(active_guids)} active interface(s)")
        return active_guids

    def _apply_to_all_interfaces(self, settings: dict[str, int]) -> None:
        """Apply settings to active network interfaces only."""
        for guid in self._get_active_interface_guids():
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
                            raw_key = parts[0].strip().lower()
                            key = raw_key.replace(" ", "").replace("-", "")
                            value = parts[1].strip()

                            # Map to our setting names
                            if (
                                "receivewindowautotuninglevel" in key
                                or "autotuning" in key
                                or "autotuninglevel" in key
                            ):
                                result["autotuninglevel"] = value.lower()
                            elif "ecn" in key:
                                result["ecncapability"] = value.lower()
                            elif (
                                "receivesidescalingstate" in key
                                or ("rss" in key and "receive" in key)
                            ):
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

    def _normalize_tcp_global_value(self, value: Any) -> str | None:
        """Normalize netsh TCP global output for stable verification."""
        if value is None:
            return None
        return str(value).strip().lower()
