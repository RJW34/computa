"""Game optimization profiles."""

from abso.profiles.base import BaseProfile
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.slippi_melee import SlippiMeleeProfile

__all__ = [
    "BaseProfile",
    "SlippiMeleeProfile",
    "Rivals2Profile",
    "CodBo7Profile",
    "Diablo4Profile",
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
        "cod-bo7": CodBo7Profile(),
        "diablo4": Diablo4Profile(),
    }
