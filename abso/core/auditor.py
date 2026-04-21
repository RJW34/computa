"""Configuration audit engine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from abso.core.models import Issue

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


def _get_handlers() -> list[SettingsHandler]:
    """Lazily import and instantiate settings handlers.

    This avoids circular import issues between core and settings modules.
    """
    from abso.settings.audio import AudioSettingsHandler
    from abso.settings.diagnostics import DiagnosticsSettingsHandler
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
    from abso.settings.vbs_optin import VBSOptInHandler
    from abso.settings.visual import VisualSettingsHandler
    from abso.settings.windows import WindowsSettingsHandler

    return [
        WindowsSettingsHandler(),
        PowerSettingsHandler(),
        RegistrySettingsHandler(),
        NvidiaSettingsHandler(),
        TimerSettingsHandler(),
        MouseSettingsHandler(),
        GraphicsSettingsHandler(),
        ServicesSettingsHandler(),
        TasksSettingsHandler(),
        MemorySettingsHandler(),
        NetworkSettingsHandler(),
        VisualSettingsHandler(),
        StorageSettingsHandler(),
        AudioSettingsHandler(),
        UpdatesSettingsHandler(),
        # Audit-only diagnostics — GPU prefs, overlays, update activity,
        # driver freshness, XMP/EXPO, Resizable BAR, DirectStorage,
        # multi-monitor refresh mix.
        DiagnosticsSettingsHandler(),
        # Opt-in VBS/HVCI/VMP status surfacing. Never mutates state unless
        # called with explicit acknowledgement.
        VBSOptInHandler(),
    ]


class ConfigurationAuditor:
    """Audits system configuration for gaming optimization issues."""

    _handlers: list[SettingsHandler]

    def __init__(self) -> None:
        self._handlers = _get_handlers()

    def audit_all(self) -> list[Issue]:
        """Run all configuration audits.

        Returns:
            List of issues found across all handlers.
        """
        all_issues: list[Issue] = []

        for handler in self._handlers:
            try:
                issues = handler.audit()
                all_issues.extend(issues)
            except PermissionError as e:
                logger.error(f"Permission denied during audit of {handler.__class__.__name__}: {e}")
                all_issues.append(Issue(
                    title=f"Audit failed (permission denied): {handler.__class__.__name__}",
                    severity="warning",
                    current_value="Access Denied",
                    optimal_value="N/A",
                    explanation=f"Administrator privileges may be required: {e}",
                    category="system",
                ))
            except OSError as e:
                logger.error(f"OS error during audit of {handler.__class__.__name__}: {e}")
                all_issues.append(Issue(
                    title=f"Audit failed (OS error): {handler.__class__.__name__}",
                    severity="warning",
                    current_value="Error",
                    optimal_value="N/A",
                    explanation=str(e),
                    category="system",
                ))
            except (ValueError, TypeError, AttributeError) as e:
                logger.error(f"Data error during audit of {handler.__class__.__name__}: {e}")
                all_issues.append(Issue(
                    title=f"Audit failed (data error): {handler.__class__.__name__}",
                    severity="warning",
                    current_value="Error",
                    optimal_value="N/A",
                    explanation=str(e),
                    category="system",
                ))

        # Check for problematic Windows updates
        try:
            from abso.core.kb_checker import check_problematic_kbs

            bad_kbs = check_problematic_kbs()
            for kb in bad_kbs:
                all_issues.append(Issue(
                    title=f"Problematic update installed: {kb.kb_id} — {kb.title}",
                    severity=kb.severity,
                    current_value=f"{kb.kb_id} installed ({kb.affected})",
                    optimal_value=f"Uninstall {kb.kb_id}",
                    explanation=f"This Windows update is known to cause: {kb.affected}. "
                                f"Run 'abso setup' or uninstall manually via Windows Update.",
                    category="windows_update",
                ))
        except Exception as e:
            logger.error(f"KB check failed: {e}")

        # Sort by severity (critical first)
        severity_order = {"critical": 0, "warning": 1, "info": 2}
        all_issues.sort(key=lambda x: severity_order.get(x.severity, 3))

        return all_issues

    def audit_category(self, category: str) -> list[Issue]:
        """Run audit for a specific category.

        Args:
            category: Category to audit (windows, power, registry, nvidia, timer,
                      mouse, graphics, services, tasks, memory, network, visual,
                      storage, audio, updates).

        Returns:
            List of issues found in the category.
        """
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

        handler_map = {
            "windows": WindowsSettingsHandler,
            "power": PowerSettingsHandler,
            "registry": RegistrySettingsHandler,
            "nvidia": NvidiaSettingsHandler,
            "timer": TimerSettingsHandler,
            "mouse": MouseSettingsHandler,
            "graphics": GraphicsSettingsHandler,
            "services": ServicesSettingsHandler,
            "tasks": TasksSettingsHandler,
            "memory": MemorySettingsHandler,
            "network": NetworkSettingsHandler,
            "visual": VisualSettingsHandler,
            "storage": StorageSettingsHandler,
            "audio": AudioSettingsHandler,
            "updates": UpdatesSettingsHandler,
        }

        handler_class = handler_map.get(category.lower())
        if not handler_class:
            raise ValueError(f"Unknown category: {category}")

        handler = handler_class()
        return handler.audit()
