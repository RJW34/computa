"""Static regression checks for tray PowerShell script compatibility."""

from __future__ import annotations

import ast
import json
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
TRAY_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Tray.ps1"
THEME_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Theme.ps1"
ICONS_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Icons.ps1"
NOTIFICATIONS_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Notifications.ps1"
INSTALL_SCRIPT = REPO_ROOT / "abso" / "tray" / "Install-Startup.ps1"
SETTINGS_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-Settings.ps1"
QUICK_PANEL_SCRIPT = REPO_ROOT / "abso" / "tray" / "ABSO-QuickPanel.ps1"
CATALOG_SCRIPT = REPO_ROOT / "abso" / "profiles" / "catalog.py"
CACHED_TRAY_CATALOG = REPO_ROOT / "abso" / "tray" / "profile-catalog-cache.json"
GAME_DETECTION_MANIFEST = REPO_ROOT / "abso" / "core" / "manifests" / "game_detection.json"
INTEGRATION_TEST_MATRIX = REPO_ROOT / "abso" / "core" / "manifests" / "integration_test_matrix.json"


def test_profiles_ordered_dictionary_uses_contains_not_contains_key() -> None:
    """PowerShell OrderedDictionary has Contains(), not ContainsKey()."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$script:Profiles.ContainsKey(" not in script


def test_tray_color_table_references_are_all_defined() -> None:
    """Every ``$script:Colors.<Key>`` reference must exist in the Colors table.

    Regression guard for the tray-startup crash where the display-topology
    icon referenced ``$script:Colors.AccentCyan`` — a key that was never
    defined. It resolved to ``$null``, and
    ``New-Object System.Drawing.SolidBrush($null)`` throws "a constructor was
    not found", which took down tray startup whenever a single-rate display
    made that icon branch render.
    """
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    match = re.search(r"\$script:Colors\s*=\s*@\{(.*?)\n\}", tray, re.DOTALL)
    assert match, "Could not locate the $script:Colors hashtable definition"
    defined = set(re.findall(r"^\s*([A-Za-z][A-Za-z0-9]*)\s*=", match.group(1), re.MULTILINE))
    # Sanity: the table actually parsed and carries known keys.
    assert {"AccentAmber", "AccentTeal", "Text"} <= defined, sorted(defined)

    # Hashtable members are not color keys (e.g. $script:Colors.Count).
    hashtable_members = {
        "Count", "Keys", "Values", "ContainsKey", "Contains", "Clone",
        "GetEnumerator", "Item", "Remove", "Add", "GetType",
    }
    # $script:Colors is dot-sourced into the sibling tray scripts, so check
    # references everywhere it is used, not just ABSO-Tray.ps1.
    referenced: set[str] = set()
    for path in (
        TRAY_SCRIPT, ICONS_SCRIPT, NOTIFICATIONS_SCRIPT, SETTINGS_SCRIPT, QUICK_PANEL_SCRIPT,
    ):
        if path.exists():
            referenced |= set(
                re.findall(r"\$script:Colors\.([A-Za-z][A-Za-z0-9]*)", path.read_text(encoding="utf-8"))
            )
    missing = sorted(referenced - defined - hashtable_members)
    assert not missing, f"$script:Colors references undefined keys: {missing}"
    assert "AccentCyan" not in referenced  # the specific bug stays fixed


def test_same_active_profile_selection_is_verify_gated() -> None:
    """Tray clicking the selected active profile must avoid redundant apply."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$sameActiveProfile" in script
    assert "Complete-SameActiveProfileSelectionIfHandled" in script
    assert "using apply-pending instead of full apply" in script
    assert "already verifies active; skipping apply" in script
    assert 'Get-AbsoBackendArgs -CommandArgs @("reapply", "--json")' in script
    assert "using reapply instead of full apply" in script


def test_same_active_profile_notices_keep_profile_visuals() -> None:
    """Already-active no-op notices should be profile-branded, not generic toasts."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    same_active_section = script.split("function Complete-SameActiveProfileSelectionIfHandled", 1)[1].split(
        "function Refresh-ActiveProfileVerificationState",
        1,
    )[0]

    assert "$sameActiveNoticeVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $Profile" in (
        same_active_section
    )
    assert "$profileTitle = Get-TrayProfileObjectDisplayName -Profile $Profile -Fallback $ProfileId" in (
        same_active_section
    )
    assert (
        'Show-Notification @sameActiveNoticeVisual -Title $profileTitle '
        '-Message "Already active. Windows restart required: $rebootText" -Type "Warning" -MetaText $ProfileId'
    ) in same_active_section
    assert (
        'Show-Notification @sameActiveNoticeVisual -Title $profileTitle '
        '-Message "Already active." -Type "Info" -MetaText $ProfileId'
    ) in same_active_section
    assert (
        'Show-Notification @sameActiveNoticeVisual -Title $profileTitle '
        '-Message "Verifying current profile before reapply." -Type "Info" -MetaText $ProfileId'
    ) in same_active_section
    assert 'Show-Notification -Title $Profile.Name -Message "Already active.' not in same_active_section
    assert '"Already active. Restart required: $rebootText"' not in same_active_section
    assert 'Show-Notification -Title $Profile.Name -Message "Verifying current profile before reapply."' not in (
        same_active_section
    )


def test_startup_restore_refreshes_last_profile_state() -> None:
    """Startup state-file adoption must not leave stale tray profile metadata."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Set-LastProfileState `" in script
    assert "Get-StartupRestoreStateSource -Source $stateSource" in script
    assert "-Source $restoreSource" in script
    assert "Startup restore selected active profile" in script
    assert "Startup restore selected no active profile" in script
    assert "Startup state loaded: $startupProfileName" not in script
    assert "Startup state loaded: no active profile" not in script
    assert "Startup restore [$($startupProfile.source)]" not in script


def test_tray_runs_read_only_state_verification_on_explicit_refresh() -> None:
    """Tray explicit/apply status paths must verify state without applying profiles."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'Get-AbsoBackendArgs -CommandArgs @("state", "--json", "--verify")' in script
    assert "Refreshes the tray's read-only view" in script
    assert "Test-ActiveProfileVerificationInFlight" in script
    assert "coalescing refresh request" in script
    assert "Start-ActiveProfileVerificationTimer" in script
    assert "Start-ActiveProfileVerificationProcess" in script
    assert "Complete-ActiveProfileVerificationIfReady" in script
    assert "$proc.WaitForExit(20000)" not in script


def test_tray_defers_startup_profile_verification() -> None:
    """Tray startup must not spawn display/NVIDIA verifier readback automatically."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    startup_section = script.split("# Only play restart sound once the new tray instance has fully initialized.", 1)[1].split(
        "# Narrow one-shot command file used by local automation",
        1,
    )[0]

    assert "Startup profile verification deferred" in startup_section
    assert "Start-ActiveProfileVerificationTimer" not in startup_section


def test_launch_sanitizer_sweep_does_not_block_ui_thread() -> None:
    """Runtime launch-sweep should be single-flight and poll-based."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Start-LaunchSweepCliProcess" in script
    assert "Complete-LaunchSweepIfReady" in script
    assert "Test-LaunchSweepInFlight" in script
    assert "sweep already running; skipping duplicate tick" in script
    launch_section = script.split("function Start-LaunchSweepCliProcess", 1)[1].split(
        "function Invoke-LaunchSanitizerTick", 1
    )[0]
    assert '"launch-sweep", $ProfileId, "--json"' in launch_section
    assert "-Wait" not in launch_section
    assert "System.Windows.Forms.Timer" in launch_section


def test_launch_sanitizer_toast_uses_triggering_profile_visuals() -> None:
    """Launch sanitizer success toast should identify the protected game profile."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    sanitizer_section = script.split("function Apply-LaunchSweepPayload", 1)[1].split(
        "function Complete-LaunchSweepIfReady",
        1,
    )[0]

    assert "$sanitizerProfile = $null" in sanitizer_section
    assert "$script:Profiles.Contains($ProfileId)" in sanitizer_section
    assert "$sanitizerProfile = $script:Profiles[$ProfileId]" in sanitizer_section
    assert (
        "$sanitizerVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId "
        "-Profile $sanitizerProfile -ActiveBadge"
    ) in sanitizer_section
    assert "$sanitizerTitle = if ($sanitizerProfile) {" in sanitizer_section
    assert "Get-TrayProfileDisplayName -ProfileId $ProfileId" in sanitizer_section
    assert '"A.B.S.O. Launch Sanitizer"' in sanitizer_section
    assert (
        'Show-Notification @sanitizerVisual -Title $sanitizerTitle `\n'
        '                -Message "Launch sanitizer stopped: $summary" `\n'
        '                -Type "Success" `\n'
        "                -MetaText $ProfileId"
    ) in sanitizer_section
    assert 'Show-Notification -Title "A.B.S.O. Launch Sanitizer"' not in sanitizer_section
    assert '-Message "Stopped: $summary"' not in sanitizer_section


def test_tray_audit_action_does_not_block_ui_thread() -> None:
    """Read-only tray audit should not freeze the menu while the CLI runs."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Test-AuditInFlight" in script
    assert "Complete-AuditIfReady" in script
    assert "Audit is already running." in script
    audit_section = script.split("function Run-Audit", 1)[1].split(
        "function Open-BackupsFolder", 1
    )[0]
    assert 'Get-AbsoBackendArgs -CommandArgs @("audit", "--json")' in audit_section
    assert "-Wait" not in audit_section
    assert "System.Windows.Forms.Timer" in audit_section


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
    assert '$pendingStatusLabel = if ($statusIsVerificationMismatch) { "Profile mismatch" } else { "Pending profile fix" }' in script
    assert 'Add-UniqueTrayMessage -Target $statusParts -Message "${pendingStatusLabel}: $pendingApplyText"' in script


def test_tray_surfaces_verification_mismatch_state() -> None:
    """Generic verifier mismatches should be visible after silent startup checks."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    pending_section = script.split("function Get-ActiveProfilePendingApplyText", 1)[1].split(
        "function Get-ActiveProfileRebootPendingText",
        1,
    )[0]
    verify_section = script.split("function Apply-ActiveProfileVerificationJson", 1)[1].split(
        "function Start-ActiveProfileVerificationProcess",
        1,
    )[0]
    same_active_section = script.split("function Complete-SameActiveProfileSelectionIfHandled", 1)[1].split(
        "function Refresh-ActiveProfileVerificationState",
        1,
    )[0]
    menu_state_section = script.split("if ($script:applyPendingItem) {", 1)[1].split(
        "Restore-TrayTooltipFromState",
        1,
    )[0]

    assert '"pending_apply", "mismatch"' in pending_section
    assert '$script:ActiveProfileVerificationStatus -eq "mismatch"' in pending_section
    assert "Active profile verification mismatch: $pendingText" in verify_section
    assert 'Profile mismatch: $pendingText' in verify_section
    assert '$script:ActiveProfileVerificationStatus -ne "mismatch"' in same_active_section
    assert '$lastActionText.StartsWith("Profile mismatch:")' in script
    assert 'return "A.B.S.O. - Profile mismatch: $profileName"' in script
    assert 'return "Active state: profile mismatch for $pendingText"' in script
    assert "Apply-PendingProfileFixes routing mismatch" in script
    assert "Reapply Active Profile: $pendingApplyTextForAction" in menu_state_section
    assert "Verifier mismatch: $pendingApplyTextForAction" in menu_state_section
    assert '"PROFILE MISMATCH"' in menu_state_section


def test_tray_exposes_targeted_apply_pending_action() -> None:
    """Elevated tray should expose the narrow pending-fix CLI path."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "Apply-PendingProfileFixes" in script
    assert '"apply-pending", $script:activeProfile, "--json"' in script
    assert "Apply Pending Fixes: $pendingApplyTextForAction" in script
    assert "No backup, baseline restore, or display reset" in script


def test_apply_pending_menu_tooltip_reports_current_fix_scope() -> None:
    """Pending-fix menu tooltip should not stay generic after a verifier mismatch appears."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    update_section = script.split("if ($script:applyPendingItem) {", 1)[1].split(
        "Restore-TrayTooltipFromState",
        1,
    )[0]
    creation_section = script.split("# Apply Pending Fixes - targeted verifier remediation", 1)[1].split(
        "$actionsMenu.DropDownItems.Add($script:applyPendingItem)",
        1,
    )[0]
    assert '$script:applyPendingItem.ToolTipText = "No verifier-reported pending fixes for the active profile"' in creation_section
    assert (
        '$script:applyPendingItem.ToolTipText = "Targeted verifier fix: $pendingApplyTextForAction. No backup, baseline restore, or display reset."'
        in update_section
    )
    assert "$pendingFixCheckingText = Get-ActiveProfileVerificationInProgressText" in update_section
    assert '$script:applyPendingItem.Visible = ($script:applyPendingItem.Enabled -or $pendingFixChecking)' in update_section
    assert '$script:applyPendingItem.Text = "Checking Pending Fixes"' in update_section
    assert (
        '$script:applyPendingItem.ToolTipText = "Verifier is reading current settings; pending fixes will appear here if found."'
        in update_section
    )
    assert '$script:applyPendingItem.AccessibleDescription = "PENDING FIXES"' in update_section
    assert '$script:applyPendingItem.AccessibleDescription = "PROFILE MISMATCH"' in update_section
    assert '$script:applyPendingItem.AccessibleDescription = "CHECKING PENDING FIXES"' in update_section
    assert '$script:applyPendingItem.AccessibleDescription = "NO PENDING FIXES"' in update_section
    assert 'Set-MenuItemImageSafe -Item $script:applyPendingItem -NewImage (New-ActionBitmap -Action "PendingFix" -Color $script:Colors.AccentAmber)' in update_section
    assert 'Set-MenuItemImageSafe -Item $script:applyPendingItem -NewImage (New-ActionBitmap -Action "PendingFix" -Color $script:Colors.AccentBlue)' in update_section
    assert 'Set-MenuItemImageSafe -Item $script:applyPendingItem -NewImage (New-ActionBitmap -Action "PendingFix" -Color $script:Colors.TextDisabled)' in update_section
    assert '$script:applyPendingItem.Image = New-ActionBitmap -Action "PendingFix" -Color $script:Colors.TextDisabled' in creation_section
    assert '$script:applyPendingItem.Image = New-ActionBitmap -Action "Apply" -Color $script:Colors.AccentAmber' not in creation_section
    assert "$pendingRepairScope" not in update_section
    assert "Apply verifier-reported pending fixes without backup, baseline restore, or display reset" not in creation_section


def test_tray_manual_profile_apply_disables_backend_fallback() -> None:
    """A manual tray click must not silently commit a different fallback profile."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'Get-AbsoBackendArgs -CommandArgs @("apply", $ProfileId, "--json", "--no-fallback")' in script
    assert "Profile fallback applied: requested=$requestedProfileId actual=$appliedProfileId" in script


def test_missing_backend_exit_code_is_reported_plainly() -> None:
    """Failure messages should say the exit code was not reported, not unavailable."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    descriptor_section = script.split("function Get-ExitCodeDescriptor", 1)[1].split(
        "function Format-TrayUserFacingText",
        1,
    )[0]

    assert 'return "not reported"' in descriptor_section
    assert 'return "unavailable"' not in descriptor_section
    assert "exit code: $(Get-ExitCodeDescriptor -ExitCode $ExitCode)" in script
    assert "exit code: $(Get-ExitCodeDescriptor -ExitCode $exitCode)" in script


def test_tray_profile_copy_normalizes_gsync_typography() -> None:
    """Tray profile names should not leak stale GSYNC typography from cache/fallback data."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Format-TrayDisplayCopy" in script
    assert "'(?i)\\bG[\\s_-]?SYNC\\b'" in script
    assert "'G-SYNC'" in script
    assert "return (Format-TrayDisplayCopy -Text $friendly)" in script
    assert '$fallbackProfile[$copyField] = Format-TrayDisplayCopy -Text "$($fallbackProfile[$copyField])"' in script
    assert "$name = Format-TrayDisplayCopy -Text $rawName" in script
    assert "$sub = Format-TrayDisplayCopy -Text $rawSub" in script
    assert "$desc = Format-TrayDisplayCopy -Text $rawDesc" in script
    assert "$groupName = Format-TrayDisplayCopy -Text $rawGroupName" in script
    assert "$variant = Format-TrayDisplayCopy -Text $rawVariant" in script
    assert 'return "$($profile.Name)"' not in script


def test_profile_apply_timeout_toast_keeps_profile_visuals() -> None:
    """Apply timeout error should identify the profile that was being applied."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    apply_section = script.split("function Apply-Profile", 1)[1].split(
        "function Apply-PendingProfileFixes",
        1,
    )[0]
    timeout_section = apply_section.split('Write-TrayLog "Apply-Profile timed out after 120s', 1)[1].split(
        "return",
        1,
    )[0]

    assert "$timeoutVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $profile" in (
        timeout_section
    )
    assert "$profileTitle = Get-TrayProfileObjectDisplayName -Profile $profile -Fallback $ProfileId" in apply_section
    assert "$timeoutTitle = $profileTitle" in timeout_section
    assert (
        'Show-Notification @timeoutVisual -Title $timeoutTitle '
        '-Message "Apply timed out after 120s" -Type "Error" -MetaText $ProfileId'
    ) in timeout_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Apply timed out after 120s"' not in timeout_section
    assert 'Set-TrayLastAction -Message "Apply timed out after 120s"' in timeout_section


def test_profile_apply_failure_names_failed_action() -> None:
    """Profile apply failures should use the plain-English not-applied body."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    apply_section = script.split("function Apply-Profile", 1)[1].split(
        "function Apply-PendingProfileFixes",
        1,
    )[0]
    failure_section = apply_section.split('Write-TrayLog "Profile apply failed: $err"', 1)[1].split(
        "Update-MenuState",
        1,
    )[0]

    assert "Convert-ApplyFailureTextToPlainEnglish" in script
    assert 'Show-Notification @failureVisual -Title $failureTitle -Message $err' in failure_section
    assert "$script:LastAction = $err" in failure_section
    assert "Not applied.$restoredPrefix Add $exe to NVIDIA profile" in script
    assert 'Show-Notification @failureVisual -Title $failureTitle -Message "Apply failed: $err"' not in (
        failure_section
    )
    assert '$script:LastAction = "Apply failed: $err"' not in failure_section
    assert '-Message "Failed: $err"' not in failure_section
    assert '$script:LastAction = "Failed: $err"' not in failure_section


def test_tray_surfaces_reboot_pending_after_targeted_fix() -> None:
    """After a boot-gated pending fix, tray should show a Windows restart warning."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "ActiveProfileStateRebootPending" in script
    assert "function Set-ActiveProfileVerificationSeedFromApplyData" in script
    assert "Get-ActiveProfileRebootPendingText" in script
    assert "Format-TrayUserFacingText" in script
    assert '"GraphicsSettingsHandler" = "Graphics settings"' in script
    assert '"GraphicsSettingsHandler.mpo_disabled" = "Graphics settings (MPO)"' in script
    assert '$script:ActiveProfileVerificationStatus -eq "active"' in script
    assert '$script:ActiveProfileVerificationStatus = "pending_reboot"' in script
    assert '$script:ActiveProfileVerificationStatus = "active"' in script
    assert '$script:ActiveProfileStateRebootReasons = @("profile changes")' in script
    assert '$pendingApplyAfter = @($Data.pending_apply_settings_after)' in script
    assert '$pendingRebootAfter = @($Data.pending_reboot_gated_settings_after)' in script
    assert '$requiresReboot = [bool]$Data.requires_reboot' in script
    assert "Windows restart required: $rebootPendingText" in script
    assert "Windows restart required: $pendingText" in script
    assert "Pending profile fixes applied: $pendingText. Windows restart required." in script
    assert "Windows restart required to take full effect" in script
    assert "Pending fix applied: $pendingText. Restart required." not in script
    assert "Restart required to take full effect" not in script


def test_apply_success_seeds_verifier_state_before_menu_surfaces_refresh() -> None:
    """Apply success should not show previous-profile restart/apply state while verifier catches up."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    apply_success_section = script.split("if ($applySucceeded) {", 1)[1].split(
        "else {\n            $err = Get-ApplyFailureMessage",
        1,
    )[0]

    assert "$script:activeProfile = $appliedProfileId" in apply_success_section
    assert "Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data" in apply_success_section
    assert (
        apply_success_section.index("Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data")
        < apply_success_section.index("Update-MenuState")
    )
    assert (
        apply_success_section.index("Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data")
        < apply_success_section.index("Update-QuickPanel")
    )
    assert (
        apply_success_section.index("Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data")
        < apply_success_section.index("Start-ActiveProfileVerificationTimer -DelayMilliseconds 500")
    )


def test_apply_success_surfaces_post_apply_manual_notes() -> None:
    """Apply success toast should surface profile-specific manual game steps."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    apply_success_section = script.split("if ($applySucceeded) {", 1)[1].split(
        "else {\n            $err = Get-ApplyFailureMessage",
        1,
    )[0]

    assert "function Get-ApplyPostApplyNoteMessages" in script
    assert "$Json.data.post_apply_notes" in script
    assert "$applyPostApplyNotes = Get-ApplyPostApplyNoteMessages -Json $json" in (
        apply_success_section
    )
    assert '$extras += ("Manual: " + $applyPostApplyNotes[0])' in apply_success_section
    assert 'Write-TrayLog "Apply manual note [$appliedProfileId]: $note"' in (
        apply_success_section
    )


def test_apply_notifications_support_allowlisted_manual_action_buttons() -> None:
    """Manual post-apply steps should expose safe toast buttons when possible."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    apply_success_section = tray.split("if ($applySucceeded) {", 1)[1].split(
        "else {\n            $err = Get-ApplyFailureMessage",
        1,
    )[0]
    apply_failure_section = tray.split("else {\n            $err = Get-ApplyFailureMessage", 1)[1].split(
        "catch {",
        1,
    )[0]

    assert "[object[]]$ActionButtons = @()" in notifications
    assert "$toastActions = @($ActionButtons" in notifications
    assert "Invoke-TrayToastAction -Action $s.Tag" in notifications
    assert "-ActionButtons @($q.ActionButtons)" in notifications
    assert "function Get-ApplyManualActionButtons" in tray
    assert "function Get-ApplyFailureActionButtons" in tray
    assert "function Invoke-TrayToastAction" in tray
    assert '"open_nvidia_profile_inspector"' in tray
    assert '"open_nvidia_control_panel"' in tray
    assert '"copy_text"' in tray
    assert '"open_windows_settings"' in tray
    assert "$applyActionButtons = Get-ApplyManualActionButtons -Json $json" in apply_success_section
    assert apply_success_section.count("-ActionButtons @($applyActionButtons)") >= 7
    assert "$failureActionButtons = Get-ApplyFailureActionButtons -Message $err -Json $json" in apply_failure_section
    assert "-ActionButtons @($failureActionButtons)" in apply_failure_section
    assert "Start-Process -FilePath \"$uri\"" in tray
    assert 'if (-not [string]::IsNullOrWhiteSpace($uri) -and "$uri" -like "ms-settings:*")' in tray


def test_apply_success_warnings_are_plain_english() -> None:
    """Apply warning toasts should show actionable user steps, not raw backend proof text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    warning_section = script.split("function Get-ApplyWarningMessages", 1)[1].split(
        "function Get-ApplyNoticeMessages",
        1,
    )[0]

    assert "function Convert-ApplyWarningTextToPlainEnglish" in script
    assert "Convert-ApplyWarningTextToPlainEnglish -Message \"$warning\"" in warning_section
    assert "Convert-ApplyWarningTextToPlainEnglish -Message \"$($checkpoint.message)\"" in (
        warning_section
    )
    assert "Manual NVIDIA step: Add $exe to NVIDIA profile '$profile' in NVIDIA Control Panel" in (
        script
    )
    assert 'return $null' in script
    assert 'Add-UniqueTrayMessage -Target $messages -Message "$warning"' not in warning_section


def test_apply_pending_success_seeds_verifier_state_before_menu_refresh() -> None:
    """Apply-pending success should clear stale pending-fix UI immediately."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    pending_success_section = script.split("function Apply-PendingProfileFixes", 1)[1].split(
        "catch {\n        Close-ProgressOverlay",
        1,
    )[0]
    pending_success_section = pending_success_section.split("Close-ProgressOverlay", 1)[1]

    assert "Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data" in pending_success_section
    assert (
        pending_success_section.index("Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data")
        < pending_success_section.index("Show-TrayToast @pendingToastVisual")
    )
    assert (
        pending_success_section.index("Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data")
        < pending_success_section.index('Show-Notification @pendingToastVisual -Title $pendingTitle -Message "No pending profile fix was needed"')
    )
    assert (
        pending_success_section.index("Set-ActiveProfileVerificationSeedFromApplyData -Data $json.data")
        < pending_success_section.index("Update-MenuState")
    )


def test_tray_verification_clears_stale_pending_last_action() -> None:
    """A clean verifier result should replace stale pending-fix/restart action text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '$script:ActiveProfileVerificationStatus -eq "active"' in script
    assert "function Normalize-TrayLastActionMessage" in script
    assert 'return "Windows restart required: $($Matches[1].Trim())"' in script
    assert 'return "Pending profile fix: $($Matches[1].Trim())"' in script
    assert '$lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction' in script
    assert '$lastActionText.StartsWith("Pending profile fix:")' in script
    assert '$lastActionText.StartsWith("Windows restart required:")' in script
    assert '$lastActionText.StartsWith("Restart required:")' not in script
    assert 'Write-TrayLog "Active profile now verifies clean; replacing stale verifier action' in script
    assert '$script:LastAction = "Verified active: $activeName"' in script


def test_tray_verification_failure_replaces_stale_verifying_action_only() -> None:
    """Verifier failures should not leave a user-triggered Verifying status stuck forever."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Set-ActiveProfileVerificationFailureAction" in script
    failure_section = script.split("function Set-ActiveProfileVerificationFailureAction", 1)[1].split(
        "function Set-ActiveProfileVerificationUnavailableAction",
        1,
    )[0]
    assert '$lastActionText.StartsWith("Verifying:")' in failure_section
    assert '$failureReason = if ([string]::IsNullOrWhiteSpace($Reason)) { "reason not reported" } else { $Reason.Trim() }' in failure_section
    assert 'Set-TrayLastAction -Message "Verify failed: $failureReason"' in failure_section
    assert 'else { "unknown error" }' not in failure_section
    assert '$lastActionText.StartsWith("Needs apply:")' not in failure_section
    assert '$lastActionText.StartsWith("Pending profile fix:")' not in failure_section
    assert '$lastActionText.StartsWith("Windows restart required:")' not in failure_section
    assert '$lastActionText.StartsWith("Restart required:")' not in failure_section
    assert 'Set-ActiveProfileVerificationFailureAction -Reason "$($_.Exception.Message)"' in script


def test_tray_ignored_verification_clears_stale_restart_state() -> None:
    """Ignored verifier results must not leave stale restart/apply warnings in tray UI."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Set-ActiveProfileVerificationUnavailableAction" in script
    unavailable_section = script.split(
        "function Set-ActiveProfileVerificationUnavailableAction", 1
    )[1].split("function Stop-ActiveProfileVerificationRuntime", 1)[0]
    assert '$lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction' in unavailable_section
    assert '$lastActionText.StartsWith("Pending profile fix:")' in unavailable_section
    assert '$lastActionText.StartsWith("Windows restart required:")' in unavailable_section
    assert '$lastActionText.StartsWith("Restart required:")' not in unavailable_section
    assert '$statusPrefix = if ($cleanReason -in @("profile changed", "not current")) {' in unavailable_section
    assert '"Verification not current"' in unavailable_section
    assert '"Verification status not reported"' in unavailable_section
    assert 'Set-TrayLastAction -Message "${statusPrefix}: $cleanReason"' in unavailable_section
    assert '"Verification unavailable: $cleanReason"' not in unavailable_section

    verify_section = script.split("function Apply-ActiveProfileVerificationJson", 1)[1].split(
        "function Start-ActiveProfileVerificationProcess", 1
    )[0]
    assert 'Write-TrayLog "State verification returned no verification block" -Level "WARN"' in verify_section
    assert 'Set-ActiveProfileVerificationUnavailableAction -Reason "missing verifier data"' in verify_section
    assert 'Write-TrayLog "State verification returned no verification status" -Level "WARN"' in verify_section
    assert 'Set-ActiveProfileVerificationUnavailableAction -Reason "missing verifier status"' in verify_section
    assert 'else { "unknown" }' not in verify_section
    assert (
        'Write-TrayLog "State verification profile \'$verifiedProfile\' does not match tray active profile '
        "'$script:activeProfile'\" -Level \"WARN\""
    ) in verify_section
    assert 'Set-ActiveProfileVerificationUnavailableAction -Reason "profile changed"' in verify_section
    assert verify_section.count("Reset-ActiveProfileVerificationState") >= 2


def test_tray_user_status_replaces_raw_handler_identifiers() -> None:
    """Frequent tray surfaces should not leak backend handler class names."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$normalized = Format-TrayUserFacingText -Text $Message" in script
    assert 'return (Format-TrayUserFacingText -Text "$($reasons[0])")' in script
    assert 'return (Format-TrayUserFacingText -Text "$($pending[0])")' in script
    assert "$friendlyHandlers = @($FailedHandlers | ForEach-Object { Format-TrayUserFacingText -Text \"$_\" })" in script
    assert '-Message "Failed settings: $($friendlyHandlers -join \', \')"' in script
    assert 'return "Failed settings: $($friendlyHandlers -join \', \')"' not in script
    assert '"Handler failures: $($FailedHandlers -join \', \')"' not in script


def test_settings_default_profile_label_does_not_claim_auto_apply() -> None:
    """The default profile is a startup reminder, not an automatic apply."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    assert "Default Profile (startup reminder):" in script
    assert "Default Profile (apply on startup):" not in script


