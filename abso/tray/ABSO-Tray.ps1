# ABSO-Tray.ps1 - System tray for A.B.S.O. with Dark Theme (Modernized)
# Memory: ~25-35MB | CPU: Near-zero when idle
# Left-click shows profile menu, applies via CLI, monitors game lifecycle
# Features: Dynamic icons, favorites, search, progress overlay, hotkeys, settings

param([switch]$Hidden)

# ============================================================================
# ADMIN ELEVATION CHECK
# ============================================================================

$isAdmin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)

if (-not $isAdmin) {
    $scriptPath = $PSCommandPath
    try {
        Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -File `"$scriptPath`" -Hidden" -Verb RunAs -WindowStyle Hidden
    }
    catch {
        Add-Type -AssemblyName System.Windows.Forms
        [System.Windows.Forms.MessageBox]::Show(
            "A.B.S.O. Tray requires administrator privileges to apply profiles.`n`nPlease run as Administrator.",
            "A.B.S.O.",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Warning
        )
    }
    exit 0
}

Add-Type -AssemblyName System.Windows.Forms
Add-Type -AssemblyName System.Drawing
Add-Type -AssemblyName presentationCore

# Catch WinForms thread exceptions (e.g. renderer GDI+ errors) — log instead of showing .NET dialog
# MUST be called before any Controls are created
[System.Windows.Forms.Application]::SetUnhandledExceptionMode([System.Windows.Forms.UnhandledExceptionMode]::CatchException)
$script:ThreadExceptionCount = 0
$script:ThreadExceptionThrottle = $null
[System.Windows.Forms.Application]::add_ThreadException({
    param($sender, $eventArgs)
    $script:ThreadExceptionCount++
    # Throttle: log first 5 fully, then only every 100th, to prevent log spam
    if ($script:ThreadExceptionCount -le 5 -or ($script:ThreadExceptionCount % 100) -eq 0) {
        $ex = $eventArgs.Exception
        $msg = "WinForms ThreadException #$($script:ThreadExceptionCount): $($ex.GetType().Name): $($ex.Message)"
        if ($ex.StackTrace) { $msg += "`n$($ex.StackTrace)" }
        if ($ex.InnerException) { $msg += "`nInner: $($ex.InnerException.Message)" }
        try { Write-TrayLog $msg -Level "ERROR" } catch {
            $logPath = Join-Path $env:TEMP "abso_tray.log"
            "[$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')] [ERROR] $msg" | Out-File -FilePath $logPath -Append -Encoding UTF8
        }
    }
})

# ============================================================================
# DWM INTEROP - Modern Windows 11 Window Effects
# ============================================================================

Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;

public static class DwmHelper {
    [DllImport("dwmapi.dll")]
    public static extern int DwmSetWindowAttribute(IntPtr hwnd, int attr, ref int attrValue, int attrSize);

    [DllImport("dwmapi.dll")]
    public static extern int DwmExtendFrameIntoClientArea(IntPtr hwnd, ref MARGINS pMarInset);

    [StructLayout(LayoutKind.Sequential)]
    public struct MARGINS {
        public int cxLeftWidth;
        public int cxRightWidth;
        public int cyTopHeight;
        public int cyBottomHeight;
    }

    // DWMWA_WINDOW_CORNER_PREFERENCE = 33  |  DWMWCP_ROUND = 2, DWMWCP_ROUNDSMALL = 3
    public static void SetRoundedCorners(IntPtr hwnd, int preference) {
        DwmSetWindowAttribute(hwnd, 33, ref preference, sizeof(int));
    }

    // DWMWA_USE_IMMERSIVE_DARK_MODE = 20
    public static void SetDarkMode(IntPtr hwnd) {
        int value = 1;
        DwmSetWindowAttribute(hwnd, 20, ref value, sizeof(int));
    }

    // DWMWA_BORDER_COLOR = 34  (COLORREF: 0x00BBGGRR)
    public static void SetBorderColor(IntPtr hwnd, int colorRef) {
        DwmSetWindowAttribute(hwnd, 34, ref colorRef, sizeof(int));
    }

    // Enable drop shadow via frame extension
    public static void EnableShadow(IntPtr hwnd) {
        MARGINS margins = new MARGINS {
            cxLeftWidth = 1, cxRightWidth = 1,
            cyTopHeight = 1, cyBottomHeight = 1
        };
        DwmExtendFrameIntoClientArea(hwnd, ref margins);
    }
}
"@ -ErrorAction SilentlyContinue

function Apply-DwmWindowEffects {
    <#
    .SYNOPSIS
    Applies modern Windows 11 DWM effects (rounded corners, dark mode, shadow) to a form.
    Falls back silently on older builds.
    .PARAMETER Form
    The WinForms Form to style.
    .PARAMETER CornerStyle
    2 = round (default), 3 = round small.
    .PARAMETER BorderColorRGB
    Optional border color as [R,G,B] array. Converted to COLORREF internally.
    #>
    param(
        [System.Windows.Forms.Form]$Form,
        [int]$CornerStyle = 2,
        [int[]]$BorderColorRGB = $null
    )

    if (-not $Form -or $Form.IsDisposed) { return }

    try {
        $handle = $Form.Handle
        [DwmHelper]::SetRoundedCorners($handle, $CornerStyle)
        [DwmHelper]::SetDarkMode($handle)
        [DwmHelper]::EnableShadow($handle)

        if ($BorderColorRGB -and $BorderColorRGB.Count -ge 3) {
            # COLORREF = 0x00BBGGRR
            $colorRef = $BorderColorRGB[2] -shl 16 -bor $BorderColorRGB[1] -shl 8 -bor $BorderColorRGB[0]
            [DwmHelper]::SetBorderColor($handle, $colorRef)
        }
    }
    catch {
        # Silently ignore on unsupported Windows builds
    }
}

# ============================================================================
# LOAD MODULES
# ============================================================================

$script:ScriptDir = $PSScriptRoot
. (Join-Path $script:ScriptDir "ABSO-Icons.ps1")
. (Join-Path $script:ScriptDir "ABSO-Notifications.ps1")
. (Join-Path $script:ScriptDir "ABSO-Settings.ps1")
. (Join-Path $script:ScriptDir "ABSO-StartupState.ps1")
. (Join-Path $script:ScriptDir "ABSO-QuickPanel.ps1")

# ============================================================================
# SOUND EFFECTS
# ============================================================================

$script:SoundFile = Join-Path $PSScriptRoot "pokemon-red_blue_yellow-save-game-sound-effect.mp3"
$script:FailSoundFile = Join-Path $PSScriptRoot "hit-weak-not-very-effective.mp3"
$script:VrrWarningSoundFile = Join-Path $PSScriptRoot "oot_navi_hey1.mp3"
$script:RestartSoundFile = Join-Path $PSScriptRoot "pokemon-redblueyellow-item-found-sound-effect.mp3"
$script:MediaPlayer = $null
$script:RestartSoundMarkerMaxAgeSeconds = 180
try {
    $restartMarkerRoot = Join-Path ([Environment]::GetFolderPath("LocalApplicationData")) "AdaptiveBattleStationOptimizer"
}
catch {
    $restartMarkerRoot = $env:TEMP
}
$script:RestartSoundMarkerFile = Join-Path $restartMarkerRoot "tray-restart-pending.json"

function Get-MediaPlayer {
    if ($null -eq $script:MediaPlayer) {
        $script:MediaPlayer = New-Object System.Windows.Media.MediaPlayer
        $script:MediaEndedSub = Register-ObjectEvent -InputObject $script:MediaPlayer -EventName MediaEnded -Action {
            $script:MediaPlayer.Close()
        }
    }
    return $script:MediaPlayer
}

function Play-SoundFile {
    <#
    .SYNOPSIS
    Plays a sound file via the shared MediaPlayer. Stops any current playback first.
    #>
    param([string]$FilePath, [double]$Volume = 0.2)

    $player = Get-MediaPlayer
    # Stop current playback before opening new file
    $player.Stop()
    $player.Open([Uri]$FilePath)
    $player.Volume = $Volume
    $player.Play()
}

function Play-SuccessSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        if (Test-Path $script:SoundFile) {
            Play-SoundFile -FilePath $script:SoundFile -Volume $script:TrayConfig.soundVolume
            Write-TrayLog "Playing success sound"
        }
        else {
            Write-TrayLog "Sound file not found: $($script:SoundFile)" -Level "WARN"
        }
    }
    catch {
        Write-TrayLog "Failed to play sound: $($_.Exception.Message)" -Level "WARN"
    }
}

function Play-FailSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        if (Test-Path $script:FailSoundFile) {
            Play-SoundFile -FilePath $script:FailSoundFile -Volume ([Math]::Min(1.0, $script:TrayConfig.soundVolume * 3))
            Write-TrayLog "Playing fail sound"
        }
    }
    catch {
        Write-TrayLog "Failed to play fail sound: $($_.Exception.Message)" -Level "WARN"
    }
}

function Play-VrrWarningSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) { return }
        if (Test-Path $script:VrrWarningSoundFile) {
            Play-SoundFile -FilePath $script:VrrWarningSoundFile -Volume ([Math]::Min(1.0, $script:TrayConfig.soundVolume * 2.5))
            Write-TrayLog "Playing VRR warning sound"
        }
        else {
            Write-TrayLog "VRR warning sound file not found: $($script:VrrWarningSoundFile)" -Level "WARN"
            Play-FailSound
        }
    }
    catch {
        Write-TrayLog "Failed to play VRR warning sound: $($_.Exception.Message)" -Level "WARN"
        Play-FailSound
    }
}

