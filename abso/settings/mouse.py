"""Mouse and input settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from abso.settings.base import SettingsHandler
from abso.core.models import Issue

logger = logging.getLogger(__name__)


class MouseSettingsHandler(SettingsHandler):
    """Handles mouse and input optimization settings.

    Manages:
    - Mouse acceleration (Enhanced Pointer Precision)
    - Mouse sensitivity curves
    - Raw input settings

    Technical notes:
    - MouseSpeed: 0 = acceleration off, 1 = acceleration on, 2 = double acceleration
    - MouseThreshold1/2: Acceleration thresholds (0,0 = disabled)
    - SmoothMouseXCurve/YCurve: 5 points defining acceleration curve
      - Linear (1:1) curve is optimal for gaming
      - Default Windows curve applies acceleration
    """

    # Registry paths
    MOUSE_KEY = r"Control Panel\Mouse"

    # Linear (1:1) mouse curves - no acceleration
    # These are the raw bytes for a perfectly linear response
    LINEAR_X_CURVE = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 1: 0
        0x00, 0xa0, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 2: 40960
        0x00, 0x40, 0x01, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 3: 81920
        0x00, 0x80, 0x02, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 4: 163840
        0x00, 0x00, 0x05, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 5: 327680
    ])

    LINEAR_Y_CURVE = bytes([
        0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 1: 0
        0x00, 0x00, 0x38, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 2: 14336
        0x00, 0x00, 0x70, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 3: 28672
        0x00, 0x00, 0xa0, 0x00, 0x00, 0x00, 0x00, 0x00,  # Point 4: 40960
        0x00, 0x00, 0x40, 0x01, 0x00, 0x00, 0x00, 0x00,  # Point 5: 81920
    ])

    def detect(self) -> dict[str, Any]:
        """Detect current mouse settings."""
        return {
            "mouse_speed": self._get_mouse_speed(),
            "mouse_threshold1": self._get_mouse_threshold(1),
            "mouse_threshold2": self._get_mouse_threshold(2),
            "enhanced_pointer_precision": self._get_enhanced_pointer_precision(),
            "smooth_mouse_x_curve": self._get_smooth_curve("SmoothMouseXCurve"),
            "smooth_mouse_y_curve": self._get_smooth_curve("SmoothMouseYCurve"),
            "is_acceleration_disabled": self._is_acceleration_disabled(),
        }

    def audit(self) -> list[Issue]:
        """Audit mouse settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check if acceleration is enabled
        if not current.get("is_acceleration_disabled"):
            # Determine what's causing acceleration
            details = []
            if current.get("mouse_speed", 0) != 0:
                details.append(f"MouseSpeed={current.get('mouse_speed')}")
            if current.get("mouse_threshold1", 0) != 0:
                details.append(f"Threshold1={current.get('mouse_threshold1')}")
            if current.get("mouse_threshold2", 0) != 0:
                details.append(f"Threshold2={current.get('mouse_threshold2')}")
            if current.get("enhanced_pointer_precision"):
                details.append("Enhanced Pointer Precision enabled")

            issues.append(Issue(
                title="Mouse acceleration is enabled",
                severity="warning",
                current_value=", ".join(details) if details else "Acceleration detected",
                optimal_value="All acceleration disabled (1:1 raw input)",
                explanation=(
                    "Mouse acceleration changes cursor speed based on how fast you move the mouse. "
                    "This makes muscle memory inconsistent. Disable for precise aiming in FPS games."
                ),
                category="mouse",
            ))

        # Check for non-linear curves even if other settings are correct
        if not self._is_curve_linear(current.get("smooth_mouse_x_curve")):
            issues.append(Issue(
                title="Mouse X curve is not linear",
                severity="info",
                current_value="Non-linear curve",
                optimal_value="Linear (1:1) curve",
                explanation=(
                    "Windows applies a curve to mouse input that can affect precision. "
                    "A linear curve ensures consistent 1:1 input translation."
                ),
                category="mouse",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply mouse optimization settings."""
        errors: list[str] = []

        try:
            if settings.get("disable_acceleration", False):
                self._disable_acceleration()

            if settings.get("set_linear_curve", False):
                self._set_linear_curves()

            if "mouse_speed" in settings:
                self._set_mouse_speed(settings["mouse_speed"])

            if "mouse_sensitivity" in settings:
                self._set_mouse_sensitivity(settings["mouse_sensitivity"])

        except PermissionError as e:
            errors.append(f"Permission denied: {e}")
        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,  # Mouse changes apply immediately
        }

    def backup(self) -> dict[str, Any]:
        """Backup current mouse settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore mouse settings from backup."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.MOUSE_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
            try:
                if "mouse_speed" in data and data["mouse_speed"] is not None:
                    winreg.SetValueEx(key, "MouseSpeed", 0, winreg.REG_SZ, str(data["mouse_speed"]))
                if "mouse_threshold1" in data and data["mouse_threshold1"] is not None:
                    winreg.SetValueEx(key, "MouseThreshold1", 0, winreg.REG_SZ, str(data["mouse_threshold1"]))
                if "mouse_threshold2" in data and data["mouse_threshold2"] is not None:
                    winreg.SetValueEx(key, "MouseThreshold2", 0, winreg.REG_SZ, str(data["mouse_threshold2"]))
                if "smooth_mouse_x_curve" in data and data["smooth_mouse_x_curve"] is not None:
                    winreg.SetValueEx(key, "SmoothMouseXCurve", 0, winreg.REG_BINARY, bytes(data["smooth_mouse_x_curve"]))
                if "smooth_mouse_y_curve" in data and data["smooth_mouse_y_curve"] is not None:
                    winreg.SetValueEx(key, "SmoothMouseYCurve", 0, winreg.REG_BINARY, bytes(data["smooth_mouse_y_curve"]))
            finally:
                winreg.CloseKey(key)

            # Apply changes immediately
            self._notify_settings_change()
            return True

        except Exception as e:
            logger.error(f"Failed to restore mouse settings: {e}")
            return False

    # Private helper methods

    def _get_mouse_speed(self) -> int | None:
        """Get MouseSpeed value (0=off, 1=on, 2=double)."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.MOUSE_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, "MouseSpeed")[0]
                return int(value)
            except (FileNotFoundError, ValueError):
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get MouseSpeed: {e}")
            return None

    def _get_mouse_threshold(self, threshold_num: int) -> int | None:
        """Get MouseThreshold1 or MouseThreshold2 value."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.MOUSE_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, f"MouseThreshold{threshold_num}")[0]
                return int(value)
            except (FileNotFoundError, ValueError):
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get MouseThreshold{threshold_num}: {e}")
            return None

    def _get_enhanced_pointer_precision(self) -> bool:
        """Check if Enhanced Pointer Precision is enabled."""
        # EPP is enabled when MouseSpeed=1 and thresholds are set
        speed = self._get_mouse_speed()
        thresh1 = self._get_mouse_threshold(1)
        thresh2 = self._get_mouse_threshold(2)

        # EPP is enabled if speed >= 1 and thresholds are non-zero
        if speed is not None and speed >= 1:
            if (thresh1 is not None and thresh1 > 0) or (thresh2 is not None and thresh2 > 0):
                return True
        return False

    def _get_smooth_curve(self, curve_name: str) -> list[int] | None:
        """Get SmoothMouseXCurve or SmoothMouseYCurve as list of bytes."""
        try:
            key = winreg.OpenKey(winreg.HKEY_CURRENT_USER, self.MOUSE_KEY, 0, winreg.KEY_READ)
            try:
                value = winreg.QueryValueEx(key, curve_name)[0]
                return list(value) if value else None
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get {curve_name}: {e}")
            return None

    def _is_acceleration_disabled(self) -> bool:
        """Check if all mouse acceleration is disabled."""
        speed = self._get_mouse_speed()
        thresh1 = self._get_mouse_threshold(1)
        thresh2 = self._get_mouse_threshold(2)

        # Acceleration is disabled when:
        # - MouseSpeed = 0 (completely off), OR
        # - MouseSpeed = 1 but both thresholds are 0
        if speed == 0:
            return True
        if speed == 1 and thresh1 == 0 and thresh2 == 0:
            return True
        return False

    def _is_curve_linear(self, curve: list[int] | None) -> bool:
        """Check if a curve is linear (matches our linear curve)."""
        if curve is None:
            return False
        return bytes(curve) == self.LINEAR_X_CURVE or bytes(curve) == self.LINEAR_Y_CURVE

    def _set_mouse_speed(self, speed: int) -> None:
        """Set MouseSpeed value."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.MOUSE_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "MouseSpeed", 0, winreg.REG_SZ, str(speed))
        finally:
            winreg.CloseKey(key)

    def _set_mouse_sensitivity(self, sensitivity: int) -> None:
        """Set mouse sensitivity (pointer speed slider, 1-20)."""
        # Sensitivity is stored in MouseSensitivity
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.MOUSE_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            # Clamp to valid range
            sensitivity = max(1, min(20, sensitivity))
            winreg.SetValueEx(key, "MouseSensitivity", 0, winreg.REG_SZ, str(sensitivity))
        finally:
            winreg.CloseKey(key)

    def _disable_acceleration(self) -> None:
        """Disable all mouse acceleration."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.MOUSE_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            # Set MouseSpeed to 0 (disable acceleration)
            winreg.SetValueEx(key, "MouseSpeed", 0, winreg.REG_SZ, "0")
            # Set thresholds to 0 (no acceleration thresholds)
            winreg.SetValueEx(key, "MouseThreshold1", 0, winreg.REG_SZ, "0")
            winreg.SetValueEx(key, "MouseThreshold2", 0, winreg.REG_SZ, "0")
        finally:
            winreg.CloseKey(key)

        # Apply changes immediately
        self._notify_settings_change()

    def _set_linear_curves(self) -> None:
        """Set mouse curves to linear (1:1 input)."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.MOUSE_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            winreg.SetValueEx(key, "SmoothMouseXCurve", 0, winreg.REG_BINARY, self.LINEAR_X_CURVE)
            winreg.SetValueEx(key, "SmoothMouseYCurve", 0, winreg.REG_BINARY, self.LINEAR_Y_CURVE)
        finally:
            winreg.CloseKey(key)

        # Apply changes immediately
        self._notify_settings_change()

    def _notify_settings_change(self) -> None:
        """Notify Windows that mouse settings have changed."""
        try:
            import ctypes
            # SPI_SETMOUSE = 0x0004
            # SPIF_UPDATEINIFILE | SPIF_SENDCHANGE = 0x03
            ctypes.windll.user32.SystemParametersInfoW(0x0004, 0, None, 0x03)
        except Exception as e:
            logger.debug(f"Failed to notify settings change: {e}")