def test_tray_about_hotkeys_report_actual_registration_status() -> None:
    """About/settings copy should not imply configured hotkeys are definitely active."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    settings = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    assert '-Text "HOTKEYS" `' in settings
    assert "CONFIGURED HOTKEYS" not in settings
    assert "$script:HotkeyRegistrationStatus = @{}" in settings
    assert "function Get-HotkeyRegistrationSummaryText" in settings
    assert "function Get-HotkeyRegistrationChipInfo" in settings
    assert "function Get-HotkeyActionDisplayName" in settings
    assert 'return "Action not reported"' in settings
    assert 'return "Unknown Action"' not in settings
    assert "function New-HotkeyStatusChipLabel" in settings
    assert '$hk1Status = New-HotkeyStatusChipLabel -Name "openMenu"' in settings
    assert '$hk2Status = New-HotkeyStatusChipLabel -Name "restore"' in settings
    assert "Restore hotkey requires an active profile." in settings
    assert '"ACTIVE"' in settings
    assert '"BLOCKED"' in settings
    assert '"INVALID"' in settings
    assert '"CONFIG"' in settings
    assert "not registered this session" in settings
    assert "unavailable: $reason$restoreContext" in settings
    assert '"reason not reported"' in settings
    assert '"not available"' not in settings
    assert "Windows or another app is using it" in settings
    assert '$script:HotkeysRegistered = ($script:HotkeyActions.Count -gt 0)' in settings
    assert "Restore Previous Settings" in settings
    assert "$hotkeyRegistration = Register-GlobalHotkeys" in tray
    assert "Global hotkeys active: $($hotkeyRegistration.Active)/$($hotkeyRegistration.Total)" in tray
    assert "Global hotkeys partially active: $($hotkeyRegistration.Active)/$($hotkeyRegistration.Total)" in tray
    assert "No global hotkeys active; configured keys may be unavailable" in tray
    assert "function Show-AboutPanel" in tray
    assert "$hotkeyText = Get-HotkeyRegistrationSummaryText -Config $script:TrayConfig" in tray
    assert "$aboutItem.Add_Click({ Show-AboutPanel })" in tray
    assert "No active profile to restore. Apply a profile first." in tray
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "No active profile to restore. Apply a profile first." '
        '-Type "Info" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber'
    ) in tray
    assert 'Set-TrayLastAction -Message "Restore hotkey ignored: no active profile"' in tray
    assert "Global hotkeys registered" not in tray
    assert "$($script:TrayConfig.hotkeys.openMenu) - Open Menu" not in tray


def test_tray_about_uses_branded_panel_not_messagebox() -> None:
    """About should use the tray visual system and accurate no-auto-apply copy."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    about_section = script.split("function Show-AboutPanel", 1)[1].split(
        "# ============================================================================\n# MAIN",
        1,
    )[0]
    about_menu_section = script.split("# About", 1)[1].split(
        "# Exit",
        1,
    )[0]

    assert "$script:AboutForm = $null" in script
    assert "falling back to a generic MessageBox" in about_section
    assert "$script:AboutForm.BringToFront()" in about_section
    assert "$form.Size = New-Object System.Drawing.Size(430, 398)" in about_section
    assert "$header.Add_Paint({" in about_section
    assert "$orbitStart = ($frame * 8) % 360" in about_section
    assert "$g.DrawArc($orbitPen, 12, 9, 48, 48, $orbitStart, 88)" in about_section
    assert "$sweepX = 72 + (($frame * 7) % [Math]::Max(1, $s.Width - 150))" in about_section
    assert '$brandBox.Image = New-ActionBitmap -Action "Brand" -Color $script:Colors.AccentGold' in about_section
    assert '$roleLabel.Text = "Tray control surface"' in about_section
    assert (
        '$truthLabel.Text = "Profiles apply only from explicit tray actions. Startup profile is a reminder, not an automatic apply."'
        in about_section
    )
    assert "$truthStrip = New-Object System.Windows.Forms.Panel" in about_section
    assert "$truthStrip.Location = New-Object System.Drawing.Point(24, 170)" in about_section
    assert "$truthStrip.Size = New-Object System.Drawing.Size(364, 46)" in about_section
    assert "$truthStrip.Add_Paint({" in about_section
    assert "$sweepX = 10 + (($frame * 5) % [Math]::Max(1, $s.Width - 42))" in about_section
    assert '$applyTruthIcon.Image = New-ActionBitmap -Action "Apply" -Color $script:Colors.AccentGreen' in about_section
    assert '$applyTruthLabel.Text = "Explicit apply"' in about_section
    assert '$startupTruthIcon.Image = New-ActionBitmap -Action "Startup" -Color $script:Colors.AccentGold' in about_section
    assert '$startupTruthLabel.Text = "Reminder only"' in about_section
    assert '$hotkeyTruthIcon.Image = New-ActionBitmap -Action "Hotkey" -Color $script:Colors.AccentBlue' in about_section
    assert '$hotkeyTruthLabel.Text = "Session state"' in about_section
    assert "$aboutTruthPulseTimer = New-Object System.Windows.Forms.Timer" in about_section
    assert "$aboutTruthPulseTimer.Interval = 115" in about_section
    assert "$aboutTruthPulseTimer.Tag = $truthStrip" in about_section
    assert 'try { $aboutTruthPulseTimer.Stop() } catch {}' in about_section
    assert 'try { $aboutTruthPulseTimer.Dispose() } catch {}' in about_section
    assert "$hotkeyLabel.Text = $hotkeyText" in about_section
    assert "$hotkeyLabel.Location = New-Object System.Drawing.Point(24, 232)" in about_section
    assert "$hotkeyLabel.Size = New-Object System.Drawing.Size(364, 76)" in about_section
    assert "$closeBtn.Location = New-Object System.Drawing.Point(302, 312)" in about_section
    assert '$closeBtn.Image = New-ActionBitmap -Action "Close" -Color $script:Colors.TextDim' in about_section
    assert 'foreach ($control in @($brandBox, $infoBox, $closeBtn, $applyTruthIcon, $startupTruthIcon, $hotkeyTruthIcon))' in about_section
    assert "Apply-DwmWindowEffects -Form $form -CornerStyle 2 -BorderColorRGB @(0, 245, 212)" in about_section
    assert "[System.Windows.Forms.MessageBox]::Show" not in about_section
    assert "$aboutItem.Add_Click({ Show-AboutPanel })" in about_menu_section
    assert "[System.Windows.Forms.MessageBox]::Show" not in about_menu_section


def test_settings_default_profile_preview_uses_game_marks_and_truthful_copy() -> None:
    """Settings should visually confirm the reminder profile without implying auto-apply."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    assert "function Set-SettingsProfilePreview" in script
    assert "function Get-SettingsProfileGameGroup" in script
    assert "function Get-SettingsProfileModeBadge" in script
    assert "function Get-SelectedDefaultProfileId" in script
    assert "function Get-SettingsProfileDisplayName" in script
    assert "function Set-SettingsPreviewPanelState" in script
    assert "function New-SettingsPreviewMedallionBitmap" in script
    assert "Wraps the reminder-profile mark in a compact settings medallion" in script
    assert "New-GameBitmap -GameGroup $gameGroup" in script
    assert "New-FavoriteGameBitmap `" in script
    assert "New-GameSyncBadgeBitmap `" in script
    assert "$modeBadge = Get-SettingsProfileModeBadge -ProfileId $ProfileId -Profile $profile -Variant $variant" in script
    assert '$favoriteBadge = (@($Config.favorites) | ForEach-Object { "$_" }) -contains "$ProfileId"' in script
    assert "-SyncMode \"agnostic\" `" in script
    assert "-ModeBadge $modeBadge" in script
    assert '$mark = New-GameBitmap -GameGroup "productivity" -Color $neutralColor -Category "Desktop"' in script
    assert '$mark = New-CategoryBitmap -Category "Desktop" -Color $neutralColor' not in script
    assert '$mark = New-ActionBitmap -Action "Startup" -Color $neutralColor' in script
    assert "$mark = New-GameBitmap -GameGroup $gameGroup -Color $catColor -Category $cat" in script
    assert "$IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $catColor" in script
    assert "$IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $neutralColor" in script
    assert 'Set-SettingsPreviewPanelState -PreviewPanel $PreviewPanel -Color $neutralColor -State "none"' in script
    assert 'Set-SettingsPreviewPanelState -PreviewPanel $PreviewPanel -Color $neutralColor -State "missing"' in script
    assert "Set-SettingsPreviewPanelState -PreviewPanel $PreviewPanel -Color $catColor -State $previewState" in script
    assert "$PreviewPanel.Tag = @{" in script
    assert "State = if ([string]::IsNullOrWhiteSpace($State)) { \"reminder\" } else { \"$State\" }" in script
    assert "$missingName = Get-SettingsProfileDisplayName -ProfileId $ProfileId" in script
    assert "$NameLabel.Text = $missingName" in script
    assert '$MetaLabel.Text = "Not in the current profile list"' in script
    assert "$gameGroup = Get-SettingsProfileGameGroup -ProfileId $ProfileId -Profile $null" in script
    assert "$modeBadge = Get-SettingsProfileModeBadge -ProfileId $ProfileId -Profile $null" in script
    assert 'New-GameSyncBadgeBitmap `' in script
    assert '$mark = New-GameBitmap -GameGroup $gameGroup -Color $neutralColor -Category "Other"' in script
    assert "$IconBox.Image = New-SettingsPreviewMedallionBitmap -Mark $mark -Color $neutralColor -WarningBadge" in script
    assert "$g.DrawArc($arcPen, 2, 2, 28, 28, 215, 48)" in script
    assert "$g.DrawImage($Mark, (New-Object System.Drawing.Rectangle(8, 8, 16, 16)))" in script
    assert "$g.DrawLine($badgeMarkPen, [float]25.5, [float]23.5, [float]25.5, [float]26.0)" in script
    assert "$g.FillEllipse($badgeMarkBrush, [float]24.9, [float]27.0, [float]1.2, [float]1.2)" in script
    assert "Startup reminder only. Nothing is applied automatically." in script
    assert "No profile is applied automatically." in script
    assert "Startup reminder profile missing" not in script
    assert "$ProfileId is not in the current profile list" not in script
    assert "Reminder is preserved; nothing is applied automatically." in script
    assert 'New-ActionBitmap -Action "Warning" -Color $neutralColor' not in script
    assert '$profileName = Get-SettingsProfileDisplayName -ProfileId $id -Profile $p' in script
    assert '$defCombo.Items.Add("$id - $profileName")' in script
    assert '$missingDefaultName = Get-SettingsProfileDisplayName -ProfileId "$($Config.defaultProfile)"' in script
    assert (
        '$defCombo.Items.Add("$($Config.defaultProfile) - $missingDefaultName '
        '(missing from current profile list)")'
    ) in script
    assert '$defCombo.Items.Add("$($Config.defaultProfile) - (missing from current profile list)")' not in script
    assert "missing from loaded catalog" not in script
    assert "$matchedDefaultProfile = $false" in script
    assert "Add_SelectedIndexChanged" in script
    assert "Get-SelectedDefaultProfileId -ComboBox $defCombo" in script
    assert "-Config $Config" in script
    assert "AutoEllipsis = $true" in script


def test_settings_startup_resolution_record_uses_reported_labels() -> None:
    """Persisted startup-resolution metadata should not display raw unknown placeholders."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    section = script.split("function Set-StartupResolutionRecord", 1)[1].split(
        "# ============================================================================\n# FAVORITES",
        1,
    )[0]
    assert 'else { "status not reported" }' in section
    assert 'else { "source not reported" }' in section
    assert 'else { "decision not reported" }' in section
    assert 'else { "unknown" }' not in section


def test_settings_default_profile_preview_keeps_variant_and_favorite_badges() -> None:
    """The settings reminder preview should match the rest of the tray visual system."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    mode_section = script.split("function Get-SettingsProfileModeBadge", 1)[1].split(
        "function New-SettingsPreviewMedallionBitmap",
        1,
    )[0]
    preview_section = script.split("function Set-SettingsProfilePreview", 1)[1].split(
        "function Set-LastProfileState",
        1,
    )[0]

    assert '"$ProfileId" -match \'(?i)capture\' -or $variantText -match \'(?i)capture\'' in mode_section
    assert '$variantText -match \'(?i)\\bHDR\\b\' -or "$ProfileId" -match \'(?i)-hdr($|-)\' )' in mode_section
    assert 'return "capture"' in mode_section
    assert 'return "hdr"' in mode_section
    assert "[hashtable]$Config = $null" in preview_section
    assert "$favoriteBadge = $false" in preview_section
    assert 'if ($Config -and $Config.ContainsKey("favorites"))' in preview_section
    assert '$previewState = if ($favoriteBadge) {' in preview_section
    assert '"favorite"' in preview_section
    assert 'elseif (-not [string]::IsNullOrWhiteSpace($modeBadge)) {' in preview_section
    assert '"reminder"' in preview_section
    assert "Get-SettingsProfileDisplayName -ProfileId $ProfileId" in preview_section
    assert "Get-SettingsProfileGameGroup -ProfileId $ProfileId -Profile $null" in preview_section
    assert "Get-SettingsProfileModeBadge -ProfileId $ProfileId -Profile $null" in preview_section
    assert 'New-FavoriteGameBitmap `' in preview_section
    assert 'New-GameSyncBadgeBitmap `' in preview_section
    assert '-ModeBadge $modeBadge' in preview_section
    assert '-SyncMode "agnostic"' in preview_section


def test_settings_panel_has_branded_animated_header() -> None:
    """The tray settings window should share the upgraded visual system."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    chip_helper = script.split("function Get-SettingsHeaderChipText", 1)[1].split(
        "function New-SettingsBrandHeaderPanel",
        1,
    )[0]
    header_section = script.split("function New-SettingsBrandHeaderPanel", 1)[1].split(
        "function Clear-SettingsGeneratedImages",
        1,
    )[0]
    settings_panel_section = script.split("function Show-SettingsPanel", 1)[1].split(
        "# ============================================================================\n# GLOBAL HOTKEYS",
        1,
    )[0]

    assert "Builds the branded settings header used at the top of the tray settings" in header_section
    assert 'New-ActionBitmap -Action "Brand" -Color $Accent' in header_section
    assert '$title.Text = "TRAY SETTINGS"' in header_section
    assert '$subtitle.Text = "Reminder, surfaces, audio, hotkeys"' in header_section
    assert 'return "NOT SET"' in chip_helper
    assert "if ([bool]$Config.notificationsEnabled) { $enabledCount++ }" in chip_helper
    assert "if ([bool]$Config.showQuickPanel) { $enabledCount++ }" in chip_helper
    assert "if ([bool]$Config.soundEnabled) { $enabledCount++ }" in chip_helper
    assert 'return "$enabledCount/3 ON"' in chip_helper
    assert '[string]$ChipText = "TRAY"' in header_section
    assert '$chipTextValue = if ([string]::IsNullOrWhiteSpace($ChipText)) { "TRAY" } else { $ChipText.Trim().ToUpperInvariant() }' in header_section
    assert "$chip.Text = $chipTextValue" in header_section
    assert "$chip.AccessibleDescription = \"Enabled tray popups, Quick Panel restore, and audio cues\"" in header_section
    assert '$orbitStart = ($frame * 9) % 360' in header_section
    assert '$g.DrawArc($orbitPen, 14, 12, 40, 40, $orbitStart, 86)' in header_section
    assert '$sweepX = 72 + (($frame * 7) % [Math]::Max(1, $s.Width - 150))' in header_section
    assert '$g.DrawLine($sweepPen, $sweepX, 8, [Math]::Min($s.Width - 12, $sweepX + 58), 8)' in header_section
    assert "function Clear-SettingsGeneratedImages" in script
    assert "$Root -is [System.Windows.Forms.PictureBox]" in script
    assert "$Root -is [System.Windows.Forms.Button]" in script
    assert "$form.ClientSize = New-Object System.Drawing.Size(404, 760)" in settings_panel_section
    assert "$form.MinimumSize = New-Object System.Drawing.Size(420, 780)" in settings_panel_section
    assert "$requiredClientHeight = [Math]::Max(" in settings_panel_section
    assert "[Math]::Max($saveBtn.Bottom, $closeBtn.Bottom)" in settings_panel_section
    assert "$form.ClientSize = New-Object System.Drawing.Size($form.ClientSize.Width, $requiredClientHeight)" in (
        settings_panel_section
    )
    assert "$form.Size = New-Object System.Drawing.Size(420, 725)" not in settings_panel_section
    assert "$settingsHeader = New-SettingsBrandHeaderPanel `" in settings_panel_section
    assert "-ChipText (Get-SettingsHeaderChipText -Config $Config)" in settings_panel_section
    assert "$settingsHeaderPulseTimer = New-Object System.Windows.Forms.Timer" in settings_panel_section
    assert "$settingsHeaderPulseTimer.Interval = 95" in settings_panel_section
    assert "$settingsPreviewPulseTimer = New-Object System.Windows.Forms.Timer" in settings_panel_section
    assert "$settingsPreviewPulseTimer.Interval = 110" in settings_panel_section
    assert "$settingsPreviewPulseTimer.Tag = $profilePreview" in settings_panel_section
    assert '$target.Tag["Frame"] = ([int]$target.Tag["Frame"] + 1) % 120' in settings_panel_section
    assert 'if ($settingsPreviewPulseTimer) {' in settings_panel_section
    assert 'try { $settingsPreviewPulseTimer.Stop() } catch {}' in settings_panel_section
    assert 'try { $settingsPreviewPulseTimer.Dispose() } catch {}' in settings_panel_section
    assert '$profilePreview.Tag = @{' in settings_panel_section
    assert '$previewState = if ($s.Tag -is [hashtable]) { $s.Tag } else { @{} }' in settings_panel_section
    assert '$stateName = if ($previewState.ContainsKey("State")) { "$($previewState["State"])" } else { "reminder" }' in settings_panel_section
    assert '$railX = $s.Width - 9' in settings_panel_section
    assert '$railAlpha = if ($stateName -in @("reminder", "favorite", "capture", "hdr")) {' in settings_panel_section
    assert '$scanY = $railTop + (($frame * 3) % [Math]::Max(1, $railHeight))' in settings_panel_section
    assert '$g.DrawLine($scanPen, ($railX - 4), $scanY, ($railX + 5), $scanY)' in settings_panel_section
    assert "Clear-SettingsGeneratedImages -Root $form" in settings_panel_section


def test_settings_panel_section_headers_are_icon_backed_and_precise() -> None:
    """Settings sections should not use vague, plain text-only labels."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    settings_panel_section = script.split("function Show-SettingsPanel", 1)[1].split(
        "# ============================================================================\n# GLOBAL HOTKEYS",
        1,
    )[0]
    section_helper = script.split("function New-SettingsSectionHeaderPanel", 1)[1].split(
        "function Clear-SettingsGeneratedImages",
        1,
    )[0]

    assert "function New-SettingsSectionHeaderPanel" in script
    assert 'New-ActionBitmap -Action $Action -Color $Color' in section_helper
    assert "$g.DrawLine($linePen, 28, 20, [Math]::Min($s.Width - 1, 150), 20)" in section_helper
    assert "$g.FillEllipse($dotBrush, 154, 18, 3, 3)" in section_helper
    assert "$iconBox.Size = New-Object System.Drawing.Size(18, 18)" in section_helper
    assert "$label.AutoEllipsis = $true" in section_helper
    assert '$genLabel = New-SettingsSectionHeaderPanel `' in settings_panel_section
    assert '-Text "STARTUP REMINDER" `' in settings_panel_section
    assert '-Action "Startup" `' in settings_panel_section
    assert '$surfaceLabel = New-SettingsSectionHeaderPanel `' in settings_panel_section
    assert '-Text "TRAY SURFACES" `' in settings_panel_section
    assert '-Action "QuickPanel" `' in settings_panel_section
    assert '$audioLabel = New-SettingsSectionHeaderPanel `' in settings_panel_section
    assert '-Text "AUDIO" `' in settings_panel_section
    assert '-Action "Sound" `' in settings_panel_section
    assert '$hkLabel = New-SettingsSectionHeaderPanel `' in settings_panel_section
    assert '-Text "HOTKEYS" `' in settings_panel_section
    assert '-Action "Hotkey" `' in settings_panel_section
    assert '$genLabel.Text = "GENERAL"' not in settings_panel_section
    assert '$hkLabel.Text = "CONFIGURED HOTKEYS"' not in settings_panel_section


def test_settings_panel_exposes_tray_surface_preferences() -> None:
    """Settings should expose durable tray-surface prefs with scope-accurate copy."""
    settings = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    settings_panel_section = settings.split("function Show-SettingsPanel", 1)[1].split(
        "# ============================================================================\n# GLOBAL HOTKEYS",
        1,
    )[0]
    settings_save_section = settings_panel_section.split("$saveBtn.Add_Click({", 1)[1].split(
        "Save-TrayConfig $Config",
        1,
    )[0]
    settings_callback_section = tray.split("Show-SettingsPanel -Config $script:TrayConfig -OnSave {", 1)[1].split(
        "$settingsMenu.DropDownItems.Add($settingsPanelItem)",
        1,
    )[0]

    assert '$toastCheck.Text = "Show themed toast popups"' in settings_panel_section
    assert "$toastCheck.Checked = [bool]$Config.notificationsEnabled" in settings_panel_section
    assert '$toastNote.Text = "Tray hover/status text still updates when popups are off."' in settings_panel_section
    assert '$quickPanelCheck.Text = "Restore Quick Panel on tray startup"' in settings_panel_section
    assert "$quickPanelCheck.Checked = [bool]$Config.showQuickPanel" in settings_panel_section
    assert '$quickPanelNote.Text = "Shows an empty/profile-missing card instead of silently hiding."' in (
        settings_panel_section
    )
    assert "$Config.notificationsEnabled = $toastCheck.Checked" in settings_save_section
    assert "$Config.showQuickPanel = $quickPanelCheck.Checked" in settings_save_section
    assert "$script:EnableBalloonNotifications = [bool]$script:TrayConfig.notificationsEnabled" in (
        settings_callback_section
    )
    assert "Disable all notifications" not in settings_panel_section
    assert "Launch Quick Panel immediately" not in settings_panel_section


def test_settings_panel_command_buttons_use_action_icons() -> None:
    """Settings command buttons should share the tray action icon language."""
    script = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    settings_panel_section = script.split("function Show-SettingsPanel", 1)[1].split(
        "# ============================================================================\n# GLOBAL HOTKEYS",
        1,
    )[0]

    assert (
        '$profilesFolderBtn.Image = New-ActionBitmap -Action "Folder" -Color ([System.Drawing.Color]::FromArgb(255, 190, 190, 195))'
        in settings_panel_section
    )
    assert (
        '$saveBtn.Image = New-ActionBitmap -Action "Save" -Color ([System.Drawing.Color]::FromArgb(255, 16, 16, 16))'
        in settings_panel_section
    )
    assert (
        '$closeBtn.Image = New-ActionBitmap -Action "Close" -Color ([System.Drawing.Color]::FromArgb(255, 190, 190, 195))'
        in settings_panel_section
    )
    assert (
        "$profilesFolderBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText"
        in settings_panel_section
    )
    assert (
        "$saveBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText"
        in settings_panel_section
    )
    assert (
        "$closeBtn.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText"
        in settings_panel_section
    )


def test_tray_status_bar_deduplicates_repeated_status_fragments() -> None:
    """Status bar should not repeat restart/apply text already stored as LastAction."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$statusParts = [System.Collections.Generic.List[string]]::new()" in script
    assert (
        'Add-UniqueTrayMessage -Target $statusParts -Message "Windows restart required: $rebootPendingText"'
        in script
    )
    assert 'Add-UniqueTrayMessage -Target $statusParts -Message "Restart required: $rebootPendingText"' not in script
    assert "$lastActionText = Normalize-TrayLastActionMessage -Message $script:LastAction" in script
    assert "$statusBarLastActionText = $lastActionText" in script
    assert "Add-UniqueTrayMessage -Target $statusParts -Message $statusBarLastActionText" in script
    assert "Add-UniqueTrayMessage -Target $statusParts -Message $script:LastAction" not in script


def test_tray_status_bar_renders_state_chips_from_existing_status_truth() -> None:
    """Footer status should visualize real status parts instead of inventing a second warning source."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    chip_section = script.split("function Get-TrayStatusBarChipText", 1)[1].split(
        "function New-TrayLastActionStatusBitmap",
        1,
    )[0]
    renderer_background = script.split('if (e.Item.AccessibleName == "__status_bar__")', 1)[1].split(
        "// --- Top-level flyout commands",
        1,
    )[0]
    renderer_text = script.split('if (e.Item.AccessibleName == "__status_bar__")', 2)[2].split(
        'if (e.Item.AccessibleName == "__flyout_command__")',
        1,
    )[0]

    assert '$script:statusBarItem.AccessibleName = "__status_bar__"' in script
    assert '$script:statusBarItem.AccessibleDescription = "READY"' in script
    assert '[void]$chips.Add("PREVIEW")' in chip_section
    assert '[void]$chips.Add("FIX")' in chip_section
    assert '[void]$chips.Add("RESTART")' in chip_section
    assert '[void]$chips.Add("CHECK")' in chip_section
    assert '[void]$chips.Add("ACTION")' in chip_section
    assert '[void]$chips.Add("BACKUP")' in chip_section
    assert '[void]$chips.Add("READY")' in chip_section
    assert "$statusHasBackup = ($backupTime -ne \"Never\")" in script
    assert '$statusIsVerificationMismatch = ($script:ActiveProfileVerificationStatus -eq "mismatch")' in script
    assert '$pendingStatusLabel = if ($statusIsVerificationMismatch) { "Profile mismatch" } else { "Pending profile fix" }' in script
    assert 'Add-UniqueTrayMessage -Target $statusParts -Message "${pendingStatusLabel}: $pendingApplyText"' in script
    assert '$statusBarLastActionText = $lastActionText' in script
    assert '$statusBarLastActionText.StartsWith("Profile mismatch:")' in script
    assert '$statusBarLastActionText = $null' in script
    assert '$statusBarText = if ($statusParts.Count -gt 0) { @($statusParts) -join \'  |  \' } else { "Ready" }' in script
    assert '$script:statusBarItem.Text = "  $statusBarText"' in script
    assert "$script:statusBarItem.AccessibleDescription = Get-TrayStatusBarChipText `" in script
    assert "-PendingApplyText $pendingApplyText `" in script
    assert "-RebootPendingText $rebootPendingText `" in script
    assert "-VerificationProgressText $verificationProgressText `" in script
    assert "-LastActionText $statusBarLastActionText `" in script
    assert "-HasBackup $statusHasBackup" in script
    assert "$script:statusBarItem.AccessibleDescription = Get-TrayStatusBarChipText -Preview $true" not in script
    assert 'chipRaw.Contains("FIX") || chipRaw.Contains("RESTART")' in renderer_background
    assert 'chipRaw.Contains("CHECK") || chipRaw.Contains("PREVIEW")' in renderer_background
    assert 'chipRaw.Contains("BACKUP")' in renderer_background
    assert 'chipRaw.Contains("MIXED")' in renderer_background
    assert 'chipRaw.Contains("DISPLAY") || chipRaw.Contains("GPU") || chipRaw.Contains("HZ")' in renderer_background
    assert 'chipRaw.Contains("NO-DATA")' in renderer_background
    assert "g.DrawLine(sweepPen, sweepX, rect.Y + 2, Math.Min(rect.Right - 9, sweepX + sweepWidth), rect.Y + 2);" in renderer_background
    assert "string[] chips = chipRaw.Split(new char[] { '|' }, StringSplitOptions.RemoveEmptyEntries);" in renderer_text
    assert 'if (chip == "FIX" || chip == "RESTART")' in renderer_text
    assert 'if (chip == "CHECK" || chip == "PREVIEW")' in renderer_text
    assert 'if (chip == "MIXED")' in renderer_text
    assert 'if (chip == "DISPLAY" || chip == "GPU" || chip == "HZ")' in renderer_text
    assert 'if (chip == "NO-DATA")' in renderer_text
    assert 'e.Graphics.DrawString(label, e.TextFont, brush, labelRect, format);' in renderer_text
    pulse_section = script.split("function Invoke-TrayMenuPulseInvalidation", 1)[1].split(
        "function Stop-TrayMenuPulseTimer",
        1,
    )[0]
    assert "if (-not $script:activeProfile) { return }" not in pulse_section


def test_tray_menu_renderer_uses_bounded_chip_layout() -> None:
    """Right-edge chips should not chase an over-wide or clipped popup width."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    renderer_section = script.split("public class DarkThemeRenderer", 1)[1].split(
        '"@ -ReferencedAssemblies System.Windows.Forms,System.Drawing',
        1,
    )[0]
    menu_width_section = script.split("function Get-TrayMenuWidthBudget", 1)[1].split(
        "function Invoke-TrayMenuPulseInvalidation",
        1,
    )[0]
    menu_creation_section = script.split("$menu = New-Object System.Windows.Forms.ContextMenuStrip", 1)[1].split(
        "# ─── HEADER ───",
        1,
    )[0]

    assert "private const int SafeMenuMaxWidth = 520;" in renderer_section
    assert "private static int GetSafeItemWidth(ToolStripItem item)" in renderer_section
    assert "if (ownerWidth > 0) width = width > 0 ? Math.Min(width, ownerWidth) : ownerWidth;" in renderer_section
    assert "private static Rectangle GetBoundedRowRect(Rectangle rect, int maxWidth, int minWidth)" in renderer_section
    assert "private static int GetSafeChipRight(ToolStripItem item)" in renderer_section
    assert "int chipRight = GetSafeChipRight(e.Item);" in renderer_section
    assert "e.Item.Width - 24" not in renderer_section
    assert "$script:TrayMenuPreferredWidth = 520" in script
    assert "$script:TrayMenuScreenMargin = 48" in script
    assert "$DropDown.MinimumSize = New-Object System.Drawing.Size($minimumWidth, 0)" in menu_width_section
    assert "$DropDown.MaximumSize = New-Object System.Drawing.Size($widthBudget, 0)" in menu_width_section
    assert "Set-TrayDropDownWidthBudget -DropDown $menu" in menu_creation_section
    assert "Set-TrayDropDownWidthBudget -DropDown $item.DropDown" in menu_creation_section


def test_profile_launcher_uses_readable_spacing_and_plain_choice_labels() -> None:
    """Profile launcher rows should use the menu width for readable choices."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")

    assert '$script:FontNormal  = New-Object System.Drawing.Font("Segoe UI", 10.0)' in script
    assert '$script:FontMenuRow = New-Object System.Drawing.Font("Segoe UI", 10.5)' in script
    assert "$script:FontSectionHeader = [DarkThemeRenderer]::ResolveEyebrowFont(16.4)" in script
    assert "$script:FontCategoryHeader = [DarkThemeRenderer]::ResolveEyebrowFont(13.8)" in script
    assert '$script:FontMono    = New-Object System.Drawing.Font("Segoe UI", 9.0)' in script
    assert '"Bahnschrift' not in script
    assert '"Cascadia' not in script
    assert '"Consolas"' not in script
    assert "$script:TrayMenuMinimumWidth = 360" in script
    assert "$script:statusItem.Size = New-Object System.Drawing.Size(480, 48)" in script
    assert "$script:statusItem.Font = $script:FontMenuRowBold" in script
    assert "$searchBox.Size = New-Object System.Drawing.Size(300, 26)" in script
    assert "$searchBox.Font = $script:FontMenuRow" in script
    assert "Font heroFont = ResolveHeroFont(13.0f, FontStyle.Regular);" in script
    assert "float labelSize = isSectionHeader ? 16.4f : 13.8f;" in script
    assert "int labelAlpha = isSectionHeader ? 255 : 248;" in script
    assert "Color labelColor = isCategoryHeader" in script
    assert "private static readonly Color TextPaper = Color.FromArgb(255, 232, 238, 246);" in script
    assert 'Color rowTextColor = e.Item.AccessibleName == "__backup_menu_item__" ? TextMist : TextPaper;' in script
    assert '$variantLabel = if ($VariantCount -eq 1) { "1 choice" } else { "$VariantCount choices" }' in script
    assert '$profileVariantChip = ""' in script
    assert '$submenuItem.ToolTipText = "Open profile choices for $($groupInfo.Name): $($profileIds.Count)"' in script
    assert "Set-TrayGameGroupRowVisualState -Item $submenuItem" in script
    assert '"$($profileIds.Count) VAR"' not in script


def test_tray_surfaces_verification_in_progress_truthfully() -> None:
    """Tray hover/menu text should not claim active is verified while verifier is running."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-ActiveProfileVerificationInProgressText" in script
    assert "if (-not (Test-ActiveProfileVerificationInFlight)) { return $null }" in script
    assert "if (Get-ActiveProfilePendingApplyText) { return $null }" in script
    assert "if (Get-ActiveProfileRebootPendingText) { return $null }" in script
    assert 'return "checking profile state"' in script
    assert 'return "A.B.S.O. - Checking profile state: $profileName"' in script
    assert '$verificationProgressText = Get-ActiveProfileVerificationInProgressText' in script
    assert 'Add-UniqueTrayMessage -Target $statusParts -Message "Checking profile state"' in script
    assert '$script:statusItem.Text = "$profileDisplayName|Checking profile state..."' in script
    assert "$script:statusItem.ForeColor = $script:Colors.AccentBlue" in script
    assert 'return "A.B.S.O. - Verified active: $($p.Name)"' not in script