function Play-RestartSound {
    try {
        if (-not $script:TrayConfig.soundEnabled) {
            Write-TrayLog "Restart sound skipped (sound effects disabled)"
            return
        }

        if (-not (Test-Path $script:RestartSoundFile)) {
            Write-TrayLog "Restart sound file not found: $($script:RestartSoundFile)" -Level "WARN"
            return
        }

        if (-not ("AbsoMci" -as [type])) {
            Add-Type -TypeDefinition @"
using System;
using System.Runtime.InteropServices;
using System.Text;
public static class AbsoMci {
    [DllImport("winmm.dll", CharSet = CharSet.Unicode)]
    public static extern int mciSendStringW(string command, StringBuilder buffer, int bufferSize, IntPtr callback);
}
"@
        }

        $volume = [Math]::Max(0, [Math]::Min(1000, [int]([Math]::Round($script:TrayConfig.soundVolume * 1000))))
        $alias = "abso_restart_$PID"

        $errBuf = New-Object System.Text.StringBuilder 260
        $openRc = [AbsoMci]::mciSendStringW("open `"$($script:RestartSoundFile)`" type mpegvideo alias $alias", $errBuf, $errBuf.Capacity, [IntPtr]::Zero)
        if ($openRc -ne 0) {
            throw "MCI open failed (code=$openRc, detail='$($errBuf.ToString())')"
        }

        [void][AbsoMci]::mciSendStringW("setaudio $alias volume to $volume", $null, 0, [IntPtr]::Zero)

        $playBuf = New-Object System.Text.StringBuilder 260
        $playRc = [AbsoMci]::mciSendStringW("play $alias wait", $playBuf, $playBuf.Capacity, [IntPtr]::Zero)
        [void][AbsoMci]::mciSendStringW("close $alias", $null, 0, [IntPtr]::Zero)
        if ($playRc -ne 0) {
            throw "MCI play failed (code=$playRc, detail='$($playBuf.ToString())')"
        }

        Write-TrayLog "Playing restart sound (synchronous, mciSendString)"
    }
    catch {
        Write-TrayLog "Failed to play restart sound via MCI: $($_.Exception.Message)" -Level "WARN"
        # Fallback to shared MediaPlayer to keep behavior resilient on systems where MCI MP3 is unavailable.
        try {
            Play-SoundFile -FilePath $script:RestartSoundFile -Volume $script:TrayConfig.soundVolume
            Start-Sleep -Milliseconds 350
            Write-TrayLog "Restart sound fallback played via MediaPlayer"
        }
        catch {
            Write-TrayLog "Restart sound fallback failed: $($_.Exception.Message)" -Level "WARN"
        }
    }
}

function Set-RestartSuccessSoundMarker {
    try {
        if (-not $script:RestartSoundMarkerFile) { return }

        $dir = Split-Path -Parent $script:RestartSoundMarkerFile
        if ($dir -and -not (Test-Path $dir)) {
            New-Item -Path $dir -ItemType Directory -Force | Out-Null
        }

        $payload = [ordered]@{
            requested_at = (Get-Date).ToString("o")
            requested_pid = $PID
            source = "restart_menu"
        }
        $payload | ConvertTo-Json -Depth 3 | Set-Content -Path $script:RestartSoundMarkerFile -Encoding UTF8
        Write-TrayLog "Restart success-sound marker written"
    }
    catch {
        Write-TrayLog "Failed to write restart success-sound marker: $($_.Exception.Message)" -Level "WARN"
    }
}

function Invoke-RestartSuccessSoundIfPending {
    if (-not $script:RestartSoundMarkerFile -or -not (Test-Path $script:RestartSoundMarkerFile)) {
        return
    }

    try {
        $raw = Get-Content -Path $script:RestartSoundMarkerFile -Raw -ErrorAction Stop
        if ([string]::IsNullOrWhiteSpace($raw)) {
            Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
            return
        }

        $marker = $raw | ConvertFrom-Json
        [datetime]$requestedAt = [datetime]::MinValue
        $hasTimestamp = $false
        if ($marker -and $marker.requested_at) {
            $hasTimestamp = [datetime]::TryParse("$($marker.requested_at)", [ref]$requestedAt)
        }

        if ($hasTimestamp) {
            $ageSeconds = [Math]::Abs(((Get-Date).ToUniversalTime() - $requestedAt.ToUniversalTime()).TotalSeconds)
            if ($ageSeconds -gt $script:RestartSoundMarkerMaxAgeSeconds) {
                Write-TrayLog "Restart success-sound marker expired ($([int]$ageSeconds)s old) - skipping sound" -Level "INFO"
                Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
                return
            }
        }

        # Consume marker first to avoid replay if audio fails.
        Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
        Write-TrayLog "Restart marker consumed; playing restart success sound"
        Play-RestartSound
    }
    catch {
        Write-TrayLog "Failed processing restart success-sound marker: $($_.Exception.Message)" -Level "WARN"
        Remove-Item -Path $script:RestartSoundMarkerFile -Force -ErrorAction SilentlyContinue
    }
}

function Test-IsVrrPrerequisiteError {
    param([string]$Message)

    if (-not $Message) { return $false }

    return (
        $Message -match "VRR/G-SYNC support" -or
        $Message -match "Adaptive Sync/FreeSync" -or
        $Message -match "Enable G-SYNC in NVIDIA Control Panel"
    )
}

function Test-NeedsNoSyncOsdReminder {
    param(
        [string]$FromProfileId,
        [string]$ToProfileId
    )

    if ([string]::IsNullOrWhiteSpace($FromProfileId) -or [string]::IsNullOrWhiteSpace($ToProfileId)) {
        return $false
    }

    $fromProfile = $script:Profiles[$FromProfileId]
    $toProfile = $script:Profiles[$ToProfileId]
    if (-not $fromProfile -or -not $toProfile) { return $false }

    $fromSyncMode = if ($fromProfile.SyncMode) { "$($fromProfile.SyncMode)".ToLowerInvariant() } else { "" }
    $toSyncMode = if ($toProfile.SyncMode) { "$($toProfile.SyncMode)".ToLowerInvariant() } else { "" }
    if (($fromSyncMode -eq "on") -and ($toSyncMode -eq "off")) {
        return $true
    }

    $fromText = (($fromProfile.Name, $fromProfile.Sub, $fromProfile.Desc) -join " ").ToLowerInvariant()
    $toText = (($toProfile.Name, $toProfile.Sub, $toProfile.Desc) -join " ").ToLowerInvariant()

    # Treat profile metadata as source of truth:
    # - sync-on intents should contain explicit ON markers
    # - no-sync intents should contain explicit OFF/no-sync markers
    $fromSyncOn = (
        $fromText -match "\bg-?sync\s*on\b" -or
        $fromText -match "\bvrr\s*on\b"
    )
    $toSyncOff = (
        $toText -match "\bg-?sync\s*off\b" -or
        $toText -match "\bvrr\s*off\b" -or
        $toText -match "\bno[-\s]?sync\b" -or
        $toText -match "\bno\s+vrr\b"
    )

    return ($fromSyncOn -and $toSyncOff)
}

$script:SoundFilesChecked = $false

function Test-SoundFilesExist {
    # Only log warnings once per session
    if ($script:SoundFilesChecked) { return ($script:SoundFilesValid) }
    $script:SoundFilesChecked = $true
    $script:SoundFilesValid = $true

    if (-not (Test-Path $script:SoundFile)) {
        Write-TrayLog "SUCCESS SOUND FILE MISSING: $($script:SoundFile)" -Level "WARN"
        $script:SoundFilesValid = $false
    }
    if (-not (Test-Path $script:FailSoundFile)) {
        Write-TrayLog "FAIL SOUND FILE MISSING: $($script:FailSoundFile)" -Level "WARN"
        $script:SoundFilesValid = $false
    }
    if (-not (Test-Path $script:VrrWarningSoundFile)) {
        Write-TrayLog "VRR WARNING SOUND FILE MISSING: $($script:VrrWarningSoundFile)" -Level "WARN"
        $script:SoundFilesValid = $false
    }
    if (-not (Test-Path $script:RestartSoundFile)) {
        Write-TrayLog "RESTART SOUND FILE MISSING: $($script:RestartSoundFile)" -Level "WARN"
        $script:SoundFilesValid = $false
    }
    if ($script:SoundFilesValid) { Write-TrayLog "Sound files validated" }
    return $script:SoundFilesValid
}

# ============================================================================
# DARK THEME COLORS
# ============================================================================

$script:Colors = @{
    Background      = [System.Drawing.Color]::FromArgb(255, 26, 26, 30)
    BackgroundDark  = [System.Drawing.Color]::FromArgb(255, 20, 20, 24)
    BackgroundLight = [System.Drawing.Color]::FromArgb(255, 36, 36, 42)
    Hover           = [System.Drawing.Color]::FromArgb(255, 44, 44, 50)
    HoverBright     = [System.Drawing.Color]::FromArgb(255, 56, 56, 62)
    Text            = [System.Drawing.Color]::FromArgb(255, 230, 230, 235)
    TextDim         = [System.Drawing.Color]::FromArgb(255, 125, 125, 135)
    TextDisabled    = [System.Drawing.Color]::FromArgb(255, 75, 75, 85)
    Border          = [System.Drawing.Color]::FromArgb(255, 55, 55, 62)
    Separator       = [System.Drawing.Color]::FromArgb(255, 48, 48, 55)
    AccentGold      = [System.Drawing.Color]::FromArgb(255, 230, 190, 70)
    AccentGreen     = [System.Drawing.Color]::FromArgb(255, 80, 210, 120)
    AccentBlue      = [System.Drawing.Color]::FromArgb(255, 75, 155, 235)
    AccentPurple    = [System.Drawing.Color]::FromArgb(255, 145, 120, 225)
    AccentAmber     = [System.Drawing.Color]::FromArgb(255, 240, 170, 60)
    AccentRed       = [System.Drawing.Color]::FromArgb(255, 220, 75, 75)
    AccentTeal      = [System.Drawing.Color]::FromArgb(255, 70, 200, 200)
    FavoriteStar    = [System.Drawing.Color]::FromArgb(255, 255, 215, 70)
    CatFighting     = [System.Drawing.Color]::FromArgb(255, 235, 115, 115)
    CatARPG         = [System.Drawing.Color]::FromArgb(255, 175, 145, 225)
    CatShooter      = [System.Drawing.Color]::FromArgb(255, 115, 180, 225)
    CatStreaming    = [System.Drawing.Color]::FromArgb(255, 70, 200, 200)
    CatOther        = [System.Drawing.Color]::FromArgb(255, 145, 200, 145)
    CatProd         = [System.Drawing.Color]::FromArgb(255, 220, 190, 115)
}

# ============================================================================
# LOGGING
# ============================================================================

$script:LogFile = Join-Path $env:TEMP "abso_tray.log"
$script:LogMaxBytes = 2 * 1024 * 1024  # 2 MB max log size
$script:LogCheckedSize = $false

function Write-TrayLog {
    param([string]$Message, [string]$Level = "INFO")
    $timestamp = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
    $line = "[$timestamp] [$Level] $Message"
    try {
        # Rotate log if too large (check once per session, then every ~100 writes)
        if (-not $script:LogCheckedSize) {
            $script:LogCheckedSize = $true
            $script:LogWriteCount = 0
            if (Test-Path $script:LogFile) {
                $fileInfo = Get-Item $script:LogFile -ErrorAction SilentlyContinue
                if ($fileInfo -and $fileInfo.Length -gt $script:LogMaxBytes) {
                    $backupLog = "$($script:LogFile).old"
                    Move-Item $script:LogFile $backupLog -Force -ErrorAction SilentlyContinue
                }
            }
        }
        $script:LogWriteCount++
        if ($script:LogWriteCount -ge 100) {
            $script:LogCheckedSize = $false  # Re-check on next write
        }
        Add-Content -Path $script:LogFile -Value $line -ErrorAction SilentlyContinue
    }
    catch {}
}

# ============================================================================
# NOTIFICATION SYSTEM
# ============================================================================

$script:EnableBalloonNotifications = $true

function Show-Notification {
    param(
        [string]$Title,
        [string]$Message,
        [ValidateSet("Info", "Warning", "Error")]
        [string]$Type = "Info"
    )

    # Update tray tooltip
    $maxLen = [Math]::Min(63, "$Title - $Message".Length)
    $script:notifyIcon.Text = "$Title - $Message".Substring(0, $maxLen)

    if ($script:EnableBalloonNotifications) {
        # Map "Info" -> "Info" for toast (toast also accepts "Success")
        $toastType = switch ($Type) {
            "Warning" { "Warning" }
            "Error"   { "Error" }
            default   { "Info" }
        }
        Show-ThemedToast -Title $Title -Message $Message -Type $toastType
    }
}

# ============================================================================
# SINGLE INSTANCE ENFORCEMENT
# ============================================================================

$script:mutexName = "Global\ABSO_Tray_SingleInstance_v2"
$script:createdNew = $false
try {
    $script:mutex = New-Object System.Threading.Mutex($true, $script:mutexName, [ref]$script:createdNew)
}
catch {
    exit 0
}

if (-not $script:createdNew) {
    if ($script:mutex) {
        $script:mutex.Close()
        $script:mutex = $null
    }
    exit 0
}

# ============================================================================
# PATHS
# ============================================================================

$script:ProjectRoot = (Resolve-Path (Join-Path $PSScriptRoot "..\..")).Path

# Resolve full python path at startup.
# Prefer the repo-local virtualenv so tray restarts always see the current workspace code.
$script:PythonExe = $null
$localVenvPython = Join-Path $script:ProjectRoot ".venv\Scripts\python.exe"
if (Test-Path $localVenvPython) {
    $script:PythonExe = $localVenvPython
}

# Fallback to PATH/global Python if no local virtualenv exists.
if (-not $script:PythonExe) {
    $script:PythonExe = (Get-Command python -ErrorAction SilentlyContinue).Source
}
if (-not $script:PythonExe) {
    # Fallback: search common Python install paths across versions
    $found = $false
    foreach ($ver in @("Python313", "Python312", "Python311", "Python310", "Python39")) {
        $candidate = Join-Path $env:LOCALAPPDATA "Programs\Python\$ver\python.exe"
        if (Test-Path $candidate) {
            $script:PythonExe = $candidate
            $found = $true
            break
        }
    }
    if (-not $found) {
        # Also check user PATH from registry (admin sessions lose inherited user PATH)
        try {
            $userPath = [Environment]::GetEnvironmentVariable("Path", "User")
            if ($userPath) {
                foreach ($dir in ($userPath -split ';')) {
                    $candidate = Join-Path $dir "python.exe"
                    if ($dir -and (Test-Path $candidate)) {
                        $script:PythonExe = $candidate
                        $found = $true
                        break
                    }
                }
            }
        } catch {}
    }
    if (-not $found) { $script:PythonExe = "python" }  # last resort
}

# ============================================================================
# PROFILE DEFINITIONS
# ============================================================================

$script:AppVersion = "2.5.0"

$script:FallbackProfiles = [ordered]@{
    # --- Productivity ---
    "productivity" = @{
        Name     = "Desktop / Productivity"
        Sub      = "HDR ON | Adaptive VSync | VRR (if enabled)"
        Cat      = "Productivity"
        Desc     = "Multi-monitor browsing/coding. HDR, adaptive sync (VRR if enabled). No power plan change."
        Exes     = @("Code.exe", "devenv.exe", "chrome.exe", "firefox.exe", "msedge.exe", "WindowsTerminal.exe", "idea64.exe")
    }

    # --- Fighting Games: Rivals 2 ---
    "rivals2" = @{
        Name     = "Rivals of Aether 2"
        Sub      = "LLM ON | No Sync (Default)"
        Cat      = "Fighting"
        Desc     = "Default Rivals 2 profile. Minimum-latency no-sync path, Ultimate Performance."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "off"
    }
    "rivals2-offline"   = @{
        Name     = "Rivals 2: Training"
        Sub      = "LLM ON | No Sync | Uncapped"
        Cat      = "Fighting"
        Desc     = "Offline training/combos. LLM ON, no sync, uncapped FPS, Ultimate Performance."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-online"    = @{
        Name     = "Rivals 2: Online"
        Sub      = "LLM ON | Uncapped | Rollback-Safe"
        Cat      = "Fighting"
        Desc     = "Ranked/online. LLM ON (not Ultra), uncapped FPS, max refresh, no VRR. Ultimate Performance."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-streaming" = @{
        Name     = "Rivals 2: Streaming"
        Sub      = "Rollback-Safe | OBS 1080p60"
        Cat      = "Streaming"
        Desc     = "Streaming profile for Rivals 2. OBS settings applied, FSO/MPO ON for multi-monitor."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-tournament-sim-144hz" = @{
        Name     = "Rivals 2: Tournament Sim"
        Sub      = "LLM ON | 144Hz | No VRR"
        Cat      = "Fighting"
        Desc     = "Simulates tournament PCs. 144Hz forced, no G-Sync, no Ultra, Ultimate Performance."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }
    "rivals2-gsync" = @{
        Name     = "Rivals 2: G-SYNC"
        Sub      = "LLM ON | G-SYNC ON | VSync Safety Net"
        Cat      = "Fighting"
        Desc     = "Low latency VRR profile. G-SYNC ON, VSync safety net, auto FPS cap at refresh-3."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "on"
    }
    "rivals2-online-gsync" = @{
        Name     = "Rivals 2: Online G-SYNC"
        Sub      = "G-SYNC ON | Rollback-Safe | VRR"
        Cat      = "Fighting"
        Desc     = "Rollback-safe VRR profile. G-SYNC ON, stability-focused, conservative priority."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
        SyncMode = "on"
    }
    "rivals2-300hz-max" = @{
        Name     = "Rivals 2: 300Hz MAX"
        Sub      = "LLM ON | 300Hz | No Sync"
        Cat      = "Fighting"
        Desc     = "Absolute minimum latency. 300Hz, LLM ON, uncapped, all aggressive opts."
        Exes     = @("Rivals2-Win64-Shipping.exe", "RivalsofAether2.exe", "Rivals2.exe")
    }

    # --- Fighting Games: Melee ---
    "slippi-melee"      = @{
        Name     = "Slippi Melee (Competitive)"
        Sub      = "Competitive | No Sync | Backend-Aware"
        Cat      = "Fighting"
        Desc     = "Latency-first competitive Slippi profile with backend-aware LLM/HAGS and no-sync output."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "off"
    }
    "slippi-melee-console-parity" = @{
        Name     = "Slippi Melee (Console-Parity)"
        Sub      = "Console-Parity | 60Hz + VSync | LLM OFF"
        Cat      = "Fighting"
        Desc     = "Console-style offline profile: 60Hz desktop cadence, VSync ON, and stable frame presentation."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "on"
    }
    "slippi-melee-universal" = @{
        Name     = "Slippi Melee (Universal)"
        Sub      = "Lowest Latency | HAGS ON | No Sync"
        Cat      = "Fighting"
        Desc     = "Absolute minimum latency with HAGS kept on so re-applying does not require a reboot. VSync OFF, G-SYNC/VRR OFF."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "off"
    }
    "slippi-melee-vrr-lab" = @{
        Name     = "Slippi Melee (VRR Lab)"
        Sub      = "VRR Lab | G-SYNC ON | A/B Test"
        Cat      = "Fighting"
        Desc     = "Experimental VRR/G-SYNC path for controlled A/B testing versus competitive no-sync."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
        SyncMode = "on"
    }
    "slippi-melee-streaming" = @{
        Name     = "Slippi Melee (Streaming)"
        Sub      = "OBS 1080p60 | Multi-monitor"
        Cat      = "Streaming"
        Desc     = "Streaming profile for Slippi. OBS settings applied, FSO/MPO ON for multi-monitor."
        Exes     = @("Slippi Dolphin.exe", "Dolphin.exe")
    }

    # --- Fighting Games: SSBU ---
    "ryujinx-ssbu"      = @{
        Name     = "SSBU / HewDraw Remix"
        Sub      = "Vulkan | Fixed 60fps | HAGS ON"
        Cat      = "Fighting"
        Desc     = "Smash Ultimate via Ryujinx/forks. HAGS ON, Vulkan backend, Ultimate Performance."
        Exes     = @("Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe", "Ryubing.exe")
    }
    "ryujinx-ssbu-streaming" = @{
        Name     = "SSBU / HewDraw Remix (Streaming)"
        Sub      = "OBS 1080p60 | Multi-monitor"
        Cat      = "Streaming"
        Desc     = "Streaming profile for Ryujinx/forks. OBS settings applied, FSO/MPO ON for multi-monitor."
        Exes     = @("Ryujinx.exe", "Ryujinx.Ava.exe", "Ryujinx.Headless.SDL2.exe", "Ryubing.exe")
    }

    # --- ARPG ---
    "diablo4"           = @{
        Name     = "Diablo 4"
        Sub      = "HDR ON | Reflex ON+Boost | LLM OFF"
        Cat      = "ARPG"
        Desc     = "Native HDR, Reflex handles latency (LLM OFF). Ultimate Performance plan."
        Exes     = @("Diablo IV.exe")
    }

    # --- Shooter ---
    "cod-bo7"           = @{
        Name     = "CoD: Black Ops 7"
        Sub      = "HDR ON | Reflex ON+Boost | LLM OFF"
        Cat      = "Shooter"
        Desc     = "Reflex handles latency (LLM OFF). HDR, HAGS ON, Ultimate Performance."
        Exes     = @("cod.exe", "BlackOps7.exe")
    }
    "fortnite"          = @{
        Name     = "Fortnite"
        Sub      = "Reflex ON+Boost | LLM OFF | HAGS ON"
        Cat      = "Shooter"
        Desc     = "Competitive Fortnite. Reflex handles latency, max refresh, Ultimate Performance."
        Exes     = @(
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe"
        )
    }
    "marvel-rivals-sdr" = @{
        Name     = "Marvel Rivals - SDR"
        Sub      = "SDR | Reflex ON+Boost | G-SYNC ON"
        Cat      = "Shooter"
        Desc     = "Performance-first SDR Marvel Rivals profile for this 300Hz G-SYNC display. Uses Reflex, VRR, and refresh-3 cap behavior."
        Exes     = @("Marvel.exe", "Marvel-Win64-Shipping.exe")
        SyncMode = "on"
    }
    "marvel-rivals-hdr" = @{
        Name     = "Marvel Rivals - HDR"
        Sub      = "HDR ON | Reflex ON+Boost | G-SYNC ON"
        Cat      = "Shooter"
        Desc     = "Performance-first HDR Marvel Rivals profile for the HDR-capable primary display. Uses Reflex, VRR, and refresh-3 cap behavior."
        Exes     = @("Marvel.exe", "Marvel-Win64-Shipping.exe")
        SyncMode = "on"
    }
    "fortnite-streaming" = @{
        Name     = "Fortnite (Streaming)"
        Sub      = "Reflex ON+Boost | OBS 1080p60"
        Cat      = "Streaming"
        Desc     = "Streaming profile for Fortnite. OBS settings applied, FSO/MPO ON for multi-monitor."
        Exes     = @(
            "FortniteClient-Win64-Shipping.exe",
            "FortniteClient-Win64-Shipping_EAC.exe",
            "FortniteClient-Win64-Shipping_BE.exe",
            "FortniteClient-Win64-Shipping_EAC_EOS.exe"
        )
    }
    "overwatch2"        = @{
        Name     = "Overwatch 2 - No-Sync"
        Sub      = "Reflex OFF | VSync OFF | G-SYNC OFF"
        Cat      = "Shooter"
        Desc     = "Minimum latency profile. No-sync path with VRR explicitly disabled for deterministic behavior."
        Exes     = @("Overwatch.exe")
        SyncMode = "off"
    }
    "overwatch2-gsync"  = @{
        Name     = "Overwatch 2 - GSYNC"
        Sub      = "Reflex ON+Boost | VSync Safety Net | G-SYNC ON"
        Cat      = "Shooter"
        Desc     = "Tear-free low latency VRR profile. Use in-game FPS cap at refresh minus 3."
        Exes     = @("Overwatch.exe")
        SyncMode = "on"
    }
    "overwatch2-gsync-hdr" = @{
        Name     = "Overwatch 2 - GSYNC HDR"
        Sub      = "HDR ON | Reflex ON+Boost | G-SYNC ON"
        Cat      = "Shooter"
        Desc     = "Tear-free low latency VRR with native HDR for OLED/Mini-LED displays."
        Exes     = @("Overwatch.exe")
        SyncMode = "on"
    }

    # --- Browser Games ---
    "pokemon-auto-chess" = @{
        Name     = "Pokemon Auto Chess"
        Sub      = "LLM ON | Browser WebGL"
        Cat      = "Other"
        Desc     = "WebGL browser game. VSync OFF, Ultimate Performance, foreground priority boost."
        Exes     = @("chrome.exe", "msedge.exe", "firefox.exe", "brave.exe")
    }
    "pacdeluxe"         = @{
        Name     = "PACDeluxe (Pokemon Auto Chess)"
        Sub      = "LLM ON | Tauri + WebView2 | Adaptive VSync"
        Cat      = "Other"
        Desc     = "Native Tauri client. Adaptive sync, Ultimate Performance, priority boost."
        Exes     = @("pac-deluxe.exe", "msedgewebview2.exe")
    }
    "pacdeluxe-streaming" = @{
        Name     = "PACDeluxe (Streaming)"
        Sub      = "OBS 1080p60 | Multi-monitor"
        Cat      = "Streaming"
        Desc     = "Streaming profile for PACDeluxe. OBS settings applied, FSO/MPO ON for multi-monitor."
        Exes     = @("pac-deluxe.exe", "msedgewebview2.exe")
    }
}

$script:Profiles = [ordered]@{}
foreach ($id in $script:FallbackProfiles.Keys) {
    $script:Profiles[$id] = $script:FallbackProfiles[$id]
}
$script:ProfileCatalogCacheFile = Join-Path $script:ScriptDir "profile-catalog-cache.json"

function Get-CategoryFromOptimizationTarget {
    param([string]$OptimizationTarget)

    $target = if ($null -eq $OptimizationTarget) { "" } else { "$OptimizationTarget" }
    switch ($target.ToLowerInvariant()) {
        "productivity" { return "Productivity" }
        "low_latency_high_fps" { return "Shooter" }
        "stable_online" { return "Fighting" }
        "stable_online_vrr" { return "Fighting" }
        "minimum_latency" { return "Fighting" }
        "minimum_latency_offline" { return "Fighting" }
        "low_latency_vrr" { return "Fighting" }
        "tournament_simulation" { return "Fighting" }
        "balanced" { return "Other" }
        "smooth_framerate" { return "Other" }
        default { return "Other" }
    }
}

function Copy-ProfileMap {
    param([hashtable]$Source)

    $copy = [ordered]@{}
    if ($Source) {
        foreach ($id in $Source.Keys) {
            $copy[$id] = $Source[$id]
        }
    }
    return $copy
}

function Convert-CatalogEntriesToProfileMap {
    param(
        [object[]]$Entries,
        [hashtable]$FallbackProfiles
    )

    $profiles = [ordered]@{}
    foreach ($entry in @($Entries)) {
        $id = "$($entry.id)"
        if ([string]::IsNullOrWhiteSpace($id)) { continue }

        $fallback = if ($FallbackProfiles -and $FallbackProfiles.Contains($id)) {
            $FallbackProfiles[$id]
        }
        else {
            $null
        }

        $name = if ($entry.display_name) { "$($entry.display_name)" } elseif ($fallback) { "$($fallback.Name)" } else { $id }
        $sub = if ($entry.tray_subtitle) { "$($entry.tray_subtitle)" } elseif ($fallback) { "$($fallback.Sub)" } else { "Profile" }
        $cat = if ($entry.tray_category) {
            "$($entry.tray_category)"
        }
        elseif ($fallback) {
            "$($fallback.Cat)"
        }
        else {
            Get-CategoryFromOptimizationTarget -OptimizationTarget "$($entry.optimization_target)"
        }
        $desc = if ($entry.tray_description) {
            "$($entry.tray_description)"
        }
        elseif ($entry.description) {
            "$($entry.description)"
        }
        elseif ($fallback) {
            "$($fallback.Desc)"
        }
        else {
            ""
        }

        $exeHints = @()
        foreach ($exe in @($entry.executables)) {
            if (-not [string]::IsNullOrWhiteSpace("$exe")) {
                $exeHints += "$exe"
            }
        }
        if ($exeHints.Count -eq 0 -and $fallback) {
            $exeHints = @($fallback.Exes)
        }

        $syncMode = if ($entry.sync_mode) {
            "$($entry.sync_mode)".ToLowerInvariant()
        }
        elseif ($fallback -and $fallback.SyncMode) {
            "$($fallback.SyncMode)".ToLowerInvariant()
        }
        else {
            "agnostic"
        }

        $optTarget = if ($entry.optimization_target) {
            "$($entry.optimization_target)"
        } elseif ($fallback -and $fallback.OptTarget) {
            "$($fallback.OptTarget)"
        } else {
            ""
        }

        $profiles[$id] = @{
            Name      = $name
            Sub       = $sub
            Cat       = $cat
            Desc      = $desc
            Exes      = $exeHints
            SyncMode  = $syncMode
            OptTarget = $optTarget
        }
    }

    return $profiles
}

function Read-ProfileCatalogCacheEntries {
    if (-not $script:ProfileCatalogCacheFile -or -not (Test-Path $script:ProfileCatalogCacheFile)) {
        return @()
    }

    try {
        $cacheRaw = Get-Content $script:ProfileCatalogCacheFile -Raw -ErrorAction Stop
        if (-not $cacheRaw) { return @() }
        $cachePayload = $cacheRaw | ConvertFrom-Json
        if ($cachePayload -and $cachePayload.profiles) {
            return @($cachePayload.profiles)
        }
    }
    catch {
        Write-TrayLog "Profile catalog cache read failed: $($_.Exception.Message)" -Level "WARN"
    }

    return @()
}

function Write-ProfileCatalogCache {
    param([object[]]$Entries)

    if (-not $script:ProfileCatalogCacheFile -or -not $Entries -or $Entries.Count -eq 0) {
        return
    }

    try {
        $payload = [ordered]@{
            version = 1
            saved_at = (Get-Date).ToString("o")
            profiles = @($Entries)
        }
        $dir = Split-Path -Parent $script:ProfileCatalogCacheFile
        if ($dir -and -not (Test-Path $dir)) {
            New-Item -Path $dir -ItemType Directory -Force | Out-Null
        }
        $payload | ConvertTo-Json -Depth 8 | Set-Content -Path $script:ProfileCatalogCacheFile -Encoding UTF8
    }
    catch {
        Write-TrayLog "Profile catalog cache write failed: $($_.Exception.Message)" -Level "WARN"
    }
}

function Initialize-ProfilesFromCliCatalog {
    <#
    .SYNOPSIS
    Loads profile metadata from Python CLI to prevent registry drift.

    If CLI metadata is unavailable, keeps built-in fallback definitions.
    #>
    $fallbackProfiles = if ($script:FallbackProfiles) {
        $script:FallbackProfiles
    }
    else {
        $script:Profiles
    }

    $entries = @()
    $source = "fallback"

    # Primary source: live CLI profile catalog
    if ($script:PythonExe) {
        try {
            $raw = & $script:PythonExe "-m" "abso" "profiles" "--json" 2>$null
            if ($LASTEXITCODE -eq 0 -and $raw) {
                $payload = $raw | ConvertFrom-Json
                if ($payload -and $payload.success -and $payload.data) {
                    $entries = @($payload.data)
                    $source = "cli"
                    Write-ProfileCatalogCache -Entries $entries
                }
                else {
                    Write-TrayLog "Profile catalog payload missing/invalid from CLI; trying cache fallback" -Level "WARN"
                }
            }
            else {
                Write-TrayLog "Profile catalog refresh skipped from CLI (exit=$LASTEXITCODE); trying cache fallback" -Level "WARN"
            }
        }
        catch {
            Write-TrayLog "Profile catalog refresh failed from CLI: $($_.Exception.Message); trying cache fallback" -Level "WARN"
        }
    }
    else {
        Write-TrayLog "Python executable unavailable for profile catalog refresh; trying cache fallback" -Level "WARN"
    }

    # Secondary source: last known-good cached catalog (prevents drift when CLI unavailable)
    if ($entries.Count -eq 0) {
        $cachedEntries = Read-ProfileCatalogCacheEntries
        if ($cachedEntries.Count -gt 0) {
            $entries = @($cachedEntries)
            $source = "cache"
        }
    }

    if ($entries.Count -gt 0) {
        $resolved = Convert-CatalogEntriesToProfileMap -Entries $entries -FallbackProfiles $fallbackProfiles
        if ($resolved.Count -gt 0) {
            $script:Profiles = $resolved
            Write-TrayLog "Profile catalog loaded from $source ($($resolved.Count) profiles)"
            return
        }

        Write-TrayLog "Resolved profile catalog from $source is empty; using built-in fallback definitions" -Level "WARN"
    }

    # Final source: built-in emergency fallback map in this script
    $script:Profiles = Copy-ProfileMap -Source $fallbackProfiles
    Write-TrayLog "Profile catalog using built-in fallback definitions ($($script:Profiles.Count) profiles)" -Level "WARN"
}

Initialize-ProfilesFromCliCatalog

# Preferred order for known categories; any new ones sort alphabetically after
$preferredCategoryOrder = @("Productivity", "Fighting", "ARPG", "Shooter", "Streaming", "Other")
$allCategories = $script:Profiles.Values | ForEach-Object { $_.Cat } | Select-Object -Unique
$script:CategoryOrder = @()
foreach ($cat in $preferredCategoryOrder) {
    if ($allCategories -contains $cat) { $script:CategoryOrder += $cat }
}
foreach ($cat in ($allCategories | Sort-Object)) {
    if ($script:CategoryOrder -notcontains $cat) { $script:CategoryOrder += $cat }
}
$script:CategoryColors = @{
    "Productivity" = $script:Colors.CatProd
    "Fighting"     = $script:Colors.CatFighting
    "ARPG"         = $script:Colors.CatARPG
    "Shooter"      = $script:Colors.CatShooter
    "Streaming"    = $script:Colors.CatStreaming
    "Other"        = $script:Colors.CatOther
}

# ============================================================================
# COLOR HELPERS
# ============================================================================

function Get-CategoryColor {
    param(
        [string]$Category,
        [System.Drawing.Color]$Fallback = $script:Colors.Text
    )
    if ($Category -and $script:CategoryColors.ContainsKey($Category)) {
        return $script:CategoryColors[$Category]
    }
    return $Fallback
}

function Blend-Color {
    param(
        [System.Drawing.Color]$Base,
        [System.Drawing.Color]$Overlay,
        [double]$Ratio = 0.2
    )
    $ratio = [Math]::Max(0.0, [Math]::Min(1.0, $Ratio))
    $r = [int]([Math]::Round($Base.R * (1 - $ratio) + $Overlay.R * $ratio))
    $g = [int]([Math]::Round($Base.G * (1 - $ratio) + $Overlay.G * $ratio))
    $b = [int]([Math]::Round($Base.B * (1 - $ratio) + $Overlay.B * $ratio))
    return [System.Drawing.Color]::FromArgb(255, $r, $g, $b)
}

function Dim-Color {
    param(
        [System.Drawing.Color]$Color,
        [int]$Alpha = 200
    )
    $alpha = [Math]::Max(0, [Math]::Min(255, $Alpha))
    return [System.Drawing.Color]::FromArgb($alpha, $Color.R, $Color.G, $Color.B)
}

# ============================================================================
# CUSTOM DARK THEME RENDERER (ToolStripRenderer)
# ============================================================================

Add-Type -TypeDefinition @"
using System;
using System.Drawing;
using System.Drawing.Drawing2D;
using System.Windows.Forms;

public class DarkThemeRenderer : ToolStripProfessionalRenderer
{
    // Core dark palette
    private static readonly Color BgColor = Color.FromArgb(255, 26, 26, 30);
    private static readonly Color BgDark = Color.FromArgb(255, 20, 20, 24);
    private static readonly Color BgSubtle = Color.FromArgb(255, 32, 32, 36);
    private static readonly Color SepColor = Color.FromArgb(255, 44, 44, 52);
    private static readonly Color BorderColor = Color.FromArgb(255, 50, 50, 58);
    private static readonly Color AccentGold = Color.FromArgb(255, 230, 190, 70);
    private static readonly Color AccentGoldDim = Color.FromArgb(60, 230, 190, 70);

    public DarkThemeRenderer() : base(new DarkColorTable()) { }

    // Paint the entire menu background with a subtle vertical gradient
    protected override void OnRenderToolStripBackground(ToolStripRenderEventArgs e)
    {
        try
        {
            var g = e.Graphics;
            var bounds = e.AffectedBounds;
            if (bounds.Width < 1 || bounds.Height < 1) { base.OnRenderToolStripBackground(e); return; }
            using (var brush = new LinearGradientBrush(
                bounds, BgSubtle, BgColor, LinearGradientMode.Vertical))
            {
                var blend = new ColorBlend(3);
                blend.Colors = new Color[] { BgSubtle, BgColor, BgDark };
                blend.Positions = new float[] { 0f, 0.15f, 1f };
                brush.InterpolationColors = blend;
                g.FillRectangle(brush, bounds);
            }
        }
        catch { base.OnRenderToolStripBackground(e); }
    }

    // Paint the menu border with accent and subtle inner shadow
    protected override void OnRenderToolStripBorder(ToolStripRenderEventArgs e)
    {
        try
        {
            var g = e.Graphics;
            int w = e.ToolStrip.Width;
            int h = e.ToolStrip.Height;
            if (w < 2 || h < 2) return;

            // Outer border
            using (var pen = new Pen(BorderColor, 1f))
            {
                g.DrawRectangle(pen, 0, 0, w - 1, h - 1);
            }

            // Top accent gradient line (gold, bright center, fading edges)
            using (var brush = new LinearGradientBrush(
                new Point(0, 0), new Point(Math.Max(1, w), 0),
                Color.FromArgb(0, AccentGold.R, AccentGold.G, AccentGold.B),
                Color.FromArgb(0, AccentGold.R, AccentGold.G, AccentGold.B)))
            {
                var blend = new ColorBlend(5);
                blend.Colors = new Color[] {
                    Color.FromArgb(10, AccentGold.R, AccentGold.G, AccentGold.B),
                    Color.FromArgb(160, AccentGold.R, AccentGold.G, AccentGold.B),
                    Color.FromArgb(220, AccentGold.R, AccentGold.G, AccentGold.B),
                    Color.FromArgb(160, AccentGold.R, AccentGold.G, AccentGold.B),
                    Color.FromArgb(10, AccentGold.R, AccentGold.G, AccentGold.B)
                };
                blend.Positions = new float[] { 0f, 0.2f, 0.5f, 0.8f, 1f };
                brush.InterpolationColors = blend;
                using (var pen = new Pen(brush, 2f))
                {
                    g.DrawLine(pen, 1, 0, w - 2, 0);
                }
            }

            // Subtle inner highlight along top (gives depth)
            using (var pen = new Pen(Color.FromArgb(8, 255, 255, 255), 1f))
            {
                g.DrawLine(pen, 1, 1, w - 2, 1);
            }
        }
        catch {}
    }

    // Paint item backgrounds with richer hover highlighting
    protected override void OnRenderMenuItemBackground(ToolStripItemRenderEventArgs e)
    {
        var g = e.Graphics;
        g.SmoothingMode = SmoothingMode.AntiAlias;
        int w = e.Item.Width;
        int h = e.Item.Height;
        if (w < 2 || h < 2) return; // guard against zero-size layout passes
        var rect = new Rectangle(3, 1, w - 6, h - 2);

        try
        {
            // --- Hero Banner: active profile status item ---
            var tag = e.Item.Tag as string;
            if (tag == "__hero_banner__")
            {
                Color tint = e.Item.ForeColor;
                // Full-width gradient background in category color (alpha 20 -> 8)
                var fullRect = new Rectangle(0, 0, w, h);
                using (var brush = new LinearGradientBrush(
                    new Rectangle(0, 0, Math.Max(1, w), Math.Max(1, h)),
                    Color.FromArgb(20, tint.R, tint.G, tint.B),
                    Color.FromArgb(8, tint.R, tint.G, tint.B),
                    LinearGradientMode.Horizontal))
                {
                    g.FillRectangle(brush, fullRect);
                }

                // 4px left accent bar (full alpha, rounded)
                int barH = h - 12;
                if (barH > 2)
                {
                    using (var brush = new SolidBrush(Color.FromArgb(220, tint.R, tint.G, tint.B)))
                    {
                        FillRoundRect(g, brush, new Rectangle(2, 6, 4, barH), 2);
                    }
                }

                // Glowing dot (10px circle with outer glow ring)
                int dotX = 12;
                int dotY = (h / 2) - 5;
                using (var glowBrush = new SolidBrush(Color.FromArgb(35, tint.R, tint.G, tint.B)))
                {
                    g.FillEllipse(glowBrush, dotX - 3, dotY - 3, 16, 16);
                }
                using (var dotBrush = new SolidBrush(Color.FromArgb(200, tint.R, tint.G, tint.B)))
                {
                    g.FillEllipse(dotBrush, dotX, dotY, 10, 10);
                }
                using (var specBrush = new SolidBrush(Color.FromArgb(80, 255, 255, 255)))
                {
                    g.FillEllipse(specBrush, dotX + 2, dotY + 1, 4, 3);
                }

                // Render text manually (profile name + subtitle)
                string text = e.Item.Text ?? "";
                string[] parts = text.Split('|');
                string name = parts.Length > 0 ? parts[0].Trim() : "";
                string subtitle = parts.Length > 1 ? parts[1].Trim() : "";

                g.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;

                int textX = 28;
                // Profile name in 10pt Bold, bright category color
                Color brightTint = Color.FromArgb(255,
                    Math.Min(255, tint.R + 40),
                    Math.Min(255, tint.G + 40),
                    Math.Min(255, tint.B + 40));
                using (var font = new Font("Segoe UI", 10f, FontStyle.Bold))
                using (var brush = new SolidBrush(brightTint))
                {
                    g.DrawString(name, font, brush, textX, 6);
                }

                // Subtitle in 7.5pt, dimmed category color
                if (!string.IsNullOrEmpty(subtitle))
                {
                    Color dimTint = Color.FromArgb(160, tint.R, tint.G, tint.B);
                    using (var font = new Font("Segoe UI", 7.5f))
                    using (var brush = new SolidBrush(dimTint))
                    {
                        g.DrawString(subtitle, font, brush, textX, 26);
                    }
                }
                return;
            }

            // --- Section headers: disabled + bold items (category headers) ---
            if (!e.Item.Enabled && e.Item.Font != null && e.Item.Font.Bold)
            {
                Color tint = e.Item.ForeColor;

                // Gradient background: category color alpha 18 -> 0
                using (var brush = new LinearGradientBrush(
                    new Rectangle(0, 0, Math.Max(1, w), Math.Max(1, h)),
                    Color.FromArgb(18, tint.R, tint.G, tint.B),
                    Color.FromArgb(0, tint.R, tint.G, tint.B),
                    LinearGradientMode.Horizontal))
                {
                    g.FillRectangle(brush, 0, 0, w, h);
                }

                // Bottom accent line: category color alpha 40
                using (var pen = new Pen(Color.FromArgb(40, tint.R, tint.G, tint.B), 1f))
                {
                    int lineY = h - 1;
                    g.DrawLine(pen, 28, lineY, w - 8, lineY);
                }
                return;
            }

            if (e.Item.Selected && e.Item.Enabled)
            {
                Color tint = e.Item.ForeColor;

                if (rect.Width > 0 && rect.Height > 0)
                {
                    // Gradient fill: category-tinted with subtle horizontal gradient
                    using (var brush = new LinearGradientBrush(
                        rect, Color.FromArgb(35, tint.R, tint.G, tint.B),
                        Color.FromArgb(12, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        FillRoundRect(g, brush, rect, 5);
                    }

                    // Subtle border
                    using (var pen = new Pen(Color.FromArgb(40, tint.R, tint.G, tint.B), 1f))
                    {
                        DrawRoundRect(g, pen, rect, 5);
                    }
                }

                // Left accent bar with vertical gradient (full alpha center, fading top/bottom)
                var barRect = new Rectangle(3, rect.Y + 2, 3, rect.Height - 4);
                if (barRect.Width > 0 && barRect.Height > 2)
                {
                    using (var brush = new LinearGradientBrush(
                        barRect,
                        Color.FromArgb(60, tint.R, tint.G, tint.B),
                        Color.FromArgb(60, tint.R, tint.G, tint.B),
                        LinearGradientMode.Vertical))
                    {
                        var blend = new ColorBlend(3);
                        blend.Colors = new Color[] {
                            Color.FromArgb(60, tint.R, tint.G, tint.B),
                            Color.FromArgb(220, tint.R, tint.G, tint.B),
                            Color.FromArgb(60, tint.R, tint.G, tint.B)
                        };
                        blend.Positions = new float[] { 0f, 0.5f, 1f };
                        brush.InterpolationColors = blend;
                        FillRoundRect(g, brush, barRect, 1);
                    }
                }

                // Soft circle glow behind the image area (icon glow)
                using (var brush = new SolidBrush(Color.FromArgb(20, tint.R, tint.G, tint.B)))
                {
                    g.FillEllipse(brush, 2, rect.Y - 2, 28, rect.Height + 4);
                }

                // Subtle glow on the left edge
                using (var brush = new SolidBrush(Color.FromArgb(15, tint.R, tint.G, tint.B)))
                {
                    g.FillRectangle(brush, 3, rect.Y, 30, rect.Height);
                }

                // Right-edge gradient fade for card depth
                int fadeW = 30;
                var fadeRect = new Rectangle(w - fadeW, rect.Y, fadeW, rect.Height);
                if (fadeRect.Width > 0 && fadeRect.Height > 0)
                {
                    using (var brush = new LinearGradientBrush(
                        fadeRect,
                        Color.FromArgb(0, tint.R, tint.G, tint.B),
                        Color.FromArgb(8, tint.R, tint.G, tint.B),
                        LinearGradientMode.Horizontal))
                    {
                        g.FillRectangle(brush, fadeRect);
                    }
                }
            }
            else if (e.Item.Pressed)
            {
                if (rect.Width > 0 && rect.Height > 0)
                {
                    using (var brush = new SolidBrush(Color.FromArgb(25, 255, 255, 255)))
                    {
                        FillRoundRect(g, brush, rect, 5);
                    }
                }
            }
        }
        catch
        {
            // Silently swallow GDI+ rendering errors to prevent .NET popups
        }
    }

    // Custom dark separators with elegant gradient fade
    protected override void OnRenderSeparator(ToolStripSeparatorRenderEventArgs e)
    {
        try
        {
            int y = e.Item.Height / 2;
            var g = e.Graphics;
            int w = e.Item.Width;
            if (w <= 42) { base.OnRenderSeparator(e); return; }

            using (var brush = new LinearGradientBrush(
                new Point(20, y), new Point(w - 20, y),
                Color.Transparent, Color.Transparent))
            {
                var blend = new ColorBlend(5);
                blend.Colors = new Color[] {
                    Color.FromArgb(0, SepColor.R, SepColor.G, SepColor.B),
                    Color.FromArgb(60, SepColor.R, SepColor.G, SepColor.B),
                    Color.FromArgb(80, SepColor.R, SepColor.G, SepColor.B),
                    Color.FromArgb(60, SepColor.R, SepColor.G, SepColor.B),
                    Color.FromArgb(0, SepColor.R, SepColor.G, SepColor.B)
                };
                blend.Positions = new float[] { 0f, 0.2f, 0.5f, 0.8f, 1f };
                brush.InterpolationColors = blend;
                using (var pen = new Pen(brush, 1f))
                {
                    g.DrawLine(pen, 20, y, w - 20, y);
                }
            }
        }
        catch { base.OnRenderSeparator(e); }
    }

    // Custom checked item: glowing dot with ring
    protected override void OnRenderItemCheck(ToolStripItemImageRenderEventArgs e)
    {
        try
        {
            var g = e.Graphics;
            g.SmoothingMode = SmoothingMode.AntiAlias;
            var r = e.ImageRectangle;
            Color dotColor = e.Item.ForeColor;

            // Outer glow ring
            using (var brush = new SolidBrush(Color.FromArgb(30, dotColor.R, dotColor.G, dotColor.B)))
            {
                g.FillEllipse(brush, r.X, r.Y, 12, 12);
            }
            // Inner solid dot
            using (var brush = new SolidBrush(dotColor))
            {
                g.FillEllipse(brush, r.X + 2, r.Y + 2, 8, 8);
            }
            // Specular highlight
            using (var brush = new SolidBrush(Color.FromArgb(60, 255, 255, 255)))
            {
                g.FillEllipse(brush, r.X + 3, r.Y + 3, 4, 3);
            }
        }
        catch {}
    }

    // Dark image margin (skip default rendering)
    protected override void OnRenderImageMargin(ToolStripRenderEventArgs e)
    {
        // Intentionally empty - keeps the entire background dark
    }

    // Override text rendering for cleaner anti-aliasing
    protected override void OnRenderItemText(ToolStripItemTextRenderEventArgs e)
    {
        // Skip default text rendering for hero banner items (text is painted in background pass)
        var tag = e.Item.Tag as string;
        if (tag == "__hero_banner__") return;

        e.Graphics.TextRenderingHint = System.Drawing.Text.TextRenderingHint.ClearTypeGridFit;
        base.OnRenderItemText(e);
    }

    // Helper: Fill rounded rectangle
    private static void FillRoundRect(Graphics g, Brush brush, Rectangle r, int radius)
    {
        using (var path = RoundRectPath(r, radius))
        {
            g.FillPath(brush, path);
        }
    }

    // Helper: Draw rounded rectangle
    private static void DrawRoundRect(Graphics g, Pen pen, Rectangle r, int radius)
    {
        using (var path = RoundRectPath(r, radius))
        {
            g.DrawPath(pen, path);
        }
    }

    private static GraphicsPath RoundRectPath(Rectangle r, int radius)
    {
        int d = radius * 2;
        var path = new GraphicsPath();
        path.AddArc(r.X, r.Y, d, d, 180, 90);
        path.AddArc(r.Right - d, r.Y, d, d, 270, 90);
        path.AddArc(r.Right - d, r.Bottom - d, d, d, 0, 90);
        path.AddArc(r.X, r.Bottom - d, d, d, 90, 90);
        path.CloseFigure();
        return path;
    }
}

public class DarkColorTable : ProfessionalColorTable
{
    public override Color MenuBorder { get { return Color.FromArgb(255, 50, 50, 58); } }
    public override Color MenuItemBorder { get { return Color.Transparent; } }
    public override Color MenuItemSelected { get { return Color.FromArgb(255, 42, 42, 48); } }
    public override Color MenuItemSelectedGradientBegin { get { return Color.FromArgb(255, 38, 38, 44); } }
    public override Color MenuItemSelectedGradientEnd { get { return Color.FromArgb(255, 38, 38, 44); } }
    public override Color MenuItemPressedGradientBegin { get { return Color.FromArgb(255, 34, 34, 40); } }
    public override Color MenuItemPressedGradientEnd { get { return Color.FromArgb(255, 34, 34, 40); } }
    public override Color MenuStripGradientBegin { get { return Color.FromArgb(255, 26, 26, 30); } }
    public override Color MenuStripGradientEnd { get { return Color.FromArgb(255, 26, 26, 30); } }
    public override Color ToolStripDropDownBackground { get { return Color.FromArgb(255, 26, 26, 30); } }
    public override Color ImageMarginGradientBegin { get { return Color.FromArgb(255, 26, 26, 30); } }
    public override Color ImageMarginGradientMiddle { get { return Color.FromArgb(255, 26, 26, 30); } }
    public override Color ImageMarginGradientEnd { get { return Color.FromArgb(255, 26, 26, 30); } }
    public override Color SeparatorDark { get { return Color.FromArgb(255, 44, 44, 52); } }
    public override Color SeparatorLight { get { return Color.Transparent; } }
    public override Color CheckBackground { get { return Color.FromArgb(255, 38, 38, 44); } }
    public override Color CheckSelectedBackground { get { return Color.FromArgb(255, 48, 48, 55); } }
    public override Color CheckPressedBackground { get { return Color.FromArgb(255, 34, 34, 40); } }
}
"@ -ReferencedAssemblies System.Windows.Forms,System.Drawing -ErrorAction SilentlyContinue

# ============================================================================
# ICON STATE MANAGEMENT
# ============================================================================

# Cached shared fonts (disposed in finally block)
$script:FontNormal = New-Object System.Drawing.Font("Segoe UI", 9)
$script:FontBold = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)

$script:IconState = "Idle"
$script:ApplyAnimTimer = $null
$script:StartupIconHealTimer = $null
$script:StartupIconHealAttempts = 0

function Set-IconSafe {
    <#
    .SYNOPSIS
    Safely swaps the tray icon, disposing the old one only after the new one is assigned.
    #>
    param([System.Drawing.Icon]$NewIcon)

    if (-not $script:notifyIcon -or -not $NewIcon) { return }
    $oldIcon = $script:notifyIcon.Icon
    $script:notifyIcon.Icon = $NewIcon
    # Dispose old icon AFTER new one is assigned — prevents race with animation timer
    if ($oldIcon -and $oldIcon -ne $NewIcon) {
        try { $oldIcon.Dispose() } catch {}
    }
}

function Set-IconState {
    <#
    .SYNOPSIS
    Sets the tray icon to a named state with appropriate visual.
    #>
    param(
        [ValidateSet("Idle", "Active", "Gaming", "Applying", "Warning", "Error")]
        [string]$State
    )

    $script:IconState = $State

    # Stop animation first to prevent timer tick racing
    if ($script:ApplyAnimTimer) {
        $script:ApplyAnimTimer.Stop()
    }
    $newIcon = New-StateIcon -State $State
    Set-IconSafe -NewIcon $newIcon
}

function Invoke-NotifyIconRefresh {
    <#
    .SYNOPSIS
    Re-registers the tray icon with Explorer to recover from shell startup races.
    #>
    param([string]$Reason = "runtime")

    if (-not $script:notifyIcon) { return }

    try {
        $state = if ($script:IconState) { $script:IconState } else { "Idle" }
        $freshIcon = New-StateIcon -State $state
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::DoEvents()
        Start-Sleep -Milliseconds 120
        Set-IconSafe -NewIcon $freshIcon
        $script:notifyIcon.Visible = $true
        Write-TrayLog "Notify icon refreshed ($Reason)"
    }
    catch {
        Write-TrayLog "Notify icon refresh failed ($Reason): $($_.Exception.Message)" -Level "WARN"
    }
}

function Start-StartupIconSelfHeal {
    <#
    .SYNOPSIS
    Performs a few delayed icon refreshes after startup.
    #>
    if ($script:StartupIconHealTimer) {
        try { $script:StartupIconHealTimer.Stop() } catch {}
        try { $script:StartupIconHealTimer.Dispose() } catch {}
    }

    $script:StartupIconHealAttempts = 0
    $script:StartupIconHealTimer = New-Object System.Windows.Forms.Timer
    $script:StartupIconHealTimer.Interval = 7000
    $script:StartupIconHealTimer.Add_Tick({
        try {
            $script:StartupIconHealAttempts++
            Invoke-NotifyIconRefresh -Reason "startup-heal-$($script:StartupIconHealAttempts)"
        }
        catch { try { Write-TrayLog "StartupIconHealTimer tick error: $($_.Exception.Message)" -Level "WARN" } catch {} }
        finally {
            if ($script:StartupIconHealAttempts -ge 3 -and $script:StartupIconHealTimer) {
                try { $script:StartupIconHealTimer.Stop() } catch {}
            }
        }
    })
    $script:StartupIconHealTimer.Start()
}

function Wait-ExplorerShellReady {
    <#
    .SYNOPSIS
    Waits briefly for explorer.exe in this session before registering NotifyIcon.
    #>
    param([int]$TimeoutSeconds = 45)

    try {
        $sessionId = (Get-Process -Id $PID -ErrorAction SilentlyContinue).SessionId
        $deadline = (Get-Date).AddSeconds($TimeoutSeconds)
        while ((Get-Date) -lt $deadline) {
            $explorer = Get-Process -Name explorer -ErrorAction SilentlyContinue |
                Where-Object { $_.SessionId -eq $sessionId } |
                Select-Object -First 1
            if ($explorer) {
                return $true
            }
            Start-Sleep -Milliseconds 400
        }
    }
    catch {}

    return $false
}

function Play-ApplySuccessIconAnimation {
    <#
    .SYNOPSIS
    Plays "Pokeball -> pop -> Swampert" confirmation sequence, then stays on Active.
    #>
    try {
        $frames = Get-ApplySuccessIcons
        if (-not $frames -or $frames.Count -lt 2) {
            Set-IconState -State "Active"
            return
        }

        $script:IconState = "Active"

        # Keep timings short so UX stays snappy.
        $durations = @(110, 120, 160)
        $maxStep = [Math]::Min($durations.Count, $frames.Count - 1)
        for ($i = 0; $i -lt $maxStep; $i++) {
            Set-IconSafe -NewIcon $frames[$i]
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds $durations[$i]
        }

        # Final frame is the steady active icon (Swampert)
        Set-IconSafe -NewIcon $frames[$frames.Count - 1]
    }
    catch {
        Write-TrayLog "Play-ApplySuccessIconAnimation failed: $($_.Exception.Message)" -Level "WARN"
        Set-IconState -State "Active"
    }
}

# ============================================================================
# APPLY / RESTORE
# ============================================================================

function Apply-Profile {
    param([string]$ProfileId)

    Write-TrayLog "Apply-Profile called with: $ProfileId"
    $profile = $script:Profiles[$ProfileId]
    $previousProfileId = $script:activeProfile
    $needsNoSyncOsdReminder = Test-NeedsNoSyncOsdReminder -FromProfileId $previousProfileId -ToProfileId $ProfileId

    if (-not $profile) {
        Write-TrayLog "Profile not found: $ProfileId" -Level "ERROR"
        Play-FailSound
        Set-IconState -State "Error"
        Show-Notification -Title "A.B.S.O." -Message "Profile not found: $ProfileId" -Type "Error"
        return
    }

    # Show applying state
    Set-IconState -State "Applying"
    $script:notifyIcon.Text = "A.B.S.O. - Applying..."

    # Show progress overlay
    Show-ProgressOverlay -Title "Applying $($profile.Name)" -StepText "Initializing..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"

        Update-ProgressOverlay -StepText "Running profile application..."

        Write-TrayLog "Running: $($script:PythonExe) -m abso apply $ProfileId --json"
        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList "-m", "abso", "apply", $ProfileId, "--json" `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile

        # Poll instead of -Wait so the UI thread message pump stays alive
        $timeout = (Get-Date).AddSeconds(120)
        while (-not $proc.HasExited -and (Get-Date) -lt $timeout) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }
        if (-not $proc.HasExited) {
            Write-TrayLog "Apply-Profile timed out after 120s, killing process" -Level "ERROR"
            $proc.Kill()
            $proc.Dispose()
            Close-ProgressOverlay
            Play-FailSound
            Set-IconState -State "Error"
            Show-Notification -Title "A.B.S.O." -Message "Apply timed out after 120s" -Type "Error"
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Remove-Item $errFile -Force -ErrorAction SilentlyContinue
            return
        }
        $proc.Dispose()

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        Write-TrayLog "CLI output: $rawOutput"
        if ($errOutput) { Write-TrayLog "CLI stderr: $errOutput" -Level "WARN" }

        if (-not $rawOutput) { throw "No output from CLI" }

        $json = $rawOutput | ConvertFrom-Json

        # Treat as success if either fully successful or has applied settings (partial success)
        $hasAppliedSettings = $json.data.applied_settings -and $json.data.applied_settings.Count -gt 0
        if (($json.success -and $json.data.success) -or $hasAppliedSettings) {
            $msg = "$($profile.Name) ($($profile.Sub))"
            if ($json.data.requires_reboot) { $msg += " - Restart required" }

            # Check for partial failures in individual handlers
            $failedHandlers = @()
            if ($json.data.results) {
                foreach ($r in $json.data.results) {
                    if ($r.status -and $r.status -ne "success" -and $r.status -ne "skipped") {
                        $failedHandlers += $r.handler
                    }
                }
            }
            if ($failedHandlers.Count -gt 0) {
                $msg += " (partial: $($failedHandlers -join ', ') failed)"
                Write-TrayLog "Profile applied with partial failures: $($failedHandlers -join ', ')" -Level "WARN"
            }
            else {
                Write-TrayLog "Profile applied successfully: $ProfileId"
            }

            Update-ProgressOverlay -StepText "Profile applied successfully!"
            Start-Sleep -Milliseconds 500
            Close-ProgressOverlay

            if ($needsNoSyncOsdReminder) {
                $msg += " | Reminder: Turn OFF Adaptive Sync/FreeSync in monitor OSD for strict No-Sync mode."
                Play-VrrWarningSound
                Write-TrayLog "No-Sync OSD reminder shown for transition: $previousProfileId -> $ProfileId"
                Play-ApplySuccessIconAnimation
                Show-ThemedToast -Title "A.B.S.O." -Message $msg -Type "Warning" -Duration 6000
            }
            else {
                Play-SuccessSound
                Play-ApplySuccessIconAnimation
                Show-ThemedToast -Title "A.B.S.O." -Message $msg -Type "Success"
            }

            $script:activeProfile = $ProfileId
            $script:LastAction = "Applied: $($profile.Name)"
            $script:LastActionTime = Get-Date -Format "HH:mm"

            # Power plan switching: save current plan and switch to gaming plan
            # if this profile has a power_plan_on_launch metadata field.
            try {
                $powerPlan = $profile.power_plan_on_launch
                if (-not $powerPlan) {
                    # Default: competitive profiles use Ultimate Performance
                    $opt = $profile.OptTarget
                    if ($opt -and ($opt -match "latency|fps|tournament")) {
                        $powerPlan = "ultimate_performance"
                    }
                }
                if ($powerPlan) {
                    # Save current plan for restoration
                    $currentPlan = (powercfg /getactivescheme 2>$null) -replace '.*GUID:\s*(\S+).*','$1'
                    if ($currentPlan -and $currentPlan -match '^[0-9a-f\-]+$') {
                        $stateFile = Join-Path $script:ProjectRoot ".power_switcher_state.json"
                        @{ pre_game_plan_guid = $currentPlan; game_plan_name = $powerPlan; game_exe = $ProfileId } |
                            ConvertTo-Json | Set-Content $stateFile -Encoding UTF8
                        Write-TrayLog "Saved pre-game power plan: $currentPlan"
                    }
                    # Find and activate the gaming plan
                    $plans = powercfg /list 2>$null
                    $targetGuid = $null
                    foreach ($line in $plans) {
                        if ($line -match "ultimate" -and $line -match '(\{?[0-9a-f\-]+\}?)') {
                            $targetGuid = $Matches[1] -replace '[{}]',''
                            break
                        }
                    }
                    if ($targetGuid) {
                        powercfg /setactive $targetGuid 2>$null
                        Write-TrayLog "Switched to power plan: $powerPlan ($targetGuid)"
                    }
                }
            } catch {
                Write-TrayLog "Power plan switch failed: $($_.Exception.Message)" -Level "WARN"
            }

            # Record in history and persist the last known active state for startup arbitration.
            $script:TrayConfig = Add-ProfileHistory -ProfileId $ProfileId -ProfileName $profile.Name -Config $script:TrayConfig

            Update-MenuState
            Update-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -OnApply { param($id) Apply-Profile $id }
        }
        else {
            $err = if ($json.error) {
                $json.error
            }
            elseif ($json.data -and $json.data.error) {
                $json.data.error
            }
            else {
                "Unknown error"
            }
            Write-TrayLog "Profile apply failed: $err" -Level "ERROR"
            Close-ProgressOverlay
            $isVrrPrereqError = Test-IsVrrPrerequisiteError -Message $err
            if ($isVrrPrereqError) {
                Play-VrrWarningSound
            }
            else {
                Play-FailSound
            }
            Set-IconState -State "Error"
            $notifyType = if ($isVrrPrereqError) { "Warning" } else { "Error" }
            Show-Notification -Title "A.B.S.O." -Message "Failed: $err" -Type $notifyType
            $script:LastAction = "Failed: $err"
            $script:LastActionTime = Get-Date -Format "HH:mm"
            Update-MenuState
        }
    }
    catch {
        Write-TrayLog "Apply-Profile exception: $($_.Exception.Message)" -Level "ERROR"
        Close-ProgressOverlay
        Play-FailSound
        Set-IconState -State "Error"
        Show-Notification -Title "A.B.S.O." -Message "Error: $($_.Exception.Message)" -Type "Error"
        $script:LastAction = "Error: $($_.Exception.Message)"
        $script:LastActionTime = Get-Date -Format "HH:mm"
        Update-MenuState
    }
}

