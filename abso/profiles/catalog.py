"""Central profile catalog and metadata.

This module is the single source of truth for profile registration and
cross-surface metadata (CLI, tray, GUI integrations).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from abso.profiles.base import BaseProfile
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
            tray_subtitle="Competitive | No Sync | Backend-Aware",
            sync_mode="off",
        ),
        "slippi-melee-console-parity": ProfileCatalogEntry(
            profile_class=SlippiMeleeConsoleParityProfile,
            tray_category="Fighting",
            tray_subtitle="Console-Parity | 60Hz + VSync | LLM OFF",
            sync_mode="on",
        ),
        "slippi-melee-universal": ProfileCatalogEntry(
            profile_class=SlippiMeleeUniversalProfile,
            tray_category="Fighting",
            tray_subtitle="Lowest Latency | HAGS ON | No Sync",
            tray_description=(
                "Absolute minimum latency with HAGS kept on so re-applying does not require "
                "a reboot. VSync OFF, G-SYNC/VRR OFF."
            ),
            sync_mode="off",
        ),
        "slippi-melee-vrr-lab": ProfileCatalogEntry(
            profile_class=SlippiMeleeVRRLabProfile,
            tray_category="Fighting",
            tray_subtitle="VRR Lab | G-SYNC ON | A/B Test",
            sync_mode="on",
        ),
        "rivals2-offline": ProfileCatalogEntry(
            profile_class=Rivals2OfflineProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | No Sync | Uncapped",
            sync_mode="off",
        ),
        "rivals2-offline-hdr": ProfileCatalogEntry(
            profile_class=Rivals2OfflineHDRProfile,
            tray_category="Fighting",
            tray_subtitle="HDR ON | No Sync | Uncapped",
            tray_description=(
                "Offline/training Rivals 2 profile with native HDR output enabled. "
                "Keeps the uncapped no-sync path while turning on the game's HDR output."
            ),
            sync_mode="off",
        ),
        "rivals2-online": ProfileCatalogEntry(
            profile_class=Rivals2OnlineProfile,
            tray_category="Fighting",
            tray_subtitle="LLM ON | Uncapped | Rollback-Safe",
            sync_mode="off",
        ),
        "rivals2-online-hdr": ProfileCatalogEntry(
            profile_class=Rivals2OnlineHDRProfile,
            tray_category="Fighting",
            tray_subtitle="HDR ON | Uncapped | Rollback-Safe",
            tray_description=(
                "Rollback-safe Rivals 2 profile with native HDR output enabled. "
                "Keeps the conservative online timing path while turning on HDR."
            ),
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
        "rivals2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Rivals2GSyncHDRProfile,
            tray_category="Fighting",
            tray_subtitle="HDR ON | G-SYNC ON | VSync Safety Net",
            tray_description=(
                "Native HDR Rivals 2 VRR profile. Uses fullscreen G-SYNC plus the game's "
                "HDR output path and an in-game refresh-minus-3 cap."
            ),
            sync_mode="on",
        ),
        "rivals2-online-gsync": ProfileCatalogEntry(
            profile_class=Rivals2OnlineGSyncProfile,
            tray_category="Fighting",
            tray_subtitle="G-SYNC ON | Rollback-Safe | VRR",
            sync_mode="on",
        ),
        "rivals2-online-gsync-hdr": ProfileCatalogEntry(
            profile_class=Rivals2OnlineGSyncHDRProfile,
            tray_category="Fighting",
            tray_subtitle="HDR ON | G-SYNC ON | Rollback-Safe",
            tray_description=(
                "Rollback-safe native HDR Rivals 2 VRR profile. Uses fullscreen G-SYNC, "
                "HDR output, and an in-game refresh-minus-3 cap."
            ),
            sync_mode="on",
        ),
        "cod-bo7": ProfileCatalogEntry(
            profile_class=CodBo7Profile,
            tray_category="Shooter",
            tray_subtitle="HDR ON | Reflex ON+Boost | LLM OFF",
            sync_mode="agnostic",
        ),
        "cod-bo7-sdr": ProfileCatalogEntry(
            profile_class=CodBo7SDRProfile,
            tray_category="Shooter",
            tray_subtitle="SDR | Reflex ON+Boost | LLM OFF",
            sync_mode="agnostic",
        ),
        "diablo4": ProfileCatalogEntry(
            profile_class=Diablo4Profile,
            tray_category="ARPG",
            tray_subtitle="HDR ON | Reflex ON+Boost | LLM OFF",
            sync_mode="on",
        ),
        "diablo4-sdr": ProfileCatalogEntry(
            profile_class=Diablo4SDRProfile,
            tray_category="ARPG",
            tray_subtitle="SDR | Reflex ON+Boost | VRR",
            sync_mode="on",
        ),
        "fortnite": ProfileCatalogEntry(
            profile_class=FortniteProfile,
            tray_category="Shooter",
            tray_subtitle="SDR | Reflex ON+Boost | No Sync",
            sync_mode="agnostic",
        ),
        "fortnite-hdr": ProfileCatalogEntry(
            profile_class=FortniteHDRProfile,
            tray_category="Shooter",
            tray_subtitle="HDR ON | Reflex ON+Boost | No Sync",
            sync_mode="agnostic",
        ),
        "marvel-rivals-sdr": ProfileCatalogEntry(
            profile_class=MarvelRivalsSDRProfile,
            tray_category="Shooter",
            tray_subtitle="SDR | Reflex ON+Boost | G-SYNC ON",
            tray_description=(
                "Performance-first SDR Marvel Rivals profile. Uses Reflex + VRR and expects "
                "you to A/B the in-game Performance Optimization (Beta) toggle on your hardware."
            ),
            sync_mode="on",
        ),
        "marvel-rivals-hdr": ProfileCatalogEntry(
            profile_class=MarvelRivalsHDRProfile,
            tray_category="Shooter",
            tray_subtitle="HDR ON | Reflex ON+Boost | G-SYNC ON",
            tray_description=(
                "Performance-first HDR Marvel Rivals profile. Uses Reflex + VRR and expects "
                "you to A/B the in-game Performance Optimization (Beta) toggle on your hardware."
            ),
            sync_mode="on",
        ),
        "fortnite-streaming": ProfileCatalogEntry(
            profile_class=FortniteStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="SDR | Reflex ON+Boost | OBS 1080p60",
            sync_mode="agnostic",
        ),
        "fortnite-streaming-hdr": ProfileCatalogEntry(
            profile_class=FortniteHDRStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="HDR ON | Reflex ON+Boost | OBS 1080p60",
            sync_mode="agnostic",
        ),
        "overwatch2": ProfileCatalogEntry(
            profile_class=Overwatch2Profile,
            tray_category="Shooter",
            tray_subtitle="Reflex OFF | VSync OFF | G-SYNC OFF",
            sync_mode="off",
        ),
        "overwatch2-gsync": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncProfile,
            tray_category="Shooter",
            tray_subtitle="Strict Exclusive | Reflex ON+Boost | G-SYNC ON",
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRProfile,
            tray_category="Shooter",
            tray_subtitle="Strict HDR Exclusive | Reflex ON+Boost | G-SYNC ON",
            sync_mode="on",
        ),
        "overwatch2-gsync-capture": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncCaptureProfile,
            tray_category="Shooter",
            tray_subtitle="Capture-Safe | Borderless VRR | Medal/Discord Friendly",
            tray_description=(
                "Borderless/windowed G-SYNC profile for the active gaming display. "
                "Keeps Medal, Discord, and similar capture overlays compatible."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr-capture": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRCaptureProfile,
            tray_category="Shooter",
            tray_subtitle="HDR Capture-Safe | Borderless VRR | Overlay Friendly",
            tray_description=(
                "HDR borderless/windowed G-SYNC profile for the active gaming display. "
                "Best fit when you want HDR plus Medal/Discord-style capture workflows."
            ),
            sync_mode="on",
        ),
        "overwatch2-gsync-hdr-streaming": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncHDRStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="HDR + G-SYNC | OBS 1080p60",
            sync_mode="on",
        ),
        "overwatch2-gsync-streaming": ProfileCatalogEntry(
            profile_class=Overwatch2GSyncStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="G-SYNC | OBS 1080p60",
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
            tray_subtitle="Vulkan | Fixed 60fps | HAGS ON | LLM OFF",
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
        "rivals2-streaming-hdr": ProfileCatalogEntry(
            profile_class=Rivals2HDRStreamingProfile,
            tray_category="Streaming",
            tray_subtitle="HDR ON | Rollback-Safe | OBS 1080p60",
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

PROFILE_ALIASES: dict[str, str] = {
    # Retired generic/no-value Rivals variants now map to the evidence-backed
    # offline no-sync lane instead of lingering as separate menu clutter.
    "rivals2": "rivals2-offline",
    "rivals2-300hz-max": "rivals2-offline",
}


def _load_user_profiles() -> dict[str, ProfileCatalogEntry]:
    """Load user-defined YAML profiles from ~/.abso/profiles/.

    User profiles cannot override built-in profile IDs.
    """
    try:
        from abso.profiles.yaml_loader import YAMLProfileLoader

        loader = YAMLProfileLoader()
        user_profiles = loader.load_directory()
        # Filter out conflicts with built-in profiles
        safe = {}
        for pid, entry in user_profiles.items():
            if pid in PROFILE_CATALOG:
                import logging

                logging.getLogger(__name__).warning(
                    f"User profile '{pid}' conflicts with built-in profile, skipping"
                )
            else:
                safe[pid] = entry
        return safe
    except Exception as e:
        import logging

        logging.getLogger(__name__).debug(f"User profile loading skipped: {e}")
        return {}


def _get_full_catalog() -> dict[str, ProfileCatalogEntry]:
    """Get built-in + user profiles merged."""
    merged = dict(PROFILE_CATALOG)
    merged.update(_load_user_profiles())
    return merged


def get_profile_classes() -> dict[str, type[BaseProfile]]:
    """Get profile registry mapping profile ID to profile class."""
    return {pid: entry.profile_class for pid, entry in _get_full_catalog().items()}


def resolve_profile_id(profile_id: str | None) -> str | None:
    """Resolve a potentially legacy profile id to its canonical id."""
    if profile_id is None:
        return None
    return PROFILE_ALIASES.get(profile_id, profile_id)


def get_profile_instances() -> dict[str, BaseProfile]:
    """Get all profile instances keyed by profile ID."""
    return {pid: entry.profile_class() for pid, entry in _get_full_catalog().items()}


def get_profile_manifest() -> list[dict[str, Any]]:
    """Get profile metadata for GUI/tray clients."""
    manifest: list[dict[str, Any]] = []
    for profile_id, entry in _get_full_catalog().items():
        profile = entry.profile_class()
        handlers = [handler.__class__.__name__ for handler in profile.get_handlers()]
        manifest.append(
            {
                "id": profile_id,
                "display_name": profile.display_name,
                "description": profile.description,
                "optimization_target": profile.optimization_target,
                "executables": profile.executable_hints,
                "handlers": handlers,
                "has_in_game_settings": profile.has_in_game_settings(),
                "tray_category": entry.tray_category,
                "tray_subtitle": entry.tray_subtitle,
                "tray_description": entry.tray_description or profile.description,
                "sync_mode": entry.sync_mode,
            }
        )
    return manifest