def test_tray_notification_tooltip_restores_current_state() -> None:
    """Transient notifications should not become stale persistent tray hover text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Set-NotifyIconTooltipText" in script
    assert "function Get-TrayStateTooltipText" in script
    assert "function Restore-TrayTooltipFromState" in script
    assert "param([switch]$Force)" in script
    assert "if ($script:NotificationTooltipRestoreTimer -and -not $Force) { return }" in script
    assert "function Start-NotificationTooltipRestoreTimer" in script
    assert 'Set-NotifyIconTooltipText -Text "$Title - $Message"' in script
    assert "Start-NotificationTooltipRestoreTimer" in script
    assert "Restore-TrayTooltipFromState -Force" in script
    assert 'Stop-NotificationTooltipRestoreTimer' in script
    assert "function Set-TrayOperationTooltipText" in script
    assert "Stop-NotificationTooltipRestoreTimer\n    Set-NotifyIconTooltipText -Text $Text" in script
    assert 'Set-TrayOperationTooltipText -Text "A.B.S.O. - Applying..."' in script
    assert 'Set-TrayOperationTooltipText -Text "A.B.S.O. - Applying pending profile fixes..."' in script
    assert 'Set-TrayOperationTooltipText -Text "A.B.S.O. - Restoring..."' in script
    assert 'Set-TrayOperationTooltipText -Text "A.B.S.O. - Running Audit..."' in script
    assert '$script:notifyIcon.Text = "A.B.S.O. - Applying..."' not in script
    assert '$script:notifyIcon.Text = "A.B.S.O. - Applying pending profile fixes..."' not in script
    assert "Applying pending fix" not in script
    assert '$script:notifyIcon.Text = "A.B.S.O. - Restoring..."' not in script
    assert '$script:notifyIcon.Text = "A.B.S.O. - Running Audit..."' not in script
    assert '$script:notifyIcon.Text = "$Title - $Message".Substring' not in script
    assert '$profileName = if (' in script
    assert '-not [string]::IsNullOrWhiteSpace("$($activeRecord.Profile.Name)")' in script
    assert 'return "A.B.S.O. - Windows restart required: $profileName"' in script
    assert 'return "A.B.S.O. - Checking profile state: $profileName"' in script
    assert 'return "A.B.S.O. - Restart required: $($p.Name)"' not in script
    menu_state_section = script.split("function Update-MenuState", 1)[1].split(
        "# ============================================================================\n# SYSTEM INFO",
        1,
    )[0]
    assert "Restore-TrayTooltipFromState" in menu_state_section
    assert "$script:notifyIcon.Text = $tooltipText" not in menu_state_section


def test_active_profile_status_handles_catalog_mismatch_truthfully() -> None:
    """Active state should not be displayed as Ready when catalog metadata is missing."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-ActiveTrayProfileRecord" in script
    assert "function Set-TrayActiveStatusItemFromState" in script
    assert 'return "A.B.S.O. - Profile missing from current list: $($activeRecord.DisplayName)"' in script
    assert '$script:statusItem.Text = "$($activeRecord.DisplayName)|Active profile not in current profile list"' in script
    assert '$profileDisplayName = if (' in script
    assert '-not [string]::IsNullOrWhiteSpace("$($activeRecord.Profile.Name)")' in script
    assert '$pendingStatusLabel = if ($script:ActiveProfileVerificationStatus -eq "mismatch") { "Profile mismatch" } else { "Pending profile fix" }' in script
    assert '$script:statusItem.Text = "$profileDisplayName|${pendingStatusLabel}: $pendingApplyText"' in script
    assert '$script:statusItem.Text = "$profileDisplayName|Windows restart required: $rebootPendingText"' in script
    assert 'Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -PendingApplyBadge' in script
    assert 'Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -WindowsRestartBadge' in script
    assert 'Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -VerificationBadge' in script
    assert '$script:statusItem.Text = "$($p.Name)|Restart required: $rebootPendingText"' not in script
    assert 'return "A.B.S.O. - Catalog missing: $($activeRecord.DisplayName)"' not in script
    assert "Active profile not in loaded catalog" not in script
    assert "$script:statusItem.ForeColor = $script:Colors.AccentAmber" in script
    assert "Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $null -ActiveBadge" in script
    assert "Set-TrayActiveStatusItemFromState" in script
    assert "$script:Profiles[$script:activeProfile]" not in script
    assert "$script:Profiles.Contains($script:activeProfile)" not in script


def test_tray_menu_section_headers_are_colored_bands_not_profile_rows() -> None:
    """Section/category headers should use color as structure, not profile-row text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    renderer_section = script.split("// --- Section headers: disabled + bold items (section/category bands) ---", 1)[1].split(
        "var profileMenuItem = e.Item as ToolStripMenuItem;",
        1,
    )[0]

    assert 'bool isSectionHeader = e.Item.AccessibleName == "__section_header__";' in renderer_section
    assert 'bool isCategoryHeader = e.Item.AccessibleName == "__category_header__";' in renderer_section
    assert "int fillAlpha = isCategoryHeader ? 18 : 14;" in renderer_section
    assert "int lineAlpha = isCategoryHeader ? 90 : 72;" in renderer_section
    assert "Header bands use color as structure; selectable rows use color as text." in renderer_section
    assert "var railRect = new Rectangle(5, 4, isCategoryHeader ? 5 : 6, Math.Max(2, h - 8));" in renderer_section
    assert "Color labelGlow = MixColor(tint, Color.White, 0.45);" in renderer_section
    assert "double wave = (Math.Sin(PulseFrame / 7.0) + 1.0) / 2.0;" not in renderer_section
    assert "sweepX = 34 + ((PulseFrame * 3) % sweepTravel)" not in renderer_section
    assert 'if (e.Item.AccessibleName == "__category_header__" || e.Item.AccessibleName == "__section_header__")' in script
    assert "function Get-TraySectionHeaderSummaryChips" in script
    assert "function Set-TraySectionHeaderVisualState" in script
    assert '$Item.AccessibleName = "__section_header__"' in script
    assert '$Item.AccessibleDescription = ""' in script
    assert "$Item.ToolTipText = $ChipText.Trim()" in script
    assert "$Item.Padding = New-Object System.Windows.Forms.Padding(0)" in script
    assert "function Get-TraySectionHeaderTint" in script
    assert "function Get-TrayCategoryHeaderTint" in script
    assert "$favLabel.Image = $null" in script
    assert "$recentLabel.Image = $null" in script
    assert "$profilesLabel.Image = $null" in script
    assert "$backupsItem.Image = New-BackupGameMosaicBitmap -GameGroups @($backupHeaderGameGroups) -Color $script:Colors.AccentPurple -Category \"Other\"" in script
    assert '$backupsItem.Image = New-ActionBitmap -Action "Backups" -Color $script:Colors.AccentPurple' in script


def test_favorites_section_header_stays_quiet_without_game_marks() -> None:
    """Favorites section header should stay lighter than selectable profile rows."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    favorites_section = script.split("# ─── FAVORITES ───", 1)[1].split(
        "# ─── RECENT ───",
        1,
    )[0]

    assert "$favoriteHeaderGameGroups = [System.Collections.Generic.List[string]]::new()" in favorites_section
    assert "$favoriteHeaderGroupKeys = @{}" in favorites_section
    assert "foreach ($favId in $favProfiles)" in favorites_section
    assert "if (-not $script:Profiles.Contains($favId)) { continue }" in favorites_section
    assert "$favoriteGroup = Get-GameGroup -ProfileId $favId" in favorites_section
    assert "$favoriteHeaderGroupKeys.ContainsKey($favoriteGroupKey)" in favorites_section
    assert "$favoriteHeaderGroupKeys[$favoriteGroupKey] = $true" in favorites_section
    assert "if ($favoriteHeaderGameGroups.Count -lt 3) {" in favorites_section
    assert "[void]$favoriteHeaderGameGroups.Add($favoriteGroup)" in favorites_section
    assert "if ($favoriteHeaderGameGroups.Count -ge 3) { break }" not in favorites_section
    assert "Set-TraySectionHeaderVisualState `" in favorites_section
    assert '$favLabel.ForeColor = Get-TraySectionHeaderTint -Section "Favorites"' in favorites_section
    assert "-ItemCount $favProfiles.Count `" in favorites_section
    assert '-ItemSingular "favorite" `' in favorites_section
    assert '-ItemPlural "favorites" `' in favorites_section
    assert "-GameCount $favoriteHeaderGroupKeys.Count" in favorites_section
    assert "$favLabel.Image = $null" in favorites_section
    assert "New-FavoriteGameMosaicBitmap" not in favorites_section
    assert 'New-ActionBitmap -Action "Favorite"' not in favorites_section


def test_recent_section_header_stays_quiet_without_game_marks() -> None:
    """Recent section header should not add another icon row above recent profiles."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    recent_section = script.split("# ─── RECENT ───", 1)[1].split(
        "# ─── PROFILES (game submenus with sync badges) ───",
        1,
    )[0]

    assert "$recentHeaderGameGroups = [System.Collections.Generic.List[string]]::new()" in recent_section
    assert "$recentHeaderGroupKeys = @{}" in recent_section
    assert "$recentDisplayCount = 0" in recent_section
    assert "if ($favProfiles -contains $rId) { continue }" in recent_section
    assert "if (-not $script:Profiles.Contains($rId)) { continue }" in recent_section
    assert "if ($recentDisplayCount -ge 3) { break }" in recent_section
    assert "$recentDisplayCount += 1" in recent_section
    assert "$recentGroup = Get-GameGroup -ProfileId $rId" in recent_section
    assert "$recentHeaderGroupKeys.ContainsKey($recentGroupKey)" in recent_section
    assert "[void]$recentHeaderGameGroups.Add($recentGroup)" in recent_section
    assert "if ($recentHeaderGameGroups.Count -ge 3) { break }" in recent_section
    assert "Set-TraySectionHeaderVisualState `" in recent_section
    assert '$recentLabel.ForeColor = Get-TraySectionHeaderTint -Section "Recent"' in recent_section
    assert "-ItemCount $recentDisplayCount `" in recent_section
    assert '-ItemSingular "recent" `' in recent_section
    assert '-ItemPlural "recent" `' in recent_section
    assert "-GameCount $recentHeaderGameGroups.Count" in recent_section
    assert "$recentLabel.Image = $null" in recent_section
    assert "New-GameMosaicBitmap -GameGroups @($recentHeaderGameGroups)" not in recent_section
    assert 'New-ActionBitmap -Action "Recent"' not in recent_section


def test_profiles_section_header_stays_quiet_without_game_marks() -> None:
    """Profiles section header should be a divider, not another game-mark row."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    profiles_section = script.split("# ─── PROFILES (game submenus with sync badges) ───", 1)[1].split(
        "# Helper to create a profile menu item",
        1,
    )[0]

    assert "$profilesHeaderGameGroups = [System.Collections.Generic.List[string]]::new()" in profiles_section
    assert "$profilesHeaderGroupKeys = @{}" in profiles_section
    assert "$profilesVisibleCount = 0" in profiles_section
    assert "foreach ($id in $script:Profiles.Keys)" in profiles_section
    assert "if ($null -ne $p.TrayVisible -and -not [bool]$p.TrayVisible) { continue }" in profiles_section
    assert "$profilesVisibleCount += 1" in profiles_section
    assert "$profileHeaderGroup = Get-GameGroup -ProfileId $id" in profiles_section
    assert "$profilesHeaderGroupKeys.ContainsKey($profileHeaderGroupKey)" in profiles_section
    assert "$profilesHeaderGroupKeys[$profileHeaderGroupKey] = $true" in profiles_section
    assert "if ($profilesHeaderGameGroups.Count -lt 3) {" in profiles_section
    assert "[void]$profilesHeaderGameGroups.Add($profileHeaderGroup)" in profiles_section
    assert "if ($profilesHeaderGameGroups.Count -ge 3) { break }" not in profiles_section
    assert "Set-TraySectionHeaderVisualState `" in profiles_section
    assert '$profilesLabel.ForeColor = Get-TraySectionHeaderTint -Section "Profiles"' in profiles_section
    assert "-ItemCount $profilesVisibleCount `" in profiles_section
    assert '-ItemSingular "profile" `' in profiles_section
    assert '-ItemPlural "profiles" `' in profiles_section
    assert "-GameCount $profilesHeaderGroupKeys.Count" in profiles_section
    assert "$profilesLabel.Image = $null" in profiles_section
    assert "New-GameMosaicBitmap -GameGroups @($profilesHeaderGameGroups)" not in profiles_section
    assert 'New-ActionBitmap -Action "Profiles"' not in profiles_section


def test_tray_top_level_rows_use_icons_without_fake_padding() -> None:
    """Top-level tray rows with real icons should not rely on leading spaces."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '$header.Text = "A.B.S.O.   v$($script:AppVersion)"' in script
    assert '$header.Image = New-ActionBitmap -Action "Brand" -Color $script:Colors.AccentGold' in script
    assert '$actionsMenu.Text = "Actions"' in script
    assert '$actionsMenu.Image = New-ActionBitmap -Action "Actions" -Color $script:Colors.AccentAmber' in script
    assert '$settingsMenu.Text = "Settings"' in script
    assert '$restartItem.Text = "Restart Tray"' in script
    assert '$aboutItem.Text = "About A.B.S.O."' in script
    assert '$exitItem.Text = "Exit"' in script
    assert '$header.Text = "  A.B.S.O.   v$($script:AppVersion)"' not in script
    assert '$actionsMenu.Text = "  Actions"' not in script
    assert '$settingsMenu.Text = "  Settings"' not in script
    assert '$restartItem.Text = "  Restart Tray"' not in script
    assert '$aboutItem.Text = "  About A.B.S.O."' not in script
    assert '$exitItem.Text = "  Exit"' not in script


def test_tray_top_level_flyouts_render_as_command_pills() -> None:
    """Primary flyouts should read as visual command launchers, not plain text rows."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    renderer_section = script.split("// --- Top-level flyout commands: compact animated launcher pills ---", 1)[1].split(
        "// --- Section headers",
        1,
    )[0]
    text_section = script.split('if (e.Item.AccessibleName == "__flyout_command__")', 1)[1].split(
        'if (e.Item.AccessibleName == "__category_header__" || e.Item.AccessibleName == "__section_header__")',
        1,
    )[0]

    assert 'e.Item.AccessibleName == "__flyout_command__"' in renderer_section
    assert "double wave = (Math.Sin(PulseFrame / 5.0) + 1.0) / 2.0;" in renderer_section
    assert "FillRoundRect(g, brush, rect, 5)" in renderer_section
    assert "DrawRoundRect(g, pen, rect, 5)" in renderer_section
    assert "int sweepX = rect.X + 14 + ((PulseFrame * 5) % sweepTravel);" in renderer_section
    assert "g.DrawLine(sweepPen, sweepX, rect.Y + 2, Math.Min(rect.Right - 10, sweepX + sweepWidth), rect.Y + 2);" in renderer_section
    assert 'e.Graphics.DrawString((e.Text ?? "").Trim().ToUpperInvariant(), labelFont, labelBrush, labelRect, labelFormat);' in text_section
    assert "e.Graphics.DrawString(chip.ToUpperInvariant(), chipFont, chipTextBrush, chipRect, chipFormat);" in text_section
    assert '$actionsMenu.AccessibleName = "__flyout_command__"' in script
    assert '$actionsMenu.AccessibleDescription = "TOOLS"' in script
    assert "$actionsMenu.Padding = New-Object System.Windows.Forms.Padding(0, 0, 56, 0)" in script
    assert '$settingsMenu.AccessibleName = "__flyout_command__"' in script
    assert '$settingsMenu.AccessibleDescription = "PREFS"' in script
    assert "$settingsMenu.Padding = New-Object System.Windows.Forms.Padding(0, 0, 56, 0)" in script


def test_tray_action_rows_render_as_command_pills() -> None:
    """Action flyout commands should use the animated command-row treatment with truthful chips."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    helper_section = script.split("function Set-TrayCommandItemVisualState", 1)[1].split(
        "function Invoke-TrayMenuPulseInvalidation",
        1,
    )[0]
    actions_section = script.split("# ─── ACTIONS (flyout submenu) ───", 1)[1].split(
        "# ─── SETTINGS (flyout submenu) ───",
        1,
    )[0]

    assert '$Item.AccessibleName = "__flyout_command__"' in helper_section
    assert '$Item.AccessibleDescription = if ([string]::IsNullOrWhiteSpace($ChipText)) { "" } else { $ChipText.Trim().ToUpperInvariant() }' in helper_section
    assert "$Item.Padding = New-Object System.Windows.Forms.Padding(0, 0, $PaddingRight, 0)" in helper_section
    assert 'Set-TrayCommandItemVisualState -Item $script:restoreItem -ChipText "RESTORE"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $auditItem -ChipText "AUDIT"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $script:applyPendingItem -ChipText "FIX"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $resetDisplayItem -ChipText "RESET"' in actions_section
    assert (
        "Set-TrayCommandItemVisualState -Item $backupsItem -ChipText "
        "(Get-BackupMenuChipText -VisibleBackupCount @($recentBackups).Count)"
    ) in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $openBackupsItem -ChipText "FOLDER"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $quickPanelItem -ChipText "PANEL"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $refreshProfilesItem -ChipText "REFRESH"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $openProfilesItem -ChipText "FOLDER"' in actions_section
    assert 'Set-TrayCommandItemVisualState -Item $clearMemoryItem -ChipText "MEMORY"' in actions_section
    assert "$script:applyPendingItem.AccessibleDescription = \"PENDING FIXES\"" in script
    assert "$script:applyPendingItem.AccessibleDescription = \"CHECKING PENDING FIXES\"" in script
    assert "$script:applyPendingItem.AccessibleDescription = \"NO PENDING FIXES\"" in script


def test_tray_settings_rows_render_as_command_pills() -> None:
    """Settings flyout commands should share the same animated command-row treatment."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    startup_state_section = script.split("function Set-StartupMenuState", 1)[1].split(
        "function Toggle-Startup",
        1,
    )[0]
    settings_section = script.split("# ─── SETTINGS (flyout submenu) ───", 1)[1].split(
        "# ─── STATUS BAR ───",
        1,
    )[0]

    assert '$startupChipText = if ($startupActionIsStale) { "STALE" } else { "STARTUP" }' in startup_state_section
    assert 'Set-TrayCommandItemVisualState -Item $script:startupItem -ChipText $startupChipText' in startup_state_section
    assert 'Set-TrayCommandItemVisualState -Item $script:notifyToggle -ChipText "TOAST"' in settings_section
    assert 'Set-TrayCommandItemVisualState -Item $soundToggle -ChipText "AUDIO"' in settings_section
    assert 'Set-TrayCommandItemVisualState -Item $settingsPanelItem -ChipText "CONFIG"' in settings_section
    assert 'Set-TrayCommandItemVisualState -Item $logItem -ChipText "LOG"' in settings_section
    assert 'Set-TrayCommandItemVisualState -Item $configFolderItem -ChipText "FOLDER"' in settings_section
    assert 'Set-TrayCommandItemVisualState -Item $runtimeFolderItem -ChipText "RUNTIME"' in settings_section
    assert '$script:notifyToggle.ToolTipText = "Toggle themed toast popups; tray hover/status text still updates"' in (
        settings_section
    )
    assert '$soundToggle.ToolTipText = "Toggle tray audio cues; toasts and status text still update"' in settings_section
    assert '$runtimeFolderItem.ToolTipText = "Opens abso.yaml, installed binaries, backups, and deployed tray assets"' in (
        settings_section
    )


def test_apply_action_icon_is_defined() -> None:
    """The pending-fix menu item should not get a blank action icon."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    apply_section = script.split('"Apply" {', 1)[1].split('"Backups" {', 1)[0]
    pending_section = script.split('"PendingFix" {', 1)[1].split('"Backups" {', 1)[0]
    assert '"Apply" {' in script
    assert "$checkPoints = [System.Drawing.PointF[]]@(" in apply_section
    assert "$g.DrawLines($checkPen, $checkPoints)" in apply_section
    assert "$g.DrawLines($checkPen, @(" not in apply_section
    assert '"PendingFix" {' in script
    assert "Pending verifier fix: wrench body with an amber exclamation badge." in pending_section
    assert "$g.DrawLine($markPen, [float]5.5, [float]9.7, [float]5.5, [float]12.0)" in pending_section
    assert "$g.FillEllipse($dotBrush, [float]4.9, [float]12.7, [float]1.2, [float]1.2)" in pending_section


def test_refresh_profiles_action_icon_is_distinct_from_audit() -> None:
    """Refreshing profiles should not reuse the audit/search glyph."""
    icon_script = ICONS_SCRIPT.read_text(encoding="utf-8")
    tray_script = TRAY_SCRIPT.read_text(encoding="utf-8")
    refresh_icon_section = icon_script.split('"Refresh" {', 1)[1].split('"Apply" {', 1)[0]
    assert "Two circular arrows for profile catalog reload." in refresh_icon_section
    assert "$g.DrawArc($arcPen, 3, 3, 10, 10, 25, 180)" in refresh_icon_section
    assert "$headOnePoints = [System.Drawing.PointF[]]@(" in refresh_icon_section
    refresh_menu_section = tray_script.split("# Refresh Profiles", 1)[1].split(
        "$actionsMenu.DropDownItems.Add($refreshProfilesItem)",
        1,
    )[0]
    assert '$refreshProfilesItem.Image = New-ActionBitmap -Action "Refresh" -Color $script:Colors.AccentBlue' in refresh_menu_section
    assert '$refreshProfilesItem.Image = New-ActionBitmap -Action "Audit" -Color $script:Colors.AccentBlue' not in refresh_menu_section


def test_folder_log_memory_reset_and_info_action_icons_are_defined() -> None:
    """Common tray utility actions should have first-party action art."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    for action in [
        "Brand",
        "Actions",
        "Search",
        "Favorite",
        "Recent",
        "Profiles",
        "Display",
        "Startup",
        "Toast",
        "Sound",
        "Hotkey",
        "Folder",
        "Log",
        "Memory",
        "Reset",
        "Info",
        "Save",
        "Close",
    ]:
        assert f'"{action}" {{' in script
    assert "A.B.S.O. angular station mark with a small optimizer spark." in script
    assert "Stacked command chevrons for primary tray actions." in script
    assert "Search result lens with three scan ticks." in script
    assert "Filled star for pinned favorite profiles." in script
    assert "Clock face with a recent-history sweep arrow." in script
    assert "Stacked profile cards for the profile catalog section." in script
    assert "Display topology monitor with a compact GPU chip." in script
    assert "Startup launch arrow from a small Windows tile." in script
    assert "Toast notification bubble with a small status pip." in script
    assert "Speaker cone with two sound waves." in script
    assert "Keyboard shortcut keycap with a small command spark." in script
    assert "Folder tab with subtle document line." in script
    assert "Log document with two readable lines." in script
    assert "RAM chip with pins." in script
    assert "High-impact display recovery mark: bolt inside warning ring." in script
    assert "Information dot for About/help surfaces." in script
    assert "Compact disk/save glyph with an applied-settings check." in script
    assert "Window close X inside a quiet control disc." in script


def test_warning_action_icon_is_defined_with_typed_points() -> None:
    """Settings/status warning previews should use real action art, not generic fallback."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    warning_section = script.split('"Warning" {', 1)[1].split('"Exit" {', 1)[0]
    assert "$triPoints = [System.Drawing.PointF[]]@(" in warning_section
    assert "$g.FillPolygon($triBrush, $triPoints)" in warning_section
    assert "$g.DrawPolygon($borderPen, $triPoints)" in warning_section
    assert "$g.DrawLine($markPen, 8, 5, 8, 9)" in warning_section


def test_tray_game_marks_cover_current_profile_groups() -> None:
    """Tray game icons should not fall back to generic category art for shipped games."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    assert "function Resolve-GameVisualIdentityGroup" in script
    assert "function Get-GameVisualIdentity" in script
    assert "function Get-GameAccentColor" in script
    for group in [
        "slippi-melee",
        "rivals2",
        "overwatch2",
        "fortnite",
        "marvel-rivals",
        "deadlock",
        "call-of-duty",
        "diablo4",
        "ryujinx-ssbu",
        "pokemon-auto-chess",
        "pacdeluxe",
        "productivity",
    ]:
        assert f'"{group}"' in script
    assert '"deadlock" {' in script
    assert '"call-of-duty" {' in script
    assert 'Name = "Overwatch"' in script
    assert 'Name = "Call of Duty"' in script
    assert 'Name = "Diablo IV"' in script
    assert '$identity["Key"] = $resolvedGameGroup' in script
    assert 'IsKnown = $false' in script
    assert '$identity["IsKnown"] = $true' in script


def test_tray_game_marks_cover_common_custom_profile_groups() -> None:
    """Common custom-profile game groups should get explicit marks, not generated initials."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    new_game_section = script.split("function New-GameBitmap", 1)[1].split(
        "function New-ActiveGameBitmap",
        1,
    )[0]

    for group in [
        "valorant",
        "apex-legends",
        "counter-strike-2",
        "rocket-league",
        "minecraft",
        "league-of-legends",
        "destiny-2",
        "elden-ring",
        "halo-infinite",
        "cyberpunk-2077",
        "helldivers-2",
    ]:
        assert f'"{group}"' in resolver_section
        assert f'"{group}" {{' in new_game_section

    assert '"valorant-win64-shipping-exe" = "valorant"' in resolver_section
    assert '"r5apex-exe" = "apex-legends"' in resolver_section
    assert '"cs2-exe" = "counter-strike-2"' in resolver_section
    assert '"rocketleague-win64-shipping-exe" = "rocket-league"' in resolver_section
    assert '"minecraftlauncher-exe" = "minecraft"' in resolver_section
    assert '"leagueclient-exe" = "league-of-legends"' in resolver_section
    assert '"destiny2-exe" = "destiny-2"' in resolver_section
    assert '"eldenring-exe" = "elden-ring"' in resolver_section
    assert '"haloinfinite-exe" = "halo-infinite"' in resolver_section
    assert '"cyberpunk2077-exe" = "cyberpunk-2077"' in resolver_section
    assert '"helldivers2-exe" = "helldivers-2"' in resolver_section
    assert "Valorant: twin tactical V shards" in new_game_section
    assert "Apex Legends: three-point drop banner" in new_game_section
    assert "Counter-Strike 2: compact crosshair ring" in new_game_section
    assert "Rocket League: arena shield with a car nose chasing a ball." in new_game_section
    assert "Minecraft: isometric grass block" in new_game_section
    assert "League of Legends: ornate crest ring" in new_game_section
    assert "Destiny 2: tricorn-inspired three-lobed mark with a pale center." in new_game_section
    assert "Elden Ring: stacked rune rings crossed by a golden sigil stem." in new_game_section
    assert "Halo Infinite: Spartan helmet visor over an olive armor shell." in new_game_section
    assert "Cyberpunk 2077: jagged neon shard with cyan glitch rails." in new_game_section
    assert "Helldivers 2: descending drop pod over a bright tactical star." in new_game_section


def test_tray_game_marks_cover_catalog_tray_groups() -> None:
    """Every built-in catalog tray group should have an explicit icon resolver key."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    catalog_tree = ast.parse(CATALOG_SCRIPT.read_text(encoding="utf-8"))
    catalog_groups: set[str] = set()
    for node in ast.walk(catalog_tree):
        if (
            isinstance(node, ast.AnnAssign)
            and isinstance(node.target, ast.Name)
            and node.target.id == "BUILTIN_TRAY_UI"
            and isinstance(node.value, ast.Dict)
        ):
            for value in node.value.values:
                if (
                    isinstance(value, ast.Call)
                    and value.args
                    and isinstance(value.args[0], ast.Constant)
                    and isinstance(value.args[0].value, str)
                ):
                    catalog_groups.add(value.args[0].value)
            break

    assert catalog_groups
    for group in sorted(catalog_groups):
        assert f'"{group}"' in resolver_section


def test_tray_game_marks_cover_cached_profile_catalog_groups() -> None:
    """The deployed tray cache should not introduce profile groups with placeholder art."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    cached_catalog = json.loads(CACHED_TRAY_CATALOG.read_text(encoding="utf-8"))
    cached_groups = {
        profile["tray_group"]
        for profile in cached_catalog["profiles"]
        if isinstance(profile, dict) and profile.get("tray_group")
    }

    assert cached_groups
    for group in sorted(cached_groups):
        assert f'"{group}"' in resolver_section


def test_tray_game_marks_cover_integration_matrix_variants() -> None:
    """Every shipped profile variant in the matrix should strip to a known game mark."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    known_groups_match = re.search(r"\$knownGameGroups\s*=\s*@\((.*?)\)", resolver_section, re.S)
    assert known_groups_match
    known_groups = set(re.findall(r'"([^"]+)"', known_groups_match.group(1)))
    matrix = json.loads(INTEGRATION_TEST_MATRIX.read_text(encoding="utf-8"))
    profile_ids = {
        scenario["profile_id"]
        for scenario in matrix["scenarios"]
        if scenario.get("kind") == "apply_profile" and scenario.get("profile_id")
    }
    variant_suffixes = [
        "-online-gsync-hdr",
        "-gsync-hdr-capture",
        "-gsync-capture",
        "-online-gsync",
        "-offline-gsync-hdr",
        "-offline-hdr",
        "-online-hdr",
        "-console-parity-hdr",
        "-universal-hdr",
        "-gsync-hdr",
        "-tournament-sim-144hz",
        "-console-parity",
        "-300hz-max",
        "-streaming-hdr",
        "-streaming",
        "-offline",
        "-online",
        "-vrr-lab",
        "-gsync",
        "-hdr",
        "-sdr",
        "-universal",
        "-capture",
    ]

    assert profile_ids
    for profile_id in sorted(profile_ids):
        base_id = profile_id
        for suffix in variant_suffixes:
            if base_id.endswith(suffix):
                base_id = base_id[: -len(suffix)]
                break
        assert base_id in known_groups, f"{profile_id} resolves to uncovered group {base_id}"
        if base_id != profile_id:
            assert f'"{suffix}"' in resolver_section


