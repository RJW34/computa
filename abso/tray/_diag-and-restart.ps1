# Diagnostic: check log, kill old, clear mutex, relaunch with visible console for errors
Write-Host "=== ABSO Tray Diagnostic ==="

# Show recent log
$logFile = Join-Path $env:TEMP "abso_tray.log"
if (Test-Path $logFile) {
    Write-Host "`n--- Last 30 log lines ---"
    Get-Content $logFile -Tail 30
} else {
    Write-Host "No log file found at: $logFile"
}

# Kill ALL existing tray/watcher processes
Write-Host "`n--- Killing existing processes ---"
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*ABSO-Tray*' -or $_.CommandLine -like '*ABSO-Watcher*' }
foreach ($p in $procs) {
    if ($p.ProcessId -ne $PID) {
        Write-Host "  Killing PID $($p.ProcessId)"
        Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
    }
}

# Clear stale PID files
$pidFile = Join-Path $env:TEMP "abso_watcher.pid"
if (Test-Path $pidFile) { Remove-Item $pidFile -Force; Write-Host "  Cleared watcher PID file" }

$activeFile = Join-Path $env:TEMP "abso_active_profile.json"
if (Test-Path $activeFile) { Remove-Item $activeFile -Force; Write-Host "  Cleared active profile file" }

# Wait for mutex release
Start-Sleep -Milliseconds 1000

# Test-load the script to check for syntax errors
Write-Host "`n--- Syntax check ---"
$trayScript = Join-Path $PSScriptRoot "ABSO-Tray.ps1"
try {
    $tokens = $null
    $errors = $null
    [System.Management.Automation.Language.Parser]::ParseFile($trayScript, [ref]$tokens, [ref]$errors)
    if ($errors.Count -gt 0) {
        Write-Host "SYNTAX ERRORS FOUND in ABSO-Tray.ps1:"
        foreach ($err in $errors) {
            Write-Host "  Line $($err.Extent.StartLineNumber): $($err.Message)"
        }
    } else {
        Write-Host "  ABSO-Tray.ps1: OK"
    }
} catch {
    Write-Host "  Parse failed: $($_.Exception.Message)"
}

# Check modules too
foreach ($mod in @("ABSO-Icons.ps1", "ABSO-Notifications.ps1", "ABSO-Settings.ps1", "ABSO-QuickPanel.ps1")) {
    $modPath = Join-Path $PSScriptRoot $mod
    if (Test-Path $modPath) {
        try {
            $tokens = $null
            $errors = $null
            [System.Management.Automation.Language.Parser]::ParseFile($modPath, [ref]$tokens, [ref]$errors)
            if ($errors.Count -gt 0) {
                Write-Host "SYNTAX ERRORS in ${mod}:"
                foreach ($err in $errors) {
                    Write-Host "  Line $($err.Extent.StartLineNumber): $($err.Message)"
                }
            } else {
                Write-Host "  ${mod}: OK"
            }
        } catch {
            Write-Host "  ${mod} parse failed: $($_.Exception.Message)"
        }
    } else {
        Write-Host "  MISSING: $mod"
    }
}

Write-Host "`n--- Relaunching tray (visible console for debugging) ---"
Write-Host "Starting: $trayScript"
Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$trayScript`"" -Verb RunAs
Write-Host "Done. Check for UAC prompt and tray icon."
