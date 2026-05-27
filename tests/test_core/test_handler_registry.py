"""Tests for the unified handler registry.

The registry replaces the parallel handler lists that used to live in
``abso.core.auditor`` and ``abso.core.backup``. These tests pin the
contracts the rest of ABSO relies on:

* every handler returned is a SettingsHandler instance
* audit and backup contain the expected core families
* no entry is silently dropped from both audit and backup
* the critical-verify cache resolved from the registry contains the
  family we expect (Windows, Nvidia, Power, etc.)
"""

from __future__ import annotations

from abso.core.compliance import ComplianceEngine
from abso.core.handler_registry import (
    _all_entries,
    get_audit_handlers,
    get_backup_handlers,
)
from abso.settings.base import SettingsHandler


def test_every_entry_appears_in_at_least_one_set():
    """A handler with both flags False would be unreachable — guard against it."""
    for entry in _all_entries():
        assert entry.audit or entry.backup, (
            f"Handler {entry.factory.__name__} has both audit and backup False"
        )


def test_audit_handlers_are_settings_handler_instances():
    handlers = get_audit_handlers()
    assert handlers, "audit handler set is empty"
    for h in handlers:
        assert isinstance(h, SettingsHandler)


def test_backup_handlers_are_settings_handler_instances():
    handlers = get_backup_handlers()
    assert handlers, "backup handler set is empty"
    for h in handlers:
        assert isinstance(h, SettingsHandler)


def test_core_families_present_in_both_lists():
    """Windows / NVIDIA / Power / Registry sit in both factories."""
    audit_names = {type(h).__name__ for h in get_audit_handlers()}
    backup_names = {type(h).__name__ for h in get_backup_handlers()}
    for name in (
        "WindowsSettingsHandler",
        "NvidiaSettingsHandler",
        "PowerSettingsHandler",
        "RegistrySettingsHandler",
    ):
        assert name in audit_names, f"{name} missing from audit set"
        assert name in backup_names, f"{name} missing from backup set"


def test_profile_config_handlers_are_backup_only():
    """Per-game config handlers are backed up but never audited generically."""
    audit_names = {type(h).__name__ for h in get_audit_handlers()}
    backup_names = {type(h).__name__ for h in get_backup_handlers()}
    for name in (
        "Diablo4ConfigHandler",
        "OW2ConfigHandler",
        "Rivals2ConfigHandler",
        "FortniteConfigHandler",
        "MarvelRivalsConfigHandler",
    ):
        assert name in backup_names, f"{name} missing from backup set"
        assert name not in audit_names, f"{name} should be backup-only"


def test_diagnostics_and_vbs_optin_are_audit_only():
    audit_names = {type(h).__name__ for h in get_audit_handlers()}
    backup_names = {type(h).__name__ for h in get_backup_handlers()}
    assert "DiagnosticsSettingsHandler" in audit_names
    assert "DiagnosticsSettingsHandler" not in backup_names
    assert "VBSOptInHandler" in audit_names
    assert "VBSOptInHandler" not in backup_names


def test_compliance_critical_set_derived_from_registry():
    """ComplianceEngine.is_critical_verify-based set must include core families."""
    ComplianceEngine.invalidate_critical_handler_cache()
    critical = ComplianceEngine._resolve_critical_handler_names()
    for name in (
        "WindowsSettingsHandler",
        "NvidiaSettingsHandler",
        "PowerSettingsHandler",
        "RegistrySettingsHandler",
        "NetworkSettingsHandler",
        "MouseSettingsHandler",
        "GraphicsSettingsHandler",
        "ProcessPriorityHandler",
        "OW2ConfigHandler",
        "Rivals2ConfigHandler",
        "FortniteConfigHandler",
        "MarvelRivalsConfigHandler",
        "Diablo4ConfigHandler",
    ):
        assert name in critical, f"{name} should be critical-verify"


def test_compliance_critical_set_excludes_audit_only_handlers():
    """Diagnostic / opt-in handlers must NOT be critical."""
    ComplianceEngine.invalidate_critical_handler_cache()
    critical = ComplianceEngine._resolve_critical_handler_names()
    assert "DiagnosticsSettingsHandler" not in critical
    assert "VBSOptInHandler" not in critical
    assert "XboxModeSettingsHandler" not in critical
    assert "AIAgentsSettingsHandler" not in critical


def test_handler_entry_dataclass_is_immutable():
    """HandlerEntry is frozen so registries can't be mutated at runtime."""
    sample = _all_entries()[0]
    try:
        sample.audit = False  # type: ignore[misc]
    except Exception:
        return
    raise AssertionError("HandlerEntry should be frozen")
