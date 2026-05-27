"""Static regression checks for tray PowerShell script compatibility."""

from __future__ import annotations

from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAY_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Tray.ps1"
ICONS_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Icons.ps1"
INSTALL_SCRIPT = REPO_ROOT / "abso" / "tray" / "Install-Startup.ps1"


def test_profiles_ordered_dictionary_uses_contains_not_contains_key() -> None:
    """PowerShell OrderedDictionary has Contains(), not ContainsKey()."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$script:Profiles.ContainsKey(" not in script


def test_same_active_profile_selection_is_verify_gated() -> None:
    """Tray clicking the selected active profile must avoid redundant apply."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$sameActiveProfile" in script
    assert "Complete-SameActiveProfileSelectionIfHandled" in script
    assert "using apply-pending instead of full apply" in script
    assert "already verifies active; skipping apply" in script
    assert 'Get-AbsoBackendArgs -CommandArgs @("reapply", "--json")' in script
    assert "using reapply instead of full apply" in script


def test_startup_restore_refreshes_last_profile_state() -> None:
    """Startup state-file adoption must not leave stale tray profile metadata."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Set-LastProfileState `" in script
    assert "Get-StartupRestoreStateSource -Source $stateSource" in script
    assert "-Source $restoreSource" in script


def test_tray_runs_read_only_state_verification() -> None:
    """Tray startup/apply status must verify state without applying profiles."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'Get-AbsoBackendArgs -CommandArgs @("state", "--json", "--verify")' in script
    assert "Refreshes the tray's read-only view" in script
    assert "Start-ActiveProfileVerificationTimer" in script
    assert "Start-ActiveProfileVerificationProcess" in script
    assert "Complete-ActiveProfileVerificationIfReady" in script
    assert "$proc.WaitForExit(20000)" not in script


def test_tray_prefers_installed_backend_before_source_python() -> None:
    """Deployed tray runtime should use installed abso.exe when present."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'AdaptiveBattleStationOptimizer\\abso.exe' in script
    assert "Prefer the installed packaged backend" in script
    assert "Get-AbsoBackendArgs" in script
    assert '$script:AbsoBackendArgsPrefix = @("-m", "abso")' in script
    assert "ABSO backend resolved" in script


def test_tray_surfaces_pending_apply_state() -> None:
    """Pending apply settings should be visible in tray status text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "ActiveProfilePendingApplySettings" in script
    assert "Get-ActiveProfilePendingApplyText" in script
    assert "Needs apply: $pendingApplyText" in script


def test_tray_exposes_targeted_apply_pending_action() -> None:
    """Elevated tray should expose the narrow pending-fix CLI path."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Apply-PendingProfileFixes" in script
    assert '"apply-pending", $script:activeProfile, "--json"' in script
    assert "Apply Pending Fix: $pendingApplyTextForAction" in script
    assert "without backup, baseline restore, or display reset" in script


def test_tray_manual_profile_apply_disables_backend_fallback() -> None:
    """A manual tray click must not silently commit a different fallback profile."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'Get-AbsoBackendArgs -CommandArgs @("apply", $ProfileId, "--json", "--no-fallback")' in script
    assert "Profile fallback applied: requested=$requestedProfileId actual=$appliedProfileId" in script


def test_tray_surfaces_reboot_pending_after_targeted_fix() -> None:
    """After a boot-gated pending fix, tray should show restart required."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "ActiveProfileStateRebootPending" in script
    assert "Get-ActiveProfileRebootPendingText" in script
    assert "Restart required: $rebootPendingText" in script
    assert "Restart required: $pendingText" in script


def test_apply_action_icon_is_defined() -> None:
    """The pending-fix menu item should not get a blank action icon."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    assert '"Apply" {' in script


def test_tray_command_file_is_limited_to_vetted_actions() -> None:
    """Tray automation should not become a generic elevated command runner."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Get-TrayCommandFilePath" in script
    assert "Invoke-TrayCommandFile" in script
    assert 'tray-command.json' in script
    assert '$command -notin @("apply_pending", "repair_startup")' in script
    assert "Apply-PendingProfileFixes -Force" in script
    assert "Repair-StartupRegistration -Force" in script


def test_tray_can_repair_startup_task_to_installed_assets() -> None:
    """Elevated tray should have a narrow self-repair for stale startup actions."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Get-InstalledAppRoot" in script
    assert "Get-InstalledTrayDir" in script
    assert "Get-InstalledStartupStatus" in script
    assert "Repair-StartupRegistration" in script
    assert '"Install-Startup.ps1"' in script
    assert '"-Install"' in script
    assert "task_action_path_current" in script


def test_profile_catalog_cache_write_skips_semantically_unchanged_content() -> None:
    """Tray should not dirty the tracked catalog cache for timestamp-only rewrites."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Profile catalog cache unchanged; skipping write" in script
    assert "Read-ProfileCatalogCacheEntries" in script
    assert "Read-ProfileAliasMapFromCache" in script
    assert "$existingProfilesJson -eq $newProfilesJson" in script
    assert "$existingAliasesJson -eq $newAliasesJson" in script
    assert 'saved_at = (Get-Date).ToString("o")' in script


def test_tray_backup_menu_uses_logical_backup_timestamp() -> None:
    """Copied backup folders should be sorted by manifest/ID time, not copy time."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-BackupTimestamp" in script
    assert "Prefer manifest `created_at`, then the timestamp-style directory name." in script
    assert '$mj.created_at' in script
    assert 'ParseExact($Directory.Name, "yyyy-MM-dd_HHmmss"' in script
    assert "Sort-Object Time -Descending" in script
    assert "Filesystem CreationTime is only a fallback" in script


def test_tray_writes_runtime_marker_for_health_staleness_checks() -> None:
    """Health should be able to prove whether live tray code matches disk."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Write-TrayRuntimeMarker" in script
    assert '"tray-runtime.json"' in script
    assert "script_hash_sha256" in script
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "Write-TrayRuntimeMarker" in script


def test_tray_display_pipeline_reset_requires_warning_confirmation() -> None:
    """Manual driver-reset recovery must not be one click from the tray."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '$resetDisplayItem.Text = "Reset Display Pipeline..."' in script
    assert "[System.Windows.Forms.MessageBox]::Show" in script
    assert "can blank or disconnect monitors for a few seconds" in script
    assert "[System.Windows.Forms.MessageBoxDefaultButton]::Button2" in script
    assert 'Get-AbsoBackendArgs -CommandArgs @("reset-display", "--method", "driver-hotkey", "--json")' in script


def test_startup_status_reports_actual_task_action_drift() -> None:
    """Startup status must expose the scheduled task action, not just intended paths."""
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "action_execute" in script
    assert "action_arguments" in script
    assert "action_path_current" in script
    assert "action_expected_launcher_path" in script
    assert "action_expected_vbs_path" in script
    assert "$taskInfo.action_path_current" in script
