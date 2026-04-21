# Visual demo of the v3 HUD notification system.
# Fires one toast of each type in rapid succession so the stack, queue,
# dedup, and new palette are all visible at once.

$ErrorActionPreference = "Stop"
Set-StrictMode -Version Latest

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing

$scriptDir = Split-Path -Parent $PSCommandPath
$root = Split-Path -Parent $scriptDir
$trayDir = Join-Path $root "abso\tray"

# Minimal Write-TrayLog stub so Show-ThemedToast's dedup logger doesn't
# blow up when called outside the real tray.
$script:LogFile = Join-Path $env:TEMP "abso_tray_demo.log"
$script:LogCheckedSize = $true
$script:LogMaxBytes = 1048576
$script:LogWriteCount = 0
function Write-TrayLog {
    param([string]$Message, [string]$Level = "INFO")
    $line = "[{0}] [{1}] {2}" -f (Get-Date -Format "HH:mm:ss"), $Level, $Message
    Add-Content -Path $script:LogFile -Value $line -ErrorAction SilentlyContinue
    Write-Host $line
}

# Dot-source the notification module
. (Join-Path $trayDir "ABSO-Notifications.ps1")

# Sequence: cyan Info, phosphor Success, amber Warning, an Info dup that
# should be silently deduped, and finally an Error that preempts when full.
Show-ThemedToast -Title "A.B.S.O." -Message "Profile catalog refreshed. 22 profiles, 17 aliases loaded." -Type "Info" -MetaText "v2.5.0"
Start-Sleep -Milliseconds 220
Show-ThemedToast -Title "A.B.S.O." -Message "Rivals 2 Online applied. 12 handlers tuned in 4.2 s." -Type "Success" -MetaText "backup 2026-04-18_014221"
Start-Sleep -Milliseconds 220
Show-ThemedToast -Title "A.B.S.O." -Message "Mixed refresh rates detected (59.95 Hz to 300 Hz) on the gaming display." -Type "Warning" -MetaText "multimon"
Start-Sleep -Milliseconds 220

# Dedup: this one is identical to the first, fired within 2 s
Show-ThemedToast -Title "A.B.S.O." -Message "Profile catalog refreshed. 22 profiles, 17 aliases loaded." -Type "Info" -MetaText "dedup test"

Start-Sleep -Milliseconds 400
# Error: should preempt the oldest low-priority toast if the stack is full
Show-ThemedToast -Title "A.B.S.O." -Message "NVIDIA profile 'Diablo IV' does not exist. Launch the game once to seed it." -Type "Error" -MetaText "preflight"

# Keep the process alive long enough for the user to observe
Write-Host "Demo toasts dispatched. Keeping alive for 12 s so you can observe."
$end = (Get-Date).AddSeconds(12)
while ((Get-Date) -lt $end) {
    [System.Windows.Forms.Application]::DoEvents()
    Start-Sleep -Milliseconds 30
}
Close-ThemedToast
Start-Sleep -Milliseconds 500
Write-Host "Demo complete."
