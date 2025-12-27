"""Visual effects settings handler."""

from __future__ import annotations

import logging
import winreg
from typing import Any

from gametune.settings.base import SettingsHandler
from gametune.core.models import Issue

logger = logging.getLogger(__name__)


class VisualSettingsHandler(SettingsHandler):
    """Handles Windows visual effects optimization settings.

    Manages:
    - Window animations
    - Transparency effects
    - Shadow effects
    - Visual effects profile (performance vs appearance)

    Registry paths:
    - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Explorer\\VisualEffects
    - HKCU\\Control Panel\\Desktop\\WindowMetrics
    - HKCU\\Software\\Microsoft\\Windows\\CurrentVersion\\Themes\\Personalize

    Note: Disabling visual effects has minimal performance impact on modern systems
    but can reduce DWM overhead and memory usage slightly.
    """

    # Registry paths
    VISUAL_EFFECTS_KEY = r"Software\Microsoft\Windows\CurrentVersion\Explorer\VisualEffects"
    DESKTOP_KEY = r"Control Panel\Desktop"
    WINDOW_METRICS_KEY = r"Control Panel\Desktop\WindowMetrics"
    PERSONALIZE_KEY = r"Software\Microsoft\Windows\CurrentVersion\Themes\Personalize"
    DWMAPI_KEY = r"Software\Microsoft\Windows\DWM"

    # Visual effects flags (UserPreferencesMask)
    # These are bit flags in a REG_BINARY value
    EFFECTS = {
        "animations": "Animate windows and controls",
        "smooth_scrolling": "Smooth-scroll list boxes",
        "font_smoothing": "ClearType font smoothing",
        "drop_shadows": "Drop shadows under windows",
        "thumbnail_previews": "Show window previews in taskbar",
    }

    def detect(self) -> dict[str, Any]:
        """Detect current visual effects settings."""
        return {
            "visual_fx_setting": self._get_visual_fx_setting(),
            "transparency": self._get_transparency_enabled(),
            "animations": self._get_animations_enabled(),
            "menu_animation": self._get_menu_animation(),
        }

    def audit(self) -> list[Issue]:
        """Audit visual effects settings for gaming optimization issues."""
        issues: list[Issue] = []
        current = self.detect()

        # Check transparency
        if current.get("transparency"):
            issues.append(Issue(
                title="Transparency effects are enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation=(
                    "Transparency effects use GPU compositing. Disabling saves a small "
                    "amount of GPU overhead. Impact is minimal on modern systems."
                ),
                category="visual",
            ))

        # Check animations
        if current.get("animations"):
            issues.append(Issue(
                title="Window animations are enabled",
                severity="info",
                current_value="Enabled",
                optimal_value="Disabled",
                explanation=(
                    "Window animations add latency when opening/closing windows. "
                    "Disabling makes the UI feel more responsive."
                ),
                category="visual",
            ))

        return issues

    def apply(self, settings: dict[str, Any]) -> dict[str, Any]:
        """Apply visual effects settings.

        Settings format:
        {
            "disable_transparency": True,
            "disable_animations": True,
        }

        Or use preset:
        {
            "preset": "performance"  # Disables all effects for max performance
        }
        """
        errors: list[str] = []

        try:
            if settings.get("preset") == "performance":
                self._set_transparency_enabled(False)
                self._set_animations_enabled(False)
                self._set_menu_animation(False)

            else:
                if "disable_transparency" in settings:
                    self._set_transparency_enabled(not settings["disable_transparency"])

                if "disable_animations" in settings:
                    self._set_animations_enabled(not settings["disable_animations"])

        except Exception as e:
            errors.append(str(e))

        return {
            "success": len(errors) == 0,
            "error": "; ".join(errors) if errors else None,
            "requires_reboot": False,  # Changes apply immediately
        }

    def backup(self) -> dict[str, Any]:
        """Backup current visual effects settings."""
        return self.detect()

    def restore(self, data: dict[str, Any]) -> bool:
        """Restore visual effects settings from backup."""
        try:
            if "transparency" in data:
                self._set_transparency_enabled(data["transparency"])
            if "animations" in data:
                self._set_animations_enabled(data["animations"])
            if "menu_animation" in data:
                self._set_menu_animation(data["menu_animation"])
            return True
        except Exception as e:
            logger.error(f"Failed to restore visual effects settings: {e}")
            return False

    # Private helper methods

    def _get_visual_fx_setting(self) -> str | None:
        """Get the overall visual effects setting.

        Returns: 'best_appearance', 'best_performance', 'custom', or None
        """
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.VISUAL_EFFECTS_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "VisualFXSetting")[0]
                return {0: "best_appearance", 1: "best_performance", 2: "custom"}.get(value)
            except FileNotFoundError:
                return None
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get VisualFXSetting: {e}")
            return None

    def _get_transparency_enabled(self) -> bool | None:
        """Check if transparency effects are enabled."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.PERSONALIZE_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "EnableTransparency")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get transparency setting: {e}")
            return None

    def _set_transparency_enabled(self, enabled: bool) -> None:
        """Enable or disable transparency effects."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.PERSONALIZE_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.PERSONALIZE_KEY)

        try:
            winreg.SetValueEx(key, "EnableTransparency", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

    def _get_animations_enabled(self) -> bool | None:
        """Check if window animations are enabled."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.DWMAPI_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                # EnableAeroPeek controls several animation effects
                value = winreg.QueryValueEx(key, "EnableAeroPeek")[0]
                return bool(value)
            except FileNotFoundError:
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get animation setting: {e}")
            return None

    def _set_animations_enabled(self, enabled: bool) -> None:
        """Enable or disable window animations."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.DWMAPI_KEY,
                0,
                winreg.KEY_ALL_ACCESS
            )
        except FileNotFoundError:
            key = winreg.CreateKey(winreg.HKEY_CURRENT_USER, self.DWMAPI_KEY)

        try:
            winreg.SetValueEx(key, "EnableAeroPeek", 0, winreg.REG_DWORD, 1 if enabled else 0)
        finally:
            winreg.CloseKey(key)

        # Also update SystemParametersInfo for immediate effect
        try:
            import ctypes
            # SPI_SETCLIENTAREAANIMATION = 0x1043
            ctypes.windll.user32.SystemParametersInfoW(0x1043, 0, 1 if enabled else 0, 0x03)
        except Exception as e:
            logger.debug(f"Failed to update animation via SPI: {e}")

    def _get_menu_animation(self) -> bool | None:
        """Check if menu animation is enabled."""
        try:
            key = winreg.OpenKey(
                winreg.HKEY_CURRENT_USER,
                self.DESKTOP_KEY,
                0,
                winreg.KEY_READ
            )
            try:
                value = winreg.QueryValueEx(key, "MenuShowDelay")[0]
                # Default is 400ms, 0 means no delay/animation
                return int(value) > 0
            except (FileNotFoundError, ValueError):
                return True  # Default is enabled
            finally:
                winreg.CloseKey(key)
        except Exception as e:
            logger.debug(f"Failed to get menu animation setting: {e}")
            return None

    def _set_menu_animation(self, enabled: bool) -> None:
        """Enable or disable menu animation."""
        key = winreg.OpenKey(
            winreg.HKEY_CURRENT_USER,
            self.DESKTOP_KEY,
            0,
            winreg.KEY_ALL_ACCESS
        )
        try:
            # 400 = default delay, 0 = no delay
            delay = "400" if enabled else "0"
            winreg.SetValueEx(key, "MenuShowDelay", 0, winreg.REG_SZ, delay)
        finally:
            winreg.CloseKey(key)
