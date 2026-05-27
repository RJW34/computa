"""Game optimization profiles."""

from abso.profiles.base import BaseProfile
from abso.profiles.catalog import (
    PROFILE_CATALOG,
    get_profile_instances,
    get_profile_manifest,
    resolve_profile_id,
)
from abso.profiles.deadlock import (
    DeadlockGSyncHDRProfile,
    DeadlockGSyncProfile,
    DeadlockHDRProfile,
    DeadlockProfile,
)
from abso.profiles.diablo4 import Diablo4Profile, Diablo4SDRProfile
from abso.profiles.fortnite import FortniteHDRProfile, FortniteProfile
from abso.profiles.marvel_rivals import MarvelRivalsHDRProfile, MarvelRivalsSDRProfile
from abso.profiles.overwatch2 import (
    Overwatch2GSyncCaptureProfile,
    Overwatch2GSyncHDRCaptureProfile,
    Overwatch2GSyncHDRProfile,
    Overwatch2GSyncProfile,
    Overwatch2NoSyncHDRProfile,
    Overwatch2Profile,
)
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.productivity_oled import ProductivityOLEDProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_300hz_max import Rivals2_300HzMaxProfile
from abso.profiles.rivals2_gsync import (
    Rivals2GSyncHDRProfile,
    Rivals2GSyncProfile,
    Rivals2OnlineGSyncHDRProfile,
    Rivals2OnlineGSyncProfile,
)
from abso.profiles.rivals2_offline import Rivals2OfflineHDRProfile, Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineHDRProfile, Rivals2OnlineProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityHDRProfile,
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeHDRProfile,
    SlippiMeleeProfile,
    SlippiMeleeUniversalHDRProfile,
    SlippiMeleeUniversalProfile,
)

__all__ = [
    "BaseProfile",
    "SlippiMeleeConsoleParityProfile",
    "SlippiMeleeConsoleParityHDRProfile",
    "SlippiMeleeProfile",
    "SlippiMeleeHDRProfile",
    "SlippiMeleeUniversalProfile",
    "SlippiMeleeUniversalHDRProfile",
    "Rivals2Profile",
    "Rivals2OfflineProfile",
    "Rivals2OfflineHDRProfile",
    "Rivals2OnlineProfile",
    "Rivals2OnlineHDRProfile",
    "Rivals2_300HzMaxProfile",
    "Rivals2GSyncProfile",
    "Rivals2GSyncHDRProfile",
    "Rivals2OnlineGSyncProfile",
    "Rivals2OnlineGSyncHDRProfile",
    "Diablo4Profile",
    "Diablo4SDRProfile",
    "FortniteProfile",
    "FortniteHDRProfile",
    "MarvelRivalsSDRProfile",
    "MarvelRivalsHDRProfile",
    "Overwatch2Profile",
    "Overwatch2NoSyncHDRProfile",
    "Overwatch2GSyncProfile",
    "Overwatch2GSyncHDRProfile",
    "Overwatch2GSyncCaptureProfile",
    "Overwatch2GSyncHDRCaptureProfile",
    "DeadlockProfile",
    "DeadlockHDRProfile",
    "DeadlockGSyncProfile",
    "DeadlockGSyncHDRProfile",
    "PokemonAutoChessProfile",
    "PACDeluxeProfile",
    "ProductivityOLEDProfile",
    "RyujinxSSBUProfile",
    "PROFILE_CATALOG",
    "get_profile_manifest",
    "resolve_profile_id",
    "get_all_profiles",
]


def get_all_profiles() -> dict[str, BaseProfile]:
    """Get all available game profiles.

    Returns:
        Dictionary mapping profile ID to profile instance.
    """
    return get_profile_instances()
