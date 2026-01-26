"""Core modules for ABSO.

Includes validation subsystems:
- ProfileLinter: Static validation before apply
- RollbackGuard: Online netcode protection
- StabilityGate: Conditional aggressive settings
- NetworkScopeManager: Per-game network tuning
- MultiMonitorDetector: Compositor edge cases
- FallbackController: Failure persistence
"""

from abso.core.applier import ApplyResult, ProfileApplier
from abso.core.auditor import ConfigurationAuditor
from abso.core.backup import BackupManager
from abso.core.detector import HardwareDetector
from abso.core.fallback_controller import FallbackController, FallbackState, FailureRecord
from abso.core.linter import LintIssue, LintResult, LintSeverity, ProfileLinter
from abso.core.models import Issue
from abso.core.multimon_detector import (
    DisplayEnvironment,
    MonitorInfo,
    MultiMonitorDetector,
    MultiMonitorResult,
    MultiMonitorWarning,
)
from abso.core.network_scope import NetworkScope, NetworkScopeManager, NetworkScopeResult
from abso.core.rollback_guard import (
    RollbackGuard,
    RollbackGuardResult,
    RollbackViolation,
)
from abso.core.stability_gate import (
    GateDecision,
    GatedSetting,
    SettingClass,
    StabilityGate,
    StabilityGateResult,
)

__all__ = [
    # Core
    "Issue",
    "HardwareDetector",
    "ConfigurationAuditor",
    "ProfileApplier",
    "ApplyResult",
    "BackupManager",
    # Linter
    "ProfileLinter",
    "LintResult",
    "LintIssue",
    "LintSeverity",
    # RollbackGuard
    "RollbackGuard",
    "RollbackGuardResult",
    "RollbackViolation",
    # StabilityGate
    "StabilityGate",
    "StabilityGateResult",
    "GateDecision",
    "GatedSetting",
    "SettingClass",
    # FallbackController
    "FallbackController",
    "FallbackState",
    "FailureRecord",
    # NetworkScopeManager
    "NetworkScopeManager",
    "NetworkScope",
    "NetworkScopeResult",
    # MultiMonitorDetector
    "MultiMonitorDetector",
    "MultiMonitorResult",
    "MultiMonitorWarning",
    "DisplayEnvironment",
    "MonitorInfo",
]
