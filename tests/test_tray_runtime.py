"""Execute isolated tray functions with mocked processes, never the live tray."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TRAY_SCRIPT = Path(__file__).resolve().parents[1] / "abso/tray/ABSO-Tray.ps1"
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 5.1 harness")


def _run_functions(
    tmp_path: Path, names: list[str], body: str, *, module: Path = TRAY_SCRIPT,
) -> dict:
    selected = ", ".join("'" + name + "'" for name in names)
    script_path = str(module).replace("'", "''")
    startup_path = str(TRAY_SCRIPT.with_name("ABSO-StartupState.ps1")).replace("'", "''")
    harness = tmp_path / "tray-functions.ps1"
    harness.write_text(
        f"""
$ErrorActionPreference = 'Stop'
Add-Type -AssemblyName System.Windows.Forms
. '{startup_path}'
$tokens = $null; $errors = $null
$ast = [System.Management.Automation.Language.Parser]::ParseFile('{script_path}', [ref]$tokens, [ref]$errors)
if ($errors.Count) {{ throw ($errors | Out-String) }}
$selected = @({selected})
$definitions = $ast.FindAll({{ param($node)
    $node -is [System.Management.Automation.Language.FunctionDefinitionAst] -and $node.Name -in $selected
}}, $true)
if ($definitions.Count -ne $selected.Count) {{ throw 'Missing harness functions' }}
foreach ($definition in $definitions) {{ Invoke-Expression $definition.Extent.Text }}
function Write-TrayLog {{ param($Message, $Level) }}
{body}
""",
        encoding="utf-8-sig",
    )
    result = subprocess.run(
        ["powershell.exe", "-NoProfile", "-ExecutionPolicy", "Bypass", "-File", str(harness)],
        capture_output=True,
        text=True,
        check=True,
        timeout=20,
    )
    return json.loads(result.stdout)


def test_process_guard_never_boosts_idle_or_below_normal(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Get-TrayProcessPriorityRank", "Invoke-ProcessGuardTick"],
        """
$script:ProcessGuardNames = @('MockDiscord')
$script:ProcessGuardCeiling = [System.Diagnostics.ProcessPriorityClass]::Normal
$script:ProcessGuardDemotedPIDs = @{}
$script:ProcessGuardTimer = $null
$script:ProcessGuardIdleIntervalMs = 30000
$script:ProcessGuardActiveIntervalMs = 5000
$script:procs = @()
$processId = 100
foreach ($name in @('Idle', 'BelowNormal', 'Normal', 'AboveNormal', 'High', 'RealTime')) {
    $script:procs += [pscustomobject]@{
        Id = $processId++; ProcessName = $name
        PriorityClass = [System.Diagnostics.ProcessPriorityClass]::$name
    }
}
function Get-Process { param($Name, $ErrorAction) return $script:procs }
Invoke-ProcessGuardTick
$states = @{}
foreach ($proc in $script:procs) { $states[$proc.ProcessName] = $proc.PriorityClass.ToString() }
$states | ConvertTo-Json -Compress
""",
    )
    assert result == {
        "Idle": "Idle",
        "BelowNormal": "BelowNormal",
        "Normal": "Normal",
        "AboveNormal": "Normal",
        "High": "Normal",
        "RealTime": "Normal",
    }


@pytest.mark.parametrize("outcome", ["success", "failure", "invalid", "timeout", "shutdown"])
def test_catalog_refresh_is_single_flight_and_cleans_up(tmp_path: Path, outcome: str) -> None:
    result = _run_functions(
        tmp_path,
        [
            "Stop-BackgroundCatalogProcess",
            "Stop-BackgroundCatalogRefresh",
            "Start-BackgroundCatalogStage",
            "Complete-BackgroundCatalogIfReady",
            "Start-BackgroundCatalogRefresh",
        ],
        """