def test_tray_game_marks_cover_detected_battle_net_games() -> None:
    """Game detection names should normalize to hand-drawn tray marks when known."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    detection = json.loads(GAME_DETECTION_MANIFEST.read_text(encoding="utf-8"))
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    battle_net_games = set(detection["battle_net_games"].keys())

    assert {"Diablo IV", "Overwatch 2", "Call of Duty"} <= battle_net_games
    assert '"diablo-iv" = "diablo4"' in resolver_section
    assert '"overwatch-2" = "overwatch2"' in resolver_section
    assert '"call-of-duty" = "call-of-duty"' in resolver_section
    assert '"callofduty" = "call-of-duty"' in resolver_section
    assert '"cod" = "call-of-duty"' in resolver_section
    assert '"modernwarfare" = "call-of-duty"' in resolver_section
    assert '"modern-warfare" = "call-of-duty"' in resolver_section


def test_tray_game_marks_cover_detected_executable_names() -> None:
    """Detected process/executable labels should still resolve to game-specific marks."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    detection = json.loads(GAME_DETECTION_MANIFEST.read_text(encoding="utf-8"))
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    detection_executables = set()
    for patterns in detection["steam_game_patterns"].values():
        detection_executables.update(patterns)
    for patterns in detection["epic_game_patterns"].values():
        detection_executables.update(patterns)
    for game in detection["battle_net_games"].values():
        detection_executables.update(game["executables"])
    detection_executables.update(detection["standalone_executables"])

    assert {
        "Overwatch.exe",
        "Diablo IV.exe",
        "cod.exe",
        "ModernWarfare.exe",
        "RivalsOfAether2-Win64-Shipping.exe",
        "Marvel-Win64-Shipping.exe",
        "FortniteClient-Win64-Shipping_EAC_EOS.exe",
        "Slippi Dolphin.exe",
        "Dolphin.exe",
    } <= detection_executables
    assert '"overwatch-exe" = "overwatch2"' in resolver_section
    assert '"diablo-iv-exe" = "diablo4"' in resolver_section
    assert '"cod-exe" = "call-of-duty"' in resolver_section
    assert '"modernwarfare-exe" = "call-of-duty"' in resolver_section
    assert '"rivalsofaether2-win64-shipping-exe" = "rivals2"' in resolver_section
    assert '"marvel-win64-shipping-exe" = "marvel-rivals"' in resolver_section
    assert '"fortniteclient-win64-shipping-eac-eos-exe" = "fortnite"' in resolver_section
    assert '"slippi-dolphin" = "slippi-melee"' in resolver_section
    assert '"slippi-dolphin-exe" = "slippi-melee"' in resolver_section
    assert '"dolphin-exe" = "slippi-melee"' in resolver_section


def test_tray_game_marks_cover_detected_storefront_names() -> None:
    """Steam/Epic detection labels should not drop to generated initials."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    detection = json.loads(GAME_DETECTION_MANIFEST.read_text(encoding="utf-8"))
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    steam_names = set(detection["steam_game_patterns"].keys())
    epic_names = set(detection["epic_game_patterns"].keys())

    assert {"Rivals of Aether 2", "Marvel Rivals", "Diablo IV", "Slippi Launcher"} <= steam_names
    assert {"Rivals of Aether 2", "Fortnite"} <= epic_names
    assert '"rivals-of-aether-2" = "rivals2"' in resolver_section
    assert '"rivalsofaether2" = "rivals2"' in resolver_section
    assert '"slippi-launcher" = "slippi-melee"' in resolver_section
    assert '"slippi-dolphin" = "slippi-melee"' in resolver_section
    assert '"marvelrivals" = "marvel-rivals"' in resolver_section
    assert '"diabloiv" = "diablo4"' in resolver_section


def test_game_visual_identity_normalizes_profile_variants_to_base_marks() -> None:
    """Variant ids and human labels should still resolve to hand-drawn game marks."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    resolver_section = script.split("function Resolve-GameVisualIdentityGroup", 1)[1].split(
        "function Get-GameVisualIdentity",
        1,
    )[0]
    new_game_section = script.split("function New-GameBitmap", 1)[1].split(
        "function New-ActiveGameBitmap",
        1,
    )[0]

    assert '"overwatch-2" = "overwatch2"' in resolver_section
    assert '"rivals-of-aether-2" = "rivals2"' in resolver_section
    assert '"slippi-launcher" = "slippi-melee"' in resolver_section
    assert '"call-of-duty-modern-warfare" = "call-of-duty"' in resolver_section
    assert '"cod-bo7" = "call-of-duty"' in resolver_section
    assert '"black-ops-7" = "call-of-duty"' in resolver_section
    assert '"warzone" = "call-of-duty"' in resolver_section
    assert '"modern-warfare-iii" = "call-of-duty"' in resolver_section
    assert '"diablo-iv" = "diablo4"' in resolver_section
    assert '"ssbu-hewdraw-remix-ryujinx" = "ryujinx-ssbu"' in resolver_section
    assert '"desktop-productivity" = "productivity"' in resolver_section
    assert '"pacdeluxe-pokemon-auto-chess" = "pacdeluxe"' in resolver_section
    assert '"-gsync-hdr-capture"' in resolver_section
    assert '"-online-gsync-hdr"' in resolver_section
    assert '"-console-parity-hdr"' in resolver_section
    assert '"-tournament-sim-144hz"' in resolver_section
    assert '"-300hz-max"' in resolver_section
    assert '"-streaming-hdr"' in resolver_section
    assert '"-streaming"' in resolver_section
    assert '"-vrr-lab"' in resolver_section
    assert 'if ($knownGameGroups.Contains($candidate)) { return $candidate }' in resolver_section
    assert "$resolvedGameGroup = Resolve-GameVisualIdentityGroup -GameGroup $GameGroup" in script
    assert 'switch ("$resolvedGameGroup")' in script
    assert '$gameKey = if ($identity.ContainsKey("Key")' in new_game_section
    assert "switch ($gameKey)" in new_game_section
    assert "switch ($GameGroup)" not in new_game_section


def test_call_of_duty_detection_mark_is_stylized_not_monogram() -> None:
    """Detected COD installs should get a tactical mark instead of generated initials."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    cod_section = script.split('"call-of-duty" {', 2)[2].split(
        '"diablo4" {',
        1,
    )[0]

    assert "Call of Duty: tactical rank chevrons on a compact armor plate." in cod_section
    assert "$platePoints = [System.Drawing.PointF[]]@(" in cod_section
    assert "$g.FillPolygon($plateBrush, $platePoints)" in cod_section
    assert "$g.DrawPolygon($platePen, $platePoints)" in cod_section
    assert "$g.DrawLine($chevronPen, 4.6, 5.4, 8, 8.3)" in cod_section
    assert "$g.DrawLine($chevronPen, 4.8, 8.2, 8, 11.1)" in cod_section
    assert "$g.FillRectangle($topBrush, 5, 3, 6, 1)" in cod_section
    assert "New-StylizedGameFallbackBitmap" not in cod_section


def test_productivity_group_has_dedicated_mark_not_category_placeholder() -> None:
    """Desktop/productivity profiles should get their own tray mark."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    productivity_section = script.split('"productivity" {', 2)[2].split(
        "default {",
        1,
    )[0]

    assert "Productivity workspace: compact app window with a verified task check." in productivity_section
    assert "$g.FillRectangle($frameBrush, 3, 3, 10, 9)" in productivity_section
    assert "$g.FillRectangle($titleBrush, 3, 3, 10, 2)" in productivity_section
    assert "$g.FillRectangle($paneBrush, 4, 6, 4, 5)" in productivity_section
    assert "$g.DrawLine($checkPen, 5, 9, 6.5, 10.5)" in productivity_section
    assert "$g.DrawLine($standPen, 5, 14, 11, 14)" in productivity_section
    assert "New-CategoryBitmap" not in productivity_section


def test_pokemon_auto_chess_and_pacdeluxe_marks_are_distinct_and_truthful() -> None:
    """PACDeluxe is the native PAC app lane, so it should not look like Pac-Man."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    pokemon_section = script.split('"pokemon-auto-chess" {', 2)[2].split(
        '"pacdeluxe" {',
        1,
    )[0]
    pacdeluxe_section = script.split('"pacdeluxe" {', 2)[2].split(
        '"productivity" {',
        1,
    )[0]

    assert "Pokemon Auto Chess: checker board with a compact pokeball piece." in pokemon_section
    assert "$g.FillRectangle($boardBrush, 2, 2, 12, 12)" in pokemon_section
    assert "$g.FillRectangle($tileBrush, 6, 6, 3, 3)" in pokemon_section
    assert "$g.FillEllipse($topBrush, 4, 4, 8, 8)" in pokemon_section
    assert "$g.DrawLine($bandPen, 4, 8, 12, 8)" in pokemon_section
    assert "PACDeluxe: native app window wrapped around the Pokemon Auto Chess piece." in pacdeluxe_section
    assert "$g.FillRectangle($windowBrush, 2, 3, 12, 10)" in pacdeluxe_section
    assert "$g.FillRectangle($titleBrush, 3, 4, 10, 2)" in pacdeluxe_section
    assert "$g.DrawLine($gridPen, 3, 9, 13, 9)" in pacdeluxe_section
    assert "$g.FillEllipse($pieceBrush, [float]6.1, [float]7.1, [float]3.8, [float]3.8)" in pacdeluxe_section
    assert "Pac-Man: circle with wedge mouth cut out" not in pacdeluxe_section
    assert "$mouthPoints" not in pacdeluxe_section


def test_unknown_game_groups_get_stylized_marks_not_category_placeholders() -> None:
    """User/catalog game groups should get deterministic marks instead of broad category icons."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-GameFallbackInitials" in script
    assert "function Get-GameFallbackHash" in script
    assert "function Get-GameFallbackColor" in script
    assert "function New-StylizedGameFallbackBitmap" in script
    assert "Unknown non-empty game groups get deterministic monogram marks" in script
    assert 'return New-StylizedGameFallbackBitmap -GameGroup $GameGroup -Color $Color -Category $Category' in script
    assert "if ([string]::IsNullOrWhiteSpace($GameGroup)) {\n        return New-CategoryBitmap -Category $Category -Color $Color\n    }" in script
    fallback_section = script.split("function New-StylizedGameFallbackBitmap", 1)[1].split(
        "function New-GameBitmap",
        1,
    )[0]
    assert "$platePoints = [System.Drawing.PointF[]]@(" in fallback_section
    assert "$g.FillPolygon($plateBrush, $platePoints)" in fallback_section
    assert "$g.DrawString($initials, $font, $textBrush, $textRect, $sf)" in fallback_section
    new_game_section = script.split("function New-GameBitmap", 1)[1].split(
        "function New-ActiveGameBitmap",
        1,
    )[0]
    assert "return New-CategoryBitmap -Category $Category -Color $Color" not in new_game_section
    accent_section = script.split("function Get-GameAccentColor", 1)[1].split(
        "function Get-GameFallbackInitials",
        1,
    )[0]
    assert "Unknown non-empty game groups use the same deterministic fallback palette" in accent_section
    assert "return Get-GameFallbackColor -GameGroup $GameGroup -FallbackColor $FallbackColor" in accent_section
    assert "return $FallbackColor" in accent_section


def test_category_arpg_icon_uses_typed_polygon_points() -> None:
    """Category icon polygons should bind reliably to GDI+ overloads in PowerShell."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    arpg_section = script.split('"ARPG" {', 1)[1].split('"Shooter" {', 1)[0]
    assert "$points = [System.Drawing.PointF[]]@(" in arpg_section
    assert "$diamondPoints = [System.Drawing.PointF[]]@(" in arpg_section
    assert "$g.DrawPolygon($borderPen, $points)" in arpg_section


def test_profile_surfaces_use_game_identity_accent_colors() -> None:
    """Game marks should drive visible accents, not only broad category color."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    quick_panel = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")

    assert "function Get-TrayProfileAccentColor" in tray
    assert "Get-TrayProfileMenuAccent" in tray
    assert "Get-GameAccentColor -GameGroup $gameGroup -FallbackColor $baseColor" in tray
    assert "ProfileColor = $color" in tray
    assert "$item.ForeColor = $gameColor" in tray
    assert "$submenuItem.ForeColor = $submenuGameColor" in tray
    assert "Get-TrayProfileAccentColor -ProfileId $item.Tag -Profile $p -Fallback $catColor" in tray
    assert "Blend-Color -Base $script:Colors.Background -Overlay $gameColor -Ratio 0.15" in tray

    assert "$gameColor = if (Get-Command Get-GameAccentColor" in quick_panel
    assert "Get-GameAccentColor -GameGroup $gameGroup -FallbackColor $catColor" in quick_panel
    assert "$capCardColor = $gameColor" in quick_panel
    assert "New-QuickPanelGameMedallionBitmap `" in quick_panel
    assert "-GameGroup $gameGroup `" in quick_panel
    assert "-Color $gameColor `" in quick_panel
    assert "-Category $catName `" in quick_panel
    assert "-ActiveBadge:$isActive `" in quick_panel


def test_profile_menu_hover_handlers_are_layout_stable() -> None:
    """Hovering profile rows should not rewrite menu content or force width recalculation."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    hover_section = script.split("function Set-TrayProfileHoverPreview", 1)[1].split(
        "function Get-RecentProfileTooltipText",
        1,
    )[0]

    assert "function Get-TrayProfilePreviewText" in script
    assert "function Register-TrayProfileHoverPreview" in script
    assert "$Item.Add_MouseEnter" in hover_section
    assert "$Item.Add_MouseLeave" in hover_section
    assert "Preview: $groupName" in script
    assert "Keep row hover layout-neutral." in hover_section
    assert '$script:statusItem.Text = "$previewName|$subtitle"' not in hover_section
    assert "$script:statusBarItem.Text = \"  $(Get-TrayProfilePreviewText -ProfileId $ProfileId -Profile $profile)\"" not in hover_section
    assert "Set-MenuItemImageSafe -Item $script:statusBarItem -NewImage $previewImage" not in hover_section
    assert "Update-MenuState" not in hover_section
    assert "Clear-TrayProfileHoverPreview" in hover_section
    assert "Set-TrayLastAction" not in hover_section
    assert "Register-TrayProfileHoverPreview -Item $item -ProfileId $favId" in script
    assert "Register-TrayProfileHoverPreview -Item $item -ProfileId $rId" in script
    assert "Register-TrayProfileHoverPreview -Item $item -ProfileId $ProfileId" in script


def test_tray_search_reports_match_count_without_filtering_placeholder() -> None:
    """Search should show accurate match feedback and ignore placeholder text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Set-TraySearchStatus" in script
    assert "function Get-TraySearchResultGameGroups" in script
    assert "$script:searchStatusItem.Visible = $false" in script
    assert '$script:searchStatusItem.AccessibleDescription = ""' in script
    assert '$script:searchStatusItem.Text = "SEARCH: no matches | $cleanQuery"' in script
    assert '$script:searchStatusItem.Text = "SEARCH: $matchCount $plural | $cleanQuery"' in script
    assert '$script:searchStatusItem.Text = "  SEARCH: no matches | $cleanQuery"' not in script
    assert '$script:searchStatusItem.Text = "  SEARCH: $matchCount $plural | $cleanQuery"' not in script
    assert "$script:searchStatusItem.ForeColor = $script:Colors.AccentAmber" in script
    assert "$script:searchStatusItem.ForeColor = $script:Colors.AccentGold" in script
    assert '$script:searchStatusItem.ToolTipText = "No profile matches: $fullQuery"' in script
    assert '$script:searchStatusItem.ToolTipText = "${tooltipCount}: $fullQuery"' in script
    assert '$script:searchStatusItem.AccessibleDescription = "SEARCH|NONE"' in script
    assert '$script:searchStatusItem.AccessibleDescription = if ($matchCount -eq 1) { "SEARCH|MATCH" } else { "SEARCH|MATCHES" }' in script
    assert 'Set-MenuItemImageSafe -Item $script:searchStatusItem -NewImage (New-ActionBitmap -Action "Search" -Color $script:Colors.AccentAmber)' in script
    assert "$matchedGameGroups = Get-TraySearchResultGameGroups -MatchedIds $MatchedIds -Count 3" in script
    assert "New-GameMosaicBitmap -GameGroups $matchedGameGroups -Color $script:Colors.AccentGold -Category \"Other\"" in script
    assert 'Set-MenuItemImageSafe -Item $script:searchStatusItem -NewImage (New-ActionBitmap -Action "Search" -Color $script:Colors.AccentGold)' in script
    assert "$script:searchStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem" in script
    assert '$script:searchStatusItem.AccessibleName = "__status_bar__"' in script
    assert '$script:searchStatusItem.AccessibleDescription = "SEARCH"' in script
    assert "$script:searchStatusItem.Font = $script:FontEyebrow" in script
    assert '$script:searchStatusItem.Image = New-ActionBitmap -Action "Search" -Color $script:Colors.TextDim' in script
    assert "$menu.Items.Add($script:searchStatusItem) | Out-Null" in script
    assert "Set-TraySearchStatus -Query $query -MatchedIds $matchedIds" in script
    assert '$script:searchIsPlaceholder = $false\n            $this.Text = ""' in script
    assert '$script:searchIsPlaceholder = $true\n            $this.Text = "Search profiles..."' in script


def test_tray_search_result_icon_uses_matched_game_mosaic() -> None:
    """Positive search results should preview matched game identities."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    helper_section = script.split("function Get-TraySearchResultGameGroups", 1)[1].split(
        "function Set-TraySearchStatus",
        1,
    )[0]
    status_section = script.split("function Set-TraySearchStatus", 1)[1].split(
        "# ============================================================================\n# PROCESS GUARD",
        1,
    )[0]

    assert "$groups = [System.Collections.Generic.List[string]]::new()" in helper_section
    assert "Get-TrayProfileGameGroup -ProfileId \"$id\" -Profile $profile" in helper_section
    assert "$seen.ContainsKey($key)" in helper_section
    assert "if ($groups.Count -ge $Count) { break }" in helper_section
    assert "return @($groups)" in helper_section
    assert "$matchedGameGroups.Count -gt 0" in status_section
    assert "Get-Command New-GameMosaicBitmap -ErrorAction SilentlyContinue" in status_section
    assert "New-GameMosaicBitmap -GameGroups $matchedGameGroups" in status_section


def test_status_dashboard_uses_active_game_medallion() -> None:
    """Hero status banner should show the active/hovered game mark, not only a dot."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    renderer_section = script.split("// --- Hero Banner: active profile status item ---", 1)[1].split(
        "// --- Section headers",
        1,
    )[0]

    assert "Image heroImage = e.Item.Image;" in renderer_section
    assert "bool hasHeroImage = heroImage != null;" in renderer_section
    assert "double heroWave = (Math.Sin(PulseFrame / 6.0) + 1.0) / 2.0;" in renderer_section
    assert "int heroGlowAlpha = 36 + (int)(heroWave * 28);" in renderer_section
    assert "int heroRingAlpha = 120 + (int)(heroWave * 70);" in renderer_section
    assert "int orbitStart = (PulseFrame * 9) % 360;" in renderer_section
    assert "g.DrawArc(orbitPen, medallionX - 2, medallionY - 2, medallionSize + 3, medallionSize + 3, orbitStart, 82);" in renderer_section
    assert "int sweepX = medallionX + medallionSize + 8 + ((PulseFrame * 6) % Math.Max(1, w - medallionX - medallionSize - 88));" in renderer_section
    assert "g.DrawLine(sweepPen, sweepX, 6, Math.Min(w - 18, sweepX + 48), 6);" in renderer_section
    assert "g.DrawImage(heroImage, imageRect);" in renderer_section
    assert "int textX = hasHeroImage ? 54 : 28;" in renderer_section
    assert "Fallback glowing dot" in renderer_section

    assert "function Set-TrayStatusHeroImage" in script
    status_hero_section = script.split("function Set-TrayStatusHeroImage", 1)[1].split(
        "function Set-TrayActiveStatusItemFromState",
        1,
    )[0]
    assert "If catalog metadata is stale, keep the status hero identifiable" in status_hero_section
    assert "if (-not $Profile) {" not in status_hero_section
    assert '$category = if ($Profile -and $Profile.Cat) { "$($Profile.Cat)" } else { "Other" }' in (
        status_hero_section
    )
    assert '$variant = if ($Profile -and $Profile.Variant) { "$($Profile.Variant)" } else { "" }' in (
        status_hero_section
    )
    assert "New-ActiveGameBitmap `" in script
    assert "-ModeBadge $modeBadge" in script
    assert "-FavoriteBadge $favoriteBadge" in script
    assert "-PendingApplyBadge ([bool]$PendingApplyBadge)" in status_hero_section
    assert "-WindowsRestartBadge ([bool]$WindowsRestartBadge) `" in status_hero_section
    assert "-VerificationBadge ([bool]$VerificationBadge)" in status_hero_section
    assert "$favoriteBadge = (Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig)" in script
    assert "New-FavoriteGameBitmap `" in status_hero_section
    assert "New-GameSyncBadgeBitmap `" in status_hero_section
    assert '-SyncMode "agnostic" `' in status_hero_section
    assert "Set-MenuItemImageSafe -Item $script:statusItem -NewImage $heroImage" in script
    assert "Set-MenuItemImageSafe -Item $script:statusItem -NewImage $null" in script
    assert "Set-TrayActiveStatusItemFromState" in script
    assert "Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $p -ActiveBadge" in script
    assert "Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -PendingApplyBadge" in script
    assert "Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -WindowsRestartBadge" in script
    assert "Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $activeRecord.Profile -ActiveBadge -VerificationBadge" in script
    assert "Set-TrayStatusHeroImage -ProfileId $null -Profile $null" in script
    assert "Set-TrayStatusHeroImage -ProfileId $activeRecord.Id -Profile $null -ActiveBadge" in script
    assert "Set-TrayStatusHeroImage -ProfileId $ProfileId -Profile $profile -ActiveBadge:($ProfileId -eq $script:activeProfile)" not in script


def test_active_profile_menu_keeps_game_mark_with_status_badge() -> None:
    """Active rows should keep their game mark instead of degrading to a generic check."""
    icon_script = ICONS_SCRIPT.read_text(encoding="utf-8")
    tray_script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function New-ActiveGameBitmap" in icon_script
    assert "New-GameBitmap -GameGroup $GameGroup" in icon_script
    active_section = icon_script.split("function New-ActiveGameBitmap", 1)[1].split(
        "function New-FavoriteGameBitmap",
        1,
    )[0]
    assert '[string]$ModeBadge = ""' in active_section
    assert "[bool]$FavoriteBadge = $false" in active_section
    assert "[bool]$PendingApplyBadge = $false" in active_section
    assert "[bool]$WindowsRestartBadge = $false" in active_section
    assert "[bool]$VerificationBadge = $false" in active_section
    assert '$normalizedModeBadge = if ([string]::IsNullOrWhiteSpace($ModeBadge))' in active_section
    assert "Favorite corner badge stays away from the active check." in active_section
    assert "Active rows use the same top-right HDR/capture mode badge as" in active_section
    assert "shortcut rows; capture wins over HDR when both are true." in active_section
    assert "$g.FillPolygon($starBrush, $starPoints)" in active_section
    assert "$g.FillRectangle($modeBadgeBrush, 10, 1, 6, 6)" in active_section
    assert "$badgeColor = if ($PendingApplyBadge -or $WindowsRestartBadge)" in active_section
    assert "elseif ($VerificationBadge)" in active_section
    assert "[System.Drawing.Color]::FromArgb(255, 80, 170, 255)" in active_section
    assert "$g.DrawLine($pendingPen, [float]12.0, [float]9.8, [float]12.0, [float]12.7)" in active_section
    assert "$g.FillEllipse($pendingDotBrush, [float]11.35, [float]13.35, [float]1.3, [float]1.3)" in (
        active_section
    )
    assert "$g.DrawArc($restartPen, [float]9.7, [float]9.7, [float]4.9, [float]4.9, 38, 286)" in (
        active_section
    )
    assert "$g.DrawLine($restartPen, [float]12.1, [float]9.4, [float]12.1, [float]12.2)" in (
        active_section
    )
    assert "$g.DrawArc($verifyPen, [float]9.9, [float]9.9, [float]4.8, [float]4.8, 205, 290)" in (
        active_section
    )
    assert "$g.DrawLine($verifyPen, [float]12.0, [float]12.0, [float]14.5, [float]10.6)" in active_section
    assert "$g.FillEllipse($verifyDotBrush, [float]11.35, [float]11.35, [float]1.4, [float]1.4)" in (
        active_section
    )
    assert "$g.DrawLine($checkPen, [float]9.8, [float]12.0, [float]11.4, [float]13.6)" in active_section
    assert "Compact badge keeps the game silhouette visible" in icon_script
    assert "New-TrayProfileMenuImage" in tray_script
    assert "New-ActiveGameBitmap `" in tray_script
    assert "-GameGroup $gameGroup" in tray_script
    assert "-ModeBadge $modeBadge" in tray_script
    assert "-FavoriteBadge $FavoriteBadge" in tray_script
    assert "$pendingApplyBadge = -not [string]::IsNullOrWhiteSpace((Get-ActiveProfilePendingApplyText))" in tray_script
    assert "$windowsRestartBadge = (" in tray_script
    assert "$verificationBadge = (" in tray_script
    assert "-PendingApplyBadge $pendingApplyBadge" in tray_script
    assert "-WindowsRestartBadge $windowsRestartBadge" in tray_script
    assert "-VerificationBadge $verificationBadge" in tray_script
    menu_state_section = tray_script.split("function Update-MenuState", 1)[1].split(
        "# ============================================================================\n# SYSTEM INFO",
        1,
    )[0]
    assert "New-ActiveCheckBitmap" not in menu_state_section


def test_favorite_game_bitmap_composes_star_with_game_and_sync_badges() -> None:
    """Favorite rows should get a compact star without replacing game/sync art."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    favorite_section = script.split("function New-FavoriteGameBitmap", 1)[1].split(
        "function New-ActionBitmap",
        1,
    )[0]

    assert "Creates a game-specific profile bitmap with a compact favorite star badge." in favorite_section
    assert '[string]$ModeBadge = ""' in favorite_section
    assert "New-GameSyncBadgeBitmap -GameGroup $GameGroup -Color $Color -Category $Category -SyncMode $SyncMode -ModeBadge $ModeBadge" in favorite_section
    assert "$starPoints = [System.Drawing.PointF[]]@(" in favorite_section
    assert "$shadowPoints = [System.Drawing.PointF[]]@(" in favorite_section
    assert "Favorite star badge keeps the game/sync mark visible" in favorite_section
    assert "$g.FillPolygon($shadowBrush, $shadowPoints)" in favorite_section
    assert "$g.FillPolygon($starBrush, $starPoints)" in favorite_section
    assert "$g.DrawPolygon($starPen, $starPoints)" in favorite_section


def test_favorite_game_mosaic_bitmap_overlays_star_on_game_marks() -> None:
    """Favorites header should preview pinned game marks while keeping the favorite star cue."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    favorite_mosaic_section = script.split("function New-FavoriteGameMosaicBitmap", 1)[1].split(
        "function New-ActionBitmap",
        1,
    )[0]

    assert "Creates a compact favorite-section mosaic from actual game marks." in favorite_mosaic_section
    assert "Favorites headers should preview the pinned games themselves" in favorite_mosaic_section
    assert "New-GameMosaicBitmap -GameGroups $GameGroups -Color $Color -Category $Category" in favorite_mosaic_section
    assert "$starPoints = [System.Drawing.PointF[]]@(" in favorite_mosaic_section
    assert "$shadowPoints = [System.Drawing.PointF[]]@(" in favorite_mosaic_section
    assert "$g.FillPolygon($starShadowBrush, $shadowPoints)" in favorite_mosaic_section
    assert "$g.FillPolygon($starBrush, $starPoints)" in favorite_mosaic_section
    assert "$g.DrawPolygon($starPen, $starPoints)" in favorite_mosaic_section


def test_backup_game_mosaic_bitmap_overlays_restore_cue_on_game_marks() -> None:
    """Backups header should preview restorable game marks with a restore cue."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    backup_mosaic_section = script.split("function New-BackupGameMosaicBitmap", 1)[1].split(
        "function New-ActionBitmap",
        1,
    )[0]

    assert "Creates a compact backup-section mosaic from restorable profile game marks." in backup_mosaic_section
    assert "Backup headers should show which games have restore points available" in backup_mosaic_section
    assert "New-GameMosaicBitmap -GameGroups $GameGroups -Color $Color -Category $Category" in backup_mosaic_section
    assert "$g.FillEllipse($badgeShadowBrush, 7, 7, 9, 9)" in backup_mosaic_section
    assert "$g.FillEllipse($badgeBrush, 8, 8, 8, 8)" in backup_mosaic_section
    assert "$g.DrawEllipse($badgeRingPen, [float]8.0, [float]8.0, [float]7.6, [float]7.6)" in backup_mosaic_section
    assert "$g.DrawLine($arrowPen, [float]10.2, [float]11.5, [float]13.6, [float]11.5)" in backup_mosaic_section
    assert "$g.DrawLine($arrowPen, [float]10.0, [float]9.9, [float]10.0, [float]13.0)" in backup_mosaic_section


def test_game_sync_badge_can_add_hdr_or_capture_mode_marker() -> None:
    """HDR/capture variants should be visible in the icon, not only in row text."""
    script = ICONS_SCRIPT.read_text(encoding="utf-8")
    badge_section = script.split("function New-GameSyncBadgeBitmap", 1)[1]

    assert '[string]$ModeBadge = ""' in badge_section
    assert '$normalizedModeBadge = if ([string]::IsNullOrWhiteSpace($ModeBadge))' in badge_section
    assert '$normalizedModeBadge -ne "hdr" -and $normalizedModeBadge -ne "capture"' in badge_section
    assert "$hasSyncBadge = ($SyncMode -eq \"on\" -or $SyncMode -eq \"off\")" in badge_section
    assert "if (-not $hasSyncBadge -and [string]::IsNullOrWhiteSpace($normalizedModeBadge)) { return $bmp }" in badge_section
    assert "Mode badge uses the top-right corner so favorite stars and sync" in badge_section
    assert "badges remain legible. Capture wins over HDR when both are true." in badge_section
    assert '$modeColor = if ($normalizedModeBadge -eq "capture")' in badge_section
    assert "$g.FillRectangle($modeBadgeBrush, 10, 1, 6, 6)" in badge_section
    assert "$g.DrawEllipse($modePen, [float]11.6, [float]2.5, [float]2.8, [float]2.8)" in badge_section
    assert '$g.DrawString("H", $modeFont, $modeTextBrush' in badge_section


def test_profile_menu_refresh_preserves_submenu_variant_labels_and_sync_badges() -> None:
    """State refresh should not replace flyout variant rows with repeated full game names."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    icon_script = ICONS_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-ProfileMenuDisplayText" in script
    assert "if ($InSubmenu) { return (Get-ProfileVariantLabel -ProfileId $ProfileId) }" in script
    assert "function New-TrayProfileMenuImage" in script
    assert '[bool]$ShowSyncBadge = $false' in script
    assert '[bool]$FavoriteBadge = $false' in script
    profile_image_section = script.split("function New-TrayProfileMenuImage", 1)[1].split(
        "function New-TrayGameGroupMedallionBitmap",
        1,
    )[0]
    assert '$modeBadge = if ("$ProfileId" -match \'(?i)capture\' -or $variant -match \'(?i)capture\')' in script
    assert 'elseif ($variant -match \'(?i)\\bHDR\\b\' -or "$ProfileId" -match \'(?i)-hdr($|-)\' )' in script
    assert "$pendingApplyBadge = -not [string]::IsNullOrWhiteSpace((Get-ActiveProfilePendingApplyText))" in (
        profile_image_section
    )
    assert "-not [string]::IsNullOrWhiteSpace((Get-ActiveProfileRebootPendingText))" in profile_image_section
    assert "-not [string]::IsNullOrWhiteSpace((Get-ActiveProfileVerificationInProgressText))" in (
        profile_image_section
    )
    assert "-PendingApplyBadge $pendingApplyBadge `" in profile_image_section
    assert "-WindowsRestartBadge $windowsRestartBadge `" in profile_image_section
    assert "-VerificationBadge $verificationBadge" in profile_image_section
    assert "New-FavoriteGameBitmap `" in script
    assert 'if ($InSubmenu -or $ShowSyncBadge) {' in script
    assert "New-GameSyncBadgeBitmap `" in script
    assert "-GameGroup $gameGroup `" in script
    assert "-SyncMode $syncMode" in script
    assert "-ModeBadge $modeBadge" in script
    assert "function New-GameSyncBadgeBitmap" in icon_script
    assert "New-GameBitmap -GameGroup $GameGroup -Color $Color -Category $Category" in icon_script
    assert "Game-sync badge keeps the game silhouette visible" in icon_script
    assert "New-SyncBadgeImage -SyncMode $syncMode" not in script
    assert "Get-ProfileMenuDisplayText -ProfileId $item.Tag -InSubmenu $inSubmenu" in script
    assert '$showSyncBadge = ($item.AccessibleName -eq "__profile_menu_item__")' in script
    assert "$favoriteBadge = (Test-Favorite -ProfileId $item.Tag -Config $script:TrayConfig)" in script
    assert "-ShowSyncBadge $showSyncBadge" in script
    assert "-FavoriteBadge $favoriteBadge" in script
    assert "New-TrayProfileMenuImage `" in script
    assert "New-TrayGameGroupMedallionBitmap" in script


