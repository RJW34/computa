# install.ps1 - A.B.S.O. end-user installer
#
# Installs a released abso.exe into %LOCALAPPDATA%\AdaptiveBattleStationOptimizer,
# optionally adds it to the user PATH, and launches the first-run setup wizard
# (elevated). Ship this script next to abso.exe as a release asset.
#
# Usage (from the folder containing abso.exe):
#   powershell -ExecutionPolicy Bypass -File .\install.ps1
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -ExePath C:\Downloads\abso.exe
#   powershell -ExecutionPolicy Bypass -File .\install.ps1 -NoSetup -NoPath

param(
    [string]$ExePath = "",
    [switch]$NoSetup,
    [switch]$NoPath
)

$ErrorActionPreference = "Stop"

$installRoot = Join-Path $env:LOCALAPPDATA "AdaptiveBattleStationOptimizer"
$installedExe = Join-Path $installRoot "abso.exe"

# Resolve the source executable: explicit param, else next to this script.
if ([string]::IsNullOrWhiteSpace($ExePath)) {
    $ExePath = Join-Path $PSScriptRoot "abso.exe"
}
if (-not (Test-Path $ExePath)) {
    Write-Host "abso.exe not found at: $ExePath" -ForegroundColor Red
    Write-Host "Download abso.exe from the latest release and place it next to this script,"
    Write-Host "or pass -ExePath <path-to-abso.exe>."
    exit 1
}

Write-Host ""
Write-Host "A.B.S.O. installer" -ForegroundColor Cyan
Write-Host "  Source:  $ExePath"
Write-Host "  Target:  $installedExe"
Write-Host ""

New-Item -ItemType Directory -Force -Path $installRoot | Out-Null
Copy-Item -Path $ExePath -Destination $installedExe -Force
Write-Host "Installed abso.exe." -ForegroundColor Green

if (-not $NoPath) {
    $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
    if ($null -eq $userPath) { $userPath = "" }
    $onPath = ($userPath -split ";" | Where-Object { $_.TrimEnd("\") -ieq $installRoot.TrimEnd("\") }).Count -gt 0
    if (-not $onPath) {
        $newPath = if ([string]::IsNullOrWhiteSpace($userPath)) { $installRoot } else { "$userPath;$installRoot" }
        [Environment]::SetEnvironmentVariable("Path", $newPath, "User")
        Write-Host "Added to user PATH (new terminals can run 'abso' directly)." -ForegroundColor Green
    }
    else {
        Write-Host "Install folder already on user PATH." -ForegroundColor DarkGray
    }
}

if ($NoSetup) {
    Write-Host ""
    Write-Host "Skipped setup. Run this later from an elevated terminal:" -ForegroundColor Yellow
    Write-Host "  abso setup"
    exit 0
}

Write-Host ""
Write-Host "Launching the first-run setup wizard (requires administrator approval)..." -ForegroundColor Cyan
try {
    Start-Process -FilePath $installedExe -ArgumentList "setup" -Verb RunAs -Wait
}
catch {
    Write-Host "Setup was not started ($($_.Exception.Message))." -ForegroundColor Yellow
    Write-Host "Run it yourself from an elevated terminal:  abso setup"
}

Write-Host ""
Write-Host "Done. Useful commands:" -ForegroundColor Cyan
Write-Host "  abso profiles      list profiles available on this machine"
Write-Host "  abso apply <id>    apply a profile (automatic backup first)"
Write-Host "  abso restore latest  roll back the last apply"
Write-Host "  abso uninstall     restore the setup baseline and remove ABSO"