Add-Type @'
public class FakeCatalogProcess {
    public bool HasExited = false;
    public int ExitCode = 0;
    public int Handle = 42;
    public bool Disposed = false;
    public bool Killed = false;
    public void Kill() { Killed = true; HasExited = true; }
    public void Dispose() { Disposed = true; }
}
'@
$script:PythonExe = 'not-a-real-backend'
$script:ProjectRoot = $PSScriptRoot
$script:ProfileCatalogCacheFile = Join-Path $PSScriptRoot 'mock-cache.json'
$script:children = @()
$script:tempPaths = @()
$script:writes = 0
$script:adoptions = 0
$script:entries = $null
$script:aliases = $null
function Get-AbsoBackendArgs { param($CommandArgs) return $CommandArgs }
function Start-Process {
    param($FilePath, $ArgumentList, [switch]$NoNewWindow, [switch]$PassThru,
          $WorkingDirectory, $RedirectStandardOutput, $RedirectStandardError)
    if ($FilePath -ne 'not-a-real-backend') { throw 'Unexpected process request' }
    $child = New-Object FakeCatalogProcess
    $script:children += $child
    $script:tempPaths += $RedirectStandardOutput, $RedirectStandardError
    $payload = if ($ArgumentList[0] -eq 'profiles') {
        '{"success":true,"data":[{"id":"mock-profile"}]}'
    } else { '{"success":true,"data":{"old-profile":"mock-profile"}}' }
    [System.IO.File]::WriteAllText($RedirectStandardOutput, $payload)
    [System.IO.File]::WriteAllText($RedirectStandardError, '')
    return $child
}
function Write-ProfileCatalogCache {
    param($Entries, $Aliases, [switch]$ThrowOnFailure)
    $script:writes++
    $script:entries = $Entries
    $script:aliases = $Aliases
    return $true
}
function Set-RefreshedTrayCatalog { param($Entries, $Aliases) $script:adoptions++; return $false }
Start-BackgroundCatalogRefresh
Complete-BackgroundCatalogIfReady
$first = $script:children[0]
$timer = $script:BackgroundCatalogTimer
Start-BackgroundCatalogRefresh
Complete-BackgroundCatalogIfReady
$coalesced = $script:children.Count -eq 1 -and [object]::ReferenceEquals($timer, $script:BackgroundCatalogTimer)
if ('OUTCOME' -eq 'timeout') {
    $script:BackgroundCatalogStartedAt = [DateTime]::UtcNow.AddSeconds(-20)
    Complete-BackgroundCatalogIfReady
} elseif ('OUTCOME' -eq 'shutdown') {
    Stop-BackgroundCatalogRefresh
} else {
    $first.HasExited = $true
    if ('OUTCOME' -eq 'invalid') {
        [System.IO.File]::WriteAllText($script:BackgroundCatalogOutputFile, '{"success":true,"data":[{"id":""}]}')
    }
    Complete-BackgroundCatalogIfReady
    if ('OUTCOME' -ne 'invalid') {
        $second = $script:children[1]
        $second.HasExited = $true
        if ('OUTCOME' -eq 'failure') { $second.ExitCode = 9 }
        Complete-BackgroundCatalogIfReady
    }
}
$remainingPaths = @($script:tempPaths | Where-Object { Test-Path -LiteralPath $_ })
@{
    coalesced = $coalesced; writes = $script:writes
    adoptions = $script:adoptions
    entries = @($script:entries); aliases = $script:aliases
    cleaned = $null -eq $script:BackgroundCatalogProc -and $null -eq $script:BackgroundCatalogTimer
    disposed = @($script:children | Where-Object { -not $_.Disposed }).Count -eq 0
    killed = $first.Killed; remainingPaths = $remainingPaths.Count
} | ConvertTo-Json -Depth 5 -Compress
""".replace("OUTCOME", outcome),
    )
    assert result["coalesced"]
    assert result["cleaned"]
    assert result["disposed"]
    assert result["remainingPaths"] == 0
    assert result["writes"] == (1 if outcome == "success" else 0)
    assert result["adoptions"] == (1 if outcome == "success" else 0)
    assert result["killed"] == (outcome in {"timeout", "shutdown"})
    if outcome == "success":
        assert result["entries"] == [{"id": "mock-profile"}]
        assert result["aliases"] == {"old-profile": "mock-profile"}


@pytest.mark.parametrize("change", ["unchanged", "guidance", "policy", "removed"])
def test_fresh_catalog_replaces_loaded_metadata_without_applying(tmp_path: Path, change: str) -> None:
    result = _run_functions(
        tmp_path,
        ["Set-RefreshedTrayCatalog", "Get-TrayCatalogSessionPolicy", "Convert-CatalogEntriesToProfileMap"],
        """
function Format-TrayDisplayCopy { param($Text) return $Text }
function Normalize-TrayCategory { param($Category) return $Category }
function Stop-LaunchSweepRuntime { param([switch]$KillProcess) $script:sweepsStopped++ }
function Stop-CpuBalancerForGame { $script:governorsStopped++ }
function Clear-AbsoKeepAwake {}
function Reset-ActiveProfileVerificationState { $script:verificationResets++ }
function Update-MenuState { $script:menuUpdates++ }
function Update-TrayQuickPanelVerificationState { $script:panelUpdates++ }
function Apply-Profile { throw 'Refreshing metadata must not apply a profile' }
$entry = '{"id":"ow2","display_name":"OW2","tray_subtitle":"Old guidance","tray_description":"Old guidance","tray_category":"Shooters","tray_group":"ow2","tray_group_name":"Overwatch","executables":["Overwatch.exe"],"cpu_partition_policy":"full","launch_process_killset":{"always_safe":["OldOverlay.exe"]},"settings":{"ow2_config":{"vsync":false}}}' | ConvertFrom-Json
$script:FallbackProfiles = @{}
$script:Profiles = Convert-CatalogEntriesToProfileMap -Entries @($entry) -FallbackProfiles @{}
$script:activeProfile = 'ow2'
$script:ProfileAliases = @{ old = 'wrong-profile' }
$script:profileMenuItems = @([pscustomobject]@{ Tag = 'ow2'; Enabled = $true })
$script:notifyIcon = [pscustomobject]@{ ContextMenuStrip = $true }
$script:QuickPanelVisible = $true
$script:sweepsStopped = 0; $script:governorsStopped = 0; $script:verificationResets = 0
$script:menuUpdates = 0; $script:panelUpdates = 0
if ('CHANGE' -eq 'guidance') { $entry.tray_subtitle = 'In-game VSync ON' }
if ('CHANGE' -eq 'policy') { $entry.launch_process_killset.always_safe = @(); $entry.cpu_partition_policy = 'off' }
if ('CHANGE' -eq 'removed') { $entry.id = 'new-profile' }
$script:MutatingOperationInProgress = $true
$blocked = $false
try { Set-RefreshedTrayCatalog -Entries @($entry) -Aliases @{ old = 'ow2' } } catch { $blocked = $true }
$unchangedWhileBusy = $script:ProfileAliases.old -eq 'wrong-profile' -and $script:menuUpdates -eq 0
$script:MutatingOperationInProgress = $false
$menuChanged = Set-RefreshedTrayCatalog -Entries @($entry) -Aliases @{ old = 'ow2' }
$loaded = $script:Profiles[$entry.id]
@{ blocked = $blocked; unchangedWhileBusy = $unchangedWhileBusy; source = $script:ProfileCatalogLastSource
   active = $script:activeProfile; alias = $script:ProfileAliases.old; subtitle = $loaded.Sub
   policy = $loaded.CpuPartitionPolicy; killsetCount = $loaded.KillsetAlwaysSafe.Count
   containsSettingValues = $loaded.ContainsKey('settings'); menuChanged = $menuChanged
   rowEnabled = $script:profileMenuItems[0].Enabled; resets = $script:verificationResets
   sweepsStopped = $script:sweepsStopped; governorsStopped = $script:governorsStopped
   menuUpdates = $script:menuUpdates; panelUpdates = $script:panelUpdates } | ConvertTo-Json -Compress
