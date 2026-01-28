"""Game optimization profiles."""

from abso.profiles.base import BaseProfile
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.productivity_oled import ProductivityOLEDProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_offline import Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineProfile
from abso.profiles.rivals2_tournament_sim import Rivals2TournamentSimProfile
from abso.profiles.rivals2_300hz_max import Rivals2_300HzMaxProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import SlippiMeleeProfile

__all__ = [
    "BaseProfile",
    "SlippiMeleeProfile",
    "Rivals2Profile",
    "Rivals2OfflineProfile",
    "Rivals2OnlineProfile",
    "Rivals2TournamentSimProfile",
    "Rivals2_300HzMaxProfile",
    "CodBo7Profile",
    "Diablo4Profile",
    "PokemonAutoChessProfile",
    "PACDeluxeProfile",
    "ProductivityOLEDProfile",
    "RyujinxSSBUProfile",
    "get_all_profiles",
]


def get_all_profiles() -> dict[str, BaseProfile]:
    """Get all available game profiles.

    Returns:
        Dictionary mapping profile ID to profile instance.
    """
    return {
        "slippi-melee": SlippiMeleeProfile(),
        "rivals2": Rivals2Profile(),
        "rivals2-offline": Rivals2OfflineProfile(),
        "rivals2-online": Rivals2OnlineProfile(),
        "rivals2-tournament-sim-144hz": Rivals2TournamentSimProfile(),
        "rivals2-300hz-max": Rivals2_300HzMaxProfile(),
        "cod-bo7": CodBo7Profile(),
        "diablo4": Diablo4Profile(),
        "pokemon-auto-chess": PokemonAutoChessProfile(),
        "pacdeluxe": PACDeluxeProfile(),
        "productivity": ProductivityOLEDProfile(),
        "ryujinx-ssbu": RyujinxSSBUProfile(),
    }