def test_favorite_recent_and_direct_rows_keep_game_marks_with_sync_badges() -> None:
    """High-frequency shortcut rows should show game identity plus sync state."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    favorites_section = script.split("# \u2500\u2500\u2500 FAVORITES \u2500\u2500\u2500", 1)[1].split(
        "# \u2500\u2500\u2500 RECENT \u2500\u2500\u2500",
        1,
    )[0]
    recent_section = script.split("# \u2500\u2500\u2500 RECENT \u2500\u2500\u2500", 1)[1].split(
        "# \u2500\u2500\u2500 PROFILES (game submenus with sync badges) \u2500\u2500\u2500",
        1,
    )[0]
    profile_helper_section = script.split("function New-ProfileMenuItem", 1)[1].split(
        "function New-GameFlyoutHeaderItem",
        1,
    )[0]

    assert "New-TrayProfileMenuImage `" in favorites_section
    assert "-ProfileId $favId `" in favorites_section
    assert "-ShowSyncBadge $true" in favorites_section
    assert "-FavoriteBadge $true" in favorites_section
    assert "New-GameBitmap -GameGroup $gg" not in favorites_section
    assert "New-TrayProfileMenuImage `" in recent_section
    assert "-ProfileId $rId `" in recent_section
    assert "-ShowSyncBadge $true" in recent_section
    assert "-FavoriteBadge $true" not in recent_section
    assert "New-GameBitmap -GameGroup $gg" not in recent_section
    assert "-ShowSyncBadge $ShowBadge" in profile_helper_section
    assert "-FavoriteBadge $isFav" in profile_helper_section


def test_profile_menu_rows_render_compact_status_chips() -> None:
    """Profile rows should expose mode/capture/HDR state without replacing game marks."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert (
        'if (e.Item.AccessibleName == "__profile_menu_item__" || '
        'e.Item.AccessibleName == "__backup_menu_item__")'
    ) in script
    assert 'string chipRaw = e.Item.AccessibleDescription ?? "";' in script
    assert "string[] chips = chipRaw.Split(new char[] { '|' }, StringSplitOptions.RemoveEmptyEntries);" in script
    assert "for (int i = chips.Length - 1; i >= 0; i--)" in script
    assert "string chip = chips[i].Trim();" in script
    assert "int chipX = chipRight - chipWidth;" in script
    assert "FillRoundRect(e.Graphics, chipBrush, chipRect, 4)" in script
    assert "DrawRoundRect(e.Graphics, chipPen, chipRect, 4)" in script
    assert "e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat)" in script
    assert "bool isActiveProfileChip = profileMenuItem != null && profileMenuItem.Checked;" in script
    assert "int chipEdgeAlpha = isActiveProfileChip ? 105 + (int)(chipWave * 70) : 90;" in script
    assert "int chipSweepX = chipRect.X + 4 + ((PulseFrame * 4) % sweepTravel);" in script
    assert "function Get-ProfileMenuChipText" in script
    assert 'return "CAPTURE"' in script
    assert 'return "G-SYNC"' in script
    assert 'return "NO-SYNC"' in script
    assert 'return "HDR"' in script
    assert 'return "SDR"' in script
    assert "function Get-ProfileMenuActiveStateChipText" in script
    assert 'if ("$ProfileId" -ne "$script:activeProfile") { return "" }' in script
    assert 'if (Get-ActiveProfilePendingApplyText) { return "FIX" }' in script
    assert 'if (Get-ActiveProfileRebootPendingText) { return "RESTART" }' in script
    assert 'if (Get-ActiveProfileVerificationInProgressText) { return "CHECK" }' in script
    assert "function Get-ProfileMenuActiveStateTooltipText" in script
    assert 'return "Active state: pending profile fix for $pendingText"' in script
    assert 'return "Active state: profile mismatch for $pendingText"' in script
    assert 'return "Active state: Windows restart required for $rebootText"' in script
    assert 'return "Active state: checking profile state"' in script
    assert "function Set-TrayProfileMenuItemTooltipState" in script
    assert "Native ToolStrip tooltips float over the owner-drawn profile list." in script
    assert '$Item.ToolTipText = ""' in script
    assert "function Get-TrayProfileChipPaddingRight" in script
    assert "return [Math]::Min(260, 82 + (($ChipCount - 1) * 72))" in script
    assert "function Set-TrayProfileMenuItemMetadata" in script
    assert '$Item.AccessibleName = "__profile_menu_item__"' in script
    assert "[string]$ExtraChipText = \"\"" in script
    assert "$stateChipText = Get-ProfileMenuActiveStateChipText -ProfileId $ProfileId" in script
    assert "$stateTooltipText = Get-ProfileMenuActiveStateTooltipText -ProfileId $ProfileId" in script
    assert "if (-not [string]::IsNullOrWhiteSpace($stateChipText)) { $chips += $stateChipText }" in script
    assert "Set-TrayProfileMenuItemTooltipState -Item $Item -StateText $stateTooltipText" in script
    assert "$Item.AccessibleDescription = ($chips -join \"|\")" in script
    assert "$paddingRight = Get-TrayProfileChipPaddingRight -ChipCount $chips.Count" in script
    assert "$Item.Padding = New-Object System.Windows.Forms.Padding(0, 0, $paddingRight, 0)" in script
    assert "Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $favId -Profile $p" in script
    assert 'Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $rId -Profile $p -ExtraChipText "RECENT"' in script
    assert "Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $ProfileId -Profile $p" in script
    assert "Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $item.Tag -Profile $p" in script


def test_recent_profile_rows_keep_recency_chip_after_menu_state_refresh() -> None:
    """Recent profile rows should keep RECENT context alongside sync/mode chips."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    metadata_section = script.split("function Set-TrayProfileMenuItemMetadata", 1)[1].split(
        "function Get-GameFlyoutHeaderSummaryChips",
        1,
    )[0]
    recent_section = script.split("# ─── RECENT ───", 1)[1].split(
        "# ─── PROFILES (game submenus with sync badges) ───",
        1,
    )[0]

    assert 'Set-TrayProfileMenuItemMetadata -Item $item -ProfileId $rId -Profile $p -ExtraChipText "RECENT"' in recent_section
    assert "$Item.AccessibleDescription -and" in metadata_section
    assert "\"$($Item.AccessibleDescription)\" -match '(^|\\|)RECENT(\\||$)'" in metadata_section
    assert '$ExtraChipText = "RECENT"' in metadata_section
    assert "if (-not [string]::IsNullOrWhiteSpace($chipText)) { $chips += $chipText }" in metadata_section
    assert (
        "if (-not [string]::IsNullOrWhiteSpace($ExtraChipText)) "
        "{ $chips += $ExtraChipText.Trim().ToUpperInvariant() }"
    ) in metadata_section
    assert "if (-not [string]::IsNullOrWhiteSpace($stateChipText)) { $chips += $stateChipText }" in metadata_section
    assert '$Item.AccessibleDescription = ($chips -join "|")' in metadata_section


def test_active_profile_menu_row_has_renderer_driven_pulse() -> None:
    """Active profile rows should animate through the renderer without backend work."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "public static int PulseFrame = 0;" in script
    assert 'bool isActiveProfileRow = e.Item.AccessibleName == "__profile_menu_item__" &&' in script
    assert "profileMenuItem != null && profileMenuItem.Checked" in script
    assert "double wave = (Math.Sin(PulseFrame / 4.0) + 1.0) / 2.0;" in script
    assert "Rectangle activeRect = GetBoundedRowRect(rect, 430, 250);" in script
    assert "FillRoundRect(g, brush, activeRect, 5)" in script
    assert "DrawRoundRect(g, pen, activeRect, 5)" in script
    assert "int sweepX = activeRect.X + 9 + ((PulseFrame * 7) % sweepTravel);" in script
    assert "g.DrawLine(sweepPen, sweepX, activeRect.Y + 2, Math.Min(activeRect.Right - 9, sweepX + sweepWidth), activeRect.Y + 2);" in script
    assert "double chipWave = (Math.Sin(PulseFrame / 4.5) + 1.0) / 2.0;" in script
    assert "e.Graphics.DrawLine(chipSweepPen, chipSweepX, chipRect.Y + 2, Math.Min(chipRect.Right - 4, chipSweepX + sweepWidth), chipRect.Y + 2);" in script
    assert "$script:TrayMenuPulseTimer = $null" in script
    assert "$script:TrayMenuPulseFrame = 0" in script
    assert "function Invoke-TrayMenuPulseInvalidation" in script
    assert "$menu.Invalidate()" in script
    assert "$item.Owner.Invalidate()" in script
    assert "function Start-TrayMenuPulseTimer" in script
    assert "$script:TrayMenuPulseTimer.Interval = 90" in script
    assert "$script:TrayMenuPulseFrame = ($script:TrayMenuPulseFrame + 1) % 120" in script
    assert "[DarkThemeRenderer]::PulseFrame = $script:TrayMenuPulseFrame" in script
    assert "Invoke-TrayMenuPulseInvalidation" in script
    assert "Start-TrayMenuPulseTimer" in script
    assert "function Stop-TrayMenuPulseTimer" in script
    assert "Stop-TrayMenuPulseTimer" in script


def test_tray_row_highlights_are_bounded_to_content() -> None:
    """Hover and active treatments should not paint empty full-width slabs."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    hover_section = script.split("if (e.Item.Selected && e.Item.Enabled)", 1)[1].split(
        "else if (e.Item.Pressed)",
        1,
    )[0]

    assert "Rectangle selectedRect = GetBoundedRowRect(rect, 440, 250);" in hover_section
    assert "FillRoundRect(g, brush, selectedRect, 5)" in hover_section
    assert "DrawRoundRect(g, pen, selectedRect, 5)" in hover_section
    assert "var fadeRect = new Rectangle(selectedRect.Right - fadeW, selectedRect.Y, fadeW, selectedRect.Height);" in hover_section


def test_game_flyouts_have_identity_headers_without_breaking_search() -> None:
    """Game variant flyouts should have a visual header that search ignores."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'if (e.Item.AccessibleName == "__game_flyout_header__")' in script
    assert 'string chipRaw = e.Item.AccessibleDescription ?? "";' in script
    assert "e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat)" in script
    assert "e.Graphics.DrawString(labelText.ToUpperInvariant(), labelFont, labelBrush, labelRect, labelFormat)" in script
    assert "function Get-GameFlyoutHeaderSummaryChips" in script
    assert '${syncOn} G-SYNC' in script
    assert '${syncOff} NO-SYNC' in script
    assert '${hdr} HDR' in script
    assert '${capture} CAP' in script
    assert "function New-GameFlyoutHeaderItem" in script
    assert '$headerItem.Tag = "__game_flyout_header__"' in script
    assert '$headerItem.AccessibleName = "__game_flyout_header__"' in script
    assert "$headerItem.AccessibleDescription = Get-GameFlyoutHeaderSummaryChips -ProfileIds $ProfileIds" in script
    assert "$headerItem.Padding = New-Object System.Windows.Forms.Padding(0, 0, 76, 0)" in script
    assert '$headerItem.Text = "$($GroupInfo.Name)  |  $variantLabel"' in script
    assert "$headerItem.Image = New-TrayGameGroupMedallionBitmap -GameGroup $GameGroup -Color $gameColor -Category $Category" in script
    assert "$submenuItem.Image = New-TrayGameGroupMedallionBitmap -GameGroup $gameGroup -Color $submenuGameColor -Category $cat" in script
    assert '$profileVariantChip = ""' in script
    assert '$submenuItem.ToolTipText = "Open profile choices for $($groupInfo.Name): $($profileIds.Count)"' in script
    assert "function Set-TrayGameGroupRowVisualState" in script
    assert '$Item.AccessibleName = "__game_group_row__"' in script
    assert "Set-TrayGameGroupRowVisualState -Item $submenuItem" in script
    assert '$headerItem.ToolTipText = "Game group header for $($GroupInfo.Name): $variantLabel"' in script
    assert "$flyoutHeader = New-GameFlyoutHeaderItem `" in script
    assert "-ProfileIds $profileIds" in script
    assert "$submenuItem.DropDownItems.Add($flyoutHeader) | Out-Null" in script
    assert '$child.Tag -ne "__game_flyout_header__"' in script


def test_game_group_menu_rows_use_compact_medallions() -> None:
    """Game group rows should get the newer ringed mark without changing profile variant badges."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    game_row_background = script.split("// --- Game group rows: readable lane entries with color carried by rails/icons ---", 1)[1].split(
        "// --- Section headers",
        1,
    )[0]
    game_row_text = script.split('if (e.Item.AccessibleName == "__game_group_row__")', 2)[2].split(
        'if (e.Item.AccessibleName == "__category_header__" || e.Item.AccessibleName == "__section_header__")',
        1,
    )[0]

    assert 'e.Item.AccessibleName == "__game_group_row__"' in game_row_background
    assert "Rectangle laneRect = GetBoundedRowRect(rect, 350, 190);" in game_row_background
    assert "Color.FromArgb(20, tint.R, tint.G, tint.B)" in game_row_background
    assert "FillRoundRect(g, brush, laneRect, 4)" in game_row_background
    assert "var railRect = new Rectangle(laneRect.X + 5, laneRect.Y + 4, 4, Math.Max(3, laneRect.Height - 8));" in game_row_background
    assert "g.DrawLine(pen, laneRect.X + 18, laneRect.Y + 1, Math.Min(laneRect.Right - 14, laneRect.X + 128), laneRect.Y + 1);" in game_row_background
    assert "Color labelColor = TextPaper;" in game_row_text
    assert "ResolveEyebrowFont(11.0f)" not in game_row_text
    assert 'e.Graphics.DrawString((e.Text ?? "").Trim(), e.TextFont, labelBrush, labelRect, labelFormat);' in game_row_text

    medallion_section = script.split("function New-TrayGameGroupMedallionBitmap", 1)[1].split(
        "function Get-TrayProfileMenuAccent",
        1,
    )[0]
    assert "New-GameBitmap -GameGroup $GameGroup -Color $Color -Category $Category" in medallion_section
    assert "$g.FillEllipse($glowBrush, 0, 0, 16, 16)" in medallion_section
    assert "$g.DrawEllipse($ringPen, 2, 2, 12, 12)" in medallion_section
    assert "$g.DrawArc($arcPen, 1, 1, 14, 14, 215, 50)" in medallion_section
    assert "$g.DrawImage($mark, (New-Object System.Drawing.Rectangle(3, 3, 10, 10)))" in medallion_section
    profile_image_section = script.split("function New-TrayProfileMenuImage", 1)[1].split(
        "function New-TrayGameGroupMedallionBitmap",
        1,
    )[0]
    assert "$profile = $null" in profile_image_section
    assert "$script:Profiles -and $script:Profiles.Contains($ProfileId)" in profile_image_section
    assert 'else { "Other" }' in profile_image_section
    assert "Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $profile -Fallback $script:Colors.Text" in (
        profile_image_section
    )
    assert "Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $profile" in profile_image_section
    assert "if (-not $profile) { return $null }" not in profile_image_section
    assert "New-GameSyncBadgeBitmap `" in profile_image_section
    assert "New-TrayGameGroupMedallionBitmap" not in profile_image_section


def test_category_headers_avoid_game_mark_icons() -> None:
    """Category bands should not look like selectable game/profile rows."""
    icon_script = ICONS_SCRIPT.read_text(encoding="utf-8")
    tray_script = TRAY_SCRIPT.read_text(encoding="utf-8")
    mosaic_section = icon_script.split("function New-GameMosaicBitmap", 1)[1].split(
        "function New-ActionBitmap",
        1,
    )[0]
    category_section = tray_script.split('$catItem = New-Object System.Windows.Forms.ToolStripMenuItem', 1)[1].split(
        '$menu.Items.Add($catItem) | Out-Null',
        1,
    )[0]

    assert "function New-GameMosaicBitmap" in icon_script
    assert "Creates a compact 16x16 category mosaic from actual game marks." in mosaic_section
    assert "return New-CategoryBitmap -Category $Category -Color $Color" in mosaic_section
    assert "New-GameBitmap -GameGroup $group -Color $markColor -Category $Category" in mosaic_section
    assert "Get-GameAccentColor -GameGroup $group -FallbackColor $baseColor" in mosaic_section
    assert "$g.DrawImage($mark, $rect)" in mosaic_section
    assert "$catItem.Image = $null" in category_section
    assert "New-GameMosaicBitmap -GameGroups $categorySampleGameGroups" not in category_section
    assert "New-CategoryBitmap -Category $cat" not in category_section


def test_category_headers_keep_counts_in_tooltips_without_breaking_filtering() -> None:
    """Top-level category bands should not draw visible count badges."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'if (e.Item.AccessibleName == "__category_header__" || e.Item.AccessibleName == "__section_header__")' in script
    assert 'string chipRaw = e.Item.AccessibleDescription ?? "";' in script
    assert "e.Graphics.DrawString(chip, chipFont, chipTextBrush, chipRect, chipFormat)" in script
    assert 'e.Graphics.DrawString((e.Item.Text ?? "").Trim().ToUpperInvariant(), labelFont, labelBrush, labelRect, labelFormat)' in script
    assert "function Get-CategoryHeaderSummaryChips" in script
    assert 'return "$GameCount $gameLabel, $ProfileCount $profileLabel"' in script
    assert "$catGameCount = @($catGameGroups[$cat].Keys).Count" in script
    assert "$catProfileCount += @($catGameGroups[$cat][$gameGroupKey]).Count" in script
    assert '$catItem.AccessibleName = "__category_header__"' in script
    assert '$catItem.AccessibleDescription = ""' in script
    assert "$catItem.ToolTipText = Get-CategoryHeaderSummaryChips -GameCount $catGameCount -ProfileCount $catProfileCount" in script
    assert "$catItem.Padding = New-Object System.Windows.Forms.Padding(0)" in script
    assert "$catItem.ForeColor = Get-TrayCategoryHeaderTint -Category $cat -CategoryColor $catColor" in script
    assert "$catItem.Tag = $cat" in script


def test_profile_toasts_use_game_marks_without_breaking_generic_toasts() -> None:
    """Profile apply/fix toasts should carry game marks, while generic toasts remain optional."""
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '[string]$ProfileGameGroup = ""' in notifications
    assert "[System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty" in notifications
    assert "New-GameBitmap -GameGroup $ProfileGameGroup" in notifications
    assert "New-ActiveGameBitmap `" in notifications
    assert "function New-ProfileMarkMedallionBitmap" in notifications
    assert "function New-ActionMarkMedallionBitmap" in notifications
    medallion_section = notifications.split("function New-ProfileMarkMedallionBitmap", 1)[1].split(
        "# ============================================================================\n# FORM CONSTRUCTION",
        1,
    )[0]
    assert "Wraps a game/profile mark in the same circular glow/ring treatment" in medallion_section
    assert "$g.FillEllipse($glowBrush, 1, 1, 34, 34)" in medallion_section
    assert "$g.DrawEllipse($ringPen, 5, 5, 26, 26)" in medallion_section
    assert "$g.DrawArc($tickPen, 3, 3, 30, 30, 212, 42)" in medallion_section
    assert "$g.DrawImage($mark, (New-Object System.Drawing.Rectangle(9, 9, 18, 18)))" in medallion_section
    assert '[string]$ModeBadge = ""' in medallion_section
    assert "[switch]$FavoriteBadge" in medallion_section
    assert "-ModeBadge $ModeBadge `" in medallion_section
    assert "-FavoriteBadge ([bool]$FavoriteBadge)" in medallion_section
    assert "New-FavoriteGameBitmap `" in medallion_section
    assert "New-GameSyncBadgeBitmap `" in medallion_section
    action_medallion_section = notifications.split("function New-ActionMarkMedallionBitmap", 1)[1].split(
        "# ============================================================================\n# FORM CONSTRUCTION",
        1,
    )[0]
    assert "Wraps a tray action glyph in the same toast medallion treatment" in action_medallion_section
    assert "$mark = New-ActionBitmap -Action $ActionName -Color $Color" in action_medallion_section
    assert "$g.DrawImage($mark, (New-Object System.Drawing.Rectangle(10, 10, 16, 16)))" in action_medallion_section
    toast_form_section = notifications.split("function _Build-ToastForm", 1)[1].split(
        "# Eyebrow",
        1,
    )[0]
    assert "New-ProfileMarkMedallionBitmap `" in toast_form_section
    assert 'New-ActionMarkMedallionBitmap -ActionName $ActionName -Color $markColor' in toast_form_section
    assert "$hasSideMark = ($hasProfileMark -or $hasActionMark)" in toast_form_section
    assert '$gutterX   = if ($hasSideMark) { 76 } else { 28 }' in toast_form_section
    assert "-ProfileGameGroup $ProfileGameGroup `" in toast_form_section
    assert "-ActiveBadge:$ProfileActiveBadge" in toast_form_section
    assert "-ModeBadge $ProfileModeBadge `" in toast_form_section
    assert "-FavoriteBadge:$ProfileFavoriteBadge" in toast_form_section
    assert "ProfileImageBox = $profileImageBox" in notifications
    assert "ProfileImage = $profileImage" in notifications
    assert "$tt.ProfileImage.Dispose()" in notifications
    assert "ProfileGameGroup = $ProfileGameGroup; ProfileCategory = $ProfileCategory" in notifications
    assert "ProfileActiveBadge = [bool]$ProfileActiveBadge" in notifications
    assert "ProfileModeBadge = $ProfileModeBadge; ProfileFavoriteBadge = [bool]$ProfileFavoriteBadge" in notifications
    assert "ActionName = $ActionName; ActionColor = $ActionColor" in notifications
    assert "-ProfileModeBadge $q.ProfileModeBadge -ProfileFavoriteBadge:([bool]$q.ProfileFavoriteBadge)" in notifications
    assert "-ActionName $q.ActionName -ActionColor $q.ActionColor" in notifications
    assert "Get-TrayProfileToastVisualArgs" in tray
    assert "ProfileModeBadge = $modeBadge" in tray
    assert "ProfileFavoriteBadge = [bool]$favoriteBadge" in tray
    assert "Catalog-drift or user-profile misses still get deterministic stylized" in tray
    assert "if (-not $Profile) { return @{} }" not in tray
    assert "function Show-TrayToast" in tray
    assert "Set-TransientNotificationTooltip -Title $Title -Message $Message" in tray
    assert "if ($script:EnableBalloonNotifications)" in tray
    assert "-ProfileModeBadge $ProfileModeBadge `" in tray
    assert "-ProfileFavoriteBadge:$ProfileFavoriteBadge" in tray
    assert '[string]$ActionName = ""' in tray
    assert "[System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty" in tray
    assert "-ActionName $ActionName `" in tray
    assert "-ActionColor $ActionColor" in tray
    assert "Show-TrayToast @toastProfileVisual" in tray
    assert "Show-TrayToast @pendingToastVisual" in tray
    assert "Show-ThemedToast @toastProfileVisual" not in tray
    assert "Show-ThemedToast @pendingToastVisual" not in tray
    assert "Show-Notification @failureVisual" in tray
    assert "Show-Notification @pendingFailureVisual" in tray


def test_generic_toast_titles_are_type_accurate_not_vague_soft_warnings() -> None:
    """Empty generic toast fallbacks should name the tray status type directly."""
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    title_section = notifications.split("function _Derive-ToastTitle", 1)[1].split(
        "function _Derive-ToastBody",
        1,
    )[0]
    assert '"Success" { return "Tray action complete" }' in title_section
    assert '"Warning" { return "Tray warning" }' in title_section
    assert '"Error"   { return "Tray error" }' in title_section
    assert 'default   { return "Tray status" }' in title_section
    assert "Heads up" not in title_section
    assert "Something went wrong" not in title_section