""".replace("CHANGE", change),
    )
    assert result["blocked"] and result["unchangedWhileBusy"]
    assert result["source"] == "backend"
    assert result["active"] == "ow2"
    assert result["alias"] == "ow2"
    assert not result["containsSettingValues"]
    assert result["menuChanged"] is (change == "removed")
    assert result["rowEnabled"] is (change != "removed")
    assert result["resets"] == (0 if change == "unchanged" else 1)
    assert result["panelUpdates"] == (0 if change == "unchanged" else 1)
    assert result["menuUpdates"] == 1
    assert result["sweepsStopped"] == result["governorsStopped"] == (1 if change in {"policy", "removed"} else 0)
    if change == "guidance":
        assert result["subtitle"] == "In-game VSync ON"
    if change == "policy":
        assert result["policy"] == "off"
        assert result["killsetCount"] == 0


def test_manual_catalog_refresh_waits_for_backend_success(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Request-TrayCatalogRefresh", "Complete-BackgroundCatalogIfReady"],
        """
function Test-TrayMutationInProgress { param($RequestedAction) return $false }
function Start-BackgroundCatalogRefresh { $script:BackgroundCatalogTimer = $true }
function Stop-BackgroundCatalogRefresh { $script:BackgroundCatalogTimer = $null; $script:BackgroundCatalogProc = $null }
function Set-TrayLastAction { param($Message) $script:LastAction = $Message }
function Show-Notification { param($Title, $Message, $Type, $ActionName, $ActionColor) $script:notices += @{ type = $Type; message = $Message } }
function Update-MenuState {}
function Write-ProfileCatalogCache { param($Entries,$Aliases,[switch]$ThrowOnFailure) return $false }
function Set-RefreshedTrayCatalog { param($Entries,$Aliases) $script:adopted = $true; return $true }
$script:PythonExe = 'mock'; $script:notices = @(); $script:adopted = $false
Request-TrayCatalogRefresh
$earlyNotices = $script:notices.Count
$requestAction = $script:LastAction
$script:BackgroundCatalogStage = 'profile-aliases'
$script:BackgroundCatalogProc = [pscustomobject]@{ HasExited = $true; ExitCode = 0 }
$script:BackgroundCatalogEntries = @(@{ id = 'ow2' })
$script:BackgroundCatalogOutputFile = Join-Path $PSScriptRoot 'aliases.json'
$script:BackgroundCatalogErrorFile = Join-Path $PSScriptRoot 'aliases.err'
Set-Content $script:BackgroundCatalogOutputFile '{"success":true,"data":{}}'
Set-Content $script:BackgroundCatalogErrorFile ''
$script:MutatingOperationInProgress = $true
Complete-BackgroundCatalogIfReady
$blocked = -not $script:adopted -and $script:notices.Count -eq 0
$script:MutatingOperationInProgress = $false
Complete-BackgroundCatalogIfReady
$successAction = $script:LastAction
Request-TrayCatalogRefresh
$script:BackgroundCatalogProc = [pscustomobject]@{ HasExited = $true; ExitCode = 9 }
Complete-BackgroundCatalogIfReady
@{ earlyNotices = $earlyNotices; requestAction = $requestAction; blocked = $blocked
   adopted = $script:adopted; successAction = $successAction; notices = $script:notices
   pending = $script:ProfileCatalogRefreshRequested } | ConvertTo-Json -Depth 4 -Compress
""",
    )
    assert result["earlyNotices"] == 0
    assert result["requestAction"] == "Profile refresh requested; checking backend"
    assert result["blocked"] and result["adopted"]
    assert "Profiles refreshed from backend" in result["successAction"]
    assert "Restart tray" in result["successAction"]
    assert [notice["type"] for notice in result["notices"]] == ["Success", "Error"]
    assert "exit code 9" in result["notices"][1]["message"]
    assert not result["pending"]


def test_hidden_menu_never_starts_animation_timer(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Stop-TrayMenuPulseTimer", "Start-TrayMenuPulseTimer"],
        """
$script:notifyIcon = [pscustomobject]@{
    ContextMenuStrip = [pscustomobject]@{ Visible = $false }
}
Start-TrayMenuPulseTimer
$hiddenStopped = $null -eq $script:TrayMenuPulseTimer
$script:notifyIcon.ContextMenuStrip.Visible = $true
Start-TrayMenuPulseTimer
$visibleRunning = $script:TrayMenuPulseTimer.Enabled
Stop-TrayMenuPulseTimer
@{ hiddenStopped = $hiddenStopped; visibleRunning = $visibleRunning
   closedStopped = $null -eq $script:TrayMenuPulseTimer } | ConvertTo-Json -Compress
""",
    )
    assert result == {"hiddenStopped": True, "visibleRunning": True, "closedStopped": True}


def test_catalog_replace_failure_preserves_previous_cache(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Write-ProfileCatalogCache"],
        """
$script:ProfileCatalogCacheFile = Join-Path $PSScriptRoot 'existing-cache.json'
[System.IO.File]::WriteAllText($script:ProfileCatalogCacheFile, 'previous bytes')
function Read-ProfileCatalogCacheEntries { return @() }
function Read-ProfileAliasMapFromCache { return @{} }
$cacheLock = [System.IO.File]::Open($script:ProfileCatalogCacheFile,
    [System.IO.FileMode]::Open, [System.IO.FileAccess]::Read, [System.IO.FileShare]::Read)