function Restore-Settings {
    Set-IconState -State "Applying"
    $script:notifyIcon.Text = "A.B.S.O. - Restoring..."
    Show-ProgressOverlay -Title "Restoring Settings" -StepText "Restoring previous configuration..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"

        $proc = Start-Process -FilePath $script:PythonExe -ArgumentList "-m", "abso", "restore", "latest", "--json" `
            -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile

        $timeout = (Get-Date).AddSeconds(120)
        while (-not $proc.HasExited -and (Get-Date) -lt $timeout) {
            [System.Windows.Forms.Application]::DoEvents()
            Start-Sleep -Milliseconds 100
        }
        if (-not $proc.HasExited) {
            Write-TrayLog "Restore-Settings timed out after 120s, killing process" -Level "ERROR"
            $proc.Kill()
            $proc.Dispose()
            Close-ProgressOverlay
            Show-Notification -Title "A.B.S.O." -Message "Restore timed out after 120s" -Type "Error"
            Set-IconState -State "Error"
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            Remove-Item $errFile -Force -ErrorAction SilentlyContinue
            return
        }
        $proc.Dispose()

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue

        if (-not $rawOutput) { throw "No output" }

        $json = $rawOutput | ConvertFrom-Json

        if ($json.success) {
            Close-ProgressOverlay
            Show-Notification -Title "A.B.S.O." -Message "Settings restored" -Type "Info"
            $script:activeProfile = $null
            $script:LastAction = "Restored settings"
            $script:LastActionTime = Get-Date -Format "HH:mm"
            $script:TrayConfig = Set-LastProfileState -Config $script:TrayConfig -Status "restored" -Source "tray_restore"
            Set-IconState -State "Idle"
            Update-MenuState
        }
        else {
            Close-ProgressOverlay
            Show-Notification -Title "A.B.S.O." -Message "Failed: $($json.error)" -Type "Warning"
            Set-IconState -State "Warning"
        }
    }
    catch {
        Close-ProgressOverlay
        Show-Notification -Title "A.B.S.O." -Message "Error: $($_.Exception.Message)" -Type "Warning"
        Set-IconState -State "Error"
    }
    $script:notifyIcon.Text = "A.B.S.O."
}

# ============================================================================
# MENU STATE
# ============================================================================

function Update-MenuState {
    foreach ($item in $script:profileMenuItems) {
        $isActive = ($item.Tag -eq $script:activeProfile)
        $item.Checked = $isActive

        $p = $script:Profiles[$item.Tag]
        if (-not $p) { continue }
        $catColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.Text

        # Items inside submenus (OwnerItem is a ToolStripMenuItem) vs top-level items
        $inSubmenu = ($null -ne $item.OwnerItem -and $item.OwnerItem -is [System.Windows.Forms.ToolStripMenuItem])

        try {
            if ($isActive) {
                $item.Text = $p.Name
                $item.Image = New-ActiveCheckBitmap -Color $catColor
                $item.ForeColor = [System.Drawing.Color]::FromArgb(
                    255,
                    [Math]::Min(255, $catColor.R + 30),
                    [Math]::Min(255, $catColor.G + 30),
                    [Math]::Min(255, $catColor.B + 30)
                )
                $item.Font = $script:FontBold
                $item.BackColor = Blend-Color -Base $script:Colors.Background -Overlay $catColor -Ratio 0.15
            }
            else {
                $item.Text = $p.Name
                $item.Image = New-CategoryBitmap -Category $p.Cat -Color $catColor
                $item.ForeColor = $catColor
                $item.Font = $script:FontNormal
                $item.BackColor = $script:Colors.Background
            }
        }
        catch {
            Write-TrayLog "Update-MenuState icon error for $($item.Tag): $($_.Exception.Message)" -Level "ERROR"
        }
    }
    if ($script:restoreItem) { $script:restoreItem.Enabled = ($null -ne $script:activeProfile) }

    if ($script:activeProfile) {
        $p = $script:Profiles[$script:activeProfile]
        $tooltipText = "A.B.S.O. - $($p.Name)"
        if ($tooltipText.Length -gt 63) {
            $tooltipText = $tooltipText.Substring(0, 60) + "..."
        }
        $script:notifyIcon.Text = $tooltipText

        if ($script:statusItem) {
            $script:statusItem.Text = "$($p.Name)|$($p.Sub)"
            $script:statusItem.ForeColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.AccentGreen
        }
    }
    else {
        $script:notifyIcon.Text = "A.B.S.O. - Ready"

        if ($script:statusItem) {
            $script:statusItem.Text = "Ready|No profile active"
            $script:statusItem.ForeColor = $script:Colors.AccentGreen
        }
    }

    # Update status bar
    if ($script:statusBarItem) {
        $parts = @()
        if ($script:LastAction) { $parts += $script:LastAction }
        if ($script:LastActionTime) { $parts += $script:LastActionTime }
        $backupTime = Get-LastBackupTime
        if ($backupTime -ne "Never") { $parts += "Backup: $backupTime" }
        $script:statusBarItem.Text = "  $($parts -join '  |  ')"
    }
}

# ============================================================================
# SYSTEM INFO
# ============================================================================

function Get-SystemInfo {
    $info = @{
        GPU = "Unknown GPU"
        Monitor = "Unknown"
        RefreshRate = "?"
    }

    try {
        $virtualAdapters = @(
            "Parsec", "Virtual", "Microsoft Basic", "Microsoft Remote",
            "VNC", "TeamViewer", "AnyDesk", "Citrix", "VMware", "VirtualBox", "Hyper-V"
        )

        $gpus = Get-CimInstance Win32_VideoController -ErrorAction SilentlyContinue
        $realGpu = $gpus | Where-Object {
            $name = $_.Name
            $isVirtual = $false
            foreach ($v in $virtualAdapters) {
                if ($name -like "*$v*") { $isVirtual = $true; break }
            }
            -not $isVirtual
        } | Select-Object -First 1

        if (-not $realGpu) { $realGpu = $gpus | Select-Object -First 1 }

        if ($realGpu) {
            $gpuName = $realGpu.Name -replace "NVIDIA ", "" -replace "GeForce ", "" -replace "AMD ", "" -replace "Radeon ", ""
            $info.GPU = $gpuName.Trim()
        }

        $monitor = Get-CimInstance WmiMonitorID -Namespace root/wmi -ErrorAction SilentlyContinue | Select-Object -First 1
        if ($monitor -and $monitor.UserFriendlyName) {
            $name = [System.Text.Encoding]::ASCII.GetString($monitor.UserFriendlyName).Trim([char]0)
            $info.Monitor = $name
        }

        if ($realGpu -and $realGpu.CurrentRefreshRate) {
            $info.RefreshRate = "$($realGpu.CurrentRefreshRate)Hz"
        }
    }
    catch {
        Write-TrayLog "Failed to get system info: $($_.Exception.Message)" -Level "WARN"
    }

    return $info
}

# ============================================================================
# ACTIONS
# ============================================================================

function Run-Audit {
    Write-TrayLog "Running audit..."
    Set-IconState -State "Applying"
    $script:notifyIcon.Text = "A.B.S.O. - Running Audit..."

    try {
        $tempFile = [System.IO.Path]::GetTempFileName()
        $errFile = "$tempFile.err"
        Start-Process -FilePath $script:PythonExe -ArgumentList "-m", "abso", "audit", "--json" `
            -NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `
            -RedirectStandardOutput $tempFile -RedirectStandardError $errFile

        $rawOutput = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
        $errOutput = Get-Content $errFile -Raw -ErrorAction SilentlyContinue
        Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
        Remove-Item $errFile -Force -ErrorAction SilentlyContinue
        if ($errOutput) { Write-TrayLog "Audit CLI stderr: $errOutput" -Level "WARN" }

        if ($rawOutput) {
            $json = $rawOutput | ConvertFrom-Json
            if ($json.success -and $json.data) {
                $issues = $json.data.issues
                $issueCount = if ($issues) { $issues.Count } else { 0 }
                $script:AuditIssueCount = $issueCount

                if ($issueCount -eq 0) {
                    Show-Notification -Title "A.B.S.O. Audit" -Message "No issues found - system optimized!" -Type "Info"
                    Set-IconState -State $(if ($script:activeProfile) { "Active" } else { "Idle" })
                }
                else {
                    Show-Notification -Title "A.B.S.O. Audit" -Message "$issueCount issue(s) found. Run 'abso audit' for details." -Type "Warning"
                    Set-IconState -State "Warning"
                }

                # Update audit menu item
                if ($script:auditStatusItem) {
                    if ($issueCount -gt 0) {
                        $script:auditStatusItem.Text = "      Issues Found: $issueCount"
                        $script:auditStatusItem.ForeColor = [System.Drawing.Color]::FromArgb(255, 240, 180, 60)
                        $script:auditStatusItem.Visible = $true
                    }
                    else {
                        $script:auditStatusItem.Text = "      No Issues"
                        $script:auditStatusItem.ForeColor = $script:Colors.AccentGreen
                        $script:auditStatusItem.Visible = $true
                    }
                }
            }
        }
    }
    catch {
        Write-TrayLog "Audit failed: $($_.Exception.Message)" -Level "ERROR"
        Show-Notification -Title "A.B.S.O." -Message "Audit failed: $($_.Exception.Message)" -Type "Error"
        Set-IconState -State "Error"
    }

    $script:LastAction = "Audit completed"
    $script:LastActionTime = Get-Date -Format "HH:mm"
    Update-MenuState
}

function Open-BackupsFolder {
    $backupsPath = Join-Path $script:ProjectRoot "backups"
    if (Test-Path $backupsPath) {
        try {
            Start-Process "explorer.exe" -ArgumentList $backupsPath -ErrorAction Stop
        }
        catch {
            Write-TrayLog "Failed to open backups folder: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "A.B.S.O." -Message "Failed to open folder: $($_.Exception.Message)" -Type "Error"
        }
    }
    else {
        Show-Notification -Title "A.B.S.O." -Message "No backups folder found" -Type "Warning"
    }
}

function Open-LogFile {
    if (Test-Path $script:LogFile) {
        Start-Process "notepad.exe" -ArgumentList $script:LogFile
    }
}

function Open-ConfigFolder {
    $configDir = Join-Path $env:APPDATA "ABSO"
    if (-not (Test-Path $configDir)) {
        New-Item -Path $configDir -ItemType Directory -Force | Out-Null
    }
    Start-Process "explorer.exe" -ArgumentList $configDir
}

function Open-ProfilesFolder {
    $profilesDir = Join-Path $env:USERPROFILE ".abso\profiles"
    if (-not (Test-Path $profilesDir)) {
        New-Item -ItemType Directory -Path $profilesDir -Force | Out-Null
    }
    Start-Process "explorer.exe" -ArgumentList $profilesDir
}

function Get-StartupStatus {
    $legacyShortcutPath = [System.IO.Path]::Combine(
        [Environment]::GetFolderPath("Startup"),
        "ABSO-Tray.lnk"
    )
    $installScript = Join-Path $script:ScriptDir "Install-Startup.ps1"

    # Fallback for missing installer script
    if (-not (Test-Path $installScript)) {
        $legacyInstalled = Test-Path $legacyShortcutPath
        return [PSCustomObject]@{
            installed          = $legacyInstalled
            mode               = if ($legacyInstalled) { "startup_shortcut" } else { "none" }
            task_installed     = $false
            shortcut_installed = $legacyInstalled
        }
    }

    try {
        $args = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $installScript,
            "-Status",
            "-Json"
        )
        $raw = & powershell.exe @args
        if ($LASTEXITCODE -eq 0 -and $raw) {
            return ($raw | ConvertFrom-Json)
        }

        Write-TrayLog "Get-StartupStatus fallback: installer returned empty or exit code $LASTEXITCODE" -Level "WARN"
    }
    catch {
        Write-TrayLog "Get-StartupStatus failed: $($_.Exception.Message)" -Level "WARN"
    }

    $legacyInstalled = Test-Path $legacyShortcutPath
    return [PSCustomObject]@{
        installed          = $legacyInstalled
        mode               = if ($legacyInstalled) { "startup_shortcut" } else { "none" }
        task_installed     = $false
        shortcut_installed = $legacyInstalled
    }
}

function Set-StartupMenuState {
    param([object]$StartupStatus)

    if (-not $script:startupItem) {
        return
    }

    $isInstalled = $false
    $mode = "none"

    if ($StartupStatus) {
        $isInstalled = [bool]$StartupStatus.installed
        if ($StartupStatus.mode) {
            $mode = "$($StartupStatus.mode)"
        }
    }

    $modeLabel = switch ($mode) {
        "scheduled_task" { "Task Scheduler" }
        "startup_shortcut" { "Startup Folder shortcut" }
        default { "not configured" }
    }

    $script:startupItem.Text = if ($isInstalled) { "      Disable Auto-Start" } else { "      Enable Auto-Start" }
    $script:startupItem.Checked = $isInstalled
    $script:startupItem.ToolTipText = if ($isInstalled) {
        "Start A.B.S.O. Tray when Windows starts (configured via $modeLabel)"
    }
    else {
        "Start A.B.S.O. Tray when Windows starts"
    }
}

function Toggle-Startup {
    $installScript = Join-Path $script:ScriptDir "Install-Startup.ps1"
    if (-not (Test-Path $installScript)) {
        Show-Notification -Title "A.B.S.O." -Message "Startup installer not found" -Type "Error"
        Write-TrayLog "Toggle-Startup failed: missing installer script at $installScript" -Level "ERROR"
        return
    }

    $before = Get-StartupStatus
    $operation = if ($before.installed) { "-Uninstall" } else { "-Install" }

    try {
        $args = @(
            "-NoProfile",
            "-ExecutionPolicy", "Bypass",
            "-File", $installScript,
            $operation,
            "-Json"
        )
        $raw = & powershell.exe @args
        if ($LASTEXITCODE -ne 0) {
            throw "Installer exit code $LASTEXITCODE. Output: $raw"
        }
    }
    catch {
        Show-Notification -Title "A.B.S.O." -Message "Failed to update startup registration" -Type "Error"
        Write-TrayLog "Toggle-Startup failed: $($_.Exception.Message)" -Level "ERROR"
        return
    }

    $after = Get-StartupStatus
    Set-StartupMenuState -StartupStatus $after

    if ((-not $before.installed) -and $after.installed) {
        $modeLabel = if ("$($after.mode)" -eq "scheduled_task") { "Task Scheduler" } else { "Startup Folder shortcut" }
        Show-Notification -Title "A.B.S.O." -Message "Added to Windows startup ($modeLabel)" -Type "Info"
        Write-TrayLog "Startup enabled via mode: $($after.mode)"
    }
    elseif ($before.installed -and (-not $after.installed)) {
        Show-Notification -Title "A.B.S.O." -Message "Removed from Windows startup" -Type "Info"
        Write-TrayLog "Startup disabled"
    }
    else {
        $state = if ($after.installed) { "enabled" } else { "disabled" }
        Show-Notification -Title "A.B.S.O." -Message "Startup is $state" -Type "Warning"
        Write-TrayLog "Toggle-Startup no state change detected (before=$($before.installed), after=$($after.installed))" -Level "WARN"
    }
}

function Get-LastBackupTime {
    $backupsPath = Join-Path $script:ProjectRoot "backups"
    if (Test-Path $backupsPath) {
        $latest = Get-ChildItem $backupsPath -Directory -ErrorAction SilentlyContinue |
            Sort-Object CreationTime -Descending | Select-Object -First 1
        if ($latest) {
            $age = (Get-Date) - $latest.CreationTime
            if ($age.TotalMinutes -lt 60) { return "$([int]$age.TotalMinutes)m ago" }
            elseif ($age.TotalHours -lt 24) { return "$([int]$age.TotalHours)h ago" }
            else { return "$([int]$age.TotalDays)d ago" }
        }
    }
    return "Never"
}

function Get-RecentBackups {
    <#
    .SYNOPSIS
    Gets the last N backup folders with metadata.
    #>
    param([int]$Count = 5)

    $backupsPath = Join-Path $script:ProjectRoot "backups"
    $result = @()
    if (Test-Path $backupsPath) {
        $dirs = Get-ChildItem $backupsPath -Directory -ErrorAction SilentlyContinue |
            Sort-Object CreationTime -Descending | Select-Object -First $Count
        foreach ($dir in $dirs) {
            $manifest = Join-Path $dir.FullName "manifest.json"
            $label = $dir.Name
            if (Test-Path $manifest) {
                try {
                    $mj = Get-Content $manifest -Raw | ConvertFrom-Json
                    if ($mj.profile_id) { $label = "$($mj.profile_id) - $($dir.CreationTime.ToString('MMM dd HH:mm'))" }
                    else { $label = $dir.CreationTime.ToString("MMM dd HH:mm") }
                } catch {
                    $label = $dir.CreationTime.ToString("MMM dd HH:mm")
                }
            }
            $result += @{ Path = $dir.FullName; Name = $dir.Name; Label = $label; Time = $dir.CreationTime }
        }
    }
    return $result
}

# ============================================================================
# SEARCH / FILTER
# ============================================================================

function Find-Profiles {
    <#
    .SYNOPSIS
    Fuzzy-matches profiles by search query.
    #>
    param([string]$Query)

    if (-not $Query -or $Query.Length -eq 0) {
        return $script:Profiles.Keys
    }

    $q = $Query.ToLower()
    $matches = @()

    foreach ($id in $script:Profiles.Keys) {
        $p = $script:Profiles[$id]
        $searchText = "$id $($p.Name) $($p.Sub) $($p.Cat) $($p.Desc)".ToLower()

        # Exact substring match
        if ($searchText -like "*$q*") {
            $matches += $id
            continue
        }

        # Fuzzy: check if all characters appear in order
        $qi = 0
        $matched = $true
        foreach ($char in $q.ToCharArray()) {
            $pos = $searchText.IndexOf($char, $qi)
            if ($pos -lt 0) { $matched = $false; break }
            $qi = $pos + 1
        }
        if ($matched) { $matches += $id }
    }

    return $matches
}

# ============================================================================
# MAIN
# ============================================================================

function Start-TrayApp {
    Test-SoundFilesExist | Out-Null

    if (-not (Wait-ExplorerShellReady -TimeoutSeconds 45)) {
        Write-TrayLog "Explorer shell not detected within startup wait window; continuing anyway" -Level "WARN"
    }
    else {
        # Small buffer after shell detection to reduce startup icon race conditions.
        Start-Sleep -Milliseconds 1500
    }

    # Load config
    $script:TrayConfig = Read-TrayConfig
    $script:LastAction = $null
    $script:LastActionTime = $null
    $script:AuditIssueCount = 0

    $script:notifyIcon = New-Object System.Windows.Forms.NotifyIcon
    Set-IconState -State "Idle"
    $script:notifyIcon.Text = "A.B.S.O. - Ready"
    $script:notifyIcon.Visible = $true
    Start-StartupIconSelfHeal

    # Restore startup state using the freshest candidate across state files and tray metadata.
    $script:activeProfile = $null
    $startupProfile = Resolve-StartupActiveProfile -Config $script:TrayConfig -ProfileMap $script:Profiles
    $script:TrayConfig = Set-StartupResolutionRecord -Config $script:TrayConfig -Record $startupProfile
    if ($startupProfile -and $startupProfile.status -eq "active" -and $startupProfile.id) {
        $script:activeProfile = "$($startupProfile.id)"
        $startupProfileName = if ($startupProfile.name) {
            "$($startupProfile.name)"
        }
        elseif ($script:Profiles.Contains($script:activeProfile)) {
            "$($script:Profiles[$script:activeProfile].Name)"
        }
        else {
            $script:activeProfile
        }
        $script:LastAction = "Startup restore [$($startupProfile.source)]: $startupProfileName"
        $script:LastActionTime = Get-Date -Format "HH:mm"
        Write-TrayLog "Startup restore selected active profile '$($startupProfile.id)' from '$($startupProfile.source)' (decision=$($startupProfile.decision), timestamp=$($startupProfile.timestamp))"
    }
    elseif ($startupProfile -and $startupProfile.status -eq "restored") {
        $script:LastAction = "Startup restore [$($startupProfile.source)]: no active profile"
        $script:LastActionTime = Get-Date -Format "HH:mm"
        Write-TrayLog "Startup restore selected no active profile from '$($startupProfile.source)' (decision=$($startupProfile.decision), timestamp=$($startupProfile.timestamp))"
    }
    else {
        Write-TrayLog "No previously active profile restored at startup"
    }
    $script:profileMenuItems = @()

    # Power plan crash recovery: if a gaming power plan was active when
    # the tray or system crashed, restore the pre-game plan.
    try {
        $powerStateFile = Join-Path $script:ProjectRoot ".power_switcher_state.json"
        if (Test-Path $powerStateFile) {
            $powerState = Get-Content $powerStateFile -Raw | ConvertFrom-Json
            if ($powerState.pre_game_plan_guid) {
                powercfg /setactive $powerState.pre_game_plan_guid 2>$null
                Write-TrayLog "Power plan crash recovery: restored $($powerState.pre_game_plan_guid)"
                Remove-Item $powerStateFile -Force -ErrorAction SilentlyContinue
            }
        }
    } catch {
        Write-TrayLog "Power plan crash recovery failed: $($_.Exception.Message)" -Level "WARN"
    }

    # ═══════════════════════════════════════════════════════════════════════
    # HIDDEN FORM FOR HOTKEYS (WM_HOTKEY receiver)
    # ═══════════════════════════════════════════════════════════════════════

    # Create a NativeWindow subclass to handle WM_HOTKEY messages
    Add-Type -TypeDefinition @"
using System;
using System.Windows.Forms;

public class HotkeyMessageWindow : NativeWindow {
    public event EventHandler<int> HotkeyPressed;
    private const int WM_HOTKEY = 0x0312;

    public HotkeyMessageWindow() {
        CreateParams cp = new CreateParams();
        this.CreateHandle(cp);
    }

    protected override void WndProc(ref Message m) {
        if (m.Msg == WM_HOTKEY) {
            int id = m.WParam.ToInt32();
            if (HotkeyPressed != null)
                HotkeyPressed(this, id);
        }
        base.WndProc(ref m);
    }
}
"@ -ReferencedAssemblies System.Windows.Forms -ErrorAction SilentlyContinue

    $script:HotkeyWindow = New-Object HotkeyMessageWindow

    # Also keep a hidden form for other uses
    $script:HiddenForm = New-Object System.Windows.Forms.Form
    $script:HiddenForm.Text = "ABSO_HotkeyReceiver"
    $script:HiddenForm.ShowInTaskbar = $false
    $script:HiddenForm.WindowState = [System.Windows.Forms.FormWindowState]::Minimized
    $script:HiddenForm.Visible = $false
    $script:HiddenForm.Show()
    $script:HiddenForm.Hide()

    # Register hotkeys using the NativeWindow handle
    try {
        Register-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle -Config $script:TrayConfig -Actions @{
            openMenu = {
                $mi = $script:notifyIcon.GetType().GetMethod(
                    "ShowContextMenu",
                    [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic
                )
                $mi.Invoke($script:notifyIcon, $null)
            }
            restore = {
                if ($script:activeProfile) { Restore-Settings }
            }
        }

        # Wire up the HotkeyPressed event to dispatch to registered actions
        $script:HotkeyPressedSub = Register-ObjectEvent -InputObject $script:HotkeyWindow -EventName HotkeyPressed -Action {
            $hotkeyId = $Event.SourceEventArgs
            $action = Get-HotkeyAction -HotkeyId $hotkeyId
            if ($action) {
                & $action
            }
        }

        Write-TrayLog "Global hotkeys registered"
    }
    catch {
        Write-TrayLog "Failed to register hotkeys: $($_.Exception.Message)" -Level "WARN"
    }

    # ═══════════════════════════════════════════════════════════════════════
    # CONTEXT MENU
    # ═══════════════════════════════════════════════════════════════════════

    $menu = New-Object System.Windows.Forms.ContextMenuStrip
    $menu.BackColor = $script:Colors.Background
    $menu.ForeColor = $script:Colors.Text
    $menu.ShowImageMargin = $true
    $menu.ShowCheckMargin = $false
    try {
        $menu.Renderer = New-Object DarkThemeRenderer
    }
    catch {
        $menu.Renderer = New-Object System.Windows.Forms.ToolStripProfessionalRenderer
        $menu.Renderer.RoundedEdges = $false
        Write-TrayLog "DarkThemeRenderer failed, using fallback: $($_.Exception.Message)" -Level "WARN"
    }

    # Apply DWM rounded corners and dark mode to the context menu popup
    $menu.Add_Opened({
        try {
            if ("DwmHelper" -as [type]) {
                [DwmHelper]::SetRoundedCorners($menu.Handle, 3)
                [DwmHelper]::SetDarkMode($menu.Handle)
            }
        } catch {}
    })

    # Also apply DWM to any submenu dropdowns as they open
    $menu.Add_ItemAdded({
        param($s, $e)
        $item = $e.Item
        if ($item -is [System.Windows.Forms.ToolStripMenuItem]) {
            $item.DropDown.Add_Opened({
                param($ds, $de)
                try {
                    if ("DwmHelper" -as [type]) {
                        [DwmHelper]::SetRoundedCorners($ds.Handle, 3)
                        [DwmHelper]::SetDarkMode($ds.Handle)
                    }
                } catch {}
            })
        }
    })

    # ─── HEADER ───

    $header = New-Object System.Windows.Forms.ToolStripMenuItem
    $header.Text = "  A.B.S.O.  v$($script:AppVersion)"
    $header.Enabled = $false
    $header.BackColor = $script:Colors.BackgroundDark
    $header.ForeColor = $script:Colors.AccentGold
    $header.Font = New-Object System.Drawing.Font("Segoe UI", 10, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($header) | Out-Null

    # ─── STATUS DASHBOARD ───

    $sysInfo = Get-SystemInfo

    $script:statusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:statusItem.Tag = "__hero_banner__"
    $script:statusItem.AutoSize = $false
    $script:statusItem.Height = 48
    if ($script:activeProfile) {
        $ap = $script:Profiles[$script:activeProfile]
        $script:statusItem.Text = "$($ap.Name)|$($ap.Sub)"
        $script:statusItem.ForeColor = Get-CategoryColor -Category $ap.Cat -Fallback $script:Colors.AccentGreen
    }
    else {
        $script:statusItem.Text = "Ready|No profile active"
        $script:statusItem.ForeColor = $script:Colors.AccentGreen
    }
    $script:statusItem.Enabled = $false
    $script:statusItem.BackColor = $script:Colors.BackgroundDark
    $script:statusItem.Font = New-Object System.Drawing.Font("Segoe UI", 9, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($script:statusItem) | Out-Null

    # System info line (GPU + refresh rate)
    $sysInfoText = "$($sysInfo.GPU)  |  $($sysInfo.RefreshRate)"
    $sysInfoItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $sysInfoItem.Text = $sysInfoText
    $sysInfoItem.Enabled = $false
    $sysInfoItem.BackColor = $script:Colors.BackgroundDark
    $sysInfoItem.ForeColor = [System.Drawing.Color]::FromArgb(255, 90, 90, 100)
    $sysInfoItem.Font = New-Object System.Drawing.Font("Consolas", 7.5)
    $menu.Items.Add($sysInfoItem) | Out-Null

    # Audit status item (hidden until audit is run)
    $script:auditStatusItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:auditStatusItem.Text = ""
    $script:auditStatusItem.Enabled = $false
    $script:auditStatusItem.BackColor = $script:Colors.BackgroundDark
    $script:auditStatusItem.ForeColor = $script:Colors.AccentGreen
    $script:auditStatusItem.Font = New-Object System.Drawing.Font("Segoe UI", 8)
    $script:auditStatusItem.Visible = $false
    $menu.Items.Add($script:auditStatusItem) | Out-Null

    # ─── SEARCH ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $searchBox = New-Object System.Windows.Forms.ToolStripTextBox
    $searchBox.Size = New-Object System.Drawing.Size(250, 24)
    $searchBox.BackColor = [System.Drawing.Color]::FromArgb(255, 45, 45, 50)
    $searchBox.ForeColor = $script:Colors.Text
    $searchBox.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $searchBox.ToolTipText = "Search profiles... (type to filter)"
    # Placeholder text
    $searchBox.Text = "Search profiles..."
    $searchBox.ForeColor = $script:Colors.TextDim
    $script:searchIsPlaceholder = $true

    $searchBox.Add_GotFocus({
        if ($script:searchIsPlaceholder) {
            $this.Text = ""
            $this.ForeColor = $script:Colors.Text
            $script:searchIsPlaceholder = $false
        }
    })
    $searchBox.Add_LostFocus({
        if ($this.Text -eq "") {
            $this.Text = "Search profiles..."
            $this.ForeColor = $script:Colors.TextDim
            $script:searchIsPlaceholder = $true
        }
    })
    $searchBox.Add_TextChanged({
        if (-not $script:searchIsPlaceholder) {
            $query = $this.Text
            $matchedIds = Find-Profiles -Query $query
            foreach ($item in $script:profileMenuItems) {
                $item.Visible = ($matchedIds -contains $item.Tag)
            }
            # Show/hide game group submenus based on whether any children match
            foreach ($submenuItem in $script:gameGroupSubmenus) {
                $hasVisible = $false
                foreach ($child in $submenuItem.DropDownItems) {
                    if ($child -is [System.Windows.Forms.ToolStripMenuItem] -and $child.Visible) {
                        $hasVisible = $true
                        break
                    }
                }
                $submenuItem.Visible = $hasVisible
            }
            # Show/hide category headers
            foreach ($catItem in $script:categoryHeaders) {
                $cat = $catItem.Tag
                $hasVisible = $false
                foreach ($pItem in $script:profileMenuItems) {
                    if ($pItem.Visible -and $script:Profiles[$pItem.Tag] -and $script:Profiles[$pItem.Tag].Cat -eq $cat) {
                        $hasVisible = $true
                        break
                    }
                }
                # Also check game group submenus under this category
                foreach ($submenuItem in $script:gameGroupSubmenus) {
                    if ($submenuItem.Visible -and $submenuItem.Tag -eq $cat) {
                        $hasVisible = $true
                        break
                    }
                }
                $catItem.Visible = $hasVisible
            }
        }
    })
    $menu.Items.Add($searchBox) | Out-Null

    # ─── FAVORITES ───

    $favProfiles = @()
    foreach ($favId in $script:TrayConfig.favorites) {
        if ($script:Profiles.Contains($favId)) {
            $favProfiles += $favId
        }
    }

    if ($favProfiles.Count -gt 0) {
        $favLabel = New-Object System.Windows.Forms.ToolStripMenuItem
        $favLabel.Text = "FAVORITES"
        $favLabel.Enabled = $false
        $favLabel.BackColor = $script:Colors.Background
        $favLabel.ForeColor = $script:Colors.FavoriteStar
        $favLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
        $menu.Items.Add($favLabel) | Out-Null
        $script:favSectionLabel = $favLabel

        foreach ($favId in $favProfiles) {
            $p = $script:Profiles[$favId]
            $catColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.Text
            $item = New-Object System.Windows.Forms.ToolStripMenuItem
            $item.Text = $p.Name
            $item.Tag = $favId
            $item.Image = New-CategoryBitmap -Category $p.Cat -Color $catColor
            $item.BackColor = $script:Colors.Background
            $item.ForeColor = $catColor
            $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)
            $item.ToolTipText = "$($p.Sub)`n$($p.Desc)"
            $item.Add_Click({
                param($s, $ev)
                Apply-Profile $s.Tag
            }.GetNewClosure())
            $menu.Items.Add($item) | Out-Null
            $script:profileMenuItems += $item
        }
    }

    # ─── RECENT ───

    $recentProfiles = @($script:TrayConfig.recentProfiles)
    if ($recentProfiles.Count -gt 0) {
        $recentLabel = New-Object System.Windows.Forms.ToolStripMenuItem
        $recentLabel.Text = "RECENT"
        $recentLabel.Enabled = $false
        $recentLabel.BackColor = $script:Colors.Background
        $recentLabel.ForeColor = $script:Colors.TextDim
        $recentLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7.5, [System.Drawing.FontStyle]::Bold)
        $menu.Items.Add($recentLabel) | Out-Null

        $shownRecent = 0
        foreach ($entry in $recentProfiles) {
            $rId = $entry.id
            if (-not $rId) { continue }
            # Skip if already in favorites
            if ($favProfiles -contains $rId) { continue }
            if (-not $script:Profiles.Contains($rId)) { continue }
            if ($shownRecent -ge 3) { break }

            $p = $script:Profiles[$rId]
            $catColor = Dim-Color -Color (Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.TextDim) -Alpha 200
            $item = New-Object System.Windows.Forms.ToolStripMenuItem
            $item.Text = $p.Name
            $item.Tag = $rId
            $item.Image = New-CategoryBitmap -Category $p.Cat -Color $catColor
            $item.BackColor = $script:Colors.Background
            $item.ForeColor = $catColor
            $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)
            $item.ToolTipText = "$($p.Sub) - Last: $($entry.timestamp)"
            $item.Add_Click({
                param($s, $ev)
                Apply-Profile $s.Tag
            }.GetNewClosure())
            $menu.Items.Add($item) | Out-Null
            $shownRecent++
        }
    }

    # ─── PROFILES (game submenus with sync badges) ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $profilesLabel = New-Object System.Windows.Forms.ToolStripMenuItem
    $profilesLabel.Text = "PROFILES"
    $profilesLabel.Enabled = $false
    $profilesLabel.BackColor = $script:Colors.BackgroundDark
    $profilesLabel.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 110, 130)
    $profilesLabel.Font = New-Object System.Drawing.Font("Segoe UI", 7, [System.Drawing.FontStyle]::Bold)
    $menu.Items.Add($profilesLabel) | Out-Null

    # --- Derive game groups from profile IDs ---
    # Strip known variant suffixes to get the base game identifier.
    # Order matters: longer suffixes before shorter ones that are substrings.
    $variantSuffixes = @(
        "-online-gsync", "-tournament-sim-144hz", "-console-parity", "-gsync-hdr", "-300hz-max",
        "-streaming", "-offline", "-online", "-vrr-lab", "-gsync", "-hdr", "-sdr"
    )

    function Get-GameGroup {
        param([string]$ProfileId)
        foreach ($suffix in $variantSuffixes) {
            if ($ProfileId.EndsWith($suffix)) {
                return $ProfileId.Substring(0, $ProfileId.Length - $suffix.Length)
            }
        }
        return $ProfileId
    }

    # Helper to create a profile menu item (used in both direct items and submenus)
    function New-ProfileMenuItem {
        param([string]$ProfileId, [bool]$InSubmenu = $false, [bool]$ShowBadge = $false)
        $p = $script:Profiles[$ProfileId]
        $isFav = Test-Favorite -ProfileId $ProfileId -Config $script:TrayConfig
        $catColor = Get-CategoryColor -Category $p.Cat -Fallback $script:Colors.Text

        $item = New-Object System.Windows.Forms.ToolStripMenuItem
        $item.Text = $p.Name

        # Category icon by default; sync badge overrides for variant items in submenus only
        $badgeSet = $false
        if ($ShowBadge -and $InSubmenu) {
            $sm = if ($p.SyncMode) { $p.SyncMode } else { "agnostic" }
            $badgeImg = New-SyncBadgeImage -SyncMode $sm
            if ($badgeImg) {
                $item.Image = $badgeImg
                $badgeSet = $true
            }
        }
        if (-not $badgeSet) {
            $item.Image = New-CategoryBitmap -Category $p.Cat -Color $catColor
        }

        $item.Tag = $ProfileId
        $item.BackColor = $script:Colors.Background
        $item.ForeColor = $catColor
        $item.Font = New-Object System.Drawing.Font("Segoe UI", 9)

        $tooltipText = "$($p.Sub)`n"
        if ($p.Desc) { $tooltipText += "`n$($p.Desc)" }
        if ($isFav) { $tooltipText += "`n`n[Favorited]" }
        $item.ToolTipText = $tooltipText.Trim()

        $item.Add_Click({
            param($s, $ev)
            Apply-Profile $s.Tag
        }.GetNewClosure())

        return $item
    }

    # Group non-streaming profiles by category, then by game group.
    # Streaming profiles are collected into a single flyout submenu.
    $catGameGroups = [ordered]@{}
    $streamingProfiles = @()

    foreach ($id in $script:Profiles.Keys) {
        $p = $script:Profiles[$id]
        if ($p.Cat -eq "Streaming") {
            $streamingProfiles += $id
            continue
        }
        $gameGroup = Get-GameGroup -ProfileId $id
        $cat = $p.Cat
        if (-not $catGameGroups.Contains($cat)) {
            $catGameGroups[$cat] = [ordered]@{}
        }
        if (-not $catGameGroups[$cat].Contains($gameGroup)) {
            $catGameGroups[$cat][$gameGroup] = @()
        }
        $catGameGroups[$cat][$gameGroup] += $id
    }

    $script:categoryHeaders = @()
    $script:gameGroupSubmenus = @()

    # Merge ARPG + Other into a single "Other" section
    # Build category order dynamically: use preferred order for known categories,
    # append any new user-defined categories alphabetically (exclude merged/special ones)
    $mergedExclude = @("ARPG", "Other", "Streaming")
    $preferredMergedOrder = @("Productivity", "Fighting", "Shooter")
    $mergedCategoryOrder = @()
    foreach ($cat in $preferredMergedOrder) {
        if ($catGameGroups.Contains($cat)) { $mergedCategoryOrder += $cat }
    }
    foreach ($cat in ($catGameGroups.Keys | Sort-Object)) {
        if ($mergedExclude -contains $cat) { continue }
        if ($mergedCategoryOrder -notcontains $cat) { $mergedCategoryOrder += $cat }
    }
    # Add ARPG/Other as merged
    $mergedOther = @()
    if ($catGameGroups.Contains("ARPG")) {
        foreach ($gg in $catGameGroups["ARPG"].Keys) {
            foreach ($profId in $catGameGroups["ARPG"][$gg]) { $mergedOther += $profId }
        }
    }
    if ($catGameGroups.Contains("Other")) {
        foreach ($gg in $catGameGroups["Other"].Keys) {
            foreach ($profId in $catGameGroups["Other"][$gg]) { $mergedOther += $profId }
        }
    }

    foreach ($cat in $mergedCategoryOrder) {
        if (-not $catGameGroups.Contains($cat)) { continue }

        $catColor = if ($script:CategoryColors.ContainsKey($cat)) { $script:CategoryColors[$cat] } else { $script:Colors.Text }
        $catItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $catItem.Text = $cat
        $catItem.Tag = $cat
        $catItem.Image = New-CategoryBitmap -Category $cat -Color $catColor
        $catItem.Enabled = $false
        $catItem.BackColor = $script:Colors.Background
        $catItem.ForeColor = $catColor
        $catItem.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
        $menu.Items.Add($catItem) | Out-Null
        $script:categoryHeaders += $catItem

        foreach ($gameGroup in $catGameGroups[$cat].Keys) {
            $profileIds = $catGameGroups[$cat][$gameGroup]

            if ($profileIds.Count -eq 1) {
                # Single profile — show directly with optional sync badge
                $item = New-ProfileMenuItem -ProfileId $profileIds[0] -ShowBadge $true
                $menu.Items.Add($item) | Out-Null
                $script:profileMenuItems += $item
            }
            else {
                # Multiple profiles — create a flyout submenu
                $firstProfile = $script:Profiles[$profileIds[0]]
                $submenuItem = New-Object System.Windows.Forms.ToolStripMenuItem
                $submenuItem.Text = ($firstProfile.Name -replace '(:|\s+-\s+).*$', '')
                $submenuItem.Tag = $cat
                $submenuItem.Image = New-CategoryBitmap -Category $cat -Color $catColor
                $submenuItem.BackColor = $script:Colors.Background
                $submenuItem.ForeColor = $catColor
                $submenuItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)

                foreach ($profId in $profileIds) {
                    $subItem = New-ProfileMenuItem -ProfileId $profId -InSubmenu $true -ShowBadge $true
                    $submenuItem.DropDownItems.Add($subItem) | Out-Null
                    $script:profileMenuItems += $subItem
                }

                $menu.Items.Add($submenuItem) | Out-Null
                $script:gameGroupSubmenus += $submenuItem
            }
        }
    }

    # Merged ARPG + Other category
    if ($mergedOther.Count -gt 0) {
        $otherColor = if ($script:CategoryColors.ContainsKey("Other")) { $script:CategoryColors["Other"] } else { $script:Colors.Text }
        $otherCatItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $otherCatItem.Text = "Other"
        $otherCatItem.Tag = "Other"
        $otherCatItem.Image = New-CategoryBitmap -Category "Other" -Color $otherColor
        $otherCatItem.Enabled = $false
        $otherCatItem.BackColor = $script:Colors.Background
        $otherCatItem.ForeColor = $otherColor
        $otherCatItem.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)
        $menu.Items.Add($otherCatItem) | Out-Null
        $script:categoryHeaders += $otherCatItem

        foreach ($profId in $mergedOther) {
            $item = New-ProfileMenuItem -ProfileId $profId
            $menu.Items.Add($item) | Out-Null
            $script:profileMenuItems += $item
        }
    }

    # Streaming — single flyout submenu
    if ($streamingProfiles.Count -gt 0) {
        $streamColor = if ($script:CategoryColors.ContainsKey("Streaming")) { $script:CategoryColors["Streaming"] } else { $script:Colors.Text }
        $streamingSubmenu = New-Object System.Windows.Forms.ToolStripMenuItem
        $streamingSubmenu.Text = "Streaming"
        $streamingSubmenu.Tag = "Streaming"
        $streamingSubmenu.Image = New-CategoryBitmap -Category "Streaming" -Color $streamColor
        $streamingSubmenu.BackColor = $script:Colors.Background
        $streamingSubmenu.ForeColor = $streamColor
        $streamingSubmenu.Font = New-Object System.Drawing.Font("Segoe UI", 8.5, [System.Drawing.FontStyle]::Bold)

        foreach ($profId in $streamingProfiles) {
            $subItem = New-ProfileMenuItem -ProfileId $profId -InSubmenu $true
            $streamingSubmenu.DropDownItems.Add($subItem) | Out-Null
            $script:profileMenuItems += $subItem
        }

        $menu.Items.Add($streamingSubmenu) | Out-Null
        $script:gameGroupSubmenus += $streamingSubmenu
    }

    # ─── ACTIONS (flyout submenu) ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $actionsMenu = New-Object System.Windows.Forms.ToolStripMenuItem
    $actionsMenu.Text = "  Actions"
    $actionsMenu.BackColor = $script:Colors.Background
    $actionsMenu.ForeColor = $script:Colors.AccentAmber
    $actionsMenu.Font = New-Object System.Drawing.Font("Segoe UI", 9)

    # Restore Previous
    $script:restoreItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:restoreItem.Text = "Restore Previous Settings"
    $script:restoreItem.Enabled = $false
    $script:restoreItem.BackColor = $script:Colors.Background
    $script:restoreItem.ForeColor = $script:Colors.AccentAmber
    $script:restoreItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $script:restoreItem.Image = New-ActionBitmap -Action "Restore" -Color $script:Colors.AccentAmber
    $script:restoreItem.ToolTipText = "Restore the last backup before profile was applied"
    $script:restoreItem.Add_Click({ Restore-Settings })
    $actionsMenu.DropDownItems.Add($script:restoreItem) | Out-Null

    # Run Audit
    $auditItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $auditItem.Text = "Run System Audit"
    $auditItem.BackColor = $script:Colors.Background
    $auditItem.ForeColor = $script:Colors.AccentBlue
    $auditItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $auditItem.Image = New-ActionBitmap -Action "Audit" -Color $script:Colors.AccentBlue
    $auditItem.ToolTipText = "Scan system for optimization issues"
    $auditItem.Add_Click({ Run-Audit })
    $actionsMenu.DropDownItems.Add($auditItem) | Out-Null

    # Backups submenu (nested inside Actions)
    $backupTime = Get-LastBackupTime
    $backupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $backupsItem.Text = "Backups ($backupTime)"
    $backupsItem.BackColor = $script:Colors.Background
    $backupsItem.ForeColor = $script:Colors.AccentPurple
    $backupsItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $backupsItem.Image = New-ActionBitmap -Action "Backups" -Color $script:Colors.AccentPurple

    $openBackupsItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $openBackupsItem.Text = "Open Backups Folder"
    $openBackupsItem.BackColor = $script:Colors.Background
    $openBackupsItem.ForeColor = $script:Colors.Text
    $openBackupsItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $openBackupsItem.Add_Click({ Open-BackupsFolder })
    $backupsItem.DropDownItems.Add($openBackupsItem) | Out-Null

    $backupsItem.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $recentBackups = Get-RecentBackups -Count 5
    foreach ($backup in $recentBackups) {
        $bItem = New-Object System.Windows.Forms.ToolStripMenuItem
        $bItem.Text = $backup.Label
        $bItem.Tag = $backup.Name
        $bItem.BackColor = $script:Colors.Background
        $bItem.ForeColor = $script:Colors.TextDim
        $bItem.Font = New-Object System.Drawing.Font("Consolas", 8)
        $bItem.ToolTipText = "Click to restore this backup"
        $capturedName = $backup.Name
        $bItem.Add_Click({
            $script:notifyIcon.Text = "A.B.S.O. - Restoring..."
            try {
                $tf = [System.IO.Path]::GetTempFileName()
                Start-Process -FilePath $script:PythonExe -ArgumentList "-m", "abso", "restore", $capturedName, "--json" `
                    -NoNewWindow -Wait -WorkingDirectory $script:ProjectRoot `
                    -RedirectStandardOutput $tf
                $out = Get-Content $tf -Raw -ErrorAction SilentlyContinue
                Remove-Item $tf -Force -ErrorAction SilentlyContinue
                if ($out) {
                    $j = $out | ConvertFrom-Json
                    if ($j.success) {
                        Show-Notification -Title "A.B.S.O." -Message "Restored from: $capturedName" -Type "Info"
                        $script:activeProfile = $null
                        Set-IconState -State "Idle"
                        Update-MenuState
                    }
                }
            } catch {
                Show-Notification -Title "A.B.S.O." -Message "Restore failed" -Type "Error"
            }
        }.GetNewClosure())
        $backupsItem.DropDownItems.Add($bItem) | Out-Null
    }

    $actionsMenu.DropDownItems.Add($backupsItem) | Out-Null

    $actionsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Toggle Quick Panel
    $quickPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $quickPanelItem.Text = "Quick Panel"
    $quickPanelItem.BackColor = $script:Colors.Background
    $quickPanelItem.ForeColor = $script:Colors.AccentGreen
    $quickPanelItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $quickPanelItem.Image = New-ActionBitmap -Action "QuickPanel" -Color $script:Colors.AccentGreen
    $quickPanelItem.ToolTipText = "Toggle floating quick-access panel"
    $quickPanelItem.Checked = $script:TrayConfig.showQuickPanel
    $quickPanelItem.Add_Click({
        if ($script:QuickPanelVisible) {
            Close-QuickPanel
            $script:TrayConfig.showQuickPanel = $false
        }
        else {
            Show-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -OnApply { param($id) Apply-Profile $id }
            $script:TrayConfig.showQuickPanel = $true
        }
        $quickPanelItem.Checked = $script:TrayConfig.showQuickPanel
        Save-TrayConfig $script:TrayConfig
    })
    $actionsMenu.DropDownItems.Add($quickPanelItem) | Out-Null

    $actionsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Refresh Profiles
    $refreshProfilesItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $refreshProfilesItem.Text = "Refresh Profiles"
    $refreshProfilesItem.BackColor = $script:Colors.Background
    $refreshProfilesItem.ForeColor = $script:Colors.AccentBlue
    $refreshProfilesItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $refreshProfilesItem.Image = New-ActionBitmap -Action "Audit" -Color $script:Colors.AccentBlue
    $refreshProfilesItem.ToolTipText = "Reload profiles from CLI catalog and user profiles"
    $refreshProfilesItem.Add_Click({
        try {
            Initialize-ProfilesFromCliCatalog
            Show-Notification -Title "A.B.S.O." -Message "Profiles refreshed ($($script:Profiles.Count) profiles loaded)" -Type "Info"
            Write-TrayLog "Profiles refreshed via menu ($($script:Profiles.Count) profiles)"
        }
        catch {
            Write-TrayLog "Failed to refresh profiles: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "A.B.S.O." -Message "Failed to refresh profiles" -Type "Error"
        }
    })
    $actionsMenu.DropDownItems.Add($refreshProfilesItem) | Out-Null

    # Open Profiles Folder
    $openProfilesItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $openProfilesItem.Text = "Open Profiles Folder"
    $openProfilesItem.BackColor = $script:Colors.Background
    $openProfilesItem.ForeColor = $script:Colors.TextDim
    $openProfilesItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $openProfilesItem.ToolTipText = "Open user profiles folder in Explorer"
    $openProfilesItem.Add_Click({ Open-ProfilesFolder })
    $actionsMenu.DropDownItems.Add($openProfilesItem) | Out-Null

    $actionsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Clear Standby List (ISLC equivalent)
    $clearMemoryItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $clearMemoryItem.Text = "Clear Standby List"
    $clearMemoryItem.BackColor = $script:Colors.Background
    $clearMemoryItem.ForeColor = $script:Colors.AccentBlue
    $clearMemoryItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $clearMemoryItem.ToolTipText = "Purge cached memory pages (ISLC equivalent)"
    $clearMemoryItem.Add_Click({
        try {
            Write-TrayLog "Clearing standby list..."
            $tempFile = [System.IO.Path]::GetTempFileName()
            $proc = Start-Process -FilePath $script:PythonExe `
                -ArgumentList "-m", "abso", "memory-clear", "--json" `
                -NoNewWindow -PassThru -WorkingDirectory $script:ProjectRoot `
                -RedirectStandardOutput $tempFile
            $proc.WaitForExit(15000)
            if (-not $proc.HasExited) { $proc.Kill() }
            $proc.Dispose()
            $raw = Get-Content $tempFile -Raw -ErrorAction SilentlyContinue
            Remove-Item $tempFile -Force -ErrorAction SilentlyContinue
            if ($raw) {
                $json = $raw | ConvertFrom-Json
                if ($json.success -and $json.data) {
                    $freed = $json.data.freed_mb
                    Show-Notification -Title "A.B.S.O." -Message "Standby list cleared. Freed ~${freed}MB" -Type "Success"
                    Write-TrayLog "Standby list cleared: freed ${freed}MB"
                } else {
                    Show-Notification -Title "A.B.S.O." -Message "Standby clear failed" -Type "Error"
                }
            }
        } catch {
            Write-TrayLog "Clear standby failed: $($_.Exception.Message)" -Level "ERROR"
            Show-Notification -Title "A.B.S.O." -Message "Standby clear failed: $($_.Exception.Message)" -Type "Error"
        }
    })
    $actionsMenu.DropDownItems.Add($clearMemoryItem) | Out-Null

    $menu.Items.Add($actionsMenu) | Out-Null

    # ─── SETTINGS (flyout submenu) ───

    $settingsMenu = New-Object System.Windows.Forms.ToolStripMenuItem
    $settingsMenu.Text = "  Settings"
    $settingsMenu.BackColor = $script:Colors.Background
    $settingsMenu.ForeColor = $script:Colors.Text
    $settingsMenu.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $settingsMenu.Image = New-ActionBitmap -Action "Settings" -Color $script:Colors.Text

    # Auto-Start toggle
    $startupStatus = Get-StartupStatus
    $script:startupItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:startupItem.BackColor = $script:Colors.Background
    $script:startupItem.ForeColor = $script:Colors.Text
    $script:startupItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    Set-StartupMenuState -StartupStatus $startupStatus
    $script:startupItem.Add_Click({ Toggle-Startup })
    $settingsMenu.DropDownItems.Add($script:startupItem) | Out-Null

    # Notifications toggle
    $script:notifyToggle = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:notifyToggle.Text = "Notifications"
    $script:notifyToggle.Checked = $script:EnableBalloonNotifications
    $script:notifyToggle.BackColor = $script:Colors.Background
    $script:notifyToggle.ForeColor = $script:Colors.Text
    $script:notifyToggle.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $script:notifyToggle.ToolTipText = "Toggle balloon notifications"
    $script:notifyToggle.Add_Click({
        $script:EnableBalloonNotifications = -not $script:EnableBalloonNotifications
        $script:notifyToggle.Checked = $script:EnableBalloonNotifications
        $state = if ($script:EnableBalloonNotifications) { "enabled" } else { "disabled" }
        Write-TrayLog "Notifications $state"
    })
    $settingsMenu.DropDownItems.Add($script:notifyToggle) | Out-Null

    # Sound toggle
    $soundToggle = New-Object System.Windows.Forms.ToolStripMenuItem
    $soundToggle.Text = "Sound Effects"
    $soundToggle.Checked = $script:TrayConfig.soundEnabled
    $soundToggle.BackColor = $script:Colors.Background
    $soundToggle.ForeColor = $script:Colors.Text
    $soundToggle.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $soundToggle.ToolTipText = "Toggle sound effects"
    $soundToggle.Add_Click({
        $script:TrayConfig.soundEnabled = -not $script:TrayConfig.soundEnabled
        $soundToggle.Checked = $script:TrayConfig.soundEnabled
        Save-TrayConfig $script:TrayConfig
        Write-TrayLog "Sound effects: $($script:TrayConfig.soundEnabled)"
    })
    $settingsMenu.DropDownItems.Add($soundToggle) | Out-Null

    $settingsMenu.DropDownItems.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Open Settings Panel
    $settingsPanelItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $settingsPanelItem.Text = "Open Settings..."
    $settingsPanelItem.BackColor = $script:Colors.Background
    $settingsPanelItem.ForeColor = $script:Colors.Text
    $settingsPanelItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $settingsPanelItem.Add_Click({
        Show-SettingsPanel -Config $script:TrayConfig -OnSave {
            param($cfg)
            $script:TrayConfig = $cfg
            Write-TrayLog "Settings saved"
        }
    })
    $settingsMenu.DropDownItems.Add($settingsPanelItem) | Out-Null

    # View Log
    $logItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $logItem.Text = "View Log File"
    $logItem.BackColor = $script:Colors.Background
    $logItem.ForeColor = $script:Colors.TextDim
    $logItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $logItem.ToolTipText = $script:LogFile
    $logItem.Add_Click({ Open-LogFile })
    $settingsMenu.DropDownItems.Add($logItem) | Out-Null

    # Open Config Folder
    $configFolderItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $configFolderItem.Text = "Open Config Folder"
    $configFolderItem.BackColor = $script:Colors.Background
    $configFolderItem.ForeColor = $script:Colors.TextDim
    $configFolderItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $configFolderItem.Add_Click({ Open-ConfigFolder })
    $settingsMenu.DropDownItems.Add($configFolderItem) | Out-Null

    $menu.Items.Add($settingsMenu) | Out-Null

    # ─── STATUS BAR ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    $script:statusBarItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $script:statusBarItem.Text = "  Ready"
    $script:statusBarItem.Enabled = $false
    $script:statusBarItem.BackColor = $script:Colors.BackgroundDark
    $script:statusBarItem.ForeColor = [System.Drawing.Color]::FromArgb(255, 100, 100, 110)
    $script:statusBarItem.Font = New-Object System.Drawing.Font("Consolas", 7.5)
    $menu.Items.Add($script:statusBarItem) | Out-Null

    # ─── EXIT SECTION ───

    $menu.Items.Add((New-Object System.Windows.Forms.ToolStripSeparator)) | Out-Null

    # Restart
    $restartItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $restartItem.Text = "  Restart Tray"
    $restartItem.BackColor = $script:Colors.Background
    $restartItem.ForeColor = $script:Colors.TextDim
    $restartItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $restartItem.Add_Click({
        Set-RestartSuccessSoundMarker
        if ($script:HotkeyWindow) { Unregister-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle }
        Close-QuickPanel
        Close-ProgressOverlay
        $script:notifyIcon.Visible = $false
        if ($script:mutex) {
            try { $script:mutex.ReleaseMutex() } catch {}
            $script:mutex.Close()
            $script:mutex = $null
        }
        # Brief delay to ensure mutex is fully released before new instance acquires it
        Start-Sleep -Milliseconds 300
        $vbsPath = Join-Path $script:ScriptDir "ABSO-Tray.vbs"
        if (Test-Path $vbsPath) {
            Start-Process "wscript.exe" -ArgumentList "`"$vbsPath`"" -WindowStyle Hidden
        }
        else {
            Start-Process powershell.exe -ArgumentList "-NoProfile -ExecutionPolicy Bypass -WindowStyle Hidden -File `"$PSCommandPath`"" -WindowStyle Hidden
        }
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($restartItem) | Out-Null

    # About
    $aboutItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $aboutItem.Text = "  About A.B.S.O."
    $aboutItem.BackColor = $script:Colors.Background
    $aboutItem.ForeColor = $script:Colors.TextDim
    $aboutItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $aboutItem.Add_Click({
        [System.Windows.Forms.MessageBox]::Show(
            "A.B.S.O. v$($script:AppVersion)`n`nAdaptive Battle Station Optimizer`n`nWindows 11 Gaming Optimization Tool`nSingle-instance system tray application`n`nHotkeys:`n  $($script:TrayConfig.hotkeys.openMenu) - Open Menu`n  $($script:TrayConfig.hotkeys.restore) - Restore Settings",
            "About A.B.S.O.",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Information
        )
    })
    $menu.Items.Add($aboutItem) | Out-Null

    # Exit
    $exitItem = New-Object System.Windows.Forms.ToolStripMenuItem
    $exitItem.Text = "  Exit"
    $exitItem.BackColor = $script:Colors.Background
    $exitItem.ForeColor = $script:Colors.TextDim
    $exitItem.Font = New-Object System.Drawing.Font("Segoe UI", 9)
    $exitItem.Image = New-ActionBitmap -Action "Exit" -Color $script:Colors.TextDim
    $exitItem.Add_Click({
        if ($script:HotkeyWindow) { Unregister-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle }
        Close-QuickPanel
        Close-ProgressOverlay
        $script:notifyIcon.Visible = $false
        [System.Windows.Forms.Application]::Exit()
    })
    $menu.Items.Add($exitItem) | Out-Null

    $script:notifyIcon.ContextMenuStrip = $menu
    Update-MenuState
    Set-IconState -State $(if ($script:activeProfile) { "Active" } else { "Idle" })

    # ─── LEFT-CLICK SHOWS MENU ───

    $script:notifyIcon.Add_Click({
        param($s, $ev)
        if ($ev.Button -eq [System.Windows.Forms.MouseButtons]::Left) {
            $mi = $script:notifyIcon.GetType().GetMethod(
                "ShowContextMenu",
                [System.Reflection.BindingFlags]::Instance -bor [System.Reflection.BindingFlags]::NonPublic
            )
            $mi.Invoke($script:notifyIcon, $null)
        }
    })

    # ─── DOUBLE-CLICK: APPLY LAST FAVORITE ───

    $script:notifyIcon.Add_DoubleClick({
        param($s, $ev)
        if ($script:TrayConfig.favorites.Count -gt 0) {
            $lastFav = $script:TrayConfig.favorites[0]
            if ($script:Profiles.Contains($lastFav)) {
                Apply-Profile $lastFav
            }
        }
    })

    # ─── DEFAULT PROFILE (notify only, do not auto-apply) ───

    if (-not $script:activeProfile -and $script:TrayConfig.defaultProfile -and $script:Profiles.Contains($script:TrayConfig.defaultProfile)) {
        $defProfile = $script:Profiles[$script:TrayConfig.defaultProfile]
        Write-TrayLog "Default profile available: $($script:TrayConfig.defaultProfile) (not auto-applying)"
        Show-Notification -Title "A.B.S.O." -Message "Default profile ready: $($defProfile.Name). Right-click to apply." -Type "Info"
    }

    # ─── SHOW QUICK PANEL IF ENABLED ───

    if ($script:TrayConfig.showQuickPanel -and $script:TrayConfig.favorites.Count -gt 0) {
        Show-QuickPanel -Favorites $script:TrayConfig.favorites -Profiles $script:Profiles -ActiveProfile $script:activeProfile -OnApply { param($id) Apply-Profile $id }
    }

    # Only play restart sound once the new tray instance has fully initialized.
    Invoke-RestartSuccessSoundIfPending

    [System.Windows.Forms.Application]::Run()
    $script:notifyIcon.Visible = $false
    $script:notifyIcon.Dispose()
}

