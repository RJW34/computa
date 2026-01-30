# ABSO-Watcher.ps1 - Ultra-lightweight game process monitor
# Memory: ~12-15MB | CPU: Near-zero (optimized polling)
#
# Monitors for game process start/stop:
# - When game starts: kills tray to free resources
# - When game exits: restarts tray, then self-terminates

param(
    [Parameter(Mandatory=$true)]
    [string]$ExeList,

    [Parameter(Mandatory=$true)]
    [int]$TrayPID,

    [Parameter(Mandatory=$true)]
    [string]$TrayScript
)

# Parse executable list into HashSet for O(1) lookups
$executables = $ExeList -split ','
$processNameSet = [System.Collections.Generic.HashSet[string]]::new(
    [System.StringComparer]::OrdinalIgnoreCase
)
foreach ($exe in $executables) {
    $name = [System.IO.Path]::GetFileNameWithoutExtension($exe)
    [void]$processNameSet.Add($name)
}

$gameRunning = $false
$trayKilled = $false
$checkCounter = 0
$maxWaitIterations = 360  # 30 minutes at 5s intervals before giving up
$waitIterations = 0

# Check if any game process is running (optimized)
function Test-GameRunning {
    # Get all processes once, then filter - more efficient than multiple Get-Process calls
    $procs = $null
    try {
        $procs = [System.Diagnostics.Process]::GetProcesses()
        foreach ($p in $procs) {
            try {
                if ($processNameSet.Contains($p.ProcessName)) {
                    return $true
                }
            } catch {
                # Process may have exited - ignore
            } finally {
                $p.Dispose()
            }
        }
    } catch {
        # Fallback if GetProcesses fails
    } finally {
        # Dispose any remaining process objects if early return didn't happen
        if ($procs) {
            foreach ($p in $procs) {
                try { $p.Dispose() } catch {}
            }
        }
    }
    return $false
}

# Check if tray is still alive (cached process handle)
$script:trayProcess = $null
function Test-TrayAlive {
    try {
        if ($null -eq $script:trayProcess) {
            $script:trayProcess = [System.Diagnostics.Process]::GetProcessById($TrayPID)
        }
        return -not $script:trayProcess.HasExited
    } catch {
        return $false
    }
}

# Main monitoring loop
while ($true) {
    $gameNowRunning = Test-GameRunning

    if ($gameNowRunning -and -not $gameRunning) {
        # Game just started - kill tray to free resources
        $gameRunning = $true
        $trayKilled = $true

        try {
            # Signal tray to shut down gracefully via named event
            $shutdownEvent = $null
            try {
                $shutdownEvent = [System.Threading.EventWaitHandle]::OpenExisting("Global\ABSO_Tray_Shutdown")
                $shutdownEvent.Set()
                # Wait up to 3 seconds for graceful exit
                $trayExited = $false
                for ($i = 0; $i -lt 6; $i++) {
                    Start-Sleep -Milliseconds 500
                    if (-not (Test-TrayAlive)) { $trayExited = $true; break }
                }
                if (-not $trayExited) {
                    Stop-Process -Id $TrayPID -Force -ErrorAction SilentlyContinue
                }
            } catch {
                # Named event doesn't exist yet or tray already gone - force kill
                Stop-Process -Id $TrayPID -Force -ErrorAction SilentlyContinue
            } finally {
                if ($shutdownEvent) { $shutdownEvent.Dispose() }
            }
        } catch {}
    }
    elseif (-not $gameNowRunning -and $gameRunning) {
        # Game just exited - restart tray and exit watcher
        $gameRunning = $false

        # Small delay to ensure mutex is released from killed tray
        Start-Sleep -Milliseconds 300

        # Start tray (single-instance check in tray will prevent duplicates)
        $vbsLauncher = Join-Path (Split-Path $TrayScript) "ABSO-Tray.vbs"
        if (Test-Path $vbsLauncher) {
            Start-Process "wscript.exe" -ArgumentList "`"$vbsLauncher`"" -WindowStyle Hidden
        } else {
            Start-Process "powershell.exe" -ArgumentList @(
                "-NoProfile", "-WindowStyle", "Hidden", "-ExecutionPolicy", "Bypass",
                "-File", "`"$TrayScript`""
            ) -WindowStyle Hidden
        }

        # Clean exit
        exit 0
    }
    elseif (-not $gameRunning -and -not $trayKilled) {
        # Increment wait counter when game hasn't started yet
        $waitIterations++

        # Timeout: exit after 30 minutes of waiting for game to start
        if ($waitIterations -ge $maxWaitIterations) {
            # Game never started - exit quietly
            exit 0
        }

        # Check tray alive only every 3rd iteration (15s) to reduce overhead
        $checkCounter++
        if ($checkCounter -ge 3) {
            $checkCounter = 0
            if (-not (Test-TrayAlive)) {
                exit 0
            }
        }
    }

    # Adaptive sleep:
    # - 5s when waiting for game to start
    # - 2s when game is running (detect exit quickly)
    $sleepMs = if ($gameRunning) { 2000 } else { 5000 }
    Start-Sleep -Milliseconds $sleepMs
}

# Cleanup
try {
    if ($script:trayProcess) { $script:trayProcess.Dispose() }
} catch {}
