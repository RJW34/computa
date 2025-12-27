"""Settings handler modules."""

from gametune.settings.base import SettingsHandler
from gametune.settings.windows import WindowsSettingsHandler
from gametune.settings.power import PowerSettingsHandler
from gametune.settings.registry import RegistrySettingsHandler
from gametune.settings.nvidia import NvidiaSettingsHandler
from gametune.settings.network import NetworkSettingsHandler
from gametune.settings.timer import TimerSettingsHandler

__all__ = [
    "SettingsHandler",
    "WindowsSettingsHandler",
    "PowerSettingsHandler",
    "RegistrySettingsHandler",
    "NvidiaSettingsHandler",
    "NetworkSettingsHandler",
    "TimerSettingsHandler",
]