$threw = $false
try {
    $null = Write-ProfileCatalogCache -Entries @(@{ id = 'new' }) -Aliases @{} -ThrowOnFailure
} catch { $threw = $true }
finally { $cacheLock.Dispose() }
@{ threw = $threw; bytes = [System.IO.File]::ReadAllText($script:ProfileCatalogCacheFile)
   tempCount = @(Get-ChildItem -LiteralPath $PSScriptRoot -Filter '*.tmp').Count
} | ConvertTo-Json -Compress
""",
    )
    assert result == {"threw": True, "bytes": "previous bytes", "tempCount": 0}


def test_external_profile_changes_adopt_and_stop_old_session_policy(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Read-TrayBackendProfileState", "Sync-TrayBackendProfileState", "Invoke-LaunchSanitizerTick"],
        """
function Get-InstalledAppRoot { return $PSScriptRoot }
function Resolve-ProfileAlias { param($ProfileId) return $ProfileId }
function Get-TrayProfileDisplayName { param($ProfileId) return $ProfileId }
function Set-LastProfileState {
    param($Config, $Status, $ProfileId, $ProfileName, $Source, $Timestamp)
    $Config.lastProfileState = @{ status = $Status; id = $ProfileId }
    return $Config
}
function Set-TrayLastAction { param($Message) $script:lastAction = $Message }
function Set-IconState { param($State) $script:iconState = $State }
function Update-MenuState { $script:updates++ }
function Stop-LaunchSweepRuntime { param([switch]$KillProcess) $script:stops++ }
function Stop-CpuBalancerForGame { $script:governorStops++ }
function Clear-AbsoKeepAwake { $script:awake = $false }
function Reset-ActiveProfileVerificationState { $script:verifierResets++ }
function Start-LaunchSweepCliProcess { throw 'Must not launch a sweep with unreadable backend state' }
$script:AbsoBackendArgsPrefix = @()
$script:activeProfile = 'overlay-free'
$script:TrayConfig = @{}
$script:QuickPanelVisible = $false
$script:stops = 0; $script:governorStops = 0; $script:updates = 0; $script:verifierResets = 0
$script:awake = $true
$statePath = Join-Path $PSScriptRoot '.abso_state.json'
[System.IO.File]::WriteAllText($statePath,
    '{"current_profile":"capture","applied_at":"2026-09-06T12:00:00","reboot_pending":false}')
$adopted = Sync-TrayBackendProfileState
$afterAdopt = $script:activeProfile
$savedId = $script:TrayConfig.lastProfileState.id
$oldSessionStopped = $script:stops -eq 1 -and $script:governorStops -eq 1 -and -not $script:awake
$resetsBefore = $script:verifierResets
$null = Sync-TrayBackendProfileState
$unchangedStable = $script:stops -eq 1 -and $script:verifierResets -eq $resetsBefore
[System.IO.File]::WriteAllText($statePath, 'malformed')
$invalid = Sync-TrayBackendProfileState
Invoke-LaunchSanitizerTick
$invalidPaused = $script:BackendProfileStateUnavailable -and $script:iconState -eq 'Warning'
Remove-Item -LiteralPath $statePath
$restored = Sync-TrayBackendProfileState
@{ adopted = $adopted; afterAdopt = $afterAdopt; savedId = $savedId
   oldSessionStopped = $oldSessionStopped; unchangedStable = $unchangedStable
   invalid = $invalid; invalidPaused = $invalidPaused; restored = $restored
   activeAfterRestore = $script:activeProfile; savedStatus = $script:TrayConfig.lastProfileState.status
} | ConvertTo-Json -Compress
""",
    )
    assert result == {
        "adopted": True,
        "afterAdopt": "capture",
        "savedId": "capture",
        "oldSessionStopped": True,
        "unchangedStable": True,
        "invalid": False,
        "invalidPaused": True,
        "restored": True,
        "activeAfterRestore": None,
        "savedStatus": "restored",
    }


@pytest.mark.parametrize("source_mode", [True, False])
def test_backend_state_paths_match_packaged_and_source_modes(tmp_path: Path, source_mode: bool) -> None:
    result = _run_functions(
        tmp_path,
        ["Read-TrayBackendProfileState"],
        """
function Get-InstalledAppRoot { return $PSScriptRoot }
$script:ProjectRoot = Join-Path $PSScriptRoot 'repo'
New-Item -ItemType Directory -Path $script:ProjectRoot | Out-Null
$script:AbsoBackendArgsPrefix = if (SOURCE_MODE) { @('-m', 'abso') } else { @() }
[System.IO.File]::WriteAllText((Join-Path $PSScriptRoot '.abso_state.json'),
    '{"current_profile":"installed","applied_at":"2026-09-06T12:00:00"}')
[System.IO.File]::WriteAllText((Join-Path $script:ProjectRoot '.abso_state.json'),
    '{"current_profile":"source-newer","applied_at":"2026-09-06T13:00:00"}')
Read-TrayBackendProfileState | ConvertTo-Json -Compress
""".replace("SOURCE_MODE", "$true" if source_mode else "$false"),
    )
    assert result["current_profile"] == ("source-newer" if source_mode else "installed")


@pytest.mark.parametrize("partition_policy,restraint", [("off", True), ("full", False)])
def test_session_features_work_for_game_without_process_killset(
    tmp_path: Path, partition_policy: str, restraint: bool,
) -> None:
    result = _run_functions(
        tmp_path,
        ["Invoke-LaunchSanitizerTick"],
        """
