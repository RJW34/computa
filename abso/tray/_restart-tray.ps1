# Helper script to kill existing tray and relaunch
# Self-elevate so manual restarts work the same way as the tray host.
$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
    [Security.Principal.WindowsBuiltInRole]::Administrator
)

if (-not $isAdmin) {
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`"" -Verb RunAs
    exit 0
}

# Kill any existing ABSO tray processes
$trayPs1 = Join-Path $PSScriptRoot "ABSO-Tray.ps1"
$trayVbs = Join-Path $PSScriptRoot "ABSO-Tray.vbs"
$startupLauncher = Join-Path $PSScriptRoot "ABSO-StartupLaunch.ps1"

$procs = Get-CimInstance Win32_Process | Where-Object {
    $_.ProcessId -ne $PID -and
    $_.CommandLine -and
    (
        $_.CommandLine -like "*$trayPs1*" -or
        $_.CommandLine -like "*$trayVbs*" -or
        $_.CommandLine -like "*$startupLauncher*"
    )
}
foreach ($p in $procs) {
    Write-Host "Killing PID $($p.ProcessId): $($p.CommandLine)"
    Stop-Process -Id $p.ProcessId -Force -ErrorAction SilentlyContinue
}

Start-Sleep -Milliseconds 500

# Launch tray
if (Test-Path $trayVbs) {
    Write-Host "Launching via VBS: $trayVbs"
    Start-Process "wscript.exe" -ArgumentList "`"$trayVbs`"" -WindowStyle Hidden
} else {
    Write-Host "Launching via PowerShell: $trayPs1"
    Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$trayPs1`"" -Verb RunAs
}

Write-Host "Done. Tray should appear in system tray."
