# ABSO-StartupLaunch.ps1
# Startup helper that waits for Explorer shell, then launches the tray hidden.

param(
    [int]$MaxWaitSeconds = 120,
    [int]$PostExplorerDelayMs = 2500
)

$ErrorActionPreference = "Stop"

$logPath = Join-Path $env:TEMP "abso_tray_startup.log"
$vbsPath = Join-Path $PSScriptRoot "ABSO-Tray.vbs"
$trayScriptPath = Join-Path $PSScriptRoot "ABSO-Tray.ps1"

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

function Test-TrayProcessRunning {
    param([string]$TrayScript)

    if (-not (Test-Path $TrayScript)) {
        return $false
    }

    $needle = [System.IO.Path]::GetFileName($TrayScript).ToLowerInvariant()

    try {
        $powershellProcesses = Get-CimInstance Win32_Process -Filter "Name='powershell.exe'" -ErrorAction SilentlyContinue
        foreach ($proc in $powershellProcesses) {
            $commandLine = "$($proc.CommandLine)"
            if (-not [string]::IsNullOrWhiteSpace($commandLine) -and $commandLine.ToLowerInvariant().Contains($needle)) {
                return $true
            }
        }
    }
    catch {}

    return $false
}

function Start-TrayViaVbs {
    param([string]$VbsPath)
    Start-Process -FilePath "wscript.exe" -ArgumentList "`"$VbsPath`"" -WindowStyle Hidden | Out-Null
}

try {
    $attempts = 0
    $maxAttempts = 2

    while ($attempts -lt $maxAttempts) {
        $attempts++
        Start-TrayViaVbs -VbsPath $vbsPath
        Write-StartupLog "Tray launch command executed (attempt $attempts)"

        Start-Sleep -Milliseconds 1800
        if (Test-TrayProcessRunning -TrayScript $trayScriptPath) {
            Write-StartupLog "Tray process detected after launch (attempt $attempts)"
            exit 0
        }

        Write-StartupLog "Tray process not detected after launch attempt $attempts" "WARN"
    }

    Write-StartupLog "Tray process failed to start after $maxAttempts attempts" "ERROR"
    exit 1
}
catch {
    Write-StartupLog "Tray launch failed: $($_.Exception.Message)" "ERROR"
    exit 1
}