function Sync-TrayBackendProfileState { return $true }
function Test-LaunchSweepInFlight { return $false }
function Test-IsActiveProfileGameRunning { return $true }
function Test-CpuBalancerRunning { return $false }
function Get-ActiveProfileGamePid { return 123 }
function Set-AbsoKeepAwake { $script:awake = $true }
function Start-CpuBalancerForGame { param($ProfileId, $GamePid) $script:governorGame = $GamePid; return $true }
function Start-LaunchSweepCliProcess { throw 'Empty killset must not launch a backend process' }
$script:activeProfile = 'mock-game'
$script:Profiles = @{ 'mock-game' = @{ Exes = @('game.exe'); KillsetAlwaysSafe = @(); KillsetOptIn = @(); KeepAwakeWhileGaming = $true; CpuPartitionPolicy = 'PARTITION_POLICY' } }
$script:TrayConfig = @{ cpuBalancer = RESTRAINT }
$script:LaunchSanitizerTimer = [pscustomobject]@{ Interval = 30000 }
$script:LaunchSanitizerActiveIntervalMs = 10000
Invoke-LaunchSanitizerTick
@{ awake = $script:awake; governorGame = $script:governorGame
   gameAlive = $script:LaunchSanitizerGameWasAlive; interval = $script:LaunchSanitizerTimer.Interval
} | ConvertTo-Json -Compress
""".replace("PARTITION_POLICY", partition_policy).replace("RESTRAINT", "$true" if restraint else "$false"),
    )
    assert result == {"awake": True, "governorGame": 123, "gameAlive": True, "interval": 10000}


def test_backend_adoption_pauses_during_mutating_transaction(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Sync-TrayBackendProfileState"],
        """
$script:MutatingOperationInProgress = $true
$script:activeProfile = 'prior-profile'
function Read-TrayBackendProfileState { throw 'Intermediate state must not be read' }
function Stop-LaunchSweepRuntime { throw 'Mutation guard must not alter session runtime' }
@{ paused = -not (Sync-TrayBackendProfileState); profile = $script:activeProfile } | ConvertTo-Json -Compress
""",
    )
    assert result == {"paused": True, "profile": "prior-profile"}


@pytest.mark.parametrize("malformed_output", [False, True])
def test_failed_apply_invalidates_old_verification_and_refreshes_without_retry(
    tmp_path: Path, malformed_output: bool,
) -> None:
    result = _run_functions(
        tmp_path,
        [
            "Apply-Profile", "Refresh-TrayStateAfterFailedApply",
            "Reset-ActiveProfileVerificationState", "Invoke-JsonSafe",
        ],
        r"""
$script:activeProfile = 'overwatch2-gsync-hdr-capture'
$script:ActiveProfileVerificationStatus = 'active'
$script:ActiveProfileVerificationCheckedAt = 'old-check'
$script:Profiles = @{ 'slippi-melee-universal-hdr' = @{ Name = 'Slippi' } }
$script:PythonExe = 'mock-backend'
$script:ProjectRoot = $PSScriptRoot
$script:Colors = @{}
$script:backendStarts = 0; $script:verifierStops = 0
function Test-TrayMutationInProgress { param($RequestedAction) return $false }
function Sync-TrayBackendProfileState {
    if ($script:MutatingOperationInProgress) { throw 'Must wait for backend exit' }
    # Simulate saved-state adoption trying to replace the failure feedback.
    $script:LastAction = 'Profile state loaded: Overwatch'
    return $true
}
function Resolve-ProfileAlias { param($ProfileId) return $ProfileId }
function Test-NeedsNoSyncOsdReminder { param($FromProfileId, $ToProfileId) return $false }
function Get-TrayProfileObjectDisplayName { param($Profile, $Fallback) return 'Slippi' }
function Stop-ActiveProfileVerificationRuntime { param([switch]$KillProcess) $script:verifierStops++ }
function Set-IconState { param($State) }
function Set-TrayOperationTooltipText { param($Text) }
function Get-TrayProfileToastVisualArgs { param($ProfileId, $Profile) return @{} }
function Show-ProgressOverlay { param($Title, $StepText) }
function Update-ProgressOverlay { param($StepText) }
function Get-AbsoBackendArgs { param($CommandArgs) return $CommandArgs }
function Start-Process {
    param($FilePath, $ArgumentList, [switch]$NoNewWindow, [switch]$PassThru,
          $WorkingDirectory, $RedirectStandardOutput, $RedirectStandardError)
    $script:backendStarts++
    $script:cacheAtLaunch = $script:ActiveProfileVerificationStatus
    if ('MALFORMED' -eq 'yes') {
        Set-Content -LiteralPath $RedirectStandardOutput -Value 'not-json'
    } else {
        Set-Content -LiteralPath $RedirectStandardOutput -Value '{"success":false,"data":{"success":false,"error":"Baseline restore incomplete; recovery incomplete. Verify previous profile.","transaction":{"rollback_attempted":true,"rollback_performed":false}}}'
    }
    $mock = [pscustomobject]@{ HasExited = $true; Handle = 1; ExitCode = 1 }
    $mock | Add-Member ScriptMethod WaitForExit { $script:waited = $true }
    $mock | Add-Member ScriptMethod Dispose { $script:disposed = $true }
    return $mock
}
function Get-ApplyFailureMessage { param($Json, $FailedHandlers, $ExitCode) return "Not applied. $($Json.data.error)" }
function Close-ProgressOverlay {}
function Test-IsVrrPrerequisiteError { param($Message) return $false }
function Play-FailSound {}
function Get-ApplyFailureActionButtons { param($Message, $Json) return @() }
function Show-Notification {
    param($Title, $Message, $Type, $MetaText, $ActionButtons)
    $script:toast = $Message; $script:toastTarget = $MetaText
}
function Update-MenuState {}
function Complete-TrayMutatingChildProcess {
    param($Process, $OperationName)
    if (-not $script:MutatingOperationInProgress) { throw 'Guard released early' }
    return $true
}
function Start-ActiveProfileVerificationProcess {
    param([switch]$Silent, [switch]$PreserveLastAction)
    if ($script:MutatingOperationInProgress) { throw 'Verification overlapped mutation' }
    $script:verifiedProfile = $script:activeProfile
    $script:preserveFailure = [bool]$PreserveLastAction
}
Apply-Profile -ProfileId 'slippi-melee-universal-hdr'
@{
    status = $script:ActiveProfileVerificationStatus
    checkedAt = $script:ActiveProfileVerificationCheckedAt
    cacheAtLaunch = $script:cacheAtLaunch
    lastAction = $script:LastAction; toast = $script:toast; target = $script:toastTarget
    verifiedProfile = $script:verifiedProfile; preserveFailure = $script:preserveFailure
    backendStarts = $script:backendStarts; verifierStops = $script:verifierStops
    guard = $script:MutatingOperationInProgress; disposed = $script:disposed
} | ConvertTo-Json -Compress
""".replace("MALFORMED", "yes" if malformed_output else "no"),
    )
    assert result["status"] is None
    assert result["checkedAt"] is None
    assert result["cacheAtLaunch"] is None
    assert result["lastAction"] == result["toast"]
    assert result["target"] == "slippi-melee-universal-hdr"
    assert result["verifiedProfile"] == "overwatch2-gsync-hdr-capture"
    assert result["preserveFailure"] is True
    assert result["backendStarts"] == 1
    assert result["verifierStops"] == 2
    assert result["guard"] is False
    assert result["disposed"] is True
    assert ("malformed JSON" if malformed_output else "recovery incomplete") in result["toast"]


@pytest.mark.parametrize("status", ["active", "mismatch", "pending_apply", "pending_reboot"])
def test_post_failure_verifier_updates_status_without_replacing_failure(
    tmp_path: Path, status: str,
) -> None:
    result = _run_functions(
        tmp_path,
        ["Apply-ActiveProfileVerificationJson"],
        """
