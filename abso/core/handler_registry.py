"""Central settings-handler registry.

Before this module existed, ``abso/core/auditor.py`` and
``abso/core/backup.py`` each carried their own list of every handler ABSO
talks to. Adding a new handler meant remembering to register it in both
places, and discrepancies showed up as silent gaps (a handler that gets
backed up but never audited, or vice versa).

The registry stores one entry per handler with two booleans controlling
which factory ``audit`` and ``backup`` use. Imports are kept inline
inside ``_all_entries()`` to preserve the circular-import escape the
previous lazy factories provided.

To register a new handler, add a single :class:`HandlerEntry` row below.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING, Callable

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler


@dataclass(frozen=True)
class HandlerEntry:
    """One row in the handler registry.

    Attributes:
        factory: zero-argument callable that constructs the handler.
        audit: True if :func:`get_audit_handlers` should include it.
        backup: True if :func:`get_backup_handlers` should include it.
        notes: free-text rationale for unusual flags (e.g. audit-only).
    """

    factory: Callable[[], "SettingsHandler"]
    audit: bool
    backup: bool
    notes: str | None = None


def _all_entries() -> list[HandlerEntry]:
    """Build the registry. Inline imports keep this circular-safe.

    Ordering matches the prior audit / backup factory orderings so that
    apply, verify, and backup ordering stays byte-identical to before
    this refactor.
    """
    # Core system / shell handlers — audited and backed up.
    from abso.settings.audio import AudioSettingsHandler
    from abso.settings.graphics import GraphicsSettingsHandler
    from abso.settings.memory import MemorySettingsHandler
    from abso.settings.mouse import MouseSettingsHandler
    from abso.settings.network import NetworkSettingsHandler
    from abso.settings.nvidia import NvidiaSettingsHandler
    from abso.settings.power import PowerSettingsHandler
    from abso.settings.registry import RegistrySettingsHandler
    from abso.settings.services import ServicesSettingsHandler
    from abso.settings.storage import StorageSettingsHandler
    from abso.settings.tasks import TasksSettingsHandler
    from abso.settings.timer import TimerSettingsHandler
    from abso.settings.updates import UpdatesSettingsHandler
    from abso.settings.visual import VisualSettingsHandler
    from abso.settings.windows import WindowsSettingsHandler

    # Audit-only diagnostics & opt-in surfaces.
    from abso.settings.diagnostics import DiagnosticsSettingsHandler
    from abso.settings.display_range import DisplayColorRangeHandler
    from abso.settings.vbs_optin import VBSOptInHandler

    # Profile-specific config handlers — backed up so settings from one
    # game don't leak into another's restore.
    from abso.settings.cnm import CNMSettingsHandler
    from abso.settings.color import ColorProfileSettingsHandler
    from abso.settings.cpu_affinity import CpuAffinityHandler
    from abso.settings.debloat import DebloatHandler
    from abso.settings.diablo4_config import Diablo4ConfigHandler
    from abso.settings.dolphin import DolphinConfigHandler
    from abso.settings.fortnite_config import FortniteConfigHandler
    from abso.settings.marvel_rivals_config import MarvelRivalsConfigHandler
    from abso.settings.nvidia_notifications import NvidiaNotificationHandler
    from abso.settings.obs import OBSSettingsHandler
    from abso.settings.ow2_config import OW2ConfigHandler
    from abso.settings.process_priority import ProcessPriorityHandler
    from abso.settings.rivals2_config import Rivals2ConfigHandler
    from abso.settings.standby_list import StandbyListHandler

    # 25H2 feature-flag rollout surfaces — detect-only, audited, backed
    # up (restore_guarantee = "none" so backup-restore stays non-blocking).
    from abso.settings.ai_agents import AIAgentsSettingsHandler
    from abso.settings.xbox_mode import XboxModeSettingsHandler

    return [
        # --- Core system / shell ---
        HandlerEntry(WindowsSettingsHandler, audit=True, backup=True),
        HandlerEntry(PowerSettingsHandler, audit=True, backup=True),
        HandlerEntry(RegistrySettingsHandler, audit=True, backup=True),
        HandlerEntry(NvidiaSettingsHandler, audit=True, backup=True),
        HandlerEntry(TimerSettingsHandler, audit=True, backup=True),
        HandlerEntry(MouseSettingsHandler, audit=True, backup=True),
        HandlerEntry(GraphicsSettingsHandler, audit=True, backup=True),
        HandlerEntry(ServicesSettingsHandler, audit=True, backup=True),
        HandlerEntry(TasksSettingsHandler, audit=True, backup=True),
        HandlerEntry(MemorySettingsHandler, audit=True, backup=True),
        HandlerEntry(NetworkSettingsHandler, audit=True, backup=True),
        HandlerEntry(VisualSettingsHandler, audit=True, backup=True),
        HandlerEntry(StorageSettingsHandler, audit=True, backup=True),
        HandlerEntry(AudioSettingsHandler, audit=True, backup=True),
        HandlerEntry(UpdatesSettingsHandler, audit=True, backup=True),
        HandlerEntry(
            DisplayColorRangeHandler,
            audit=True,
            backup=True,
            notes="Flags PC monitors stuck on Limited RGB / TV range after NVIDIA driver update.",
        ),

        # --- Audit-only surfaces ---
        HandlerEntry(
            DiagnosticsSettingsHandler,
            audit=True,
            backup=False,
            notes="Audit-only diagnostics — GPU prefs, overlays, update activity, driver freshness.",
        ),
        HandlerEntry(
            VBSOptInHandler,
            audit=True,
            backup=False,
            notes="Opt-in VBS/HVCI/VMP status surfacing. Never mutates unless explicitly acknowledged.",
        ),

        # --- Profile-specific config handlers (backup-only) ---
        HandlerEntry(Diablo4ConfigHandler, audit=False, backup=True),
        HandlerEntry(DolphinConfigHandler, audit=False, backup=True),
        HandlerEntry(FortniteConfigHandler, audit=False, backup=True),
        HandlerEntry(MarvelRivalsConfigHandler, audit=False, backup=True),
        HandlerEntry(OW2ConfigHandler, audit=False, backup=True),
        HandlerEntry(Rivals2ConfigHandler, audit=False, backup=True),
        HandlerEntry(NvidiaNotificationHandler, audit=False, backup=True),
        HandlerEntry(OBSSettingsHandler, audit=False, backup=True),
        HandlerEntry(ProcessPriorityHandler, audit=False, backup=True),
        HandlerEntry(CNMSettingsHandler, audit=False, backup=True),
        HandlerEntry(ColorProfileSettingsHandler, audit=False, backup=True),
        HandlerEntry(CpuAffinityHandler, audit=False, backup=True),
        HandlerEntry(StandbyListHandler, audit=False, backup=True),
        HandlerEntry(DebloatHandler, audit=False, backup=True),

        # --- 25H2 feature-flag rollouts ---
        HandlerEntry(
            XboxModeSettingsHandler,
            audit=True,
            backup=True,
            notes="Detect-only; restore_guarantee='none' keeps backup-restore non-blocking.",
        ),
        HandlerEntry(
            AIAgentsSettingsHandler,
            audit=True,
            backup=True,
            notes="Detect-only; restore_guarantee='none' keeps backup-restore non-blocking.",
        ),
    ]


def get_audit_handlers() -> list["SettingsHandler"]:
    """Construct one handler instance per registry entry tagged ``audit``."""
    return [entry.factory() for entry in _all_entries() if entry.audit]


def get_backup_handlers() -> list["SettingsHandler"]:
    """Construct one handler instance per registry entry tagged ``backup``."""
    return [entry.factory() for entry in _all_entries() if entry.backup]
