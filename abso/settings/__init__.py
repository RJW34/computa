"""Settings handler modules."""

from abso.settings.base import SettingsHandler
from abso.settings.cnm import CNMSettingsHandler
from abso.settings.network import NetworkSettingsHandler
from abso.settings.nvidia import NvidiaSettingsHandler
from abso.settings.obs import OBSSettingsHandler
from abso.settings.power import PowerSettingsHandler
from abso.settings.registry import RegistrySettingsHandler
from abso.settings.timer import TimerSettingsHandler
from abso.settings.windows import WindowsSettingsHandler

__all__ = [
    "SettingsHandler",
    "WindowsSettingsHandler",
    "PowerSettingsHandler",
    "RegistrySettingsHandler",
    "NvidiaSettingsHandler",
    "NetworkSettingsHandler",
    "TimerSettingsHandler",
    "CNMSettingsHandler",
    "OBSSettingsHandler",
]