function Sync-TrayBackendProfileState { return $true }
$script:activeProfile = 'overwatch2-gsync-hdr-capture'
$script:LastAction = 'Not applied. Recovery incomplete: NVIDIA unavailable.'
$script:LastActionTime = 'failure-time'
$payload = '{"success":true,"data":{"reboot_pending":false,"verification":{"profile":"overwatch2-gsync-hdr-capture","status":"STATUS","mismatched_handlers":["AudioEngineHandler"],"checked_at":"new-check"}}}' | ConvertFrom-Json
Apply-ActiveProfileVerificationJson -Json $payload -Silent -PreserveLastAction
@{ status = $script:ActiveProfileVerificationStatus; action = $script:LastAction
   actionTime = $script:LastActionTime; checkedAt = $script:ActiveProfileVerificationCheckedAt
   mismatches = $script:ActiveProfileMismatchedHandlers } | ConvertTo-Json -Compress
""".replace("STATUS", status),
    )
    assert result == {
        "status": status,
        "action": "Not applied. Recovery incomplete: NVIDIA unavailable.",
        "actionTime": "failure-time",
        "checkedAt": "new-check",
        "mismatches": ["AudioEngineHandler"],
    }


@pytest.mark.parametrize("backend_state", ["unavailable", "no_active_profile"])
def test_failed_apply_refresh_stays_unverified_when_backend_state_is_unavailable(
    tmp_path: Path, backend_state: str,
) -> None:
    result = _run_functions(
        tmp_path,
        ["Refresh-TrayStateAfterFailedApply", "Reset-ActiveProfileVerificationState"],
        """
$script:activeProfile = 'previous-profile'
$script:ActiveProfileVerificationStatus = 'active'
$script:LastAction = 'Not applied. Restore failed.'
$script:LastActionTime = 'failure-time'
function Stop-ActiveProfileVerificationRuntime { param([switch]$KillProcess) }
function Sync-TrayBackendProfileState {
    if ('BACKEND_STATE' -eq 'unavailable') { return $false }
    $script:activeProfile = $null
    $script:LastAction = 'Backend reports no active profile'
    return $true
}
function Start-ActiveProfileVerificationProcess { throw 'No usable active profile to verify' }
function Update-MenuState {}
Refresh-TrayStateAfterFailedApply
@{ status = $script:ActiveProfileVerificationStatus; action = $script:LastAction
   actionTime = $script:LastActionTime; profile = $script:activeProfile } | ConvertTo-Json -Compress
""".replace("BACKEND_STATE", backend_state),
    )
    assert result == {
        "status": None,
        "action": "Not applied. Restore failed.",
        "actionTime": "failure-time",
        "profile": "previous-profile" if backend_state == "unavailable" else None,
    }


def test_menu_animation_hooks_and_catalog_poll_have_no_waits() -> None:
    script = TRAY_SCRIPT.read_text(encoding="utf-8")
    menu_setup = script.split("$menu = New-Object System.Windows.Forms.ContextMenuStrip", 1)[1]
    opened = menu_setup.split("$menu.Add_Opened({", 1)[1].split("})", 1)[0]
    assert "Start-TrayMenuPulseTimer" in opened
    assert "$menu.Add_Closed({ Stop-TrayMenuPulseTimer })" in menu_setup
    ready = menu_setup.split("$script:notifyIcon.ContextMenuStrip = $menu", 1)[1]
    assert "Start-TrayMenuPulseTimer" not in ready
    catalog_poll = script.split("function Start-BackgroundCatalogStage", 1)[1].split(
        "function Initialize-ProfilesFromCliCatalog", 1
    )[0]
    assert "WaitForExit" not in catalog_poll
    assert "Start-Sleep" not in catalog_poll
    assert "Invoke-CliCatalogRefresh" not in catalog_poll


@pytest.mark.parametrize("satisfied,current_label", [(True, "Enabled + Boost"), (False, "Disabled"), (None, "unknown")])
def test_manual_settings_verification_lifecycle(
    tmp_path: Path, satisfied: bool | None, current_label: str,
) -> None:
    step = {
        "key": "reflex_mode", "label": "NVIDIA Reflex (in-game)",
        "current_label": current_label, "expected_label": "Enabled + Boost", "satisfied": satisfied,
    }
    result = _run_functions(
        tmp_path,
        ["Reset-ActiveProfileVerificationState", "Apply-ActiveProfileVerificationJson",
         "Get-ActiveProfileManualStepText", "Set-ActiveProfileVerificationSeedFromApplyData",
         "Set-ActiveProfileVerificationUnavailableAction"],
        """
