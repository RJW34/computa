"""Legacy Rivals 2 300 Hz profile alias.

This ID remains importable for compatibility, but the explicit offline/training
profile now owns the no-sync low-latency lane and automatically targets the
highest available refresh on the gaming display.
"""

from __future__ import annotations

from abso.profiles.rivals2_offline import Rivals2OfflineProfile


class Rivals2_300HzMaxProfile(Rivals2OfflineProfile):
    """Backward-compatible alias of the consolidated offline Rivals 2 profile."""

    @property
    def profile_id(self) -> str:
        return "rivals2-300hz-max"

    @property
    def display_name(self) -> str:
        return "Rivals 2: 300Hz Maximum"

    @property
    def description(self) -> str:
        return "Legacy alias for the offline/training Rivals 2 profile"
