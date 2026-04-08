"""Game optimization profiles."""

from abso.profiles.base import BaseProfile
from abso.profiles.catalog import (
    PROFILE_CATALOG,
    get_profile_instances,
    get_profile_manifest,
    resolve_profile_id,
)
from abso.profiles.cod_bo7 import CodBo7Profile, CodBo7SDRProfile
from abso.profiles.diablo4 import Diablo4Profile, Diablo4SDRProfile
from abso.profiles.fortnite import FortniteHDRProfile, FortniteProfile
from abso.profiles.marvel_rivals import MarvelRivalsHDRProfile, MarvelRivalsSDRProfile
from abso.profiles.overwatch2 import (
    Overwatch2GSyncCaptureProfile,
    Overwatch2GSyncHDRCaptureProfile,
    Overwatch2GSyncHDRProfile,
    Overwatch2GSyncProfile,
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
from abso.profiles.rivals2_tournament_sim import Rivals2TournamentSimProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeProfile,
    SlippiMeleeUniversalProfile,
    SlippiMeleeVRRLabProfile,
)
from abso.profiles.streaming_profiles import (
    FortniteHDRStreamingProfile,
    FortniteStreamingProfile,
    Overwatch2GSyncStreamingProfile,
    Overwatch2GSyncHDRStreamingProfile,
    PACDeluxeStreamingProfile,
    Rivals2HDRStreamingProfile,
    Rivals2StreamingProfile,
    RyujinxSSBUStreamingProfile,
    SlippiMeleeStreamingProfile,
)

__all__ = [
    "BaseProfile",
    "SlippiMeleeConsoleParityProfile",
    "SlippiMeleeProfile",
    "SlippiMeleeUniversalProfile",
    "SlippiMeleeVRRLabProfile",
    "Rivals2Profile",
    "Rivals2OfflineProfile",
    "Rivals2OfflineHDRProfile",
    "Rivals2OnlineProfile",
    "Rivals2OnlineHDRProfile",
    "Rivals2TournamentSimProfile",
    "Rivals2_300HzMaxProfile",
    "Rivals2GSyncProfile",
    "Rivals2GSyncHDRProfile",
    "Rivals2OnlineGSyncProfile",
    "Rivals2OnlineGSyncHDRProfile",
    "CodBo7Profile",
    "CodBo7SDRProfile",
    "Diablo4Profile",
    "Diablo4SDRProfile",
    "FortniteProfile",
    "FortniteHDRProfile",
    "FortniteStreamingProfile",
    "FortniteHDRStreamingProfile",
    "MarvelRivalsSDRProfile",
    "MarvelRivalsHDRProfile",
    "Overwatch2Profile",
    "Overwatch2GSyncProfile",
    "Overwatch2GSyncHDRProfile",
    "Overwatch2GSyncCaptureProfile",
    "Overwatch2GSyncHDRCaptureProfile",
    "Overwatch2GSyncStreamingProfile",
    "Overwatch2GSyncHDRStreamingProfile",
    "PokemonAutoChessProfile",
    "PACDeluxeProfile",
    "PACDeluxeStreamingProfile",
    "ProductivityOLEDProfile",
    "RyujinxSSBUProfile",
    "RyujinxSSBUStreamingProfile",
    "Rivals2StreamingProfile",
    "Rivals2HDRStreamingProfile",
    "SlippiMeleeStreamingProfile",
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