function Sync-TrayBackendProfileState { return $true }
function Normalize-TrayLastActionMessage { param($Message) return $Message }
function Get-TrayProfileDisplayName { param($ProfileId) return 'Overwatch 2' }
function Set-TrayLastAction { param($Message) $script:LastAction = $Message }
$script:activeProfile = 'overwatch2-gsync-hdr-capture'
$script:LastAction = ''
$step = 'STEP_JSON' | ConvertFrom-Json
$payload = [pscustomobject]@{ success = $true; data = [pscustomobject]@{
    reboot_pending = $false; verification = [pscustomobject]@{
        profile = $script:activeProfile; status = 'active'; manual_steps = @($step)
        checked_at = (Get-Date).ToString('o')
    }
} }
Apply-ActiveProfileVerificationJson -Json $payload -Silent
$first = @{ text = Get-ActiveProfileManualStepText; status = $script:ActiveProfileVerificationStatus; action = $script:LastAction }
$payload.data.verification.manual_steps = @()
Apply-ActiveProfileVerificationJson -Json $payload -Silent
$cleared = Get-ActiveProfileManualStepText
$clearedAction = $script:LastAction
Set-ActiveProfileVerificationSeedFromApplyData -Data ([pscustomobject]@{ manual_steps = @($step) })
$seeded = Get-ActiveProfileManualStepText
$script:LastAction = 'Check in-game settings: Old profile instruction'
$payload.data.verification.profile = 'slippi-melee-universal-hdr'
$payload.data.verification.manual_steps = @($step)
Apply-ActiveProfileVerificationJson -Json $payload -Silent
$crossProfileCleared = $script:ActiveProfileManualSteps.Count -eq 0 -and $null -eq $script:ActiveProfileVerificationStatus
@{ first = $first; cleared = $cleared; clearedAction = $clearedAction; seeded = $seeded; crossProfileCleared = $crossProfileCleared; crossProfileAction = $script:LastAction } | ConvertTo-Json -Depth 5 -Compress
""".replace("STEP_JSON", json.dumps(step)),
    )
    assert result["first"]["status"] == "active"
    if satisfied:
        assert result["first"]["text"] is None
        assert result["seeded"] is None
    else:
        text = result["first"]["text"]
        assert ("not confirmed" if satisfied is None else "Disabled") in text
        assert "expected Enabled + Boost" in text
        assert result["first"]["action"].startswith("Check in-game settings:")
        assert result["seeded"] == text
    assert result["cleared"] is None
    assert result["clearedAction"] == "Verified active: Overwatch 2"
    assert result["crossProfileCleared"] is True
    assert result["crossProfileAction"] == "Verification not current: profile changed"


@pytest.mark.parametrize("stale", [False, True])
def test_manual_only_active_selection_never_requests_apply(tmp_path: Path, stale: bool) -> None:
    result = _run_functions(
        tmp_path,
        ["Complete-SameActiveProfileSelectionIfHandled", "Get-ActiveProfileManualStepText",
         "Get-ActiveProfilePendingApplyText", "Test-ActiveProfileVerificationStale"],
        """
$script:activeProfile = 'overwatch2-gsync-hdr-capture'
$script:ActiveProfileVerificationStatus = 'active'
$script:ActiveProfileVerificationCheckedAt = [DateTimeOffset]::UtcNow.AddSeconds(AGE).ToString('o')
$script:ActiveProfileManualSteps = @([pscustomobject]@{ key = 'reflex_mode'; label = 'NVIDIA Reflex'; current_label = 'Disabled'; expected_label = 'Enabled + Boost'; satisfied = $false })
function Get-TrayProfileToastVisualArgs { param($ProfileId, $Profile) return @{} }
function Get-TrayProfileObjectDisplayName { param($Profile, $Fallback) return 'Overwatch 2' }
function Get-ActiveProfileRebootPendingText { return $null }
function Apply-PendingProfileFixes { throw 'Manual setting must never trigger writes' }
function Refresh-ActiveProfileVerificationState { param([switch]$Silent) $script:refreshed = $true }
function Start-ActiveProfileVerificationTimer { param($DelayMilliseconds) $script:scheduled = $true }
function Show-Notification { param($Title, $Message, $Type, $MetaText) $script:notice = $Message }
function Set-IconState { param($State) }
function Update-MenuState {}
$handled = Complete-SameActiveProfileSelectionIfHandled -ProfileId $script:activeProfile -Profile @{}
@{ handled = $handled; notice = $script:notice; refreshed = [bool]$script:refreshed; scheduled = [bool]$script:scheduled } | ConvertTo-Json -Compress
""".replace("AGE", "-120" if stale else "0"),
    )
    assert result["handled"] is True  # Apply-Profile returns before reapply.
    assert result["refreshed"] is stale
    if stale:
        assert "Verifying current profile" in result["notice"]
    else:
        assert "Check in-game settings" in result["notice"]
        assert "Disabled; expected Enabled + Boost" in result["notice"]


def test_manual_guidance_distinguishes_game_settings_from_app_setup(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Get-ActiveProfileManualStepText"],
        """
