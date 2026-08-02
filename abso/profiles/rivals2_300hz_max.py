"""Legacy Rivals 2 300 Hz profile alias.

This ID remains importable for compatibility, but the merged no-sync lane now
owns the no-sync path and automatically targets the highest available refresh
on the gaming display.
"""

from __future__ import annotations

from abso.profiles.rivals2_nosync import Rivals2NoSyncProfile


class Rivals2_300HzMaxProfile(Rivals2NoSyncProfile):
    """Backward-compatible alias of the merged no-sync Rivals 2 profile."""

    @property
    def profile_id(self) -> str:
        return "rivals2-300hz-max"

    @property
    def display_name(self) -> str:
        return "Rivals 2: 300Hz Maximum"

    @property
    def description(self) -> str:
        return "Legacy alias for the merged no-sync Rivals 2 profile"
