"""Execute isolated tray functions with mocked processes, never the live tray."""

from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

TRAY_SCRIPT = Path(__file__).resolve().parents[1] / "abso/tray/ABSO-Tray.ps1"
pytestmark = pytest.mark.skipif(sys.platform != "win32", reason="PowerShell 5.1 harness")


def _run_functions(tmp_path: Path, names: list[str], body: str) -> dict:
    selected = ", ".join("'" + name + "'" for name in names)
    script_path = str(TRAY_SCRIPT).replace("'", "''")
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


@pytest.mark.parametrize("outcome", ["success", "failure", "timeout", "shutdown"])
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
    Complete-BackgroundCatalogIfReady
    $second = $script:children[1]
    $second.HasExited = $true
    if ('OUTCOME' -eq 'failure') { $second.ExitCode = 9 }
    Complete-BackgroundCatalogIfReady
}
$remainingPaths = @($script:tempPaths | Where-Object { Test-Path -LiteralPath $_ })
@{
    coalesced = $coalesced; writes = $script:writes
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
    assert result["killed"] == (outcome in {"timeout", "shutdown"})
    if outcome == "success":
        assert result["entries"] == [{"id": "mock-profile"}]
        assert result["aliases"] == {"old-profile": "mock-profile"}


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


def test_session_features_work_for_game_without_process_killset(tmp_path: Path) -> None:
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
$script:Profiles = @{ 'mock-game' = @{ Exes = @('game.exe'); KillsetAlwaysSafe = @(); KillsetOptIn = @(); KeepAwakeWhileGaming = $true } }
$script:TrayConfig = @{ cpuBalancer = $true }
$script:LaunchSanitizerTimer = [pscustomobject]@{ Interval = 30000 }
$script:LaunchSanitizerActiveIntervalMs = 10000
Invoke-LaunchSanitizerTick
@{ awake = $script:awake; governorGame = $script:governorGame
   gameAlive = $script:LaunchSanitizerGameWasAlive; interval = $script:LaunchSanitizerTimer.Interval
} | ConvertTo-Json -Compress
""",
    )
    assert result == {"awake": True, "governorGame": 123, "gameAlive": True, "interval": 10000}


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
