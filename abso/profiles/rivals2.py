"""Legacy Rivals 2 profile alias.

This ID remains importable for compatibility, but the shipped catalog now
consolidates generic Rivals usage onto the explicit offline/training lane.
"""

from __future__ import annotations

from abso.profiles.rivals2_offline import Rivals2OfflineProfile


class Rivals2Profile(Rivals2OfflineProfile):
    """Backward-compatible alias of the offline/training Rivals 2 profile."""

    @property
    def profile_id(self) -> str:
        return "rivals2"

    @property
    def display_name(self) -> str:
        return "Rivals of Aether 2"

    @property
    def description(self) -> str:
        return "Legacy alias for the offline/training Rivals 2 profile"
