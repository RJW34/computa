"""Configuration audit engine."""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from abso.core.models import Issue

if TYPE_CHECKING:
    from abso.settings.base import SettingsHandler

logger = logging.getLogger(__name__)


def _get_handlers() -> list[SettingsHandler]:
    """Return the audit handler set from the central registry."""
    from abso.core.handler_registry import get_audit_handlers

    return get_audit_handlers()


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

        # Check for problematic Windows updates (build-aware so superseded
        # regressions stay quiet on patched machines).
        try:
            from abso.core.kb_checker import (
                check_problematic_kbs,
                is_review_stale,
                list_review_staleness,
            )
            from abso.utils.os_release import detect_os_release

            release = detect_os_release()
            build_revision = (
                release.build_revision if release.build else None
            )
            bad_kbs = check_problematic_kbs(build_revision=build_revision)
            for kb in bad_kbs:
                if kb.fix_action == "install_kb" and kb.superseded_by:
                    optimal = f"Install {kb.superseded_by}"
                    remediation = (
                        f"Install {kb.superseded_by} (or a newer cumulative) "
                        f"to patch the regression."
                    )
                elif kb.fix_action == "advisory":
                    optimal = "No action required"
                    remediation = "Advisory only — surfaced for visibility."
                else:
                    optimal = f"Uninstall {kb.kb_id}"
                    remediation = (
                        "Run 'abso setup' or uninstall manually via Windows Update."
                    )
                all_issues.append(Issue(
                    title=f"Problematic update installed: {kb.kb_id} — {kb.title}",
                    severity=kb.severity,
                    current_value=f"{kb.kb_id} installed ({kb.affected})",
                    optimal_value=optimal,
                    explanation=(
                        f"This Windows update is known to cause: {kb.affected}. "
                        f"{remediation}"
                    ),
                    category="windows_update",
                ))
            if is_review_stale():
                days = list_review_staleness()
                all_issues.append(Issue(
                    title="KB known-bad list review is overdue",
                    severity="info",
                    current_value=f"Last reviewed {days} days ago",
                    optimal_value="Review within 60 days of each Patch Tuesday",
                    explanation=(
                        "ABSO's known-bad KB list has not been refreshed "
                        "recently. New cumulative-update regressions may not "
                        "yet be tracked."
                    ),
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
