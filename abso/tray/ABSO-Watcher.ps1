# ABSO-Watcher.ps1 - Ultra-lightweight game process monitor
# Memory: ~15-20MB | CPU: Near-zero (adaptive polling)
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

# Parse executable list
$executables = $ExeList -split ','
$processNames = $executables | ForEach-Object {
    [System.IO.Path]::GetFileNameWithoutExtension($_)
}

$gameRunning = $false
$trayKilled = $false

# Check if any game process is running
function Test-GameRunning {
    foreach ($name in $processNames) {
        if (Get-Process -Name $name -ErrorAction SilentlyContinue) {
            return $true
        }
    }
    return $false
}

# Check if tray is still alive
function Test-TrayAlive {
    try {
        $proc = Get-Process -Id $TrayPID -ErrorAction SilentlyContinue
        return ($null -ne $proc)
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

        Stop-Process -Id $TrayPID -Force -ErrorAction SilentlyContinue

        # Optional: show brief notification that tray is paused
        # (commented out to minimize overhead during gaming)
        # Add-Type -AssemblyName System.Windows.Forms
        # [System.Windows.Forms.MessageBox]::Show("A.B.S.O. paused during gaming", "A.B.S.O.", "OK", "Information")
    }
    elseif (-not $gameNowRunning -and $gameRunning) {
        # Game just exited - restart tray and exit watcher
        $gameRunning = $false

        # Small delay to ensure mutex is released from killed tray
        Start-Sleep -Milliseconds 500

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

        # Clean exit - our job is done
        exit 0
    }
    elseif (-not $gameRunning -and -not $trayKilled) {
        # Game hasn't started yet - check if tray is still alive
        # If user closed tray manually, no point in watching
        if (-not (Test-TrayAlive)) {
            exit 0
        }
    }

    # Adaptive sleep:
    # - 5s when waiting for game to start (low urgency)
    # - 2s when game is running (need to detect exit quickly)
    $sleepMs = if ($gameRunning) { 2000 } else { 5000 }
    Start-Sleep -Milliseconds $sleepMs
}