def test_profile_toast_visual_args_fallback_to_profile_id_art() -> None:
    """Profile-id-only notices should still get deterministic game/profile art."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    visual_args_section = script.split("function Get-TrayProfileToastVisualArgs", 1)[1].split(
        "function Get-SyncTransitionDirection",
        1,
    )[0]
    apply_profile_section = script.split("function Apply-Profile", 1)[1].split(
        "if ($sameActiveProfile",
        1,
    )[0]

    assert "Catalog-drift or user-profile misses still get deterministic stylized" in visual_args_section
    assert "if (-not $Profile) { return @{} }" not in visual_args_section
    assert '$category = if ($Profile -and $Profile.Cat) { "$($Profile.Cat)" } else { "Other" }' in (
        visual_args_section
    )
    assert "$gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $Profile" in visual_args_section
    assert "$color = Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $Profile -Fallback $script:Colors.Text" in (
        visual_args_section
    )
    assert '$variant = if ($Profile -and $Profile.Variant) { "$($Profile.Variant)" } else { "" }' in (
        visual_args_section
    )
    assert "$missingProfileVisual = Get-TrayProfileToastVisualArgs -ProfileId $ProfileId -Profile $null" in (
        apply_profile_section
    )
    assert "$missingProfileTitle = Get-TrayProfileDisplayName -ProfileId $ProfileId" in apply_profile_section
    assert 'Write-TrayLog "Profile missing from current profile list: $ProfileId" -Level "WARN"' in apply_profile_section
    assert (
        'Show-Notification @missingProfileVisual -Title $missingProfileTitle '
        '-Message "Profile missing from current list." -Type "Warning" -MetaText $ProfileId'
    ) in apply_profile_section
    assert 'Set-IconState -State "Warning"' in apply_profile_section
    assert 'Set-TrayLastAction -Message "Profile missing from current list: $missingProfileTitle"' in apply_profile_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Profile not found: $ProfileId"' not in (
        apply_profile_section
    )
    assert 'Set-TrayLastAction -Message "Profile not found: $ProfileId"' not in apply_profile_section


def test_legacy_notification_helper_uses_current_tray_policy_when_available() -> None:
    """Legacy helper should not leave stale hover text or bypass disabled toast popups."""
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    legacy_section = notifications.split("function Show-ABSONotification", 1)[1].split(
        "# ============================================================================\n# STATUS BAR",
        1,
    )[0]
    assert "Set-TransientNotificationTooltip -Title $Title -Message $Message" in legacy_section
    assert "Get-Variable -Name EnableBalloonNotifications -Scope Script" in legacy_section
    assert "if ($popupToggle -and -not $script:EnableBalloonNotifications) { return }" in legacy_section
    assert '$NotifyIcon.Text = "$Title - $Message".Substring' not in legacy_section
    assert '$tooltipText = $tooltipText.Substring(0, 60) + "..."' in legacy_section
    assert '[string]$ActionName = ""' in legacy_section
    assert "[System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty" in legacy_section
    assert "-ActionName $ActionName `" in legacy_section
    assert "-ActionColor $ActionColor" in legacy_section


def test_progress_overlay_uses_profile_or_action_medallions() -> None:
    """Profile and action progress overlays should carry specific medallion art."""
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    progress_section = notifications.split("function Show-ProgressOverlay", 1)[1].split(
        "function Update-ProgressOverlay",
        1,
    )[0]
    close_section = notifications.split("function Close-ProgressOverlay", 1)[1].split(
        "# ============================================================================\n# LEGACY COMPAT",
        1,
    )[0]
    assert '[string]$ProfileGameGroup = ""' in progress_section
    assert "[System.Drawing.Color]$ProfileColor = [System.Drawing.Color]::Empty" in progress_section
    assert '[string]$ProfileModeBadge = ""' in progress_section
    assert "[switch]$ProfileFavoriteBadge" in progress_section
    assert '[string]$ActionName = ""' in progress_section
    assert "[System.Drawing.Color]$ActionColor = [System.Drawing.Color]::Empty" in progress_section
    assert "$hasProfileMark" in progress_section
    assert "$hasActionMark" in progress_section
    assert "$hasSideMark = ($hasProfileMark -or $hasActionMark)" in progress_section
    assert "New-ProfileMarkMedallionBitmap `" in progress_section
    assert "-ProfileGameGroup $ProfileGameGroup `" in progress_section
    assert "-ActiveBadge:$ProfileActiveBadge" in progress_section
    assert "-ModeBadge $ProfileModeBadge `" in progress_section
    assert "-FavoriteBadge:$ProfileFavoriteBadge" in progress_section
    assert "New-ActionMarkMedallionBitmap -ActionName $ActionName -Color $accent" in progress_section
    assert "$width  = if ($hasSideMark) { 500 } else { 460 }" in progress_section
    assert "$capProgressAccent = $accent" in progress_section
    assert "$capHasSideMark = $hasSideMark" in progress_section
    assert "if ($capHasSideMark)" in progress_section
    assert "$markWave = ([Math]::Sin($script:ProgressAngle / 24.0) + 1.0) / 2.0" in progress_section
    assert "$g.FillEllipse($markHaloBrush, 19, 37, 50, 50)" in progress_section
    assert "$g.DrawArc($markOrbitPen, 20, 38, 48, 48, (($script:ProgressAngle + 205) % 360), 84)" in progress_section
    assert "$g.DrawLine($markLinkPen, 64, 62, 74, 62)" in progress_section
    assert "$script:ProgressProfileImageBox = $profileImageBox" in progress_section
    assert "$script:ProgressProfileImage.Dispose()" in close_section
    assert "Show-ProgressOverlay @progressVisual" in tray
    assert "Show-ProgressOverlay @pendingProgressVisual" in tray
    assert '-Title "Restoring Settings" `' in tray
    assert '-ActionName "Restore" `' in tray
    assert "-ActionColor $script:Colors.AccentPurple" in tray


def test_progress_overlay_dismiss_action_uses_close_icon_button() -> None:
    """Progress overlay dismiss control should be an icon-backed action, not stale plain text."""
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    progress_section = notifications.split("function Show-ProgressOverlay", 1)[1].split(
        "function Update-ProgressOverlay",
        1,
    )[0]
    close_section = notifications.split("function Close-ProgressOverlay", 1)[1].split(
        "# ============================================================================\n# LEGACY COMPAT",
        1,
    )[0]
    assert "$cancelLabel = New-Object System.Windows.Forms.Label" not in progress_section
    assert '$cancelLabel.Text      = "DISMISS"' not in progress_section
    assert "$cancelButton = New-Object System.Windows.Forms.Button" in progress_section
    assert 'New-ActionBitmap -Action "Close" -Color $script:Penumbra.Fog' in progress_section
    assert "$cancelButton.TextImageRelation = [System.Windows.Forms.TextImageRelation]::ImageBeforeText" in progress_section
    assert "$cancelButton.FlatAppearance.MouseOverBackColor" in progress_section
    assert "$cancelButton.Add_Click({ Close-ProgressOverlay })" in progress_section
    assert "$script:ProgressDismissButton = $cancelButton" in progress_section
    assert "$script:ProgressDismissImage = $dismissImage" in progress_section
    assert "$script:ProgressDismissButton.Image = $null" in close_section
    assert "$script:ProgressDismissImage.Dispose()" in close_section


def test_quick_panel_uses_game_marks_and_active_pulse() -> None:
    """Favorites quick panel should show game marks, not generic category placeholders."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "Get-QuickPanelGameGroup" in script
    assert "function New-QuickPanelGameMedallionBitmap" in script
    assert "New-GameBitmap -GameGroup $GameGroup" in script
    assert "New-ActiveGameBitmap `" in script
    assert '[string]$ModeBadge = ""' in script
    assert "[switch]$FavoriteBadge" in script
    assert "[switch]$PendingApplyBadge" in script
    assert "[switch]$WindowsRestartBadge" in script
    assert "[switch]$VerificationBadge" in script
    assert "[switch]$EmptyBadge" in script
    assert "$g.DrawArc($arcPen, 2, 2, 26, 26, 210, 56)" in script
    assert "$g.DrawImage($mark, (New-Object System.Drawing.Rectangle(7, 7, 16, 16)))" in script
    assert '$mark = New-ActionBitmap -Action "QuickPanel" -Color $Color' in script
    assert "$g.DrawLine($emptyBadgePen, [float]23.0, [float]24.5, [float]26.0, [float]24.5)" in script
    assert "$iconBox.Size = New-Object System.Drawing.Size(30, 30)" in script
    assert "$iconBox.Image = New-QuickPanelGameMedallionBitmap" in script
    assert "QuickPanelPulseTimer" in script
    assert "QuickPanelPulseFrame" in script
    assert "$target.Invalidate()" in script
    assert "[void]$script:QuickPanelPulseTargets.Add($form)" in script
    quick_medallion_section = script.split("function New-QuickPanelGameMedallionBitmap", 1)[1].split(
        "# ============================================================================\n# PUBLIC: Show-QuickPanel",
        1,
    )[0]
    assert "-ModeBadge $ModeBadge `" in quick_medallion_section
    assert "-FavoriteBadge ([bool]$FavoriteBadge) `" in quick_medallion_section
    assert "-PendingApplyBadge ([bool]$PendingApplyBadge) `" in quick_medallion_section
    assert "-WindowsRestartBadge ([bool]$WindowsRestartBadge) `" in quick_medallion_section
    assert "-VerificationBadge ([bool]$VerificationBadge)" in quick_medallion_section
    assert 'if ($EmptyBadge -and (Get-Command New-ActionBitmap -ErrorAction SilentlyContinue)) {' in quick_medallion_section
    assert "New-FavoriteGameBitmap `" in quick_medallion_section
    assert "New-GameSyncBadgeBitmap `" in quick_medallion_section
    assert "New-CategoryBitmap -Category $Category -Color $Color" in quick_medallion_section
    card_loop_section = script.split("# Profile cards", 1)[1].split(
        "# DWM rounded corners",
        1,
    )[0]
    assert '$modeBadge = if ("$($entry.Id)" -match \'(?i)capture\' -or $variant -match \'(?i)capture\')' in card_loop_section
    assert 'elseif ($variant -match \'(?i)\\bHDR\\b\' -or "$($entry.Id)" -match \'(?i)-hdr($|-)\' )' in card_loop_section
    assert '"$($entry.Kind)" -eq "favorite"' in card_loop_section
    assert '(@($Favorites) | ForEach-Object { "$_" }) -contains "$($entry.Id)"' in card_loop_section
    assert '$emptyBadge = ("$($entry.Kind)" -eq "empty" -and "$($entry.Id)" -eq "__quick_panel_empty__")' in card_loop_section
    assert "-EmptyBadge:$emptyBadge" in card_loop_section
    assert "$pendingApplyBadge = ($isActive -and -not [string]::IsNullOrWhiteSpace($ActivePendingApplyText))" in card_loop_section
    assert "$windowsRestartBadge = ($isActive -and -not [string]::IsNullOrWhiteSpace($ActiveWindowsRestartText))" in card_loop_section
    assert "$verificationBadge = (" in card_loop_section
    assert "-not [string]::IsNullOrWhiteSpace($ActiveVerificationText)" in card_loop_section
    assert '-not $pendingApplyBadge -and' in card_loop_section
    assert '-not $windowsRestartBadge -and' in card_loop_section
    assert '-not $verificationBadge' in card_loop_section
    assert '$chipText = "MISSING"' in card_loop_section
    assert "-ModeBadge $modeBadge `" in card_loop_section
    assert "-FavoriteBadge:$favoriteBadge `" in card_loop_section
    assert "-PendingApplyBadge:$pendingApplyBadge `" in card_loop_section
    assert "-WindowsRestartBadge:$windowsRestartBadge `" in card_loop_section
    assert "-VerificationBadge:$verificationBadge `" in card_loop_section


def test_quick_panel_surface_has_ambient_header_sweep() -> None:
    """The quick panel shell should animate even when no card is active."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    paint_section = script.split("$form.Add_Paint({", 1)[1].split(
        "# Header eyebrow",
        1,
    )[0]
    assert "Ambient header sweep" in paint_section
    assert "$ambientAlpha = [int](42 + (30 * ([Math]::Sin($script:QuickPanelPulseFrame / 5.0) + 1.0)))" in paint_section
    assert "$ambientX = $padX + (($script:QuickPanelPulseFrame * 6) % [Math]::Max(1, ($capW - ($padX * 2) - 70)))" in paint_section
    assert "[System.Drawing.Color]::FromArgb($ambientAlpha, $qpLagoon.R, $qpLagoon.G, $qpLagoon.B), 1.0" in paint_section
    assert "$g.DrawLine($ambientPen, $ambientX, ($padTop + $headerHeight - 8)," in paint_section
    assert "[Math]::Min(($capW - $padX), ($ambientX + 54)), ($padTop + $headerHeight - 8))" in paint_section
    assert "[void]$script:QuickPanelPulseTargets.Add($form)" in script


def test_quick_panel_close_affordance_uses_generated_icon() -> None:
    """Quick panel close should use tray action art, not a raw text X."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    close_section = script.split("# Close affordance - generated icon button", 1)[1].split(
        "# Profile cards",
        1,
    )[0]

    assert "function Set-QuickPanelPictureImageSafe" in script
    assert "$oldImage = $PictureBox.Image" in script
    assert "$oldImage.Dispose()" in script
    assert "$closeBox = New-Object System.Windows.Forms.PictureBox" in close_section
    assert '$closeBox.Image     = New-ActionBitmap -Action "Close" -Color $script:QPPalette.Lagoon' in close_section
    assert '$toolTip.SetToolTip($closeBox, "Close Quick Panel")' in close_section
    assert "$closeBox.Add_Click({ Close-QuickPanel })" in close_section
    assert 'Set-QuickPanelPictureImageSafe -PictureBox $this -Image (New-ActionBitmap -Action "Close" -Color $qpPaper)' in close_section
    assert 'Set-QuickPanelPictureImageSafe -PictureBox $this -Image (New-ActionBitmap -Action "Close" -Color $qpLagoon)' in close_section
    assert "$form.Controls.Add($closeBox)" in close_section
    assert "$closeLabel = New-Object System.Windows.Forms.Label" not in script
    assert "$closeLabel.Text      = [string][char]0x00D7" not in script


def test_quick_panel_cards_show_text_status_chips_without_overlap() -> None:
    """Quick panel cards should expose active/variant/favorite state as clipped text chips."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-QuickPanelCardChipText" in script
    assert "function Get-QuickPanelCardTooltipText" in script
    assert '[bool]$PendingApply = $false' in script
    assert '[bool]$WindowsRestart = $false' in script
    assert '[bool]$VerificationInProgress = $false' in script
    assert 'return "RESTART"' in script
    assert 'return "FIX"' in script
    assert 'return "PENDING"' not in script
    assert 'return "CHECK"' in script
    assert 'return "ACTIVE"' in script
    assert 'return "EMPTY"' in script
    assert '$chipText = "MISSING"' in script
    assert 'return "INFO"' not in script
    assert "function Get-QuickPanelCompactChipText" in script
    assert 'return (Get-QuickPanelCompactChipText -Text "$($Profile.Variant)")' in script
    assert 'return (Get-QuickPanelCompactChipText -Text "$($Profile.SyncMode)")' in script
    assert 'return (Format-QuickPanelDisplayCopy -Text "$($Profile.Variant)")' not in script
    assert 'return (Format-QuickPanelDisplayCopy -Text "$($Profile.SyncMode)")' not in script
    assert "'(?i)capture' { return \"CAPTURE\" }" in script
    assert "'(?i)console[-\\s]?parity' { return \"CONSOLE\" }" in script
    assert "'(?i)g[-\\s]?sync' { return \"G-SYNC\" }" in script
    assert "'(?i)no\\s*sync' { return \"NO SYNC\" }" in script
    assert "if ($upper.Length -gt 8) { return $upper.Substring(0, 8) }" in script
    assert 'function Format-QuickPanelDisplayCopy' in script
    assert 'function Format-QuickPanelUserFacingText' in script
    assert 'return "FAV"' in script
    assert '[string]$ActivePendingApplyText = ""' in script
    assert '[string]$ActiveWindowsRestartText = ""' in script
    assert '[string]$ActiveVerificationText = ""' in script
    assert '[void]$parts.Add("Status: Windows restart required")' in script
    assert '[void]$parts.Add("$($ActiveWindowsRestartText.Trim()) needs a Windows restart to finish.")' in script
    assert '[void]$parts.Add("Status: pending profile fixes available")' in script
    assert '[void]$parts.Add("Click applies pending profile fixes for $($ActivePendingApplyText.Trim()).")' in script
    assert '[void]$parts.Add("Status: checking profile state")' in script
    assert '[void]$parts.Add("Verifier is reading current settings before showing fixes or reapply.")' in script
    assert '[void]$parts.Add("Status: active profile")' in script
    assert '[void]$parts.Add("Status: favorite shortcut")' in script
    assert '[void]$parts.Add("Status: no quick profiles")' in script
    assert '[void]$parts.Add("No active profile or favorite shortcuts are available.")' in script
    assert '[void]$parts.Add("Status: profile reference missing")' in script
    assert '[void]$parts.Add("This saved profile id is not in the current profile list.")' in script
    empty_tooltip_section = script.split('if ("$Kind" -eq "empty") {', 1)[1].split(
        'elseif ($Disabled) {',
        1,
    )[0]
    assert '[void]$parts.Add("Status: Windows restart required")' in empty_tooltip_section
    assert '[void]$parts.Add("Status: pending profile fixes available")' in empty_tooltip_section
    assert '[void]$parts.Add("Status: checking profile state")' in empty_tooltip_section
    assert '[void]$parts.Add("Status: profile reference missing")' in empty_tooltip_section
    assert '[void]$parts.Add("Status: empty panel")' not in script
    assert '[void]$parts.Add("No profile will apply from this card.")' not in script
    assert '[void]$parts.Add("Status: disabled shortcut")' in script
    assert '[void]$parts.Add("This card will not apply a profile.")' in script
    assert '[void]$parts.Add("Status: unavailable")' not in script
    assert '[void]$parts.Add("Click checks current state first; fixes or reapplies only if needed.")' in script
    assert "Click to verify or repair this active profile." not in script
    assert '$script:QuickPanelToolTip = $toolTip' in script
    assert "$form.Add_Disposed({ Clear-QuickPanelToolTip })" in script
    assert "$capHeaderChipFont = $script:QPFont_Eyebrow" in script
    assert "$g.DrawString($capHeaderChipText, $capHeaderChipFont" in script
    assert "$g.DrawString($capHeaderChipText, $script:QPFont_Eyebrow" not in script
    assert "$chipText = Get-QuickPanelCardChipText `" in script
    assert "-PendingApply $pendingApplyBadge `" in script
    assert "-WindowsRestart $windowsRestartBadge `" in script
    assert "-VerificationInProgress $verificationBadge" in script
    assert "$tooltipText = Get-QuickPanelCardTooltipText `" in script
    assert "-ActivePendingApplyText $ActivePendingApplyText `" in script
    assert "-ActiveWindowsRestartText $ActiveWindowsRestartText `" in script
    assert "-ActiveVerificationText $ActiveVerificationText" in script
    assert "$toolTip.SetToolTip($card, $tooltipText)" in script
    assert "$toolTip.SetToolTip($iconBox, $tooltipText)" in script
    assert "$capCardChip = $chipText" in script
    assert '$stateRailKind = if ($pendingApplyBadge) {' in script
    assert '"fix"' in script
    assert 'elseif ($windowsRestartBadge) {' in script
    assert '"restart"' in script
    assert 'elseif ($verificationBadge) {' in script
    assert '"check"' in script
    assert 'elseif ($emptyBadge -or $isDisabled) {' in script
    assert '"missing"' in script
    assert 'elseif ($favoriteBadge) {' in script
    assert '"favorite"' in script
    assert '$capStateRailKind = $stateRailKind' in script
    assert '$capStateRailColor = $stateRailColor' in script
    assert "# Right state rail: non-layout visual state channel for active/fix/restart/check cards." in script
    assert "$railX = $s.Width - 11" in script
    assert "$railTop = 26" in script
    assert "$railHeight = [Math]::Max(18, ($s.Height - 34))" in script
    assert '$capStateRailKind -in @("fix", "restart", "check", "active")' in script
    assert '$capStateRailKind -in @("fix", "restart", "check")' in script
    assert '$scanY = $railTop + (($script:QuickPanelPulseFrame * 3) % [Math]::Max(1, $railHeight))' in script
    assert '$g.DrawLine($scanPen, ($railX - 4), $scanY, ($railX + 6), $scanY)' in script
    assert "$panelWidth   = 440" in script
    assert "$chipRect = New-Object System.Drawing.Rectangle(($s.Width - 96), 8, 72, 15)" in script
    assert "$chipRect = New-Object System.Drawing.Rectangle(($s.Width - 82), 8, 58, 15)" not in script
    assert "$chipFormat.Trimming = [System.Drawing.StringTrimming]::EllipsisCharacter" in script
    assert "$chipFormat.FormatFlags = [System.Drawing.StringFormatFlags]::NoWrap" in script
    assert "$chipTextRect = New-Object System.Drawing.RectangleF(" in script
    assert "$g.DrawString($capCardChip, $capChipFont, $chipBrush, $chipTextRect, $chipFormat)" in script
    assert "$g.DrawString($capCardChip, $capChipFont, $chipBrush, $chipRect, $chipFormat)" not in script
    assert "$sweepAlpha = [int](55 + (30 * ([Math]::Sin($script:QuickPanelPulseFrame / 4.0) + 1.0)))" in script
    assert "$g.DrawLine($sweepPen, 6, 1, ($s.Width - 10), 1)" in script
    assert '$nameLabel.Text      = if ($entry.Profile -and -not [string]::IsNullOrWhiteSpace("$($entry.Profile.Name)")) {' in script
    assert 'Format-QuickPanelDisplayCopy -Text "$($entry.Profile.Name)"' in script
    assert 'Format-QuickPanelUserFacingText -Text "$($entry.Id)"' in script
    assert '$nameLabel.Text      = $entry.Profile.Name' not in script
    assert "$nameLabel.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 152), 20)" in script
    assert 'Format-QuickPanelDisplayCopy -Text "$($entry.Profile.Sub)"' in script
    assert 'Format-QuickPanelDisplayCopy -Text "$($entry.Profile.Cat)"' in script
    assert '$subText = if ($entry.Profile.Sub) { $entry.Profile.Sub } else { $entry.Profile.Cat }' not in script
    assert "$subLabel.Size      = if ($isDisabled)" in script
    assert "New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 76), 32)" in script
    assert "New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 72), 16)" in script


def test_quick_panel_pins_active_profile_before_favorites() -> None:
    """Quick panel should not hide active state when the active profile is not favorited."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "$maxQuickPanelCards = 3" in script
    assert "$panelProfiles += @{ Id = $ActiveProfile; Profile = $Profiles[$ActiveProfile]; Kind = \"active\" }" in script
    assert "if ($fav -eq $ActiveProfile) { continue }" in script
    assert "if ($Profiles -and $Profiles.Contains($fav))" in script
    assert "if ($panelProfiles.Count -ge $maxQuickPanelCards) { break }" in script
    assert "$panelProfiles.Count -eq 0" in script
    assert "$favProfiles.Count -eq 0" not in script
    assert '$emptyEyebrowText = if ($emptyPanel)' in script
    assert '"QUICK PANEL / EMPTY"' in script
    assert '"PROFILE LIST / MISSING"' in script
    assert '"PROFILE CATALOG / EMPTY"' not in script
    assert '"ACTIVE / QUICK LAUNCH"' in script


def test_quick_panel_header_chip_summarizes_visible_state() -> None:
    """Quick Panel header should summarize rendered cards without stale generic copy."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-QuickPanelHeaderChipText" in script
    assert '$firstEntry = if ($visibleCount -gt 0) { $PanelProfiles[0] } else { $null }' in script
    assert '$firstEntry -is [System.Collections.IDictionary] -and $firstEntry.Contains("Id")' in script
    assert 'return "MISSING"' in script
    assert 'return "EMPTY"' in script
    assert 'if ($extraCount -gt 0) { return "ACTIVE +$extraCount" }' in script
    assert 'return "ACTIVE"' in script
    assert 'if ($visibleCount -eq 1) { return "1 FAVORITE" }' in script
    assert 'return "$visibleCount FAVORITES"' in script
    assert "$headerChipText = Get-QuickPanelHeaderChipText `" in script
    assert "-PanelProfiles @($panelProfiles) `" in script
    assert "-EmptyPanel:$emptyPanel `" in script
    assert "-HasPinnedActiveProfile:$hasPinnedActiveProfile" in script
    assert '$headerChip.Tag       = "__quick_panel_header_chip__"' in script
    assert "$eyebrow.Size      = New-Object System.Drawing.Size(($panelWidth - $padX * 2 - 124), 14)" in script
    assert "$headerChip.Size      = New-Object System.Drawing.Size(84, 17)" in script
    assert '$toolTip.SetToolTip($headerChip, "Quick Panel summary: $headerChipText")' in script
    assert '[void]$script:QuickPanelPulseTargets.Add($headerChip)' in script
    assert '$sweepX = 4 + (($script:QuickPanelPulseFrame * 3) % [Math]::Max(1, ($s.Width - 26)))' in script
    assert "$capHeaderChipFont = $script:QPFont_Eyebrow" in script
    assert "$g.DrawString($capHeaderChipText, $capHeaderChipFont" in script
    assert "$g.DrawString($capHeaderChipText, $script:QPFont_Eyebrow" not in script


def test_quick_panel_paint_uses_valid_drawing_constructors() -> None:
    """Paint handlers must pass colors through ArgumentList, not type-name suffixes."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "New-Object System.Drawing.SolidBrush(" not in script
    assert "New-Object System.Drawing.Pen(" not in script
    assert "New-Object System.Drawing.SolidBrush -ArgumentList" in script
    assert "New-Object System.Drawing.Pen -ArgumentList" in script


def test_quick_panel_empty_rebuild_renders_disabled_empty_state() -> None:
    """Quick panel should explain empty catalog state instead of silently disappearing."""
    script = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "$script:QuickPanelForm = $null\n        $script:QuickPanelVisible = $false\n        $script:QuickPanelEmptyState = $false" in script
    assert '[string]$EmptyMessage = "No active profile or favorites to show."' in script
    assert '[string]$EmptyProfileId = ""' in script
    assert "$emptyPanel = $false" in script
    assert '$emptyProfileId = if (-not [string]::IsNullOrWhiteSpace($EmptyProfileId))' in script
    assert 'Format-TrayUserFacingText -Text $emptyProfileId' in script
    assert "Get-QuickPanelGameGroup -ProfileId $emptyProfileId -Profile $null" in script
    assert 'Id = $emptyProfileId' in script
    assert '"No quick profiles"' in script
    assert "Name = $emptyName" in script
    assert "GameGroup = $emptyGameGroup" in script
    assert 'Kind = "empty"' in script
    assert "Disabled = $true" in script
    assert '"QUICK PANEL / EMPTY"' in script
    assert '"PROFILE LIST / MISSING"' in script
    assert '"PROFILE CATALOG / EMPTY"' not in script
    assert "$cardHeight   = if ($emptyPanel) { 70 } else { 56 }" in script
    assert '$card.Cursor   = if ($isDisabled) { [System.Windows.Forms.Cursors]::Default } else { [System.Windows.Forms.Cursors]::Hand }' in script
    assert "if (-not $isDisabled) {" in script
    assert "$script:QuickPanelEmptyState = $emptyPanel" in script
    assert "if ($panelProfiles.Count -eq 0) {\n        $script:QuickPanelVisible = $false\n        return\n    }" not in script


def test_tray_quick_panel_toggle_tracks_actual_visibility() -> None:
    """Tray setting/checkmark should reflect a real quick panel form, not just user intent."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$script:TrayConfig.showQuickPanel = [bool]$script:QuickPanelVisible" in script
    assert "function Get-QuickPanelEmptyStatus" in script
    assert "Active profile and favorites are not in the current profile list." in script
    assert "Active profile is not in the current profile list: $($activeRecord.DisplayName)." in script
    assert "Favorite profiles are not in the current profile list." in script
    assert "loaded profile catalog" not in script
    assert "No active profile or favorites to show." in script
    assert 'ProfileId = "$($activeRecord.Id)"' in script
    assert 'ProfileId = "$($favoriteIds[0])"' in script
    assert "ProfileId = $null" in script
    assert "$quickPanelEmpty = Get-QuickPanelEmptyStatus" in script
    assert "-EmptyMessage $quickPanelEmpty.Message" in script
    assert "-EmptyProfileId $quickPanelEmpty.ProfileId" in script
    assert "-EmptyMessage $startupQuickPanelEmpty.Message" in script
    assert "-EmptyProfileId $startupQuickPanelEmpty.ProfileId" in script
    assert "$quickPanelPendingApplyText = Get-ActiveProfilePendingApplyText" in script
    assert "$quickPanelWindowsRestartText = Get-ActiveProfileRebootPendingText" in script
    assert "$quickPanelVerificationText = Get-ActiveProfileVerificationInProgressText" in script
    assert "$startupQuickPanelPendingApplyText = Get-ActiveProfilePendingApplyText" in script
    assert "$startupQuickPanelWindowsRestartText = Get-ActiveProfileRebootPendingText" in script
    assert "$startupQuickPanelVerificationText = Get-ActiveProfileVerificationInProgressText" in script
    assert "-ActivePendingApplyText $quickPanelPendingApplyText" in script
    assert "-ActiveWindowsRestartText $quickPanelWindowsRestartText" in script
    assert "-ActiveVerificationText $quickPanelVerificationText" in script
    assert "-ActivePendingApplyText $startupQuickPanelPendingApplyText" in script
    assert "-ActiveWindowsRestartText $startupQuickPanelWindowsRestartText" in script
    assert "-ActiveVerificationText $startupQuickPanelVerificationText" in script
    assert "Update-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -ActivePendingApplyText $quickPanelPendingApplyText -ActiveWindowsRestartText $quickPanelWindowsRestartText -ActiveVerificationText $quickPanelVerificationText -EmptyMessage $quickPanelEmpty.Message" in script
    assert "function Update-QuickPanel" in QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert '[string]$EmptyMessage = "No active profile or favorites to show."' in QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert '[string]$EmptyProfileId = ""' in QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "Show-QuickPanel -Favorites $Favorites -Profiles $Profiles -ActiveProfile $ActiveProfile -ActivePendingApplyText $ActivePendingApplyText -ActiveWindowsRestartText $ActiveWindowsRestartText -ActiveVerificationText $ActiveVerificationText -EmptyMessage $EmptyMessage -EmptyProfileId $EmptyProfileId -OnApply $OnApply" in QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")
    assert "$quickPanelEmptyVisual = Get-TrayProfileToastVisualArgs -ProfileId $quickPanelEmpty.ProfileId -Profile $null" in script
    assert "$quickPanelEmptyTitle = Get-TrayProfileDisplayName -ProfileId $quickPanelEmpty.ProfileId" in script
    assert "Show-Notification @quickPanelEmptyVisual -Title $quickPanelEmptyTitle -Message $quickPanelEmpty.Message -Type \"Info\" -MetaText $quickPanelEmpty.ProfileId" in script
    assert (
        'Show-Notification -Title "A.B.S.O. Quick Panel" -Message $quickPanelEmpty.Message '
        '-Type "Info" -ActionName "QuickPanel" -ActionColor $script:Colors.AccentBlue'
    ) in script
    assert "Set-TrayLastAction -Message $quickPanelEmpty.LastAction" in script
    assert "elseif ($script:QuickPanelEmptyState)" in script
    assert "$quickPanelIsVisible = [bool](" in script
    assert "$script:QuickPanelVisible -and" in script
    assert "-not $script:QuickPanelForm.IsDisposed" in script
    assert '$quickPanelItem.Text = if ($quickPanelIsVisible) { "Close Quick Panel" } else { "Open Quick Panel" }' in script
    assert "$quickPanelItem.Checked = $quickPanelIsVisible" in script
    assert '"Open the floating quick-access panel; empty/profile-missing states are shown in the panel"' in script
    assert '"Toggle floating quick-access panel"' not in script
    assert "$quickPanelItem.Checked = [bool]$script:QuickPanelVisible" in script
    assert '$quickPanelItem.Text = if ($script:QuickPanelVisible) { "Close Quick Panel" } else { "Open Quick Panel" }' in script
    assert "if ($script:TrayConfig.showQuickPanel) {" in script
    assert "$script:TrayConfig.showQuickPanel -and ($script:TrayConfig.favorites.Count -gt 0 -or $script:activeProfile)" not in script


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


def test_tray_wires_keep_awake_for_gaming_sessions() -> None:
    """Keep-Awake must be wired via SetThreadExecutionState on the session lifecycle."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    # P/Invoke + assert/clear helpers
    assert "SetThreadExecutionState" in script
    assert "function Set-AbsoKeepAwake" in script
    assert "function Clear-AbsoKeepAwake" in script
    # Per-profile flag carried from the catalog cache
    assert "keep_awake_while_gaming" in script  # cache field read
    assert "KeepAwakeWhileGaming" in script  # mapped profile property
    # Asserted on the alive path and released on shutdown
    assert "Set-AbsoKeepAwake" in script
    assert "Clear-AbsoKeepAwake" in script


def test_tray_wires_cpu_balancer_governor() -> None:
    """ProBalance governor must be wired via the cpu-balance CLI + stop-file sentinel."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Start-CpuBalancerForGame" in script
    assert "function Stop-CpuBalancerForGame" in script
    assert "function Get-ActiveProfileGamePid" in script
    assert "cpu-balance" in script
    assert "--stop-file" in script
    # Graceful stop (sentinel + wait), not a hard kill, so demoted priorities
    # are restored by the daemon's cleanup.
    assert "WaitForExit" in script
    # Gated on the tray-config flag (opt-in per machine).
    assert "cpuBalancer" in script
    # Tier B opt-ins passed through to the daemon as CLI flags.
    assert "--cpu-sets" in script
    assert "--eco" in script
    assert "--watchdog" in script
    assert "cpuSets" in script
    assert "ecoMode" in script
    # Watchdog online-gating: --online passed for online profiles.
    assert "--online" in script
    assert "IsOnline" in script
    assert "is_online_profile" in script


def test_tray_backup_menu_uses_logical_backup_timestamp() -> None:
    """Copied backup folders should be sorted by manifest/ID time, not copy time."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-BackupTimestamp" in script
    assert "Prefer manifest `created_at`, then the timestamp-style directory name." in script
    assert '$mj.created_at' in script
    assert 'ParseExact($Directory.Name, "yyyy-MM-dd_HHmmss"' in script
    assert "Sort-Object Time -Descending" in script
    assert "Filesystem CreationTime is only a fallback" in script


def test_tray_backup_menu_prefers_installed_runtime_backups() -> None:
    """Tray backup status should not read the stale workspace mirror first."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-BackupRoots" in script
    assert "function Get-BackupDirectoryEntries" in script
    assert '[PSCustomObject]@{ Role = "installed"; Path = (Join-Path (Get-InstalledAppRoot) "backups") }' in script
    assert '[PSCustomObject]@{ Role = "workspace"; Path = (Join-Path $script:ProjectRoot "backups") }' in script
    assert "$roots = @(Get-BackupRoots)" in script
    assert "$entriesById.ContainsKey($dir.Name)" in script
    assert "Source = $entry.RootRole" in script
    assert "SourceLabel = Get-BackupSourceLabel -Source $entry.RootRole" in script
    assert "RootPath = $entry.RootPath" in script
    assert "function Get-BackupSourceLabel" in script
    assert '"installed" { return "installed backup folder" }' in script
    assert '"workspace" { return "workspace backup folder" }' in script
    assert "function Get-BackupSourceChipText" in script
    assert '"installed" { return "INSTALLED" }' in script
    assert '"workspace" { return "WORKSPACE" }' in script
    assert "function Get-BackupMenuChipText" in script
    assert 'if ($count -le 0) { return "NO BACKUPS" }' in script
    assert 'if ($count -eq 1) { return "1 BACKUP" }' in script
    assert 'return "$count BACKUPS"' in script
    assert '"workspace" { return "workspace fallback" }' not in script
    assert '$backupsPath = Join-Path $script:ProjectRoot "backups"' not in script


def test_tray_backup_age_never_reports_negative_relative_time() -> None:
    """Clock skew or UTC parsing should not produce impossible backup ages."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    backup_time_section = script.split("function Get-LastBackupTime", 1)[1].split(
        "function Get-RecentBackups",
        1,
    )[0]
    assert '$age = (Get-Date) - $latest.Time' in backup_time_section
    assert 'if ($age.TotalSeconds -lt 0) { return "just now" }' in backup_time_section
    assert 'return "$([int]$age.TotalMinutes)m ago"' in backup_time_section
    assert 'Add-UniqueTrayMessage -Target $statusParts -Message "Backup: $backupTime"' in script


