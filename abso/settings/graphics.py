"""Graphics and display settings handler."""

from __future__ import annotations

import contextlib
import logging
import winreg
from typing import Any

from abso.core.models import Issue
from abso.settings import MONITOR_DATA_STORE_KEY as _MONITOR_DATA_STORE_KEY
from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


class GraphicsSettingsHandler(SettingsHandler):
    """Handles graphics and display optimization settings.

    Manages:
    - Multi-Plane Overlay (MPO) - can cause stutter on some systems
    - Desktop Window Manager (DWM) settings
    - Global Fullscreen Optimizations (FSO)
    - Hardware cursor settings

    Technical notes:
    - MPO allows Windows to composite multiple planes in hardware
      Can cause issues with G-Sync, overlays, and some games
    - FSO (GameDVR_FSEBehavior) controls whether games get true exclusive fullscreen
    - DWM cannot be disabled on Windows 10/11 but some settings can be tuned

    Reboot behavior:
    - MPO changes (OverlayTestMode registry key) require a reboot to take effect
    - HOWEVER, if MPO is already disabled from a previous profile application,
      no reboot is needed when switching to another profile that also disables MPO
    - FSO changes take effect immediately on next game launch (no reboot needed)
    - Switching between profiles that share the same MPO setting won't require a reboot
    """

    is_critical_verify = True

    # Registry paths
    DWM_KEY = r"SOFTWARE\Microsoft\Windows\Dwm"
    # MPO disable: Windows 11 24H2+ requires DisableOverlays under GraphicsDrivers.
    # The old OverlayTestMode under DWM no longer works on 24H2+.
    GRAPHICS_DRIVERS_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers"
    DWM_LEGACY_KEY = r"SOFTWARE\Microsoft\Windows\Dwm"  # Fallback for pre-24H2
    GAME_CONFIG_KEY = r"System\GameConfigStore"
    EXPLORER_ADVANCED_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\Advanced"
    COLOR_MANAGEMENT_KEY = r"Software\Microsoft\Windows\CurrentVersion\ColorManagement"
    MONITOR_DATA_STORE_KEY = _MONITOR_DATA_STORE_KEY

    def detect(self) -> dict[str, Any]:
        """Detect current graphics settings."""
        return {
            "mpo_disabled": self._get_mpo_disabled(),
            "global_fso_disabled": self._get_global_fso_disabled(),
            "game_dvr_behavior": self._get_game_dvr_behavior(),
            "hardware_cursor": self._get_hardware_cursor(),
            "auto_color_management": self._get_auto_color_management(),
        }

    def audit(self) -> list[Issue]:
        """Audit graphics settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check MPO status
        # NOTE: MPO being enabled is usually CORRECT for VRR/G-Sync setups
        # Only flag as issue if user reports stuttering
        if not current.get("mpo_disabled"):
            issues.append(
                Issue(
                    title="MPO is enabled (expected default)",
                    severity="info",
                    current_value="Enabled (default)",
                    optimal_value="Keep enabled for VRR/G-Sync",
                    explanation=(
                        "MPO (Multi-Plane Overlay) is the expected default on modern "
                        "Windows 11. ABSO keeps it enabled for VRR profiles because "
                        "disabling MPO can alter or break the VRR/compositor path on "
                        "some GPU, driver, and Windows build combinations. Disable it "
                        "only for a specific measured compositor problem."
                    ),
                    category="graphics",
                )
            )

        # Check global FSO status
        game_dvr_behavior = current.get("game_dvr_behavior")
        if game_dvr_behavior == 2:
            issues.append(
                Issue(
                    title="Global Fullscreen Optimizations are forcibly disabled",
                    severity="info",
                    current_value="Disabled",
                    optimal_value="Profile-managed per-exe policy",
                    explanation=(
                        "Windows 'Optimizations for windowed games' (Fullscreen "
                        "Optimizations) is not a universal off-for-gaming toggle. "
                        "Microsoft documents it as a DX10/DX11 windowed/borderless "
                        "performance and feature path. ABSO uses per-executable FSO "
                        "overrides for strict profiles and clears them for capture "
                        "profiles, so a global disable can conflict with those lanes."
                    ),
                    category="graphics",
                )
            )

        # Check Auto Color Management (ACM) status
        acm_status = current.get("auto_color_management", {})
        acm_enabled_monitors = []
        for monitor_id, enabled in acm_status.get("per_monitor", {}).items():
            if enabled:
                acm_enabled_monitors.append(monitor_id)

        if acm_enabled_monitors:
            issues.append(
                Issue(
                    title="Auto Color Management (ACM) is enabled",
                    severity="warning",
                    current_value=f"Enabled on {len(acm_enabled_monitors)} monitor(s)",
                    optimal_value="Disabled",
                    explanation=(
                        "Auto Color Management changes the display color-management path. "
                        "That can be desirable for color-accurate creative work, but gaming "
                        "profiles that manage HDR/ICC state may prefer a fixed unmanaged "
                        "path to avoid unexpected gamut or SDR clamp changes."
                    ),
                    category="graphics",
                )
            )

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply graphics optimization settings.

        Only sets requires_reboot=True if we actually change MPO state.
        If MPO is already in the desired state, no reboot is needed.
        """
        errors: list[str] = []
        notices: list[str] = []
        changed_keys: list[str] = []
        requires_reboot = False

        # Get current values to check if we're actually changing anything
        current = self.detect()

        try:
            if "disable_mpo" in settings:
                target = settings["disable_mpo"]
                if current.get("mpo_disabled") != target:
                    self._set_mpo_disabled(target)
                    requires_reboot = True  # Actually changed MPO state
                    changed_keys.append("disable_mpo")
                    notices.append(
                        "MPO registry state changed; reboot before judging display "
                        "flicker because the live compositor path is boot-gated."
                    )

            if "disable_global_fso" in settings:
                target_disabled = bool(settings["disable_global_fso"])
                target_behavior = 2 if target_disabled else 0
                if current.get("global_fso_disabled") != target_disabled:
                    self._set_global_fso_disabled(target_disabled)
                    changed_keys.append("disable_global_fso")
                    current["global_fso_disabled"] = target_disabled
                    current["game_dvr_behavior"] = target_behavior

            if "game_dvr_behavior" in settings:
                target_behavior = int(settings["game_dvr_behavior"])
                if current.get("game_dvr_behavior") != target_behavior:
                    self._set_game_dvr_behavior(target_behavior)
                    changed_keys.append("game_dvr_behavior")
                    current["game_dvr_behavior"] = target_behavior
                    current["global_fso_disabled"] = target_behavior == 2

            if "disable_auto_color_management" in settings:
                # ACM = Windows 11 24H2+ Auto Color Management. When it turns
                # on for a wide-gamut display (OLED/Mini-LED/DCI-P3), Windows
                # clamps SDR content to sRGB gamut system-wide, which on
                # panels previously used un-clamped produces a washed-out /
                # desaturated look. Windows updates and display re-enumeration
                # (e.g. after NVIDIA driver installs) can silently re-enable
                # it, so gaming profiles re-assert this on every apply.
                disable = bool(settings["disable_auto_color_management"])
                target_enabled = not disable
                if not self._auto_color_management_matches(
                    current.get("auto_color_management"),
                    target_enabled,
                ):
                    acm_result = self._set_auto_color_management(target_enabled)
                    if int(acm_result.get("applied_count", 0) or 0) > 0:
                        changed_keys.append("disable_auto_color_management")
                    if acm_result.get("errors"):
                        for err in acm_result["errors"]:
                            errors.append(f"ACM: {err}")

        except PermissionError as e:
            errors.append(f"Permission denied: {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": requires_reboot,
            "notices": notices,
            "changed": bool(changed_keys),
            "changed_keys": changed_keys,
        }

    def verify_active(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Verify that reboot-requiring settings are already active.

        Use this to check if the MPO registry target is written. Windows'
        live compositor MPO state is boot-gated, so this verifier can prove
        the requested registry target exists, but it cannot prove the live
        DWM path has consumed that target until after a reboot.

        Returns:
            Dict with 'all_active' bool and details for each setting.
        """
        current = self.detect()
        results = {"all_active": True, "settings": {}}

        if "disable_mpo" in settings:
            target = settings["disable_mpo"]
            is_active = current.get("mpo_disabled") == target
            # Determine whether a reboot is still pending so we can caveat the
            # "registry written" state with "but compositor commit not yet live".
            # The reboot_pending bit in settings (threaded from the caller, e.g.
            # the applier) is the authoritative signal. Fall back to reading the
            # LocalAppData state file directly when nothing was threaded in.
            reboot_pending: bool
            if "_reboot_pending" in settings:
                reboot_pending = bool(settings.get("_reboot_pending"))
            else:
                try:
                    from abso.core.app_paths import app_state_file
                    from abso.core.state_store import read_state_snapshot

                    state_snapshot = read_state_snapshot([app_state_file()])
                    reboot_pending = bool(state_snapshot.get("reboot_pending", False))
                except Exception:  # noqa: BLE001 — state read must never break verify
                    reboot_pending = False

            results["settings"]["mpo_disabled"] = {
                "target": target,
                "current": current.get("mpo_disabled"),
                "active": is_active,
                "reboot_gated": True,
                "activation": "after_reboot",
                "registry_target_written": is_active,
                "live_activation_verifiable": False,
                "live_commit_pending": bool(is_active and reboot_pending),
                "next_action": (
                    "reboot_to_commit_live_compositor"
                    if is_active and reboot_pending
                    else (
                        "no_action_required"
                        if is_active
                        else "run_elevated_apply_to_write_registry"
                    )
                ),
                "note": (
                    "This verifies the MPO registry target only. If current does "
                    "not equal target, the registry mitigation has not been "
                    "written yet and an elevated apply is still required. After "
                    "the registry target is written, Windows applies the live "
                    "compositor path only after reboot."
                ),
            }
            if not is_active:
                results.setdefault("pending_apply_settings", []).append("mpo_disabled")
                results["all_active"] = False
            elif reboot_pending:
                # Registry target is written but live compositor commit is reboot-gated
                # and the system state still says a reboot is pending. Surface this so
                # the CLI/tray/state command renders the pending-reboot caveat instead
                # of falsely reporting the setting as fully active.
                results.setdefault("pending_reboot_gated_settings", []).append("mpo_disabled")
                results["all_active"] = False

        return results

    def backup(self) -> dict[str, Any]:
        """Backup current graphics settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore graphics settings from backup."""
        try:
            if "mpo_disabled" in data:
                self._set_mpo_disabled(data["mpo_disabled"])
            if "game_dvr_behavior" in data and data["game_dvr_behavior"] is not None:
                self._set_game_dvr_behavior(data["game_dvr_behavior"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore graphics settings: {e}")
            return False

    # Private helper methods

    def _get_mpo_disabled(self) -> bool:
        """Check if Multi-Plane Overlay is disabled.

        Windows 11 24H2+ uses DisableOverlays under GraphicsDrivers.
        Falls back to the legacy OverlayTestMode under DWM for pre-24H2.
        """
        # Check new 24H2+ key first
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.GRAPHICS_DRIVERS_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                value = winreg.QueryValueEx(key, "DisableOverlays")[0]
                if value in (0, 1):
                    return value == 1
            except FileNotFoundError:
                pass  # Key doesn't exist, check legacy
            finally:
                winreg.CloseKey(key)
        except Exception:
            pass

        # Fallback: legacy DWM key (pre-24H2)
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.DWM_LEGACY_KEY,
                0,
                winreg.KEY_READ,
            )
            try:
                value = winreg.QueryValueEx(key, "OverlayTestMode")[0]
                return value == 5
            except FileNotFoundError:
                return False
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get MPO status: {e}")
            return False

    def _set_mpo_disabled(self, disabled: bool) -> None:
        """Enable or disable Multi-Plane Overlay.

        Sets BOTH the new 24H2+ key (DisableOverlays) and the legacy DWM
        key (OverlayTestMode) for compatibility across Windows versions.
        The 24H2+ GraphicsDrivers key is authoritative; failure there must
        bubble up so an apply cannot claim the MPO mitigation was written.
        """
        # Set new 24H2+ key: GraphicsDrivers\DisableOverlays
        key = None
        try:
            try:
                key = winreg.OpenKey(
                    winreg.HKEY_LOCAL_MACHINE,
                    self.GRAPHICS_DRIVERS_KEY,
                    0,
                    winreg.KEY_ALL_ACCESS,
                )
            except FileNotFoundError:
                key = winreg.CreateKeyEx(
                    winreg.HKEY_LOCAL_MACHINE,
                    self.GRAPHICS_DRIVERS_KEY,
                    0,
                    winreg.KEY_ALL_ACCESS,
                )

            try:
                if disabled:
                    winreg.SetValueEx(key, "DisableOverlays", 0, winreg.REG_DWORD, 1)
                else:
                    with contextlib.suppress(FileNotFoundError):
                        winreg.DeleteValue(key, "DisableOverlays")
            finally:
                if key is not None:
                    winreg.CloseKey(key)
        except PermissionError as e:
            raise PermissionError(
                "Permission denied setting DisableOverlays (requires admin)"
            ) from e
        except OSError as e:
            raise OSError(f"Failed to set DisableOverlays: {e}") from e

        # Also set legacy DWM key for pre-24H2 compatibility
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.DWM_LEGACY_KEY,
                0,
                winreg.KEY_ALL_ACCESS,
            )
            try:
                if disabled:
                    winreg.SetValueEx(key, "OverlayTestMode", 0, winreg.REG_DWORD, 5)
                else:
                    with contextlib.suppress(FileNotFoundError):
                        winreg.DeleteValue(key, "OverlayTestMode")
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Legacy DWM MPO key: {e}")

    def _get_global_fso_disabled(self) -> bool:
        """Check if global Fullscreen Optimizations are disabled."""
        behavior = self._get_game_dvr_behavior()
        # GameDVR_FSEBehavior = 2 means FSO disabled globally
        return behavior == 2

    def _get_game_dvr_behavior(self) -> int | None:
        """Get GameDVR Fullscreen Exclusive behavior.

        Values:
        0 = Default (FSO enabled)
        1 = FSO enabled
        2 = FSO disabled (true exclusive fullscreen)
        """
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.GAME_CONFIG_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, "GameDVR_FSEBehavior")[0]
                return value
            except FileNotFoundError:
                return 0  # Default
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get GameDVR_FSEBehavior: {e}")
            return None

    def _set_game_dvr_behavior(self, value: int) -> None:
        """Set GameDVR Fullscreen Exclusive behavior."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.GAME_CONFIG_KEY, 0, winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.GAME_CONFIG_KEY)

        try:
            winreg.SetValueEx(key, "GameDVR_FSEBehavior", 0, winreg.REG_DWORD, value)
        finally:
            winreg.CloseKey(key)

    def _set_global_fso_disabled(self, disabled: bool) -> None:
        """Enable or disable global Fullscreen Optimizations."""
        self._set_game_dvr_behavior(2 if disabled else 0)

    def _get_hardware_cursor(self) -> bool | None:
        """Check if hardware cursor is enabled (vs software cursor)."""
        # Hardware cursor is default and generally preferred
        # This is mostly informational
        try:
            # Check for software cursor override
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.EXPLORER_ADVANCED_KEY, 0, winreg.KEY_READ
            )
            try:
                # If DisableHardwareCursor exists and is 1, hardware cursor is off
                value = winreg.QueryValueEx(key, "DisableHardwareCursor")[0]
                return value != 1
            except FileNotFoundError:
                return True  # Default = hardware cursor enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get hardware cursor status: {e}")
            return None

    def _get_auto_color_management(self) -> dict[str, Any]:
        """Check Auto Color Management (ACM) status.

        ACM is a Windows 11 feature that applies color profiles automatically.
        For gaming, ACM adds processing overhead and should generally be disabled.

        Returns:
            Dict with 'global' (bool or None) and 'per_monitor' (dict of monitor_id: bool)
        """
        result: dict[str, Any] = {
            "global": None,
            "per_monitor": {},
        }

        # Check global ACM setting (HKCU)
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER, self.COLOR_MANAGEMENT_KEY, 0, winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "AutoColorManagement")[0]
                result["global"] = value != 0
            except FileNotFoundError:
                result["global"] = None  # Not set
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get global ACM status: {e}")

        # Check per-monitor ACM settings
        try:
            key = winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE, self.MONITOR_DATA_STORE_KEY, 0, winreg.KEY_READ
            )
            try:
                # Enumerate all monitor subkeys
                i = 0
                while True:
                    try:
                        monitor_id = winreg.EnumKey(key, i)
                        i += 1
                        # Check this monitor's ACM setting
                        try:
                            monitor_key = winreg.OpenKey(key, monitor_id, 0, winreg.KEY_READ)
                            try:
                                value = winreg.QueryValueEx(
                                    monitor_key, "AutoColorManagementEnabled"
                                )[0]
                                result["per_monitor"][monitor_id] = value != 0
                            except FileNotFoundError:
                                # Not set = disabled by default
                                result["per_monitor"][monitor_id] = False
                            finally:
                                winreg.CloseKey(monitor_key)
                        except Exception as e:
                            logger.debug(f"Failed to read ACM for monitor {monitor_id}: {e}")
                    except OSError:
                        break  # No more subkeys
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to enumerate monitors for ACM: {e}")

        return result

    @staticmethod
    def _auto_color_management_matches(
        state: dict[str, Any] | None,
        enabled: bool,
    ) -> bool:
        """Return True when global/per-monitor ACM state is known and matches."""
        if not isinstance(state, dict):
            return False

        saw_known_value = False
        global_value = state.get("global")
        if global_value is not None:
            saw_known_value = True
            if bool(global_value) != bool(enabled):
                return False

        per_monitor = state.get("per_monitor")
        if isinstance(per_monitor, dict) and per_monitor:
            saw_known_value = True
            if any(bool(value) != bool(enabled) for value in per_monitor.values()):
                return False

        return saw_known_value

    def _set_auto_color_management(self, enabled: bool) -> dict[str, Any]:
        """Set Auto Color Management on/off for every enumerated monitor.

        Writes:
            HKLM\\...\\MonitorDataStore\\{monitor_id}\\AutoColorManagementEnabled
                (per-monitor, authoritative)
            HKCU\\...\\ColorManagement\\AutoColorManagement
                (user-scope global, lower precedence)

        Both get the same value (1 when enabled, 0 when disabled). The
        per-monitor keys are what Windows' desktop compositor actually
        reads; the global HKCU key is a user-preference fallback that
        Windows uses when no per-monitor setting exists yet. We write both
        so a future display re-enumeration can't silently default back on.

        Returns dict with applied_count / skipped_count / errors so the
        caller can log and surface partial failures without flipping
        overall handler success.
        """
        value = 1 if enabled else 0
        result: dict[str, Any] = {
            "success": True,
            "applied_count": 0,
            "skipped_count": 0,
            "errors": [],
        }

        # Per-monitor: iterate MonitorDataStore and write into each subkey.
        try:
            with winreg.OpenKey(
                winreg.HKEY_LOCAL_MACHINE,
                self.MONITOR_DATA_STORE_KEY,
                0,
                winreg.KEY_READ,
            ) as root:
                monitor_ids: list[str] = []
                i = 0
                while True:
                    try:
                        monitor_ids.append(winreg.EnumKey(root, i))
                        i += 1
                    except OSError:
                        break

            for monitor_id in monitor_ids:
                sub_path = f"{self.MONITOR_DATA_STORE_KEY}\\{monitor_id}"
                try:
                    with winreg.OpenKey(
                        winreg.HKEY_LOCAL_MACHINE,
                        sub_path,
                        0,
                        winreg.KEY_ALL_ACCESS,
                    ) as sub:
                        # Read current value so we don't noisily rewrite.
                        try:
                            current = winreg.QueryValueEx(sub, "AutoColorManagementEnabled")[0]
                        except FileNotFoundError:
                            current = None
                        if current == value:
                            result["skipped_count"] += 1
                            continue
                        winreg.SetValueEx(
                            sub,
                            "AutoColorManagementEnabled",
                            0,
                            winreg.REG_DWORD,
                            value,
                        )
                        result["applied_count"] += 1
                        logger.info(
                            "ACM set to %d for monitor %s (was %s)",
                            value,
                            monitor_id,
                            current,
                        )
                except PermissionError as e:
                    result["errors"].append(f"{monitor_id}: permission denied ({e})")
                    result["success"] = False
                except Exception as e:
                    # Partial failures on individual monitors are recorded
                    # but don't fail the whole operation — ACM is best-effort
                    # across monitors, and anti-cheat style per-path quirks
                    # can block specific subkeys on some systems.
                    result["errors"].append(f"{monitor_id}: {e}")
        except Exception as e:
            # Enumeration itself failed — MonitorDataStore missing or locked.
            result["errors"].append(f"Enumerate monitors: {e}")
            result["success"] = False

        # Global HKCU: write the user-scope fallback too.
        try:
            with winreg.CreateKeyEx(
                winreg.HKEY_CURRENT_USER,
                self.COLOR_MANAGEMENT_KEY,
                0,
                winreg.KEY_ALL_ACCESS,
            ) as key:
                winreg.SetValueEx(key, "AutoColorManagement", 0, winreg.REG_DWORD, value)
        except Exception as e:
            # HKCU write failing is non-fatal if the per-monitor writes
            # succeeded — those are authoritative.
            result["errors"].append(f"HKCU global: {e}")

        return result