$script:activeProfile = 'ow2'
$game = [pscustomobject]@{ key = 'reflex_mode'; label = 'Reflex'; current = 'Disabled'; expected = 'Enabled + Boost'; satisfied = $false; instruction = 'Open Options > Video > General > NVIDIA Reflex.' }
$binding = [pscustomobject]@{ key = 'applications'; label = 'NVIDIA app binding'; current = 'missing'; expected = 'Overwatch.exe'; satisfied = $true }
$script:ActiveProfileManualSteps = @($game, $binding)
$gameOnly = Get-ActiveProfileManualStepText
$binding.satisfied = 'true' # A non-boolean value must not hide a manual step.
$mixed = Get-ActiveProfileManualStepText
$game.satisfied = $true
$appOnly = Get-ActiveProfileManualStepText
@{ gameOnly = $gameOnly; mixed = $mixed; appOnly = $appOnly } | ConvertTo-Json -Compress
""",
    )
    assert result["gameOnly"].startswith("Check in-game settings:")
    assert "Open Options > Video > General > NVIDIA Reflex." in result["gameOnly"]
    assert "Disabled; expected Enabled + Boost" in result["gameOnly"]
    assert result["mixed"].startswith("Check manual settings:")
    assert "NVIDIA app binding: missing; expected Overwatch.exe" in result["mixed"]
    assert result["appOnly"] == "Check manual settings: NVIDIA app binding: missing; expected Overwatch.exe"


def test_menu_open_verification_is_stale_only_coalesced_and_throttled(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Request-ActiveProfileVerificationIfStale", "Test-ActiveProfileVerificationStale"],
        """
$script:activeProfile = 'ow2'
$script:starts = 0
function Test-ActiveProfileVerificationInFlight { return [bool]$script:inFlight }
function Start-ActiveProfileVerificationTimer { param($DelayMilliseconds) $script:starts++; $script:ActiveProfileVerifyTimer = $true }
$script:ActiveProfileVerificationCheckedAt = [DateTimeOffset]::UtcNow.ToString('o')
$fresh = Request-ActiveProfileVerificationIfStale
$script:ActiveProfileVerificationCheckedAt = [DateTimeOffset]::UtcNow.AddSeconds(-60).ToString('o')
$old = Request-ActiveProfileVerificationIfStale
$coalesced = Request-ActiveProfileVerificationIfStale
$script:ActiveProfileVerifyTimer = $null
$cooldown = Request-ActiveProfileVerificationIfStale
$script:ActiveProfileVerifyLastRequestedAt = [DateTimeOffset]::UtcNow.AddSeconds(-31)
$script:inFlight = $true
$running = Request-ActiveProfileVerificationIfStale
$script:inFlight = $false
$script:MutatingOperationInProgress = $true
$mutating = Request-ActiveProfileVerificationIfStale
$script:MutatingOperationInProgress = $false
$nextOpen = Request-ActiveProfileVerificationIfStale
@{ fresh = $fresh; old = $old; coalesced = $coalesced; cooldown = $cooldown; running = $running; mutating = $mutating; nextOpen = $nextOpen; starts = $script:starts } | ConvertTo-Json -Compress
""",
    )
    assert result == {
        "fresh": False, "old": True, "coalesced": False, "cooldown": False,
        "running": False, "mutating": False, "nextOpen": True, "starts": 2,
    }


def test_quick_panel_verification_refresh_only_renders_changed_visible_state(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Update-TrayQuickPanelVerificationState"],
        """
$script:activeProfile = 'ow2'; $script:TrayConfig = @{}; $script:updates = 0
$script:manual = 'Reflex: Disabled; expected Enabled + Boost'
function Get-ActiveProfilePendingApplyText { return $null }
function Get-ActiveProfileRebootPendingText { return $null }
function Get-ActiveProfileVerificationInProgressText { return $null }
function Get-ActiveProfileManualStepText { return $script:manual }
function Get-QuickPanelEmptyStatus { return @{ Message = ''; ProfileId = '' } }
function Update-QuickPanel { param($Favorites, $Profiles, $ActiveProfile, $ActivePendingApplyText, $ActiveWindowsRestartText, $ActiveVerificationText, $ActiveManualStepText, $EmptyMessage, $EmptyProfileId, $OnApply) $script:updates++; $script:lastManual = $ActiveManualStepText }
function Start-ActiveProfileVerificationProcess { throw 'Rendering must not launch verification' }
Update-TrayQuickPanelVerificationState
$hiddenUpdates = $script:updates
$script:QuickPanelVisible = $true
Update-TrayQuickPanelVerificationState
Update-TrayQuickPanelVerificationState
$unchangedUpdates = $script:updates
$script:manual = $null
Update-TrayQuickPanelVerificationState
# An explicit panel reopen displayed CHECK. The next identical clean result
# must repaint even though it matches the previous verifier completion.
$script:QuickPanelVerificationRenderKey = @('ow2', '', '', 'Checking profile state', '') | ConvertTo-Json -Compress
Update-TrayQuickPanelVerificationState
@{ hiddenUpdates = $hiddenUpdates; unchangedUpdates = $unchangedUpdates; total = $script:updates; lastManual = $script:lastManual } | ConvertTo-Json -Compress
""",
    )
    assert result == {"hiddenUpdates": 0, "unchangedUpdates": 1, "total": 3, "lastManual": None}


def test_quick_panel_manual_guidance_is_distinct_from_automatic_fix(tmp_path: Path) -> None:
    result = _run_functions(
        tmp_path,
        ["Get-QuickPanelCardChipText", "Get-QuickPanelCardTooltipText"],
        """
function Format-QuickPanelDisplayCopy { param($Text) return $Text }
function Format-QuickPanelUserFacingText { param($Text) return $Text }
$text = Get-QuickPanelCardTooltipText -Kind active -ProfileId ow2 -ActiveManualStepText 'Check in-game settings: Reflex: not confirmed; expected Enabled + Boost'
@{ chip = Get-QuickPanelCardChipText -Kind active -ManualSteps $true; tooltip = $text } | ConvertTo-Json -Compress
""",
        module=TRAY_SCRIPT.with_name("ABSO-QuickPanel.ps1"),
    )
    assert result["chip"] == "MANUAL"
    assert "Check in-game settings: Reflex: not confirmed" in result["tooltip"]
    assert "without changing manual settings" in result["tooltip"]
    assert "Click applies pending profile fixes" not in result["tooltip"]