# ============================================================================
# RUN
# ============================================================================

try {
    Write-TrayLog "ABSO Tray starting (PID: $PID) v$($script:AppVersion)"
    Start-TrayApp
    Write-TrayLog "ABSO Tray exiting normally"
}
catch {
    $fatal = $_.Exception.Message
    Write-TrayLog "ABSO Tray fatal startup/runtime error: $fatal" -Level "ERROR"
    try {
        [System.Windows.Forms.MessageBox]::Show(
            "A.B.S.O. Tray encountered a fatal error and exited.`n`n$fatal`n`nSee log: $($script:LogFile)",
            "A.B.S.O.",
            [System.Windows.Forms.MessageBoxButtons]::OK,
            [System.Windows.Forms.MessageBoxIcon]::Error
        ) | Out-Null
    }
    catch {}
}
finally {
    if ($script:StartupIconHealTimer) {
        try { $script:StartupIconHealTimer.Stop() } catch {}
        try { $script:StartupIconHealTimer.Dispose() } catch {}
    }
    if ($script:ApplyAnimTimer) {
        $script:ApplyAnimTimer.Stop()
        $script:ApplyAnimTimer.Dispose()
    }
    # Unregister event subscriptions
    if ($script:MediaEndedSub) {
        try { Unregister-Event -SubscriptionId $script:MediaEndedSub.Id -ErrorAction SilentlyContinue } catch {}
    }
    if ($script:HotkeyPressedSub) {
        try { Unregister-Event -SubscriptionId $script:HotkeyPressedSub.Id -ErrorAction SilentlyContinue } catch {}
    }
    Close-ThemedToast
    Close-ProgressOverlay
    Close-QuickPanel
    if ($script:notifyIcon) {
        $script:notifyIcon.Visible = $false
        try { $script:notifyIcon.Dispose() } catch {}
    }
    if ($script:HotkeyWindow) {
        try { Unregister-GlobalHotkeys -WindowHandle $script:HotkeyWindow.Handle } catch {}
        try { $script:HotkeyWindow.DestroyHandle() } catch {}
    }
    if ($script:HiddenForm) {
        $script:HiddenForm.Dispose()
    }
    if ($script:MediaPlayer) {
        try { $script:MediaPlayer.Close() } catch {}
        $script:MediaPlayer = $null
    }
    if ($script:FontNormal) {
        try { $script:FontNormal.Dispose() } catch {}
    }
    if ($script:FontBold) {
        try { $script:FontBold.Dispose() } catch {}
    }
    if ($script:mutex) {
        try { $script:mutex.ReleaseMutex() } catch {}
        $script:mutex.Close()
        $script:mutex = $null
    }
}
