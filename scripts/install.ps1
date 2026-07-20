# install.ps1 - computa portable/power-user installer (console).
#
# Most users should use computa-setup.exe (the standard Windows installer);
# this script is the no-installer path: it copies computa.exe into
# %LOCALAPPDATA%\AdaptiveBattleStationOptimizer, optionally adds it to the
# user PATH, and launches the first-run setup.
#
# Usage (from the folder containing computa.exe):
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -ExePath C:\Downloads\computa.exe
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoSetup -NoPath

param(
    [string]$ExePath = "",
    [switch]$NoSetup,
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "AdaptiveBattleStationOptimizer"
$installedExe = Join-Path $installRoot "computa.exe"

if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $ExePath = Join-Path $PSScriptRoot "computa.exe"
}
if (-not (Test-Path $ExePath)) {
    Write-Host "computa.exe not found at: $ExePath" -ForegroundColor Red
    Write-Host "Download computa.exe from the latest release and place it next to this script,"
    Write-Host "or pass -ExePath <path-to-computa.exe>."
    exit 1
}

Write-Host ""
Write-Host "computa installer (portable)" -ForegroundColor Cyan
Write-Host "  Source:  $ExePath"
Write-Host "  Target:  $installedExe"
Write-Host ""

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Copy-Item -Path $ExePath -Destination $installedExe -Force
Write-Host "Installed computa.exe." -ForegroundColor Green

if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $userPath) { $userPath = "" }
    $onPath = ($userPath -split ";" | Where-Object { $_.TrimEnd("\") -ieq $installRoot.TrimEnd("\") }).Count -gt 0
    if (-not $onPath) {
        $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $installRoot } else { "$userPath;$installRoot" }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Added to user PATH (new terminals can run 'computa' directly)." -ForegroundColor Green
    }
    else {
        Write-Host "Install folder already on user PATH." -ForegroundColor DarkGray
    }
}

if ($NoSetup) {
    Write-Host ""
    Write-Host "Skipped setup. Run this later from an elevated terminal:" -ForegroundColor Yellow
    Write-Host "  computa setup"
    exit 0
}

Write-Host ""
Write-Host "Launching the first-run setup wizard (requires administrator approval)..." -ForegroundColor Cyan
try {
    Start-Process -FilePath $installedExe -ArgumentList "setup" -Verb RunAs -Wait
}
catch {
    Write-Host "Setup was not started ($($_.Exception.Message))." -ForegroundColor Yellow
    Write-Host "Run it yourself from an elevated terminal:  computa setup"
}

Write-Host ""
Write-Host "Done. Useful commands:" -ForegroundColor Cyan
Write-Host "  computa profiles      list profiles available on this machine"
Write-Host "  computa apply <id>    apply a profile (automatic backup first)"
Write-Host "  computa restore latest  roll back the last apply"
Write-Host "  computa uninstall     restore the setup baseline and remove computa"
exit 0
