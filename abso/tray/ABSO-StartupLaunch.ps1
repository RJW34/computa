# ABSO-StartupLaunch.ps1
# Startup helper that waits for Explorer shell, then launches the tray hidden.

param(
    [int]$MaxWaitSeconds = 120,
    [int]$PostExplorerDelayMs = 2500
)

$ErrorActionPreference = "Stop"

$logPath = Join-Path $env:TEMP "abso_tray_startup.log"
$vbsPath = Join-Path $PSScriptRoot "ABSO-Tray.vbs"

function Write-StartupLog {
    param(
        [string]$Message,
        [string]$Level = "INFO"
    )

    try {
        $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
        Add-Content -Path $logPath -Value "[$timestamp] [$Level] $Message" -ErrorAction SilentlyContinue
    }
    catch {}
}

if (-not (Test-Path $vbsPath)) {
    Write-StartupLog "Launcher file not found: $vbsPath" "ERROR"
    exit 1
}

try {
    $sessionId = (Get-Process -Id $PID).SessionId
}
catch {
    $sessionId = $null
}

$explorerReady = $false
$deadline = (Get-Date).AddSeconds([Math]::Max(5, $MaxWaitSeconds))

while ((Get-Date) -lt $deadline) {
    try {
        $explorer = Get-Process -Name explorer -ErrorAction SilentlyContinue |
            Where-Object { ($null -eq $sessionId) -or ($_.SessionId -eq $sessionId) } |
            Select-Object -First 1
        if ($explorer) {
            $explorerReady = $true
            break
        }
    }
    catch {}

    Start-Sleep -Milliseconds 500
}

if ($explorerReady) {
    Start-Sleep -Milliseconds ([Math]::Max(0, $PostExplorerDelayMs))
    Write-StartupLog "Explorer detected; launching tray"
}
else {
    Write-StartupLog "Explorer not detected within wait window; launching tray anyway" "WARN"
}

try {
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$vbsPath`"" -WindowStyle Hidden | Out-Null
    Write-StartupLog "Tray launch command executed"
    exit 0
}
catch {
    Write-StartupLog "Tray launch failed: $($_.Exception.Message)" "ERROR"
    exit 1
}
