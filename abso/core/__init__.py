"""Core package.

This initializer intentionally avoids eager imports. Several settings and
profile modules import small core submodules during startup, and importing the
profile applier from here would recursively initialize the profile catalog.
"""

from __future__ import annotations

from importlib import import_module
from typing import Any

_LAZY_EXPORTS = {
    "Issue": ("abso.core.models", "Issue"),
    "HardwareDetector": ("abso.core.detector", "HardwareDetector"),
    "ConfigurationAuditor": ("abso.core.auditor", "ConfigurationAuditor"),
    "ProfileApplier": ("abso.core.applier", "ProfileApplier"),
    "ApplyResult": ("abso.core.applier", "ApplyResult"),
    "BackupManager": ("abso.core.backup", "BackupManager"),
    "CapabilityEngine": ("abso.core.capabilities", "CapabilityEngine"),
    "CapabilityReport": ("abso.core.capabilities", "CapabilityReport"),
    "CapabilityFinding": ("abso.core.capabilities", "CapabilityFinding"),
    "ProfileLinter": ("abso.core.linter", "ProfileLinter"),
    "LintResult": ("abso.core.linter", "LintResult"),
    "LintIssue": ("abso.core.linter", "LintIssue"),
    "LintSeverity": ("abso.core.linter", "LintSeverity"),
    "RollbackGuard": ("abso.core.rollback_guard", "RollbackGuard"),
    "RollbackGuardResult": ("abso.core.rollback_guard", "RollbackGuardResult"),
    "RollbackViolation": ("abso.core.rollback_guard", "RollbackViolation"),
    "StabilityGate": ("abso.core.stability_gate", "StabilityGate"),
    "StabilityGateResult": ("abso.core.stability_gate", "StabilityGateResult"),
    "GateDecision": ("abso.core.stability_gate", "GateDecision"),
    "GatedSetting": ("abso.core.stability_gate", "GatedSetting"),
    "SettingClass": ("abso.core.stability_gate", "SettingClass"),
    "FallbackController": ("abso.core.fallback_controller", "FallbackController"),
    "FallbackState": ("abso.core.fallback_controller", "FallbackState"),
    "FailureRecord": ("abso.core.fallback_controller", "FailureRecord"),
    "NetworkScopeManager": ("abso.core.network_scope", "NetworkScopeManager"),
    "NetworkScope": ("abso.core.network_scope", "NetworkScope"),
    "NetworkScopeResult": ("abso.core.network_scope", "NetworkScopeResult"),
    "MultiMonitorDetector": ("abso.core.multimon_detector", "MultiMonitorDetector"),
    "MultiMonitorResult": ("abso.core.multimon_detector", "MultiMonitorResult"),
    "MultiMonitorWarning": ("abso.core.multimon_detector", "MultiMonitorWarning"),
    "DisplayEnvironment": ("abso.core.multimon_detector", "DisplayEnvironment"),
    "MonitorInfo": ("abso.core.multimon_detector", "MonitorInfo"),
}


def __getattr__(name: str) -> Any:
    """Lazily expose common core classes for compatibility."""
    try:
        module_name, attr_name = _LAZY_EXPORTS[name]
    except KeyError as exc:
        raise AttributeError(name) from exc

    value = getattr(import_module(module_name), attr_name)
    globals()[name] = value
    return value


__all__ = list(_LAZY_EXPORTS)
