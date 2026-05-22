"""Settings handler package.

Keep this initializer lightweight. Eagerly importing concrete handlers here
creates circular imports when profile catalog modules import individual
settings submodules during startup.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

MONITOR_DATA_STORE_KEY = r"SYSTEM\CurrentControlSet\Control\GraphicsDrivers\MonitorDataStore"

_LAZY_EXPORTS = {
    "SettingsHandler": ("abso.settings.base", "SettingsHandler"),
    "WindowsSettingsHandler": ("abso.settings.windows", "WindowsSettingsHandler"),
    "PowerSettingsHandler": ("abso.settings.power", "PowerSettingsHandler"),
    "RegistrySettingsHandler": ("abso.settings.registry", "RegistrySettingsHandler"),
    "NvidiaSettingsHandler": ("abso.settings.nvidia", "NvidiaSettingsHandler"),
    "NetworkSettingsHandler": ("abso.settings.network", "NetworkSettingsHandler"),
    "Diablo4ConfigHandler": ("abso.settings.diablo4_config", "Diablo4ConfigHandler"),
    "TimerSettingsHandler": ("abso.settings.timer", "TimerSettingsHandler"),
    "CNMSettingsHandler": ("abso.settings.cnm", "CNMSettingsHandler"),
    "OBSSettingsHandler": ("abso.settings.obs", "OBSSettingsHandler"),
}


def __getattr__(name: str) -> Any:
    """Lazily expose common handler classes for compatibility."""
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = [
    "MONITOR_DATA_STORE_KEY",
    *_LAZY_EXPORTS.keys(),
]