def test_tray_settings_menu_distinguishes_tray_and_runtime_folders() -> None:
    """Settings flyout should not call the tray config directory the app config folder."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-TrayConfigDir" in script
    assert "function Open-RuntimeFolder" in script
    assert "$configDir = Get-TrayConfigDir" in script
    assert "$runtimeDir = Get-InstalledAppRoot" in script
    assert '$configFolderItem.Text = "Open Tray Settings Folder"' in script
    assert '$configFolderItem.ToolTipText = "Opens tray-config.json storage: $(Get-TrayConfigDir)"' in script
    assert '$runtimeFolderItem.Text = "Open Installed Runtime Folder"' in script
    assert '$runtimeFolderItem.ToolTipText = "Opens abso.yaml, installed binaries, backups, and deployed tray assets"' in script
    assert "$runtimeFolderItem.Add_Click({ Open-RuntimeFolder })" in script
    assert '$configFolderItem.Text = "Open Config Folder"' not in script
    assert '$configDir = Join-Path $env:APPDATA "ABSO"' not in script


def test_tray_log_action_is_explicit_and_not_silent() -> None:
    """View log should open the tray log or tell the user why it could not."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Open-LogFile" in script
    assert "Tray log file created for manual view request" in script
    assert 'Start-Process "notepad.exe" -ArgumentList $script:LogFile -ErrorAction Stop' in script
    assert 'Write-TrayLog "Failed to open tray log file: $($_.Exception.Message)" -Level "ERROR"' in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Failed to open tray log: $($_.Exception.Message)" '
        '-Type "Error" -ActionName "Log" -ActionColor $script:Colors.TextDim'
    ) in script
    assert '$logItem.Text = "View Tray Log File"' in script
    assert '$logItem.ToolTipText = "Opens current tray log: $script:LogFile"' in script
    assert '$logItem.Text = "View Log File"' not in script


def test_tray_recent_and_backup_menus_use_friendly_time_and_profile_labels() -> None:
    """Recent/backup menu surfaces should not expose raw timestamps or profile ids."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Format-TrayTimestamp" in script
    assert "function Get-TrayProfileDisplayName" in script
    display_name_section = script.split("function Get-TrayProfileDisplayName", 1)[1].split(
        "function Get-TrayProfileObjectDisplayName",
        1,
    )[0]
    assert 'return "Profile not reported"' in display_name_section
    assert 'return "Unknown profile"' not in display_name_section
    assert "function Get-RecentProfileTooltipText" in script
    assert '[void]$parts.Add((Format-TrayDisplayCopy -Text "$($Profile.Sub)"))' in script
    assert "$item.ToolTipText = Get-RecentProfileTooltipText -Profile $p -Entry $entry" not in script
    assert '$profileId = "$($mj.profile_id)"' in script
    assert "$profileName = Get-TrayProfileDisplayName -ProfileId $profileId" in script
    assert '$label = "$profileName - $displayTime"' in script
    assert "$label = Format-TrayTimestamp -Value $timestamp" in script
    assert "ProfileId = $profileId" in script
    assert '$backupsItem.ToolTipText = if ($backupTime -eq "Never") {' in script
    assert '"No backups found. Applying a profile creates a restorable backup."' in script
    assert '"No backups found. Open the backups folder to inspect or create one by applying a profile."' not in script
    assert '"Restore backup: $($backup.Label)`nSource: $($backup.SourceLabel)"' in script
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restored from: $capturedLabel" '
        '-Type "Success" -MetaText $restoreMetaText'
    ) in script
    assert 'Set-TrayLastAction -Message "Restored backup: $capturedLabel"' in script
    assert 'Set-LastProfileState -Config $script:TrayConfig -Status "restored" -Source "tray_restore_backup"' in script
    assert 'Set-TrayLastAction -Message "Restored backup: $capturedName"' not in script
    assert 'Set-TrayLastAction -Message "Restore timed out: $capturedLabel"' in script
    assert '"$($p.Sub) - Last: $($entry.timestamp)"' not in script
    assert '"$($mj.profile_id) - $($timestamp.ToString' not in script


def test_tray_backup_rows_use_profile_marks_when_manifest_profile_is_known() -> None:
    """Backup rows should carry recognizable profile artwork when the manifest identifies a known profile."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    recent_section = script.split("function Get-RecentBackups", 1)[1].split(
        "# ============================================================================\n# SEARCH / FILTER",
        1,
    )[0]
    backups_section = script.split("# Backups submenu (nested inside Actions)", 1)[1].split(
        "$actionsMenu.DropDownItems.Add($backupsItem)",
        1,
    )[0]

    assert "$profileId = $null" in recent_section
    assert '$profileId = "$($mj.profile_id)"' in recent_section
    assert "$profileName = Get-TrayProfileDisplayName -ProfileId $profileId" in recent_section
    assert "ProfileId = $profileId" in recent_section
    assert '$backupProfileId = if ($backup.ProfileId) { "$($backup.ProfileId)" } else { "" }' in backups_section
    assert "$backupProfile = $null" in backups_section
    assert "if (-not [string]::IsNullOrWhiteSpace($backupProfileId)) {" in backups_section
    assert "$script:Profiles.Contains($backupProfileId)" in backups_section
    assert "$backupFavoriteBadge = if (Get-Command Test-Favorite -ErrorAction SilentlyContinue)" in backups_section
    assert '$bItem.AccessibleName = "__backup_menu_item__"' in backups_section
    assert "$bItem.AccessibleDescription = Get-BackupSourceChipText -Source $backup.Source" in backups_section
    assert "$bItem.Padding = New-Object System.Windows.Forms.Padding(0, 0, 70, 0)" in backups_section
    assert "New-TrayProfileMenuImage `" in backups_section
    assert "-ProfileId $backupProfileId `" in backups_section
    assert "-ShowSyncBadge $true `" in backups_section
    assert "-FavoriteBadge $backupFavoriteBadge" in backups_section
    assert (
        "Get-TrayProfileAccentColor -ProfileId $backupProfileId -Profile $backupProfile "
        "-Fallback $script:Colors.TextDim"
    ) in backups_section
    assert '$bItem.Image = New-ActionBitmap -Action "Restore" -Color $script:Colors.AccentPurple' in backups_section
    assert 'if (-not ($script:Profiles -and $script:Profiles.Contains($backupProfileId))) { continue }' not in (
        backups_section
    )


def test_tray_backup_restore_toasts_use_manifest_profile_visuals() -> None:
    """Backup restore outcome toasts should carry the manifest profile identity when known."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    restore_backup_section = script.split("$bItem.Add_Click({", 1)[1].split(
        "}.GetNewClosure())",
        1,
    )[0]

    assert "$capturedProfileId = $backupProfileId" in script
    assert "$restoreProfile = $null" in restore_backup_section
    assert "$script:Profiles.Contains($capturedProfileId)" in restore_backup_section
    assert "$restoreProfile = $script:Profiles[$capturedProfileId]" in restore_backup_section
    assert "$restoreVisual = Get-TrayProfileToastVisualArgs -ProfileId $capturedProfileId -Profile $restoreProfile" in (
        restore_backup_section
    )
    assert '$restoreTitle = if (-not [string]::IsNullOrWhiteSpace($capturedProfileId)) { Get-TrayProfileDisplayName -ProfileId $capturedProfileId } else { "A.B.S.O." }' in restore_backup_section
    assert (
        '$restoreMetaText = if (-not [string]::IsNullOrWhiteSpace($capturedProfileId)) '
        "{ $capturedProfileId } else { $capturedName }"
    ) in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore timed out: $capturedLabel" '
        '-Type "Error" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restored from: $capturedLabel" '
        '-Type "Success" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle '
        '-Message "Restore failed: runtime status unreadable. See tray log." -Type "Error" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: $restoreErr" '
        '-Type "Error" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: runtime returned no status" '
        '-Type "Error" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert "bad CLI response" not in restore_backup_section
    assert "no CLI output" not in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore failed: $($_.Exception.Message)" '
        '-Type "Error" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Restored from: $capturedLabel"' not in (
        restore_backup_section
    )
    assert 'Show-Notification -Title "A.B.S.O." -Message "Restore failed' not in restore_backup_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Restore timed out: $capturedLabel"' not in (
        restore_backup_section
    )


def test_tray_backups_header_previews_restorable_game_marks() -> None:
    """Backups submenu header should summarize games represented by recent backups."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    backups_section = script.split("# Backups submenu (nested inside Actions)", 1)[1].split(
        "$actionsMenu.DropDownItems.Add($backupsItem)",
        1,
    )[0]

    assert "$recentBackups = Get-RecentBackups -Count 5" in backups_section
    assert backups_section.index("$recentBackups = Get-RecentBackups -Count 5") < backups_section.index(
        "$backupsItem = New-Object System.Windows.Forms.ToolStripMenuItem",
    )
    assert "$recentBackups = Get-RecentBackups -Count 5" in backups_section
    assert backups_section.count("$recentBackups = Get-RecentBackups -Count 5") == 1
    assert "$backupHeaderGameGroups = [System.Collections.Generic.List[string]]::new()" in backups_section
    assert "$backupHeaderGroupKeys = @{}" in backups_section
    assert "foreach ($backup in @($recentBackups))" in backups_section
    assert '$backupProfileId = if ($backup.ProfileId) { "$($backup.ProfileId)" } else { "" }' in backups_section
    assert "$backupGroup = Get-GameGroup -ProfileId $backupProfileId" in backups_section
    header_collect_section = backups_section.split("foreach ($backup in @($recentBackups))", 1)[1].split(
        "$backupsItem = New-Object System.Windows.Forms.ToolStripMenuItem",
        1,
    )[0]
    assert "Manifest profile ids are still useful when the live catalog is stale." in header_collect_section
    assert "$script:Profiles.Contains($backupProfileId)" not in header_collect_section
    assert "$backupHeaderGroupKeys.ContainsKey($backupGroupKey)" in backups_section
    assert "[void]$backupHeaderGameGroups.Add($backupGroup)" in backups_section
    assert "if ($backupHeaderGameGroups.Count -ge 3) { break }" in backups_section
    assert (
        "$backupHeaderGameGroups.Count -gt 0 -and "
        "(Get-Command New-BackupGameMosaicBitmap -ErrorAction SilentlyContinue)"
    ) in backups_section
    assert (
        "$backupsItem.Image = New-BackupGameMosaicBitmap -GameGroups @($backupHeaderGameGroups) "
        '-Color $script:Colors.AccentPurple -Category "Other"'
    ) in backups_section
    assert '$backupsItem.Image = New-ActionBitmap -Action "Backups" -Color $script:Colors.AccentPurple' in backups_section
    assert (
        "Set-TrayCommandItemVisualState -Item $backupsItem -ChipText "
        "(Get-BackupMenuChipText -VisibleBackupCount @($recentBackups).Count)"
    ) in backups_section
    assert 'Set-TrayCommandItemVisualState -Item $backupsItem -ChipText "BACKUP"' not in backups_section


def test_tray_backups_submenu_has_empty_state_row() -> None:
    """The backups flyout should explain an empty backup list instead of looking broken."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    backups_section = script.split("# Backups submenu (nested inside Actions)", 1)[1].split(
        "$actionsMenu.DropDownItems.Add($backupsItem)",
        1,
    )[0]

    assert "$recentBackups = Get-RecentBackups -Count 5" in backups_section
    assert "if (@($recentBackups).Count -le 0) {" in backups_section
    assert '$noBackupsItem.Text = "No backups found"' in backups_section
    assert "$noBackupsItem.Enabled = $false" in backups_section
    assert "$noBackupsItem.BackColor = $script:Colors.BackgroundDark" in backups_section
    assert "$noBackupsItem.ForeColor = $script:Colors.TextDisabled" in backups_section
    assert '$noBackupsItem.Image = New-ActionBitmap -Action "Backups" -Color $script:Colors.TextDisabled' in backups_section
    assert '$noBackupsItem.Image = New-ActionBitmap -Action "Info" -Color $script:Colors.TextDisabled' not in backups_section
    assert (
        '$noBackupsItem.ToolTipText = "No backup folders were found in installed or workspace backup locations."'
        in backups_section
    )
    assert "workspace fallback" not in backups_section
    assert '$openBackupsItem.ToolTipText = "Open the current backups folder"' in backups_section
    assert "$backupsItem.DropDownItems.Add($noBackupsItem) | Out-Null" in backups_section


def test_tray_backup_restore_timeout_replaces_restoring_state() -> None:
    """Backup restore should not leave the tray stuck in Restoring if the CLI hangs."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    restore_backup_section = script.split("$bItem.Add_Click({", 1)[1].split(
        "}.GetNewClosure())",
        1,
    )[0]
    assert 'Set-TrayOperationTooltipText -Text "A.B.S.O. - Restoring..."' in restore_backup_section
    assert "-NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `" in restore_backup_section
    assert "-RedirectStandardOutput $tf -RedirectStandardError $errFile" in restore_backup_section
    assert "$completed = $proc.WaitForExit(120000)" in restore_backup_section
    assert "$exitCode = $proc.ExitCode" in restore_backup_section
    assert "$exitCodeOk = ($null -eq $exitCode -or $exitCode -eq 0)" in restore_backup_section
    assert 'if ($exitCodeOk -and $null -ne $j -and $j.success -and $j.data -and $j.data.success)' in restore_backup_section
    assert 'if ($null -ne $j -and $j.success)' not in restore_backup_section
    assert 'elseif ($j.data -and $j.data.error) { $j.data.error }' in restore_backup_section
    assert 'elseif ($j.data -and $j.data.message) { $j.data.message }' in restore_backup_section
    assert 'Write-TrayLog "Restore \'$capturedName\' timed out after 120s" -Level "ERROR"' in restore_backup_section
    assert (
        'Show-Notification @restoreVisual -Title $restoreTitle -Message "Restore timed out: $capturedLabel" '
        '-Type "Error" -MetaText $restoreMetaText'
    ) in restore_backup_section
    assert 'Set-TrayLastAction -Message "Restore timed out: $capturedLabel"' in restore_backup_section
    assert 'if ($tf) { Remove-Item $tf -Force -ErrorAction SilentlyContinue }' in restore_backup_section
    assert 'if ($errFile) { Remove-Item $errFile -Force -ErrorAction SilentlyContinue }' in restore_backup_section
    assert "-NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `" not in restore_backup_section


def test_tray_system_info_uses_multidisplay_refresh_summary() -> None:
    """The tray should not imply one WMI refresh rate describes every display."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Ensure-TrayDisplaySettingsReader" in script
    assert "EnumDisplaySettings" in script
    assert "[System.Windows.Forms.Screen]::AllScreens" in script
    assert "function Get-TrayDisplaySummary" in script
    assert "function New-TrayDisplayTopologyBitmap" in script
    assert 'DisplaySummary = "Display status not reported"' in script
    assert 'return "Display status not reported"' in script
    assert '"Display unknown"' not in script
    assert '"$screenCount displays - $($rateLabels -join \'/\') mixed"' in script
    assert "$displayCount = 0" in script
    assert "$isMixed = ($summary -match '(?i)\\bmixed\\b' -or $summary -match '\\d+\\s*Hz\\s*/\\s*\\d+\\s*Hz')" in script
    assert "$hasRate = ($summary -match '\\d+\\s*Hz')" in script
    assert "$summary -notmatch '(?i)unknown|not reported'" in script
    assert "$accent = if ($isMixed) { $script:Colors.AccentAmber } elseif ($hasRate) { $script:Colors.AccentTeal } else { $Color }" in script
    assert "$g.FillEllipse($accentBrush, 10, 0, 5, 5)" in script
    assert "$sysInfoText = \"$($sysInfo.GPU)  |  $($sysInfo.DisplaySummary)\"" in script
    assert "$sysInfoItem.AccessibleName = \"__status_bar__\"" in script
    assert "$sysInfoItem.AccessibleDescription = Get-TraySystemInfoChipText -GpuName $sysInfo.GPU -DisplaySummary $sysInfo.DisplaySummary" in script
    assert "$sysInfoItem.Image = New-TrayDisplayTopologyBitmap -DisplaySummary $sysInfo.DisplaySummary -Color $script:Colors.TextDisabled" in script
    assert '$sysInfoItem.Image = New-ActionBitmap -Action "Display" -Color $script:Colors.TextDisabled' not in script
    assert "$sysInfoText = \"$($sysInfo.GPU)  |  $($sysInfo.RefreshRate)\"" not in script
    system_info_section = script.split("function Get-SystemInfo", 1)[1].split(
        "function ConvertTo-TrayDateTime",
        1,
    )[0]
    assert 'GPU = "GPU not reported"' in system_info_section
    assert 'Monitor = "Display not reported"' in system_info_section
    assert 'RefreshRate = "Refresh rate not reported"' in system_info_section
    assert 'GPU = "Unknown GPU"' not in system_info_section
    assert 'Monitor = "Unknown"' not in system_info_section
    assert 'RefreshRate = "?"' not in system_info_section
    system_chip_section = script.split("function Get-TraySystemInfoChipText", 1)[1].split(
        "function ConvertTo-TrayDateTime",
        1,
    )[0]
    assert "$gpuReported = (-not [string]::IsNullOrWhiteSpace($gpuText) -and $gpuText -notmatch '(?i)unknown|not reported')" in system_chip_section
    assert "$displayReported = (-not [string]::IsNullOrWhiteSpace($displayText) -and $displayText -notmatch '(?i)unknown|not reported')" in system_chip_section
    assert '[void]$chips.Add("GPU")' in system_chip_section
    assert '[void]$chips.Add("DISPLAY")' in system_chip_section
    assert '[void]$chips.Add("MIXED")' in system_chip_section
    assert '[void]$chips.Add("HZ")' in system_chip_section
    assert '[void]$chips.Add("NO-DATA")' in system_chip_section


def test_tray_last_action_status_uses_timestamped_failure_state() -> None:
    """Durable tray status should not keep a stale action after restore failures."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Set-TrayLastAction" in script
    assert "function Normalize-TrayLastActionMessage" in script
    assert "$script:LastAction = Normalize-TrayLastActionMessage -Message $Message" in script
    assert "function Get-TrayLastActionTimeMessage" in script
    assert "function New-TrayLastActionStatusBitmap" in script
    assert "function New-TrayStatusBarImage" in script
    assert 'return New-ActionBitmap -Action "PendingFix" -Color $script:Colors.AccentAmber' in script
    assert 'return New-ActionBitmap -Action "Apply" -Color $script:Colors.AccentAmber' not in script
    assert 'return New-ActionBitmap -Action "WindowsRestart" -Color $script:Colors.AccentAmber' in script
    assert 'return New-ActionBitmap -Action "Warning" -Color $script:Colors.AccentAmber' not in script
    status_image_section = script.split("function New-TrayStatusBarImage", 1)[1].split(
        "function Get-TrayProfileDisplayName",
        1,
    )[0]
    assert "$favoriteBadge = (Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig)" in status_image_section
    assert "return New-TrayProfileMenuImage `" in status_image_section
    assert "-ProfileId $ProfileId `" in status_image_section
    assert "-IsActive ($ProfileId -eq $script:activeProfile) `" in status_image_section
    assert "-ShowSyncBadge $true `" in status_image_section
    assert "-FavoriteBadge $favoriteBadge" in status_image_section
    assert 'if (-not [string]::IsNullOrWhiteSpace($ProfileId)) {' in status_image_section
    assert "[AllowNull()][string]$VerificationProgressText" in status_image_section
    assert "$verificationBadge = -not [string]::IsNullOrWhiteSpace($VerificationProgressText)" in status_image_section
    assert "[AllowNull()][string]$LastActionText" in status_image_section
    assert "-VerificationBadge $verificationBadge" in status_image_section
    assert 'return New-ActionBitmap -Action "Search" -Color $script:Colors.AccentBlue' in status_image_section
    assert "$lastActionImage = New-TrayLastActionStatusBitmap -LastActionText $LastActionText -FallbackColor $dimColor" in (
        status_image_section
    )
    assert "if ($lastActionImage) { return $lastActionImage }" in status_image_section
    assert "-VerificationProgressText $verificationProgressText `" in script
    assert "-LastActionText $statusBarLastActionText `" in script


def test_tray_status_bar_maps_last_action_to_specific_glyphs() -> None:
    """Non-profile LastAction messages should not all collapse to the Info glyph."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    action_section = script.split("function New-TrayLastActionStatusBitmap", 1)[1].split(
        "function New-TrayStatusBarImage",
        1,
    )[0]

    for action in [
        "PendingFix",
        "WindowsRestart",
        "Restore",
        "Audit",
        "Startup",
        "Reset",
        "Memory",
        "QuickPanel",
        "Refresh",
        "Backups",
        "Log",
        "Settings",
        "Folder",
        "Toast",
        "Sound",
        "Apply",
    ]:
        assert f'$action = "{action}"' in action_section

    assert "switch -Regex ($text)" in action_section
    assert "'^(Quick Panel)'" in action_section
    assert "'^(Display reset)'" in action_section
    assert "'^(Profiles refreshed|Profiles fallback|Profile refresh)'" in action_section
    assert "'^(Tray restart)'" in action_section
    assert "'^(Opened backups|Open backups|No backups|Current backups)'" in action_section
    assert "$color = if ($text -match '(?i)failed|warning') { $script:Colors.AccentAmber } else { $script:Colors.AccentBlue }" in (
        action_section
    )
    assert "'^(Toast popups)'" in action_section
    assert "'^(Tray audio cues)'" in action_section
    assert "'^(Profile missing|Profile not found|Apply timed out|Apply failed:|Not applied\\.|Applied|Failed:|Error:)'" in (
        action_section
    )
    assert "return New-ActionBitmap -Action $action -Color $color" in action_section
    assert 'return New-ActionBitmap -Action "Info" -Color $dimColor' not in action_section


def test_tray_has_dedicated_windows_restart_status_glyph() -> None:
    """Windows-restart warnings should not look like generic warnings or tray restarts."""
    icons = ICONS_SCRIPT.read_text(encoding="utf-8")
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    status_image_section = script.split("function New-TrayStatusBarImage", 1)[1].split(
        "function Get-TrayProfileDisplayName",
        1,
    )[0]
    assert "WindowsRestart" in icons
    restart_icon_section = icons.split('"WindowsRestart" {', 1)[1].split('"Toast" {', 1)[0]
    assert "Windows reboot-required mark" in restart_icon_section
    assert "$g.DrawArc($arcPen, 3, 2, 10, 10, 210, 285)" in restart_icon_section
    assert "$g.FillPolygon($headBrush, $headPoints)" in restart_icon_section
    assert "$g.DrawLine($powerPen, 8, 5, 8, 7.5)" in restart_icon_section
    assert "Startup launch arrow from a small Windows tile" in icons
    assert "$accent = Get-TrayProfileAccentColor -ProfileId $ProfileId -Profile $profile -Fallback $dimColor" in (
        status_image_section
    )
    assert "$gameGroup = Get-TrayProfileGameGroup -ProfileId $ProfileId -Profile $profile" in status_image_section
    assert "return New-ActiveGameBitmap `" in status_image_section
    assert "return New-FavoriteGameBitmap `" in status_image_section
    assert "return New-GameSyncBadgeBitmap `" in status_image_section
    assert '-SyncMode "agnostic" `' in status_image_section
    assert 'return New-ActionBitmap -Action "Info" -Color $dimColor' in script
    assert "Set-MenuItemImageSafe -Item $script:statusBarItem -NewImage $statusImage" in script
    assert '$script:statusBarItem.Image = New-ActionBitmap -Action "Info" -Color $script:statusBarItem.ForeColor' in script
    assert 'return "Action: $displayTime"' in script
    assert 'Set-TrayLastAction -Message "Restore timed out after 120s"' in script
    assert 'Set-TrayLastAction -Message "Restore timed out: $capturedLabel"' in script
    assert 'Set-TrayLastAction -Message "Restored backup: $capturedLabel"' in script
    assert 'Set-TrayLastAction -Message "Restore failed: $restoreError"' in script
    assert 'Set-TrayLastAction -Message "Restore failed: runtime status unreadable"' in script
    assert 'Set-TrayLastAction -Message "Restore failed: runtime returned no status"' in script
    assert 'Set-TrayLastAction -Message "Restore failed: $($_.Exception.Message)"' in script
    assert "Restore-TrayTooltipFromState" in script
    restore_settings_section = script.split("function Restore-Settings", 1)[1].split(
        "# ============================================================================\n# MENU STATE",
        1,
    )[0]
    assert "Restore-TrayTooltipFromState" in restore_settings_section
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Restore timed out after 120s" '
        '-Type "Error" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber'
    ) in restore_settings_section
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Settings restored" '
        '-Type "Success" -ActionName "Restore" -ActionColor $script:Colors.AccentGreen'
    ) in restore_settings_section
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Restore failed: $restoreError" '
        '-Type "Error" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber'
    ) in restore_settings_section
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Restore failed: $($_.Exception.Message)" '
        '-Type "Error" -ActionName "Restore" -ActionColor $script:Colors.AccentAmber'
    ) in restore_settings_section
    assert 'Set-IconState -State "Error"' in restore_settings_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Failed: $restoreError" -Type "Warning"' not in restore_settings_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Error: $($_.Exception.Message)" -Type "Warning"' not in restore_settings_section
    assert 'Set-IconState -State "Warning"' not in restore_settings_section
    assert 'throw "runtime returned no restore status"' in restore_settings_section
    assert 'throw "No output"' not in restore_settings_section
    assert '$script:notifyIcon.Text = "A.B.S.O."' not in restore_settings_section
    assert "$lastActionTimeMessage = Get-TrayLastActionTimeMessage -Value $script:LastActionTime" in script
    assert "$statusShouldShowActionTime = (" in script
    assert "[string]::IsNullOrWhiteSpace($pendingApplyText)" in script
    assert "if ($statusShouldShowActionTime) { Add-UniqueTrayMessage -Target $statusParts -Message $lastActionTimeMessage }" in script
    assert 'LastActionTime = Get-Date -Format "HH:mm"' not in script
    assert "Add-UniqueTrayMessage -Target $statusParts -Message $script:LastActionTime" not in script


def test_tray_action_toasts_update_durable_status() -> None:
    """Tray actions that show result toasts should not leave an older status bar action."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'Set-TrayLastAction -Message "Startup enabled: $modeLabel"' in script
    assert 'Set-TrayLastAction -Message "Startup enabled with warning: $modeLabel"' in script
    assert 'Set-TrayLastAction -Message "Startup disabled"' in script
    assert 'Set-TrayLastAction -Message "Startup disabled with warning"' in script
    assert 'Set-TrayLastAction -Message "Startup unchanged: $state"' in script
    assert '"Startup unchanged; still $state"' in script
    assert '"Startup unchanged; still ${state}: $installerWarning"' in script
    assert '"Startup is $state"' not in script
    assert 'Set-TrayLastAction -Message "Startup update running"' in script
    assert 'Set-TrayLastAction -Message "Startup update failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Startup update failed"' not in script
    assert 'Set-TrayLastAction -Message "Display reset: $count combo(s) sent"' in script
    assert 'Set-TrayLastAction -Message "Display reset timed out after 30s"' in script
    assert 'Set-TrayLastAction -Message "Display reset failed: runtime status unreadable"' in script
    assert 'Set-TrayLastAction -Message "Display reset failed: runtime returned no status"' in script
    assert 'Set-TrayLastAction -Message "Quick Panel opened"' in script
    assert 'Set-TrayLastAction -Message "Quick Panel closed"' in script
    assert 'LastAction = "Quick Panel empty"' in script
    assert 'Set-TrayLastAction -Message $quickPanelEmpty.LastAction' in script
    assert 'Set-TrayLastAction -Message "Profiles refreshed: $profileCount from $catalogSource"' in script
    assert 'Set-TrayLastAction -Message "Profiles fallback list loaded: $profileCount"' in script
    assert 'Set-TrayLastAction -Message "Profiles safe list loaded: $profileCount"' not in script
    assert 'Set-TrayLastAction -Message "Profiles fallback loaded: $profileCount"' not in script
    assert 'Set-TrayLastAction -Message "Profile refresh failed: no profiles loaded"' in script
    assert 'Set-TrayLastAction -Message "Profile refresh failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Profiles refreshed: $($script:Profiles.Count) loaded"' not in script
    assert 'Set-TrayLastAction -Message "Profile refresh failed"' not in script
    assert 'Set-TrayLastAction -Message "Clearing standby list"' in script
    assert 'Set-TrayLastAction -Message "Standby list cleared: ~${freed}MB"' in script
    assert 'Set-TrayLastAction -Message "Standby clear timed out after 15s"' in script
    assert 'Set-TrayLastAction -Message "Standby clear failed: runtime returned no status"' in script
    assert '$clearError = if ($json.error)' in script
    assert 'Set-TrayLastAction -Message "Standby clear failed: $clearError"' in script
    assert 'Set-TrayLastAction -Message "Standby clear failed"' not in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Standby list cleared. Freed ~${freed}MB" '
        '-Type "Success" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue'
    ) in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Standby clear failed: runtime returned no status" '
        '-Type "Error" -ActionName "Memory" -ActionColor $script:Colors.AccentBlue'
    ) in script


