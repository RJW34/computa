# Helper script to kill existing tray and relaunch
# Kill any existing ABSO tray processes
$procs = Get-CimInstance Win32_Process | Where-Object { $_.CommandLine -like '*ABSO-Tray*' -and $_.ProcessId -ne $PID }
foreach ($p in $procs) {
    Write-Host "Killing PID $($p.ProcessId): $($p.CommandLine)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 500

# Launch tray
$trayVbs = Join-Path $PSScriptRoot "ABSO-Tray.vbs"
$trayPs1 = Join-Path $PSScriptRoot "ABSO-Tray.ps1"

if (Test-Path $trayVbs) {
    Write-Host "Launching via VBS: $trayVbs"
    Start-Process "wscript.exe" -ArgumentList "`"$trayVbs`"" -WindowStyle Hidden
} else {
    Write-Host "Launching via PowerShell: $trayPs1"
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`"" -Verb RunAs
}

Write-Host "Done. Tray should appear in system tray."
