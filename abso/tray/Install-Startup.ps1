# Install-Startup.ps1 - Add/Remove A.B.S.O. tray from Windows startup
# Usage:
#   .\Install-Startup.ps1 -Install    # Add to startup
#   .\Install-Startup.ps1 -Uninstall  # Remove from startup
#   .\Install-Startup.ps1 -Status     # Check if installed

param(
    [switch]$Install,
    [switch]$Uninstall,
    [switch]$Status
)

$StartupFolder = [Environment]::GetFolderPath("Startup")
$ShortcutPath = Join-Path $StartupFolder "ABSO-Tray.lnk"
$VBSPath = Join-Path $PSScriptRoot "ABSO-Tray.vbs"

function Get-InstallStatus {
    if (Test-Path $ShortcutPath) {
        return $true
    }
    return $false
}

if ($Status) {
    if (Get-InstallStatus) {
        Write-Host "A.B.S.O. Tray is installed in Windows startup" -ForegroundColor Green
        Write-Host "Location: $ShortcutPath"
    } else {
        Write-Host "A.B.S.O. Tray is NOT in Windows startup" -ForegroundColor Yellow
    }
    exit
}

if ($Install) {
    if (-not (Test-Path $VBSPath)) {
        Write-Host "Error: ABSO-Tray.vbs not found at: $VBSPath" -ForegroundColor Red
        exit 1
    }

    # Create shortcut
    $WshShell = New-Object -ComObject WScript.Shell
    $Shortcut = $WshShell.CreateShortcut($ShortcutPath)
    $Shortcut.TargetPath = "wscript.exe"
    $Shortcut.Arguments = "`"$VBSPath`""
    $Shortcut.WorkingDirectory = $PSScriptRoot
    $Shortcut.Description = "A.B.S.O. System Tray"
    $Shortcut.Save()

    Write-Host "A.B.S.O. Tray added to Windows startup" -ForegroundColor Green
    Write-Host "Location: $ShortcutPath"
    Write-Host ""
    Write-Host "The tray will start automatically on next login."
    Write-Host "To start now, run: wscript.exe `"$VBSPath`""
    exit
}

if ($Uninstall) {
    if (Test-Path $ShortcutPath) {
        Remove-Item $ShortcutPath -Force
        Write-Host "A.B.S.O. Tray removed from Windows startup" -ForegroundColor Green
    } else {
        Write-Host "A.B.S.O. Tray was not in startup" -ForegroundColor Yellow
    }
    exit
}

# Default: show usage
Write-Host ""
Write-Host "A.B.S.O. Tray Startup Installer" -ForegroundColor Cyan
Write-Host ""
Write-Host "Usage:"
Write-Host "  -Install    Add A.B.S.O. tray to Windows startup"
Write-Host "  -Uninstall  Remove from Windows startup"
Write-Host "  -Status     Check if installed in startup"
Write-Host ""
