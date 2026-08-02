"""Legacy Rivals 2 profile alias.

This ID remains importable for compatibility, but the shipped catalog now
consolidates generic Rivals usage onto the merged no-sync lane.
"""

from __future__ import annotations

from abso.profiles.rivals2_nosync import Rivals2NoSyncProfile


class Rivals2Profile(Rivals2NoSyncProfile):
    """Backward-compatible alias of the merged no-sync Rivals 2 profile."""

    @property
    def profile_id(self) -> str:
        return "rivals2"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2"

    @property
    def description(self) -> str:
        return "Legacy alias for the merged no-sync Rivals 2 profile"
