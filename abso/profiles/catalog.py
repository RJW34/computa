"""Central profile catalog and metadata.

This module is the single source of truth for profile registration and
cross-surface metadata (CLI, tray, GUI integrations).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from abso.profiles.base import BaseProfile
from abso.profiles.cod_bo7 import CodBo7Profile
from abso.profiles.diablo4 import Diablo4Profile
from abso.profiles.fortnite import FortniteProfile
from abso.profiles.overwatch2 import (
    Overwatch2GSyncHDRProfile,
    Overwatch2GSyncProfile,
    Overwatch2Profile,
)
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.pokemon_auto_chess import PokemonAutoChessProfile
from abso.profiles.productivity_oled import ProductivityOLEDProfile
from abso.profiles.rivals2 import Rivals2Profile
from abso.profiles.rivals2_300hz_max import Rivals2_300HzMaxProfile
from abso.profiles.rivals2_gsync import Rivals2GSyncProfile, Rivals2OnlineGSyncProfile
from abso.profiles.rivals2_offline import Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineProfile
from abso.profiles.rivals2_tournament_sim import Rivals2TournamentSimProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeProfile,
)
from abso.profiles.streaming_profiles import (
    FortniteStreamingProfile,
    PACDeluxeStreamingProfile,
    Rivals2StreamingProfile,
    RyujinxSSBUStreamingProfile,
    SlippiMeleeStreamingProfile,
)

TrayCategory = Literal["Productivity", "Fighting", "ARPG", "Shooter", "Streaming", "Other"]
SyncMode = Literal["on", "off", "agnostic"]


@dataclass(frozen=True)
class ProfileCatalogEntry:
    """Profile class and UI metadata consumed by tray/GUI surfaces."""

    profile_class: type[BaseProfile]
    tray_category: TrayCategory
    tray_subtitle: str
    tray_description: str | None = None
    sync_mode: SyncMode = "agnostic"


PROFILE_CATALOG: OrderedDict[str, ProfileCatalogEntry] = OrderedDict(
    {
        "slippi-melee": ProfileCatalogEntry(
            profile_class=SlippiMeleeProfile,
            tray_category="Fighting",
            tray_subtitle="Competitive | LLM ON | No Sync",
            sync_mode="off",
        ),
        "slippi-melee-console-parity": ProfileCatalogEntry(
            profile_class=SlippiMeleeConsoleParityProfile,
            tray_category="Fighting",
            tray_subtitle="Console-Parity | VSync ON | LLM OFF",
            sync_mode="off",
        ),
        "rivals2": ProfileCatalogEntry(
            profile_class=Rivals2Profile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | No Sync (Default)",
            sync_mode="off",
        ),
        "rivals2-offline": ProfileCatalogEntry(
            profile_class=Rivals2OfflineProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | No Sync | Uncapped",
            sync_mode="off",
        ),
        "rivals2-online": ProfileCatalogEntry(
            profile_class=Rivals2OnlineProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | Uncapped | Rollback-Safe",
            sync_mode="off",
        ),
        "rivals2-tournament-sim-144hz": ProfileCatalogEntry(
            profile_class=Rivals2TournamentSimProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | 144Hz | No VRR",
            sync_mode="off",
        ),
        "rivals2-gsync": ProfileCatalogEntry(
            profile_class=Rivals2GSyncProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | G-SYNC ON | VSync Safety Net",
            sync_mode="on",
        ),
        "rivals2-online-gsync": ProfileCatalogEntry(
            profile_class=Rivals2OnlineGSyncProfile,
            tray_category="Fighting",
            tray_subtitle="G-SYNC ON | Rollback-Safe | VRR",
            sync_mode="on",
        ),
        "rivals2-300hz-max": ProfileCatalogEntry(
            profile_class=Rivals2_300HzMaxProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | 300Hz | No Sync",
            sync_mode="off",
        ),
        "cod-bo7": ProfileCatalogEntry(
            profile_class=CodBo7Profile,
            tray_category="Shooter",
            tray_subtitle="HDR ON | Reflex ON+Boost | LLM OFF",
            sync_mode="agnostic",
        ),
        "diablo4": ProfileCatalogEntry(
            profile_class=Diablo4Profile,
            tray_category="ARPG",
            tray_subtitle="HDR ON | Reflex ON+Boost | LLM OFF",
            sync_mode="agnostic",
        ),
        "fortnite": ProfileCatalogEntry(
            profile_class=FortniteProfile,
            tray_category="Shooter",
            tray_subtitle="Reflex ON+Boost | LLM OFF | HAGS ON",
            sync_mode="agnostic",
        ),
        "fortnite-streaming": ProfileCatalogEntry(
            profile_class=FortniteStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="Reflex ON+Boost | OBS 1080p60",
            sync_mode="agnostic",
        ),
        "overwatch2": ProfileCatalogEntry(
            profile_class=Overwatch2Profile,
            tray_category="Shooter",
            tray_subtitle="Reflex ON+Boost | VSync OFF | G-SYNC OFF",
            sync_mode="off",
        ),
        "overwatch2-gsync": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncProfile,
            tray_category="Shooter",
            tray_subtitle="Reflex ON+Boost | VSync Safety Net | G-SYNC ON",
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRProfile,
            tray_category="Shooter",
            tray_subtitle="HDR ON | Reflex ON+Boost | G-SYNC ON",
            sync_mode="on",
        ),
        "pokemon-auto-chess": ProfileCatalogEntry(
            profile_class=PokemonAutoChessProfile,
            tray_category="Other",
            tray_subtitle="LLM ON | Browser WebGL",
            sync_mode="agnostic",
        ),
        "pacdeluxe": ProfileCatalogEntry(
            profile_class=PACDeluxeProfile,
            tray_category="Other",
            tray_subtitle="LLM ON | Tauri + WebView2 | Adaptive VSync",
            sync_mode="agnostic",
        ),
        "pacdeluxe-streaming": ProfileCatalogEntry(
            profile_class=PACDeluxeStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="OBS 1080p60 | Multi-monitor",
            sync_mode="agnostic",
        ),
        "productivity": ProfileCatalogEntry(
            profile_class=ProductivityOLEDProfile,
            tray_category="Productivity",
            tray_subtitle="HDR ON | Adaptive VSync | VRR (if enabled)",
            sync_mode="agnostic",
        ),
        "ryujinx-ssbu": ProfileCatalogEntry(
            profile_class=RyujinxSSBUProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | Vulkan | Fixed 60fps",
            sync_mode="off",
        ),
        "ryujinx-ssbu-streaming": ProfileCatalogEntry(
            profile_class=RyujinxSSBUStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="OBS 1080p60 | Multi-monitor",
            sync_mode="agnostic",
        ),
        "rivals2-streaming": ProfileCatalogEntry(
            profile_class=Rivals2StreamingProfile,
            tray_category="Streaming",
            tray_subtitle="Rollback-Safe | OBS 1080p60",
            sync_mode="agnostic",
        ),
        "slippi-melee-streaming": ProfileCatalogEntry(
            profile_class=SlippiMeleeStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="OBS 1080p60 | Multi-monitor",
            sync_mode="agnostic",
        ),
    }
)


def get_profile_classes() -> dict[str, type[BaseProfile]]:
    """Get profile registry mapping profile ID to profile class."""
    return {profile_id: entry.profile_class for profile_id, entry in PROFILE_CATALOG.items()}


def get_profile_instances() -> dict[str, BaseProfile]:
    """Get all profile instances keyed by profile ID."""
    return {
        profile_id: entry.profile_class()
        for profile_id, entry in PROFILE_CATALOG.items()
    }


def get_profile_manifest() -> list[dict[str, Any]]:
    """Get profile metadata for GUI/tray clients."""
    manifest: list[dict[str, Any]] = []
    for profile_id, entry in PROFILE_CATALOG.items():
        profile = entry.profile_class()
        manifest.append(
            {
                "id": profile_id,
                "display_name": profile.display_name,
                "description": profile.description,
                "optimization_target": profile.optimization_target,
                "executables": profile.executable_hints,
                "tray_category": entry.tray_category,
                "tray_subtitle": entry.tray_subtitle,
                "tray_description": entry.tray_description or profile.description,
                "sync_mode": entry.sync_mode,
            }
        )
    return manifest
