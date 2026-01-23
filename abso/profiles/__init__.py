"""Game optimization profiles."""

from abso.profiles.base import BaseProfile
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.cod_bo7_oled import CodBo7OLEDProfile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.diablo4_oled import Diablo4OLEDProfile
from abso.profiles.diablo4_oled_vrr import Diablo4OLEDVRRProfile
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pacdeluxe_oled import PACDeluxeOLEDProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.pokemon_auto_chess_oled import PokemonAutoChessOLEDProfile
from abso.profiles.productivity_oled import ProductivityOLEDProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_offline import Rivals2OfflineProfile
from abso.profiles.rivals2_oled import Rivals2OLEDProfile
from abso.profiles.rivals2_oled_vrr import Rivals2OLEDVRRProfile
from abso.profiles.rivals2_oled_vrr_multimon import Rivals2OLEDVRRMultiMonProfile
from abso.profiles.rivals2_online import Rivals2OnlineProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.ryujinx_ssbu_oled import RyujinxSSBUOLEDProfile
from abso.profiles.ryujinx_ssbu_vrr import RyujinxSSBUVRRProfile
from abso.profiles.slippi_melee import SlippiMeleeProfile
from abso.profiles.slippi_melee_oled import SlippiMeleeOLEDProfile

__all__ = [
    "BaseProfile",
    "SlippiMeleeProfile",
    "SlippiMeleeOLEDProfile",
    "Rivals2Profile",
    "Rivals2OfflineProfile",
    "Rivals2OnlineProfile",
    "Rivals2OLEDProfile",
    "Rivals2OLEDVRRProfile",
    "Rivals2OLEDVRRMultiMonProfile",
    "CodBo7Profile",
    "CodBo7OLEDProfile",
    "Diablo4Profile",
    "Diablo4OLEDProfile",
    "Diablo4OLEDVRRProfile",
    "PokemonAutoChessProfile",
    "PokemonAutoChessOLEDProfile",
    "PACDeluxeProfile",
    "PACDeluxeOLEDProfile",
    "ProductivityOLEDProfile",
    "RyujinxSSBUProfile",
    "RyujinxSSBUOLEDProfile",
    "RyujinxSSBUVRRProfile",
    "get_all_profiles",
]


def get_all_profiles() -> dict[str, BaseProfile]:
    """Get all available game profiles.

    Returns:
        Dictionary mapping profile ID to profile instance.
    """
    return {
        "slippi-melee": SlippiMeleeProfile(),
        "slippi-melee-oled": SlippiMeleeOLEDProfile(),
        "rivals2": Rivals2Profile(),
        "rivals2-offline": Rivals2OfflineProfile(),
        "rivals2-online": Rivals2OnlineProfile(),
        "rivals2-oled": Rivals2OLEDProfile(),
        "rivals2-oled-vrr": Rivals2OLEDVRRProfile(),
        "rivals2-oled-vrr-multimon": Rivals2OLEDVRRMultiMonProfile(),
        "cod-bo7": CodBo7Profile(),
        "cod-bo7-oled": CodBo7OLEDProfile(),
        "diablo4": Diablo4Profile(),
        "diablo4-oled": Diablo4OLEDProfile(),
        "diablo4-oled-vrr": Diablo4OLEDVRRProfile(),
        "pokemon-auto-chess": PokemonAutoChessProfile(),
        "pokemon-auto-chess-oled": PokemonAutoChessOLEDProfile(),
        "pacdeluxe": PACDeluxeProfile(),
        "pacdeluxe-oled": PACDeluxeOLEDProfile(),
        "productivity-oled": ProductivityOLEDProfile(),
        "ryujinx-ssbu": RyujinxSSBUProfile(),
        "ryujinx-ssbu-oled": RyujinxSSBUOLEDProfile(),
        "ryujinx-ssbu-vrr": RyujinxSSBUVRRProfile(),
    }
