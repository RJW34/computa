"""Streaming-specific variants for game profiles."""

from __future__ import annotations

from abso.profiles.fortnite import FortniteProfile
from abso.profiles.overwatch2 import Overwatch2GSyncHDRProfile
from abso.profiles.pacdeluxe import PACDeluxeProfile
from abso.profiles.profile_bases import OBSStreamingMixin
from abso.profiles.rivals2_online import Rivals2OnlineProfile
from abso.profiles.ryujinx_ssbu import RyujinxSSBUProfile
from abso.profiles.slippi_melee import SlippiMeleeProfile


class FortniteStreamingProfile(OBSStreamingMixin, FortniteProfile):
    """Streaming profile for Fortnite with OBS settings applied."""

    @property
    def profile_id(self) -> str:
        return "fortnite-streaming"

    @property
    def display_name(self) -> str:
        return "Fortnite (Streaming)"

    @property
    def description(self) -> str:
        return "Streaming-optimized Fortnite profile for multi-monitor OBS"


class SlippiMeleeStreamingProfile(OBSStreamingMixin, SlippiMeleeProfile):
    """Streaming profile for Slippi Melee with OBS settings applied."""

    @property
    def profile_id(self) -> str:
        return "slippi-melee-streaming"

    @property
    def display_name(self) -> str:
        return "Slippi Melee (Streaming)"

    @property
    def description(self) -> str:
        return "Streaming-optimized Slippi profile for multi-monitor setups"


class Rivals2StreamingProfile(OBSStreamingMixin, Rivals2OnlineProfile):
    """Streaming profile for Rivals 2 based on rollback-safe settings."""

    @property
    def profile_id(self) -> str:
        return "rivals2-streaming"

    @property
    def display_name(self) -> str:
        return "Rivals 2 (Streaming)"

    @property
    def description(self) -> str:
        return "Streaming-optimized Rivals 2 profile (rollback-safe)"


class RyujinxSSBUStreamingProfile(OBSStreamingMixin, RyujinxSSBUProfile):
    """Streaming profile for SSBU/HDR via Ryujinx with OBS settings applied."""

    @property
    def profile_id(self) -> str:
        return "ryujinx-ssbu-streaming"

    @property
    def display_name(self) -> str:
        return "SSBU / HewDraw Remix (Streaming)"

    @property
    def description(self) -> str:
        return "Streaming-optimized Ryujinx profile for multi-monitor setups"


class Overwatch2GSyncHDRStreamingProfile(OBSStreamingMixin, Overwatch2GSyncHDRProfile):
    """Streaming profile for Overwatch 2 G-SYNC HDR with OBS settings applied."""

    @property
    def profile_id(self) -> str:
        return "overwatch2-gsync-hdr-streaming"

    @property
    def display_name(self) -> str:
        return "Overwatch 2 - GSYNC HDR (Streaming)"

    @property
    def description(self) -> str:
        return "Streaming-optimized OW2 G-SYNC HDR profile for multi-monitor OBS"


class PACDeluxeStreamingProfile(OBSStreamingMixin, PACDeluxeProfile):
    """Streaming profile for PACDeluxe with OBS settings applied."""

    @property
    def profile_id(self) -> str:
        return "pacdeluxe-streaming"

    @property
    def display_name(self) -> str:
        return "PACDeluxe (Streaming)"

    @property
    def description(self) -> str:
        return "Streaming-optimized PACDeluxe profile for multi-monitor OBS"
