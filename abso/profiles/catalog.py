"""Central profile catalog and metadata.

This module is the single source of truth for profile registration and
cross-surface metadata (CLI, tray, GUI integrations).
"""

from __future__ import annotations

from collections import OrderedDict
from dataclasses import dataclass
from typing import Any, Literal

from abso.profiles.base import BaseProfile
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
    Rivals2GSyncProfile,
    Rivals2OnlineGSyncProfile,
)
from abso.profiles.rivals2_offline import Rivals2OfflineProfile
from abso.profiles.rivals2_online import Rivals2OnlineProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import (
    SlippiMeleeConsoleParityProfile,
    SlippiMeleeProfile,
    SlippiMeleeUniversalProfile,
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
        "diablo4": ProfileCatalogEntry(
            profile_class=Diablo4Profile,
            tray_category="ARPG",
            tray_subtitle="HDR ON | Reflex ON | LLM OFF",
            sync_mode="on",
        ),
        "diablo4-sdr": ProfileCatalogEntry(
            profile_class=Diablo4SDRProfile,
            tray_category="ARPG",
            tray_subtitle="SDR | Reflex ON | VRR",
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
                "Performance-first SDR Marvel Rivals profile. Uses Reflex + VRR and keeps "
                "engine-specific options in the native config handler."
            ),
            sync_mode="on",
        ),
        "marvel-rivals-hdr": ProfileCatalogEntry(
            profile_class=MarvelRivalsHDRProfile,
            tray_category="Shooter",
            tray_subtitle="HDR ON | Reflex ON+Boost | G-SYNC ON",
            tray_description=(
                "Performance-first HDR Marvel Rivals profile. Uses Reflex + VRR and keeps "
                "engine-specific options in the native config handler."
            ),
            sync_mode="on",
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
            tray_description=(
                "Low-latency Ryujinx system path for SSBU/HewDraw Remix. ABSO handles the OS/driver side, "
                "but emulator settings still need to be configured manually."
            ),
            sync_mode="off",
        ),
    }
)

PROFILE_ALIASES: dict[str, str] = {
    # Retired generic/no-value Rivals variants map to the evidence-backed
    # offline no-sync lane instead of lingering as separate menu clutter.
    "rivals2": "rivals2-offline",
    "rivals2-300hz-max": "rivals2-offline",
    "rivals2-tournament-sim-144hz": "rivals2-offline",
    # HDR twins consolidated into SDR base profiles.
    "rivals2-offline-hdr": "rivals2-offline",
    "rivals2-online-hdr": "rivals2-online",
    "rivals2-gsync-hdr": "rivals2-gsync",
    "rivals2-online-gsync-hdr": "rivals2-online-gsync",
    # Streaming variants consolidated into their base profiles.
    "fortnite-streaming": "fortnite",
    "fortnite-streaming-hdr": "fortnite-hdr",
    "overwatch2-gsync-streaming": "overwatch2-gsync",
    "overwatch2-gsync-hdr-streaming": "overwatch2-gsync-hdr",
    "pacdeluxe-streaming": "pacdeluxe",
    "ryujinx-ssbu-streaming": "ryujinx-ssbu",
    "rivals2-streaming": "rivals2-online",
    "rivals2-streaming-hdr": "rivals2-online",
    "slippi-melee-streaming": "slippi-melee",
    # Experimental/duplicate Slippi variants.
    "slippi-melee-vrr-lab": "slippi-melee",
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
                "application_scope": profile.application_scope,
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
