"""Configuration audit engine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from gametune.core.models import Issue
from gametune.core.exceptions import SettingsAuditError

if TYPE_CHECKING:
    from gametune.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


def _get_handlers() -> list[SettingsHandler]:
    """Lazily import and instantiate settings handlers.

    This avoids circular import issues between core and settings modules.
    """
    from gametune.settings.windows import WindowsSettingsHandler
    from gametune.settings.power import PowerSettingsHandler
    from gametune.settings.registry import RegistrySettingsHandler
    from gametune.settings.nvidia import NvidiaSettingsHandler
    from gametune.settings.timer import TimerSettingsHandler
    from gametune.settings.mouse import MouseSettingsHandler
    from gametune.settings.graphics import GraphicsSettingsHandler
    from gametune.settings.services import ServicesSettingsHandler
    from gametune.settings.tasks import TasksSettingsHandler
    from gametune.settings.memory import MemorySettingsHandler
    from gametune.settings.network import NetworkSettingsHandler
    from gametune.settings.visual import VisualSettingsHandler
    from gametune.settings.storage import StorageSettingsHandler
    from gametune.settings.audio import AudioSettingsHandler
    from gametune.settings.updates import UpdatesSettingsHandler

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
        from gametune.settings.windows import WindowsSettingsHandler
        from gametune.settings.power import PowerSettingsHandler
        from gametune.settings.registry import RegistrySettingsHandler
        from gametune.settings.nvidia import NvidiaSettingsHandler
        from gametune.settings.timer import TimerSettingsHandler
        from gametune.settings.mouse import MouseSettingsHandler
        from gametune.settings.graphics import GraphicsSettingsHandler
        from gametune.settings.services import ServicesSettingsHandler
        from gametune.settings.tasks import TasksSettingsHandler
        from gametune.settings.memory import MemorySettingsHandler
        from gametune.settings.network import NetworkSettingsHandler
        from gametune.settings.visual import VisualSettingsHandler
        from gametune.settings.storage import StorageSettingsHandler
        from gametune.settings.audio import AudioSettingsHandler
        from gametune.settings.updates import UpdatesSettingsHandler

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