def test_tray_settings_and_folder_actions_update_durable_status() -> None:
    """Menu settings/folder actions should not leave older action text in the status bar."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '$auditActionMessage = "Audit clean: no issues in scope"' in script
    assert '$auditIssueLabel = if ($issueCount -eq 1) { "issue" } else { "issues" }' in script
    assert '$auditStatusLabel = if ($issueCount -eq 1) { "Issue Found" } else { "Issues Found" }' in script
    assert '$auditActionMessage = "Audit ${auditIssueLabel} found: $issueCount"' in script
    assert '$script:LastAction = $auditActionMessage' in script
    assert "function Set-TrayAuditStatusItem" in script
    assert '$script:auditStatusItem.AccessibleName = "__status_bar__"' in script
    assert '$script:auditStatusItem.AccessibleDescription = "AUDIT"' in script
    assert '$script:auditStatusItem.AccessibleDescription = if ([string]::IsNullOrWhiteSpace($ChipText)) { "AUDIT" } else { $ChipText }' in script
    assert 'Set-TrayAuditStatusItem -Text "Audit Running" -Color $script:Colors.AccentBlue -ChipText "AUDIT|RUN"' in script
    assert 'Set-TrayAuditStatusItem -Text "Audit Failed" -Color $script:Colors.AccentAmber -ChipText "AUDIT|FAIL" -IssueBadge' in script
    assert 'Set-TrayAuditStatusItem `' in script
    assert '-Text "${auditStatusLabel}: $issueCount" `' in script
    assert '-ChipText "AUDIT|ISSUES" `' in script
    assert 'Set-TrayAuditStatusItem -Text "No Issues In Scope" -Color $script:Colors.AccentGreen -ChipText "AUDIT|CLEAN"' in script
    assert "function New-AuditStatusBitmap" in ICONS_SCRIPT.read_text(encoding="utf-8")
    assert "Issue states keep the audit lens visible" in ICONS_SCRIPT.read_text(encoding="utf-8")
    assert "New-AuditStatusBitmap -Color $script:auditStatusItem.ForeColor -IssueBadge:$IssueBadge" in script
    assert "$script:auditStatusItem.Image = New-AuditStatusBitmap -Color $script:Colors.AccentGreen" in script
    assert '$script:auditStatusItem.Text = "${auditStatusLabel}: $issueCount"' not in script
    assert '$script:auditStatusItem.Text = "No Issues In Scope"' not in script
    assert 'New-ActionBitmap -Action "Warning" -Color $script:auditStatusItem.ForeColor' not in script
    assert '$script:auditStatusItem.Text = "      Issues Found: $issueCount"' not in script
    assert '$script:auditStatusItem.Text = "      No Issues In Scope"' not in script
    assert '$script:LastAction = "Audit failed: runtime returned no status"' in script
    assert '$script:LastAction = "Audit failed: runtime status unreadable"' in script
    assert '$script:LastAction = "Audit failed: $auditError"' in script
    assert '$script:LastAction = "Audit failed: $($_.Exception.Message)"' in script
    assert '$script:LastAction = "Audit failed"' not in script
    assert '"Audit failed: no CLI output"' not in script
    assert '"Audit failed: bad CLI response"' not in script
    assert '$auditActionMessage = "Audit completed: no details"' not in script
    assert 'Write-TrayLog "Audit issue ${issueIndex}/${issueCount}: $(Format-TrayUserFacingText -Text $issueText)" -Level "WARN"' in script
    assert (
        'Show-Notification -Title "A.B.S.O. Audit" -Message "$issueCount $auditIssueLabel found. See tray log for details." '
        '-Type "Warning" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue'
    ) in script
    assert "issue(s)" not in script
    assert (
        'Show-Notification -Title "A.B.S.O. Audit" -Message "No issues detected by the current audit scope." '
        '-Type "Success" -ActionName "Audit" -ActionColor $script:Colors.AccentBlue'
    ) in script
    assert "Run 'abso audit' for details" not in script
    assert 'Set-TrayLastAction -Message "Opened backups folder"' in script
    assert 'Set-TrayLastAction -Message "Open backups failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Open backups failed"' not in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Failed to open backups folder: $($_.Exception.Message)" '
        '-Type "Error" -ActionName "Folder" -ActionColor $script:Colors.AccentPurple'
    ) in script
    assert 'Show-Notification -Title "A.B.S.O." -Message "Failed to open folder: $($_.Exception.Message)"' not in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Current backups folder not found. Applying a profile creates it." '
        '-Type "Info" -ActionName "Backups" -ActionColor $script:Colors.AccentPurple'
    ) in script
    assert 'Set-TrayLastAction -Message "Current backups folder not found"' in script
    assert 'Show-Notification -Title "A.B.S.O." -Message "No backups have been created yet"' not in script
    assert 'Set-TrayLastAction -Message "No backups created yet"' not in script
    assert 'Show-Notification -Title "A.B.S.O." -Message "No backups folder found" -Type "Warning"' not in script
    assert 'Set-TrayLastAction -Message "No backups folder found"' not in script
    assert 'Set-TrayLastAction -Message "Opened tray log file"' in script
    assert 'Set-TrayLastAction -Message "Open tray log failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Open tray log failed"' not in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Failed to open tray log: $($_.Exception.Message)" '
        '-Type "Error" -ActionName "Log" -ActionColor $script:Colors.TextDim'
    ) in script
    assert 'Set-TrayLastAction -Message "Opened tray settings folder"' in script
    assert 'Set-TrayLastAction -Message "Open tray settings failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Open tray settings failed"' not in script
    assert 'Set-TrayLastAction -Message "Opened installed runtime folder"' in script
    assert 'Set-TrayLastAction -Message "Open runtime folder failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Open runtime folder failed"' not in script
    assert 'Set-TrayLastAction -Message "Opened user profiles folder"' in script
    assert 'Set-TrayLastAction -Message "Open profiles folder failed: $($_.Exception.Message)"' in script
    assert 'Set-TrayLastAction -Message "Open profiles folder failed"' not in script
    assert 'Set-TrayLastAction -Message "Toast popups $state"' in script
    assert 'Set-TrayLastAction -Message "Tray audio cues $state"' in script
    assert 'Set-TrayLastAction -Message "Tray settings saved"' in script
    assert '$auditItem.ToolTipText = "Scan the current audit scope for optimization issues"' in script
    assert '$auditItem.ToolTipText = "Scan system for optimization issues"' not in script
    assert '$resetDisplayItem.Image = New-ActionBitmap -Action "Reset" -Color $script:Colors.AccentAmber' in script
    assert "$startupIconAction = if ($startupActionIsStale) { \"Warning\" } else { \"Startup\" }" in script
    assert "Set-MenuItemImageSafe -Item $script:startupItem -NewImage (New-ActionBitmap -Action $startupIconAction -Color $startupIconColor)" in script
    assert '$script:startupItem.Image = New-ActionBitmap -Action "Startup" -Color $script:Colors.Text' not in script
    assert '$script:notifyToggle.Image = New-ActionBitmap -Action "Toast" -Color $script:Colors.Text' in script
    assert '$soundToggle.Image = New-ActionBitmap -Action "Sound" -Color $script:Colors.Text' in script
    assert '"      Disable Auto-Start"' not in script
    assert '"      Enable Auto-Start"' not in script
    assert '"Disable Auto-Start"' in script
    assert '"Enable Auto-Start"' in script
    assert '$openBackupsItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.AccentPurple' in script
    assert '$bItem.Image = New-ActionBitmap -Action "Restore" -Color $script:Colors.AccentPurple' in script
    assert '$openProfilesItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.TextDim' in script
    assert '$clearMemoryItem.Image = New-ActionBitmap -Action "Memory" -Color $script:Colors.AccentBlue' in script
    assert '$clearMemoryItem.ToolTipText = "Requests a standby-memory purge; does not close apps or change profiles"' in script
    assert "Purge cached memory pages (ISLC equivalent)" not in script
    assert '$settingsPanelItem.Image = New-ActionBitmap -Action "Settings" -Color $script:Colors.Text' in script
    assert '$logItem.Image = New-ActionBitmap -Action "Log" -Color $script:Colors.TextDim' in script
    assert '$configFolderItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.TextDim' in script
    assert '$runtimeFolderItem.Image = New-ActionBitmap -Action "Folder" -Color $script:Colors.TextDim' in script
    assert '$restartItem.Image = New-ActionBitmap -Action "Refresh" -Color $script:Colors.TextDim' in script
    assert '$aboutItem.Image = New-ActionBitmap -Action "Info" -Color $script:Colors.TextDim' in script


def test_tray_toast_toggle_copy_and_state_are_accurate() -> None:
    """The tray popup toggle should not claim to disable all notifications or reset on restart."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    settings = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    assert "notificationsEnabled = $true" in settings
    assert "$script:EnableBalloonNotifications = [bool]$script:TrayConfig.notificationsEnabled" in tray
    assert '$script:notifyToggle.Text = "Toast Popups"' in tray
    assert '$script:notifyToggle.ToolTipText = "Toggle themed toast popups; tray hover/status text still updates"' in tray
    assert "$script:TrayConfig.notificationsEnabled = $script:EnableBalloonNotifications" in tray
    assert 'Write-TrayLog "Toast popups $state"' in tray
    assert 'Set-TrayLastAction -Message "Toast popups $state"' in tray
    assert 'Toggle balloon notifications' not in tray
    assert '$script:notifyToggle.Text = "Notifications"' not in tray


def test_tray_sound_toggle_copy_is_scope_accurate() -> None:
    """Sound toggle should describe tray audio cues without implying visual status is disabled."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    settings = SETTINGS_SCRIPT.read_text(encoding="utf-8")
    assert '$soundToggle.Text = "Tray Audio Cues"' in tray
    assert '$soundToggle.ToolTipText = "Toggle tray audio cues; toasts and status text still update"' in tray
    assert '$soundCheck.Text = "Enable tray audio cues"' in settings
    assert 'Write-TrayLog "Tray audio cues: $($script:TrayConfig.soundEnabled)"' in tray
    assert 'Set-TrayLastAction -Message "Tray audio cues $state"' in tray
    assert "Restart sound skipped (tray audio cues disabled)" in tray
    assert '$soundToggle.ToolTipText = "Toggle sound effects"' not in tray
    assert '$soundToggle.Text = "Sound Effects"' not in tray
    assert '$soundCheck.Text = "Enable sound effects"' not in settings
    assert 'Set-TrayLastAction -Message "Sound effects $state"' not in tray


def test_tray_profile_refresh_reports_actual_catalog_source() -> None:
    """Manual profile refresh should not report generic success when fallback/empty data loaded."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$script:ProfileCatalogLastSource = $null" in tray
    assert "$script:ProfileCatalogLastCount = 0" in tray
    assert "$script:ProfileCatalogUsedFallback = $false" in tray
    assert '$script:ProfileCatalogLastSource = $source' in tray
    assert '$script:ProfileCatalogLastSource = "built-in fallback"' in tray
    assert '$catalogSource = if ($script:ProfileCatalogLastSource) { "$($script:ProfileCatalogLastSource)" } else { "source not reported" }' in tray
    assert '"unknown source"' not in tray
    assert '$refreshProfilesItem.ToolTipText = "Reload the profile list and user profiles; no profile is applied."' in tray
    assert 'Reload profile catalog from cache/CLI, then user profiles' not in tray
    assert 'Profiles loaded from built-in fallback profile list ($profileCount profiles)' in tray
    assert 'Profiles loaded from built-in safe list ($profileCount profiles)' not in tray
    assert 'Profiles loaded from built-in fallback ($profileCount profiles)' not in tray
    assert 'Profiles refreshed from $catalogSource ($profileCount profiles loaded)' in tray
    assert 'Profile refresh failed: no profiles loaded' in tray
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Profiles refreshed from $catalogSource ($profileCount profiles loaded)" '
        '-Type "Success" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue'
    ) in tray
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Profiles loaded from built-in fallback profile list ($profileCount profiles)" '
        '-Type "Warning" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue'
    ) in tray
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Profile refresh failed: no profiles loaded" '
        '-Type "Error" -ActionName "Refresh" -ActionColor $script:Colors.AccentBlue'
    ) in tray
    assert 'Profiles refreshed ($($script:Profiles.Count) profiles loaded)' not in tray
    assert 'Reload profiles from CLI catalog and user profiles' not in tray


def test_tray_noop_notifications_update_durable_status() -> None:
    """No-op/error notifications should also replace stale status-bar action text."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'Set-TrayLastAction -Message "Profile missing from current list: $missingProfileTitle"' in script
    assert 'Set-TrayLastAction -Message "Apply timed out after 120s"' in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "No active profile to repair" '
        '-Type "Info" -ActionName "Apply" -ActionColor $script:Colors.AccentAmber'
    ) in script
    assert 'Show-Notification -Title "A.B.S.O." -Message "No active profile to repair" -Type "Warning"' not in script
    assert 'Set-TrayLastAction -Message "No active profile to repair"' in script
    assert 'Set-TrayLastAction -Message "No pending profile fixes found"' in script
    assert 'Set-TrayLastAction -Message "Restore hotkey ignored: no active profile"' in script
    assert 'Set-TrayLastAction -Message "Audit already running"' in script
    assert (
        "$defaultReminderTitle = Get-TrayProfileObjectDisplayName -Profile $defProfile -Fallback $defaultProfileId"
        in script
    )
    assert 'Set-TrayLastAction -Message "Startup reminder: $defaultReminderTitle"' in script
    assert 'Set-TrayLastAction -Message "Startup reminder: $($defProfile.Name)"' not in script
    assert 'Startup reminder profile is not in the current profile list.' in script
    assert '$defaultMissingVisual = Get-TrayProfileToastVisualArgs -ProfileId $defaultProfileId -Profile $null' in script
    assert 'Show-Notification @defaultMissingVisual -Title $defaultProfileName -Message "Startup reminder profile is not in the current profile list." -Type "Warning" -MetaText $defaultProfileId' in script
    assert 'Set-TrayLastAction -Message "Startup reminder missing: $defaultProfileName"' in script
    assert 'Default startup reminder profile \'$defaultProfileId\' is not in the current profile list' in script
    assert 'Default startup reminder profile \'$defaultProfileId\' is not in the loaded catalog' not in script
    assert 'Set-TrayLastAction -Message "Double-click ignored: no favorite"' in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "No favorite profile configured for double-click." '
        '-Type "Info" -ActionName "Favorite" -ActionColor $script:Colors.AccentAmber'
    ) in script
    assert 'Favorite profile is not in the current profile list.' in script
    assert '$favMissingVisual = Get-TrayProfileToastVisualArgs -ProfileId $lastFav -Profile $null' in script
    assert 'Show-Notification @favMissingVisual -Title $favName -Message "Favorite profile is not in the current profile list." -Type "Warning" -MetaText $lastFav' in script
    assert 'Favorite profile is not in the loaded catalog: $favName.' not in script
    assert 'Set-TrayLastAction -Message "Favorite missing: $favName"' in script
    assert "Open tray menu to apply." in script
    assert "Right-click to apply." not in script


def test_default_profile_startup_reminder_keeps_profile_visuals() -> None:
    """Default startup reminder should show the configured profile identity without applying it."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    reminder_section = script.split("# ─── DEFAULT PROFILE (notify only, do not auto-apply) ───", 1)[1].split(
        "# Only play restart sound once the new tray instance has fully initialized.",
        1,
    )[0]

    assert "$defaultProfileId = \"$($script:TrayConfig.defaultProfile)\"" in reminder_section
    assert "$defProfile = $script:Profiles[$defaultProfileId]" in reminder_section
    assert 'Write-TrayLog "Default profile available: $defaultProfileId (not auto-applying)"' in reminder_section
    assert "$defaultReminderVisual = Get-TrayProfileToastVisualArgs -ProfileId $defaultProfileId -Profile $defProfile" in (
        reminder_section
    )
    assert (
        "$defaultReminderTitle = Get-TrayProfileObjectDisplayName -Profile $defProfile -Fallback $defaultProfileId"
        in reminder_section
    )
    assert (
        'Show-Notification @defaultReminderVisual -Title $defaultReminderTitle '
        '-Message "Default profile ready. Open tray menu to apply." -Type "Info" -MetaText $defaultProfileId'
    ) in reminder_section
    assert 'Show-Notification @defaultReminderVisual -Title $defProfile.Name' not in reminder_section
    assert 'Set-TrayLastAction -Message "Startup reminder: $defaultReminderTitle"' in reminder_section
    assert 'Set-TrayLastAction -Message "Startup reminder: $($defProfile.Name)"' not in reminder_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Default profile ready:' not in reminder_section
    assert "not auto-applying" in reminder_section


def test_apply_pending_noop_notices_keep_active_profile_visuals() -> None:
    """Pending-fix no-op toasts should keep active profile game context."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    pending_section = script.split("function Apply-PendingProfileFixes", 1)[1].split(
        "function Get-TrayCommandFilePath",
        1,
    )[0]

    assert "$activeRecord = Get-ActiveTrayProfileRecord" in pending_section
    assert "$pendingNoopVisual = Get-TrayProfileToastVisualArgs `" in pending_section
    assert "$pendingNoopTitle = if ($activeRecord.Id) { $activeRecord.DisplayName } else { \"A.B.S.O.\" }" in (
        pending_section
    )
    assert (
        'Show-Notification @pendingNoopVisual -Title $pendingNoopTitle '
        '-Message "No pending profile fixes found" -Type "Info" -MetaText $script:activeProfile'
    ) in pending_section
    assert "$pendingToastVisual = Get-TrayProfileToastVisualArgs `" in pending_section
    assert "$pendingTitle = if ($activeRecord.Id) { $activeRecord.DisplayName } else { \"A.B.S.O.\" }" in (
        pending_section
    )
    assert (
        'Show-Notification @pendingToastVisual -Title $pendingTitle '
        '-Message "No pending profile fix was needed" -Type "Info" -MetaText $script:activeProfile'
    ) in pending_section
    assert 'else { "reason not reported" }' in pending_section
    assert 'else { "unknown error" }' not in pending_section
    assert '$script:LastAction = "No pending profile fix needed"' in pending_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "No pending profile fixes found"' not in pending_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "No pending write was needed"' not in pending_section
    assert "No pending write was needed" not in pending_section
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "No active profile to repair" '
        '-Type "Info" -ActionName "Apply" -ActionColor $script:Colors.AccentAmber'
    ) in pending_section


def test_apply_success_status_uses_backend_applied_profile_display_name() -> None:
    """Apply success copy should not reuse requested profile metadata after catalog drift."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    apply_success_section = script.split("if ($applySucceeded) {", 1)[1].split(
        "else {\n            $err = Get-ApplyFailureMessage",
        1,
    )[0]
    assert '$appliedProfile = $null' in apply_success_section
    assert "$appliedProfileId -eq $ProfileId -and $profile" in apply_success_section
    assert "$appliedDisplayName = if ($appliedProfile" in apply_success_section
    assert "Get-TrayProfileDisplayName -ProfileId $appliedProfileId" in apply_success_section
    assert '$toastTitle = $appliedDisplayName' in apply_success_section
    assert '$msg = if ([string]::IsNullOrWhiteSpace($appliedSub)) { "Applied." } else { "Applied. $appliedSub." }' in apply_success_section
    assert "Get-TrayProfileDisplayName -ProfileId $requestedProfileId" in apply_success_section
    assert '"Applied: $appliedDisplayName"' in apply_success_section
    assert "Add-ProfileHistory -ProfileId $appliedProfileId -ProfileName $appliedDisplayName" in apply_success_section


def test_tray_restart_sound_marker_is_token_scoped() -> None:
    """A stale restart marker from an abandoned restart must not play on unrelated tray starts."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '[string]$RestartToken = ""' in script
    assert "$script:RestartToken = if ([string]::IsNullOrWhiteSpace($RestartToken))" in script
    assert "function Clear-RestartSuccessSoundMarker" in script
    assert "restart_token = $RestartToken.Trim()" in script
    assert "$markerToken -ne $script:RestartToken" in script
    assert "Restart success-sound marker ignored: token mismatch or missing" in script
    assert '$restartToken = [guid]::NewGuid().ToString("N")' in script
    assert "Set-RestartSuccessSoundMarker -RestartToken $restartToken" in script
    assert '"-RestartToken", "`"$restartToken`""' in script
    restart_section = script.split('$restartItem.Add_Click({', 1)[1].split(
        '$menu.Items.Add($restartItem)',
        1,
    )[0]
    assert "try {" in restart_section
    assert "Clear-RestartSuccessSoundMarker" in restart_section
    assert 'if ($script:notifyIcon) { $script:notifyIcon.Visible = $true }' in restart_section
    assert 'Set-TrayLastAction -Message "Tray restart failed: $($_.Exception.Message)"' in restart_section
    assert "Restore-TrayTooltipFromState -Force" in restart_section
    assert "Update-MenuState" in restart_section
    assert 'Show-Notification -Title "A.B.S.O." -Message "Tray restart failed: $($_.Exception.Message)" -Type "Error" -ActionName "Refresh" -ActionColor $script:Colors.AccentAmber' in restart_section
    assert 'Start-Process "wscript.exe"' not in restart_section


def test_tray_writes_runtime_marker_for_health_staleness_checks() -> None:
    """Health should be able to prove whether live tray code matches disk."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Write-TrayRuntimeMarker" in script
    assert '"tray-runtime.json"' in script
    assert "script_hash_sha256" in script
    assert "module_hashes = $moduleHashes" in script
    assert '"ABSO-Theme.ps1"' in script
    assert '"ABSO-QuickPanel.ps1"' in script
    assert '"ABSO-Icons.ps1"' in script
    assert "Get-FileHash -Algorithm SHA256" in script
    assert "Write-TrayRuntimeMarker" in script


def test_tray_uses_shared_theme_tokens_across_surfaces() -> None:
    """Menu, toasts, and quick panel should share one visual token source."""
    tray = TRAY_SCRIPT.read_text(encoding="utf-8")
    theme = THEME_SCRIPT.read_text(encoding="utf-8")
    notifications = NOTIFICATIONS_SCRIPT.read_text(encoding="utf-8")
    quick_panel = QUICK_PANEL_SCRIPT.read_text(encoding="utf-8")

    assert '. (Join-Path $script:ScriptDir "ABSO-Theme.ps1")' in tray
    assert "function Get-TrayThemePalette" in theme
    assert "CategoryDesktop" in theme
    assert "$script:Colors = Get-TrayThemePalette" in tray
    assert "$script:Penumbra = if (Get-Command Get-TrayThemePalette" in notifications
    assert "$script:QPPalette = if (Get-Command Get-TrayThemePalette" in quick_panel


def test_tray_display_pipeline_reset_requires_warning_confirmation() -> None:
    """Manual driver-reset recovery must not be one click from the tray."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert '$resetDisplayItem.Text = "Reset Display Pipeline..."' in script
    assert "[System.Windows.Forms.MessageBox]::Show" in script
    assert "can blank or disconnect monitors for a few seconds" in script
    assert "[System.Windows.Forms.MessageBoxDefaultButton]::Button2" in script
    assert 'Get-AbsoBackendArgs -CommandArgs @("reset-display", "--method", "driver-hotkey", "--json")' in script
    reset_section = script.split('$resetDisplayItem.Add_Click({', 1)[1].split(
        '$actionsMenu.DropDownItems.Add($resetDisplayItem)',
        1,
    )[0]
    assert "-PassThru" in reset_section
    assert "-RedirectStandardError $errFile" in reset_section
    assert "$completed = $proc.WaitForExit(30000)" in reset_section
    assert (
        'Show-Notification -Title "A.B.S.O." `\n'
        '                    -Message "Display reset timed out after 30s" -Type "Error" `\n'
        '                    -ActionName "Reset" -ActionColor $script:Colors.AccentAmber'
    ) in reset_section
    assert '"Reset timed out after 30s"' not in reset_section
    assert 'Set-TrayLastAction -Message "Display reset timed out after 30s"' in reset_section
    assert "$exitCodeOk -and" in reset_section
    assert "-Wait" not in reset_section


def test_tray_startup_fallback_reports_scheduled_task_state() -> None:
    """Startup menu fallback should not ignore the Task Scheduler registration."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Get-StartupStatusFallback" in script
    assert '$taskName = "ABSO-Tray-Startup"' in script
    assert "Get-ScheduledTask -TaskName $taskName -ErrorAction SilentlyContinue" in script
    assert 'mode                     = $mode' in script
    assert 'task_action_path_current = $actionPathCurrent' in script
    assert '"Startup fallback scheduled-task probe failed: $($_.Exception.Message)"' in script
    assert "failed or task missing" not in script
    assert 'return (Get-StartupStatusFallback -InstallScript $installScript)' in script
    assert 'return (Get-StartupStatusFallback -InstallScript $installedScript)' in script


def test_tray_startup_menu_tooltip_reports_stale_task_action() -> None:
    """Auto-start menu text should not call a stale scheduled task cleanly configured."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    startup_menu_section = script.split("function Set-StartupMenuState", 1)[1].split(
        "function Toggle-Startup",
        1,
    )[0]
    assert '$taskActionCurrent = $true' in startup_menu_section
    assert '$StartupStatus.PSObject.Properties["task_action_path_current"]' in startup_menu_section
    assert '$startupActionIsStale = ($isInstalled -and $mode -eq "scheduled_task" -and -not $taskActionCurrent)' in startup_menu_section
    assert '$startupIconAction = if ($startupActionIsStale) { "Warning" } else { "Startup" }' in startup_menu_section
    assert '$startupIconColor = if ($startupActionIsStale) { $script:Colors.AccentAmber } else { $script:Colors.Text }' in startup_menu_section
    assert '$script:startupItem.ForeColor = if ($startupActionIsStale) { $script:Colors.AccentAmber } else { $script:Colors.Text }' in startup_menu_section
    assert "Set-MenuItemImageSafe -Item $script:startupItem -NewImage (New-ActionBitmap -Action $startupIconAction -Color $startupIconColor)" in startup_menu_section
    assert '$startupChipText = if ($startupActionIsStale) { "STALE" } else { "STARTUP" }' in startup_menu_section
    assert '"Auto-start task points at different tray files; toggle auto-start to rewrite it"' in startup_menu_section
    assert '"run startup repair or toggle auto-start"' not in startup_menu_section
    assert '"Start A.B.S.O. Tray when Windows starts (configured via $modeLabel)"' in startup_menu_section


def test_tray_startup_installer_calls_are_timeout_status_aware() -> None:
    """Startup helper calls should not block the tray without an accurate status."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "function Invoke-StartupInstallerJson" in script
    assert 'Start-Process -FilePath "powershell.exe" -ArgumentList $psArgs `' in script
    assert "$completed = $proc.WaitForExit($timeoutMs)" in script
    assert 'throw "$Source timed out after ${TimeoutSeconds}s"' in script
    assert 'Invoke-StartupInstallerJson -ScriptPath $installScript -CommandArgs @("-Status", "-Json") -TimeoutSeconds 15 -Source "StartupStatus"' in script
    assert 'Invoke-StartupInstallerJson -ScriptPath $installedScript -CommandArgs @("-Status", "-Json") -TimeoutSeconds 15 -Source "InstalledStartupStatus"' in script
    assert 'Invoke-StartupInstallerJson -ScriptPath $installedScript -CommandArgs @("-Install", "-Json") -TimeoutSeconds 120 -Source "StartupRepair"' in script
    assert 'Set-TrayOperationTooltipText -Text "A.B.S.O. - Updating startup..."' in script
    assert 'Set-TrayLastAction -Message "Startup update running"' in script
    assert 'Invoke-StartupInstallerJson -ScriptPath $installScript -CommandArgs @($operation, "-Json") -TimeoutSeconds 120 -Source "Startup update"' in script
    assert '$result.Payload.PSObject.Properties["success"]' in script
    assert 'throw $payloadError' in script
    assert '$installerWarning = "$($result.Payload.warning)"' in script
    assert '$startupType = if ([string]::IsNullOrWhiteSpace($installerWarning)) { "Info" } else { "Warning" }' in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message $startupMessage -Type $startupType '
        '-ActionName "Startup" -ActionColor $script:Colors.AccentBlue'
    ) in script
    assert (
        'Show-Notification -Title "A.B.S.O." -Message "Startup update failed: $($_.Exception.Message)" '
        '-Type "Error" -ActionName "Startup" -ActionColor $script:Colors.AccentAmber'
    ) in script
    assert '& powershell.exe @args' not in script


def test_startup_status_reports_actual_task_action_drift() -> None:
    """Startup status must expose the scheduled task action, not just intended paths."""
    script = INSTALL_SCRIPT.read_text(encoding="utf-8")
    assert "action_execute" in script
    assert "action_arguments" in script
    assert "action_path_current" in script
    assert "action_expected_launcher_path" in script
    assert "action_expected_vbs_path" in script
    assert "$taskInfo.action_path_current" in script


def test_start_process_exitcode_consumers_cache_process_handle() -> None:
    """PS 5.1 Start-Process -PassThru reads .ExitCode as $null unless the handle
    was cached before the child exited. That defect made Get-StartupStatus fall
    back on every tray start ("empty/bad JSON or exit code ") and would make
    Toggle-Startup throw on success. Every backend shell-out that consumes
    ExitCode must cache the handle right after spawn, and installer result
    checks must tolerate a null exit code when the payload parsed."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")

    # Sync shell-outs ($proc) plus the named async procs.
    assert script.count("if ($proc) { $null = $proc.Handle }") >= 8
    assert "$null = $script:ActiveProfileVerifyProc.Handle" in script
    assert "$null = $script:AuditProc.Handle" in script
    assert "$null = $script:LaunchSanitizerSweepProc.Handle" in script

    # Installer wrapper hardening: no $args automatic-variable shadowing, a
    # finalizing parameterless WaitForExit, and null-exit-tolerant checks.
    installer_section = script.split("function Invoke-StartupInstallerJson", 1)[1].split(
        "function Get-StartupStatus",
        1,
    )[0]
    assert "$psArgs = @(" in installer_section
    assert "-ArgumentList $psArgs" in installer_section
    assert "$proc.WaitForExit()" in installer_section
    assert (
        '($result.ExitCode -eq 0 -or $null -eq $result.ExitCode) -and $result.Payload'
    ) in script
    assert "if ($null -ne $result.ExitCode -and $result.ExitCode -ne 0) {" in script
    assert "if ($result.ExitCode -eq 0 -and $result.Payload) {" not in script


def test_background_catalog_refresh_logs_honest_write_state() -> None:
    """The deferred catalog refresh must not claim a cache write it skipped.

    Write-ProfileCatalogCache returns $true only when it actually wrote the
    file; the background refresh log line distinguishes "wrote cache" from
    "verified cache current" so the tray log cannot contradict the
    "cache unchanged; skipping write" line emitted moments earlier."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert "$wroteCache = [bool](Write-ProfileCatalogCache" in script
    assert "Background catalog refresh wrote cache" in script
    assert "Background catalog refresh verified cache current" in script
    assert "$null = Write-ProfileCatalogCache -Entries $entries -Aliases $aliasMap" in script

    cache_fn = script.split("function Write-ProfileCatalogCache", 1)[1].split(
        "function Resolve-ProfileAlias",
        1,
    )[0]
    assert "return $true" in cache_fn
    assert "return $false" in cache_fn


def test_clean_verification_surfaces_verified_status_on_fresh_session() -> None:
    """The first clean verification of a session must write a positive status.

    After an OS reboot the tray may start with an empty last-action line; if a
    user-triggered verification comes back clean it should affirmatively show
    "Verified active: <profile>" so the user knows the pre-reboot
    "Windows restart required" notice no longer applies."""
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    assert 'elseif ([string]::IsNullOrWhiteSpace($lastActionText)) {' in script
    assert "Active profile verifies clean on fresh session; surfacing verified status" in script
    # Both the stale-replacement and fresh-session branches write the same
    # affirmative status format.
    assert script.count('$script:LastAction = "Verified active: $activeName"') >= 2
